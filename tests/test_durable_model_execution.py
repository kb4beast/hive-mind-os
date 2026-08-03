from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.durable_model_execution import (
    DurableModelExecutionContext,
    DurableModelExecutionError,
    DurableModelRoleExecutor,
)
from hive_mind_os.model_backend import ModelBackend, ModelTurnError
from hive_mind_os.model_provider import (
    ModelRequest,
    ModelResponse,
    ModelTransportError,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.model_turn_state import (
    ModelTurnBudget,
    ModelTurnPhase,
    ModelTurnStore,
)
from hive_mind_os.models import AgentResult, Evidence, Objective, Role, WorkItem
from hive_mind_os.prompt_registry import generation_zero_prompt, prompt_digest
from hive_mind_os.roles import ROLE_CONTRACTS


def valid_turn(role: Role, *, marker: str = "") -> str:
    return json.dumps(
        {
            "summary": f"{role.value} complete {marker}".strip(),
            "outputs": {
                name: f"evidence for {name} {marker}".strip()
                for name in ROLE_CONTRACTS[role].required_outputs
            },
            "proposed_actions": [],
            "lessons": [f"bounded lesson {marker}".strip()],
            "success": True,
        },
        sort_keys=True,
    )


@dataclass
class FakeProvider:
    responses: list[str | BaseException]
    model: str = "durable-fake-model"
    max_output_tokens: int = 128
    max_retries: int = 2
    api_key_env: str = "DURABLE_TEST_KEY"

    def __post_init__(self) -> None:
        self.config = ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://models.example/v1",
            self.model,
            self.api_key_env,
            max_output_tokens=self.max_output_tokens,
            max_retries=self.max_retries,
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
            separators=(",", ":"),
        ).encode()

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        raw = json.dumps({"content": response}, sort_keys=True).encode()
        return ModelResponse(response, raw, 10, 5)

    def complete(self, request: ModelRequest) -> ModelResponse:
        raise AssertionError("durable model execution must never call complete()")


