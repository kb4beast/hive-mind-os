"""Incremental, untrusted PR feedback triage with cursor and head binding."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .brain_kernel.canonical import canonical_digest
class FeedbackDecision(str,Enum): DUPLICATE="DUPLICATE"; STALE_HEAD="STALE_HEAD"; ACTIONABLE="ACTIONABLE"; NEEDS_CLARIFICATION="NEEDS_CLARIFICATION"; AUTHORITY_CHANGE="AUTHORITY_CHANGE"; INFORMATIONAL="INFORMATIONAL"
@dataclass(frozen=True,slots=True)
class FeedbackObservation:
    provider:str; pr_id:str; head:str; event_id:str; source_identity:str; observed_at:float; status:str; content_digest:str; evidence_refs:tuple[str,...]=()
@dataclass(frozen=True,slots=True)
class FeedbackResult:
    decision:FeedbackDecision; reason:str; package_id:str|None=None
class FeedbackObserver:
    def __init__(self): self.cursor=None; self.seen=set(); self.repairs={}
    def observe(self,o:FeedbackObservation,current_head:str)->FeedbackResult:
        key=(o.provider,o.pr_id,o.event_id,o.content_digest)
        if key in self.seen:return FeedbackResult(FeedbackDecision.DUPLICATE,"event already observed")
        self.seen.add(key); self.cursor=o.event_id
        if o.head != current_head:return FeedbackResult(FeedbackDecision.STALE_HEAD,"feedback is bound to an older head")
        text=o.status.lower()
        if any(x in text for x in ("permission","credential","access")): return FeedbackResult(FeedbackDecision.AUTHORITY_CHANGE,"provider requested authority change")
        if any(x in text for x in ("fail","error","request changes","bug")):
            package="repair-"+canonical_digest(o)[7:19]; self.repairs[package]=o; return FeedbackResult(FeedbackDecision.ACTIONABLE,"reproducible feedback candidate",package)
        return FeedbackResult(FeedbackDecision.INFORMATIONAL,"no actionable change")
