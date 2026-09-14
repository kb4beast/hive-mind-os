"""Typed Roblox Studio runtime evidence; static checks never substitute."""
from dataclasses import dataclass
from enum import StrEnum
class RuntimeVerdict(StrEnum): RUNTIME_VALIDATED="RUNTIME_VALIDATED"; PRODUCTION_CANDIDATE="PRODUCTION_CANDIDATE"; BLOCKED_RUNTIME="BLOCKED_RUNTIME"; FAILED="FAILED"; INCONCLUSIVE="INCONCLUSIVE"; DEPLOYED_OBSERVED="DEPLOYED_OBSERVED"
@dataclass(frozen=True, slots=True)
class RobloxRuntimeEvidence:
 candidate_digest:str; profile_digest:str; platform_tool_version:str; environment_id:str; scenario_manifest_digest:str; account_capability_refs:tuple[str,...]; runtime_receipts:tuple[str,...]; performance_samples:tuple[float,...]; persistence_results:dict[str,str]; security_results:dict[str,str]; asset_results:dict[str,str]; cleanup_receipt:str; verdict:RuntimeVerdict; missing_obligations:tuple[str,...]=()
 def __post_init__(self):
  if self.verdict is RuntimeVerdict.PRODUCTION_CANDIDATE and self.missing_obligations: raise ValueError("production candidate cannot have missing obligations")
def blocked_runtime(reason): return RobloxRuntimeEvidence("unknown","unknown","unknown","unavailable","unknown",(),(),(),{}, {}, {}, "none",RuntimeVerdict.BLOCKED_RUNTIME,(reason,))
