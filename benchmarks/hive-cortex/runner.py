"""Reproducible multi-scenario autonomy benchmark for the hive-cortex fixtures.

Seven dimensions are measured for every attempt: correctness, human
interventions, role coverage, recovery, evidence completeness, cost, and
latency. Latency is recorded but excluded from every digest, because it is the
one dimension that cannot be reproduced byte-for-byte.

This directory is intentionally NOT a Python package: the hyphen in
``hive-cortex`` makes it unimportable by module path. Load this file with
:func:`importlib.util.spec_from_file_location` (see ``README.md``), and run it
as a script with ``src`` on ``PYTHONPATH``::

    PYTHONPATH=src python benchmarks/hive-cortex/runner.py --output <dir> \\
        --seed 7 --repetitions 3

The benchmark is offline and toolchain-free. Scenario checkers are pure-Python
assertion programs, so Node and C# fixtures are checked by file-content and
digest assertions rather than by invoking ``node`` or ``dotnet``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from hive_mind_os.benchmark_harness import MEASUREMENT_DISPOSITION, bootstrap_interval

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parents[1]
SCENARIOS_PATH = _HERE / "scenarios.json"
COMPARATORS_PATH = _HERE / "comparators.json"
COURT_PATH = _HERE / "comparator_court.py"

SCHEMA_VERSION = 1
CHECKER_TIMEOUT_SECONDS = 30

#: The seven acceptance dimensions, in the order they are reported.
METRIC_DIMENSIONS: tuple[str, ...] = (
    "correctness",
    "human_interventions",
    "role_coverage",
    "recovery",
    "evidence_completeness",
    "cost_units",
    "latency_seconds",
)

#: Written for every attempt, including failed and losing ones.
ATTEMPT_ARTIFACTS: tuple[str, ...] = (
    "lane-report.json",
    "metrics.json",
    "check.json",
    "checkpoint.json",
)

REPRODUCTION_COMMAND = (
    "PYTHONPATH=src python benchmarks/hive-cortex/runner.py "
    "--output <output-dir> --seed {seed} --repetitions {repetitions} "
    "--render docs/benchmarks/HIVE_CORTEX_RESULTS.md"
)

_SHA256_PLACEHOLDER = re.compile(r"\{\{sha256:([^{}]+)\}\}")


def _load_sibling(alias: str, filename: str):
    """Load a sibling file as a module, since this directory is not a package."""

    path = _HERE / filename
    spec = importlib.util.spec_from_file_location(alias, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load benchmark module by path: {path}")
    module = importlib.util.module_from_spec(spec)
    # Required before exec_module: dataclasses resolve field types through
    # sys.modules[cls.__module__], which raises AttributeError for a module
    # that was never registered.
    sys.modules[alias] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(alias, None)
        raise
    return module


court = _load_sibling("hive_cortex_comparator_court", "comparator_court.py")


class ScenarioError(ValueError):
    """Raised when the scenario registry is unusable or internally inconsistent."""


class _SimulatedInterruption(RuntimeError):
    """Scripted crash used only by the recovery drill."""

    def __init__(self, partial: "LaneResult") -> None:
        super().__init__("scripted interruption after checkpoint")
        self.partial = partial


# --------------------------------------------------------------------------
# digest helpers
# --------------------------------------------------------------------------


def _canonical_text(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_bytes(value: object) -> bytes:
    return _canonical_text(value).encode("utf-8")


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_digest(value: object) -> str:
    return _digest_bytes(_canonical_bytes(value))


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(value) + b"\n")


def _relative_files(root: Path) -> list[str]:
    return sorted(
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file()
    )


def tree_digest(root: Path) -> str:
    """sha256 over sorted ``(relative posix path, bytes)`` pairs beneath *root*."""

    hasher = hashlib.sha256()
    for relpath in _relative_files(root):
        payload = (root / relpath).read_bytes()
        hasher.update(relpath.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(str(len(payload)).encode("ascii"))
        hasher.update(b"\x00")
        hasher.update(payload)
        hasher.update(b"\x00")
    return "sha256:" + hasher.hexdigest()


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(float(value) for value in values) / len(values), 6)


def _top_component(relpath: str) -> str:
    head, separator, _ = relpath.partition("/")
    return head if separator else ""


# --------------------------------------------------------------------------
# scenarios
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    fixture: Path
    required_roles: tuple[str, ...]
    patch: Mapping[str, str]
    checker: str
    fixture_digest: str

    def digest(self) -> str:
        return _canonical_digest(
            {
                "schema_version": SCHEMA_VERSION,
                "scenario_id": self.scenario_id,
                "required_roles": list(self.required_roles),
                "patch": dict(self.patch),
                "checker": self.checker,
                "fixture_digest": self.fixture_digest,
            }
        )

    def checker_digest(self) -> str:
        return _digest_bytes(self.checker.encode("utf-8"))

    def touched_components(self) -> tuple[str, ...]:
        return tuple(sorted({_top_component(relpath) for relpath in self.patch}))


def _resolve_checker(checker: str, fixture: Path, scenario_id: str) -> str:
    """Substitute ``{{sha256:<relpath>}}`` with the fixture file's real digest.

    The runbook asks the ``no-test-csharp`` checker to assert that
    ``Program.cs`` is unchanged byte-for-byte "vs a recorded sha256". A literal
    digest baked into ``scenarios.json`` would bind the bytes of one checkout:
    ``*.cs`` and ``*.js`` have no ``eol`` pin in ``.gitattributes`` and this
    repository sets ``core.autocrlf=true``, so those fixtures are CRLF on
    Windows and LF on POSIX. Recording the digest of the fixture as actually
    loaded keeps the assertion byte-exact without silently failing on the other
    platform.
    """

    def replace(match: re.Match[str]) -> str:
        relpath = match.group(1).strip()
        target = fixture / relpath
        if not target.is_file():
            raise ScenarioError(
                f"scenario {scenario_id} references a missing fixture file: {relpath}"
            )
        return hashlib.sha256(target.read_bytes()).hexdigest()

    return _SHA256_PLACEHOLDER.sub(replace, checker)


def load_scenarios(repo_root: str | Path) -> tuple[Scenario, ...]:
    """Parse ``scenarios.json`` and bind each scenario to real fixture bytes."""

    root = Path(repo_root).resolve()
    payload = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScenarioError("scenario registry must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ScenarioError(
            f"unsupported scenario schema_version: {payload.get('schema_version')!r}"
        )
    entries = payload.get("scenarios")
    if not isinstance(entries, list) or not entries:
        raise ScenarioError("scenario registry must declare at least one scenario")

    scenarios: list[Scenario] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ScenarioError("scenario entries must be JSON objects")
        scenario_id = str(entry.get("scenario_id", "")).strip()
        if not scenario_id:
            raise ScenarioError("scenario entries require a scenario_id")
        if scenario_id in seen:
            raise ScenarioError(f"duplicate scenario_id: {scenario_id}")
        seen.add(scenario_id)

        fixture_relpath = str(entry.get("fixture", "")).strip()
        if not fixture_relpath:
            raise ScenarioError(f"scenario {scenario_id} requires a fixture path")
        fixture = (root / fixture_relpath).resolve()
        if not fixture.is_dir():
            raise ScenarioError(
                f"scenario {scenario_id} fixture directory is missing: {fixture_relpath}"
            )

        roles = entry.get("required_roles")
        if not isinstance(roles, list) or not roles:
            raise ScenarioError(
                f"scenario {scenario_id} requires a non-empty required_roles list; "
                "role coverage is undefined with zero required roles"
            )
        required_roles = tuple(str(role) for role in roles)
        if len(set(required_roles)) != len(required_roles):
            raise ScenarioError(f"scenario {scenario_id} repeats a required role")

        patch = entry.get("patch")
        if not isinstance(patch, dict) or not patch:
            raise ScenarioError(f"scenario {scenario_id} requires a non-empty patch")
        for relpath, content in patch.items():
            if not isinstance(relpath, str) or not relpath.strip():
                raise ScenarioError(f"scenario {scenario_id} has an empty patch path")
            if relpath.startswith("/") or ".." in Path(relpath).parts:
                raise ScenarioError(
                    f"scenario {scenario_id} patch path escapes the workspace: {relpath}"
                )
            if not isinstance(content, str):
                raise ScenarioError(
                    f"scenario {scenario_id} patch content must be text: {relpath}"
                )

        checker = entry.get("checker")
        if not isinstance(checker, str) or not checker.strip():
            raise ScenarioError(f"scenario {scenario_id} requires a checker program")

        scenarios.append(
            Scenario(
                scenario_id=scenario_id,
                fixture=fixture,
                required_roles=required_roles,
                patch=dict(patch),
                checker=_resolve_checker(checker, fixture, scenario_id),
                fixture_digest=tree_digest(fixture),
            )
        )
    return tuple(scenarios)


# --------------------------------------------------------------------------
# metrics and lanes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AttemptMetrics:
    """The seven acceptance dimensions for a single attempt."""

    correctness: bool
    human_interventions: int
    role_coverage: float
    recovery: bool
    evidence_completeness: bool
    cost_units: int
    latency_seconds: float

    def to_dict(self) -> dict[str, object]:
        return {
            "correctness": bool(self.correctness),
            "human_interventions": int(self.human_interventions),
            "role_coverage": round(float(self.role_coverage), 6),
            "recovery": bool(self.recovery),
            "evidence_completeness": bool(self.evidence_completeness),
            "cost_units": int(self.cost_units),
            "latency_seconds": round(float(self.latency_seconds), 6),
        }


@dataclass(frozen=True)
class LaneResult:
    status: str
    roles_exercised: tuple[str, ...]
    human_interventions: int
    cost_units: int
    artifacts: Mapping[str, str]


class _CheckpointingLane:
    """Shared exploration/checkpoint behaviour for the two in-repository lanes."""

    identity = ""
    interrupt_after_checkpoint = False

    def _observe(self, workspace: Path) -> tuple[str, ...]:
        observed = _relative_files(workspace)
        for relpath in observed:
            (workspace / relpath).read_bytes()
        return tuple(observed)

    def _checkpoint_payload(
        self,
        scenario: Scenario,
        observed: Sequence[str],
        stage: str,
        resumed: bool,
    ) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "lane": self.identity,
            "scenario_id": scenario.scenario_id,
            "stage": stage,
            "resumed": resumed,
            "files_observed": list(observed),
            "patch_targets": sorted(scenario.patch),
        }

    def _explore_or_resume(
        self,
        scenario: Scenario,
        workspace: Path,
        checkpoint: Path,
        resume: bool,
    ) -> tuple[tuple[str, ...], int, int]:
        """Return ``(observed files, read cost, human interventions)``."""

        if resume and checkpoint.is_file():
            state = json.loads(checkpoint.read_text(encoding="utf-8"))
            observed = tuple(str(item) for item in state.get("files_observed", ()))
            # Resuming a crashed attempt is an operator action; count it.
            return observed, 1, 1
        observed = self._observe(workspace)
        _write_json(
            checkpoint,
            self._checkpoint_payload(scenario, observed, "explored", False),
        )
        if self.interrupt_after_checkpoint:
            raise _SimulatedInterruption(
                LaneResult(
                    status="interrupted",
                    roles_exercised=("explorer",),
                    human_interventions=0,
                    cost_units=len(observed),
                    artifacts={},
                )
            )
        return observed, len(observed), 0


class ScriptedHiveCortexLane(_CheckpointingLane):
    """Deterministic lane that applies each scenario's recorded patch."""

    identity = "hive-cortex-scripted-lane-v1"

    def execute(
        self,
        scenario: Scenario,
        workspace: Path,
        checkpoint: Path,
        resume: bool,
    ) -> LaneResult:
        observed, read_cost, interventions = self._explore_or_resume(
            scenario, workspace, checkpoint, resume
        )
        written: dict[str, str] = {}
        for relpath in sorted(scenario.patch):
            target = workspace / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(scenario.patch[relpath], encoding="utf-8", newline="\n")
            written[relpath] = _digest_bytes(target.read_bytes())
        verified = all((workspace / relpath).is_file() for relpath in scenario.patch)
        roles = ["explorer", "builder", "verifier"]
        if len(scenario.touched_components()) > 1:
            # A patch spanning more than one top-level component required an
            # integration decision, so that role was genuinely exercised.
            roles.append("integrator")
        _write_json(
            checkpoint,
            self._checkpoint_payload(scenario, observed, "completed", resume),
        )
        return LaneResult(
            status="succeeded" if verified else "failed",
            roles_exercised=tuple(roles),
            human_interventions=interventions,
            cost_units=read_cost + len(written) + 1,
            artifacts={
                "patch-manifest.json": _canonical_text(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "lane": self.identity,
                        "written": written,
                    }
                )
                + "\n"
            },
        )


