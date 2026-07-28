from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from hive_mind_os.experiment_runner import (
    ExperimentRunner,
    PITEpisodeSurface,
    SurfaceObservation,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.model_backend import ModelBackend
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.models import Objective, Role, WorkItem
from hive_mind_os.prompt_registry import (
    PromptRegistry,
    generation_zero_prompt,
    prompt_digest,
)
from hive_mind_os.recursive_improvement import (
    ExperimentVerdict,
    MetricDirection,
    MetricSpec,
    RecursiveImprovementContract,
)
from hive_mind_os.roles import ROLE_CONTRACTS


class RiggedSurface:
    name = "rigged-fixtures"
    episode_ids = ("episode-1", "episode-2")

    def __init__(
        self,
        *,
        baseline: tuple[float, float, float],
        candidate: tuple[float, float, float],
    ) -> None:
        self.baseline = baseline
        self.candidate = candidate

    def evaluate(
        self,
        prompt: str,
        role: Role,
        repetition: int,
    ) -> SurfaceObservation:
        selected = self.candidate if prompt == "challenger" else self.baseline
        return SurfaceObservation(*selected, (f"rigged:{repetition}",))


@dataclass
class FakeProvider:
    responses: list[str]

    def __post_init__(self) -> None:
        self.config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://models.example/v1",
            "fake-model",
            "FAKE_KEY",
            max_retries=0,
        )
        self.kind = ProviderKind.OPENAI_COMPATIBLE
        self.calls: list[ModelRequest] = []

    def build_request_body(self, request: ModelRequest) -> bytes:
        return json.dumps(
            {
                "system": request.system,
                "user": request.user,
                "corrective": request.corrective_message,
            },
            sort_keys=True,
        ).encode("utf-8")

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        content = self.responses.pop(0)
        return ModelResponse(content, content.encode("utf-8"), 10, 5)

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self.complete_once(request)


def valid_turn(role: Role) -> str:
    return json.dumps(
        {
            "summary": "complete",
            "outputs": {
                name: f"evidence for {name}"
                for name in ROLE_CONTRACTS[role].required_outputs
            },
            "proposed_actions": [],
            "lessons": [],
            "success": True,
        }
    )


class ExperimentRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = EvidenceLedger()
        self.registry = PromptRegistry(self.root / "registry", ledger=self.ledger)
        self.champion = self.registry.register(
            Role.BUILDER,
            "champion",
            parent_digest=None,
            created_by="repository:generation-0",
        )
        self.registry.promote(
            Role.BUILDER,
            self.champion,
            promoted_by="repository:generation-0",
            experiment_id="generation-0",
            expected_current=None,
        )
        self.runner = ExperimentRunner(
            self.registry,
            self.root / "evidence",
            state_path=self.root / "runner-state.json",
        )

    def tearDown(self) -> None:
        self.registry.close()
        self.ledger.close()
        self.temporary.cleanup()

    def _surface(
        self,
        baseline: tuple[float, float, float],
        candidate: tuple[float, float, float],
    ) -> RiggedSurface:
        return RiggedSurface(baseline=baseline, candidate=candidate)

    def test_keep_promotes_and_records_complete_lineage(self) -> None:
        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=self._surface((0.4, 10, 1), (0.8, 12, 1)),
            repetitions=3,
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.KEEP)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), result.challenger_digest)
        lineage = self.registry.lineage(result.challenger_digest)
        self.assertTrue(
            any(
                row["kind"] == "promotion"
                and row["parent_digest"] == self.champion
                and row["experiment_id"] == result.experiment_id
                for row in lineage
            )
        )
        event_types = [
            event["event_type"]
            for event in self.ledger.events(result.experiment_id)
        ]
        self.assertEqual(event_types[0], "prompt.registered")
        self.assertIn("experiment.started", event_types)
        self.assertIn("prompt.promoted", event_types)
        self.assertIn("experiment.closed", event_types)
        self.assertIn("experiment.recorded", event_types)

    def test_noise_retests_then_stops_at_patience_without_promotion(self) -> None:
        contract = RecursiveImprovementContract(
            MetricSpec("task_success_rate", MetricDirection.MAXIMIZE, 0.01),
            (
                MetricSpec(
                    "token_cost",
                    MetricDirection.MINIMIZE,
                    maximum_regression=64,
                    hard_guardrail=True,
                ),
                MetricSpec(
                    "evidence_completeness",
                    MetricDirection.MAXIMIZE,
                    hard_guardrail=True,
                ),
            ),
            minimum_repetitions=3,
            patience=2,
        )
        surface = self._surface((0.5, 10, 1), (0.505, 10, 1))
        first = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=surface,
            repetitions=3,
            contract=contract,
        )
        second = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=surface,
            repetitions=3,
            contract=contract,
        )
        self.assertIs(first.decision.verdict, ExperimentVerdict.RETEST)
        self.assertIs(second.decision.verdict, ExperimentVerdict.STOP)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.champion)

    def test_token_guardrail_regression_discards(self) -> None:
        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=self._surface((0.4, 10, 1), (0.8, 100, 1)),
            repetitions=3,
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.DISCARD)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.champion)

    def test_self_evaluator_is_quarantined(self) -> None:
        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=self._surface((0.4, 10, 1), (0.8, 10, 1)),
            repetitions=3,
            author_id="same-identity",
            evaluator_id="same-identity",
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.QUARANTINE)
        self.assertTrue(self.registry.is_quarantined(result.challenger_digest))
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.champion)

    def test_author_reveal_before_start_invalidates_and_records(self) -> None:
        self.ledger.append_event(
            "episode-1",
            "pit.target.revealed",
            "author:cli",
            {"target_sha": "episode-1"},
        )
        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=self._surface((0.4, 10, 1), (0.8, 10, 1)),
            repetitions=3,
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.QUARANTINE)
        record = json.loads(result.evidence_path.read_text(encoding="utf-8"))
        self.assertFalse(record["holdout_ordering"]["valid"])
        self.assertTrue(record["holdout_ordering"]["author_reveal_sequences"])

    def test_model_receipt_follows_promotion_and_rollback(self) -> None:
        role = Role.BUILDER
        champion_prompt = generation_zero_prompt(ROLE_CONTRACTS[role])
        original = self.registry.register(
            role,
            champion_prompt,
            parent_digest=self.champion,
            created_by="author:test",
        )
        self.registry.promote(
            role,
            original,
            promoted_by="evaluator:test",
            experiment_id="EXP-original",
            expected_current=self.champion,
        )
        variant_prompt = champion_prompt + "\nVerify every required output and receipt."
        variant = self.registry.register(
            role,
            variant_prompt,
            parent_digest=original,
            created_by="author:test",
        )
        self.registry.promote(
            role,
            variant,
            promoted_by="evaluator:test",
            experiment_id="EXP-variant",
            expected_current=original,
        )
        self._execute_model(role)
        first_call = [
            event for event in self.ledger.events() if event["event_type"] == "model.call"
        ][-1]
        self.assertEqual(first_call["payload"]["prompt_artifact_digest"], variant)
        self.registry.rollback_champion(
            role,
            original,
            actor="steward:test",
            reason="verification",
        )
        self._execute_model(role)
        second_call = [
            event for event in self.ledger.events() if event["event_type"] == "model.call"
        ][-1]
        self.assertEqual(second_call["payload"]["prompt_artifact_digest"], original)

    def test_model_backend_without_registry_preserves_generation_zero_prompt(self) -> None:
        role = Role.ARCHITECT
        provider = FakeProvider([valid_turn(role)])
        ledger = EvidenceLedger()
        try:
            self._execute_model(role, provider=provider, ledger=ledger, registry=None)
            expected = generation_zero_prompt(ROLE_CONTRACTS[role])
            self.assertEqual(provider.calls[0].system, expected)
            event = ledger.events()[0]
            self.assertEqual(
                event["payload"]["prompt_artifact_digest"],
                prompt_digest(expected),
            )
        finally:
            ledger.close()

    def test_pit_surface_runs_each_pinned_oracle_episode(self) -> None:
        record = self.root / "pit-record.json"
        record.write_text(
            json.dumps(
                {
                    "grade": {"score": 0.75},
                    "receipts": [{"digest": "sha256:test"}],
                    "ledger_events": [{"event_type": "pit.episode.graded"}],
                    "prediction": {"digest": "sha256:test"},
                }
            ),
            encoding="utf-8",
        )

        class Oracle:
            def __init__(self) -> None:
                self.targets: list[str] = []

            def run_scripted_episode(
                self,
                target_sha: str,
                *,
                self_history: bool = False,
            ) -> Path:
                self.targets.append(target_sha)
                return record

        oracle = Oracle()
        surface = PITEpisodeSurface(oracle, ("a" * 40, "b" * 40))  # type: ignore[arg-type]
        observation = surface.evaluate("prompt", Role.BUILDER, 0)
        self.assertEqual(observation.task_success, 0.75)
        self.assertEqual(observation.evidence_completeness, 1.0)
        self.assertEqual(oracle.targets, ["a" * 40, "b" * 40])

    def _execute_model(
        self,
        role: Role,
        *,
        provider: FakeProvider | None = None,
        ledger: EvidenceLedger | None = None,
        registry: PromptRegistry | None | object = ...,
    ) -> None:
        selected_provider = provider or FakeProvider([valid_turn(role)])
        selected_ledger = ledger or self.ledger
        selected_registry = self.registry if registry is ... else registry
        backend = ModelBackend(
            selected_provider,
            ledger=selected_ledger,
            prompt_registry=selected_registry,
        )
        objective = Objective("verify prompt provenance")
        work_item = WorkItem(objective.id, role, "bounded work")
        asyncio.run(
            backend.execute(ROLE_CONTRACTS[role], work_item, objective, ())
        )


if __name__ == "__main__":
    unittest.main()
