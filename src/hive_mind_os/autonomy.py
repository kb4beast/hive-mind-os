from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256
from statistics import fmean
from typing import Iterable, Protocol
from uuid import uuid4

from .learning import EvaluationSummary, LearningPromotionGate, PromotionDecision
from .models import Role


def _bounded(name: str, value: float) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


class BudgetExceeded(RuntimeError):
    """Raised when an autonomous run attempts to exceed its fixed envelope."""


@dataclass(frozen=True, slots=True)
class MissionCharter:
    """Immutable goal and authority boundary for an autonomous mission."""

    goal: str
    allowed_repositories: tuple[str, ...] = ()
    forbidden_capabilities: tuple[str, ...] = (
        "self_replication",
        "goal_mutation",
        "policy_mutation",
        "credential_exfiltration",
        "unbounded_resource_acquisition",
        "concealment",
    )
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("mission goal cannot be empty")

    @property
    def fingerprint(self) -> str:
        canonical = "\n".join(
            (self.goal, *sorted(self.allowed_repositories), *sorted(self.forbidden_capabilities))
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EpisodeAllowance:
    tool_calls: int
    compute_units: float


@dataclass(slots=True)
class AutonomyBudget:
    """Non-renewable execution envelope. Units are internal and cannot buy resources."""

    max_episodes: int
    max_tool_calls: int
    max_compute_units: float
    max_tool_calls_per_episode: int = 20
    max_compute_units_per_episode: float = 100.0
    episodes_used: int = 0
    tool_calls_used: int = 0
    compute_units_used: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.max_episodes,
            self.max_tool_calls,
            self.max_compute_units,
            self.max_tool_calls_per_episode,
            self.max_compute_units_per_episode,
        )
        if any(value < 0 for value in values):
            raise ValueError("budget limits cannot be negative")

    def issue_allowance(self) -> EpisodeAllowance:
        if self.exhausted:
            raise BudgetExceeded("resource budget exhausted")
        return EpisodeAllowance(
            tool_calls=min(self.max_tool_calls_per_episode, self.max_tool_calls - self.tool_calls_used),
            compute_units=min(
                self.max_compute_units_per_episode,
                self.max_compute_units - self.compute_units_used,
            ),
        )

    def consume(self, allowance: EpisodeAllowance, *, tool_calls: int, compute_units: float) -> None:
        if tool_calls < 0 or compute_units < 0:
            raise ValueError("resource consumption cannot be negative")
        if tool_calls > allowance.tool_calls or compute_units > allowance.compute_units:
            raise BudgetExceeded("episode exceeded its issued allowance")
        if self.episodes_used + 1 > self.max_episodes:
            raise BudgetExceeded("episode budget exhausted")
        self.episodes_used += 1
        self.tool_calls_used += tool_calls
        self.compute_units_used += compute_units

    @property
    def exhausted(self) -> bool:
        return (
            self.episodes_used >= self.max_episodes
            or self.tool_calls_used >= self.max_tool_calls
            or self.compute_units_used >= self.max_compute_units
        )


@dataclass(frozen=True, slots=True)
class AgentVariant:
    """Versioned behavior candidate. A variant cannot grant itself more authority."""

    role: Role
    strategy: str
    generation: int = 0
    parent_id: str | None = None
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.strategy.strip():
            raise ValueError("strategy cannot be empty")
        if self.generation < 0:
            raise ValueError("generation cannot be negative")


@dataclass(frozen=True, slots=True)
class EpisodeOutcome:
    variant_id: str
    task_id: str
    success: bool
    customer_value: float
    quality: float
    trust: float
    cooperation: float
    cost_efficiency: float
    evidence_count: int
    tool_calls: int = 0
    compute_units: float = 0.0
    policy_violations: tuple[str, ...] = ()
    attempted_capabilities: tuple[str, ...] = ()
    charter_fingerprint: str = ""
    lessons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("customer_value", "quality", "trust", "cooperation", "cost_efficiency"):
            _bounded(name, getattr(self, name))
        if self.evidence_count < 0 or self.tool_calls < 0 or self.compute_units < 0:
            raise ValueError("counts and costs cannot be negative")


@dataclass(frozen=True, slots=True)
class FitnessScore:
    score: float
    eligible: bool
    reasons: tuple[str, ...] = ()


class FitnessEvaluator:
    """Rewards useful autonomy while making safety and evidence hard gates."""

    def __init__(self, minimum_evidence: int = 1) -> None:
        self.minimum_evidence = minimum_evidence

    def evaluate(self, outcome: EpisodeOutcome, charter: MissionCharter) -> FitnessScore:
        reasons: list[str] = []
        if outcome.policy_violations:
            reasons.append("policy violation")
        forbidden = set(outcome.attempted_capabilities) & set(charter.forbidden_capabilities)
        if forbidden:
            reasons.append(f"forbidden capability attempted: {', '.join(sorted(forbidden))}")
        if outcome.charter_fingerprint != charter.fingerprint:
            reasons.append("mission charter changed")
        if outcome.evidence_count < self.minimum_evidence:
            reasons.append("insufficient evidence")

        score = (
            0.25 * outcome.customer_value
            + 0.20 * outcome.quality
            + 0.20 * outcome.trust
            + 0.10 * outcome.cooperation
            + 0.10 * outcome.cost_efficiency
            + 0.15 * float(outcome.success)
        )
        return FitnessScore(round(score, 6), not reasons, tuple(reasons))


