"""Prompt champion/challenger experiments driven by the recursive-improvement gate."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence
from uuid import uuid4

from .acceptance import AcceptanceSpecification
from .ledger import EvidenceLedger
from .mission import RepositoryMission, ScriptedRepositoryBackend
from .models import Role, WorkStatus, utc_now
from .pit_oracle import PointInTimeOracle
from .prompt_registry import PromptRegistry
from .receipts import FileReceiptValidator, ReceiptReference, sha256_digest
from .recursive_improvement import (
    ExperimentCandidate,
    ExperimentDecision,
    ExperimentEvidence,
    ExperimentVerdict,
    MetricDirection,
    MetricObservation,
    MetricSpec,
    RecursiveImprovementContract,
    RecursiveImprovementGate,
)
from .roles import ROLE_CONTRACTS

SCRIPTED_EVALUATOR_ID = "evaluator:scripted-harness"
SCRIPTED_JUDGE_ID = "judge:recursive-improvement"


@dataclass(frozen=True, slots=True)
class SurfaceObservation:
    task_success: float
    token_cost: float
    evidence_completeness: float
    artifact_refs: tuple[str, ...]


class EvaluationSurface(Protocol):
    name: str
    episode_ids: tuple[str, ...]

    def evaluate(
        self,
        prompt: str,
        role: Role,
        repetition: int,
    ) -> SurfaceObservation: ...


class FixtureMissionSurface:
    """Deterministic prompt checks backed by real P05 fixture missions and receipts."""

    name: str = "fixture-missions"
    episode_ids: tuple[str, ...] = (
        "fixture:repair-regression",
        "fixture:preserve-evidence",
        "fixture:bounded-delivery",
    )

    def __init__(
        self,
        artifact_root: str | Path = ".hive-mind-experiments/fixture-missions",
    ) -> None:
        self.artifact_root = Path(artifact_root).resolve() / uuid4().hex[:12]
        self.artifact_root.mkdir(parents=True, exist_ok=False)
        self._mission_cache: dict[
            int,
            tuple[float, float, tuple[str, ...]],
        ] = {}

    def evaluate(
        self,
        prompt: str,
        role: Role,
        repetition: int,
    ) -> SurfaceObservation:
        mission_success, completeness, artifact_refs = self._mission_observation(
            repetition
        )
        contract = ROLE_CONTRACTS[role]
        checks = (
            ("Return only a JSON object" in prompt, 0.25),
            (f"role {role.value}" in prompt, 0.10),
            (all(name in prompt for name in contract.required_outputs), 0.25),
            (all(gate in prompt for gate in contract.quality_gates), 0.20),
            ("verify every required output" in prompt.casefold(), 0.10),
            ("receipt" in prompt.casefold(), 0.10),
        )
        prompt_score = sum(weight for passed, weight in checks if passed)
        success = round(
            0.5 * mission_success + 0.5 * prompt_score,
            6,
        )
        return SurfaceObservation(
            task_success=success,
            token_cost=max(1.0, len(prompt.encode("utf-8")) / 4.0),
            evidence_completeness=completeness,
            artifact_refs=artifact_refs,
        )

    def _mission_observation(
        self,
        repetition: int,
    ) -> tuple[float, float, tuple[str, ...]]:
        cached = self._mission_cache.get(repetition)
        if cached is not None:
            return cached
        episode_root = self.artifact_root / str(repetition)
        episode_root.mkdir(parents=True, exist_ok=False)
        output_root = episode_root / "d"
        with tempfile.TemporaryDirectory(prefix="hmos-p10-") as temporary:
            repository, pin = _build_fixture_repository(Path(temporary))
            report = asyncio.run(
                RepositoryMission(
                    repository,
                    "Fix the failing increment regression",
                    acceptance_criteria=("increment(1) returns 2",),
                    acceptance_specifications=(
                        AcceptanceSpecification(
                            "increment-returns-two",
                            "increment(1) returns 2",
                            (
                                sys.executable,
                                "-B",
                                "-c",
                                "from tiny_pkg.maths import increment; assert increment(1) == 2",
                            ),
                        ),
                    ),
                    backend=ScriptedRepositoryBackend(),
                    pin=pin,
                    output_dir=output_root,
                ).run()
            )
        report_root = report.artifact_directory or report.receipt_root
        report_path = (
            None if report_root is None else Path(report_root) / "mission-report.json"
        )
        receipt_complete, receipt_paths = _validate_receipt_records(
            report.receipt_root,
            report.receipts,
        )
        mission_complete = (
            report.status is WorkStatus.SUCCEEDED
            and report.curator_verdict == "adopt"
            and report_path is not None
            and report_path.is_file()
            and receipt_complete
        )
        retained_paths = list(receipt_paths)
        if report_path is not None and report_path.is_file():
            retained_paths.insert(
                0,
                (report_path, sha256_digest(report_path.read_bytes())),
            )
        references = tuple(
            _artifact_reference(path, digest)
            for path, digest in retained_paths
        )
        observation = (
            float(report.status is WorkStatus.SUCCEEDED),
            float(mission_complete),
            references,
        )
        self._mission_cache[repetition] = observation
        return observation


class PITEpisodeSurface:
    """Run pinned P09 targets and expose their recorded grades to the gate."""

    name = "pit-episodes"

    def __init__(
        self,
        oracle: PointInTimeOracle,
        target_shas: Sequence[str],
        *,
        self_history: bool = False,
    ) -> None:
        if not target_shas:
            raise ValueError("PIT evaluation requires pinned target SHAs")
        self.oracle = oracle
        self.episode_ids = tuple(target_shas)
        self.self_history = self_history

    def evaluate(
        self,
        prompt: str,
        role: Role,
        repetition: int,
    ) -> SurfaceObservation:
        grades: list[float] = []
        references: list[str] = []
        completeness: list[float] = []
        for target_sha in self.episode_ids:
            record_path = self.oracle.run_scripted_episode(
                target_sha,
                self_history=self.self_history,
            )
            document = json.loads(record_path.read_text(encoding="utf-8"))
            grades.append(float(document["grade"]["score"]))
            references.append(
                _artifact_reference(
                    record_path,
                    sha256_digest(record_path.read_bytes()),
                )
            )
            receipts_valid, receipt_paths = _validate_receipt_records(
                document.get("receipt_root"),
                document.get("receipts"),
            )
            references.extend(
                _artifact_reference(path, digest)
                for path, digest in receipt_paths
            )
            completeness.append(
                float(
                    receipts_valid
                    and bool(document.get("ledger_events"))
                    and bool(document.get("prediction"))
                )
            )
        return SurfaceObservation(
            task_success=sum(grades) / len(grades),
            token_cost=max(1.0, len(prompt.encode("utf-8")) / 4.0),
            evidence_completeness=min(completeness),
            artifact_refs=tuple(references),
        )


def default_prompt_contract(repetitions: int) -> RecursiveImprovementContract:
    return RecursiveImprovementContract(
        primary=MetricSpec(
            "task_success_rate",
            MetricDirection.MAXIMIZE,
            minimum_effect=0.01,
        ),
        guardrails=(
            MetricSpec(
                "token_cost",
                MetricDirection.MINIMIZE,
                maximum_regression=64.0,
                hard_guardrail=True,
            ),
            MetricSpec(
                "evidence_completeness",
                MetricDirection.MAXIMIZE,
                maximum_regression=0.0,
                hard_guardrail=True,
            ),
        ),
        minimum_repetitions=repetitions,
        noise_multiplier=2.0,
        patience=3,
        max_experiments=25,
    )


@dataclass(frozen=True, slots=True)
class ExperimentRun:
    experiment_id: str
    decision: ExperimentDecision
    evidence_path: Path
    champion_before: str
    champion_after: str
    challenger_digest: str
    promotion_pending: bool


class ExperimentRunner:
    def __init__(
        self,
        registry: PromptRegistry,
        evidence_root: str | Path,
        *,
        ledger: EvidenceLedger | None = None,
        state_path: str | Path | None = None,
    ) -> None:
        self.registry = registry
        self.evidence_root = Path(evidence_root).resolve()
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self.ledger = ledger or registry.ledger
        self.state_path = Path(state_path).resolve() if state_path else None

    def run(
        self,
        role: Role | str,
        challenger: str | bytes,
        *,
        surface: EvaluationSurface,
        repetitions: int,
        author_id: str = "author:cli",
        builder_id: str = "builder:prompt-registry",
        evaluator_id: str = SCRIPTED_EVALUATOR_ID,
        judge_id: str = SCRIPTED_JUDGE_ID,
        contract: RecursiveImprovementContract | None = None,
    ) -> ExperimentRun:
        role_value = Role(role)
        if repetitions < 2:
            raise ValueError("experiments require at least two repetitions")
        active_contract = contract or default_prompt_contract(repetitions)
        if active_contract.minimum_repetitions > repetitions:
            raise ValueError("repetitions do not satisfy the experiment contract")
        champion_prompt, champion_digest = self.registry.champion_prompt(role_value)
        experiment_id = f"EXP-{uuid4()}"
        challenger_digest = self.registry.register(
            role_value,
            challenger,
            parent_digest=champion_digest,
            created_by=author_id,
            experiment_id=experiment_id,
        )
        if challenger_digest == champion_digest:
            raise ValueError("challenger must differ from the active champion")
        prompt_refs = (
            self._retain_prompt_artifact(
                experiment_id,
                champion_digest,
                champion_prompt.encode("utf-8"),
            ),
            self._retain_prompt_artifact(
                experiment_id,
                challenger_digest,
                self.registry.read(challenger_digest).encode("utf-8"),
            ),
        )

        state = self._read_state()
        role_state = state.setdefault(
            role_value.value,
            {"experiments_completed": 0, "consecutive_non_improvements": 0},
        )
        start_sequence = self.ledger.append_event(
            experiment_id,
            "experiment.started",
            "optimizer",
            {
                "role": role_value.value,
                "contract_fingerprint": active_contract.fingerprint,
                "champion_digest": champion_digest,
                "challenger_digest": challenger_digest,
                "surface": surface.name,
                "episode_ids": list(surface.episode_ids),
                "repetitions": repetitions,
                "author_id": author_id,
                "builder_id": builder_id,
                "evaluator_id": evaluator_id,
                "judge_id": judge_id,
            },
        )
        champion_results = [
            surface.evaluate(champion_prompt, role_value, index)
            for index in range(repetitions)
        ]
        challenger_prompt = self.registry.read(challenger_digest)
        challenger_results = [
            surface.evaluate(challenger_prompt, role_value, index)
            for index in range(repetitions)
        ]
        validation_issues = self._validate_observations(
            (*champion_results, *challenger_results)
        )
        reveal_sequences = self._author_reveal_sequences(
            author_id,
            surface.episode_ids,
        )
        observations = (
            self._metric(
                "task_success_rate",
                champion_results,
                challenger_results,
                "task_success",
            ),
            self._metric(
                "token_cost",
                champion_results,
                challenger_results,
                "token_cost",
            ),
            self._metric(
                "evidence_completeness",
                champion_results,
                challenger_results,
                "evidence_completeness",
            ),
        )
        artifact_refs = tuple(
            dict.fromkeys(
                (
                    *prompt_refs,
                    *(
                        reference
                        for result in (*champion_results, *challenger_results)
                        for reference in result.artifact_refs
                    ),
                )
            )
        )
        identities = (author_id, builder_id, evaluator_id, judge_id)
        if any(not identity.strip() for identity in identities):
            validation_issues = (
                *validation_issues,
                "experiment identities must be nonempty",
            )
        elif len(set(identities)) != 4:
            validation_issues = (
                *validation_issues,
                "experiment requires four distinct proposer, builder, evaluator, "
                "and judge identities",
            )
        evidence = ExperimentEvidence(
            candidate=ExperimentCandidate(
                id=challenger_digest,
                parent_champion_id=champion_digest,
                hypothesis="a versioned role prompt improves repeated evaluation outcomes",
                changed_paths=(f"prompt:{role_value.value}",),
                rollback_ref=champion_digest,
            ),
            contract_fingerprint=active_contract.fingerprint,
            proposer_id=author_id,
            builder_id=builder_id,
            evaluator_id=evaluator_id,
            observations=observations,
            artifact_refs=artifact_refs,
            accessed_holdout=bool(reveal_sequences),
            policy_violations=validation_issues,
        )
        decision = RecursiveImprovementGate(active_contract).evaluate(
            evidence,
            consecutive_non_improvements=int(
                role_state["consecutive_non_improvements"]
            ),
            experiments_completed=int(role_state["experiments_completed"]),
        )
        role_state["experiments_completed"] = int(role_state["experiments_completed"]) + 1
        role_state["consecutive_non_improvements"] = (
            decision.next_non_improvement_count
        )

        evaluation_sequence = self.ledger.append_event(
            experiment_id,
            "experiment.evaluation",
            evaluator_id,
            {
                "verdict": decision.verdict.value,
                "role": role_value.value,
                "candidate_digest": challenger_digest,
                "current_digest": champion_digest,
                "registration_experiment_id": experiment_id,
                "registration_role": role_value.value,
                "registration_author": author_id,
                "registration_parent_digest": champion_digest,
                "proposer_id": author_id,
                "builder_id": builder_id,
                "evaluator_id": evaluator_id,
                "judge_id": judge_id,
                "retained_artifact_refs": list(artifact_refs),
                "contract_fingerprint": active_contract.fingerprint,
                "reasons": list(decision.reasons),
            },
        )
        champion_after = champion_digest
        promotion_pending = decision.verdict is ExperimentVerdict.KEEP
        if decision.verdict is ExperimentVerdict.KEEP:
            self.ledger.append_event(
                experiment_id,
                "experiment.promotion_appeal",
                "optimizer:recursive-improvement",
                {
                    "role": role_value.value,
                    "candidate_digest": challenger_digest,
                    "current_digest": champion_digest,
                    "evaluation_event_sequence": evaluation_sequence,
                    "requested_judge_id": judge_id,
                    "retained_artifact_refs": list(artifact_refs),
                    "contract_fingerprint": active_contract.fingerprint,
                    "status": "pending-independent-court",
                },
            )
        elif decision.verdict is ExperimentVerdict.QUARANTINE:
            self.registry.quarantine(
                role_value,
                challenger_digest,
                actor=evaluator_id,
                experiment_id=experiment_id,
                reasons=decision.reasons,
            )

        close_sequence = self.ledger.append_event(
            experiment_id,
            "experiment.closed",
            evaluator_id,
            {
                "verdict": decision.verdict.value,
                "reasons": list(decision.reasons),
                "champion_before": champion_digest,
                "champion_after": champion_after,
                "promotion_pending": promotion_pending,
                "holdout_ordering_valid": not reveal_sequences,
            },
        )
        record = {
            "schema_version": 1,
            "experiment_id": experiment_id,
            "recorded_at": utc_now(),
            "role": role_value.value,
            "surface": surface.name,
            "episode_ids": list(surface.episode_ids),
            "repetitions": repetitions,
            "contract": {
                "fingerprint": active_contract.fingerprint,
                "primary": active_contract.primary.name,
                "guardrails": [
                    {
                        "name": metric.name,
                        "direction": metric.direction.value,
                        "maximum_regression": metric.maximum_regression,
                        "hard_guardrail": metric.hard_guardrail,
                    }
                    for metric in active_contract.guardrails
                ],
            },
            "identities": {
                "author": author_id,
                "builder": builder_id,
                "evaluator": evaluator_id,
                "judge": judge_id,
            },
            "champion_before": champion_digest,
            "challenger_digest": challenger_digest,
            "champion_after": champion_after,
            "promotion_pending": promotion_pending,
            "observations": [
                {
                    "metric_name": item.metric_name,
                    "baseline_samples": list(item.baseline_samples),
                    "candidate_samples": list(item.candidate_samples),
                }
                for item in observations
            ],
            "artifact_refs": list(artifact_refs),
            "surface_validation": {
                "complete": not validation_issues,
                "issues": list(validation_issues),
            },
            "holdout_ordering": {
                "valid": not reveal_sequences,
                "author_reveal_sequences": list(reveal_sequences),
                "experiment_start_sequence": start_sequence,
                "experiment_close_sequence": close_sequence,
            },
            "decision": {
                "verdict": decision.verdict.value,
                "reasons": list(decision.reasons),
                "primary_effect": decision.primary_effect,
                "required_effect": decision.required_effect,
                "next_non_improvement_count": decision.next_non_improvement_count,
                "event_sequence": evaluation_sequence,
            },
        }
        evidence_path = self.evidence_root / f"{experiment_id}.json"
        self._write_new_json(evidence_path, record)
        self.ledger.append_event(
            experiment_id,
            "experiment.recorded",
            evaluator_id,
            {
                "path": evidence_path.as_posix(),
                "digest": sha256_digest(evidence_path.read_bytes()),
            },
        )
        self._write_state(state)
        return ExperimentRun(
            experiment_id,
            decision,
            evidence_path,
            champion_digest,
            champion_after,
            challenger_digest,
            promotion_pending,
        )

    def _retain_prompt_artifact(
        self,
        experiment_id: str,
        digest: str,
        content: bytes,
    ) -> str:
        if sha256_digest(content) != digest:
            raise RuntimeError("prompt artifact digest does not match retained bytes")
        path = (
            self.evidence_root
            / "_artifacts"
            / experiment_id
            / "prompts"
            / f"{digest.removeprefix('sha256:')}.txt"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            if path.read_bytes() != content:
                raise RuntimeError("retained prompt artifact was mutated")
        return _artifact_reference(path, digest)

    @staticmethod
    def _validate_observations(
        observations: Sequence[SurfaceObservation],
    ) -> tuple[str, ...]:
        issues: list[str] = []
        for index, observation in enumerate(observations):
            if observation.evidence_completeness != 1.0:
                issues.append(f"surface observation {index} reported incomplete evidence")
            if not observation.artifact_refs:
                issues.append(f"surface observation {index} has no artifact references")
            for reference in observation.artifact_refs:
                issue = _validate_artifact_reference(reference)
                if issue is not None:
                    issues.append(f"surface observation {index}: {issue}")
        return tuple(dict.fromkeys(issues))

    def _author_reveal_sequences(
        self,
        author_id: str,
        episode_ids: Sequence[str],
    ) -> tuple[int, ...]:
        selected = set(episode_ids)
        return tuple(
            int(event["sequence"])
            for event in self.ledger.events()
            if event["event_type"] == "pit.target.revealed"
            and event["actor"] == author_id
            and (
                event["run_id"] in selected
                or event["payload"].get("target_sha") in selected
            )
        )

    @staticmethod
    def _metric(
        name: str,
        baseline: Sequence[SurfaceObservation],
        candidate: Sequence[SurfaceObservation],
        attribute: str,
    ) -> MetricObservation:
        return MetricObservation(
            name,
            tuple(float(getattr(item, attribute)) for item in baseline),
            tuple(float(getattr(item, attribute)) for item in candidate),
        )

    def _read_state(self) -> dict[str, Any]:
        if self.state_path is None or not self.state_path.exists():
            return {}
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise RuntimeError("experiment runner state is malformed")
        return document

    def _write_state(self, state: dict[str, Any]) -> None:
        if self.state_path is not None:
            self._atomic_json(self.state_path, state)

    @staticmethod
    def _write_new_json(path: Path, document: dict[str, Any]) -> None:
        payload = (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)

    @staticmethod
    def _atomic_json(path: Path, document: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _artifact_reference(path: Path, digest: str) -> str:
    resolved = path.resolve()
    try:
        rendered = resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        rendered = resolved.as_posix()
    return f"{rendered}#{digest}"


def _validate_artifact_reference(reference: str) -> str | None:
    raw_path, separator, expected_digest = reference.rpartition("#")
    if not separator or not raw_path or not expected_digest.startswith("sha256:"):
        return "artifact reference must be path#sha256:<digest>"
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        return f"artifact does not resolve: {raw_path}"
    if sha256_digest(path.read_bytes()) != expected_digest:
        return f"artifact digest mismatch: {raw_path}"
    return None


def _validate_receipt_records(
    raw_root: object,
    raw_records: object,
) -> tuple[bool, tuple[tuple[Path, str], ...]]:
    if not isinstance(raw_root, str) or not isinstance(raw_records, (list, tuple)):
        return False, ()
    if not raw_records:
        return False, ()
    try:
        validator = FileReceiptValidator(raw_root)
    except ValueError:
        return False, ()
    paths: list[tuple[Path, str]] = []
    valid = True
    for record in raw_records:
        if not isinstance(record, dict):
            valid = False
            continue
        try:
            reference = ReceiptReference(
                str(record["path"]),
                str(record["digest"]),
            )
            validation = validator.validate(
                reference,
                mission_id=str(record["mission_id"]),
                state_ref=str(record["state_ref"]),
                actor_id=str(record["actor_id"]),
                action_id=str(record["action_id"]),
                action_kind=str(record["action_kind"]),
                action_digest=str(record["action_digest"]),
            )
        except (KeyError, TypeError, ValueError):
            valid = False
            continue
        valid = valid and validation.valid
        paths.append(
            (
                Path(raw_root).resolve() / Path(*reference.path.split("/")),
                reference.digest,
            )
        )
    return valid and len(paths) == len(raw_records), tuple(paths)


def _build_fixture_repository(root: Path) -> tuple[Path, str]:
    repository = root / "repo"
    repository.mkdir(parents=True)
    environment = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_DATE": "2026-01-02T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-02T00:00:00Z",
    }

    def git(*arguments: str) -> str:
        completed = subprocess.run(
            (
                "git",
                "-c",
                "user.name=p10-fixture",
                "-c",
                "user.email=p10-fixture@hive-mind.invalid",
                "-c",
                "core.autocrlf=false",
                "-c",
                "commit.gpgsign=false",
                *arguments,
            ),
            cwd=repository,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "fixture git command failed: "
                + completed.stderr.decode("utf-8", "replace")
            )
        return completed.stdout.decode("utf-8").strip()

    git("init", "--initial-branch=main")
    (repository / "tiny_pkg").mkdir()
    (repository / "tests").mkdir()
    (repository / "tiny_pkg" / "__init__.py").write_text(
        "from .maths import increment\n",
        encoding="utf-8",
        newline="\n",
    )
    (repository / "tiny_pkg" / "maths.py").write_text(
        "def increment(value: int) -> int:\n    return value - 1\n",
        encoding="utf-8",
        newline="\n",
    )
    (repository / "tests" / "test_maths.py").write_text(
        (
            "import unittest\n\n"
            "from tiny_pkg.maths import increment\n\n\n"
            "class MathsTests(unittest.TestCase):\n"
            "    def test_increment_regression(self) -> None:\n"
            "        self.assertEqual(increment(1), 2)\n\n\n"
            'if __name__ == "__main__":\n'
            "    unittest.main()\n"
        ),
        encoding="utf-8",
        newline="\n",
    )
    git("add", "--all")
    git("commit", "-m", "fixture: introduce regression")
    return repository, git("rev-parse", "HEAD")
