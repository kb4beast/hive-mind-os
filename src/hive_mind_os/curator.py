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
import shutil
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Literal, Mapping, Sequence, TypedDict

from .acceptance import AcceptanceSpecification, normalize_acceptance_specifications
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
    """One sealed command, optionally bound to a typed acceptance specification."""

    name: str
    argv: tuple[str, ...]
    expected: CheckOutcome = "succeeded"
    criteria: tuple[str, ...] = ()
    specification_id: str | None = None
    specification_digest: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("acceptance check name is required")
        if not self.argv or not all(
            isinstance(item, str) and item for item in self.argv
        ):
            raise ValueError("acceptance check argv must be a nonempty string tuple")
        if self.expected not in {"succeeded", "failed"}:
            raise ValueError("acceptance check expectation must be succeeded or failed")
        if any(not isinstance(item, str) or not item.strip() for item in self.criteria):
            raise ValueError("acceptance check criteria must be non-empty strings")
        if len(set(self.criteria)) != len(self.criteria):
            raise ValueError("acceptance check criteria must not contain duplicates")
        if self.specification_id is None and self.specification_digest is not None:
            raise ValueError("acceptance check digest requires a specification id")
        if self.specification_id is not None and not self.specification_id.strip():
            raise ValueError("acceptance check specification id must not be empty")
        if self.specification_digest is not None and (
            not self.specification_digest.startswith("sha256:")
            or len(self.specification_digest) != 71
        ):
            raise ValueError("acceptance check specification digest must be SHA-256")


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

    supported_fields = {
        "role",
        "prior_roles",
        "summaries",
        "receipt_digests",
        "provider_kind",
        "model_id",
        "provider_configuration",
    }
    unsupported_fields = sorted(str(key) for key in set(manifest) - supported_fields)
    if unsupported_fields:
        raise ContaminationError(
            "verification context contains unsupported fields: "
            + ", ".join(unsupported_fields)
        )
    missing_fields = sorted(supported_fields - set(manifest))
    if missing_fields:
        raise ContaminationError(
            "verification context is missing required manifest fields: "
            + ", ".join(missing_fields)
        )
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

    prior_roles = _required_string_list(manifest, "prior_roles")
    summaries = _required_string_list(manifest, "summaries")
    receipt_digests = set(_required_string_list(manifest, "receipt_digests"))
    scalar_fields = (
        "role",
        "provider_kind",
        "model_id",
        "provider_configuration",
    )
    for field in scalar_fields:
        if not isinstance(manifest[field], str) or not str(manifest[field]).strip():
            raise ContaminationError(
                f"verification context {field} must be a non-empty string"
            )
    if manifest["role"] != verifying_identity:
        raise ContaminationError(
            "verification context manifest role must equal the verifying identity"
        )
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
    rendered = "\n".join(
        (
            *prior_roles,
            *summaries,
            *receipt_digests,
            *(str(manifest[field]) for field in scalar_fields if field in manifest),
        )
    )
    if "diff --git " in rendered or "\n@@ " in rendered:
        raise ContaminationError("verification context contains candidate diff bytes")
    if any(rationale and rationale in rendered for rationale in builder_rationales):
        raise ContaminationError("verification context contains Builder rationale")


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
        acceptance_specifications: Sequence[AcceptanceSpecification | Mapping[str, object]] = (),
    ) -> None:
        self.run_id = run_id
        self.ledger = ledger
        self.objective = objective
        self.acceptance_specifications = normalize_acceptance_specifications(
            acceptance_specifications
        )
        specification_criteria = tuple(
            item.criterion for item in self.acceptance_specifications
        )
        declared_criteria = tuple(acceptance_criteria)
        if declared_criteria and not self.acceptance_specifications:
            raise ContaminationError(
                "declared acceptance criteria require typed executable specifications"
            )
        if self.acceptance_specifications and declared_criteria and (
            len(declared_criteria) != len(set(declared_criteria))
            or set(declared_criteria) != set(specification_criteria)
        ):
            raise ContaminationError(
                "typed acceptance specifications must exactly match the declared criterion set"
            )
        self.acceptance_criteria = specification_criteria
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
        declared_criteria = set(self.acceptance_criteria)
        covered_criteria = {
            criterion for check in frozen for criterion in check.criteria
        }
        unknown_criteria = sorted(covered_criteria - declared_criteria)
        if unknown_criteria:
            raise ContaminationError(
                "acceptance checks refer to undeclared criteria: "
                + ", ".join(unknown_criteria)
            )
        missing_criteria = sorted(declared_criteria - covered_criteria)
        if missing_criteria:
            raise ContaminationError(
                "blind phase did not define executable checks for criteria: "
                + ", ".join(missing_criteria)
            )
        self._validate_specification_bindings(frozen)
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
                "acceptance_specifications": [
                    item.to_dict() for item in self.acceptance_specifications
                ],
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
            [AcceptanceCheck],
            tuple[Mapping[str, object], Sequence[Mapping[str, object]]],
        ],
        repository_test_argv: Sequence[str],
        delivery_verifier: Callable[[], tuple[bool, Sequence[Mapping[str, object]]]],
        provenance_resolves: bool,
        license_evaluated: bool = False,
    ) -> tuple[ReviewVerdict, tuple[Mapping[str, object], ...]]:
        """Run only sealed checks and derive a verdict from observed results."""

        if self._seal_digest is None or self._seal_sequence is None:
            raise ContaminationError("reproduction cannot precede the blind seal")
        if acceptance_checks_digest(self._checks) != self._seal_digest:
            raise ContaminationError(
                "sealed acceptance checks changed before reproduction"
            )

        evidence_records: list[Mapping[str, object]] = []
        acceptance_results: list[Mapping[str, object]] = []
        observed_by_argv: dict[tuple[str, ...], dict[str, object]] = {}
        for check in self._checks:
            receipt, records = command_runner(check)
            evidence_records.extend(records)
            observed = str(receipt.get("result", "unknown"))
            receipt_binding = _evaluate_check_receipt(check, receipt)
            evaluation = {
                "observed": observed,
                "matched": receipt_binding == "matched",
                "receipt_binding": receipt_binding,
            }
            observed_by_argv.setdefault(check.argv, evaluation)
            acceptance_results.append(
                {
                    "name": check.name,
                    "argv": list(check.argv),
                    "expected": check.expected,
                    "criteria": list(check.criteria),
                    "specification_id": check.specification_id,
                    "specification_digest": check.specification_digest,
                    "observed": observed,
                    "matched": evaluation["matched"],
                    "receipt_binding": receipt_binding,
                    "sealed_digest": self._seal_digest,
                }
            )

        repository_argv = tuple(repository_test_argv)
        repository_evaluation = observed_by_argv.get(repository_argv)
        verification_source = "sealed-acceptance-check"
        if repository_evaluation is None:
            repository_check = AcceptanceCheck(
                "repository-own-tests",
                repository_argv,
            )
            repository_receipt, repository_records = command_runner(repository_check)
            evidence_records.extend(repository_records)
            repository_evaluation = {
                "observed": str(repository_receipt.get("result", "unknown")),
                "matched": _evaluate_check_receipt(
                    repository_check,
                    repository_receipt,
                )
                == "matched",
                "receipt_binding": _evaluate_check_receipt(
                    repository_check,
                    repository_receipt,
                ),
            }
            verification_source = "repository-command"
        assert repository_evaluation is not None
        acceptance_results.append(
            {
                "name": "repository-own-tests",
                "argv": list(repository_argv),
                "expected": "succeeded",
                "criteria": [],
                "specification_id": None,
                "specification_digest": None,
                "observed": repository_evaluation["observed"],
                "matched": repository_evaluation["matched"],
                "receipt_binding": repository_evaluation["receipt_binding"],
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

    def _validate_specification_bindings(
        self,
        checks: Sequence[AcceptanceCheck],
    ) -> None:
        """Require one exact sealed check per declared typed specification."""

        if not self.acceptance_specifications:
            return
        by_identifier = {
            item.identifier: item for item in self.acceptance_specifications
        }
        bound: dict[str, list[AcceptanceCheck]] = {
            identifier: [] for identifier in by_identifier
        }
        for check in checks:
            if check.specification_id is None:
                if check.criteria:
                    raise ContaminationError(
                        "criterion-scoped acceptance checks must bind a specification"
                    )
                continue
            specification = by_identifier.get(check.specification_id)
            if specification is None:
                raise ContaminationError(
                    "acceptance check refers to an unknown specification: "
                    + check.specification_id
                )
            if check.specification_digest != specification.digest:
                raise ContaminationError(
                    "acceptance check specification digest does not bind the declared command"
                )
            if (
                check.argv != specification.argv
                or check.expected != specification.expected
                or check.criteria != (specification.criterion,)
            ):
                raise ContaminationError(
                    "acceptance check does not exactly match its typed specification: "
                    + specification.identifier
                )
            bound[specification.identifier].append(check)
        missing = sorted(identifier for identifier, items in bound.items() if not items)
        if missing:
            raise ContaminationError(
                "typed acceptance specifications lack sealed checks: "
                + ", ".join(missing)
            )
        duplicated = sorted(identifier for identifier, items in bound.items() if len(items) > 1)
        if duplicated:
            raise ContaminationError(
                "typed acceptance specifications have multiple sealed checks: "
                + ", ".join(duplicated)
            )

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


def _evaluate_check_receipt(
    check: AcceptanceCheck,
    receipt: Mapping[str, object],
) -> str:
    """Return a stable reason unless a receipt proves the sealed check ran.

    The record must bind the exact request and the resolved executable, the typed
    specification (when present), a non-truncated process result, and a compatible
    exit status.  A sandbox timeout is never an expected failed acceptance check.
    """

    execution = receipt.get("execution")
    if not isinstance(execution, Mapping):
        return "missing-execution"
    requested = execution.get("requested_argv")
    actual = execution.get("argv")
    if not _string_argv_matches(requested, check.argv):
        return "requested-argv-mismatch"
    if not _executed_argv_matches(actual, check.argv):
        return "executed-argv-mismatch"
    if check.specification_id is not None:
        binding = execution.get("acceptance_specification")
        if not isinstance(binding, Mapping):
            return "missing-specification-binding"
        if binding.get("id") != check.specification_id:
            return "specification-id-mismatch"
        if binding.get("digest") != check.specification_digest:
            return "specification-digest-mismatch"
    outcome = execution.get("outcome")
    exit_code = execution.get("exit_code")
    if outcome not in {"succeeded", "failed"}:
        return "invalid-execution-outcome"
    if receipt.get("result") != outcome:
        return "receipt-result-mismatch"
    if type(exit_code) is not int:
        return "missing-exit-code"
    stdout = execution.get("stdout")
    stderr = execution.get("stderr")
    if not isinstance(stdout, Mapping) or not isinstance(stderr, Mapping):
        return "missing-output-metadata"
    if stdout.get("truncated") is True or stderr.get("truncated") is True:
        return "truncated-output"
    if check.expected == "succeeded" and (outcome != "succeeded" or exit_code != 0):
        return "unexpected-process-outcome"
    if check.expected == "failed" and (outcome != "failed" or exit_code == 0):
        return "unexpected-process-outcome"
    return "matched"


def _string_argv_matches(value: object, expected: Sequence[str]) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) for item in value
    ) and tuple(value) == tuple(expected)


def _executed_argv_matches(value: object, expected: Sequence[str]) -> bool:
    if not _string_argv_matches(value, expected):
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return False
        if len(value) != len(expected) or tuple(value[1:]) != tuple(expected[1:]):
            return False
        return _resolved_executable(value[0]) == _resolved_executable(expected[0])
    return True


def _resolved_executable(value: str) -> Path:
    resolved = shutil.which(value) or value
    return Path(resolved).resolve()


def _required_string_list(
    manifest: Mapping[str, object],
    field: str,
) -> tuple[str, ...]:
    if field not in manifest:
        raise ContaminationError(f"verification context is missing required {field}")
    value = manifest[field]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContaminationError(
            f"verification context {field} must be a list of strings"
        )
    return tuple(value)


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
        if not _is_test_path(relative) or base_files.get(relative) == head_files.get(
            relative
        ):
            continue
        before = _python_test_metrics(base_files.get(relative, b""))
        after = _python_test_metrics(head_files.get(relative, b""))
        retained_assertions = len(
            before["assertion_signatures"] & after["assertion_signatures"]
        )
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
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name.startswith("test"):
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
