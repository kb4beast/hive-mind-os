"""The direct implementation of the curator agent."""

from __future__ import annotations

from ..models import Role
from .base import Agent
from .contracts import RoleCapabilities, RoleContract


class CuratorAgent(Agent):
    role = Role.CURATOR
    contract = RoleContract(
        role,
        "Protect quality, trust, compliance, and factual integrity.",
        ("verification report", "defect findings", "release recommendation"),
        (
            "read_repository",
            "write_workspace",
            "run_tests",
            "run_commands",
            "inspect_diff",
            "security_scan",
        ),
        ("claims have evidence", "critical regressions are absent"),
        ("exact candidate", "independent verification", "non-mutating review"),
    )
    capabilities = RoleCapabilities(
        ("read_fresh_workspace", "request_test", "inspect_diff"),
        ("candidate_write", "accept", "reuse_builder_scratchpad"),
        ("check_results", "defect_findings", "verdict", "evidence_bundle"),
    )
    next_role = Role.INTEGRATOR
    requires_evaluator_mode = True
