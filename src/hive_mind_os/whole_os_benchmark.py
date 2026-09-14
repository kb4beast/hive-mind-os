"""Measured N30 tournament orchestration over the frozen N02 protocol."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Iterable, Mapping

from .benchmark_adapters import (
    AdmittedBenchmarkInvocation,
    AdmittedBenchmarkRunner,
    BenchmarkResponse,
)
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
        if (
            type(self.expires_at) is not int
            or self.expires_at < 0
            or type(self.maximum_attempts) is not int
            or self.maximum_attempts < 1
        ):
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
            raise TournamentError(
                "independent evaluator/custodian identities are required"
            )
        required = {
            "current-baseline",
            "selected-design",
            "minimal-builder",
            "sdk-builder",
        }
        if not required.issubset(self.candidate_digests):
            raise TournamentError("frozen experiment lacks required original lanes")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "experiment_id": self.experiment_id,
                "protocol_digest": self.protocol_digest,
                "task_manifest_digest": self.task_manifest_digest,
                "family_manifest_digest": self.family_manifest_digest,
                "environment_digest": self.environment_digest,
                "budget_digest": self.budget_digest,
                "evaluator_id": self.evaluator_id,
                "custodian_id": self.custodian_id,
                "builder_ids": self.builder_ids,
                "candidate_digests": dict(self.candidate_digests),
            }
        )


@dataclass(frozen=True, slots=True)
class RecordedAttempt:
    metric: AttemptMetric
    operation_id: str
    receipt_digest: str
    failure_category: str | None
    admission_digest: str
    lease_digest: str
    variant_seal_digest: str
    execution_binding_digest: str


class WholeOSTournament:
    """Durably execute only exact lanes admitted by the closed N02 protocol.

    An execution intent is persisted before the broker is reached.  A retry
    re-plans from live registry state and uses the broker's inspect-first
    contract, so an uncertain write can be reconciled without executing twice
    or fabricating a failure receipt.
    """

    def __init__(
        self,
        runner: AdmittedBenchmarkRunner,
        *,
        state_path: str | Path | None = None,
    ) -> None:
        self.runner = runner
        self.state_path = Path(state_path) if state_path is not None else None
        self._attempts: list[RecordedAttempt] = []
        self._pending: Mapping[str, object] | None = None
        if self.state_path is not None and self.state_path.exists():
            self._load()

    @property
    def tournament_digest(self) -> str:
        return canonical_digest(
            {
                "protocol_digest": self.runner.protocol.protocol_digest,
                "adapter_manifest_digest": self.runner.manifest.digest,
            }
        )

    @property
    def attempts(self) -> tuple[RecordedAttempt, ...]:
        return tuple(self._attempts)

    def run(
        self,
        *,
        stage: str,
        variant_id: str,
        task_id: str,
        repetition: int = 0,
    ) -> RecordedAttempt:
        if self.state_path is None:
            raise TournamentError(
                "RESULT_STORE_REQUIRED: tournament execution requires durable state"
            )
        invocation = self.runner.plan(
            stage=stage,
            variant_id=variant_id,
            task_id=task_id,
            repetition=repetition,
        )
        existing = next(
            (
                item
                for item in self._attempts
                if item.operation_id == invocation.request.operation_id
            ),
            None,
        )
        if existing is not None:
            return existing

        intent = self._intent(invocation)
        if self._pending is not None and self._pending != intent:
            raise TournamentError(
                "RECONCILIATION_REQUIRED: another benchmark result is pending"
            )
        self._pending = intent
        self._persist()

        # Exceptions are evidence gaps, not benchmark failures.  Preserve the
        # pending intent and propagate them; never synthesize a receipt.
        response = self.runner.execute(invocation)
        recorded = self._record(
            invocation,
            response,
            model_digest=self.runner.manifest.recipes[variant_id].model_digest,
        )
        self._attempts.append(recorded)
        self._pending = None
        try:
            self._persist()
        except Exception:
            self._attempts.pop()
            self._pending = intent
            raise
        return recorded

    @staticmethod
    def _intent(invocation: AdmittedBenchmarkInvocation) -> Mapping[str, object]:
        request = invocation.request
        return {
            "operation_id": request.operation_id,
            "stage": request.stage,
            "variant_id": invocation.variant_id,
            "task_id": request.task_id,
            "family_id": request.family_id,
            "repetition": invocation.repetition,
            "seed": invocation.seed,
            "admission_digest": invocation.admission_digest,
            "lease_digest": invocation.lease_digest,
            "variant_seal_digest": invocation.variant_seal_digest,
            "execution_binding_digest": invocation.execution_binding_digest,
        }

    @staticmethod
    def _record(
        invocation: AdmittedBenchmarkInvocation,
        response: BenchmarkResponse,
        *,
        model_digest: str,
    ) -> RecordedAttempt:
        request = invocation.request
        status_to_result = {
            "success": "success",
            "failure": "failure",
            "timeout": "failure",
            "budget_exhausted": "failure",
            "no_change": "inconclusive",
            "blocked": "not_attempted",
            "inconclusive": "inconclusive",
        }
        metric = AttemptMetric(
            subject_family=request.family_id,
            task_id=request.task_id,
            variant_id=invocation.variant_id,
            candidate_digest=request.candidate_digest,
            configuration_digest=request.recipe_digest,
            model_digest=model_digest,
            environment_digest=request.environment_digest,
            eligibility="eligible",
            result=status_to_result[response.status],
            active_seconds=response.active_seconds,
            queue_seconds=None,
            wall_seconds=response.wall_seconds,
            usage_units=response.usage_units,
            usage_basis="measured" if response.usage_units is not None else "unknown",
            provider_cost=response.provider_cost,
            provider_cost_basis="billed"
            if response.provider_cost is not None
            else "unknown",
            currency="USD" if response.provider_cost is not None else None,
            checks=(response.result_digest,),
            defects=(response.failure_category,) if response.failure_category else (),
        )
        recorded = RecordedAttempt(
            metric,
            response.operation_id,
            response.receipt_digest,
            response.failure_category,
            invocation.admission_digest,
            invocation.lease_digest,
            invocation.variant_seal_digest,
            invocation.execution_binding_digest,
        )
        return recorded

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": 2,
            "tournament_digest": self.tournament_digest,
            "pending": self._pending,
            "attempts": [asdict(item) for item in self._attempts],
        }
        encoded = (
            json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        )
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        try:
            temporary.write_text(encoded, encoding="utf-8")
            temporary.replace(self.state_path)
        except (OSError, UnicodeError) as exc:
            raise TournamentError(
                "RESULT_STORE_UNAVAILABLE: benchmark state was not durably written"
            ) from exc

    def _load(self) -> None:
        if self.state_path is None:
            raise TournamentError("cannot load tournament state without a state path")
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if (
                not isinstance(raw, dict)
                or set(raw) != {
                    "schema_version",
                    "tournament_digest",
                    "pending",
                    "attempts",
                }
                or raw["schema_version"] != 2
                or raw["tournament_digest"] != self.tournament_digest
                or not isinstance(raw["attempts"], list)
                or raw["pending"] is not None
                and not isinstance(raw["pending"], dict)
            ):
                raise TournamentError(
                    "persisted tournament state is invalid or bound elsewhere"
                )
            self._pending = raw["pending"]
            for item in raw["attempts"]:
                metric = AttemptMetric(**item["metric"])
                recorded = RecordedAttempt(
                    metric,
                    item["operation_id"],
                    item["receipt_digest"],
                    item.get("failure_category"),
                    item["admission_digest"],
                    item["lease_digest"],
                    item["variant_seal_digest"],
                    item["execution_binding_digest"],
                )
                for digest in (
                    recorded.operation_id,
                    recorded.receipt_digest,
                    recorded.admission_digest,
                    recorded.lease_digest,
                    recorded.variant_seal_digest,
                    recorded.execution_binding_digest,
                ):
                    if (
                        type(digest) is not str
                        or len(digest) != 71
                        or not digest.startswith("sha256:")
                    ):
                        raise TournamentError("persisted attempt has an invalid digest")
                if any(
                    prior.operation_id == recorded.operation_id
                    for prior in self._attempts
                ):
                    raise TournamentError(
                        "persisted tournament contains duplicate operations"
                    )
                self._attempts.append(recorded)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
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
        if type(self.disposition) is not PromotionDisposition or any(
            type(value) is not bool
            for value in (
                self.hard_gates_passed,
                self.noninferiority_passed,
                self.measurable_benefit,
            )
        ):
            raise TournamentError("promotion disposition and gates must be typed")
        for digest in (self.candidate_digest, self.prior_champion_digest):
            if not _is_digest(digest):
                raise TournamentError("promotion candidate digests are invalid")
        if self.disposition is PromotionDisposition.ADOPT and (
            not self.hard_gates_passed
            or not self.noninferiority_passed
            or not self.measurable_benefit
            or not _has_independent_receipts(self.independent_receipt_digests)
        ):
            raise TournamentError("promotion exceeds measured evidence")


def _is_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 71
        and value.startswith("sha256:")
        and not set(value[7:]) - set("0123456789abcdef")
    )


def _has_independent_receipts(receipts: tuple[str, ...]) -> bool:
    return (
        len(receipts) >= 2
        and len(receipts) == len(set(receipts))
        and all(_is_digest(receipt) for receipt in receipts)
    )


def decide_promotion(
    *,
    candidate_digest: str,
    prior_champion_digest: str,
    hard_gates_passed: bool,
    noninferiority_passed: bool,
    measurable_benefit: bool,
    independent_receipt_digests: Iterable[str],
    critical_violation: bool = False,
) -> PromotionDecision:
    receipts = tuple(independent_receipt_digests)
    if critical_violation:
        disposition = PromotionDisposition.QUARANTINE
    elif not hard_gates_passed:
        disposition = PromotionDisposition.REJECT
    elif (
        not noninferiority_passed
        or not measurable_benefit
        or not _has_independent_receipts(receipts)
    ):
        disposition = PromotionDisposition.DEFER
    else:
        disposition = PromotionDisposition.ADOPT
    return PromotionDecision(
        candidate_digest,
        disposition,
        prior_champion_digest,
        hard_gates_passed,
        noninferiority_passed,
        measurable_benefit,
        receipts,
    )
