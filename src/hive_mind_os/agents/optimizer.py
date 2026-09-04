"""The direct implementation of the optimizer agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class OptimizerAgent(Agent):
    role = Role.OPTIMIZER
    contract = RoleContract(
        role,
        "Measure outcomes, run controlled experiments, and improve the system.",
        ("metrics", "experiment result", "improvement proposal"),
        ("query_ledger", "run_evaluations", "run_commands", "propose_skill_change"),
        ("improvement beats baseline", "regressions stay within budget"),
    )
    capabilities = RoleCapabilities(
        ("query_ledger", "request_held_out_experiment", "register_candidate"),
        ("promote", "change_champion", "change_dataset", "policy_change"),
        ("comparison", "measurement_caveats", "promotion_recommendation"),
    )
    next_role = None
