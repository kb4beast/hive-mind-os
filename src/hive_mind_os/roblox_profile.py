"""Static Roblox/Rojo profile discovery; no runtime claim (N26)."""
from dataclasses import dataclass
from enum import StrEnum
from .brain_kernel.canonical import canonical_digest, canonical_document
class ProfileStatus(StrEnum): PROFILE_VALID="PROFILE_VALID"; BLOCKED_TOOLCHAIN="BLOCKED_TOOLCHAIN"; BLOCKED_SOURCE="BLOCKED_SOURCE"; STATIC_VALIDATED="STATIC_VALIDATED"
@dataclass(frozen=True, slots=True)
class RobloxProfile:
 profile_id:str; profile_selection_receipt_digest:str; source_refs:tuple[str,...]; toolchain_versions:dict[str,str]; executable_paths:dict[str,str]; executable_digests:dict[str,str]; image_digest:str; project_manifest_paths:tuple[str,...]; source_roots:tuple[str,...]; package_lock_digests:tuple[str,...]; build_commands:tuple[tuple[str,...],...]; static_check_commands:tuple[tuple[str,...],...]; artifact_paths:tuple[str,...]; asset_manifest_digest:str; runtime_requirements:dict[str,object]; capability_status:ProfileStatus
 def __post_init__(self):
  if any(type(x) is not str or not x.strip() for x in (self.profile_id,self.profile_selection_receipt_digest,self.image_digest,self.asset_manifest_digest)): raise ValueError("profile identity is required")
  if not self.project_manifest_paths or not self.source_roots: raise ValueError("project manifests and source roots are required")
  if self.capability_status is ProfileStatus.STATIC_VALIDATED and not self.build_commands: raise ValueError("static validation requires sealed build command")
 @property
 def digest(self): return canonical_digest(self)
 def to_dict(self): return canonical_document(self)
 @classmethod
 def from_dict(cls,value):
  required=set(cls.__dataclass_fields__)
  if set(value)!=required: raise ValueError("closed Roblox profile schema")
  return cls(**{**value,"capability_status":ProfileStatus(value["capability_status"]),"source_refs":tuple(value["source_refs"]),"project_manifest_paths":tuple(value["project_manifest_paths"]),"source_roots":tuple(value["source_roots"]),"package_lock_digests":tuple(value["package_lock_digests"]),"build_commands":tuple(tuple(x) for x in value["build_commands"]),"static_check_commands":tuple(tuple(x) for x in value["static_check_commands"]),"artifact_paths":tuple(value["artifact_paths"])})
