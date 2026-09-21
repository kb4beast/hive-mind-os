"""Offline OCI Python verification for trusted, single-tenant local targets.

An image-pinned adapter seals fixed Linux ``python -m unittest`` argv; a Docker
sandbox at the ``SandboxAdapter`` seam runs only those argv inside a container
with no network, a read-only root and workspace, a private tmpfs, dropped
capabilities and bounded CPU, memory, pids, disk, wall time and output.

This is *not* hostile-code isolation.  The Docker engine and its VM are shared by
the operator, so ``hostile_code_isolation`` stays ``False`` and the default
``verify_repository`` requirement still blocks.  Every allocation is journaled
append-only before and after each effect so an interrupted run can be reconciled
without ever repeating execution (see ADR-089).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .path_boundary import is_within
from .runtime_contracts import canonical_json_bytes, raw_sha256
from .verification_adapters import (
    SandboxCapabilities,
    SandboxUnavailable,
    SealedCommand,
    VerificationBudget,
    VerificationError,
    _safe_test_paths,
)

PYTHON_BINARY = "/usr/local/bin/python"
WORKSPACE_MOUNT = "/workspace"
CONTAINER_USER = "65534:65534"
# The only variables passed with --env.  The pinned image's own baked variables are
# read from the image and merged with these deterministically (these win); the
# resulting container environment must equal that merge exactly, never a superset.
CONTAINER_ENVIRONMENT = (("PYTHONPATH", "src"), ("PYTHONDONTWRITEBYTECODE", "1"), ("TMPDIR", "/tmp"))
LABEL_KEY = "io.hive-mind-os.verification-allocation"
NAME_PREFIX = "hive-verify-"
MAX_TEST_PATHS = 256

_IMAGE = re.compile(
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*@sha256:[0-9a-f]{64}", re.ASCII)
_TEST_PATH = re.compile(r"(?:[A-Za-z_][A-Za-z0-9_]*/)*test_[A-Za-z0-9_]*\.py", re.ASCII)
_ALLOCATION_ID = re.compile(r"[0-9a-f]{32}", re.ASCII)
_CONTAINER_ID = re.compile(r"[0-9a-f]{64}", re.ASCII)
_JOURNAL_NAME = re.compile(r"sandbox-(?:version|tests)\.journal\.jsonl")
_DRIVE_PATH = re.compile(r"([A-Za-z]):[\\/](.+)", re.DOTALL)
# Local daemon endpoints only: no tcp/ssh (certificates, credentials, remote hosts).
_DOCKER_HOST = re.compile(r"npipe:////\./pipe/[A-Za-z0-9_.-]+|unix:///[A-Za-z0-9_./-]+", re.ASCII)
# Host variables the docker client may see.  No DOCKER_* selector or config variable
# and no proxy variable is ever forwarded; the daemon is selected explicitly instead.
_CLIENT_ENVIRONMENT = ("SystemRoot", "USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA")
# Contents of the owned, empty Docker client configuration directory.  A user's
# config.json (proxies, credential helpers, contexts) is never read or copied.
_INERT_CONFIG = b"{}\n"
_CONFIG_DIGEST = raw_sha256(_INERT_CONFIG)
_CONFIG_DIRECTORY = "docker-config"
_CONTROL_TIMEOUT = 60.0
_CONTROL_LIMIT = 262_144
_CLEANUP_ALLOWANCE = 20.0   # one shared budget for stop/inspect/remove after the execution deadline
_RECOVERY_ALLOWANCE = 60.0  # one shared budget per recover() call
_READER_JOIN_SECONDS = 5.0
_STOP_POLLS = 50


class SandboxOwnershipError(SandboxUnavailable):
    """A container did not carry this allocation's name, label and identity; it was not touched."""


class SandboxCleanupError(SandboxUnavailable):
    """The owned allocation could not be verified removed (or its creation is unresolved)."""


def validate_image_reference(value: object) -> str:
    """Accept only an exact ``name@sha256:<64 hex>`` reference, never a mutable tag."""

    if not isinstance(value, str) or _IMAGE.fullmatch(value) is None:
        raise VerificationError("container image must be an exact name@sha256:<64 hex> reference")
    return value


def expected_mount_source(workspace: str, *, windows: bool | None = None) -> str:
    """Return the Linux-side spelling of a workspace bind.

    Linux engines report the host path unchanged. Docker Desktop on Windows can
    report the exact supplied drive path or its Linux-side spelling, such as
    ``C:\\Users\\a`` to ``/run/desktop/mnt/host/c/Users/a``. UNC and ``\\\\?\\``
    paths have no such translation and are refused. Callers check only these
    two exact spellings, never suffixes or arbitrary aliases.
    """

    if not (os.name == "nt" if windows is None else windows):
        return workspace
    match = _DRIVE_PATH.fullmatch(workspace)
    if match is None:
        raise VerificationError("workspace path has no Docker Desktop drive translation")
    return f"/run/desktop/mnt/host/{match[1].lower()}/{match[2].replace(chr(92), '/')}"


