"""Private, content-addressed lesson draft lifecycle (N20)."""
from dataclasses import dataclass, replace
from enum import StrEnum
from datetime import datetime, timezone
from .brain_kernel.canonical import canonical_digest
class DraftError(ValueError): pass
class ProcessingState(StrEnum):
 CAPTURED_PRIVATE="CAPTURED_PRIVATE"; CANDIDATE_PRIVATE="CANDIDATE_PRIVATE"; SANITIZED_DRAFT="SANITIZED_DRAFT"; REVIEWED_DRAFT="REVIEWED_DRAFT"; COMMITTED_DRAFT="COMMITTED_DRAFT"; DRAFT_PR_OPEN="DRAFT_PR_OPEN"; BLOCKED_EXPORT_DESTINATION="BLOCKED_EXPORT_DESTINATION"; BLOCKED_EXPORT_AUTHORITY="BLOCKED_EXPORT_AUTHORITY"; QUARANTINED_EXPORT="QUARANTINED_EXPORT"; EXPORT_FAILED_RETRYABLE="EXPORT_FAILED_RETRYABLE"
@dataclass(frozen=True, slots=True)
class LessonDraft:
 draft_id:str; document_status:str; processing_state:ProcessingState; origin_subject_token:str; origin_mission_token:str; statement:str; applicability:tuple[str,...]; outcome_class:str; evidence_tokens:tuple[str,...]; private_custody_token:str; confidence_basis:str; counterexamples:tuple[str,...]; disposition_refs:tuple[str,...]; generator_id:str; reviewer_id:str|None; sanitization_receipt_digest:str|None; export_policy_digest:str; withheld_reason_code:str|None; created_at:str
 def __post_init__(self):
  if self.document_status!="DRAFT": raise DraftError("document_status is immutable and must be DRAFT")
  if len(self.statement)>2000 or len(self.applicability)>20 or len(self.counterexamples)>20: raise DraftError("draft bounds exceeded")
  if self.processing_state is ProcessingState.REVIEWED_DRAFT and (not self.reviewer_id or not self.sanitization_receipt_digest): raise DraftError("reviewed draft requires reviewer and sanitization receipt")
 @property
 def digest(self): return canonical_digest(self)
 def transition(self,state,**changes):
  if state is ProcessingState.REVIEWED_DRAFT and (not changes.get("reviewer_id",self.reviewer_id) or not changes.get("sanitization_receipt_digest",self.sanitization_receipt_digest)): raise DraftError("review evidence required")
  return replace(self,processing_state=state,**changes)
def create_draft(**kwargs):
 kwargs.setdefault("document_status","DRAFT"); kwargs.setdefault("created_at",datetime.now(timezone.utc).isoformat()); kwargs.setdefault("reviewer_id",None); kwargs.setdefault("sanitization_receipt_digest",None); return LessonDraft(**kwargs)
