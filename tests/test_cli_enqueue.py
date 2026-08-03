from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path

from hive_mind_os import cli
from hive_mind_os.scheduler import Scheduler
from tests.fixtures.fixture_repo import build_fixture_repo


class EnqueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = build_fixture_repo(self.root / "repository")
        self.state_dir = self.root / "state"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def specification(self, identifier: str, criterion: str) -> Path:
        path = self.root / f"{identifier}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": identifier,
                    "criterion": criterion,
                    "command": {
                        "argv": ["python", "-B", "-c", "pass"],
                        "expected": "succeeded",
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def enqueue(
        self,
        criteria: list[str],
        *,
        specifications: list[Path] | None = None,
        pin: str | None = None,
    ) -> dict[str, str]:
        output = io.StringIO()
        arguments = Namespace(
            repository=str(self.fixture.root),
            objective="Fix the failing test",
            criterion=criteria,
            acceptance_spec=[str(path) for path in specifications or ()],
            backend="scripted",
            pin=pin,
            max_attempts=3,
            state_dir=str(self.state_dir),
        )
        with redirect_stdout(output):
            self.assertEqual(cli._run_enqueue(arguments), 0)
        return json.loads(output.getvalue())

    def test_enqueue_resolves_a_pin_and_deduplicates_semantic_work(self) -> None:
        alpha = self.specification("alpha", "criterion a")
        beta = self.specification("beta", "criterion b")
        first = self.enqueue(
            ["criterion b", "criterion a"], specifications=[beta, alpha]
        )
        second = self.enqueue(
            ["criterion a", "criterion b"], specifications=[alpha, beta]
        )
        self.assertEqual(first["mission_id"], second["mission_id"])
        self.assertEqual(first["job_id"], second["job_id"])

        scheduler = Scheduler(self.state_dir)
        try:
            job = scheduler.get(first["job_id"])
        finally:
            scheduler.close()
        self.assertEqual(job.payload["pin"], self.fixture.commit_two)
        self.assertEqual(
            job.payload["acceptance_criteria"], ["criterion a", "criterion b"]
        )
        self.assertEqual(
            [item["id"] for item in job.payload["acceptance_specifications"]],
            ["alpha", "beta"],
        )

    def test_enqueue_rejects_criteria_without_typed_specifications(self) -> None:
        with self.assertRaisesRegex(SystemExit, "typed executable"):
            self.enqueue(["criterion a"])

    def test_enqueue_rejects_a_mutable_pin(self) -> None:
        with self.assertRaisesRegex(SystemExit, "full 40-hex"):
            self.enqueue([], pin="main")


if __name__ == "__main__":
    unittest.main()