class ImagePythonUnittestAdapter:
    """Seal Linux ``python -m unittest`` inside one pinned image.

    The image comes from the trusted constructor, never from target content.  The
    workspace is read-only, so tests that write relative to it fail truthfully.
    """

    adapter_id = "python-unittest-oci"

    def __init__(self, image: str) -> None:
        self.image = validate_image_reference(image)
        self.adapter_version = f"1|{self.image}"

    def seal(self, repository: Path, selected_paths: Sequence[str]) -> SealedCommand | None:
        values = tuple(selected_paths) or tuple(
            path.relative_to(repository).as_posix()
            for path in sorted(repository.rglob("test_*.py"))
            if path.is_file() and ".git" not in path.parts
        )
        selected = tuple(
            path for path in _safe_test_paths(repository, values, {".py"}) if Path(path).name.startswith("test_")
        )
        importable = tuple(path for path in selected if _TEST_PATH.fullmatch(path))
        if selected_paths and importable != selected:
            raise VerificationError("selected test path is not an importable relative unittest module")
        if not importable:
            return None
        if len(importable) > MAX_TEST_PATHS:
            raise VerificationError("too many selected test paths")
        return SealedCommand(
            self.adapter_id, (PYTHON_BINARY, "-B", "-m", "unittest", *importable, "-v"),
            (PYTHON_BINARY, "--version"), importable, CONTAINER_ENVIRONMENT, image_identity=self.image,
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    timed_out: bool = False
    truncated: bool = False


def _positive_finite(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value > 0)


class _BoundedSink:
    """Keep at most ``limit`` bytes, in memory or appended to an existing file."""

    def __init__(self, limit: int, path: Path | None) -> None:
        self.limit, self.size, self.data = limit, 0, bytearray()
        self.error: OSError | None = None
        self._handle = path.open("ab") if path is not None else None

    def pump(self, stream: Any, exceeded: threading.Event) -> None:
        try:
            while chunk := stream.read1(65536):
                keep = chunk[: max(0, self.limit - self.size)]
                if keep:
                    self.size += len(keep)
                    if self._handle is not None:
                        self._handle.write(keep)
                    else:
                        self.data.extend(keep)
                if len(keep) < len(chunk):
                    exceeded.set()
        except OSError as error:
            self.error = error
            exceeded.set()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()


def _close_quietly(stream: Any) -> None:
    close = getattr(stream, "close", None)
    if callable(close):
        try:
            close()
        except (OSError, ValueError):
            pass


def run_bounded(
    argv: Sequence[str], *, environment: Mapping[str, str], timeout: float, limit: int,
    stdout_path: Path | None = None, stderr_path: Path | None = None,
) -> CommandResult:
    """Run one host command with list argv, an explicit environment and bounded streaming.

    One monotonic deadline covers the process *and* its readers: closing the pipes does
    not end the wait while the process lives.  Output beyond ``limit`` bytes per stream
    is dropped as it arrives and the client process is killed and reaped.  Host pipe
    handles are closed only after their reader thread has finished; a reader still
    blocked (a descendant inherited the pipe) is left to its daemon thread rather than
    closed under it, so a stuck handle can never deadlock the caller.
    """

    if not _positive_finite(timeout) or not _positive_finite(limit):
        raise VerificationError("bounded runner requires a positive finite timeout and limit")
    options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    )
    sinks = (_BoundedSink(int(limit), stdout_path), _BoundedSink(int(limit), stderr_path))
    exceeded, timed_out = threading.Event(), False
    threads: list[threading.Thread] = []
    streams: tuple[Any, Any] = (None, None)
    try:
        process = subprocess.Popen(
            list(argv), env=dict(environment), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False, **options,
        )
        streams = (process.stdout, process.stderr)
        threads = [
            threading.Thread(target=sink.pump, args=(stream, exceeded), daemon=True)
            for sink, stream in zip(sinks, streams)
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + timeout
        try:
            while True:
                if exceeded.is_set():
                    break
                if process.poll() is not None and not any(thread.is_alive() for thread in threads):
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                exceeded.wait(0.05)
            if exceeded.is_set() or timed_out:
                process.kill()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired as error:
                    raise VerificationError("host client process could not be reaped") from error
        except BaseException:
            process.kill()
            raise
        finally:
            for thread in threads:
                thread.join(_READER_JOIN_SECONDS)
    finally:
        for index, stream in enumerate(streams):
            reader = threads[index] if index < len(threads) else None
            if stream is not None and (reader is None or not reader.is_alive()):
                _close_quietly(stream)
        for sink in sinks:
            sink.close()
    error = next((sink.error for sink in sinks if sink.error is not None), None)
    if error is not None:
        raise VerificationError("host log write failed") from error
    return CommandResult(
        process.returncode, bytes(sinks[0].data), bytes(sinks[1].data), sinks[0].size, sinks[1].size,
        timed_out, exceeded.is_set(),
    )


class _Deadline:
    """One monotonic budget shared by every call made under it."""

    def __init__(self, clock: Callable[[], float], seconds: float) -> None:
        self._clock, self.seconds = clock, float(seconds)
        self._start = clock()
        self._end = self._start + self.seconds

    def remaining(self) -> float:
        return self._end - self._clock()

    def elapsed(self) -> float:
        return self._clock() - self._start

    def bound(self, ceiling: float) -> float:
        left = self.remaining()
        if not left > 0:  # also true for NaN
            raise SandboxUnavailable("sandbox deadline expired")
        return min(float(ceiling), left)


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace").strip()[:2000]


def _alias(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(os.lstat(path), "st_file_attributes", 0) & 0x400)
    except OSError:
        return True


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def _never_started(state: Mapping[str, Any]) -> bool:
    return str(state.get("StartedAt") or "0001-01-01").startswith("0001-01-01")


def _container_not_found(result: CommandResult, reference: str) -> bool:
    """True only for Docker's exact, identifier-bound "no such container" diagnostic.

    Anything else (socket or pipe missing, proxy errors, daemon errors, extra lines, a
    different identifier) is a transport or daemon problem, never proof of absence.
    """

    lines = [line.strip() for line in result.stderr.decode("utf-8", "replace").splitlines() if line.strip()]
    return (
        result.returncode == 1 and not result.timed_out and not result.truncated
        and result.stdout.strip() in (b"", b"[]") and len(lines) == 1
        and lines[0] in {
            f"Error: No such container: {reference}", f"Error: No such object: {reference}",
            f"Error response from daemon: No such container: {reference}",
        }
    )


def _environment_mapping(items: object) -> dict[str, str] | None:
    """Parse ``KEY=value`` entries; None for malformed entries or duplicate keys."""

    if items is None:
        return {}
    if not isinstance(items, list):
        return None
    mapping: dict[str, str] = {}
    for item in items:
        if not isinstance(item, str):
            return None
        key, separator, value = item.partition("=")
        if not key or not separator or key in mapping:
            return None
        mapping[key] = value
    return mapping


def _state_summary(info: Mapping[str, Any]) -> dict[str, Any]:
    state = _mapping(info.get("State"))
    return {
        "status": state.get("Status"), "running": state.get("Running"), "exit_code": state.get("ExitCode"),
        "oom_killed": state.get("OOMKilled"), "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"), "error": str(state.get("Error") or "")[:300],
    }


def _summary(info: Mapping[str, Any]) -> dict[str, Any]:
    """Applied configuration facts retained in journals and receipts."""

    host, config = _mapping(info.get("HostConfig")), _mapping(info.get("Config"))
    return {
        "id": info.get("Id"), "name": info.get("Name"), "image": config.get("Image"), "image_id": info.get("Image"),
        "allocation_label": _mapping(config.get("Labels")).get(LABEL_KEY), "user": config.get("User"),
        "entrypoint": config.get("Entrypoint"), "cmd": config.get("Cmd"), "working_dir": config.get("WorkingDir"),
        "environment_names": sorted(str(item).partition("=")[0] for item in config.get("Env") or []),
        "open_stdin": config.get("OpenStdin"), "tty": config.get("Tty"),
        "network_mode": host.get("NetworkMode"), "read_only_rootfs": host.get("ReadonlyRootfs"),
        "cap_drop": host.get("CapDrop"), "cap_add": host.get("CapAdd"), "security_opt": host.get("SecurityOpt"),
        "privileged": host.get("Privileged"), "memory": host.get("Memory"), "memory_swap": host.get("MemorySwap"),
        "pids_limit": host.get("PidsLimit"), "nano_cpus": host.get("NanoCpus"), "ulimits": host.get("Ulimits"),
        "log_driver": _mapping(host.get("LogConfig")).get("Type"), "tmpfs": host.get("Tmpfs"),
        "binds": host.get("Binds"), "devices": host.get("Devices"), "volumes_from": host.get("VolumesFrom"),
        "ipc_mode": host.get("IpcMode"), "pid_mode": host.get("PidMode"),
        "mounts": [
            {"type": _mapping(m).get("Type"), "source": _mapping(m).get("Source"),
             "destination": _mapping(m).get("Destination"), "rw": _mapping(m).get("RW")}
            for m in info.get("Mounts") or []
        ],
        "host_config_mounts": [
            {"type": _mapping(m).get("Type"), "source": _mapping(m).get("Source"),
             "target": _mapping(m).get("Target"), "read_only": _mapping(m).get("ReadOnly")}
            for m in host.get("Mounts") or []
        ],
        "state": _state_summary(info),
    }


