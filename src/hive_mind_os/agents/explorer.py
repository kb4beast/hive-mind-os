"""The direct implementation of the explorer agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class ExplorerAgent(Agent):
    role = Role.EXPLORER
    contract = RoleContract(
        role,
        "Find the highest-value problems using repository, user, product, and external evidence.",
        ("problem statement", "evidence map", "ranked opportunities"),
        (
            "read_repository",
            "search_web",
            "inspect_history",
            "run_analysis",
            "run_commands",
        ),
        ("problem is evidence-backed", "alternatives were considered"),
    )
    capabilities = RoleCapabilities(
        ("read", "analyze", "request_source_search"),
        ("write", "accept", "candidate_mutation"),
        ("evidence_map", "candidate", "uncertainty"),
    )
    next_role = Role.ARCHITECT