@dataclass(slots=True)
class VariantState:
    variant: AgentVariant
    quarantined: bool = False
    quarantine_reasons: tuple[str, ...] = ()
    outcomes: list[EpisodeOutcome] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)

    @property
    def mean_fitness(self) -> float:
        return fmean(self.scores) if self.scores else 0.0

    @property
    def evaluation_summary(self) -> EvaluationSummary:
        regressions = sum(
            1
            for outcome in self.outcomes
            if outcome.policy_violations
            or not outcome.success
            or outcome.quality < 0.5
            or outcome.trust < 0.5
        )
        return EvaluationSummary(
            runs=len(self.outcomes),
            successes=sum(outcome.success for outcome in self.outcomes),
            regressions=regressions,
        )


@dataclass(frozen=True, slots=True)
class ArenaDecision:
    candidate_id: str | None
    promotion: PromotionDecision


@dataclass(frozen=True, slots=True)
class TeachingPacket:
    """Lessons supported by repeated, eligible outcomes for peer-agent training."""

    lessons: tuple[str, ...]
    source_runs: int
    minimum_support: int


class EvolutionArena:
    """A bounded selection environment for agent strategies, not agent survival."""

    def __init__(
        self,
        charter: MissionCharter,
        evaluator: FitnessEvaluator | None = None,
        promotion_gate: LearningPromotionGate | None = None,
    ) -> None:
        self.charter = charter
        self.evaluator = evaluator or FitnessEvaluator()
        self.promotion_gate = promotion_gate or LearningPromotionGate()
        self._states: dict[str, VariantState] = {}

    def register(self, variant: AgentVariant) -> None:
        if variant.id in self._states:
            raise ValueError(f"variant already registered: {variant.id}")
        self._states[variant.id] = VariantState(variant)

    def record(self, outcome: EpisodeOutcome) -> FitnessScore:
        state = self._states.get(outcome.variant_id)
        if state is None:
            raise KeyError(f"unknown variant: {outcome.variant_id}")
        score = self.evaluator.evaluate(outcome, self.charter)
        state.outcomes.append(outcome)
        if score.eligible:
            state.scores.append(score.score)
        else:
            state.quarantined = True
            state.quarantine_reasons = tuple(
                dict.fromkeys((*state.quarantine_reasons, *score.reasons))
            )
        return score

    def state(self, variant_id: str) -> VariantState:
        return self._states[variant_id]

    def eligible_variants(self) -> tuple[VariantState, ...]:
        return tuple(state for state in self._states.values() if not state.quarantined)

    def select_for_task(self) -> AgentVariant:
        eligible = self.eligible_variants()
        if not eligible:
            raise RuntimeError("no eligible variants remain")
        selected = min(
            eligible,
            key=lambda state: (len(state.outcomes), -state.mean_fitness, state.variant.id),
        )
        return selected.variant

    def recommend_promotion(self, champion_id: str) -> ArenaDecision:
        champion = self.state(champion_id)
        challengers = [
            state
            for state in self.eligible_variants()
            if state.variant.id != champion_id and state.outcomes
        ]
        if not challengers:
            return ArenaDecision(
                None,
                PromotionDecision(False, "no eligible challenger has evidence"),
            )
        candidate = max(
            challengers,
            key=lambda state: (state.mean_fitness, len(state.outcomes)),
        )
        decision = self.promotion_gate.evaluate(
            candidate.evaluation_summary,
            champion.evaluation_summary,
        )
        if decision.promote and candidate.mean_fitness <= champion.mean_fitness:
            decision = PromotionDecision(False, "candidate did not beat champion fitness")
        return ArenaDecision(candidate.variant.id, decision)

    def build_teaching_packet(self, minimum_support: int = 2) -> TeachingPacket:
        if minimum_support < 1:
            raise ValueError("minimum support must be positive")
        eligible = self.eligible_variants()
        lessons = Counter(
            lesson
            for state in eligible
            for outcome in state.outcomes
            for lesson in outcome.lessons
            if lesson.strip()
        )
        supported = tuple(
            lesson
            for lesson, count in sorted(lessons.items(), key=lambda item: (-item[1], item[0]))
            if count >= minimum_support
        )
        return TeachingPacket(
            lessons=supported,
            source_runs=sum(len(state.outcomes) for state in eligible),
            minimum_support=minimum_support,
        )


class EpisodeExecutor(Protocol):
    async def __call__(
        self,
        variant: AgentVariant,
        task_id: str,
        charter: MissionCharter,
        allowance: EpisodeAllowance,
    ) -> EpisodeOutcome: ...


@dataclass(frozen=True, slots=True)
class AutonomousRunReport:
    completed_tasks: tuple[str, ...]
    stopped_reason: str
    promotion: ArenaDecision
    teaching: TeachingPacket


class AutonomousMissionLoop:
    """Runs queued work without supervision until evidence, policy, or budget stops it."""

    def __init__(self, arena: EvolutionArena, budget: AutonomyBudget, champion_id: str) -> None:
        self.arena = arena
        self.budget = budget
        self.champion_id = champion_id

    async def run(self, task_ids: Iterable[str], executor: EpisodeExecutor) -> AutonomousRunReport:
        completed: list[str] = []
        stopped_reason = "work queue completed"

        for task_id in task_ids:
            try:
                allowance = self.budget.issue_allowance()
                variant = self.arena.select_for_task()
                outcome = await executor(variant, task_id, self.arena.charter, allowance)
                self.budget.consume(
                    allowance,
                    tool_calls=outcome.tool_calls,
                    compute_units=outcome.compute_units,
                )
            except BudgetExceeded:
                stopped_reason = "resource budget exhausted"
                break

            score = self.arena.record(outcome)
            completed.append(task_id)
            if not score.eligible and not self.arena.eligible_variants():
                stopped_reason = "all variants quarantined"
                break
            await asyncio.sleep(0)

        return AutonomousRunReport(
            completed_tasks=tuple(completed),
            stopped_reason=stopped_reason,
            promotion=self.arena.recommend_promotion(self.champion_id),
            teaching=self.arena.build_teaching_packet(),
        )
