"""N04 closed inert campaign contracts; no record grants authority or effects."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping
from .runtime_contracts import ContractViolation, canonical_digest, portable_path, require_digest, require_identifier, require_time, strict_json_object
from .brain_kernel.contracts import MissionState, WorkState
_SHA=re.compile(r"[0-9a-f]{40}\Z")
class CampaignContractErrorCode(StrEnum):
 INVALID="N04-INVALID"; UNKNOWN_FIELD="N04-UNKNOWN-FIELD"; UNKNOWN_STATE="N04-UNKNOWN-STATE"; ORPHAN_REQUIREMENT="N04-ORPHAN-REQUIREMENT"; ORPHAN_DEPENDENCY="N04-ORPHAN-DEPENDENCY"; AUTHORITY_CHANGED="N04-AUTHORITY-CHANGED"; RECEIPT_INCONSISTENT="N04-RECEIPT-INCONSISTENT"; HISTORICAL_NOT_ALLOWED="N04-HISTORICAL-NOT-ALLOWED"
ERROR_CODES=tuple(x.value for x in CampaignContractErrorCode)
class CampaignContractError(ContractViolation):
 def __init__(self,code:CampaignContractErrorCode,msg:str): self.code=code;super().__init__(f"{code.value}: {msg}")
def _fail(c,m):raise CampaignContractError(c,m)
def _id(v,l):
 try:require_identifier(v,l)
 except ContractViolation as e:_fail(CampaignContractErrorCode.INVALID,str(e))
def _dg(v,l):
 try:require_digest(v,l)
 except ContractViolation as e:_fail(CampaignContractErrorCode.INVALID,str(e))
def _tm(v,l):
 try:require_time(v,l)
 except ContractViolation as e:_fail(CampaignContractErrorCode.INVALID,str(e))
def _path(v):
 try:return portable_path(v)
 except ContractViolation as e:_fail(CampaignContractErrorCode.INVALID,str(e))
def _ids(v,l,req=True):
 if type(v)is not tuple or (req and not v) or len(v)!=len(set(v)):_fail(CampaignContractErrorCode.INVALID,f"{l} unique/nonempty")
 for x in v:_id(x,l)
def _sha(v,l):
 if type(v)is not str or _SHA.fullmatch(v)is None:_fail(CampaignContractErrorCode.INVALID,f"{l} sha")
class ClaimLevel(StrEnum): STATIC="static";RUNTIME="runtime";PRODUCTION_CANDIDATE="production-candidate";DEPLOYED_OBSERVED="deployed-observed"
class CampaignState(StrEnum): DRAFT="DRAFT";READY="READY";RUNNING="RUNNING";VERIFYING="VERIFYING";COMPLETED="COMPLETED";NO_CHANGE="NO_CHANGE";FAILED="FAILED";CANCELLED="CANCELLED"
class PackageState(StrEnum): PROPOSED="PROPOSED";READY="READY";RUNNING="RUNNING";VERIFYING="VERIFYING";COMPLETED="COMPLETED";NO_CHANGE="NO_CHANGE";FAILED="FAILED";CANCELLED="CANCELLED";SUPERSEDED="SUPERSEDED"
def campaign_state_event(s):
 if not isinstance(s,CampaignState):_fail(CampaignContractErrorCode.UNKNOWN_STATE,"campaign")
 if s is CampaignState.DRAFT:return "mission.created",{}
 return "mission.transition",{"status":{CampaignState.READY:MissionState.READY,CampaignState.RUNNING:MissionState.RUNNING,CampaignState.VERIFYING:MissionState.VERIFYING,CampaignState.COMPLETED:MissionState.COMPLETED,CampaignState.NO_CHANGE:MissionState.COMPLETED,CampaignState.FAILED:MissionState.FAILED,CampaignState.CANCELLED:MissionState.CANCELLED}[s].value}
def package_state_event(s):
 if not isinstance(s,PackageState):_fail(CampaignContractErrorCode.UNKNOWN_STATE,"package")
 if s is PackageState.PROPOSED:return "work.created",{}
 return "work.transition",{"status":{PackageState.READY:WorkState.READY,PackageState.RUNNING:WorkState.RUNNING,PackageState.VERIFYING:WorkState.AWAITING_VERIFICATION,PackageState.COMPLETED:WorkState.INTEGRATED,PackageState.NO_CHANGE:WorkState.INTEGRATED,PackageState.FAILED:WorkState.TERMINAL_FAILED,PackageState.CANCELLED:WorkState.CANCELLED,PackageState.SUPERSEDED:WorkState.SUPERSEDED}[s].value}
@dataclass(frozen=True,slots=True)
class ResourceAllocation:
 max_wall_seconds:int;max_model_calls:int;max_cost_microunits:int
 def __post_init__(self):
  for n in self.__dataclass_fields__:
   if type(getattr(self,n))is not int or getattr(self,n)<0:_fail(CampaignContractErrorCode.INVALID,n)
 def to_document(self):return {n:getattr(self,n) for n in self.__dataclass_fields__}
@dataclass(frozen=True,slots=True)
class AcceptanceBinding:
 acceptance_id:str;capability:str;artifact_ref:str;result:str;owner:str;claim_level:ClaimLevel;evidence_digest:str|None=None
 def __post_init__(self):
  for x,n in ((self.acceptance_id,"acceptance_id"),(self.capability,"capability"),(self.owner,"owner")):_id(x,n)
  if type(self.artifact_ref)is not str or not self.artifact_ref or self.result not in {"passed","failed","observed"} or not isinstance(self.claim_level,ClaimLevel):_fail(CampaignContractErrorCode.INVALID,"acceptance")
  if self.evidence_digest is not None:_dg(self.evidence_digest,"evidence")
 def to_document(self):return {"acceptance_id":self.acceptance_id,"capability":self.capability,"artifact_ref":self.artifact_ref,"result":self.result,"owner":self.owner,"claim_level":self.claim_level.value,"evidence_digest":self.evidence_digest}
@dataclass(frozen=True,slots=True)
class CandidateCompletion:
 mission_id:str;package_id:str;authority_digest:str;base_commit_sha:str;base_tree_digest:str;commit_sha:str;tree_digest:str;output_receipts:tuple[tuple[str,str],...];acceptance_receipts:tuple[tuple[str,str],...];disposition:str
 def __post_init__(self):
  for x,n in ((self.mission_id,"mission"),(self.package_id,"package")):_id(x,n)
  for x,n in ((self.authority_digest,"authority"),(self.base_tree_digest,"base tree"),(self.tree_digest,"tree")):_dg(x,n)
  _sha(self.base_commit_sha,"base commit");_sha(self.commit_sha,"commit")
  if self.disposition not in {"implemented","no-change"}:_fail(CampaignContractErrorCode.INVALID,"disposition")
  for xs,n in ((self.output_receipts,"outputs"),(self.acceptance_receipts,"acceptance")):
   if type(xs)is not tuple or not xs or any(type(x)is not tuple or len(x)!=2 or any(type(y)is not str for y in x) for x in xs) or len({x[0] for x in xs})!=len(xs):_fail(CampaignContractErrorCode.INVALID,n)
   for a,b in xs:_id(a,n);_dg(b,n)
  object.__setattr__(self,"output_receipts",tuple(tuple(x) for x in self.output_receipts));object.__setattr__(self,"acceptance_receipts",tuple(tuple(x) for x in self.acceptance_receipts))
  if self.disposition=="no-change" and (self.base_commit_sha!=self.commit_sha or self.base_tree_digest!=self.tree_digest):_fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT,"no-change equality")
@dataclass(frozen=True,slots=True)
class WorkPackage:
 schema_version:int;revision:int;package_id:str;mission_id:str;objective:str;target_boundary:str;requirement_ids:tuple[str,...];dependencies:tuple[str,...];capabilities:tuple[str,...];acceptance:tuple[AcceptanceBinding,...];risk:str;resources:ResourceAllocation;outputs:tuple[str,...];rollback:str;authority_digest:str;state:PackageState;created_at:str;completion:CandidateCompletion|None=None
 def __post_init__(self):
  if type(self.schema_version)is not int or self.schema_version!=1 or type(self.revision)is not int or self.revision<1:_fail(CampaignContractErrorCode.INVALID,"version")
  for x,n in ((self.package_id,"package"),(self.mission_id,"mission")):_id(x,n)
  if not all(type(x)is str and x for x in (self.objective,self.risk,self.rollback)):_fail(CampaignContractErrorCode.INVALID,"required text")
  object.__setattr__(self,"target_boundary",_path(self.target_boundary));_ids(self.requirement_ids,"requirements");_ids(self.dependencies,"dependencies",False);_ids(self.capabilities,"capabilities");_ids(self.outputs,"outputs")
  if self.package_id in self.dependencies:_fail(CampaignContractErrorCode.ORPHAN_DEPENDENCY,"self")
  if type(self.acceptance)is not tuple or not self.acceptance or any(type(x)is not AcceptanceBinding for x in self.acceptance) or len({x.acceptance_id for x in self.acceptance})!=len(self.acceptance):_fail(CampaignContractErrorCode.INVALID,"acceptance exact")
  if any(x.capability not in self.capabilities or x.artifact_ref not in self.outputs or x.owner=="builder" for x in self.acceptance):_fail(CampaignContractErrorCode.INVALID,"acceptance binding")
  if any(x.claim_level is ClaimLevel.DEPLOYED_OBSERVED and (x.result!="observed" or x.evidence_digest is None) for x in self.acceptance):_fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT,"deployment evidence")
  if type(self.resources)is not ResourceAllocation:_fail(CampaignContractErrorCode.INVALID,"resource type")
  _dg(self.authority_digest,"authority");_tm(self.created_at,"time")
  if not isinstance(self.state,PackageState):_fail(CampaignContractErrorCode.UNKNOWN_STATE,"package")
  if self.completion is not None and type(self.completion)is not CandidateCompletion:_fail(CampaignContractErrorCode.INVALID,"completion type")
  terminal=self.state in {PackageState.COMPLETED,PackageState.NO_CHANGE}
  if terminal != (self.completion is not None):_fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT,"terminal")
  if self.completion:
   c=self.completion
   if (c.mission_id,c.package_id,c.authority_digest)!=(self.mission_id,self.package_id,self.authority_digest) or set(x[0] for x in c.output_receipts)!=set(self.outputs) or set(x[0] for x in c.acceptance_receipts)!={x.acceptance_id for x in self.acceptance} or (self.state is PackageState.NO_CHANGE)!=(c.disposition=="no-change"):_fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT,"completion binding")
   if self.state is PackageState.COMPLETED and any(x.result not in {"passed","observed"} for x in self.acceptance):_fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT,"completed package requires passing acceptance")
 def to_document(self):return {"schema_version":self.schema_version,"revision":self.revision,"package_id":self.package_id,"mission_id":self.mission_id,"objective":self.objective,"target_boundary":self.target_boundary,"requirement_ids":list(self.requirement_ids),"dependencies":list(self.dependencies),"capabilities":list(self.capabilities),"acceptance":[x.to_document() for x in self.acceptance],"risk":self.risk,"resources":self.resources.to_document(),"outputs":list(self.outputs),"rollback":self.rollback,"authority_digest":self.authority_digest,"state":self.state.value,"created_at":self.created_at,"completion":None if self.completion is None else {"mission_id":self.completion.mission_id,"package_id":self.completion.package_id,"authority_digest":self.completion.authority_digest,"base_commit_sha":self.completion.base_commit_sha,"base_tree_digest":self.completion.base_tree_digest,"commit_sha":self.completion.commit_sha,"tree_digest":self.completion.tree_digest,"output_receipts":[list(x) for x in self.completion.output_receipts],"acceptance_receipts":[list(x) for x in self.completion.acceptance_receipts],"disposition":self.completion.disposition}}
@dataclass(frozen=True,slots=True)
class CampaignMission:
 schema_version:int;revision:int;mission_id:str;objective:str;target_boundary:str;requirement_ids:tuple[str,...];packages:tuple[WorkPackage,...];authority_digest:str;state:CampaignState;created_at:str;parent_digest:str|None=None
 def __post_init__(self):
  if type(self.schema_version)is not int or self.schema_version!=1 or type(self.revision)is not int or self.revision<1:_fail(CampaignContractErrorCode.INVALID,"version")
  _id(self.mission_id,"mission");object.__setattr__(self,"target_boundary",_path(self.target_boundary));_ids(self.requirement_ids,"requirements");_dg(self.authority_digest,"authority");_tm(self.created_at,"time")
  if not isinstance(self.state,CampaignState) or type(self.objective)is not str or not self.objective or type(self.packages)is not tuple or not self.packages or any(type(x)is not WorkPackage for x in self.packages) or len({x.package_id for x in self.packages})!=len(self.packages):_fail(CampaignContractErrorCode.INVALID,"mission")
  ids={x.package_id for x in self.packages};covered=set().union(*(set(x.requirement_ids) for x in self.packages))
  if any(x.mission_id!=self.mission_id or x.authority_digest!=self.authority_digest for x in self.packages):_fail(CampaignContractErrorCode.AUTHORITY_CHANGED,"package")
  if any(not(x.target_boundary==self.target_boundary or x.target_boundary.startswith(self.target_boundary+"/")) for x in self.packages):_fail(CampaignContractErrorCode.INVALID,"target")
  if covered!=set(self.requirement_ids):_fail(CampaignContractErrorCode.ORPHAN_REQUIREMENT,"coverage")
  pending={x.package_id:set(x.dependencies) for x in self.packages}
  if any(not v.issubset(ids) for v in pending.values()):_fail(CampaignContractErrorCode.ORPHAN_DEPENDENCY,"unknown")
  while pending:
   ready={k for k,v in pending.items() if not v}
   if not ready:_fail(CampaignContractErrorCode.ORPHAN_DEPENDENCY,"cycle")
   for k in ready:del pending[k]
   for v in pending.values():v.difference_update(ready)
  if self.parent_digest is not None:_dg(self.parent_digest,"parent")
  terminal={PackageState.COMPLETED,PackageState.NO_CHANGE,PackageState.FAILED,PackageState.CANCELLED,PackageState.SUPERSEDED}
  if self.state is CampaignState.COMPLETED and (any(x.state is not PackageState.COMPLETED for x in self.packages)):_fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT,"completed mission requires completed packages")
  if self.state is CampaignState.NO_CHANGE and (any(x.state is not PackageState.NO_CHANGE for x in self.packages)):_fail(CampaignContractErrorCode.RECEIPT_INCONSISTENT,"no-change mission requires no-change packages")
 def to_document(self):return {"schema_version":self.schema_version,"revision":self.revision,"mission_id":self.mission_id,"objective":self.objective,"target_boundary":self.target_boundary,"requirement_ids":list(self.requirement_ids),"packages":[x.to_document() for x in self.packages],"authority_digest":self.authority_digest,"state":self.state.value,"created_at":self.created_at,"parent_digest":self.parent_digest}
 @property
 def digest(self):return canonical_digest(self.to_document())
@dataclass(frozen=True,slots=True)
class SuccessorContract:
 predecessor:CampaignMission;successor:CampaignMission;independent_disposition_digest:str|None=None
 def __post_init__(self):
  if type(self.predecessor)is not CampaignMission or type(self.successor)is not CampaignMission:_fail(CampaignContractErrorCode.INVALID,"types")
  if self.successor.parent_digest!=self.predecessor.digest or self.successor.authority_digest!=self.predecessor.authority_digest or set(self.successor.requirement_ids)!=set(self.predecessor.requirement_ids):_fail(CampaignContractErrorCode.AUTHORITY_CHANGED,"successor")
  if self.successor.revision<=self.predecessor.revision:_fail(CampaignContractErrorCode.INVALID,"revision")
  old={(x.acceptance_id,x.to_document().__repr__()) for p in self.predecessor.packages for x in p.acceptance};new={(x.acceptance_id,x.to_document().__repr__()) for p in self.successor.packages for x in p.acceptance}
  if old!=new and self.independent_disposition_digest is None:_fail(CampaignContractErrorCode.INVALID,"changed acceptance")
  if self.independent_disposition_digest is not None:_dg(self.independent_disposition_digest,"disposition")
def parse_campaign_mission(raw:bytes,*,fixture_mode=False):
    """Production parser: strict JSON plus constructor admission; errors are N04-coded."""
    try:
        d=strict_json_object(raw)
        if d.get("schema_version")!=1 or type(d.get("schema_version")) is not int:_fail(CampaignContractErrorCode.HISTORICAL_NOT_ALLOWED,"version")
        allowed={"schema_version","revision","mission_id","objective","target_boundary","requirement_ids","packages","authority_digest","state","created_at","parent_digest"}
        if set(d)!=allowed:_fail(CampaignContractErrorCode.UNKNOWN_FIELD,"campaign")
        packages=[]
        for p in d["packages"]:
            if not isinstance(p,Mapping):_fail(CampaignContractErrorCode.INVALID,"package")
            a=tuple(AcceptanceBinding(**{**x,"claim_level":ClaimLevel(x["claim_level"])}) for x in p["acceptance"])
            c=p["completion"]
            completion=None if c is None else CandidateCompletion(c["mission_id"],c["package_id"],c["authority_digest"],c["base_commit_sha"],c["base_tree_digest"],c["commit_sha"],c["tree_digest"],tuple(tuple(x) for x in c["output_receipts"]),tuple(tuple(x) for x in c["acceptance_receipts"]),c["disposition"])
            packages.append(WorkPackage(p["schema_version"],p["revision"],p["package_id"],p["mission_id"],p["objective"],p["target_boundary"],tuple(p["requirement_ids"]),tuple(p["dependencies"]),tuple(p["capabilities"]),a,p["risk"],ResourceAllocation(**p["resources"]),tuple(p["outputs"]),p["rollback"],p["authority_digest"],PackageState(p["state"]),p["created_at"],completion))
        return CampaignMission(d["schema_version"],d["revision"],d["mission_id"],d["objective"],d["target_boundary"],tuple(d["requirement_ids"]),tuple(packages),d["authority_digest"],CampaignState(d["state"]),d["created_at"],d["parent_digest"])
    except CampaignContractError: raise
    except (ContractViolation,ValueError,KeyError,TypeError) as e:_fail(CampaignContractErrorCode.INVALID,str(e))
def parse_historical_inert_plan(raw:bytes,*,fixture_mode=False):
 try:d=strict_json_object(raw)
 except ContractViolation as e:_fail(CampaignContractErrorCode.INVALID,str(e))
 if not fixture_mode or set(d)!={"schema_version","historical_inert_plan","fixture_id","candidate"} or d.get("schema_version")!=0 or d.get("historical_inert_plan") is not True or d.get("fixture_id")!="N04-HISTORICAL-V0" or d.get("candidate")!="candidate/app.txt":_fail(CampaignContractErrorCode.HISTORICAL_NOT_ALLOWED,"historical")
 return d
