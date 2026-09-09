"""Sealed verification adapters for arbitrary local repository targets.

Commands are selected only by installed adapter code.  Model reports and target
text cannot supply an argv.  The default sandbox requirement is hostile-code
isolation and therefore fails closed when only the explicitly weaker local
single-operator process boundary is configured.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from .path_boundary import is_within, require_external_path
from .runtime_contracts import canonical_json_bytes, raw_sha256


class VerificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class VerificationBudget:
    wall_seconds: float = 300.0
    cpu_seconds: int = 240
    memory_bytes: int = 1_073_741_824
    disk_bytes: int = 1_073_741_824
    max_output_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        values = (self.wall_seconds, self.cpu_seconds, self.memory_bytes, self.disk_bytes, self.max_output_bytes)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0 for value in values):
            raise VerificationError("verification budgets must be positive numbers")


@dataclass(frozen=True, slots=True)
class SandboxRequirements:
    network_policy: str = "deny"
    hostile_code_isolation: bool = True
    secret_access: str = "deny"

    def __post_init__(self) -> None:
        if self.network_policy not in {"deny", "inherit"}:
            raise VerificationError("network policy must be deny or inherit")
        if self.secret_access != "deny":
            raise VerificationError("verification never grants secret access")


@dataclass(frozen=True, slots=True)
class SandboxCapabilities:
    adapter_id: str
    adapter_version: str
    available: bool
    hostile_code_isolation: bool
    network_deny: bool
    cpu_memory_limits: bool
    filesystem_isolation: bool
    process_tree_cleanup: bool
    runtime_identity: str

    def document(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_version": self.adapter_version,
            "available": self.available,
            "hostile_code_isolation": self.hostile_code_isolation,
            "network_deny": self.network_deny,
            "cpu_memory_limits": self.cpu_memory_limits,
            "filesystem_isolation": self.filesystem_isolation,
            "process_tree_cleanup": self.process_tree_cleanup,
            "runtime_identity": self.runtime_identity,
            "image_identity": None,
            "boundary_claim": (
                "hostile-code-isolation" if self.hostile_code_isolation
                else "trusted-local-process-only"
            ),
        }


class SandboxAdapter(Protocol):
    @property
    def capabilities(self) -> SandboxCapabilities: ...

    def run(
        self, argv: tuple[str, ...], *, workspace: Path, environment: dict[str, str],
        timeout: float, stdout_path: Path, stderr_path: Path, budget: VerificationBudget,
    ) -> tuple[int | None, bool]: ...


def _kill_tree(process: subprocess.Popen[Any]) -> None:
    if os.name == "nt":
        taskkill = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"
        subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, timeout=15, check=False)
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired as error:
        raise VerificationError("sandbox process tree could not be terminated") from error


class LocalProcessSandbox:
    """Truthfully labelled compatibility boundary for trusted local targets."""

    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            "local-process", "1", True, False, False, os.name != "nt", False, True,
            f"{platform.system()}-{platform.release()}|python-{platform.python_version()}",
        )

    def run(
        self, argv: tuple[str, ...], *, workspace: Path, environment: dict[str, str],
        timeout: float, stdout_path: Path, stderr_path: Path, budget: VerificationBudget,
    ) -> tuple[int | None, bool]:
        options: dict[str, Any]
        if os.name == "nt":
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
        else:
            def limits() -> None:
                import resource
                resource.setrlimit(resource.RLIMIT_CPU, (budget.cpu_seconds, budget.cpu_seconds))
                resource.setrlimit(resource.RLIMIT_AS, (budget.memory_bytes, budget.memory_bytes))
            options = {"start_new_session": True, "preexec_fn": limits}
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(list(argv), cwd=workspace, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       shell=False, **options)
            try:
                process.wait(timeout=timeout)
                return process.returncode, False
            except subprocess.TimeoutExpired:
                _kill_tree(process)
                return process.returncode, True
            except BaseException:
                _kill_tree(process)
                raise


class UnavailableSandbox:
    @property
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities("unavailable", "1", False, False, False, False, False, False, "unavailable")

    def run(self, *args: Any, **kwargs: Any) -> tuple[int | None, bool]:
        raise VerificationError("sandbox adapter is unavailable")


@dataclass(frozen=True, slots=True)
class SealedCommand:
    adapter_id: str
    argv: tuple[str, ...]
    version_argv: tuple[str, ...]
    selected_tests: tuple[str, ...]
    fixed_environment: tuple[tuple[str, str], ...] = ()
    verification_kind: str = "test-execution"

    def __post_init__(self) -> None:
        if self.verification_kind not in {"test-execution", "compile-check"}:
            raise VerificationError("verification kind is unsupported")

    @property
    def digest(self) -> str:
        return raw_sha256(canonical_json_bytes({
            "adapter_id": self.adapter_id, "argv": list(self.argv),
            "version_argv": list(self.version_argv), "selected_tests": list(self.selected_tests),
            "fixed_environment": [list(item) for item in self.fixed_environment],
            "verification_kind": self.verification_kind,
        }))


class VerificationAdapter(Protocol):
    adapter_id: str
    adapter_version: str

    def seal(self, repository: Path, selected_paths: Sequence[str]) -> SealedCommand | None: ...


def _executable(name: str) -> str | None:
    result = shutil.which(name)
    return str(Path(result).resolve()) if result else None


def _safe_test_paths(repository: Path, values: Sequence[str], suffixes: set[str]) -> tuple[str, ...]:
    selected: list[str] = []
    for raw in values:
        path = Path(raw.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise VerificationError("verification path escapes the repository")
        candidate = (repository / path).resolve(strict=False)
        if not is_within(candidate, repository):
            raise VerificationError("verification path escapes through a filesystem alias")
        if candidate.is_symlink() or (candidate.exists() and candidate.suffix.casefold() in suffixes):
            if candidate.is_symlink():
                raise VerificationError("verification rejects symlink test paths")
            selected.append(candidate.relative_to(repository).as_posix())
    return tuple(sorted(set(selected)))


class PythonUnittestAdapter:
    adapter_id = "python-unittest"
    adapter_version = "1"

    def seal(self, repository: Path, selected_paths: Sequence[str]) -> SealedCommand | None:
        python = str(Path(sys.executable).resolve())
        candidates = tuple(
            path.relative_to(repository).as_posix()
            for path in sorted(repository.rglob("test_*.py"))
            if path.is_file() and ".git" not in path.parts
        )
        selected = _safe_test_paths(repository, selected_paths or candidates, {".py"})
        selected = tuple(path for path in selected if Path(path).name.startswith("test_"))
        if not selected:
            return None
        argv = (python, "-m", "unittest", *selected, "-v")
        return SealedCommand(self.adapter_id, argv, (python, "--version"), selected,
                             (("PYTHONPATH", "src"), ("PYTHONDONTWRITEBYTECODE", "1")))


class NodeTypescriptAdapter:
    adapter_id = "node-typescript"
    adapter_version = "1"

    def seal(self, repository: Path, selected_paths: Sequence[str]) -> SealedCommand | None:
        node = _executable("node")
        if node is None:
            return None
        suffixes = {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"}
        candidates = tuple(path.relative_to(repository).as_posix() for path in sorted(repository.rglob("*"))
                           if path.is_file() and path.suffix.casefold() in suffixes and
                           (path.name.startswith("test") or ".test." in path.name or path.parent.name in {"test", "tests"}))
        selected = _safe_test_paths(repository, selected_paths or candidates, suffixes)
        selected = tuple(path for path in selected if Path(path).suffix.casefold() in suffixes)
        if not selected:
            return None
        return SealedCommand(self.adapter_id, (node, "--test", *selected), (node, "--version"), selected)


class GoTestAdapter:
    adapter_id = "go-test"
    adapter_version = "1"

    def seal(self, repository: Path, selected_paths: Sequence[str]) -> SealedCommand | None:
        go = _executable("go")
        if go is None or not (repository / "go.mod").is_file():
            return None
        selected = _safe_test_paths(repository, selected_paths, {".go"}) if selected_paths else ()
        return SealedCommand(self.adapter_id, (go, "test", "./..."), (go, "version"), selected or ("./...",),
                             (("GOTOOLCHAIN", "local"),))


class RustCompileAdapter:
    adapter_id = "rustc-check"
    adapter_version = "1"

    def seal(self, repository: Path, selected_paths: Sequence[str]) -> SealedCommand | None:
        rustc = _executable("rustc")
        source = repository / "src" / "lib.rs"
        if rustc is None or not source.is_file():
            return None
        selected = _safe_test_paths(repository, selected_paths or ("src/lib.rs",), {".rs"})
        return SealedCommand(
            self.adapter_id,
            (rustc, "--crate-name", "hive_target", "--crate-type", "lib", "--edition", "2021",
             "--cfg", "test", "--emit", "metadata", "src/lib.rs"),
            (rustc, "--version"), selected, verification_kind="compile-check",
        )


class VerificationRegistry:
    def __init__(self, adapters: Sequence[VerificationAdapter] | None = None) -> None:
        self.adapters = tuple(adapters or (
            PythonUnittestAdapter(), NodeTypescriptAdapter(), RustCompileAdapter(), GoTestAdapter()
        ))
        identities = [adapter.adapter_id for adapter in self.adapters]
        if len(set(identities)) != len(identities):
            raise VerificationError("verification adapter ids must be unique")

    def seal(self, repository: Path, selected_paths: Sequence[str] = (), adapter_id: str | None = None) -> SealedCommand | None:
        matches = [adapter for adapter in self.adapters if adapter_id is None or adapter.adapter_id == adapter_id]
        if adapter_id is not None and not matches:
            raise VerificationError("requested verification adapter is not allowlisted")
        for adapter in matches:
            command = adapter.seal(repository, selected_paths)
            if command is not None:
                return command
        return None


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink())


def verify_repository(
    repository: str | Path, *, evidence_directory: str | Path,
    selected_paths: Sequence[str] = (), adapter_id: str | None = None,
    sandbox: SandboxAdapter | None = None, requirements: SandboxRequirements | None = None,
    budget: VerificationBudget | None = None,
) -> dict[str, Any]:
    root = Path(repository).resolve()
    if not root.is_dir() or root.is_symlink():
        raise VerificationError("verification requires a real repository directory")
    evidence = require_external_path(evidence_directory, root, label="verification evidence")
    boundary = sandbox or UnavailableSandbox()
    required = requirements or SandboxRequirements()
    limits = budget or VerificationBudget()
    capabilities = boundary.capabilities

    def retain_status(document: dict[str, Any]) -> dict[str, Any]:
        evidence.mkdir(parents=True, exist_ok=False)
        retained = dict(document)
        retained["receipt_digest"] = raw_sha256(canonical_json_bytes(retained))
        (evidence / "receipt.json").write_bytes(canonical_json_bytes(retained) + b"\n")
        return retained

    issues = []
    if not capabilities.available:
        issues.append("sandbox adapter unavailable")
    if required.hostile_code_isolation and not capabilities.hostile_code_isolation:
        issues.append("hostile-code isolation unavailable")
    if required.network_policy == "deny" and not capabilities.network_deny:
        issues.append("network-deny enforcement unavailable")
    if required.hostile_code_isolation and not capabilities.cpu_memory_limits:
        issues.append("CPU/memory enforcement unavailable")
    if issues:
        return retain_status({
            "schema_version": 1, "status": "BLOCKED", "reason": "; ".join(issues),
            "sandbox": capabilities.document(), "source_repository": str(root),
            "verification_obligation": "Configure an adapter that satisfies the sealed sandbox requirements.",
        })
    command = VerificationRegistry().seal(root, selected_paths, adapter_id)
    if command is None:
        return retain_status({
            "schema_version": 1, "status": "VERIFICATION_OBLIGATION",
            "reason": "no compatible allowlisted verification adapter",
            "sandbox": capabilities.document(), "adapter_id": adapter_id,
            "source_repository": str(root),
        })
    unsafe_links = [path for path in root.rglob("*") if path.is_symlink()]
    if unsafe_links:
        raise VerificationError("verification rejects repository symlinks before execution")
    evidence.mkdir(parents=True, exist_ok=False)
    workspace = evidence / "workspace"
    shutil.copytree(root, workspace, ignore=shutil.ignore_patterns(".git", ".hg", ".svn"))
    environment: dict[str, str] = {}
    if os.name == "nt" and os.environ.get("SystemRoot"):
        environment["SystemRoot"] = os.environ["SystemRoot"]
    if os.environ.get("PATH"):
        # Executables remain adapter-selected and absolute. PATH is retained only
        # for compiler/linker subprocesses and is content-digested in the receipt.
        environment["PATH"] = os.environ["PATH"]
    environment.update(dict(command.fixed_environment))
    before_size = _tree_size(workspace)
    started = time.monotonic()
    version_stdout_path, version_stderr_path = evidence / "version.stdout.bin", evidence / "version.stderr.bin"
    version_exit, version_timed_out = boundary.run(
        command.version_argv, workspace=workspace, environment=environment,
        timeout=min(30.0, limits.wall_seconds), stdout_path=version_stdout_path,
        stderr_path=version_stderr_path, budget=limits,
    )
    version_stdout, version_stderr = version_stdout_path.read_bytes(), version_stderr_path.read_bytes()
    if version_exit != 0 or version_timed_out:
        raise VerificationError("verification adapter version probe failed")
    stdout_path, stderr_path = evidence / "stdout.bin", evidence / "stderr.bin"
    remaining = limits.wall_seconds - (time.monotonic() - started)
    if remaining <= 0:
        raise VerificationError("verification budget expired during version probe")
    exit_code, timed_out = boundary.run(command.argv, workspace=workspace, environment=environment,
                                        timeout=remaining, stdout_path=stdout_path,
                                        stderr_path=stderr_path, budget=limits)
    duration_ms = int((time.monotonic() - started) * 1000)
    after_size = _tree_size(workspace)
    stdout, stderr = stdout_path.read_bytes(), stderr_path.read_bytes()
    if len(stdout) > limits.max_output_bytes or len(stderr) > limits.max_output_bytes:
        raise VerificationError("verification output exceeded its sealed budget")
    disk_delta = max(0, after_size - before_size)
    status = "PASSED" if exit_code == 0 and not timed_out and disk_delta <= limits.disk_bytes else "FAILED"
    receipt: dict[str, Any] = {
        "schema_version": 1, "status": status, "adapter_id": command.adapter_id,
        "adapter_version": next(a.adapter_version for a in VerificationRegistry().adapters if a.adapter_id == command.adapter_id),
        "sealed_command_digest": command.digest, "argv": list(command.argv),
        "selected_tests": list(command.selected_tests), "environment": sorted(environment),
        "verification_kind": command.verification_kind,
        "tests_executed": command.verification_kind == "test-execution",
        "environment_digest": raw_sha256(canonical_json_bytes(environment)),
        "tool_version_command": list(command.version_argv),
        "tool_version": {
            "stdout_digest": f"sha256:{hashlib.sha256(version_stdout).hexdigest()}",
            "stderr_digest": f"sha256:{hashlib.sha256(version_stderr).hexdigest()}",
            "text": (version_stdout + version_stderr).decode("utf-8", "replace").strip(),
        },
        "runtime": capabilities.document(), "budget": {
            "wall_seconds": limits.wall_seconds, "cpu_seconds": limits.cpu_seconds,
            "memory_bytes": limits.memory_bytes, "disk_bytes": limits.disk_bytes,
            "max_output_bytes": limits.max_output_bytes,
        },
        "duration_ms": duration_ms, "exit_code": exit_code, "timed_out": timed_out,
        "source_repository": str(root), "execution_workspace": str(workspace),
        "disk_delta_bytes": disk_delta,
        "stdout": {"path": str(stdout_path), "bytes": len(stdout), "digest": f"sha256:{hashlib.sha256(stdout).hexdigest()}"},
        "stderr": {"path": str(stderr_path), "bytes": len(stderr), "digest": f"sha256:{hashlib.sha256(stderr).hexdigest()}"},
    }
    receipt["receipt_digest"] = raw_sha256(canonical_json_bytes(receipt))
    (evidence / "receipt.json").write_bytes(canonical_json_bytes(receipt) + b"\n")
    return receipt


__all__ = [
    "GoTestAdapter", "LocalProcessSandbox", "NodeTypescriptAdapter", "PythonUnittestAdapter", "RustCompileAdapter",
    "SandboxCapabilities", "SandboxRequirements", "SealedCommand", "UnavailableSandbox",
    "VerificationBudget", "VerificationError", "VerificationRegistry", "verify_repository",
]
