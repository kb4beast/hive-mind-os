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
        ("read_repository", "search_web", "inspect_history", "run_analysis"),
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
        ("write_workspace", "run_commands", "create_branch", "open_pull_request"),
        ("tests pass", "change is traceable to the objective"),
    ),
    Role.CURATOR: RoleContract(
        Role.CURATOR,
        "Protect quality, trust, compliance, and factual integrity.",
        ("verification report", "defect findings", "release recommendation"),
        ("read_repository", "run_tests", "inspect_diff", "security_scan"),
        ("claims have evidence", "critical regressions are absent"),
    ),
    Role.OPTIMIZER: RoleContract(
        Role.OPTIMIZER,
        "Measure outcomes, run controlled experiments, and improve the system.",
        ("metrics", "experiment result", "improvement proposal"),
        ("query_ledger", "run_evaluations", "propose_skill_change"),
        ("improvement beats baseline", "regressions stay within budget"),
    ),
    Role.STEWARD: RoleContract(
        Role.STEWARD,
        "Keep code, infrastructure, dependencies, and operational knowledge healthy.",
        ("health report", "maintenance change", "operational runbook"),
        ("inspect_runtime", "manage_dependencies", "write_workspace", "run_tests"),
        ("system remains recoverable", "maintenance reduces measured risk"),
    ),
    Role.INTEGRATOR: RoleContract(
        Role.INTEGRATOR,
        "Connect systems, data, tools, and workflows through stable contracts.",
        ("integration contract", "compatibility result", "data lineage"),
        ("inspect_interfaces", "write_adapters", "run_contract_tests"),
        ("contracts are versioned", "provenance is preserved"),
    ),
}

# Dependency order for a complete product-and-engineering loop. Each role is an
# independent agent; ordering only expresses evidence dependencies.
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
