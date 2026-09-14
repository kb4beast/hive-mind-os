"""Frozen, fail-closed metrics and tournament bookkeeping for N02.

This module records measurements; it neither runs a comparator nor declares a
winner for the whole operating system.  In particular, ``None`` is an
intentional unknown, never a zero hidden by an aggregate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from random import Random
from statistics import mean
from typing import Iterable, Mapping, Sequence


class CampaignMetricsError(ValueError):
    pass


def canonical_digest(value: object) -> str:
    return "sha256:" + sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _id(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or any(c.isspace() for c in value):
        raise CampaignMetricsError(f"{name} must be a non-empty stable identifier")


def _digest(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise CampaignMetricsError(f"{name} must be a sha256 digest")
    if any(c not in "0123456789abcdef" for c in value[7:]):
        raise CampaignMetricsError(f"{name} must be lowercase sha256")


def _nonnegative(value: float | None, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
        raise CampaignMetricsError(f"{name} must be non-negative or unknown")


@dataclass(frozen=True, slots=True)
class AttemptMetric:
    """One retained attempt, including ineligible and failed attempts."""
    subject_family: str
    task_id: str
    variant_id: str
    candidate_digest: str
    configuration_digest: str
    model_digest: str
    environment_digest: str
    eligibility: str  # eligible, ineligible, unknown
    result: str       # success, failure, inconclusive, unknown, not_attempted
    active_seconds: float | None
    queue_seconds: float | None
    wall_seconds: float | None
    usage_units: float | None
    usage_basis: str  # measured, estimated, unknown
    provider_cost: float | None
    provider_cost_basis: str  # billed, estimated, unknown
    checks: tuple[str, ...] = ()
    defects: tuple[str, ...] = ()
    recovery_events: tuple[str, ...] = ()
    disclosure_events: tuple[str, ...] = ()
    context_retransmissions: int | None = None
    redundant_checks: int | None = None
    model_calls: int | None = None
    avoided_work_units: float | None = None

    def __post_init__(self) -> None:
        for name in ("subject_family", "task_id", "variant_id"):
            _id(getattr(self, name), name)
        for name in ("candidate_digest", "configuration_digest", "model_digest", "environment_digest"):
            _digest(getattr(self, name), name)
        if self.eligibility not in {"eligible", "ineligible", "unknown"}:
            raise CampaignMetricsError("unknown eligibility")
        if self.result not in {"success", "failure", "inconclusive", "unknown", "not_attempted"}:
            raise CampaignMetricsError("unknown result")
        for name in ("active_seconds", "queue_seconds", "wall_seconds", "usage_units", "provider_cost", "avoided_work_units"):
            _nonnegative(getattr(self, name), name)
        if self.usage_basis not in {"measured", "estimated", "unknown"} or self.provider_cost_basis not in {"billed", "estimated", "unknown"}:
            raise CampaignMetricsError("unknown measurement basis")
        if (self.usage_basis == "unknown") != (self.usage_units is None):
            raise CampaignMetricsError("unknown usage must be None; known usage needs a basis")
        if (self.provider_cost_basis == "unknown") != (self.provider_cost is None):
            raise CampaignMetricsError("unknown provider cost must be None; known cost needs a basis")
        for name in ("context_retransmissions", "redundant_checks", "model_calls"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise CampaignMetricsError(f"{name} must be a non-negative integer or unknown")


@dataclass(frozen=True, slots=True)
class PairedInterval:
    estimate: float | None
    lower: float | None
    upper: float | None
    family_count: int
    resamples: int = 10_000
    confidence: float = 0.95


def paired_family_bootstrap(pairs: Mapping[str, Sequence[float]], *, seed: int, resamples: int = 10_000) -> PairedInterval:
    """Bootstrap family means, so repeated seeds in one repo are not new repos."""
    if resamples != 10_000:
        raise CampaignMetricsError("N02 freezes 10,000 bootstrap resamples")
    families = sorted(pairs)
    if not families:
        return PairedInterval(None, None, None, 0)
    values: list[float] = []
    for family in families:
        observations = list(pairs[family])
        if not observations or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in observations):
            raise CampaignMetricsError("every family needs numeric paired observations")
        values.append(mean(observations))
    rng = Random(seed)
    samples = sorted(mean(values[rng.randrange(len(values))] for _ in values) for _ in range(resamples))
    return PairedInterval(mean(values), samples[249], samples[9749], len(values))


def noninferior(success_difference: PairedInterval, *, margin: float = -0.05, hard_gates_pass: bool) -> bool:
    return bool(hard_gates_pass and success_difference.lower is not None and success_difference.lower > margin)


def summarize_attempts(records: Iterable[AttemptMetric]) -> dict[str, int]:
    """Count every record while exposing, rather than erasing, the success denominator."""
    rows = tuple(records)
    eligible_attempted = [r for r in rows if r.eligibility == "eligible" and r.result != "not_attempted"]
    return {
        "records": len(rows),
        "eligible_attempted": len(eligible_attempted),
        "eligible_successes": sum(r.result == "success" for r in eligible_attempted),
        "eligible_failures": sum(r.result == "failure" for r in eligible_attempted),
        "ineligible": sum(r.eligibility == "ineligible" for r in rows),
        "unknown_eligibility": sum(r.eligibility == "unknown" for r in rows),
        "unknown_result": sum(r.result == "unknown" for r in rows),
        "inconclusive": sum(r.result == "inconclusive" for r in rows),
    }


@dataclass(frozen=True, slots=True)
class VariantSeal:
    variant_id: str
    recipe_digest: str
    candidate_digest: str
    evaluator_id: str
    stage: str

    def __post_init__(self) -> None:
        _id(self.variant_id, "variant_id"); _id(self.evaluator_id, "evaluator_id"); _id(self.stage, "stage")
        _digest(self.recipe_digest, "recipe_digest"); _digest(self.candidate_digest, "candidate_digest")


@dataclass(frozen=True, slots=True)
class MatchProtocol:
    protocol_id: str
    version: str
    track_id: str
    entrant_recipes: Mapping[str, Mapping[str, object]]
    variant_digest_rules: Mapping[str, object]
    candidate_seal_rule: str
    scenario_task_ids: tuple[str, ...]
    dataset_block_ids: tuple[str, ...]
    pairing_rule: str
    decision_rule: str
    hybrid_recipes: Mapping[str, Mapping[str, object]]
    elimination_losses: int = 3
    resource_lease_ref: str = "lease-required"
    max_rounds: int = 24
    terminal_rules: tuple[str, ...] = ("one_survivor", "no_schedulable_pairs", "max_rounds", "lease_exhausted")

    def __post_init__(self) -> None:
        for name in ("protocol_id", "version", "track_id", "resource_lease_ref"):
            _id(getattr(self, name), name)
        for name in ("candidate_seal_rule", "pairing_rule", "decision_rule"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise CampaignMetricsError(f"{name} is required")
        if self.elimination_losses != 3 or self.max_rounds != 24:
            raise CampaignMetricsError("protocol freezes triple elimination and 24 rounds")
        if not self.scenario_task_ids or not self.dataset_block_ids:
            raise CampaignMetricsError("scenario tasks and dataset blocks are required")
        if len(set(self.entrant_recipes)) != len(self.entrant_recipes):
            raise CampaignMetricsError("duplicate entrant IDs")
        for entrant, recipe in self.entrant_recipes.items():
            _id(entrant, "entrant_id")
            if not isinstance(recipe, Mapping) or "recipe_digest" not in recipe:
                raise CampaignMetricsError("each entrant requires a frozen recipe digest")
            _digest(str(recipe["recipe_digest"]), "recipe_digest")

    def validate_seals(self, seals: Iterable[VariantSeal], *, final: bool = False) -> None:
        seen: dict[str, VariantSeal] = {}
        for seal in seals:
            if seal.variant_id in seen:
                raise CampaignMetricsError("a variant may only be sealed once per stage")
            seen[seal.variant_id] = seal
        if final and len(seen) != 2:
            raise CampaignMetricsError("final holdout requires exactly two distinct sealed variants")


@dataclass(frozen=True, slots=True)
class ScheduledPair:
    left: str
    right: str | None
    bye: bool = False


def schedule_round(entrants: Sequence[str], losses: Mapping[str, int], byes: Mapping[str, int], *, round_number: int, inconclusive_meetings: Mapping[frozenset[str], int] | None = None) -> tuple[ScheduledPair, ...]:
    """Frozen rotate-left/odd-bye scheduler.  Two inconclusives make a pair ineligible."""
    if round_number < 1 or round_number > 24:
        raise CampaignMetricsError("round outside frozen bound")
    active = sorted(set(entrants), key=lambda e: (losses.get(e, 0), e))
    if any(losses.get(e, 0) >= 3 for e in active):
        raise CampaignMetricsError("eliminated entrant supplied to scheduler")
    rotate = (round_number - 1) % len(active) if active else 0
    active = active[rotate:] + active[:rotate]
    result: list[ScheduledPair] = []
    if len(active) % 2:
        bye = min(active, key=lambda e: (byes.get(e, 0), e))
        active.remove(bye); result.append(ScheduledPair(bye, None, True))
    prior = inconclusive_meetings or {}
    while active:
        left = active.pop(0)
        index = next((i for i, right in enumerate(active) if prior.get(frozenset((left, right)), 0) < 2), None)
        if index is None:
            result.append(ScheduledPair(left, None, False))
        else:
            result.append(ScheduledPair(left, active.pop(index), False))
    return tuple(result)


def decide_match(success: PairedInterval, cost_ratio: PairedInterval, time_ratio: PairedInterval, *, left_hard_gates: bool, right_hard_gates: bool) -> str:
    """Return LEFT/RIGHT/DRAW/INCONCLUSIVE; never breaks a scientific tie by ID."""
    if not left_hard_gates and right_hard_gates: return "RIGHT"
    if not right_hard_gates and left_hard_gates: return "LEFT"
    if not left_hard_gates and not right_hard_gates: return "INCONCLUSIVE"
    if success.lower is None: return "INCONCLUSIVE"
    if success.lower > 0: return "LEFT"
    if success.upper is not None and success.upper < 0: return "RIGHT"
    if noninferior(success, hard_gates_pass=True) and cost_ratio.upper is not None and time_ratio.upper is not None:
        if cost_ratio.upper < 1 and time_ratio.upper <= 1.10: return "LEFT"
        if cost_ratio.lower is not None and time_ratio.lower is not None and cost_ratio.lower > 1 and time_ratio.lower > 1.10: return "RIGHT"
    return "DRAW"


__all__ = ["AttemptMetric", "CampaignMetricsError", "MatchProtocol", "PairedInterval", "ScheduledPair", "VariantSeal", "canonical_digest", "decide_match", "noninferior", "paired_family_bootstrap", "schedule_round", "summarize_attempts"]
