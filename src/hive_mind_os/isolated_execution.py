"""Replaceable, fail-closed execution boundary contracts (N18)."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, Sequence
from .durable_contracts import ContractStore
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
    def to_dict(self):
        from .brain_kernel.canonical import canonical_document
        return canonical_document(self)
    @classmethod
    def from_dict(cls, value):
        required = {"backend_id","backend_version","image_digest","tenant_id","repository_id","filesystem_scope","network_policy_digest","credential_policy_digest","writable_mounts","resource_limits","probe_suite_digest","probe_result","expires_at"}
        if set(value) != required: raise IsolationError("closed attestation schema")
        return cls(**{**value, "probe_result": ProbeResult(value["probe_result"]), "writable_mounts": tuple(value["writable_mounts"])})
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

class IsolationRegistry:
    """Durable backend attestations, keyed by tenant/repository/backend."""
    def __init__(self, path): self._store = ContractStore(path, IsolationAttestation.from_dict)
    def register(self, attestation):
        if attestation.probe_result is ProbeResult.ENFORCED and not attestation.image_digest: raise IsolationError("enforced backend requires pinned image")
        return self._store.put(f"{attestation.tenant_id}:{attestation.repository_id}:{attestation.backend_id}", attestation)
    def get(self, tenant_id, repository_id, backend_id): return self._store.get(f"{tenant_id}:{repository_id}:{backend_id}")
