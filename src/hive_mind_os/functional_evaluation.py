"""Observable behavior evaluation contracts (N24)."""

from dataclasses import dataclass
from enum import StrEnum

from .brain_kernel.canonical import canonical_digest, canonical_document
from .durable_contracts import ContractStore


class CheckOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvaluationVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED_ENVIRONMENT = "BLOCKED_ENVIRONMENT"
    CONTAMINATED = "CONTAMINATED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class FunctionalEvaluation:
    episode_id: str
    candidate_digest: str
    rubric_digest: str
    environment_digest: str
    reference_health: CheckOutcome
    required_checks: tuple[str, ...]
    capability_results: dict[str, CheckOutcome]
    quality_metrics: dict[str, float]
    security_results: dict[str, CheckOutcome]
    resource_use: dict[str, float]
    contamination_status: str
    evaluator_id: str
    verdict: EvaluationVerdict
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            self.contamination_status != "CLEAR"
            and self.verdict is not EvaluationVerdict.CONTAMINATED
        ):
            raise ValueError("contamination must quarantine evaluation")
        if (
            self.reference_health is CheckOutcome.UNAVAILABLE
            and self.verdict is EvaluationVerdict.PASS
        ):
            raise ValueError("unavailable reference cannot pass")

    @property
    def digest(self):
        return canonical_digest(self)

    def to_dict(self):
        return canonical_document(self)

    @classmethod
    def from_dict(cls, value):
        fields = {
            "episode_id",
            "candidate_digest",
            "rubric_digest",
            "environment_digest",
            "reference_health",
            "required_checks",
            "capability_results",
            "quality_metrics",
            "security_results",
            "resource_use",
            "contamination_status",
            "evaluator_id",
            "verdict",
            "evidence_refs",
        }
        if set(value) != fields:
            raise ValueError("closed evaluation schema")
        return cls(
            **{
                **value,
                "reference_health": CheckOutcome(value["reference_health"]),
                "verdict": EvaluationVerdict(value["verdict"]),
                "required_checks": tuple(value["required_checks"]),
                "evidence_refs": tuple(value["evidence_refs"]),
                "capability_results": {
                    k: CheckOutcome(v) for k, v in value["capability_results"].items()
                },
                "security_results": {
                    k: CheckOutcome(v) for k, v in value["security_results"].items()
                },
            }
        )


class FunctionalEvaluationStore:
    def __init__(self, path):
        self._store = ContractStore(path, FunctionalEvaluation.from_dict)

    def put(self, evaluation):
        return self._store.put(evaluation.digest, evaluation)

    def get(self, digest):
        return self._store.get(digest)


class FunctionalAdapter:
    """Runs one frozen observable check set against both implementations."""

    def evaluate(self, reference, candidate, checks):
        results = {}
        for name, check in checks.items():
            try:
                results[name] = (
                    CheckOutcome.PASS
                    if check(reference, candidate)
                    else CheckOutcome.FAIL
                )
            except NotImplementedError:
                results[name] = CheckOutcome.UNAVAILABLE
            except Exception:
                results[name] = CheckOutcome.INCONCLUSIVE
        return results


def verdict_for(checks, *, contaminated=False):
    if contaminated:
        return EvaluationVerdict.CONTAMINATED
    vals = list(checks.values())
    if any(v is CheckOutcome.FAIL for v in vals):
        return EvaluationVerdict.FAIL
    if any(v is CheckOutcome.UNAVAILABLE for v in vals):
        return EvaluationVerdict.BLOCKED_ENVIRONMENT
    if any(v is CheckOutcome.INCONCLUSIVE for v in vals):
        return EvaluationVerdict.INCONCLUSIVE
    return EvaluationVerdict.PASS
