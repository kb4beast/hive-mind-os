"""N07 explicit model routing and bounded repair leases."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .runtime_contracts import canonical_digest, require_digest, require_identifier


class RouteStatus(StrEnum):
    READY = "READY"
    BLOCKED_CAPABILITY = "BLOCKED_CAPABILITY"
    BLOCKED_BUDGET = "BLOCKED_BUDGET"
    NO_MODEL = "NO_MODEL"


@dataclass(frozen=True, slots=True)
class ModelRoute:
    provider_id: str
    model_id: str
    effort: str
    data_policy_digest: str
    capability_ids: tuple[str, ...]
    max_calls: int
    max_tokens: int

    def __post_init__(self):
        for x in (self.provider_id, self.model_id, self.effort):
            require_identifier(x, "route field")
        require_digest(self.data_policy_digest, "data_policy_digest")
        if not self.capability_ids or len(set(self.capability_ids)) != len(
            self.capability_ids
        ):
            raise ValueError("route must have unique capabilities")
        if any(not isinstance(x, str) or not x for x in self.capability_ids):
            raise ValueError("route capabilities must be identifiers")
        if min(self.max_calls, self.max_tokens) < 0 or any(
            isinstance(x, bool) for x in (self.max_calls, self.max_tokens)
        ):
            raise ValueError("route must have nonnegative integer limits")

    @property
    def digest(self):
        return canonical_digest(
            {
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "effort": self.effort,
                "data_policy_digest": self.data_policy_digest,
                "capability_ids": self.capability_ids,
                "max_calls": self.max_calls,
                "max_tokens": self.max_tokens,
            }
        )


@dataclass(frozen=True, slots=True)
class RouteDecision:
    status: RouteStatus
    route: ModelRoute | None
    reason: str


def select_route(
    *,
    required_capabilities: tuple[str, ...],
    permitted_policy_digest: str,
    routes: tuple[ModelRoute, ...],
    deterministic: bool = False,
) -> RouteDecision:
    require_digest(permitted_policy_digest, "permitted_policy_digest")
    if any(not isinstance(x, str) or not x for x in required_capabilities):
        return RouteDecision(
            RouteStatus.BLOCKED_CAPABILITY, None, "invalid required capability"
        )
    if deterministic:
        return RouteDecision(RouteStatus.NO_MODEL, None, "deterministic task")
    for route in routes:
        if route.data_policy_digest == permitted_policy_digest and set(
            required_capabilities
        ).issubset(route.capability_ids):
            return RouteDecision(RouteStatus.READY, route, "admitted route")
    return RouteDecision(
        RouteStatus.BLOCKED_CAPABILITY,
        None,
        "no admitted route matches capability and data policy",
    )


@dataclass(frozen=True, slots=True)
class RepairLease:
    lease_digest: str
    used_calls: int = 0
    used_tokens: int = 0
    repair_attempts: int = 0
    max_repairs: int = 2

    def __post_init__(self):
        require_digest(self.lease_digest, "lease_digest")
        if (
            min(
                self.used_calls,
                self.used_tokens,
                self.repair_attempts,
                self.max_repairs,
            )
            < 0
        ):
            raise ValueError("lease values must be nonnegative")

    def consume(
        self,
        *,
        calls: int,
        tokens: int,
        repeated_failure: bool = False,
        route: ModelRoute | None = None,
    ) -> "RepairLease":
        if any(type(x) is not int or x < 0 for x in (calls, tokens)) or (
            repeated_failure and self.repair_attempts >= self.max_repairs
        ):
            raise ValueError("repair lease exhausted or invalid")
        if route is not None and (
            self.used_calls + calls > route.max_calls
            or self.used_tokens + tokens > route.max_tokens
        ):
            raise ValueError("route allowance exhausted")
        return RepairLease(
            self.lease_digest,
            self.used_calls + calls,
            self.used_tokens + tokens,
            self.repair_attempts + int(repeated_failure),
            self.max_repairs,
        )

    @property
    def exhausted(self) -> bool:
        return self.repair_attempts >= self.max_repairs


@dataclass(frozen=True, slots=True)
class RouteUsageReceipt:
    route_digest: str
    calls: int
    tokens: int
    status: RouteStatus
    reason: str

    def __post_init__(self) -> None:
        require_digest(self.route_digest, "route_digest")
        if (
            any(type(x) is not int or x < 0 for x in (self.calls, self.tokens))
            or not isinstance(self.status, RouteStatus)
            or not self.reason.strip()
        ):
            raise ValueError("invalid route usage receipt")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "route_digest": self.route_digest,
                "calls": self.calls,
                "tokens": self.tokens,
                "status": self.status.value,
                "reason": self.reason,
            }
        )


@dataclass(frozen=True, slots=True)
class RouteEscalation:
    failed_route_digest: str
    failure_fingerprint: str
    hypothesis: str
    retained_candidate_digest: str
    delta_context_digest: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.failed_route_digest, "failed_route_digest"),
            (self.failure_fingerprint, "failure_fingerprint"),
            (self.retained_candidate_digest, "retained_candidate_digest"),
            (self.delta_context_digest, "delta_context_digest"),
        ):
            require_digest(value, label)
        if not self.hypothesis.strip():
            raise ValueError("escalation hypothesis is required")

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "failed_route_digest": self.failed_route_digest,
                "failure_fingerprint": self.failure_fingerprint,
                "hypothesis": self.hypothesis,
                "retained_candidate_digest": self.retained_candidate_digest,
                "delta_context_digest": self.delta_context_digest,
            }
        )