def _limits(budget: VerificationBudget) -> tuple[int, int, int]:
    """Return memory bytes, cpu seconds and tmpfs bytes derived from a budget."""

    memory = int(budget.memory_bytes)
    return memory, max(1, int(budget.cpu_seconds)), min(int(budget.disk_bytes), memory)


def _ulimits_ok(value: object, cpu: int) -> bool:
    return isinstance(value, list) and [
        (_mapping(item).get("Name"), _mapping(item).get("Soft"), _mapping(item).get("Hard")) for item in value
    ] == [("cpu", cpu, cpu)]


def _tmpfs_ok(value: object, size: int) -> bool:
    if not isinstance(value, dict) or set(value) != {"/tmp"}:
        return False
    options = str(value["/tmp"]).split(",")
    return len(options) == len(set(options)) and set(options) == {
        "rw", "noexec", "nosuid", "nodev", "mode=1777", f"size={size}",
    }


def _creation_unresolved(history: Sequence[Mapping[str, Any]]) -> bool:
    """True unless a create outcome or its reaping is durably recorded.

    Only a returned container ID, a create that was provably never attempted, or a
    recorded removal of an *owned* container resolves it.  Any failed attempted create
    (whatever its exit code or wording), an intent with no create result, and absence
    of a container all stay unresolved: nothing the client prints proves that the
    daemon did not receive the request.
    """

    for record in history:
        if record.get("phase") == "create_resolved":
            return False
        if record.get("phase") == "create_result" and record.get("outcome") in {"created", "not_attempted"}:
            return False
    return True


@dataclass(slots=True)
class _Allocation:
    name: str
    token: str
    phase: str
    container_id: str | None = None
    create_unresolved: bool = False


class _Journal:
    """Append-only hash-chained JSON lines; records are never rewritten."""

    def __init__(self, path: Path, records: list[dict[str, Any]]) -> None:
        self.path, self.records = path, records

    @classmethod
    def create(cls, path: Path) -> "_Journal":
        try:
            path.open("xb").close()
        except FileExistsError as error:
            raise VerificationError("sandbox journal already exists; overwrite refused") from error
        return cls(path, [])

    @staticmethod
    def verified_prefix(raw: bytes) -> tuple[list[dict[str, Any]], bytes]:
        """Return the verified records and any untrusted tail (empty when intact).

        Only the final line may be damaged (a torn write); damage earlier in the file
        is a broken chain and is refused.  Nothing here modifies or discards bytes.
        """

        lines = raw.split(b"\n")
        unterminated = lines.pop()  # b"" when the file ends with a newline
        records: list[dict[str, Any]] = []
        previous: str | None = None
        for index, line in enumerate(lines):
            try:
                record = json.loads(line)
                claimed = record.pop("digest", None)
                intact = (record.get("prev") == previous and record.get("seq") == len(records)
                          and raw_sha256(canonical_json_bytes(record)) == claimed)
            except (ValueError, AttributeError, TypeError):
                intact = False
            if not intact:
                if index == len(lines) - 1 and not unterminated:
                    return records, line + b"\n"
                raise VerificationError("sandbox journal chain is broken before its final record")
            record["digest"] = previous = claimed
            records.append(record)
        return records, unterminated

    @property
    def digest(self) -> str | None:
        return self.records[-1]["digest"] if self.records else None

    def append(self, phase: str, **facts: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "seq": len(self.records), "prev": self.digest, "phase": phase,
            "at": datetime.now(timezone.utc).isoformat(), **facts,
        }
        record["digest"] = raw_sha256(canonical_json_bytes(record))
        with self.path.open("ab") as handle:
            handle.write(canonical_json_bytes(record) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.records.append(record)
        return record


@dataclass(slots=True)
class _Execution:
    alloc: _Allocation
    argv: tuple[str, ...]
    create_argv: tuple[str, ...]
    workspace: Path
    stdout_path: Path
    stderr_path: Path
    receipt_path: Path
    budget: VerificationBudget
    journal: _Journal
    deadline: _Deadline
    cleanup: _Deadline | None = None
    applied: dict[str, Any] | None = None
    expected_environment: dict[str, str] | None = None
    environment_report: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)


Runner = Callable[..., CommandResult]


