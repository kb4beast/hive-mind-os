"""Closed inert N02 metrics/bracket contract; it executes no comparators."""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
import json, math
from pathlib import Path
from random import Random
from statistics import mean
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence
import hmac

BOOTSTRAP_RESAMPLES=10_000; CONFIDENCE=.95; NONINFERIORITY_MARGIN=-.05; SCREENING_FAMILIES=12; FINAL_FAMILIES=30
RECIPE_FIELDS=("source_or_binary_digest","prompt_digest","model_digest","command_profile_digest","tool_digest","context_digest","check_policy_digest","learning_policy_digest")
class CampaignMetricsError(ValueError): pass
REQUIRED_STRATA=("small-bug","feature","absent-tests","multi-file","cross-language","self-runtime","ambiguous-backlog","provider-failure","restart","tenant-isolation","draft-export","endpoint-learning","roblox-runtime")

@dataclass(frozen=True,slots=True)
class SignedCustodyEnvelope:
 """Verifier-bound evidence envelope; fixture HMAC is not a production key store."""
 signer_id:str;role:str;payload_digest:str;signature:str;issued_at:int
 def __post_init__(self):
  _id(self.signer_id,"signer");_digest(self.payload_digest,"payload");
  if self.role not in {"evaluator","custodian"} or type(self.issued_at)is not int or self.issued_at<0 or not isinstance(self.signature,str):raise CampaignMetricsError("invalid custody envelope")
 def verify_fixture_hmac(self,key:bytes)->bool:
  expected=hmac.new(key,(self.signer_id+"|"+self.role+"|"+self.payload_digest+"|"+str(self.issued_at)).encode(),"sha256").hexdigest()
  return hmac.compare_digest(expected,self.signature)
@dataclass(frozen=True,slots=True)
class StageEvidence:
 stage:str;block_digest:str;task_manifest_digest:str;family_manifest_digest:str;lease_digest:str;evaluator:SignedCustodyEnvelope;strata:tuple[str,...];families:int;repetitions:int;seed:int
 def __post_init__(self):
  if self.stage not in {"original","hybrid","final"}:raise CampaignMetricsError("invalid stage evidence")
  for n in ("block_digest","task_manifest_digest","family_manifest_digest","lease_digest"):_digest(getattr(self,n),n)
  if set(self.strata)!=set(REQUIRED_STRATA) or len(self.strata)!=len(REQUIRED_STRATA):raise CampaignMetricsError("exact thirteen strata required")
  required=(30,3) if self.stage=="final" else (12,1)
  if (self.families,self.repetitions)!=required or type(self.seed)is not int:raise CampaignMetricsError("stage threshold/repetition mismatch")
@dataclass(frozen=True,slots=True)
class LeaseRecord:
 lease_digest:str;scope:str;expires_at:int;issued_by:str;active:bool=True
 def __post_init__(self):
  _digest(self.lease_digest,"lease");_id(self.scope,"lease scope");_id(self.issued_by,"lease issuer")
  if type(self.expires_at)is not int or self.expires_at<0 or type(self.active)is not bool:raise CampaignMetricsError("invalid lease")
@dataclass(frozen=True,slots=True)
class IssuedReceipt:
 stage:str;round_number:int;left:str;right:str;block_digest:str;task_id:str;seed:int;evaluator_id:str;receipt_digest:str
 def __post_init__(self):
  for n in ("stage","left","right","task_id","evaluator_id"):_id(getattr(self,n),n)
  for n in ("block_digest","receipt_digest"):_digest(getattr(self,n),n)
  if self.left==self.right or type(self.round_number)is not int or self.round_number<1 or type(self.seed)is not int:raise CampaignMetricsError("invalid issued receipt")
 @property
 def identity(self):return (self.stage,self.round_number,self.left,self.right,self.block_digest,self.task_id,self.seed,self.evaluator_id,self.receipt_digest)
def reject_receipt_replay(receipts:Iterable[IssuedReceipt])->None:
 rows=tuple(receipts)
 if len({x.identity for x in rows})!=len(rows):raise CampaignMetricsError("receipt replay")
