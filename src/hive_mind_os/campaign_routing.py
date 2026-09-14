"""N07 explicit model routing and bounded repair leases."""
from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum
from .runtime_contracts import canonical_digest, require_digest, require_identifier

class RouteStatus(StrEnum): READY="READY"; BLOCKED_CAPABILITY="BLOCKED_CAPABILITY"; BLOCKED_BUDGET="BLOCKED_BUDGET"; NO_MODEL="NO_MODEL"
@dataclass(frozen=True, slots=True)
class ModelRoute:
    provider_id: str; model_id: str; effort: str; data_policy_digest: str; capability_ids: tuple[str,...]; max_calls: int; max_tokens: int
    def __post_init__(self):
        for x in (self.provider_id,self.model_id,self.effort): require_identifier(x,"route field")
        require_digest(self.data_policy_digest,"data_policy_digest")
        if not self.capability_ids or min(self.max_calls,self.max_tokens)<0: raise ValueError("route must have capabilities and nonnegative limits")
    @property
    def digest(self): return canonical_digest({"provider_id":self.provider_id,"model_id":self.model_id,"effort":self.effort,"data_policy_digest":self.data_policy_digest,"capability_ids":self.capability_ids,"max_calls":self.max_calls,"max_tokens":self.max_tokens})
@dataclass(frozen=True, slots=True)
class RouteDecision:
    status: RouteStatus; route: ModelRoute|None; reason: str
def select_route(*, required_capabilities: tuple[str,...], permitted_policy_digest: str, routes: tuple[ModelRoute,...], deterministic: bool=False) -> RouteDecision:
    require_digest(permitted_policy_digest,"permitted_policy_digest")
    if deterministic: return RouteDecision(RouteStatus.NO_MODEL,None,"deterministic task")
    for route in routes:
        if route.data_policy_digest == permitted_policy_digest and set(required_capabilities).issubset(route.capability_ids): return RouteDecision(RouteStatus.READY,route,"admitted route")
    return RouteDecision(RouteStatus.BLOCKED_CAPABILITY,None,"no admitted route matches capability and data policy")
@dataclass(frozen=True, slots=True)
class RepairLease:
    lease_digest: str; used_calls:int=0; used_tokens:int=0; repair_attempts:int=0; max_repairs:int=2
    def __post_init__(self):
        require_digest(self.lease_digest,"lease_digest")
        if min(self.used_calls,self.used_tokens,self.repair_attempts,self.max_repairs)<0: raise ValueError("lease values must be nonnegative")
    def consume(self, *, calls:int, tokens:int, repeated_failure:bool=False) -> "RepairLease":
        if calls<0 or tokens<0 or (repeated_failure and self.repair_attempts>=self.max_repairs): raise ValueError("repair lease exhausted or invalid")
        return RepairLease(self.lease_digest,self.used_calls+calls,self.used_tokens+tokens,self.repair_attempts+int(repeated_failure),self.max_repairs)
