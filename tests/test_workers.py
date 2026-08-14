from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fixtures.fixture_repo import build_fixture_repo

from hive_mind_os.scheduler import Scheduler
from hive_mind_os.workers import Worker, serve


class WorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_seeded_process_kill_sweep_reclaims_without_duplicate_effects(self) -> None:
        queue = Scheduler(self.root, lease_seconds=0.15)
        effects = self.root / "effects.sqlite3"
        try:
            for index in range(3):
                queue.enqueue(
                    "test",
                    {
                        "mission_id": f"mission-{index}",
                        "intent_digest": f"sha256:intent-{index}",
                    },
                    mission_id=f"mission-{index}",
                )
                marker = self.root / f"claimed-{index}"
                script = (
                    "import pathlib,sys,time;"
                    "from hive_mind_os.scheduler import Scheduler;"
                    "q=Scheduler(sys.argv[1],lease_seconds=.15);"
                    "j=q.claim('crash-worker');"
                    "pathlib.Path(sys.argv[2]).write_text(j.id if j else 'none');"
                    "time.sleep(30)"
                )
                process = subprocess.Popen(
                    [sys.executable, "-c", script, str(self.root), str(marker)],
                    cwd=Path(__file__).resolve().parents[1] / "src",
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(marker.exists())
                process.terminate() if index < 2 else process.kill()
                process.wait(timeout=5)
                lease_expiry = queue.get(
                    marker.read_text(encoding="utf-8")
                ).lease_expiry
                self.assertIsNotNone(lease_expiry)
                assert lease_expiry is not None
                time.sleep(max(0.01, lease_expiry - time.time() + 0.01))

                def execute(job, state_dir):
                    connection = sqlite3.connect(effects)
                    try:
                        connection.execute(
                            "CREATE TABLE IF NOT EXISTS effects(digest TEXT PRIMARY KEY)"
                        )
                        connection.execute(
                            "INSERT OR IGNORE INTO effects(digest) VALUES(?)",
                            (job.payload["intent_digest"],),
                        )
                        connection.commit()
                    finally:
                        connection.close()
                    return str(job.payload["mission_id"])

                recovery_deadline = time.monotonic() + 5
                while (
                    queue.get(marker.read_text(encoding="utf-8")).state != "done"
                    and time.monotonic() < recovery_deadline
                ):
                    Worker(queue, f"recovery-{index}", executor=execute).run_once()
                    time.sleep(0.01)
                self.assertEqual(
                    queue.get(marker.read_text(encoding="utf-8")).state,
                    "done",
                )
            self.assertTrue(all(job.state == "done" for job in queue.jobs()))
            connection = sqlite3.connect(effects)
            try:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM effects").fetchone()[0],
                    3,
                )
            finally:
                connection.close()
            self.assertTrue(
                all(job.lease_token is None and job.lease_owner is None for job in queue.jobs())
            )
        finally:
            queue.close()

    def test_graceful_shutdown_finishes_inflight_job(self) -> None:
        queue = Scheduler(self.root)
        queue.enqueue(
            "test",
            {"mission_id": "mission-graceful"},
            mission_id="mission-graceful",
        )
        queue.close()
        started = threading.Event()
        release = threading.Event()
        stopping = threading.Event()

        def execute(job, state_dir):
            started.set()
            self.assertTrue(release.wait(5))
            return "mission-graceful"

        result: list[int] = []
        thread = threading.Thread(
            target=lambda: result.append(
                serve(
                    self.root,
                    worker_count=1,
                    once=False,
                    stop_event=stopping,
                    executor=execute,
                )
            )
        )
        thread.start()
        self.assertTrue(started.wait(5))
        stopping.set()
        release.set()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        queue = Scheduler(self.root)
        try:
            self.assertEqual(queue.jobs()[0].state, "done")
            self.assertEqual(result, [0])
        finally:
            queue.close()

    def test_worker_executes_real_durable_mission_with_unique_effect_adoption(self) -> None:
        fixture = build_fixture_repo(self.root)
        mission_id = "M-real-fixture"
        queue = Scheduler(self.root / "state")
        try:
            queue.enqueue(
                "repository-mission",
                {
                    "mission_id": mission_id,
                    "repository": str(fixture.root),
                    "objective": "Fix the failing test",
                    "acceptance_criteria": ["increment(1) returns 2"],
                    "acceptance_specifications": [
                        {
                            "schema_version": 1,
                            "id": "increment-returns-two",
                            "criterion": "increment(1) returns 2",
                            "command": {
                                "argv": [
                                    sys.executable,
                                    "-B",
                                    "-c",
                                    "from tiny_pkg.maths import increment; assert increment(1) == 2",
                                ],
                                "expected": "succeeded",
                            },
                        }
                    ],
                    "backend": "scripted",
                    "scripted_variant": "good",
                    "pin": fixture.commit_two,
                },
                mission_id=mission_id,
            )
            self.assertTrue(Worker(queue, "real-worker").run_once())
            self.assertEqual(queue.jobs()[0].state, "done")
            self.assertTrue((self.root / "state" / "d" / mission_id).is_dir())
            ledger = sqlite3.connect(
                self.root / "state" / "evidence-ledger.sqlite3"
            )
            try:
                rows = ledger.execute(
                    "SELECT payload FROM events WHERE event_type='receipt.recorded'"
                ).fetchall()
                digests = [
                    json.loads(row[0])["action_digest"] for row in rows
                ]
                self.assertEqual(len(digests), len(set(digests)))
            finally:
                ledger.close()
        finally:
            queue.close()

    def test_worker_dead_letters_an_unpinned_repository_mission(self) -> None:
        fixture = build_fixture_repo(self.root)
        queue = Scheduler(self.root / "state")
        try:
            job = queue.enqueue(
                "repository-mission",
                {
                    "mission_id": "M-unpinned",
                    "repository": str(fixture.root),
                    "objective": "Fix the failing test",
                    "acceptance_criteria": [],
                    "acceptance_specifications": [],
                    "backend": "scripted",
                    "scripted_variant": "good",
                    "pin": None,
                },
                max_attempts=1,
                mission_id="M-unpinned",
            )
            self.assertTrue(Worker(queue, "pin-guard").run_once())
            failed = queue.get(job.id)
            self.assertEqual(failed.state, "dead-letter")
            self.assertIn("full immutable pin", failed.last_error or "")
        finally:
            queue.close()


if __name__ == "__main__":
    unittest.main()
