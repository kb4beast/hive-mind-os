"""Blind-first, evidence-bound Curator verification.

The Curator defines executable acceptance checks against the base workspace, seals
them in the append-only ledger, and only then receives a candidate workspace.  This
module intentionally contains deterministic policy rather than orchestration trust:
identity, context contamination, seal ordering, reproduction, and checklist verdicts
are all derived from recorded evidence.
"""

from __future__ import annotations

import ast
import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Literal, Mapping, Sequence, TypedDict

from .ledger import EvidenceLedger

CheckOutcome = Literal["succeeded", "failed"]
Finding = Literal["pass", "fail", "not-evaluated"]
CHECKLIST_VERSION = "P08-v1"


class _PythonTestMetrics(TypedDict):
    assertions: int
    test_functions: int
    assertion_signatures: set[str]


class ContaminationError(RuntimeError):
    """Raised when purportedly independent verification is contaminated."""


@dataclass(frozen=True, slots=True)
class AcceptanceCheck:
    """One sealed, argv-form command and its expected process outcome."""

    name: str
    argv: tuple[str, ...]
    expected: CheckOutcome = "succeeded"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("acceptance check name is required")
        if not self.argv or not all(isinstance(item, str) and item for item in self.argv):
            raise ValueError("acceptance check argv must be a nonempty string tuple")
        if self.expected not in {"succeeded", "failed"}:
            raise ValueError("acceptance check expectation must be succeeded or failed")


@dataclass(frozen=True, slots=True)
class ChecklistItem:
    """A versioned, explicit tri-state adversarial finding."""

    key: str
    finding: Finding
    details: Mapping[str, object]
    version: str = CHECKLIST_VERSION

    def __post_init__(self) -> None:
        if self.finding not in {"pass", "fail", "not-evaluated"}:
            raise ValueError("checklist finding must be pass, fail, or not-evaluated")


@dataclass(frozen=True, slots=True)
class ReviewVerdict:
    """The Curator's derived decision and all evidence used to reach it."""

    decision: Literal["adopt", "reject"]
    acceptance_results: tuple[Mapping[str, object], ...]
    checklist: tuple[ChecklistItem, ...]

    @property
    def accepted(self) -> bool:
        return self.decision == "adopt"


