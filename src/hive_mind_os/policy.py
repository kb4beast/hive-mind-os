from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

from .models import AutonomyLevel, RiskTier, Role


class Action(StrEnum):
    READ_REPOSITORY = "read_repository"
    SEARCH_WEB = "search_web"
    WRITE_WORKSPACE = "write_workspace"
    RUN_COMMANDS = "run_commands"
    CREATE_BRANCH = "create_branch"
    OPEN_PULL_REQUEST = "open_pull_request"
    MERGE_PULL_REQUEST = "merge_pull_request"
    DEPLOY = "deploy"
    MANAGE_SECRETS = "manage_secrets"
    SPEND_MONEY = "spend_money"


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
    Action.CREATE_BRANCH: RequiredLevel.REPOSITORY,
    Action.OPEN_PULL_REQUEST: RequiredLevel.REPOSITORY,
    Action.MERGE_PULL_REQUEST: RequiredLevel.DELIVERY,
    Action.DEPLOY: RequiredLevel.DELIVERY,
    Action.MANAGE_SECRETS: RequiredLevel.FULL,
    Action.SPEND_MONEY: RequiredLevel.FULL,
}


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str


class PolicyEngine:
    """Fail-closed authority checks for every side effect."""

    def __init__(self, autonomy: AutonomyLevel = AutonomyLevel.SANDBOX) -> None:
        self.autonomy = autonomy

    def decide(self, role: Role, action: Action, risk: RiskTier) -> PolicyDecision:
        required = ACTION_LEVEL[action]
        if self.autonomy < required:
            return PolicyDecision(False, f"{action} requires autonomy level {int(required)}")
        if risk is RiskTier.CRITICAL and action in {
            Action.MERGE_PULL_REQUEST,
            Action.DEPLOY,
            Action.MANAGE_SECRETS,
            Action.SPEND_MONEY,
        }:
            return PolicyDecision(False, "critical-risk irreversible actions require an external policy grant")
        if role is Role.EXPLORER and action not in {Action.READ_REPOSITORY, Action.SEARCH_WEB}:
            return PolicyDecision(False, "explorer is read-only by role contract")
        return PolicyDecision(True, "allowed by autonomy level and role contract")
