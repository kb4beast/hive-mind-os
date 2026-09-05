"""Direct tests for the standardized one-class-per-agent architecture."""

from __future__ import annotations

import ast
import asyncio
import re
import unittest
from pathlib import Path

from hive_mind_os.agents import AGENT_TYPES, Agent, canonical_roles, create_agents
from hive_mind_os.models import Objective, Role, WorkItem, WorkStatus
from hive_mind_os.runtime import DeterministicBackend, HiveKernel


class DirectAgentArchitectureTests(unittest.TestCase):
    def test_each_constitutional_role_has_its_own_direct_class(self) -> None:
        self.assertEqual(
            canonical_roles(),
            (
                Role.ORCHESTRATOR,
                Role.EXPLORER,
                Role.ARCHITECT,
                Role.BUILDER,
                Role.CURATOR,
                Role.INTEGRATOR,
                Role.STEWARD,
                Role.OPTIMIZER,
            ),
        )
        self.assertEqual(len({agent_type.__module__ for agent_type in AGENT_TYPES}), 8)
        self.assertTrue(
            all(issubclass(agent_type, Agent) for agent_type in AGENT_TYPES)
        )

    def test_direct_agent_modules_have_no_dag_dependency_or_reference(self) -> None:
        source_root = Path(__file__).resolve().parents[1] / "src" / "hive_mind_os"
        for agent_type in AGENT_TYPES:
            module_path = source_root / Path(*agent_type.__module__.split(".")[1:])
            source = module_path.with_suffix(".py").read_text(encoding="utf-8")
            tree = ast.parse(source)
            imported_modules = {
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            }
            imported_modules.update(
                alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            )
            self.assertFalse(
                any("dag" in module for module in imported_modules),
                agent_type.__name__,
            )
            self.assertIsNone(
                re.search(r"\b(?:DAG|Dag[A-Z_])", source), agent_type.__name__
            )

    def test_hive_kernel_constructs_direct_agent_classes(self) -> None:
        kernel = HiveKernel()
        self.assertEqual(
            tuple(type(agent) for agent in kernel.agents.values()), AGENT_TYPES
        )

    def test_each_direct_agent_runs_its_own_contract(self) -> None:
        async def run() -> None:
            objective = Objective(goal="exercise every direct agent")
            context = ()
            for agent in create_agents(DeterministicBackend()):
                work_item = WorkItem(
                    objective_id=objective.id,
                    role=agent.role,
                    instruction=agent.contract.mission,
                )
                result = await agent.run(work_item, objective, context)
                self.assertEqual(result.role, agent.role)
                self.assertEqual(work_item.status, WorkStatus.SUCCEEDED)
                self.assertEqual(
                    {evidence.summary for evidence in result.evidence},
                    set(agent.contract.required_outputs),
                )
                context = (*context, result)

        asyncio.run(run())

    def test_legacy_tournament_role_behaviors_are_owned_by_direct_classes(self) -> None:
        """Retain role semantics without restoring the retired tournament runtime."""

        expected_obligations = {
            Role.ORCHESTRATOR: {"objective decomposition", "budget allocation", "stop conditions"},
            Role.EXPLORER: {"repository inspection", "evidence map", "non-mutating discovery"},
            Role.ARCHITECT: {"interfaces", "migration", "rollback"},
            Role.BUILDER: {"bounded implementation", "executable tests", "typed effect intents"},
            Role.CURATOR: {"exact candidate", "independent verification", "non-mutating review"},
            Role.INTEGRATOR: {"versioned contracts", "compatibility", "repair routing"},
            Role.STEWARD: {"health", "recovery", "operational readiness"},
            Role.OPTIMIZER: {"measure outcomes", "held-out evaluation", "challenger proposal"},
        }
        implementations = {agent_type.role: agent_type for agent_type in AGENT_TYPES}

        self.assertEqual(set(implementations), set(expected_obligations))
        for role, obligations in expected_obligations.items():
            self.assertTrue(
                obligations <= set(implementations[role].contract.readiness_obligations),
                role.value,
            )
