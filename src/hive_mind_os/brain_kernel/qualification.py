"""Pure, claim-scoped qualification over immutable evidence receipts.

Qualification levels are cumulative.  Every level is reached only through its
hard evidence predicates; numeric scores are retained for reporting and never
participate in the decision.  The caller supplies both the trust registry and an
explicit evaluation instant, keeping evaluation deterministic and free of I/O.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from statistics import fmean
from typing import Iterable

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


class QualificationLevel(StrEnum):
    STRUCTURAL = "STRUCTURAL"
    BOUNDED_LOCAL = "BOUNDED_LOCAL"
    PROVIDER_BACKED = "PROVIDER_BACKED"
    INDEPENDENT_E2E = "INDEPENDENT_E2E"
    PRODUCTION = "PRODUCTION"
    SUPERIORITY = "SUPERIORITY"


class EvidenceKind(StrEnum):
    STRUCTURAL = "STRUCTURAL"
    BOUNDED_LOCAL = "BOUNDED_LOCAL"
    CONTROL_PLANE = "CONTROL_PLANE"
    FULL_SUITE = "FULL_SUITE"
    PROVIDER_BACKED = "PROVIDER_BACKED"
    INDEPENDENT_E2E = "INDEPENDENT_E2E"
    PRODUCTION = "PRODUCTION"
    SUPERIORITY = "SUPERIORITY"


class ExecutionMode(StrEnum):
    STATIC = "STATIC"
    FIXTURE = "FIXTURE"
    TEST_DOUBLE = "TEST_DOUBLE"
    LOCAL = "LOCAL"
    PROVIDER = "PROVIDER"
    PRODUCTION = "PRODUCTION"


class QualificationDisposition(StrEnum):
    ADOPT = "ADOPT"
    DEFER = "DEFER"
    QUARANTINE = "QUARANTINE"


_LEVELS = (
    QualificationLevel.STRUCTURAL,
    QualificationLevel.BOUNDED_LOCAL,
    QualificationLevel.PROVIDER_BACKED,
    QualificationLevel.INDEPENDENT_E2E,
    QualificationLevel.PRODUCTION,
    QualificationLevel.SUPERIORITY,
)
_PROVIDER_MODES = frozenset({ExecutionMode.PROVIDER, ExecutionMode.PRODUCTION})
_STRICT_GATES = frozenset({EvidenceKind.CONTROL_PLANE, EvidenceKind.FULL_SUITE})


def _require_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")


def _require_digest(value: object, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be lowercase sha256:<64 hex>")


def _instant(value: str, label: str) -> datetime:
    _require_text(value, label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} must be an RFC 3339 time") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include an offset")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceReceipt:
    """One issuer assertion, bound to exactly one claim and candidate."""

    receipt_id: str
    claim_id: str
    candidate_digest: str
    evidence_kind: EvidenceKind
    passed: bool
    issuer_id: str
    issuer_trust_domain: str
    observed_at: str
    expires_at: str
    artifact_digest: str
    execution_mode: ExecutionMode
    strict: bool = False
    score: float | None = None
    comparator_digest: str | None = None
    budget_digest: str | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_id, "receipt_id"),
            (self.claim_id, "claim_id"),
            (self.issuer_id, "issuer_id"),
            (self.issuer_trust_domain, "issuer_trust_domain"),
        ):
            _require_text(value, label)
        _require_digest(self.candidate_digest, "candidate_digest")
        _require_digest(self.artifact_digest, "artifact_digest")
        if not isinstance(self.evidence_kind, EvidenceKind):
            raise ValueError("evidence_kind must be an EvidenceKind")
        if not isinstance(self.execution_mode, ExecutionMode):
            raise ValueError("execution_mode must be an ExecutionMode")
        if type(self.passed) is not bool or type(self.strict) is not bool:
            raise ValueError("passed and strict must be booleans")
        observed = _instant(self.observed_at, "observed_at")
        expires = _instant(self.expires_at, "expires_at")
        if expires < observed:
            raise ValueError("expires_at must not precede observed_at")
        if self.score is not None:
            if (
                isinstance(self.score, bool)
                or not isinstance(self.score, (int, float))
                or not math.isfinite(self.score)
                or not 0 <= self.score <= 100
            ):
                raise ValueError("score must be a finite number from 0 through 100")
        if self.strict and self.evidence_kind not in _STRICT_GATES:
            raise ValueError(
                "strict is valid only for control-plane or full-suite evidence"
            )
        comparison_values = (
            self.comparator_digest,
            self.budget_digest,
            self.run_id,
        )
        if self.evidence_kind is EvidenceKind.SUPERIORITY:
            _require_digest(self.comparator_digest, "comparator_digest")
            _require_digest(self.budget_digest, "budget_digest")
            _require_text(self.run_id, "run_id")
        elif any(value is not None for value in comparison_values):
            raise ValueError(
                "comparison fields are valid only for superiority evidence"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class IssuerAuthority:
    """Caller-provided binding from issuer identity to its trusted assertions."""

    issuer_id: str
    trust_domain: str
    evidence_kinds: tuple[EvidenceKind, ...]

    def __post_init__(self) -> None:
        _require_text(self.issuer_id, "issuer_id")
        _require_text(self.trust_domain, "trust_domain")
        if not self.evidence_kinds:
            raise ValueError("issuer authority requires at least one evidence kind")
        if any(not isinstance(kind, EvidenceKind) for kind in self.evidence_kinds):
            raise ValueError("authority evidence kinds must be EvidenceKind values")
        if len(set(self.evidence_kinds)) != len(self.evidence_kinds):
            raise ValueError("authority evidence kinds must be unique")


@dataclass(frozen=True, slots=True, kw_only=True)
class QualificationRequest:
    claim_id: str
    candidate_digest: str
    candidate_trust_domain: str
    target_level: QualificationLevel
    as_of: str

    def __post_init__(self) -> None:
        _require_text(self.claim_id, "claim_id")
        _require_digest(self.candidate_digest, "candidate_digest")
        _require_text(self.candidate_trust_domain, "candidate_trust_domain")
        if not isinstance(self.target_level, QualificationLevel):
            raise ValueError("target_level must be a QualificationLevel")
        _instant(self.as_of, "as_of")


@dataclass(frozen=True, slots=True, kw_only=True)
class QualificationPolicy:
    max_evidence_age_seconds: int = 30 * 24 * 60 * 60
    superiority_min_comparators: int = 2
    superiority_repetitions: int = 2

    def __post_init__(self) -> None:
        for name in (
            "max_evidence_age_seconds",
            "superiority_min_comparators",
            "superiority_repetitions",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.superiority_min_comparators < 2:
            raise ValueError("superiority requires at least two comparators")
        if self.superiority_repetitions < 2:
            raise ValueError("superiority requires repeated receipts")


@dataclass(frozen=True, slots=True)
class QualificationDecision:
    claim_id: str
    candidate_digest: str
    target_level: QualificationLevel
    achieved_level: QualificationLevel | None
    disposition: QualificationDisposition
    qualified: bool
    missing_requirements: tuple[str, ...]
    failures: tuple[str, ...]
    accepted_receipt_ids: tuple[str, ...]
    rejected_receipt_ids: tuple[str, ...]
    informational_score: float | None


def _has(
    receipts: tuple[EvidenceReceipt, ...],
    kind: EvidenceKind,
    *,
    strict: bool | None = None,
) -> bool:
    return any(
        receipt.passed
        and receipt.evidence_kind is kind
        and (strict is None or receipt.strict is strict)
        for receipt in receipts
    )


def _superiority_requirements(
    receipts: tuple[EvidenceReceipt, ...],
    policy: QualificationPolicy,
) -> tuple[dict[str, bool], tuple[str, ...]]:
    comparisons = tuple(
        receipt
        for receipt in receipts
        if receipt.passed and receipt.evidence_kind is EvidenceKind.SUPERIORITY
    )
    comparator_digests = {receipt.comparator_digest for receipt in comparisons}
    budgets = {receipt.budget_digest for receipt in comparisons}
    enough_comparators = len(comparator_digests) >= policy.superiority_min_comparators
    equal_budget = bool(comparisons) and len(budgets) == 1
    repetitions = enough_comparators
    for comparator in comparator_digests:
        group = tuple(
            receipt
            for receipt in comparisons
            if receipt.comparator_digest == comparator
        )
        if (
            len({receipt.run_id for receipt in group}) < policy.superiority_repetitions
            or len({receipt.artifact_digest for receipt in group})
            < policy.superiority_repetitions
        ):
            repetitions = False
    geometry_failures: list[str] = []
    if len(budgets) > 1:
        geometry_failures.append(
            "superiority receipts do not share one equal budget digest"
        )
    return (
        {
            "superiority:at_least_two_pinned_comparators": enough_comparators,
            "superiority:equal_budget": equal_budget,
            "superiority:repeated_independent_receipts": repetitions,
        },
        tuple(geometry_failures),
    )


def qualify_claim(
    request: QualificationRequest,
    receipts: Iterable[EvidenceReceipt],
    authorities: Iterable[IssuerAuthority],
    *,
    policy: QualificationPolicy = QualificationPolicy(),
) -> QualificationDecision:
    """Evaluate one claim without I/O, ambient time, or compensating scores."""

    evidence = tuple(
        sorted(
            receipts,
            key=lambda item: (
                item.receipt_id,
                item.artifact_digest,
                item.evidence_kind.value,
            ),
        )
    )
    authority_items = tuple(authorities)
    if len({item.issuer_id for item in authority_items}) != len(authority_items):
        raise ValueError("issuer authority ids must be unique")
    authority_by_id = {item.issuer_id: item for item in authority_items}
    as_of = _instant(request.as_of, "as_of")
    failures: list[str] = []
    rejected: set[str] = set()
    receipt_id_counts = Counter(item.receipt_id for item in evidence)
    duplicate_ids = {
        receipt_id for receipt_id, count in receipt_id_counts.items() if count > 1
    }
    if duplicate_ids:
        failures.append("receipt ids must be unique")
        rejected.update(duplicate_ids)

    valid: list[EvidenceReceipt] = []
    for receipt in evidence:
        receipt_failures: list[str] = []
        if receipt.receipt_id in duplicate_ids:
            receipt_failures.append("duplicate receipt id")
        if receipt.claim_id != request.claim_id:
            receipt_failures.append("claim binding mismatch")
        if receipt.candidate_digest != request.candidate_digest:
            receipt_failures.append("candidate binding mismatch")
        authority = authority_by_id.get(receipt.issuer_id)
        if authority is None:
            receipt_failures.append("issuer is not trusted")
        else:
            if authority.trust_domain != receipt.issuer_trust_domain:
                receipt_failures.append("issuer trust-domain binding mismatch")
            if receipt.evidence_kind not in authority.evidence_kinds:
                receipt_failures.append("issuer is not trusted for this evidence kind")
        observed = _instant(receipt.observed_at, "observed_at")
        expires = _instant(receipt.expires_at, "expires_at")
        age_seconds = (as_of - observed).total_seconds()
        if age_seconds < 0:
            receipt_failures.append("evidence is future-dated")
        if age_seconds > policy.max_evidence_age_seconds or expires < as_of:
            receipt_failures.append("evidence is stale")
        if receipt.evidence_kind in {
            EvidenceKind.BOUNDED_LOCAL,
            EvidenceKind.CONTROL_PLANE,
            EvidenceKind.FULL_SUITE,
        } and receipt.execution_mode not in {
            ExecutionMode.LOCAL,
            ExecutionMode.PROVIDER,
            ExecutionMode.PRODUCTION,
        }:
            receipt_failures.append(
                "fixture and test-double evidence cannot satisfy executable local gates"
            )
        if (
            receipt.evidence_kind is EvidenceKind.PROVIDER_BACKED
            and receipt.execution_mode not in _PROVIDER_MODES
        ):
            receipt_failures.append(
                "fixture, test-double, and local evidence cannot satisfy provider backing"
            )
        if receipt.evidence_kind is EvidenceKind.INDEPENDENT_E2E:
            if receipt.execution_mode not in _PROVIDER_MODES:
                receipt_failures.append(
                    "independent end-to-end evidence requires a real provider execution"
                )
            if receipt.issuer_trust_domain == request.candidate_trust_domain:
                receipt_failures.append("evaluator and candidate share a trust domain")
        if (
            receipt.evidence_kind is EvidenceKind.PRODUCTION
            and receipt.execution_mode is not ExecutionMode.PRODUCTION
        ):
            receipt_failures.append("production evidence requires production execution")
        if (
            receipt.evidence_kind is EvidenceKind.SUPERIORITY
            and receipt.comparator_digest == request.candidate_digest
        ):
            receipt_failures.append("a candidate cannot be its own comparator")
        if receipt.evidence_kind is EvidenceKind.SUPERIORITY:
            if receipt.execution_mode not in _PROVIDER_MODES:
                receipt_failures.append(
                    "superiority evidence requires provider or production execution"
                )
            if receipt.issuer_trust_domain == request.candidate_trust_domain:
                receipt_failures.append(
                    "superiority evaluator and candidate share a trust domain"
                )
        if receipt_failures:
            rejected.add(receipt.receipt_id)
            failures.extend(
                f"{receipt.receipt_id}: {failure}" for failure in receipt_failures
            )
        else:
            valid.append(receipt)

    for receipt in valid:
        if receipt.passed:
            continue
        if receipt.strict and receipt.evidence_kind in _STRICT_GATES:
            failure = f"failed strict {receipt.evidence_kind.value.lower()} gate"
        else:
            failure = f"adverse {receipt.evidence_kind.value.lower()} evidence reported failure"
        failures.append(f"{receipt.receipt_id}: {failure}")
        rejected.add(receipt.receipt_id)

    valid_receipts = tuple(valid)
    superiority, geometry_failures = _superiority_requirements(valid_receipts, policy)
    failures.extend(geometry_failures)
    requirements: dict[QualificationLevel, dict[str, bool]] = {
        QualificationLevel.STRUCTURAL: {
            "structural:verified_contracts": _has(
                valid_receipts, EvidenceKind.STRUCTURAL
            )
        },
        QualificationLevel.BOUNDED_LOCAL: {
            "bounded_local:real_local_execution": _has(
                valid_receipts, EvidenceKind.BOUNDED_LOCAL
            ),
            "bounded_local:strict_control_plane": _has(
                valid_receipts, EvidenceKind.CONTROL_PLANE, strict=True
            ),
            "bounded_local:strict_full_suite": _has(
                valid_receipts, EvidenceKind.FULL_SUITE, strict=True
            ),
        },
        QualificationLevel.PROVIDER_BACKED: {
            "provider_backed:real_provider_execution": _has(
                valid_receipts, EvidenceKind.PROVIDER_BACKED
            )
        },
        QualificationLevel.INDEPENDENT_E2E: {
            "independent_e2e:separate_trust_domain": _has(
                valid_receipts, EvidenceKind.INDEPENDENT_E2E
            )
        },
        QualificationLevel.PRODUCTION: {
            "production:observed_production_execution": _has(
                valid_receipts, EvidenceKind.PRODUCTION
            )
        },
        QualificationLevel.SUPERIORITY: superiority,
    }

    target_index = _LEVELS.index(request.target_level)
    required_through_target = {
        name: passed
        for level in _LEVELS[: target_index + 1]
        for name, passed in requirements[level].items()
    }
    missing = tuple(
        name for name, passed in required_through_target.items() if not passed
    )
    achieved: QualificationLevel | None = None
    cumulative = True
    for level in _LEVELS:
        cumulative = cumulative and all(requirements[level].values())
        if cumulative:
            achieved = level
        else:
            break

    qualified = not failures and not missing
    if failures:
        disposition = QualificationDisposition.QUARANTINE
    elif qualified:
        disposition = QualificationDisposition.ADOPT
    else:
        disposition = QualificationDisposition.DEFER
    accepted = tuple(
        sorted(
            receipt.receipt_id
            for receipt in valid_receipts
            if receipt.passed and receipt.receipt_id not in rejected
        )
    )
    scores = tuple(
        float(receipt.score)
        for receipt in valid_receipts
        if receipt.passed
        and receipt.receipt_id not in rejected
        and receipt.score is not None
    )
    return QualificationDecision(
        claim_id=request.claim_id,
        candidate_digest=request.candidate_digest,
        target_level=request.target_level,
        achieved_level=achieved,
        disposition=disposition,
        qualified=qualified,
        missing_requirements=missing,
        failures=tuple(sorted(set(failures))),
        accepted_receipt_ids=accepted,
        rejected_receipt_ids=tuple(sorted(rejected)),
        informational_score=fmean(scores) if scores else None,
    )
