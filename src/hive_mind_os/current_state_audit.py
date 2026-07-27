from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import platform
import re
import subprocess
import sys
import types
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


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


@dataclass(frozen=True, slots=True)
class CommandObservation:
    command: tuple[str, ...]
    cwd: str
    return_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


CommandExecutor = Callable[[Sequence[str], Path], CommandObservation]


def execute_command(command: Sequence[str], cwd: Path) -> CommandObservation:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return CommandObservation(
        command=tuple(command),
        cwd=str(cwd),
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
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
    candidate = Path(local_path)
    if candidate.is_absolute():
        return None, "absolute paths are not repository receipts"
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
    has_recognized_result = any(counts.values())
    return {
        "status": "passed" if observation.succeeded and has_recognized_result else "failed",
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
                if not run_tests:
                    entry["execution"] = {"status": "not_run"}
                    entry["valid"] = False
                    entry["issues"].append("test receipt was not executed")
                elif path is not None:
                    local_path = path.relative_to(repository).as_posix()
                    command = (sys.executable, "-m", "pytest", "-q", "--", local_path)
                    observation = observe(command, required=False)
                    result = _parse_test_result(observation, expected_command=command)
                    result["command_observation_index"] = len(observations) - 1
                    entry["execution"] = result
                    entry["valid"] = result["status"] == "passed"
                    if not entry["valid"]:
                        entry["issues"].append("test receipt execution did not pass")
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
        disposition_counts = _counter([decision.disposition.value for decision in docket.decisions])
        source_blockers = sorted(
            {
                issue.source_id
                for issue in docket_audit.issues
                if issue.source_id
                and issue.message
                == "source requires complete ingestion before derived ideas may be promoted"
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
        broken_references = _broken_references(docket, requested_repository)
        source_count: int | None = docket.source_count
        claim_count: int | None = docket.claim_count
        inventory_complete = docket_audit.inventory_complete
        release_ready = docket_audit.release_ready
    else:
        source_status_counts = {}
        claim_state_counts = {}
        disposition_counts = {}
        source_blockers = []
        docket_issues = []
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
        "disposition_counts": disposition_counts,
        "test_passed_count": test_result["passed"],
    }

    timestamp = (generated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    audit: dict[str, object] = {
        "schema_version": 1,
        "artifact_type": "CurrentStateAudit",
        "generated_at": timestamp,
        "invocation": list(invocation),
        "repository": {
            "root": str(requested_repository),
            "head": current_counts["repository_sha"],
            "working_tree_clean": not bool(working_tree_entries),
            "working_tree_entries": working_tree_entries,
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
            "disposition_counts": disposition_counts,
            "inventory_complete": inventory_complete,
            "release_ready": release_ready,
            "source_blockers": source_blockers,
            "issues": docket_issues,
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
        "complete": run_tests and receipts_valid and not failures,
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


def verify_audit_artifact(
    artifact: Mapping[str, object],
    *,
    signing_key: bytes | None = None,
) -> tuple[bool, tuple[str, ...]]:
    issues: list[str] = []
    audit = artifact.get("audit")
    integrity = artifact.get("integrity")
    if not isinstance(audit, Mapping) or not isinstance(integrity, Mapping):
        return False, ("artifact must contain audit and integrity objects",)

    if audit.get("schema_version") != 1:
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
    if integrity.get("canonicalization") != "json-sort-keys-utf8-v1":
        issues.append("unsupported canonicalization")

    expected_digest = _sha256(_canonical_bytes(dict(audit)))
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
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True))
        stream.write("\n")
