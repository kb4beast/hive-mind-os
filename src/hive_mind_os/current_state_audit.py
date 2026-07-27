from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import tempfile
import threading
import types
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .receipts import portable_path_parts

AUDITED_BASELINE: Mapping[str, object] = {
    "repository_sha": "d7a738a7287cbc487edc35b7ae6aa4a339104f71",
    "full_ref_commit_count": 77,
    "earliest_commit": "069ef07807a6be156533a4344355fda3ad31589a",
    "tracked_file_count": 47,
    "source_count": 22,
    "claim_count": 80,
    "source_status_counts": {"verified": 15, "partial": 5, "pending_ingestion": 2},
    "claim_state_counts": {"implemented": 19, "planned": 58, "inventoried": 3},
    "disposition_counts": {"adopt": 25, "adapt": 52, "defer": 3},
    "test_passed_count": 56,
}
COMMAND_TIMEOUT_SECONDS = 300
MAX_COMMAND_OUTPUT_BYTES = 1_000_000
OUTPUT_DRAIN_TIMEOUT_SECONDS = 1.0
MAX_ARTIFACT_NESTING_DEPTH = 128
_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GIT_OBJECT_PATTERN = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
_CREATE_SUSPENDED = 0x00000004
_SOURCE_EVIDENCE_BLOCKERS = frozenset(
    {
        "source provenance is incomplete",
        "source requires complete ingestion before derived ideas may be promoted",
        "repository source lacks an exact commit object pin",
        "repository source pin is mutable or ambiguous",
        "source content digest is not a raw-byte SHA-256 receipt",
        "source license or reuse grant is unresolved",
    }
)
_INVENTORY_FAILURES = frozenset(
    {
        "source has no captured claim",
        "claim has no courtroom decision",
        "claim references an unknown source",
        "decision references an unknown claim",
    }
)
_MATURITY_SCALE = (
    "specified",
    "structurally_prototyped",
    "executed_in_isolation",
    "independently_verified_e2e",
    "production_proven",
)


@dataclass(frozen=True, slots=True)
class CommandObservation:
    command: tuple[str, ...]
    cwd: str
    return_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    output_truncated: bool = False
    drain_incomplete: bool = False

    @property
    def succeeded(self) -> bool:
        return (
            self.return_code == 0
            and not self.timed_out
            and not self.output_truncated
            and not self.drain_incomplete
        )


CommandExecutor = Callable[[Sequence[str], Path], CommandObservation]


def _json_escaped_utf8_size(value: str) -> int:
    size = 0
    short_escapes = {'"', "\\", "\b", "\f", "\n", "\r", "\t"}
    for character in value:
        if character in short_escapes:
            size += 2
        elif ord(character) < 0x20:
            size += 6
        else:
            size += len(character.encode("utf-8"))
    return size


def _retain_json_escaped_utf8(value: str, remaining: int) -> tuple[str, bool]:
    retained: list[str] = []
    used = 0
    for character in value:
        character_size = _json_escaped_utf8_size(character)
        if used + character_size > remaining:
            return "".join(retained), True
        retained.append(character)
        used += character_size
    return value, False


def _contains_invalid_unicode_scalar(
    value: object,
) -> bool:
    pending = [value]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                return True
            continue
        if isinstance(current, Mapping):
            if id(current) in seen:
                continue
            seen.add(id(current))
            for key, item in current.items():
                pending.extend((key, item))
            continue
        if isinstance(current, (list, tuple)):
            if id(current) in seen:
                continue
            seen.add(id(current))
            pending.extend(current)
    return False


def _exceeds_artifact_nesting_depth(value: object) -> bool:
    pending = [(value, 0)]
    greatest_depth: dict[int, int] = {}
    while pending:
        current, depth = pending.pop()
        if not isinstance(current, (Mapping, list, tuple)):
            continue
        if depth > MAX_ARTIFACT_NESTING_DEPTH:
            return True
        previous_depth = greatest_depth.get(id(current), -1)
        if depth <= previous_depth:
            continue
        greatest_depth[id(current)] = depth
        if isinstance(current, Mapping):
            for key, item in current.items():
                pending.extend(((key, depth + 1), (item, depth + 1)))
        else:
            pending.extend((item, depth + 1) for item in current)
    return False


