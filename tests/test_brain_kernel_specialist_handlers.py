from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.dag_runtime import (
    ExecutableDagRuntime,
    NodeStatus,
    SpecialistContext,
    SpecialistResult,
)
from hive_mind_os.cortex.repository.specialist_handlers import (
    RepositorySpecialistHandlers,
    repository_candidate_digest,
    repository_specialist_plan,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RepositoryCandidateBindingTests(unittest.TestCase):
    def test_candidate_digest_binds_committed_repository_and_plan(self) -> None:
        first = repository_specialist_plan(plan_id="candidate-binding-one")
        second = repository_specialist_plan(plan_id="candidate-binding-two")
        first_digest = repository_candidate_digest(REPOSITORY_ROOT, first.digest)
        self.assertRegex(first_digest, r"\Asha256:[0-9a-f]{64}\Z")
        self.assertNotEqual(
            first_digest,
            repository_candidate_digest(REPOSITORY_ROOT, second.digest),
        )
        with self.assertRaisesRegex(ValueError, "plan digest"):
            repository_candidate_digest(REPOSITORY_ROOT, "not-a-digest")

    def test_every_registered_handler_rejects_a_mismatched_candidate(self) -> None:
        plan = repository_specialist_plan(plan_id="candidate-mismatch")
        handlers = RepositorySpecialistHandlers(REPOSITORY_ROOT)
        wrong_candidate = canonical_digest({"candidate": "not-this-repository"})
        with tempfile.TemporaryDirectory(prefix="hvb-") as temporary:
            workspaces = Path(temporary) / "workspaces"
            workspaces.mkdir()
            for node in plan.nodes:
                workspace = workspaces / node.node_id
                workspace.mkdir()
                context = SpecialistContext(
                    plan.digest,
                    wrong_candidate,
                    node,
                    workspace,
                    workspaces,
                    MappingProxyType({}),
                )
                with (
                    self.subTest(role=node.role),
                    self.assertRaisesRegex(RuntimeError, "candidate does not match"),
                ):
                    handlers.handler_for(node.role)(context)


class RepositorySpecialistEvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_curator_steward_and_optimizer_report_bounded_truth(self) -> None:
        plan = repository_specialist_plan(plan_id="bounded-truth")
        candidate = repository_candidate_digest(REPOSITORY_ROOT, plan.digest)
        handlers = RepositorySpecialistHandlers(REPOSITORY_ROOT)
        with tempfile.TemporaryDirectory(prefix="hvt-") as temporary:
            runtime = ExecutableDagRuntime(temporary, candidate_digest=candidate)
            result = await runtime.run(plan, handlers)
            documents = {
                receipt.role: json.loads(
                    runtime.artifact_store.get(receipt.artifact_digest).decode("utf-8")
                )
                for receipt in result.receipts
                if receipt.artifact_digest is not None
            }

        self.assertTrue(
            all(receipt.status is NodeStatus.SUCCEEDED for receipt in result.receipts)
        )
        curator = documents["curator"]
        self.assertEqual("adopt", curator["verdict"])
        self.assertTrue(curator["builder_validation"]["passed"])
        self.assertEqual(
            documents["builder"]["workspace_product_digest"],
            curator["builder_validation"]["product_digest"],
        )
        self.assertTrue(curator["smoke_test"]["passed"])
        self.assertGreater(curator["smoke_test"]["tests_run"], 0)
        self.assertEqual(
            "tests.test_brain_kernel_artifacts",
            curator["smoke_test"]["module"],
        )
        self.assertNotIn("specialist_handlers", " ".join(curator["smoke_test"]["argv"]))

        integrator = documents["integrator"]
        self.assertEqual("compatible", integrator["status"])
        self.assertTrue(integrator["curator_evidence_complete"])

        steward = documents["steward"]
        self.assertEqual("repair_required", steward["readiness"])
        self.assertEqual(
            ["receipts", "snapshots", "workspaces"],
            steward["observed_surfaces"],
        )
        self.assertEqual(
            ["event_chains", "leases", "providers", "queues"],
            steward["unobserved_surfaces"],
        )
        for surface in steward["observed_surfaces"]:
            self.assertEqual("healthy", steward["surface_statuses"][surface])
        for surface in steward["unobserved_surfaces"]:
            self.assertEqual("degraded", steward["surface_statuses"][surface])

        optimizer = documents["optimizer"]
        self.assertFalse(optimizer["evidence_complete"])
        self.assertEqual("defer", optimizer["recommendation"])
        self.assertIn(
            "operational-surfaces-are-unobserved-or-unhealthy",
            optimizer["completeness_reasons"],
        )

    async def test_corrupt_builder_product_fails_curator_and_blocks_descendants(
        self,
    ) -> None:
        plan = repository_specialist_plan(plan_id="corrupt-builder-handoff")
        candidate = repository_candidate_digest(REPOSITORY_ROOT, plan.digest)
        native = RepositorySpecialistHandlers(REPOSITORY_ROOT)
        handlers = {role: native.handler_for(role) for role in native.native_roles}
        builder = handlers["builder"]

        def corrupt_after_build(context: SpecialistContext) -> SpecialistResult:
            result = builder(context)
            if not isinstance(result, SpecialistResult):  # pragma: no cover
                raise TypeError("native Builder unexpectedly returned an awaitable")
            context.confined_path("candidate/builder-output.json").write_text(
                "{}\n", encoding="utf-8"
            )
            return result

        handlers["builder"] = corrupt_after_build
        with tempfile.TemporaryDirectory(prefix="hvc-") as temporary:
            result = await ExecutableDagRuntime(
                temporary, candidate_digest=candidate
            ).run(plan, handlers)

        builder_receipt = result.receipt_for("04-builder")
        curator_receipt = result.receipt_for("05-curator")
        self.assertIs(NodeStatus.SUCCEEDED, builder_receipt.status)
        self.assertIs(NodeStatus.FAILED, curator_receipt.status)
        self.assertEqual("RuntimeError", curator_receipt.error_type)
        self.assertRegex(curator_receipt.error_message or "", r"diagnostic=sha256:")
        for node_id in ("06-integrator", "07-steward", "08-optimizer"):
            with self.subTest(node_id=node_id):
                self.assertIs(NodeStatus.BLOCKED, result.receipt_for(node_id).status)


if __name__ == "__main__":
    unittest.main()
