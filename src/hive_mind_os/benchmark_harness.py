"""Budget-equal, offline benchmark harness with raw losing-case retention."""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .autonomy import AutonomyBudget, BudgetExceeded
from .benchmark_baseline import BaselineAgent
from .benchmark_corpus import (
    BudgetSpec,
    CorpusTask,
    LaneTask,
    build_corpus,
)
from .mission import RepositoryMission, ScriptedRepositoryBackend
from .models import AutonomyLevel
from .policy import PolicyEngine
from .receipts import sha256_digest

MEASUREMENT_DISPOSITION = "measurement-recorded"
DEFAULT_JUDGE_ID = "p13-independent-benchmark-judge"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    return sha256_digest(_canonical_bytes(value))


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_canonical_bytes(value) + b"\n")


def _remove_tree(root: Path) -> None:
    def make_writable_and_retry(
        function: object,
        path: str,
        _error: object,
    ) -> None:
        os.chmod(path, stat.S_IWRITE)
        assert callable(function)
        function(path)

    shutil.rmtree(root, onerror=make_writable_and_retry)


def _git(root: Path, *args: str) -> str:
    environment = dict(os.environ)
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"})
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "benchmark Git command failed: "
            + completed.stderr.decode("utf-8", "replace")
        )
    return completed.stdout.decode("utf-8", "strict").strip()


def _clone(repository: Path, destination: Path) -> None:
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    _git(parent, "clone", "--quiet", "--no-hardlinks", str(repository), str(destination))


def _materialize_delivery(
    repository: Path,
    artifact: Path,
    destination: Path,
) -> None:
    _clone(repository, destination)
    manifest = json.loads((artifact / "delivery.json").read_text(encoding="utf-8"))
    head_sha = manifest["head_sha"]
    _git(destination, "fetch", "--quiet", str(artifact / "changes.bundle"), head_sha)
    _git(destination, "checkout", "--quiet", "--detach", head_sha)


@dataclass(frozen=True, slots=True)
class LaneExecution:
    status: str
    identity: str
    workspace: Path
    report: dict[str, object]
    receipts: tuple[dict[str, object], ...]


class LaneRunner(Protocol):
    identity: str

    def execute(
        self,
        task: LaneTask,
        budget: AutonomyBudget,
        attempt_root: Path,
    ) -> LaneExecution: ...


class HiveMindLane:
    """P05 repository mission lane, invoked with the common issued budget."""

    identity = "p05-hive-mind-scripted-lane"

    def execute(
        self,
        task: LaneTask,
        budget: AutonomyBudget,
        attempt_root: Path,
    ) -> LaneExecution:
        artifact = attempt_root / "delivery"
        mission = RepositoryMission(
            task.repository,
            task.objective,
            acceptance_criteria=task.acceptance_criteria,
            backend=ScriptedRepositoryBackend(),
            pin=task.base_sha,
            output_dir=artifact,
            policy=PolicyEngine(AutonomyLevel.REPOSITORY),
            budget=budget,
        )
        report = asyncio.run(mission.run())
        evaluation = attempt_root / "evaluation"
        if report.status.value == "succeeded" and artifact.is_dir():
            _materialize_delivery(task.repository, artifact, evaluation)
        else:
            _clone(task.repository, evaluation)
        payload = report.to_dict()
        return LaneExecution(
            status=report.status.value,
            identity=self.identity,
            workspace=evaluation,
            report=payload,
            receipts=tuple(
                dict(record)
                for record in payload.get("receipts", [])
                if isinstance(record, dict)
            ),
        )


class BaselineLane:
    identity = BaselineAgent.identity

    def __init__(self) -> None:
        self.agent = BaselineAgent()

    def execute(
        self,
        task: LaneTask,
        budget: AutonomyBudget,
        attempt_root: Path,
    ) -> LaneExecution:
        evaluation = attempt_root / "evaluation"
        _clone(task.repository, evaluation)
        result = self.agent.execute(task, budget, evaluation)
        return LaneExecution(
            status=result.status,
            identity=result.identity,
            workspace=evaluation,
            report=result.report,
            receipts=result.receipts,
        )


