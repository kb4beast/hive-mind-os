from __future__ import annotations

import json
import unittest
from importlib.resources import files

import hive_mind_os
from hive_mind_os.contracts import validate_contract
from hive_mind_os.models import Role
from hive_mind_os.reference.package_system import (
    AgentManifest,
    ComponentKind,
    WorkflowManifest,
)
from hive_mind_os.reference.package_system.builtins import hive_core_catalog, hive_core_root
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS

EXPECTED_ROLE_DATA = {
    Role.ORCHESTRATOR: (
        "Translate outcomes into bounded work, coordinate specialists, and manage tradeoffs.",
        ("objective decomposition", "execution plan", "risk register"),
        ("read_repository", "query_agents", "create_work_items"),
        ("acceptance criteria are testable", "dependencies are explicit"),
    ),
    Role.EXPLORER: (
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
    Role.ARCHITECT: (
        "Design scalable, secure, evolvable solutions and explicit decision records.",
        ("architecture", "interfaces", "threat model", "migration plan"),
        ("read_repository", "model_system", "write_design"),
        ("constraints are satisfied", "failure modes are addressed"),
    ),
    Role.BUILDER: (
        "Implement the smallest complete change and ship it with executable verification.",
        ("implementation", "tests", "change summary"),
        (
            "read_repository",
            "write_workspace",
            "run_commands",
            "create_branch",
            "open_pull_request",
        ),
        ("tests pass", "change is traceable to the objective"),
    ),
    Role.CURATOR: (
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
    Role.INTEGRATOR: (
        "Connect systems, data, tools, and workflows through stable contracts.",
        ("integration contract", "compatibility result", "data lineage"),
        ("inspect_interfaces", "write_adapters", "run_contract_tests"),
        ("contracts are versioned", "provenance is preserved"),
    ),
    Role.STEWARD: (
        "Keep code, infrastructure, dependencies, and operational knowledge healthy.",
        ("health report", "maintenance change", "operational runbook"),
        ("inspect_runtime", "manage_dependencies", "write_workspace", "run_tests"),
        ("system remains recoverable", "maintenance reduces measured risk"),
    ),
    Role.OPTIMIZER: (
        "Measure outcomes, run controlled experiments, and improve the system.",
        ("metrics", "experiment result", "improvement proposal"),
        ("query_ledger", "run_evaluations", "propose_skill_change"),
        ("improvement beats baseline", "regressions stay within budget"),
    ),
}
EXPECTED_LIFECYCLE = (
    Role.ORCHESTRATOR,
    Role.EXPLORER,
    Role.ARCHITECT,
    Role.BUILDER,
    Role.CURATOR,
    Role.INTEGRATOR,
    Role.STEWARD,
    Role.OPTIMIZER,
)


class PackageRegistryCompatibilityTests(unittest.TestCase):
    def test_builtin_agent_manifests_exactly_preserve_legacy_contracts(self) -> None:
        catalog = hive_core_catalog()
        observed: dict[Role, tuple[object, ...]] = {}
        for role in Role:
            component = catalog.component(f"agent.{role.value}")
            self.assertIsInstance(component, AgentManifest)
            assert isinstance(component, AgentManifest)
            observed[role] = (
                component.mission,
                component.required_outputs,
                component.requested_capabilities,
                component.quality_gates,
            )
        self.assertEqual(observed, EXPECTED_ROLE_DATA)

    def test_builtin_workflow_exactly_preserves_legacy_lifecycle(self) -> None:
        component = hive_core_catalog().component("workflow.default-lifecycle")
        self.assertIsInstance(component, WorkflowManifest)
        assert isinstance(component, WorkflowManifest)
        states = tuple(
            Role(transition.to_state)
            for transition in component.transitions
            if transition.to_state not in component.terminal_states
        )
        self.assertEqual(states, EXPECTED_LIFECYCLE)

    def test_roles_facade_remains_exactly_compatible(self) -> None:
        observed = {
            role: (
                contract.mission,
                contract.required_outputs,
                contract.default_capabilities,
                contract.quality_gates,
            )
            for role, contract in ROLE_CONTRACTS.items()
        }
        self.assertEqual(observed, EXPECTED_ROLE_DATA)
        self.assertEqual(DEFAULT_LIFECYCLE, EXPECTED_LIFECYCLE)

    def test_builtin_package_resources_and_formal_schemas_are_available(self) -> None:
        package = hive_core_catalog().package("hive-core")
        resource_root = files("hive_mind_os").joinpath(
            "builtin_packages",
            "hive-core",
        )
        self.assertTrue(resource_root.joinpath("package.json").is_file())
        self.assertEqual(package.root, hive_core_root().resolve())
        self.assertTrue(
            validate_contract(
                "package-manifest",
                json.loads(resource_root.joinpath("package.json").read_text()),
            ).valid
        )

        schema_by_kind = {
            ComponentKind.AGENT: "agent-component",
            ComponentKind.SKILL: "skill-component",
            ComponentKind.TOOL: "tool-component",
            ComponentKind.WORKFLOW: "workflow-component",
        }
        refs = {
            reference.component_id: reference
            for reference in package.manifest.components
        }
        for component in package.components:
            reference = refs[component.component_id]
            document = json.loads(
                resource_root.joinpath(reference.manifest_path).read_text()
            )
            validation = validate_contract(schema_by_kind[reference.kind], document)
            self.assertTrue(
                validation.valid,
                (reference.component_id, validation.issues),
            )

    def test_package_types_are_additive_root_exports(self) -> None:
        for name in (
            "AgentManifest",
            "CatalogSnapshot",
            "ComponentKind",
            "ComponentRef",
            "EvidenceLevel",
            "FileRecord",
            "HostCapability",
            "HostCapabilityProfile",
            "LicenseStatus",
            "LoadedPackage",
            "OODAContractValidation",
            "OODAPhase",
            "OODAState",
            "OODAStatus",
            "OODATerminalRecord",
            "OODATransition",
            "PackageCatalog",
            "PackageManifest",
            "PackagePin",
            "PackageValidationError",
            "SkillManifest",
            "ToolManifest",
            "TrustState",
            "WorkflowManifest",
            "WorkflowTransition",
            "validate_ooda_contract",
        ):
            self.assertIn(name, hive_mind_os.__all__)
            self.assertTrue(hasattr(hive_mind_os, name))


if __name__ == "__main__":
    unittest.main()
