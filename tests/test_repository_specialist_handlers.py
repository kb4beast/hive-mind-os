from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

from hive_mind_os.brain_kernel.architect import Architect
from hive_mind_os.brain_kernel.builder import BuilderCoordinator
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.curator_runtime import CuratorRuntime
from hive_mind_os.brain_kernel.dag_runtime import (
    SPECIALIST_ROLES,
    ExecutableDagRuntime,
    NodeStatus,
)
from hive_mind_os.brain_kernel.explorer import RepositoryExplorer
from hive_mind_os.brain_kernel.integrator import Integrator
from hive_mind_os.brain_kernel.optimizer import Optimizer
from hive_mind_os.brain_kernel.planner import OrchestratorPlanner
from hive_mind_os.brain_kernel.steward import Steward
from hive_mind_os.cortex.repository.specialist_handlers import (
    RepositorySpecialistHandlers,
    repository_specialist_plan,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = canonical_digest({"candidate": "repository-specialist-handler-tests"})


def _spy_method(stack: ExitStack, owner: type, name: str) -> MagicMock:
    original = getattr(owner, name)
    spy = stack.enter_context(patch.object(owner, name, autospec=True))
    spy.side_effect = original
    return spy


class RepositorySpecialistPlanTests(unittest.TestCase):
    def test_plan_contains_every_role_once_with_typed_branching(self) -> None:
        plan = repository_specialist_plan()
        self.assertEqual(set(SPECIALIST_ROLES), {node.role for node in plan.nodes})
        self.assertEqual(8, len({node.executor_id for node in plan.nodes}))
        self.assertNotEqual(
            next(node.executor_id for node in plan.nodes if node.role == "builder"),
            next(node.executor_id for node in plan.nodes if node.role == "curator"),
        )
        integrator = next(node for node in plan.nodes if node.role == "integrator")
        steward = next(node for node in plan.nodes if node.role == "steward")
        self.assertEqual(integrator.dependencies, steward.dependencies)
        self.assertNotIn(integrator.node_id, steward.dependencies)
        for node in plan.nodes:
            self.assertEqual(
                set(node.dependencies),
                {item.producer_node_id for item in node.required_artifacts},
            )


class RepositorySpecialistExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_handlers_invoke_their_concrete_existing_role(self) -> None:
        handlers = RepositorySpecialistHandlers(REPOSITORY_ROOT)
        with ExitStack() as stack:
            spies = {
                "orchestrator": _spy_method(stack, OrchestratorPlanner, "plan"),
                "explorer": _spy_method(stack, RepositoryExplorer, "discover_tests"),
                "architect": _spy_method(stack, Architect, "produce"),
                "builder": _spy_method(stack, BuilderCoordinator, "repair"),
                "curator": _spy_method(stack, CuratorRuntime, "verify"),
                "integrator": _spy_method(stack, Integrator, "validate"),
                "steward": _spy_method(stack, Steward, "assess"),
                "optimizer": _spy_method(
                    stack, Optimizer, "recommend_independent_review"
                ),
            }
            with tempfile.TemporaryDirectory(prefix="hsd-v2-") as temporary:
                runtime = ExecutableDagRuntime(temporary, candidate_digest=CANDIDATE)
                result = await runtime.run(repository_specialist_plan(), handlers)
                documents = {
                    receipt.role: json.loads(
                        runtime.artifact_store.get(receipt.artifact_digest).decode(
                            "utf-8"
                        )
                    )
                    for receipt in result.receipts
                    if receipt.artifact_digest is not None
                }
                builder_product = (
                    Path(temporary)
                    / "workspaces"
                    / "04-builder"
                    / "candidate"
                    / "builder-output.json"
                )
                curator_clone = (
                    Path(temporary) / "workspaces" / "05-curator" / "candidate"
                )
                self.assertTrue(builder_product.is_file())
                self.assertTrue((curator_clone / ".git").exists())

        self.assertTrue(
            all(value.status is NodeStatus.SUCCEEDED for value in result.receipts)
        )
        self.assertEqual(set(SPECIALIST_ROLES), set(documents))
        for role, spy in spies.items():
            with self.subTest(role=role):
                self.assertEqual(1, spy.call_count)
                receipt = next(value for value in result.receipts if value.role == role)
                self.assertTrue(receipt.native_evidence)
                self.assertNotEqual("generic-fallback", receipt.invoked_symbol)

    async def test_generic_fallback_is_retained_but_cannot_earn_native_evidence(
        self,
    ) -> None:
        handlers = RepositorySpecialistHandlers(REPOSITORY_ROOT)
        handlers._handlers.pop("builder")
        with tempfile.TemporaryDirectory(prefix="hsd-v2-fallback-") as temporary:
            result = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE
            ).run(repository_specialist_plan(), handlers)
        builder = next(value for value in result.receipts if value.role == "builder")
        curator = next(value for value in result.receipts if value.role == "curator")
        architect = next(
            value for value in result.receipts if value.role == "architect"
        )
        self.assertIs(NodeStatus.FAILED, builder.status)
        self.assertEqual("NativeEvidenceRequired", builder.error_type)
        self.assertFalse(builder.native_evidence)
        self.assertIs(NodeStatus.BLOCKED, curator.status)
        self.assertIs(NodeStatus.SUCCEEDED, architect.status)


if __name__ == "__main__":
    unittest.main()
