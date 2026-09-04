"""The direct implementation of the integrator agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class IntegratorAgent(Agent):
    role = Role.INTEGRATOR
    contract = RoleContract(
        role,
        "Connect systems, data, tools, and workflows through stable contracts.",
        ("integration contract", "compatibility result", "data lineage"),
        ("inspect_interfaces", "write_adapters", "run_contract_tests"),
        ("contracts are versioned", "provenance is preserved"),
    )
    capabilities = RoleCapabilities(
        ("read", "request_contract_test", "request_builder_work"),
        ("write", "merge", "conceal_breaking_change"),
        ("compatibility_report", "data_lineage", "integration_result"),
    )
    next_role = Role.BUILDER
