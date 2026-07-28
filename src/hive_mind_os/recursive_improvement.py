from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from statistics import fmean, pstdev


class MetricDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class ExperimentVerdict(StrEnum):
    KEEP = "keep"
    RETEST = "retest"
    DISCARD = "discard"
    QUARANTINE = "quarantine"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str
    direction: MetricDirection
    minimum_effect: float = 0.0
    maximum_regression: float = 0.0
    hard_guardrail: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("metric name cannot be empty")
        if self.minimum_effect < 0 or self.maximum_regression < 0:
            raise ValueError("metric thresholds cannot be negative")


@dataclass(frozen=True, slots=True)
class RecursiveImprovementContract:
    """Immutable experiment constitution for bounded weak recursive improvement."""

    primary: MetricSpec
    guardrails: tuple[MetricSpec, ...]
    minimum_repetitions: int = 3
    noise_multiplier: float = 2.0
    patience: int = 5
    max_experiments: int = 100
    forbidden_behaviors: tuple[str, ...] = (
        "goal_mutation",
        "policy_mutation",
        "live_champion_mutation",
        "self_evaluation",
        "holdout_access",
        "metric_gaming",
        "evidence_concealment",
        "unbounded_resource_acquisition",
        "self_weight_modification",
    )

    def __post_init__(self) -> None:
        names = (self.primary.name, *(metric.name for metric in self.guardrails))
        if len(names) != len(set(names)):
            raise ValueError("recursive-improvement metrics must have unique names")
        if self.primary.hard_guardrail:
            raise ValueError("the primary metric cannot be marked as a guardrail")
        if self.minimum_repetitions < 2:
            raise ValueError("at least two repetitions are required")
        if self.noise_multiplier < 0:
            raise ValueError("noise multiplier cannot be negative")
        if self.patience < 1 or self.max_experiments < 1:
            raise ValueError("patience and experiment limits must be positive")

    @property
    def fingerprint(self) -> str:
        metric_rows = (
            self._metric_row(self.primary),
            *(self._metric_row(metric) for metric in self.guardrails),
        )
        canonical = "\n".join(
            (
                *metric_rows,
                str(self.minimum_repetitions),
                str(self.noise_multiplier),
                str(self.patience),
                str(self.max_experiments),
                *self.forbidden_behaviors,
            )
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _metric_row(metric: MetricSpec) -> str:
        return "|".join(
            (
                metric.name,
                metric.direction.value,
                str(metric.minimum_effect),
                str(metric.maximum_regression),
                str(metric.hard_guardrail),
            )
        )


@dataclass(frozen=True, slots=True)
class ExperimentCandidate:
    id: str
    parent_champion_id: str
    hypothesis: str
    changed_paths: tuple[str, ...]
    rollback_ref: str

    def __post_init__(self) -> None:
        required = (self.id, self.parent_champion_id, self.hypothesis, self.rollback_ref)
        if any(not value.strip() for value in required):
            raise ValueError("candidate identity, parent, hypothesis, and rollback are required")
        if self.id == self.parent_champion_id:
            raise ValueError("a challenger cannot mutate the live champion in place")
        if not self.changed_paths:
            raise ValueError("candidate must declare its changed paths")


@dataclass(frozen=True, slots=True)
class MetricObservation:
    metric_name: str
    baseline_samples: tuple[float, ...]
    candidate_samples: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.metric_name.strip():
            raise ValueError("metric observation requires a name")
        if not self.baseline_samples or not self.candidate_samples:
            raise ValueError("baseline and candidate samples are required")
        samples = (*self.baseline_samples, *self.candidate_samples)
        if any(not isfinite(value) for value in samples):
            raise ValueError("metric samples must be finite")


@dataclass(frozen=True, slots=True)
class ExperimentEvidence:
    candidate: ExperimentCandidate
    contract_fingerprint: str
    proposer_id: str
    builder_id: str
    evaluator_id: str
    observations: tuple[MetricObservation, ...]
    artifact_refs: tuple[str, ...]
    policy_violations: tuple[str, ...] = ()
    metric_gaming_signals: tuple[str, ...] = ()
    accessed_holdout: bool = False

    def __post_init__(self) -> None:
        identities = (self.proposer_id, self.builder_id, self.evaluator_id)
        if any(not identity.strip() for identity in identities):
            raise ValueError("proposer, builder, and evaluator identities are required")


@dataclass(frozen=True, slots=True)
class ExperimentDecision:
    verdict: ExperimentVerdict
    reasons: tuple[str, ...]
    primary_effect: float | None = None
    required_effect: float | None = None
    next_non_improvement_count: int = 0


class RecursiveImprovementGate:
    """Keeps only independently reproduced improvements that beat noise and guardrails."""

    def __init__(self, contract: RecursiveImprovementContract) -> None:
        self.contract = contract

    def evaluate(
        self,
        evidence: ExperimentEvidence,
        *,
        consecutive_non_improvements: int = 0,
        experiments_completed: int = 0,
    ) -> ExperimentDecision:
        if consecutive_non_improvements < 0 or experiments_completed < 0:
            raise ValueError("experiment counters cannot be negative")

        quarantine_reasons: list[str] = []
        if evidence.contract_fingerprint != self.contract.fingerprint:
            quarantine_reasons.append("recursive-improvement contract changed")
        if evidence.proposer_id == evidence.builder_id:
            quarantine_reasons.append(
                "candidate proposer attempted to build its own challenger"
            )
        if evidence.evaluator_id in {evidence.proposer_id, evidence.builder_id}:
            quarantine_reasons.append("acting agent attempted to evaluate its own candidate")
        if not evidence.artifact_refs:
            quarantine_reasons.append("experiment has no retained artifacts")
        if evidence.policy_violations:
            quarantine_reasons.append("experiment contains policy violations")
        if evidence.metric_gaming_signals:
            quarantine_reasons.append("metric gaming was detected")
        if evidence.accessed_holdout:
            quarantine_reasons.append("candidate accessed protected holdout evidence")
        if quarantine_reasons:
            return ExperimentDecision(
                ExperimentVerdict.QUARANTINE,
                tuple(quarantine_reasons),
                next_non_improvement_count=consecutive_non_improvements + 1,
            )

        observations = {item.metric_name: item for item in evidence.observations}
        expected = {self.contract.primary.name, *(metric.name for metric in self.contract.guardrails)}
        missing = expected - set(observations)
        unknown = set(observations) - expected
        if missing or unknown:
            reasons = []
            if missing:
                reasons.append("missing metrics: " + ", ".join(sorted(missing)))
            if unknown:
                reasons.append("undeclared metrics: " + ", ".join(sorted(unknown)))
            return ExperimentDecision(
                ExperimentVerdict.QUARANTINE,
                tuple(reasons),
                next_non_improvement_count=consecutive_non_improvements + 1,
            )

        insufficient = [
            name
            for name, observation in observations.items()
            if min(len(observation.baseline_samples), len(observation.candidate_samples))
            < self.contract.minimum_repetitions
        ]
        if insufficient:
            return self._non_improvement_decision(
                "insufficient repeated measurements: " + ", ".join(sorted(insufficient)),
                consecutive_non_improvements,
                experiments_completed,
                prefer_retest=True,
            )

        for guardrail in self.contract.guardrails:
            observation = observations[guardrail.name]
            effect = self._effect(guardrail, observation)
            regression = max(0.0, -effect)
            if guardrail.hard_guardrail and regression > guardrail.maximum_regression:
                return self._non_improvement_decision(
                    f"hard guardrail regressed: {guardrail.name}",
                    consecutive_non_improvements,
                    experiments_completed,
                    prefer_retest=False,
                )

        primary_observation = observations[self.contract.primary.name]
        primary_effect = self._effect(self.contract.primary, primary_observation)
        required_effect = max(
            self.contract.primary.minimum_effect,
            self.contract.noise_multiplier * self._noise_floor(primary_observation),
        )

        if primary_effect > required_effect:
            return ExperimentDecision(
                ExperimentVerdict.KEEP,
                ("candidate beat the champion beyond the measured noise floor",),
                primary_effect=round(primary_effect, 9),
                required_effect=round(required_effect, 9),
                next_non_improvement_count=0,
            )

        if primary_effect < -required_effect:
            return self._non_improvement_decision(
                "candidate materially underperformed the champion",
                consecutive_non_improvements,
                experiments_completed,
                prefer_retest=False,
                primary_effect=primary_effect,
                required_effect=required_effect,
            )

        return self._non_improvement_decision(
            "candidate improvement did not exceed the measured noise floor",
            consecutive_non_improvements,
            experiments_completed,
            prefer_retest=True,
            primary_effect=primary_effect,
            required_effect=required_effect,
        )

    def _non_improvement_decision(
        self,
        reason: str,
        consecutive_non_improvements: int,
        experiments_completed: int,
        *,
        prefer_retest: bool,
        primary_effect: float | None = None,
        required_effect: float | None = None,
    ) -> ExperimentDecision:
        next_count = consecutive_non_improvements + 1
        reached_limit = experiments_completed + 1 >= self.contract.max_experiments
        exhausted_patience = next_count >= self.contract.patience
        if reached_limit or exhausted_patience:
            stop_reason = (
                "maximum experiment budget reached"
                if reached_limit
                else "diminishing returns exhausted the configured patience"
            )
            verdict = ExperimentVerdict.STOP
            reasons = (reason, stop_reason)
        else:
            verdict = ExperimentVerdict.RETEST if prefer_retest else ExperimentVerdict.DISCARD
            reasons = (reason,)
        return ExperimentDecision(
            verdict,
            reasons,
            primary_effect=None if primary_effect is None else round(primary_effect, 9),
            required_effect=None if required_effect is None else round(required_effect, 9),
            next_non_improvement_count=next_count,
        )

    @staticmethod
    def _effect(spec: MetricSpec, observation: MetricObservation) -> float:
        baseline = fmean(observation.baseline_samples)
        candidate = fmean(observation.candidate_samples)
        if spec.direction is MetricDirection.MAXIMIZE:
            return candidate - baseline
        return baseline - candidate

    @staticmethod
    def _noise_floor(observation: MetricObservation) -> float:
        baseline_noise = pstdev(observation.baseline_samples)
        candidate_noise = pstdev(observation.candidate_samples)
        return max(baseline_noise, candidate_noise)


@dataclass(slots=True)
class RecursiveImprovementController:
    """Simulate evaluations without changing an authoritative champion pointer."""

    contract: RecursiveImprovementContract
    champion_id: str
    experiments_completed: int = 0
    consecutive_non_improvements: int = 0
    decisions: list[ExperimentDecision] = field(default_factory=list)
    pending_candidate_id: str | None = None
    evaluated_candidate_ids: list[str] = field(default_factory=list)

    def evaluate(self, evidence: ExperimentEvidence) -> ExperimentDecision:
        if evidence.candidate.parent_champion_id != self.champion_id:
            decision = ExperimentDecision(
                ExperimentVerdict.QUARANTINE,
                ("candidate was not derived from the active champion",),
                next_non_improvement_count=self.consecutive_non_improvements + 1,
            )
        else:
            decision = RecursiveImprovementGate(self.contract).evaluate(
                evidence,
                consecutive_non_improvements=self.consecutive_non_improvements,
                experiments_completed=self.experiments_completed,
            )

        self.experiments_completed += 1
        self.decisions.append(decision)
        self.evaluated_candidate_ids.append(evidence.candidate.id)
        self.consecutive_non_improvements = decision.next_non_improvement_count
        if decision.verdict is ExperimentVerdict.KEEP:
            self.pending_candidate_id = evidence.candidate.id
        return decision
