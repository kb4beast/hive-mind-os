from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path

from hive_mind_os import cli
from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.scheduler import Scheduler
from tests.fixtures.fixture_repo import build_fixture_repo


class EnqueueCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = build_fixture_repo(self.root / "source")
        self.state_dir = self.root / "state"
        self.kernel_state_dir = self.root / ".hive-mind-kernel-state"

    def specification(self, identifier: str, criterion: str) -> Path:
        path = self.root / f"{identifier}.json"
        specification = AcceptanceSpecification(
            identifier,
            criterion,
            (sys.executable, "-B", "-c", "pass"),
        )
        path.write_text(json.dumps(specification.to_dict()), encoding="utf-8")
        return path

    def enqueue(
        self,
        criteria: list[str],
        specifications: list[Path],
        *,
        pin: str | None = None,
        compatibility_mode: str = "kernel-v1",
    ) -> dict[str, str]:
        output = io.StringIO()
        arguments = Namespace(
            repository=str(self.fixture.root),
            objective="Fix the failing test",
            criterion=criteria,
            acceptance_spec=[str(path) for path in specifications],
            backend="scripted",
            pin=pin,
            max_attempts=3,
            state_dir=str(self.state_dir),
            kernel_state_dir=None,
            compatibility_mode=compatibility_mode,
        )
        with redirect_stdout(output):
            self.assertEqual(cli._run_enqueue(arguments), 0)
        return json.loads(output.getvalue())

    def test_enqueue_pins_and_deduplicates_semantic_work(self) -> None:
        alpha = self.specification("alpha", "criterion a")
        beta = self.specification("beta", "criterion b")
        first = self.enqueue(["criterion b", "criterion a"], [beta, alpha])
        second = self.enqueue(["criterion a", "criterion b"], [alpha, beta])

        self.assertEqual(first["mission_id"], second["mission_id"])
        self.assertEqual(first["job_id"], second["job_id"])
        scheduler = Scheduler(self.state_dir)
        try:
            job = scheduler.get(first["job_id"])
        finally:
            scheduler.close()
        self.assertEqual(job.payload["pin"], self.fixture.commit_two)
        self.assertEqual(job.payload["acceptance_criteria"], ["criterion a", "criterion b"])

        kernel = KernelStore(
            self.kernel_state_dir / "brain-kernel.sqlite3", read_only=True
        )
        try:
            events = kernel.events()
        finally:
            kernel.close()
        self.assertEqual(1, len(events))
        self.assertEqual("mission.created", events[0]["event_type"])
        self.assertEqual(first["mission_id"], events[0]["payload"]["legacy_mission_id"])
        self.assertEqual(first["job_id"], events[0]["payload"]["scheduler_job_id"])
        self.assertEqual("legacy-enqueue-v1", events[0]["payload"]["migration_route"])

    def test_legacy_rollback_mode_reuses_the_existing_job_without_kernel_writes(self) -> None:
        specification = self.specification("alpha", "criterion a")
        migrated = self.enqueue(["criterion a"], [specification])
        rolled_back = self.enqueue(
            ["criterion a"], [specification], compatibility_mode="legacy"
        )

        self.assertEqual(migrated, rolled_back)
        kernel = KernelStore(
            self.kernel_state_dir / "brain-kernel.sqlite3", read_only=True
        )
        try:
            self.assertEqual(1, len(kernel.events()))
        finally:
            kernel.close()

    def test_enqueue_rejects_a_mutable_pin(self) -> None:
        with self.assertRaisesRegex(SystemExit, "full 40-hex"):
            self.enqueue([], [], pin="main")


if __name__ == "__main__":
    unittest.main()
