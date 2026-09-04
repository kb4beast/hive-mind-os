"""The direct implementation of the builder agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class BuilderAgent(Agent):
    role = Role.BUILDER
    contract = RoleContract(
        role,
        "Implement the smallest complete change and ship it with executable verification.",
        ("implementation", "tests", "change summary"),
        (
            "read_repository",
            "model_system",
            "write_workspace",
            "run_commands",
            "create_branch",
            "open_pull_request",
            "comment_pull_request",
        ),
        ("tests pass", "change is traceable to the objective"),
    )
    capabilities = RoleCapabilities(
        ("request_isolated_write", "request_command", "request_branch_commit"),
        ("accept", "protected_branch", "merge", "deploy", "modify_sealed_acceptance"),
        ("candidate", "tests", "change_summary", "effect_intents"),
    )
    next_role = Role.CURATOR
