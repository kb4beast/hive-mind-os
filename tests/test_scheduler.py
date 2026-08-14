from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from hashlib import sha256
from pathlib import Path

from hive_mind_os.scheduler import (
    ManualClock,
    Scheduler,
    SchedulerIntegrityError,
    StaleLeaseError,
)


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.clock = ManualClock(100.0)
        self.scheduler = Scheduler(
            self.root,
            clock=self.clock,
            lease_seconds=10,
            backoff_seconds=2,
        )

    def tearDown(self) -> None:
        self.scheduler.close()
        self.temporary.cleanup()

    def _enqueue(self, suffix: str = "one", max_attempts: int = 3):
        return self.scheduler.enqueue(
            "test",
            {"mission_id": f"mission-{suffix}", "value": suffix},
            max_attempts=max_attempts,
            mission_id=f"mission-{suffix}",
        )

    def test_contended_claim_has_exactly_one_winner(self) -> None:
        self._enqueue()
        barrier = threading.Barrier(2)
        winners = []

        def claim(owner: str) -> None:
            queue = Scheduler(self.root, clock=self.clock, lease_seconds=10)
            try:
                barrier.wait()
                winners.append(queue.claim(owner))
            finally:
                queue.close()

        threads = [
            threading.Thread(target=claim, args=(f"worker-{index}",))
            for index in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(job is not None for job in winners), 1)

    def test_expired_lease_reclaims_and_rejects_late_completion(self) -> None:
        self._enqueue()
        first = self.scheduler.claim("first")
        assert first is not None and first.lease_token is not None
        self.clock.advance(11)
        second = self.scheduler.claim("second")
        assert second is not None and second.lease_token is not None
        self.assertEqual(second.id, first.id)
        with self.assertRaises(StaleLeaseError):
            self.scheduler.complete(
                first.id,
                first.lease_token,
                mission_id="mission-one",
            )
        completed = self.scheduler.complete(
            second.id,
            second.lease_token,
            mission_id="mission-one",
        )
        self.assertEqual(completed.state, "done")

    def test_expired_lease_rejects_completion_before_reclaim(self) -> None:
        self._enqueue()
        claimed = self.scheduler.claim("worker")
        assert claimed is not None and claimed.lease_token is not None
        self.clock.advance(11)
        with self.assertRaises(StaleLeaseError):
            self.scheduler.complete(
                claimed.id,
                claimed.lease_token,
                mission_id="late-success",
            )
        self.assertEqual(self.scheduler.get(claimed.id).state, "leased")

    def test_expired_lease_rejects_failure_before_reclaim(self) -> None:
        self._enqueue()
        claimed = self.scheduler.claim("worker")
        assert claimed is not None and claimed.lease_token is not None
        self.clock.advance(11)
        with self.assertRaises(StaleLeaseError):
            self.scheduler.fail(
                claimed.id,
                claimed.lease_token,
                "late failure",
                mission_id="late-failure",
            )
        self.assertEqual(self.scheduler.get(claimed.id).state, "leased")

    def test_heartbeat_extends_lease(self) -> None:
        self._enqueue()
        job = self.scheduler.claim("worker")
        assert job is not None and job.lease_token is not None
        self.clock.advance(9)
        extended = self.scheduler.heartbeat(job.id, job.lease_token)
        self.clock.advance(2)
        self.assertIsNone(self.scheduler.claim("competitor"))
        self.assertEqual(extended.lease_expiry, 119.0)

    def test_retry_backoff_and_dead_letter_ladder(self) -> None:
        self._enqueue(max_attempts=2)
        first = self.scheduler.claim("worker")
        assert first is not None and first.lease_token is not None
        retry = self.scheduler.fail(
            first.id,
            first.lease_token,
            "first failure",
            mission_id="mission-one",
        )
        self.assertEqual(retry.state, "ready")
        self.assertIsNone(self.scheduler.claim("too-early"))
        self.clock.advance(2)
        second = self.scheduler.claim("worker")
        assert second is not None and second.lease_token is not None
        dead = self.scheduler.fail(
            second.id,
            second.lease_token,
            "terminal failure",
            mission_id="mission-one",
        )
        self.assertEqual(dead.state, "dead-letter")
        self.assertEqual(dead.mission_id, "mission-one")
        self.assertEqual(dead.attempts, 2)

    def test_expired_final_attempt_is_dead_lettered(self) -> None:
        job = self._enqueue(max_attempts=1)
        claimed = self.scheduler.claim("crashing-worker")
        assert claimed is not None
        self.clock.advance(11)
        self.assertIsNone(self.scheduler.claim("recovery-worker"))
        dead = self.scheduler.get(job.id)
        self.assertEqual(dead.state, "dead-letter")
        self.assertIn("lease expired", dead.last_error or "")

    def test_enqueue_is_idempotent_by_payload_digest(self) -> None:
        first = self._enqueue()
        second = self._enqueue()
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(self.scheduler.jobs()), 1)

    def test_enqueue_identity_does_not_collapse_two_missions(self) -> None:
        first = self.scheduler.enqueue("test", {"value": "same"}, mission_id="A")
        second = self.scheduler.enqueue("test", {"value": "same"}, mission_id="B")
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(len(self.scheduler.jobs()), 2)

    def test_enqueue_identity_includes_retry_and_start_contract(self) -> None:
        baseline = self.scheduler.enqueue(
            "test", {"value": "same"}, mission_id="A", max_attempts=2
        )
        retries = self.scheduler.enqueue(
            "test", {"value": "same"}, mission_id="A", max_attempts=3
        )
        delayed = self.scheduler.enqueue(
            "test", {"value": "same"}, mission_id="A", max_attempts=2, not_before=200
        )
        self.assertEqual(len({baseline.id, retries.id, delayed.id}), 3)

    def test_claim_can_be_scoped_to_one_mission(self) -> None:
        self.scheduler.enqueue("test", {"value": "A"}, mission_id="A")
        expected = self.scheduler.enqueue("test", {"value": "B"}, mission_id="B")
        claimed = self.scheduler.claim("worker-B", mission_id="B")
        assert claimed is not None
        self.assertEqual(claimed.id, expected.id)

    def test_incoherent_lease_fails_closed_on_restart(self) -> None:
        job = self._enqueue()
        self.scheduler.close()
        connection = sqlite3.connect(self.root / "scheduler.sqlite3")
        connection.execute(
            "UPDATE jobs SET state='leased',attempts=1 WHERE id=?",
            (job.id,),
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(SchedulerIntegrityError, "incomplete lease"):
            Scheduler(self.root, clock=self.clock)

    def test_legacy_identity_migrates_without_duplicate_enqueue(self) -> None:
        job = self._enqueue()
        self.scheduler.close()
        connection = sqlite3.connect(self.root / "scheduler.sqlite3")
        payload_json = connection.execute(
            "SELECT payload_json FROM jobs WHERE id=?",
            (job.id,),
        ).fetchone()[0]
        legacy_digest = "sha256:" + sha256(
            ("test\0" + str(payload_json)).encode("utf-8")
        ).hexdigest()
        connection.execute(
            """
            UPDATE jobs SET enqueue_spec_json=NULL,payload_digest=? WHERE id=?
            """,
            (legacy_digest, job.id),
        )
        connection.commit()
        connection.close()

        self.scheduler = Scheduler(self.root, clock=self.clock)
        retry = self._enqueue()
        self.assertEqual(retry.id, job.id)
        self.assertEqual(len(self.scheduler.jobs()), 1)

    def test_corrupt_legacy_row_is_not_rewritten_during_failed_open(self) -> None:
        job = self._enqueue()
        self.scheduler.close()
        database = self.root / "scheduler.sqlite3"
        connection = sqlite3.connect(database)
        legacy_digest = "sha256:" + "7" * 64
        connection.execute(
            """
            UPDATE jobs
            SET payload_json='{',enqueue_spec_json=NULL,payload_digest=?
            WHERE id=?
            """,
            (legacy_digest, job.id),
        )
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(SchedulerIntegrityError, "payload JSON"):
            Scheduler(self.root, clock=self.clock)
        connection = sqlite3.connect(database)
        stored = connection.execute(
            "SELECT enqueue_spec_json,payload_digest FROM jobs WHERE id=?",
            (job.id,),
        ).fetchone()
        connection.close()
        self.assertEqual(stored, (None, legacy_digest))

    def test_completion_cannot_rebind_a_job_to_another_mission(self) -> None:
        self._enqueue()
        claimed = self.scheduler.claim("worker")
        assert claimed is not None and claimed.lease_token is not None
        with self.assertRaisesRegex(SchedulerIntegrityError, "differs"):
            self.scheduler.complete(
                claimed.id,
                claimed.lease_token,
                mission_id="another-mission",
            )
        self.assertEqual(self.scheduler.get(claimed.id).state, "leased")


if __name__ == "__main__":
    unittest.main()
