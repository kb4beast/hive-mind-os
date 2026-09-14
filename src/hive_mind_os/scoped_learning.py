"""Separate target-app and Hive OS learning routes (N25)."""

from dataclasses import dataclass, replace
from enum import StrEnum

from .brain_kernel.canonical import canonical_digest, canonical_document
from .durable_contracts import ContractStore


class LearningScope(StrEnum):
    TARGET_APP = "target_app"
    HIVE_OS = "hive_os"
    EXPORT_DRAFT = "export_draft"


class PromotionState(StrEnum):
    PROPOSED = "PROPOSED"
    EVALUATING = "EVALUATING"
    RETAIN_CHAMPION = "RETAIN_CHAMPION"
    ELIGIBLE = "ELIGIBLE"
    PROMOTED = "PROMOTED"
    ROLLED_BACK = "ROLLED_BACK"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class LearningRoute:
    origin_subject_id: str
    learning_scope: LearningScope
    destination_subject_id: str
    source_evidence_refs: tuple[str, ...]
    candidate_kind: str
    authorization_digest: str
    accepted_lesson_digest: str

    def __post_init__(self):
        required = (
            self.origin_subject_id,
            self.destination_subject_id,
            self.candidate_kind,
            self.authorization_digest,
            self.accepted_lesson_digest,
        )
        if any(type(value) is not str or not value.strip() for value in required):
            raise ValueError("learning route identity and authority are required")
        if not self.source_evidence_refs:
            raise ValueError("learning route requires retained source evidence")
        if (
            self.learning_scope is LearningScope.TARGET_APP
            and self.origin_subject_id != self.destination_subject_id
        ):
            raise ValueError("target learning cannot cross subjects")
        if (
            self.learning_scope is LearningScope.EXPORT_DRAFT
            and not self.accepted_lesson_digest
        ):
            raise ValueError("export requires lesson digest")

    @property
    def digest(self):
        return canonical_digest(self)

    def to_dict(self):
        return canonical_document(self)


@dataclass(frozen=True, slots=True)
class ScopedChallenger:
    subject_boundary_digest: str
    champion_id: str
    parent_digest: str
    candidate_digest: str
    evaluation_plan_digest: str
    evaluator_id: str
    verdict_ref: str
    promotion_state: PromotionState

    def __post_init__(self):
        if not isinstance(self.promotion_state, PromotionState):
            object.__setattr__(
                self, "promotion_state", PromotionState(self.promotion_state)
            )
        required = (
            self.subject_boundary_digest,
            self.champion_id,
            self.parent_digest,
            self.candidate_digest,
            self.evaluation_plan_digest,
            self.evaluator_id,
            self.verdict_ref,
        )
        if any(type(value) is not str or not value.strip() for value in required):
            raise ValueError("challenger identity and evidence are required")
        if self.evaluator_id == self.champion_id:
            raise ValueError("challenger evaluator must be independent")

    @property
    def digest(self):
        return canonical_digest(self)

    def to_dict(self):
        return canonical_document(self)

    @classmethod
    def from_dict(cls, value):
        if set(value) != set(cls.__dataclass_fields__):
            raise ValueError("closed scoped challenger schema")
        return cls(
            **{
                **value,
                "promotion_state": PromotionState(value["promotion_state"]),
            }
        )


class ChampionRegistry:
    def __init__(self):
        self._champions = {}

    def current(self, subject):
        return self._champions.get(subject)

    def promote(self, subject, challenger, expected_parent):
        if challenger.subject_boundary_digest != subject:
            raise ValueError("challenger belongs to another subject boundary")
        if challenger.promotion_state is not PromotionState.ELIGIBLE:
            raise ValueError("only an independently eligible challenger can promote")
        if challenger.parent_digest != expected_parent:
            raise ValueError("challenger parent does not match compare-and-swap input")
        old = self._champions.get(subject)
        if old is not None and old.candidate_digest != expected_parent:
            raise ValueError("stale champion")
        promoted = replace(challenger, promotion_state=PromotionState.PROMOTED)
        self._champions[subject] = promoted
        return promoted


class DurableChampionRegistry(ChampionRegistry):
    def __init__(self, path):
        super().__init__()
        self._store = ContractStore(path, ScopedChallenger.from_dict)

    def current(self, subject):
        return self._store.get(subject) or super().current(subject)

    def promote(self, subject, challenger, expected_parent):
        result = super().promote(subject, challenger, expected_parent)
        self._store.put(subject, result)
        return result
