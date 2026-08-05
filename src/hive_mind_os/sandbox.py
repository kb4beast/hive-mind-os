"""Deny-by-default process sandbox with typed, content-addressed receipts.

This process tier does not provide hard network isolation. POSIX adds rlimits and process
groups; Windows provides confinement checks and best-effort timeout termination.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, NoReturn, cast
from uuid import uuid4

from .autonomy import EpisodeAllowance
from .contracts import tool_intent_digest, validate_contract
from .ledger import EvidenceLedger
from .models import RiskTier, Role, utc_now
from .policy import Action, PolicyEngine
from .receipts import ReceiptReference, portable_path_parts, sha256_digest


class SandboxError(RuntimeError):
    pass


class SandboxDenied(SandboxError):
    pass


class ConfinementViolation(SandboxDenied):
    pass


class SandboxTimeout(SandboxError):
    def __init__(self, receipt: dict[str, Any]) -> None:
        super().__init__("sandbox command timed out")
        self.receipt = receipt


def _normalized_executable(value: str) -> str:
    name = Path(value).name.casefold()
    return name.removesuffix(".exe")


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    root: Path
    writable: tuple[str, ...] = ()
    argv_allowlist: tuple[str, ...] = ("python",)
    env_allowlist: tuple[str, ...] = ()
    timeout_s: float = 30.0
    max_output_bytes: int = 1_000_000
    cpu_seconds: int | None = None
    memory_bytes: int | None = None

    def __post_init__(self) -> None:
        root = self.root.resolve()
        if not root.is_dir():
            raise ValueError("sandbox root must be an existing directory")
        object.__setattr__(self, "root", root)
        if not self.argv_allowlist or self.timeout_s <= 0 or self.max_output_bytes < 1:
            raise ValueError("sandbox allowlist and limits must be positive")
        if self.cpu_seconds is not None and self.cpu_seconds < 1:
            raise ValueError("CPU limit must be positive")
        if self.memory_bytes is not None and self.memory_bytes < 1:
            raise ValueError("memory limit must be positive")
        for value in self.writable:
            parts = portable_path_parts(value)
            resolved = (root / Path(*parts)).resolve()
            try:
                resolved.relative_to(root)
            except ValueError:
                raise ValueError("writable path escapes sandbox root") from None

    def spec_digest(self) -> str:
        payload = {
            "root": self.root.as_posix(),
            "writable": list(self.writable),
            "argv_allowlist": sorted(_normalized_executable(v) for v in self.argv_allowlist),
            "env_allowlist": sorted(self.env_allowlist),
            "timeout_s": self.timeout_s,
            "max_output_bytes": self.max_output_bytes,
            "cpu_seconds": self.cpu_seconds,
            "memory_bytes": self.memory_bytes,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return sha256_digest(raw)


class SandboxRunner:
    def __init__(
        self,
        spec: SandboxSpec,
        trusted_root: str | Path,
        allowance: EpisodeAllowance,
        *,
        policy: PolicyEngine | None = None,
        role: Role = Role.BUILDER,
        risk: RiskTier = RiskTier.MODERATE,
        runner_identity: str = "sandbox-runner-v1",
        ledger: EvidenceLedger | None = None,
    ) -> None:
        self.spec = spec
        self.trusted_root = Path(trusted_root).resolve()
        try:
            self.trusted_root.relative_to(self.spec.root)
        except ValueError:
            pass
        else:
            raise ValueError("trusted receipt root must be outside the sandbox root")
        self.trusted_root.mkdir(parents=True, exist_ok=True)
        if not runner_identity.strip():
            raise ValueError("runner identity is required")
        self.allowance = allowance
        self.policy = policy or PolicyEngine()
        self.role = role
        self.risk = risk
        self.runner_identity = runner_identity
        self.ledger = ledger
        self.tool_calls_used = 0
        self.compute_units_used = 0.0
        self.spawn_count = 0
        self.last_reference: ReceiptReference | None = None
        self._usage_lock = threading.Lock()

    def run(self, intent: dict[str, Any]) -> dict[str, Any]:
        self._validate_intent(intent)
        decision = self.policy.decide(self.role, Action.RUN_COMMANDS, self.risk)
        if not decision.allowed:
            self._deny(intent, decision.reason)
        with self._usage_lock:
            if self.tool_calls_used + 1 > self.allowance.tool_calls:
                self._deny(intent, "episode tool-call allowance exhausted")
            if self.compute_units_used + 1.0 > self.allowance.compute_units:
                self._deny(intent, "episode compute allowance exhausted")
            self.tool_calls_used += 1
            self.compute_units_used += 1.0
        command = intent["command"]
        argv = list(command["argv"])
        if any("\x00" in argument for argument in argv):
            self._deny(intent, "command arguments must not contain NUL bytes")
        resolved = shutil.which(argv[0])
        if resolved is None or _normalized_executable(resolved) not in {
            _normalized_executable(value) for value in self.spec.argv_allowlist
        }:
            self._deny(intent, "executable is not allowlisted")
        argv[0] = str(Path(resolved).resolve())
        self._validate_paths(intent, argv, command["path_args"])
        if intent["actor_id"] == self.runner_identity:
            self._deny(intent, "runner identity must differ from acting identity")

        started = time.monotonic()
        deadline = started + self.spec.timeout_s
        try:
            process = self._spawn(argv)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self._deny(intent, f"process creation failed: {type(error).__name__}")
        with self._usage_lock:
            self.spawn_count += 1
        stdout: list[bytes] = []
        stderr: list[bytes] = []
        truncated = [False, False]
        readers = [
            threading.Thread(
                target=self._read_capped,
                args=(process.stdout, stdout, truncated, 0),
                daemon=True,
            ),
            threading.Thread(
                target=self._read_capped,
                args=(process.stderr, stderr, truncated, 1),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
        while not timed_out:
            readers_alive = any(reader.is_alive() for reader in readers)
            tree_alive = self._tree_alive(process)
            if not readers_alive and not tree_alive:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            for reader in readers:
                if reader.is_alive():
                    reader.join(timeout=min(remaining, 0.02))
            if not any(reader.is_alive() for reader in readers) and tree_alive:
                time.sleep(min(remaining, 0.01))
        if timed_out:
            self._kill_tree(process)
            if process.poll() is None:
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for reader in readers:
            reader.join(timeout=0.5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
        out = b"".join(stdout)
        err = b"".join(stderr)
        outcome = "timeout" if timed_out else ("succeeded" if process.returncode == 0 else "failed")
        receipt = self._persist(
            intent,
            argv,
            process.returncode if not timed_out else None,
            time.monotonic() - started,
            outcome,
            out,
            err,
            truncated,
        )
        if timed_out:
            raise SandboxTimeout(receipt)
        return receipt

    def _validate_intent(self, intent: dict[str, Any]) -> None:
        validation = validate_contract("tool-intent", intent)
        if not validation.valid:
            self._deny(intent, "; ".join(validation.issues))
        if intent.get("kind") != "command" or not isinstance(intent.get("command"), dict):
            self._deny(intent, "sandbox requires a typed command intent")
        try:
            expected = tool_intent_digest(intent)
        except (TypeError, ValueError):
            self._deny(intent, "intent cannot be canonically digested")
        if intent.get("action_digest") != expected:
            self._deny(intent, "intent digest does not bind the command")

    def _validate_paths(
        self,
        intent: Mapping[str, Any],
        argv: list[str],
        indexes: list[int],
    ) -> None:
        for index in indexes:
            if index < 1 or index >= len(argv):
                self._deny(
                    intent,
                    "path argument index is invalid",
                    ConfinementViolation,
                )
            try:
                parts = portable_path_parts(argv[index])
            except ValueError as error:
                self._deny(intent, str(error), ConfinementViolation)
            resolved = (self.spec.root / Path(*parts)).resolve()
            try:
                resolved.relative_to(self.spec.root)
            except ValueError:
                self._deny(
                    intent,
                    "path argument escapes sandbox root",
                    ConfinementViolation,
                )
            argv[index] = str(resolved)

    def _spawn(self, argv: list[str]) -> subprocess.Popen[bytes]:
        kwargs: dict[str, Any] = {
            "cwd": self.spec.root,
            "env": {name: os.environ[name] for name in self.spec.env_allowlist if name in os.environ},
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
            if self.spec.cpu_seconds is not None or self.spec.memory_bytes is not None:
                cpu_seconds = self.spec.cpu_seconds
                memory_bytes = self.spec.memory_bytes

                def set_limits() -> None:
                    import resource

                    if cpu_seconds is not None:
                        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
                    if memory_bytes is not None:
                        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

                kwargs["preexec_fn"] = set_limits
        else:
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        process = cast(subprocess.Popen[bytes], subprocess.Popen(argv, **kwargs))
        if os.name == "nt":
            setattr(
                process,
                "_hive_mind_creation_time",
                self._windows_process_creation_time(process),
            )
        return process

    def _read_capped(
        self,
        pipe: Any,
        target: list[bytes],
        truncated: list[bool],
        stream_index: int,
    ) -> None:
        remaining = self.spec.max_output_bytes
        while True:
            try:
                chunk = pipe.read(65536)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            accepted_bytes = 0
            if remaining:
                accepted = chunk[:remaining]
                target.append(accepted)
                accepted_bytes = len(accepted)
                remaining -= accepted_bytes
            if len(chunk) > accepted_bytes:
                truncated[stream_index] = True

    @staticmethod
    def _windows_process_table() -> dict[int, int]:
        if os.name != "nt":
            return {}
        import ctypes

        class ProcessEntry(ctypes.Structure):
            _fields_ = [
                ("size", ctypes.c_ulong),
                ("usage", ctypes.c_ulong),
                ("pid", ctypes.c_ulong),
                ("default_heap", ctypes.c_size_t),
                ("module_id", ctypes.c_ulong),
                ("threads", ctypes.c_ulong),
                ("parent_pid", ctypes.c_ulong),
                ("priority", ctypes.c_long),
                ("flags", ctypes.c_ulong),
                ("executable", ctypes.c_wchar * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        create_snapshot = kernel32.CreateToolhelp32Snapshot
        create_snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        create_snapshot.restype = ctypes.c_void_p
        first_process = kernel32.Process32FirstW
        first_process.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
        first_process.restype = ctypes.c_int
        next_process = kernel32.Process32NextW
        next_process.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
        next_process.restype = ctypes.c_int
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int
        snapshot = create_snapshot(0x00000002, 0)
        invalid_handle = ctypes.c_void_p(-1).value
        if snapshot == invalid_handle:
            return {}
        table: dict[int, int] = {}
        try:
            entry = ProcessEntry()
            entry.size = ctypes.sizeof(ProcessEntry)
            success = first_process(snapshot, ctypes.byref(entry))
            while success:
                table[int(entry.pid)] = int(entry.parent_pid)
                success = next_process(snapshot, ctypes.byref(entry))
        finally:
            close_handle(snapshot)
        return table

    @staticmethod
    def _windows_process_creation_time_from_handle(handle: int) -> int | None:
        if os.name != "nt":
            return None
        import ctypes

        class FileTime(ctypes.Structure):
            _fields_ = [
                ("low", ctypes.c_ulong),
                ("high", ctypes.c_ulong),
            ]

        kernel32 = ctypes.windll.kernel32
        get_process_times = kernel32.GetProcessTimes
        get_process_times.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
            ctypes.POINTER(FileTime),
        ]
        get_process_times.restype = ctypes.c_int
        created = FileTime()
        exited = FileTime()
        kernel = FileTime()
        user = FileTime()
        if not get_process_times(
            ctypes.c_void_p(handle),
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None
        return (int(created.high) << 32) | int(created.low)

    @classmethod
    def _windows_process_creation_time(
        cls,
        process: subprocess.Popen[bytes],
    ) -> int | None:
        handle = getattr(process, "_handle", None)
        if handle is None:
            return None
        return cls._windows_process_creation_time_from_handle(int(handle))

    @classmethod
    def _windows_pid_creation_time(cls, pid: int) -> int | None:
        if os.name != "nt":
            return None
        import ctypes

        kernel32 = ctypes.windll.kernel32
        open_process = kernel32.OpenProcess
        open_process.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        open_process.restype = ctypes.c_void_p
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.c_void_p]
        close_handle.restype = ctypes.c_int
        handle = open_process(0x1000, False, pid)
        if not handle:
            return None
        try:
            return cls._windows_process_creation_time_from_handle(int(handle))
        finally:
            close_handle(handle)

    @staticmethod
    def _descendants_from_table(
        root_pid: int,
        root_creation_time: int | None,
        table: Mapping[int, int],
        creation_times: Mapping[int, int | None],
    ) -> set[int]:
        def eligible(pid: int) -> bool:
            created = creation_times.get(pid)
            return (
                root_creation_time is None
                or created is None
                or created >= root_creation_time
            )

        descendants: set[int] = set()
        frontier = {root_pid}
        while frontier:
            children = {
                pid
                for pid, parent_pid in table.items()
                if parent_pid in frontier
                and pid not in descendants
                and eligible(pid)
            }
            descendants.update(children)
            frontier = children
        return descendants

    @classmethod
    def _windows_descendants(
        cls,
        root_pid: int,
        root_creation_time: int | None,
    ) -> set[int]:
        table = cls._windows_process_table()
        candidates: set[int] = set()
        frontier = {root_pid}
        while frontier:
            children = {
                pid
                for pid, parent_pid in table.items()
                if parent_pid in frontier and pid not in candidates
            }
            candidates.update(children)
            frontier = children
        creation_times = {
            pid: cls._windows_pid_creation_time(pid) for pid in candidates
        }
        return cls._descendants_from_table(
            root_pid,
            root_creation_time,
            table,
            creation_times,
        )

    @classmethod
    def _root_creation_time(
        cls,
        process: subprocess.Popen[bytes],
    ) -> int | None:
        creation_time = getattr(process, "_hive_mind_creation_time", None)
        if isinstance(creation_time, int):
            return creation_time
        return cls._windows_process_creation_time(process)

    @classmethod
    def _tree_alive(cls, process: subprocess.Popen[bytes]) -> bool:
        if process.poll() is None:
            return True
        if os.name == "posix":
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
            return True
        return bool(
            cls._windows_descendants(
                process.pid,
                cls._root_creation_time(process),
            )
        )

    @classmethod
    def _kill_tree(cls, process: subprocess.Popen[bytes]) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            # Do not use taskkill /T here: it follows a recycled PID solely by parent
            # PID and bypasses the creation-time filter required by ADR-008.
            descendants = cls._windows_descendants(
                process.pid,
                cls._root_creation_time(process),
            )
            if descendants:
                import ctypes

                kernel32 = ctypes.windll.kernel32
            for pid in descendants:
                handle = kernel32.OpenProcess(0x0001, False, pid)
                if handle:
                    try:
                        kernel32.TerminateProcess(handle, 1)
                    finally:
                        kernel32.CloseHandle(handle)
            if process.poll() is None:
                process.kill()

    def _persist(
        self,
        intent: Mapping[str, Any],
        argv: list[str],
        exit_code: int | None,
        duration_s: float,
        outcome: str,
        stdout: bytes,
        stderr: bytes,
        truncated: list[bool],
    ) -> dict[str, Any]:
        observed_at = utc_now()
        artifacts = []
        for label, content in (("stdout", stdout), ("stderr", stderr)):
            digest = sha256_digest(content)
            path = f"artifacts/{digest.removeprefix('sha256:')}.{label}"
            self._atomic_write(path, content)
            artifacts.append(
                {
                    "artifact_id": label,
                    "path": path,
                    "digest": digest,
                    "media_type": "application/octet-stream",
                    "bytes": len(content),
                    "created_by": self.runner_identity,
                    "created_at": observed_at,
                    "provenance_refs": [intent["action_digest"]],
                }
            )
        receipt = {
            "schema_version": 1,
            "receipt_id": f"REC-{uuid4()}",
            "action_id": intent["action_id"],
            "provider": "hive-mind-process-sandbox",
            "execution_id": f"EXEC-{uuid4()}",
            "mission_id": intent["mission_id"],
            "state_ref": intent["state_ref"],
            "actor_id": intent["actor_id"],
            "policy_decision_ref": intent["policy_decision_ref"],
            "lease_id": intent["lease_id"],
            "action_kind": "command",
            "action_digest": intent["action_digest"],
            "executed": True,
            "result": "succeeded" if outcome == "succeeded" else "failed",
            "observed_at": observed_at,
            "artifacts": artifacts,
            "execution": {
                "argv": argv,
                "exit_code": exit_code,
                "duration_ms": round(duration_s * 1000, 3),
                "outcome": outcome,
                "stdout": {"digest": artifacts[0]["digest"], "bytes": len(stdout), "truncated": truncated[0]},
                "stderr": {"digest": artifacts[1]["digest"], "bytes": len(stderr), "truncated": truncated[1]},
                "sandbox_spec_digest": self.spec.spec_digest(),
                "runner_identity": self.runner_identity,
            },
            "verified_by": self.runner_identity,
        }
        validation = validate_contract("tool-receipt", receipt)
        if not validation.valid:
            raise SandboxError("; ".join(validation.issues))
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        digest = sha256_digest(raw)
        path = f"receipts/{digest.removeprefix('sha256:')}.json"
        self._atomic_write(path, raw)
        self.last_reference = ReceiptReference(path, digest)
        return receipt

    def _atomic_write(self, relative: str, content: bytes) -> None:
        destination = self.trusted_root / Path(*portable_path_parts(relative))
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != content:
                raise SandboxError("content-addressed artifact collision")
            return
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, destination)

    def _deny(
        self,
        intent: object,
        reason: str,
        error_type: type[SandboxDenied] = SandboxDenied,
    ) -> NoReturn:
        document = intent if isinstance(intent, Mapping) else {}
        if self.ledger is not None:
            self.ledger.append_event(
                str(document.get("mission_id", "unknown")),
                "sandbox.denied",
                self.role.value,
                {"action_id": document.get("action_id"), "reason": reason},
            )
        raise error_type(reason)