class _WindowsJob:
    """Owns a kill-on-close Windows process tree independently of its leader."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self._ctypes = ctypes
        self._wintypes = wintypes
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._ntdll = ctypes.WinDLL("ntdll")
        self._kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel32.AssignProcessToJobObject.argtypes = (
            wintypes.HANDLE,
            wintypes.HANDLE,
        )
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
        self._kernel32.TerminateJobObject.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        self._kernel32.CloseHandle.restype = wintypes.BOOL
        self._ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
        self._ntdll.NtResumeProcess.restype = ctypes.c_long

        self.handle = self._kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW failed")
        limits = ExtendedLimitInformation()
        limits.BasicLimitInformation.LimitFlags = 0x00002000
        if not self._kernel32.SetInformationJobObject(
            self.handle,
            9,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, "SetInformationJobObject failed")

    def assign_and_resume(self, process: subprocess.Popen[Any]) -> None:
        process_handle = int(process._handle)  # type: ignore[attr-defined]
        if not self._kernel32.AssignProcessToJobObject(self.handle, process_handle):
            raise OSError(
                self._ctypes.get_last_error(),
                "AssignProcessToJobObject failed",
            )
        status = self._ntdll.NtResumeProcess(process_handle)
        if status != 0:
            raise OSError(status, "NtResumeProcess failed")

    def terminate(self) -> None:
        if self.handle:
            self._kernel32.TerminateJobObject(self.handle, 1)

    def close(self) -> None:
        if self.handle:
            self._kernel32.CloseHandle(self.handle)
            self.handle = None


def execute_command(command: Sequence[str], cwd: Path) -> CommandObservation:
    timed_out = False
    output_truncated = False
    drain_incomplete = False
    windows_job = _WindowsJob() if os.name == "nt" else None
    popen_options: dict[str, Any]
    if os.name == "nt":
        popen_options = {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED
        }
    else:
        popen_options = {"start_new_session": True}
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_options,
        )
    except Exception:
        if windows_job is not None:
            windows_job.close()
        raise
    if windows_job is not None:
        try:
            windows_job.assign_and_resume(process)
        except Exception:
            process.kill()
            windows_job.close()
            raise
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    output_lock = threading.Lock()
    termination_lock = threading.Lock()
    retained_output_bytes = 0
    termination_started = False

    def terminate_process_tree() -> None:
        nonlocal termination_started
        with termination_lock:
            if termination_started:
                return
            termination_started = True
        if windows_job is not None:
            windows_job.terminate()
        else:
            try:
                kill_process_group = getattr(os, "killpg")
                kill_signal = getattr(signal, "SIGKILL")
                kill_process_group(process.pid, kill_signal)
            except (OSError, ProcessLookupError):
                pass
        try:
            process.kill()
        except OSError:
            pass

    def drain(stream: Any, chunks: list[bytes]) -> None:
        nonlocal output_truncated, retained_output_bytes
        try:
            read_available = getattr(stream, "read1", stream.read)
            while data := read_available(65_536):
                with output_lock:
                    remaining = MAX_COMMAND_OUTPUT_BYTES - retained_output_bytes
                    retained = data[: max(remaining, 0)]
                    if retained:
                        chunks.append(retained)
                        retained_output_bytes += len(retained)
                    exceeded = len(data) > max(remaining, 0)
                    if exceeded:
                        output_truncated = True
                if exceeded:
                    terminate_process_tree()
                    break
        except (OSError, ValueError):
            if not termination_started:
                with output_lock:
                    output_truncated = True

    stdout_thread = threading.Thread(
        target=drain,
        args=(process.stdout, stdout_chunks),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=drain,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    try:
        return_code = process.wait(timeout=COMMAND_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_tree()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        return_code = 124
    if windows_job is not None:
        windows_job.close()
    else:
        try:
            kill_process_group = getattr(os, "killpg")
            kill_signal = getattr(signal, "SIGKILL")
            kill_process_group(process.pid, kill_signal)
        except (OSError, ProcessLookupError):
            pass
    stdout_thread.join(OUTPUT_DRAIN_TIMEOUT_SECONDS)
    stderr_thread.join(OUTPUT_DRAIN_TIMEOUT_SECONDS)
    if stdout_thread.is_alive() or stderr_thread.is_alive():
        drain_incomplete = True
        stdout_thread.join(OUTPUT_DRAIN_TIMEOUT_SECONDS)
        stderr_thread.join(OUTPUT_DRAIN_TIMEOUT_SECONDS)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()
    stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")

    stdout, stdout_truncated = _retain_json_escaped_utf8(
        stdout,
        MAX_COMMAND_OUTPUT_BYTES,
    )
    remaining_serialized_bytes = (
        MAX_COMMAND_OUTPUT_BYTES - _json_escaped_utf8_size(stdout)
    )
    stderr, stderr_truncated = _retain_json_escaped_utf8(
        stderr,
        remaining_serialized_bytes,
    )
    output_truncated = output_truncated or stdout_truncated or stderr_truncated
    return CommandObservation(
        command=tuple(command),
        cwd=str(cwd),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        output_truncated=output_truncated,
        drain_incomplete=drain_incomplete,
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _split_nul(value: str) -> list[str]:
    return [item for raw_item in value.split("\0") if (item := raw_item.strip("\r\n"))]


def _counter(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _local_reference(reference: str) -> str:
    return reference.split("#", 1)[0]


def _load_repository_docket(repository: Path) -> Any:
    package_path = repository / "src" / "hive_mind_os"
    if not (package_path / "source_docket.py").is_file():
        raise FileNotFoundError(f"source docket module not found under {repository}")

    package_suffix = hashlib.sha256(str(repository).encode("utf-8")).hexdigest()[:16]
    package_name = f"_hive_mind_audit_target_{package_suffix}"
    package = types.ModuleType(package_name)
    package.__path__ = [str(package_path)]
    package.__package__ = package_name
    sys.modules[package_name] = package
    try:
        source_docket = importlib.import_module(f"{package_name}.source_docket")
        return source_docket.load_source_docket()
    finally:
        for module_name in tuple(sys.modules):
            if module_name == package_name or module_name.startswith(f"{package_name}."):
                del sys.modules[module_name]


def _resolve_reference(
    repository: Path,
    reference: str,
) -> tuple[Path | None, str | None]:
    local_path = _local_reference(reference)
    if not local_path or "://" in local_path:
        return None, "reference is not a repository-local path"
    try:
        raw_parts = portable_path_parts(local_path)
    except ValueError as error:
        return None, str(error)
    candidate = Path(*raw_parts)
    resolved = (repository / candidate).resolve()
    try:
        resolved.relative_to(repository.resolve())
    except ValueError:
        return None, "referenced path escapes the repository"
    if not resolved.is_file():
        return None, "referenced file does not exist"
    return resolved, None


def _broken_references(docket: Any, repository: Path) -> list[dict[str, str]]:
    broken: list[dict[str, str]] = []
    reference_groups = (
        ("architecture", "architecture_refs"),
        ("code", "code_refs"),
        ("test", "test_refs"),
        ("benchmark", "benchmark_refs"),
    )
    for claim in docket.claims:
        for kind, attribute in reference_groups:
            for reference in getattr(claim, attribute):
                _, reason = _resolve_reference(repository, reference)
                if reason:
                    broken.append(
                        {
                            "claim_id": claim.id,
                            "kind": kind,
                            "reference": reference,
                            "reason": reason,
                        }
                    )
    return sorted(broken, key=lambda item: (item["claim_id"], item["kind"], item["reference"]))


def _trusted_pytest_command(command: Sequence[str], expected: Sequence[str]) -> bool:
    if tuple(command) != tuple(expected):
        return False
    if len(command) < 4:
        return False
    try:
        executable_matches = Path(command[0]).resolve() == Path(sys.executable).resolve()
    except OSError:
        return False
    return executable_matches and tuple(command[1:4]) == ("-m", "pytest", "-q")


def _parse_test_result(
    observation: CommandObservation | None,
    *,
    expected_command: Sequence[str] | None = None,
) -> dict[str, object]:
    if observation is None:
        return {
            "status": "not_run",
            "passed": None,
            "failed": None,
            "errors": None,
            "command_observation_index": None,
        }
    expected = tuple(expected_command or (sys.executable, "-m", "pytest", "-q"))
    if not _trusted_pytest_command(observation.command, expected):
        return {
            "status": "unverified",
            "passed": None,
            "failed": None,
            "errors": None,
            "command_observation_index": None,
            "reason": "test command is not the expected Python pytest runner",
        }
    combined = f"{observation.stdout}\n{observation.stderr}"
    counts = {
        name: int(match.group(1)) if (match := re.search(rf"(\d+)\s+{name}", combined)) else 0
        for name in ("passed", "failed", "error")
    }
    passing_result = (
        counts["passed"] > 0
        and counts["failed"] == 0
        and counts["error"] == 0
    )
    return {
        "status": "passed" if observation.succeeded and passing_result else "failed",
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["error"],
    }


def _reference_receipts(
    docket: Any,
    repository: Path,
    *,
    run_tests: bool,
    observe: Callable[..., CommandObservation],
    observations: list[CommandObservation],
    failures: list[dict[str, object]],
) -> tuple[list[dict[str, object]], bool]:
    reference_groups = (
        ("architecture", "architecture_refs"),
        ("code", "code_refs"),
        ("test", "test_refs"),
        ("benchmark", "benchmark_refs"),
    )
    resolved: dict[tuple[str, str], dict[str, object]] = {}
    for kind, attribute in reference_groups:
        references = sorted({ref for claim in docket.claims for ref in getattr(claim, attribute)})
        for reference in references:
            path, reason = _resolve_reference(repository, reference)
            entry: dict[str, object] = {
                "kind": kind,
                "reference": reference,
                "path_valid": path is not None,
                "digest": _sha256(path.read_bytes()) if path is not None else None,
                "execution": {"status": "not_applicable"},
                "valid": path is not None,
                "issues": [reason] if reason else [],
            }
            if kind == "test":
                entry_issues = entry["issues"]
                if not isinstance(entry_issues, list):
                    raise TypeError("reference receipt issues must be a list")
                if not run_tests:
                    entry["execution"] = {"status": "not_run"}
                    entry["valid"] = False
                    entry_issues.append("test receipt was not executed")
                elif path is not None:
                    local_path = path.relative_to(repository).as_posix()
                    command = (sys.executable, "-m", "pytest", "-q", "--", local_path)
                    observation = observe(command, required=False)
                    result = _parse_test_result(observation, expected_command=command)
                    result["command_observation_index"] = len(observations) - 1
                    entry["execution"] = result
                    entry["valid"] = result["status"] == "passed"
                    if not entry["valid"]:
                        entry_issues.append("test receipt execution did not pass")
                        failures.append(
                            {
                                "kind": "test_receipt_failure",
                                "reference": reference,
                                "command": list(command),
                                "return_code": observation.return_code,
                                "stderr": observation.stderr.strip(),
                            }
                        )
            resolved[(kind, reference)] = entry

    receipts: list[dict[str, object]] = []
    for claim in docket.claims:
        for kind, attribute in reference_groups:
            for reference in getattr(claim, attribute):
                receipt = dict(resolved[(kind, reference)])
                receipt["claim_id"] = claim.id
                receipts.append(receipt)
    receipts.sort(key=lambda item: (str(item["claim_id"]), str(item["kind"]), str(item["reference"])))
    return receipts, all(bool(item["valid"]) for item in receipts)


def _baseline_discrepancies(current: Mapping[str, object]) -> list[dict[str, object]]:
    discrepancies: list[dict[str, object]] = []
    for field, expected in AUDITED_BASELINE.items():
        observed = current.get(field)
        if observed != expected:
            discrepancies.append(
                {
                    "case_id": f"BASELINE-{field.upper().replace('_', '-')}",
                    "field": field,
                    "audited_value": expected,
                    "observed_value": observed,
                    "status": "open",
                }
            )
    return discrepancies


def collect_current_state_audit(
    repository: str | Path,
    *,
    run_tests: bool = True,
    test_command: Sequence[str] | None = None,
    generated_at: datetime | None = None,
    invocation: Sequence[str] = (),
    executor: CommandExecutor = execute_command,
) -> dict[str, object]:
    requested_repository = Path(repository).resolve()
    observations: list[CommandObservation] = []
    failures: list[dict[str, object]] = []

    def observe(command: Sequence[str], *, required: bool = True) -> CommandObservation:
        result = executor(command, requested_repository)
        observations.append(result)
        if required and not result.succeeded:
            failures.append(
                {
                    "command": list(command),
                    "return_code": result.return_code,
                    "stderr": result.stderr.strip(),
                }
            )
        return result

    root_result = observe(("git", "rev-parse", "--show-toplevel"))
    repository_root = (
        Path(root_result.stdout.strip()).resolve()
        if root_result.succeeded and root_result.stdout.strip()
        else requested_repository
    )
    if repository_root != requested_repository:
        requested_repository = repository_root

    head = observe(("git", "rev-parse", "HEAD"))
    commit_count = observe(("git", "rev-list", "--all", "--count"))
    commits = observe(("git", "rev-list", "--all", "--reverse"))
    tracked = observe(("git", "ls-files", "-z"))
    tracked_index = observe(("git", "ls-files", "-s", "-z"))
    status = observe(("git", "status", "--porcelain=v1", "--untracked-files=all", "-z"))
    ignored = observe(("git", "status", "--ignored", "--porcelain=v1", "-z"))
    refs = observe(
        (
            "git",
            "for-each-ref",
            "--sort=refname",
            "--format=%(refname)%09%(objectname)",
        )
    )
    historical_paths = observe(("git", "log", "--all", "--format=", "--name-only", "-z"))
    deleted_paths = observe(
        ("git", "log", "--all", "--diff-filter=D", "--format=", "--name-only", "-z")
    )
    renamed_paths = observe(
        ("git", "log", "--all", "--diff-filter=R", "--format=", "--name-only", "-z")
    )
    git_version = observe(("git", "--version"))
    working_tree_entries = _split_nul(status.stdout)
    if working_tree_entries:
        failures.append(
            {
                "kind": "dirty_worktree",
                "message": "test results cannot be bound to HEAD while tracked or untracked inputs differ",
                "entries": working_tree_entries,
            }
        )

    try:
        docket = _load_repository_docket(requested_repository)
    except Exception as error:
        failures.append(
            {
                "kind": "docket_load_failure",
                "error_type": type(error).__name__,
                "message": str(error),
            }
        )
        docket = None
    if docket is not None:
        docket_audit = docket.audit()
        source_status_counts = _counter([source.status.value for source in docket.sources])
        claim_state_counts = _counter([claim.implementation_state.value for claim in docket.claims])
        capability_maturity_counts = _counter(
            [claim.capability_maturity.value for claim in docket.claims]
        )
        disposition_counts = _counter([decision.disposition.value for decision in docket.decisions])
        source_blockers = sorted(
            {
                issue.source_id
                for issue in docket_audit.issues
                if issue.source_id
                and "," not in issue.source_id
                and issue.message
                in _SOURCE_EVIDENCE_BLOCKERS
            }
        )
        docket_issues = [
            {
                "severity": issue.severity.value,
                "message": issue.message,
                "source_id": issue.source_id,
                "claim_id": issue.claim_id,
            }
            for issue in docket_audit.issues
        ]
        machine_blocked_claim_ids = list(docket_audit.machine_blocked_claim_ids)
        claims_by_source: dict[str, list[str]] = {
            source.id: sorted(
                claim.id for claim in docket.claims if source.id in claim.source_ids
            )
            for source in docket.sources
        }
        source_coverage = [
            {
                "source_id": source.id,
                "status": source.status.value,
                "version_ref": source.version_ref,
                "object_type": source.object_type,
                "retrieved_at": source.retrieved_at,
                "license_spdx": source.license_spdx,
                "content_digest": source.content_digest,
                "unverified_digest_label": source.unverified_digest_label,
                "provenance_complete": source.provenance_complete,
                "requires_complete_ingestion": source.requires_complete_ingestion,
                "snapshot_ref": source.snapshot_ref,
                "claim_ids": claims_by_source[source.id],
                "blocking_issues": sorted(
                    {
                        issue.message
                        for issue in docket_audit.issues
                        if source.id in (issue.source_id or "").split(",")
                    }
                ),
            }
            for source in docket.sources
        ]
        implementation_state_audit = {
            "maturity_scale": list(_MATURITY_SCALE),
            "maturity_counts": capability_maturity_counts,
            "claims_by_maturity": {
                maturity: sorted(
                    claim.id
                    for claim in docket.claims
                    if claim.capability_maturity.value == maturity
                )
                for maturity in _MATURITY_SCALE
            },
            "evidence_classes": {
                "typed_domain_prototype": sorted(
                    claim.id
                    for claim in docket.claims
                    if claim.capability_maturity.value == "structurally_prototyped"
                ),
                "classic_gpt_simulation": [
                    f"CLM-{number:03d}" for number in range(74, 81)
                ],
                "partial_in_process_enforcement": [
                    "CLM-026",
                    "CLM-027",
                    "CLM-074",
                    "CLM-077",
                    "CLM-079",
                ],
                "production_proof": [],
            },
            "scope_warning": (
                "Typed models, simulations, and in-process gates do not prove complete "
                "mediation, durable external enforcement, independent agents, or production operation."
            ),
        }
        broken_references = _broken_references(docket, requested_repository)
        source_count: int | None = docket.source_count
        claim_count: int | None = docket.claim_count
        inventory_complete = docket_audit.inventory_complete
        release_ready = docket_audit.release_ready
    else:
        source_status_counts = {}
        claim_state_counts = {}
        capability_maturity_counts = {}
        disposition_counts = {}
        source_blockers = []
        docket_issues = []
        machine_blocked_claim_ids = []
        source_coverage = []
        implementation_state_audit = {}
        broken_references = []
        source_count = None
        claim_count = None
        inventory_complete = False
        release_ready = False

    test_observation: CommandObservation | None = None
    expected_test_command = tuple(test_command or (sys.executable, "-m", "pytest", "-q"))
    if run_tests:
        test_observation = observe(
            expected_test_command,
            required=False,
        )
        if not test_observation.succeeded:
            failures.append(
                {
                    "command": list(test_observation.command),
                    "return_code": test_observation.return_code,
                    "stderr": test_observation.stderr.strip(),
                    "kind": "test_failure",
                }
            )
    test_result = _parse_test_result(
        test_observation,
        expected_command=(sys.executable, "-m", "pytest", "-q"),
    )
    if run_tests and test_result["status"] == "unverified":
        failures.append(
            {
                "kind": "unverified_test_command",
                "command": list(expected_test_command),
                "message": test_result["reason"],
            }
        )
    elif run_tests and test_result["status"] != "passed" and test_observation is not None:
        failures.append(
            {
                "kind": "unrecognized_test_result",
                "command": list(expected_test_command),
                "return_code": test_observation.return_code,
                "message": "pytest did not emit a recognized successful result",
            }
        )

    if docket is not None:
        reference_receipts, receipts_valid = _reference_receipts(
            docket,
            requested_repository,
            run_tests=run_tests,
            observe=observe,
            observations=observations,
            failures=failures,
        )
    else:
        reference_receipts = []
        receipts_valid = False

    post_test_head = observe(("git", "rev-parse", "HEAD"))
    post_test_status = observe(
        ("git", "status", "--porcelain=v1", "--untracked-files=all", "-z")
    )
    immediate_post_test_entries = _split_nul(post_test_status.stdout)

    post_reference_failures: set[tuple[str, str]] = set()
    for receipt in reference_receipts:
        reference = str(receipt["reference"])
        path, reason = _resolve_reference(requested_repository, reference)
        observed_digest = _sha256(path.read_bytes()) if path is not None else None
        if reason or observed_digest != receipt["digest"]:
            receipt["valid"] = False
            issue = reason or "referenced bytes changed during audit"
            issues = receipt.get("issues")
            if isinstance(issues, list) and issue not in issues:
                issues.append(issue)
            post_reference_failures.add((str(receipt["kind"]), reference))
    for kind, reference in sorted(post_reference_failures):
        failures.append(
            {
                "kind": "reference_changed_during_audit",
                "reference_kind": kind,
                "reference": reference,
            }
        )
    receipts_valid = bool(reference_receipts) and all(
        bool(receipt["valid"]) for receipt in reference_receipts
    )
    final_head = observe(("git", "rev-parse", "HEAD"))
    final_status = observe(
        ("git", "status", "--porcelain=v1", "--untracked-files=all", "-z")
    )
    final_entries = _split_nul(final_status.stdout)
    if post_test_head.stdout.strip() != head.stdout.strip() or final_head.stdout.strip() != head.stdout.strip():
        failures.append(
            {
                "kind": "head_changed_during_audit",
                "before": head.stdout.strip(),
                "after_tests": post_test_head.stdout.strip(),
                "after_receipt_validation": final_head.stdout.strip(),
            }
        )
    if (
        immediate_post_test_entries != working_tree_entries
        or final_entries != working_tree_entries
    ):
        failures.append(
            {
                "kind": "worktree_changed_during_audit",
                "message": "test or receipt validation changed repository status entries",
                "before": working_tree_entries,
                "after_tests": immediate_post_test_entries,
                "after_receipt_validation": final_entries,
            }
        )

    ref_rows = []
    for line in refs.stdout.splitlines():
        if not line:
            continue
        ref, _, object_id = line.partition("\t")
        ref_rows.append({"ref": ref, "object_id": object_id})

    current_counts: dict[str, object] = {
        "repository_sha": head.stdout.strip() or None,
        "full_ref_commit_count": int(commit_count.stdout.strip()) if commit_count.stdout.strip().isdigit() else None,
        "earliest_commit": next(iter(commits.stdout.splitlines()), None),
        "tracked_file_count": len(_split_nul(tracked.stdout)),
        "source_count": source_count,
        "claim_count": claim_count,
        "source_status_counts": source_status_counts,
        "claim_state_counts": claim_state_counts,
        "capability_maturity_counts": capability_maturity_counts,
        "disposition_counts": disposition_counts,
        "test_passed_count": test_result["passed"],
    }

    timestamp = (generated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    audit: dict[str, object] = {
        "schema_version": 5,
        "artifact_type": "CurrentStateAudit",
        "generated_at": timestamp,
        "invocation": list(invocation),
        "repository": {
            "root": str(requested_repository),
            "head": current_counts["repository_sha"],
            "working_tree_clean": not bool(working_tree_entries),
            "working_tree_entries": working_tree_entries,
            "post_test_head": post_test_head.stdout.strip() or None,
            "post_test_working_tree_clean": not bool(immediate_post_test_entries),
            "post_test_working_tree_entries": immediate_post_test_entries,
            "final_head": final_head.stdout.strip() or None,
            "final_working_tree_clean": not bool(final_entries),
            "final_working_tree_entries": final_entries,
            "tracked_file_count": current_counts["tracked_file_count"],
            "tracked_tree_digest": _sha256(tracked_index.stdout.encode("utf-8")),
            "full_ref_commit_count": current_counts["full_ref_commit_count"],
            "earliest_commit": current_counts["earliest_commit"],
            "refs": ref_rows,
            "historical_path_count": len(set(_split_nul(historical_paths.stdout))),
            "historical_path_inventory_digest": _sha256(historical_paths.stdout.encode("utf-8")),
            "deleted_paths": sorted(set(_split_nul(deleted_paths.stdout))),
            "renamed_paths": sorted(set(_split_nul(renamed_paths.stdout))),
            "ignored_entries": [
                item for item in _split_nul(ignored.stdout) if item.startswith("!! ")
            ],
        },
        "docket": {
            "source_count": source_count,
            "claim_count": claim_count,
            "source_status_counts": source_status_counts,
            "claim_state_counts": claim_state_counts,
            "capability_maturity_counts": capability_maturity_counts,
            "disposition_counts": disposition_counts,
            "inventory_complete": inventory_complete,
            "release_ready": release_ready,
            "source_blockers": source_blockers,
            "issues": docket_issues,
            "machine_blocked_claim_ids": machine_blocked_claim_ids,
            "source_coverage": source_coverage,
            "implementation_state_audit": implementation_state_audit,
            "broken_references": broken_references,
            "reference_receipts": reference_receipts,
            "receipts_valid": receipts_valid,
        },
        "tests": test_result,
        "tools": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "git": git_version.stdout.strip(),
        },
        "baseline": {
            "audited_values": dict(AUDITED_BASELINE),
            "discrepancy_cases": _baseline_discrepancies(current_counts),
        },
        "commands": [asdict(observation) for observation in observations],
        "failures": failures,
        "complete": (
            run_tests
            and test_result["status"] == "passed"
            and receipts_valid
            and not failures
        ),
    }
    return audit


def create_audit_artifact(
    audit: Mapping[str, object],
    *,
    signing_key: bytes | None = None,
    signing_key_id: str | None = None,
) -> dict[str, object]:
    payload = dict(audit)
    digest = _sha256(_canonical_bytes(payload))
    signature: dict[str, str] | None = None
    if signing_key is not None:
        if not signing_key:
            raise ValueError("signing key must not be empty")
        if not signing_key_id or not signing_key_id.strip():
            raise ValueError("signing_key_id is required when signing")
        signature = {
            "algorithm": "hmac-sha256",
            "key_id": signing_key_id,
            "value": hmac.new(signing_key, digest.encode("ascii"), hashlib.sha256).hexdigest(),
        }
    return {
        "audit": payload,
        "integrity": {
            "canonicalization": "json-sort-keys-utf8-v1",
            "digest": digest,
            "signature": signature,
        },
    }


def _validate_schema5_docket(
    docket: Mapping[str, object],
    issues: list[str],
) -> None:
    source_count = docket.get("source_count")
    claim_count = docket.get("claim_count")
    coverage = docket.get("source_coverage")
    docket_issues = docket.get("issues")
    if type(source_count) is not int or source_count < 0:
        issues.append("audit source count is invalid")
    if type(claim_count) is not int or claim_count < 0:
        issues.append("audit claim count is invalid")
    if not isinstance(coverage, list):
        issues.append("audit source coverage is invalid")
        return
    if type(source_count) is int and len(coverage) != source_count:
        issues.append("audit source coverage count contradicts source count")

    source_ids: list[str] = []
    coverage_claims: set[str] = set()
    claims_by_source: dict[str, set[str]] = {}
    coverage_blockers: dict[str, set[str]] = {}
    coverage_statuses: list[str] = []
    for index, item in enumerate(coverage):
        if not isinstance(item, Mapping):
            issues.append(f"audit source coverage {index} is not an object")
            continue
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or re.fullmatch(r"SRC-[0-9]{3,}", source_id) is None:
            issues.append(f"audit source coverage {index} has invalid identity")
            continue
        source_ids.append(source_id)
        claim_ids = item.get("claim_ids")
        blocking_issues = item.get("blocking_issues")
        status = item.get("status")
        if not isinstance(claim_ids, list) or any(
            not isinstance(claim_id, str)
            or re.fullmatch(r"CLM-[0-9]{3,}", claim_id) is None
            for claim_id in claim_ids
        ):
            issues.append(f"audit source coverage {source_id} has invalid claims")
            claim_set: set[str] = set()
        else:
            claim_set = set(claim_ids)
            if len(claim_set) != len(claim_ids):
                issues.append(f"audit source coverage {source_id} repeats claims")
        if not isinstance(blocking_issues, list) or any(
            not isinstance(message, str) for message in blocking_issues
        ):
            issues.append(f"audit source coverage {source_id} has invalid blockers")
            blocker_set: set[str] = set()
        else:
            blocker_set = set(blocking_issues)
            if len(blocker_set) != len(blocking_issues):
                issues.append(f"audit source coverage {source_id} repeats blockers")
        if not isinstance(status, str):
            issues.append(f"audit source coverage {source_id} has invalid status")
        else:
            coverage_statuses.append(status)
        claims_by_source[source_id] = claim_set
        coverage_claims.update(claim_set)
        coverage_blockers[source_id] = blocker_set
    if len(source_ids) != len(set(source_ids)):
        issues.append("audit source coverage contains duplicate sources")
    if type(claim_count) is int and len(coverage_claims) != claim_count:
        issues.append("audit source coverage does not conserve the claim inventory")

    if not isinstance(docket_issues, list):
        issues.append("audit docket issues are invalid")
        docket_issues = []
    issue_rows: list[Mapping[str, object]] = []
    for index, item in enumerate(docket_issues):
        if (
            not isinstance(item, Mapping)
            or item.get("severity") not in {"warning", "blocking"}
            or not isinstance(item.get("message"), str)
            or item.get("source_id") is not None
            and not isinstance(item.get("source_id"), str)
            or item.get("claim_id") is not None
            and not isinstance(item.get("claim_id"), str)
        ):
            issues.append(f"audit docket issue {index} is invalid")
            continue
        issue_rows.append(item)

    for source_id in set(source_ids):
        expected_messages = {
            str(item["message"])
            for item in issue_rows
            if source_id in str(item.get("source_id") or "").split(",")
        }
        if coverage_blockers.get(source_id, set()) != expected_messages:
            issues.append(
                f"audit source coverage blockers contradict docket issues: {source_id}"
            )

    expected_source_blockers = sorted(
        {
            source_id
            for source_id, messages in coverage_blockers.items()
            if messages & _SOURCE_EVIDENCE_BLOCKERS
        }
    )
    source_blockers = docket.get("source_blockers")
    if (
        not isinstance(source_blockers, list)
        or any(not isinstance(source_id, str) for source_id in source_blockers)
        or len(source_blockers) != len(set(source_blockers))
        or source_blockers != sorted(source_blockers)
        or source_blockers != expected_source_blockers
    ):
        issues.append("audit source blockers contradict source coverage")

    dependent_issue_claims = {
        str(item["claim_id"])
        for item in issue_rows
        if item.get("message")
        == "dependent claim is machine-blocked by incomplete source evidence"
        and isinstance(item.get("claim_id"), str)
    }
    coverage_derived_claims = {
        claim_id
        for source_id, claim_ids in claims_by_source.items()
        if coverage_blockers.get(source_id, set()) & _SOURCE_EVIDENCE_BLOCKERS
        for claim_id in claim_ids
    }
    machine_blocked = docket.get("machine_blocked_claim_ids")
    if (
        not isinstance(machine_blocked, list)
        or any(not isinstance(claim_id, str) for claim_id in machine_blocked)
        or len(machine_blocked) != len(set(machine_blocked))
        or machine_blocked != sorted(machine_blocked)
        or set(machine_blocked) != dependent_issue_claims
        or set(machine_blocked) != coverage_derived_claims
    ):
        issues.append("audit machine-blocked claims contradict source evidence")

    source_status_counts = docket.get("source_status_counts")
    expected_status_counts = dict(sorted(Counter(coverage_statuses).items()))
    if source_status_counts != expected_status_counts:
        issues.append("audit source-status counts contradict source coverage")

    blocking_present = any(item.get("severity") == "blocking" for item in issue_rows)
    if docket.get("release_ready") is not (not blocking_present):
        issues.append("audit release readiness contradicts blocking docket issues")
    inventory_failures_present = any(
        item.get("message") in _INVENTORY_FAILURES for item in issue_rows
    )
    if docket.get("inventory_complete") is not (not inventory_failures_present):
        issues.append("audit inventory completeness contradicts docket issues")

    implementation = docket.get("implementation_state_audit")
    if not isinstance(implementation, Mapping):
        issues.append("audit implementation-state evidence is invalid")
        return
    if implementation.get("maturity_scale") != list(_MATURITY_SCALE):
        issues.append("audit capability maturity scale is invalid")
    claims_by_maturity = implementation.get("claims_by_maturity")
    maturity_counts = implementation.get("maturity_counts")
    if not isinstance(claims_by_maturity, Mapping) or set(claims_by_maturity) != set(
        _MATURITY_SCALE
    ):
        issues.append("audit claims-by-maturity partition is invalid")
        return
    maturity_claim_sets: dict[str, set[str]] = {}
    for maturity in _MATURITY_SCALE:
        claim_ids = claims_by_maturity.get(maturity)
        if not isinstance(claim_ids, list) or any(
            not isinstance(claim_id, str) for claim_id in claim_ids
        ):
            issues.append(f"audit {maturity} claim set is invalid")
            maturity_claim_sets[maturity] = set()
            continue
        maturity_claim_sets[maturity] = set(claim_ids)
        if len(maturity_claim_sets[maturity]) != len(claim_ids):
            issues.append(f"audit {maturity} claim set contains duplicates")
    maturity_union: set[str] = set()
    maturity_total = 0
    for claim_ids in maturity_claim_sets.values():
        maturity_union.update(claim_ids)
        maturity_total += len(claim_ids)
    if maturity_total != len(maturity_union):
        issues.append("audit maturity claim sets overlap")
    if maturity_union != coverage_claims:
        issues.append("audit maturity claims do not conserve the claim inventory")
    expected_maturity_counts = {
        maturity: len(claim_ids)
        for maturity, claim_ids in maturity_claim_sets.items()
        if claim_ids
    }
    if maturity_counts != expected_maturity_counts:
        issues.append("audit maturity counts contradict maturity claim sets")
    if docket.get("capability_maturity_counts") != expected_maturity_counts:
        issues.append("audit docket maturity counts contradict maturity claim sets")

    evidence_classes = implementation.get("evidence_classes")
    if not isinstance(evidence_classes, Mapping):
        issues.append("audit implementation evidence classes are invalid")
        return
    for evidence_class, claim_ids in evidence_classes.items():
        if not isinstance(evidence_class, str) or not isinstance(claim_ids, list) or any(
            not isinstance(claim_id, str) for claim_id in claim_ids
        ):
            issues.append("audit implementation evidence class is invalid")
            continue
        if not set(claim_ids) <= coverage_claims:
            issues.append(f"audit {evidence_class} cites unknown claims")
    if set(evidence_classes.get("typed_domain_prototype", [])) != maturity_claim_sets[
        "structurally_prototyped"
    ]:
        issues.append("audit prototype evidence contradicts structural maturity")
    if set(evidence_classes.get("production_proof", [])) != maturity_claim_sets[
        "production_proven"
    ]:
        issues.append("audit production proof contradicts production maturity")


def verify_audit_artifact(
    artifact: Mapping[str, object],
    *,
    signing_key: bytes | None = None,
) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(artifact, Mapping):
        return False, ("artifact must be an object",)
    if _contains_invalid_unicode_scalar(artifact):
        return False, ("artifact contains an invalid Unicode scalar value",)
    if _exceeds_artifact_nesting_depth(artifact):
        return False, ("artifact exceeds maximum nesting depth",)
    try:
        _canonical_bytes(artifact)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return False, ("artifact is not canonical JSON",)
    issues: list[str] = []
    audit = artifact.get("audit")
    integrity = artifact.get("integrity")
    if not isinstance(audit, Mapping) or not isinstance(integrity, Mapping):
        return False, ("artifact must contain audit and integrity objects",)

    if type(audit.get("schema_version")) is not int or audit.get("schema_version") != 5:
        issues.append("unsupported CurrentStateAudit schema version")
    if audit.get("artifact_type") != "CurrentStateAudit":
        issues.append("artifact type must be CurrentStateAudit")
    for field_name, expected_type in (
        ("repository", Mapping),
        ("docket", Mapping),
        ("tests", Mapping),
        ("commands", list),
        ("failures", list),
    ):
        if not isinstance(audit.get(field_name), expected_type):
            issues.append(f"audit {field_name} has an invalid shape")
    if not isinstance(audit.get("complete"), bool):
        issues.append("audit complete flag is required")
    else:
        repository = audit.get("repository")
        docket = audit.get("docket")
        tests = audit.get("tests")
        commands = audit.get("commands")
        failures = audit.get("failures")
        if isinstance(repository, Mapping):
            if not isinstance(repository.get("root"), str) or not repository.get("root"):
                issues.append("audit repository root is required")
            head = repository.get("head")
            if not isinstance(head, str) or not _GIT_OBJECT_PATTERN.fullmatch(head):
                issues.append("audit repository head is invalid")
            if not isinstance(repository.get("working_tree_clean"), bool):
                issues.append("audit repository cleanliness is required")
            if not isinstance(repository.get("working_tree_entries"), list):
                issues.append("audit repository entries are invalid")
            elif repository.get("working_tree_clean") is not (
                repository.get("working_tree_entries") == []
            ):
                issues.append("audit repository cleanliness contradicts its entries")
            if repository.get("post_test_head") != head:
                issues.append("audit repository head changed during tests")
            if not isinstance(repository.get("post_test_working_tree_clean"), bool):
                issues.append("audit post-test cleanliness is required")
            if not isinstance(repository.get("post_test_working_tree_entries"), list):
                issues.append("audit post-test repository entries are invalid")
            elif repository.get("post_test_working_tree_clean") is not (
                repository.get("post_test_working_tree_entries") == []
            ):
                issues.append("audit post-test cleanliness contradicts its entries")
            if repository.get("final_head") != head:
                issues.append("audit repository head changed during receipt validation")
            if not isinstance(repository.get("final_working_tree_clean"), bool):
                issues.append("audit final cleanliness is required")
            if not isinstance(repository.get("final_working_tree_entries"), list):
                issues.append("audit final repository entries are invalid")
            elif repository.get("final_working_tree_clean") is not (
                repository.get("final_working_tree_entries") == []
            ):
                issues.append("audit final cleanliness contradicts its entries")
            tracked_tree_digest = repository.get("tracked_tree_digest")
            if not isinstance(tracked_tree_digest, str) or not _SHA256_PATTERN.fullmatch(
                tracked_tree_digest
            ):
                issues.append("audit tracked tree digest is invalid")
        if isinstance(docket, Mapping):
            _validate_schema5_docket(docket, issues)
            if not isinstance(docket.get("broken_references"), list):
                issues.append("audit broken references are invalid")
            if not isinstance(docket.get("reference_receipts"), list):
                issues.append("audit reference receipts are invalid")
            if not isinstance(docket.get("receipts_valid"), bool):
                issues.append("audit receipt-valid flag is required")
            receipts = docket.get("reference_receipts")
            if isinstance(receipts, list):
                if not receipts:
                    issues.append("audit contains no reference receipts")
                for index, receipt in enumerate(receipts):
                    if not isinstance(receipt, Mapping):
                        issues.append(f"audit reference receipt {index} is not an object")
                        continue
                    if not all(
                        isinstance(receipt.get(field), str) and receipt.get(field)
                        for field in ("claim_id", "kind", "reference")
                    ):
                        issues.append(f"audit reference receipt {index} lacks identity")
                    if not isinstance(receipt.get("path_valid"), bool) or not isinstance(
                        receipt.get("valid"), bool
                    ):
                        issues.append(f"audit reference receipt {index} lacks validity")
                    digest = receipt.get("digest")
                    if receipt.get("path_valid") and (
                        not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest)
                    ):
                        issues.append(f"audit reference receipt {index} digest is invalid")
                    if not isinstance(receipt.get("execution"), Mapping):
                        issues.append(f"audit reference receipt {index} execution is invalid")
                    if not isinstance(receipt.get("issues"), list):
                        issues.append(f"audit reference receipt {index} issues are invalid")
                    execution = receipt.get("execution")
                    execution_status = (
                        execution.get("status") if isinstance(execution, Mapping) else None
                    )
                    expected_execution_status = (
                        "passed" if receipt.get("kind") == "test" else "not_applicable"
                    )
                    derived_valid = (
                        receipt.get("path_valid") is True
                        and isinstance(digest, str)
                        and bool(_SHA256_PATTERN.fullmatch(digest))
                        and receipt.get("issues") == []
                        and execution_status == expected_execution_status
                    )
                    if receipt.get("valid") is not derived_valid:
                        issues.append(
                            f"audit reference receipt {index} validity is contradictory"
                        )
                derived_receipts_valid = bool(receipts) and all(
                    isinstance(receipt, Mapping) and receipt.get("valid") is True
                    for receipt in receipts
                )
                if docket.get("receipts_valid") is not derived_receipts_valid:
                    issues.append("audit receipt-valid flag contradicts its receipts")
        if isinstance(tests, Mapping):
            if tests.get("status") not in {"passed", "failed", "not_run", "unverified"}:
                issues.append("audit test status is invalid")
            if tests.get("status") == "passed":
                if type(tests.get("passed")) is not int or tests.get("passed", 0) <= 0:
                    issues.append("audit passed-test count is invalid")
                if tests.get("failed") != 0 or tests.get("errors") != 0:
                    issues.append("audit passing test result contains failures or errors")
        if isinstance(commands, list):
            if not commands:
                issues.append("audit contains no command observations")
            for index, command in enumerate(commands):
                if not isinstance(command, Mapping):
                    issues.append(f"audit command observation {index} is not an object")
                    continue
                if (
                    not isinstance(command.get("command"), (list, tuple))
                    or not command.get("command")
                    or type(command.get("return_code")) is not int
                    or not isinstance(command.get("cwd"), str)
                    or not isinstance(command.get("stdout"), str)
                    or not isinstance(command.get("stderr"), str)
                    or not isinstance(command.get("timed_out"), bool)
                    or not isinstance(command.get("output_truncated"), bool)
                    or not isinstance(command.get("drain_incomplete"), bool)
                ):
                    issues.append(f"audit command observation {index} is invalid")
                    continue
                if (
                    _json_escaped_utf8_size(command["stdout"])
                    + _json_escaped_utf8_size(command["stderr"])
                    > MAX_COMMAND_OUTPUT_BYTES
                ):
                    issues.append(
                        f"audit command observation {index} exceeds the output budget"
                    )
        if audit.get("complete") is True:
            if not isinstance(repository, Mapping) or not (
                repository.get("working_tree_clean") is True
                and repository.get("post_test_working_tree_clean") is True
                and repository.get("final_working_tree_clean") is True
            ):
                issues.append("complete audit requires a clean repository")
            if not isinstance(tests, Mapping) or tests.get("status") != "passed":
                issues.append("complete audit requires passing tests")
            if not isinstance(docket, Mapping) or docket.get("receipts_valid") is not True:
                issues.append("complete audit requires valid reference receipts")
            if isinstance(docket, Mapping) and docket.get("broken_references") != []:
                issues.append("complete audit cannot contain broken references")
            if isinstance(docket, Mapping) and isinstance(docket.get("reference_receipts"), list):
                if any(receipt.get("valid") is not True for receipt in docket["reference_receipts"] if isinstance(receipt, Mapping)):
                    issues.append("complete audit contains an invalid reference receipt")
            if failures != []:
                issues.append("complete audit cannot contain failures")
            if isinstance(commands, list) and any(
                isinstance(command, Mapping)
                and (
                    command.get("return_code") != 0
                    or command.get("timed_out") is not False
                    or command.get("output_truncated") is not False
                    or command.get("drain_incomplete") is not False
                )
                for command in commands
            ):
                issues.append("complete audit contains an unsuccessful command observation")
    if integrity.get("canonicalization") != "json-sort-keys-utf8-v1":
        issues.append("unsupported canonicalization")

    try:
        expected_digest = _sha256(_canonical_bytes(dict(audit)))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        issues.append("audit is not canonical JSON")
        return False, tuple(issues)
    observed_digest = integrity.get("digest")
    if not hmac.compare_digest(str(observed_digest), expected_digest):
        issues.append("audit digest mismatch")

    signature = integrity.get("signature")
    if signature is not None:
        if not isinstance(signature, Mapping):
            issues.append("signature must be an object")
        elif signature.get("algorithm") != "hmac-sha256":
            issues.append("unsupported signature algorithm")
        elif signing_key is None:
            issues.append("signature is present but no verification key was supplied")
        else:
            expected_signature = hmac.new(
                signing_key,
                expected_digest.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(str(signature.get("value")), expected_signature):
                issues.append("audit signature mismatch")
    elif signing_key is not None:
        issues.append("verification key supplied for an unsigned artifact")

    return not issues, tuple(issues)


def write_audit_artifact(artifact: Mapping[str, object], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
