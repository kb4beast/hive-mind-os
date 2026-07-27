from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from .models import AutonomyLevel, RiskTier, Role


class Action(StrEnum):
    READ_REPOSITORY = "read_repository"
    SEARCH_WEB = "search_web"
    WRITE_WORKSPACE = "write_workspace"
    RUN_COMMANDS = "run_commands"
    CREATE_AGENT_VARIANT = "create_agent_variant"
    CREATE_BRANCH = "create_branch"
    OPEN_PULL_REQUEST = "open_pull_request"
    MERGE_PULL_REQUEST = "merge_pull_request"
    DEPLOY = "deploy"
    MANAGE_SECRETS = "manage_secrets"
    SPEND_MONEY = "spend_money"
    SELF_REPLICATE_UNBOUNDED = "self_replicate_unbounded"
    MUTATE_MISSION_CHARTER = "mutate_mission_charter"
    MUTATE_POLICY = "mutate_policy"
    CONCEAL_ACTIVITY = "conceal_activity"


class RequiredLevel(IntEnum):
    READ = AutonomyLevel.OBSERVE
    ADVISE = AutonomyLevel.ADVISE
    SANDBOX = AutonomyLevel.SANDBOX
    REPOSITORY = AutonomyLevel.REPOSITORY
    DELIVERY = AutonomyLevel.DELIVERY
    FULL = AutonomyLevel.GOVERNED_FULL


ACTION_LEVEL: dict[Action, RequiredLevel] = {
    Action.READ_REPOSITORY: RequiredLevel.READ,
    Action.SEARCH_WEB: RequiredLevel.READ,
    Action.WRITE_WORKSPACE: RequiredLevel.SANDBOX,
    Action.RUN_COMMANDS: RequiredLevel.SANDBOX,
    Action.CREATE_AGENT_VARIANT: RequiredLevel.SANDBOX,
    Action.CREATE_BRANCH: RequiredLevel.REPOSITORY,
    Action.OPEN_PULL_REQUEST: RequiredLevel.REPOSITORY,
    Action.MERGE_PULL_REQUEST: RequiredLevel.DELIVERY,
    Action.DEPLOY: RequiredLevel.DELIVERY,
    Action.MANAGE_SECRETS: RequiredLevel.FULL,
    Action.SPEND_MONEY: RequiredLevel.FULL,
    Action.SELF_REPLICATE_UNBOUNDED: RequiredLevel.FULL,
    Action.MUTATE_MISSION_CHARTER: RequiredLevel.FULL,
    Action.MUTATE_POLICY: RequiredLevel.FULL,
    Action.CONCEAL_ACTIVITY: RequiredLevel.FULL,
}

PROHIBITED_ACTIONS = frozenset(
    {
        Action.SELF_REPLICATE_UNBOUNDED,
        Action.MUTATE_MISSION_CHARTER,
        Action.MUTATE_POLICY,
        Action.CONCEAL_ACTIVITY,
    }
)

EXTERNAL_GRANT_ACTIONS = frozenset(
    {
        Action.MERGE_PULL_REQUEST,
        Action.DEPLOY,
        Action.MANAGE_SECRETS,
        Action.SPEND_MONEY,
    }
)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str


class PolicyEngine:
    """Fail-closed authority checks for every side effect."""

    def __init__(self, autonomy: AutonomyLevel = AutonomyLevel.SANDBOX) -> None:
        if not isinstance(autonomy, AutonomyLevel):
            raise ValueError("autonomy must be an AutonomyLevel")
        self.autonomy = autonomy

    def decide(self, role: Role, action: Action, risk: RiskTier) -> PolicyDecision:
        if not isinstance(role, Role):
            return PolicyDecision(False, "invalid role identity")
        if not isinstance(action, Action):
            return PolicyDecision(False, "invalid action")
        if not isinstance(risk, RiskTier):
            return PolicyDecision(False, "invalid risk tier")
        if action in PROHIBITED_ACTIONS:
            return PolicyDecision(False, f"{action} violates a non-delegable autonomy invariant")
        required = ACTION_LEVEL[action]
        if self.autonomy < required:
            return PolicyDecision(False, f"{action} requires autonomy level {int(required)}")
        if action in EXTERNAL_GRANT_ACTIONS:
            return PolicyDecision(False, f"{action} requires an external policy grant")
        if role is Role.EXPLORER and action not in {
            Action.READ_REPOSITORY,
            Action.SEARCH_WEB,
            Action.RUN_COMMANDS,
        }:
            return PolicyDecision(False, "explorer is read-only by role contract")
        return PolicyDecision(True, "allowed by autonomy level and role contract")
