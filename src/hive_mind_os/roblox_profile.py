"""Static Roblox/Rojo profile discovery; no runtime claim (N26)."""
from dataclasses import dataclass
from enum import StrEnum
class ProfileStatus(StrEnum): PROFILE_VALID="PROFILE_VALID"; BLOCKED_TOOLCHAIN="BLOCKED_TOOLCHAIN"; BLOCKED_SOURCE="BLOCKED_SOURCE"; STATIC_VALIDATED="STATIC_VALIDATED"
@dataclass(frozen=True, slots=True)
class RobloxProfile:
 profile_id:str; profile_selection_receipt_digest:str; source_refs:tuple[str,...]; toolchain_versions:dict[str,str]; executable_paths:dict[str,str]; executable_digests:dict[str,str]; image_digest:str; project_manifest_paths:tuple[str,...]; source_roots:tuple[str,...]; package_lock_digests:tuple[str,...]; build_commands:tuple[tuple[str,...],...]; static_check_commands:tuple[tuple[str,...],...]; artifact_paths:tuple[str,...]; asset_manifest_digest:str; runtime_requirements:dict[str,object]; capability_status:ProfileStatus