class NullBaselineLane(_CheckpointingLane):
    """Pinned control lane: it observes the workspace and changes nothing."""

    identity = "pinned-null-baseline-v1"

    def execute(
        self,
        scenario: Scenario,
        workspace: Path,
        checkpoint: Path,
        resume: bool,
    ) -> LaneResult:
        observed, read_cost, interventions = self._explore_or_resume(
            scenario, workspace, checkpoint, resume
        )
        _write_json(
            checkpoint,
            self._checkpoint_payload(scenario, observed, "completed", resume),
        )
        return LaneResult(
            status="succeeded",
            roles_exercised=("explorer",),
            human_interventions=interventions,
            cost_units=read_cost + 1,
            artifacts={
                "observation-manifest.json": _canonical_text(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "lane": self.identity,
                        "observed": list(observed),
                        "patch_applied": False,
                    }
                )
                + "\n"
            },
        )


# --------------------------------------------------------------------------
# benchmark
# --------------------------------------------------------------------------


@dataclass
class _Attempt:
    attempt_id: str
    scenario: Scenario
    lane_name: str
    lane_identity: str
    repetition: int
    attempt_root: Path
    workspace: Path
    lane_result: LaneResult | None = None
    lane_error: str | None = None
    latency_seconds: float = 0.0
    check: dict[str, object] = field(default_factory=dict)
    workspace_digest: str = ""
    drill: dict[str, object] | None = None


