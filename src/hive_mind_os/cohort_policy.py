"""Fail-closed policy contract for end-loaded cohort execution.

This module changes *when* routine assurance is collected, never whether it is
required.  A cohort may implement reversible packages in parallel and batch
routine review at convergence.  Authority and irreversible-effect boundaries
remain synchronous stops.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Mapping

from .policy import Action
from .runtime_contracts import canonical_digest


class CohortPolicyError(ValueError):
    """Raised when an execution policy document is malformed or weakened."""


class CohortExecutionMode(StrEnum):
    STRICT = "strict"
    COHORT = "cohort"


class CohortPhase(StrEnum):
    IMPLEMENTATION = "implementation"
    CONVERGENCE = "convergence"
    CLOSEOUT = "closeout"


class EffectClass(StrEnum):
    ROUTINE_REVERSIBLE = "routine_reversible"
    SECRET_ACCESS = "secret_access"
    DESTRUCTIVE = "destructive"
    IRREVERSIBLE = "irreversible"
    MISSING_AUTHORITY = "missing_authority"
    SPENDING = "spending"
    DEPLOYMENT = "deployment"
    PROTECTED_MERGE = "protected_merge"


class DeferredObligation(StrEnum):
    ROUTINE_REVIEW = "routine_review"
    EVIDENCE_AGGREGATION = "evidence_aggregation"
    INDEPENDENT_VERIFICATION = "independent_verification"


class CheckpointDisposition(StrEnum):
    PROCEED = "proceed"
    DEFER_TO_COHORT_END = "defer_to_cohort_end"
    REQUIRE_NOW = "require_now"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class CheckpointDecision:
    disposition: CheckpointDisposition
    effect: EffectClass
    phase: CohortPhase
    reason: str
    obligations: tuple[DeferredObligation, ...] = ()

    @property
    def may_continue(self) -> bool:
        return self.disposition in {
            CheckpointDisposition.PROCEED,
            CheckpointDisposition.DEFER_TO_COHORT_END,
        }


@dataclass(frozen=True, slots=True)
class CohortExecutionPolicy:
    """Immutable execution scheduling policy with non-configurable hard gates."""

    mode: CohortExecutionMode = CohortExecutionMode.STRICT
    max_parallel_packages: int = 1

    CONVERGENCE_GATE: ClassVar[str] = "all_runnable_packages_terminal"
    HARD_GATE_EFFECTS: ClassVar[frozenset[EffectClass]] = frozenset(
        {
            EffectClass.SECRET_ACCESS,
            EffectClass.DESTRUCTIVE,
            EffectClass.IRREVERSIBLE,
            EffectClass.MISSING_AUTHORITY,
            EffectClass.SPENDING,
            EffectClass.DEPLOYMENT,
            EffectClass.PROTECTED_MERGE,
        }
    )
    END_LOADED_OBLIGATIONS: ClassVar[tuple[DeferredObligation, ...]] = (
        DeferredObligation.ROUTINE_REVIEW,
        DeferredObligation.EVIDENCE_AGGREGATION,
        DeferredObligation.INDEPENDENT_VERIFICATION,
    )

    def __post_init__(self) -> None:
        if type(self.mode) is not CohortExecutionMode:
            raise CohortPolicyError("execution mode must be typed")
        if (
            not isinstance(self.max_parallel_packages, int)
            or isinstance(self.max_parallel_packages, bool)
            or self.max_parallel_packages < 1
        ):
            raise CohortPolicyError("max_parallel_packages must be a positive integer")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "execution_mode": self.mode.value,
            "max_parallel_packages": self.max_parallel_packages,
            "convergence_gate": self.CONVERGENCE_GATE,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> "CohortExecutionPolicy":
        required = {
            "schema_version",
            "execution_mode",
            "max_parallel_packages",
            "convergence_gate",
        }
        if set(document) != required or document.get("schema_version") != 1:
            raise CohortPolicyError("cohort execution policy has an unknown shape or schema")
        if document.get("convergence_gate") != cls.CONVERGENCE_GATE:
            raise CohortPolicyError("the cohort convergence gate cannot be weakened")
        maximum = document.get("max_parallel_packages")
        if not isinstance(maximum, int) or isinstance(maximum, bool):
            raise CohortPolicyError("max_parallel_packages must be an integer")
        try:
            mode = CohortExecutionMode(document["execution_mode"])
        except (TypeError, ValueError) as exc:
            raise CohortPolicyError("unknown cohort execution mode") from exc
        return cls(mode=mode, max_parallel_packages=maximum)

    def checkpoint(
        self,
        effect: EffectClass,
        phase: CohortPhase,
        *,
        authority_present: bool = True,
    ) -> CheckpointDecision:
        """Return whether work proceeds, waits for assurance, or fails closed."""

        if type(effect) is not EffectClass or type(phase) is not CohortPhase:
            return CheckpointDecision(
                CheckpointDisposition.BLOCKED,
                EffectClass.MISSING_AUTHORITY,
                CohortPhase.IMPLEMENTATION,
                "untyped checkpoint input is denied",
            )
        if authority_present is not True:
            effect = EffectClass.MISSING_AUTHORITY
        if effect in self.HARD_GATE_EFFECTS:
            return CheckpointDecision(
                CheckpointDisposition.BLOCKED,
                effect,
                phase,
                f"{effect.value} requires an immediate fail-closed gate",
            )
        if self.mode is CohortExecutionMode.COHORT and phase is CohortPhase.IMPLEMENTATION:
            return CheckpointDecision(
                CheckpointDisposition.DEFER_TO_COHORT_END,
                effect,
                phase,
                "routine reversible assurance is batched at cohort convergence",
                self.END_LOADED_OBLIGATIONS,
            )
        return CheckpointDecision(
            CheckpointDisposition.REQUIRE_NOW,
            effect,
            phase,
            "routine assurance is required at this checkpoint",
            self.END_LOADED_OBLIGATIONS,
        )

    def checkpoint_action(
        self,
        action: Action,
        phase: CohortPhase,
        *,
        authority_present: bool = True,
        protected_target: bool = False,
        destructive: bool = False,
        irreversible: bool = False,
    ) -> CheckpointDecision:
        """Classify an existing policy action without granting it authority."""

        effect = self.classify_action(
            action,
            authority_present=authority_present,
            protected_target=protected_target,
            destructive=destructive,
            irreversible=irreversible,
        )
        return self.checkpoint(effect, phase, authority_present=authority_present)

    @staticmethod
    def classify_action(
        action: Action,
        *,
        authority_present: bool = True,
        protected_target: bool = False,
        destructive: bool = False,
        irreversible: bool = False,
    ) -> EffectClass:
        if type(action) is not Action or authority_present is not True:
            return EffectClass.MISSING_AUTHORITY
        if action is Action.MANAGE_SECRETS:
            return EffectClass.SECRET_ACCESS
        if action is Action.SPEND_MONEY:
            return EffectClass.SPENDING
        if action is Action.DEPLOY:
            return EffectClass.DEPLOYMENT
        if action is Action.MERGE_PULL_REQUEST and protected_target:
            return EffectClass.PROTECTED_MERGE
        if destructive:
            return EffectClass.DESTRUCTIVE
        if irreversible:
            return EffectClass.IRREVERSIBLE
        return EffectClass.ROUTINE_REVERSIBLE
