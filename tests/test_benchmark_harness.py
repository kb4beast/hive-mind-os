from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping, Sequence

from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.benchmark_corpus import BudgetSpec, LaneTask, build_corpus
from hive_mind_os.benchmark_harness import (
    BenchmarkHarness,
    LaneExecution,
    MeasurementVerdict,
    bootstrap_interval,
    find_unauthorized_claims,
)


def _raw_records(
    output: Path,
    report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw = output / str(report["raw_results"])
    return [
        json.loads(line)
        for line in raw.read_text(encoding="utf-8").splitlines()
    ]


def _tracked_files(repository: Path) -> tuple[str, ...]:
    completed = subprocess.run(
        ["git", "ls-files"],
        cwd=repository,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        shell=False,
    )
    return tuple(completed.stdout.decode("utf-8").splitlines())


class _OverspendingLane:
    identity = "rigged-overspending-lane"

    def execute(
        self,
        task: LaneTask,
        budget: AutonomyBudget,
        attempt_root: Path,
    ) -> LaneExecution:
        allowance = budget.issue_allowance()
        budget.consume(
            allowance,
            tool_calls=allowance.tool_calls + 1,
            compute_units=0,
        )
        raise AssertionError("unreachable")


class BenchmarkHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_corpus_is_deterministic(self) -> None:
        first = build_corpus(self.root / "first")
        second = build_corpus(self.root / "second")

        self.assertEqual(first.digest, second.digest)
        self.assertEqual(
            [task.base_sha for task in first.tasks],
            [task.base_sha for task in second.tasks],
        )
        self.assertEqual(len(first.tasks), 5)

    def test_hidden_checks_are_not_materialized_for_lanes(self) -> None:
        corpus = build_corpus(self.root / "corpus")

        for task in corpus.tasks:
            files = _tracked_files(task.repository)
            self.assertFalse(
                any("success-check" in name or "hidden" in name for name in files)
            )
            content = b"\n".join(
                (task.repository / name).read_bytes()
                for name in files
                if not name.endswith(".pyc")
            )
            self.assertNotIn(task.checker_id.encode(), content)
            self.assertFalse(hasattr(task.lane_view(), "checker_id"))

    def test_equal_budget_and_overspend_fails_closed(self) -> None:
        spec = BudgetSpec(max_tool_calls=2, max_tool_calls_per_episode=2)
        harness = BenchmarkHarness(
            lanes={"baseline": _OverspendingLane()},
            budget=spec,
        )
        output = self.root / "evidence"
        report = harness.run(
            output,
            repetitions=1,
            seed=3,
            lane_names=("baseline",),
            task_ids=("failing-test-fix",),
        )
        [record] = _raw_records(output, report)

        self.assertIs(record["success"], False)
        self.assertEqual(record["budget"]["issued"], spec.to_dict())
        self.assertIs(record["budget"]["exceeded"], True)
        self.assertIs(record["budget"]["within_budget"], False)

    def test_failed_attempts_retain_same_artifacts_as_successes(self) -> None:
        output = self.root / "evidence"
        report = BenchmarkHarness().run(
            output,
            repetitions=1,
            seed=5,
            lane_names=("baseline",),
            task_ids=("failing-test-fix", "off-by-one-green-tests"),
        )
        records = _raw_records(output, report)
        self.assertEqual(
            {record["success"] for record in records},
            {True, False},
        )
        expected_inventory = (
            "lane-report.json",
            "receipts-index.json",
            "success-check.json",
            "budget.json",
        )
        inventories = {
            tuple(Path(path).name for path in record["artifacts"])
            for record in records
        }
        self.assertEqual(inventories, {expected_inventory})
        run_root = output / str(report["run_id"])
        self.assertTrue(
            all(
                (run_root / path).is_file()
                for record in records
                for path in record["artifacts"]
            )
        )
        for record in records:
            attempt_root = (run_root / record["artifacts"][0]).parent
            self.assertEqual(
                sorted(path.name for path in attempt_root.iterdir()),
                sorted(expected_inventory),
            )

    def test_bootstrap_interval_is_seeded_and_rate_is_exact(self) -> None:
        outcomes: Sequence[bool] = (True, False, True, False)

        first = bootstrap_interval(outcomes, seed=7)
        second = bootstrap_interval(outcomes, seed=7)

        self.assertEqual(first, second)
        self.assertEqual(first[0], 0.5)
        self.assertLessEqual(first[1], first[0])
        self.assertLessEqual(first[0], first[2])

    def test_measurement_verdict_binds_digests_and_cannot_claim_superiority(
        self,
    ) -> None:
        verdict = MeasurementVerdict(
            schema_version=1,
            disposition="measurement-recorded",
            judge_id="independent-judge",
            lane_identities=("hive-lane", "baseline-lane"),
            harness_digest="sha256:" + "1" * 64,
            corpus_digest="sha256:" + "2" * 64,
            code_digest="a" * 40,
            lane_digests={"hive": "sha256:" + "3" * 64},
            results_digest="sha256:" + "4" * 64,
            obligations=("no claim",),
        )
        self.assertEqual(
            verdict.to_dict()["corpus_digest"],
            "sha256:" + "2" * 64,
        )
        self.assertNotIn(verdict.judge_id, verdict.lane_identities)

        with self.assertRaisesRegex(ValueError, "capped"):
            MeasurementVerdict(
                schema_version=1,
                disposition="adopt",
                judge_id="independent-judge",
                lane_identities=("hive-lane", "baseline-lane"),
                harness_digest="sha256:" + "1" * 64,
                corpus_digest="sha256:" + "2" * 64,
                code_digest="a" * 40,
                lane_digests={"hive": "sha256:" + "3" * 64},
                results_digest="sha256:" + "4" * 64,
                obligations=("no claim",),
            )
        with self.assertRaisesRegex(ValueError, "independent"):
            MeasurementVerdict(
                schema_version=1,
                disposition="measurement-recorded",
                judge_id="hive-lane",
                lane_identities=("hive-lane", "baseline-lane"),
                harness_digest="sha256:" + "1" * 64,
                corpus_digest="sha256:" + "2" * 64,
                code_digest="a" * 40,
                lane_digests={"hive": "sha256:" + "3" * 64},
                results_digest="sha256:" + "4" * 64,
                obligations=("no claim",),
            )

    def test_claim_guard_rejects_unbound_comparative_marketing(self) -> None:
        repository = self.root / "repository"
        docs = repository / "docs"
        docs.mkdir(parents=True)
        (repository / "README.md").write_text("# Project\n", encoding="utf-8")
        claim = docs / "claim.md"
        claim.write_text(
            "Hive Mind OS outperforms the baseline benchmark.\n",
            encoding="utf-8",
        )
        plan = docs / "plan" / "P13_BENCHMARK_COURT_MVP.md"
        plan.parent.mkdir()
        plan.write_text(
            "planting Hive Mind OS outperforms the baseline benchmark.\n",
            encoding="utf-8",
        )

        self.assertEqual(
            find_unauthorized_claims(repository),
            (
                "docs/claim.md",
                "docs/plan/P13_BENCHMARK_COURT_MVP.md",
            ),
        )
        claim.write_text(
            "Hive Mind OS outperforms the baseline benchmark.\n\n"
            "superiority-verdict: court-123\n",
            encoding="utf-8",
        )
        self.assertEqual(
            find_unauthorized_claims(repository),
            (
                "docs/claim.md",
                "docs/plan/P13_BENCHMARK_COURT_MVP.md",
            ),
        )

    def test_two_task_two_repetition_run_completes_offline(self) -> None:
        output = self.root / "evidence"
        environment = dict(os.environ)
        source_root = str(Path.cwd() / "src")
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (source_root, environment.get("PYTHONPATH", "")))
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "hive_mind_os.cli",
                "benchmark",
                "run",
                "--lanes",
                "hive,baseline",
                "--repetitions",
                "2",
                "--seed",
                "7",
                "--task",
                "failing-test-fix",
                "--task",
                "off-by-one-green-tests",
                "--output",
                str(output),
            ],
            cwd=Path.cwd(),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
            timeout=120,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr.decode("utf-8", "replace"),
        )
        report = json.loads(completed.stdout)
        records = _raw_records(output, report)

        self.assertEqual(len(records), 8)
        self.assertEqual(
            report["verdict"]["disposition"],
            "measurement-recorded",
        )
        self.assertTrue(
            (output / str(report["run_id"]) / "verdict.json").is_file()
        )
        self.assertEqual(
            {
                json.dumps(record["budget"]["issued"], sort_keys=True)
                for record in records
            },
            {json.dumps(BudgetSpec().to_dict(), sort_keys=True)},
        )
        self.assertEqual(find_unauthorized_claims(Path.cwd()), ())


if __name__ == "__main__":
    unittest.main()
