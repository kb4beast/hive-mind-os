from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from hive_mind_os.experiment_runner import (
    EVALUATION_SURFACE_UNAVAILABLE,
    EvaluationSurfaceUnavailable,
    ExperimentRunner,
    FixtureMissionSurface,
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
from hive_mind_os.receipts import sha256_digest
from hive_mind_os.recursive_improvement import (
    ExperimentVerdict,
    MetricDirection,
    MetricSpec,
    RecursiveImprovementContract,
)
from hive_mind_os.roles import ROLE_CONTRACTS


class RiggedSurface:
    name = "rigged-fixtures"
    episode_ids: tuple[str, ...] = ("episode-1", "episode-2")

    def __init__(
        self,
        artifact_root: Path,
        *,
        baseline: tuple[float, float, float],
        candidate: tuple[float, float, float],
    ) -> None:
        self.artifact_root = artifact_root
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.baseline = baseline
        self.candidate = candidate

    def evaluate(
        self,
        prompt: str,
        role: Role,
        repetition: int,
    ) -> SurfaceObservation:
        selected = self.candidate if prompt == "challenger" else self.baseline
        content = f"{prompt}:{role.value}:{repetition}".encode()
        digest = sha256_digest(content)
        path = self.artifact_root / f"{digest.removeprefix('sha256:')}.txt"
        path.write_bytes(content)
        return SurfaceObservation(
            *selected,
            (f"{path.as_posix()}#{digest}",),
        )


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
            generation_zero_prompt(ROLE_CONTRACTS[Role.BUILDER]),
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
        return RiggedSurface(
            self.root / "rigged-artifacts",
            baseline=baseline,
            candidate=candidate,
        )

    def _manual_decision(
        self,
        *,
        experiment_id: str,
        candidate: str,
        current: str,
        author: str = "author:test",
        judge: str = "judge:test",
    ) -> int:
        return self.ledger.append_event(
            experiment_id,
            "experiment.decision",
            judge,
            {
                "verdict": "keep",
                "role": Role.BUILDER.value,
                "candidate_digest": candidate,
                "current_digest": current,
                "registration_experiment_id": experiment_id,
                "registration_role": Role.BUILDER.value,
                "registration_author": author,
                "registration_parent_digest": current,
                "proposer_id": author,
                "builder_id": "builder:test",
                "evaluator_id": "evaluator:test",
                "judge_id": judge,
                "retained_artifact_refs": [
                    "artifact:test#sha256:" + "a" * 64
                ],
                "contract_fingerprint": "sha256:" + "b" * 64,
            },
        )

    def test_keep_records_pending_appeal_without_self_promotion(self) -> None:
        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=self._surface((0.4, 10, 1), (0.8, 12, 1)),
            repetitions=3,
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.KEEP)
        self.assertTrue(result.promotion_pending)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.champion)
        self.assertEqual(result.champion_after, self.champion)
        lineage = self.registry.lineage(result.challenger_digest)
        self.assertFalse(
            any(row["kind"] == "promotion" for row in lineage)
        )
        event_types = [
            event["event_type"]
            for event in self.ledger.events(result.experiment_id)
        ]
        self.assertEqual(event_types[0], "prompt.registered")
        self.assertIn("experiment.started", event_types)
        self.assertIn("experiment.evaluation", event_types)
        self.assertIn("experiment.promotion_appeal", event_types)
        self.assertNotIn("experiment.decision", event_types)
        self.assertNotIn("prompt.promoted", event_types)
        self.assertIn("experiment.closed", event_types)
        self.assertIn("experiment.recorded", event_types)
        evaluation_event = [
            event
            for event in self.ledger.events(result.experiment_id)
            if event["event_type"] == "experiment.evaluation"
        ][0]
        self.assertEqual(evaluation_event["actor"], "evaluator:scripted-harness")
        appeal_event = [
            event
            for event in self.ledger.events(result.experiment_id)
            if event["event_type"] == "experiment.promotion_appeal"
        ][0]
        self.assertEqual(
            appeal_event["payload"]["status"],
            "pending-independent-court",
        )
        record = json.loads(result.evidence_path.read_text(encoding="utf-8"))
        self.assertTrue(record["promotion_pending"])
        self.assertEqual(
            record["decision"]["event_sequence"],
            evaluation_event["sequence"],
        )

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

    def test_missing_surface_artifact_quarantines_instead_of_promoting(self) -> None:
        class MissingSurface:
            name = "missing"
            episode_ids: tuple[str, ...] = ("missing",)

            def evaluate(self, prompt: str, role: Role, repetition: int):
                selected = 0.8 if prompt == "challenger" else 0.4
                return SurfaceObservation(
                    selected,
                    10,
                    1,
                    (f"{self.root}/missing.json#sha256:{'0' * 64}",),
                )

            def __init__(self, root: Path) -> None:
                self.root = root

        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=MissingSurface(self.root),
            repetitions=3,
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.QUARANTINE)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.champion)
        record = json.loads(result.evidence_path.read_text(encoding="utf-8"))
        self.assertFalse(record["surface_validation"]["complete"])
        self.assertTrue(
            any(
                "does not resolve" in issue
                for issue in record["surface_validation"]["issues"]
            )
        )

    def test_tampered_surface_artifact_quarantines_instead_of_promoting(self) -> None:
        artifact = self.root / "tampered.json"
        artifact.write_text("observed", encoding="utf-8")

        class TamperedSurface:
            name = "tampered"
            episode_ids: tuple[str, ...] = ("tampered",)

            def evaluate(self, prompt: str, role: Role, repetition: int):
                selected = 0.8 if prompt == "challenger" else 0.4
                return SurfaceObservation(
                    selected,
                    10,
                    1,
                    (f"{artifact.as_posix()}#sha256:{'0' * 64}",),
                )

        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=TamperedSurface(),
            repetitions=3,
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.QUARANTINE)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.champion)
        record = json.loads(result.evidence_path.read_text(encoding="utf-8"))
        self.assertTrue(
            any(
                "digest mismatch" in issue
                for issue in record["surface_validation"]["issues"]
            )
        )

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

    def test_self_builder_is_quarantined(self) -> None:
        result = self.runner.run(
            Role.BUILDER,
            "challenger",
            surface=self._surface((0.4, 10, 1), (0.8, 10, 1)),
            repetitions=3,
            author_id="same-identity",
            builder_id="same-identity",
        )
        self.assertIs(result.decision.verdict, ExperimentVerdict.QUARANTINE)
        self.assertTrue(
            any("build its own" in reason for reason in result.decision.reasons)
        )
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
            experiment_id="EXP-original",
        )
        original_decision = self._manual_decision(
            experiment_id="EXP-original",
            candidate=original,
            current=self.champion,
        )
        self.registry.promote(
            role,
            original,
            promoted_by="judge:test",
            experiment_id="EXP-original",
            expected_current=self.champion,
            decision_event_sequence=original_decision,
        )
        variant_prompt = champion_prompt + "\nVerify every required output and receipt."
        variant = self.registry.register(
            role,
            variant_prompt,
            parent_digest=original,
            created_by="author:test",
            experiment_id="EXP-variant",
        )
        variant_decision = self._manual_decision(
            experiment_id="EXP-variant",
            candidate=variant,
            current=original,
        )
        self.registry.promote(
            role,
            variant,
            promoted_by="judge:test",
            experiment_id="EXP-variant",
            expected_current=original,
            decision_event_sequence=variant_decision,
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
        receipt_root = self.root / "pit-receipts"
        receipt_root.mkdir()
        artifact = receipt_root / "artifact.txt"
        artifact.write_text("observed", encoding="utf-8")
        bindings = {
            "mission_id": "pit-mission",
            "state_ref": "PIT:1",
            "actor_id": "explorer",
            "action_id": "ACT-1",
            "action_kind": "command",
            "action_digest": f"sha256:{'a' * 64}",
        }
        receipt = receipt_root / "receipt.json"
        receipt.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "receipt_id": "REC-1",
                    "provider": "test",
                    "execution_id": "EXEC-1",
                    **bindings,
                    "policy_decision_ref": "POLICY-1",
                    "lease_id": "LEASE-1",
                    "executed": True,
                    "result": "succeeded",
                    "observed_at": "2026-07-28T00:00:00Z",
                    "verified_by": "curator",
                    "artifacts": [
                        {
                            "path": artifact.name,
                            "digest": sha256_digest(artifact.read_bytes()),
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        record = self.root / "pit-record.json"
        record.write_text(
            json.dumps(
                {
                    "grade": {"score": 0.75},
                    "receipt_root": str(receipt_root),
                    "receipts": [
                        {
                            **bindings,
                            "path": receipt.name,
                            "digest": sha256_digest(receipt.read_bytes()),
                        }
                    ],
                    "ledger_events": [{"event_type": "pit.episode.graded"}],
                    "prediction": {"digest": f"sha256:{'b' * 64}"},
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

    def test_fixture_surface_is_disabled_until_it_uses_a_real_backend(self) -> None:
        surface = FixtureMissionSurface(self.root / "fixture-surface")
        with self.assertRaisesRegex(
            EvaluationSurfaceUnavailable,
            EVALUATION_SURFACE_UNAVAILABLE,
        ):
            surface.evaluate("prompt", Role.BUILDER, 0)

    def test_committed_experiment_artifacts_match_git_bytes_or_adverse_manifest(
        self,
    ) -> None:
        self.maxDiff = None
        repository = Path(__file__).resolve().parents[1]
        evidence_root = repository / "evidence" / "experiments"
        manifest = json.loads(
            (evidence_root / "adverse-artifact-integrity.json").read_text(
                encoding="utf-8"
            )
        )
        expected_by_experiment = manifest["experiments"]
        observed_experiments: set[str] = set()
        for record_path in sorted(evidence_root.glob("EXP-*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            experiment_id = record["experiment_id"]
            observed_experiments.add(experiment_id)
            mismatches: dict[tuple[str, str], dict[str, str]] = {}
            for raw_reference in record["artifact_refs"]:
                raw_path, separator, expected = raw_reference.rpartition("#")
                if separator != "#" or not expected.startswith("sha256:"):
                    mismatches[("unresolvable", raw_reference)] = {
                        "kind": "unresolvable",
                        "path": raw_reference,
                        "expected": "",
                        "observed": "",
                    }
                    continue
                content = self._git_blob(repository, raw_path)
                observed = sha256_digest(content)
                if observed != expected:
                    mismatches[("direct", raw_path)] = {
                        "kind": "direct",
                        "path": raw_path,
                        "expected": expected,
                        "observed": observed,
                    }
                if "/r/" not in raw_path or not raw_path.endswith(".json"):
                    continue
                receipt = json.loads(content.decode("utf-8"))
                receipt_root = Path(raw_path).parent.parent
                for artifact in receipt.get("artifacts", []):
                    artifact_path = (
                        receipt_root / Path(*artifact["path"].split("/"))
                    ).as_posix()
                    artifact_content = self._git_blob(repository, artifact_path)
                    artifact_observed = sha256_digest(artifact_content)
                    if artifact_observed != artifact["digest"]:
                        mismatches[("nested", artifact_path)] = {
                            "kind": "nested",
                            "path": artifact_path,
                            "expected": artifact["digest"],
                            "observed": artifact_observed,
                        }
            expected_rows = expected_by_experiment.get(
                experiment_id,
                {"mismatches": []},
            )["mismatches"]
            self.assertEqual(
                sorted(mismatches.values(), key=lambda row: (row["kind"], row["path"])),
                sorted(expected_rows, key=lambda row: (row["kind"], row["path"])),
                experiment_id,
            )
            disposition = expected_by_experiment[experiment_id]["disposition"]
            self.assertIn(disposition, {"adverse", "validated"})
            self.assertEqual(disposition == "adverse", bool(expected_rows))
        self.assertEqual(set(expected_by_experiment), observed_experiments)

    @staticmethod
    def _git_blob(repository: Path, path: str) -> bytes:
        completed = subprocess.run(
            ("git", "show", f"HEAD:{path}"),
            cwd=repository,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"experiment artifact is absent from Git: {path}: "
                + completed.stderr.decode("utf-8", "replace")
            )
        return completed.stdout

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
        selected_registry = (
            self.registry
            if registry is ...
            else cast(PromptRegistry | None, registry)
        )
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