_CHECK_PROGRAMS = {
    "increment-wide": (
        "from tiny_pkg.maths import increment; "
        "assert increment(5) == 6; assert increment(-2) == -1"
    ),
    "increment-negative": (
        "from tiny_pkg.maths import increment; assert increment(-2) == -1"
    ),
    "documentation-aligned": (
        "from pathlib import Path; from tiny_pkg.maths import increment; "
        "text=Path('README.md').read_text(encoding='utf-8').lower(); "
        "assert 'adds one' in text; assert increment(8) == 9"
    ),
    "legacy-eliminated": (
        "from pathlib import Path; from tiny_pkg.maths import increment; "
        "assert increment(3) == 4; assert not Path('tiny_pkg/legacy.py').exists()"
    ),
}


def _run_hidden_check(task: CorpusTask, workspace: Path) -> dict[str, object]:
    program = _CHECK_PROGRAMS[task.checker_id]
    completed = subprocess.run(
        [sys.executable, "-B", "-c", program],
        cwd=workspace,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        shell=False,
        timeout=30,
    )
    return {
        "schema_version": 1,
        "checker_digest": task.manifest.hidden_check_digest,
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.decode("utf-8", "replace"),
        "stderr": completed.stderr.decode("utf-8", "replace"),
    }


def bootstrap_interval(
    outcomes: Sequence[bool | int],
    *,
    seed: int,
    samples: int = 2000,
) -> tuple[float, float, float]:
    if not outcomes:
        raise ValueError("bootstrap outcomes cannot be empty")
    if samples < 100:
        raise ValueError("bootstrap sample count must be at least 100")
    values = [float(value) for value in outcomes]
    rate = sum(values) / len(values)
    generator = random.Random(seed)
    draws = sorted(
        sum(generator.choice(values) for _ in values) / len(values)
        for _ in range(samples)
    )
    lower = draws[int(0.025 * (samples - 1))]
    upper = draws[int(0.975 * (samples - 1))]
    return round(rate, 6), round(lower, 6), round(upper, 6)


@dataclass(frozen=True, slots=True)
class MeasurementVerdict:
    schema_version: int
    disposition: str
    judge_id: str
    lane_identities: tuple[str, ...]
    harness_digest: str
    corpus_digest: str
    code_digest: str
    lane_digests: Mapping[str, str]
    results_digest: str
    obligations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.disposition != MEASUREMENT_DISPOSITION:
            raise ValueError("P13 verdicts are capped at measurement-recorded")
        if self.judge_id in self.lane_identities:
            raise ValueError("benchmark judge must be independent from lane identities")
        if len(set(self.lane_identities)) != len(self.lane_identities):
            raise ValueError("benchmark lane identities must be distinct")

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["lane_identities"] = list(self.lane_identities)
        payload["lane_digests"] = dict(self.lane_digests)
        payload["obligations"] = list(self.obligations)
        return payload


def _budget_consumption(budget: AutonomyBudget) -> dict[str, int | float]:
    return {
        "episodes": budget.episodes_used,
        "tool_calls": budget.tool_calls_used,
        "compute_units": budget.compute_units_used,
    }


def _budget_within(spec: BudgetSpec, budget: AutonomyBudget) -> bool:
    return (
        budget.episodes_used <= spec.max_episodes
        and budget.tool_calls_used <= spec.max_tool_calls
        and budget.compute_units_used <= spec.max_compute_units
    )


def _safe_lane_name(name: str) -> str:
    aliases = {"hive": "hive-mind", "hive-mind": "hive-mind", "baseline": "baseline"}
    try:
        return aliases[name]
    except KeyError:
        raise ValueError(f"unsupported benchmark lane: {name}") from None


