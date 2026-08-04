"""Standalone, receipt-backed verification for an existing Git change."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .acceptance import AcceptanceSpecification
from .autonomy import AutonomyBudget
from .curator import _is_test_path, _python_test_metrics
from .ledger import EvidenceLedger
from .models import RiskTier, Role
from .receipts import portable_path_parts
from .sandbox import SandboxError, SandboxRunner, SandboxSpec, SandboxTimeout


class VerificationError(RuntimeError):
    """The requested verification could not be assembled safely."""


@dataclass(frozen=True, slots=True)
class VerificationReport:
    run_id: str
    verdict: str
    report_path: Path
    seal_sequence: int
    repository_read_sequence: int
    changed_paths: tuple[str, ...]
    undeclared_paths: tuple[str, ...]
    weakened_tests: tuple[str, ...]
    checks: tuple[dict[str, object], ...]


def verify_repository(
    repository: str | Path,
    specification_path: str | Path,
    output: str | Path,
) -> VerificationReport:
    """Seal one acceptance spec, then verify the repository's HEAD change."""

    root = Path(repository).resolve()
    if not root.is_dir() or not (root / ".git").exists():
        raise VerificationError("repository must be an existing Git worktree")
    bundle = Path(output).resolve()
    if bundle.exists():
        raise VerificationError("output bundle directory must not already exist")
    try:
        bundle.relative_to(root)
    except ValueError:
        pass
    else:
        raise VerificationError("output bundle directory must be outside the repository")

    specification = _load_specification(specification_path)
    if not specification.declared_paths:
        raise VerificationError("acceptance specification must declare changed paths")

    bundle.mkdir(parents=True)
    ledger = EvidenceLedger(bundle / "ledger.sqlite3")
    run_id = f"VERIFY-{uuid4()}"
    try:
        seal_sequence = ledger.append_event(
            run_id,
            "verify.acceptance.sealed",
            "curator",
            {
                "specification": specification.to_dict(),
                "specification_digest": specification.digest,
            },
        )
        changed_paths = _changed_paths(root)
        repository_read_sequence = ledger.append_event(
            run_id,
            "verify.repository.read",
            "curator",
            {"changed_paths": list(changed_paths)},
        )
        undeclared_paths = tuple(
            sorted(set(changed_paths) - set(specification.declared_paths))
        )
        weakened_tests = _weakened_tests(root, changed_paths)
        checks = (_run_check(root, bundle, run_id, specification, ledger),)
        accepted = (
            all(item["matched"] is True for item in checks)
            and not undeclared_paths
            and not weakened_tests
        )
        verdict = "adopt" if accepted else "reject"
        ledger.append_event(
            run_id,
            "verify.completed",
            "curator",
            {
                "verdict": verdict,
                "undeclared_paths": list(undeclared_paths),
                "weakened_tests": list(weakened_tests),
            },
        )
        document = {
            "schema_version": 1,
            "run_id": run_id,
            "verdict": verdict,
            "seal_sequence": seal_sequence,
            "repository_read_sequence": repository_read_sequence,
            "specification": specification.to_dict(),
            "changed_paths": list(changed_paths),
            "undeclared_paths": list(undeclared_paths),
            "weakened_tests": list(weakened_tests),
            "checks": list(checks),
            "ledger_events": ledger.events(run_id),
        }
        report_path = bundle / "verification.json"
        report_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return VerificationReport(
            run_id=run_id,
            verdict=verdict,
            report_path=report_path,
            seal_sequence=seal_sequence,
            repository_read_sequence=repository_read_sequence,
            changed_paths=changed_paths,
            undeclared_paths=undeclared_paths,
            weakened_tests=weakened_tests,
            checks=checks,
        )
    finally:
        ledger.close()


def _load_specification(path: str | Path) -> AcceptanceSpecification:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"acceptance specification is unreadable: {error}") from None
    if not isinstance(document, dict):
        raise VerificationError("acceptance specification must be a JSON object")
    try:
        return AcceptanceSpecification.from_dict(document)
    except ValueError as error:
        raise VerificationError(f"acceptance specification is invalid: {error}") from None


def _changed_paths(root: Path) -> tuple[str, ...]:
    completed = _git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    paths = tuple(sorted(path for path in completed.stdout.splitlines() if path))
    if not paths:
        raise VerificationError("HEAD contains no change to verify")
    for path in paths:
        try:
            portable_path_parts(path)
        except ValueError as error:
            raise VerificationError(f"Git returned an unsafe changed path: {error}") from None
    return paths


def _weakened_tests(root: Path, changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    weakened: list[str] = []
    for relative in changed_paths:
        if not _is_test_path(relative):
            continue
        before = _git_optional(root, "show", f"HEAD^:{relative}")
        path = root.joinpath(*portable_path_parts(relative))
        after = path.read_bytes() if path.is_file() else b""
        before_metrics = _python_test_metrics(before)
        after_metrics = _python_test_metrics(after)
        retained = len(
            before_metrics["assertion_signatures"]
            & after_metrics["assertion_signatures"]
        )
        if (
            retained < len(before_metrics["assertion_signatures"])
            or after_metrics["test_functions"] < before_metrics["test_functions"]
        ):
            weakened.append(relative)
    return tuple(weakened)


def _run_check(
    root: Path,
    bundle: Path,
    run_id: str,
    specification: AcceptanceSpecification,
    ledger: EvidenceLedger,
) -> dict[str, object]:
    intent = {
        "schema_version": 1,
        "action_id": f"ACT-{run_id}-0",
        "mission_id": run_id,
        "state_ref": f"MISSION_STATE:{run_id}:1",
        "actor_id": "verify-cli",
        "kind": "command",
        "description": specification.criterion,
        "policy_decision_ref": f"POLICY-{run_id}-0",
        "lease_id": f"LEASE-{run_id}-0",
        "idempotency_key": f"VERIFY-{run_id}-0",
        "rollback_ref": None,
        "status": "proposed",
        "command": {"argv": list(specification.argv), "path_args": []},
    }
    from .contracts import tool_intent_digest

    intent["action_digest"] = tool_intent_digest(intent)
    runner = SandboxRunner(
        SandboxSpec(root=root),
        bundle / "receipts",
        AutonomyBudget(
            max_episodes=1,
            max_tool_calls=1,
            max_compute_units=1.0,
            max_tool_calls_per_episode=1,
            max_compute_units_per_episode=1.0,
        ).issue_allowance(),
        role=Role.CURATOR,
        risk=RiskTier.MODERATE,
        runner_identity="verify-sandbox",
        ledger=ledger,
    )
    receipt: dict[str, object] | None = None
    error: str | None = None
    try:
        receipt = runner.run(intent)
    except SandboxTimeout as timeout:
        receipt = timeout.receipt
    except SandboxError as failure:
        error = str(failure)
    matched = (
        receipt is not None
        and receipt.get("result") == specification.expected
    )
    reference = runner.last_reference
    return {
        "id": specification.identifier,
        "expected": specification.expected,
        "matched": matched,
        "error": error,
        "receipt": (
            None
            if reference is None
            else {"path": reference.path, "digest": reference.digest}
        ),
    }


def _git(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise VerificationError(f"Git inspection failed: {completed.stderr.strip()}")
    return completed


def _git_optional(root: Path, *arguments: str) -> bytes:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else b""
