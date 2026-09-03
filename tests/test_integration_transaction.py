from __future__ import annotations

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, BrokenBarrierError, Event
from typing import Callable

from hive_mind_os.activation_bundle import (
    AuthorizedOneRun,
    request_sha256,
    validate_authorized_one_run,
)
from hive_mind_os.brain_kernel.candidate_state import (
    CandidateSnapshot,
    CandidateStateJournal,
)
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.integration_transaction import (
    IntegrationCoordinator,
    IntegrationError,
    IntegrationJournal,
    IntegrationState,
    IntegrationTargetBinding,
    IntegrationTransaction,
)
from hive_mind_os.portable_plan import PortablePlanBundle, SubjectBinding
from hive_mind_os.runtime_contracts import (
    AdapterRequirement,
    CapabilityRequirement,
    ContractViolation,
    IntegrationPolicy,
    WaveState,
)
from hive_mind_os.wave_manifest import (
    CandidateIdentity,
    WaveManifest,
    WaveNode,
    WaveNodeState,
)
from tests.test_dag_standard_product import STANDARD, compiler_plan
from tests.test_generic_dag_v4_activation import REQUEST, authorized_one_run_fixture

DIGEST = "sha256:" + "2" * 64
OTHER_DIGEST = "sha256:" + "3" * 64
REPOSITORY_DIGEST = "sha256:" + "5" * 64
EXECUTION_CLIENT_DIGEST = "sha256:" + "d" * 64
_BASE_PLAN = compiler_plan()
_ORIGINAL_REPOSITORY = _BASE_PLAN.subject.repository
assert _ORIGINAL_REPOSITORY is not None
_REPOSITORY = replace(
    _ORIGINAL_REPOSITORY,
    repository_id=REPOSITORY_DIGEST,
    commit="0" * 40,
    tree="1" * 40,
    target_branch="main",
)
_SUBJECT_BINDING = SubjectBinding.for_repository(_REPOSITORY)
SUBJECT = _SUBJECT_BINDING.subject_id
BASE = CandidateIdentity(_REPOSITORY.commit, _REPOSITORY.tree, SUBJECT)
PROPOSED = CandidateIdentity("6" * 40, "7" * 40, SUBJECT)
UNKNOWN = CandidateIdentity("e" * 40, "f" * 40, SUBJECT)
PLAN = replace(
    _BASE_PLAN,
    request_id=request_sha256(REQUEST),
    subject=_SUBJECT_BINDING,
    adapters=_BASE_PLAN.adapters
    + (AdapterRequirement("integration-target", "integration.target", "v1", DIGEST),),
    capabilities=_BASE_PLAN.capabilities
    + (
        CapabilityRequirement(
            "integrate-target",
            "integrate",
            "external-reversible",
            "local-auth",
            "integration-target",
        ),
    ),
    authority=tuple(
        replace(
            item,
            allowed_actions=item.allowed_actions + ("integrate",),
            denied_actions=tuple(
                action
                for action in item.denied_actions
                if action not in {"merge", "protected-merge"}
            ),
            external_effects=True,
        )
        for item in _BASE_PLAN.authority
    ),
    integration=IntegrationPolicy(
        "compare-and-swap",
        "main",
        canonical_digest({"commit": BASE.commit, "tree": BASE.tree}),
        True,
        False,
    ),
)
PLAN_BYTES = PLAN.canonical_bytes()
NOW = datetime(2026, 9, 2, 12, 5, tzinfo=UTC)
AUTHORITY_DIGEST = canonical_digest([item.to_document() for item in PLAN.authority])
WAVE = WaveManifest(
    1,
    "wave-1",
    PLAN.digest(),
    DIGEST,
    SUBJECT,
    None,
    WaveState.INTEGRATION_READY,
    (
        WaveNode("node-a", WaveNodeState.COMPLETED, 1, None, OTHER_DIGEST),
        WaveNode("node-b", WaveNodeState.COMPLETED, 1, None, OTHER_DIGEST),
    ),
    OTHER_DIGEST,
    PROPOSED,
    "2026-09-02T12:00:00Z",
)


def candidate(
    journal: CandidateStateJournal,
    node: str,
    digit: str,
    *,
    wave: WaveManifest = WAVE,
    authority_digest: str = AUTHORITY_DIGEST,
) -> CandidateSnapshot:
    candidate_id = f"candidate-{node}"
    journal.checkpoint(
        candidate_id=candidate_id,
        wave_id="wave-1",
        node_id=node,
        generation=1,
        manifest_digest=wave.manifest_digest,
        authority_digest=authority_digest,
        checkpoint_digest=DIGEST,
        idempotency_key=f"{node}:checkpoint",
    )
    journal.transition(
        candidate_id,
        expected_sequence=1,
        state=WaveState.CANDIDATE_SEALED,
        identity=CandidateIdentity(
            digit * 40, str((int(digit) + 1) % 10) * 40, SUBJECT
        ),
        idempotency_key=f"{node}:sealed",
    )
    journal.transition(
        candidate_id,
        expected_sequence=2,
        state=WaveState.VERIFYING,
        idempotency_key=f"{node}:verifying",
    )
    return journal.transition(
        candidate_id,
        expected_sequence=3,
        state=WaveState.INTEGRATION_READY,
        checkpoint_digest=OTHER_DIGEST,
        idempotency_key=f"{node}:ready",
    )


