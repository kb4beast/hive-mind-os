"""The direct implementation of the architect agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class ArchitectAgent(Agent):
    role = Role.ARCHITECT
    contract = RoleContract(
        role,
        "Design scalable, secure, evolvable solutions and explicit decision records.",
        ("architecture", "interfaces", "threat model", "migration plan"),
        ("read_repository", "model_system", "write_design"),
        ("constraints are satisfied", "failure modes are addressed"),
    )
    capabilities = RoleCapabilities(
        ("read", "propose_design_artifact"),
        ("implementation_approval", "weaken_constraints"),
        ("architecture", "interfaces", "threat_model", "rollback_plan"),
    )
    next_role = Role.BUILDER
