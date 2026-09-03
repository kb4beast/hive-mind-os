from __future__ import annotations

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from hive_mind_os.activation_bundle import AuthorizedOneRun
from hive_mind_os.dag_executor import (
    DagExecutionError,
    DagExecutor,
    ExecutionBlockerCode,
    ExecutionJournal,
    ExecutionRequest,
    GraphPatch,
    NodeState,
    RunState,
    validate_graph_patch,
)
from hive_mind_os.host_adapter import (
    HOST_DEADLINE_CAPABILITY,
    HostExecutionReceipt,
    HostIdentity,
    HostLease,
    HostObservation,
    HostReceiptState,
)
from hive_mind_os.host_runtime import (
    HostOperationJournal,
    HostRecoveryRequired,
    HostRuntime,
    HostRuntimeError,
)
from hive_mind_os.portable_plan import NonRepositorySubject, SubjectBinding
from hive_mind_os.runtime_contracts import (
    ContractViolation,
    canonical_digest,
    raw_sha256,
)
from tests.test_dag_standard_product import ROLES, STAGES, STANDARD, compiler_plan
from tests.test_generic_dag_v4_activation import authorized_one_run_fixture

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
PLAN_ADAPTER_INVENTORY = canonical_digest(
    [item.to_document() for item in compiler_plan().adapters]
)


class FakeHost:
    def __init__(
        self,
        *,
        fail_node: str | None = None,
        ambiguous_node: str | None = None,
        prove_parallel: bool = False,
        cancel_state: HostReceiptState = HostReceiptState.CANCELLED,
    ):
        self.fail_node = fail_node
        self.ambiguous_node = ambiguous_node
        self.cancel_state = cancel_state
        self.calls: list[str] = []
        self.prepare_calls = 0
        self.cancel_calls = 0
        self._lock = threading.Lock()
        self.barrier = threading.Barrier(2) if prove_parallel else None
        self.subject_id = ""
        self.prepared_authorization: AuthorizedOneRun | None = None
        self.observed_at = "2026-09-02T12:00:00Z"
        self.identity = HostIdentity(
            "fixture-host",
            "windows",
            "x86_64",
            "1",
            "sha256:" + "1" * 64,
            PLAN_ADAPTER_INVENTORY,
        )

    def observe(self, *, subject_id: str) -> HostObservation:
        self.subject_id = subject_id
        return HostObservation(
            self.identity,
            subject_id,
            self.observed_at,
            ("read", HOST_DEADLINE_CAPABILITY),
            "sha256:" + "3" * 64,
            True,
        )

    def prepare(
        self,
        *,
        plan_digest: str,
        generation_id: str,
        authority_digest: str,
        adapter_inventory_digest: str,
        external_effects_required: bool,
        compilation_receipt: Mapping[str, Any],
        subject_id: str,
        node_ids: tuple[str, ...],
        nonce_digest: str,
        lease_deadline: str,
        authorization: AuthorizedOneRun,
        required_capabilities: tuple[str, ...],
    ) -> HostLease:
        del plan_digest
        self.prepare_calls += 1
        self.prepared_authorization = authorization
        return HostLease(
            "lease-1",
            self.identity.host_id,
            subject_id,
            generation_id,
            authority_digest,
            adapter_inventory_digest,
            external_effects_required,
            canonical_digest(dict(compilation_receipt)),
            authorization.activation_digest,
            authorization.proof_digest,
            authorization.candidate_commit,
            authorization.candidate_tree,
            authorization.candidate_content_sha256,
            authorization.candidate_parent_commit,
            authorization.candidate_parent_tree,
            authorization.manifest_sha256,
            authorization.repository_id,
            authorization.request_sha256,
            authorization.target_branch,
            authorization.execution_client_sha256,
            authorization.issued_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            authorization.protected_merge_authorized,
            self.identity.digest,
            "sha256:" + "3" * 64,
            required_capabilities,
            "2026-09-02T12:00:00Z",
            lease_deadline,
            node_ids,
            nonce_digest,
        )

    def execute(
        self, *, node_id: str, input_bytes: bytes, lease: HostLease
    ) -> HostExecutionReceipt:
        envelope = json.loads(input_bytes)
        self.assert_envelope(envelope, node_id)
        with self._lock:
            self.calls.append(node_id)
        if node_id == self.ambiguous_node:
            raise RuntimeError("host result was lost")
        if self.barrier is not None:
            self.barrier.wait(timeout=3)
        state = (
            HostReceiptState.FAILED
            if node_id == self.fail_node
            else HostReceiptState.SUCCEEDED
        )
        return HostExecutionReceipt(
            f"receipt-{node_id}",
            lease.lease_id,
            node_id,
            state,
            raw_sha256(input_bytes),
            None
            if state is HostReceiptState.FAILED
            else canonical_digest({"node": node_id}),
            canonical_digest({"evidence": node_id}),
            "2026-09-02T12:00:00Z",
        )

    @staticmethod
    def assert_envelope(envelope: dict, node_id: str) -> None:
        if set(envelope) != {"frozen_manifest", "node_delta"}:
            raise AssertionError(
                "worker did not receive the frozen manifest plus one delta"
            )
        if envelope["node_delta"]["node"]["node_id"] != node_id:
            raise AssertionError("worker received another node's delta")

    def cancel(self, *, lease: HostLease, reason: str) -> HostExecutionReceipt:
        self.cancel_calls += 1
        return HostExecutionReceipt(
            "receipt-cancel",
            lease.lease_id,
            lease.allowed_node_ids[0],
            self.cancel_state,
            canonical_digest({"reason": reason}),
            (
                canonical_digest({"cancelled-output": False})
                if self.cancel_state is HostReceiptState.SUCCEEDED
                else None
            ),
            canonical_digest({"cancelled": True}),
            "2026-09-02T12:00:00Z",
        )


