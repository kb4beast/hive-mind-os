"""N08 host-owned descriptor for reconstructing canonical mission bindings.

The descriptor is inert data.  A host bootstrap supplies the resolver; scheduler
payloads can select a descriptor but cannot contain executable configuration.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping

from ...runtime_contracts import canonical_digest, require_digest, require_identifier, strict_json_object

class BindingState(StrEnum): UNCONFIGURED="UNCONFIGURED"; VALIDATED="VALIDATED"; READY="READY"; BLOCKED="BLOCKED"
class MissionBindingError(RuntimeError): pass

@dataclass(frozen=True, slots=True)
class MissionBindingDescriptor:
    configuration_id:str; configuration_digest:str; tenant_id:str; repository_id:str; runtime_version:str; adapter_versions:tuple[tuple[str,str],...]; role_provider_refs:tuple[str,...]; authority_ref:str; verification_profile_digest:str; state_root_ref:str; schema_version:int=1
    def __post_init__(self):
        if self.schema_version != 1: raise MissionBindingError("unsupported binding descriptor version")
        for v,n in ((self.configuration_id,"configuration_id"),(self.tenant_id,"tenant_id"),(self.repository_id,"repository_id"),(self.runtime_version,"runtime_version"),(self.authority_ref,"authority_ref"),(self.state_root_ref,"state_root_ref")): require_identifier(v,n)
        for v in (self.configuration_digest,self.verification_profile_digest): require_digest(v,"descriptor digest")
        if not self.adapter_versions or len({x[0] for x in self.adapter_versions}) != len(self.adapter_versions): raise MissionBindingError("adapter ids must be unique")
        for key,value in self.adapter_versions: require_identifier(key,"adapter id"); require_identifier(value,"adapter version")
        if not self.role_provider_refs or len(set(self.role_provider_refs)) != len(self.role_provider_refs): raise MissionBindingError("role provider refs must be unique")
        for value in self.role_provider_refs: require_identifier(value,"role provider ref")
    def to_document(self)->dict[str,Any]: return {"schema_version":self.schema_version,"configuration_id":self.configuration_id,"configuration_digest":self.configuration_digest,"tenant_id":self.tenant_id,"repository_id":self.repository_id,"runtime_version":self.runtime_version,"adapter_versions":[list(x) for x in self.adapter_versions],"role_provider_refs":list(self.role_provider_refs),"authority_ref":self.authority_ref,"verification_profile_digest":self.verification_profile_digest,"state_root_ref":self.state_root_ref}
    @property
    def digest(self)->str:return canonical_digest(self.to_document())
    @classmethod
    def from_document(cls, value:Mapping[str,Any])->"MissionBindingDescriptor":
        fields={"schema_version","configuration_id","configuration_digest","tenant_id","repository_id","runtime_version","adapter_versions","role_provider_refs","authority_ref","verification_profile_digest","state_root_ref"}
        if set(value)!=fields or not isinstance(value.get("adapter_versions"),list) or not isinstance(value.get("role_provider_refs"),list): raise MissionBindingError("descriptor has unknown shape")
        return cls(value["configuration_id"],value["configuration_digest"],value["tenant_id"],value["repository_id"],value["runtime_version"],tuple(tuple(x) for x in value["adapter_versions"]),tuple(value["role_provider_refs"]),value["authority_ref"],value["verification_profile_digest"],value["state_root_ref"],value["schema_version"])

BindingResolver=Callable[[MissionBindingDescriptor, Mapping[str,Any], Path], tuple[Any,Any]]
class ConfiguredMissionBindingsProvider:
    def __init__(self, descriptor:MissionBindingDescriptor, resolver:BindingResolver): self.descriptor=descriptor; self._resolver=resolver
    def resolve(self,payload:Mapping[str,Any],host_root:Path)->tuple[Any,Any]:
        if payload.get("tenant_id") != self.descriptor.tenant_id or payload.get("repository_id") != self.descriptor.repository_id: raise MissionBindingError("BLOCKED: payload tenant or repository differs from admitted descriptor")
        if payload.get("configuration_digest") != self.descriptor.digest: raise MissionBindingError("BLOCKED: descriptor digest mismatch")
        root=host_root.resolve()
        if not root.is_dir(): raise MissionBindingError("BLOCKED: host state root is unavailable")
        return self._resolver(self.descriptor,dict(payload),root)
    __call__=resolve

def load_descriptor(path:Path)->MissionBindingDescriptor:
    try: raw=path.read_bytes(); descriptor=MissionBindingDescriptor.from_document(strict_json_object(raw))
    except (OSError,UnicodeError,ValueError,TypeError) as error: raise MissionBindingError("BLOCKED: descriptor cannot be read") from error
    if canonical_digest(descriptor.to_document()) != descriptor.digest: raise MissionBindingError("BLOCKED: descriptor digest mismatch")
    return descriptor
