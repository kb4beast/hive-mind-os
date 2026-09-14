"""Endpoint reconstruction manifests, separate from PIT history (N22)."""
from dataclasses import dataclass
from enum import StrEnum
from .brain_kernel.canonical import canonical_digest, canonical_document
from .durable_contracts import ContractStore
class EpisodeState(StrEnum): REGISTERED="REGISTERED"; SOURCE_ADMITTED="SOURCE_ADMITTED"; BLOCKED_SOURCE="BLOCKED_SOURCE"; DEGENERATE_EPISODE="DEGENERATE_EPISODE"
class EndpointError(ValueError): pass
@dataclass(frozen=True, slots=True)
class EndpointEpisodeManifest:
 episode_id:str; source_record_id:str; mode:str; first_commit:str; first_tree_digest:str; final_commit:str; final_tree_digest:str; readme_digest:str|None; readme_origin_commit:str|None; brief_visibility:str; repository_family_id:str; dataset_split:str; dependency_manifest_digest:str; fixture_manifest_digest:str; source_dispositions:tuple[str,...]; obligation_refs:tuple[str,...]; state:EpisodeState=EpisodeState.REGISTERED
 def __post_init__(self):
  if self.mode!="endpoint_reconstruction": raise EndpointError("only endpoint_reconstruction is supported")
  if self.dataset_split not in {"training","development","promotion_holdout"}: raise EndpointError("invalid dataset split")
  if self.first_commit==self.final_commit or self.first_tree_digest==self.final_tree_digest: object.__setattr__(self,"state",EpisodeState.DEGENERATE_EPISODE)
  if any(type(v) is not str or not v.strip() for v in (self.episode_id,self.source_record_id,self.first_commit,self.first_tree_digest,self.final_commit,self.final_tree_digest,self.brief_visibility,self.repository_family_id,self.dependency_manifest_digest,self.fixture_manifest_digest)): raise EndpointError("manifest identity is required")
  if self.brief_visibility not in {"initial_readme","provided_current_readme","owner_authored_brief"}: raise EndpointError("invalid brief visibility")
 @property
 def digest(self): return canonical_digest(self)
 def to_dict(self): return canonical_document(self)
 @classmethod
 def from_dict(cls,value):
  fields={"episode_id","source_record_id","mode","first_commit","first_tree_digest","final_commit","final_tree_digest","readme_digest","readme_origin_commit","brief_visibility","repository_family_id","dataset_split","dependency_manifest_digest","fixture_manifest_digest","source_dispositions","obligation_refs","state"}
  if set(value)!=fields: raise EndpointError("closed episode schema")
  return cls(**{**value,"state":EpisodeState(value["state"]),"source_dispositions":tuple(value["source_dispositions"]),"obligation_refs":tuple(value["obligation_refs"])})

class EndpointManifestStore:
 def __init__(self,path): self._store=ContractStore(path,EndpointEpisodeManifest.from_dict)
 def put(self,manifest): return self._store.put(manifest.digest,manifest)
 def get(self,digest): return self._store.get(digest)
