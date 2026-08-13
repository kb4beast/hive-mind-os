"""Cross-boundary durability qualification for the canonical mission runtime.

Every "crash" in this suite is a real process boundary simulation: stop
cooperating mid-protocol, close the SQLite-backed object, and construct a fresh
instance over the same file. Nothing is mocked away, no assertion is relaxed to
make a boundary pass, and no wall clock is consulted.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.authority import (
    AuthorityDenied,
    AuthorityRegistry,
    CapabilityToken,
)
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import Budget, ConstraintEnvelope, EffectIntent
from hive_mind_os.brain_kernel.effect_outbox import (
    DurableEffectOutbox,
    EffectReconciliationRequired,
)
from hive_mind_os.brain_kernel.effects import (
    EffectGateway,
    build_effect_receipt,
    sealed_intent,
)
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.mission_runtime import MissionRuntime
from hive_mind_os.brain_kernel.projection import empty_state, reduce_event, state_digest
from hive_mind_os.brain_kernel.store import (
    DATABASE_FILENAME,
    KernelIntegrityError,
    KernelStore,
)
from hive_mind_os.brain_kernel.workers import KernelWorker, ScopeLockStore
from hive_mind_os.cortex.repository.mission_adapter import (
    build_local_mission_environment,
)
from hive_mind_os.scheduler import ManualClock, Scheduler, StaleLeaseError

DIGEST = "sha256:" + "0" * 64
TIME = "2030-01-01T00:00:00Z"
LATER = "2030-01-01T00:00:01Z"
MISSION = "MISSION-durable"
WORK = "WORK-durable"


def _envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-durable",
        MISSION,
        WORK,
        None,
        "builder",
        "R1",
        ("write",),
        ("push", "merge", "deploy"),
        ("workspace",),
        ("workspace",),
        (),
        (),
        (),
        (),
        Budget(30, 0, 0, 0, 0, 0, 1, 1),
        "2030-01-02T00:00:00Z",
        DIGEST,
        DIGEST,
    ).sealed()


AUTH = _envelope().digest_value


def _intent(*, key: str = DIGEST, digest: str = DIGEST) -> EffectIntent:
    return sealed_intent(EffectIntent(
        MISSION,
        WORK,
        "ATTEMPT-durable",
        "builder-1",
        "builder",
        "write",
        "R1",
        "fake",
        "workspace/result.txt",
        DIGEST,
        key,
        AUTH,
        ("workspace exists",),
        "remove workspace/result.txt",
        "POLICY-durable",
        digest,
    ))


def _forged_token(envelope_digest: str, action: str, target: str) -> CapabilityToken:
    """The A5-F10 forgery, written past the constructor's issuance check.

    Re-declared locally on purpose; sibling test modules are never imported.
    """

    forged = object.__new__(CapabilityToken)
    values = (
        envelope_digest,
        action,
        target,
        canonical_digest(
            {"envelope": envelope_digest, "action": action, "target": target}
        ),
        "",
    )
    for name, value in zip(CapabilityToken.__slots__, values):
        object.__setattr__(forged, name, value)
    return forged


def event(
    event_id: str,
    event_type: str,
    previous: str | None,
    payload: dict[str, str] | None = None,
    work_id: str | None = None,
) -> KernelEvent:
    return KernelEvent(
        event_id,
        MISSION,
        event_type,
        "actor",
        TIME,
        payload or {},
        work_id=work_id,
        previous_digest=previous,
    )


def _reopen(path: Path) -> KernelStore:
    """Restart the kernel process: a fresh store over the same durable file."""

    return KernelStore(path)


def _replay(store: KernelStore) -> dict:
    """Fold the pure reducer over the verified event spine, from nothing."""

    state = empty_state()
    for record in store.events():
        state = reduce_event(state, record)
    return state


class _DurableCase(unittest.TestCase):
    """Shared temp-directory and handle discipline (Windows cannot unlink open files)."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        # Registered first, so LIFO cleanup removes the directory only after
        # every store, scheduler, lock store, and raw connection is closed.
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def open_store(self, path: Path) -> KernelStore:
        store = KernelStore(path)
        self.addCleanup(store.close)
        return store

    def raw(self, path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        self.addCleanup(connection.close)
        return connection


class CrashMatrixTests(_DurableCase):
    """Acceptance criteria 1 (resume) and 2 (no duplicated effect or role result)."""

    def setUp(self) -> None:
        super().setUp()
        self.path = self.root / DATABASE_FILENAME
        self.store = self.open_store(self.path)
        self.registry = AuthorityRegistry()
        self.registry.mint_root(
            _envelope(),
            issuer="owner:durability-fixture",
            authority_ref="AUTHORITY-RECORD-durable",
            recorded_at="2026-01-01T00:00:00Z",
        )
        self.token = self.registry.authorize(
            AUTH, "write", "workspace/result.txt", now=TIME
        )

    def test_crash_before_adapter_run_resumes_and_delivers_exactly_once(self) -> None:
        calls: list[str] = []
        intent = _intent()
        outbox = DurableEffectOutbox(
            self.store,
            adapters={"fake": lambda _: calls.append("pre-crash")},
            authority=self.registry,
        )
        outbox.enqueue(intent, self.token)
        entry = self.store.effect_entry(intent_digest=intent.intent_digest)
        assert entry is not None
        self.assertEqual("pending", entry["state"])
        self.assertEqual([], calls)

        # Crash: the intent is durable, the adapter never ran.
        self.store.close()
        resumed = self.open_store(self.path)
        gateway = EffectGateway(resumed, authority=self.registry)
        gateway.register_adapter("fake", lambda _: calls.append("delivered"))
        first = gateway.execute(intent, self.token)
        self.assertEqual("SUCCEEDED", first.status)
        self.assertEqual(["delivered"], calls)

        # Crash again, after the receipt: resume must not redeliver.
        resumed.close()
        second_life = self.open_store(self.path)
        retry = EffectGateway(second_life, authority=self.registry)
        retry.register_adapter("fake", lambda _: calls.append("duplicate"))
        second = retry.execute(intent, self.token)
        self.assertEqual(first, second)
        self.assertEqual(["delivered"], calls)
        entry = second_life.effect_entry(intent_digest=intent.intent_digest)
        assert entry is not None
        self.assertEqual("receipt_recorded", entry["state"])

    def test_a_directly_constructed_outbox_still_consults_the_registry(self) -> None:
        """BIND-1030: constructing the outbox by hand does not skip the boundary."""

        calls: list[str] = []
        escape = sealed_intent(replace(_intent(), target="secrets/keys.txt"))
        forged = _forged_token(AUTH, "write", "secrets/keys.txt")
        outbox = DurableEffectOutbox(
            self.store,
            adapters={"fake": lambda _: calls.append("forged delivery")},
            authority=self.registry,
        )

        for call in (
            lambda: outbox.enqueue(escape, forged),
            lambda: outbox.execute(escape, forged),
        ):
            with self.subTest(call=call):
                with self.assertRaisesRegex(AuthorityDenied, "outside write scope"):
                    call()
        self.assertEqual([], calls)
        self.assertIsNone(self.store.effect_entry(intent_digest=escape.intent_digest))

        # Positive control: the same outbox delivers a token the registry issued.
        honest = _intent()
        self.assertEqual(
            "SUCCEEDED", outbox.execute(honest, self.token).status
        )
        self.assertEqual(["forged delivery"], calls)

    def test_a_reconciliation_witness_is_checked_against_the_registry(self) -> None:
        """BIND-1030: ``reconcile`` adopts a receipt only for an issued token."""

        intent = _intent(
            key=canonical_digest({"key": "reconcile-authority"}),
            digest=canonical_digest({"key": "reconcile-authority"}),
        )
        outbox = DurableEffectOutbox(
            self.store, adapters={"fake": lambda _: None}, authority=self.registry
        )
        outbox.enqueue(intent, self.token)
        receipt = build_effect_receipt(
            intent,
            adapter_identity="fake",
            adapter_version="1",
            started_at=TIME,
            ended_at=LATER,
        )

        # Cheat: a token that binds the stored intent perfectly, but that this
        # registry never issued.  Only the issuance check can tell them apart.
        with self.assertRaisesRegex(AuthorityDenied, "was not issued by this authority"):
            outbox.reconcile(
                intent.intent_digest,
                receipt,
                token=_forged_token(AUTH, "write", "workspace/result.txt"),
            )
        self.assertEqual(
            "pending",
            str(self.store.effect_entry(intent_digest=intent.intent_digest)["state"]),
        )
        # Positive control: the issued token adopts the same receipt.
        self.assertEqual(
            "SUCCEEDED",
            outbox.reconcile(intent.intent_digest, receipt, token=self.token).status,
        )

    def test_crash_during_execution_is_quarantined_not_retried(self) -> None:
        calls: list[str] = []
        intent = _intent(
            key=canonical_digest({"key": "executing"}),
            digest=canonical_digest({"key": "executing-intent"}),
        )
        DurableEffectOutbox(
            self.store, adapters={"fake": lambda _: None}, authority=self.registry
        ).enqueue(intent, self.token)
        # The process dies inside the adapter: claimed, executing, no receipt.
        claimed = self.store.begin_effect(
            intent_digest=intent.intent_digest, recorded_at=TIME
        )
        self.assertEqual("executing", claimed["state"])
        self.store.close()

        resumed = self.open_store(self.path)
        outbox = DurableEffectOutbox(
            resumed,
            adapters={"fake": lambda _: calls.append("blind-retry")},
            authority=self.registry,
        )
        self.assertEqual([intent.intent_digest], outbox.recover())
        entry = resumed.effect_entry(intent_digest=intent.intent_digest)
        assert entry is not None
        self.assertEqual("reconciliation_required", entry["state"])
        with self.assertRaises(EffectReconciliationRequired):
            outbox.execute(intent, self.token)
        self.assertEqual([], calls)

        receipt = build_effect_receipt(
            intent,
            adapter_identity="fake",
            adapter_version="1",
            started_at=TIME,
            ended_at=LATER,
        )
        repaired = outbox.reconcile(
            intent.intent_digest,
            receipt,
            token=self.token,
            evidence={"witness": "durability-qualification"},
        )
        self.assertEqual("SUCCEEDED", repaired.status)
        self.assertEqual(repaired, outbox.execute(intent, self.token))
        self.assertEqual([], calls)

    def test_crash_between_receipt_and_ack_is_idempotent(self) -> None:
        calls: list[str] = []
        intent = _intent(
            key=canonical_digest({"key": "ack"}),
            digest=canonical_digest({"key": "ack-intent"}),
        )
        gateway = EffectGateway(self.store, authority=self.registry)
        gateway.register_adapter("fake", lambda _: calls.append("physical"))
        first = gateway.execute(intent, self.token)
        # The receipt is durable; the acknowledgement to the caller is lost.
        self.store.close()

        resumed = self.open_store(self.path)
        retry = EffectGateway(resumed, authority=self.registry)
        retry.register_adapter("fake", lambda _: calls.append("duplicate"))
        second = retry.execute(intent, self.token)
        self.assertEqual(
            (first.intent_digest, first.receipt_digest, first.status),
            (second.intent_digest, second.receipt_digest, second.status),
        )
        self.assertEqual(["physical"], calls)
        entry = resumed.effect_entry(intent_digest=intent.intent_digest)
        assert entry is not None
        self.assertEqual("receipt_recorded", entry["state"])
        rows = resumed.connection.execute(
            "SELECT receipt_digest FROM effect_receipts WHERE intent_digest=?",
            (intent.intent_digest,),
        ).fetchall()
        self.assertEqual([first.receipt_digest], [str(row[0]) for row in rows])

    def test_event_append_crash_leaves_no_partial_state(self) -> None:
        self.store.append(event("EVENT-1", "mission.created", None))
        head = self.store.events()[-1]["digest"]
        before = self.store.projection()

        legal = event("EVENT-2", "mission.transition", head, {"status": "PLANNING"})
        illegal = event(
            "EVENT-3",
            "mission.transition",
            legal.digest_for(head),
            {"status": "COMPLETED"},
        )
        with self.assertRaises(KernelIntegrityError):
            self.store.append_batch(((legal, None), (illegal, None)))

        self.store.close()
        resumed = self.open_store(self.path)
        self.assertEqual(
            ["EVENT-1"], [record["event_id"] for record in resumed.events()]
        )
        self.assertEqual(before, resumed.projection())
        self.assertEqual(before, resumed.rebuild_projections())
        self.assertEqual(before, _replay(resumed))

    def test_role_result_idempotency_key_prevents_duplicate_acceptance(self) -> None:
        created = event("EVENT-1", "mission.created", None)
        sequence = self.store.append(created, idempotency_key="KEY-1")
        head = self.store.events()[-1]["digest"]
        self.store.close()

        resumed = self.open_store(self.path)
        # The exact same accepted fact, replayed by a resuming caller.
        self.assertEqual(
            sequence, resumed.append(created, idempotency_key="KEY-1")
        )
        self.assertEqual(1, len(resumed.events()))
        # A different fact under the same key is a duplicate acceptance attempt.
        competing = event(
            "EVENT-2", "mission.transition", head, {"status": "PLANNING"}
        )
        with self.assertRaises(KernelIntegrityError):
            resumed.append(competing, idempotency_key="KEY-1")
        self.assertEqual(1, len(resumed.events()))


class LeaseRecoveryTests(_DurableCase):
    """Acceptance criterion 3 (stale leases) and criterion 1 (resume)."""

    def setUp(self) -> None:
        super().setUp()
        self.clock = ManualClock()
        self.scheduler = Scheduler(
            self.root, clock=self.clock, lease_seconds=30.0, backoff_seconds=1.0
        )
        self.addCleanup(self.scheduler.close)

    def locks(self) -> ScopeLockStore:
        store = ScopeLockStore(self.root)
        self.addCleanup(store.close)
        return store

    def test_worker_crash_releases_lease_after_expiry_and_second_worker_resumes(
        self,
    ) -> None:
        job = self.scheduler.enqueue(
            "kernel-work", {"work_id": WORK}, mission_id=MISSION
        )
        dead = self.scheduler.claim("worker-a")
        assert dead is not None
        self.assertEqual(1, dead.attempts)
        # worker-a crashes here: it never completes, fails, or heartbeats.
        self.assertIsNone(self.scheduler.claim("worker-b"))

        self.clock.advance(31)
        resumed = self.scheduler.claim("worker-b")
        assert resumed is not None
        self.assertEqual(job.id, resumed.id)
        self.assertEqual(2, resumed.attempts)
        self.assertEqual("worker-b", resumed.lease_owner)
        assert dead.lease_token is not None
        with self.assertRaises(StaleLeaseError):
            self.scheduler.complete(job.id, dead.lease_token, mission_id=MISSION)
        self.assertEqual("leased", self.scheduler.get(job.id).state)

    def test_scheduler_restart_preserves_lease_and_job_state(self) -> None:
        job = self.scheduler.enqueue(
            "kernel-work", {"work_id": WORK}, mission_id=MISSION
        )
        claimed = self.scheduler.claim("worker-a")
        assert claimed is not None
        # Crash: the scheduler process dies while the lease is live.
        self.scheduler.close()

        restarted = Scheduler(
            self.root, clock=self.clock, lease_seconds=30.0, backoff_seconds=1.0
        )
        self.addCleanup(restarted.close)
        survived = restarted.get(job.id)
        self.assertEqual("leased", survived.state)
        self.assertEqual(claimed.lease_token, survived.lease_token)
        self.assertEqual("worker-a", survived.lease_owner)
        self.assertEqual(1, survived.attempts)
        self.assertIsNone(restarted.claim("worker-b"))

        self.clock.advance(31)
        reclaimed = restarted.claim("worker-b")
        assert reclaimed is not None
        self.assertEqual(job.id, reclaimed.id)
        self.assertEqual(2, reclaimed.attempts)

    def test_kernel_worker_crash_mid_job_lapses_lock_and_is_reclaimable(self) -> None:
        locks = self.locks()
        scope = ("src/durable.py",)

        def crashing(_job: object) -> None:
            raise RuntimeError("injected crash")

        crashed = KernelWorker(self.scheduler, locks, "worker-a", crashing)
        job = crashed.enqueue(MISSION, WORK, scope)
        self.assertTrue(crashed.run_once())

        after = self.scheduler.get(job.id)
        self.assertEqual("ready", after.state)
        self.assertEqual(1, after.attempts)
        self.assertIn("injected crash", str(after.last_error))
        # The crashed worker's write-scope lock did not survive it.
        self.assertTrue(locks.acquire(scope, "probe", self.clock.now(), 5.0))
        locks.release("probe")

        self.clock.advance(2)  # clear the retry backoff (backoff_seconds=1.0)
        seen: list[str] = []
        healthy = KernelWorker(
            self.scheduler,
            locks,
            "worker-b",
            lambda item: seen.append(str(item.payload["work_id"])),
        )
        self.assertTrue(healthy.run_once())
        self.assertEqual([WORK], seen)
        drained = self.scheduler.get(job.id)
        self.assertEqual("done", drained.state)
        self.assertEqual(2, drained.attempts)

    def test_kernel_worker_success_records_awaiting_verification_trail(self) -> None:
        locks = self.locks()
        store = self.open_store(self.root / DATABASE_FILENAME)
        store.append(event("EVENT-1", "mission.created", None))
        head = store.events()[-1]["digest"]
        store.append(event("EVENT-2", "work.created", head, work_id=WORK))

        worker = KernelWorker(
            self.scheduler, locks, "worker-a", lambda _job: None, store=store
        )
        job = worker.enqueue(MISSION, WORK, ("src/durable.py",))
        self.assertTrue(worker.run_once())
        self.assertEqual("done", self.scheduler.get(job.id).state)
        self.assertEqual(
            ["READY", "LEASED", "RUNNING", "AWAITING_VERIFICATION"],
            [
                record["payload"]["status"]
                for record in store.events()
                if record["event_type"] == "work.transition"
            ],
        )
        self.assertEqual(
            "AWAITING_VERIFICATION", store.projection()["work"][WORK]["status"]
        )

    def test_stale_scope_lock_expires_by_ttl(self) -> None:
        locks = self.locks()
        self.assertTrue(locks.acquire(("a.py",), "dead", 0.0, 10.0))
        self.assertFalse(locks.acquire(("a.py",), "live", 5.0, 10.0))
        self.assertTrue(locks.acquire(("a.py",), "live", 11.0, 10.0))

    def test_dead_letter_after_exhausted_crashes(self) -> None:
        job = self.scheduler.enqueue(
            "kernel-work", {"work_id": WORK}, max_attempts=2, mission_id=MISSION
        )
        for _ in range(2):
            claimed = self.scheduler.claim("worker-a")
            self.assertIsNotNone(claimed)
            self.clock.advance(31)  # the worker crashes; the lease simply expires
        self.assertIsNone(self.scheduler.claim("worker-b"))
        exhausted = self.scheduler.get(job.id)
        self.assertEqual("dead-letter", exhausted.state)
        self.assertEqual(2, exhausted.attempts)


class SnapshotCorruptionTests(_DurableCase):
    """Acceptance criterion 3 (corrupt snapshots) and criterion 1 (replay)."""

    def setUp(self) -> None:
        super().setUp()
        self.path = self.root / DATABASE_FILENAME

    def seed(self) -> dict:
        store = self.open_store(self.path)
        store.append(event("EVENT-1", "mission.created", None))
        head = store.events()[-1]["digest"]
        store.append(
            event("EVENT-2", "mission.transition", head, {"status": "PLANNING"}),
            expected_sequence=1,
        )
        truth = store.projection()
        store.write_snapshot()
        store.close()
        return truth

    def test_corrupt_snapshot_after_restart_is_rebuilt_from_events(self) -> None:
        truth = self.seed()
        connection = self.raw(self.path)
        connection.execute(
            "UPDATE snapshots SET state_json=?", ('{"missions":{},"work":{}}',)
        )
        connection.commit()
        connection.close()

        resumed = self.open_store(self.path)
        self.assertEqual(truth, resumed.load_snapshot())
        self.assertEqual(truth, resumed.projection())
        self.assertEqual(truth, _replay(resumed))
        repaired = resumed.connection.execute(
            "SELECT state_digest FROM snapshots ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(state_digest(truth), str(repaired[0]))

    def test_paired_snapshot_tamper_survives_restart(self) -> None:
        truth = self.seed()
        lie = {"missions": {MISSION: "COMPLETED"}, "work": {}}
        self.assertNotEqual(truth, lie)
        connection = self.raw(self.path)
        connection.execute(
            "UPDATE snapshots SET state_json=?, state_digest=?",
            (json.dumps(lie), state_digest(lie)),
        )
        connection.commit()
        connection.close()

        resumed = self.open_store(self.path)
        # The tampered pair is internally consistent; replay still beats it.
        self.assertEqual(truth, resumed.load_snapshot())
        self.assertEqual(truth, _replay(resumed))

    def test_corrupt_event_chain_is_quarantined_at_open(self) -> None:
        self.seed()
        connection = self.raw(self.path)
        connection.execute("DROP TRIGGER kernel_events_no_update")
        connection.execute(
            "UPDATE events SET payload_json=? WHERE event_id='EVENT-2'",
            ('{"status":"HACKED"}',),
        )
        connection.commit()
        connection.close()

        with self.assertRaises(KernelIntegrityError):
            KernelStore(self.path)
        read_only = KernelStore(self.path, read_only=True)
        self.addCleanup(read_only.close)
        with self.assertRaises(KernelIntegrityError):
            read_only.events()

    def test_read_only_open_never_mutates(self) -> None:
        truth = self.seed()
        read_only = KernelStore(self.path, read_only=True)
        self.addCleanup(read_only.close)
        self.assertEqual(truth, read_only.projection())
        head = read_only.events()[-1]["digest"]
        message = "read-only kernel store cannot be mutated"
        with self.assertRaisesRegex(KernelIntegrityError, message):
            read_only.write_snapshot()
        with self.assertRaisesRegex(KernelIntegrityError, message):
            read_only.rebuild_projections()
        with self.assertRaisesRegex(KernelIntegrityError, message):
            read_only.append(
                event("EVENT-3", "mission.transition", head, {"status": "READY"})
            )


class MissionRuntimeReplayTests(_DurableCase):
    """Bind the crash matrix to the canonical MISSION-400 runtime (criterion 1).

    ``build_local_mission_environment`` accepts a caller-supplied ``KernelStore``,
    so the canonical runtime runs against an on-disk database this test owns and
    can close, reopen, and replay.
    """

    def setUp(self) -> None:
        super().setUp()
        self.path = self.root / "kernel.sqlite3"
        store = self.open_store(self.path)
        self.environment = build_local_mission_environment(
            self.root, mission_suffix="durable", store=store
        )
        self.receipt = MissionRuntime(store).run(
            self.environment.config, self.environment.bindings
        )
        self.mission_id = self.environment.config.mission_id
        self.before_events = [record["digest"] for record in store.events()]
        self.before_status = store.status(self.mission_id)
        self.before_projection = store.projection()
        # Crash the mission process with the mission already complete.
        store.close()
        self.resumed = self.open_store(self.path)

    def test_completed_mission_reopens_from_append_only_state(self) -> None:
        self.assertEqual("COMPLETED", self.before_status["status"])
        self.assertEqual(
            self.before_events,
            [record["digest"] for record in self.resumed.events()],
        )
        self.assertEqual(self.before_status, self.resumed.status(self.mission_id))
        self.assertEqual(self.before_projection, self.resumed.projection())
        self.assertEqual(
            self.receipt.projection_digest,
            canonical_digest(self.resumed.projection()),
        )
        self.assertEqual(
            self.receipt.event_head_digest, self.resumed.events()[-1]["digest"]
        )

    def test_reopened_replay_is_deterministic(self) -> None:
        replayed = _replay(self.resumed)
        rebuilt = self.resumed.rebuild_projections()
        snapshot = self.resumed.load_snapshot()
        # Every derived view that carries the full reduced state agrees with a
        # cold fold of the pure reducer over the verified spine.
        self.assertEqual(replayed, rebuilt)
        self.assertEqual(replayed, snapshot)
        self.assertEqual(state_digest(replayed), state_digest(rebuilt))
        # The materialized read model is a projection OF that state: it carries
        # exactly the mission and work statuses, and nothing else. (The full
        # reduced state additionally accumulates evaluation digests that the
        # materialized tables never rehydrate -- see mission_runtime.py:367-370.)
        self.assertEqual(
            replayed["missions"], self.resumed.projection()["missions"]
        )
        self.assertEqual(
            {work_id: entry["status"] for work_id, entry in replayed["work"].items()},
            {
                work_id: entry["status"]
                for work_id, entry in self.resumed.projection()["work"].items()
            },
        )
        self.assertTrue(replayed["work"])
        self.assertEqual(
            {"INTEGRATED"}, {entry["status"] for entry in replayed["work"].values()}
        )

    def test_resume_replay_appends_no_duplicate_events(self) -> None:
        runtime = MissionRuntime(self.resumed)
        directories = self.environment.bundle_directories
        evidence = runtime.replay(self.mission_id, bundle_directories=directories)
        self.assertEqual(self.receipt.event_head_digest, evidence.event_head_digest)
        self.assertEqual(
            self.receipt.closeout.report_digest, evidence.closeout_report_digest
        )
        self.assertEqual(evidence.projection_digest, evidence.rebuilt_projection_digest)
        self.assertEqual(len(self.before_events), len(self.resumed.events()))
        # A second resume is equally free of side effects.
        again = runtime.replay(self.mission_id, bundle_directories=directories)
        self.assertEqual(evidence, again)
        self.assertEqual(len(self.before_events), len(self.resumed.events()))

    def test_builder_effect_is_not_redelivered_after_restart(self) -> None:
        binding = self.environment.bindings.builder_effect
        calls: list[str] = []
        gateway = EffectGateway(self.resumed, authority=binding.registry)
        gateway.register_adapter(
            binding.intent.target_adapter, lambda _: calls.append("duplicate")
        )
        token = binding.registry.authorize(
            binding.envelope_digest,
            binding.intent.action,
            binding.intent.target,
            now=binding.authorization_time,
        )
        result = gateway.execute(binding.intent, token)
        self.assertEqual([], calls)
        self.assertEqual(
            list(self.receipt.effect_receipt_digests), [result.receipt_digest]
        )
        rows = self.resumed.connection.execute(
            "SELECT receipt_digest FROM effect_receipts WHERE intent_digest=?",
            (binding.intent.intent_digest,),
        ).fetchall()
        self.assertEqual([result.receipt_digest], [str(row[0]) for row in rows])


if __name__ == "__main__":
    unittest.main()
