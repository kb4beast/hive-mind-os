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

    def run(self, intent: dict[str, Any]) -> dict[str, Any]:
        self._validate_intent(intent)
        decision = self.policy.decide(self.role, Action.RUN_COMMANDS, self.risk)
        if not decision.allowed:
            self._deny(intent, decision.reason)
        if self.tool_calls_used + 1 > self.allowance.tool_calls:
            self._deny(intent, "episode tool-call allowance exhausted")
        if self.compute_units_used + 1.0 > self.allowance.compute_units:
            self._deny(intent, "episode compute allowance exhausted")
        command = intent["command"]
        argv = list(command["argv"])
        resolved = shutil.which(argv[0])
        if resolved is None or _normalized_executable(resolved) not in {
            _normalized_executable(value) for value in self.spec.argv_allowlist
        }:
            self._deny(intent, "executable is not allowlisted")
        argv[0] = str(Path(resolved).resolve())
        self._validate_paths(argv, command["path_args"])
        if intent["actor_id"] == self.runner_identity:
            self._deny(intent, "runner identity must differ from acting identity")

        self.tool_calls_used += 1
        self.compute_units_used += 1.0
        self.spawn_count += 1
        started = time.monotonic()
        process = self._spawn(argv)
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
            process.wait(timeout=self.spec.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_tree(process)
            process.wait()
        for reader in readers:
            reader.join(timeout=2)
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
            raise SandboxDenied("; ".join(validation.issues))
        if intent.get("kind") != "command" or not isinstance(intent.get("command"), dict):
            raise SandboxDenied("sandbox requires a typed command intent")
        try:
            expected = tool_intent_digest(intent)
        except (TypeError, ValueError):
            raise SandboxDenied("intent cannot be canonically digested") from None
        if intent.get("action_digest") != expected:
            raise SandboxDenied("intent digest does not bind the command")

    def _validate_paths(self, argv: list[str], indexes: list[int]) -> None:
        for index in indexes:
            if index < 1 or index >= len(argv):
                raise ConfinementViolation("path argument index is invalid")
            try:
                parts = portable_path_parts(argv[index])
            except ValueError as error:
                raise ConfinementViolation(str(error)) from None
            resolved = (self.spec.root / Path(*parts)).resolve()
            try:
                resolved.relative_to(self.spec.root)
            except ValueError:
                raise ConfinementViolation("path argument escapes sandbox root") from None
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
        return cast(subprocess.Popen[bytes], subprocess.Popen(argv, **kwargs))

    def _read_capped(
        self,
        pipe: Any,
        target: list[bytes],
        truncated: list[bool],
        stream_index: int,
    ) -> None:
        remaining = self.spec.max_output_bytes
        while True:
            chunk = pipe.read(65536)
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
    def _kill_tree(process: subprocess.Popen[bytes]) -> None:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            taskkill = shutil.which("taskkill")
            if taskkill is not None:
                completed = subprocess.run(
                    [taskkill, "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    check=False,
                )
                if completed.returncode == 0:
                    return
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

    def _deny(self, intent: Mapping[str, Any], reason: str) -> NoReturn:
        if self.ledger is not None:
            self.ledger.append_event(
                str(intent.get("mission_id", "unknown")),
                "sandbox.denied",
                self.role.value,
                {"action_id": intent.get("action_id"), "reason": reason},
            )
        raise SandboxDenied(reason)
