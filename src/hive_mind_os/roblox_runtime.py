"""Typed Roblox Studio runtime evidence; static checks never substitute."""
from dataclasses import dataclass
from enum import StrEnum
from .brain_kernel.canonical import canonical_digest, canonical_document
class RuntimeVerdict(StrEnum): RUNTIME_VALIDATED="RUNTIME_VALIDATED"; PRODUCTION_CANDIDATE="PRODUCTION_CANDIDATE"; BLOCKED_RUNTIME="BLOCKED_RUNTIME"; FAILED="FAILED"; INCONCLUSIVE="INCONCLUSIVE"; DEPLOYED_OBSERVED="DEPLOYED_OBSERVED"
@dataclass(frozen=True, slots=True)
class RobloxRuntimeEvidence:
 candidate_digest:str; profile_digest:str; platform_tool_version:str; environment_id:str; scenario_manifest_digest:str; account_capability_refs:tuple[str,...]; runtime_receipts:tuple[str,...]; performance_samples:tuple[float,...]; persistence_results:dict[str,str]; security_results:dict[str,str]; asset_results:dict[str,str]; cleanup_receipt:str; verdict:RuntimeVerdict; missing_obligations:tuple[str,...]=()
 def __post_init__(self):
  if self.verdict is RuntimeVerdict.PRODUCTION_CANDIDATE and self.missing_obligations: raise ValueError("production candidate cannot have missing obligations")
  if self.verdict in {RuntimeVerdict.RUNTIME_VALIDATED,RuntimeVerdict.PRODUCTION_CANDIDATE} and not self.runtime_receipts: raise ValueError("runtime verdict requires receipts")
  if any(not isinstance(x,str) or not x.startswith("ref:") for x in self.account_capability_refs): raise ValueError("capabilities must be opaque references")
 @property
 def digest(self): return canonical_digest(self)
 def to_dict(self): return canonical_document(self)
 @classmethod
 def from_dict(cls,value):
  required=set(cls.__dataclass_fields__)
  if set(value)!=required: raise ValueError("closed runtime evidence schema")
  return cls(**{**value,"verdict":RuntimeVerdict(value["verdict"]),"account_capability_refs":tuple(value["account_capability_refs"]),"runtime_receipts":tuple(value["runtime_receipts"]),"performance_samples":tuple(value["performance_samples"]),"missing_obligations":tuple(value["missing_obligations"])})
def blocked_runtime(reason): return RobloxRuntimeEvidence("unknown","unknown","unknown","unavailable","unknown",(),(),(),{}, {}, {}, "none",RuntimeVerdict.BLOCKED_RUNTIME,(reason,))