class BenchmarkHarness:
    def __init__(
        self,
        *,
        lanes: Mapping[str, LaneRunner] | None = None,
        budget: BudgetSpec = BudgetSpec(),
        judge_id: str = DEFAULT_JUDGE_ID,
    ) -> None:
        self.lanes = dict(
            lanes
            or {
                "hive-mind": HiveMindLane(),
                "baseline": BaselineLane(),
            }
        )
        if not self.lanes:
            raise ValueError("benchmark requires at least one lane")
        if len({lane.identity for lane in self.lanes.values()}) != len(self.lanes):
            raise ValueError("benchmark lane identities must be distinct")
        self.budget = budget
        self.judge_id = judge_id

    def run(
        self,
        output_root: str | Path,
        *,
        repetitions: int,
        seed: int,
        lane_names: Sequence[str] = ("hive-mind", "baseline"),
        task_ids: Sequence[str] | None = None,
        code_root: str | Path = ".",
    ) -> dict[str, object]:
        if repetitions < 1:
            raise ValueError("benchmark repetitions must be positive")
        selected_lanes = tuple(_safe_lane_name(name) for name in lane_names)
        if len(set(selected_lanes)) != len(selected_lanes):
            raise ValueError("benchmark lane list contains duplicates")
        missing = set(selected_lanes) - set(self.lanes)
        if missing:
            raise ValueError("benchmark lane unavailable: " + ", ".join(sorted(missing)))

        code_repository = Path(code_root).resolve()
        code_digest = _git(code_repository, "rev-parse", "HEAD")
        harness_digest = _canonical_digest(
            {
                "schema_version": 1,
                "module": "hive_mind_os.benchmark_harness",
                "implementation_digest": sha256_digest(Path(__file__).read_bytes()),
                "budget": self.budget.to_dict(),
                "statistics": {"bootstrap_samples": 2000, "confidence": 0.95},
            }
        )
        lane_digests = {
            name: _canonical_digest(
                {
                    "lane": name,
                    "identity": self.lanes[name].identity,
                    "budget": self.budget.to_dict(),
                }
            )
            for name in selected_lanes
        }
        output = Path(output_root).resolve()
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hive-mind-p13-corpus-") as temporary:
            corpus = build_corpus(
                Path(temporary) / "corpus",
                task_ids=task_ids,
                budget=self.budget,
            )
            run_key = _canonical_digest(
                {
                    "corpus": corpus.digest,
                    "code": code_digest,
                    "lanes": lane_digests,
                    "repetitions": repetitions,
                    "seed": seed,
                }
            )
            run_id = f"p13-{run_key.removeprefix('sha256:')[:16]}"
            run_root = output / run_id
            if run_root.exists():
                raise FileExistsError(
                    "benchmark run already exists; evidence is append-only: " + run_id
                )
            run_root.mkdir()
            raw_results: list[dict[str, object]] = []
            raw_path = run_root / "raw-results.jsonl"

            for task in corpus.tasks:
                for repetition in range(1, repetitions + 1):
                    for lane_name in selected_lanes:
                        raw_results.append(
                            self._run_attempt(
                                run_root,
                                task,
                                repetition,
                                lane_name,
                            )
                        )
            raw_path.write_bytes(
                b"".join(_canonical_bytes(record) + b"\n" for record in raw_results)
            )
            stats = self._statistics(raw_results, selected_lanes, seed)
            results_digest = sha256_digest(raw_path.read_bytes())
            verdict = MeasurementVerdict(
                schema_version=1,
                disposition=MEASUREMENT_DISPOSITION,
                judge_id=self.judge_id,
                lane_identities=tuple(
                    self.lanes[name].identity for name in selected_lanes
                ),
                harness_digest=harness_digest,
                corpus_digest=corpus.digest,
                code_digest=code_digest,
                lane_digests=lane_digests,
                results_digest=results_digest,
                obligations=(
                    "No comparative quality or superiority claim is authorized.",
                    "Add multiple pinned external comparators and benchmark families before any superiority court.",
                    "Retain failed and losing attempts with the same artifact inventory.",
                ),
            )
            _write_json(run_root / "verdict.json", verdict.to_dict())
            report: dict[str, object] = {
                "schema_version": 1,
                "run_id": run_id,
                "repetitions": repetitions,
                "seed": seed,
                "task_ids": [task.manifest.task_id for task in corpus.tasks],
                "lanes": list(selected_lanes),
                "budget": self.budget.to_dict(),
                "corpus_digest": corpus.digest,
                "code_digest": code_digest,
                "harness_digest": harness_digest,
                "lane_digests": lane_digests,
                "results_digest": results_digest,
                "statistics": stats,
                "verdict": verdict.to_dict(),
                "raw_results": str(raw_path.relative_to(output).as_posix()),
            }
            _write_json(run_root / "summary.json", report)
            return report

    def _run_attempt(
        self,
        run_root: Path,
        task: CorpusTask,
        repetition: int,
        lane_name: str,
    ) -> dict[str, object]:
        attempt_id = f"{task.manifest.task_id}-r{repetition:02d}-{lane_name}"
        attempt_key = _canonical_digest(attempt_id).removeprefix("sha256:")[:16]
        attempt_root = run_root / "attempts" / f"a-{attempt_key}"
        attempt_root.mkdir(parents=True)
        budget = self.budget.create()
        lane = self.lanes[lane_name]
        execution: LaneExecution | None = None
        lane_error: str | None = None
        budget_exceeded = False
        try:
            execution = lane.execute(task.lane_view(), budget, attempt_root)
        except BudgetExceeded as error:
            budget_exceeded = True
            lane_error = f"{type(error).__name__}: {error}"
        except Exception as error:
            lane_error = f"{type(error).__name__}: {error}"

        if execution is None:
            evaluation = attempt_root / "evaluation"
            if not evaluation.exists():
                _clone(task.repository, evaluation)
            execution = LaneExecution(
                status="failed",
                identity=lane.identity,
                workspace=evaluation,
                report={
                    "schema_version": 1,
                    "status": "failed",
                    "error": lane_error or "lane did not return an execution",
                },
                receipts=(),
            )
        elif execution.identity != lane.identity:
            lane_error = "lane returned an identity different from its pinned configuration"
            execution = LaneExecution(
                status="failed",
                identity=execution.identity,
                workspace=execution.workspace,
                report=execution.report,
                receipts=execution.receipts,
            )

        check = _run_hidden_check(task, execution.workspace)
        within_budget = _budget_within(self.budget, budget) and not budget_exceeded
        success = (
            execution.status == "succeeded"
            and bool(check["passed"])
            and within_budget
            and lane_error is None
        )
        budget_record = {
            "schema_version": 1,
            "issued": self.budget.to_dict(),
            "consumed": _budget_consumption(budget),
            "within_budget": within_budget,
            "exceeded": budget_exceeded,
        }
        _write_json(attempt_root / "lane-report.json", execution.report)
        _write_json(
            attempt_root / "receipts-index.json",
            {"schema_version": 1, "receipts": list(execution.receipts)},
        )
        _write_json(attempt_root / "success-check.json", check)
        _write_json(attempt_root / "budget.json", budget_record)
        for child in attempt_root.iterdir():
            if child.is_dir():
                _remove_tree(child)
        artifact_names = (
            "lane-report.json",
            "receipts-index.json",
            "success-check.json",
            "budget.json",
        )
        return {
            "schema_version": 1,
            "attempt_id": attempt_id,
            "task_id": task.manifest.task_id,
            "repetition": repetition,
            "lane": lane_name,
            "lane_identity": execution.identity,
            "success": success,
            "lane_status": execution.status,
            "hidden_check_passed": bool(check["passed"]),
            "budget": budget_record,
            "error": lane_error,
            "artifacts": [
                str((attempt_root / name).relative_to(run_root).as_posix())
                for name in artifact_names
            ],
        }

    @staticmethod
    def _statistics(
        records: Sequence[Mapping[str, object]],
        lanes: Sequence[str],
        seed: int,
    ) -> dict[str, object]:
        by_lane: dict[str, object] = {}
        for lane_index, lane in enumerate(lanes):
            lane_records = [record for record in records if record["lane"] == lane]
            outcomes = [bool(record["success"]) for record in lane_records]
            rate, lower, upper = bootstrap_interval(
                outcomes,
                seed=seed + lane_index,
            )
            task_ids = sorted({str(record["task_id"]) for record in lane_records})
            per_task = {}
            for task_index, task_id in enumerate(task_ids):
                task_outcomes = [
                    bool(record["success"])
                    for record in lane_records
                    if record["task_id"] == task_id
                ]
                task_rate, task_lower, task_upper = bootstrap_interval(
                    task_outcomes,
                    seed=seed + lane_index * 1000 + task_index + 1,
                )
                per_task[task_id] = {
                    "attempts": len(task_outcomes),
                    "success_rate": task_rate,
                    "ci95": [task_lower, task_upper],
                }
            by_lane[lane] = {
                "attempts": len(outcomes),
                "success_rate": rate,
                "ci95": [lower, upper],
                "per_task": per_task,
            }
        return by_lane


