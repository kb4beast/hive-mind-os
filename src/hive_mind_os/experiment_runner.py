"""Prompt champion/challenger experiments driven by the recursive-improvement gate."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence
from uuid import uuid4

from .ledger import EvidenceLedger
from .models import Role, utc_now
from .pit_oracle import PointInTimeOracle
from .prompt_registry import PromptRegistry
from .receipts import sha256_digest
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
    """Deterministic offline prompt-contract checks over fixture missions."""

    name: str = "fixture-missions"
    episode_ids: tuple[str, ...] = (
        "fixture:repair-regression",
        "fixture:preserve-evidence",
        "fixture:bounded-delivery",
    )

    def evaluate(
        self,
        prompt: str,
        role: Role,
        repetition: int,
    ) -> SurfaceObservation:
        contract = ROLE_CONTRACTS[role]
        checks = (
            ("Return only a JSON object" in prompt, 0.25),
            (f"role {role.value}" in prompt, 0.10),
            (all(name in prompt for name in contract.required_outputs), 0.25),
            (all(gate in prompt for gate in contract.quality_gates), 0.20),
            ("verify every required output" in prompt.casefold(), 0.10),
            ("receipt" in prompt.casefold(), 0.10),
        )
        success = round(sum(weight for passed, weight in checks if passed), 6)
        complete = float(
            all(name in prompt for name in contract.required_outputs)
            and all(gate in prompt for gate in contract.quality_gates)
        )
        return SurfaceObservation(
            task_success=success,
            token_cost=max(1.0, len(prompt.encode("utf-8")) / 4.0),
            evidence_completeness=complete,
            artifact_refs=tuple(
                f"{episode}:repetition-{repetition}" for episode in self.episode_ids
            ),
        )


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
                f"{record_path.as_posix()}#{sha256_digest(record_path.read_bytes())}"
            )
            completeness.append(
                float(
                    bool(document.get("receipts"))
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
                    f"prompt:{champion_digest}",
                    f"prompt:{challenger_digest}",
                    *(
                        reference
                        for result in (*champion_results, *challenger_results)
                        for reference in result.artifact_refs
                    ),
                )
            )
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

        champion_after = champion_digest
        if decision.verdict is ExperimentVerdict.KEEP:
            self.registry.promote(
                role_value,
                challenger_digest,
                promoted_by=evaluator_id,
                experiment_id=experiment_id,
                expected_current=champion_digest,
            )
            champion_after = challenger_digest
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
            },
            "champion_before": champion_digest,
            "challenger_digest": challenger_digest,
            "champion_after": champion_after,
            "observations": [
                {
                    "metric_name": item.metric_name,
                    "baseline_samples": list(item.baseline_samples),
                    "candidate_samples": list(item.candidate_samples),
                }
                for item in observations
            ],
            "artifact_refs": list(artifact_refs),
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
        )

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
