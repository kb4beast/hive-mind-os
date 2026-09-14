"""Evidence-bound backlog signals and deterministic selection."""
from __future__ import annotations
from dataclasses import dataclass
import json, sqlite3, time
from pathlib import Path
from .brain_kernel.canonical import canonical_digest
@dataclass(frozen=True, slots=True)
class DiscoverySignal:
    tenant_id:str; repository_id:str; snapshot:str; kind:str; evidence_refs:tuple[str,...]; content_digest:str; confidence:float=0.0; expires_at:float|None=None
    def __post_init__(self):
        if not self.tenant_id or not self.repository_id or not self.kind or not self.content_digest: raise ValueError("signal identity is required")
        if not 0 <= self.confidence <= 1: raise ValueError("confidence must be between zero and one")
@dataclass(frozen=True, slots=True)
class BacklogCandidate:
    idea_id:str; atomic_claims:tuple[str,...]; user_impact:float; success_measure:str; effort:float; risk:float; dependencies:tuple[str,...]=(); dissent:tuple[str,...]=(); next_evidence:tuple[str,...]=()
    def __post_init__(self):
        if not self.idea_id or not self.atomic_claims or not self.success_measure: raise ValueError("candidate evidence and acceptance are required")
        if self.effort <= 0 or self.user_impact < 0 or not 0 <= self.risk <= 1: raise ValueError("invalid candidate score inputs")
@dataclass(frozen=True, slots=True)
class BacklogSelection:
    candidates:tuple[BacklogCandidate,...]; selected_ids:tuple[str,...]; scores:tuple[tuple[str,float],...]; deferred:tuple[tuple[str,str],...]=(); court_receipt:str=""
    @property
    def digest(self): return canonical_digest(self)
class DiscoveryBacklog:
    def __init__(self, state_dir: str|Path|None=None):
        self.signals={}; self.candidates={}; self._db=None
        if state_dir is not None:
            p=Path(state_dir); p.mkdir(parents=True,exist_ok=True); self._db=sqlite3.connect(p/"discovery.sqlite3")
            self._db.execute("CREATE TABLE IF NOT EXISTS signals (k TEXT PRIMARY KEY, body TEXT NOT NULL)"); self._db.commit()
    def ingest(self, signal:DiscoverySignal)->bool:
        if signal.expires_at is not None and signal.expires_at <= time.time(): return False
        key=(signal.tenant_id,signal.repository_id,signal.kind,signal.content_digest)
        if key in self.signals or (self._db and self._db.execute("SELECT 1 FROM signals WHERE k=?",(json.dumps(key),)).fetchone()):return False
        self.signals[key]=signal
        if self._db:
            body={name:getattr(signal,name) for name in signal.__dataclass_fields__}
            self._db.execute("INSERT INTO signals VALUES (?,?)",(json.dumps(key),json.dumps(body,sort_keys=True,default=str))); self._db.commit()
        return True
    def add(self,candidate:BacklogCandidate): self.candidates[candidate.idea_id]=candidate
    def select(self, *, limit:int=1)->BacklogSelection:
        if limit<1: raise ValueError("limit must be positive")
        scored=tuple(sorted(((c.idea_id,c.user_impact/max(c.effort,0.1)*(1-c.risk)*(1 if c.dissent else .9)) for c in self.candidates.values()), key=lambda x:(-x[1],x[0])))
        chosen=tuple(i for i,_ in scored[:limit]); return BacklogSelection(tuple(self.candidates.values()),chosen,scored,tuple((i,"lower evidence-adjusted value") for i,_ in scored[limit:]))