class DurableModelExecutionTests(unittest.TestCase):
    mission_id = "MISSION-DURABLE-44"

    def context(self, *, secret: str = "", budget: ModelTurnBudget | None = None):
        return DurableModelExecutionContext(
            mission_id=self.mission_id,
            state_ref=f"MISSION_STATE:{self.mission_id}:1",
            acceptance_specification=AcceptanceSpecification(
                "model-role-contract",
                "The model role result satisfies its exact structured contract.",
                ("python", "-m", "pytest", "tests/test_model_backend.py"),
            ),
            policy_decision_ref="POLICY-durable-model",
            lease_id="LEASE-durable-model",
            redaction_policy_digest="sha256:" + "a" * 64,
            budget=budget
            or ModelTurnBudget(
                self.mission_id,
                max_episodes=8,
                max_tool_calls=8,
                max_compute_units=8.0,
                max_tool_calls_per_episode=1,
                max_compute_units_per_episode=1.0,
            ),
            prompt_artifact_digests={
                Role.ARCHITECT: prompt_digest(generation_zero_prompt(ROLE_CONTRACTS[Role.ARCHITECT]))
            },
            redaction_secrets=(secret,) if secret else (),
        )

    def execute_architect(
        self,
        executor: DurableModelRoleExecutor,
        *,
        work_item_id: str = "WORK-durable-architect",
        prior_results: tuple[AgentResult, ...] = (),
    ):
        objective = Objective("Produce a durable verified design", id=self.mission_id)
        work_item = WorkItem(
            objective.id,
            Role.ARCHITECT,
            ROLE_CONTRACTS[Role.ARCHITECT].mission,
            id=work_item_id,
        )
        return asyncio.run(
            executor.execute(
                ROLE_CONTRACTS[Role.ARCHITECT],
                work_item,
                objective,
                prior_results,
            )
        )

    def test_success_rehydrates_without_a_second_provider_call_after_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model-turns.sqlite3"
            first_provider = FakeProvider([valid_turn(Role.ARCHITECT)])
            with ModelTurnStore(path) as store:
                first = self.execute_architect(
                    DurableModelRoleExecutor(
                        ModelBackend(first_provider), store, self.context()
                    )
                )
                self.assertTrue(first.success)
                self.assertEqual(len(first_provider.calls), 1)
                usage = store.budget_usage(self.mission_id)
                self.assertEqual((usage["episodes"], usage["tool_calls"]), (1, 1))
                self.assertGreater(float(usage["compute_units"]), 0.0)

            second_provider = FakeProvider([valid_turn(Role.ARCHITECT, marker="must-not-run")])
            with ModelTurnStore(path) as reopened:
                second = self.execute_architect(
                    DurableModelRoleExecutor(
                        ModelBackend(second_provider), reopened, self.context()
                    )
                )
                self.assertEqual(second.summary, first.summary)
                self.assertEqual(second_provider.calls, [])

    def test_timeout_after_dispatch_is_quarantined_and_never_retried(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model-turns.sqlite3"
            first_provider = FakeProvider([ModelTransportError("sent then timed out")])
            with ModelTurnStore(path) as store:
                with self.assertRaisesRegex(DurableModelExecutionError, "uncertain"):
                    self.execute_architect(
                        DurableModelRoleExecutor(
                            ModelBackend(first_provider), store, self.context()
                        )
                    )
                self.assertEqual(len(first_provider.calls), 1)
                records = store._connection.execute(  # noqa: SLF001 - durable-state acceptance check
                    "SELECT logical_turn_id FROM model_turn_plans"
                ).fetchall()
                self.assertEqual(len(records), 1)
                self.assertIs(
                    store.record(records[0]["logical_turn_id"]).phase,
                    ModelTurnPhase.AMBIGUOUS,
                )

            second_provider = FakeProvider([valid_turn(Role.ARCHITECT)])
            with ModelTurnStore(path) as reopened:
                with self.assertRaisesRegex(DurableModelExecutionError, "quarantined"):
                    self.execute_architect(
                        DurableModelRoleExecutor(
                            ModelBackend(second_provider), reopened, self.context()
                        )
                    )
                self.assertEqual(second_provider.calls, [])

    def test_observed_invalid_output_is_terminal_with_no_corrective_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider(["{"])
            with ModelTurnStore(Path(directory) / "model-turns.sqlite3") as store:
                executor = DurableModelRoleExecutor(
                    ModelBackend(provider), store, self.context()
                )
                with self.assertRaisesRegex(DurableModelExecutionError, "invalid role result"):
                    self.execute_architect(executor)
                self.assertEqual(len(provider.calls), 1)
                with self.assertRaisesRegex(DurableModelExecutionError, "without an admissible"):
                    self.execute_architect(executor)
                self.assertEqual(len(provider.calls), 1)

    def test_changed_provider_configuration_cannot_replan_an_existing_role_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model-turns.sqlite3"
            with ModelTurnStore(path) as store:
                provider = FakeProvider([valid_turn(Role.ARCHITECT)])
                self.execute_architect(
                    DurableModelRoleExecutor(ModelBackend(provider), store, self.context())
                )
                replacement = FakeProvider([valid_turn(Role.ARCHITECT)], model="changed-model")
                with self.assertRaisesRegex(DurableModelExecutionError, "admission failed"):
                    self.execute_architect(
                        DurableModelRoleExecutor(
                            ModelBackend(replacement), store, self.context()
                        )
                    )
                self.assertEqual(replacement.calls, [])

    def test_permanent_reservation_blocks_a_second_role_after_budget_exhaustion(self) -> None:
        budget = ModelTurnBudget(
            self.mission_id,
            max_episodes=1,
            max_tool_calls=1,
            max_compute_units=1.0,
            max_tool_calls_per_episode=1,
            max_compute_units_per_episode=1.0,
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider([valid_turn(Role.ARCHITECT), valid_turn(Role.ARCHITECT)])
            with ModelTurnStore(Path(directory) / "model-turns.sqlite3") as store:
                executor = DurableModelRoleExecutor(
                    ModelBackend(provider), store, self.context(budget=budget)
                )
                self.execute_architect(executor)
                with self.assertRaisesRegex(DurableModelExecutionError, "budget is exhausted"):
                    self.execute_architect(executor, work_item_id="WORK-durable-architect-next")
                self.assertEqual(len(provider.calls), 1)

    def test_selected_result_is_redacted_and_no_secret_reaches_the_store_or_ledger(self) -> None:
        secret = "durable-model-secret-sentinel"
        endpoint = "https://models.example/v1"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model-turns.sqlite3"
            provider = FakeProvider(
                [valid_turn(Role.ARCHITECT, marker=f"{secret} {endpoint}")]
            )
            backend = ModelBackend(provider)
            with ModelTurnStore(path, redaction_secrets=(secret,)) as store:
                result = self.execute_architect(
                    DurableModelRoleExecutor(backend, store, self.context(secret=secret))
                )
                self.assertNotIn(secret, result.summary)
                self.assertIn("[REDACTED]", result.summary)
                self.assertNotIn(endpoint, result.summary)
                durable_bytes = path.read_bytes()
                wal_path = Path(f"{path}-wal")
                if wal_path.exists():
                    durable_bytes += wal_path.read_bytes()
                self.assertNotIn(secret.encode(), durable_bytes)
                self.assertNotIn(endpoint.encode(), durable_bytes)
                self.assertNotIn(
                    secret,
                    json.dumps(backend.ledger.events(), sort_keys=True),
                )
                self.assertNotIn(
                    endpoint,
                    json.dumps(backend.ledger.events(), sort_keys=True),
                )

    def test_unavailable_or_changed_pinned_prompt_blocks_before_network_access(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider([valid_turn(Role.ARCHITECT)])
            context = self.context()
            object.__setattr__(
                context,
                "prompt_artifact_digests",
                {Role.ARCHITECT: "sha256:" + "b" * 64},
            )
            with ModelTurnStore(Path(directory) / "model-turns.sqlite3") as store:
                with self.assertRaisesRegex(ModelTurnError, "pinned prompt"):
                    self.execute_architect(
                        DurableModelRoleExecutor(ModelBackend(provider), store, context)
                    )
                self.assertEqual(provider.calls, [])

    def test_unredacted_configured_secret_in_prior_context_blocks_before_network_access(self) -> None:
        secret = "prior-context-secret-sentinel"
        prior = AgentResult(
            Role.EXPLORER,
            "WORK-durable-explorer",
            f"prior summary {secret}",
            (
                Evidence(
                    "contract-output",
                    "problem statement",
                    "test",
                    {"content": secret},
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider([valid_turn(Role.ARCHITECT)])
            with ModelTurnStore(Path(directory) / "model-turns.sqlite3") as store:
                with self.assertRaisesRegex(DurableModelExecutionError, "prior context"):
                    self.execute_architect(
                        DurableModelRoleExecutor(
                            ModelBackend(provider), store, self.context(secret=secret)
                        ),
                        prior_results=(prior,),
                    )
                self.assertEqual(provider.calls, [])

    def test_configured_secret_in_legacy_ledger_projection_blocks_before_network_access(self) -> None:
        secret = "ledger-projection-secret-sentinel"
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider(
                [valid_turn(Role.ARCHITECT)],
                api_key_env=secret,
            )
            backend = ModelBackend(provider)
            with ModelTurnStore(Path(directory) / "model-turns.sqlite3") as store:
                with self.assertRaisesRegex(DurableModelExecutionError, "ledger projection"):
                    self.execute_architect(
                        DurableModelRoleExecutor(
                            backend,
                            store,
                            self.context(secret=secret),
                        )
                    )
                self.assertEqual(provider.calls, [])
                self.assertEqual(backend.ledger.events(), [])

    def test_configured_provider_endpoint_in_prior_context_blocks_before_network_access(self) -> None:
        endpoint = "https://models.example/v1"
        prior = AgentResult(
            Role.EXPLORER,
            "WORK-durable-explorer",
            f"prior summary {endpoint}",
            (Evidence("contract-output", "problem statement", "test", {"content": "x"}),),
        )
        with tempfile.TemporaryDirectory() as directory:
            provider = FakeProvider([valid_turn(Role.ARCHITECT)])
            backend = ModelBackend(provider)
            with ModelTurnStore(Path(directory) / "model-turns.sqlite3") as store:
                with self.assertRaisesRegex(DurableModelExecutionError, "provider endpoint"):
                    self.execute_architect(
                        DurableModelRoleExecutor(backend, store, self.context()),
                        prior_results=(prior,),
                    )
                self.assertEqual(provider.calls, [])
                self.assertEqual(backend.ledger.events(), [])

    def test_lookalike_acceptance_specification_is_rejected_before_executor_admission(self) -> None:
        @dataclass(frozen=True)
        class LookalikeSpecification:
            identifier: str = "model-role-contract"
            digest: str = "sha256:" + "a" * 64

        with self.assertRaisesRegex(ValueError, "typed acceptance specification"):
            DurableModelExecutionContext(
                mission_id=self.mission_id,
                state_ref=f"MISSION_STATE:{self.mission_id}:1",
                acceptance_specification=LookalikeSpecification(),  # type: ignore[arg-type] - hostile boundary probe
                policy_decision_ref="POLICY-durable-model",
                lease_id="LEASE-durable-model",
                redaction_policy_digest="sha256:" + "a" * 64,
                budget=ModelTurnBudget(
                    self.mission_id, 1, 1, 1.0, 1, 1.0
                ),
                prompt_artifact_digests={
                    Role.ARCHITECT: prompt_digest(
                        generation_zero_prompt(ROLE_CONTRACTS[Role.ARCHITECT])
                    )
                },
            )

    def test_lookalike_budget_is_rejected_before_executor_admission(self) -> None:
        @dataclass(frozen=True)
        class LookalikeBudget:
            mission_id: str

            def to_dict(self) -> dict[str, object]:
                return {
                    "mission_id": self.mission_id,
                    "max_episodes": 1,
                    "max_tool_calls": 1,
                    "max_compute_units": 1.0,
                    "max_tool_calls_per_episode": 1,
                    "max_compute_units_per_episode": 1.0,
                }

        with self.assertRaisesRegex(ValueError, "typed model-turn budget"):
            DurableModelExecutionContext(
                mission_id=self.mission_id,
                state_ref=f"MISSION_STATE:{self.mission_id}:1",
                acceptance_specification=AcceptanceSpecification(
                    "model-role-contract",
                    "The model role result satisfies its exact structured contract.",
                    ("python", "-m", "pytest", "tests/test_model_backend.py"),
                ),
                policy_decision_ref="POLICY-durable-model",
                lease_id="LEASE-durable-model",
                redaction_policy_digest="sha256:" + "a" * 64,
                budget=LookalikeBudget(self.mission_id),  # type: ignore[arg-type] - hostile boundary probe
                prompt_artifact_digests={
                    Role.ARCHITECT: prompt_digest(
                        generation_zero_prompt(ROLE_CONTRACTS[Role.ARCHITECT])
                    )
                },
            )


if __name__ == "__main__":
    unittest.main()