def acceptance_checks_digest(checks: Sequence[AcceptanceCheck]) -> str:
    """Return the canonical digest used by the blind seal."""

    encoded = json.dumps(
        [asdict(check) for check in checks],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def check_context_manifest(
    manifest: Mapping[str, object],
    *,
    acting_identity: str,
    verifying_identity: str,
    builder_receipt_digests: Sequence[str] = (),
    builder_rationales: Sequence[str] = (),
    seal_sequence: int | None = None,
    head_access_sequence: int | None = None,
) -> None:
    """Fail closed when recorded verification evidence is not independent."""

    if not acting_identity or not verifying_identity:
        raise ContaminationError("verification identities must be recorded")
    if acting_identity == verifying_identity:
        raise ContaminationError(
            "verification identity must differ from the acting identity"
        )
    if seal_sequence is None:
        raise ContaminationError("acceptance checks were not sealed")
    if head_access_sequence is not None and seal_sequence >= head_access_sequence:
        raise ContaminationError(
            "acceptance checks were sealed after candidate-head access"
        )

    prior_roles = _string_sequence(manifest.get("prior_roles"))
    summaries = _string_sequence(manifest.get("summaries"))
    receipt_digests = set(_string_sequence(manifest.get("receipt_digests")))
    forbidden_fields = sorted(
        str(key)
        for key, value in manifest.items()
        if any(
            marker in str(key).lower()
            for marker in ("builder", "diff", "patch", "head_workspace", "head_sha")
        )
        and value not in (None, "", [], (), {})
    )
    if forbidden_fields:
        raise ContaminationError(
            "verification context contains candidate-sensitive fields: "
            + ", ".join(forbidden_fields)
        )
    if acting_identity in prior_roles:
        raise ContaminationError(
            "verification context contains the acting Builder identity"
        )
    contaminated_digests = receipt_digests.intersection(builder_receipt_digests)
    if contaminated_digests:
        raise ContaminationError(
            "verification context contains Builder receipt digests"
        )
    rendered = "\n".join(summaries)
    if "diff --git " in rendered or "\n@@ " in rendered:
        raise ContaminationError("verification context contains candidate diff bytes")
    if any(rationale and rationale in rendered for rationale in builder_rationales):
        raise ContaminationError(
            "verification context contains Builder rationale"
        )


class CuratorReview:
    """Stateful blind seal followed by deterministic candidate reproduction."""

    def __init__(
        self,
        run_id: str,
        ledger: EvidenceLedger,
        *,
        objective: str,
        acceptance_criteria: Sequence[str],
        base_workspace: Path,
    ) -> None:
        self.run_id = run_id
        self.ledger = ledger
        self.objective = objective
        self.acceptance_criteria = tuple(acceptance_criteria)
        self.base_workspace = base_workspace.resolve()
        self._checks: tuple[AcceptanceCheck, ...] = ()
        self._seal_digest: str | None = None
        self._seal_sequence: int | None = None

    @property
    def checks(self) -> tuple[AcceptanceCheck, ...]:
        return self._checks

    @property
    def seal_digest(self) -> str | None:
        return self._seal_digest

    @property
    def seal_sequence(self) -> int | None:
        return self._seal_sequence

    def seal(self, checks: Sequence[AcceptanceCheck]) -> str:
        """Seal the complete blind check set exactly once."""

        if self._seal_digest is not None:
            raise ContaminationError("acceptance checks are already sealed")
        frozen = tuple(checks)
        if not frozen:
            raise ContaminationError("blind phase produced no acceptance checks")
        digest = acceptance_checks_digest(frozen)
        sequence = self.ledger.append_event(
            self.run_id,
            "curator.acceptance.sealed",
            "curator",
            {
                "schema_version": 1,
                "digest": digest,
                "check_count": len(frozen),
                "checks": [asdict(check) for check in frozen],
                "objective_digest": _text_digest(self.objective),
                "acceptance_criteria_digest": _text_digest(
                    json.dumps(
                        list(self.acceptance_criteria),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                ),
                "base_workspace": str(self.base_workspace),
            },
        )
        self._checks = frozen
        self._seal_digest = digest
        self._seal_sequence = sequence
        return digest

    def add_check(self, check: AcceptanceCheck) -> None:
        """Reject late evidence; a new blind phase must create a new review."""

        if self._seal_digest is not None:
            raise ContaminationError(
                "a check added after the blind seal cannot be verification evidence"
            )
        self._checks = (*self._checks, check)

    def reproduce(
        self,
        *,
        head_workspace: Path,
        declared_paths: Sequence[str],
        command_runner: Callable[
            [Sequence[str]], tuple[Mapping[str, object], Sequence[Mapping[str, object]]]
        ],
        repository_test_argv: Sequence[str],
        delivery_verifier: Callable[
            [], tuple[bool, Sequence[Mapping[str, object]]]
        ],
        provenance_resolves: bool,
        license_evaluated: bool = False,
    ) -> tuple[ReviewVerdict, tuple[Mapping[str, object], ...]]:
        """Run only sealed checks and derive a verdict from observed results."""

        if self._seal_digest is None or self._seal_sequence is None:
            raise ContaminationError("reproduction cannot precede the blind seal")
        if acceptance_checks_digest(self._checks) != self._seal_digest:
            raise ContaminationError("sealed acceptance checks changed before reproduction")

        evidence_records: list[Mapping[str, object]] = []
        acceptance_results: list[Mapping[str, object]] = []
        observed_by_argv: dict[tuple[str, ...], str] = {}
        for check in self._checks:
            receipt, records = command_runner(check.argv)
            evidence_records.extend(records)
            observed = str(receipt.get("result", "unknown"))
            observed_by_argv.setdefault(check.argv, observed)
            acceptance_results.append(
                {
                    "name": check.name,
                    "argv": list(check.argv),
                    "expected": check.expected,
                    "observed": observed,
                    "matched": observed == check.expected,
                    "sealed_digest": self._seal_digest,
                }
            )

        repository_argv = tuple(repository_test_argv)
        repository_observed = observed_by_argv.get(repository_argv)
        verification_source = "sealed-acceptance-check"
        if repository_observed is None:
            repository_receipt, repository_records = command_runner(repository_argv)
            evidence_records.extend(repository_records)
            repository_observed = str(repository_receipt.get("result", "unknown"))
            verification_source = "repository-command"
        acceptance_results.append(
            {
                "name": "repository-own-tests",
                "argv": list(repository_argv),
                "expected": "succeeded",
                "observed": repository_observed,
                "matched": repository_observed == "succeeded",
                "sealed_digest": self._seal_digest,
                "verification_source": verification_source,
            }
        )

        delivery_verified, delivery_records = delivery_verifier()
        evidence_records.extend(delivery_records)
        checklist = self._checklist(
            head_workspace.resolve(),
            declared_paths=declared_paths,
            delivery_verified=delivery_verified,
            provenance_resolves=provenance_resolves,
            license_evaluated=license_evaluated,
        )
        accepted = all(bool(item["matched"]) for item in acceptance_results) and all(
            item.finding != "fail" for item in checklist
        )
        verdict = ReviewVerdict(
            "adopt" if accepted else "reject",
            tuple(acceptance_results),
            checklist,
        )
        self.ledger.append_event(
            self.run_id,
            "curator.checklist",
            "curator",
            {
                "version": CHECKLIST_VERSION,
                "items": [asdict(item) for item in checklist],
            },
        )
        self.ledger.append_event(
            self.run_id,
            "curator.reproduction.completed",
            "curator",
            {
                "seal_digest": self._seal_digest,
                "acceptance_results": list(acceptance_results),
                "decision": verdict.decision,
            },
        )
        return verdict, tuple(evidence_records)

    def _checklist(
        self,
        head_workspace: Path,
        *,
        declared_paths: Sequence[str],
        delivery_verified: bool,
        provenance_resolves: bool,
        license_evaluated: bool,
    ) -> tuple[ChecklistItem, ...]:
        weakening = _test_weakening(self.base_workspace, head_workspace)
        changed = _changed_paths(self.base_workspace, head_workspace)
        declared = set(declared_paths)
        undeclared = sorted(changed - declared)
        return (
            ChecklistItem(
                "tests-weakened",
                "fail" if weakening["weakened_files"] else "pass",
                weakening,
            ),
            ChecklistItem(
                "rollback-artifact-verifies",
                "pass" if delivery_verified else "fail",
                {"verify_delivery": delivery_verified},
            ),
            ChecklistItem(
                "diff-confined-to-declared-scope",
                "pass" if not undeclared else "fail",
                {
                    "changed_paths": sorted(changed),
                    "declared_paths": sorted(declared),
                    "undeclared_paths": undeclared,
                },
            ),
            ChecklistItem(
                "provenance-receipts-resolve",
                "pass" if provenance_resolves else "fail",
                {"resolved": provenance_resolves},
            ),
            ChecklistItem(
                "introduced-code-license-declared",
                "pass" if license_evaluated else "not-evaluated",
                {
                    "evaluated": license_evaluated,
                    "reason": (
                        "no automated introduced-code license classifier is in P08 scope"
                        if not license_evaluated
                        else "license evidence was supplied"
                    ),
                },
            ),
        )


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _text_digest(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _repository_files(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.relative_to(root).parts:
            continue
        relative = path.relative_to(root).as_posix()
        if relative == "candidate.bundle":
            continue
        files[relative] = path.read_bytes()
    return files


def _changed_paths(base: Path, head: Path) -> set[str]:
    base_files = _repository_files(base)
    head_files = _repository_files(head)
    return {
        path
        for path in base_files.keys() | head_files.keys()
        if base_files.get(path) != head_files.get(path)
    }


def _test_weakening(base: Path, head: Path) -> dict[str, object]:
    base_files = _repository_files(base)
    head_files = _repository_files(head)
    details: list[dict[str, object]] = []
    weakened_files: list[str] = []
    for relative in sorted(base_files.keys() | head_files.keys()):
        if not _is_test_path(relative) or base_files.get(relative) == head_files.get(relative):
            continue
        before = _python_test_metrics(base_files.get(relative, b""))
        after = _python_test_metrics(head_files.get(relative, b""))
        retained_assertions = len(before["assertion_signatures"] & after["assertion_signatures"])
        assertion_delta = retained_assertions - len(before["assertion_signatures"])
        test_function_delta = after["test_functions"] - before["test_functions"]
        weakened = assertion_delta < 0 or test_function_delta < 0
        if weakened:
            weakened_files.append(relative)
        details.append(
            {
                "path": relative,
                "assertion_count_before": before["assertions"],
                "assertion_count_after": after["assertions"],
                "assertion_count_delta": after["assertions"] - before["assertions"],
                "retained_assertion_delta": assertion_delta,
                "test_function_count_before": before["test_functions"],
                "test_function_count_after": after["test_functions"],
                "test_function_count_delta": test_function_delta,
                "weakened": weakened,
            }
        )
    return {"files": details, "weakened_files": weakened_files}


def _is_test_path(relative: str) -> bool:
    path = Path(relative)
    return (
        "tests" in path.parts
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


def _python_test_metrics(content: bytes) -> _PythonTestMetrics:
    try:
        tree = ast.parse(content.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError):
        return {"assertions": 0, "test_functions": 0, "assertion_signatures": set()}
    signatures: set[str] = set()
    assertion_count = 0
    test_functions = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test"
        ):
            test_functions += 1
        if isinstance(node, ast.Assert):
            assertion_count += 1
            signatures.add(ast.dump(node.test, include_attributes=False))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr.startswith("assert"):
                assertion_count += 1
                signatures.add(ast.dump(node, include_attributes=False))
    return {
        "assertions": assertion_count,
        "test_functions": test_functions,
        "assertion_signatures": signatures,
    }