class DockerPythonSandbox:
    """Run approved Python argv in a pinned, offline, read-only container.

    Not thread-safe.  ``hostile_code_isolation`` is deliberately ``False``.

    Every docker invocation carries ``--config <owned empty directory>`` so the
    operator's Docker configuration (proxies, credential helpers, contexts) is never
    inherited.  Because contexts live in that configuration, the daemon is selected
    explicitly with ``docker_host`` (``npipe:////./pipe/...`` or ``unix:///...``);
    omitting it uses the docker client's built-in default endpoint.
    """

    def __init__(
        self, image: str, *, evidence_root: str | Path, docker_executable: str | Path | None = None,
        docker_host: str | None = None, client_environment: Mapping[str, str] | None = None,
        cpus: float = 1.0, pids_limit: int = 128, runner: Runner = run_bounded,
        allocation_id_factory: Callable[[], str] | None = None,
        sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.image = validate_image_reference(image)
        root = Path(evidence_root)
        if not root.is_absolute():
            raise VerificationError("sandbox evidence root must be absolute")
        self._evidence_root = root.resolve()
        if not 0 < cpus <= 16 or not 1 <= pids_limit <= 4096:
            raise VerificationError("sandbox cpu or pid limit is out of range")
        self._cpus, self._pids = float(cpus), int(pids_limit)
        if docker_host is not None and (not isinstance(docker_host, str) or _DOCKER_HOST.fullmatch(docker_host) is None):
            raise VerificationError("docker host must be a local npipe:// or unix:// endpoint")
        self._host = docker_host
        located: str | None
        if docker_executable is None:
            located = shutil.which("docker")
        else:
            located = os.fspath(docker_executable)
            if not Path(located).is_absolute():
                raise VerificationError("docker executable must be an absolute path")
        docker = Path(os.path.abspath(located)) if located else None
        if docker is not None and not docker.is_file():
            if docker_executable is not None:
                raise VerificationError("docker executable does not exist")
            docker = None
        # Resolved and hashed once here; the digest is re-checked before every invocation.
        self._docker = str(docker) if docker is not None else None
        self._docker_digest = _file_digest(docker) if docker is not None else None
        if client_environment is None:
            client_environment = {name: os.environ[name] for name in _CLIENT_ENVIRONMENT if name in os.environ}
        if set(client_environment) - set(_CLIENT_ENVIRONMENT):
            raise VerificationError("docker client environment may contain only allowlisted client variables")
        self._client_environment = {str(k): str(v) for k, v in client_environment.items()}
        self._runner, self._sleep, self._clock = runner, sleep, clock
        self._allocation_id = allocation_id_factory or (lambda: uuid.uuid4().hex)
        self._config_dir: Path | None = None
        self._last: dict[str, Any] | None = None

    @property
    def capabilities(self) -> SandboxCapabilities:
        ready = self._docker is not None
        return SandboxCapabilities(
            "oci-python-docker", "1", ready, False, ready, ready, ready, ready,
            f"docker-cli:{self._docker}|{self._docker_digest}" if ready else "unavailable", self.image,
        )

    def last_execution_receipt(self) -> dict[str, Any] | None:
        return dict(self._last) if self._last is not None else None

    # -- approval and path boundaries ------------------------------------------------

    @staticmethod
    def _approve(argv: tuple[str, ...]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
        if argv == (PYTHON_BINARY, "--version"):
            return "version", argv[1:], ()
        tests = argv[4:-1]
        if (len(argv) >= 6 and argv[:4] == (PYTHON_BINARY, "-B", "-m", "unittest") and argv[-1] == "-v"
                and len(tests) <= MAX_TEST_PATHS and all(_TEST_PATH.fullmatch(t) for t in tests)):
            return "tests", argv[1:], tuple(tests)
        raise VerificationError("sandbox accepts only the sealed Linux python version and unittest argv")

    def _validate_paths(
        self, workspace: Path, stdout_path: Path, stderr_path: Path, tests: tuple[str, ...],
    ) -> tuple[Path, Path, Path, Path]:
        workspace, stdout_path, stderr_path = Path(workspace), Path(stdout_path), Path(stderr_path)
        if not all(path.is_absolute() for path in (workspace, stdout_path, stderr_path)):
            raise VerificationError("sandbox paths must be absolute")
        evidence = stdout_path.parent.resolve()
        if (not is_within(evidence, self._evidence_root) or not evidence.is_dir() or _alias(stdout_path.parent)
                or stderr_path.parent.resolve() != evidence or stdout_path.name == stderr_path.name):
            raise VerificationError("sandbox outputs must share one evidence directory under the evidence root")
        if workspace.name != "workspace" or workspace.parent.resolve() != evidence or _alias(workspace) \
                or not workspace.is_dir():
            raise VerificationError("sandbox workspace must be the real workspace directory beside the outputs")
        real = workspace.resolve()
        if any(char in str(real) for char in ',"\r\n\0'):
            raise VerificationError("sandbox workspace path contains a character unsafe for a mount")
        expected_mount_source(str(real))  # refuses paths whose inspected Source could not be verified
        for base, directories, files in os.walk(real):
            if any(_alias(Path(base) / name) for name in (*directories, *files)):
                raise VerificationError("sandbox workspace contains a symlink or junction")
        for test in tests:
            target = real / test
            if not target.is_file() or _alias(target):
                raise VerificationError("selected test is not a regular file in the workspace")
        return real, evidence / stdout_path.name, evidence / stderr_path.name, evidence

    @staticmethod
    def _config_is_inert(directory: Path) -> bool:
        target = directory / "config.json"
        try:
            return (not _alias(directory) and directory.is_dir() and sorted(os.listdir(directory)) == ["config.json"]
                    and not _alias(target) and target.is_file() and target.read_bytes() == _INERT_CONFIG)
        except OSError:
            return False

    def _ensure_config(self, evidence: Path) -> Path:
        """Create (never overwrite) or re-validate the owned, empty docker client config directory."""

        directory = evidence / _CONFIG_DIRECTORY
        try:
            directory.mkdir()
        except FileExistsError:
            pass
        try:
            with (directory / "config.json").open("xb") as handle:
                handle.write(_INERT_CONFIG)
        except FileExistsError:
            pass
        if not self._config_is_inert(directory):
            raise SandboxUnavailable("docker config directory is not the owned inert directory")
        return directory

    def _global_arguments(self) -> tuple[str, ...]:
        if self._config_dir is None:
            raise SandboxUnavailable("docker config directory has not been established")
        return ("--config", str(self._config_dir), *(("--host", self._host) if self._host is not None else ()))

    def _create_argv(self, alloc: _Allocation, entry_args: tuple[str, ...], workspace: Path,
                     budget: VerificationBudget) -> tuple[str, ...]:
        memory, cpu, tmpfs = _limits(budget)
        argv = [
            self._docker or "", *self._global_arguments(), "create", "--name", alloc.name,
            "--label", f"{LABEL_KEY}={alloc.token}",
            "--pull", "never", "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--user", CONTAINER_USER,
            "--memory", str(memory), "--memory-swap", str(memory), "--cpus", f"{self._cpus:g}",
            "--pids-limit", str(self._pids), "--ulimit", f"cpu={cpu}:{cpu}", "--log-driver", "none",
            "--tmpfs", f"/tmp:rw,noexec,nosuid,nodev,mode=1777,size={tmpfs}",
            "--mount", f"type=bind,source={workspace},target={WORKSPACE_MOUNT},readonly",
            "--workdir", WORKSPACE_MOUNT,
        ]
        for key, value in CONTAINER_ENVIRONMENT:
            argv += ["--env", f"{key}={value}"]
        return (*argv, "--entrypoint", PYTHON_BINARY, self.image, *entry_args)

    # -- docker client ---------------------------------------------------------------

    def _verify_docker(self) -> None:
        """Refuse to run any executable whose current bytes differ from the sealed digest."""

        if self._docker is None:
            raise SandboxUnavailable("docker executable is unavailable")
        try:
            current = _file_digest(Path(self._docker))
        except OSError as error:
            raise SandboxUnavailable("docker executable cannot be read") from error
        if current != self._docker_digest:
            raise SandboxUnavailable("docker executable changed after it was sealed; refusing to run it")

    def _verify_config(self) -> None:
        """Refuse to run docker unless its client config is still exactly the owned inert directory."""

        if self._config_dir is None or not self._config_is_inert(self._config_dir):
            raise SandboxUnavailable("docker config directory is not the owned inert directory; refusing to run docker")

    def _prepare(self, deadline: _Deadline, ceiling: float) -> float:
        """Pre-effect checks; a failure here means no docker process was started."""

        self._verify_docker()
        self._verify_config()
        return deadline.bound(ceiling)

    def _invoke(self, argv: Sequence[str], deadline: _Deadline, **options: Any) -> CommandResult:
        timeout = self._prepare(deadline, options.pop("timeout", _CONTROL_TIMEOUT))
        options.setdefault("limit", _CONTROL_LIMIT)
        try:
            return self._runner(tuple(argv), environment=self._client_environment, timeout=timeout, **options)
        except OSError as error:
            raise SandboxUnavailable(f"docker client could not run: {type(error).__name__}") from error

    def _docker_call(self, deadline: _Deadline, *args: str, **options: Any) -> CommandResult:
        return self._invoke((self._docker or "", *self._global_arguments(), *args), deadline, **options)

    def _inspect(self, reference: str, deadline: _Deadline) -> dict[str, Any] | None:
        result = self._docker_call(deadline, "inspect", "--type", "container", reference)
        if result.timed_out or result.truncated:
            raise SandboxUnavailable("docker inspect did not complete")
        if result.returncode != 0:
            if _container_not_found(result, reference):
                return None
            raise SandboxUnavailable("docker inspect failed: " + _text(result.stderr))
        try:
            document = json.loads(result.stdout)
        except ValueError as error:
            raise SandboxUnavailable("docker inspect returned malformed data") from error
        if not (isinstance(document, list) and len(document) == 1 and isinstance(document[0], dict)):
            raise SandboxUnavailable("docker inspect returned an unexpected document")
        return document[0]

    def _verify_image(self, ex: _Execution) -> None:
        """Bind the pinned image's own baked environment before any container exists."""

        result = self._docker_call(ex.deadline, "image", "inspect", self.image)
        if result.timed_out or result.truncated or result.returncode != 0:
            raise SandboxUnavailable("pinned image could not be inspected locally: " + _text(result.stderr))
        try:
            document = json.loads(result.stdout)
        except ValueError as error:
            raise SandboxUnavailable("docker image inspect returned malformed data") from error
        if not (isinstance(document, list) and len(document) == 1 and isinstance(document[0], dict)):
            raise SandboxUnavailable("docker image inspect returned an unexpected document")
        image = document[0]
        pinned = self.image.rpartition("@")[2]
        identities = {str(image.get("Id", "")), *(str(item).rpartition("@")[2] for item in image.get("RepoDigests") or [])}
        if pinned not in identities:
            raise SandboxUnavailable("local image does not carry the pinned digest")
        baked = _environment_mapping(_mapping(image.get("Config")).get("Env"))
        if baked is None:
            raise SandboxUnavailable("pinned image environment is malformed or has duplicate keys")
        ex.expected_environment = {**baked, **dict(CONTAINER_ENVIRONMENT)}
        ex.journal.append(
            "image_verified", image=self.image, image_id=image.get("Id"), baked_environment_names=sorted(baked),
            expected_environment_digest=raw_sha256(canonical_json_bytes(ex.expected_environment)),
        )

    def _environment_report(self, env: object, ex: _Execution) -> dict[str, Any]:
        """Compare the container environment with the exact expected merge, recording names and digests only."""

        expected = ex.expected_environment
        actual = _environment_mapping(env)
        report: dict[str, Any] = {
            "expected_digest": raw_sha256(canonical_json_bytes(expected)) if expected is not None else None,
            "malformed": actual is None, "unexpected": [], "missing": [], "changed": [], "value_digests": {},
        }
        if actual is not None and expected is not None:
            report["unexpected"] = sorted(set(actual) - set(expected))
            report["missing"] = sorted(set(expected) - set(actual))
            report["changed"] = sorted(key for key in set(actual) & set(expected) if actual[key] != expected[key])
            report["value_digests"] = {
                key: raw_sha256(f"{key}={actual[key]}".encode())
                for key in (*report["unexpected"], *report["changed"])
            }
        report["exact"] = (expected is not None and actual == expected)
        return report

    def _owned(self, info: Mapping[str, Any], alloc: _Allocation) -> bool:
        config = _mapping(info.get("Config"))
        identifier = str(info.get("Id", ""))
        return (
            info.get("Name") == "/" + alloc.name
            and _mapping(config.get("Labels")).get(LABEL_KEY) == alloc.token
            and str(config.get("Image", "")).rpartition("@")[2] == self.image.rpartition("@")[2]
            and _CONTAINER_ID.fullmatch(identifier) is not None
            and alloc.container_id in (None, identifier)
        )

    def _require_owned(self, journal: _Journal, info: dict[str, Any] | None, alloc: _Allocation) -> dict[str, Any]:
        if info is None:
            raise SandboxUnavailable("allocation disappeared before its result was retained")
        if not self._owned(info, alloc):
            journal.append("ownership_mismatch", observed=_summary(info))
            raise SandboxOwnershipError("container does not carry this allocation's name, label and identity")
        return info

    def _configuration_problems(self, info: Mapping[str, Any], ex: _Execution) -> list[str]:
        host, config = _mapping(info.get("HostConfig")), _mapping(info.get("Config"))
        memory, cpu, tmpfs = _limits(ex.budget)
        workspace = str(ex.workspace)
        source = expected_mount_source(workspace)
        mounts, host_mounts = info.get("Mounts") or [], host.get("Mounts") or []
        ex.environment_report = self._environment_report(config.get("Env"), ex)
        checks = {
            "network": host.get("NetworkMode") == "none",
            "read-only root": host.get("ReadonlyRootfs") is True,
            "capabilities": [str(cap).upper() for cap in host.get("CapDrop") or []] == ["ALL"]
                            and not host.get("CapAdd"),
            "privileged": host.get("Privileged") is False,
            "no-new-privileges": host.get("SecurityOpt") == ["no-new-privileges"],
            "user": config.get("User") == CONTAINER_USER,
            "memory": host.get("Memory") == memory,
            "memory swap": host.get("MemorySwap") == memory,
            "pids": host.get("PidsLimit") == self._pids,
            "cpus": host.get("NanoCpus") == round(self._cpus * 1e9),
            "cpu ulimit": _ulimits_ok(host.get("Ulimits"), cpu),
            "log driver": _mapping(host.get("LogConfig")).get("Type") == "none",
            "tmpfs": _tmpfs_ok(host.get("Tmpfs"), tmpfs),
            "mounts": isinstance(mounts, list) and len(mounts) == 1
                      and _mapping(mounts[0]).get("Type") == "bind"
                      and _mapping(mounts[0]).get("Destination") == WORKSPACE_MOUNT
                      and _mapping(mounts[0]).get("RW") is False
                      and _mapping(mounts[0]).get("Source") in {workspace, source},
            "host mounts": isinstance(host_mounts, list) and len(host_mounts) <= 1 and all(
                _mapping(m).get("Type") == "bind" and _mapping(m).get("Target") == WORKSPACE_MOUNT
                and _mapping(m).get("ReadOnly") is True and _mapping(m).get("Source") in {workspace, source}
                for m in host_mounts
            ),
            "binds and devices": not (host.get("Binds") or host.get("Devices") or host.get("VolumesFrom")),
            "namespaces": host.get("PidMode") in ("", None) and host.get("IpcMode") in ("", None, "private"),
            "command": config.get("Entrypoint") == [PYTHON_BINARY] and config.get("Cmd") == list(ex.argv[1:]),
            "environment": ex.environment_report["exact"],
            "workdir": config.get("WorkingDir") == WORKSPACE_MOUNT,
            "stdin": config.get("OpenStdin") is not True and config.get("Tty") is not True,
        }
        return sorted(name for name, ok in checks.items() if not ok)

    # -- allocation lifecycle --------------------------------------------------------

    def _create(self, ex: _Execution) -> None:
        journal, alloc = ex.journal, ex.alloc
        try:
            self._verify_image(ex)
            timeout = self._prepare(ex.deadline, _CONTROL_TIMEOUT)
        except SandboxUnavailable as error:
            journal.append("create_result", outcome="not_attempted", error=str(error)[:300])
            raise
        # From here an effect may occur that we cannot observe.  Stay unresolved until the
        # daemon returns a container ID or an owned container is found and removed: no
        # exit code or error wording proves that a request was not submitted.
        alloc.create_unresolved = True
        try:
            result = self._runner(ex.create_argv, environment=self._client_environment, timeout=timeout,
                                  limit=_CONTROL_LIMIT)
        except OSError as error:
            journal.append("create_result", outcome="unknown", error=type(error).__name__)
            raise SandboxUnavailable("docker create outcome is unknown") from error
        identifier = _text(result.stdout)
        if (result.returncode == 0 and not result.timed_out and not result.truncated
                and _CONTAINER_ID.fullmatch(identifier)):
            alloc.container_id, alloc.create_unresolved = identifier, False
            journal.append("create_result", outcome="created", container_id=identifier)
            return
        journal.append(
            "create_result", outcome="unknown", returncode=result.returncode, timed_out=result.timed_out,
            stderr=_text(result.stderr),
        )
        raise SandboxUnavailable("docker create outcome is unresolved; a late container may still appear")

    def _stop(self, journal: _Journal, alloc: _Allocation, deadline: _Deadline) -> dict[str, Any]:
        reference = alloc.container_id or alloc.name
        kill = self._docker_call(deadline, "kill", reference)
        if kill.timed_out or (kill.returncode != 0 and b"is not running" not in kill.stderr.lower()):
            journal.append("stop", ok=False, stderr=_text(kill.stderr))
            raise SandboxUnavailable("docker kill failed")
        for _ in range(_STOP_POLLS):
            info = self._require_owned(journal, self._inspect(reference, deadline), alloc)
            if not _mapping(info.get("State")).get("Running"):
                journal.append("stop", ok=True, state=_state_summary(info))
                return info
            self._sleep(0.2)
        journal.append("stop", ok=False, detail="allocation still running")
        raise SandboxUnavailable("owned allocation did not stop")

    def _cleanup(self, journal: _Journal, alloc: _Allocation, deadline: _Deadline) -> bool:
        """Stop and remove only the container whose name, label and ID match this allocation.

        Absence verifies cleanup only when creation is resolved, and only on Docker's exact
        identifier-bound not-found diagnostic.  For an unresolved create it is an
        observation, never proof; any other error leaves cleanup unverified.
        """

        try:
            info = self._inspect(alloc.container_id or alloc.name, deadline)
            if info is None:
                if alloc.create_unresolved:
                    journal.append(
                        "cleanup", verified=False,
                        detail="allocation absent but its create outcome is unresolved; a late create may still appear",
                    )
                    return False
                journal.append("cleanup", verified=True, detail="allocation absent")
                return True
            self._require_owned(journal, info, alloc)
            cid: str = info["Id"]
            alloc.container_id = cid
            if _mapping(info.get("State")).get("Running"):
                self._stop(journal, alloc, deadline)
            removal = self._docker_call(deadline, "rm", cid)
            if (removal.timed_out or removal.returncode != 0) and self._inspect(cid, deadline) is not None:
                raise SandboxUnavailable("docker rm failed: " + _text(removal.stderr))
            if self._inspect(cid, deadline) is not None:
                raise SandboxUnavailable("allocation still present after removal")
            if alloc.create_unresolved:
                journal.append("create_resolved", container_id=cid, method="owned container found and removed")
                alloc.create_unresolved = False
            journal.append("cleanup", verified=True, removed=cid)
            return True
        except SandboxOwnershipError:
            raise
        except VerificationError as error:
            journal.append("cleanup", verified=False, error=str(error)[:500])
            return False

    def _execute(self, ex: _Execution) -> None:
        alloc, journal, budget = ex.alloc, ex.journal, ex.budget
        self._create(ex)
        cid = alloc.container_id
        if cid is None:
            raise SandboxUnavailable("created allocation has no identity")
        info = self._require_owned(journal, self._inspect(cid, ex.deadline), alloc)
        problems = self._configuration_problems(info, ex)
        ex.applied = {**_summary(info), "environment_report": ex.environment_report}
        journal.append("configuration_checked", ok=not problems, problems=problems, applied=ex.applied)
        if problems:
            raise SandboxUnavailable("container configuration differs from the sealed profile: " + ", ".join(problems))
        timeout = ex.deadline.remaining()
        if not timeout > 0:
            journal.append("start_refused", detail="execution deadline expired before start")
            raise SandboxUnavailable("execution deadline expired before start")
        journal.append(
            "start_attach", argv=[self._docker, *self._global_arguments(), "start", "--attach", cid], timeout=timeout,
        )
        attach = self._docker_call(
            ex.deadline, "start", "--attach", cid, timeout=timeout, limit=int(budget.max_output_bytes) + 1,
            stdout_path=ex.stdout_path, stderr_path=ex.stderr_path,
        )
        ex.timing["execution_seconds_used"] = ex.deadline.elapsed()
        capped = attach.truncated or max(attach.stdout_bytes, attach.stderr_bytes) > int(budget.max_output_bytes)
        journal.append(
            "attach_result", returncode=attach.returncode, timed_out=attach.timed_out, output_capped=capped,
            stdout_bytes=attach.stdout_bytes, stderr_bytes=attach.stderr_bytes,
        )
        # Everything after the attach shares one separate, truthfully recorded cleanup allowance.
        cleanup = ex.cleanup = _Deadline(self._clock, _CLEANUP_ALLOWANCE)
        final = self._require_owned(journal, self._inspect(cid, cleanup), alloc)
        if attach.timed_out or capped or _mapping(final.get("State")).get("Running"):
            final = self._stop(journal, alloc, cleanup)
        state = _mapping(final.get("State"))
        journal.append("final_state", state=_state_summary(final))
        code = state.get("ExitCode")
        exit_code: int | None = code if (
            state.get("Status") == "exited" and not _never_started(state)
            and isinstance(code, int) and not isinstance(code, bool)
        ) else None
        if exit_code == 0 and attach.returncode != 0:
            exit_code = None  # the attached stream ended abnormally; never report a pass from it
        cleaned = self._cleanup(journal, alloc, cleanup)
        status = (
            "TIMED_OUT" if attach.timed_out else "OUTPUT_CAPPED" if capped
            else "NOT_COMPLETED" if exit_code is None else "EXITED"
        )
        ex.facts = {
            "status": status, "exit_code": exit_code, "timed_out": attach.timed_out, "output_capped": capped,
            "oom_killed": bool(state.get("OOMKilled")), "cleanup_verified": cleaned,
            "create_unresolved": alloc.create_unresolved,
        }

    def _record_timing(self, ex: _Execution) -> None:
        cleanup = ex.cleanup
        ex.timing.setdefault("execution_seconds_used", ex.deadline.elapsed())
        ex.timing.update({
            "execution_seconds_allowed": ex.deadline.seconds,
            "cleanup_allowance_seconds": _CLEANUP_ALLOWANCE,
            "cleanup_seconds": cleanup.elapsed() if cleanup is not None else 0.0,
            "cleanup_allowance_exhausted": cleanup is not None and not cleanup.remaining() > 0,
        })

    def _publish(self, ex: _Execution) -> None:
        journal, alloc, budget = ex.journal, ex.alloc, ex.budget
        outputs = {}
        for label, path in (("stdout", ex.stdout_path), ("stderr", ex.stderr_path)):
            data = path.read_bytes()
            outputs[label] = {"path": str(path), "bytes": len(data), "digest": f"sha256:{hashlib.sha256(data).hexdigest()}"}
        memory, _, tmpfs = _limits(budget)
        document: dict[str, Any] = {
            "schema_version": 1, "kind": "oci-python-sandbox-execution", "execution_phase": alloc.phase,
            **ex.facts, "image_identity": self.image, "command": list(ex.argv),
            "container_environment": dict(CONTAINER_ENVIRONMENT),
            "environment_source": "explicit --env values merged over the pinned image's own baked variables; the container environment must equal that merge exactly; host environment is not forwarded",
            "docker": {
                "executable": self._docker, "executable_digest": self._docker_digest,
                "client_environment_names": sorted(self._client_environment),
                "config_directory": str(self._config_dir), "config_digest": _CONFIG_DIGEST, "host": self._host,
            },
            "allocation": {"name": alloc.name, "label": {LABEL_KEY: alloc.token}, "container_id": alloc.container_id},
            "create_argv": list(ex.create_argv),
            "start_argv": [self._docker, *self._global_arguments(), "start", "--attach", alloc.container_id],
            "limits": {
                "wall_seconds": ex.deadline.seconds, "cpu_seconds": budget.cpu_seconds, "memory_bytes": memory,
                "tmpfs_bytes": tmpfs, "max_output_bytes": budget.max_output_bytes, "cpus": self._cpus,
                "pids": self._pids,
            },
            "timing": ex.timing, "applied_configuration": ex.applied, "outputs": outputs,
            "journal": {"path": str(journal.path), "records": len(journal.records), "head_digest": journal.digest},
            "hostile_code_isolation": False,
            "boundary_claim": "trusted single-tenant local verification on a shared Docker engine; no tenant-dedicated attestation",
        }
        document["receipt_digest"] = raw_sha256(canonical_json_bytes(document))
        try:
            with ex.receipt_path.open("xb") as handle:
                handle.write(canonical_json_bytes(document) + b"\n")
        except FileExistsError as error:
            raise VerificationError("sandbox receipt already exists; overwrite refused") from error
        self._last = {
            "receipt_path": str(ex.receipt_path), "receipt_digest": document["receipt_digest"],
            "journal_path": str(journal.path), "journal_head_digest": journal.digest,
            "status": ex.facts.get("status"), "cleanup_verified": ex.facts.get("cleanup_verified"),
            "create_unresolved": ex.facts.get("create_unresolved"),
            "cleanup_seconds": ex.timing.get("cleanup_seconds", 0.0),
        }

    def run(
        self, argv: tuple[str, ...], *, workspace: Path, environment: dict[str, str],
        timeout: float, stdout_path: Path, stderr_path: Path, budget: VerificationBudget,
    ) -> tuple[int | None, bool]:
        self._last = None
        phase, entry_args, tests = self._approve(tuple(argv))
        if dict(environment) != dict(CONTAINER_ENVIRONMENT):
            raise VerificationError("sandbox environment must equal the sealed container environment")
        if not _positive_finite(timeout) or not all(_positive_finite(value) for value in (
            budget.wall_seconds, budget.cpu_seconds, budget.memory_bytes, budget.disk_bytes, budget.max_output_bytes,
        )):
            raise VerificationError("sandbox timeout and budgets must be positive finite numbers")
        deadline = _Deadline(self._clock, float(timeout))  # covers validation, create, inspect and attach
        self._verify_docker()
        real, stdout_path, stderr_path, evidence = self._validate_paths(workspace, stdout_path, stderr_path, tests)
        self._config_dir = self._ensure_config(evidence)
        identifier = self._allocation_id()
        if _ALLOCATION_ID.fullmatch(str(identifier)) is None:
            raise VerificationError("allocation id must be 32 lowercase hex characters")
        alloc = _Allocation(f"{NAME_PREFIX}{phase}-{identifier}", identifier, phase)
        receipt_path = evidence / f"sandbox-{phase}.receipt.json"
        if receipt_path.exists():
            raise VerificationError("sandbox receipt already exists; overwrite refused")
        journal = _Journal.create(evidence / f"sandbox-{phase}.journal.jsonl")
        for path in (stdout_path, stderr_path):
            try:
                path.open("xb").close()
            except FileExistsError as error:
                raise VerificationError("sandbox output already exists; overwrite refused") from error
        ex = _Execution(alloc, tuple(argv), self._create_argv(alloc, entry_args, real, budget), real,
                        stdout_path, stderr_path, receipt_path, budget, journal, deadline)
        # The intent is durable before any docker effect, so an unknown create is reconcilable.
        journal.append(
            "allocation_intent", execution_phase=phase, name=alloc.name, token=alloc.token, image=self.image,
            command=list(argv), container_environment=dict(CONTAINER_ENVIRONMENT),
            create_argv=list(ex.create_argv), docker=self._docker, docker_digest=self._docker_digest,
            docker_config=str(self._config_dir), docker_config_digest=_CONFIG_DIGEST, docker_host=self._host,
            workspace=str(real), execution_seconds_allowed=deadline.seconds,
        )
        try:
            self._execute(ex)
        except BaseException as error:
            journal.append("aborted", error=type(error).__name__, message=str(error)[:500])
            replacement: Exception | None = None
            cleanup = ex.cleanup or _Deadline(self._clock, _CLEANUP_ALLOWANCE)
            ex.cleanup = cleanup
            try:
                cleaned = self._cleanup(journal, alloc, cleanup)
            except SandboxOwnershipError as ownership:
                cleaned, replacement = False, ownership
            if not cleaned and replacement is None and isinstance(error, Exception):
                replacement = SandboxCleanupError(
                    "docker create outcome is unresolved; the allocation may still appear, call recover() later"
                    if alloc.create_unresolved else "sandbox cleanup could not be verified after an aborted run"
                )
            ex.facts = {"status": "ABORTED", "exit_code": None, "timed_out": False, "output_capped": False,
                        "cleanup_verified": cleaned, "create_unresolved": alloc.create_unresolved,
                        "error": type(error).__name__}
            self._record_timing(ex)
            journal.append("outcome", **ex.facts, timing=ex.timing)
            self._publish(ex)
            if replacement is not None:
                raise replacement from error
            raise
        self._record_timing(ex)
        journal.append("outcome", **ex.facts, timing=ex.timing)
        self._publish(ex)
        if not ex.facts["cleanup_verified"]:
            raise SandboxCleanupError("owned sandbox allocation could not be verified removed")
        return ex.facts["exit_code"], ex.facts["timed_out"]

    # -- recovery --------------------------------------------------------------------

    def _recovery_journal(
        self, original: Path, raw: bytes, records: list[dict[str, Any]], tail: bytes, intent: Mapping[str, Any],
    ) -> _Journal:
        """Open (or create exclusively) the separate journal for a torn original journal.

        The original bytes are never modified.  The recovery journal anchors their full
        SHA-256 plus the digest of the last verified record; a later call for the same
        original bytes continues the same recovery journal.
        """

        whole = hashlib.sha256(raw).hexdigest()
        target = original.with_name(f"sandbox-{intent['execution_phase']}.recovery-{whole[:16]}.journal.jsonl")
        anchor: dict[str, Any] = {
            "original_path": str(original), "original_bytes": len(raw), "original_sha256": f"sha256:{whole}",
            "prefix_records": len(records), "prefix_head_digest": records[-1]["digest"],
            "torn_tail_bytes": len(tail), "torn_tail_sha256": f"sha256:{hashlib.sha256(tail).hexdigest()}",
            "execution_phase": intent["execution_phase"], "name": intent["name"], "token": intent["token"],
        }
        if not target.exists():
            journal = _Journal.create(target)
            journal.append("recovery_anchor", **anchor)
            return journal
        if _alias(target) or not target.is_file():
            raise VerificationError("recovery journal path is not a regular file")
        existing, damaged = _Journal.verified_prefix(target.read_bytes())
        if damaged or not existing or existing[0]["phase"] != "recovery_anchor" or any(
            existing[0].get(key) != value for key, value in anchor.items()
        ):
            raise VerificationError("recovery journal does not anchor the current original journal bytes")
        return _Journal(target, existing)

    def recover(self, journal_path: str | Path) -> dict[str, Any]:
        """Reconcile an interrupted allocation from its own journal without executing again.

        Inspects the recorded name/ID, requires the recorded label, stops and removes
        only that container, and appends an outcome.  A never-started container is
        removed rather than started; a started one is never treated as a result.  An
        unresolved create stays unresolved (cleanup not verified) until an owned container
        is found and removed; absence alone never settles it, so call again later.  An
        ambiguous transport error is recorded and raised without settling anything, so a
        later call with a working connection can reap the allocation.  A torn final
        journal record is preserved and reconciled through a separate journal.  The same
        docker binary, owned client config and daemon endpoint as the original run are
        required.
        """

        self._verify_docker()
        path = Path(journal_path)
        if (not path.is_absolute() or _alias(path) or not path.is_file() or not is_within(path, self._evidence_root)
                or _JOURNAL_NAME.fullmatch(path.name) is None):
            raise VerificationError("recovery requires a journal file under the evidence root")
        raw = path.read_bytes()
        records, tail = _Journal.verified_prefix(raw)
        if not records:
            raise VerificationError(
                "journal has no intact allocation intent; the original is preserved untouched (see ADR-089 procedure)"
            )
        intent = records[0]
        name, token = str(intent.get("name", "")), str(intent.get("token", ""))
        if (intent["phase"] != "allocation_intent" or intent.get("image") != self.image
                or intent.get("execution_phase") not in {"version", "tests"} or not name.startswith(NAME_PREFIX)
                or _ALLOCATION_ID.fullmatch(token) is None):
            raise VerificationError("journal does not start with an allocation intent for this image")
        if intent.get("docker_digest") != self._docker_digest:
            raise SandboxUnavailable("journal was sealed with a different docker executable; refusing to run this one")
        if intent.get("docker_config_digest") != _CONFIG_DIGEST or intent.get("docker_host") != self._host:
            raise SandboxUnavailable(
                "journal was sealed with a different docker client config or daemon endpoint; refusing to reconcile it"
            )
        self._config_dir = self._ensure_config(path.parent)
        if tail:
            journal = self._recovery_journal(path, raw, records, tail, intent)
            history = [*records, *journal.records]
        else:
            journal = _Journal(path, records)
            history = journal.records
        alloc = _Allocation(name, token, str(intent["execution_phase"]))
        for record in history:
            if record["phase"] == "create_result" and record.get("container_id"):
                alloc.container_id = str(record["container_id"])
        alloc.create_unresolved = _creation_unresolved(history)
        last = history[-1]
        if last["phase"] == "outcome" and last.get("cleanup_verified") is True and not alloc.create_unresolved:
            return {"status": last.get("status"), "re_executed": False, "journal_head_digest": journal.digest,
                    "already_settled": True, "recovery_journal": str(journal.path) if tail else None}
        deadline = _Deadline(self._clock, _RECOVERY_ALLOWANCE)
        journal.append("recovery_begin", container_id=alloc.container_id, create_unresolved=alloc.create_unresolved,
                       torn_tail_bytes=len(tail))
        try:
            info = self._inspect(alloc.container_id or alloc.name, deadline)
        except SandboxUnavailable as error:
            journal.append("recovery_unavailable", error=str(error)[:500])
            raise
        state: Mapping[str, Any] = {}
        if info is not None:
            self._require_owned(journal, info, alloc)
            alloc.container_id = info["Id"]
            journal.append("recovery_owned", observed=_summary(info))
            if _mapping(info.get("State")).get("Running"):
                info = self._stop(journal, alloc, deadline)
            state = _mapping(info.get("State"))
        else:
            journal.append("recovery_absent", create_unresolved=alloc.create_unresolved)
        cleaned = self._cleanup(journal, alloc, deadline)
        if info is None:
            status = "RECOVERED_ABSENT" if cleaned else "CREATE_UNRESOLVED"
        else:
            status = "RECOVERED_NOT_STARTED" if _never_started(state) else "RECOVERED_AFTER_START"
        journal.append("outcome", status=status, cleanup_verified=cleaned, re_executed=False,
                       create_unresolved=alloc.create_unresolved,
                       observed_state=_state_summary(info) if info is not None else None)
        if not cleaned:
            raise SandboxCleanupError(
                "creation outcome is unresolved and no owned container is present; call recover() again later"
                if alloc.create_unresolved else "recovered allocation could not be verified removed"
            )
        return {"status": status, "re_executed": False, "journal_head_digest": journal.digest,
                "already_settled": False, "recovery_journal": str(journal.path) if tail else None}


__all__ = [
    "CONTAINER_ENVIRONMENT", "CommandResult", "DockerPythonSandbox", "ImagePythonUnittestAdapter",
    "LABEL_KEY", "PYTHON_BINARY", "SandboxCleanupError", "SandboxOwnershipError",
    "expected_mount_source", "run_bounded", "validate_image_reference",
]
