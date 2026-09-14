"""Replaceable, fail-closed execution boundary contracts (N18)."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, Sequence
from .brain_kernel.canonical import canonical_digest

class ProbeResult(StrEnum): ENFORCED="ENFORCED"; FAILED="FAILED"; UNAVAILABLE="UNAVAILABLE"
class IsolationError(ValueError): pass
@dataclass(frozen=True, slots=True)
class IsolationAttestation:
    backend_id:str; backend_version:str; image_digest:str|None; tenant_id:str; repository_id:str
    filesystem_scope:str; network_policy_digest:str; credential_policy_digest:str
    writable_mounts:tuple[str,...]; resource_limits:dict[str,int|float]; probe_suite_digest:str
    probe_result:ProbeResult; expires_at:str
    def __post_init__(self):
        for n,v in (("backend_id",self.backend_id),("backend_version",self.backend_version),("tenant_id",self.tenant_id),("repository_id",self.repository_id),("filesystem_scope",self.filesystem_scope),("expires_at",self.expires_at)):
            if type(v) is not str or not v.strip(): raise IsolationError(f"{n} is required")
        if self.probe_result != ProbeResult.ENFORCED and self.probe_result not in ProbeResult: raise IsolationError("invalid probe result")
    @property
    def digest(self): return canonical_digest(self)
    def admits_untrusted(self): return self.probe_result is ProbeResult.ENFORCED
@dataclass(frozen=True, slots=True)
class ExecutionResult:
    exit_status:int|None; timed_out:bool; cleanup_receipt:str; artifact_refs:tuple[str,...]=(); error_code:str|None=None
class IsolationBackend(Protocol):
    def capabilities(self)->IsolationAttestation: ...
    def execute(self, argv:Sequence[str], *, attestation:IsolationAttestation)->ExecutionResult: ...
    def teardown(self)->str: ...
class UnavailableIsolationBackend:
    def __init__(self, reason="OCI broker unavailable"): self.reason=reason
    def capabilities(self): return IsolationAttestation("unavailable","0",None,"unknown","unknown","none","deny","deny",(),{},canonical_digest(self.reason),ProbeResult.UNAVAILABLE,"1970-01-01T00:00:00Z")
    def execute(self, argv, *, attestation): return ExecutionResult(None,False,"none",(),"BLOCKED_ISOLATION")
    def teardown(self): return "none"

def require_attested(attestation:IsolationAttestation)->None:
    if not attestation.admits_untrusted(): raise IsolationError("untrusted execution requires ENFORCED isolation attestation")
