from __future__ import annotations

from dataclasses import dataclass

from .models import Role


@dataclass(frozen=True, slots=True)
class RoleContract:
    role: Role
    mission: str
    required_outputs: tuple[str, ...]
    default_capabilities: tuple[str, ...]
    quality_gates: tuple[str, ...]


# This compatibility facade is intentionally independent of the extension
# catalog. Optional or candidate package resources must never prevent the
# constitutional runtime from importing. Package parity is enforced by tests
# and by the separately loaded hive-core catalog.
ROLE_CONTRACTS: dict[Role, RoleContract] = {
    Role.ORCHESTRATOR: RoleContract(
        Role.ORCHESTRATOR,
        "Translate outcomes into bounded work, coordinate specialists, and manage tradeoffs.",
        ("objective decomposition", "execution plan", "risk register"),
        ("read_repository", "query_agents", "create_work_items"),
        ("acceptance criteria are testable", "dependencies are explicit"),
    ),
    Role.EXPLORER: RoleContract(
        Role.EXPLORER,
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
    ),
    Role.ARCHITECT: RoleContract(
        Role.ARCHITECT,
        "Design scalable, secure, evolvable solutions and explicit decision records.",
        ("architecture", "interfaces", "threat model", "migration plan"),
        ("read_repository", "model_system", "write_design"),
        ("constraints are satisfied", "failure modes are addressed"),
    ),
    Role.BUILDER: RoleContract(
        Role.BUILDER,
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
    ),
    Role.CURATOR: RoleContract(
        Role.CURATOR,
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
    ),
    Role.INTEGRATOR: RoleContract(
        Role.INTEGRATOR,
        "Connect systems, data, tools, and workflows through stable contracts.",
        ("integration contract", "compatibility result", "data lineage"),
        ("inspect_interfaces", "write_adapters", "run_contract_tests"),
        ("contracts are versioned", "provenance is preserved"),
    ),
    Role.STEWARD: RoleContract(
        Role.STEWARD,
        "Keep code, infrastructure, dependencies, and operational knowledge healthy.",
        ("health report", "maintenance change", "operational runbook"),
        ("inspect_runtime", "manage_dependencies", "write_workspace", "run_tests"),
        ("system remains recoverable", "maintenance reduces measured risk"),
    ),
    Role.OPTIMIZER: RoleContract(
        Role.OPTIMIZER,
        "Measure outcomes, run controlled experiments, and improve the system.",
        ("metrics", "experiment result", "improvement proposal"),
        (
            "query_ledger",
            "run_evaluations",
            "run_commands",
            "propose_skill_change",
        ),
        ("improvement beats baseline", "regressions stay within budget"),
    ),
}

DEFAULT_LIFECYCLE: tuple[Role, ...] = (
    Role.ORCHESTRATOR,
    Role.EXPLORER,
    Role.ARCHITECT,
    Role.BUILDER,
    Role.CURATOR,
    Role.INTEGRATOR,
    Role.STEWARD,
    Role.OPTIMIZER,
)

# The architecture retains all eight specialist contracts.  Only these roles have
# executable repository-mission capabilities today; the remainder are planned.
IMPLEMENTED_REPOSITORY_ROLES: tuple[Role, ...] = (
    Role.EXPLORER,
    Role.BUILDER,
    Role.CURATOR,
)
PLANNED_ROLES: tuple[Role, ...] = tuple(
    role for role in Role if role not in IMPLEMENTED_REPOSITORY_ROLES
)