class HiveCortexBenchmark:
    """Runs every scenario against every lane and records append-only evidence."""

    def __init__(
        self,
        repo_root: str | Path,
        *,
        seed: int,
        repetitions: int,
        lanes: Mapping[str, object] | None = None,
    ) -> None:
        if repetitions < 1:
            raise ValueError("benchmark repetitions must be positive")
        self.repo_root = Path(repo_root).resolve()
        self.seed = int(seed)
        self.repetitions = int(repetitions)
        selected = dict(
            lanes
            if lanes is not None
            else {
                "hive-cortex": ScriptedHiveCortexLane(),
                "null-baseline": NullBaselineLane(),
            }
        )
        if not selected:
            raise ValueError("benchmark requires at least one lane")
        identities = [str(getattr(lane, "identity", "")) for lane in selected.values()]
        if not all(identities):
            raise ValueError("every benchmark lane must declare an identity")
        if len(set(identities)) != len(identities):
            raise ValueError("benchmark lane identities must be distinct")
        self.lanes = selected
        self.lane_names: tuple[str, ...] = tuple(sorted(selected))
        self.lane_identities: dict[str, str] = {
            name: str(selected[name].identity) for name in self.lane_names
        }
        self.scenarios = load_scenarios(self.repo_root)
        self.comparators = court.load_comparators(COMPARATORS_PATH)

    # -- digests ---------------------------------------------------------

    def scenario_digests(self) -> dict[str, str]:
        return {scenario.scenario_id: scenario.digest() for scenario in self.scenarios}

    def corpus_digest(self) -> str:
        return _canonical_digest(
            {"schema_version": SCHEMA_VERSION, "scenarios": self.scenario_digests()}
        )

    def runner_digest(self) -> str:
        return _digest_bytes(Path(__file__).resolve().read_bytes())

    def run_key(self) -> str:
        return _canonical_digest(
            {
                "scenarios": self.scenario_digests(),
                "lanes": dict(self.lane_identities),
                "seed": self.seed,
                "repetitions": self.repetitions,
                "runner": self.runner_digest(),
            }
        )

    def run_id(self) -> str:
        return "hive-cortex-" + self.run_key().removeprefix("sha256:")[:16]

    # -- execution -------------------------------------------------------

    def run(self, output_root: str | Path) -> dict[str, object]:
        output = Path(output_root).resolve()
        run_id = self.run_id()
        run_root = output / run_id
        if run_root.exists():
            raise FileExistsError(
                "benchmark run already exists; evidence is append-only: " + run_id
            )
        output.mkdir(parents=True, exist_ok=True)
        run_root.mkdir()

        attempts: list[_Attempt] = []
        drills: dict[tuple[str, str], dict[str, object]] = {}
        for scenario in self.scenarios:
            for lane_name in self.lane_names:
                baseline_digest: str | None = None
                for repetition in range(1, self.repetitions + 1):
                    if repetition == 2:
                        attempt = self._run_recovery_drill(
                            run_root, scenario, lane_name, repetition, baseline_digest
                        )
                        drills[(scenario.scenario_id, lane_name)] = dict(
                            attempt.drill or {}
                        )
                    else:
                        attempt = self._run_attempt(
                            run_root, scenario, lane_name, repetition
                        )
                    if repetition == 1:
                        baseline_digest = attempt.workspace_digest
                    attempts.append(attempt)

        records = [
            self._finalize_attempt(
                run_root,
                attempt,
                bool(
                    drills.get(
                        (attempt.scenario.scenario_id, attempt.lane_name), {}
                    ).get("recovered", False)
                ),
            )
            for attempt in attempts
        ]
        records.sort(
            key=lambda record: (
                str(record["scenario_id"]),
                int(record["repetition"]),
                str(record["lane"]),
            )
        )

        raw_path = run_root / "raw-results.jsonl"
        raw_path.write_bytes(
            b"".join(_canonical_bytes(record) + b"\n" for record in records)
        )
        digest_input_path = run_root / "raw-results.digest-input.jsonl"
        digest_input_path.write_bytes(
            b"".join(
                _canonical_bytes(_digest_input_record(record)) + b"\n"
                for record in records
            )
        )
        results_digest = _digest_bytes(digest_input_path.read_bytes())

        statistics = self._statistics(records)
        verdict = court.build_verdict(
            lane_identities=[self.lane_identities[name] for name in self.lane_names],
            comparators=self.comparators,
            results_digest=results_digest,
        )
        _write_json(run_root / "verdict.json", verdict.to_dict())

        report: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "run_key": self.run_key(),
            "seed": self.seed,
            "repetitions": self.repetitions,
            "attempts": len(records),
            "metric_dimensions": list(METRIC_DIMENSIONS),
            "attempt_artifacts": list(ATTEMPT_ARTIFACTS),
            "lanes": dict(self.lane_identities),
            "scenarios": [
                {
                    "scenario_id": scenario.scenario_id,
                    "required_roles": list(scenario.required_roles),
                    "fixture_digest": scenario.fixture_digest,
                    "checker_digest": scenario.checker_digest(),
                    "scenario_digest": scenario.digest(),
                }
                for scenario in self.scenarios
            ],
            "corpus_digest": self.corpus_digest(),
            "runner_digest": self.runner_digest(),
            "court_digest": _digest_bytes(COURT_PATH.read_bytes()),
            "comparators_digest": _digest_bytes(COMPARATORS_PATH.read_bytes()),
            "results_digest": results_digest,
            "statistics": statistics,
            "verdict": verdict.to_dict(),
            "raw_results": raw_path.name,
            "digest_input": digest_input_path.name,
            "reproduction_command": REPRODUCTION_COMMAND.format(
                seed=self.seed, repetitions=self.repetitions
            ),
        }
        _write_json(run_root / "summary.json", report)
        return report

    def _new_attempt(
        self,
        run_root: Path,
        scenario: Scenario,
        lane_name: str,
        repetition: int,
    ) -> _Attempt:
        attempt_id = f"{scenario.scenario_id}-r{repetition:02d}-{lane_name}"
        key = _canonical_digest(attempt_id).removeprefix("sha256:")[:16]
        attempt_root = run_root / "attempts" / f"a-{key}"
        attempt_root.mkdir(parents=True)
        workspace = attempt_root / "workspace"
        shutil.copytree(scenario.fixture, workspace)
        return _Attempt(
            attempt_id=attempt_id,
            scenario=scenario,
            lane_name=lane_name,
            lane_identity=self.lane_identities[lane_name],
            repetition=repetition,
            attempt_root=attempt_root,
            workspace=workspace,
        )

    def _invoke_lane(
        self,
        attempt: _Attempt,
        resume: bool,
    ) -> tuple[LaneResult | None, str | None]:
        lane = self.lanes[attempt.lane_name]
        checkpoint = attempt.attempt_root / "checkpoint.json"
        try:
            result = lane.execute(attempt.scenario, attempt.workspace, checkpoint, resume)
        except _SimulatedInterruption:
            raise
        except Exception as error:  # noqa: BLE001 - recorded, never swallowed
            return None, f"{type(error).__name__}: {error}"
        if not isinstance(result, LaneResult):
            return None, "lane did not return a LaneResult"
        observed_identity = str(getattr(lane, "identity", ""))
        if observed_identity != attempt.lane_identity:
            return result, (
                "lane returned an identity different from its pinned configuration: "
                f"{observed_identity!r}"
            )
        return result, None

    def _run_attempt(
        self,
        run_root: Path,
        scenario: Scenario,
        lane_name: str,
        repetition: int,
    ) -> _Attempt:
        attempt = self._new_attempt(run_root, scenario, lane_name, repetition)
        started = time.monotonic()
        try:
            result, error = self._invoke_lane(attempt, resume=False)
        except _SimulatedInterruption as interruption:
            result, error = interruption.partial, "lane interrupted outside a drill"
        attempt.lane_result = result
        attempt.lane_error = error
        attempt.check = self._run_checker(scenario, attempt.workspace)
        attempt.latency_seconds = time.monotonic() - started
        attempt.workspace_digest = tree_digest(attempt.workspace)
        return attempt

    def _run_recovery_drill(
        self,
        run_root: Path,
        scenario: Scenario,
        lane_name: str,
        repetition: int,
        baseline_digest: str | None,
    ) -> _Attempt:
        attempt = self._new_attempt(run_root, scenario, lane_name, repetition)
        lane = self.lanes[lane_name]
        started = time.monotonic()

        drill: dict[str, object] = {
            "attempted": False,
            "interrupted": False,
            "resumed": False,
            "recovered": False,
            "reason": "lane does not support scripted interruption",
        }

        if not hasattr(lane, "interrupt_after_checkpoint"):
            attempt.lane_result, attempt.lane_error = self._invoke_lane(
                attempt, resume=False
            )
        else:
            drill["attempted"] = True
            drill["reason"] = None
            interrupted_cost = 0
            interrupted = False
            lane.interrupt_after_checkpoint = True
            try:
                result, error = self._invoke_lane(attempt, resume=False)
            except _SimulatedInterruption as interruption:
                interrupted = True
                interrupted_cost = interruption.partial.cost_units
                result, error = None, None
            finally:
                lane.interrupt_after_checkpoint = False

            if not interrupted:
                attempt.lane_result = result
                attempt.lane_error = error
                drill["reason"] = "lane ignored the scripted interruption"
            else:
                drill["interrupted"] = True
                drill["interrupted_cost_units"] = interrupted_cost
                result, error = self._invoke_lane(attempt, resume=True)
                if result is not None:
                    result = LaneResult(
                        status=result.status,
                        roles_exercised=result.roles_exercised,
                        human_interventions=result.human_interventions,
                        cost_units=result.cost_units + interrupted_cost,
                        artifacts=result.artifacts,
                    )
                    drill["resumed"] = True
                attempt.lane_result = result
                attempt.lane_error = error

        attempt.check = self._run_checker(scenario, attempt.workspace)
        attempt.latency_seconds = time.monotonic() - started
        attempt.workspace_digest = tree_digest(attempt.workspace)
        if drill["interrupted"] and drill["resumed"]:
            drill["baseline_workspace_digest"] = baseline_digest
            drill["resumed_workspace_digest"] = attempt.workspace_digest
            drill["recovered"] = bool(
                baseline_digest is not None
                and attempt.workspace_digest == baseline_digest
            )
        attempt.drill = drill
        return attempt

    def _run_checker(self, scenario: Scenario, workspace: Path) -> dict[str, object]:
        environment = {
            key: value for key, value in os.environ.items() if key != "PYTHONPATH"
        }
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        record: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "scenario_id": scenario.scenario_id,
            "checker_digest": scenario.checker_digest(),
            "timeout_seconds": CHECKER_TIMEOUT_SECONDS,
        }
        try:
            completed = subprocess.run(
                [sys.executable, "-B", "-c", scenario.checker],
                cwd=workspace,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                shell=False,
                timeout=CHECKER_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            record.update(
                {
                    "passed": False,
                    "timed_out": True,
                    "returncode": None,
                    "stdout": _decode(error.stdout),
                    "stderr": _decode(error.stderr),
                }
            )
            return record
        record.update(
            {
                "passed": completed.returncode == 0,
                "timed_out": False,
                "returncode": completed.returncode,
                "stdout": _decode(completed.stdout),
                "stderr": _decode(completed.stderr),
            }
        )
        return record

    def _finalize_attempt(
        self,
        run_root: Path,
        attempt: _Attempt,
        recovery: bool,
    ) -> dict[str, object]:
        result = attempt.lane_result
        roles_exercised = tuple(result.roles_exercised) if result else ()
        required = set(attempt.scenario.required_roles)
        role_coverage = len(set(roles_exercised) & required) / len(required)
        status = "failed" if (result is None or attempt.lane_error) else result.status
        lane_report = {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": attempt.attempt_id,
            "lane": attempt.lane_name,
            "lane_identity": attempt.lane_identity,
            "scenario_id": attempt.scenario.scenario_id,
            "repetition": attempt.repetition,
            "status": status,
            "roles_exercised": list(roles_exercised),
            "required_roles": list(attempt.scenario.required_roles),
            "human_interventions": result.human_interventions if result else 0,
            "cost_units": result.cost_units if result else 0,
            "error": attempt.lane_error,
            "recovery_drill": attempt.drill,
        }
        _write_json(attempt.attempt_root / "lane-report.json", lane_report)
        _write_json(attempt.attempt_root / "check.json", attempt.check)

        lane_artifacts: dict[str, str] = {}
        if result:
            for relpath, content in result.artifacts.items():
                if relpath in ATTEMPT_ARTIFACTS:
                    continue
                target = attempt.attempt_root / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
                lane_artifacts[relpath] = _digest_bytes(target.read_bytes())

        checkpoint_path = attempt.attempt_root / "checkpoint.json"
        checkpoint_recorded = False
        if checkpoint_path.is_file():
            try:
                state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = None
            checkpoint_recorded = isinstance(state, dict) and bool(state.get("stage"))
        else:
            # Retention is unconditional: a lane that crashed before checkpointing
            # still gets the full four-artifact inventory, marked as absent.
            _write_json(
                checkpoint_path,
                {
                    "schema_version": SCHEMA_VERSION,
                    "lane": attempt.lane_identity,
                    "scenario_id": attempt.scenario.scenario_id,
                    "stage": None,
                    "recorded": False,
                    "note": "lane produced no checkpoint before it stopped",
                },
            )

        evidence_completeness = checkpoint_recorded and all(
            (attempt.attempt_root / name).is_file()
            and (attempt.attempt_root / name).stat().st_size > 0
            for name in ("lane-report.json", "check.json", "checkpoint.json")
        )

        metrics = AttemptMetrics(
            correctness=bool(attempt.check.get("passed", False))
            and status == "succeeded",
            human_interventions=result.human_interventions if result else 0,
            role_coverage=role_coverage,
            recovery=bool(recovery),
            evidence_completeness=bool(evidence_completeness),
            cost_units=result.cost_units if result else 0,
            latency_seconds=attempt.latency_seconds,
        )
        _write_json(attempt.attempt_root / "metrics.json", metrics.to_dict())

        artifacts = {}
        for name in ATTEMPT_ARTIFACTS:
            path = attempt.attempt_root / name
            if not path.is_file():
                raise RuntimeError(f"attempt artifact was not retained: {name}")
            artifacts[name] = _digest_bytes(path.read_bytes())

        return {
            "schema_version": SCHEMA_VERSION,
            "attempt_id": attempt.attempt_id,
            "scenario_id": attempt.scenario.scenario_id,
            "repetition": attempt.repetition,
            "lane": attempt.lane_name,
            "lane_identity": attempt.lane_identity,
            "lane_status": status,
            "error": attempt.lane_error,
            "roles_exercised": list(roles_exercised),
            "required_roles": list(attempt.scenario.required_roles),
            "scenario_digest": attempt.scenario.digest(),
            "fixture_digest": attempt.scenario.fixture_digest,
            "checker_digest": attempt.scenario.checker_digest(),
            "workspace_digest": attempt.workspace_digest,
            "check_passed": bool(attempt.check.get("passed", False)),
            "check_timed_out": bool(attempt.check.get("timed_out", False)),
            "recovery_drill": attempt.drill,
            "metrics": metrics.to_dict(),
            "artifacts": artifacts,
            "lane_artifacts": lane_artifacts,
            "attempt_dir": (attempt.attempt_root.relative_to(run_root)).as_posix(),
        }

    def _statistics(
        self,
        records: Sequence[Mapping[str, object]],
    ) -> dict[str, object]:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]
        statistics: dict[str, object] = {}
        for lane_index, lane_name in enumerate(self.lane_names):
            lane_records = [
                record for record in records if record["lane"] == lane_name
            ]
            metrics = [dict(record["metrics"]) for record in lane_records]  # type: ignore[arg-type]
            outcomes = [bool(entry["correctness"]) for entry in metrics]
            rate, lower, upper = bootstrap_interval(outcomes, seed=self.seed + lane_index)
            per_scenario: dict[str, object] = {}
            for scenario_index, scenario_id in enumerate(scenario_ids):
                scenario_metrics = [
                    dict(record["metrics"])  # type: ignore[arg-type]
                    for record in lane_records
                    if record["scenario_id"] == scenario_id
                ]
                if not scenario_metrics:
                    continue
                scenario_outcomes = [
                    bool(entry["correctness"]) for entry in scenario_metrics
                ]
                s_rate, s_lower, s_upper = bootstrap_interval(
                    scenario_outcomes,
                    seed=self.seed + lane_index * 1000 + scenario_index + 1,
                )
                per_scenario[scenario_id] = {
                    "attempts": len(scenario_outcomes),
                    "correctness_rate": s_rate,
                    "ci95": [s_lower, s_upper],
                    "role_coverage_mean": _mean(
                        [float(entry["role_coverage"]) for entry in scenario_metrics]
                    ),
                }
            statistics[lane_name] = {
                "identity": self.lane_identities[lane_name],
                "attempts": len(outcomes),
                "correctness_rate": rate,
                "correctness_ci95": [lower, upper],
                "human_interventions_mean": _mean(
                    [float(entry["human_interventions"]) for entry in metrics]
                ),
                "role_coverage_mean": _mean(
                    [float(entry["role_coverage"]) for entry in metrics]
                ),
                "recovery_rate": _mean([float(entry["recovery"]) for entry in metrics]),
                "evidence_completeness_rate": _mean(
                    [float(entry["evidence_completeness"]) for entry in metrics]
                ),
                "cost_units_mean": _mean(
                    [float(entry["cost_units"]) for entry in metrics]
                ),
                "latency_seconds_mean": _mean(
                    [float(entry["latency_seconds"]) for entry in metrics]
                ),
                "per_scenario": per_scenario,
            }
        return statistics

    # -- rendering -------------------------------------------------------

    @staticmethod
    def render_results(report: Mapping[str, object]) -> str:
        statistics = report["statistics"]
        assert isinstance(statistics, dict)
        verdict = report["verdict"]
        assert isinstance(verdict, dict)
        scenarios = report["scenarios"]
        assert isinstance(scenarios, list)

        lines = [
            "# Hive Cortex autonomy benchmark — recorded measurements",
            "",
            "One local run of the offline, toolchain-free hive-cortex benchmark. "
            "Every number below was produced by the reproduction command in the "
            "next section; nothing here is estimated or projected.",
            "",
            f"- Run id: `{report['run_id']}`",
            f"- Court disposition: `{MEASUREMENT_DISPOSITION}`",
            f"- Seed: {report['seed']}",
            f"- Repetitions per scenario and lane: {report['repetitions']}",
            f"- Attempts recorded: {report['attempts']}",
            f"- Corpus digest: `{report['corpus_digest']}`",
            f"- Runner digest: `{report['runner_digest']}`",
            f"- Comparator registry digest: `{report['comparators_digest']}`",
            f"- Results digest (latency-neutral): `{report['results_digest']}`",
            "",
            "## Reproduction",
            "",
            "```bash",
            str(report["reproduction_command"]),
            "```",
            "",
            "`<output-dir>` must be outside the repository tree: run outputs are "
            "evidence, not source, and are deliberately not committed. Every raw "
            "attempt artifact "
            f"(`{'`, `'.join(str(name) for name in report['attempt_artifacts'])}`) "
            "is regenerated by that command, together with `raw-results.jsonl`, "
            "`raw-results.digest-input.jsonl`, `verdict.json`, and `summary.json`.",
            "",
            "The results digest is taken over `raw-results.digest-input.jsonl`: a "
            "canonical copy of `raw-results.jsonl` in which every "
            "`latency_seconds` value is set to `0` and the recorded sha256 of "
            "each `metrics.json` is replaced by the sha256 that file would carry "
            "at zero latency. Without that second substitution the digest would "
            "still drift between runs, because `metrics.json` embeds the measured "
            "latency. Every other measured dimension remains digest-bound. The "
            "digest also binds the on-disk fixture bytes; see the reproducibility "
            "note at the end of this document.",
            "",
            "## Seven measured dimensions, per lane",
            "",
            "| Lane | Identity | Attempts | Correctness | Seeded bootstrap 95% CI "
            "| Human interventions (mean) | Role coverage (mean) | Recovery rate "
            "| Evidence completeness | Cost units (mean) "
            "| Latency s (mean; informational, excluded from digests) |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for lane, value in statistics.items():
            assert isinstance(value, dict)
            lower, upper = value["correctness_ci95"]
            lines.append(
                f"| {lane} | `{value['identity']}` | {value['attempts']} "
                f"| {value['correctness_rate']:.3f} | [{lower:.3f}, {upper:.3f}] "
                f"| {value['human_interventions_mean']:.3f} "
                f"| {value['role_coverage_mean']:.3f} "
                f"| {value['recovery_rate']:.3f} "
                f"| {value['evidence_completeness_rate']:.3f} "
                f"| {value['cost_units_mean']:.3f} "
                f"| {value['latency_seconds_mean']:.3f} |"
            )
        lines.extend(
            [
                "",
                "Latency is informational and is excluded from every digest. "
                "Correctness, human interventions, role coverage, recovery, "
                "evidence completeness, and cost are all digest-bound.",
                "",
                "**What these rates do and do not measure.** Both lanes are "
                "deterministic in-repository programs, not language models. The "
                "scripted lane applies each scenario's recorded patch; the null "
                "control applies none. The correctness column therefore measures "
                "whether the scenario checkers discriminate a patched workspace "
                "from an unpatched one, and whether the harness records that "
                "outcome reproducibly. It is not a measure of any agent's "
                "problem-solving ability, and the degenerate confidence intervals "
                "are a direct consequence of deterministic lanes.",
                "",
                "## Per-scenario correctness",
                "",
            ]
        )
        for lane, value in statistics.items():
            assert isinstance(value, dict)
            per_scenario = value["per_scenario"]
            assert isinstance(per_scenario, dict)
            lines.extend(
                [
                    f"### {lane}",
                    "",
                    "| Scenario | Attempts | Correctness | Seeded bootstrap 95% CI "
                    "| Role coverage (mean) |",
                    "|---|---:|---:|---:|---:|",
                ]
            )
            for scenario_id, entry in per_scenario.items():
                assert isinstance(entry, dict)
                lower, upper = entry["ci95"]
                lines.append(
                    f"| {scenario_id} | {entry['attempts']} "
                    f"| {entry['correctness_rate']:.3f} "
                    f"| [{lower:.3f}, {upper:.3f}] "
                    f"| {entry['role_coverage_mean']:.3f} |"
                )
            lines.append("")

        lines.extend(
            [
                "## Scenario corpus",
                "",
                "| Scenario | Required roles | Fixture digest | Checker digest |",
                "|---|---|---|---|",
            ]
        )
        for entry in scenarios:
            assert isinstance(entry, dict)
            roles = ", ".join(str(role) for role in entry["required_roles"])
            lines.append(
                f"| {entry['scenario_id']} | {roles} "
                f"| `{entry['fixture_digest']}` | `{entry['checker_digest']}` |"
            )

        lines.extend(
            [
                "",
                "## Comparator registry",
                "",
                "| Name | source_id | Pin | License | Availability | Reason |",
                "|---|---|---|---|---|---|",
            ]
        )
        comparators = verdict["comparators"]
        assert isinstance(comparators, list)
        for entry in comparators:
            assert isinstance(entry, dict)
            pin = f"`{entry['pin']}`" if entry["pin"] else "—"
            license_name = f"`{entry['license']}`" if entry["license"] else "—"
            reason = str(entry["reason"]) if entry["reason"] else "—"
            lines.append(
                f"| {entry['name']} | `{entry['source_id']}` | {pin} "
                f"| {license_name} | `{entry['availability']}` | {reason} |"
            )

        lines.extend(
            [
                "",
                "Only the two in-repository lanes are pinned. No external system "
                "was executed here, so none of them carries an invented pin or "
                "license; each is recorded as `unavailable` with its reason. "
                "Nothing in this table supports ranking one system against "
                "another.",
                "",
                "## Court",
                "",
                f"- Judge: `{verdict['judge_id']}`",
                f"- Disposition: `{verdict['disposition']}` "
                "(the only disposition this court can express)",
                f"- Lane identities: "
                + ", ".join(f"`{name}`" for name in verdict["lane_identities"]),
                f"- Results digest: `{verdict['results_digest']}`",
                "",
                "Obligations recorded with the verdict:",
                "",
            ]
        )
        for obligation in verdict["obligations"]:
            lines.append(f"- {obligation}")

        lines.extend(
            [
                "",
                "## Reproducibility notes",
                "",
                "- The run id is derived from the scenario digests, the lane "
                "identities, the seed, the repetition count, and the sha256 of "
                "`runner.py`. Editing any of those produces a different run id.",
                "- Fixture digests bind the fixture bytes as checked out. "
                "`.gitattributes` pins `*.py`, `*.json`, and `*.md` to LF but not "
                "`*.js` or `*.cs`, and this repository sets `core.autocrlf=true`, "
                "so a Windows checkout and a POSIX checkout produce different "
                "fixture digests and therefore a different run id for the same "
                "source. The measurements themselves are unaffected: the "
                "`no-test-csharp` checker records the digest of the fixture as "
                "loaded rather than a hard-coded constant.",
                "- The recorded run was executed on Windows. Cross-platform "
                "digest equality has not been measured here and is not claimed.",
                "",
                "## Claim policy",
                "",
                str(court.DISCLAIMER),
                "",
            ]
        )
        return "\n".join(lines)


def _decode(payload: bytes | None) -> str:
    if not payload:
        return ""
    return payload.decode("utf-8", "replace")


def _zero_latency(value: object) -> object:
    """Return a copy of *value* with every ``latency_seconds`` set to ``0``."""

    if isinstance(value, dict):
        return {
            key: (0 if key == "latency_seconds" else _zero_latency(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_zero_latency(item) for item in value]
    return copy.copy(value)


def _digest_input_record(record: Mapping[str, object]) -> dict[str, object]:
    """Return the latency-neutral copy of an attempt record.

    Zeroing ``latency_seconds`` in the record is not sufficient on its own:
    ``metrics.json`` contains the measured latency, so its on-disk sha256 —
    recorded under ``artifacts`` — differs between two otherwise identical
    runs. The digest input substitutes the sha256 that file would carry if
    latency were zero. Every other metric still binds the digest, because the
    full metrics mapping is itself part of the record.
    """

    neutral = _zero_latency(record)
    assert isinstance(neutral, dict)
    metrics = neutral.get("metrics")
    artifacts = neutral.get("artifacts")
    if (
        isinstance(metrics, dict)
        and isinstance(artifacts, dict)
        and "metrics.json" in artifacts
    ):
        artifacts["metrics.json"] = _digest_bytes(_canonical_bytes(metrics) + b"\n")
    return neutral


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="hive-cortex-benchmark",
        description="Run the hive-cortex autonomy benchmark and record evidence.",
    )
    parser.add_argument("--output", required=True, help="run output root (outside the repo)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument(
        "--render",
        default=None,
        help="write the rendered results document to this path",
    )
    arguments = parser.parse_args(argv)

    benchmark = HiveCortexBenchmark(
        REPO_ROOT,
        seed=arguments.seed,
        repetitions=arguments.repetitions,
    )
    report = benchmark.run(Path(arguments.output))

    if arguments.render:
        text = HiveCortexBenchmark.render_results(report)
        violations = court.guard_results_document(text)
        if violations:
            for violation in violations:
                print(f"claim guard: {violation}", file=sys.stderr)
            return 2
        target = Path(arguments.render)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        print(f"rendered {target}")

    print(f"run_id            {report['run_id']}")
    print(f"attempts          {report['attempts']}")
    print(f"corpus_digest     {report['corpus_digest']}")
    print(f"runner_digest     {report['runner_digest']}")
    print(f"results_digest    {report['results_digest']}")
    return 0


__all__ = [
    "ATTEMPT_ARTIFACTS",
    "AttemptMetrics",
    "CHECKER_TIMEOUT_SECONDS",
    "HiveCortexBenchmark",
    "LaneResult",
    "METRIC_DIMENSIONS",
    "NullBaselineLane",
    "REPRODUCTION_COMMAND",
    "Scenario",
    "ScenarioError",
    "ScriptedHiveCortexLane",
    "court",
    "load_scenarios",
    "main",
    "tree_digest",
]


if __name__ == "__main__":
    raise SystemExit(main())
