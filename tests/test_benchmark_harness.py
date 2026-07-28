from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import pytest

from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.benchmark_corpus import BudgetSpec, LaneTask, build_corpus
from hive_mind_os.benchmark_harness import (
    BenchmarkHarness,
    LaneExecution,
    MeasurementVerdict,
    bootstrap_interval,
    find_unauthorized_claims,
)


def _raw_records(output: Path, report: dict[str, object]) -> list[dict[str, object]]:
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


def test_corpus_is_deterministic(tmp_path: Path) -> None:
    first = build_corpus(tmp_path / "first")
    second = build_corpus(tmp_path / "second")

    assert first.digest == second.digest
    assert [task.base_sha for task in first.tasks] == [
        task.base_sha for task in second.tasks
    ]
    assert len(first.tasks) == 5


def test_hidden_checks_are_not_materialized_for_lanes(tmp_path: Path) -> None:
    corpus = build_corpus(tmp_path / "corpus")

    for task in corpus.tasks:
        files = _tracked_files(task.repository)
        assert not any("success-check" in name or "hidden" in name for name in files)
        content = b"\n".join(
            (task.repository / name).read_bytes()
            for name in files
            if not name.endswith(".pyc")
        )
        assert task.checker_id.encode() not in content
        assert not hasattr(task.lane_view(), "checker_id")


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


def test_equal_budget_and_overspend_fails_closed(tmp_path: Path) -> None:
    spec = BudgetSpec(max_tool_calls=2, max_tool_calls_per_episode=2)
    harness = BenchmarkHarness(
        lanes={"baseline": _OverspendingLane()},
        budget=spec,
    )
    output = tmp_path / "evidence"
    report = harness.run(
        output,
        repetitions=1,
        seed=3,
        lane_names=("baseline",),
        task_ids=("failing-test-fix",),
    )
    [record] = _raw_records(output, report)

    assert record["success"] is False
    assert record["budget"]["issued"] == spec.to_dict()
    assert record["budget"]["exceeded"] is True
    assert record["budget"]["within_budget"] is False


def test_failed_attempts_retain_same_artifacts_as_successes(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    report = BenchmarkHarness().run(
        output,
        repetitions=1,
        seed=5,
        lane_names=("baseline",),
        task_ids=("failing-test-fix", "off-by-one-green-tests"),
    )
    records = _raw_records(output, report)
    assert {record["success"] for record in records} == {True, False}
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
    assert inventories == {expected_inventory}
    run_root = output / str(report["run_id"])
    assert all(
        (run_root / path).is_file()
        for record in records
        for path in record["artifacts"]
    )
    for record in records:
        attempt_root = (run_root / record["artifacts"][0]).parent
        assert sorted(path.name for path in attempt_root.iterdir()) == sorted(
            expected_inventory
        )


def test_bootstrap_interval_is_seeded_and_rate_is_exact() -> None:
    outcomes: Sequence[bool] = (True, False, True, False)

    first = bootstrap_interval(outcomes, seed=7)
    second = bootstrap_interval(outcomes, seed=7)

    assert first == second
    assert first[0] == 0.5
    assert first[1] <= first[0] <= first[2]


def test_measurement_verdict_binds_digests_and_cannot_claim_superiority() -> None:
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
    assert verdict.to_dict()["corpus_digest"] == "sha256:" + "2" * 64
    assert verdict.judge_id not in verdict.lane_identities

    with pytest.raises(ValueError, match="capped"):
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
    with pytest.raises(ValueError, match="independent"):
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


def test_claim_guard_rejects_unbound_comparative_marketing(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    docs = repository / "docs"
    docs.mkdir(parents=True)
    (repository / "README.md").write_text("# Project\n", encoding="utf-8")
    claim = docs / "claim.md"
    claim.write_text(
        "Hive Mind OS outperforms the baseline benchmark.\n",
        encoding="utf-8",
    )

    assert find_unauthorized_claims(repository) == ("docs/claim.md",)
    claim.write_text(
        "Hive Mind OS outperforms the baseline benchmark.\n\n"
        "superiority-verdict: court-123\n",
        encoding="utf-8",
    )
    assert find_unauthorized_claims(repository) == ()


def test_two_task_two_repetition_run_completes_offline(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
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
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    report = json.loads(completed.stdout)
    records = _raw_records(output, report)

    assert len(records) == 8
    assert report["verdict"]["disposition"] == "measurement-recorded"
    assert (output / str(report["run_id"]) / "verdict.json").is_file()
    assert {
        json.dumps(record["budget"]["issued"], sort_keys=True)
        for record in records
    } == {json.dumps(BudgetSpec().to_dict(), sort_keys=True)}
    assert find_unauthorized_claims(Path.cwd()) == ()
