"""Card-only compatibility adapter for an attended Codex parent.

The supported Codex SDK and App Server APIs can manage local Codex threads, but this
adapter intentionally does not use them. It therefore never claims autonomous host
authority. ``create_thread`` writes a durable session card that an operator may open,
and progress is read back from repository evidence rather than from the host: claim
commits, pushed work, and receipt commits are authored by fixed autopilot identities,
and blocker packets land in the control plane's own state.

That inversion is the point. ``wait_threads`` polls Git under a wall-clock
deadline instead of waiting on a conversation no API can observe, so the wave
supervisor in ``host_execution.execute_contract`` cannot hang on this host —
nothing in the loop waits on the host at all. A run ends either with terminal
evidence or with a bounded no-progress verdict naming exactly which sessions the
operator still has to open.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from controller import (
    AUTHORITY_ID,
    RUNTIME_BOOTSTRAP_LOCK,
    SCHEMA_VERSION,
    parse_time,
    read_json,
    runtime_file_lock_is_held,
)
from orchestration import (
    ACTIVE_BINDING_STATES,
    OrchestrationError,
    binding_events,
    launch_authority_guard,
    launch_binding,
)

HOST_ID = "codex-attended"
CAPABILITY = "durable_user_owned_task"
CURSOR = "attended-v1"
CREATE_KIND = "hive-mind-host-task-binding-v1"
EVENT_KIND = "hive-mind-host-event-v1"
ACK_KIND = "hive-mind-host-message-ack-v1"
RECEIPT_IDENTITY = "autopilot-receipt@hive-mind.invalid"
CLAIM_IDENTITY = "autopilot-claim@hive-mind.invalid"
MIGRATION_KIND = "hive-mind-attended-ledger-migration-v1"
MIGRATION_SCHEMA_VERSION = 1

_DIGEST_TEXT = re.compile(r"sha256:[0-9a-f]{64}\Z")
_LEGACY_AUTHORITY_STATES = frozenset({"BOUND"})
_ATTENDED_ENTRY_REQUIRED_FIELDS = frozenset(
    {
        "host_id",
        "task_id",
        "cursor",
        "capability",
        "capability_digest",
        "node_id",
        "title",
        "card",
    }
)
_ATTENDED_ENTRY_LEGACY_OPTIONAL_FIELDS = frozenset(
    {"authority_state", "card_scope", "card_digest", "prompt_digest"}
)
_ATTENDED_ENTRY_FIELDS = _ATTENDED_ENTRY_REQUIRED_FIELDS | frozenset(
    {"card_scope", "card_digest", "prompt_digest"}
)
_MIGRATION_CARD_FIELDS = frozenset(
    {
        "launch_instruction_id",
        "card_digest",
        "bytes",
        "archive",
        "normalized_card",
        "normalized_entry_digest",
    }
)
_MIGRATION_BASE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "status",
        "actor",
        "recorded_at",
        "source_ledger_digest",
        "source_ledger_bytes",
        "source_archive",
        "normalized_ledger_digest",
        "entries",
        "cards",
    }
)
_MIGRATION_COMPLETE_FIELDS = _MIGRATION_BASE_FIELDS | frozenset(
    {"prepared_manifest_digest"}
)


class AttendedHostError(RuntimeError):
    """Raised when the attended host is asked for something it cannot honour."""


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _mapping_digest(value: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _bytes_digest(encoded)


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"non-finite JSON constant {value}")


def _finite_json(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _finite_json(item) for key, item in value.items()
        )
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    return value is None or type(value) in {str, int, bool}


def _canonical_document(value: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _strict_json_object(encoded: bytes, label: str) -> dict[str, Any]:
    """Parse one exact, finite, canonical JSON object or fail closed."""

    try:
        text = encoded.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise AttendedHostError(f"{label} is invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise AttendedHostError(f"{label} must be a JSON object")
    if not _finite_json(value):
        raise AttendedHostError(f"{label} contains non-finite JSON")
    try:
        canonical = _canonical_document(value)
    except (TypeError, ValueError, UnicodeError) as error:
        raise AttendedHostError(f"{label} is not canonical JSON") from error
    if encoded != canonical:
        raise AttendedHostError(f"{label} uses a noncanonical JSON encoding")
    return dict(value)


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


class AttendedCodexHost:
    """A ``HostAdapter`` for a host that only a human can actually drive."""

    # Repository evidence can prove delivery outcomes, but it cannot prove that
    # a read-only attended preparation chat stopped.  Such work must therefore
    # be omitted before contract signing rather than issued with a fabricated
    # terminal lifecycle.
    supports_preparation_only = False

    def __init__(
        self,
        plane: Any,
        *,
        wait_seconds: int = 60,
        poll_seconds: int = 5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if wait_seconds < 1 or poll_seconds < 1:
            raise AttendedHostError("attended host wait bounds must be positive")
        self.plane = plane
        self.repo_root = Path(plane.repo_root)
        self.wait_seconds = wait_seconds
        self.poll_seconds = poll_seconds
        self.clock = clock
        self.sleep = sleep
        # Migration locks, receipts, and the pre-READY attended source live in
        # the selected repository coordination root.  Once an execution
        # identity exists, cards and their registry are execution authority.
        # Keep those roots distinct: ``plane.state_dir`` deliberately points at
        # the checkout-local legacy path before READY and is therefore not a
        # valid substitute for an explicit external coordination root.
        coordination_dir = getattr(plane, "coordination_dir", None)
        if coordination_dir is None:
            coordination_dir = plane.state_dir
        self.coordination_dir = Path(coordination_dir)
        execution_dir = Path(getattr(plane, "execution_dir", self.coordination_dir))
        execution_identity = execution_dir / "execution-identity.json"
        self.authority_dir = (
            execution_dir if execution_identity.is_file() else self.coordination_dir
        )
        self.host_dir = self.authority_dir / "host"
        self.cards_dir = self.host_dir / "cards"
        self.ledger_path = self.host_dir / "attended-threads.json"
        self._nodes: dict[str, str] = {}

    def _require_current_authority_phase(self) -> None:
        """Reject reuse across the pre-READY -> execution-authority boundary."""

        execution_dir = Path(
            getattr(self.plane, "execution_dir", self.coordination_dir)
        )
        identity = execution_dir / "execution-identity.json"
        expected = execution_dir if identity.is_file() else self.coordination_dir
        if self.authority_dir.absolute() != expected.absolute():
            raise AttendedHostError(
                "attended host authority phase changed; construct a fresh adapter"
            )

    # ------------------------------------------------------------------ ledger

    def _raw_ledger_unlocked(self) -> tuple[bytes, Mapping[str, object]]:
        """Read the registry without forgiving corruption or changing its bytes."""

        self._require_current_authority_phase()
        if _is_link_like(self.host_dir):
            raise AttendedHostError("attended ledger path uses a link")
        if not self.ledger_path.is_file():
            return b"", {}
        if _is_link_like(self.ledger_path):
            raise AttendedHostError("attended ledger path uses a link")
        try:
            encoded = self.ledger_path.read_bytes()
        except OSError as error:
            raise AttendedHostError(
                f"attended ledger is unreadable: {error}"
            ) from error
        return encoded, _strict_json_object(encoded, "attended ledger")

    @staticmethod
    def _require_digest(value: object, label: str) -> str:
        if not isinstance(value, str) or _DIGEST_TEXT.fullmatch(value) is None:
            raise AttendedHostError(f"{label} must be a sha256 identity")
        return value

    def _canonical_card_path(self, task_id: str) -> str:
        self._require_current_authority_phase()
        return (
            (self.cards_dir / f"{task_id}.md")
            .relative_to(self.authority_dir)
            .as_posix()
        )

    def _validate_ledger_entry(
        self,
        instruction_id: object,
        raw_entry: object,
        *,
        allow_legacy: bool,
    ) -> tuple[dict[str, Any], bool]:
        """Validate one immutable attended binding snapshot exactly."""

        instruction = self._require_digest(
            instruction_id,
            "attended ledger launch instruction identity",
        )
        if not isinstance(raw_entry, Mapping):
            raise AttendedHostError("attended ledger entry is invalid")
        entry = dict(raw_entry)
        fields = frozenset(entry)
        if fields == _ATTENDED_ENTRY_FIELDS:
            legacy = False
        elif (
            allow_legacy
            and _ATTENDED_ENTRY_REQUIRED_FIELDS <= fields
            and fields
            <= _ATTENDED_ENTRY_REQUIRED_FIELDS | _ATTENDED_ENTRY_LEGACY_OPTIONAL_FIELDS
        ):
            legacy = True
        else:
            unexpected = sorted(
                fields
                - (
                    _ATTENDED_ENTRY_REQUIRED_FIELDS
                    | _ATTENDED_ENTRY_LEGACY_OPTIONAL_FIELDS
                )
            )
            missing = sorted(_ATTENDED_ENTRY_REQUIRED_FIELDS - fields)
            detail = ", ".join(
                [
                    *(f"unexpected {field}" for field in unexpected),
                    *(f"missing {field}" for field in missing),
                ]
            )
            raise AttendedHostError(
                "attended ledger entry does not match an exact supported schema"
                + (f": {detail}" if detail else "")
            )
        expected = {
            "host_id": HOST_ID,
            "task_id": "attended-" + _digest(instruction)[:32],
            "cursor": CURSOR,
            "capability": CAPABILITY,
            "capability_digest": "sha256:" + _digest(CAPABILITY),
        }
        for field, expected_value in expected.items():
            if entry.get(field) != expected_value:
                raise AttendedHostError(
                    f"attended ledger entry has conflicting {field}"
                )
        if not isinstance(entry.get("node_id"), str):
            raise AttendedHostError("attended ledger node identity is invalid")
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            raise AttendedHostError("attended ledger title is invalid")
        card = entry.get("card")
        if not isinstance(card, str) or not card:
            raise AttendedHostError("attended ledger card path is invalid")
        scope = entry.get("card_scope")
        if scope is not None and scope != "runtime_state":
            raise AttendedHostError("attended ledger card scope is invalid")
        if not legacy and scope != "runtime_state":
            raise AttendedHostError("attended ledger card scope is invalid")
        if not legacy and card != self._canonical_card_path(str(entry["task_id"])):
            raise AttendedHostError("attended ledger card path is noncanonical")
        card_digest = entry.get("card_digest")
        if card_digest is not None:
            self._require_digest(card_digest, "attended ledger card digest")
        elif not legacy:
            raise AttendedHostError("attended ledger card digest is missing")
        prompt_digest = entry.get("prompt_digest")
        if prompt_digest is not None:
            self._require_digest(prompt_digest, "attended ledger prompt digest")
        elif not legacy and "prompt_digest" not in entry:
            raise AttendedHostError("attended ledger prompt digest is missing")
        if "authority_state" in entry:
            if entry["authority_state"] not in _LEGACY_AUTHORITY_STATES:
                raise AttendedHostError("attended legacy authority state is invalid")
            legacy = True
        return entry, legacy

    def _validate_ledger_document(
        self,
        value: Mapping[str, object],
        *,
        allow_legacy: bool,
    ) -> tuple[dict[str, dict[str, Any]], bool]:
        ledger: dict[str, dict[str, Any]] = {}
        task_owners: dict[str, str] = {}
        migrated = False
        for instruction_id, raw_entry in value.items():
            entry, legacy = self._validate_ledger_entry(
                instruction_id,
                raw_entry,
                allow_legacy=allow_legacy,
            )
            instruction = str(instruction_id)
            task_id = str(entry["task_id"])
            prior_instruction = task_owners.get(task_id)
            if prior_instruction is not None and prior_instruction != instruction:
                raise AttendedHostError("attended ledger reuses a task identity")
            task_owners[task_id] = instruction
            ledger[instruction] = entry
            migrated = migrated or legacy
        return ledger, migrated

    def _ledger_unlocked(
        self,
        *,
        allow_legacy: bool = False,
    ) -> tuple[dict[str, Any], bool, dict[str, bytes]]:
        """Validate the registry and optionally describe its explicit migration.

        Normal reads reject legacy fields and paths.  Only
        :meth:`migrate_legacy_ledger` opts into normalization, which prevents an
        ordinary lookup or create operation from silently changing authority.
        """

        _, value = self._raw_ledger_unlocked()
        ledger, migrated = self._validate_ledger_document(
            value,
            allow_legacy=allow_legacy,
        )
        card_bytes_by_instruction: dict[str, bytes] = {}
        for instruction_id, entry in ledger.items():
            if "authority_state" in entry:
                entry.pop("authority_state", None)
                migrated = True
            task_id = str(entry["task_id"])
            scope = entry.get("card_scope")
            resolved = self._resolve_card(entry, allow_legacy=allow_legacy)
            try:
                card_bytes = resolved.read_bytes()
            except OSError as error:
                raise AttendedHostError(
                    f"attended session card is unavailable: {error}"
                ) from error
            actual_digest = _bytes_digest(card_bytes)
            stored_digest = entry.get("card_digest")
            if stored_digest is not None and stored_digest != actual_digest:
                raise AttendedHostError(
                    "attended session card failed its integrity digest"
                )
            if stored_digest is None:
                entry["card_digest"] = actual_digest
                migrated = True
            if "prompt_digest" not in entry:
                # A historical card can prove its own bytes but not the original
                # prompt boundary.  Preserve that uncertainty explicitly instead
                # of inventing an input digest during migration.
                entry["prompt_digest"] = None
                migrated = True
            expected_card = self.cards_dir / f"{task_id}.md"
            if _is_link_like(self.cards_dir) or _is_link_like(expected_card):
                raise AttendedHostError("attended ledger card path uses a link")
            expected_relative = self._canonical_card_path(task_id)
            if scope != "runtime_state" or resolved != expected_card.resolve():
                entry["card_scope"] = "runtime_state"
                entry["card"] = expected_relative
                migrated = True
            elif entry["card"] != expected_relative:
                if not allow_legacy:
                    raise AttendedHostError("attended ledger card path is noncanonical")
                entry["card"] = expected_relative
                migrated = True
            self._validate_ledger_entry(
                instruction_id,
                entry,
                allow_legacy=False,
            )
            card_bytes_by_instruction[instruction_id] = card_bytes
        return ledger, migrated, card_bytes_by_instruction

    def _ledger(self) -> dict[str, Any]:
        if not self.ledger_path.is_file():
            return {}
        with self.plane.runtime_read_lock("attended-host.lock"):
            ledger, _, _ = self._ledger_unlocked()
            return ledger

    def _resolve_card(
        self,
        entry: Mapping[str, Any],
        *,
        allow_legacy: bool = False,
    ) -> Path:
        raw = entry.get("card")
        if not isinstance(raw, str) or not raw:
            raise AttendedHostError("attended ledger card path is invalid")
        normalized_raw = raw.replace("\\", "/")
        state_dir = self.authority_dir.resolve()
        if entry.get("card_scope") == "runtime_state":
            candidate = state_dir / normalized_raw
            allowed_root = self.cards_dir.resolve()
        else:
            if not allow_legacy:
                raise AttendedHostError(
                    "attended ledger requires explicit authority migration"
                )
            legacy = Path(normalized_raw)
            roots = [self.repo_root.resolve()]
            if state_dir.name == "state" and state_dir.parent.name == ".autopilot":
                roots.append(state_dir.parents[1])
            roots = list(dict.fromkeys(roots))
            if legacy.is_absolute():
                candidate = legacy
                matches = [
                    root / ".autopilot" / "state" / "host" / "cards"
                    for root in roots
                    if legacy.resolve().is_relative_to(
                        (root / ".autopilot" / "state" / "host" / "cards").resolve()
                    )
                ]
            else:
                candidates = [root / legacy for root in roots]
                existing = list(
                    dict.fromkeys(
                        path.resolve() for path in candidates if path.is_file()
                    )
                )
                if len(existing) > 1:
                    raise AttendedHostError(
                        "attended legacy card is ambiguous across linked worktrees"
                    )
                candidate = existing[0] if existing else candidates[0]
                matches = [
                    root / ".autopilot" / "state" / "host" / "cards"
                    for root in roots
                    if candidate.resolve().is_relative_to(
                        (root / ".autopilot" / "state" / "host" / "cards").resolve()
                    )
                ]
            if len(matches) != 1:
                raise AttendedHostError(
                    "attended legacy card is outside or ambiguous across runtime roots"
                )
            allowed_root = matches[0].resolve()
        if _is_link_like(candidate):
            raise AttendedHostError("attended ledger card path uses a link")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(allowed_root):
            raise AttendedHostError(
                "attended ledger card escapes its allowed card directory"
            )
        current = allowed_root
        try:
            relative = resolved.relative_to(allowed_root)
        except ValueError as error:  # guarded above; retained as a fail-closed boundary
            raise AttendedHostError("attended ledger card path is invalid") from error
        for part in relative.parts:
            current /= part
            if _is_link_like(current):
                raise AttendedHostError("attended ledger card path uses a link")
        return resolved

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=path.name + ".", dir=path.parent
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(5):
                try:
                    os.replace(temporary_path, path)
                except PermissionError:
                    if os.name != "nt" or attempt == 4:
                        raise
                    time.sleep(0.01 * (2**attempt))
                else:
                    AttendedCodexHost._fsync_directory(path.parent)
                    return
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _atomic_write_bytes(path: Path, value: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=path.name + ".", dir=path.parent
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            for attempt in range(5):
                try:
                    os.replace(temporary_path, path)
                except PermissionError:
                    if os.name != "nt" or attempt == 4:
                        raise
                    time.sleep(0.01 * (2**attempt))
                else:
                    AttendedCodexHost._fsync_directory(path.parent)
                    return
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _write_ledger_unlocked(self, value: Mapping[str, Any]) -> None:
        self.host_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_bytes(self.ledger_path, self._encoded_ledger(value))

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        """Durably persist a directory-entry change on the current platform."""

        if os.name == "nt":
            # ``os.open`` cannot open directories on Windows.  A directory handle
            # with BACKUP_SEMANTICS and write access can be flushed instead.
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_file = kernel32.CreateFileW
            create_file.argtypes = (
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            )
            create_file.restype = wintypes.HANDLE
            flush = kernel32.FlushFileBuffers
            flush.argtypes = (wintypes.HANDLE,)
            flush.restype = wintypes.BOOL
            close = kernel32.CloseHandle
            close.argtypes = (wintypes.HANDLE,)
            close.restype = wintypes.BOOL
            generic_write = 0x40000000
            share_all = 0x00000001 | 0x00000002 | 0x00000004
            open_existing = 3
            backup_semantics = 0x02000000
            handle = create_file(
                str(path),
                generic_write,
                share_all,
                None,
                open_existing,
                backup_semantics,
                None,
            )
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not flush(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                close(handle)
            return

        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _install_immutable_card(self, path: Path, value: bytes) -> None:
        """Publish fully written evidence once, or adopt identical evidence.

        The final card name is never opened for writing.  A private sibling is
        flushed first, then ``link`` atomically claims the final name without
        replacing an incumbent.  A crash can therefore leave only an unreferenced
        temporary file, never a partial final card.
        """

        lexical_root = self.authority_dir.absolute()
        lexical_path = path.absolute()
        try:
            relative = lexical_path.relative_to(lexical_root)
        except ValueError as error:
            raise AttendedHostError(
                "attended immutable path escapes runtime state"
            ) from error
        current = lexical_root
        if _is_link_like(current):
            raise AttendedHostError("attended immutable path uses a link")
        for part in relative.parts:
            current /= part
            if _is_link_like(current):
                raise AttendedHostError("attended immutable path uses a link")
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                # Hard-link creation is an atomic create-if-absent operation on
                # the same filesystem; unlike replace, it cannot destroy a card
                # published by a concurrent writer.
                os.link(temporary_path, path)
            except FileExistsError:
                if _is_link_like(path):
                    raise AttendedHostError("attended immutable card path uses a link")
                try:
                    existing = path.read_bytes()
                except OSError as error:
                    raise AttendedHostError(
                        f"attended immutable card cannot be inspected: {error}"
                    ) from error
                if existing != value:
                    raise AttendedHostError(
                        "attended immutable card conflicts with the launch identity"
                    )
            # Persist the final name before treating either publication or
            # byte-for-byte adoption as complete.
            self._fsync_directory(path.parent)
        except BaseException:
            # A leftover private temp file is harmless and carries no authority;
            # remove it when possible without ever touching the final evidence.
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        temporary_path.unlink(missing_ok=True)
        # Persist removal of the private sibling as well, so later recovery does
        # not need to distinguish a stale temp name from live card evidence.
        self._fsync_directory(path.parent)

    def migrate_legacy_ledger(
        self,
        *,
        actor: str,
        already_holds_runtime_lock: bool = False,
    ) -> Mapping[str, object]:
        """Archive exact legacy bytes, then normalize the registry exactly once.

        ``PREPARED`` is persisted before either the canonical cards or ledger are
        replaced.  A retry can therefore distinguish the untouched source from
        the expected normalized ledger.  Content-addressed archives are never
        overwritten; an unexpected existing byte sequence is a hard conflict.
        """

        if not isinstance(actor, str) or not actor.strip():
            raise AttendedHostError("attended ledger migration actor is required")
        if type(already_holds_runtime_lock) is not bool:
            raise AttendedHostError("attended migration lock mode must be boolean")
        attended_lock_path = self.coordination_dir / "locks" / "attended-host.lock"
        bootstrap_lock_path = self.coordination_dir / RUNTIME_BOOTSTRAP_LOCK
        if already_holds_runtime_lock:
            if not (
                runtime_file_lock_is_held(bootstrap_lock_path)
                and runtime_file_lock_is_held(attended_lock_path)
            ):
                raise AttendedHostError(
                    "attended migration requires the current thread to hold its bootstrap "
                    "and attended runtime locks"
                )
            lock_context = nullcontext()
        else:
            lock_context = self.plane.runtime_lock("attended-host.lock")
        migration_root = self.coordination_dir / "migrations" / "attended-host-v1"
        manifest_path = migration_root / "manifest.json"
        with lock_context:
            manifest: dict[str, Any] | None = None
            archived_source: Mapping[str, object] | None = None
            archived_cards: Mapping[str, bytes] | None = None
            if manifest_path.is_file():
                manifest = self._read_migration_manifest(manifest_path)
                _, archived_source, archived_cards = self._validate_migration_archives(
                    manifest
                )
            if not self.ledger_path.is_file():
                if manifest is None:
                    return {"outcome": "ABSENT", "entries": 0}
                if manifest["status"] == "COMPLETE":
                    # A completed registry may contain post-migration entries that
                    # are not in the baseline manifest.  Recreating only that
                    # baseline would silently discard them, so absence is a hard
                    # reconciliation failure.
                    raise AttendedHostError(
                        "completed attended ledger is missing; reconciliation is required"
                    )
                if archived_source is None or archived_cards is None:
                    raise AttendedHostError(
                        "attended prepared migration evidence is unavailable"
                    )
                self._restore_prepared_migration(
                    manifest,
                    archived_source,
                    archived_cards,
                )
                completed = self._completed_migration_manifest(manifest)
                self._write_migration_manifest(manifest_path, completed)
                return completed

            current_bytes, _ = self._raw_ledger_unlocked()
            current_digest = _bytes_digest(current_bytes)
            if manifest is not None:
                if manifest["status"] == "COMPLETE":
                    # The registry may legitimately have accumulated new modern
                    # entries since the baseline migration.  Validate all of it,
                    # but do not demand that it still equals the baseline digest.
                    ledger, _, _ = self._ledger_unlocked()
                    self._validate_migrated_entries(ledger, manifest)
                    return manifest
                if current_digest not in {
                    manifest["source_ledger_digest"],
                    manifest["normalized_ledger_digest"],
                }:
                    raise AttendedHostError(
                        "attended ledger conflicts with its prepared migration"
                    )
                if current_digest == manifest["source_ledger_digest"]:
                    if archived_source is None or archived_cards is None:
                        raise AttendedHostError(
                            "attended prepared migration evidence is unavailable"
                        )
                    self._restore_prepared_migration(
                        manifest,
                        archived_source,
                        archived_cards,
                    )
                else:
                    ledger, _, _ = self._ledger_unlocked()
                    self._validate_migrated_entries(ledger, manifest)
                completed = self._completed_migration_manifest(manifest)
                self._write_migration_manifest(manifest_path, completed)
                return completed

            ledger, _, source_cards = self._ledger_unlocked(allow_legacy=True)
            normalized_bytes = self._encoded_ledger(ledger)
            archive = migration_root / "ledgers" / f"{current_digest[7:]}.json"
            self._install_archive(archive, current_bytes, "attended ledger archive")
            card_archives: list[dict[str, object]] = []
            for instruction_id, entry in sorted(ledger.items()):
                card_bytes = source_cards[instruction_id]
                card_digest = _bytes_digest(card_bytes)
                card_archive = migration_root / "cards" / f"{card_digest[7:]}.md"
                self._install_archive(card_archive, card_bytes, "attended card archive")
                card_archives.append(
                    {
                        "launch_instruction_id": instruction_id,
                        "card_digest": card_digest,
                        "bytes": len(card_bytes),
                        "archive": card_archive.relative_to(
                            self.coordination_dir
                        ).as_posix(),
                        "normalized_card": entry["card"],
                        "normalized_entry_digest": _mapping_digest(entry),
                    }
                )
            manifest = {
                "schema_version": MIGRATION_SCHEMA_VERSION,
                "kind": MIGRATION_KIND,
                "status": "PREPARED",
                "actor": actor,
                "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "source_ledger_digest": current_digest,
                "source_ledger_bytes": len(current_bytes),
                "source_archive": archive.relative_to(self.coordination_dir).as_posix(),
                "normalized_ledger_digest": _bytes_digest(normalized_bytes),
                "entries": len(ledger),
                "cards": card_archives,
            }
            self._validate_migration_manifest_schema(manifest)
            self._write_migration_manifest(manifest_path, manifest)
            self._validate_migration_archives(manifest)
            self._install_migrated_cards(ledger, source_cards)
            self._atomic_write_bytes(self.ledger_path, normalized_bytes)
            installed, _, _ = self._ledger_unlocked()
            self._validate_migrated_entries(installed, manifest)
            completed = self._completed_migration_manifest(manifest)
            self._write_migration_manifest(manifest_path, completed)
            return completed

    @staticmethod
    def _encoded_ledger(ledger: Mapping[str, Any]) -> bytes:
        return _canonical_document(ledger)

    def _write_migration_manifest(
        self,
        path: Path,
        value: Mapping[str, object],
    ) -> None:
        manifest = self._validate_migration_manifest_schema(value)
        self._atomic_write_bytes(path, _canonical_document(manifest))

    def _completed_migration_manifest(
        self,
        prepared_value: Mapping[str, object],
    ) -> dict[str, Any]:
        prepared = self._validate_migration_manifest_schema(prepared_value)
        if prepared["status"] != "PREPARED":
            raise AttendedHostError(
                "attended migration can only complete a PREPARED manifest"
            )
        completed = {
            **prepared,
            "status": "COMPLETE",
            "prepared_manifest_digest": _bytes_digest(_canonical_document(prepared)),
        }
        return self._validate_migration_manifest_schema(completed)

    def _validate_migration_manifest_schema(
        self,
        raw_value: Mapping[str, object],
    ) -> dict[str, Any]:
        """Validate the self-attesting PREPARED -> COMPLETE migration record."""

        value = dict(raw_value)
        status = value.get("status")
        if status not in {"PREPARED", "COMPLETE"}:
            raise AttendedHostError("attended migration manifest state is invalid")
        expected_fields = (
            _MIGRATION_BASE_FIELDS
            if status == "PREPARED"
            else _MIGRATION_COMPLETE_FIELDS
        )
        unexpected = sorted(set(value) - expected_fields)
        missing = sorted(expected_fields - set(value))
        if unexpected or missing:
            detail = ", ".join(
                [
                    *(f"unexpected {field}" for field in unexpected),
                    *(f"missing {field}" for field in missing),
                ]
            )
            raise AttendedHostError(
                "attended migration manifest does not match its exact schema"
                + (f": {detail}" if detail else "")
            )
        if (
            type(value.get("schema_version")) is not int
            or value["schema_version"] != MIGRATION_SCHEMA_VERSION
            or value.get("kind") != MIGRATION_KIND
        ):
            raise AttendedHostError("attended migration manifest schema is invalid")
        actor = value.get("actor")
        recorded_at = value.get("recorded_at")
        if not isinstance(actor, str) or not actor.strip():
            raise AttendedHostError("attended migration actor is invalid")
        if not isinstance(recorded_at, str) or not recorded_at.endswith("Z"):
            raise AttendedHostError("attended migration timestamp is invalid")
        try:
            parsed_time = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise AttendedHostError(
                "attended migration timestamp is invalid"
            ) from error
        if parsed_time.tzinfo is None:
            raise AttendedHostError("attended migration timestamp is invalid")
        for field in ("source_ledger_digest", "normalized_ledger_digest"):
            self._require_digest(value.get(field), f"attended migration {field}")
        for field in ("source_ledger_bytes", "entries"):
            if type(value.get(field)) is not int or int(value[field]) < 0:
                raise AttendedHostError(f"attended migration {field} is invalid")
        source_archive = value.get("source_archive")
        if not isinstance(source_archive, str):
            raise AttendedHostError("attended migration source archive is invalid")
        expected_source_archive = (
            "migrations/attended-host-v1/ledgers/"
            f"{str(value['source_ledger_digest'])[7:]}.json"
        )
        if source_archive != expected_source_archive:
            raise AttendedHostError("attended migration source archive is noncanonical")
        cards = value.get("cards")
        if not isinstance(cards, list) or len(cards) != value["entries"]:
            raise AttendedHostError("attended migration card inventory is invalid")
        seen_instructions: set[str] = set()
        ordered_instructions: list[str] = []
        for raw_card in cards:
            if not isinstance(raw_card, Mapping):
                raise AttendedHostError("attended migration card record is invalid")
            card = dict(raw_card)
            if set(card) != _MIGRATION_CARD_FIELDS:
                raise AttendedHostError(
                    "attended migration card record does not match its exact schema"
                )
            instruction_id = self._require_digest(
                card.get("launch_instruction_id"),
                "attended migration card launch instruction identity",
            )
            if instruction_id in seen_instructions:
                raise AttendedHostError("attended migration card identity is invalid")
            seen_instructions.add(instruction_id)
            ordered_instructions.append(instruction_id)
            for field in ("card_digest", "normalized_entry_digest"):
                self._require_digest(card.get(field), f"attended migration {field}")
            if type(card.get("bytes")) is not int or int(card["bytes"]) < 0:
                raise AttendedHostError("attended migration card bytes are invalid")
            expected_archive = (
                f"migrations/attended-host-v1/cards/{str(card['card_digest'])[7:]}.md"
            )
            if card.get("archive") != expected_archive:
                raise AttendedHostError(
                    "attended migration card archive is noncanonical"
                )
            task_id = "attended-" + _digest(instruction_id)[:32]
            if card.get("normalized_card") != self._canonical_card_path(task_id):
                raise AttendedHostError(
                    "attended migration card target is noncanonical"
                )
        if ordered_instructions != sorted(ordered_instructions):
            raise AttendedHostError(
                "attended migration card inventory is not canonical"
            )
        if status == "COMPLETE":
            prepared_digest = self._require_digest(
                value.get("prepared_manifest_digest"),
                "attended migration prepared manifest digest",
            )
            prepared = dict(value)
            prepared.pop("prepared_manifest_digest")
            prepared["status"] = "PREPARED"
            if prepared_digest != _bytes_digest(_canonical_document(prepared)):
                raise AttendedHostError(
                    "attended migration manifest has an impossible completion transition"
                )
        return value

    def _install_archive(self, path: Path, value: bytes, label: str) -> None:
        if path.is_file():
            if _is_link_like(path):
                raise AttendedHostError(f"{label} path uses a link")
            try:
                existing = path.read_bytes()
            except OSError as error:
                raise AttendedHostError(
                    f"{label} cannot be inspected: {error}"
                ) from error
            if existing != value:
                raise AttendedHostError(f"{label} conflicts with its content digest")
            return
        # Archives are append-only evidence, so a race must never replace one.
        self._install_immutable_card(path, value)

    def _install_migrated_cards(
        self,
        ledger: Mapping[str, Mapping[str, Any]],
        source_cards: Mapping[str, bytes],
    ) -> None:
        for instruction_id, entry in sorted(ledger.items()):
            target = self.coordination_dir / str(entry["card"])
            self._install_immutable_card(target, source_cards[instruction_id])

    def _restore_prepared_migration(
        self,
        manifest: Mapping[str, Any],
        source_ledger: Mapping[str, object],
        archived_cards: Mapping[str, bytes],
    ) -> None:
        """Rebuild the exact prepared registry solely from immutable evidence."""

        validated_manifest = self._validate_migration_manifest_schema(manifest)
        if validated_manifest["status"] != "PREPARED":
            raise AttendedHostError(
                "attended migration cannot restore a terminal manifest"
            )
        records = validated_manifest.get("cards")
        if not isinstance(records, list):  # exact schema validation guards this
            raise AttendedHostError("attended migration card inventory is invalid")
        ledger: dict[str, Mapping[str, Any]] = {}
        for raw in records:
            if not isinstance(raw, Mapping):
                raise AttendedHostError("attended migration card record is invalid")
            instruction_id = self._require_digest(
                raw.get("launch_instruction_id"),
                "attended migration card launch instruction identity",
            )
            source_entry = source_ledger.get(instruction_id)
            card_bytes = archived_cards.get(instruction_id)
            if not isinstance(source_entry, Mapping) or card_bytes is None:
                raise AttendedHostError(
                    "attended prepared migration evidence is incomplete"
                )
            entry = dict(source_entry)
            entry.pop("authority_state", None)
            card_digest = _bytes_digest(card_bytes)
            stored_card_digest = entry.get("card_digest")
            if stored_card_digest is not None and stored_card_digest != card_digest:
                raise AttendedHostError(
                    "attended prepared card evidence conflicts with its source"
                )
            entry["card_digest"] = card_digest
            if "prompt_digest" not in entry:
                entry["prompt_digest"] = None
            task_id = "attended-" + _digest(instruction_id)[:32]
            expected_card = self._canonical_card_path(task_id)
            if raw.get("normalized_card") != expected_card:
                raise AttendedHostError(
                    "attended prepared migration card target is invalid"
                )
            entry["card_scope"] = "runtime_state"
            entry["card"] = expected_card
            self._validate_ledger_entry(
                instruction_id,
                entry,
                allow_legacy=False,
            )
            if _mapping_digest(entry) != raw.get("normalized_entry_digest"):
                raise AttendedHostError(
                    "attended prepared migration entry failed integrity"
                )
            ledger[instruction_id] = entry
        normalized_bytes = self._encoded_ledger(ledger)
        if _bytes_digest(normalized_bytes) != validated_manifest.get(
            "normalized_ledger_digest"
        ):
            raise AttendedHostError(
                "attended prepared migration ledger failed integrity"
            )
        self._install_migrated_cards(ledger, archived_cards)
        self._atomic_write_bytes(self.ledger_path, normalized_bytes)
        installed, _, _ = self._ledger_unlocked()
        self._validate_migrated_entries(installed, validated_manifest)

    def _read_migration_manifest(self, path: Path) -> dict[str, Any]:
        try:
            encoded = path.read_bytes()
        except OSError as error:
            raise AttendedHostError(
                f"attended migration manifest is unreadable: {error}"
            ) from error
        value = _strict_json_object(encoded, "attended migration manifest")
        return self._validate_migration_manifest_schema(value)

    def _manifest_archive(self, raw: object) -> Path:
        if not isinstance(raw, str) or not raw.strip():
            raise AttendedHostError("attended migration archive path is invalid")
        if "\\" in raw:
            raise AttendedHostError("attended migration archive path is noncanonical")
        relative = Path(raw)
        if (
            relative.is_absolute()
            or relative.as_posix() != raw
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise AttendedHostError("attended migration archive path is noncanonical")
        candidate = self.coordination_dir / relative
        root = (self.coordination_dir / "migrations" / "attended-host-v1").resolve()
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise AttendedHostError(
                "attended migration archive escapes migration state"
            )
        current = self.coordination_dir
        for part in relative.parts:
            current /= part
            if _is_link_like(current):
                raise AttendedHostError("attended migration archive path uses a link")
        return resolved

    def _validate_migration_archives(
        self,
        manifest: Mapping[str, Any],
    ) -> tuple[bytes, Mapping[str, object], Mapping[str, bytes]]:
        validated_manifest = self._validate_migration_manifest_schema(manifest)
        source = self._manifest_archive(validated_manifest.get("source_archive"))
        try:
            source_bytes = source.read_bytes()
        except OSError as error:
            raise AttendedHostError(
                f"attended source ledger archive is unavailable: {error}"
            ) from error
        if _bytes_digest(source_bytes) != validated_manifest.get(
            "source_ledger_digest"
        ) or len(source_bytes) != validated_manifest.get("source_ledger_bytes"):
            raise AttendedHostError("attended source ledger archive failed integrity")
        source_value = _strict_json_object(
            source_bytes, "attended source ledger archive"
        )
        source_ledger, _ = self._validate_ledger_document(
            source_value,
            allow_legacy=True,
        )
        cards = validated_manifest["cards"]
        if not isinstance(cards, list):  # exact schema validation guards this
            raise AttendedHostError("attended migration card inventory is invalid")
        seen_instructions: set[str] = set()
        archived_cards: dict[str, bytes] = {}
        for raw in cards:
            if not isinstance(raw, Mapping):
                raise AttendedHostError("attended migration card record is invalid")
            instruction_id = raw.get("launch_instruction_id")
            if (
                not isinstance(instruction_id, str)
                or instruction_id in seen_instructions
            ):
                raise AttendedHostError("attended migration card identity is invalid")
            seen_instructions.add(instruction_id)
            archive = self._manifest_archive(raw.get("archive"))
            try:
                card_bytes = archive.read_bytes()
            except OSError as error:
                raise AttendedHostError(
                    f"attended card archive is unavailable: {error}"
                ) from error
            if _bytes_digest(card_bytes) != raw.get("card_digest") or len(
                card_bytes
            ) != raw.get("bytes"):
                raise AttendedHostError("attended card archive failed integrity")
            archived_cards[instruction_id] = card_bytes
        if seen_instructions != set(source_ledger):
            raise AttendedHostError(
                "attended migration card inventory does not match source"
            )
        return source_bytes, source_ledger, archived_cards

    def _validate_migrated_entries(
        self,
        ledger: Mapping[str, Mapping[str, Any]],
        manifest: Mapping[str, Any],
    ) -> None:
        validated_manifest = self._validate_migration_manifest_schema(manifest)
        cards = validated_manifest.get("cards")
        if not isinstance(cards, list):  # exact schema validation guards this
            raise AttendedHostError("attended migration card inventory is invalid")
        for raw in cards:
            if not isinstance(raw, Mapping):
                raise AttendedHostError("attended migration card record is invalid")
            instruction_id = raw.get("launch_instruction_id")
            if not isinstance(instruction_id, str):
                raise AttendedHostError("attended migration card identity is invalid")
            entry = ledger.get(instruction_id)
            if (
                entry is None
                or _mapping_digest(entry) != raw.get("normalized_entry_digest")
                or entry.get("card") != raw.get("normalized_card")
            ):
                raise AttendedHostError(
                    "attended migrated registry entry failed baseline integrity"
                )

    def bind_tasks(self, tasks: Sequence[Mapping[str, object]]) -> None:
        """Record which node each launch instruction belongs to.

        ``create_thread`` receives only a title, a prompt, and an idempotency key,
        but every evidence probe is per node, so the contract's own mapping is
        captured before execution rather than parsed back out of a title.
        """

        if any(
            task.get("authority_class") == "PREPARATION_ONLY"
            or task.get("authority_mode") == "PREPARATION_ONLY"
            for task in tasks
        ):
            raise AttendedHostError(
                "attended host cannot bind an unobservable preparation-only lifecycle"
            )
        for task in tasks:
            instruction = task.get("launch_instruction_id")
            node_id = task.get("node_id")
            instruction_id = self._require_digest(
                instruction,
                "attended task launch instruction identity",
            )
            if not isinstance(node_id, str):
                raise AttendedHostError("attended task node identity is invalid")
            existing = self._nodes.get(instruction_id)
            if existing is not None and existing != node_id:
                raise AttendedHostError(
                    "attended task binding conflicts with its node identity"
                )
            self._nodes[instruction_id] = node_id

    def _active_binding(
        self,
        instruction_id: str,
        entry: Mapping[str, Any],
        *,
        require_bound: bool,
    ) -> Mapping[str, object] | None:
        self._require_current_authority_phase()
        binding = launch_binding(
            self.repo_root,
            instruction_id,
            state_dir=self.authority_dir,
        )
        if binding is None or binding.get("state") not in ACTIVE_BINDING_STATES:
            return None
        if require_bound and binding.get("state") in {"PREPARED", "CREATED"}:
            return None
        if binding.get("state") != "PREPARED":
            expected = {
                "host_id": entry.get("host_id"),
                "task_id": entry.get("task_id"),
                "cursor": entry.get("cursor"),
                "capability_digest": entry.get("capability_digest"),
            }
            if any(binding.get(field) != value for field, value in expected.items()):
                raise AttendedHostError(
                    "attended registry conflicts with the binding ledger"
                )
        return binding

    @contextmanager
    def _authority_guard(self, instruction_id: str):
        self._require_current_authority_phase()
        try:
            with launch_authority_guard(
                self.repo_root,
                instruction_id,
                state_dir=self.authority_dir,
            ) as binding:
                yield binding
        except OrchestrationError as error:
            raise AttendedHostError(
                "attended task authority is stale or revoked"
            ) from error

    def pending_cards(self) -> tuple[Mapping[str, Any], ...]:
        """Return the session cards the operator has not yet shown any evidence for.

        The ledger accumulates one entry per launch attempt, but the operator
        opens one session per node, so entries are deduplicated by node.  Every
        each attempt has an immutable card and superseded entries are hidden.
        """

        self._require_current_authority_phase()
        # A repository that has never created binding authority retains the old
        # display-only card list for upgrade compatibility.  As soon as a binding
        # ledger exists, only its active instructions are visible.  The legacy
        # fallback never grants relay or wait authority.
        legacy_display_only = not binding_events(
            self.repo_root,
            state_dir=self.authority_dir,
        )
        pending: dict[str, tuple[int, Mapping[str, Any]]] = {}
        for instruction_id, entry in self._ledger().items():
            binding = self._active_binding(
                instruction_id,
                entry,
                require_bound=False,
            )
            if binding is None and not legacy_display_only:
                continue
            if (
                binding is not None
                and binding.get("authority_class") == "PREPARATION_ONLY"
            ):
                continue
            node_id = entry.get("node_id")
            if not isinstance(node_id, str) or self._observe(node_id) is None:
                key = node_id if isinstance(node_id, str) else str(entry.get("task_id"))
                epoch = binding.get("authority_epoch") if binding is not None else 0
                rank = int(epoch) if type(epoch) is int else 0
                current = pending.get(key)
                if current is None or rank > current[0]:
                    pending[key] = (rank, entry)
        return tuple(value for _, value in pending.values())

    # ------------------------------------------------------------------ adapter

    def trusted_singleton_target(self, *, repo_root: Path) -> str:
        del repo_root
        return str(self.plane.target_branch)

    def host_lifecycle_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        """Truthfully declare that cards are not an autonomous host lifecycle."""

        del repo_root
        material: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-host-lifecycle-capability-v1",
            "host_id": HOST_ID,
            "create": False,
            "query": False,
            "resume": False,
            "interrupt": False,
            "archive": False,
            "autonomous_launch": False,
            "source": "attended-card-only",
        }
        return {**material, "record_id": _mapping_digest(material)}

    @contextmanager
    def dispatcher_effect_guard(
        self,
        *,
        node_id: str,
        release_id: str,
    ):
        """Fence every attended host effect to the exact shared release."""

        with self.plane.dispatcher_launch_authority_guard(
            node_id,
            release_id=release_id,
        ) as authority:
            yield authority

    def inspect_runtime_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        """Report live claim and lease authority from the control plane's state.

        The attended host has no runtime of its own to inspect; the control
        plane's repository-shared claim files and validation lease ARE the
        runtime authority a wave must not trample.
        """

        del repo_root
        claims = [dict(value) for value in self.plane.active_claims().values()]
        lease: dict[str, Any] | None = None
        lease_path = Path(self.plane.validation_lease_path)
        with self.plane.runtime_read_lock("global-validation-lease.lock"):
            if lease_path.is_file():
                value = read_json(lease_path)
                if not isinstance(value, Mapping):
                    raise AttendedHostError("global validation lease is malformed")
                lease = dict(value)
                if (
                    lease.get("schema_version") != SCHEMA_VERSION
                    or lease.get("status") != "ACTIVE"
                    or not isinstance(lease.get("node_id"), str)
                    or not str(lease["node_id"]).strip()
                    or not isinstance(lease.get("owner"), str)
                    or not str(lease["owner"]).strip()
                    or not isinstance(lease.get("lease_id"), str)
                    or AUTHORITY_ID.fullmatch(str(lease["lease_id"])) is None
                    or type(lease.get("renewal_count")) is not int
                    or int(lease["renewal_count"]) < 0
                ):
                    raise AttendedHostError("global validation lease is malformed")
                try:
                    acquired_at = parse_time(lease.get("acquired_at"))
                    expires_at = parse_time(lease.get("expires_at"))
                except (TypeError, ValueError) as error:
                    raise AttendedHostError(
                        "global validation lease timestamps are malformed"
                    ) from error
                if expires_at <= acquired_at:
                    raise AttendedHostError(
                        "global validation lease expiry is malformed"
                    )
        return {
            "target_branch": str(self.plane.target_branch),
            "active_claims": claims,
            "active_validation_lease": lease,
            "quiescent": not claims and lease is None,
        }

    def lookup_thread(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        self._require_current_authority_phase()
        self._require_digest(idempotency_key, "attended launch instruction identity")
        entry = self._ledger().get(idempotency_key)
        if not isinstance(entry, Mapping):
            return None
        if (
            self._active_binding(
                idempotency_key,
                entry,
                require_bound=False,
            )
            is None
        ):
            return None
        return {
            "kind": CREATE_KIND,
            "host_id": entry.get("host_id"),
            "task_id": entry.get("task_id"),
            "cursor": entry.get("cursor"),
            "capability": entry.get("capability"),
            "idempotency_key": idempotency_key,
        }

    def create_thread(
        self, *, title: str, prompt: str, idempotency_key: str
    ) -> Mapping[str, object]:
        self._require_current_authority_phase()
        if (
            not isinstance(title, str)
            or not title.strip()
            or not isinstance(prompt, str)
            or not prompt.strip()
        ):
            raise AttendedHostError(
                "an attended session card requires a title and prompt"
            )
        self._require_digest(idempotency_key, "attended launch instruction identity")
        task_id = "attended-" + _digest(idempotency_key)[:32]
        node_id = self._nodes.get(idempotency_key, "")
        card_text = (
            f"# {title}\n\n"
            f"Open one Codex session named exactly `{title}` and paste everything\n"
            f"below the rule. Do not add instructions of your own.\n\n---\n\n{prompt}\n"
        )
        card_bytes = card_text.encode("utf-8")
        prompt_digest = "sha256:" + _digest(prompt)
        known_binding = launch_binding(
            self.repo_root,
            idempotency_key,
            state_dir=self.authority_dir,
        )
        if (
            known_binding is not None
            and known_binding.get("authority_class") == "PREPARATION_ONLY"
        ):
            raise AttendedHostError(
                "attended host cannot issue an unobservable preparation-only lifecycle"
            )
        authority = (
            self._authority_guard(idempotency_key)
            if known_binding is not None
            else nullcontext(None)
        )
        with authority:
            with self.plane.runtime_lock("attended-host.lock"):
                ledger, _, _ = self._ledger_unlocked()
                existing = ledger.get(idempotency_key)
                if isinstance(existing, Mapping):
                    if (
                        existing.get("task_id") != task_id
                        or existing.get("node_id") != node_id
                        or existing.get("title") != title
                        or existing.get("prompt_digest") != prompt_digest
                        or existing.get("card_digest") != _bytes_digest(card_bytes)
                    ):
                        raise AttendedHostError(
                            "attended ledger conflicts with the launch identity"
                        )
                else:
                    card_path = self.cards_dir / f"{task_id}.md"
                    self._install_immutable_card(card_path, card_bytes)
                    ledger[idempotency_key] = {
                        "host_id": HOST_ID,
                        "task_id": task_id,
                        "cursor": CURSOR,
                        "capability": CAPABILITY,
                        "capability_digest": "sha256:" + _digest(CAPABILITY),
                        "node_id": node_id,
                        "title": title,
                        "card_scope": "runtime_state",
                        "card": self._canonical_card_path(task_id),
                        "card_digest": _bytes_digest(card_bytes),
                        "prompt_digest": prompt_digest,
                    }
                    self._write_ledger_unlocked(ledger)
        return {
            "kind": CREATE_KIND,
            "host_id": HOST_ID,
            "task_id": task_id,
            "cursor": CURSOR,
            "capability": CAPABILITY,
            "idempotency_key": idempotency_key,
        }

    def wait_threads(
        self, targets: Sequence[Mapping[str, object]]
    ) -> Sequence[Mapping[str, object]]:
        """Poll repository evidence under a deadline; never wait on the host."""

        deadline = self.clock() + self.wait_seconds
        while True:
            by_task = {
                str(entry.get("task_id")): (instruction_id, entry)
                for instruction_id, entry in self._ledger().items()
                if isinstance(entry, Mapping)
            }
            events: list[Mapping[str, object]] = []
            for target in targets:
                task_id = str(target.get("task_id"))
                identified = by_task.get(task_id)
                if identified is None:
                    raise AttendedHostError(f"unknown attended task {task_id!r}")
                instruction_id, entry = identified
                if (
                    self._active_binding(
                        instruction_id,
                        entry,
                        require_bound=True,
                    )
                    is None
                ):
                    raise AttendedHostError(
                        "attended task authority is stale or revoked"
                    )
                expected_target = {
                    "host_id": entry.get("host_id"),
                    "task_id": entry.get("task_id"),
                    "cursor": entry.get("cursor"),
                    "capability": entry.get("capability"),
                }
                if any(
                    target.get(field) != value
                    for field, value in expected_target.items()
                ):
                    raise AttendedHostError(
                        "attended wait target conflicts with its registry"
                    )
                node_id = str(entry.get("node_id") or "")
                observed = self._observe(node_id) if node_id else None
                if observed is None:
                    continue
                state, cursor = observed
                if cursor == target.get("after_event_cursor"):
                    continue
                events.append(
                    {
                        "kind": EVENT_KIND,
                        "host_id": HOST_ID,
                        "task_id": task_id,
                        "cursor": CURSOR,
                        "capability": CAPABILITY,
                        "state": state,
                        "event_id": f"{task_id}:{cursor}",
                        "event_cursor": cursor,
                    }
                )
            if events or self.clock() >= deadline:
                return tuple(events)
            self.sleep(self.poll_seconds)

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
        """Record a relay instruction; the operator is the only delivery channel."""

        if host_id != HOST_ID:
            raise AttendedHostError("attended host cannot message another host")
        if (
            not isinstance(message, str)
            or not message.strip()
            or not isinstance(idempotency_key, str)
            or not idempotency_key.strip()
        ):
            raise AttendedHostError(
                "attended relay message and idempotency key are required"
            )
        ledger = self._ledger()
        identified = next(
            (
                (instruction_id, item)
                for instruction_id, item in ledger.items()
                if isinstance(item, Mapping) and item.get("task_id") == task_id
            ),
            None,
        )
        if identified is None:
            raise AttendedHostError(f"unknown attended task {task_id!r}")
        instruction_id, entry = identified
        expected_identity = {
            "host_id": entry.get("host_id"),
            "task_id": entry.get("task_id"),
            "cursor": entry.get("cursor"),
            "capability": entry.get("capability"),
        }
        presented_identity = {
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
            "capability": capability,
        }
        if presented_identity != expected_identity:
            raise AttendedHostError(
                "attended relay identity conflicts with its registry"
            )
        relay_text = (
            f"# Relay to {entry.get('title')}\n\n"
            f"Paste this into that session, then leave it running.\n\n---\n\n{message}\n"
        )
        relay_record = self.cards_dir / (
            f"{task_id}.relay.{_digest(idempotency_key)[:24]}.md"
        )
        with self._authority_guard(instruction_id) as binding:
            if binding.get("state") in {"PREPARED", "CREATED"}:
                raise AttendedHostError(
                    "attended task authority is not capability-bound"
                )
            bound_identity = {
                "host_id": binding.get("host_id"),
                "task_id": binding.get("task_id"),
                "cursor": binding.get("cursor"),
                "capability_digest": binding.get("capability_digest"),
            }
            expected_bound_identity = {
                "host_id": entry.get("host_id"),
                "task_id": entry.get("task_id"),
                "cursor": entry.get("cursor"),
                "capability_digest": entry.get("capability_digest"),
            }
            if bound_identity != expected_bound_identity:
                raise AttendedHostError(
                    "attended registry conflicts with the binding ledger"
                )
            self._install_immutable_card(relay_record, relay_text.encode("utf-8"))
            relay = self.cards_dir / f"{task_id}.relay.md"
            self._atomic_write(relay, relay_text)
        return {
            "kind": ACK_KIND,
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
            "capability": capability,
            "accepted": True,
            "message_id": "relay-" + _digest(idempotency_key)[:24],
            "idempotency_key": idempotency_key,
        }

    # ----------------------------------------------------------------- evidence

    def _observe(self, node_id: str) -> tuple[str, str] | None:
        """Classify a node from durable evidence alone, or return None if silent."""

        failure = self._recorded_failure(node_id)
        if failure is not None:
            return ("FAILED", failure)
        try:
            branch = str(self.plane.node(node_id).get("branch"))
        except Exception as error:  # unknown node is a contract fault, not a wait
            raise AttendedHostError(f"cannot observe node {node_id!r}") from error
        head = self.plane.remote_branch_sha(branch)
        if head is None:
            return None
        self.plane._git(("fetch", "origin", f"refs/heads/{branch}"), check=False)
        author = self.plane._git(
            ("show", "-s", "--format=%ae", head), check=False
        ).stdout.strip()
        if author == RECEIPT_IDENTITY:
            return ("SUCCEEDED", head)
        return ("ACTIVE", head)

    def _recorded_failure(self, node_id: str) -> str | None:
        path = Path(self.plane.blockers_dir) / f"{node_id}.jsonl"
        if not path.is_file():
            return None
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not lines:
            return None
        if getattr(self.plane, "blockers_fully_resolved", lambda _node: False)(node_id):
            # Every recorded cause carries a verified resolution; the ledger is
            # a history of healed failures, not live failure evidence.
            return None
        return "blocker:" + _digest(lines[-1])[:32]


class EvidenceResolver:
    """Answer an attention event with a bounded instruction, never a judgement call.

    The resolver deliberately does not attempt to solve a worker's problem. It
    restates the one thing that makes a session terminal, so a stalled worker
    either produces evidence or records a blocker instead of idling.
    """

    def resolve_attention(
        self, task: Mapping[str, object], event: Mapping[str, object]
    ) -> str:
        node_id = str(task.get("node_id") or "this node")
        attention = str(event.get("attention") or "").strip()
        return (
            f"Continue {node_id}. Report WHAT I DID / NEXT STEPS / BLOCKS. "
            "You are terminal only at a pushed durable receipt commit or an "
            "`autopilot fail` blocker record; chat prose is never completion. "
            "Never wait on a sibling node — record a blocker instead."
            + (f" Attention reported: {attention}" if attention else "")
        )
