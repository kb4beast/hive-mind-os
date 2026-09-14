"""Evaluator custody seal for endpoint episodes (N23)."""

from dataclasses import dataclass
from enum import StrEnum

from .brain_kernel.canonical import canonical_digest, canonical_document
from .durable_contracts import ContractStore


class CustodyError(ValueError):
    pass


class CustodyState(StrEnum):
    INPUT_SEALED = "INPUT_SEALED"
    LEARNER_RUNNING = "LEARNER_RUNNING"
    CANDIDATE_SEALED = "CANDIDATE_SEALED"
    EVALUATOR_RUNNING = "EVALUATOR_RUNNING"
    CONTAMINATED = "CONTAMINATED"
    BLOCKED_ENVIRONMENT = "BLOCKED_ENVIRONMENT"


@dataclass(frozen=True, slots=True)
class EndpointSeal:
    episode_id: str
    input_manifest_digest: str
    candidate_tree_digest: str
    learner_variant_digest: str
    prompt_memory_digest: str
    tool_profile_digest: str
    rubric_digest: str
    budget_digest: str
    learner_id: str
    evaluator_id: str
    sealed_at: str
    seal_digest: str | None = None

    def __post_init__(self):
        if self.learner_id == self.evaluator_id:
            raise CustodyError("learner and evaluator must differ")
        if self.seal_digest is not None and self.seal_digest != self.seal():
            raise CustodyError("seal digest mismatch")

    def seal(self):
        document = canonical_document(self)
        document.pop("seal_digest", None)
        return canonical_digest(document)

    def to_dict(self):
        from .brain_kernel.canonical import canonical_document

        return canonical_document(self)

    @classmethod
    def from_dict(cls, value):
        fields = {
            "episode_id",
            "input_manifest_digest",
            "candidate_tree_digest",
            "learner_variant_digest",
            "prompt_memory_digest",
            "tool_profile_digest",
            "rubric_digest",
            "budget_digest",
            "learner_id",
            "evaluator_id",
            "sealed_at",
            "seal_digest",
        }
        if set(value) != fields:
            raise CustodyError("closed endpoint seal schema")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class CustodyReceipt:
    store_id: str
    access_policy_digest: str
    object_inventory_digest: str
    contamination_probes: tuple[str, ...]
    status: CustodyState


def reject_changed_candidate(seal: EndpointSeal, candidate_digest: str):
    if seal.candidate_tree_digest != candidate_digest:
        raise CustodyError("candidate changed after seal")


class EndpointSealStore:
    def __init__(self, path):
        self._store = ContractStore(path, EndpointSeal.from_dict)

    def seal_once(self, seal):
        key = seal.episode_id
        old = self._store.get(key)
        if old and old.seal() != seal.seal():
            raise CustodyError("episode already sealed with different inputs")
        return self._store.put(key, seal)

    def get(self, episode_id):
        return self._store.get(episode_id)
