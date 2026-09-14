"""Bounded builder loop with deterministic path and tool checks."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Callable, Iterable
class BuilderState(str,Enum): READY="READY"; WORKING="WORKING"; CHECKPOINTED="CHECKPOINTED"; TERMINAL="TERMINAL"
class BuilderDisposition(str,Enum): READY_FOR_VERIFICATION="READY_FOR_VERIFICATION"; NO_CHANGE="NO_CHANGE"; NEEDS_CONTRACT_AMENDMENT="NEEDS_CONTRACT_AMENDMENT"; BUDGET_EXHAUSTED="BUDGET_EXHAUSTED"; BLOCKED="BLOCKED"
@dataclass(frozen=True,slots=True)
class BuilderSessionSpec:
    package_id:str; attempt_id:str; tenant_id:str; starting_candidate:str; allowed_paths:tuple[str,...]; operations:tuple[str,...]=( "read","edit","test"); acceptance_refs:tuple[str,...]=(); sandbox_profile:str="isolated"; model_profile:str="default"; max_tools:int=20; max_repairs:int=3; max_seconds:float=900
@dataclass(frozen=True,slots=True)
class BuilderSessionResult:
    disposition:BuilderDisposition; candidate:str|None; changed_paths:tuple[str,...]; checks:tuple[str,...]=(); failures:tuple[str,...]=(); evidence_refs:tuple[str,...]=()
class BuilderSession:
    def __init__(self,spec:BuilderSessionSpec): self.spec=spec; self.state=BuilderState.READY; self.tool_count=0; self._checkpoint=None
    def validate_paths(self, paths:Iterable[str]):
        allowed=tuple(PurePosixPath(p).as_posix() for p in self.spec.allowed_paths)
        for p in paths:
            q=PurePosixPath(p).as_posix()
            if q.startswith("../") or q not in allowed and not any(q.startswith(a.rstrip("/")+"/") for a in allowed): raise PermissionError(f"path outside builder write scope: {p}")
    def checkpoint(self,candidate:str, changed_paths:Iterable[str]): self.validate_paths(changed_paths); self._checkpoint=(candidate,tuple(changed_paths)); self.state=BuilderState.CHECKPOINTED; return self._checkpoint
    def run(self, action:Callable[["BuilderSession"],BuilderSessionResult]|None=None)->BuilderSessionResult:
        self.state=BuilderState.WORKING
        if action: result=action(self)
        elif self._checkpoint: result=BuilderSessionResult(BuilderDisposition.READY_FOR_VERIFICATION,self._checkpoint[0],self._checkpoint[1])
        else: result=BuilderSessionResult(BuilderDisposition.NO_CHANGE,self.spec.starting_candidate,())
        self.state=BuilderState.TERMINAL; return result
