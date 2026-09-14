"""Evidence-bound backlog signals and deterministic selection."""
from __future__ import annotations
from dataclasses import dataclass
from .brain_kernel.canonical import canonical_digest
@dataclass(frozen=True, slots=True)
class DiscoverySignal:
    tenant_id:str; repository_id:str; snapshot:str; kind:str; evidence_refs:tuple[str,...]; content_digest:str; confidence:float=0.0; expires_at:float|None=None
@dataclass(frozen=True, slots=True)
class BacklogCandidate:
    idea_id:str; atomic_claims:tuple[str,...]; user_impact:float; success_measure:str; effort:float; risk:float; dependencies:tuple[str,...]=(); dissent:tuple[str,...]=(); next_evidence:tuple[str,...]=()
@dataclass(frozen=True, slots=True)
class BacklogSelection:
    candidates:tuple[BacklogCandidate,...]; selected_ids:tuple[str,...]; scores:tuple[tuple[str,float],...]; deferred:tuple[tuple[str,str],...]=(); court_receipt:str=""
    @property
    def digest(self): return canonical_digest(self)
class DiscoveryBacklog:
    def __init__(self): self.signals={}; self.candidates={}
    def ingest(self, signal:DiscoverySignal)->bool:
        key=(signal.tenant_id,signal.repository_id,signal.kind,signal.content_digest)
        if key in self.signals:return False
        self.signals[key]=signal; return True
    def add(self,candidate:BacklogCandidate): self.candidates[candidate.idea_id]=candidate
    def select(self, *, limit:int=1)->BacklogSelection:
        if limit<1: raise ValueError("limit must be positive")
        scored=tuple(sorted(((c.idea_id,c.user_impact*max(c.effort,0.1)**-1*(1-c.risk)) for c in self.candidates.values()), key=lambda x:(-x[1],x[0])))
        chosen=tuple(i for i,_ in scored[:limit]); return BacklogSelection(tuple(self.candidates.values()),chosen,scored,tuple((i,"lower evidence-adjusted value") for i,_ in scored[limit:]))
