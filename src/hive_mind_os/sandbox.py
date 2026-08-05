"""Deny-by-default process sandbox with typed, content-addressed receipts.

This process tier does not provide hard network isolation. POSIX adds rlimits and process
groups; Windows provides confinement checks and best-effort timeout termination.
"""

from __future__ import annotations

import json
import os
import re
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
from .current_state_audit import _WindowsJob
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
    return name.removesuffix(".exe").removesuffix(".cmd").removesuffix(".bat")


_INTERPRETER_FLAGS = {
    "python": frozenset({"-c", "-m"}),
    "python3": frozenset({"-c", "-m"}),
    "pypy": frozenset({"-c", "-m"}),
    "pypy3": frozenset({"-c", "-m"}),
    "node": frozenset({"-e", "--eval", "-p", "--print"}),
    "ruby": frozenset({"-e"}),
    "perl": frozenset({"-e"}),
    "sh": frozenset({"-c"}),
    "bash": frozenset({"-c"}),
}
_SIMPLE_PATH_TOKEN = re.compile(r"[^/\\\s]+\.[A-Za-z0-9]{1,10}\Z")


def _interpreter_flags(executable: str) -> frozenset[str]:
    normalized = _normalized_executable(executable)
    direct = _INTERPRETER_FLAGS.get(normalized)
    if direct is not None:
        return direct
    if re.fullmatch(r"(?:python|pypy)\d+(?:\.\d+)*", normalized):
        return frozenset({"-c", "-m"})
    return frozenset()


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    root: Path
    writable: tuple[str, ...] = ()
    argv_allowlist: tuple[str, ...] = ("python",)
    allow_interpreter_flags: bool = False
    env_allowlist: tuple[str, ...] = ()
    fixed_environment: tuple[tuple[str, str], ...] = ()
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
        if type(self.allow_interpreter_flags) is not bool:
            raise ValueError("allow_interpreter_flags must be boolean")
        fixed_names: set[str] = set()
        for name, value in self.fixed_environment:
            if (
                not isinstance(name, str)
                or not name
                or "=" in name
                or "\x00" in name
                or not isinstance(value, str)
                or "\x00" in value
                or name in fixed_names
            ):
                raise ValueError("fixed environment entries must have unique safe names and values")
            fixed_names.add(name)
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
        payload: dict[str, object] = {
            "root": self.root.as_posix(),
            "writable": list(self.writable),
            "argv_allowlist": sorted(_normalized_executable(v) for v in self.argv_allowlist),
            "allow_interpreter_flags": self.allow_interpreter_flags,
            "env_allowlist": sorted(self.env_allowlist),
            "timeout_s": self.timeout_s,
            "max_output_bytes": self.max_output_bytes,
            "cpu_seconds": self.cpu_seconds,
            "memory_bytes": self.memory_bytes,
        }
        if self.fixed_environment:
            payload["fixed_environment"] = sorted(self.fixed_environment)
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
        forbidden_flags = _interpreter_flags(argv[0])
        if not self.spec.allow_interpreter_flags and any(
            argument in forbidden_flags for argument in argv[1:]
        ):
            self._deny(intent, "inline interpreter execution is not allowed by default")
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
        self._close_windows_job(process)
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
        path_indexes = set(indexes)
        path_indexes.update(
            index
            for index, argument in enumerate(argv[1:], start=1)
            if self._is_path_like(argument)
        )
        for index in sorted(path_indexes):
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

    @staticmethod
    def _is_path_like(argument: str) -> bool:
        if argument in {".", ".."} or argument.startswith(("/", "\\", "~")):
            return True
        if "=" in argument:
            return False
        if "\\" in argument or re.match(r"^[A-Za-z]:", argument):
            return True
        if "/" in argument:
            final_segment = argument.rsplit("/", 1)[-1]
            return argument.startswith(("./", "../")) or bool(
                _SIMPLE_PATH_TOKEN.fullmatch(final_segment)
            )
        return not argument.startswith("-") and bool(_SIMPLE_PATH_TOKEN.fullmatch(argument))

    def _spawn(self, argv: list[str]) -> subprocess.Popen[bytes]:
        environment = {
            name: os.environ[name]
            for name in self.spec.env_allowlist
            if name in os.environ
        }
        environment.update(dict(self.spec.fixed_environment))
        kwargs: dict[str, Any] = {
            "cwd": self.spec.root,
            "env": environment,
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "shell": False,
        }
        windows_job: _WindowsJob | None = None
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
            windows_job = _WindowsJob()
            kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            ) | 0x00000004
        try:
            process = cast(subprocess.Popen[bytes], subprocess.Popen(argv, **kwargs))
        except Exception:
            if windows_job is not None:
                windows_job.close()
            raise
        if windows_job is not None:
            try:
                windows_job.assign_and_resume(process)
            except Exception:
                try:
                    process.kill()
                except OSError:
                    pass
                windows_job.close()
                raise
            setattr(process, "_hive_mind_windows_job", windows_job)
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

    @classmethod
    def _tree_alive(cls, process: subprocess.Popen[bytes]) -> bool:
        if os.name == "nt":
            job = getattr(process, "_hive_mind_windows_job", None)
            if job is not None:
                try:
                    return job.has_active_processes()
                except OSError:
                    return True
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
        return False

    @staticmethod
    def _close_windows_job(process: subprocess.Popen[bytes]) -> None:
        job = getattr(process, "_hive_mind_windows_job", None)
        if job is not None:
            job.close()
            setattr(process, "_hive_mind_windows_job", None)

    @classmethod
    def _kill_tree(cls, process: subprocess.Popen[bytes]) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            job = getattr(process, "_hive_mind_windows_job", None)
            if job is not None:
                job.terminate()
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
        execution: dict[str, Any] = {
            "argv": argv,
            "requested_argv": list(intent["command"]["argv"]),
            "exit_code": exit_code,
            "duration_ms": round(duration_s * 1000, 3),
            "outcome": outcome,
            "stdout": {"digest": artifacts[0]["digest"], "bytes": len(stdout), "truncated": truncated[0]},
            "stderr": {"digest": artifacts[1]["digest"], "bytes": len(stderr), "truncated": truncated[1]},
            "sandbox_spec_digest": self.spec.spec_digest(),
            "runner_identity": self.runner_identity,
        }
        acceptance_specification = intent.get("acceptance_specification")
        if isinstance(acceptance_specification, Mapping):
            execution["acceptance_specification"] = dict(acceptance_specification)
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
            "enforced": {
                "filesystem": "none",
                "network": "none",
                "resources": "posix-rlimit-only",
                "executable_identity": "name-allowlist-only",
            },
            "execution": execution,
            "verified_by": self.runner_identity,
        }
        validation = validate_contract("tool-receipt", receipt)
        if not validation.valid:
            raise SandboxError("; ".join(validation.issues))
        raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        digest = sha256_digest(raw)
        path = f"r/{digest.removeprefix('sha256:')}.json"
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
