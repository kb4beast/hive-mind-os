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
    tenant_id: str | None
    repository_id: str | None
    actor_id: str | None
    decision_id: str | None
    lease_id: str | None
    public_release_decision_id: str | None
    public_release_decided_by: str | None
    public_release_subject_digest: str | None


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
    tenant_id: str | None = None,
    repository_id: str | None = None,
    actor_id: str | None = None,
    decision_id: str | None = None,
    lease_id: str | None = None,
    public_release_decision_id: str | None = None,
    public_release_decided_by: str | None = None,
    public_release_subject_digest: str | None = None,
) -> AuthorityDecision:
    """Intersect every authority dimension; evidence never grants authority."""

    mapped = FOUNDATION_ACTION_MAP.get(action)

    def deny(reason: str) -> AuthorityDecision:
        return AuthorityDecision(
            False,
            reason,
            mapped,
            action if mapped is not None else None,
            tenant_id,
            repository_id,
            actor_id,
            decision_id,
            lease_id,
            public_release_decision_id,
            public_release_decided_by,
            public_release_subject_digest,
        )

    if mapped is None:
        return deny("unknown foundation action")
    if action == "foundation.telemetry.write" and recorder_identity != TRUSTED_RECORDER:
        return deny("telemetry requires the trusted recorder")
    if role is None or role not in ROLE_CEILINGS:
        return deny("missing or invalid role")
    if action not in ROLE_CEILINGS[role]:
        return deny("action exceeds role ceiling")
    if policy_decision is None or not policy_decision.allowed:
        return deny("policy did not allow the mapped action")
    if lease_actions is None or action not in lease_actions:
        return deny("lease does not grant the action")
    if adapter_actions is None or action not in adapter_actions:
        return deny("adapter does not enforce the action")
    if mission_risk_allowed is not True:
        return deny("mission risk is not allowed")
    if budget_available is not True:
        return deny("resource budget is unavailable")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (
            tenant_id,
            repository_id,
            actor_id,
            decision_id,
            lease_id,
        )
    ):
        return deny("authority scope, actor, decision, and lease are required")
    if (public_release_decision_id is None) != (
        public_release_decided_by is None
    ):
        return deny("public-release decision identity is incomplete")
    if (public_release_decision_id is None) != (
        public_release_subject_digest is None
    ):
        return deny("public-release subject binding is incomplete")
    if (
        public_release_decided_by is not None
        and public_release_decided_by == actor_id
    ):
        return deny("public release must be independently decided")
    return AuthorityDecision(
        True,
        "all authority dimensions allowed",
        mapped,
        action,
        tenant_id,
        repository_id,
        actor_id,
        decision_id,
        lease_id,
        public_release_decision_id,
        public_release_decided_by,
        public_release_subject_digest,
    )
