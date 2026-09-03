from __future__ import annotations

import unittest
from dataclasses import replace

from hive_mind_os.brain_kernel.candidate_state import CandidateStateJournal
from hive_mind_os.dag_executor import (
    DagExecutor,
    ExecutionBlockerCode,
    ExecutionJournal,
    NodeState,
    RunState,
)
from hive_mind_os.host_adapter import HostObservation
from hive_mind_os.host_runtime import HostOperationJournal
from hive_mind_os.integration_transaction import (
    IntegrationCoordinator,
    IntegrationError,
    IntegrationJournal,
)
from hive_mind_os.portable_plan import PortablePlanBundle
from hive_mind_os.runtime_contracts import ContractViolation, canonical_digest
from tests.test_dag_executor import NOW, FakeHost, request_for, runtime
from tests.test_dag_standard_product import STANDARD, compiler_plan
from tests.test_generic_dag_v4_activation import authorized_one_run_fixture
from tests.test_integration_transaction import (
    BASE,
    PLAN_BYTES,
    PROPOSED,
    UNKNOWN,
    WAVE,
    FakeTarget,
    candidate,
)
from tests.test_integration_transaction import (
    NOW as INTEGRATION_NOW,
)


class LostHost(FakeHost):
    def execute(self, *, node_id, input_bytes, lease):
        if node_id == "explorer":
            raise OSError("injected host loss")
        return super().execute(node_id=node_id, input_bytes=input_bytes, lease=lease)


class DriftHost(FakeHost):
    def observe(self, *, subject_id: str) -> HostObservation:
        observed = super().observe(subject_id=subject_id)
        return replace(observed, subject_id=canonical_digest({"substitute": subject_id}))


class GenericDagFailureMatrixTests(unittest.TestCase):
    def execute(self, host: FakeHost, *, nonce: str):
        plan = compiler_plan()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        request = request_for(plan, nonce=nonce)
        return executor, request, executor.execute(request)

    def test_concurrent_round_starts_and_duplicate_resume_do_not_repeat_effects(self) -> None:
        host = FakeHost(prove_parallel=True)
        executor, request, first = self.execute(host, nonce="failure-concurrency")
        self.assertEqual(RunState.COMPLETED, first.state)
        calls = list(host.calls)
        self.assertEqual(first, executor.execute(request))
        self.assertEqual(calls, host.calls)

    def test_target_snapshot_drift_fails_before_prepare_or_node_execution(self) -> None:
        host = DriftHost()
        _, _, blocked = self.execute(host, nonce="failure-drift")
        self.assertEqual(RunState.BLOCKED, blocked.state)
        self.assertEqual(ExecutionBlockerCode.HOST_RECOVERY_REQUIRED, blocked.blocker_code)
        self.assertEqual([], host.calls)

    def test_hidden_dependency_and_candidate_mutation_fail_compiler_binding(self) -> None:
        plan = compiler_plan()
        document = plan.to_document()
        document["nodes"][0]["dependencies"] = ["hidden-node"]
        with self.assertRaisesRegex(ContractViolation, "unknown dependency"):
            PortablePlanBundle.from_document(document)
        changed = replace(
            plan,
            nodes=(replace(plan.nodes[0], objective="mutated candidate"), *plan.nodes[1:]),
        )
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(runtime(host, host_journal), execution_journal, clock=lambda: NOW)
        request = replace(request_for(changed), expected_plan_digest=plan.digest())
        with self.assertRaisesRegex(ContractViolation, "caller expectation"):
            executor.execute(request)
        self.assertEqual([], host.calls)

    def test_host_loss_preserves_sibling_checkpoint_and_requires_reconciliation(self) -> None:
        host = LostHost()
        _, _, blocked = self.execute(host, nonce="failure-host-loss")
        self.assertEqual(RunState.BLOCKED, blocked.state)
        self.assertEqual(
            NodeState.RECONCILIATION_REQUIRED, blocked.node("explorer").state
        )
        self.assertTrue(blocked.node("orchestrator").complete)
        self.assertEqual(1, host.calls.count("orchestrator"))

    def test_integration_target_conflict_requires_replan_without_cas(self) -> None:
        target = FakeTarget()
        target.identity = UNKNOWN
        journal = IntegrationJournal()
        self.addCleanup(journal.close)
        coordinator = IntegrationCoordinator(
            journal, target, clock=lambda: INTEGRATION_NOW
        )
        candidate_journal = CandidateStateJournal()
        self.addCleanup(candidate_journal.close)
        candidates = (
            candidate(candidate_journal, "node-a", "4"),
            candidate(candidate_journal, "node-b", "6"),
        )
        with self.assertRaisesRegex(IntegrationError, "drifted"):
            coordinator.prepare(
                round_id="round-failure-matrix",
                target_ref="main",
                expected_target=BASE,
                proposed_target=PROPOSED,
                candidates=candidates,
                idempotency_key="prepare-failure-matrix",
                authorization=authorized_one_run_fixture(
                    PLAN_BYTES, nonce_seed="failure-matrix-integration"
                ),
                plan_bytes=PLAN_BYTES,
                standard_bytes=STANDARD,
                wave_manifest_bytes=WAVE.canonical_bytes(),
                candidate_journal=candidate_journal,
            )
        self.assertEqual(0, target.calls)
        self.assertEqual(1, target.observe_calls)


if __name__ == "__main__":
    unittest.main()