class FakeTarget:
    def __init__(self) -> None:
        self.identity = BASE
        self.calls = 0
        self.binding_calls = 0
        self.observe_calls = 0
        self.behavior = "success"
        self.effect_clock: Callable[[], datetime] = lambda: NOW
        self.after_observe: Callable[[], None] | None = None
        self.before_cas: Callable[[], None] | None = None
        self.adapter_binding = IntegrationTargetBinding(
            "integration-target",
            "integration.target",
            "v1",
            DIGEST,
            EXECUTION_CLIENT_DIGEST,
            False,
        )

    def binding(self) -> IntegrationTargetBinding:
        self.binding_calls += 1
        return self.adapter_binding

    def observe_target(self, target_ref: str) -> CandidateIdentity:
        self.observe_calls += 1
        if target_ref != "main":
            raise AssertionError("unexpected target")
        if self.behavior == "binding-drift-post-cas" and self.observe_calls >= 3:
            self.adapter_binding = replace(self.adapter_binding, trust_digest=DIGEST)
        if self.after_observe is not None:
            self.after_observe()
        return self.identity

    def compare_and_swap(self, **values):
        self.calls += 1
        self.last = values
        if values["expected_binding"] != self.adapter_binding:
            return False
        authorization = validate_authorized_one_run(values["authorization"])
        plan_deadline = datetime.fromisoformat(
            values["integration_authority_expires_at"].replace("Z", "+00:00")
        )
        expected_deadline = min(authorization.expires_at, plan_deadline)
        effect_time = self.effect_clock()
        if (
            values["effect_deadline"] != expected_deadline
            or effect_time < authorization.issued_at
            or effect_time >= expected_deadline
            or values["protected_merge_authorized"] is not False
            or authorization.protected_merge_authorized
            or self.adapter_binding.protected_target is not False
        ):
            return False
        if self.before_cas is not None:
            self.before_cas()
        if self.behavior == "raise-before":
            raise OSError("transport failed")
        if self.behavior == "drift":
            self.identity = UNKNOWN
            return False
        if self.identity != values["expected_target"]:
            return False
        self.identity = values["proposed_target"]
        if self.behavior == "raise-after":
            raise OSError("response lost")
        return True


class IntegrationTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.journal = IntegrationJournal()
        self.addCleanup(self.journal.close)
        self.target = FakeTarget()
        self.coordinator = IntegrationCoordinator(
            self.journal, self.target, clock=lambda: NOW
        )
        self.candidate_journal = CandidateStateJournal()
        self.addCleanup(self.candidate_journal.close)
        self.candidates = (
            candidate(self.candidate_journal, "node-a", "4"),
            candidate(self.candidate_journal, "node-b", "6"),
        )
        self.authorization = authorized_one_run_fixture(PLAN_BYTES)

    def prepare(self, **overrides):
        values = {
            "round_id": "round-1",
            "target_ref": "main",
            "expected_target": BASE,
            "proposed_target": PROPOSED,
            "candidates": self.candidates,
            "idempotency_key": "prepare-1",
            "authorization": self.authorization,
            "plan_bytes": PLAN_BYTES,
            "standard_bytes": STANDARD,
            "wave_manifest_bytes": WAVE.canonical_bytes(),
            "candidate_journal": self.candidate_journal,
        }
        values.update(overrides)
        return self.coordinator.prepare(**values)

    def test_ordered_candidates_validate_once_and_target_advances_once(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.state, IntegrationState.PREPARED)
        self.assertEqual(self.authorization.plan_sha256, prepared.plan_digest)
        self.assertEqual(
            self.authorization.manifest_sha256,
            prepared.activation_manifest_digest,
        )
        self.assertEqual(WAVE.manifest_digest, prepared.manifest_digest)
        self.assertEqual(
            self.target.adapter_binding.digest, prepared.target_binding_digest
        )
        self.assertEqual("2030-01-01T00:00:00Z", prepared.integration_authority_expires_at)
        self.assertTrue(prepared.transaction_id.startswith("sha256:"))
        committed = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-1",
            authorization=self.authorization,
        )
        self.assertEqual(committed.state, IntegrationState.COMMITTED)
        self.assertEqual(self.target.identity, PROPOSED)
        self.assertEqual(self.target.calls, 1)
        self.assertEqual(
            [item.node_id for item in self.target.last["ordered_candidates"]],
            ["node-a", "node-b"],
        )
        self.assertEqual(
            "integration.target", self.target.last["expected_binding"].interface
        )
        self.assertEqual("v1", self.target.last["expected_binding"].version)
        again = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-1",
            authorization=self.authorization,
        )
        self.assertEqual(again, committed)
        self.assertEqual(self.target.calls, 1)
        prepared_retry = self.prepare()
        self.assertEqual(prepared_retry, committed)

    def test_round_aliases_converge_on_one_transaction_and_cas_owner(self) -> None:
        synchronization_timeout = 5.0
        prepare_start = Barrier(3)
        commit_start = Barrier(3)
        cas_entered = Event()
        loser_waiting = Event()
        release_cas = Event()

        class WaitingJournal(IntegrationJournal):
            def _wait_for_change(
                self,
                transaction_id: str,
                *,
                after_sequence: int,
                timeout: float,
            ) -> IntegrationTransaction | None:
                loser_waiting.set()
                return super()._wait_for_change(
                    transaction_id,
                    after_sequence=after_sequence,
                    timeout=timeout,
                )

        journal = WaitingJournal()
        self.addCleanup(journal.close)
        target = FakeTarget()
        coordinator = IntegrationCoordinator(journal, target, clock=lambda: NOW)

        def hold_cas() -> None:
            cas_entered.set()
            if not release_cas.wait(synchronization_timeout):
                raise AssertionError("test did not release compare-and-swap")

        def prepare_and_commit(
            round_alias: str,
        ) -> tuple[IntegrationTransaction, IntegrationTransaction]:
            prepare_start.wait(timeout=synchronization_timeout)
            prepared = coordinator.prepare(
                round_id=round_alias,
                target_ref="main",
                expected_target=BASE,
                proposed_target=PROPOSED,
                candidates=self.candidates,
                idempotency_key=f"prepare-{round_alias}",
                authorization=self.authorization,
                plan_bytes=PLAN_BYTES,
                standard_bytes=STANDARD,
                wave_manifest_bytes=WAVE.canonical_bytes(),
                candidate_journal=self.candidate_journal,
            )
            commit_start.wait(timeout=synchronization_timeout)
            committed = coordinator.commit(
                prepared.transaction_id,
                idempotency_key="concurrent-commit",
                authorization=self.authorization,
            )
            return prepared, committed

        target.before_cas = hold_cas
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = (
                pool.submit(prepare_and_commit, "caller-round-a"),
                pool.submit(prepare_and_commit, "caller-round-b"),
            )
            coordination_failures: list[str] = []
            try:
                for name, barrier in (
                    ("prepare", prepare_start),
                    ("commit", commit_start),
                ):
                    try:
                        barrier.wait(timeout=synchronization_timeout)
                    except BrokenBarrierError:
                        coordination_failures.append(f"{name} barrier broke")
                        break
                if not coordination_failures:
                    if not cas_entered.wait(synchronization_timeout):
                        coordination_failures.append("compare-and-swap was not entered")
                    if not loser_waiting.wait(synchronization_timeout):
                        coordination_failures.append("losing commit did not wait")
            finally:
                # No assertion or worker exception may strand the compare-and-swap
                # owner or a peer at a test-owned barrier during executor shutdown.
                release_cas.set()
                if coordination_failures:
                    prepare_start.abort()
                    commit_start.abort()

            results_list: list[
                tuple[IntegrationTransaction, IntegrationTransaction]
            ] = []
            worker_failures: list[str] = []
            for index, future in enumerate(futures, start=1):
                try:
                    results_list.append(
                        future.result(timeout=synchronization_timeout)
                    )
                except Exception as error:  # noqa: BLE001 - retain both worker causes
                    causes: list[str] = []
                    current: BaseException | None = error
                    while current is not None:
                        causes.append(f"{type(current).__name__}: {current}")
                        current = current.__cause__
                    worker_failures.append(
                        f"worker {index}: {' caused by '.join(causes)}"
                    )

            if coordination_failures or worker_failures:
                self.fail(
                    "; ".join((*coordination_failures, *worker_failures))
                )
            results = tuple(results_list)

        prepared_results = tuple(item[0] for item in results)
        committed_results = tuple(item[1] for item in results)
        expected_round_id = canonical_digest(
            {
                "schema_version": 1,
                "kind": "hive-mind-integration-round-v1",
                "authorization_proof_digest": self.authorization.proof_digest,
                "wave_manifest_digest": WAVE.manifest_digest,
            }
        )
        self.assertEqual(1, len({item.transaction_id for item in prepared_results}))
        self.assertEqual(
            (expected_round_id,) * 2,
            tuple(item.round_id for item in prepared_results),
        )
        self.assertEqual(
            (IntegrationState.COMMITTED,) * 2,
            tuple(item.state for item in committed_results),
        )
        self.assertEqual(committed_results[0], committed_results[1])
        self.assertEqual(1, target.calls)
        events = tuple(
            journal._decode(row)
            for row in journal._rows(prepared_results[0].transaction_id)
        )
        self.assertEqual(
            1,
            sum(item.state is IntegrationState.PREPARED for item in events),
        )
        self.assertEqual(
            1,
            sum(item.state is IntegrationState.COMMITTED for item in events),
        )

    def test_boolean_transaction_schema_version_is_rejected(self) -> None:
        document = self.prepare().to_document()
        document["schema_version"] = True
        with self.assertRaisesRegex(IntegrationError, "unknown shape"):
            IntegrationTransaction.from_document(document)

    def test_trusted_journal_preparation_receipt_survives_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "integration.sqlite"
            journal = IntegrationJournal(path)
            target = FakeTarget()
            coordinator = IntegrationCoordinator(journal, target, clock=lambda: NOW)
            prepared = coordinator.prepare(
                round_id="durable-round",
                target_ref="main",
                expected_target=BASE,
                proposed_target=PROPOSED,
                candidates=self.candidates,
                idempotency_key="durable-prepare",
                authorization=self.authorization,
                plan_bytes=PLAN_BYTES,
                standard_bytes=STANDARD,
                wave_manifest_bytes=WAVE.canonical_bytes(),
                candidate_journal=self.candidate_journal,
            )
            journal.close()

            reopened = IntegrationJournal(path)
            try:
                resumed = IntegrationCoordinator(reopened, target, clock=lambda: NOW)
                committed = resumed.commit(
                    prepared.transaction_id,
                    idempotency_key="durable-commit",
                    authorization=self.authorization,
                )

                self.assertEqual(IntegrationState.COMMITTED, committed.state)
                self.assertEqual(PROPOSED, target.identity)
            finally:
                reopened.close()

    def test_response_loss_adopts_exact_proposed_target_without_retry(self) -> None:
        prepared = self.prepare()
        self.target.behavior = "raise-after"
        result = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-lost",
            authorization=self.authorization,
        )
        self.assertEqual(result.state, IntegrationState.COMMITTED)
        self.assertEqual(self.target.calls, 1)

    def test_failure_before_effect_is_recoverable_and_never_blindly_retried(
        self,
    ) -> None:
        prepared = self.prepare()
        self.target.behavior = "raise-before"
        result = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-failed",
            authorization=self.authorization,
        )
        self.assertEqual(result.state, IntegrationState.RECOVERABLE)
        self.assertEqual(self.target.identity, BASE)
        with self.assertRaisesRegex(IntegrationError, "prepared"):
            self.coordinator.commit(
                prepared.transaction_id,
                idempotency_key="retry",
                authorization=self.authorization,
            )
        self.assertEqual(self.target.calls, 1)

    def test_unknown_target_after_cas_requires_replan(self) -> None:
        prepared = self.prepare()
        self.target.behavior = "drift"
        result = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-drift",
            authorization=self.authorization,
        )
        self.assertEqual(result.state, IntegrationState.REPLAN_REQUIRED)
        self.assertEqual(self.target.identity, UNKNOWN)

    def test_binding_drift_during_outcome_observation_never_commits(self) -> None:
        prepared = self.prepare()
        self.target.behavior = "binding-drift-post-cas"
        result = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-binding-drift",
            authorization=self.authorization,
        )
        self.assertEqual(IntegrationState.RECOVERABLE, result.state)
        self.assertEqual(PROPOSED, self.target.identity)
        self.assertEqual(1, self.target.calls)

    def test_binding_drift_during_reconcile_observation_never_commits(self) -> None:
        prepared = self.prepare()
        self.target.behavior = "raise-before"
        recoverable = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-before-reconcile-drift",
            authorization=self.authorization,
        )
        self.assertEqual(IntegrationState.RECOVERABLE, recoverable.state)
        self.target.identity = PROPOSED
        self.target.behavior = "binding-drift-post-cas"

        result = self.coordinator.reconcile(
            prepared.transaction_id,
            idempotency_key="reconcile-binding-drift",
            authorization=self.authorization,
        )

        self.assertEqual(IntegrationState.RECOVERABLE, result.state)
        self.assertEqual(1, self.target.calls)

    def test_target_drift_and_unready_or_reordered_candidates_fail_closed(self) -> None:
        self.target.identity = UNKNOWN
        with self.assertRaisesRegex(IntegrationError, "drifted"):
            self.prepare()
        self.target.identity = BASE
        with self.assertRaisesRegex(IntegrationError, "order"):
            self.prepare(integration_order=("node-b", "node-a"))
        unready = replace(self.candidates[0], state=WaveState.VERIFYING)
        with self.assertRaisesRegex(IntegrationError, "not integration-ready"):
            self.prepare(candidates=(unready, self.candidates[1]))

    def test_round_has_exactly_one_transaction_and_history_is_append_only(self) -> None:
        prepared = self.prepare()
        alias = self.prepare(round_id="caller-alias", idempotency_key="prepare-2")
        self.assertEqual(prepared, alias)
        with self.assertRaises(sqlite3.DatabaseError):
            self.journal.connection.execute("DELETE FROM integration_events")

    def test_forged_stale_and_substituted_authorization_fail_before_cas(self) -> None:
        forged = object.__new__(AuthorizedOneRun)
        with self.assertRaisesRegex(IntegrationError, "genuine AuthorizedOneRun"):
            self.prepare(authorization=forged)
        self.assertEqual(0, self.target.observe_calls)

        stale = IntegrationCoordinator(
            self.journal,
            self.target,
            clock=lambda: NOW + timedelta(minutes=6),
        )
        with self.assertRaisesRegex(IntegrationError, "stale"):
            stale.prepare(
                round_id="round-stale",
                target_ref="main",
                expected_target=BASE,
                proposed_target=PROPOSED,
                candidates=self.candidates,
                idempotency_key="prepare-stale",
                authorization=self.authorization,
                plan_bytes=PLAN_BYTES,
                standard_bytes=STANDARD,
                wave_manifest_bytes=WAVE.canonical_bytes(),
                candidate_journal=self.candidate_journal,
            )

        replacement = authorized_one_run_fixture(
            PLAN_BYTES, nonce_seed="replacement-integration-run"
        )
        prepared = self.prepare()
        with self.assertRaisesRegex(IntegrationError, "authorization was substituted"):
            self.coordinator.commit(
                prepared.transaction_id,
                idempotency_key="commit-substituted",
                authorization=replacement,
            )
        self.assertEqual(0, self.target.calls)

    def test_authorization_expiring_after_prepare_denies_commit(self) -> None:
        observed_time = [NOW]
        coordinator = IntegrationCoordinator(
            self.journal, self.target, clock=lambda: observed_time[0]
        )
        prepared = coordinator.prepare(
            round_id="round-expiry",
            target_ref="main",
            expected_target=BASE,
            proposed_target=PROPOSED,
            candidates=self.candidates,
            idempotency_key="prepare-expiry",
            authorization=self.authorization,
            plan_bytes=PLAN_BYTES,
            standard_bytes=STANDARD,
            wave_manifest_bytes=WAVE.canonical_bytes(),
            candidate_journal=self.candidate_journal,
        )
        observed_time[0] = NOW + timedelta(minutes=6)
        with self.assertRaisesRegex(IntegrationError, "stale"):
            coordinator.commit(
                prepared.transaction_id,
                idempotency_key="commit-expiry",
                authorization=self.authorization,
            )
        self.assertEqual(0, self.target.calls)

    def test_authorization_expiring_during_pre_cas_observation_denies_effect(
        self,
    ) -> None:
        observed_time = [NOW]
        coordinator = IntegrationCoordinator(
            self.journal, self.target, clock=lambda: observed_time[0]
        )
        prepared = coordinator.prepare(
            round_id="round-expiry-during-observe",
            target_ref="main",
            expected_target=BASE,
            proposed_target=PROPOSED,
            candidates=self.candidates,
            idempotency_key="prepare-expiry-during-observe",
            authorization=self.authorization,
            plan_bytes=PLAN_BYTES,
            standard_bytes=STANDARD,
            wave_manifest_bytes=WAVE.canonical_bytes(),
            candidate_journal=self.candidate_journal,
        )
        self.target.after_observe = lambda: observed_time.__setitem__(
            0, self.authorization.expires_at
        )

        with self.assertRaisesRegex(IntegrationError, "stale"):
            coordinator.commit(
                prepared.transaction_id,
                idempotency_key="commit-expiry-during-observe",
                authorization=self.authorization,
            )

        self.assertEqual(0, self.target.calls)
        self.assertEqual(BASE, self.target.identity)
        latest = self.journal.latest(prepared.transaction_id)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(
            IntegrationState.EXECUTING,
            latest.state,
        )

    def test_target_atomically_rejects_effect_after_activation_expiry(self) -> None:
        prepared = self.prepare()
        self.target.effect_clock = lambda: self.authorization.expires_at

        result = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-atomic-expiry",
            authorization=self.authorization,
        )

        self.assertEqual(IntegrationState.RECOVERABLE, result.state)
        self.assertEqual(1, self.target.calls)
        self.assertEqual(BASE, self.target.identity)

    def test_plan_authority_deadline_is_bound_and_denies_late_commit(self) -> None:
        deadline = "2026-09-02T12:06:00Z"
        expiring_plan = replace(
            PLAN,
            authority=tuple(
                replace(item, expires_at=deadline) for item in PLAN.authority
            ),
        )
        expiring_bytes = expiring_plan.canonical_bytes()
        authorization = authorized_one_run_fixture(
            expiring_bytes, nonce_seed="expiring-plan-integration-authority"
        )
        expiring_wave = replace(
            WAVE, plan_digest=expiring_plan.digest(), manifest_digest=""
        )
        authority_digest = canonical_digest(
            [item.to_document() for item in expiring_plan.authority]
        )
        candidate_journal = CandidateStateJournal()
        self.addCleanup(candidate_journal.close)
        candidates = (
            candidate(
                candidate_journal,
                "node-a",
                "4",
                wave=expiring_wave,
                authority_digest=authority_digest,
            ),
            candidate(
                candidate_journal,
                "node-b",
                "6",
                wave=expiring_wave,
                authority_digest=authority_digest,
            ),
        )
        observed_time = [NOW]
        coordinator = IntegrationCoordinator(
            self.journal, self.target, clock=lambda: observed_time[0]
        )
        prepared = coordinator.prepare(
            round_id="round-plan-authority-expiry",
            target_ref="main",
            expected_target=BASE,
            proposed_target=PROPOSED,
            candidates=candidates,
            idempotency_key="prepare-plan-authority-expiry",
            authorization=authorization,
            plan_bytes=expiring_bytes,
            standard_bytes=STANDARD,
            wave_manifest_bytes=expiring_wave.canonical_bytes(),
            candidate_journal=candidate_journal,
        )
        self.assertEqual(deadline, prepared.integration_authority_expires_at)
        observe_calls = self.target.observe_calls
        observed_time[0] = NOW + timedelta(minutes=2)

        with self.assertRaisesRegex(IntegrationError, "effect authority is stale"):
            coordinator.commit(
                prepared.transaction_id,
                idempotency_key="commit-plan-authority-expiry",
                authorization=authorization,
            )

        self.assertEqual(0, self.target.calls)
        self.assertEqual(observe_calls, self.target.observe_calls)

    def test_preissuance_clock_rollback_fails_before_target_boundary(self) -> None:
        coordinator = IntegrationCoordinator(
            self.journal,
            self.target,
            clock=lambda: self.authorization.issued_at - timedelta(microseconds=1),
        )

        with self.assertRaisesRegex(IntegrationError, "not yet valid"):
            coordinator.prepare(
                round_id="round-preissuance",
                target_ref="main",
                expected_target=BASE,
                proposed_target=PROPOSED,
                candidates=self.candidates,
                idempotency_key="prepare-preissuance",
                authorization=self.authorization,
                plan_bytes=PLAN_BYTES,
                standard_bytes=STANDARD,
                wave_manifest_bytes=WAVE.canonical_bytes(),
                candidate_journal=self.candidate_journal,
            )

        self.assertEqual(0, self.target.binding_calls)
        self.assertEqual(0, self.target.observe_calls)
        self.assertEqual(0, self.target.calls)

    def test_target_atomically_rejects_effect_before_activation_issuance(self) -> None:
        prepared = self.prepare()
        self.target.effect_clock = lambda: self.authorization.issued_at - timedelta(
            microseconds=1
        )

        result = self.coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-target-clock-rollback",
            authorization=self.authorization,
        )

        self.assertEqual(IntegrationState.RECOVERABLE, result.state)
        self.assertEqual(BASE, self.target.identity)
        self.assertEqual(1, self.target.calls)

    def test_expired_exact_authorization_reconciles_ambiguous_state(self) -> None:
        observed_time = [NOW]
        coordinator = IntegrationCoordinator(
            self.journal, self.target, clock=lambda: observed_time[0]
        )
        prepared = coordinator.prepare(
            round_id="round-expired-reconcile",
            target_ref="main",
            expected_target=BASE,
            proposed_target=PROPOSED,
            candidates=self.candidates,
            idempotency_key="prepare-expired-reconcile",
            authorization=self.authorization,
            plan_bytes=PLAN_BYTES,
            standard_bytes=STANDARD,
            wave_manifest_bytes=WAVE.canonical_bytes(),
            candidate_journal=self.candidate_journal,
        )
        self.target.behavior = "raise-before"
        recoverable = coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-expired-reconcile",
            authorization=self.authorization,
        )
        self.assertEqual(IntegrationState.RECOVERABLE, recoverable.state)
        cas_calls = self.target.calls

        observed_time[0] = NOW + timedelta(minutes=6)
        self.target.identity = PROPOSED
        reconciled = coordinator.reconcile(
            prepared.transaction_id,
            idempotency_key="expired-read-only-reconcile",
            authorization=self.authorization,
        )

        self.assertEqual(IntegrationState.COMMITTED, reconciled.state)
        self.assertEqual(cas_calls, self.target.calls)

    def test_committed_terminal_accepts_only_exact_historical_authorization(
        self,
    ) -> None:
        observed_time = [NOW]
        coordinator = IntegrationCoordinator(
            self.journal, self.target, clock=lambda: observed_time[0]
        )
        prepared = coordinator.prepare(
            round_id="round-terminal-history",
            target_ref="main",
            expected_target=BASE,
            proposed_target=PROPOSED,
            candidates=self.candidates,
            idempotency_key="prepare-terminal-history",
            authorization=self.authorization,
            plan_bytes=PLAN_BYTES,
            standard_bytes=STANDARD,
            wave_manifest_bytes=WAVE.canonical_bytes(),
            candidate_journal=self.candidate_journal,
        )
        committed = coordinator.commit(
            prepared.transaction_id,
            idempotency_key="commit-terminal-history",
            authorization=self.authorization,
        )
        target_calls = (
            self.target.binding_calls,
            self.target.observe_calls,
            self.target.calls,
        )

        for instant in (
            self.authorization.expires_at,
            self.authorization.expires_at + timedelta(days=1),
        ):
            with self.subTest(instant=instant.isoformat()):
                observed_time[0] = instant
                terminal = coordinator.commit(
                    prepared.transaction_id,
                    idempotency_key="historical-terminal-read",
                    authorization=self.authorization,
                )
                self.assertEqual(committed, terminal)
                self.assertEqual(
                    target_calls,
                    (
                        self.target.binding_calls,
                        self.target.observe_calls,
                        self.target.calls,
                    ),
                )

        replacement = authorized_one_run_fixture(
            PLAN_BYTES, nonce_seed="substituted-terminal-run"
        )
        with self.assertRaisesRegex(IntegrationError, "authorization was substituted"):
            coordinator.commit(
                prepared.transaction_id,
                idempotency_key="substituted-terminal-read",
                authorization=replacement,
            )
        self.assertEqual(
            target_calls,
            (
                self.target.binding_calls,
                self.target.observe_calls,
                self.target.calls,
            ),
        )

    def test_reopen_after_expiry_reconciles_without_process_local_capability(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "expired-reconcile.sqlite"
            journal = IntegrationJournal(path)
            target = FakeTarget()
            coordinator = IntegrationCoordinator(journal, target, clock=lambda: NOW)
            prepared = coordinator.prepare(
                round_id="round-reopen-expired-reconcile",
                target_ref="main",
                expected_target=BASE,
                proposed_target=PROPOSED,
                candidates=self.candidates,
                idempotency_key="prepare-reopen-expired-reconcile",
                authorization=self.authorization,
                plan_bytes=PLAN_BYTES,
                standard_bytes=STANDARD,
                wave_manifest_bytes=WAVE.canonical_bytes(),
                candidate_journal=self.candidate_journal,
            )
            target.behavior = "raise-before"
            recoverable = coordinator.commit(
                prepared.transaction_id,
                idempotency_key="commit-reopen-expired-reconcile",
                authorization=self.authorization,
            )
            self.assertEqual(IntegrationState.RECOVERABLE, recoverable.state)
            journal.close()

            restarted_target = FakeTarget()
            restarted_target.identity = PROPOSED
            reopened = IntegrationJournal(path)
            try:
                restarted = IntegrationCoordinator(
                    reopened,
                    restarted_target,
                    clock=lambda: self.authorization.expires_at,
                )
                reconciled = restarted.reconcile(
                    prepared.transaction_id,
                    idempotency_key="reconcile-after-restart-and-expiry",
                )

                self.assertEqual(IntegrationState.COMMITTED, reconciled.state)
                self.assertEqual(0, restarted_target.calls)
                self.assertEqual(1, restarted_target.observe_calls)
            finally:
                reopened.close()

    def test_target_adapter_substitution_after_prepare_denies_commit(self) -> None:
        prepared = self.prepare()
        self.target.adapter_binding = replace(
            self.target.adapter_binding, trust_digest=DIGEST
        )
        with self.assertRaisesRegex(IntegrationError, "adapter was substituted"):
            self.coordinator.commit(
                prepared.transaction_id,
                idempotency_key="commit-adapter-substitution",
                authorization=self.authorization,
            )
        self.assertEqual(0, self.target.calls)

    def test_interface_and_version_drift_fail_before_target_or_cas(self) -> None:
        for field, value in (("interface", "integration.other"), ("version", "v2")):
            with self.subTest(stage="prepare", field=field):
                original = self.target.adapter_binding
                self.target.adapter_binding = replace(original, **{field: value})
                with self.assertRaisesRegex(
                    IntegrationError, "target adapter was substituted"
                ):
                    self.prepare()
                self.assertEqual(0, self.target.observe_calls)
                self.assertEqual(0, self.target.calls)
                self.target.adapter_binding = original

            with self.subTest(stage="commit", field=field):
                journal = IntegrationJournal()
                self.addCleanup(journal.close)
                target = FakeTarget()
                coordinator = IntegrationCoordinator(journal, target, clock=lambda: NOW)
                prepared = coordinator.prepare(
                    round_id=f"round-{field}-drift",
                    target_ref="main",
                    expected_target=BASE,
                    proposed_target=PROPOSED,
                    candidates=self.candidates,
                    idempotency_key=f"prepare-{field}-drift",
                    authorization=self.authorization,
                    plan_bytes=PLAN_BYTES,
                    standard_bytes=STANDARD,
                    wave_manifest_bytes=WAVE.canonical_bytes(),
                    candidate_journal=self.candidate_journal,
                )
                observations = target.observe_calls
                target.adapter_binding = replace(
                    target.adapter_binding, **{field: value}
                )
                with self.assertRaisesRegex(
                    IntegrationError, "target adapter was substituted"
                ):
                    coordinator.commit(
                        prepared.transaction_id,
                        idempotency_key=f"commit-{field}-drift",
                        authorization=self.authorization,
                    )
                self.assertEqual(observations, target.observe_calls)
                self.assertEqual(0, target.calls)

        with self.assertRaises(ContractViolation):
            replace(self.target.adapter_binding, interface="integration target")
        with self.assertRaises(ContractViolation):
            replace(self.target.adapter_binding, version="v 1")

    def test_policy_plan_candidate_and_digest_substitution_fail_closed(self) -> None:
        cases = (
            ({"proposed_target": UNKNOWN}, "proposed integration target"),
            (
                {
                    "plan_bytes": replace(
                        PLAN,
                        integration=replace(
                            PLAN.integration, target="refs/heads/other"
                        ),
                    ).canonical_bytes()
                },
                "plan bytes were substituted",
            ),
            (
                {"validation_receipt_digest": OTHER_DIGEST},
                "caller-supplied integration evidence",
            ),
            (
                {"integration_policy_digest": OTHER_DIGEST},
                "caller-supplied integration evidence",
            ),
            (
                {"lease_digest": OTHER_DIGEST},
                "caller-supplied integration evidence",
            ),
            (
                {"manifest_digest": DIGEST},
                "caller-supplied wave-manifest",
            ),
            ({"transaction_id": "caller-chosen"}, "transaction id"),
        )
        for overrides, error in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(IntegrationError, error):
                    self.prepare(**overrides)
        self.assertEqual(0, self.target.calls)
        self.assertEqual(0, self.target.observe_calls)

    def test_malformed_candidate_fails_before_target_observation(self) -> None:
        unready = replace(self.candidates[0], state=WaveState.VERIFYING)
        with self.assertRaisesRegex(IntegrationError, "not integration-ready"):
            self.prepare(candidates=(unready, self.candidates[1]))
        self.assertEqual(0, self.target.observe_calls)
        self.assertEqual(0, self.target.calls)

    def test_noncanonical_or_unbound_plan_contract_fails_before_target(self) -> None:
        noncanonical = PLAN_BYTES.replace(b"{", b"{ ", 1)
        wrong_compiler = replace(
            PLAN,
            standard=replace(PLAN.standard, package_digest=OTHER_DIGEST),
        )
        incomplete_governance = replace(PLAN, nodes=PLAN.nodes[:-1])
        cases = (
            (
                {
                    "plan_bytes": noncanonical,
                    "authorization": authorized_one_run_fixture(
                        noncanonical, nonce_seed="noncanonical-integration-plan"
                    ),
                },
                "canonical form",
            ),
            ({"standard_bytes": b"substituted standard\n"}, "raw digest"),
            (
                {
                    "plan_bytes": wrong_compiler.canonical_bytes(),
                    "authorization": authorized_one_run_fixture(
                        wrong_compiler.canonical_bytes(),
                        nonce_seed="wrong-integration-compiler",
                    ),
                },
                "package identity",
            ),
            (
                {
                    "plan_bytes": incomplete_governance.canonical_bytes(),
                    "authorization": authorized_one_run_fixture(
                        incomplete_governance.canonical_bytes(),
                        nonce_seed="incomplete-integration-governance",
                    ),
                },
                "omits required specialist",
            ),
        )
        for overrides, error in cases:
            with self.subTest(error=error):
                with self.assertRaisesRegex(IntegrationError, error):
                    self.prepare(**overrides)
        self.assertEqual(0, self.target.observe_calls)
        self.assertEqual(0, self.target.calls)

    def test_reversed_caller_order_fails_before_target_observation(self) -> None:
        with self.assertRaisesRegex(
            IntegrationError, "caller-supplied integration order"
        ):
            self.prepare(integration_order=("node-b", "node-a"))
        self.assertEqual(0, self.target.observe_calls)
        self.assertEqual(0, self.target.calls)

        fabricated = replace(
            self.candidates[0], candidate_id="candidate-fabricated-node-a"
        )
        with self.assertRaisesRegex(IntegrationError, "not present in the supplied"):
            self.prepare(candidates=(fabricated, self.candidates[1]))
        self.assertEqual(0, self.target.observe_calls)
        self.assertEqual(0, self.target.calls)

    def test_wave_manifest_self_hash_is_integrity_not_authority(self) -> None:
        alternate_wave = replace(
            WAVE,
            nodes=tuple(reversed(WAVE.nodes)),
            manifest_digest="",
        )
        alternate_journal = CandidateStateJournal()
        self.addCleanup(alternate_journal.close)
        alternate_candidates = (
            candidate(alternate_journal, "node-b", "6", wave=alternate_wave),
            candidate(alternate_journal, "node-a", "4", wave=alternate_wave),
        )

        prepared = self.prepare(
            wave_manifest_bytes=alternate_wave.canonical_bytes(),
            candidate_journal=alternate_journal,
            candidates=alternate_candidates,
        )

        self.assertEqual(
            ["node-b", "node-a"],
            [item.node_id for item in prepared.contributions],
        )
        self.assertEqual(
            self.authorization.candidate_commit, prepared.proposed_target.commit
        )
        self.assertEqual(
            self.authorization.candidate_tree, prepared.proposed_target.tree
        )

    def test_public_journal_cannot_inject_forged_prepared_transaction(self) -> None:
        prepared = self.prepare()
        protected_policy_digest = canonical_digest(
            replace(PLAN.integration, protected_target=True).to_document()
        )
        forged = replace(
            prepared,
            transaction_id="forged-transaction",
            round_id="forged-round",
            target_ref="protected",
            expected_target=UNKNOWN,
            integration_policy_digest=protected_policy_digest,
        )
        challenged_journal = IntegrationJournal()
        self.addCleanup(challenged_journal.close)
        challenged_target = FakeTarget()
        challenged_coordinator = IntegrationCoordinator(
            challenged_journal, challenged_target, clock=lambda: NOW
        )

        with self.assertRaisesRegex(IntegrationError, "trusted journal path"):
            challenged_journal.append(forged, idempotency_key="forged-prepare")
        with self.assertRaises(sqlite3.DatabaseError):
            challenged_journal.connection.execute(
                """
                INSERT INTO integration_preparations(
                    transaction_id, prepared_transaction_digest
                ) VALUES(?,?)
                """,
                (forged.transaction_id, forged.intent_digest),
            )
        with self.assertRaisesRegex(
            IntegrationError, "unknown integration transaction"
        ):
            challenged_coordinator.commit(
                forged.transaction_id,
                idempotency_key="forged-commit",
                authorization=self.authorization,
            )
        self.assertEqual(0, challenged_target.observe_calls)
        self.assertEqual(0, challenged_target.calls)

    def test_protected_target_is_never_authorized_by_one_run_capability(self) -> None:
        protected_bytes = replace(
            PLAN,
            integration=replace(PLAN.integration, protected_target=True),
        ).canonical_bytes()
        protected_authorization = authorized_one_run_fixture(
            protected_bytes, nonce_seed="protected-integration-run"
        )
        with self.assertRaisesRegex(IntegrationError, "does not authorize protected"):
            self.prepare(
                plan_bytes=protected_bytes,
                authorization=protected_authorization,
            )
        self.assertIsNone(self.journal.for_round("round-1"))
        self.assertEqual(0, self.target.calls)
        self.assertEqual(0, self.target.observe_calls)

    def test_target_reported_protection_overrides_unprotected_plan(self) -> None:
        self.target.adapter_binding = replace(
            self.target.adapter_binding, protected_target=True
        )

        with self.assertRaisesRegex(IntegrationError, "protected or protection is unknown"):
            self.prepare()

        self.assertEqual(0, self.target.calls)
        self.assertEqual(0, self.target.observe_calls)

    def test_signed_plan_without_external_effect_authority_is_denied(self) -> None:
        denied_plan = replace(
            PLAN,
            authority=tuple(
                replace(item, external_effects=False) for item in PLAN.authority
            ),
        )
        denied_bytes = denied_plan.canonical_bytes()
        authorization = authorized_one_run_fixture(
            denied_bytes, nonce_seed="external-integration-denial"
        )
        denied_wave = replace(
            WAVE, plan_digest=denied_plan.digest(), manifest_digest=""
        )
        denied_authority_digest = canonical_digest(
            [item.to_document() for item in denied_plan.authority]
        )
        denied_journal = CandidateStateJournal()
        self.addCleanup(denied_journal.close)
        denied_candidates = (
            candidate(
                denied_journal,
                "node-a",
                "4",
                wave=denied_wave,
                authority_digest=denied_authority_digest,
            ),
            candidate(
                denied_journal,
                "node-b",
                "6",
                wave=denied_wave,
                authority_digest=denied_authority_digest,
            ),
        )
        with self.assertRaisesRegex(IntegrationError, "denies external integration"):
            self.prepare(
                plan_bytes=denied_bytes,
                authorization=authorization,
                wave_manifest_bytes=denied_wave.canonical_bytes(),
                candidate_journal=denied_journal,
                candidates=denied_candidates,
            )
        self.assertEqual(0, self.target.calls)
        self.assertEqual(0, self.target.observe_calls)

    def test_local_reversible_capability_cannot_authorize_external_cas(self) -> None:
        local_only_plan = replace(
            PLAN,
            capabilities=tuple(
                replace(item, effect_class="local-reversible")
                if item.operation == "integrate"
                else item
                for item in PLAN.capabilities
            ),
        )
        plan_bytes = local_only_plan.canonical_bytes()
        authorization = authorized_one_run_fixture(
            plan_bytes, nonce_seed="local-only-integration-capability"
        )
        wave = replace(
            WAVE, plan_digest=local_only_plan.digest(), manifest_digest=""
        )
        candidate_journal = CandidateStateJournal()
        self.addCleanup(candidate_journal.close)
        candidates = (
            candidate(candidate_journal, "node-a", "4", wave=wave),
            candidate(candidate_journal, "node-b", "6", wave=wave),
        )

        with self.assertRaisesRegex(IntegrationError, "denies external integration"):
            self.prepare(
                authorization=authorization,
                plan_bytes=plan_bytes,
                wave_manifest_bytes=wave.canonical_bytes(),
                candidate_journal=candidate_journal,
                candidates=candidates,
            )

        self.assertEqual(0, self.target.observe_calls)
        self.assertEqual(0, self.target.calls)

    def test_checked_v4_plan_remains_inert_at_integration_boundary(self) -> None:
        plan_bytes = Path(
            "docs/execution/dags/generic-hive-mind-product-v4/plan.json"
        ).read_bytes()
        plan = PortablePlanBundle.from_bytes(plan_bytes)
        repository = plan.subject.repository
        assert repository is not None
        expected = CandidateIdentity(
            repository.commit, repository.tree, plan.subject.subject_id
        )
        proposed = CandidateIdentity("6" * 40, "7" * 40, plan.subject.subject_id)
        candidates = tuple(
            replace(
                item,
                identity=CandidateIdentity(
                    item.identity.commit,
                    item.identity.tree,
                    plan.subject.subject_id,
                ),
            )
            for item in self.candidates
            if item.identity is not None
        )
        target = FakeTarget()
        target.identity = expected
        coordinator = IntegrationCoordinator(
            IntegrationJournal(), target, clock=lambda: NOW
        )
        self.addCleanup(coordinator.journal.close)
        authorization = authorized_one_run_fixture(
            plan_bytes, nonce_seed="checked-v4-integration-denial"
        )
        with self.assertRaisesRegex(IntegrationError, "does not authorize protected"):
            coordinator.prepare(
                round_id="round-checked-v4",
                target_ref="main",
                expected_target=expected,
                proposed_target=proposed,
                candidates=candidates,
                idempotency_key="prepare-checked-v4",
                authorization=authorization,
                plan_bytes=plan_bytes,
                standard_bytes=Path(
                    "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
                ).read_bytes(),
            )
        self.assertEqual(0, target.calls)


if __name__ == "__main__":
    unittest.main()
