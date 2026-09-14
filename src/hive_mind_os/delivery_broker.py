"""Separate, grant-checked delivery boundary for qualified artifacts."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol
from .brain_kernel.canonical import canonical_digest
class DeliveryState(str,Enum): LOCAL_ARTIFACT_READY="LOCAL_ARTIFACT_READY"; PUSH_PENDING="PUSH_PENDING"; PR_PENDING="PR_PENDING"; PUBLISHED="PUBLISHED"; RECONCILIATION_REQUIRED="RECONCILIATION_REQUIRED"; BLOCKED="BLOCKED"
class ArtifactKind(str,Enum): APPLICATION="application"; LESSONS_ONLY="lessons-only"
@dataclass(frozen=True,slots=True)
class DeliveryRequest:
    request_id:str; package_id:str; tenant_id:str; candidate_commit:str; candidate_tree:str; qualification_digest:str; target:str; base:str; run_branch:str; grant_ref:str; artifact_kind:ArtifactKind; content_digest:str; idempotency_key:str; changed_paths:tuple[str,...]=()
@dataclass(frozen=True,slots=True)
class DeliveryResult:
    state:DeliveryState; request_digest:str; branch_head:str|None=None; pr_id:str|None=None; blocker:str|None=None
class DeliveryTransport(Protocol):
    def push(self, branch:str, commit:str)->str: ...
    def find_or_create_draft(self, branch:str, base:str, title:str, body:str)->str: ...
class DeliveryBroker:
    def __init__(self, transport:DeliveryTransport|None=None, *, grants:dict[str,Any]|None=None): self.transport=transport; self.grants=grants or {}; self.results={}
    def prepare(self,r:DeliveryRequest)->DeliveryResult:
        digest=canonical_digest(r)
        if r.artifact_kind is ArtifactKind.LESSONS_ONLY and any(p.endswith(('.py','.js','.ts','.go','.rs')) for p in r.changed_paths): return DeliveryResult(DeliveryState.BLOCKED,digest,blocker="lessons artifact contains code")
        grant=self.grants.get(r.grant_ref)
        if grant is None: return DeliveryResult(DeliveryState.LOCAL_ARTIFACT_READY,digest,blocker="delivery grant unavailable")
        if self.transport is None: return DeliveryResult(DeliveryState.LOCAL_ARTIFACT_READY,digest,blocker="delivery transport unavailable")
        if r.idempotency_key in self.results:return self.results[r.idempotency_key]
        try:
            head=self.transport.push(r.run_branch,r.candidate_commit); pr=self.transport.find_or_create_draft(r.run_branch,r.base,"Hive Mind candidate",f"Validation receipt: {r.qualification_digest}")
            result=DeliveryResult(DeliveryState.PUBLISHED,digest,head,str(pr)); self.results[r.idempotency_key]=result; return result
        except (TimeoutError,ConnectionError): return DeliveryResult(DeliveryState.RECONCILIATION_REQUIRED,digest,blocker="remote effect uncertain")
        except PermissionError as e:return DeliveryResult(DeliveryState.BLOCKED,digest,blocker=str(e))
