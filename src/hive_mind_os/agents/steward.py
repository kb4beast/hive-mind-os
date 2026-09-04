"""The direct implementation of the steward agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class StewardAgent(Agent):
    role = Role.STEWARD
    contract = RoleContract(
        role,
        "Keep code, infrastructure, dependencies, and operational knowledge healthy.",
        ("health report", "maintenance change", "operational runbook"),
        ("inspect_runtime", "manage_dependencies", "write_workspace", "run_tests"),
        ("system remains recoverable", "maintenance reduces measured risk"),
    )
    capabilities = RoleCapabilities(
        ("read_runtime_state", "request_recovery_test", "propose_maintenance_work"),
        ("trade_recoverability_for_speed",),
        ("recovery_proof", "operational_readiness", "maintenance_findings"),
    )
    next_role = Role.OPTIMIZER
