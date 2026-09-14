"""Endpoint reconstruction manifests, separate from PIT history (N22)."""
from dataclasses import dataclass
from enum import StrEnum
class EpisodeState(StrEnum): REGISTERED="REGISTERED"; SOURCE_ADMITTED="SOURCE_ADMITTED"; BLOCKED_SOURCE="BLOCKED_SOURCE"; DEGENERATE_EPISODE="DEGENERATE_EPISODE"
class EndpointError(ValueError): pass
@dataclass(frozen=True, slots=True)
class EndpointEpisodeManifest:
 episode_id:str; source_record_id:str; mode:str; first_commit:str; first_tree_digest:str; final_commit:str; final_tree_digest:str; readme_digest:str|None; readme_origin_commit:str|None; brief_visibility:str; repository_family_id:str; dataset_split:str; dependency_manifest_digest:str; fixture_manifest_digest:str; source_dispositions:tuple[str,...]; obligation_refs:tuple[str,...]; state:EpisodeState=EpisodeState.REGISTERED
 def __post_init__(self):
  if self.mode!="endpoint_reconstruction": raise EndpointError("only endpoint_reconstruction is supported")
  if self.dataset_split not in {"training","development","promotion_holdout"}: raise EndpointError("invalid dataset split")
  if self.first_commit==self.final_commit or self.first_tree_digest==self.final_tree_digest: object.__setattr__(self,"state",EpisodeState.DEGENERATE_EPISODE)
