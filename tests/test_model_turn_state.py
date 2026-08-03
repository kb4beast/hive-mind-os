from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from hive_mind_os.contracts import validate_contract
from hive_mind_os.model_turn_state import (
    ModelProviderIdentity,
    ModelRoleResult,
    ModelTurnAmbiguity,
    ModelTurnOutcome,
    ModelTurnPhase,
    ModelTurnPlan,
    ModelTurnResult,
    ModelTurnStateError,
    ModelTurnStore,
)
from hive_mind_os.models import AgentResult, Evidence, Role


def digest(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


class ModelTurnStateTests(unittest.TestCase):
    def plan(self, *, request: str = "request-v1") -> ModelTurnPlan:
        return ModelTurnPlan.create(
            mission_id="MISSION-44",
            state_ref="MISSION_STATE:MISSION-44:1",
            role="architect",
            work_item_id="WORK-architecture",
            provider=ModelProviderIdentity(
                "openai_compatible", "models.example", "model-v1"
            ),
            prompt_digest=digest("system-prompt"),
            request_digest=digest(request),
            acceptance_specification_id="acceptance-model-turn",
            acceptance_specification_digest=digest("acceptance-specification"),
            role_contract_digest=digest("architect-role-contract"),
            configuration_digest=digest("sealed-model-configuration"),
            selection_digest=digest("sealed-champion-selection"),
            policy_decision_ref="POLICY-model-turn",
            lease_id="LEASE-model-turn",
            redaction_policy_digest=digest("model-redaction-policy-v1"),
        )

    def result(
        self,
        plan: ModelTurnPlan,
        *,
        outcome: ModelTurnOutcome = ModelTurnOutcome.SUCCEEDED,
    ) -> ModelTurnResult:
        return ModelTurnResult.from_dict(
            {
                "schema_version": 1,
                "logical_turn_id": plan.logical_turn_id,
                "outcome": outcome.value,
                "response_digest": digest("provider-response"),
                "structured_result_digest": (
                    digest("parsed-structured-result")
                    if outcome is ModelTurnOutcome.SUCCEEDED
                    else None
                ),
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "transport_retry_index": 0,
            }
        )

    def role_result(self, plan: ModelTurnPlan, *, secret: str = "") -> ModelRoleResult:
        return ModelRoleResult.from_agent_result(
            plan.logical_turn_id,
            AgentResult(
                role=Role.ARCHITECT,
                work_item_id=plan.work_item_id,
                summary=f"architecture {secret}".strip(),
                evidence=(
                    Evidence(
                        "contract-output",
                        "design",
                        "model:architect",
                        {"content": f"bounded design {secret}".strip()},
                    ),
                ),
                proposed_actions=(f"implement {secret}".strip(),),
                lessons=(f"retain provenance {secret}".strip(),),
                completed_at="2026-08-03T12:00:00Z",
            ),
            redaction_policy_digest=plan.redaction_policy_digest,
            redaction_secrets=(secret,) if secret else (),
        )

    def test_stable_logical_id_binds_all_planning_inputs(self) -> None:
        first = self.plan()
        self.assertEqual(first.logical_turn_id, self.plan().logical_turn_id)
        self.assertNotEqual(first.logical_turn_id, self.plan(request="request-v2").logical_turn_id)
        self.assertTrue(validate_contract("model-turn-plan", first.to_dict()).valid)

    def test_durable_lifecycle_and_reopen_preserve_only_digest_provenance(self) -> None:
        prompt_secret = "prompt-secret-must-not-persist"
        response_secret = "response-secret-must-not-persist"
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model-turns.sqlite"
            with ModelTurnStore(path, redaction_secrets=(response_secret,)) as store:
                planned = store.register_plan(plan)
                self.assertIs(planned.phase, ModelTurnPhase.PLANNED)
                self.assertTrue(planned.may_dispatch)
                dispatching = store.start_dispatch(plan.logical_turn_id)
                self.assertIs(dispatching.phase, ModelTurnPhase.DISPATCH_STARTED)
                role_result = self.role_result(plan, secret=response_secret)
                completed = store.adopt_role_result(
                    replace(self.result(plan), structured_result_digest=role_result.digest),
                    role_result,
                )
                self.assertIs(completed.phase, ModelTurnPhase.COMPLETED)
                self.assertEqual(completed.role_result, role_result)
                assert completed.role_result is not None
                self.assertEqual(completed.role_result.to_agent_result().summary, "architecture [REDACTED]")
                self.assertEqual(store.event_count(plan.logical_turn_id), 3)

            with ModelTurnStore(path, redaction_secrets=(response_secret,)) as reopened:
                record = reopened.record(plan.logical_turn_id)
                self.assertIs(record.phase, ModelTurnPhase.COMPLETED)
                self.assertFalse(record.may_dispatch)
                self.assertIsNotNone(record.role_result)
                assert record.role_result is not None
                self.assertEqual(record.role_result.to_agent_result().work_item_id, plan.work_item_id)
                raw = path.read_bytes()
                self.assertNotIn(prompt_secret.encode(), raw)
                self.assertNotIn(response_secret.encode(), raw)
                self.assertNotIn(b"api_key", raw)

    def test_ambiguous_provider_outcome_is_permanently_quarantined(self) -> None:
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            with ModelTurnStore(Path(directory) / "model-turns.sqlite") as store:
                store.register_plan(plan)
                store.start_dispatch(plan.logical_turn_id)
                ambiguous = store.mark_ambiguous(
                    plan.logical_turn_id,
                    ModelTurnAmbiguity.PROVIDER_OUTCOME_UNKNOWN,
                )
                self.assertIs(ambiguous.phase, ModelTurnPhase.AMBIGUOUS)
                self.assertFalse(ambiguous.may_dispatch)
                self.assertEqual(
                    ambiguous.events[-1]["payload"],
                    {"reason_code": "provider_outcome_unknown"},
                )
                with self.assertRaisesRegex(ModelTurnStateError, "forbidden"):
                    store.start_dispatch(plan.logical_turn_id)
                with self.assertRaisesRegex(ModelTurnStateError, "forbidden"):
                    store.adopt_result(
                        self.result(plan, outcome=ModelTurnOutcome.INVALID_OUTPUT)
                    )

    def test_recovery_quarantines_interrupted_dispatch_across_reopen(self) -> None:
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model-turns.sqlite"
            with ModelTurnStore(path) as store:
                store.register_plan(plan)
                store.start_dispatch(plan.logical_turn_id)

            with ModelTurnStore(path) as reopened:
                recovered = reopened.recover(plan.logical_turn_id)
                self.assertIs(recovered.phase, ModelTurnPhase.AMBIGUOUS)
                self.assertEqual(
                    recovered.events[-1]["payload"],
                    {"reason_code": "interrupted_after_dispatch_start"},
                )
                self.assertIs(reopened.recover(plan.logical_turn_id).phase, ModelTurnPhase.AMBIGUOUS)

    def test_plan_and_result_replays_or_tampering_fail_closed(self) -> None:
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            with ModelTurnStore(Path(directory) / "model-turns.sqlite") as store:
                self.assertEqual(store.register_plan(plan).phase, ModelTurnPhase.PLANNED)
                self.assertEqual(store.register_plan(plan).phase, ModelTurnPhase.PLANNED)
                self.assertEqual(store.event_count(plan.logical_turn_id), 1)
                forged = replace(plan, request_digest=digest("other-request"))
                with self.assertRaisesRegex(ModelTurnStateError, "does not bind"):
                    store.register_plan(forged)
                with self.assertRaisesRegex(ModelTurnStateError, "without one in-progress"):
                    store.adopt_result(
                        self.result(plan, outcome=ModelTurnOutcome.INVALID_OUTPUT)
                    )
                store.start_dispatch(plan.logical_turn_id)
                with self.assertRaisesRegex(ModelTurnStateError, "requires a resumable"):
                    store.adopt_result(self.result(plan))
                invalid = self.result(plan, outcome=ModelTurnOutcome.INVALID_OUTPUT)
                completed = store.adopt_result(invalid)
                self.assertEqual(completed.result, invalid)
                with self.assertRaisesRegex(ModelTurnStateError, "forbidden"):
                    store.adopt_result(invalid)

    def test_sqlite_provenance_rows_reject_mutation_or_deletion(self) -> None:
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            with ModelTurnStore(Path(directory) / "model-turns.sqlite") as store:
                store.register_plan(plan)
                with self.assertRaises(sqlite3.DatabaseError):
                    store._connection.execute(  # noqa: SLF001 - trigger acceptance check
                        "DELETE FROM model_turn_plans WHERE logical_turn_id=?",
                        (plan.logical_turn_id,),
                    )
                with self.assertRaises(sqlite3.DatabaseError):
                    store._connection.execute(  # noqa: SLF001 - trigger acceptance check
                        "UPDATE model_turn_events SET event_kind='forged' "
                        "WHERE logical_turn_id=?",
                        (plan.logical_turn_id,),
                    )

    def test_closed_contracts_reject_raw_bodies_secrets_and_inconsistent_results(self) -> None:
        plan = self.plan()
        invalid_plan = dict(plan.to_dict())
        invalid_plan["prompt"] = "raw prompt body"
        self.assertFalse(validate_contract("model-turn-plan", invalid_plan).valid)
        bad_result = self.result(plan).to_dict()
        bad_result["outcome"] = "invalid_output"
        self.assertFalse(validate_contract("model-turn-result", bad_result).valid)
        with self.assertRaisesRegex(ModelTurnStateError, "expected null"):
            ModelTurnResult.from_dict(bad_result)
        self.assertFalse(
            validate_contract(
                "model-turn-result",
                {
                    **self.result(plan).to_dict(),
                    "provider_error": "credential=secret",
                },
            ).valid
        )
        role_result = self.role_result(plan)
        invalid_role = role_result.to_dict()
        invalid_role["provider_response"] = "raw response"
        self.assertFalse(validate_contract("model-role-result", invalid_role).valid)

    def test_memory_database_is_rejected_by_the_durable_adapter(self) -> None:
        with self.assertRaisesRegex(ModelTurnStateError, "filesystem path"):
            ModelTurnStore(":memory:")
        with self.assertRaisesRegex(ModelTurnStateError, "filesystem path"):
            ModelTurnStore("file::memory:?cache=shared")

    def test_stored_plan_digest_and_event_kind_tampering_fail_closed(self) -> None:
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            with ModelTurnStore(Path(directory) / "model-turns.sqlite") as store:
                store.register_plan(plan)
                store._connection.execute(  # noqa: SLF001 - tamper detection check
                    "DROP TRIGGER model_turn_plans_no_update"
                )
                store._connection.execute(  # noqa: SLF001 - tamper detection check
                    "UPDATE model_turn_plans SET plan_digest=? WHERE logical_turn_id=?",
                    (digest("forged-plan"), plan.logical_turn_id),
                )
                with self.assertRaisesRegex(ModelTurnStateError, "plan digest"):
                    store.record(plan.logical_turn_id)

            with ModelTurnStore(Path(directory) / "events.sqlite") as store:
                store.register_plan(plan)
                store._connection.execute(  # noqa: SLF001 - tamper detection check
                    "DROP TRIGGER model_turn_events_no_update"
                )
                store._connection.execute(  # noqa: SLF001 - tamper detection check
                    "UPDATE model_turn_events SET event_kind='completed' WHERE logical_turn_id=?",
                    (plan.logical_turn_id,),
                )
                with self.assertRaisesRegex(ModelTurnStateError, "event kind"):
                    store.record(plan.logical_turn_id)

    def test_results_are_response_observed_and_closed_contract_valid(self) -> None:
        result = self.result(self.plan())
        self.assertTrue(validate_contract("model-turn-result", result.to_dict()).valid)
        self.assertEqual(
            json.loads(json.dumps(result.to_dict()))["response_digest"],
            result.response_digest,
        )

    def test_role_result_requires_successful_response_and_exact_plan_bindings(self) -> None:
        plan = self.plan()
        role_result = self.role_result(plan)
        with tempfile.TemporaryDirectory() as directory:
            with ModelTurnStore(Path(directory) / "model-turns.sqlite") as store:
                store.register_plan(plan)
                store.start_dispatch(plan.logical_turn_id)
                with self.assertRaisesRegex(ModelTurnStateError, "succeeded"):
                    store.adopt_role_result(self.result(plan, outcome=ModelTurnOutcome.INVALID_OUTPUT), role_result)
                with self.assertRaisesRegex(ModelTurnStateError, "does not bind"):
                    store.adopt_role_result(self.result(plan), role_result)
                completed = store.adopt_role_result(
                    replace(self.result(plan), structured_result_digest=role_result.digest),
                    role_result,
                )
                self.assertEqual(completed.role_result, role_result)
                self.assertEqual(store.record(plan.logical_turn_id).role_result, role_result)

    def test_store_rejects_direct_role_result_mapping_with_configured_secret(self) -> None:
        plan = self.plan()
        secret = "direct-mapping-secret"
        role_result = self.role_result(plan)
        forged = role_result.to_dict()
        forged["summary"] = f"unsafe {secret}"
        result = replace(
            self.result(plan),
            structured_result_digest=ModelRoleResult.from_dict(forged).digest,
        )
        with tempfile.TemporaryDirectory() as directory:
            with ModelTurnStore(
                Path(directory) / "model-turns.sqlite", redaction_secrets=(secret,)
            ) as store:
                store.register_plan(plan)
                store.start_dispatch(plan.logical_turn_id)
                with self.assertRaisesRegex(ModelTurnStateError, "unredacted"):
                    store.adopt_role_result(result, forged)

    def test_two_store_dispatch_race_is_normalized_and_never_duplicates_start(self) -> None:
        plan = self.plan()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model-turns.sqlite"
            with ModelTurnStore(path) as first, ModelTurnStore(path) as second:
                first.register_plan(plan)
                barrier = threading.Barrier(2)
                outcomes: list[ModelTurnPhase | BaseException] = []

                def attempt(store: ModelTurnStore) -> None:
                    try:
                        barrier.wait()
                        outcomes.append(store.start_dispatch(plan.logical_turn_id).phase)
                    except BaseException as error:  # test captures cross-store race result
                        outcomes.append(error)

                one = threading.Thread(target=attempt, args=(first,))
                two = threading.Thread(target=attempt, args=(second,))
                one.start()
                two.start()
                one.join()
                two.join()
                self.assertEqual(outcomes.count(ModelTurnPhase.DISPATCH_STARTED), 1)
                failures = [item for item in outcomes if isinstance(item, BaseException)]
                self.assertEqual(len(failures), 1)
                self.assertIsInstance(failures[0], ModelTurnStateError)
                self.assertEqual(first.event_count(plan.logical_turn_id), 2)


if __name__ == "__main__":
    unittest.main()