_ADMISSION_TOKEN=object()
class AdmittedProtocol:
 """Host-issued opaque capability; public construction is refused."""
 __slots__=("protocol","stage_evidence","admission_digest","_token")
 def __init__(self,protocol,stage_evidence,admission_digest,*,_token=None):
  if _token is not _ADMISSION_TOKEN:raise CampaignMetricsError("admission receipts are host-issued")
  self.protocol=protocol;self.stage_evidence=stage_evidence;self.admission_digest=admission_digest;self._token=_token
 def __setattr__(self,name,value):
  if hasattr(self,name):raise CampaignMetricsError("admission receipt is immutable")
  object.__setattr__(self,name,value)
def admit_protocol(protocol:object,stage_evidence:StageEvidence,*,lease:LeaseRecord|None=None,fixture_hmac_key:bytes|None=None,builder_ids:Sequence[str]=())->AdmittedProtocol:
 """Only execution-facing gateway; OPEN/deferred or unverified evidence cannot pass."""
 if not isinstance(protocol,MatchProtocol):raise CampaignMetricsError("inspection is not executable")
 if lease is None or not lease.active or lease.lease_digest!=stage_evidence.lease_digest or lease.scope!=protocol.protocol_id:raise CampaignMetricsError("missing or mismatched issued lease")
 if not stage_evidence.evaluator.verify_fixture_hmac(fixture_hmac_key or b""):raise CampaignMetricsError("unauthenticated evaluator signature")
 if stage_evidence.evaluator.signer_id in set(builder_ids):raise CampaignMetricsError("evaluator is not independent")
 manifest=protocol.experiment_manifest
 for key in ("selection_seed","bootstrap_seed","retry_rule"):
  if key not in manifest:raise CampaignMetricsError("missing frozen experiment field")
 if manifest.get("holdout_manifest_digest") is None or any(str(manifest.get(k,"" )).startswith("OPEN_") for k in ("task_manifest_status","family_split_status","custody_status","holdout_signature_status")):raise CampaignMetricsError("open external evidence")
 _digest(manifest["holdout_manifest_digest"],"holdout manifest")
 if stage_evidence.stage=="final" and stage_evidence.block_digest!=manifest["holdout_manifest_digest"]:raise CampaignMetricsError("final holdout mismatch")
 for recipe in (*protocol.entrant_recipes.values(),*protocol.hybrid_recipes.values()):
  if recipe.get("availability")!="available" or "provenance_digest" not in recipe:raise CampaignMetricsError("recipe is deferred or lacks provenance")
  _digest(recipe["provenance_digest"],"recipe provenance")
 return AdmittedProtocol(protocol,stage_evidence,canonical_digest([protocol.protocol_digest,stage_evidence.block_digest,stage_evidence.evaluator.payload_digest]),_token=_ADMISSION_TOKEN)
def _require_admission(protocol:object,admission:AdmittedProtocol|None,*,stage:str|None)->None:
 if not isinstance(admission,AdmittedProtocol) or admission._token is not _ADMISSION_TOKEN or admission.protocol is not protocol:raise CampaignMetricsError("missing or foreign admission receipt")
 if admission.admission_digest!=canonical_digest([protocol.protocol_digest,admission.stage_evidence.block_digest,admission.stage_evidence.evaluator.payload_digest]):raise CampaignMetricsError("stale admission receipt")
 if stage is not None and admission.stage_evidence.stage!=stage:raise CampaignMetricsError("admission stage mismatch")