_CLAIM_PATTERN = re.compile(
    r"hive\s+mind\s+os.{0,160}\b(outperforms|beats|stronger\s+than)\b"
    r".{0,160}\b(benchmark|baseline|comparator)\b"
    r"|\b(outperforms|beats|stronger\s+than)\b.{0,160}hive\s+mind\s+os"
    r".{0,160}\b(benchmark|baseline|comparator)\b",
    re.IGNORECASE | re.DOTALL,
)


def find_unauthorized_claims(root: str | Path) -> tuple[str, ...]:
    """Return user-facing Markdown files with P13-forbidden comparative claims."""

    repository = Path(root)
    candidates = [repository / "README.md"]
    docs = repository / "docs"
    if docs.is_dir():
        candidates.extend(sorted(docs.rglob("*.md")))
    findings: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if path.name == "P13_BENCHMARK_COURT_MVP.md":
            text = "\n".join(
                line for line in text.splitlines() if "planting " not in line
            )
        if _CLAIM_PATTERN.search(text):
            findings.append(path.relative_to(repository).as_posix())
    return tuple(findings)


def render_results(report: Mapping[str, object]) -> str:
    statistics = report["statistics"]
    assert isinstance(statistics, dict)
    lines = [
        "# P13 Benchmark Court Results",
        "",
        f"- Run: `{report['run_id']}`",
        f"- Disposition: `{MEASUREMENT_DISPOSITION}`",
        f"- Corpus digest: `{report['corpus_digest']}`",
        f"- Code commit: `{report['code_digest']}`",
        f"- Repetitions: {report['repetitions']}",
        f"- Seed: {report['seed']}",
        "",
        "| Lane | Attempts | Success rate | Seeded bootstrap 95% CI |",
        "|---|---:|---:|---:|",
    ]
    for lane, value in statistics.items():
        assert isinstance(value, dict)
        lower, upper = value["ci95"]
        lines.append(
            f"| {lane} | {value['attempts']} | {value['success_rate']:.3f} "
            f"| [{lower:.3f}, {upper:.3f}] |"
        )
    lines.extend(["", "## Per-task measurements", ""])
    for lane, value in statistics.items():
        assert isinstance(value, dict)
        per_task = value["per_task"]
        assert isinstance(per_task, dict)
        lines.extend(
            [
                f"### {lane}",
                "",
                "| Task | Attempts | Success rate | Seeded bootstrap 95% CI |",
                "|---|---:|---:|---:|",
            ]
        )
        for task_id, task_value in per_task.items():
            assert isinstance(task_value, dict)
            lower, upper = task_value["ci95"]
            lines.append(
                f"| {task_id} | {task_value['attempts']} "
                f"| {task_value['success_rate']:.3f} "
                f"| [{lower:.3f}, {upper:.3f}] |"
            )
        lines.append("")
    lines.extend(
        [
            "These are measurements from one scripted task family and one in-repository "
            "baseline. They authorize no comparative quality or superiority claim.",
            "Raw results and every failed attempt are retained under "
            f"`evidence/benchmarks/{report['run_id']}/`.",
            "",
            "## Required next evidence",
            "",
            "- Multiple pinned external comparators.",
            "- Multiple benchmark families and declared safety floors.",
            "- Independent reproduction before any higher-burden court.",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "BaselineLane",
    "BenchmarkHarness",
    "DEFAULT_JUDGE_ID",
    "HiveMindLane",
    "LaneExecution",
    "LaneRunner",
    "MEASUREMENT_DISPOSITION",
    "MeasurementVerdict",
    "bootstrap_interval",
    "find_unauthorized_claims",
    "render_results",
]
