"""Measured N30 tournament orchestration over the frozen N02 protocol."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from dataclasses import asdict
import json
from pathlib import Path
from typing import Iterable, Mapping

from .benchmark_adapters import BenchmarkExecutionBroker, BenchmarkResponse, PinnedRecipeAdapter
from .campaign_metrics import AttemptMetric, canonical_digest, summarize_attempts


class TournamentError(ValueError):
    pass


class PromotionDisposition(StrEnum):
    ADOPT = "adopt"
    ADAPT = "adapt"
    DEFER = "defer"
    REJECT = "reject"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class ExperimentLease:
    lease_handle: str
    experiment_id: str
    admission_digest: str
    expires_at: int
    maximum_attempts: int
    revoked: bool = False

    def __post_init__(self) -> None:
        if not self.lease_handle or not self.experiment_id:
            raise TournamentError("lease identity is required")
        if type(self.expires_at) is not int or self.expires_at < 0 or type(self.maximum_attempts) is not int or self.maximum_attempts < 1:
            raise TournamentError("lease limits are invalid")

    def check(self, *, now: int, attempts: int, admission_digest: str) -> None:
        if self.revoked or now > self.expires_at:
            raise TournamentError("BLOCKED_AUTHORITY: experiment lease unavailable")
        if attempts >= self.maximum_attempts:
            raise TournamentError("BUDGET_EXHAUSTED: experiment attempt cap reached")
        if admission_digest != self.admission_digest:
            raise TournamentError("STALE_EVIDENCE: admission digest changed")


@dataclass(frozen=True, slots=True)
class FrozenExperiment:
    experiment_id: str
    protocol_digest: str
    task_manifest_digest: str
    family_manifest_digest: str
    environment_digest: str
    budget_digest: str
    evaluator_id: str
    custodian_id: str
    builder_ids: tuple[str, ...]
    candidate_digests: Mapping[str, str]

    def __post_init__(self) -> None:
        identities = (self.evaluator_id, self.custodian_id, *self.builder_ids)
        if len(identities) != len(set(identities)):
            raise TournamentError("independent evaluator/custodian identities are required")
        required = {"current-baseline", "selected-design", "minimal-builder", "sdk-builder"}
        if not required.issubset(self.candidate_digests):
            raise TournamentError("frozen experiment lacks required original lanes")

    @property
    def digest(self) -> str:
        return canonical_digest({
            "experiment_id": self.experiment_id, "protocol_digest": self.protocol_digest,
            "task_manifest_digest": self.task_manifest_digest,
            "family_manifest_digest": self.family_manifest_digest,
            "environment_digest": self.environment_digest, "budget_digest": self.budget_digest,
            "evaluator_id": self.evaluator_id, "custodian_id": self.custodian_id,
            "builder_ids": self.builder_ids, "candidate_digests": dict(self.candidate_digests),
        })


@dataclass(frozen=True, slots=True)
class RecordedAttempt:
    metric: AttemptMetric
    operation_id: str
    receipt_digest: str
    failure_category: str | None


class WholeOSTournament:
    """Records every eligible execution result; no result is silently dropped."""

    def __init__(self, experiment: FrozenExperiment, lease: ExperimentLease, broker: BenchmarkExecutionBroker, *, state_path: str | Path | None = None) -> None:
        if lease.experiment_id != experiment.experiment_id or lease.admission_digest != experiment.digest:
            raise TournamentError("lease is not bound to the frozen experiment")
        self.experiment = experiment
        self.lease = lease
        self.broker = broker
        self.state_path = Path(state_path) if state_path is not None else None
        self._attempts: list[RecordedAttempt] = []
        if self.state_path is not None and self.state_path.exists():
            self._load()

    @property
    def attempts(self) -> tuple[RecordedAttempt, ...]:
        return tuple(self._attempts)

    def run(
        self, *, now: int, stage: str, variant_id: str, task_id: str,
        family_id: str, adapter: PinnedRecipeAdapter,
    ) -> RecordedAttempt:
        self.lease.check(now=now, attempts=len(self._attempts), admission_digest=self.experiment.digest)
        if variant_id not in self.experiment.candidate_digests:
            raise TournamentError("variant was not sealed in the experiment")
        candidate = self.experiment.candidate_digests[variant_id]
        request = adapter.request(
            experiment_id=self.experiment.experiment_id, stage=stage, task_id=task_id,
            family_id=family_id, candidate_digest=candidate,
            budget_digest=self.experiment.budget_digest,
            environment_digest=self.experiment.environment_digest,
            lease_handle=self.lease.lease_handle,
        )
        try:
            response = adapter.run(request, self.broker)
        except Exception as exc:
            response = BenchmarkResponse(
                operation_id=request.operation_id, status="failure",
                result_digest=canonical_digest({"exception_type": type(exc).__name__}),
                receipt_digest=canonical_digest({"operation": request.operation_id, "observed": "adapter_exception"}),
                active_seconds=None, wall_seconds=None, usage_units=None,
                provider_cost=None, failure_category="adapter_exception",
            )
        status_to_result = {
            "success": "success", "failure": "failure", "timeout": "failure",
            "budget_exhausted": "failure", "no_change": "inconclusive",
            "blocked": "not_attempted", "inconclusive": "inconclusive",
        }
        metric = AttemptMetric(
            subject_family=family_id, task_id=task_id, variant_id=variant_id,
            candidate_digest=candidate, configuration_digest=adapter.manifest.digest,
            model_digest=adapter.manifest.model_digest,
            environment_digest=self.experiment.environment_digest,
            eligibility="eligible", result=status_to_result[response.status],
            active_seconds=response.active_seconds, queue_seconds=None,
            wall_seconds=response.wall_seconds, usage_units=response.usage_units,
            usage_basis="measured" if response.usage_units is not None else "unknown",
            provider_cost=response.provider_cost,
            provider_cost_basis="billed" if response.provider_cost is not None else "unknown",
            currency="USD" if response.provider_cost is not None else None,
            checks=(response.result_digest,), defects=(response.failure_category,) if response.failure_category else (),
        )
        recorded = RecordedAttempt(metric, response.operation_id, response.receipt_digest, response.failure_category)
        self._attempts.append(recorded)
        self._persist()
        return recorded

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        document = {"experiment_digest": self.experiment.digest, "attempts": [asdict(item) for item in self._attempts]}
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(encoded, encoding="utf-8")
        temporary.replace(self.state_path)

    def _load(self) -> None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if raw.get("experiment_digest") != self.experiment.digest or not isinstance(raw.get("attempts"), list):
                raise TournamentError("persisted tournament state is bound to another experiment")
            for item in raw["attempts"]:
                metric = AttemptMetric(**item["metric"])
                recorded = RecordedAttempt(metric, item["operation_id"], item["receipt_digest"], item.get("failure_category"))
                if recorded.metric.variant_id not in self.experiment.candidate_digests or recorded.metric.candidate_digest != self.experiment.candidate_digests[recorded.metric.variant_id]:
                    raise TournamentError("persisted attempt targets an unsealed candidate")
                self._attempts.append(recorded)
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, TournamentError):
                raise
            raise TournamentError("persisted tournament state is corrupt") from exc

    def summary(self) -> Mapping[str, int]:
        return summarize_attempts(row.metric for row in self._attempts)


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    candidate_digest: str
    disposition: PromotionDisposition
    prior_champion_digest: str
    hard_gates_passed: bool
    noninferiority_passed: bool
    measurable_benefit: bool
    independent_receipt_digests: tuple[str, ...]
    dissent: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.disposition is PromotionDisposition.ADOPT and (
            not self.hard_gates_passed or not self.noninferiority_passed or
            not self.measurable_benefit or not self.independent_receipt_digests
        ):
            raise TournamentError("promotion exceeds measured evidence")


def decide_promotion(
    *, candidate_digest: str, prior_champion_digest: str,
    hard_gates_passed: bool, noninferiority_passed: bool,
    measurable_benefit: bool, independent_receipt_digests: Iterable[str],
    critical_violation: bool = False,
) -> PromotionDecision:
    receipts = tuple(independent_receipt_digests)
    if critical_violation:
        disposition = PromotionDisposition.QUARANTINE
    elif not hard_gates_passed:
        disposition = PromotionDisposition.REJECT
    elif not noninferiority_passed or not measurable_benefit or not receipts:
        disposition = PromotionDisposition.DEFER
    else:
        disposition = PromotionDisposition.ADOPT
    return PromotionDecision(
        candidate_digest, disposition, prior_champion_digest,
        hard_gates_passed, noninferiority_passed, measurable_benefit, receipts,
    )
