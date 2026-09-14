"""Separate target-app and Hive OS learning routes (N25)."""

from dataclasses import dataclass
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

    @property
    def digest(self):
        return canonical_digest(self)


class ChampionRegistry:
    def __init__(self):
        self._champions = {}

    def current(self, subject):
        return self._champions.get(subject)

    def promote(self, subject, challenger, expected_parent):
        old = self._champions.get(subject)
        if old is not None and old != expected_parent:
            raise ValueError("stale champion")
        self._champions[subject] = challenger
        return challenger


class DurableChampionRegistry(ChampionRegistry):
    def __init__(self, path):
        super().__init__()
        self._store = ContractStore(path, lambda v: v)

    def promote(self, subject, challenger, expected_parent):
        result = super().promote(subject, challenger, expected_parent)
        self._store.put(
            subject,
            {
                "subject": subject,
                "challenger": challenger.digest,
                "parent": challenger.parent_digest,
                "state": challenger.promotion_state.value,
            },
        )
        return result
