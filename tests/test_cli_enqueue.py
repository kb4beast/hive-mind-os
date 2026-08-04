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
from hive_mind_os.scheduler import Scheduler
from tests.fixtures.fixture_repo import build_fixture_repo


class EnqueueCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.fixture = build_fixture_repo(self.root / "source")
        self.state_dir = self.root / "state"

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

    def test_enqueue_rejects_a_mutable_pin(self) -> None:
        with self.assertRaisesRegex(SystemExit, "full 40-hex"):
            self.enqueue([], [], pin="main")


if __name__ == "__main__":
    unittest.main()
