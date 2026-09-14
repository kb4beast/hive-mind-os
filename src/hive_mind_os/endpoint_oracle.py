"""Evaluator custody seal for endpoint episodes (N23)."""
from dataclasses import dataclass
from enum import StrEnum
from .brain_kernel.canonical import canonical_digest
class CustodyError(ValueError): pass
class CustodyState(StrEnum): INPUT_SEALED="INPUT_SEALED"; LEARNER_RUNNING="LEARNER_RUNNING"; CANDIDATE_SEALED="CANDIDATE_SEALED"; EVALUATOR_RUNNING="EVALUATOR_RUNNING"; CONTAMINATED="CONTAMINATED"; BLOCKED_ENVIRONMENT="BLOCKED_ENVIRONMENT"
@dataclass(frozen=True, slots=True)
class EndpointSeal:
 episode_id:str; input_manifest_digest:str; candidate_tree_digest:str; learner_variant_digest:str; prompt_memory_digest:str; tool_profile_digest:str; rubric_digest:str; budget_digest:str; learner_id:str; evaluator_id:str; sealed_at:str; seal_digest:str|None=None
 def __post_init__(self):
  if self.learner_id==self.evaluator_id: raise CustodyError("learner and evaluator must differ")
  if self.seal_digest is not None and self.seal_digest!=canonical_digest(self): raise CustodyError("seal digest mismatch")
 def seal(self): return canonical_digest(self)
@dataclass(frozen=True, slots=True)
class CustodyReceipt:
 store_id:str; access_policy_digest:str; object_inventory_digest:str; contamination_probes:tuple[str,...]; status:CustodyState
def reject_changed_candidate(seal:EndpointSeal,candidate_digest:str):
 if seal.candidate_tree_digest!=candidate_digest: raise CustodyError("candidate changed after seal")