def request_for(
    plan, *, nonce: str = "nonce-1", bind_subject: bool = True
) -> ExecutionRequest:
    repository = plan.subject.repository
    binding = (
        {}
        if repository is None or not bind_subject
        else {
            "repository_id": repository.repository_id,
            "candidate_parent_commit": repository.commit,
            "candidate_parent_tree": repository.tree,
            "target_branch": repository.target_branch,
        }
    )
    authorization = authorized_one_run_fixture(
        plan.canonical_bytes(), nonce_seed=nonce, **binding
    )
    return ExecutionRequest(
        plan.canonical_bytes(),
        plan.digest(),
        STANDARD,
        canonical_digest({"generation": 1}),
        authorization,
        ("subject-adapter",),
    )


def single_node_plan():
    plan = compiler_plan()
    node = replace(
        plan.nodes[0],
        dependencies=(),
        roles=ROLES,
        lifecycle_stages=STAGES,
    )
    return replace(plan, nodes=(node,))


def runtime(
    host: FakeHost,
    journal: HostOperationJournal,
    *,
    adoption_verifier=None,
) -> HostRuntime:
    return HostRuntime(
        host,
        journal,
        one_run_deadline="2027-01-01T00:00:00Z",
        clock=lambda: NOW,
        adoption_verifier=adoption_verifier,
    )