def canonical_digest(v:object)->str:
 def plain(x):
  if isinstance(x,Mapping):return {str(k):plain(y)for k,y in x.items()}
  if isinstance(x,(tuple,list)):return [plain(y)for y in x]
  return x
 return "sha256:"+sha256(json.dumps(plain(v),sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
def _id(v:object,n:str)->None:
 if not isinstance(v,str) or not v or any(c.isspace() for c in v):raise CampaignMetricsError(f"{n} must be a stable identifier")
def _digest(v:object,n:str)->None:
 if not isinstance(v,str) or len(v)!=71 or not v.startswith("sha256:") or any(c not in "0123456789abcdef" for c in v[7:]):raise CampaignMetricsError(f"{n} must be lowercase sha256")
def _num(v:object,n:str,nullable=True,nonnegative=True)->None:
 if v is None and nullable:return
 if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or (nonnegative and v<0):raise CampaignMetricsError(f"{n} must be finite" + (" and nonnegative" if nonnegative else ""))
def _freeze(v:object)->object:
 if isinstance(v,Mapping):return MappingProxyType({k:_freeze(x) for k,x in v.items()})
 if isinstance(v,(list,tuple)):return tuple(_freeze(x) for x in v)
 return v

@dataclass(frozen=True,slots=True)
class AttemptMetric:
 subject_family:str;task_id:str;variant_id:str;candidate_digest:str;configuration_digest:str;model_digest:str;environment_digest:str;eligibility:str;result:str;active_seconds:float|None;queue_seconds:float|None;wall_seconds:float|None;usage_units:float|None;usage_basis:str;provider_cost:float|None;provider_cost_basis:str
 usage_unit:str="tokens";currency:str|None=None;provider_available:str="unknown";input_usage:float|None=None;output_usage:float|None=None;cache_read_usage:float|None=None;cache_write_usage:float|None=None;reasoning_usage:float|None=None;checks:tuple[str,...]=();defects:tuple[str,...]=();recovery_events:tuple[str,...]=();disclosure_events:tuple[str,...]=();context_retransmissions:int|None=None;redundant_checks:int|None=None;model_calls:int|None=None;avoided_work_units:float|None=None
 def __post_init__(self):
  for n in ("subject_family","task_id","variant_id"):_id(getattr(self,n),n)
  for n in ("candidate_digest","configuration_digest","model_digest","environment_digest"):_digest(getattr(self,n),n)
  if self.eligibility not in {"eligible","ineligible","unknown"} or self.result not in {"success","failure","inconclusive","unknown","not_attempted"}:raise CampaignMetricsError("invalid eligibility/result")
  for n in ("active_seconds","queue_seconds","wall_seconds","usage_units","provider_cost","input_usage","output_usage","cache_read_usage","cache_write_usage","reasoning_usage","avoided_work_units"):_num(getattr(self,n),n)
  if self.usage_basis not in {"measured","estimated","unknown"} or self.provider_cost_basis not in {"billed","estimated","unknown"}:raise CampaignMetricsError("invalid measurement basis")
  if (self.usage_basis=="unknown") != (self.usage_units is None) or (self.provider_cost_basis=="unknown") != (self.provider_cost is None):raise CampaignMetricsError("unknown must be null and known must have basis")
  if self.usage_units is None and any(x is not None for x in (self.input_usage,self.output_usage,self.cache_read_usage,self.cache_write_usage,self.reasoning_usage)):raise CampaignMetricsError("unknown total usage cannot contain detailed usage")
  if self.provider_available not in {"available","unavailable","unknown"}:raise CampaignMetricsError("invalid availability")
  for n in ("context_retransmissions","redundant_checks","model_calls"):
   v=getattr(self,n)
   if v is not None and(type(v)is not int or v<0):raise CampaignMetricsError(f"{n} must be nonnegative integer")
  for n in ("checks","defects","recovery_events","disclosure_events"):object.__setattr__(self,n,tuple(getattr(self,n)))
def summarize_attempts(rows:Iterable[AttemptMetric])->dict[str,int]:
 rows=tuple(rows);out={"records":len(rows)}
 for e in ("eligible","ineligible","unknown"):
  out[f"eligibility_{e}"]=sum(r.eligibility==e for r in rows)
  for r in ("success","failure","inconclusive","unknown","not_attempted"):out[f"{e}_{r}"]=sum(x.eligibility==e and x.result==r for x in rows)
 out["eligible_attempted"]=out["eligibility_eligible"]-out["eligible_not_attempted"];return out
@dataclass(frozen=True,slots=True)
class PairedInterval:
 estimate:float|None;lower:float|None;upper:float|None;family_count:int;resamples:int=BOOTSTRAP_RESAMPLES;confidence:float=CONFIDENCE
 def __post_init__(self):
  if (self.estimate is None) != (self.lower is None and self.upper is None):raise CampaignMetricsError("interval wholly known or unknown")
  for n in ("estimate","lower","upper"):_num(getattr(self,n),n,nonnegative=False)
  if self.lower is not None and not self.lower<=self.estimate<=self.upper:raise CampaignMetricsError("invalid interval ordering")
  if type(self.family_count)is not int or self.family_count<0 or (self.estimate is not None and self.family_count<1) or (self.estimate is None and self.family_count!=0) or self.resamples!=BOOTSTRAP_RESAMPLES or self.confidence!=CONFIDENCE:raise CampaignMetricsError("unfrozen interval")
def paired_family_bootstrap(pairs:Mapping[str,Sequence[float]],*,seed:int,resamples:int=BOOTSTRAP_RESAMPLES)->PairedInterval:
 if resamples!=BOOTSTRAP_RESAMPLES or type(seed)is not int:raise CampaignMetricsError("frozen bootstrap parameters")
 fs=sorted(pairs)
 if len(fs)<SCREENING_FAMILIES:raise CampaignMetricsError("undersized family sample")
 if not fs:return PairedInterval(None,None,None,0)
 vals=[]
 for f in fs:
  _id(f,"family");xs=tuple(pairs[f])
  if not xs:raise CampaignMetricsError("unpaired family")
  for x in xs:_num(x,"paired observation",False,False)
  vals.append(mean(xs))
 rng=Random(seed);s=sorted(mean(vals[rng.randrange(len(vals))]for _ in vals)for _ in range(BOOTSTRAP_RESAMPLES));return PairedInterval(mean(vals),s[249],s[9749],len(vals))
def noninferior(i:PairedInterval,*,hard_gates_pass:bool)->bool:
 if type(hard_gates_pass)is not bool:raise CampaignMetricsError("hard gates must be boolean")
 return hard_gates_pass and i.lower is not None and i.lower>NONINFERIORITY_MARGIN
@dataclass(frozen=True,slots=True)
class VariantSeal:
 protocol_digest:str;variant_id:str;recipe_digest:str;candidate_digest:str;evaluator_id:str;stage:str;block_digest:str;regime_id:str;sealed_at:str
 def __post_init__(self):
  for n in ("protocol_digest","recipe_digest","candidate_digest","block_digest"):_digest(getattr(self,n),n)
  for n in ("variant_id","evaluator_id","stage","regime_id","sealed_at"):_id(getattr(self,n),n)
@dataclass(frozen=True,slots=True)
class MatchProtocol:
 protocol_id:str;version:str;track_id:str;entrant_recipes:Mapping[str,Mapping[str,object]];variant_digest_rules:Mapping[str,object];candidate_seal_rule:str;scenario_task_ids:tuple[str,...];dataset_block_ids:tuple[str,...];pairing_rule:str;decision_rule:str;hybrid_recipes:Mapping[str,Mapping[str,object]];experiment_manifest:Mapping[str,object];elimination_losses:int=3;resource_lease_ref:str="lease-required";max_rounds:int=24;terminal_rules:tuple[str,...]=( "one_survivor","no_schedulable_pairs","max_rounds","lease_exhausted")
 def __post_init__(self):
  for n in ("protocol_id","version","track_id","resource_lease_ref"):_id(getattr(self,n),n)
  if self.elimination_losses!=3 or self.max_rounds!=24 or set(self.terminal_rules)!={"one_survivor","no_schedulable_pairs","max_rounds","lease_exhausted"}:raise CampaignMetricsError("closed tournament rules required")
  er=_freeze(self.entrant_recipes);hr=_freeze(self.hybrid_recipes);object.__setattr__(self,"entrant_recipes",er);object.__setattr__(self,"hybrid_recipes",hr);object.__setattr__(self,"variant_digest_rules",_freeze(self.variant_digest_rules));object.__setattr__(self,"experiment_manifest",_freeze(self.experiment_manifest));object.__setattr__(self,"scenario_task_ids",tuple(self.scenario_task_ids));object.__setattr__(self,"dataset_block_ids",tuple(self.dataset_block_ids))
  req={"MB0":"builder-component","MB1":"builder-component","MB2":"builder-component","MB3":"builder-component","MC0":"whole-campaign","MC1":"whole-campaign"}
  if set(er)!=set(req) or set(hr)!={"MH1","MH2","MH3","MH4"}:raise CampaignMetricsError("exact MB/MC/MH recipes required")
  seen=set()
  for k,r in {**er,**hr}.items():
   if not isinstance(r,Mapping)or r.get("track")!=req.get(k,"whole-campaign")or set(RECIPE_FIELDS)-set(r):raise CampaignMetricsError("incomplete recipe")
   for f in RECIPE_FIELDS:_digest(r[f],f)
   d=canonical_digest({f:r[f]for f in RECIPE_FIELDS})
   if d in seen:raise CampaignMetricsError("duplicate complete behavior digest")
   seen.add(d)
  if len(self.scenario_task_ids)<SCREENING_FAMILIES or set(self.dataset_block_ids)!={"development-screening","harder-hybrid-development","promotion_holdout"}:raise CampaignMetricsError("frozen task/block metadata required")
 @property
 def protocol_digest(self):return canonical_digest(self.to_document())
 def to_document(self):return {n:getattr(self,n)for n in self.__dataclass_fields__}
 def recipe(self,v):return ({**dict(self.entrant_recipes),**dict(self.hybrid_recipes)}).get(v)
 def validate_seals(self,seals:Iterable[VariantSeal],*,admission:AdmittedProtocol|None=None,final=False,evaluator_id:str|None=None)->None:
  _require_admission(self,admission,stage="final" if final else None)
  prior={};finals=[]
  for s in seals:
   if s.protocol_digest!=self.protocol_digest or self.recipe(s.variant_id)is None or s.stage not in {"original","hybrid","final"}:raise CampaignMetricsError("unknown variant/protocol/stage")
   if s.evaluator_id!=admission.stage_evidence.evaluator.signer_id or (evaluator_id is not None and s.evaluator_id!=evaluator_id):raise CampaignMetricsError("wrong evaluator")
   if s.stage!=admission.stage_evidence.stage or s.block_digest!=admission.stage_evidence.block_digest:raise CampaignMetricsError("seal stage/block mismatch")
   expected=canonical_digest({f:self.recipe(s.variant_id)[f]for f in RECIPE_FIELDS})
   if s.recipe_digest!=expected:raise CampaignMetricsError("seal recipe mismatch")
   if(s.variant_id,s.stage)in prior:raise CampaignMetricsError("stage rebinding")
   prior[s.variant_id,s.stage]=s
   if s.stage=="final":finals.append(s)
  if final:
   if len(finals)!=2 or len({x.regime_id for x in finals})!=1 or any(x.block_digest!=canonical_digest("promotion_holdout")for x in finals):raise CampaignMetricsError("invalid final custody")
   ids={x.variant_id for x in finals}
   if not(ids&set(self.entrant_recipes)and ids&set(self.hybrid_recipes)):raise CampaignMetricsError("final needs original/hybrid")
   for x in finals:
    before=prior.get((x.variant_id,"original"if x.variant_id in self.entrant_recipes else"hybrid"))
    if before is None or before.candidate_digest!=x.candidate_digest:raise CampaignMetricsError("final changed/unqualified")
def load_match_protocol(path:str|Path)->MatchProtocol:
 return _load_match_protocol(path,allow_unsealed=False)
def _load_match_protocol(path:str|Path,*,allow_unsealed:bool)->MatchProtocol:
 d=json.loads(Path(path).read_text(encoding="utf-8"));seed=d.pop("recipe_seed",None);manifest=d.get("experiment_manifest",{});d.pop("kind",None);d.pop("status",None);d.pop("protocol_digest",None)
 if not allow_unsealed and (manifest.get("holdout_signature_status")!="SIGNED" or manifest.get("custody_status")!="ATTESTED" or seed):raise CampaignMetricsError("external N30 blocker: concrete recipes, signed holdout custody required")
 if seed and not d["entrant_recipes"]:
  def recipe(ident,track):
   return {"track":track,**{f:canonical_digest([seed,ident,f]) for f in RECIPE_FIELDS}}
  d["entrant_recipes"]={x:recipe(x,"builder-component") for x in ("MB0","MB1","MB2","MB3")}|{x:recipe(x,"whole-campaign") for x in ("MC0","MC1")}
  d["hybrid_recipes"]={x:recipe(x,"whole-campaign") for x in ("MH1","MH2","MH3","MH4")}
 return MatchProtocol(**d)
@dataclass(frozen=True,slots=True)
class MatchProtocolInspection:
 """Opaque audit projection; deliberately has no schedule, seal, or recipe API."""
 protocol_digest:str
 status:str
 blockers:tuple[str,...]
 document_digest:str
def load_match_protocol_for_inspection(path:str|Path)->MatchProtocolInspection:
 """Parse only enough deferred metadata to audit blockers; never returns a protocol."""
 raw=Path(path).read_bytes();d=json.loads(raw)
 manifest=d.get("experiment_manifest",{})
 return MatchProtocolInspection(canonical_digest(d),str(d.get("status","UNKNOWN")),tuple(sorted(k for k,v in manifest.items() if v is None or (isinstance(v,str) and v.startswith("OPEN_")))),canonical_digest(raw.decode("utf-8")))
@dataclass(frozen=True,slots=True)
class ScheduledPair:left:str;right:str|None;bye:bool=False;block_id:str|None=None
def schedule_round(entrants:Sequence[str],losses:Mapping[str,int],byes:Mapping[str,int],*,round_number:int,inconclusive_meetings:Mapping[frozenset[str],int]|None=None,blocks:Sequence[str]=())->tuple[ScheduledPair,...]:
 if round_number<1 or round_number>24:raise CampaignMetricsError("round outside bound")
 if len(set(entrants))!=len(entrants):raise CampaignMetricsError("duplicate entrant")
 a=sorted(set(entrants),key=lambda x:(losses.get(x,0),x));r=(round_number-1)%len(a)if a else 0;a=a[r:]+a[:r];out=[]
 if len(a)%2:b=min(a,key=lambda x:(byes.get(x,0),x));a.remove(b);out.append(ScheduledPair(b,None,True))
 prior=inconclusive_meetings or {}
 while a:
  x=a.pop(0);i=next((i for i,y in enumerate(a)if prior.get(frozenset((x,y)),0)<2),None);out.append(ScheduledPair(x,a.pop(i)if i is not None else None,False,blocks[(round_number+len(out)-2)%len(blocks)]if blocks else None))
 return tuple(out)
@dataclass(frozen=True,slots=True)
class BracketState:
 protocol_digest:str;stage:str;track:str;round_number:int=0;losses:Mapping[str,int]=field(default_factory=dict);byes:Mapping[str,int]=field(default_factory=dict);inconclusive:Mapping[frozenset[str],int]=field(default_factory=dict);quarantined:frozenset[str]=frozenset();terminal:str|None=None;applied_receipt_digests:frozenset[str]=frozenset()
 def __post_init__(self):
  for n in ("protocol_digest","stage","track"):_id(getattr(self,n),n)
  if type(self.round_number)is not int or self.round_number<0 or self.round_number>24:raise CampaignMetricsError("invalid round")
  for n in ("losses","byes","inconclusive"):object.__setattr__(self,n,_freeze(getattr(self,n)))
  for pair,count in self.inconclusive.items():
   if not isinstance(pair,frozenset) or len(pair)!=2 or any(not isinstance(x,str) for x in pair) or type(count)is not int or count<0:raise CampaignMetricsError("invalid inconclusive matchup")
  for digest in self.applied_receipt_digests:_digest(digest,"applied receipt")
 def schedule(self,p:MatchProtocol,*,admission:AdmittedProtocol|None=None,lease_active=True):
  _require_admission(p,admission,stage=self.stage)
  if self.protocol_digest!=p.protocol_digest:raise CampaignMetricsError("foreign protocol")
  if self.terminal:return ()
  if not lease_active:object.__setattr__(self,"terminal","lease_exhausted");return ()
  if self.round_number>=p.max_rounds:object.__setattr__(self,"terminal","max_rounds");return ()
  if self.stage not in {"original","hybrid","final"}:raise CampaignMetricsError("unknown stage")
  source=dict(p.entrant_recipes) if self.stage=="original" else (dict(p.hybrid_recipes) if self.stage=="hybrid" else {})
  ids=[x for x,r in source.items()if r["track"]==self.track and x not in self.quarantined and self.losses.get(x,0)<3]
  if len(ids)==1:object.__setattr__(self,"terminal","one_survivor");return ()
  blocks=("development-screening",) if self.stage=="original" else (("harder-hybrid-development",) if self.stage=="hybrid" else ())
  return schedule_round(ids,self.losses,self.byes,round_number=self.round_number+1,inconclusive_meetings=self.inconclusive,blocks=blocks)
 def apply(self,p:MatchProtocol,pairs:Sequence[ScheduledPair],outcomes:Mapping[frozenset[str],str],*,receipt:IssuedReceipt|None=None,admission:AdmittedProtocol|None=None,lease_active=True):
  _require_admission(p,admission,stage=self.stage)
  if receipt is None or receipt.stage!=self.stage or receipt.round_number!=self.round_number+1 or receipt.evaluator_id!=admission.stage_evidence.evaluator.signer_id or receipt.block_digest!=admission.stage_evidence.block_digest:raise CampaignMetricsError("missing or mismatched issued receipt")
  if receipt.receipt_digest in self.applied_receipt_digests:raise CampaignMetricsError("receipt replay")
  if not lease_active:return BracketState(self.protocol_digest,self.stage,self.track,self.round_number,self.losses,self.byes,self.inconclusive,self.quarantined,"lease_exhausted")
  l=dict(self.losses);b=dict(self.byes);i=dict(self.inconclusive);q=set(self.quarantined)
  issued=tuple(self.schedule(p,admission=admission,lease_active=True));allowed={x.left if x.right is None else (x.left,x.right,x.bye,x.block_id) for x in issued}
  if not issued or issued[0].right is None or (receipt.left,receipt.right)!=(issued[0].left,issued[0].right) or receipt.seed!=admission.stage_evidence.seed or receipt.task_id not in p.scenario_task_ids:raise CampaignMetricsError("receipt does not bind issued task/orientation/seed")
  if len(pairs)!=len(set((x.left,x.right,x.bye,x.block_id) for x in pairs)):raise CampaignMetricsError("duplicate issued pair")
  for x in pairs:
   if (x.left if x.right is None else (x.left,x.right,x.bye,x.block_id)) not in allowed:raise CampaignMetricsError("pair was not issued")
   if x.bye:b[x.left]=b.get(x.left,0)+1;continue
   if x.right is None:continue
   o=outcomes.get(frozenset((x.left,x.right)),"INCONCLUSIVE");k=frozenset((x.left,x.right))
   if o not in {"LEFT","RIGHT","DRAW","INCONCLUSIVE","QUARANTINE_LEFT","QUARANTINE_RIGHT"}:raise CampaignMetricsError("unknown outcome")
   if o=="LEFT":l[x.right]=l.get(x.right,0)+1
   elif o=="RIGHT":l[x.left]=l.get(x.left,0)+1
   elif o=="QUARANTINE_LEFT":q.add(x.left)
   elif o=="QUARANTINE_RIGHT":q.add(x.right)
   else:i[k]=i.get(k,0)+1
  n=self.round_number+1;terminal="max_rounds"if n>=p.max_rounds else None;return BracketState(self.protocol_digest,self.stage,self.track,n,l,b,i,frozenset(q),terminal,self.applied_receipt_digests|frozenset((receipt.receipt_digest,)))
def decide_match(success:PairedInterval,cost_ratio:PairedInterval,time_ratio:PairedInterval,*,left_hard_gates:bool,right_hard_gates:bool)->str:
 if type(left_hard_gates)is not bool or type(right_hard_gates)is not bool:raise CampaignMetricsError("hard gates boolean")
 if not left_hard_gates and not right_hard_gates:return"QUARANTINE_BOTH"
 if not left_hard_gates:return"QUARANTINE_LEFT"
 if not right_hard_gates:return"QUARANTINE_RIGHT"
 if success.lower is None:return"INCONCLUSIVE"
 if success.lower>0:return"LEFT"
 if success.upper<0:return"RIGHT"
 ln=noninferior(success,hard_gates_pass=True);rn=-success.upper>NONINFERIORITY_MARGIN
 if not(ln and rn)or None in(cost_ratio.lower,cost_ratio.upper,time_ratio.lower,time_ratio.upper):return"DRAW"
 if(cost_ratio.upper<1 and time_ratio.upper<=1.1)or(time_ratio.upper<1 and cost_ratio.upper<=1.1):return"LEFT"
 if(cost_ratio.lower>1 and time_ratio.lower>=1/1.1)or(time_ratio.lower>1 and cost_ratio.lower>=1/1.1):return"RIGHT"
 return"DRAW"
__all__=["AdmittedProtocol","AttemptMetric","BracketState","CampaignMetricsError","IssuedReceipt","LeaseRecord","MatchProtocol","MatchProtocolInspection","PairedInterval","RECIPE_FIELDS","REQUIRED_STRATA","ScheduledPair","SignedCustodyEnvelope","StageEvidence","VariantSeal","admit_protocol","canonical_digest","decide_match","load_match_protocol","load_match_protocol_for_inspection","noninferior","paired_family_bootstrap","reject_receipt_replay","schedule_round","summarize_attempts"]
