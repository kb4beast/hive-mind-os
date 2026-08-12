"""Focused tests for the hive-cortex autonomy benchmark and comparator court.

Run with::

    PYTHONPATH=src python -m unittest tests.test_hive_cortex_benchmark -v
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping, Sequence

from hive_mind_os.benchmark_harness import (
    MEASUREMENT_DISPOSITION,
    bootstrap_interval,
    find_unauthorized_claims,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
_BENCH = REPO_ROOT / "benchmarks" / "hive-cortex"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "hive_cortex"
RESULTS_DOCUMENT = REPO_ROOT / "docs" / "benchmarks" / "HIVE_CORTEX_RESULTS.md"
RESULTS_DOCUMENT_RELPATH = "docs/benchmarks/HIVE_CORTEX_RESULTS.md"

#: The seven acceptance dimensions, written out literally so that narrowing the
#: implementation's own dimension list cannot make the coverage test vacuous.
EXPECTED_METRIC_KEYS = frozenset(
    {
        "correctness",
        "human_interventions",
        "role_coverage",
        "recovery",
        "evidence_completeness",
        "cost_units",
        "latency_seconds",
    }
)

EXPECTED_ATTEMPT_ARTIFACTS = frozenset(
    {"lane-report.json", "metrics.json", "check.json", "checkpoint.json"}
)


def _load(alias: str, filename: str):
    """Load a benchmark module by path: ``benchmarks/hive-cortex`` is not a package."""

    spec = importlib.util.spec_from_file_location(alias, _BENCH / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve field types through sys.modules[cls.__module__].
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


runner = _load("hive_cortex_runner", "runner.py")
court = _load("hive_cortex_comparator_court", "comparator_court.py")


def _raw_records(run_root: Path) -> list[dict[str, Any]]:
    raw = run_root / "raw-results.jsonl"
    return [
        json.loads(line)
        for line in raw.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _digest_input_records(run_root: Path) -> list[dict[str, Any]]:
    raw = run_root / "raw-results.digest-input.jsonl"
    return [
        json.loads(line)
        for line in raw.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _use_registry(case: unittest.TestCase, entries: Sequence[Mapping[str, Any]]) -> None:
    """Point ``load_scenarios`` at a throwaway registry for one test."""

    directory = tempfile.TemporaryDirectory()
    case.addCleanup(directory.cleanup)
    path = Path(directory.name) / "scenarios.json"
    path.write_text(
        json.dumps({"schema_version": 1, "scenarios": list(entries)}),
        encoding="utf-8",
    )
    original = runner.SCENARIOS_PATH
    runner.SCENARIOS_PATH = path
    case.addCleanup(setattr, runner, "SCENARIOS_PATH", original)


class _AlwaysFailingLane:
    """Rigged lane that never produces a result and never checkpoints."""

    identity = "rigged-always-failing-lane"

    def execute(
        self,
        scenario: Any,
        workspace: Path,
        checkpoint: Path,
        resume: bool,
    ) -> Any:
        raise RuntimeError("rigged lane failure")


class _IdentitySwappingLane(runner.NullBaselineLane):
    """Rigged lane that reports a different identity than it was pinned with."""

    identity = "rigged-identity-swapping-lane"

    def execute(
        self,
        scenario: Any,
        workspace: Path,
        checkpoint: Path,
        resume: bool,
    ) -> Any:
        result = super().execute(scenario, workspace, checkpoint, resume)
        self.identity = "rigged-identity-swapping-lane-IMPOSTOR"
        return result


class BenchmarkHarnessTests(unittest.TestCase):
    """Seven-dimension coverage, reproducibility, recovery, and retention."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._directory.cleanup)
        cls.output = Path(cls._directory.name) / "canonical"
        cls.seed = 7
        cls.repetitions = 3
        benchmark = runner.HiveCortexBenchmark(
            REPO_ROOT, seed=cls.seed, repetitions=cls.repetitions
        )
        cls.report = benchmark.run(cls.output)
        cls.run_root = cls.output / str(cls.report["run_id"])
        cls.records = _raw_records(cls.run_root)

    def test_run_reports_all_seven_metric_dimensions(self) -> None:
        self.assertEqual(len(EXPECTED_METRIC_KEYS), 7)
        self.assertTrue(self.records)
        for record in self.records:
            metrics = record["metrics"]
            self.assertEqual(
                set(metrics),
                set(EXPECTED_METRIC_KEYS),
                f"attempt {record['attempt_id']} metric keys",
            )
            self.assertEqual(len(metrics), 7)
        # metrics.json on disk carries the same seven dimensions
        for record in self.records:
            payload = json.loads(
                (self.run_root / record["attempt_dir"] / "metrics.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(set(payload), set(EXPECTED_METRIC_KEYS))
        self.assertEqual(set(runner.METRIC_DIMENSIONS), set(EXPECTED_METRIC_KEYS))

        # every dimension is populated with a value of the right shape
        for record in self.records:
            metrics = record["metrics"]
            self.assertIsInstance(metrics["correctness"], bool)
            self.assertIsInstance(metrics["recovery"], bool)
            self.assertIsInstance(metrics["evidence_completeness"], bool)
            self.assertIsInstance(metrics["human_interventions"], int)
            self.assertIsInstance(metrics["cost_units"], int)
            self.assertGreaterEqual(metrics["role_coverage"], 0.0)
            self.assertLessEqual(metrics["role_coverage"], 1.0)
            self.assertGreaterEqual(metrics["latency_seconds"], 0.0)

    def test_same_seed_reproduces_results_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = runner.HiveCortexBenchmark(REPO_ROOT, seed=23, repetitions=2).run(
                root / "first"
            )
            second = runner.HiveCortexBenchmark(REPO_ROOT, seed=23, repetitions=2).run(
                root / "second"
            )
            self.assertEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["results_digest"], second["results_digest"])

            first_root = root / "first" / str(first["run_id"])
            second_root = root / "second" / str(second["run_id"])
            self.assertEqual(
                (first_root / "raw-results.digest-input.jsonl").read_bytes(),
                (second_root / "raw-results.digest-input.jsonl").read_bytes(),
            )
            # latency is real, positive, and recorded ...
            raw = _raw_records(first_root)
            neutral = {
                record["attempt_id"]: record
                for record in _digest_input_records(first_root)
            }
            self.assertTrue(
                any(record["metrics"]["latency_seconds"] > 0.0 for record in raw)
            )
            # ... and neutralized in the digest input, which is why digests match
            differing = 0
            for record in raw:
                mirror = neutral[record["attempt_id"]]
                self.assertEqual(mirror["metrics"]["latency_seconds"], 0)
                if record["metrics"]["latency_seconds"] > 0.0:
                    # metrics.json embeds latency, so its recorded sha256 must be
                    # restated at zero latency or the digest drifts.
                    self.assertNotEqual(
                        mirror["artifacts"]["metrics.json"],
                        record["artifacts"]["metrics.json"],
                    )
                    differing += 1
                for name in sorted(EXPECTED_ATTEMPT_ARTIFACTS - {"metrics.json"}):
                    self.assertEqual(
                        mirror["artifacts"][name], record["artifacts"][name]
                    )
            self.assertGreater(differing, 0)

    def test_run_directory_is_append_only(self) -> None:
        summary = self.run_root / "summary.json"
        before = summary.read_bytes()
        repeat = runner.HiveCortexBenchmark(
            REPO_ROOT, seed=self.seed, repetitions=self.repetitions
        )
        self.assertEqual(repeat.run_id(), str(self.report["run_id"]))
        with self.assertRaises(FileExistsError) as caught:
            repeat.run(self.output)
        self.assertIn(str(self.report["run_id"]), str(caught.exception))
        self.assertEqual(summary.read_bytes(), before)

    def test_recovery_drill_resumes_from_checkpoint(self) -> None:
        by_key = {
            (record["scenario_id"], record["lane"], record["repetition"]): record
            for record in self.records
        }
        scenario_ids = {record["scenario_id"] for record in self.records}
        lanes = {record["lane"] for record in self.records}
        self.assertTrue(scenario_ids)
        self.assertTrue(lanes)

        for scenario_id in sorted(scenario_ids):
            for lane in sorted(lanes):
                first = by_key[(scenario_id, lane, 1)]
                drilled = by_key[(scenario_id, lane, 2)]
                third = by_key[(scenario_id, lane, 3)]

                self.assertIsNone(first["recovery_drill"])
                drill = drilled["recovery_drill"]
                self.assertIsNotNone(drill)
                self.assertTrue(drill["attempted"], drill)
                self.assertTrue(drill["interrupted"], drill)
                self.assertTrue(drill["resumed"], drill)
                self.assertTrue(drill["recovered"], drill)
                self.assertEqual(
                    drill["baseline_workspace_digest"],
                    drill["resumed_workspace_digest"],
                )
                self.assertEqual(
                    drill["resumed_workspace_digest"], drilled["workspace_digest"]
                )
                self.assertEqual(first["workspace_digest"], drilled["workspace_digest"])
                self.assertGreater(drill["interrupted_cost_units"], 0)

                # the drill result is what every repetition records
                for record in (first, drilled, third):
                    self.assertTrue(record["metrics"]["recovery"], record["attempt_id"])

                # resuming is an operator action and costs extra
                self.assertEqual(first["metrics"]["human_interventions"], 0)
                self.assertEqual(drilled["metrics"]["human_interventions"], 1)
                self.assertGreater(
                    drilled["metrics"]["cost_units"], first["metrics"]["cost_units"]
                )

                checkpoint = json.loads(
                    (
                        self.run_root / drilled["attempt_dir"] / "checkpoint.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(checkpoint["stage"], "completed")
                self.assertTrue(checkpoint["resumed"])
                self.assertTrue(checkpoint["files_observed"])

                plain_checkpoint = json.loads(
                    (self.run_root / first["attempt_dir"] / "checkpoint.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertFalse(plain_checkpoint["resumed"])

    def test_failed_attempts_are_retained_with_same_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            benchmark = runner.HiveCortexBenchmark(
                REPO_ROOT,
                seed=5,
                repetitions=2,
                lanes={
                    "hive-cortex": runner.ScriptedHiveCortexLane(),
                    "rigged": _AlwaysFailingLane(),
                },
            )
            report = benchmark.run(Path(temporary))
            run_root = Path(temporary) / str(report["run_id"])
            records = _raw_records(run_root)

            failures = [record for record in records if record["lane"] == "rigged"]
            passes = [record for record in records if record["lane"] == "hive-cortex"]
            self.assertTrue(failures)
            self.assertTrue(passes)

            passing_inventory = {frozenset(record["artifacts"]) for record in passes}
            self.assertEqual(passing_inventory, {EXPECTED_ATTEMPT_ARTIFACTS})

            for record in failures:
                self.assertEqual(record["lane_status"], "failed")
                self.assertIn("rigged lane failure", str(record["error"]))
                self.assertFalse(record["metrics"]["correctness"])
                self.assertFalse(record["metrics"]["evidence_completeness"])
                self.assertEqual(record["metrics"]["role_coverage"], 0.0)
                # identical artifact inventory to a passing attempt
                self.assertEqual(
                    frozenset(record["artifacts"]), EXPECTED_ATTEMPT_ARTIFACTS
                )
                attempt_dir = run_root / record["attempt_dir"]
                for name in sorted(EXPECTED_ATTEMPT_ARTIFACTS):
                    artifact = attempt_dir / name
                    self.assertTrue(artifact.is_file(), f"{record['attempt_id']}/{name}")
                    self.assertGreater(artifact.stat().st_size, 0)
                # the workspace of the losing attempt is retained too
                self.assertTrue((attempt_dir / "workspace").is_dir())

            statistics = report["statistics"]["rigged"]
            self.assertEqual(statistics["correctness_rate"], 0.0)
            self.assertEqual(statistics["evidence_completeness_rate"], 0.0)

    def test_statistics_use_seeded_bootstrap_interval(self) -> None:
        lanes = sorted(self.report["lanes"])
        self.assertEqual(lanes, sorted(self.report["statistics"]))
        for lane_index, lane in enumerate(lanes):
            outcomes = [
                bool(record["metrics"]["correctness"])
                for record in self.records
                if record["lane"] == lane
            ]
            self.assertTrue(outcomes)
            rate, lower, upper = bootstrap_interval(
                outcomes, seed=int(self.report["seed"]) + lane_index
            )
            statistics = self.report["statistics"][lane]
            self.assertEqual(statistics["attempts"], len(outcomes))
            self.assertEqual(statistics["correctness_rate"], rate)
            self.assertEqual(statistics["correctness_ci95"], [lower, upper])

            scenario_ids = [
                entry["scenario_id"] for entry in self.report["scenarios"]
            ]
            for scenario_index, scenario_id in enumerate(scenario_ids):
                scenario_outcomes = [
                    bool(record["metrics"]["correctness"])
                    for record in self.records
                    if record["lane"] == lane and record["scenario_id"] == scenario_id
                ]
                expected = bootstrap_interval(
                    scenario_outcomes,
                    seed=int(self.report["seed"])
                    + lane_index * 1000
                    + scenario_index
                    + 1,
                )
                entry = statistics["per_scenario"][scenario_id]
                self.assertEqual(entry["correctness_rate"], expected[0])
                self.assertEqual(entry["ci95"], [expected[1], expected[2]])

    def test_scenarios_cover_all_four_fixtures(self) -> None:
        expected = sorted(
            path.name for path in FIXTURE_ROOT.iterdir() if path.is_dir()
        )
        self.assertEqual(len(expected), 4)
        self.assertEqual(
            expected,
            [
                "hidden-defect-python",
                "misleading-readme-node",
                "monorepo-cross-language",
                "no-test-csharp",
            ],
        )
        scenarios = runner.load_scenarios(REPO_ROOT)
        self.assertEqual(sorted(item.scenario_id for item in scenarios), expected)

        for scenario in scenarios:
            fixture = (FIXTURE_ROOT / scenario.scenario_id).resolve()
            self.assertEqual(scenario.fixture, fixture)
            manifest = json.loads((fixture / "fixture.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["fixture_id"], scenario.scenario_id)
            self.assertTrue(scenario.required_roles)
            self.assertTrue(scenario.patch)
            self.assertTrue(scenario.checker.strip())
            self.assertNotIn("{{sha256:", scenario.checker)
            self.assertEqual(scenario.fixture_digest, runner.tree_digest(fixture))

        # the recorded run exercised every scenario against every lane
        covered = {
            (record["scenario_id"], record["lane"]) for record in self.records
        }
        self.assertEqual(
            covered,
            {
                (scenario_id, lane)
                for scenario_id in expected
                for lane in self.report["lanes"]
            },
        )


class BenchmarkEdgeCaseTests(unittest.TestCase):
    """Edge cases called out by the runbook's test plan."""

    def test_empty_scenario_registry_is_rejected(self) -> None:
        _use_registry(self, [])
        with self.assertRaises(runner.ScenarioError):
            runner.load_scenarios(REPO_ROOT)

    def test_zero_required_roles_is_rejected_at_load_time(self) -> None:
        _use_registry(
            self,
            [
                {
                    "scenario_id": "no-roles",
                    "fixture": "tests/fixtures/hive_cortex/hidden-defect-python",
                    "required_roles": [],
                    "patch": {"app.py": "x = 1\n"},
                    "checker": "assert True",
                }
            ],
        )
        with self.assertRaises(runner.ScenarioError) as caught:
            runner.load_scenarios(REPO_ROOT)
        self.assertIn("required_roles", str(caught.exception))

    def test_missing_fixture_directory_is_rejected(self) -> None:
        _use_registry(
            self,
            [
                {
                    "scenario_id": "ghost",
                    "fixture": "tests/fixtures/hive_cortex/does-not-exist",
                    "required_roles": ["explorer"],
                    "patch": {"app.py": "x = 1\n"},
                    "checker": "assert True",
                }
            ],
        )
        with self.assertRaises(runner.ScenarioError):
            runner.load_scenarios(REPO_ROOT)

    def test_non_positive_repetitions_is_rejected(self) -> None:
        for repetitions in (0, -1):
            with self.subTest(repetitions=repetitions):
                with self.assertRaises(ValueError):
                    runner.HiveCortexBenchmark(
                        REPO_ROOT, seed=1, repetitions=repetitions
                    )

    def test_duplicate_lane_identities_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            runner.HiveCortexBenchmark(
                REPO_ROOT,
                seed=1,
                repetitions=1,
                lanes={
                    "a": runner.NullBaselineLane(),
                    "b": runner.NullBaselineLane(),
                },
            )

    def test_wrong_lane_identity_marks_the_attempt_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            benchmark = runner.HiveCortexBenchmark(
                REPO_ROOT,
                seed=3,
                repetitions=1,
                lanes={"swapper": _IdentitySwappingLane()},
            )
            report = benchmark.run(Path(temporary))
            records = _raw_records(Path(temporary) / str(report["run_id"]))
            self.assertTrue(records)
            for record in records:
                self.assertEqual(record["lane_status"], "failed")
                self.assertIn("identity", str(record["error"]))
                self.assertFalse(record["metrics"]["correctness"])

    def test_checker_timeout_records_failure_and_retains_the_attempt(self) -> None:
        _use_registry(
            self,
            [
                {
                    "scenario_id": "stalling-checker",
                    "fixture": "tests/fixtures/hive_cortex/hidden-defect-python",
                    "required_roles": ["explorer", "builder", "verifier"],
                    "patch": {"app.py": "def discount_total(t, d):\n    return t - d\n"},
                    "checker": "import time\ntime.sleep(30)\n",
                }
            ],
        )
        original_timeout = runner.CHECKER_TIMEOUT_SECONDS
        runner.CHECKER_TIMEOUT_SECONDS = 2
        self.addCleanup(
            setattr, runner, "CHECKER_TIMEOUT_SECONDS", original_timeout
        )
        self.assertEqual(original_timeout, 30)

        with tempfile.TemporaryDirectory() as temporary:
            benchmark = runner.HiveCortexBenchmark(
                REPO_ROOT,
                seed=9,
                repetitions=1,
                lanes={"hive-cortex": runner.ScriptedHiveCortexLane()},
            )
            report = benchmark.run(Path(temporary))
            run_root = Path(temporary) / str(report["run_id"])
            records = _raw_records(run_root)
            self.assertEqual(len(records), 1)
            record = records[0]
            self.assertTrue(record["check_timed_out"])
            self.assertFalse(record["metrics"]["correctness"])
            # no drill runs at repetitions=1, so recovery is honestly false
            self.assertFalse(record["metrics"]["recovery"])
            self.assertEqual(
                frozenset(record["artifacts"]), EXPECTED_ATTEMPT_ARTIFACTS
            )
            check = json.loads(
                (run_root / record["attempt_dir"] / "check.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(check["timed_out"])
            self.assertIsNone(check["returncode"])


class ComparatorProvenanceTests(unittest.TestCase):
    """Every comparator is pinned and licensed, or excused with a reason."""

    def test_registry_entries_are_pinned_or_marked_unavailable(self) -> None:
        records = court.load_comparators(_BENCH / "comparators.json")
        self.assertGreaterEqual(len(records), 10)

        pinned = []
        for record in records:
            self.assertIn(
                record.availability,
                (court.AVAILABILITY_PINNED, court.AVAILABILITY_UNAVAILABLE),
            )
            if record.availability == court.AVAILABILITY_PINNED:
                self.assertTrue((record.pin or "").strip(), record.source_id)
                self.assertTrue((record.license or "").strip(), record.source_id)
                pinned.append(record)
            else:
                self.assertIsNone(record.pin, record.source_id)
                self.assertIsNone(record.license, record.source_id)
                self.assertTrue((record.reason or "").strip(), record.source_id)

        # only the two in-repository lanes may be pinned
        self.assertEqual(
            sorted(record.name for record in pinned),
            sorted(
                [
                    runner.ScriptedHiveCortexLane.identity,
                    runner.NullBaselineLane.identity,
                ]
            ),
        )

        # every founding-suite comparator is accounted for, and none was invented
        founding = json.loads(
            (REPO_ROOT / "benchmarks" / "founding-comparator-suite.json").read_text(
                encoding="utf-8"
            )
        )
        founding_ids = {entry["source_id"] for entry in founding["comparators"]}
        registry_ids = {record.source_id for record in records}
        self.assertTrue(founding_ids <= registry_ids, founding_ids - registry_ids)
        for record in records:
            if record.source_id in founding_ids:
                self.assertEqual(
                    record.availability, court.AVAILABILITY_UNAVAILABLE, record.source_id
                )

    def test_pinned_without_license_is_rejected(self) -> None:
        for license_value in (None, "", "   "):
            with self.subTest(license=license_value):
                with self.assertRaises(court.ComparatorProvenanceError):
                    court.ComparatorRecord(
                        source_id="SRC-999",
                        name="Unlicensed Comparator",
                        pin="0123456789abcdef0123456789abcdef01234567",
                        license=license_value,
                        availability=court.AVAILABILITY_PINNED,
                        reason=None,
                    )
        # missing pin is rejected the same way
        with self.assertRaises(court.ComparatorProvenanceError):
            court.ComparatorRecord(
                source_id="SRC-999",
                name="Unpinned Comparator",
                pin=None,
                license="MIT",
                availability=court.AVAILABILITY_PINNED,
                reason=None,
            )
        # a fully provenanced entry is accepted
        record = court.ComparatorRecord(
            source_id="SRC-999",
            name="Provenanced Comparator",
            pin="0123456789abcdef0123456789abcdef01234567",
            license="MIT",
            availability=court.AVAILABILITY_PINNED,
            reason=None,
        )
        self.assertEqual(record.to_dict()["availability"], court.AVAILABILITY_PINNED)

    def test_unavailable_without_reason_is_rejected(self) -> None:
        for reason in (None, "", "  "):
            with self.subTest(reason=reason):
                with self.assertRaises(court.ComparatorProvenanceError):
                    court.ComparatorRecord(
                        source_id="SRC-998",
                        name="Unexplained Absence",
                        pin=None,
                        license=None,
                        availability=court.AVAILABILITY_UNAVAILABLE,
                        reason=reason,
                    )
        record = court.ComparatorRecord(
            source_id="SRC-998",
            name="Explained Absence",
            pin=None,
            license=None,
            availability=court.AVAILABILITY_UNAVAILABLE,
            reason="not executed in this repository",
        )
        self.assertEqual(record.to_dict()["reason"], "not executed in this repository")

    def test_court_verdict_pins_lane_identities_and_judge_independence(self) -> None:
        comparators = court.load_comparators(_BENCH / "comparators.json")
        identities = (
            runner.ScriptedHiveCortexLane.identity,
            runner.NullBaselineLane.identity,
        )
        verdict = court.build_verdict(
            lane_identities=identities,
            comparators=comparators,
            results_digest="sha256:" + "0" * 64,
        )
        payload = verdict.to_dict()
        self.assertEqual(payload["judge_id"], court.JUDGE_ID)
        self.assertNotIn(court.JUDGE_ID, payload["lane_identities"])
        self.assertEqual(payload["lane_identities"], list(identities))
        self.assertEqual(payload["disposition"], MEASUREMENT_DISPOSITION)
        self.assertEqual(len(payload["comparators"]), len(comparators))
        self.assertEqual(payload["obligations"], list(court.OBLIGATIONS))

        with self.assertRaises(ValueError):
            court.ComparatorCourtVerdict(
                schema_version=1,
                disposition=MEASUREMENT_DISPOSITION,
                judge_id=court.JUDGE_ID,
                lane_identities=(court.JUDGE_ID, identities[0]),
                comparators=comparators,
                results_digest="sha256:" + "0" * 64,
                obligations=court.OBLIGATIONS,
            )

        with self.assertRaises(ValueError):
            court.ComparatorCourtVerdict(
                schema_version=1,
                disposition=MEASUREMENT_DISPOSITION,
                judge_id=court.JUDGE_ID,
                lane_identities=(identities[0], identities[0]),
                comparators=comparators,
                results_digest="sha256:" + "0" * 64,
                obligations=court.OBLIGATIONS,
            )

        # the recorded run's verdict carries the same guarantees
        with tempfile.TemporaryDirectory() as temporary:
            report = runner.HiveCortexBenchmark(
                REPO_ROOT, seed=13, repetitions=1
            ).run(Path(temporary))
            recorded = report["verdict"]
            self.assertEqual(recorded["disposition"], MEASUREMENT_DISPOSITION)
            self.assertNotIn(recorded["judge_id"], recorded["lane_identities"])
            self.assertEqual(
                sorted(recorded["lane_identities"]), sorted(set(identities))
            )
            self.assertEqual(recorded["results_digest"], report["results_digest"])


class SuperiorityClaimGuardTests(unittest.TestCase):
    """No comparative claim survives without reproducible receipts."""

    def test_guard_flags_superiority_phrasing(self) -> None:
        # Assembled at runtime so the forbidden phrase never appears verbatim in
        # any file scanned by find_unauthorized_claims.
        probe = "Hive Mind OS " + "outper" + "forms the baseline on this benchmark."
        violations = court.guard_results_document(probe + "\n" + court.DISCLAIMER)
        self.assertTrue(violations)
        self.assertTrue(
            any("superiority phrasing" in violation for violation in violations),
            violations,
        )

        for verb in ("beats", "is " + "superior" + " to", "is stronger than"):
            with self.subTest(verb=verb):
                text = f"The hive-cortex lane {verb} every comparator.\n"
                self.assertTrue(
                    court.guard_results_document(text + court.DISCLAIMER),
                    verb,
                )

        # a factual, non-comparative sentence about the same subjects is clean
        clean = (
            "Recorded measurements for the hive-cortex benchmark and its "
            "comparator registry; the null baseline applied no patch.\n"
            + court.DISCLAIMER
            + "\n"
        )
        self.assertEqual(court.guard_results_document(clean), ())

    def test_guard_requires_disclaimer_line(self) -> None:
        self.assertEqual(
            court.DISCLAIMER,
            "These are measurements only; they authorize no comparative quality "
            "or superiority claim.",
        )
        without = "# Results\n\n- Run id: `hive-cortex-0000000000000000`\n"
        violations = court.guard_results_document(without)
        self.assertEqual(len(violations), 1)
        self.assertIn("missing mandatory disclaimer", violations[0])
        self.assertIn(court.DISCLAIMER, violations[0])

        self.assertEqual(
            court.guard_results_document(without + "\n" + court.DISCLAIMER + "\n"), ()
        )
        # a paraphrase is not the mandated line
        paraphrase = without + "\nThese are measurements only.\n"
        self.assertTrue(court.guard_results_document(paraphrase))

    def test_results_document_passes_guard(self) -> None:
        self.assertTrue(
            RESULTS_DOCUMENT.is_file(),
            f"{RESULTS_DOCUMENT_RELPATH} must be generated by a real run",
        )
        text = RESULTS_DOCUMENT.read_text(encoding="utf-8")
        self.assertEqual(court.guard_results_document(text), ())
        self.assertIn(court.DISCLAIMER, text)
        # the document is a receipt, not a narrative: it must carry its digests
        self.assertIn("hive-cortex-", text)
        self.assertIn("Results digest", text)
        self.assertIn("Corpus digest", text)
        self.assertIn("Runner digest", text)
        self.assertIn(MEASUREMENT_DISPOSITION, text)
        self.assertIn("--repetitions", text)
        self.assertIn("--seed", text)

    def test_non_measurement_disposition_raises_superiority_claim_error(self) -> None:
        comparators = court.load_comparators(_BENCH / "comparators.json")
        for disposition in ("superiority-established", "hive-cortex-wins", ""):
            with self.subTest(disposition=disposition):
                with self.assertRaises(court.SuperiorityClaimError) as caught:
                    court.ComparatorCourtVerdict(
                        schema_version=1,
                        disposition=disposition,
                        judge_id=court.JUDGE_ID,
                        lane_identities=(runner.NullBaselineLane.identity,),
                        comparators=comparators,
                        results_digest="sha256:" + "0" * 64,
                        obligations=court.OBLIGATIONS,
                    )
                self.assertIn("reproducible receipts", str(caught.exception))

        accepted = court.ComparatorCourtVerdict(
            schema_version=1,
            disposition=MEASUREMENT_DISPOSITION,
            judge_id=court.JUDGE_ID,
            lane_identities=(runner.NullBaselineLane.identity,),
            comparators=comparators,
            results_digest="sha256:" + "0" * 64,
            obligations=court.OBLIGATIONS,
        )
        self.assertEqual(accepted.disposition, MEASUREMENT_DISPOSITION)

    def test_repo_docs_scan_stays_clean(self) -> None:
        findings = find_unauthorized_claims(REPO_ROOT)
        self.assertNotIn(RESULTS_DOCUMENT_RELPATH, findings)
        self.assertTrue(RESULTS_DOCUMENT.is_file())


if __name__ == "__main__":
    unittest.main()