class DagExecutorTests(unittest.TestCase):
    def test_all_permitted_workers_start_before_poll_and_run_is_repeat_idempotent(
        self,
    ) -> None:
        plan = compiler_plan()
        host = FakeHost(prove_parallel=True)
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )

        first = executor.execute(request_for(plan))
        self.assertEqual(RunState.COMPLETED, first.state)
        self.assertTrue(all(node.complete for node in first.nodes))
        self.assertIsNotNone(host.prepared_authorization)
        assert host.prepared_authorization is not None
        self.assertEqual(
            "6" * 40, host.prepared_authorization.candidate_commit
        )
        proof = host.prepared_authorization.proof_document()
        self.assertIn("signed_proof", proof)
        principals = proof["principals"]
        self.assertIsInstance(principals, dict)
        assert isinstance(principals, dict)
        host_attester = principals["host_attester"]
        self.assertIsInstance(host_attester, dict)
        assert isinstance(host_attester, dict)
        self.assertEqual("principal:host", host_attester["principal_id"])
        self.assertEqual(8, len(host.calls))
        second = executor.execute(request_for(plan))
        self.assertEqual(first, second)
        self.assertEqual(8, len(host.calls), "completed resume repeated a host effect")

    def test_ambiguous_sibling_requires_authenticated_host_reconciliation(
        self,
    ) -> None:
        plan = compiler_plan()
        failed_node = "explorer"
        host = FakeHost(ambiguous_node=failed_node)
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        expected_adoption = canonical_digest({"adoption": failed_node})
        host_runtime = runtime(
            host,
            host_journal,
            adoption_verifier=lambda **values: (
                values["evidence_digest"] == expected_adoption
            ),
        )
        executor = DagExecutor(host_runtime, execution_journal, clock=lambda: NOW)
        request = request_for(plan)

        blocked = executor.execute(request)
        self.assertEqual(RunState.BLOCKED, blocked.state)
        self.assertEqual(
            NodeState.RECONCILIATION_REQUIRED, blocked.node(failed_node).state
        )
        self.assertTrue(blocked.node("orchestrator").complete)
        calls = list(host.calls)
        self.assertEqual(blocked, executor.execute(request))
        self.assertEqual(calls, host.calls)

        failed = blocked.node(failed_node)
        assert failed.input_digest is not None and blocked.lease_id is not None
        receipt = HostExecutionReceipt(
            "external-receipt",
            blocked.lease_id,
            failed_node,
            HostReceiptState.SUCCEEDED,
            failed.input_digest,
            canonical_digest({"adopted": failed_node}),
            canonical_digest({"host-witness": failed_node}),
            "2026-09-02T12:00:00Z",
        )
        with self.assertRaisesRegex(DagExecutionError, "not authenticated"):
            executor.reconcile(
                run_id=blocked.run_id,
                receipt=receipt,
                adoption_evidence_digest=canonical_digest(
                    {"forged-adoption": failed_node}
                ),
            )
        unchanged = execution_journal.snapshot(blocked.run_id)
        self.assertIsNotNone(unchanged)
        assert unchanged is not None
        self.assertEqual(
            NodeState.RECONCILIATION_REQUIRED,
            unchanged.node(failed_node).state,
        )
        executor.reconcile(
            run_id=blocked.run_id,
            receipt=receipt,
            adoption_evidence_digest=expected_adoption,
        )
        completed = executor.execute(request)
        self.assertEqual(RunState.COMPLETED, completed.state)
        self.assertEqual(NodeState.ADOPTED, completed.node(failed_node).state)
        self.assertEqual(1, host.calls.count(failed_node))

    def test_definitive_failed_receipt_cannot_be_rewritten_by_reconciliation(
        self,
    ) -> None:
        plan = compiler_plan()
        failed_node = "explorer"
        host = FakeHost(fail_node=failed_node)
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal, adoption_verifier=lambda **_: True),
            execution_journal,
            clock=lambda: NOW,
        )
        blocked = executor.execute(request_for(plan, nonce="definitive-failure"))
        failed = blocked.node(failed_node)
        self.assertEqual(NodeState.FAILED, failed.state)
        assert failed.input_digest is not None and blocked.lease_id is not None
        forged_success = HostExecutionReceipt(
            "forged-success",
            blocked.lease_id,
            failed_node,
            HostReceiptState.SUCCEEDED,
            failed.input_digest,
            canonical_digest({"forged": "output"}),
            canonical_digest({"forged": "evidence"}),
            "2026-09-02T12:00:00Z",
        )
        with self.assertRaisesRegex(DagExecutionError, "no ambiguous host intent"):
            executor.reconcile(
                run_id=blocked.run_id,
                receipt=forged_success,
                adoption_evidence_digest=canonical_digest({"forged": "adoption"}),
            )
        self.assertEqual(
            NodeState.FAILED,
            execution_journal.snapshot(blocked.run_id).node(failed_node).state,  # type: ignore[union-attr]
        )

    def test_historical_ambiguous_receipt_can_be_reconciled_after_lease_expiry(
        self,
    ) -> None:
        plan = compiler_plan()
        failed_node = "explorer"
        host = FakeHost(ambiguous_node=failed_node)
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        request = request_for(plan, nonce="post-expiry-reconciliation")
        evidence_digest = canonical_digest({"adoption": "post-expiry"})
        executor = DagExecutor(
            runtime(
                host,
                host_journal,
                adoption_verifier=lambda **values: (
                    values["evidence_digest"] == evidence_digest
                ),
            ),
            execution_journal,
            clock=lambda: NOW,
        )
        blocked = executor.execute(request)
        node = blocked.node(failed_node)
        self.assertIs(NodeState.RECONCILIATION_REQUIRED, node.state)
        assert node.input_digest is not None and blocked.lease_id is not None

        # Reconstruct the runtime after both the lease and its original
        # one-run deadline.  Recovery may observe and authenticate historical
        # proof, but it must not reacquire live effect authority.
        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovery_runtime = HostRuntime(
            host,
            host_journal,
            one_run_deadline="2026-09-02T12:15:00Z",
            clock=lambda: after_expiry,
            adoption_verifier=lambda **values: (
                values["evidence_digest"] == evidence_digest
            ),
        )
        historical_observer = recovery_runtime._historical_observer  # noqa: SLF001
        self.assertFalse(hasattr(historical_observer, "prepare"))
        self.assertFalse(hasattr(historical_observer, "execute"))
        self.assertFalse(hasattr(historical_observer, "cancel"))
        recovery_executor = DagExecutor(
            recovery_runtime,
            execution_journal,
            clock=lambda: after_expiry,
        )
        historical = HostExecutionReceipt(
            "historical-receipt",
            blocked.lease_id,
            failed_node,
            HostReceiptState.SUCCEEDED,
            node.input_digest,
            canonical_digest({"historical": "output"}),
            canonical_digest({"historical": "host-evidence"}),
            "2026-09-02T12:09:00Z",
        )
        reconciled = recovery_executor.reconcile(
            run_id=blocked.run_id,
            receipt=historical,
            adoption_evidence_digest=evidence_digest,
        )
        self.assertIs(NodeState.ADOPTED, reconciled.node(failed_node).state)
        self.assertEqual(1, host.calls.count(failed_node))

        lease = recovery_runtime.resume_for_reconciliation(
            create_idempotency_key=DagExecutor._idempotency(  # noqa: SLF001
                blocked.run_id, "create"
            ),
            poll_idempotency_key=canonical_digest({"post-expiry": "second-poll"}),
        )
        with self.assertRaisesRegex(HostRuntimeError, "expired"):
            recovery_runtime.message(
                lease=lease,
                node_id=failed_node,
                input_bytes=b"must not run after expiry",
                idempotency_key="post-expiry-new-message",
            )
        self.assertEqual(1, host.calls.count(failed_node))
        self.assertEqual(1, host.prepare_calls)
        self.assertEqual(0, host.cancel_calls)

    def test_expired_restart_closes_message_checkpoint_executor_crash_window(
        self,
    ) -> None:
        plan = single_node_plan()
        request = request_for(plan, nonce="checkpoint-crash-expiry")
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        append = executor._append_event  # noqa: SLF001

        def crash_before_node_success(run_id, kind, payload):
            if kind == "node.succeeded":
                raise RuntimeError("crash after durable host checkpoint")
            return append(run_id, kind, payload)

        executor._append_event = crash_before_node_success  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "durable host checkpoint"):
            executor.execute(request)
        self.assertEqual(1, len(host.calls))

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovered = DagExecutor(
            HostRuntime(
                host,
                host_journal,
                one_run_deadline="2026-09-02T12:10:00Z",
                clock=lambda: after_expiry,
            ),
            execution_journal,
            clock=lambda: after_expiry,
        ).execute(request)
        self.assertIs(recovered.state, RunState.COMPLETED)
        self.assertEqual(1, len(host.calls))
        self.assertEqual(1, host.prepare_calls)
        self.assertEqual(0, host.cancel_calls)

    def test_expired_restart_checkpoints_a_durable_message_without_reexecution(
        self,
    ) -> None:
        plan = single_node_plan()
        request = request_for(plan, nonce="message-before-checkpoint-expiry")
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        live_runtime = runtime(host, host_journal)
        executor = DagExecutor(live_runtime, execution_journal, clock=lambda: NOW)

        def crash_before_checkpoint(**_values):
            raise RuntimeError("crash before durable checkpoint")

        live_runtime.checkpoint = crash_before_checkpoint  # type: ignore[method-assign]
        with self.assertRaisesRegex(RuntimeError, "before durable checkpoint"):
            executor.execute(request)
        self.assertEqual(1, len(host.calls))
        self.assertFalse(
            any(record.action == "checkpoint" for record in host_journal.records())
        )

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovered = DagExecutor(
            HostRuntime(
                host,
                host_journal,
                one_run_deadline="2026-09-02T12:10:00Z",
                clock=lambda: after_expiry,
            ),
            execution_journal,
            clock=lambda: after_expiry,
        ).execute(request)
        self.assertIs(recovered.state, RunState.COMPLETED)
        self.assertEqual(1, len(host.calls))
        self.assertEqual(1, host.prepare_calls)
        self.assertEqual(0, host.cancel_calls)
        self.assertTrue(
            any(
                record.action == "checkpoint"
                and record.state.value == "SUCCEEDED"
                for record in host_journal.records()
            )
        )

    def test_expired_restart_recovers_create_before_executor_lease_event(self) -> None:
        plan = single_node_plan()
        request = request_for(plan, nonce="create-before-lease-event-expiry")
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        append = executor._append_event  # noqa: SLF001

        def crash_before_lease_event(run_id, kind, payload):
            if kind == "host.lease-ready":
                raise RuntimeError("crash before executor lease event")
            return append(run_id, kind, payload)

        executor._append_event = crash_before_lease_event  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "executor lease event"):
            executor.execute(request)
        self.assertEqual(1, host.prepare_calls)
        self.assertEqual([], host.calls)

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovered = DagExecutor(
            HostRuntime(
                host,
                host_journal,
                one_run_deadline="2026-09-02T12:10:00Z",
                clock=lambda: after_expiry,
            ),
            execution_journal,
            clock=lambda: after_expiry,
        ).execute(request)
        self.assertIs(recovered.state, RunState.BLOCKED)
        self.assertIsNotNone(recovered.lease_id)
        self.assertEqual(1, host.prepare_calls)
        self.assertEqual([], host.calls)
        self.assertEqual(0, host.cancel_calls)

    def test_expired_restart_recovers_proven_node_while_sibling_stays_blocked(
        self,
    ) -> None:
        plan = compiler_plan()
        request = request_for(plan, nonce="mixed-sibling-expiry")
        host = FakeHost(ambiguous_node="explorer")
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        append = executor._append_event  # noqa: SLF001

        def crash_after_blocking_sibling(run_id, kind, payload):
            if kind == "node.succeeded" and payload["node_id"] == "orchestrator":
                append(
                    run_id,
                    "run.blocked",
                    {
                        "code": "RECONCILIATION_REQUIRED",
                        "reason": "simulated restart blocked the mixed round",
                    },
                )
                raise RuntimeError("crash with proven sibling still running")
            return append(run_id, kind, payload)

        executor._append_event = crash_after_blocking_sibling  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "proven sibling"):
            executor.execute(request)
        before = execution_journal.snapshot(DagExecutor._run_id(request))  # noqa: SLF001
        assert before is not None
        self.assertIs(before.state, RunState.BLOCKED)
        self.assertIs(before.node("explorer").state, NodeState.RECONCILIATION_REQUIRED)
        self.assertIs(before.node("orchestrator").state, NodeState.RUNNING)
        effect_count = len(host.calls)

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovered = DagExecutor(
            HostRuntime(
                host,
                host_journal,
                one_run_deadline="2026-09-02T12:10:00Z",
                clock=lambda: after_expiry,
            ),
            execution_journal,
            clock=lambda: after_expiry,
        ).execute(request)
        self.assertIs(recovered.state, RunState.BLOCKED)
        self.assertIs(recovered.node("orchestrator").state, NodeState.SUCCEEDED)
        self.assertIs(
            recovered.node("explorer").state,
            NodeState.RECONCILIATION_REQUIRED,
        )
        self.assertEqual(effect_count, len(host.calls))
        self.assertEqual(1, host.prepare_calls)
        self.assertEqual(0, host.cancel_calls)

    def test_expired_restart_closes_missing_run_completed_and_is_idempotent(
        self,
    ) -> None:
        plan = compiler_plan()
        request = request_for(plan, nonce="run-completion-crash-expiry")
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        append = executor._append_event  # noqa: SLF001

        def crash_before_run_completion(run_id, kind, payload):
            if kind == "run.completed":
                raise RuntimeError("crash before executor completion")
            return append(run_id, kind, payload)

        executor._append_event = crash_before_run_completion  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "executor completion"):
            executor.execute(request)
        effect_count = len(host.calls)
        self.assertEqual(len(plan.nodes), effect_count)

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovery_runtime = HostRuntime(
            host,
            host_journal,
            one_run_deadline="2026-09-02T12:10:00Z",
            clock=lambda: after_expiry,
        )
        recovery = DagExecutor(
            recovery_runtime,
            execution_journal,
            clock=lambda: after_expiry,
        )
        completed = recovery.execute(request)
        self.assertIs(completed.state, RunState.COMPLETED)
        observation_count = host.prepare_calls
        again = recovery.execute(request)
        self.assertEqual(completed, again)
        self.assertEqual(effect_count, len(host.calls))
        self.assertEqual(observation_count, host.prepare_calls)
        self.assertEqual(0, host.cancel_calls)

    def test_committed_cancellation_precedes_completion_after_crash_and_expiry(
        self,
    ) -> None:
        plan = compiler_plan()
        request = request_for(plan, nonce="cancel-precedes-completion")
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        append = executor._append_event  # noqa: SLF001
        succeeded = 0

        def crash_after_last_node(run_id, kind, payload):
            nonlocal succeeded
            event = append(run_id, kind, payload)
            if kind == "node.succeeded":
                succeeded += 1
                if succeeded == len(plan.nodes):
                    raise RuntimeError("crash before terminal ordering")
            return event

        executor._append_event = crash_after_last_node  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "terminal ordering"):
            executor.execute(request)
        before_cancel = execution_journal.snapshot(
            DagExecutor._run_id(request)  # noqa: SLF001
        )
        self.assertIsNotNone(before_cancel)
        assert before_cancel is not None
        self.assertTrue(all(node.complete for node in before_cancel.nodes))
        executor._append_event = append  # type: ignore[method-assign]  # noqa: SLF001

        def crash_before_cancel_event(run_id, kind, payload):
            if kind == "run.cancelled":
                raise RuntimeError("crash after host cancellation")
            return append(run_id, kind, payload)

        executor._append_event = crash_before_cancel_event  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "host cancellation"):
            executor.cancel(request, reason="cancel won before completion")
        self.assertEqual(1, host.cancel_calls)
        effect_count = len(host.calls)

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovered = DagExecutor(
            HostRuntime(
                host,
                host_journal,
                one_run_deadline="2026-09-02T12:10:00Z",
                clock=lambda: after_expiry,
            ),
            execution_journal,
            clock=lambda: after_expiry,
        ).execute(request)
        self.assertIs(recovered.state, RunState.CANCELLED)
        cancellation = execution_journal.events(recovered.run_id)[-1]
        self.assertEqual("run.cancelled", cancellation.kind)
        self.assertEqual(
            "cancel won before completion", cancellation.payload["reason"]
        )
        self.assertEqual(effect_count, len(host.calls))
        self.assertEqual(1, host.cancel_calls)
        self.assertNotIn(
            "run.completed",
            {event.kind for event in execution_journal.events(recovered.run_id)},
        )

    def test_ambiguous_cancellation_claim_cannot_be_overwritten_by_completion(
        self,
    ) -> None:
        plan = compiler_plan()
        request = request_for(plan, nonce="ambiguous-cancel-precedes-completion")
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        append = executor._append_event  # noqa: SLF001
        succeeded = 0

        def crash_after_last_node(run_id, kind, payload):
            nonlocal succeeded
            event = append(run_id, kind, payload)
            if kind == "node.succeeded":
                succeeded += 1
                if succeeded == len(plan.nodes):
                    raise RuntimeError("crash before terminal ordering")
            return event

        executor._append_event = crash_after_last_node  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "terminal ordering"):
            executor.execute(request)
        executor._append_event = append  # type: ignore[method-assign]  # noqa: SLF001

        def ambiguous_cancel(*, lease: HostLease, reason: str):
            del lease, reason
            host.cancel_calls += 1
            raise RuntimeError("cancel result lost")

        host.cancel = ambiguous_cancel  # type: ignore[method-assign]
        with self.assertRaises(HostRecoveryRequired):
            executor.cancel(request, reason="ambiguous cancellation")
        effect_count = len(host.calls)

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovery = DagExecutor(
            HostRuntime(
                host,
                host_journal,
                one_run_deadline="2026-09-02T12:10:00Z",
                clock=lambda: after_expiry,
            ),
            execution_journal,
            clock=lambda: after_expiry,
        )
        blocked = recovery.execute(request)
        self.assertIs(blocked.state, RunState.BLOCKED)
        self.assertEqual(ExecutionBlockerCode.HOST_RECOVERY_REQUIRED, blocked.blocker_code)
        self.assertEqual(effect_count, len(host.calls))
        self.assertEqual(1, host.cancel_calls)
        kinds = {event.kind for event in execution_journal.events(blocked.run_id)}
        self.assertNotIn("run.completed", kinds)
        self.assertNotIn("run.cancelled", kinds)
        self.assertEqual(blocked, recovery.execute(request))
        self.assertEqual(1, host.cancel_calls)

    def test_expired_restart_closes_host_cancel_before_executor_cancel_event(
        self,
    ) -> None:
        plan = compiler_plan()
        request = request_for(plan, nonce="cancel-crash-expiry")
        host = FakeHost(ambiguous_node=plan.nodes[0].node_id)
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )
        blocked = executor.execute(request)
        self.assertIs(blocked.state, RunState.BLOCKED)
        append = executor._append_event  # noqa: SLF001

        def crash_before_cancel_event(run_id, kind, payload):
            if kind == "run.cancelled":
                raise RuntimeError("crash before executor cancellation")
            return append(run_id, kind, payload)

        executor._append_event = crash_before_cancel_event  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaisesRegex(RuntimeError, "executor cancellation"):
            executor.cancel(request, reason="durable cancellation")
        self.assertEqual(1, host.cancel_calls)
        effect_count = len(host.calls)

        after_expiry = datetime(2026, 9, 2, 12, 16, tzinfo=UTC)
        host.observed_at = "2026-09-02T12:16:00Z"
        recovered = DagExecutor(
            HostRuntime(
                host,
                host_journal,
                one_run_deadline="2026-09-02T12:10:00Z",
                clock=lambda: after_expiry,
            ),
            execution_journal,
            clock=lambda: after_expiry,
        ).cancel(request, reason="durable cancellation")
        self.assertIs(recovered.state, RunState.CANCELLED)
        self.assertEqual(1, host.cancel_calls)
        self.assertEqual(effect_count, len(host.calls))

    def test_cancel_is_idempotent_but_cannot_rewrite_a_completed_run(self) -> None:
        plan = compiler_plan()
        completed_host = FakeHost()
        completed_host_journal = HostOperationJournal()
        completed_execution_journal = ExecutionJournal()
        self.addCleanup(completed_host_journal.close)
        self.addCleanup(completed_execution_journal.close)
        completed_executor = DagExecutor(
            runtime(completed_host, completed_host_journal),
            completed_execution_journal,
            clock=lambda: NOW,
        )
        request = request_for(plan)
        completed = completed_executor.execute(request)
        self.assertEqual(RunState.COMPLETED, completed.state)
        rolled_back = datetime(2026, 9, 2, 11, 59, tzinfo=UTC)
        historical_executor = DagExecutor(
            completed_executor.host_runtime,
            completed_execution_journal,
            clock=lambda: rolled_back,
        )
        self.assertEqual(completed, historical_executor.execute(request))
        with self.assertRaisesRegex(
            DagExecutionError, "completed.*cannot be cancelled"
        ):
            completed_executor.cancel(request, reason="too late")
        self.assertEqual(0, completed_host.cancel_calls)

        blocked_host = FakeHost(fail_node="explorer")
        blocked_host_journal = HostOperationJournal()
        blocked_execution_journal = ExecutionJournal()
        self.addCleanup(blocked_host_journal.close)
        self.addCleanup(blocked_execution_journal.close)
        blocked_executor = DagExecutor(
            runtime(blocked_host, blocked_host_journal),
            blocked_execution_journal,
            clock=lambda: NOW,
        )
        blocked_request = request_for(plan, nonce="nonce-cancel")
        self.assertEqual(
            RunState.BLOCKED, blocked_executor.execute(blocked_request).state
        )
        cancelled = blocked_executor.cancel(blocked_request, reason="operator stop")
        self.assertEqual(RunState.CANCELLED, cancelled.state)
        cancelled_historical_executor = DagExecutor(
            blocked_executor.host_runtime,
            blocked_execution_journal,
            clock=lambda: rolled_back,
        )
        self.assertEqual(
            cancelled,
            cancelled_historical_executor.execute(blocked_request),
        )
        self.assertEqual(
            cancelled,
            cancelled_historical_executor.cancel(
                blocked_request, reason="operator stop"
            ),
        )
        self.assertEqual(
            cancelled, blocked_executor.cancel(blocked_request, reason="operator stop")
        )
        self.assertEqual(cancelled, blocked_executor.execute(blocked_request))
        with self.assertRaisesRegex(DagExecutionError, "another reason"):
            blocked_executor.cancel(blocked_request, reason="changed reason")
        self.assertEqual(1, blocked_host.cancel_calls)

    def test_non_cancelled_host_receipt_never_appends_run_cancelled(self) -> None:
        plan = compiler_plan()
        for state in (HostReceiptState.FAILED, HostReceiptState.SUCCEEDED):
            with self.subTest(state=state):
                host = FakeHost(fail_node="explorer", cancel_state=state)
                host_journal = HostOperationJournal()
                execution_journal = ExecutionJournal()
                self.addCleanup(host_journal.close)
                self.addCleanup(execution_journal.close)
                executor = DagExecutor(
                    runtime(host, host_journal),
                    execution_journal,
                    clock=lambda: NOW,
                )
                request = request_for(plan, nonce=f"bad-cancel-{state.value}")
                blocked = executor.execute(request)
                self.assertEqual(RunState.BLOCKED, blocked.state)
                with self.assertRaises(HostRecoveryRequired):
                    executor.cancel(request, reason="operator stop")
                after = execution_journal.snapshot(blocked.run_id)
                self.assertIsNotNone(after)
                assert after is not None
                self.assertEqual(RunState.BLOCKED, after.state)
                self.assertNotIn(
                    "run.cancelled",
                    {event.kind for event in execution_journal.events(blocked.run_id)},
                )

    def test_execution_journal_rejects_invalid_transitions_before_append(self) -> None:
        journal = ExecutionJournal()
        host_journal = HostOperationJournal()
        self.addCleanup(journal.close)
        self.addCleanup(host_journal.close)
        executor = DagExecutor(
            runtime(FakeHost(), host_journal), journal, clock=lambda: NOW
        )
        run_id = canonical_digest({"run": "transition-test"})
        journal.append(
            run_id,
            "run.initialized",
            {
                "plan_digest": canonical_digest({"plan": 1}),
                "generation_id": canonical_digest({"generation": 1}),
                "subject_id": canonical_digest({"subject": 1}),
                "compilation_digest": canonical_digest({"compilation": 1}),
                "node_ids": ["node-1"],
            },
        )
        with self.assertRaisesRegex(DagExecutionError, "claims completion"):
            executor._append_event(  # noqa: SLF001 - state-machine unit test
                run_id, "run.completed", {}
            )
        self.assertEqual(1, len(journal.events(run_id)))

        executor._append_event(  # noqa: SLF001 - state-machine unit test
            run_id, "host.lease-ready", {"lease_id": "lease-1"}
        )
        executor._append_event(  # noqa: SLF001 - state-machine unit test
            run_id, "run.started", {}
        )
        input_digest = canonical_digest({"input": 1})
        executor._append_event(  # noqa: SLF001 - state-machine unit test
            run_id,
            "node.started",
            {"node_id": "node-1", "input_digest": input_digest},
        )
        with self.assertRaisesRegex(DagExecutionError, "more than once"):
            executor._append_event(  # noqa: SLF001 - state-machine unit test
                run_id,
                "node.started",
                {"node_id": "node-1", "input_digest": input_digest},
            )
        self.assertEqual(4, len(journal.events(run_id)))

    def test_public_execution_journal_cannot_forge_completed_run(self) -> None:
        plan = compiler_plan()
        host = FakeHost()
        host_journal = HostOperationJournal()
        journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(journal.close)
        request = request_for(plan, nonce="forged-completed-history")
        run_id = DagExecutor._run_id(request)  # noqa: SLF001 - adversarial identity
        journal.append(
            run_id,
            "run.initialized",
            {
                "plan_digest": plan.digest(),
                "generation_id": request.generation_id,
                "subject_id": plan.subject.subject_id,
                "compilation_digest": canonical_digest({"forged": "compiler"}),
                "node_ids": [node.node_id for node in plan.nodes],
            },
        )
        forged_events = [
            ("host.lease-ready", {"lease_id": "forged-lease"}),
            ("run.started", {}),
        ]
        for node in plan.nodes:
            forged_events.extend(
                (
                    (
                        "node.started",
                        {"node_id": node.node_id, "input_digest": canonical_digest({"input": node.node_id})},
                    ),
                    (
                        "node.succeeded",
                        {
                            "node_id": node.node_id,
                            "input_digest": canonical_digest({"input": node.node_id}),
                            "output_digest": canonical_digest({"output": node.node_id}),
                            "evidence_digest": canonical_digest({"evidence": node.node_id}),
                            "checkpoint_digest": canonical_digest({"checkpoint": node.node_id}),
                        },
                    ),
                )
            )
        forged_events.append(("run.completed", {}))
        for kind, payload in forged_events:
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(DagExecutionError, "executor-owned"):
                    journal.append(run_id, kind, payload)
        snapshot = journal.snapshot(run_id)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertIs(RunState.INITIALIZED, snapshot.state)
        self.assertEqual([], host.calls)
        self.assertEqual(0, host.prepare_calls)

    def test_stale_activation_missing_adapter_and_insufficient_authority_fail_before_host(
        self,
    ) -> None:
        plan = compiler_plan()
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )

        missing = replace(request_for(plan), available_adapter_ids=())
        with self.assertRaisesRegex(DagExecutionError, "ADAPTER_MISSING"):
            executor.execute(missing)
        expanded = replace(
            request_for(plan, nonce="expanded-adapter-claim"),
            available_adapter_ids=("subject-adapter", "caller-extra-adapter"),
        )
        with self.assertRaisesRegex(DagExecutionError, "ADAPTER_INVALID"):
            executor.execute(expanded)
        stale_request = request_for(plan, nonce="stale-activation")
        stale_executor = DagExecutor(
            runtime(host, host_journal),
            execution_journal,
            clock=lambda: stale_request.authorization.expires_at,
        )
        with self.assertRaisesRegex(DagExecutionError, "ACTIVATION_INVALID"):
            stale_executor.execute(stale_request)
        future_request = request_for(plan, nonce="future-activation")
        future_executor = DagExecutor(
            runtime(host, host_journal),
            execution_journal,
            clock=lambda: datetime(2026, 9, 2, 11, 59, tzinfo=UTC),
        )
        with self.assertRaisesRegex(DagExecutionError, "not yet valid"):
            future_executor.execute(future_request)
        self.assertIsNone(
            execution_journal.snapshot(DagExecutor._run_id(future_request))  # noqa: SLF001
        )
        clock_values = iter(
            (NOW, datetime(2026, 9, 2, 11, 59, tzinfo=UTC))
        )
        rollback_request = request_for(plan, nonce="in-call-clock-rollback")
        rollback_executor = DagExecutor(
            runtime(host, host_journal),
            execution_journal,
            clock=lambda: next(clock_values),
        )
        with self.assertRaisesRegex(DagExecutionError, "not yet valid"):
            rollback_executor.execute(rollback_request)
        self.assertIsNone(
            execution_journal.snapshot(
                DagExecutor._run_id(rollback_request)  # noqa: SLF001
            )
        )
        authority = replace(plan.authority[0], allowed_actions=())
        invalid = replace(plan, authority=(authority,))
        with self.assertRaisesRegex(DagExecutionError, "AUTHORITY_INVALID"):
            executor.execute(request_for(invalid, nonce="nonce-2"))
        external_without_authority = replace(
            plan,
            capabilities=tuple(
                replace(item, effect_class="external-reversible")
                for item in plan.capabilities
            ),
        )
        with self.assertRaisesRegex(DagExecutionError, "external effect"):
            executor.execute(
                request_for(
                    external_without_authority,
                    nonce="external-reversible-without-authority",
                )
            )
        self.assertEqual([], host.calls)
        self.assertEqual(0, host.prepare_calls)

    def test_executor_cross_binds_request_repository_base_and_target_before_host(
        self,
    ) -> None:
        plan = compiler_plan()
        repository = plan.subject.repository
        assert repository is not None
        variants = (
            ("request", replace(plan, request_id=canonical_digest({"other": 1}))),
            (
                "repository",
                replace(
                    plan,
                    subject=SubjectBinding.for_repository(
                        replace(
                            repository,
                            repository_id=canonical_digest({"other": "repo"}),
                        )
                    ),
                ),
            ),
            (
                "base-commit",
                replace(
                    plan,
                    subject=SubjectBinding.for_repository(
                        replace(repository, commit="e" * 40)
                    ),
                ),
            ),
            (
                "base-tree",
                replace(
                    plan,
                    subject=SubjectBinding.for_repository(
                        replace(repository, tree="e" * 40)
                    ),
                ),
            ),
            (
                "target",
                replace(
                    plan,
                    subject=SubjectBinding.for_repository(
                        replace(repository, target_branch="other")
                    ),
                ),
            ),
            (
                "non-repository",
                replace(
                    plan,
                    subject=SubjectBinding.for_non_repository(
                        NonRepositorySubject(
                            "artifact",
                            canonical_digest({"locator": 1}),
                            canonical_digest({"version": 1}),
                        )
                    ),
                ),
            ),
        )
        for label, changed in variants:
            with self.subTest(label=label):
                host = FakeHost()
                host_journal = HostOperationJournal()
                execution_journal = ExecutionJournal()
                self.addCleanup(host_journal.close)
                self.addCleanup(execution_journal.close)
                executor = DagExecutor(
                    runtime(host, host_journal),
                    execution_journal,
                    clock=lambda: NOW,
                )
                with self.assertRaisesRegex(DagExecutionError, "ACTIVATION_INVALID"):
                    executor.execute(
                        request_for(
                            changed,
                            nonce="binding-" + label,
                            bind_subject=False,
                        )
                    )
                self.assertEqual(0, host.prepare_calls)
                self.assertEqual([], host.calls)

    def test_forged_or_tampered_one_run_capability_fails_before_host(self) -> None:
        plan = compiler_plan()
        host = FakeHost()
        host_journal = HostOperationJournal()
        execution_journal = ExecutionJournal()
        self.addCleanup(host_journal.close)
        self.addCleanup(execution_journal.close)
        executor = DagExecutor(
            runtime(host, host_journal), execution_journal, clock=lambda: NOW
        )

        forged = object.__new__(AuthorizedOneRun)
        with self.assertRaisesRegex(ContractViolation, "sealed external"):
            replace(request_for(plan), authorization=forged)

        request = request_for(plan, nonce="tampered-capability")
        object.__setattr__(
            request.authorization.payload,
            "candidate_commit",
            "f" * 40,
        )
        with self.assertRaisesRegex(DagExecutionError, "capability seal"):
            executor.execute(request)
        self.assertEqual([], host.calls)
        self.assertEqual(0, host.cancel_calls)

    def test_execution_journal_reopens_and_rejects_tamper(self) -> None:
        plan = compiler_plan()
        host = FakeHost()
        with tempfile.TemporaryDirectory() as temporary:
            execution_path = Path(temporary) / "execution.sqlite3"
            host_path = Path(temporary) / "host.sqlite3"
            with HostOperationJournal(host_path) as host_journal:
                with ExecutionJournal(execution_path) as execution_journal:
                    executor = DagExecutor(
                        runtime(host, host_journal),
                        execution_journal,
                        clock=lambda: NOW,
                    )
                    finished = executor.execute(request_for(plan))
            with ExecutionJournal(execution_path) as reopened:
                self.assertEqual(finished, reopened.snapshot(finished.run_id))
                reopened.connection.execute(
                    "DROP TRIGGER dag_execution_events_no_update"
                )
                reopened.connection.execute(
                    "UPDATE dag_execution_events SET payload_json='{}' WHERE sequence=1"
                )
                reopened.connection.commit()
                with self.assertRaises(DagExecutionError):
                    reopened.verify()

    def test_execution_journal_rejects_boolean_schema_version(self) -> None:
        journal = ExecutionJournal()
        self.addCleanup(journal.close)
        run_id = canonical_digest({"run": "boolean-schema"})
        journal.append(
            run_id,
            "run.initialized",
            {
                "plan_digest": canonical_digest({"plan": 1}),
                "generation_id": canonical_digest({"generation": 1}),
                "subject_id": canonical_digest({"subject": 1}),
                "compilation_digest": canonical_digest({"compilation": 1}),
                "node_ids": ["node-1"],
            },
        )
        row = journal.connection.execute(
            "SELECT payload_json FROM dag_execution_events WHERE run_id=?",
            (run_id,),
        ).fetchone()
        payload = json.loads(str(row[0]))
        payload["schema_version"] = True
        journal.connection.execute("DROP TRIGGER dag_execution_events_no_update")
        journal.connection.execute(
            "UPDATE dag_execution_events SET payload_json=? WHERE run_id=?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), run_id),
        )
        journal.connection.commit()
        with self.assertRaisesRegex(DagExecutionError, "malformed"):
            journal.verify()

    def test_crash_between_host_create_and_lease_event_reobserves_before_execute(
        self,
    ) -> None:
        plan = compiler_plan()
        request = request_for(plan, nonce="create-crash-window")
        host = FakeHost()
        with tempfile.TemporaryDirectory() as temporary:
            host_path = Path(temporary) / "host.sqlite3"
            execution_path = Path(temporary) / "execution.sqlite3"
            with HostOperationJournal(host_path) as host_journal:
                with ExecutionJournal(execution_path) as execution_journal:
                    original_append = execution_journal.append

                    def crash_before_lease_event(
                        run_id: str,
                        kind: str,
                        payload: dict,
                        **options: object,
                    ):
                        if kind == "host.lease-ready":
                            raise RuntimeError("simulated process loss")
                        return original_append(run_id, kind, payload, **options)

                    execution_journal.append = crash_before_lease_event  # type: ignore[method-assign]
                    executor = DagExecutor(
                        runtime(host, host_journal),
                        execution_journal,
                        clock=lambda: NOW,
                    )
                    with self.assertRaisesRegex(RuntimeError, "process loss"):
                        executor.execute(request)
                    self.assertEqual(1, host.prepare_calls)
                    self.assertEqual([], host.calls)

            host.identity = replace(host.identity, executable_digest="sha256:" + "f" * 64)
            with HostOperationJournal(host_path) as reopened_host:
                with ExecutionJournal(execution_path) as reopened_execution:
                    restarted = DagExecutor(
                        runtime(host, reopened_host),
                        reopened_execution,
                        clock=lambda: NOW,
                    )
                    blocked = restarted.execute(request)
                    self.assertEqual(RunState.BLOCKED, blocked.state)
                    self.assertEqual([], host.calls)
                    self.assertEqual(1, host.prepare_calls)

    def test_graph_patch_requires_signature_and_is_monotonic(self) -> None:
        base = compiler_plan()
        first = replace(
            base.nodes[0],
            acceptance_criteria=(*base.nodes[0].acceptance_criteria, "extra proof"),
        )
        successor = replace(base, nodes=(first, *base.nodes[1:]))
        patch = GraphPatch(
            base.digest(),
            successor.digest(),
            None,
            "2027-01-01T00:00:00Z",
            "external-planner",
            "key-1",
            "signature",
        )
        receipt = validate_graph_patch(
            base.canonical_bytes(),
            successor.canonical_bytes(),
            standard_bytes=STANDARD,
            patch=patch,
            expected_one_run_expires_at="2027-01-01T00:00:00Z",
            verifier=lambda _patch, _material: True,
        )
        self.assertEqual(successor.digest(), receipt.plan_digest)
        with self.assertRaisesRegex(DagExecutionError, "signature"):
            validate_graph_patch(
                base.canonical_bytes(),
                successor.canonical_bytes(),
                standard_bytes=STANDARD,
                patch=patch,
                expected_one_run_expires_at="2027-01-01T00:00:00Z",
                verifier=lambda _patch, _material: False,
            )
        weakened = replace(
            successor, nodes=(replace(first, objective="substitute"), *base.nodes[1:])
        )
        weak_patch = replace(patch, successor_plan_digest=weakened.digest())
        with self.assertRaisesRegex(DagExecutionError, "protected node"):
            validate_graph_patch(
                base.canonical_bytes(),
                weakened.canonical_bytes(),
                standard_bytes=STANDARD,
                patch=weak_patch,
                expected_one_run_expires_at="2027-01-01T00:00:00Z",
                verifier=lambda _patch, _material: True,
            )


if __name__ == "__main__":
    unittest.main()
