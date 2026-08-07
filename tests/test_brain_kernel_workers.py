from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.brain_kernel.workers import KernelWorker, ScopeLockStore
from hive_mind_os.scheduler import ManualClock, Scheduler


class KernelWorkerTests(unittest.TestCase):
    def test_kernel_events_precede_local_worker_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clock = ManualClock()
            scheduler = Scheduler(root, clock=clock)
            locks = ScopeLockStore(root)
            store = KernelStore(root / "brain-kernel.sqlite3")
            try:
                store.append(KernelEvent("mission", "MISSION-one", "mission.created", "test", "1970-01-01T00:00:00Z", {}))
                head = store.events()[-1]["digest"]
                store.append(KernelEvent("work", "MISSION-one", "work.created", "test", "1970-01-01T00:00:00Z", {}, work_id="WORK-one", previous_digest=head))
                worker = KernelWorker(scheduler, locks, "worker", lambda _: None, store=store)
                job = worker.enqueue("MISSION-one", "WORK-one", ())
                self.assertTrue(worker.run_once())
                self.assertEqual("done", scheduler.get(job.id).state)
                self.assertEqual("AWAITING_VERIFICATION", store.projection()["work"]["WORK-one"]["status"])
            finally:
                store.close()
                locks.close()
                scheduler.close()

    def test_idempotent_enqueue_and_independent_work_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clock = ManualClock()
            scheduler = Scheduler(root, clock=clock)
            locks = ScopeLockStore(root)
            try:
                seen: list[str] = []
                worker = KernelWorker(scheduler, locks, "worker", lambda job: seen.append(job.payload["work_id"]))
                first = worker.enqueue("MISSION-one", "WORK-one", ("src/one.py",))
                self.assertEqual(first.id, worker.enqueue("MISSION-one", "WORK-one", ("src/one.py",)).id)
                worker.enqueue("MISSION-one", "WORK-two", ("docs/readme.md",))
                self.assertTrue(worker.run_once())
                self.assertTrue(worker.run_once())
                self.assertEqual({"WORK-one", "WORK-two"}, set(seen))
            finally:
                locks.close()
                scheduler.close()

    def test_locked_writer_retries_without_execution_and_expired_lock_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clock = ManualClock()
            scheduler = Scheduler(root, clock=clock, backoff_seconds=0)
            locks = ScopeLockStore(root)
            try:
                self.assertTrue(locks.acquire(("src/main.py",), "other", 0, 2))
                seen: list[str] = []
                worker = KernelWorker(scheduler, locks, "worker", lambda job: seen.append(job.payload["work_id"]))
                worker.enqueue("MISSION-one", "WORK-one", ("src/main.py",))
                self.assertTrue(worker.run_once())
                self.assertEqual([], seen)
                clock.advance(3)
                self.assertTrue(worker.run_once())
                self.assertEqual(["WORK-one"], seen)
            finally:
                locks.close()
                scheduler.close()
