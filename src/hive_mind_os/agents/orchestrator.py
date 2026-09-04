"""The direct implementation of the orchestrator agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class OrchestratorAgent(Agent):
    role = Role.ORCHESTRATOR
    contract = RoleContract(
        role,
        "Translate outcomes into bounded work, coordinate specialists, and manage tradeoffs.",
        ("objective decomposition", "execution plan", "risk register"),
        ("read_repository", "query_agents", "create_work_items"),
        ("acceptance criteria are testable", "dependencies are explicit"),
    )
    capabilities = RoleCapabilities(
        ("query_state", "plan", "request_human_gate"),
        ("write", "accept", "verify", "merge", "policy_change"),
        ("objective_dag", "risk_register", "budget_allocation", "stop_conditions"),
    )
    next_role = Role.EXPLORER
