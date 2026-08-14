"""Authenticated Codex App Server lifecycle adapter.

This module is intentionally a host adapter, not a scheduler.  It launches one
exact local ``codex`` executable over the documented stdio JSONL transport,
persists only execution-local adoption evidence, and reports lifecycle facts.
It never decides that a DAG is complete and never constructs controller
fixed-point evidence.

Protocol source: https://developers.openai.com/codex/app-server (retrieved
2026-08-14).  The implementation uses the stable initialize/initialized,
thread start/read/list/resume/name/archive, and turn start/steer/interrupt
methods plus turn lifecycle notifications described there.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import queue
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Protocol, TextIO

APP_SERVER_HOST_ADAPTER_KIND = "hive-mind-codex-app-server-host-v1"
APP_SERVER_HOST_ADAPTER_VERSION = 1

_CAPABILITY_KIND = "hive-mind-host-lifecycle-capability-v1"
_IDENTITY_KIND = "hive-mind-codex-app-server-identity-v1"
_THREAD_KIND = "hive-mind-codex-app-server-thread-v1"
_MESSAGE_KIND = "hive-mind-codex-app-server-message-v1"
_SIDECAR_KIND = "hive-mind-codex-app-server-sidecar-v1"
_EFFECT_OBSERVATION_KIND = "hive-mind-host-effect-reconciliation-observation-v1"
_OBSERVATION_KIND = "hive-mind-authenticated-host-lifecycle-observation-v1"
_RECONCILIATION_KIND = "hive-mind-host-lifecycle-reconciliation-v1"
_TASK_LIFECYCLE_OBSERVATION_KIND = "hive-mind-host-lifecycle-observation-v1"
_STALE_TEMPORARY_KIND = "hive-mind-app-server-stale-temporary-v1"

_HOST_BINDING_KIND = "hive-mind-host-task-binding-v1"
_HOST_EVENT_KIND = "hive-mind-host-event-v1"
_HOST_ACK_KIND = "hive-mind-host-message-ack-v1"
_HOST_SIDECAR_BINDING_KIND = "hive-mind-host-sidecar-binding-v1"
_HOST_SIDECAR_EVENT_KIND = "hive-mind-host-sidecar-event-v1"
_HOST_SIDECAR_ACK_KIND = "hive-mind-host-sidecar-message-ack-v1"

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_MAX_LINE_BYTES = 4 * 1024 * 1024
_MAX_TEXT = 1_000_000
_TERMINAL_TURN_STATES = frozenset({"completed", "failed", "interrupted"})
_THREAD_STATES = frozenset(
    {
        "PREPARED",
        "ATTEMPTED",
        "THREAD_STARTED",
        "NAMED",
        "BOUND",
        "RECOVERY_REQUIRED",
        "ARCHIVED",
    }
)
_THREAD_TRANSITIONS = {
    "PREPARED": frozenset({"ATTEMPTED", "NAMED", "RECOVERY_REQUIRED"}),
    "ATTEMPTED": frozenset({"THREAD_STARTED", "RECOVERY_REQUIRED"}),
    "THREAD_STARTED": frozenset({"NAMED", "RECOVERY_REQUIRED"}),
    "NAMED": frozenset({"BOUND", "RECOVERY_REQUIRED"}),
    "BOUND": frozenset({"ARCHIVED"}),
    "RECOVERY_REQUIRED": frozenset({"RECOVERY_REQUIRED", "NAMED"}),
    "ARCHIVED": frozenset(),
}

_SAFE_ENVIRONMENT = frozenset(
    {
        "APPDATA",
        "CODEX_HOME",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "HOME",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "LOGNAME",
        "NO_PROXY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
        "USERPROFILE",
        "WINDIR",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    }
)


class AppServerHostError(RuntimeError):
    """The local App Server lifecycle could not be authenticated or reconciled."""


class AppServerProtocolError(AppServerHostError):
    """The stdio peer violated the bounded JSON-RPC contract."""


class _Process(Protocol):
    stdin: TextIO | None
    stdout: TextIO | None
    stderr: TextIO | None

    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


ProcessFactory = Callable[[Sequence[str], Path, Mapping[str, str]], _Process]
VersionProbe = Callable[[Path, Mapping[str, str]], str]
SchemaProbe = Callable[[Path, Mapping[str, str]], Mapping[str, str]]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _now_text(clock: Callable[[], datetime]) -> str:
    value = clock()
    if value.tzinfo is None:
        raise AppServerHostError("host clock must return an aware datetime")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AppServerHostError(f"{label} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise AppServerHostError(
            f"{label} must be a canonical UTC timestamp"
        ) from error
    if parsed.tzinfo is None or _now_text(lambda: parsed) != value:
        raise AppServerHostError(f"{label} must be a canonical UTC timestamp")
    return parsed.astimezone(UTC)


def _require_text(value: object, label: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AppServerHostError(f"{label} must be bounded non-empty text")
    return value


def _require_digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise AppServerHostError(f"{label} must be an exact SHA-256 identity")
    return value


def _no_duplicate_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AppServerProtocolError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise AppServerProtocolError(f"non-finite JSON constant: {value}")


def _strict_json(data: bytes | str, label: str) -> object:
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise AppServerProtocolError(f"{label} is not UTF-8") from error
    else:
        text = data
    try:
        return json.loads(
            text,
            object_pairs_hook=_no_duplicate_object,
            parse_constant=_reject_constant,
        )
    except AppServerProtocolError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise AppServerProtocolError(f"{label} is not strict JSON") from error


def _is_link_like(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        junction = getattr(path, "is_junction", None)
        return bool(callable(junction) and junction())
    except OSError as error:
        raise AppServerHostError(f"cannot inspect path {path}: {error}") from error


def _reject_link_components(path: Path, *, label: str) -> Path:
    absolute = path.absolute()
    parts = absolute.parts
    if not parts:
        raise AppServerHostError(f"{label} path is empty")
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        if current.exists() and _is_link_like(current):
            raise AppServerHostError(f"{label} path uses a link: {current}")
    return absolute


def _fsync_directory(path: Path) -> None:
    """Durably publish a directory entry on POSIX and Windows."""

    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return
    # Windows does not support FlushFileBuffers on a directory handle.  The
    # write-through MoveFileEx transition in ``_atomic_write`` is the durable
    # directory-entry primitive on that platform.
    del path


def _replace_write_through(source: Path, target: Path) -> None:
    if os.name != "nt":
        os.replace(source, target)
        _fsync_directory(target.parent)
        return
    import ctypes
    from ctypes import wintypes

    move = ctypes.windll.kernel32.MoveFileExW
    move.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    move.restype = wintypes.BOOL
    # MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH
    if not move(str(source), str(target), 0x1 | 0x8):
        error = ctypes.get_last_error()
        raise AppServerHostError(
            f"cannot durably replace App Server evidence ({error}): {target}"
        )


def _atomic_write(path: Path, value: Mapping[str, object]) -> None:
    parent = _reject_link_components(path.parent, label="App Server evidence directory")
    parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(parent, label="App Server evidence directory")
    if path.exists() and _is_link_like(path):
        raise AppServerHostError("App Server evidence path uses a link")
    payload = _canonical(dict(value)) + b"\n"
    # A PID/thread-derived name can be reused after a crash and turn a harmless
    # orphan into a permanent O_EXCL wedge.  A cryptographically random private
    # name makes every retry independent; startup separately quarantines stale
    # private files without ever treating them as installed authority.
    temporary = parent / (f".atomic.{path.name}.{secrets.token_hex(16)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_write_through(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _read_sealed(path: Path, *, kind: str, fields: frozenset[str]) -> dict[str, object]:
    if not path.is_file() or _is_link_like(path):
        raise AppServerHostError(f"sealed App Server evidence is missing: {path}")
    raw = path.read_bytes()
    value = _strict_json(raw, str(path))
    if not isinstance(value, dict) or frozenset(value) != fields:
        raise AppServerHostError(
            f"sealed App Server evidence schema is invalid: {path}"
        )
    material = dict(value)
    record_id = material.pop("record_id", None)
    if value.get("schema_version") != 1 or value.get("kind") != kind:
        raise AppServerHostError(f"sealed App Server evidence kind is invalid: {path}")
    if record_id != _digest(material):
        raise AppServerHostError(
            f"sealed App Server evidence digest is invalid: {path}"
        )
    if raw != _canonical(value) + b"\n":
        raise AppServerHostError(f"sealed App Server evidence is noncanonical: {path}")
    return value


_STALE_TEMPORARY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "source_relative_path",
        "payload_digest",
        "payload_bytes",
        "quarantine_blob",
        "quarantined_at",
        "record_id",
    }
)


def _write_immutable_blob(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(path.parent, label="App Server quarantine")
    if path.exists():
        if _is_link_like(path) or not path.is_file() or path.read_bytes() != payload:
            raise AppServerHostError(
                "App Server stale-temporary quarantine blob conflicts"
            )
        return
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(path.parent)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
        raise


def _reconcile_stale_atomic_temporaries(
    root: Path,
    directories: Sequence[Path],
    *,
    clock: Callable[[], datetime],
    minimum_age_seconds: float = 300.0,
) -> None:
    """Quarantine abandoned atomic-write bytes without installing them as truth."""

    root = _reject_link_components(root, label="App Server evidence root")
    quarantine = root / "stale-temporary-quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    _reject_link_components(quarantine, label="App Server stale-temporary quarantine")

    # Receipt-write temporaries are reconstructible because their immutable raw
    # blob is installed first.  Remove only stale regular files here, then scan
    # authority directories and preserve their exact bytes plus a sealed receipt.
    now_seconds = time.time()
    for candidate in quarantine.glob(".atomic.*.tmp"):
        if _is_link_like(candidate) or not candidate.is_file():
            raise AppServerHostError(
                "App Server quarantine contains a non-regular temporary"
            )
        if now_seconds - candidate.stat().st_mtime >= minimum_age_seconds:
            candidate.unlink()
            _fsync_directory(quarantine)

    unique_directories = {Path(item).absolute() for item in directories}
    for directory in sorted(unique_directories, key=lambda item: str(item).casefold()):
        _reject_link_components(directory, label="App Server evidence directory")
        if not directory.is_dir() or directory == quarantine:
            continue
        for candidate in sorted(directory.glob(".*.tmp")):
            if _is_link_like(candidate) or not candidate.is_file():
                raise AppServerHostError(
                    "App Server evidence contains a non-regular temporary"
                )
            if now_seconds - candidate.stat().st_mtime < minimum_age_seconds:
                continue
            payload = candidate.read_bytes()
            payload_digest = _bytes_digest(payload)
            blob_name = payload_digest.removeprefix("sha256:") + ".blob"
            blob_path = quarantine / blob_name
            _write_immutable_blob(blob_path, payload)
            source_relative = candidate.relative_to(root).as_posix()
            receipt_key = _digest(
                {
                    "source_relative_path": source_relative,
                    "payload_digest": payload_digest,
                }
            ).removeprefix("sha256:")
            receipt_path = quarantine / f"{receipt_key}.json"
            if receipt_path.exists():
                receipt = _read_sealed(
                    receipt_path,
                    kind=_STALE_TEMPORARY_KIND,
                    fields=_STALE_TEMPORARY_FIELDS,
                )
                if (
                    receipt.get("source_relative_path") != source_relative
                    or receipt.get("payload_digest") != payload_digest
                    or receipt.get("payload_bytes") != len(payload)
                    or receipt.get("quarantine_blob") != blob_name
                ):
                    raise AppServerHostError(
                        "App Server stale-temporary receipt conflicts"
                    )
            else:
                material: dict[str, object] = {
                    "schema_version": 1,
                    "kind": _STALE_TEMPORARY_KIND,
                    "source_relative_path": source_relative,
                    "payload_digest": payload_digest,
                    "payload_bytes": len(payload),
                    "quarantine_blob": blob_name,
                    "quarantined_at": _now_text(clock),
                }
                _atomic_write(
                    receipt_path,
                    {**material, "record_id": _digest(material)},
                )
            candidate.unlink()
            _fsync_directory(directory)


_THREAD_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "idempotency_key",
        "adoption_token",
        "title",
        "prompt_digest",
        "baseline_thread_ids",
        "unobserved_thread_ids",
        "state",
        "thread_id",
        "turn_id",
        "created_at",
        "updated_at",
        "transition_index",
        "previous_record_id",
        "record_id",
    }
)

_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "machine_user_id",
        "provider_identity_digest",
        "adapter_module_path",
        "adapter_module_digest",
        "launcher_path",
        "launcher_digest",
        "cli_module_path",
        "cli_module_digest",
        "executable_path",
        "executable_digest",
        "executable_version",
        "schema_bundle_digest",
        "thread_start_schema_digest",
        "turn_start_schema_digest",
        "environment_root_digest",
        "behavior_environment_digest",
        "provider_config_digest",
        "execution_config_digest",
        "account_identity_digest",
        "effective_model",
        "effective_model_provider",
        "transport",
        "initialize_result_digest",
        "created_at",
        "record_id",
    }
)

_MESSAGE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "thread_id",
        "idempotency_key",
        "message_digest",
        "turn_id",
        "state",
        "created_at",
        "record_id",
    }
)

_SIDECAR_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "sidecar_id",
        "thread_id",
        "parent_launch_instruction_id",
        "token_budget",
        "state",
        "created_at",
        "record_id",
    }
)

_EFFECT_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "outcome",
        "external_identity",
        "result",
        "unobserved_host_lifecycle_items",
        "observed_at",
        "record_id",
    }
)

_EFFECT_EXTERNAL_IDENTITY_KIND = "hive-mind-host-effect-external-identity-v1"
_EFFECT_EXTERNAL_IDENTITY_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "external_id",
        "record_id",
    }
)
_UNOBSERVED_EFFECT_ITEM_KIND = "hive-mind-unobserved-host-lifecycle-item-v1"
_UNOBSERVED_EFFECT_ITEM_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "item_type",
        "item_identity",
        "record_id",
    }
)
_UNOBSERVED_EFFECT_ITEM_TYPES = frozenset({"THREAD", "TURN", "EFFECT"})

_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "frontier_id",
        "disposition",
        "active_host_threads",
        "active_host_turns",
        "unobserved_host_lifecycle_items",
        "observed_at",
        "observation_id",
    }
)

_RECONCILIATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "reservation_id",
        "thread_id",
        "turn_id",
        "thread_status",
        "turn_status",
        "external_cancellation_proven",
        "safe_to_release_capacity",
        "unobserved_host_lifecycle_items",
        "observed_at",
        "record_id",
    }
)

_TASK_LIFECYCLE_OBSERVATION_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "host_id",
        "reservation_id",
        "execution_id",
        "local_reservation_id",
        "capacity_generation",
        "host_task_id",
        "host_cursor",
        "capability_digest",
        "state",
        "terminal_state",
        "observed_at",
        "source_event_id",
        "observation_id",
    }
)


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class _FileLock:
    def __init__(self, path: Path, timeout: float) -> None:
        self.path = path
        self.timeout = timeout
        self.stream: Any = None
        self.local: threading.RLock | None = None

    def __enter__(self) -> _FileLock:
        self.path = self.path.absolute()
        key = str(self.path).casefold()
        with _THREAD_LOCKS_GUARD:
            self.local = _THREAD_LOCKS.setdefault(key, threading.RLock())
        assert self.local is not None
        if not self.local.acquire(timeout=self.timeout):
            raise AppServerHostError(f"timed out acquiring local lock: {self.path}")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _reject_link_components(self.path.parent, label="App Server lock")
            if _is_link_like(self.path):
                raise AppServerHostError(
                    f"App Server lock path uses a link: {self.path}"
                )
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_BINARY"):
                flags |= os.O_BINARY
            descriptor = os.open(self.path, flags, 0o600)
            try:
                if _is_link_like(self.path):
                    raise AppServerHostError(
                        f"App Server lock path became a link: {self.path}"
                    )
                path_stat = os.stat(self.path, follow_symlinks=False)
                handle_stat = os.fstat(descriptor)
                if not stat.S_ISREG(path_stat.st_mode) or not stat.S_ISREG(
                    handle_stat.st_mode
                ):
                    raise AppServerHostError(
                        f"App Server lock is not a regular file: {self.path}"
                    )
                if (
                    path_stat.st_dev != handle_stat.st_dev
                    or path_stat.st_ino != handle_stat.st_ino
                ):
                    raise AppServerHostError(
                        f"App Server lock path changed while opening: {self.path}"
                    )
                self.stream = os.fdopen(descriptor, "r+b", closefd=True)
                descriptor = -1
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            self.stream.seek(0, os.SEEK_END)
            if self.stream.tell() == 0:
                self.stream.write(b"\0")
                self.stream.flush()
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    self.stream.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise AppServerHostError(
                            f"timed out acquiring App Server evidence lock: {self.path}"
                        ) from error
                    time.sleep(0.01)
        except BaseException:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            self.local.release()
            raise

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if self.stream is not None:
                self.stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
                self.stream.close()
        finally:
            assert self.local is not None
            self.local.release()


def _sanitized_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if source is None else source
    result: dict[str, str] = {}
    allowed = {name.casefold() for name in _SAFE_ENVIRONMENT}
    for key, value in source.items():
        if key.casefold() in allowed and isinstance(value, str) and "\x00" not in value:
            result[key] = value
    result["NO_COLOR"] = "1"
    # These variables can inject code into subprocess runtimes and are never
    # required by the Codex executable contract.
    for unsafe in ("PYTHONHOME", "PYTHONPATH", "NODE_OPTIONS", "RUSTC_WRAPPER"):
        for present in tuple(result):
            if present.casefold() == unsafe.casefold():
                result.pop(present, None)
    return result


def _environment_root_digest(environment: Mapping[str, str]) -> str:
    """Bind non-secret installation roots that can change Codex behavior."""

    roots: dict[str, str] = {}
    for name in (
        "APPDATA",
        "CODEX_HOME",
        "HOME",
        "LOCALAPPDATA",
        "USERPROFILE",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    ):
        value = next(
            (
                item
                for key, item in environment.items()
                if key.casefold() == name.casefold()
            ),
            None,
        )
        if value is None:
            continue
        path = Path(value)
        if not path.is_absolute():
            raise AppServerHostError(f"{name} must be an absolute installation root")
        roots[name] = str(_reject_link_components(path, label=name))
    return _digest({"kind": "hive-mind-codex-environment-roots-v1", "roots": roots})


def _behavior_environment_digest(environment: Mapping[str, str]) -> str:
    """Hash routing and trust inputs without retaining their values in evidence."""

    selected: dict[str, str] = {}
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    ):
        matches = [
            value
            for key, value in environment.items()
            if key.casefold() == name.casefold()
        ]
        if len(matches) > 1 and len(set(matches)) != 1:
            raise AppServerHostError(
                f"conflicting case variants were supplied for {name}"
            )
        if matches:
            selected[name] = matches[0]
    return _digest(
        {
            "kind": "hive-mind-codex-behavior-environment-v1",
            "routing_and_trust": selected,
        }
    )


def _host_kernel_machine_user_id(host_runtime_dir: Path) -> str:
    path = host_runtime_dir / "host-runtime-identity.json"
    if not path.is_file() or _is_link_like(path):
        raise AppServerHostError("sealed machine-user host runtime identity is absent")
    value = _strict_json(path.read_bytes(), "host runtime identity")
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "kind",
        "machine_user_id",
        "record_id",
    }:
        raise AppServerHostError("host runtime identity schema is invalid")
    material = dict(value)
    record_id = material.pop("record_id", None)
    machine_user_id = _require_digest(value.get("machine_user_id"), "machine-user id")
    if (
        value.get("schema_version") != 1
        or value.get("kind") != "hive-mind-host-runtime-identity-v1"
        or record_id != _digest(material)
    ):
        raise AppServerHostError("host runtime identity is not sealed")
    return machine_user_id


def _default_version_probe(path: Path, environment: Mapping[str, str]) -> str:
    try:
        result = subprocess.run(
            [str(path), "--version"],
            cwd=str(path.parent),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=10,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AppServerHostError(
            f"cannot authenticate Codex executable version: {error}"
        ) from error
    version = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(
        r"codex-cli [0-9A-Za-z.+_-]+", version
    ):
        raise AppServerHostError(
            "Codex executable returned an invalid version identity"
        )
    return version


def _default_process_factory(
    argv: Sequence[str], cwd: Path, environment: Mapping[str, str]
) -> _Process:
    return subprocess.Popen(
        list(argv),
        cwd=str(cwd),
        env=dict(environment),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="strict",
        bufsize=1,
        shell=False,
        creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),
    )


def _default_schema_probe(
    path: Path, environment: Mapping[str, str]
) -> Mapping[str, str]:
    """Generate and pin the exact stable request schemas for this executable."""

    with tempfile.TemporaryDirectory(prefix="hive-codex-app-server-schema-") as raw:
        destination = Path(raw)
        try:
            result = subprocess.run(
                [
                    str(path),
                    "app-server",
                    "generate-json-schema",
                    "--out",
                    str(destination),
                ],
                cwd=str(path.parent),
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=30,
                shell=False,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            raise AppServerHostError(
                f"cannot generate App Server schema: {error}"
            ) from error
        if result.returncode != 0:
            raise AppServerHostError(
                "Codex executable could not generate its App Server schema"
            )
        files = sorted(item for item in destination.rglob("*") if item.is_file())
        if not files or any(_is_link_like(item) for item in files):
            raise AppServerHostError(
                "generated App Server schema bundle is missing or linked"
            )
        raw_digests: dict[str, str] = {}
        semantic_digests: dict[str, str] = {}
        for item in files:
            relative = item.relative_to(destination).as_posix()
            raw = item.read_bytes()
            raw_digests[relative] = _bytes_digest(raw)
            semantic_digests[relative] = _digest(
                _strict_json(raw, f"generated App Server schema {relative}")
            )
        thread_path = destination / "v2" / "ThreadStartParams.json"
        turn_path = destination / "v2" / "TurnStartParams.json"
        for schema_path, title, required_properties in (
            (
                thread_path,
                "ThreadStartParams",
                {"cwd", "approvalPolicy", "sandbox", "serviceName"},
            ),
            (
                turn_path,
                "TurnStartParams",
                {
                    "threadId",
                    "input",
                    "cwd",
                    "approvalPolicy",
                    "sandboxPolicy",
                    "clientUserMessageId",
                },
            ),
        ):
            if not schema_path.is_file() or _is_link_like(schema_path):
                raise AppServerHostError(f"generated {title} schema is missing")
            schema = _strict_json(schema_path.read_bytes(), title)
            properties = (
                schema.get("properties") if isinstance(schema, Mapping) else None
            )
            if (
                not isinstance(properties, Mapping)
                or schema.get("title") != title
                or not required_properties <= set(properties)
                or "idempotency" in properties
                or "idempotencyKey" in properties
            ):
                raise AppServerHostError(
                    f"installed {title} schema differs from the authenticated adapter contract"
                )
        thread_schema = _strict_json(thread_path.read_bytes(), "ThreadStartParams")
        turn_schema = _strict_json(turn_path.read_bytes(), "TurnStartParams")
        thread_definitions = thread_schema.get("definitions")
        turn_definitions = turn_schema.get("definitions")
        if (
            not isinstance(thread_definitions, Mapping)
            or not isinstance(thread_definitions.get("SandboxMode"), Mapping)
            or "workspace-write"
            not in thread_definitions["SandboxMode"].get("enum", [])
            or not isinstance(turn_definitions, Mapping)
            or not isinstance(turn_definitions.get("SandboxPolicy"), Mapping)
            or not any(
                "workspaceWrite" == text
                for text in _walk_strings(turn_definitions["SandboxPolicy"])
            )
        ):
            raise AppServerHostError(
                "installed sandbox schemas differ from the authenticated adapter contract"
            )
        return {
            # The generator's combined v2 definitions object is emitted in a
            # nondeterministic key order.  Bind the exact JSON meaning of every
            # file while retaining raw-byte identities for the two authority-
            # critical request schemas, whose installed bytes are stable.
            "schema_bundle_digest": _digest(semantic_digests),
            "thread_start_schema_digest": raw_digests["v2/ThreadStartParams.json"],
            "turn_start_schema_digest": raw_digests["v2/TurnStartParams.json"],
        }


@dataclass(frozen=True, slots=True)
class _CodexInstallation:
    executable_path: Path
    executable_digest: str
    executable_version: str
    launcher_path: Path
    launcher_digest: str
    cli_module_path: Path | None
    cli_module_digest: str | None
    executable_file_identity: tuple[int, int, int, int]


def _stable_executable_identity(
    path: Path, *, expected_digest: str | None = None
) -> tuple[str, tuple[int, int, int, int]]:
    """Read an executable across matching metadata cuts and reject replacement."""

    if not path.is_file() or _is_link_like(path):
        raise AppServerHostError("Codex executable identity path is not a regular file")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    before_identity = (
        int(before.st_dev),
        int(before.st_ino),
        int(before.st_size),
        int(before.st_mtime_ns),
    )
    after_identity = (
        int(after.st_dev),
        int(after.st_ino),
        int(after.st_size),
        int(after.st_mtime_ns),
    )
    digest = _bytes_digest(data)
    if before_identity != after_identity or not data:
        raise AppServerHostError("Codex executable changed while its identity was read")
    if expected_digest is not None and digest != expected_digest:
        raise AppServerHostError(
            "Codex executable differs from its authenticated bytes"
        )
    return digest, after_identity


def _windows_npm_native(launcher: Path) -> tuple[Path, Path, str]:
    module = _reject_link_components(
        launcher.parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js",
        label="Codex CLI module",
    )
    package_path = module.parent.parent / "package.json"
    if (
        not module.is_file()
        or _is_link_like(module)
        or not package_path.is_file()
        or _is_link_like(package_path)
    ):
        raise AppServerHostError(
            "codex.cmd is not backed by an exact local Codex module"
        )
    package = _strict_json(package_path.read_bytes(), "Codex package identity")
    if (
        not isinstance(package, Mapping)
        or package.get("name") != "@openai/codex"
        or not isinstance(package.get("version"), str)
        or not str(package["version"]).strip()
    ):
        raise AppServerHostError("Codex package identity is malformed")
    machine = platform.machine().casefold()
    if machine in {"amd64", "x86_64"}:
        package_name = "codex-win32-x64"
        target = "x86_64-pc-windows-msvc"
    elif machine in {"arm64", "aarch64"}:
        package_name = "codex-win32-arm64"
        target = "aarch64-pc-windows-msvc"
    else:
        raise AppServerHostError(
            "installed Codex package does not support this architecture"
        )
    native = _reject_link_components(
        module.parent.parent
        / "node_modules"
        / "@openai"
        / package_name
        / "vendor"
        / target
        / "bin"
        / "codex.exe",
        label="Codex native executable",
    )
    if not native.is_file() or _is_link_like(native):
        raise AppServerHostError(
            "Codex native executable is absent from its pinned package"
        )
    wrapper = launcher.read_bytes()
    if b"node_modules\\@openai\\codex\\bin\\codex.js" not in wrapper:
        raise AppServerHostError(
            "codex.cmd does not launch the pinned Codex CLI module"
        )
    return native, module, str(package["version"])


def _executable_identity(
    explicit: str | Path | None,
    environment: Mapping[str, str],
    probe: VersionProbe,
) -> _CodexInstallation:
    selected = (
        str(explicit)
        if explicit is not None
        else shutil.which(
            "codex.cmd" if os.name == "nt" else "codex",
            path=environment.get("PATH"),
        )
    )
    if not selected:
        raise AppServerHostError("the local Codex executable is not installed on PATH")
    launcher = _reject_link_components(Path(selected), label="Codex launcher")
    if not launcher.is_file() or _is_link_like(launcher):
        raise AppServerHostError("Codex launcher must be a regular non-link file")
    if os.name == "nt" and launcher.suffix.casefold() not in {".cmd", ".exe"}:
        raise AppServerHostError(
            "Codex App Server requires an exact codex.cmd or codex.exe launcher"
        )
    cli_module: Path | None = None
    package_version: str | None = None
    path = launcher
    if os.name == "nt" and launcher.suffix.casefold() == ".cmd":
        path, cli_module, package_version = _windows_npm_native(launcher)
    mode = path.stat().st_mode
    if os.name != "nt" and not (mode & stat.S_IXUSR):
        raise AppServerHostError("Codex executable is not executable")
    executable_digest, executable_file_identity = _stable_executable_identity(path)
    version = probe(path, environment)
    version = _require_text(version, "Codex version", maximum=256)
    if package_version is not None and version != "codex-cli " + package_version:
        raise AppServerHostError("Codex native version differs from its CLI package")
    return _CodexInstallation(
        executable_path=path,
        executable_digest=executable_digest,
        executable_version=version,
        launcher_path=launcher,
        launcher_digest=_bytes_digest(launcher.read_bytes()),
        cli_module_path=cli_module,
        cli_module_digest=(
            _bytes_digest(cli_module.read_bytes()) if cli_module is not None else None
        ),
        executable_file_identity=executable_file_identity,
    )


class _RpcClient:
    def __init__(
        self,
        *,
        executable: Path,
        executable_digest: str,
        executable_file_identity: tuple[int, int, int, int],
        cwd: Path,
        environment: Mapping[str, str],
        process_factory: ProcessFactory,
        timeout: float,
    ) -> None:
        self.timeout = timeout
        before_digest, before_identity = _stable_executable_identity(
            executable, expected_digest=executable_digest
        )
        if (
            before_digest != executable_digest
            or before_identity != executable_file_identity
        ):
            raise AppServerHostError(
                "Codex executable changed after version/schema authentication"
            )
        process = process_factory(
            (str(executable), "app-server", "--listen", "stdio://"),
            cwd,
            environment,
        )
        try:
            after_digest, after_identity = _stable_executable_identity(
                executable, expected_digest=executable_digest
            )
            if (
                after_digest != executable_digest
                or after_identity != executable_file_identity
            ):
                raise AppServerHostError(
                    "Codex executable changed across App Server process creation"
                )
        except BaseException:
            if process.poll() is None:
                with contextlib.suppress(OSError):
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired, TimeoutError):
                    with contextlib.suppress(OSError):
                        process.kill()
                    with contextlib.suppress(
                        OSError, subprocess.TimeoutExpired, TimeoutError
                    ):
                        process.wait(timeout=2)
            raise
        self.process = process
        if self.process.stdin is None or self.process.stdout is None:
            raise AppServerProtocolError("App Server process has no stdio transport")
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[object]] = {}
        self._request_id = 0
        self._notifications: deque[dict[str, object]] = deque(maxlen=4096)
        self._notification_condition = threading.Condition()
        self._closed = False
        self._reader_error: BaseException | None = None
        self._adverse_items = 0
        self._stderr: deque[str] = deque(maxlen=100)
        self._reader = threading.Thread(
            target=self._read_stdout, name="hive-codex-app-server-stdout", daemon=True
        )
        self._reader.start()
        self._stderr_reader: threading.Thread | None = None
        if self.process.stderr is not None:
            self._stderr_reader = threading.Thread(
                target=self._read_stderr,
                name="hive-codex-app-server-stderr",
                daemon=True,
            )
            self._stderr_reader.start()
        initialized = self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "hive_mind_os",
                    "title": "Hive Mind OS",
                    "version": "1",
                }
            },
        )
        if not isinstance(initialized, Mapping):
            self.close()
            raise AppServerProtocolError("initialize response is not an object")
        for field in ("userAgent", "platformFamily", "platformOs"):
            _require_text(initialized.get(field), f"initialize.{field}", maximum=1024)
        self.initialize_result = dict(initialized)
        self.notify("initialized", {})
        self.handshake_authenticated = True

    @property
    def adverse_items(self) -> int:
        return self._adverse_items + int(self._reader_error is not None)

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        try:
            for line in self.process.stderr:
                self._stderr.append(line.rstrip()[:4096])
        except (OSError, UnicodeError):
            self._adverse_items += 1

    def _send(self, message: Mapping[str, object]) -> None:
        payload = _canonical(dict(message)).decode("utf-8") + "\n"
        if len(payload.encode("utf-8")) > _MAX_LINE_BYTES:
            raise AppServerProtocolError("outbound App Server message is too large")
        with self._write_lock:
            if self._closed or self.process.poll() is not None:
                raise AppServerProtocolError("App Server process is not running")
            try:
                assert self.process.stdin is not None
                self.process.stdin.write(payload)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError, UnicodeError) as error:
                raise AppServerProtocolError("cannot write App Server stdio") from error

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        try:
            while True:
                line = self.process.stdout.readline()
                if line == "":
                    if not self._closed:
                        raise AppServerProtocolError(
                            "App Server stdout closed unexpectedly"
                        )
                    return
                if len(line.encode("utf-8")) > _MAX_LINE_BYTES:
                    raise AppServerProtocolError(
                        "App Server message exceeded the size bound"
                    )
                value = _strict_json(line, "App Server message")
                if not isinstance(value, dict):
                    raise AppServerProtocolError("App Server message must be an object")
                if "id" in value and "method" not in value:
                    request_id = value.get("id")
                    if type(request_id) is not int:
                        raise AppServerProtocolError(
                            "App Server response id must be an integer"
                        )
                    with self._pending_lock:
                        target = self._pending.get(request_id)
                    if target is None:
                        self._adverse_items += 1
                    else:
                        target.put(value)
                    continue
                method = value.get("method")
                params = value.get("params")
                if not isinstance(method, str) or not isinstance(params, Mapping):
                    raise AppServerProtocolError(
                        "App Server notification schema is invalid"
                    )
                if "id" in value:
                    self._adverse_items += 1
                    self._send(
                        {
                            "id": value["id"],
                            "error": {
                                "code": -32601,
                                "message": "Hive Mind host does not authorize server requests",
                            },
                        }
                    )
                    continue
                with self._notification_condition:
                    self._notifications.append(dict(value))
                    self._notification_condition.notify_all()
        except BaseException as error:
            self._reader_error = error
            with self._pending_lock:
                pending = tuple(self._pending.values())
            for target in pending:
                with contextlib.suppress(queue.Full):
                    target.put(error, block=False)
            with self._notification_condition:
                self._notification_condition.notify_all()

    def request(
        self,
        method: str,
        params: Mapping[str, object] | None = None,
        *,
        timeout: float | None = None,
    ) -> object:
        _require_text(method, "App Server method", maximum=256)
        with self._pending_lock:
            self._request_id += 1
            request_id = self._request_id
            target: queue.Queue[object] = queue.Queue(maxsize=1)
            self._pending[request_id] = target
        try:
            self._send(
                {"method": method, "id": request_id, "params": dict(params or {})}
            )
            try:
                response = target.get(
                    timeout=self.timeout if timeout is None else timeout
                )
            except queue.Empty as error:
                raise AppServerProtocolError(
                    f"App Server request timed out: {method}"
                ) from error
            if isinstance(response, BaseException):
                raise AppServerProtocolError(
                    f"App Server reader failed during {method}"
                ) from response
            if not isinstance(response, Mapping) or response.get("id") != request_id:
                raise AppServerProtocolError(
                    "App Server response correlation is invalid"
                )
            if set(response) == {"id", "error"}:
                error = response.get("error")
                if not isinstance(error, Mapping):
                    raise AppServerProtocolError(
                        "App Server error response is malformed"
                    )
                code = error.get("code")
                message = error.get("message")
                raise AppServerProtocolError(
                    f"App Server {method} failed ({code}): {message}"
                )
            if set(response) != {"id", "result"}:
                raise AppServerProtocolError("App Server response has unknown fields")
            return response.get("result")
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: Mapping[str, object] | None = None) -> None:
        self._send({"method": method, "params": dict(params or {})})

    def notification_snapshot(self) -> tuple[dict[str, object], ...]:
        with self._notification_condition:
            return tuple(dict(item) for item in self._notifications)

    def wait_notification_change(self, count: int, timeout: float) -> int:
        with self._notification_condition:
            if len(self._notifications) <= count and self._reader_error is None:
                self._notification_condition.wait(timeout=timeout)
            return len(self._notifications)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(BrokenPipeError, OSError):
            if self.process.stdin is not None:
                self.process.stdin.close()
        if self.process.poll() is None:
            with contextlib.suppress(OSError):
                self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired, TimeoutError):
                with contextlib.suppress(OSError):
                    self.process.kill()
                with contextlib.suppress(
                    OSError, subprocess.TimeoutExpired, TimeoutError
                ):
                    self.process.wait(timeout=2)


def _thread_from_result(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or not isinstance(value.get("thread"), Mapping):
        raise AppServerProtocolError(f"{label} response has no thread")
    thread = dict(value["thread"])
    _require_text(thread.get("id"), f"{label} thread id", maximum=512)
    return thread


def _turn_from_result(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or not isinstance(value.get("turn"), Mapping):
        raise AppServerProtocolError(f"{label} response has no turn")
    turn = dict(value["turn"])
    _require_text(turn.get("id"), f"{label} turn id", maximum=512)
    return turn


def _walk_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _walk_strings(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            yield from _walk_strings(item)


@dataclass(frozen=True, slots=True)
class _Lifecycle:
    thread: Mapping[str, object]
    thread_id: str
    thread_status: str
    turn_id: str | None
    turn_status: str | None

    @property
    def terminal(self) -> bool:
        return (
            self.turn_status in _TERMINAL_TURN_STATES
            or self.thread_status == "systemError"
        )

    @property
    def active_turn(self) -> bool:
        return self.turn_status in {"inProgress", "active"}


class CodexAppServerHost:
    """Execution-scoped, authenticated host lifecycle over Codex App Server."""

    supports_preparation_only = True

    def __init__(
        self,
        *,
        plane: Any,
        host_id: str | None,
        execution_namespace: str,
        execution_id: str,
        execution_dir: str | Path,
        host_runtime_dir: str | Path,
        wait_seconds: int,
        adapter_module_digest: str,
        executable_path: str | Path | None = None,
        process_factory: ProcessFactory = _default_process_factory,
        version_probe: VersionProbe = _default_version_probe,
        schema_probe: SchemaProbe = _default_schema_probe,
        environment: Mapping[str, str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.plane = plane
        requested_host_id = host_id
        if requested_host_id is not None:
            requested_host_id = _require_text(requested_host_id, "host id", maximum=256)
            if _SAFE_ID.fullmatch(requested_host_id) is None:
                raise AppServerHostError("host id is noncanonical")
        self.execution_namespace = _require_text(
            execution_namespace, "execution namespace", maximum=64
        )
        self.execution_id = _require_digest(execution_id, "execution id")
        self.adapter_module_digest = _require_digest(
            adapter_module_digest, "adapter module digest"
        )
        module_path = _reject_link_components(
            Path(__file__), label="App Server adapter module"
        )
        if self.adapter_module_digest != _bytes_digest(module_path.read_bytes()):
            raise AppServerHostError(
                "adapter module digest differs from its loaded bytes"
            )
        self.adapter_module_path = module_path
        self.repo_root = _reject_link_components(
            Path(plane.repo_root), label="repository"
        )
        self.execution_dir = _reject_link_components(
            Path(execution_dir), label="execution"
        )
        expected_execution = Path(
            getattr(plane, "execution_dir", self.execution_dir)
        ).absolute()
        if self.execution_dir != expected_execution:
            raise AppServerHostError(
                "adapter execution directory differs from the control plane"
            )
        if (
            getattr(plane, "execution_id", execution_id) != execution_id
            or getattr(plane, "execution_namespace", execution_namespace)
            != execution_namespace
        ):
            raise AppServerHostError(
                "adapter execution identity differs from the control plane"
            )
        self.host_runtime_dir = _reject_link_components(
            Path(host_runtime_dir), label="host runtime"
        )
        expected_host_runtime = Path(
            getattr(plane, "host_runtime_dir", self.host_runtime_dir)
        ).absolute()
        if self.host_runtime_dir != expected_host_runtime:
            raise AppServerHostError(
                "adapter host runtime differs from the control plane"
            )
        self.machine_user_id = _host_kernel_machine_user_id(self.host_runtime_dir)
        if type(wait_seconds) is not int or wait_seconds < 1 or wait_seconds > 3600:
            raise AppServerHostError("App Server wait bound is invalid")
        self.wait_seconds = wait_seconds
        self.clock = clock
        self.environment = _sanitized_environment(environment)
        self.environment_root_digest = _environment_root_digest(self.environment)
        self.behavior_environment_digest = _behavior_environment_digest(
            self.environment
        )
        installation = _executable_identity(
            executable_path, self.environment, version_probe
        )
        self.executable_path = installation.executable_path
        self.executable_digest = installation.executable_digest
        self.executable_version = installation.executable_version
        self.launcher_path = installation.launcher_path
        self.launcher_digest = installation.launcher_digest
        self.cli_module_path = installation.cli_module_path
        self.cli_module_digest = installation.cli_module_digest
        schemas = schema_probe(self.executable_path, self.environment)
        expected_schema_keys = {
            "schema_bundle_digest",
            "thread_start_schema_digest",
            "turn_start_schema_digest",
        }
        if set(schemas) != expected_schema_keys or any(
            _DIGEST.fullmatch(str(schemas.get(key))) is None
            for key in expected_schema_keys
        ):
            raise AppServerHostError(
                "App Server schema probe returned an invalid identity"
            )
        self.schema_bundle_digest = str(schemas["schema_bundle_digest"])
        self.thread_start_schema_digest = str(schemas["thread_start_schema_digest"])
        self.turn_start_schema_digest = str(schemas["turn_start_schema_digest"])
        self.root = self.execution_dir / "host" / "codex-app-server-v1"
        self.threads_dir = self.root / "threads"
        self.thread_history_dir = self.root / "thread-history"
        self.messages_dir = self.root / "messages"
        self.sidecars_dir = self.root / "sidecars"
        self.effect_observations_dir = self.root / "effect-observations"
        self.observations_dir = self.root / "observations"
        self.reconciliations_dir = self.root / "reconciliations"
        evidence_directories = (
            self.root,
            self.threads_dir,
            self.thread_history_dir,
            self.messages_dir,
            self.sidecars_dir,
            self.effect_observations_dir,
            self.observations_dir,
            self.reconciliations_dir,
        )
        for path in evidence_directories:
            path.mkdir(parents=True, exist_ok=True)
            _reject_link_components(path, label="App Server evidence")
        with _FileLock(self.root / "stale-temporary-recovery.lock", 30.0):
            _reconcile_stale_atomic_temporaries(
                self.root,
                evidence_directories,
                clock=self.clock,
            )
        self.client = _RpcClient(
            executable=self.executable_path,
            executable_digest=self.executable_digest,
            executable_file_identity=installation.executable_file_identity,
            cwd=self.repo_root,
            environment=self.environment,
            process_factory=process_factory,
            timeout=min(float(wait_seconds), 60.0),
        )
        provider_config = self.client.request(
            "config/read",
            {"cwd": str(self.host_runtime_dir), "includeLayers": True},
        )
        execution_config = self.client.request(
            "config/read",
            {"cwd": str(self.repo_root), "includeLayers": True},
        )
        account_identity = self.client.request("account/read", {"refreshToken": False})
        for value, label in (
            (provider_config, "provider config/read"),
            (execution_config, "execution config/read"),
            (account_identity, "account/read"),
        ):
            if not isinstance(value, Mapping):
                self.client.close()
                raise AppServerProtocolError(f"{label} response is not an object")
            if len(_canonical(value)) > _MAX_LINE_BYTES:
                self.client.close()
                raise AppServerProtocolError(f"{label} response is too large")
        effective_config = execution_config.get("config")
        if not isinstance(effective_config, Mapping):
            self.client.close()
            raise AppServerProtocolError(
                "execution config/read response has no effective config"
            )
        self.effective_model = _require_text(
            effective_config.get("model"), "effective Codex model", maximum=512
        )
        raw_provider = effective_config.get("model_provider")
        if raw_provider is None:
            self.effective_model_provider = None
        else:
            self.effective_model_provider = _require_text(
                raw_provider, "effective Codex model provider", maximum=512
            )
        self.provider_config_digest = _digest(provider_config)
        self.execution_config_digest = _digest(execution_config)
        self.account_identity_digest = _digest(account_identity)
        initialize_result_digest = _digest(self.client.initialize_result)
        provider_material: dict[str, object] = {
            "kind": "hive-mind-codex-app-server-provider-identity-v1",
            "machine_user_id": self.machine_user_id,
            "launcher_path": str(self.launcher_path),
            "launcher_digest": self.launcher_digest,
            "cli_module_path": (
                str(self.cli_module_path) if self.cli_module_path is not None else None
            ),
            "cli_module_digest": self.cli_module_digest,
            "executable_path": str(self.executable_path),
            "executable_digest": self.executable_digest,
            "executable_version": self.executable_version,
            "schema_bundle_digest": self.schema_bundle_digest,
            "thread_start_schema_digest": self.thread_start_schema_digest,
            "turn_start_schema_digest": self.turn_start_schema_digest,
            "environment_root_digest": self.environment_root_digest,
            "behavior_environment_digest": self.behavior_environment_digest,
            "provider_config_digest": self.provider_config_digest,
            "account_identity_digest": self.account_identity_digest,
            "transport": "stdio://",
            "initialize_result_digest": initialize_result_digest,
        }
        self.provider_identity_digest = _digest(provider_material)
        self.host_id = _digest(
            {
                "kind": "hive-mind-codex-app-server-provider-v1",
                "machine_user_id": self.machine_user_id,
            }
        )
        if requested_host_id is not None and requested_host_id != self.host_id:
            self.client.close()
            raise AppServerHostError(
                "caller host id differs from the authenticated App Server provider"
            )
        self._tasks: dict[str, str] = {}
        try:
            self._install_identity()
        except BaseException:
            self.client.close()
            raise

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> CodexAppServerHost:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _install_identity(self) -> None:
        identity_path = self.root / "identity.json"
        invariants: dict[str, object] = {
            "schema_version": 1,
            "kind": _IDENTITY_KIND,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "host_id": self.host_id,
            "machine_user_id": self.machine_user_id,
            "provider_identity_digest": self.provider_identity_digest,
            "adapter_module_path": str(self.adapter_module_path),
            "adapter_module_digest": self.adapter_module_digest,
            "launcher_path": str(self.launcher_path),
            "launcher_digest": self.launcher_digest,
            "cli_module_path": (
                str(self.cli_module_path) if self.cli_module_path is not None else None
            ),
            "cli_module_digest": self.cli_module_digest,
            "executable_path": str(self.executable_path),
            "executable_digest": self.executable_digest,
            "executable_version": self.executable_version,
            "schema_bundle_digest": self.schema_bundle_digest,
            "thread_start_schema_digest": self.thread_start_schema_digest,
            "turn_start_schema_digest": self.turn_start_schema_digest,
            "environment_root_digest": self.environment_root_digest,
            "behavior_environment_digest": self.behavior_environment_digest,
            "provider_config_digest": self.provider_config_digest,
            "execution_config_digest": self.execution_config_digest,
            "account_identity_digest": self.account_identity_digest,
            "effective_model": self.effective_model,
            "effective_model_provider": self.effective_model_provider,
            "transport": "stdio://",
            "initialize_result_digest": _digest(self.client.initialize_result),
        }
        with _FileLock(self.root / "identity.lock", 30.0):
            if identity_path.exists():
                existing = _read_sealed(
                    identity_path, kind=_IDENTITY_KIND, fields=_IDENTITY_FIELDS
                )
                for key, value in invariants.items():
                    if existing.get(key) != value:
                        raise AppServerHostError(
                            f"App Server identity changed at {key}; explicit host rebind required"
                        )
                self.identity = existing
                return
            material = {**invariants, "created_at": _now_text(self.clock)}
            identity = {**material, "record_id": _digest(material)}
            _atomic_write(identity_path, identity)
            self.identity = identity

    def _thread_path(self, idempotency_key: str) -> Path:
        key = _require_digest(idempotency_key, "thread idempotency key")
        return self.threads_dir / (key.removeprefix("sha256:") + ".json")

    def _thread_archive_path(self, idempotency_key: str, record_id: str) -> Path:
        key = _require_digest(idempotency_key, "thread idempotency key")
        identity = _require_digest(record_id, "thread predecessor record id")
        del key
        return self.thread_history_dir / (identity.removeprefix("sha256:") + ".json")

    def _message_path(self, idempotency_key: str) -> Path:
        key = _require_digest(idempotency_key, "message idempotency key")
        return self.messages_dir / (key.removeprefix("sha256:") + ".json")

    def _sidecar_path(self, sidecar_id: str) -> Path:
        key = _require_digest(sidecar_id, "sidecar id")
        return self.sidecars_dir / (key.removeprefix("sha256:") + ".json")

    def _validate_thread_record_shape(
        self, record: Mapping[str, object], *, idempotency_key: str
    ) -> None:
        key = _require_digest(idempotency_key, "thread idempotency key")
        if (
            record.get("schema_version") != 1
            or record.get("kind") != _THREAD_KIND
            or record.get("execution_id") != self.execution_id
            or record.get("execution_namespace") != self.execution_namespace
            or record.get("host_id") != self.host_id
            or record.get("idempotency_key") != key
        ):
            raise AppServerHostError("thread evidence identity is invalid")
        expected_token = (
            "hive-"
            + self.execution_id.removeprefix("sha256:")[:12]
            + "-"
            + key.removeprefix("sha256:")
        )
        if record.get("adoption_token") != expected_token:
            raise AppServerHostError(
                "thread adoption token is not derived from authority"
            )
        _require_text(record.get("title"), "thread title", maximum=4096)
        _require_digest(record.get("prompt_digest"), "thread prompt digest")
        baseline = record.get("baseline_thread_ids")
        unobserved = record.get("unobserved_thread_ids")
        for value, label in (
            (baseline, "baseline thread ids"),
            (unobserved, "unobserved thread ids"),
        ):
            if (
                not isinstance(value, list)
                or any(
                    not isinstance(item, str) or not item or len(item) > 512
                    for item in value
                )
                or value != sorted(set(value))
            ):
                raise AppServerHostError(f"{label} are noncanonical")
        state = record.get("state")
        if state not in _THREAD_STATES:
            raise AppServerHostError("thread lifecycle state is invalid")
        thread_id = record.get("thread_id")
        turn_id = record.get("turn_id")
        if thread_id is not None:
            _require_text(thread_id, "thread id", maximum=512)
        if turn_id is not None:
            _require_text(turn_id, "turn id", maximum=512)
        if state in {"PREPARED", "ATTEMPTED"} and (
            thread_id is not None or turn_id is not None
        ):
            raise AppServerHostError("pre-start thread evidence contains host identity")
        if state in {"THREAD_STARTED", "NAMED"} and (
            thread_id is None or turn_id is not None
        ):
            raise AppServerHostError("started thread evidence has impossible identity")
        if state in {"BOUND", "ARCHIVED"} and (thread_id is None or turn_id is None):
            raise AppServerHostError("terminal thread evidence lacks bound identity")
        if state == "RECOVERY_REQUIRED" and turn_id is not None:
            raise AppServerHostError("recovery-required thread evidence binds a turn")
        if state == "RECOVERY_REQUIRED" and thread_id is None and not unobserved:
            raise AppServerHostError(
                "recovery-required thread evidence lacks an observed ambiguity"
            )
        if state != "RECOVERY_REQUIRED" and unobserved:
            raise AppServerHostError(
                "non-adverse thread evidence retains unobserved host identities"
            )
        created_at = _parse_time(record.get("created_at"), "thread created_at")
        updated_at = _parse_time(record.get("updated_at"), "thread updated_at")
        if updated_at < created_at:
            raise AppServerHostError("thread lifecycle timestamp moved backwards")
        index = record.get("transition_index")
        previous = record.get("previous_record_id")
        if type(index) is not int or index < 0:
            raise AppServerHostError("thread transition index is invalid")
        if index == 0:
            if previous is not None or state != "PREPARED":
                raise AppServerHostError("thread lifecycle root is invalid")
        else:
            _require_digest(previous, "thread predecessor record id")

    def _validate_thread_transition(
        self, prior: Mapping[str, object], current: Mapping[str, object]
    ) -> None:
        if current.get("state") not in _THREAD_TRANSITIONS[str(prior.get("state"))]:
            raise AppServerHostError("thread lifecycle transition is illegal")
        if (
            current.get("previous_record_id") != prior.get("record_id")
            or current.get("transition_index")
            != int(prior.get("transition_index", -1)) + 1
        ):
            raise AppServerHostError("thread lifecycle predecessor is invalid")
        for field in (
            "schema_version",
            "kind",
            "execution_namespace",
            "execution_id",
            "host_id",
            "idempotency_key",
            "adoption_token",
            "title",
            "prompt_digest",
            "baseline_thread_ids",
            "created_at",
        ):
            if current.get(field) != prior.get(field):
                raise AppServerHostError(
                    f"thread lifecycle mutated immutable field: {field}"
                )
        for field in ("thread_id", "turn_id"):
            prior_value = prior.get(field)
            if prior_value is not None and current.get(field) != prior_value:
                raise AppServerHostError(
                    f"thread lifecycle changed bound identity: {field}"
                )
        if _parse_time(current.get("updated_at"), "thread updated_at") < _parse_time(
            prior.get("updated_at"), "prior thread updated_at"
        ):
            raise AppServerHostError("thread transition timestamp moved backwards")

    def _thread_history_chain(
        self, idempotency_key: str
    ) -> tuple[dict[str, object], ...]:
        key = _require_digest(idempotency_key, "thread idempotency key")
        records: list[dict[str, object]] = []
        for archive in self.thread_history_dir.glob("*.json"):
            value = _read_sealed(archive, kind=_THREAD_KIND, fields=_THREAD_FIELDS)
            if value.get("idempotency_key") != key:
                continue
            if archive.stem != str(value.get("record_id")).removeprefix("sha256:"):
                raise AppServerHostError(
                    "thread history filename differs from its record identity"
                )
            self._validate_thread_record_shape(value, idempotency_key=key)
            records.append(value)
        records.sort(key=lambda item: int(item["transition_index"]))
        if not records:
            return ()
        if [item["transition_index"] for item in records] != list(range(len(records))):
            raise AppServerHostError(
                "thread lifecycle history is branched or incomplete"
            )
        for prior, current in zip(records, records[1:], strict=False):
            self._validate_thread_transition(prior, current)
        return tuple(records)

    def _read_thread_record(self, path: Path) -> dict[str, object]:
        if path.parent != self.threads_dir or path.suffix != ".json":
            raise AppServerHostError("thread evidence path is noncanonical")
        key = "sha256:" + path.stem
        _require_digest(key, "thread evidence path identity")
        installed = _read_sealed(path, kind=_THREAD_KIND, fields=_THREAD_FIELDS)
        self._validate_thread_record_shape(installed, idempotency_key=key)
        chain = self._thread_history_chain(key)
        if not chain or installed not in chain:
            raise AppServerHostError(
                "thread projection is not anchored in immutable lifecycle history"
            )
        latest = chain[-1]
        if installed != latest:
            # The history record is installed before the mutable projection.  This
            # exact prefix state is therefore a recoverable crash cut, not licence
            # to choose a new transition or roll authority backwards.
            _atomic_write(path, latest)
        return latest

    def _write_thread_record(
        self,
        prior: Mapping[str, object],
        *,
        state: str,
        thread_id: str | None = None,
        turn_id: str | None = None,
        unobserved: Sequence[str] | None = None,
    ) -> dict[str, object]:
        key = _require_digest(prior.get("idempotency_key"), "thread idempotency key")
        path = self._thread_path(key)
        installed = self._read_thread_record(path)
        if installed != dict(prior):
            raise AppServerHostError("thread lifecycle transition token is stale")
        material = dict(installed)
        material.pop("record_id", None)
        material["state"] = state
        if thread_id is not None:
            material["thread_id"] = thread_id
        if turn_id is not None:
            material["turn_id"] = turn_id
        if unobserved is not None:
            material["unobserved_thread_ids"] = sorted(set(unobserved))
        material["updated_at"] = _now_text(self.clock)
        material["transition_index"] = int(installed["transition_index"]) + 1
        material["previous_record_id"] = installed["record_id"]
        record = {**material, "record_id": _digest(material)}
        self._validate_thread_record_shape(record, idempotency_key=key)
        self._validate_thread_transition(installed, record)
        archive_path = self._thread_archive_path(key, str(record["record_id"]))
        if archive_path.exists():
            archived = _read_sealed(
                archive_path, kind=_THREAD_KIND, fields=_THREAD_FIELDS
            )
            if archived != record:
                raise AppServerHostError("thread lifecycle archive is not immutable")
        else:
            _atomic_write(archive_path, record)
        _atomic_write(path, record)
        return self._read_thread_record(path)

    def _list_threads(
        self, *, search_term: str | None = None, archived: bool = False
    ) -> list[dict[str, object]]:
        cursor: str | None = None
        result: list[dict[str, object]] = []
        for _ in range(100):
            params: dict[str, object] = {
                "limit": 100,
                "archived": archived,
                "cwd": str(self.repo_root),
                "sourceKinds": ["appServer"],
            }
            if search_term is not None:
                params["searchTerm"] = search_term
            if cursor is not None:
                params["cursor"] = cursor
            page = self.client.request("thread/list", params)
            if not isinstance(page, Mapping) or not isinstance(page.get("data"), list):
                raise AppServerProtocolError("thread/list response is malformed")
            for item in page["data"]:
                if not isinstance(item, Mapping):
                    raise AppServerProtocolError("thread/list item is malformed")
                thread = dict(item)
                _require_text(thread.get("id"), "listed thread id", maximum=512)
                result.append(thread)
            next_cursor = page.get("nextCursor")
            if next_cursor is None:
                return result
            cursor = _require_text(next_cursor, "thread/list cursor", maximum=4096)
        raise AppServerProtocolError("thread/list pagination exceeded its bound")

    def _read_thread(self, thread_id: str) -> dict[str, object]:
        value = self.client.request(
            "thread/read", {"threadId": thread_id, "includeTurns": True}
        )
        thread = _thread_from_result(value, "thread/read")
        if thread.get("id") != thread_id:
            raise AppServerProtocolError(
                "thread/read response changed the requested thread identity"
            )
        return thread

    def _lifecycle(self, thread_id: str) -> _Lifecycle:
        thread = self._read_thread(thread_id)
        status_value = thread.get("status")
        if isinstance(status_value, Mapping):
            thread_status = _require_text(
                status_value.get("type"), "thread status", maximum=64
            )
        else:
            thread_status = "unknown"
        turns = thread.get("turns")
        if turns is None:
            turns = []
        if not isinstance(turns, list) or any(
            not isinstance(item, Mapping) for item in turns
        ):
            raise AppServerProtocolError("thread/read turns are malformed")
        turn: Mapping[str, object] | None = turns[-1] if turns else None
        turn_id = (
            None
            if turn is None
            else _require_text(turn.get("id"), "turn id", maximum=512)
        )
        turn_status = None
        if turn is not None and turn.get("status") is not None:
            turn_status = _require_text(turn.get("status"), "turn status", maximum=64)
        return _Lifecycle(thread, thread_id, thread_status, turn_id, turn_status)

    def bind_tasks(self, tasks: Sequence[Mapping[str, object]]) -> None:
        for task in tasks:
            instruction = _require_digest(
                task.get("launch_instruction_id"), "launch instruction id"
            )
            node_id = _require_text(task.get("node_id"), "node id", maximum=256)
            prior = self._tasks.get(instruction)
            if prior is not None and prior != node_id:
                raise AppServerHostError("task binding changed its node identity")
            self._tasks[instruction] = node_id

    def trusted_singleton_target(self, *, repo_root: Path) -> str:
        if Path(repo_root).absolute() != self.repo_root:
            raise AppServerHostError("trusted target requested for another repository")
        return _require_text(self.plane.target_branch, "target branch", maximum=1024)

    @contextlib.contextmanager
    def dispatcher_effect_guard(self, *, node_id: str, release_id: str):
        with self.plane.dispatcher_launch_authority_guard(
            node_id, host_id=self.host_id, release_id=release_id
        ) as authority:
            yield authority

    def host_capacity_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        """Read, but never publish or infer, the controller's host policy record."""

        if Path(repo_root).absolute() != self.repo_root:
            raise AppServerHostError("host capacity requested for another repository")
        controller = sys.modules.get("controller")
        expected = self.adapter_module_path.with_name("controller.py")
        source = (
            Path(str(getattr(controller, "__file__", ""))).absolute()
            if controller
            else None
        )
        if controller is None or source != expected:
            raise AppServerHostError(
                "trusted controller module is not loaded from this checkout"
            )
        reader = getattr(controller, "read_host_capacity", None)
        if not callable(reader):
            raise AppServerHostError("controller has no host-capacity reader")
        now = (
            self.plane.clock()
            if callable(getattr(self.plane, "clock", None))
            else self.clock()
        )
        value = reader(self.host_runtime_dir, self.host_id, now=now)
        if not isinstance(value, Mapping):
            raise AppServerHostError("controller host-capacity record is malformed")
        return value

    def host_lifecycle_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        if Path(repo_root).absolute() != self.repo_root:
            raise AppServerHostError("host lifecycle requested for another repository")
        if not self.client.handshake_authenticated:
            raise AppServerHostError(
                "App Server lifecycle handshake is not authenticated"
            )
        current = _read_sealed(
            self.root / "identity.json", kind=_IDENTITY_KIND, fields=_IDENTITY_FIELDS
        )
        if current != self.identity:
            raise AppServerHostError("App Server lifecycle identity changed")
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": _CAPABILITY_KIND,
            "host_id": self.host_id,
            "create": True,
            "query": True,
            "resume": True,
            "interrupt": True,
            "archive": True,
            # Installed schema 0.146.0 exposes no creation idempotency or
            # atomically host-visible caller token on thread/start.  A process
            # loss after acceptance therefore cannot always distinguish its
            # thread from a concurrent creator.  Routine crash-exact launch is
            # truthfully withheld until the product protocol closes that gap.
            "autonomous_launch": False,
            "source": "codex-app-server-stdio:" + str(self.identity["record_id"]),
        }
        return {**material, "record_id": _digest(material)}

    def host_provider_identity(self, *, repo_root: Path) -> Mapping[str, object]:
        """Return the exact sealed installation identity for capacity policy."""

        if Path(repo_root).absolute() != self.repo_root:
            raise AppServerHostError(
                "host provider identity requested for another repository"
            )
        current = _read_sealed(
            self.root / "identity.json", kind=_IDENTITY_KIND, fields=_IDENTITY_FIELDS
        )
        if current != self.identity or not self.client.handshake_authenticated:
            raise AppServerHostError(
                "App Server provider identity is not authenticated"
            )
        return dict(current)

    def lookup_thread(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        path = self._thread_path(idempotency_key)
        if not path.exists():
            return None
        record = self._read_thread_record(path)
        if record.get("state") != "BOUND":
            return None
        thread_id = _require_text(record.get("thread_id"), "thread id", maximum=512)
        self.query_thread(thread_id=thread_id)
        capability = _digest(
            {
                "execution_id": self.execution_id,
                "host_id": self.host_id,
                "idempotency_key": idempotency_key,
                "thread_id": thread_id,
                "module": self.adapter_module_digest,
            }
        )
        cursor = _digest(
            {
                "thread_id": thread_id,
                "idempotency_key": idempotency_key,
                "capability": capability,
            }
        )
        return {
            "kind": _HOST_BINDING_KIND,
            "host_id": self.host_id,
            "task_id": thread_id,
            "cursor": cursor,
            "capability": capability,
            "idempotency_key": idempotency_key,
        }

    def create_thread(
        self, *, title: str, prompt: str, idempotency_key: str
    ) -> Mapping[str, object]:
        title = _require_text(title, "thread title", maximum=4096)
        prompt = _require_text(prompt, "thread prompt")
        idempotency_key = _require_digest(idempotency_key, "thread idempotency key")
        path = self._thread_path(idempotency_key)
        token = (
            "hive-"
            + self.execution_id.removeprefix("sha256:")[:12]
            + "-"
            + idempotency_key.removeprefix("sha256:")
        )
        with _FileLock(path.with_suffix(".lock"), min(float(self.wait_seconds), 120.0)):
            if path.exists():
                record = self._read_thread_record(path)
                if record.get("title") != title or record.get(
                    "prompt_digest"
                ) != _digest({"prompt": prompt}):
                    raise AppServerHostError(
                        "thread idempotency key was reused with different input"
                    )
                existing = self.lookup_thread(idempotency_key=idempotency_key)
                if existing is not None:
                    return existing
            else:
                retained = self._thread_history_chain(idempotency_key)
                if retained:
                    _atomic_write(path, retained[-1])
                    record = self._read_thread_record(path)
                    if record.get("title") != title or record.get(
                        "prompt_digest"
                    ) != _digest({"prompt": prompt}):
                        raise AppServerHostError(
                            "retained thread history has different input"
                        )
                else:
                    baseline = sorted(str(item["id"]) for item in self._list_threads())
                    material: dict[str, object] = {
                        "schema_version": 1,
                        "kind": _THREAD_KIND,
                        "execution_namespace": self.execution_namespace,
                        "execution_id": self.execution_id,
                        "host_id": self.host_id,
                        "idempotency_key": idempotency_key,
                        "adoption_token": token,
                        "title": title,
                        "prompt_digest": _digest({"prompt": prompt}),
                        "baseline_thread_ids": baseline,
                        "unobserved_thread_ids": [],
                        "state": "PREPARED",
                        "thread_id": None,
                        "turn_id": None,
                        "created_at": _now_text(self.clock),
                        "updated_at": _now_text(self.clock),
                        "transition_index": 0,
                        "previous_record_id": None,
                    }
                    record = {**material, "record_id": _digest(material)}
                    self._validate_thread_record_shape(
                        record, idempotency_key=idempotency_key
                    )
                    _atomic_write(
                        self._thread_archive_path(
                            idempotency_key, str(record["record_id"])
                        ),
                        record,
                    )
                    _atomic_write(path, record)
            thread_id = record.get("thread_id")
            if thread_id is None:
                if record.get("state") == "RECOVERY_REQUIRED":
                    raise AppServerHostError(
                        "thread creation has a retained ambiguity; list shrinkage "
                        "cannot adjudicate a previously observed external effect"
                    )
                named = self._list_threads(search_term=token)
                if len(named) > 1:
                    record = self._write_thread_record(
                        record,
                        state="RECOVERY_REQUIRED",
                        unobserved=[str(item["id"]) for item in named],
                    )
                    raise AppServerHostError(
                        "multiple App Server threads match one adoption token"
                    )
                if len(named) == 1:
                    thread_id = str(named[0]["id"])
                    record = self._write_thread_record(
                        record,
                        state="NAMED",
                        thread_id=thread_id,
                        unobserved=[],
                    )
                else:
                    if record.get("state") in {
                        "ATTEMPTED",
                        "RECOVERY_REQUIRED",
                    }:
                        raise AppServerHostError(
                            "thread creation remains ambiguous; explicit external "
                            "adjudication is required before another launch"
                        )
                    current = {str(item["id"]) for item in self._list_threads()}
                    baseline = {str(item) for item in record["baseline_thread_ids"]}
                    unknown = sorted(current - baseline)
                    if unknown:
                        self._write_thread_record(
                            record,
                            state="RECOVERY_REQUIRED",
                            unobserved=unknown,
                        )
                        raise AppServerHostError(
                            "thread creation has ambiguous external effects; no duplicate was launched"
                        )
                    # There is no host-visible idempotency token in thread/start.
                    # Persist the irreversible attempt before crossing stdio. A
                    # restart must never infer "not accepted" from an empty current
                    # inventory: the accepted thread may already have been archived
                    # or deleted outside this process.
                    record = self._write_thread_record(record, state="ATTEMPTED")
                    started = _thread_from_result(
                        self.client.request(
                            "thread/start",
                            {
                                "cwd": str(self.repo_root),
                                "approvalPolicy": "never",
                                "sandbox": "workspace-write",
                                "serviceName": "hive_mind_os",
                                "model": self.effective_model,
                                "modelProvider": self.effective_model_provider,
                            },
                        ),
                        "thread/start",
                    )
                    thread_id = str(started["id"])
                    record = self._write_thread_record(
                        record, state="THREAD_STARTED", thread_id=thread_id
                    )
            thread_id = _require_text(thread_id, "thread id", maximum=512)
            if record.get("state") in {
                "THREAD_STARTED",
                "RECOVERY_REQUIRED",
                "PREPARED",
            }:
                result = self.client.request(
                    "thread/name/set",
                    {"threadId": thread_id, "name": f"{title} [{token}]"},
                )
                if not isinstance(result, Mapping):
                    raise AppServerProtocolError(
                        "thread/name/set response is malformed"
                    )
                record = self._write_thread_record(
                    record,
                    state="NAMED",
                    thread_id=thread_id,
                    unobserved=[],
                )
            lifecycle = self._lifecycle(thread_id)
            matching_turns = [
                item
                for item in lifecycle.thread.get("turns", [])
                if isinstance(item, Mapping)
                and any(token in text for text in _walk_strings(item))
            ]
            if len(matching_turns) > 1:
                self._write_thread_record(record, state="RECOVERY_REQUIRED")
                raise AppServerHostError(
                    "multiple turns match one thread adoption token"
                )
            if matching_turns:
                turn_id = _require_text(
                    matching_turns[0].get("id"), "adopted turn id", maximum=512
                )
            else:
                if lifecycle.active_turn:
                    self._write_thread_record(record, state="RECOVERY_REQUIRED")
                    raise AppServerHostError("thread has an unrecognized active turn")
                self.resume_thread(thread_id=thread_id)
                turn = _turn_from_result(
                    self.client.request(
                        "turn/start",
                        {
                            "threadId": thread_id,
                            "input": [
                                {
                                    "type": "text",
                                    "text": f"[hive-mind-adoption:{token}]\n{prompt}",
                                }
                            ],
                            "clientUserMessageId": token,
                            "model": self.effective_model,
                            "cwd": str(self.repo_root),
                            "approvalPolicy": "never",
                            "sandboxPolicy": {
                                "type": "workspaceWrite",
                                "writableRoots": [str(self.repo_root)],
                                "networkAccess": True,
                            },
                        },
                    ),
                    "turn/start",
                )
                turn_id = str(turn["id"])
            self._write_thread_record(
                record,
                state="BOUND",
                thread_id=thread_id,
                turn_id=turn_id,
                unobserved=[],
            )
            binding = self.lookup_thread(idempotency_key=idempotency_key)
            if binding is None:
                raise AppServerHostError("thread binding was not durably installed")
            return binding

    def query_thread(self, *, thread_id: str) -> Mapping[str, object]:
        lifecycle = self._lifecycle(_require_text(thread_id, "thread id", maximum=512))
        return {
            "thread_id": lifecycle.thread_id,
            "thread_status": lifecycle.thread_status,
            "turn_id": lifecycle.turn_id,
            "turn_status": lifecycle.turn_status,
            "terminal": lifecycle.terminal,
        }

    def resume_thread(self, *, thread_id: str) -> Mapping[str, object]:
        thread_id = _require_text(thread_id, "thread id", maximum=512)
        lifecycle = self._lifecycle(thread_id)
        if lifecycle.thread_status == "notLoaded":
            return _thread_from_result(
                self.client.request("thread/resume", {"threadId": thread_id}),
                "thread/resume",
            )
        return dict(lifecycle.thread)

    def interrupt_thread(
        self, *, thread_id: str, turn_id: str | None = None
    ) -> Mapping[str, object]:
        thread_id = _require_text(thread_id, "thread id", maximum=512)
        lifecycle = self._lifecycle(thread_id)
        selected = turn_id or lifecycle.turn_id
        if selected is None or lifecycle.terminal:
            return self.query_thread(thread_id=thread_id)
        selected = _require_text(selected, "turn id", maximum=512)
        result = self.client.request(
            "turn/interrupt", {"threadId": thread_id, "turnId": selected}
        )
        if not isinstance(result, Mapping):
            raise AppServerProtocolError("turn/interrupt response is malformed")
        deadline = time.monotonic() + self.wait_seconds
        while True:
            observed = self.query_thread(thread_id=thread_id)
            if observed.get("terminal"):
                return observed
            if time.monotonic() >= deadline:
                raise AppServerHostError(
                    "turn interruption did not reach a terminal state"
                )
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    def archive_thread(self, *, thread_id: str) -> Mapping[str, object]:
        thread_id = _require_text(thread_id, "thread id", maximum=512)
        active = [item for item in self._list_threads() if item.get("id") == thread_id]
        if active:
            lifecycle = self._lifecycle(thread_id)
            if lifecycle.active_turn:
                self.interrupt_thread(thread_id=thread_id, turn_id=lifecycle.turn_id)
            result = self.client.request("thread/archive", {"threadId": thread_id})
            if not isinstance(result, Mapping):
                raise AppServerProtocolError("thread/archive response is malformed")
        archived = [
            item
            for item in self._list_threads(archived=True)
            if item.get("id") == thread_id
        ]
        if not archived:
            raise AppServerHostError("thread archive could not be verified")
        for path in self.threads_dir.glob("*.json"):
            record = self._read_thread_record(path)
            if (
                record.get("thread_id") == thread_id
                and record.get("state") != "ARCHIVED"
            ):
                with _FileLock(path.with_suffix(".lock"), 30.0):
                    current = self._read_thread_record(path)
                    self._write_thread_record(current, state="ARCHIVED")
        return {"thread_id": thread_id, "archived": True}

    def observe_task_lifecycle(
        self,
        *,
        reservation: Mapping[str, object],
        local_binding: Mapping[str, object],
        idempotency_key: str,
    ) -> Mapping[str, object] | None:
        """Return controller-verifiable terminal host truth, or ``None``.

        The adapter never infers cancellation from reservation expiry.  A live
        or unobservable App Server thread therefore remains WAITING_FOR_HOST in
        the controller.  Only an exact terminal turn, an authenticated absence,
        or an archived thread permits the controller to reconcile capacity.
        """

        _require_digest(idempotency_key, "lifecycle observation idempotency key")
        reservation_id = _require_digest(
            reservation.get("reservation_id"), "host reservation id"
        )
        reservation_execution_id = _require_digest(
            reservation.get("execution_id"), "reservation execution id"
        )
        if reservation_execution_id != self.execution_id:
            raise AppServerHostError(
                "host reservation belongs to another execution adapter"
            )
        if reservation.get("host_id") != self.host_id:
            raise AppServerHostError("host reservation belongs to another provider")
        local_reservation_id = _require_digest(
            reservation.get("local_reservation_id"), "local reservation id"
        )
        capacity_generation = _require_digest(
            reservation.get("capacity_generation"), "capacity generation"
        )
        task_field = (
            "sidecar_task_id"
            if reservation.get("reservation_kind") == "SIDECAR"
            else "task_id"
        )
        host_task_id = _require_text(
            local_binding.get(task_field), "observed host task id", maximum=512
        )
        host_cursor = _require_text(
            local_binding.get("cursor"), "observed host cursor", maximum=512
        )
        capability_digest = _require_digest(
            local_binding.get("capability_digest"), "observed capability digest"
        )
        path = self.reconciliations_dir / (
            "task-" + idempotency_key.removeprefix("sha256:") + ".json"
        )
        if path.exists():
            stored = _strict_json(path.read_bytes(), str(path))
            if (
                not isinstance(stored, dict)
                or frozenset(stored) != _TASK_LIFECYCLE_OBSERVATION_FIELDS
                or stored.get("observation_id")
                != _digest(
                    {
                        key: value
                        for key, value in stored.items()
                        if key != "observation_id"
                    }
                )
                or path.read_bytes() != _canonical(stored) + b"\n"
                or any(
                    stored.get(field) != expected
                    for field, expected in {
                        "host_id": self.host_id,
                        "reservation_id": reservation_id,
                        "execution_id": reservation_execution_id,
                        "local_reservation_id": local_reservation_id,
                        "capacity_generation": capacity_generation,
                        "host_task_id": host_task_id,
                        "host_cursor": host_cursor,
                        "capability_digest": capability_digest,
                    }.items()
                )
            ):
                raise AppServerHostError(
                    "task lifecycle observation evidence changed its request"
                )
            return stored

        # Observe the exact authenticated external task identity. `thread/list`
        # is cwd-filtered by the App Server protocol, so a provider instance for
        # another repository/worktree cannot use list absence as proof that this
        # task is absent. A failed direct read remains unknown and keeps capacity
        # charged; only exact terminal thread evidence permits reclamation.
        try:
            lifecycle = self._lifecycle(host_task_id)
        except (AppServerHostError, AppServerProtocolError):
            return None
        if not lifecycle.terminal:
            return None
        state = "TERMINAL"
        terminal_state = {
            "completed": "SUCCEEDED",
            "failed": "FAILED",
            "interrupted": "CANCELLED",
        }.get(lifecycle.turn_status, "FAILED")
        source_event_id = _digest(
            {
                "thread_id": lifecycle.thread_id,
                "thread_status": lifecycle.thread_status,
                "turn_id": lifecycle.turn_id,
                "turn_status": lifecycle.turn_status,
                "thread": lifecycle.thread,
            }
        )
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": _TASK_LIFECYCLE_OBSERVATION_KIND,
            "host_id": self.host_id,
            "reservation_id": reservation_id,
            "execution_id": reservation_execution_id,
            "local_reservation_id": local_reservation_id,
            "capacity_generation": capacity_generation,
            "host_task_id": host_task_id,
            "host_cursor": host_cursor,
            "capability_digest": capability_digest,
            "state": state,
            "terminal_state": terminal_state,
            "observed_at": _now_text(self.clock),
            "source_event_id": source_event_id,
        }
        observation = {**material, "observation_id": _digest(material)}
        with _FileLock(path.with_suffix(".lock"), 30.0):
            if path.exists():
                stored = _strict_json(path.read_bytes(), str(path))
                if (
                    not isinstance(stored, dict)
                    or frozenset(stored) != _TASK_LIFECYCLE_OBSERVATION_FIELDS
                    or stored.get("observation_id")
                    != _digest(
                        {
                            key: value
                            for key, value in stored.items()
                            if key != "observation_id"
                        }
                    )
                    or path.read_bytes() != _canonical(stored) + b"\n"
                    or any(
                        stored.get(field) != expected
                        for field, expected in {
                            "host_id": self.host_id,
                            "reservation_id": reservation_id,
                            "execution_id": reservation_execution_id,
                            "local_reservation_id": local_reservation_id,
                            "capacity_generation": capacity_generation,
                            "host_task_id": host_task_id,
                            "host_cursor": host_cursor,
                            "capability_digest": capability_digest,
                        }.items()
                    )
                ):
                    raise AppServerHostError(
                        "task lifecycle observation evidence is invalid"
                    )
                return stored
            _atomic_write(path, observation)
        return observation

    def _binding_by_thread(
        self, thread_id: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        matches: list[dict[str, object]] = []
        for path in self.threads_dir.glob("*.json"):
            record = self._read_thread_record(path)
            if record.get("thread_id") == thread_id:
                matches.append(record)
        if len(matches) != 1:
            raise AppServerHostError("thread is unknown or ambiguously bound")
        binding = self.lookup_thread(idempotency_key=str(matches[0]["idempotency_key"]))
        if binding is None:
            raise AppServerHostError("thread is not actively bound")
        return matches[0], dict(binding)

    def _sidecar_by_thread(self, thread_id: str) -> dict[str, object]:
        matches: list[dict[str, object]] = []
        for path in self.sidecars_dir.glob("*.json"):
            record = _read_sealed(path, kind=_SIDECAR_KIND, fields=_SIDECAR_FIELDS)
            if record.get("thread_id") == thread_id:
                matches.append(record)
        if len(matches) != 1:
            raise AppServerHostError("sidecar thread is unknown or ambiguously bound")
        return matches[0]

    def _sidecar_binding(self, record: Mapping[str, object]) -> dict[str, object]:
        sidecar_id = _require_digest(record.get("sidecar_id"), "sidecar id")
        thread_id = _require_text(
            record.get("thread_id"), "sidecar thread id", maximum=512
        )
        primary_path = self._thread_path(sidecar_id)
        primary = self._read_thread_record(primary_path)
        capability = _digest(
            {
                "execution_id": self.execution_id,
                "host_id": self.host_id,
                "idempotency_key": sidecar_id,
                "thread_id": thread_id,
                "module": self.adapter_module_digest,
            }
        )
        cursor = _digest(
            {
                "thread_id": thread_id,
                "idempotency_key": sidecar_id,
                "capability": capability,
            }
        )
        if primary.get("thread_id") != thread_id:
            raise AppServerHostError("sidecar metadata conflicts with thread evidence")
        return {
            "kind": _HOST_SIDECAR_BINDING_KIND,
            "host_id": self.host_id,
            "sidecar_task_id": thread_id,
            "cursor": cursor,
            "capability": capability,
            "idempotency_key": sidecar_id,
            "parent_launch_instruction_id": record["parent_launch_instruction_id"],
        }

    def lookup_sidecar(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        path = self._sidecar_path(idempotency_key)
        if not path.exists():
            return None
        record = _read_sealed(path, kind=_SIDECAR_KIND, fields=_SIDECAR_FIELDS)
        if record.get("state") != "BOUND":
            return None
        self.query_thread(thread_id=str(record["thread_id"]))
        return self._sidecar_binding(record)

    def spawn_sidecar(
        self,
        *,
        prompt: str,
        token_budget: int,
        idempotency_key: str,
        parent_launch_instruction_id: str,
    ) -> Mapping[str, object]:
        if type(token_budget) is not int or token_budget < 1:
            raise AppServerHostError("sidecar token budget is invalid")
        sidecar_id = _require_digest(idempotency_key, "sidecar id")
        parent = _require_digest(
            parent_launch_instruction_id, "sidecar parent launch instruction"
        )
        binding = self.create_thread(
            title=f"Hive Mind sidecar {sidecar_id[-12:]}",
            prompt=prompt,
            idempotency_key=sidecar_id,
        )
        path = self._sidecar_path(sidecar_id)
        with _FileLock(path.with_suffix(".lock"), 30.0):
            if path.exists():
                record = _read_sealed(path, kind=_SIDECAR_KIND, fields=_SIDECAR_FIELDS)
                if (
                    record.get("parent_launch_instruction_id") != parent
                    or record.get("token_budget") != token_budget
                    or record.get("thread_id") != binding.get("task_id")
                ):
                    raise AppServerHostError("sidecar idempotency key was reused")
            else:
                material: dict[str, object] = {
                    "schema_version": 1,
                    "kind": _SIDECAR_KIND,
                    "execution_namespace": self.execution_namespace,
                    "execution_id": self.execution_id,
                    "host_id": self.host_id,
                    "sidecar_id": sidecar_id,
                    "thread_id": binding["task_id"],
                    "parent_launch_instruction_id": parent,
                    "token_budget": token_budget,
                    "state": "BOUND",
                    "created_at": _now_text(self.clock),
                }
                record = {**material, "record_id": _digest(material)}
                _atomic_write(path, record)
        result = self._sidecar_binding(record)
        self._seal_effect_observation(
            effect_kind="SPAWN_SIDECAR",
            idempotency_key=sidecar_id,
            outcome="COMPLETED",
            external_identity=str(result["sidecar_task_id"]),
            result=result,
            unobserved=(),
        )
        return result

    def send_message_to_sidecar(
        self,
        *,
        host_id: str,
        sidecar_task_id: str,
        cursor: str,
        capability: str,
        message: str,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        sidecar = self._sidecar_by_thread(sidecar_task_id)
        binding = self._sidecar_binding(sidecar)
        if (
            host_id != self.host_id
            or binding["cursor"] != cursor
            or binding["capability"] != capability
            or sidecar.get("state") != "BOUND"
        ):
            raise AppServerHostError("sidecar message capability is stale or forged")
        ack = self.send_message_to_thread(
            host_id=host_id,
            task_id=sidecar_task_id,
            cursor=cursor,
            capability=capability,
            message=message,
            idempotency_key=idempotency_key,
        )
        return {
            "kind": _HOST_SIDECAR_ACK_KIND,
            "host_id": host_id,
            "sidecar_task_id": sidecar_task_id,
            "cursor": cursor,
            "capability": capability,
            "accepted": True,
            "message_id": ack["message_id"],
            "idempotency_key": idempotency_key,
        }

    def _sidecar_event_for_target(
        self, target: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        thread_id = _require_text(
            target.get("sidecar_task_id"), "sidecar wait thread id", maximum=512
        )
        record = self._sidecar_by_thread(thread_id)
        binding = self._sidecar_binding(record)
        if (
            target.get("host_id") != self.host_id
            or target.get("cursor") != binding["cursor"]
            or target.get("capability") != binding["capability"]
        ):
            raise AppServerHostError("sidecar wait capability is stale or forged")
        lifecycle = self._lifecycle(thread_id)
        material = {
            "thread_id": thread_id,
            "thread_status": lifecycle.thread_status,
            "turn_id": lifecycle.turn_id,
            "turn_status": lifecycle.turn_status,
        }
        event_cursor = _digest(material)
        if target.get("after_event_cursor") == event_cursor:
            return None
        if lifecycle.turn_status == "completed":
            state = "SUCCEEDED"
        elif (
            lifecycle.turn_status == "failed"
            or lifecycle.thread_status == "systemError"
        ):
            state = "FAILED"
        elif lifecycle.turn_status == "interrupted":
            state = "CANCELLED"
        else:
            status = lifecycle.thread.get("status")
            flags = status.get("activeFlags", []) if isinstance(status, Mapping) else []
            state = "NEEDS_ATTENTION" if "waitingOnApproval" in flags else "ACTIVE"
        event: dict[str, object] = {
            "kind": _HOST_SIDECAR_EVENT_KIND,
            "host_id": self.host_id,
            "sidecar_task_id": thread_id,
            "cursor": binding["cursor"],
            "capability": binding["capability"],
            "sidecar_id": record["sidecar_id"],
            "state": state,
            "event_id": _digest(
                {"sidecar_id": record["sidecar_id"], "cursor": event_cursor}
            ),
            "event_cursor": event_cursor,
        }
        if state == "NEEDS_ATTENTION":
            event["attention"] = "Codex App Server reports waitingOnApproval"
        elif state in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            # App Server proves lifecycle termination, but it does not emit the
            # Hive sidecar-result schema.  The caller converts this intentionally
            # untrusted payload into its bounded adverse result.
            event["result"] = None
        return event

    def wait_activity(
        self,
        primary_targets: Sequence[Mapping[str, object]],
        sidecar_targets: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]:
        if len(primary_targets) + len(sidecar_targets) > 8:
            raise AppServerHostError(
                "combined App Server wait supports at most eight targets"
            )
        deadline = time.monotonic() + self.wait_seconds
        notification_count = len(self.client.notification_snapshot())
        while True:
            primary = [
                item
                for target in primary_targets
                if (item := self._event_for_target(target))
            ]
            sidecars = [
                item
                for target in sidecar_targets
                if (item := self._sidecar_event_for_target(target))
            ]
            if primary or sidecars:
                return {"primary_events": primary, "sidecar_events": sidecars}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {"primary_events": [], "sidecar_events": []}
            notification_count = self.client.wait_notification_change(
                notification_count, min(remaining, 1.0)
            )

    def close_sidecar(
        self,
        *,
        host_id: str,
        sidecar_task_id: str,
        cursor: str,
        capability: str,
        reason: str,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        del reason
        idempotency_key = _require_digest(
            idempotency_key, "sidecar close idempotency key"
        )
        record = self._sidecar_by_thread(sidecar_task_id)
        binding = self._sidecar_binding(record)
        if (
            host_id != self.host_id
            or binding["cursor"] != cursor
            or binding["capability"] != capability
        ):
            raise AppServerHostError("sidecar close capability is stale or forged")
        self.archive_thread(thread_id=sidecar_task_id)
        path = self._sidecar_path(str(record["sidecar_id"]))
        with _FileLock(path.with_suffix(".lock"), 30.0):
            current = _read_sealed(path, kind=_SIDECAR_KIND, fields=_SIDECAR_FIELDS)
            if current.get("state") != "CLOSED":
                material = dict(current)
                material.pop("record_id", None)
                material["state"] = "CLOSED"
                current = {**material, "record_id": _digest(material)}
                _atomic_write(path, current)
        event_cursor = _digest(
            {"sidecar_id": record["sidecar_id"], "close_key": idempotency_key}
        )
        result: dict[str, object] = {
            "kind": _HOST_SIDECAR_EVENT_KIND,
            "host_id": self.host_id,
            "sidecar_task_id": sidecar_task_id,
            "cursor": cursor,
            "capability": capability,
            "sidecar_id": record["sidecar_id"],
            "state": "CANCELLED",
            "event_id": _digest(
                {"sidecar_id": record["sidecar_id"], "event_cursor": event_cursor}
            ),
            "event_cursor": event_cursor,
            "result": None,
        }
        self._seal_effect_observation(
            effect_kind="CLOSE_SIDECAR",
            idempotency_key=idempotency_key,
            outcome="COMPLETED",
            external_identity=sidecar_task_id,
            result=result,
            unobserved=(),
        )
        return result

    def _seal_effect_observation(
        self,
        *,
        effect_kind: str,
        idempotency_key: str,
        outcome: str,
        external_identity: str | None,
        result: Mapping[str, object] | None,
        unobserved: Sequence[tuple[str, str]],
    ) -> Mapping[str, object]:
        effect_kind = _require_text(effect_kind, "host effect kind", maximum=128)
        idempotency_key = _require_digest(
            idempotency_key, "host effect idempotency key"
        )
        if outcome not in {"COMPLETED", "UNKNOWN"}:
            raise AppServerHostError("host effect reconciliation outcome is invalid")
        external_material: dict[str, object] = {
            "schema_version": 1,
            "kind": _EFFECT_EXTERNAL_IDENTITY_KIND,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "host_id": self.host_id,
            "effect_kind": effect_kind,
            "idempotency_key": idempotency_key,
            "external_id": external_identity,
        }
        sealed_external_identity = {
            **external_material,
            "record_id": _digest(external_material),
        }
        unobserved_items: list[Mapping[str, object]] = []
        for item_type, item_identity in unobserved:
            if item_type not in _UNOBSERVED_EFFECT_ITEM_TYPES:
                raise AppServerHostError(
                    "host effect reconciliation item type is invalid"
                )
            item_identity = _require_text(
                item_identity,
                "unobserved host lifecycle item identity",
                maximum=1024,
            )
            item_material: dict[str, object] = {
                "schema_version": 1,
                "kind": _UNOBSERVED_EFFECT_ITEM_KIND,
                "execution_namespace": self.execution_namespace,
                "execution_id": self.execution_id,
                "host_id": self.host_id,
                "effect_kind": effect_kind,
                "idempotency_key": idempotency_key,
                "item_type": item_type,
                "item_identity": item_identity,
            }
            unobserved_items.append(
                {**item_material, "record_id": _digest(item_material)}
            )
        if outcome == "COMPLETED" and (
            external_identity is None or result is None or unobserved_items
        ):
            raise AppServerHostError(
                "completed host effect reconciliation is incomplete"
            )
        if outcome == "UNKNOWN" and (
            external_identity is not None or result is not None or not unobserved_items
        ):
            raise AppServerHostError(
                "unknown host effect reconciliation fabricates terminal evidence"
            )
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": _EFFECT_OBSERVATION_KIND,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "host_id": self.host_id,
            "effect_kind": effect_kind,
            "idempotency_key": idempotency_key,
            "outcome": outcome,
            "external_identity": sealed_external_identity,
            "result": dict(result) if result is not None else None,
            "unobserved_host_lifecycle_items": unobserved_items,
            "observed_at": _now_text(self.clock),
        }
        record = {**material, "record_id": _digest(material)}
        path = self.effect_observations_dir / (
            str(record["record_id"]).removeprefix("sha256:") + ".json"
        )
        with _FileLock(path.with_suffix(".lock"), 30.0):
            if path.exists():
                return self._read_effect_observation(path)
            _atomic_write(path, record)
        return record

    def _read_effect_observation(self, path: Path) -> Mapping[str, object]:
        value = _read_sealed(
            path,
            kind=_EFFECT_OBSERVATION_KIND,
            fields=_EFFECT_OBSERVATION_FIELDS,
        )
        external = value.get("external_identity")
        items = value.get("unobserved_host_lifecycle_items")
        if (
            value.get("execution_namespace") != self.execution_namespace
            or value.get("execution_id") != self.execution_id
            or value.get("host_id") != self.host_id
            or value.get("outcome") not in {"COMPLETED", "UNKNOWN"}
            or not isinstance(external, Mapping)
            or set(external) != _EFFECT_EXTERNAL_IDENTITY_FIELDS
            or not isinstance(items, list)
        ):
            raise AppServerHostError(
                "host effect reconciliation observation is semantically invalid"
            )
        effect_kind = value.get("effect_kind")
        idempotency_key = value.get("idempotency_key")
        external_material = dict(external)
        external_record_id = external_material.pop("record_id", None)
        if (
            external.get("schema_version") != 1
            or external.get("kind") != _EFFECT_EXTERNAL_IDENTITY_KIND
            or external.get("execution_namespace") != self.execution_namespace
            or external.get("execution_id") != self.execution_id
            or external.get("host_id") != self.host_id
            or external.get("effect_kind") != effect_kind
            or external.get("idempotency_key") != idempotency_key
            or external_record_id != _digest(external_material)
        ):
            raise AppServerHostError(
                "host effect external identity is semantically invalid"
            )
        seen_items: set[str] = set()
        for item in items:
            if (
                not isinstance(item, Mapping)
                or set(item) != _UNOBSERVED_EFFECT_ITEM_FIELDS
            ):
                raise AppServerHostError(
                    "unobserved host lifecycle item is semantically invalid"
                )
            item_material = dict(item)
            item_record_id = item_material.pop("record_id", None)
            if (
                item.get("schema_version") != 1
                or item.get("kind") != _UNOBSERVED_EFFECT_ITEM_KIND
                or item.get("execution_namespace") != self.execution_namespace
                or item.get("execution_id") != self.execution_id
                or item.get("host_id") != self.host_id
                or item.get("effect_kind") != effect_kind
                or item.get("idempotency_key") != idempotency_key
                or item.get("item_type") not in _UNOBSERVED_EFFECT_ITEM_TYPES
                or not isinstance(item.get("item_identity"), str)
                or not str(item["item_identity"]).strip()
                or item_record_id != _digest(item_material)
                or item_record_id in seen_items
            ):
                raise AppServerHostError(
                    "unobserved host lifecycle item is semantically invalid"
                )
            seen_items.add(str(item_record_id))
        _parse_time(value.get("observed_at"), "host effect observation time")
        result = value.get("result")
        external_id = external.get("external_id")
        if value.get("outcome") == "COMPLETED":
            if (
                not isinstance(external_id, str)
                or not external_id.strip()
                or not isinstance(result, Mapping)
                or items
            ):
                raise AppServerHostError(
                    "completed host effect observation is semantically invalid"
                )
        elif external_id is not None or result is not None or not items:
            raise AppServerHostError(
                "unknown host effect observation is semantically invalid"
            )
        return value

    def _completed_effect_observation(
        self, *, effect_kind: str, idempotency_key: str
    ) -> Mapping[str, object] | None:
        if not self.effect_observations_dir.is_dir():
            return None
        completed: list[Mapping[str, object]] = []
        for path in sorted(self.effect_observations_dir.glob("*.json")):
            value = self._read_effect_observation(path)
            if (
                value.get("effect_kind") == effect_kind
                and value.get("idempotency_key") == idempotency_key
                and value.get("outcome") == "COMPLETED"
            ):
                completed.append(value)
        if not completed:
            return None
        outcomes = {
            _digest(
                {
                    "external_identity": value["external_identity"],
                    "result": value["result"],
                }
            )
            for value in completed
        }
        if len(outcomes) != 1:
            raise AppServerHostError(
                "host effect has conflicting completed reconciliation evidence"
            )
        return max(
            completed,
            key=lambda value: _parse_time(
                value.get("observed_at"), "host effect observation time"
            ),
        )

    def read_effect_reconciliation(
        self, *, effect_kind: str, idempotency_key: str
    ) -> Mapping[str, object]:
        """Reconcile an ambiguous accepted-before-response effect without retrying it."""

        effect_kind = _require_text(effect_kind, "host effect kind", maximum=128)
        idempotency_key = _require_digest(
            idempotency_key, "host effect idempotency key"
        )
        prior = self._completed_effect_observation(
            effect_kind=effect_kind,
            idempotency_key=idempotency_key,
        )
        if prior is not None:
            return prior
        result: Mapping[str, object] | None = None
        external_identity: str | None = None
        unobserved: list[tuple[str, str]] = []
        if effect_kind == "CREATE_THREAD":
            result = self.lookup_thread(idempotency_key=idempotency_key)
            if result is not None:
                external_identity = str(result["task_id"])
            else:
                path = self._thread_path(idempotency_key)
                if path.exists():
                    record = self._read_thread_record(path)
                    retained = record.get("unobserved_thread_ids", [])
                    if isinstance(retained, list) and retained:
                        unobserved.extend(("THREAD", str(item)) for item in retained)
                    else:
                        unobserved.append(("EFFECT", idempotency_key))
        elif effect_kind == "SPAWN_SIDECAR":
            result = self.lookup_sidecar(idempotency_key=idempotency_key)
            if result is not None:
                external_identity = str(result["sidecar_task_id"])
            else:
                path = self._thread_path(idempotency_key)
                if path.exists():
                    record = self._read_thread_record(path)
                    retained = record.get("unobserved_thread_ids", [])
                    if isinstance(retained, list) and retained:
                        unobserved.extend(("THREAD", str(item)) for item in retained)
                    else:
                        unobserved.append(("EFFECT", idempotency_key))
        elif effect_kind in {"SEND_PRIMARY_MESSAGE", "SEND_SIDECAR_MESSAGE"}:
            path = self._message_path(idempotency_key)
            if path.exists():
                message = _read_sealed(path, kind=_MESSAGE_KIND, fields=_MESSAGE_FIELDS)
                external_identity = str(message["turn_id"])
                result = message
            else:
                unobserved.append(("TURN", idempotency_key))
        else:
            # Close/archive reconciliation requires the exact external thread id;
            # callers use ``read_reconciliation_observation`` for that identity.
            unobserved.append(("EFFECT", idempotency_key))
        return self._seal_effect_observation(
            effect_kind=effect_kind,
            idempotency_key=idempotency_key,
            outcome="COMPLETED" if result is not None else "UNKNOWN",
            external_identity=external_identity,
            result=result,
            unobserved=unobserved,
        )

    def send_message_to_thread(
        self,
        *,
        host_id: str,
        task_id: str,
        cursor: str,
        capability: str,
        message: str,
        idempotency_key: str,
    ) -> Mapping[str, object]:
        if host_id != self.host_id:
            raise AppServerHostError("message host id differs from lifecycle authority")
        message = _require_text(message, "thread message")
        idempotency_key = _require_digest(idempotency_key, "message idempotency key")
        record, binding = self._binding_by_thread(task_id)
        if binding.get("cursor") != cursor or binding.get("capability") != capability:
            raise AppServerHostError("message binding capability is stale or forged")
        path = self._message_path(idempotency_key)
        token = "message-" + idempotency_key.removeprefix("sha256:")
        with _FileLock(path.with_suffix(".lock"), min(float(self.wait_seconds), 120.0)):
            if path.exists():
                saved = _read_sealed(path, kind=_MESSAGE_KIND, fields=_MESSAGE_FIELDS)
                if saved.get("message_digest") != _digest({"message": message}):
                    raise AppServerHostError("message idempotency key was reused")
                turn_id = _require_text(
                    saved.get("turn_id"), "message turn id", maximum=512
                )
            else:
                lifecycle = self._lifecycle(task_id)
                matching = [
                    item
                    for item in lifecycle.thread.get("turns", [])
                    if isinstance(item, Mapping)
                    and any(token in text for text in _walk_strings(item))
                ]
                if len(matching) > 1:
                    raise AppServerHostError("multiple turns match one message token")
                if matching:
                    turn_id = _require_text(
                        matching[0].get("id"), "message turn id", maximum=512
                    )
                elif lifecycle.active_turn and lifecycle.turn_id is not None:
                    response = self.client.request(
                        "turn/steer",
                        {
                            "threadId": task_id,
                            "expectedTurnId": lifecycle.turn_id,
                            "clientUserMessageId": token,
                            "input": [
                                {
                                    "type": "text",
                                    "text": f"[hive-mind-{token}]\n{message}",
                                }
                            ],
                        },
                    )
                    if not isinstance(response, Mapping):
                        raise AppServerProtocolError("turn/steer response is malformed")
                    turn_id = _require_text(
                        response.get("turnId"), "steered turn id", maximum=512
                    )
                else:
                    self.resume_thread(thread_id=task_id)
                    turn = _turn_from_result(
                        self.client.request(
                            "turn/start",
                            {
                                "threadId": task_id,
                                "input": [
                                    {
                                        "type": "text",
                                        "text": f"[hive-mind-{token}]\n{message}",
                                    }
                                ],
                                "clientUserMessageId": token,
                                "model": self.effective_model,
                            },
                        ),
                        "turn/start",
                    )
                    turn_id = str(turn["id"])
                material: dict[str, object] = {
                    "schema_version": 1,
                    "kind": _MESSAGE_KIND,
                    "execution_namespace": self.execution_namespace,
                    "execution_id": self.execution_id,
                    "host_id": self.host_id,
                    "thread_id": task_id,
                    "idempotency_key": idempotency_key,
                    "message_digest": _digest({"message": message}),
                    "turn_id": turn_id,
                    "state": "ACCEPTED",
                    "created_at": _now_text(self.clock),
                }
                _atomic_write(path, {**material, "record_id": _digest(material)})
        return {
            "kind": _HOST_ACK_KIND,
            "host_id": self.host_id,
            "task_id": task_id,
            "cursor": cursor,
            "capability": capability,
            "accepted": True,
            "message_id": _digest(
                {
                    "idempotency_key": idempotency_key,
                    "thread_id": task_id,
                    "turn_id": turn_id,
                }
            ),
            "idempotency_key": idempotency_key,
        }

    def _event_for_target(
        self, target: Mapping[str, object]
    ) -> Mapping[str, object] | None:
        if target.get("host_id") != self.host_id:
            raise AppServerHostError("wait target host id differs")
        task_id = _require_text(
            target.get("task_id"), "wait target task id", maximum=512
        )
        _, binding = self._binding_by_thread(task_id)
        if (
            target.get("cursor") != binding["cursor"]
            or target.get("capability") != binding["capability"]
        ):
            raise AppServerHostError("wait target capability is stale or forged")
        lifecycle = self._lifecycle(task_id)
        material = {
            "thread_id": task_id,
            "thread_status": lifecycle.thread_status,
            "turn_id": lifecycle.turn_id,
            "turn_status": lifecycle.turn_status,
        }
        event_cursor = _digest(material)
        if target.get("after_event_cursor") == event_cursor:
            return None
        if lifecycle.turn_status == "completed":
            state = "SUCCEEDED"
        elif (
            lifecycle.turn_status == "failed"
            or lifecycle.thread_status == "systemError"
        ):
            state = "FAILED"
        elif lifecycle.turn_status == "interrupted":
            state = "CANCELLED"
        else:
            status = lifecycle.thread.get("status")
            active_flags = (
                status.get("activeFlags", []) if isinstance(status, Mapping) else []
            )
            state = (
                "NEEDS_ATTENTION" if "waitingOnApproval" in active_flags else "ACTIVE"
            )
        event: dict[str, object] = {
            "kind": _HOST_EVENT_KIND,
            "host_id": self.host_id,
            "task_id": task_id,
            "cursor": binding["cursor"],
            "capability": binding["capability"],
            "state": state,
            "event_id": _digest({"task_id": task_id, "event_cursor": event_cursor}),
            "event_cursor": event_cursor,
        }
        if state == "NEEDS_ATTENTION":
            event["attention"] = "Codex App Server reports waitingOnApproval"
        return event

    def wait_threads(
        self, targets: Sequence[Mapping[str, object]]
    ) -> Sequence[Mapping[str, object]]:
        if not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
            raise AppServerHostError("wait targets must be a sequence")
        if len(targets) > 8:
            raise AppServerHostError("App Server wait supports at most eight targets")
        deadline = time.monotonic() + self.wait_seconds
        notification_count = len(self.client.notification_snapshot())
        while True:
            events = [
                event for target in targets if (event := self._event_for_target(target))
            ]
            if events:
                return events
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return []
            notification_count = self.client.wait_notification_change(
                notification_count, min(remaining, 1.0)
            )

    def inspect_runtime_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        if Path(repo_root).absolute() != self.repo_root:
            raise AppServerHostError(
                "runtime authority requested for another repository"
            )
        claims = self.plane.active_claims()
        if not isinstance(claims, Mapping):
            raise AppServerHostError("control-plane claim inventory is malformed")
        release = self.plane.current_release()
        lease = None
        quiescent = not claims
        if isinstance(release, Mapping) and isinstance(release.get("release_id"), str):
            snapshot = self.plane.round_authority_snapshot(str(release["release_id"]))
            lease = snapshot.get("active_validation_lease")
            quiescent = (
                quiescent
                and not snapshot.get("active_host_reservations")
                and lease is None
            )
        return {
            "target_branch": str(self.plane.target_branch),
            "active_claims": [dict(item) for item in claims.values()],
            "active_validation_lease": dict(lease)
            if isinstance(lease, Mapping)
            else None,
            "quiescent": bool(quiescent),
        }

    def _lifecycle_counts(self) -> tuple[int, int, int]:
        active_threads = 0
        active_turns = 0
        unobserved = self.client.adverse_items
        known_ids: set[str] = set()
        for path in self.threads_dir.glob("*.json"):
            record = self._read_thread_record(path)
            unknown = record.get("unobserved_thread_ids")
            if not isinstance(unknown, list):
                raise AppServerHostError(
                    "thread evidence has invalid unobserved identities"
                )
            unobserved += len(unknown)
            thread_id = record.get("thread_id")
            if not isinstance(thread_id, str):
                if record.get("state") not in {"ARCHIVED"}:
                    unobserved += 1
                continue
            known_ids.add(thread_id)
            if record.get("state") == "ARCHIVED":
                continue
            try:
                lifecycle = self._lifecycle(thread_id)
            except AppServerHostError:
                unobserved += 1
                continue
            if not lifecycle.terminal:
                active_threads += 1
            if lifecycle.active_turn:
                active_turns += 1
        marker = "hive-" + self.execution_id.removeprefix("sha256:")[:12] + "-"
        for thread in self._list_threads(search_term=marker):
            name = thread.get("name")
            if (
                isinstance(name, str)
                and self.execution_id.removeprefix("sha256:")[:12] in name
            ):
                if thread.get("id") not in known_ids:
                    unobserved += 1
        return active_threads, active_turns, unobserved

    def capture_lifecycle_observation(
        self, *, frontier_id: str, disposition: str
    ) -> Mapping[str, object]:
        frontier_id = _require_digest(frontier_id, "frontier id")
        disposition = _require_text(disposition, "lifecycle disposition", maximum=64)
        stored_fields = frozenset(
            (_OBSERVATION_FIELDS - {"observation_id"}) | {"record_id"}
        )

        def public(value: Mapping[str, object]) -> dict[str, object]:
            translated = dict(value)
            translated["observation_id"] = translated.pop("record_id")
            return translated

        key_id = _digest(
            {
                "kind": "hive-mind-host-lifecycle-observation-key-v1",
                "execution_namespace": self.execution_namespace,
                "execution_id": self.execution_id,
                "host_id": self.host_id,
                "frontier_id": frontier_id,
                "disposition": disposition,
            }
        )
        key_path = self.observations_dir / (
            key_id.removeprefix("sha256:") + ".key.json"
        )
        with _FileLock(key_path.with_suffix(".lock"), 30.0):
            if key_path.exists():
                return public(
                    _read_sealed(
                        key_path,
                        kind=_OBSERVATION_KIND,
                        fields=stored_fields,
                    )
                )
            candidates: list[dict[str, object]] = []
            for candidate_path in self.observations_dir.glob("*.json"):
                if candidate_path.name.endswith(".key.json"):
                    continue
                candidate = _read_sealed(
                    candidate_path,
                    kind=_OBSERVATION_KIND,
                    fields=stored_fields,
                )
                if (
                    candidate.get("execution_id") == self.execution_id
                    and candidate.get("host_id") == self.host_id
                    and candidate.get("frontier_id") == frontier_id
                    and candidate.get("disposition") == disposition
                ):
                    candidates.append(candidate)
            if len(candidates) > 1:
                raise AppServerHostError(
                    "multiple lifecycle observations match one durable frontier"
                )
            if candidates:
                _atomic_write(key_path, candidates[0])
                return public(candidates[0])
            active_threads, active_turns, unobserved = self._lifecycle_counts()
            material: dict[str, object] = {
                "schema_version": 1,
                "kind": _OBSERVATION_KIND,
                "execution_namespace": self.execution_namespace,
                "execution_id": self.execution_id,
                "host_id": self.host_id,
                "frontier_id": frontier_id,
                "disposition": disposition,
                "active_host_threads": active_threads,
                "active_host_turns": active_turns,
                "unobserved_host_lifecycle_items": unobserved,
                "observed_at": _now_text(self.clock),
            }
            observation = {**material, "observation_id": _digest(material)}
            path = self.observations_dir / (
                str(observation["observation_id"]).removeprefix("sha256:") + ".json"
            )
            stored = dict(observation)
            stored["record_id"] = stored.pop("observation_id")
            if path.exists():
                existing = _read_sealed(
                    path,
                    kind=_OBSERVATION_KIND,
                    fields=stored_fields,
                )
                if existing != stored:
                    raise AppServerHostError("lifecycle observation identity collided")
            else:
                _atomic_write(path, stored)
            _atomic_write(key_path, stored)
            return observation

    def capture_terminal_lifecycle_observation(
        self,
        *,
        execution_namespace: str,
        execution_id: str,
        execution_dir: str | Path,
        host_id: str,
        frontier_id: str,
        release_id: str,
    ) -> Mapping[str, object]:
        """Seal a zero-lifecycle candidate without judging DAG completion."""

        if (
            execution_namespace != self.execution_namespace
            or execution_id != self.execution_id
            or Path(execution_dir).absolute() != self.execution_dir
            or host_id != self.host_id
        ):
            raise AppServerHostError(
                "terminal lifecycle capture changed the execution identity"
            )
        _require_digest(release_id, "terminal lifecycle release")
        current_release = self.plane.current_release()
        if (
            not isinstance(current_release, Mapping)
            or current_release.get("release_id") != release_id
        ):
            raise AppServerHostError(
                "terminal lifecycle capture is not bound to the current release"
            )
        active_threads, active_turns, unobserved = self._lifecycle_counts()
        if active_threads or active_turns or unobserved:
            raise AppServerHostError(
                "terminal lifecycle capture requires zero authenticated host activity"
            )
        return self.capture_lifecycle_observation(
            frontier_id=frontier_id,
            disposition="PLAN_QUIESCENT",
        )

    def read_lifecycle_observation(
        self,
        *,
        execution_namespace: str,
        execution_id: str,
        execution_dir: str | Path,
        host_id: str,
        frontier_id: str,
        observation_id: str,
    ) -> Mapping[str, object]:
        observation_id = _require_digest(observation_id, "lifecycle observation id")
        if (
            execution_namespace != self.execution_namespace
            or execution_id != self.execution_id
            or Path(execution_dir).absolute() != self.execution_dir
            or host_id != self.host_id
        ):
            raise AppServerHostError(
                "lifecycle observation request changed execution identity"
            )
        path = self.observations_dir / (
            observation_id.removeprefix("sha256:") + ".json"
        )
        stored = _read_sealed(
            path,
            kind=_OBSERVATION_KIND,
            fields=frozenset(
                (_OBSERVATION_FIELDS - {"observation_id"}) | {"record_id"}
            ),
        )
        result = dict(stored)
        result["observation_id"] = result.pop("record_id")
        if (
            result.get("frontier_id") != frontier_id
            or result.get("observation_id") != observation_id
        ):
            raise AppServerHostError(
                "lifecycle observation does not match the requested frontier"
            )
        return result

    def read_reconciliation_observation(
        self,
        *,
        reservation_id: str,
        thread_id: str | None,
        turn_id: str | None,
    ) -> Mapping[str, object]:
        """Report exact external state without treating clock expiry as cancellation.

        A global reservation may be released only when ``safe_to_release_capacity``
        is true.  An expired timestamp alone never makes that true.
        """

        reservation_id = _require_digest(reservation_id, "reservation id")
        lifecycle: _Lifecycle | None = None
        unobserved = self.client.adverse_items
        if thread_id is not None:
            thread_id = _require_text(thread_id, "thread id", maximum=512)
            try:
                lifecycle = self._lifecycle(thread_id)
            except AppServerHostError:
                unobserved += 1
        cancellation = bool(
            lifecycle is not None and lifecycle.turn_status == "interrupted"
        )
        terminal = bool(lifecycle is not None and lifecycle.terminal)
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": _RECONCILIATION_KIND,
            "execution_namespace": self.execution_namespace,
            "execution_id": self.execution_id,
            "host_id": self.host_id,
            "reservation_id": reservation_id,
            "thread_id": thread_id,
            "turn_id": turn_id
            if turn_id is not None
            else (lifecycle.turn_id if lifecycle else None),
            "thread_status": lifecycle.thread_status if lifecycle else "UNOBSERVED",
            "turn_status": lifecycle.turn_status if lifecycle else None,
            "external_cancellation_proven": cancellation,
            "safe_to_release_capacity": terminal and unobserved == 0,
            "unobserved_host_lifecycle_items": unobserved,
            "observed_at": _now_text(self.clock),
        }
        record = {**material, "record_id": _digest(material)}
        path = self.reconciliations_dir / (
            record["record_id"].removeprefix("sha256:") + ".json"
        )
        with _FileLock(path.with_suffix(".lock"), 30.0):
            if path.exists():
                return _read_sealed(
                    path, kind=_RECONCILIATION_KIND, fields=_RECONCILIATION_FIELDS
                )
            _atomic_write(path, record)
        return record


def create_app_server_host(
    *,
    plane: Any,
    host_id: str | None,
    execution_namespace: str,
    execution_id: str,
    execution_dir: str | Path,
    host_runtime_dir: str | Path,
    wait_seconds: int,
    adapter_module_digest: str,
) -> CodexAppServerHost:
    """Create the production adapter used by the sealed-path CLI loader."""

    return CodexAppServerHost(
        plane=plane,
        host_id=host_id,
        execution_namespace=execution_namespace,
        execution_id=execution_id,
        execution_dir=execution_dir,
        host_runtime_dir=host_runtime_dir,
        wait_seconds=wait_seconds,
        adapter_module_digest=adapter_module_digest,
    )


__all__ = [
    "APP_SERVER_HOST_ADAPTER_KIND",
    "APP_SERVER_HOST_ADAPTER_VERSION",
    "AppServerHostError",
    "AppServerProtocolError",
    "CodexAppServerHost",
    "create_app_server_host",
]
