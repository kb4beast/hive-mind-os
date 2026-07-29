from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet

from hive_mind_os.models import Role
from hive_mind_os.policy import Action, PolicyDecision

FOUNDATION_ACTION_MAP: dict[str, Action] = {
    "foundation.repository.register": Action.WRITE_WORKSPACE,
    "foundation.memory.write": Action.WRITE_WORKSPACE,
    "foundation.opportunity.write": Action.WRITE_WORKSPACE,
    "foundation.telemetry.write": Action.WRITE_WORKSPACE,
    "foundation.outbox.deliver": Action.WRITE_WORKSPACE,
}
ROLE_CEILINGS: dict[Role, frozenset[str]] = {
    role: frozenset(FOUNDATION_ACTION_MAP)
    for role in Role
}
ROLE_CEILINGS[Role.EXPLORER] = frozenset(
    {"foundation.memory.write", "foundation.opportunity.write", "foundation.telemetry.write"}
)
TRUSTED_RECORDER = "foundation-usage-recorder-v1"


@dataclass(frozen=True, slots=True)
class AuthorityDecision:
    allowed: bool
    reason: str
    mapped_action: Action | None
    foundation_action: str | None
    public_release_allowed: bool


def decide_foundation_write(
    *,
    role: Role | None,
    action: str,
    policy_decision: PolicyDecision | None,
    lease_actions: AbstractSet[str] | None,
    adapter_actions: AbstractSet[str] | None,
    mission_risk_allowed: bool | None,
    budget_available: bool | None,
    recorder_identity: str | None = None,
    public_release_allowed: bool = False,
) -> AuthorityDecision:
    """Intersect every authority dimension; evidence never grants authority."""

    mapped = FOUNDATION_ACTION_MAP.get(action)
    if mapped is None:
        return AuthorityDecision(False, "unknown foundation action", None, None, False)
    if action == "foundation.telemetry.write" and recorder_identity != TRUSTED_RECORDER:
        return AuthorityDecision(
            False,
            "telemetry requires the trusted recorder",
            mapped,
            action,
            False,
        )
    if role is None or role not in ROLE_CEILINGS:
        return AuthorityDecision(
            False, "missing or invalid role", mapped, action, False
        )
    if action not in ROLE_CEILINGS[role]:
        return AuthorityDecision(
            False, "action exceeds role ceiling", mapped, action, False
        )
    if policy_decision is None or not policy_decision.allowed:
        return AuthorityDecision(
            False,
            "policy did not allow the mapped action",
            mapped,
            action,
            False,
        )
    if lease_actions is None or action not in lease_actions:
        return AuthorityDecision(
            False, "lease does not grant the action", mapped, action, False
        )
    if adapter_actions is None or action not in adapter_actions:
        return AuthorityDecision(
            False,
            "adapter does not enforce the action",
            mapped,
            action,
            False,
        )
    if mission_risk_allowed is not True:
        return AuthorityDecision(
            False, "mission risk is not allowed", mapped, action, False
        )
    if budget_available is not True:
        return AuthorityDecision(
            False,
            "resource budget is unavailable",
            mapped,
            action,
            False,
        )
    return AuthorityDecision(
        True,
        "all authority dimensions allowed",
        mapped,
        action,
        public_release_allowed,
    )
