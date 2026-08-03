from __future__ import annotations

import tempfile
import threading
import unittest
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

    def test_tampered_payload_is_rejected_before_a_lease_is_issued(self) -> None:
        job = self._enqueue()
        with self.scheduler._connection:
            self.scheduler._connection.execute(
                "UPDATE jobs SET payload_json=? WHERE id=?",
                ('{"mission_id":"attacker","value":"attacker"}', job.id),
            )
        with self.assertRaisesRegex(SchedulerIntegrityError, "no longer binds"):
            self.scheduler.claim("worker")
        state = self.scheduler._connection.execute(
            "SELECT state FROM jobs WHERE id=?", (job.id,)
        ).fetchone()["state"]
        self.assertEqual(state, "ready")


if __name__ == "__main__":
    unittest.main()
