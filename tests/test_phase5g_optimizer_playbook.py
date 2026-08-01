from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.optimizer_playbook import (
    compile_optimizer_intake,
    example_optimizer_request,
)
from hive_mind_os.foundation.optimizer_playbook_contracts import (
    CHALLENGER_ID,
    CHAMPION_ID,
    OPEN_DEBT_IDS,
    OUTPUT_FIELDS,
    RESOLVED_DEBT_IDS,
    OptimizerContractError,
    validate_optimizer,
    validate_optimizer_request,
)


class OptimizerIntakeTests(unittest.TestCase):
    def test_example_compiles_deterministically_and_validates(self) -> None:
        request = example_optimizer_request()
        first = compile_optimizer_intake(request)
        second = compile_optimizer_intake(request)
        self.assertEqual(first, second)
        validate_optimizer(first)

    def test_exact_debt_and_degraded_baseline_are_preserved(self) -> None:
        envelope = compile_optimizer_intake(example_optimizer_request())
        snapshot = envelope["outputs"]["baseline_snapshot"]
        self.assertEqual(tuple(snapshot["open_debt_ids"]), OPEN_DEBT_IDS)
        self.assertEqual(tuple(snapshot["resolved_debt_ids"]), RESOLVED_DEBT_IDS)
        self.assertEqual(snapshot["health_status"], "degraded")
        self.assertEqual(snapshot["evidence_status"], "incomplete")
        self.assertEqual(snapshot["release_recommendation"], "defer")

    def test_challenger_is_distinct_and_champion_is_immutable(self) -> None:
        envelope = compile_optimizer_intake(example_optimizer_request())
        plan = envelope["outputs"]["challenger_plan"]
        self.assertEqual(plan["champion_id"], CHAMPION_ID)
        self.assertEqual(plan["challenger_id"], CHALLENGER_ID)
        self.assertNotEqual(plan["champion_id"], plan["challenger_id"])
        self.assertEqual(plan["status"], "proposed")
        self.assertEqual(plan["execution_status"], "not-run")
        self.assertFalse(plan["champion_mutation_authorized"])
        self.assertFalse(plan["skill_change_authorized"])
        self.assertTrue(plan["evidence_preservation_required"])

    def test_evaluation_claims_no_holdout_access_or_results(self) -> None:
        envelope = compile_optimizer_intake(example_optimizer_request())
        plan = envelope["outputs"]["evaluation_plan"]
        self.assertEqual(plan["holdout_exposure_status"], "sealed-not-accessed")
        self.assertEqual(plan["execution_status"], "not-run")
        self.assertEqual(plan["outcome_evidence_status"], "not-evaluated")
        self.assertEqual(plan["regression_budget_status"], "not-evaluated")
        self.assertEqual(plan["superiority_claim"], "prohibited")
        self.assertTrue(plan["losing_results_preserved"])

    def test_promotion_handoff_is_blocked_and_authority_free(self) -> None:
        envelope = compile_optimizer_intake(example_optimizer_request())
        handoff = envelope["outputs"]["promotion_handoff"]
        self.assertEqual(handoff["requested_stage"], "promotion-court")
        self.assertEqual(handoff["status"], "blocked")
        self.assertFalse(handoff["eligible"])
        self.assertEqual(tuple(handoff["blockers"]), OPEN_DEBT_IDS)
        self.assertTrue(handoff["independent_court_required"])
        self.assertFalse(handoff["promotion_authorized"])
        self.assertFalse(handoff["self_promotion_authorized"])
        self.assertFalse(handoff["release_authorized"])
        self.assertEqual(handoff["recommendation"], "defer")

    def test_request_requires_exact_containers_and_fields(self) -> None:
        request = example_optimizer_request()
        validate_optimizer_request(request)
        hostile = deepcopy(request)
        hostile["unexpected"] = True
        with self.assertRaises(OptimizerContractError):
            validate_optimizer_request(hostile)
        hostile = deepcopy(request)
        hostile["open_debt_ids"] = tuple(OPEN_DEBT_IDS)
        with self.assertRaises(OptimizerContractError):
            validate_optimizer_request(hostile)

    def test_scope_identity_debt_and_holdout_substitutions_fail_closed(self) -> None:
        request = example_optimizer_request()
        for field, replacement in (
            ("tenant_id", "tenant:other"),
            ("repository_id", "github:other/repository"),
            ("subject_commit", "0" * 40),
            ("steward_envelope_digest", "sha256:" + ("0" * 64)),
            ("champion_id", "champion:other"),
            ("challenger_id", "challenger:other"),
            ("holdout_manifest_digest", "sha256:" + ("0" * 64)),
            ("requested_next_stage", "release"),
            ("authority", "repository"),
            ("activation", "active"),
        ):
            hostile = deepcopy(request)
            hostile[field] = replacement
            with self.assertRaises(OptimizerContractError):
                validate_optimizer_request(hostile)
        hostile = deepcopy(request)
        hostile["open_debt_ids"].pop()
        with self.assertRaises(OptimizerContractError):
            validate_optimizer_request(hostile)

    def test_semantic_reseal_cannot_claim_health_superiority_or_promotion(self) -> None:
        envelope = compile_optimizer_intake(example_optimizer_request())
        mutations = (
            ("baseline_snapshot", "health_status", "healthy"),
            ("evaluation_plan", "superiority_claim", "proven"),
            ("promotion_handoff", "eligible", True),
            ("promotion_handoff", "promotion_authorized", True),
        )
        for output_name, field, replacement in mutations:
            hostile = deepcopy(envelope)
            hostile["outputs"][output_name][field] = replacement
            hostile["output_digests"][output_name] = digest(
                hostile["outputs"][output_name]
            )
            body = {key: value for key, value in hostile.items() if key != "envelope_digest"}
            hostile["envelope_digest"] = digest(body)
            with self.assertRaises(OptimizerContractError):
                validate_optimizer(hostile)

    def test_every_output_and_envelope_digest_is_checked(self) -> None:
        envelope = compile_optimizer_intake(example_optimizer_request())
        for field in OUTPUT_FIELDS:
            hostile = deepcopy(envelope)
            hostile["output_digests"][field] = "sha256:" + ("0" * 64)
            with self.assertRaises(OptimizerContractError):
                validate_optimizer(hostile)
        hostile = deepcopy(envelope)
        hostile["envelope_digest"] = "sha256:" + ("0" * 64)
        with self.assertRaises(OptimizerContractError):
            validate_optimizer(hostile)

    def test_outputs_are_defensive_private_and_plan_is_present(self) -> None:
        request = example_optimizer_request()
        envelope = compile_optimizer_intake(request)
        request["open_debt_ids"].clear()
        self.assertEqual(tuple(envelope["request"]["open_debt_ids"]), OPEN_DEBT_IDS)
        envelope["outputs"]["baseline_snapshot"]["open_debt_ids"].clear()
        rebuilt = compile_optimizer_intake(example_optimizer_request())
        self.assertEqual(
            tuple(rebuilt["outputs"]["baseline_snapshot"]["open_debt_ids"]),
            OPEN_DEBT_IDS,
        )
        self.assertFalse(hasattr(hive_mind_os, "compile_optimizer_intake"))
        self.assertFalse(hasattr(foundation, "compile_optimizer_intake"))
        root = Path(__file__).resolve().parents[1]
        plan = root / "docs" / "plan" / "PHASE5_CARRIED_FORWARD_DEBT.md"
        text = plan.read_text(encoding="utf-8")
        for debt_id in (*OPEN_DEBT_IDS, *RESOLVED_DEBT_IDS):
            self.assertIn(debt_id, text)


if __name__ == "__main__":
    unittest.main()
