"""Inert N02 protocol primitives behind a host-owned admission registry.

This module validates data and computes deterministic bracket/statistical results.
It deliberately contains no verifier, signing key, admission constructor, default
registry, or executable fallback. A host registry owns opaque handles, principal
authentication, lease/revocation state, append-only seals, receipt issuance and
replay custody.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from random import Random
from statistics import mean
from types import MappingProxyType
from typing import Iterable, Mapping, Protocol, Sequence

BOOTSTRAP_RESAMPLES = 10_000
CONFIDENCE = 0.95
NONINFERIORITY_MARGIN = -0.05
SCREENING_FAMILIES = 12
FINAL_FAMILIES = 30
RECIPE_FIELDS = (
    "source_or_binary_digest",
    "prompt_digest",
    "model_digest",
    "command_profile_digest",
    "tool_digest",
    "context_digest",
    "check_policy_digest",
    "learning_policy_digest",
)
REQUIRED_STRATA = (
    "small-bug",
    "feature",
    "absent-tests",
    "multi-file",
    "cross-language",
    "self-runtime",
    "ambiguous-backlog",
    "provider-failure",
    "restart",
    "tenant-isolation",
    "draft-export",
    "endpoint-learning",
    "roblox-runtime",
)
STAGES = ("original", "hybrid", "final")
TERMINALS = ("one_survivor", "no_schedulable_pairs", "max_rounds", "lease_exhausted")
OPERATIONS = ("schedule", "apply", "seal", "aggregate", "decide")


class CampaignMetricsError(ValueError):
    pass


class LeaseExhausted(CampaignMetricsError):
    """Typed stop used when a revalidated lease is expired or revoked."""


def canonical_digest(value: object) -> str:
    def plain(item: object) -> object:
        if hasattr(item, "to_document"):
            return plain(item.to_document())  # type: ignore[union-attr]
        if isinstance(item, Mapping):
            return {str(key): plain(val) for key, val in item.items()}
        if isinstance(item, (tuple, list, set, frozenset)):
            values = [plain(val) for val in item]
            return (
                sorted(values, key=lambda val: json.dumps(val, sort_keys=True))
                if isinstance(item, (set, frozenset))
                else values
            )
        return item

    encoded = json.dumps(
        plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()


def _id(value: object, name: str) -> None:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        raise CampaignMetricsError(f"{name} must be a stable identifier")


def _digest(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(char not in "0123456789abcdef" for char in value[7:])
    ):
        raise CampaignMetricsError(f"{name} must be lowercase sha256")


def _num(
    value: object, name: str, *, nullable: bool = True, nonnegative: bool = True
) -> None:
    if value is None and nullable:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or (nonnegative and value < 0)
    ):
        suffix = " and nonnegative" if nonnegative else ""
        raise CampaignMetricsError(f"{name} must be finite{suffix}")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(val) for key, val in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(val) for val in value)
    if isinstance(value, set):
        return frozenset(_freeze(val) for val in value)
    return value


def _timestamp(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise CampaignMetricsError(f"{name} must be a nonnegative epoch second")
    return value


@dataclass(frozen=True, slots=True)
class AttemptMetric:
    subject_family: str
    task_id: str
    variant_id: str
    candidate_digest: str
    configuration_digest: str
    model_digest: str
    environment_digest: str
    eligibility: str
    result: str
    active_seconds: float | None
    queue_seconds: float | None
    wall_seconds: float | None
    usage_units: float | None
    usage_basis: str
    provider_cost: float | None
    provider_cost_basis: str
    usage_unit: str = "tokens"
    currency: str | None = None
    provider_available: str = "unknown"
    input_usage: float | None = None
    output_usage: float | None = None
    cache_read_usage: float | None = None
    cache_write_usage: float | None = None
    reasoning_usage: float | None = None
    checks: tuple[str, ...] = ()
    defects: tuple[str, ...] = ()
    recovery_events: tuple[str, ...] = ()
    disclosure_events: tuple[str, ...] = ()
    context_retransmissions: int | None = None
    redundant_checks: int | None = None
    model_calls: int | None = None
    avoided_work_units: float | None = None

    def __post_init__(self) -> None:
        for name in ("subject_family", "task_id", "variant_id", "usage_unit"):
            _id(getattr(self, name), name)
        for name in (
            "candidate_digest",
            "configuration_digest",
            "model_digest",
            "environment_digest",
        ):
            _digest(getattr(self, name), name)
        if self.eligibility not in {
            "eligible",
            "ineligible",
            "unknown",
        } or self.result not in {
            "success",
            "failure",
            "inconclusive",
            "unknown",
            "not_attempted",
        }:
            raise CampaignMetricsError("invalid eligibility/result")
        for name in (
            "active_seconds",
            "queue_seconds",
            "wall_seconds",
            "usage_units",
            "provider_cost",
            "input_usage",
            "output_usage",
            "cache_read_usage",
            "cache_write_usage",
            "reasoning_usage",
            "avoided_work_units",
        ):
            _num(getattr(self, name), name)
        if self.usage_basis not in {
            "measured",
            "estimated",
            "unknown",
        } or self.provider_cost_basis not in {"billed", "estimated", "unknown"}:
            raise CampaignMetricsError("invalid measurement basis")
        if (self.usage_basis == "unknown") != (self.usage_units is None) or (
            self.provider_cost_basis == "unknown"
        ) != (self.provider_cost is None):
            raise CampaignMetricsError(
                "unknown must be null and known must have a basis"
            )
        details = (
            self.input_usage,
            self.output_usage,
            self.cache_read_usage,
            self.cache_write_usage,
            self.reasoning_usage,
        )
        if self.usage_units is None and any(value is not None for value in details):
            raise CampaignMetricsError(
                "unknown total usage cannot contain detailed usage"
            )
        if self.provider_cost is not None:
            if self.currency is None:
                raise CampaignMetricsError("known cost requires currency")
            _id(self.currency, "currency")
        elif self.currency is not None:
            raise CampaignMetricsError("unknown cost cannot carry currency")
        if self.provider_available not in {"available", "unavailable", "unknown"}:
            raise CampaignMetricsError("invalid provider availability")
        for name in ("context_retransmissions", "redundant_checks", "model_calls"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise CampaignMetricsError(f"{name} must be nonnegative integer")
        for name in ("checks", "defects", "recovery_events", "disclosure_events"):
            values = tuple(getattr(self, name))
            for value in values:
                _id(value, name)
            object.__setattr__(self, name, values)


def summarize_attempts(rows: Iterable[AttemptMetric]) -> dict[str, int]:
    records = tuple(rows)
    result = {"records": len(records)}
    for eligibility in ("eligible", "ineligible", "unknown"):
        result[f"eligibility_{eligibility}"] = sum(
            row.eligibility == eligibility for row in records
        )
        for outcome in (
            "success",
            "failure",
            "inconclusive",
            "unknown",
            "not_attempted",
        ):
            result[f"{eligibility}_{outcome}"] = sum(
                row.eligibility == eligibility and row.result == outcome
                for row in records
            )
    result["eligible_attempted"] = (
        result["eligibility_eligible"] - result["eligible_not_attempted"]
    )
    return result


@dataclass(frozen=True, slots=True)
class DescriptiveInterval:
    """A statistical description with no qualification authority."""

    estimate: float | None
    lower: float | None
    upper: float | None
    family_count: int
    resamples: int = BOOTSTRAP_RESAMPLES
    confidence: float = CONFIDENCE

    def __post_init__(self) -> None:
        known = (
            self.estimate is not None,
            self.lower is not None,
            self.upper is not None,
        )
        if any(known) and not all(known):
            raise CampaignMetricsError(
                "interval must be wholly known or wholly unknown"
            )
        for name in ("estimate", "lower", "upper"):
            _num(getattr(self, name), name, nonnegative=False)
        if self.lower is not None and not self.lower <= self.estimate <= self.upper:  # type: ignore[operator]
            raise CampaignMetricsError("invalid interval ordering")
        if (
            type(self.family_count) is not int
            or self.family_count < 0
            or all(known) != (self.family_count > 0)
        ):
            raise CampaignMetricsError("interval/family count mismatch")
        if self.resamples != BOOTSTRAP_RESAMPLES or self.confidence != CONFIDENCE:
            raise CampaignMetricsError("unfrozen interval parameters")

    def to_document(self) -> Mapping[str, object]:
        return {
            "estimate": self.estimate,
            "lower": self.lower,
            "upper": self.upper,
            "family_count": self.family_count,
            "resamples": self.resamples,
            "confidence": self.confidence,
        }


def paired_family_bootstrap(
    pairs: Mapping[str, Sequence[float]], *, seed: int
) -> DescriptiveInterval:
    """Return an inert description; raw output is never qualification-capable."""
    if type(seed) is not int:
        raise CampaignMetricsError("seed must be integer")
    families = sorted(pairs)
    if not families:
        return DescriptiveInterval(None, None, None, 0)
    values = []
    for family in families:
        _id(family, "family")
        observations = tuple(pairs[family])
        if not observations:
            raise CampaignMetricsError("unpaired family")
        for observation in observations:
            _num(observation, "paired observation", nullable=False, nonnegative=False)
        values.append(mean(observations))
    rng = Random(seed)
    samples = sorted(
        mean(values[rng.randrange(len(values))] for _ in values)
        for _ in range(BOOTSTRAP_RESAMPLES)
    )
    return DescriptiveInterval(mean(values), samples[249], samples[9749], len(values))


@dataclass(frozen=True, slots=True)
class TaskBinding:
    task_id: str
    family_id: str
    strata: tuple[str, ...]
    repetition_seeds: tuple[int, ...]

    def __post_init__(self) -> None:
        _id(self.task_id, "task")
        _id(self.family_id, "family")
        if (
            not self.strata
            or any(value not in REQUIRED_STRATA for value in self.strata)
            or len(set(self.strata)) != len(self.strata)
        ):
            raise CampaignMetricsError("task has invalid strata")
        if (
            not self.repetition_seeds
            or any(type(seed) is not int for seed in self.repetition_seeds)
            or len(set(self.repetition_seeds)) != len(self.repetition_seeds)
        ):
            raise CampaignMetricsError(
                "task requires distinct integer repetition seeds"
            )

    def to_document(self) -> Mapping[str, object]:
        return {
            "task_id": self.task_id,
            "family_id": self.family_id,
            "strata": self.strata,
            "repetition_seeds": self.repetition_seeds,
        }


@dataclass(frozen=True, slots=True)
class AuthorityBinding:
    evaluator_id: str
    custodian_id: str
    builder_ids: tuple[str, ...]
    affected_champion_ids: tuple[str, ...]
    evaluator_signature_ref: str
    custody_signature_ref: str

    def __post_init__(self) -> None:
        for name in (
            "evaluator_id",
            "custodian_id",
            "evaluator_signature_ref",
            "custody_signature_ref",
        ):
            _id(getattr(self, name), name)
        for name in ("builder_ids", "affected_champion_ids"):
            values = tuple(getattr(self, name))
            if not values or len(values) != len(set(values)):
                raise CampaignMetricsError(f"duplicate {name}")
            for value in values:
                _id(value, name)
            object.__setattr__(self, name, values)
        identities = (
            self.evaluator_id,
            self.custodian_id,
            *self.builder_ids,
            *self.affected_champion_ids,
        )
        if len(set(identities)) != len(identities):
            raise CampaignMetricsError("evaluator/custodian independence violated")

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class FinalistBinding:
    variant_id: str
    candidate_digest: str
    recipe_digest: str
    regime_id: str
    qualification_stage: str
    qualification_seal_digest: str

    def __post_init__(self) -> None:
        for name in ("variant_id", "regime_id"):
            _id(getattr(self, name), name)
        for name in ("candidate_digest", "recipe_digest", "qualification_seal_digest"):
            _digest(getattr(self, name), name)
        if self.qualification_stage not in {"original", "hybrid"}:
            raise CampaignMetricsError("invalid qualification stage")

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class StageEvidence:
    protocol_document_digest: str
    recipe_manifest_digest: str
    stage: str
    block_id: str
    block_digest: str
    task_manifest_digest: str
    family_manifest_digest: str
    manifest_signature_ref: str
    tasks: tuple[TaskBinding, ...]
    principals: AuthorityBinding
    seed: int
    repetitions: int
    stage_opened_at: int
    final_pair: tuple[FinalistBinding, ...] = ()
    holdout_opened_at: int | None = None

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise CampaignMetricsError("invalid stage")
        for name in (
            "protocol_document_digest",
            "recipe_manifest_digest",
            "block_digest",
            "task_manifest_digest",
            "family_manifest_digest",
        ):
            _digest(getattr(self, name), name)
        for name in ("block_id", "manifest_signature_ref"):
            _id(getattr(self, name), name)
        if type(self.seed) is not int:
            raise CampaignMetricsError("stage seed must be integer")
        _timestamp(self.stage_opened_at, "stage_opened_at")
        tasks = tuple(self.tasks)
        object.__setattr__(self, "tasks", tasks)
        expected = FINAL_FAMILIES if self.stage == "final" else SCREENING_FAMILIES
        repetitions = 3 if self.stage == "final" else 1
        if len(tasks) != expected or self.repetitions != repetitions:
            raise CampaignMetricsError("stage family/repetition threshold mismatch")
        if len({task.task_id for task in tasks}) != len(tasks) or len(
            {task.family_id for task in tasks}
        ) != len(tasks):
            raise CampaignMetricsError("stage task/family membership must be unique")
        if any(len(task.repetition_seeds) != repetitions for task in tasks):
            raise CampaignMetricsError("task repetition declaration mismatch")
        if {stratum for task in tasks for stratum in task.strata} != set(
            REQUIRED_STRATA
        ):
            raise CampaignMetricsError("exact thirteen-strata coverage required")
        if self.stage == "final":
            if len(self.final_pair) != 2 or self.holdout_opened_at is None:
                raise CampaignMetricsError("final requires pair and holdout-open time")
            _timestamp(self.holdout_opened_at, "holdout_opened_at")
            if self.holdout_opened_at < self.stage_opened_at:
                raise CampaignMetricsError("holdout opened before final admission")
        elif self.final_pair or self.holdout_opened_at is not None:
            raise CampaignMetricsError("development stage has final custody fields")

    @property
    def evidence_digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class LeaseRecord:
    lease_digest: str
    protocol_id: str
    stage: str
    budget_digest: str
    issued_by: str
    issued_at: int
    expires_at: int
    revoked_at: int | None
    operations: frozenset[str]

    def __post_init__(self) -> None:
        for name in ("lease_digest", "budget_digest"):
            _digest(getattr(self, name), name)
        _id(self.protocol_id, "protocol_id")
        _id(self.issued_by, "lease issuer")
        if self.stage not in STAGES:
            raise CampaignMetricsError("invalid lease stage")
        _timestamp(self.issued_at, "issued_at")
        _timestamp(self.expires_at, "expires_at")
        if self.expires_at <= self.issued_at:
            raise CampaignMetricsError("lease expiry must follow issuance")
        if self.revoked_at is not None:
            _timestamp(self.revoked_at, "revoked_at")
        operations = frozenset(self.operations)
        if not operations or not operations <= set(OPERATIONS):
            raise CampaignMetricsError("invalid lease operations")
        object.__setattr__(self, "operations", operations)

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class VariantSeal:
    protocol_digest: str
    stage_evidence_digest: str
    sequence: int
    variant_id: str
    recipe_digest: str
    candidate_digest: str
    evaluator_id: str
    custodian_id: str
    stage: str
    block_digest: str
    task_manifest_digest: str
    family_manifest_digest: str
    regime_id: str
    sealed_at: int
    signature_ref: str

    def __post_init__(self) -> None:
        for name in (
            "protocol_digest",
            "stage_evidence_digest",
            "recipe_digest",
            "candidate_digest",
            "block_digest",
            "task_manifest_digest",
            "family_manifest_digest",
        ):
            _digest(getattr(self, name), name)
        for name in (
            "variant_id",
            "evaluator_id",
            "custodian_id",
            "regime_id",
            "signature_ref",
        ):
            _id(getattr(self, name), name)
        if (
            self.stage not in STAGES
            or type(self.sequence) is not int
            or self.sequence < 1
        ):
            raise CampaignMetricsError("invalid seal stage/sequence")
        _timestamp(self.sealed_at, "sealed_at")

    @property
    def seal_digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


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
    experiment_manifest: Mapping[str, object]
    closure_receipt_ref: str
    elimination_losses: int = 3
    resource_lease_ref: str = "N30-bounded-lease-required"
    max_rounds: int = 24
    terminal_rules: tuple[str, ...] = TERMINALS

    def __post_init__(self) -> None:
        for name in (
            "protocol_id",
            "version",
            "track_id",
            "candidate_seal_rule",
            "pairing_rule",
            "decision_rule",
            "closure_receipt_ref",
            "resource_lease_ref",
        ):
            _id(getattr(self, name), name)
        if (
            self.elimination_losses != 3
            or self.max_rounds != 24
            or set(self.terminal_rules) != set(TERMINALS)
        ):
            raise CampaignMetricsError("closed tournament rules required")
        entrants = _freeze(self.entrant_recipes)
        hybrids = _freeze(self.hybrid_recipes)
        object.__setattr__(self, "entrant_recipes", entrants)
        object.__setattr__(self, "hybrid_recipes", hybrids)
        object.__setattr__(
            self, "variant_digest_rules", _freeze(self.variant_digest_rules)
        )
        object.__setattr__(
            self, "experiment_manifest", _freeze(self.experiment_manifest)
        )
        object.__setattr__(self, "scenario_task_ids", tuple(self.scenario_task_ids))
        object.__setattr__(self, "dataset_block_ids", tuple(self.dataset_block_ids))
        object.__setattr__(self, "terminal_rules", tuple(self.terminal_rules))
        required = {
            "MB0": "builder-component",
            "MB1": "builder-component",
            "MB2": "builder-component",
            "MB3": "builder-component",
            "MC0": "whole-campaign",
            "MC1": "whole-campaign",
        }
        if set(entrants) != set(required) or set(hybrids) != {
            "MH1",
            "MH2",
            "MH3",
            "MH4",
        }:
            raise CampaignMetricsError("exact MB/MC/MH recipes required")
        behaviors: set[str] = set()
        for variant_id, recipe in {**dict(entrants), **dict(hybrids)}.items():
            if (
                recipe.get("track") != required.get(variant_id, "whole-campaign")
                or recipe.get("availability") != "available"
            ):
                raise CampaignMetricsError(
                    "only available, correctly tracked recipes may close"
                )
            _id(recipe.get("regime_id"), "recipe regime")
            _digest(recipe.get("provenance_digest"), "recipe provenance")
            for recipe_field in RECIPE_FIELDS:
                _digest(recipe.get(recipe_field), recipe_field)
            behavior = self.recipe_digest(variant_id, recipe)
            if behavior in behaviors:
                raise CampaignMetricsError("duplicate complete behavior digest")
            behaviors.add(behavior)
        if (
            len(set(self.scenario_task_ids)) != len(self.scenario_task_ids)
            or len(self.scenario_task_ids) < FINAL_FAMILIES
        ):
            raise CampaignMetricsError("closed protocol needs thirty unique task IDs")
        for task_id in self.scenario_task_ids:
            _id(task_id, "scenario task")
        if set(self.dataset_block_ids) != {
            "development-screening",
            "harder-hybrid-development",
            "promotion_holdout",
        }:
            raise CampaignMetricsError("closed block IDs required")
        manifest = self.experiment_manifest
        required_manifest = {
            "selection_seed",
            "bootstrap_seed",
            "retry_rule",
            "screening_families",
            "final_families",
            "final_repetitions",
            "recipe_manifest_digest",
            "block_manifest_digests",
            "task_manifest_digests",
            "family_manifest_digests",
            "manifest_signature_refs",
            "custody_receipt_ref",
        }
        if set(manifest) != required_manifest:
            raise CampaignMetricsError(
                "closed experiment manifest has missing/extra fields"
            )
        if (
            type(manifest["selection_seed"]) is not int
            or type(manifest["bootstrap_seed"]) is not int
            or manifest["retry_rule"] != "invalidated-only"
            or manifest["screening_families"] != SCREENING_FAMILIES
            or manifest["final_families"] != FINAL_FAMILIES
            or manifest["final_repetitions"] != 3
        ):
            raise CampaignMetricsError("unfrozen experiment parameters")
        _digest(manifest["recipe_manifest_digest"], "recipe manifest")
        for key in (
            "block_manifest_digests",
            "task_manifest_digests",
            "family_manifest_digests",
            "manifest_signature_refs",
        ):
            mapping = manifest[key]
            if not isinstance(mapping, Mapping) or set(mapping) != set(STAGES):
                raise CampaignMetricsError(f"{key} must bind every stage")
            for value in mapping.values():
                _id(value, key) if key == "manifest_signature_refs" else _digest(
                    value, key
                )
        _id(manifest["custody_receipt_ref"], "custody receipt")

    @staticmethod
    def recipe_digest(variant_id: str, recipe: Mapping[str, object]) -> str:
        _id(variant_id, "variant")
        return canonical_digest({field: recipe[field] for field in RECIPE_FIELDS})

    @property
    def protocol_digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    def recipe(self, variant_id: str) -> Mapping[str, object] | None:
        return self.entrant_recipes.get(variant_id) or self.hybrid_recipes.get(
            variant_id
        )


@dataclass(frozen=True, slots=True)
class MatchProtocolInspection:
    document_digest: str
    protocol_id: str
    status: str
    blockers: tuple[str, ...]


def _read_protocol_document(path: str | Path) -> Mapping[str, object]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CampaignMetricsError("protocol document unreadable") from error
    if not isinstance(document, dict):
        raise CampaignMetricsError("protocol document must be object")
    return document


def load_match_protocol_for_inspection(path: str | Path) -> MatchProtocolInspection:
    document = _read_protocol_document(path)
    blockers = tuple(
        sorted(
            str(value) for value in document.get("external_evidence_obligations", ())
        )
    )
    return MatchProtocolInspection(
        canonical_digest(document),
        str(document.get("protocol_id", "UNKNOWN")),
        str(document.get("status", "UNKNOWN")),
        blockers,
    )


def load_match_protocol(path: str | Path) -> MatchProtocol:
    """Pure validation only; a returned document is not execution authority."""
    document = dict(_read_protocol_document(path))
    if document.pop("kind", None) != "hive-mind-closed-match-protocol":
        raise CampaignMetricsError("wrong protocol kind")
    if document.pop("status", None) != "CLOSED_ADMISSION_CANDIDATE":
        raise CampaignMetricsError("OPEN or relabelled protocol is not closed")
    if document.pop("external_evidence_obligations", None):
        raise CampaignMetricsError("closed candidate retains open obligations")
    declared = document.pop("protocol_digest", None)
    protocol = MatchProtocol(**document)
    if declared is not None and declared != protocol.protocol_digest:
        raise CampaignMetricsError("protocol digest mismatch")
    return protocol


@dataclass(frozen=True, slots=True)
class AdmissionUse:
    protocol_digest: str
    stage: str
    operation: str
    state_admission_digest: str | None = None


@dataclass(frozen=True, slots=True)
class AdmissionSnapshot:
    """Registry assertion returned after authenticating one opaque handle."""

    admission_digest: str
    protocol_digest: str
    stage_evidence: StageEvidence
    lease: LeaseRecord
    trusted_lease_issuers: frozenset[str]
    observed_at: int
    seal_history: tuple[VariantSeal, ...] = ()

    def __post_init__(self) -> None:
        _digest(self.admission_digest, "admission")
        _digest(self.protocol_digest, "protocol")
        _timestamp(self.observed_at, "observed_at")
        issuers = frozenset(self.trusted_lease_issuers)
        if not issuers:
            raise CampaignMetricsError("registry supplied no trusted issuer")
        for issuer in issuers:
            _id(issuer, "trusted lease issuer")
        object.__setattr__(self, "trusted_lease_issuers", issuers)
        object.__setattr__(self, "seal_history", tuple(self.seal_history))


@dataclass(frozen=True, slots=True)
class RoundPlanEntry:
    admission_digest: str
    protocol_digest: str
    bracket_digest: str
    stage: str
    round_number: int
    pair_index: int
    left: str
    right: str | None
    bye: bool
    track: str
    regime_id: str
    block_id: str
    block_digest: str
    task_id: str
    family_id: str
    repetition: int
    seed: int
    evaluator_id: str
    custodian_id: str

    def __post_init__(self) -> None:
        if self.bye != (self.right is None) or self.right == self.left:
            raise CampaignMetricsError("invalid pair/bye")
        for name in (
            "admission_digest",
            "protocol_digest",
            "bracket_digest",
            "block_digest",
        ):
            _digest(getattr(self, name), name)
        for name in (
            "left",
            "track",
            "regime_id",
            "block_id",
            "task_id",
            "family_id",
            "evaluator_id",
            "custodian_id",
        ):
            _id(getattr(self, name), name)
        if self.right is not None:
            _id(self.right, "right")
        if (
            self.stage not in STAGES
            or type(self.round_number) is not int
            or self.round_number < 1
            or type(self.pair_index) is not int
            or self.pair_index < 0
            or type(self.repetition) is not int
            or self.repetition < 0
            or type(self.seed) is not int
        ):
            raise CampaignMetricsError("invalid round plan counters/stage")

    @property
    def plan_digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class IssuedReceipt:
    """Registry-bound receipt; ``opaque_handle`` is never interpreted here."""

    opaque_handle: object = field(repr=False, compare=False)
    plan: RoundPlanEntry
    issued_at: int

    def __post_init__(self) -> None:
        if self.opaque_handle is None:
            raise CampaignMetricsError("receipt requires opaque handle")
        _timestamp(self.issued_at, "receipt issued_at")

    @property
    def receipt_digest(self) -> str:
        return canonical_digest({"plan": self.plan, "issued_at": self.issued_at})


@dataclass(frozen=True, slots=True)
class ReceiptOutcome:
    receipt: IssuedReceipt
    outcome: str

    def __post_init__(self) -> None:
        allowed = {
            "LEFT",
            "RIGHT",
            "DRAW",
            "INCONCLUSIVE",
            "QUARANTINE_LEFT",
            "QUARANTINE_RIGHT",
            "QUARANTINE_BOTH",
            "BYE",
        }
        if self.outcome not in allowed or self.receipt.plan.bye != (
            self.outcome == "BYE"
        ):
            raise CampaignMetricsError("invalid outcome for issued receipt")


@dataclass(frozen=True, slots=True)
class ConsumeRoundRequest:
    admission_digest: str
    protocol_digest: str
    stage: str
    round_number: int
    expected_bracket_digest: str
    results: tuple[ReceiptOutcome, ...]
    transition: "BracketTransition"


@dataclass(frozen=True, slots=True)
class FamilyObservation:
    family_id: str
    task_id: str
    repetition: int
    receipt_digest: str
    value: float

    def __post_init__(self) -> None:
        _id(self.family_id, "family")
        _id(self.task_id, "task")
        if type(self.repetition) is not int or self.repetition < 0:
            raise CampaignMetricsError("invalid repetition")
        _digest(self.receipt_digest, "receipt")
        _num(self.value, "observation", nullable=False, nonnegative=False)

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True, order=True)
class ObservationShapeEntry:
    """One independently recheckable admitted task/repetition identity."""

    family_id: str
    task_id: str
    repetition: int
    seed: int

    def __post_init__(self) -> None:
        _id(self.family_id, "family")
        _id(self.task_id, "task")
        if (
            type(self.repetition) is not int
            or self.repetition < 0
            or type(self.seed) is not int
        ):
            raise CampaignMetricsError("invalid observation-shape repetition/seed")

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class AggregateEvidence:
    admission_digest: str
    protocol_digest: str
    stage: str
    track: str
    regime_id: str
    block_digest: str
    task_manifest_digest: str
    family_manifest_digest: str
    observation_shape: tuple[ObservationShapeEntry, ...]
    metric: str
    left: str
    right: str
    observation_digest: str
    interval: DescriptiveInterval
    left_hard_gates: bool
    right_hard_gates: bool

    def __post_init__(self) -> None:
        for name in (
            "admission_digest",
            "protocol_digest",
            "block_digest",
            "task_manifest_digest",
            "family_manifest_digest",
            "observation_digest",
        ):
            _digest(getattr(self, name), name)
        for name in ("track", "regime_id", "metric", "left", "right"):
            _id(getattr(self, name), name)
        if (
            self.stage not in STAGES
            or self.left == self.right
            or type(self.left_hard_gates) is not bool
            or type(self.right_hard_gates) is not bool
        ):
            raise CampaignMetricsError("invalid aggregate binding")
        shape = tuple(self.observation_shape)
        if (
            not shape
            or any(not isinstance(entry, ObservationShapeEntry) for entry in shape)
            or len(shape) != len(set(shape))
        ):
            raise CampaignMetricsError("aggregate requires unique observation shape")
        by_family: dict[str, list[ObservationShapeEntry]] = {}
        for entry in shape:
            by_family.setdefault(entry.family_id, []).append(entry)
        if any(
            len({entry.task_id for entry in entries}) != 1
            or len({entry.repetition for entry in entries}) != len(entries)
            or len({entry.seed for entry in entries}) != len(entries)
            for entries in by_family.values()
        ):
            raise CampaignMetricsError(
                "aggregate observation shape repeats task/repetition/seed"
            )
        object.__setattr__(self, "observation_shape", tuple(sorted(shape)))

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class AggregateReceipt:
    opaque_handle: object = field(repr=False, compare=False)
    aggregate_digest: str

    def __post_init__(self) -> None:
        if self.opaque_handle is None:
            raise CampaignMetricsError("aggregate requires opaque handle")
        _digest(self.aggregate_digest, "aggregate")


class AdmissionRegistry(Protocol):
    """Host-owned authority boundary; implementations are outside this module."""

    def resolve(self, handle: object, use: AdmissionUse) -> AdmissionSnapshot: ...
    def open_bracket(
        self, handle: object, protocol_digest: str, stage: str, track: str
    ) -> "BracketState": ...
    def resolve_bracket(
        self, handle: object, state_handle: object, protocol_digest: str, operation: str
    ) -> "BracketSnapshot": ...
    def issue_round(
        self, handle: object, plans: tuple[RoundPlanEntry, ...]
    ) -> tuple[IssuedReceipt, ...]: ...
    def consume_round(
        self, handle: object, state_handle: object, request: ConsumeRoundRequest
    ) -> "BracketState": ...
    def commit_bracket(
        self,
        handle: object,
        state_handle: object,
        expected_bracket_digest: str,
        transition: "BracketTransition",
    ) -> "BracketState": ...
    def append_seals(
        self,
        handle: object,
        expected_history_digest: str,
        expected_observed_at: int,
        seals: tuple[VariantSeal, ...],
    ) -> None: ...
    def record_aggregate(
        self,
        handle: object,
        evidence: AggregateEvidence,
        observations: tuple[FamilyObservation, ...],
    ) -> AggregateReceipt: ...
    def resolve_aggregate(
        self, handle: object, receipt: AggregateReceipt
    ) -> AggregateEvidence: ...


def _expected_admission_digest(
    protocol: MatchProtocol, evidence: StageEvidence, lease: LeaseRecord
) -> str:
    return canonical_digest(
        {
            "protocol_digest": protocol.protocol_digest,
            "stage_evidence": evidence,
            "lease": lease,
        }
    )


def _resolve(
    registry: AdmissionRegistry,
    handle: object,
    protocol: MatchProtocol,
    stage: str,
    operation: str,
    state_admission_digest: str | None = None,
) -> AdmissionSnapshot:
    if registry is None or handle is None:
        raise CampaignMetricsError("host registry and opaque admission handle required")
    snapshot = registry.resolve(
        handle,
        AdmissionUse(
            protocol.protocol_digest, stage, operation, state_admission_digest
        ),
    )
    if not isinstance(snapshot, AdmissionSnapshot):
        raise CampaignMetricsError("registry returned invalid admission")
    evidence = snapshot.stage_evidence
    lease = snapshot.lease
    manifest = protocol.experiment_manifest
    if (
        snapshot.protocol_digest != protocol.protocol_digest
        or evidence.stage != stage
        or evidence.protocol_document_digest != protocol.protocol_digest
    ):
        raise CampaignMetricsError("foreign protocol/stage admission")
    if snapshot.admission_digest != _expected_admission_digest(
        protocol, evidence, lease
    ):
        raise CampaignMetricsError("incomplete or stale admission identity")
    if (
        state_admission_digest is not None
        and snapshot.admission_digest != state_admission_digest
    ):
        raise CampaignMetricsError("state admission binding changed")
    expected = {
        "recipe_manifest_digest": manifest["recipe_manifest_digest"],
        "block_digest": manifest["block_manifest_digests"][stage],
        "task_manifest_digest": manifest["task_manifest_digests"][stage],
        "family_manifest_digest": manifest["family_manifest_digests"][stage],
        "manifest_signature_ref": manifest["manifest_signature_refs"][stage],
    }
    if any(getattr(evidence, name) != value for name, value in expected.items()):
        raise CampaignMetricsError("admitted manifests/signature do not match protocol")
    if (
        evidence.block_id
        != {
            "original": "development-screening",
            "hybrid": "harder-hybrid-development",
            "final": "promotion_holdout",
        }[stage]
    ):
        raise CampaignMetricsError("stage block label mismatch")
    if lease.protocol_id != protocol.protocol_id or lease.stage != stage:
        raise CampaignMetricsError("lease scope mismatch")
    if lease.issued_by not in snapshot.trusted_lease_issuers:
        raise CampaignMetricsError("untrusted lease issuer")
    if lease.revoked_at is not None and lease.revoked_at <= snapshot.observed_at:
        raise LeaseExhausted("lease revoked")
    if (
        snapshot.observed_at < lease.issued_at
        or snapshot.observed_at >= lease.expires_at
    ):
        raise LeaseExhausted("lease expired or not active")
    if operation not in lease.operations:
        raise CampaignMetricsError("lease does not allow operation")
    if not {task.task_id for task in evidence.tasks} <= set(protocol.scenario_task_ids):
        raise CampaignMetricsError("stage task membership outside protocol")
    if evidence.stage_opened_at > snapshot.observed_at:
        raise CampaignMetricsError("stage has not opened at trusted registry time")
    if evidence.stage == "final":
        if operation == "seal" and snapshot.observed_at >= evidence.holdout_opened_at:  # type: ignore[operator]
            raise CampaignMetricsError("final seal window closed when holdout opened")
        if operation != "seal" and snapshot.observed_at < evidence.holdout_opened_at:  # type: ignore[operator]
            raise CampaignMetricsError("promotion holdout has not opened")
    _validate_final_binding(
        protocol,
        evidence,
        snapshot.seal_history,
        require_final_seals=operation != "seal",
    )
    return snapshot


def _validate_final_binding(
    protocol: MatchProtocol,
    evidence: StageEvidence,
    history: Sequence[VariantSeal],
    *,
    require_final_seals: bool,
) -> None:
    if evidence.stage != "final":
        return
    finalists = evidence.final_pair
    if finalists[0].variant_id == finalists[1].variant_id:
        raise CampaignMetricsError("finalists must be distinct")
    original = [
        entry for entry in finalists if entry.variant_id in protocol.entrant_recipes
    ]
    hybrid = [
        entry for entry in finalists if entry.variant_id in protocol.hybrid_recipes
    ]
    if len(original) != 1 or len(hybrid) != 1:
        raise CampaignMetricsError("final requires original and hybrid")
    recipes = [protocol.recipe(entry.variant_id) for entry in finalists]
    if (
        any(recipe is None or recipe["track"] != "whole-campaign" for recipe in recipes)
        or len({entry.regime_id for entry in finalists}) != 1
    ):
        raise CampaignMetricsError("finalists must share whole-campaign regime")
    for entry, recipe in zip(finalists, recipes):
        assert recipe is not None
        expected_stage = (
            "hybrid" if entry.variant_id in protocol.hybrid_recipes else "original"
        )
        prior = next(
            (
                seal
                for seal in history
                if seal.seal_digest == entry.qualification_seal_digest
            ),
            None,
        )
        if (
            entry.qualification_stage != expected_stage
            or entry.recipe_digest != protocol.recipe_digest(entry.variant_id, recipe)
            or entry.regime_id != recipe["regime_id"]
        ):
            raise CampaignMetricsError("finalist recipe/stage/regime mismatch")
        if (
            prior is None
            or prior.protocol_digest != protocol.protocol_digest
            or prior.variant_id != entry.variant_id
            or prior.stage != expected_stage
            or prior.candidate_digest != entry.candidate_digest
            or prior.recipe_digest != entry.recipe_digest
            or prior.regime_id != entry.regime_id
            or prior.block_digest
            != protocol.experiment_manifest["block_manifest_digests"][expected_stage]
            or prior.task_manifest_digest
            != protocol.experiment_manifest["task_manifest_digests"][expected_stage]
            or prior.family_manifest_digest
            != protocol.experiment_manifest["family_manifest_digests"][expected_stage]
            or prior.evaluator_id != evidence.principals.evaluator_id
            or prior.custodian_id != evidence.principals.custodian_id
            or prior.sealed_at >= evidence.stage_opened_at
        ):
            raise CampaignMetricsError("finalist lacks prior qualification seal")
    finals = [seal for seal in history if seal.stage == "final"]
    if not require_final_seals and not finals:
        return
    if len(finals) != 2:
        raise CampaignMetricsError("final admission requires two pre-open final seals")
    if (
        [seal.sequence for seal in history] != list(range(1, len(history) + 1))
        or any(a.sealed_at >= b.sealed_at for a, b in zip(history, history[1:]))
        or any(seal.sealed_at > evidence.holdout_opened_at for seal in history)
    ):  # type: ignore[operator]
        raise CampaignMetricsError("seal registry history is out of order")
    for entry in finalists:
        final = next(
            (seal for seal in finals if seal.variant_id == entry.variant_id), None
        )
        if (
            final is None
            or final.protocol_digest != protocol.protocol_digest
            or final.stage_evidence_digest != evidence.evidence_digest
            or final.recipe_digest != entry.recipe_digest
            or final.candidate_digest != entry.candidate_digest
            or final.regime_id != entry.regime_id
            or final.block_digest != evidence.block_digest
            or final.task_manifest_digest != evidence.task_manifest_digest
            or final.family_manifest_digest != evidence.family_manifest_digest
            or final.evaluator_id != evidence.principals.evaluator_id
            or final.custodian_id != evidence.principals.custodian_id
            or final.sealed_at < evidence.stage_opened_at
            or final.sealed_at >= evidence.holdout_opened_at
        ):  # type: ignore[operator]
            raise CampaignMetricsError("final pair changed, late, or outside custody")


def _active_variants(
    protocol: MatchProtocol, evidence: StageEvidence, track: str
) -> tuple[str, ...]:
    source = (
        protocol.entrant_recipes
        if evidence.stage == "original"
        else protocol.hybrid_recipes
        if evidence.stage == "hybrid"
        else {
            entry.variant_id: protocol.recipe(entry.variant_id)
            for entry in evidence.final_pair
        }
    )
    return tuple(
        sorted(
            variant
            for variant, recipe in source.items()
            if recipe is not None and recipe["track"] == track
        )
    )


def _observation_shape(evidence: StageEvidence) -> tuple[ObservationShapeEntry, ...]:
    return tuple(
        sorted(
            ObservationShapeEntry(
                task.family_id,
                task.task_id,
                repetition,
                task.repetition_seeds[repetition],
            )
            for task in evidence.tasks
            for repetition in range(evidence.repetitions)
        )
    )


def _compatible(protocol: MatchProtocol, left: str, right: str) -> bool:
    a = protocol.recipe(left)
    b = protocol.recipe(right)
    return bool(
        a and b and a["track"] == b["track"] and a["regime_id"] == b["regime_id"]
    )


def _maximum_pairs(
    protocol: MatchProtocol,
    ordered: tuple[str, ...],
    inconclusive: Mapping[frozenset[str], int],
) -> tuple[tuple[str, str], ...]:
    if len(ordered) < 2:
        return ()
    left = ordered[0]
    best = _maximum_pairs(protocol, ordered[1:], inconclusive)
    for index, right in enumerate(ordered[1:], 1):
        if inconclusive.get(frozenset((left, right)), 0) >= 2 or not _compatible(
            protocol, left, right
        ):
            continue
        candidate = ((left, right),) + _maximum_pairs(
            protocol, ordered[1:index] + ordered[index + 1 :], inconclusive
        )
        if len(candidate) > len(best):
            best = candidate
    return best


@dataclass(frozen=True, slots=True)
class BracketSnapshot:
    """Registry-authenticated bracket history; callers never submit this to execute."""

    protocol_digest: str
    admission_digest: str
    stage: str
    track: str
    round_number: int = 0
    losses: Mapping[str, int] = field(default_factory=dict)
    byes: Mapping[str, int] = field(default_factory=dict)
    inconclusive: Mapping[frozenset[str], int] = field(default_factory=dict)
    quarantined: frozenset[str] = frozenset()
    terminal: str | None = None
    applied_receipt_digests: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _digest(self.protocol_digest, "protocol")
        _digest(self.admission_digest, "admission")
        if self.stage not in STAGES:
            raise CampaignMetricsError("invalid bracket stage")
        _id(self.track, "track")
        if (
            type(self.round_number) is not int
            or not 0 <= self.round_number <= 24
            or self.terminal is not None
            and self.terminal not in TERMINALS
        ):
            raise CampaignMetricsError("invalid bracket round/terminal")
        for name in ("losses", "byes"):
            mapping = dict(getattr(self, name))
            for variant, count in mapping.items():
                _id(variant, name)
                if type(count) is not int or count < 0:
                    raise CampaignMetricsError(f"invalid {name} count")
            object.__setattr__(self, name, MappingProxyType(mapping))
        meetings = dict(self.inconclusive)
        for pair, count in meetings.items():
            if (
                not isinstance(pair, frozenset)
                or len(pair) != 2
                or any(not isinstance(value, str) for value in pair)
                or type(count) is not int
                or count < 0
            ):
                raise CampaignMetricsError("invalid inconclusive matchup")
        object.__setattr__(self, "inconclusive", MappingProxyType(meetings))
        object.__setattr__(self, "quarantined", frozenset(self.quarantined))
        digests = frozenset(self.applied_receipt_digests)
        for digest in digests:
            _digest(digest, "applied receipt")
        object.__setattr__(self, "applied_receipt_digests", digests)

    @property
    def bracket_digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class BracketTransition:
    round_number: int
    losses: Mapping[str, int]
    byes: Mapping[str, int]
    inconclusive: Mapping[frozenset[str], int]
    quarantined: frozenset[str]
    terminal: str | None
    applied_receipt_digests: frozenset[str]

    def __post_init__(self) -> None:
        # Reuse the strict snapshot validator with inert canonical identities.
        BracketSnapshot(
            DUMMY_DIGEST,
            DUMMY_DIGEST,
            "original",
            "validation",
            self.round_number,
            self.losses,
            self.byes,
            self.inconclusive,
            self.quarantined,
            self.terminal,
            self.applied_receipt_digests,
        )

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


DUMMY_DIGEST = "sha256:" + "0" * 64


@dataclass(frozen=True, slots=True)
class BracketState:
    """Opaque registry-owned bracket handle; it carries no caller-editable history."""

    opaque_handle: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.opaque_handle is None:
            raise CampaignMetricsError("bracket requires opaque registry handle")

    def _snapshots(
        self,
        registry: AdmissionRegistry,
        admission_handle: object,
        protocol: MatchProtocol,
        operation: str,
    ) -> tuple[BracketSnapshot, AdmissionSnapshot]:
        bracket = registry.resolve_bracket(
            admission_handle, self.opaque_handle, protocol.protocol_digest, operation
        )
        if (
            not isinstance(bracket, BracketSnapshot)
            or bracket.protocol_digest != protocol.protocol_digest
        ):
            raise CampaignMetricsError("registry returned foreign bracket state")
        admission = _resolve(
            registry,
            admission_handle,
            protocol,
            bracket.stage,
            operation,
            bracket.admission_digest,
        )
        active = set(
            _active_variants(protocol, admission.stage_evidence, bracket.track)
        )
        referenced = (
            set(bracket.losses)
            | set(bracket.byes)
            | set(bracket.quarantined)
            | {variant for pair in bracket.inconclusive for variant in pair}
        )
        if not referenced <= active:
            raise CampaignMetricsError("registry bracket references ineligible entrant")
        return bracket, admission

    def _terminal(
        self,
        registry: AdmissionRegistry,
        admission_handle: object,
        bracket: BracketSnapshot,
        reason: str,
    ) -> "BracketState":
        transition = BracketTransition(
            bracket.round_number,
            bracket.losses,
            bracket.byes,
            bracket.inconclusive,
            bracket.quarantined,
            reason,
            bracket.applied_receipt_digests,
        )
        state = registry.commit_bracket(
            admission_handle, self.opaque_handle, bracket.bracket_digest, transition
        )
        if not isinstance(state, BracketState):
            raise CampaignMetricsError("registry failed bracket terminal commit")
        return state

    def schedule(
        self,
        protocol: MatchProtocol,
        *,
        registry: AdmissionRegistry,
        admission_handle: object,
    ) -> "BracketSchedule":
        try:
            bracket, snapshot = self._snapshots(
                registry, admission_handle, protocol, "schedule"
            )
        except LeaseExhausted:
            bracket = registry.resolve_bracket(
                admission_handle,
                self.opaque_handle,
                protocol.protocol_digest,
                "schedule",
            )
            return BracketSchedule(
                (),
                "lease_exhausted",
                self._terminal(registry, admission_handle, bracket, "lease_exhausted"),
            )
        if bracket.terminal:
            return BracketSchedule((), bracket.terminal, self)
        if bracket.round_number >= protocol.max_rounds:
            return BracketSchedule(
                (),
                "max_rounds",
                self._terminal(registry, admission_handle, bracket, "max_rounds"),
            )
        evidence = snapshot.stage_evidence
        eligible = [
            variant
            for variant in _active_variants(protocol, evidence, bracket.track)
            if variant not in bracket.quarantined
            and bracket.losses.get(variant, 0) < protocol.elimination_losses
        ]
        if len(eligible) == 1:
            return BracketSchedule(
                (),
                "one_survivor",
                self._terminal(registry, admission_handle, bracket, "one_survivor"),
            )
        if not eligible:
            return BracketSchedule(
                (),
                "no_schedulable_pairs",
                self._terminal(
                    registry, admission_handle, bracket, "no_schedulable_pairs"
                ),
            )
        ordered = sorted(
            eligible, key=lambda variant: (bracket.losses.get(variant, 0), variant)
        )
        rotation = bracket.round_number % len(ordered)
        ordered = ordered[rotation:] + ordered[:rotation]
        bye = None
        if len(ordered) % 2:
            bye = min(
                ordered, key=lambda variant: (bracket.byes.get(variant, 0), variant)
            )
            ordered.remove(bye)
        pairs = _maximum_pairs(protocol, tuple(ordered), bracket.inconclusive)
        if not pairs:
            return BracketSchedule(
                (),
                "no_schedulable_pairs",
                self._terminal(
                    registry, admission_handle, bracket, "no_schedulable_pairs"
                ),
            )
        items: tuple[tuple[str, str | None], ...] = (
            (((bye, None),) + pairs) if bye is not None else pairs
        )
        entries = []
        for pair_index, (left, right) in enumerate(items):
            task = evidence.tasks[
                (bracket.round_number + pair_index) % len(evidence.tasks)
            ]
            repetition = bracket.round_number % evidence.repetitions
            recipe = protocol.recipe(left)
            assert recipe is not None
            entries.append(
                RoundPlanEntry(
                    snapshot.admission_digest,
                    protocol.protocol_digest,
                    bracket.bracket_digest,
                    bracket.stage,
                    bracket.round_number + 1,
                    pair_index,
                    left,
                    right,
                    right is None,
                    bracket.track,
                    str(recipe["regime_id"]),
                    evidence.block_id,
                    evidence.block_digest,
                    task.task_id,
                    task.family_id,
                    repetition,
                    task.repetition_seeds[repetition],
                    evidence.principals.evaluator_id,
                    evidence.principals.custodian_id,
                )
            )
        receipts = tuple(registry.issue_round(admission_handle, tuple(entries)))
        if (
            len(receipts) != len(entries)
            or any(
                not isinstance(receipt, IssuedReceipt)
                or receipt.plan != entry
                or not snapshot.observed_at
                <= receipt.issued_at
                < snapshot.lease.expires_at
                for receipt, entry in zip(receipts, entries)
            )
            or len({id(receipt.opaque_handle) for receipt in receipts}) != len(receipts)
        ):
            raise CampaignMetricsError(
                "registry did not issue one exact unique receipt per pair/bye"
            )
        return BracketSchedule(receipts, None, self)

    def apply(
        self,
        protocol: MatchProtocol,
        results: Sequence[ReceiptOutcome],
        *,
        registry: AdmissionRegistry,
        admission_handle: object,
    ) -> "BracketState":
        try:
            bracket, _ = self._snapshots(registry, admission_handle, protocol, "apply")
        except LeaseExhausted:
            if results:
                raise CampaignMetricsError("expired lease cannot consume results")
            bracket = registry.resolve_bracket(
                admission_handle, self.opaque_handle, protocol.protocol_digest, "apply"
            )
            return self._terminal(
                registry, admission_handle, bracket, "lease_exhausted"
            )
        scheduled = self.schedule(
            protocol, registry=registry, admission_handle=admission_handle
        )
        if scheduled.terminal is not None:
            if results:
                raise CampaignMetricsError("terminal schedule cannot accept results")
            return scheduled.state
        submitted = tuple(results)
        expected = {
            id(receipt.opaque_handle): receipt for receipt in scheduled.receipts
        }
        if (
            len(submitted) != len(scheduled.receipts)
            or len({id(result.receipt.opaque_handle) for result in submitted})
            != len(submitted)
            or {id(result.receipt.opaque_handle) for result in submitted}
            != set(expected)
        ):
            raise CampaignMetricsError(
                "results must exactly cover every unique issued receipt"
            )
        for result in submitted:
            issued = expected[id(result.receipt.opaque_handle)]
            if (
                result.receipt.plan != issued.plan
                or result.receipt.receipt_digest != issued.receipt_digest
            ):
                raise CampaignMetricsError("receipt mutated or substituted")
        losses = dict(bracket.losses)
        byes = dict(bracket.byes)
        inconclusive = dict(bracket.inconclusive)
        quarantined = set(bracket.quarantined)
        for result in submitted:
            plan = result.receipt.plan
            if result.outcome == "BYE":
                byes[plan.left] = byes.get(plan.left, 0) + 1
                continue
            assert plan.right is not None
            key = frozenset((plan.left, plan.right))
            if result.outcome == "LEFT":
                losses[plan.right] = losses.get(plan.right, 0) + 1
            elif result.outcome == "RIGHT":
                losses[plan.left] = losses.get(plan.left, 0) + 1
            elif result.outcome == "QUARANTINE_LEFT":
                quarantined.add(plan.left)
            elif result.outcome == "QUARANTINE_RIGHT":
                quarantined.add(plan.right)
            elif result.outcome == "QUARANTINE_BOTH":
                quarantined.update((plan.left, plan.right))
            else:
                inconclusive[key] = inconclusive.get(key, 0) + 1
        next_round = bracket.round_number + 1
        terminal = "max_rounds" if next_round >= protocol.max_rounds else None
        transition = BracketTransition(
            next_round,
            losses,
            byes,
            inconclusive,
            frozenset(quarantined),
            terminal,
            bracket.applied_receipt_digests
            | frozenset(result.receipt.receipt_digest for result in submitted),
        )
        request = ConsumeRoundRequest(
            bracket.admission_digest,
            bracket.protocol_digest,
            bracket.stage,
            bracket.round_number + 1,
            bracket.bracket_digest,
            submitted,
            transition,
        )
        state = registry.consume_round(admission_handle, self.opaque_handle, request)
        if not isinstance(state, BracketState):
            raise CampaignMetricsError("registry failed atomic receipt/state commit")
        return state


@dataclass(frozen=True, slots=True)
class BracketSchedule:
    receipts: tuple[IssuedReceipt, ...]
    terminal: str | None
    state: BracketState

    def __post_init__(self) -> None:
        if self.terminal is not None and (
            self.terminal not in TERMINALS or self.receipts
        ):
            raise CampaignMetricsError("invalid terminal schedule")


def validate_and_append_seals(
    protocol: MatchProtocol,
    seals: Sequence[VariantSeal],
    *,
    registry: AdmissionRegistry,
    admission_handle: object,
) -> None:
    rows = tuple(seals)
    if not rows:
        raise CampaignMetricsError("no seals supplied")
    snapshot = _resolve(registry, admission_handle, protocol, rows[0].stage, "seal")
    evidence = snapshot.stage_evidence
    history = tuple(snapshot.seal_history)
    if history and (
        [seal.sequence for seal in history] != list(range(1, len(history) + 1))
        or any(a.sealed_at >= b.sealed_at for a, b in zip(history, history[1:]))
    ):
        raise CampaignMetricsError("registry seal history is not append-only")
    last_sequence = history[-1].sequence if history else 0
    last_time = history[-1].sealed_at if history else -1
    for offset, seal in enumerate(rows, 1):
        recipe = protocol.recipe(seal.variant_id)
        if (
            recipe is None
            or seal.sequence != last_sequence + offset
            or seal.sealed_at <= last_time
        ):
            raise CampaignMetricsError("seal history/variant invalid")
        last_time = seal.sealed_at
        if (
            seal.protocol_digest != protocol.protocol_digest
            or seal.stage_evidence_digest != evidence.evidence_digest
            or seal.stage != evidence.stage
            or seal.block_digest != evidence.block_digest
            or seal.task_manifest_digest != evidence.task_manifest_digest
            or seal.family_manifest_digest != evidence.family_manifest_digest
            or seal.evaluator_id != evidence.principals.evaluator_id
            or seal.custodian_id != evidence.principals.custodian_id
            or seal.recipe_digest != protocol.recipe_digest(seal.variant_id, recipe)
            or seal.regime_id != recipe["regime_id"]
            or seal.sealed_at < evidence.stage_opened_at
            or seal.sealed_at > snapshot.observed_at
        ):
            raise CampaignMetricsError("seal outside admitted stage/custody")
        if (
            evidence.stage == "original"
            and seal.variant_id not in protocol.entrant_recipes
            or evidence.stage == "hybrid"
            and seal.variant_id not in protocol.hybrid_recipes
        ):
            raise CampaignMetricsError("seal variant/stage mismatch")
        if evidence.stage == "final":
            finalists = {entry.variant_id: entry for entry in evidence.final_pair}
            entry = finalists.get(seal.variant_id)
            if (
                entry is None
                or seal.candidate_digest != entry.candidate_digest
                or seal.recipe_digest != entry.recipe_digest
                or seal.sealed_at >= evidence.holdout_opened_at
            ):  # type: ignore[operator]
                raise CampaignMetricsError(
                    "final seal changed pair or followed holdout open"
                )
    if evidence.stage == "final" and {seal.variant_id for seal in rows} != {
        entry.variant_id for entry in evidence.final_pair
    }:
        raise CampaignMetricsError("final seals must append exact pair together")
    registry.append_seals(
        admission_handle, canonical_digest(history), snapshot.observed_at, rows
    )


def _stage_from_handle(
    registry: AdmissionRegistry, handle: object, protocol: MatchProtocol, operation: str
) -> str:
    for stage in STAGES:
        try:
            snapshot = registry.resolve(
                handle, AdmissionUse(protocol.protocol_digest, stage, operation)
            )
        except CampaignMetricsError:
            continue
        if (
            isinstance(snapshot, AdmissionSnapshot)
            and snapshot.stage_evidence.stage == stage
        ):
            return stage
    raise CampaignMetricsError("opaque admission handle does not resolve")


def stage_paired_bootstrap(
    protocol: MatchProtocol,
    metric: str,
    left: str,
    right: str,
    observations: Sequence[FamilyObservation],
    *,
    left_hard_gates: bool,
    right_hard_gates: bool,
    registry: AdmissionRegistry,
    admission_handle: object,
) -> AggregateReceipt:
    stage = _stage_from_handle(registry, admission_handle, protocol, "aggregate")
    snapshot = _resolve(registry, admission_handle, protocol, stage, "aggregate")
    evidence = snapshot.stage_evidence
    if type(left_hard_gates) is not bool or type(right_hard_gates) is not bool:
        raise CampaignMetricsError("hard gates must be booleans")
    _id(metric, "metric")
    left_recipe = protocol.recipe(left)
    right_recipe = protocol.recipe(right)
    if left == right or left_recipe is None or right_recipe is None:
        raise CampaignMetricsError("invalid aggregate pair")
    active = set(_active_variants(protocol, evidence, str(left_recipe["track"])))
    if (
        left not in active
        or right not in active
        or left_recipe["track"] != right_recipe["track"]
        or left_recipe["regime_id"] != right_recipe["regime_id"]
    ):
        raise CampaignMetricsError(
            "aggregate pair is outside admitted stage/track/regime"
        )
    if stage == "final" and (left, right) != tuple(
        entry.variant_id for entry in evidence.final_pair
    ):
        raise CampaignMetricsError(
            "final aggregate pair differs from admitted finalists"
        )
    rows = tuple(observations)
    expected = {
        (task.family_id, task.task_id, repetition)
        for task in evidence.tasks
        for repetition in range(evidence.repetitions)
    }
    actual = {(row.family_id, row.task_id, row.repetition) for row in rows}
    if (
        len(actual) != len(rows)
        or actual != expected
        or len({row.receipt_digest for row in rows}) != len(rows)
    ):
        raise CampaignMetricsError(
            "observations do not exactly match admitted family/task repetitions"
        )
    grouped: dict[str, list[float]] = {}
    for row in rows:
        if metric == "success_difference" and not -1 <= row.value <= 1:
            raise CampaignMetricsError("success differences must be within [-1, 1]")
        if metric in {"cost_ratio", "time_ratio"} and row.value <= 0:
            raise CampaignMetricsError("cost/time ratios must be strictly positive")
        if metric not in {"success_difference", "cost_ratio", "time_ratio"}:
            raise CampaignMetricsError("unknown qualification metric")
        grouped.setdefault(row.family_id, []).append(row.value)
    interval = paired_family_bootstrap(grouped, seed=evidence.seed)
    record = AggregateEvidence(
        snapshot.admission_digest,
        protocol.protocol_digest,
        stage,
        str(left_recipe["track"]),
        str(left_recipe["regime_id"]),
        evidence.block_digest,
        evidence.task_manifest_digest,
        evidence.family_manifest_digest,
        _observation_shape(evidence),
        metric,
        left,
        right,
        canonical_digest(rows),
        interval,
        left_hard_gates,
        right_hard_gates,
    )
    receipt = registry.record_aggregate(admission_handle, record, rows)
    if not isinstance(
        receipt, AggregateReceipt
    ) or receipt.aggregate_digest != canonical_digest(record):
        raise CampaignMetricsError("registry returned invalid aggregate receipt")
    return receipt


def decide_match(
    protocol: MatchProtocol,
    success: AggregateReceipt,
    cost_ratio: AggregateReceipt,
    time_ratio: AggregateReceipt,
    *,
    registry: AdmissionRegistry,
    admission_handle: object,
) -> str:
    if not all(
        isinstance(receipt, AggregateReceipt)
        for receipt in (success, cost_ratio, time_ratio)
    ):
        raise CampaignMetricsError(
            "qualification decisions require registry aggregate receipts"
        )
    stage = _stage_from_handle(registry, admission_handle, protocol, "decide")
    snapshot = _resolve(registry, admission_handle, protocol, stage, "decide")
    aggregates = tuple(
        registry.resolve_aggregate(admission_handle, receipt)
        for receipt in (success, cost_ratio, time_ratio)
    )
    expected_metrics = ("success_difference", "cost_ratio", "time_ratio")
    first = aggregates[0]
    expected_shape = _observation_shape(snapshot.stage_evidence)
    expected_family_count = len({entry.family_id for entry in expected_shape})
    for aggregate, metric in zip(aggregates, expected_metrics):
        if (
            not isinstance(aggregate, AggregateEvidence)
            or aggregate.metric != metric
            or aggregate.admission_digest != snapshot.admission_digest
            or aggregate.protocol_digest != protocol.protocol_digest
            or aggregate.stage != stage
            or aggregate.track != first.track
            or aggregate.regime_id != first.regime_id
            or aggregate.block_digest != snapshot.stage_evidence.block_digest
            or aggregate.task_manifest_digest
            != snapshot.stage_evidence.task_manifest_digest
            or aggregate.family_manifest_digest
            != snapshot.stage_evidence.family_manifest_digest
            or aggregate.observation_shape != expected_shape
            or aggregate.interval.family_count != expected_family_count
            or (aggregate.left, aggregate.right) != (first.left, first.right)
            or aggregate.left_hard_gates != first.left_hard_gates
            or aggregate.right_hard_gates != first.right_hard_gates
        ):
            raise CampaignMetricsError("qualification aggregates are not co-bound")
    left_recipe = protocol.recipe(first.left)
    right_recipe = protocol.recipe(first.right)
    if (
        left_recipe is None
        or right_recipe is None
        or first.track != left_recipe["track"]
        or first.track != right_recipe["track"]
        or first.regime_id != left_recipe["regime_id"]
        or first.regime_id != right_recipe["regime_id"]
    ):
        raise CampaignMetricsError("aggregate receipt has invalid track/regime")
    if stage == "final" and (first.left, first.right) != tuple(
        entry.variant_id for entry in snapshot.stage_evidence.final_pair
    ):
        raise CampaignMetricsError("decision pair differs from admitted finalists")
    success_i, cost_i, time_i = (item.interval for item in aggregates)
    if success_i.lower is not None and (success_i.lower < -1 or success_i.upper > 1):  # type: ignore[operator]
        raise CampaignMetricsError(
            "success interval outside probability-difference domain"
        )
    if any(
        value is not None and value <= 0
        for interval in (cost_i, time_i)
        for value in (interval.estimate, interval.lower, interval.upper)
    ):
        raise CampaignMetricsError(
            "cost/time ratio intervals must be strictly positive"
        )
    if not first.left_hard_gates and not first.right_hard_gates:
        return "QUARANTINE_BOTH"
    if not first.left_hard_gates:
        return "QUARANTINE_LEFT"
    if not first.right_hard_gates:
        return "QUARANTINE_RIGHT"
    if success_i.lower is None:
        return "INCONCLUSIVE"
    if success_i.lower > 0:
        return "LEFT"
    if success_i.upper < 0:
        return "RIGHT"  # type: ignore[operator]
    if not (
        success_i.lower > NONINFERIORITY_MARGIN
        and -success_i.upper > NONINFERIORITY_MARGIN
    ):
        return "DRAW"  # type: ignore[operator]
    if None in (cost_i.lower, cost_i.upper, time_i.lower, time_i.upper):
        return "INCONCLUSIVE"
    if (cost_i.upper < 1 and time_i.upper <= 1.10) or (
        time_i.upper < 1 and cost_i.upper <= 1.10
    ):
        return "LEFT"
    if (cost_i.lower > 1 and time_i.lower >= 1 / 1.10) or (
        time_i.lower > 1 and cost_i.lower >= 1 / 1.10
    ):
        return "RIGHT"
    return "DRAW"


__all__ = [
    "AdmissionRegistry",
    "AdmissionSnapshot",
    "AdmissionUse",
    "AggregateEvidence",
    "AggregateReceipt",
    "AttemptMetric",
    "AuthorityBinding",
    "BracketSchedule",
    "BracketSnapshot",
    "BracketState",
    "BracketTransition",
    "CampaignMetricsError",
    "ConsumeRoundRequest",
    "DescriptiveInterval",
    "FamilyObservation",
    "FinalistBinding",
    "IssuedReceipt",
    "LeaseExhausted",
    "LeaseRecord",
    "MatchProtocol",
    "MatchProtocolInspection",
    "ObservationShapeEntry",
    "RECIPE_FIELDS",
    "REQUIRED_STRATA",
    "ReceiptOutcome",
    "RoundPlanEntry",
    "StageEvidence",
    "TaskBinding",
    "VariantSeal",
    "canonical_digest",
    "decide_match",
    "load_match_protocol",
    "load_match_protocol_for_inspection",
    "paired_family_bootstrap",
    "stage_paired_bootstrap",
    "summarize_attempts",
    "validate_and_append_seals",
]
