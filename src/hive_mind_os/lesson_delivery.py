"""Durable lessons-only publication obligation (N21)."""
from dataclasses import dataclass
from enum import StrEnum
class ObligationState(StrEnum): REQUIRED="REQUIRED"; RETAINED_DRAFT="RETAINED_DRAFT"; COMMITTED_DRAFT="COMMITTED_DRAFT"; UPSTREAM_PENDING="UPSTREAM_PENDING"; DRAFT_PR_OPEN="DRAFT_PR_OPEN"; BLOCKED_EXPORT_AUTHORITY="BLOCKED_EXPORT_AUTHORITY"; BLOCKED_EXPORT_DESTINATION="BLOCKED_EXPORT_DESTINATION"; EXPORT_FAILED_RETRYABLE="EXPORT_FAILED_RETRYABLE"; QUARANTINED_EXPORT="QUARANTINED_EXPORT"
@dataclass(frozen=True, slots=True)
class LessonDeliveryObligation:
 external_mission_id:str; origin_mission_token:str; subject_id:str; safe_draft_digest:str; local_artifact_path:str; local_commit_sha:str|None; upstream_repository_id:str|None; upstream_path:str|None; export_authority_digest:str|None; delivery_idempotency_key:str; obligation_state:ObligationState=ObligationState.REQUIRED; upstream_pr_url:str|None=None; upstream_head_sha:str|None=None; failure_code:str|None=None
class DeliveryLedger:
 def __init__(self): self._items={}
 def admit(self,item):
  key=item.subject_id+":"+item.external_mission_id
  if key in self._items and self._items[key].safe_draft_digest!=item.safe_draft_digest: raise ValueError("mission obligation already exists")
  self._items.setdefault(key,item); return self._items[key]
 def get(self,subject_id,mission_id): return self._items.get(subject_id+":"+mission_id)
