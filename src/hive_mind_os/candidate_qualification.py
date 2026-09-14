"""Independent qualification receipts; cache origins remain explicit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .brain_kernel.canonical import canonical_digest


class QualificationDisposition(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class QualificationRequest:
    candidate_id: str
    base_id: str
    acceptance_manifest: tuple[str, ...]
    changed_surfaces: tuple[str, ...]
    risk_tier: str
    sandbox_digest: str
    toolchain_digest: str
    environment_digest: str
    evaluator_id: str
    allowed_cache_origins: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            not self.candidate_id
            or not self.base_id
            or not self.acceptance_manifest
            or not self.evaluator_id
        ):
            raise ValueError("candidate, base, acceptance and evaluator are required")


@dataclass(frozen=True, slots=True)
class CheckReceipt:
    name: str
    kind: str
    input_digest: str
    origin: str
    status: str
    actual_count: int = 0
    artifacts: tuple[str, ...] = ()
    omitted: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QualificationReceipt:
    request_digest: str
    disposition: QualificationDisposition
    checks: tuple[CheckReceipt, ...]
    invalidations: tuple[str, ...] = ()

    @property
    def digest(self):
        return canonical_digest(self)


class CandidateQualifier:
    def __init__(self, executor: Callable[[str], int] | None = None):
        self.executor = executor

    def qualify(self, request: QualificationRequest) -> QualificationReceipt:
        if not request.evaluator_id:
            raise ValueError("independent evaluator required")
        checks = []
        if self.executor is None:
            return QualificationReceipt(
                canonical_digest(request),
                QualificationDisposition.INCOMPLETE,
                (),
                ("toolchain-unexecuted",),
            )
        for name in request.acceptance_manifest:
            try:
                count = self.executor(name) if self.executor else 0
            except Exception:
                return QualificationReceipt(
                    canonical_digest(request),
                    QualificationDisposition.FAILED,
                    tuple(checks),
                    ("check-failed",),
                )
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                return QualificationReceipt(
                    canonical_digest(request),
                    QualificationDisposition.QUARANTINED,
                    tuple(checks),
                    ("invalid-executor-result",),
                )
            checks.append(
                CheckReceipt(
                    name,
                    "acceptance",
                    canonical_digest((request.candidate_id, name)),
                    "curator-execution",
                    "passed" if count > 0 else "failed",
                    count,
                )
            )
        disposition = (
            QualificationDisposition.PASSED
            if checks and all(c.status == "passed" for c in checks)
            else QualificationDisposition.INCOMPLETE
        )
        return QualificationReceipt(
            canonical_digest(request), disposition, tuple(checks)
        )

    @staticmethod
    def invalidated(
        receipt: QualificationReceipt,
        request: QualificationRequest,
        *,
        candidate_id: str | None = None,
        environment_digest: str | None = None,
    ) -> tuple[str, ...]:
        reasons = list(receipt.invalidations)
        if candidate_id is not None and candidate_id != request.candidate_id:
            reasons.append("candidate-changed")
        if (
            environment_digest is not None
            and environment_digest != request.environment_digest
        ):
            reasons.append("environment-changed")
        return tuple(dict.fromkeys(reasons))
