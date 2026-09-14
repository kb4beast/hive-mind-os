"""Independent qualification receipts; cache origins remain explicit."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Callable
from .brain_kernel.canonical import canonical_digest
class QualificationDisposition(str,Enum): PASSED="PASSED"; FAILED="FAILED"; INCOMPLETE="INCOMPLETE"; QUARANTINED="QUARANTINED"
@dataclass(frozen=True,slots=True)
class QualificationRequest:
    candidate_id:str; base_id:str; acceptance_manifest:tuple[str,...]; changed_surfaces:tuple[str,...]; risk_tier:str; sandbox_digest:str; toolchain_digest:str; environment_digest:str; evaluator_id:str; allowed_cache_origins:tuple[str,...]=()
@dataclass(frozen=True,slots=True)
class CheckReceipt:
    name:str; kind:str; input_digest:str; origin:str; status:str; actual_count:int=0; artifacts:tuple[str,...]=(); omitted:tuple[str,...]=()
@dataclass(frozen=True,slots=True)
class QualificationReceipt:
    request_digest:str; disposition:QualificationDisposition; checks:tuple[CheckReceipt,...]; invalidations:tuple[str,...]=()
    @property
    def digest(self): return canonical_digest(self)
class CandidateQualifier:
    def __init__(self, executor:Callable[[str],int]|None=None): self.executor=executor
    def qualify(self, request:QualificationRequest)->QualificationReceipt:
        if not request.evaluator_id: raise ValueError("independent evaluator required")
        checks=[]
        for name in request.acceptance_manifest:
            try: count=self.executor(name) if self.executor else 0
            except Exception: return QualificationReceipt(canonical_digest(request),QualificationDisposition.FAILED,tuple(checks),("check-failed",))
            checks.append(CheckReceipt(name,"acceptance",canonical_digest((request.candidate_id,name)),"curator-execution","passed" if count>0 else "failed",count))
        disposition=QualificationDisposition.PASSED if checks and all(c.status=="passed" for c in checks) else QualificationDisposition.INCOMPLETE
        return QualificationReceipt(canonical_digest(request),disposition,tuple(checks))
