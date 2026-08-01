from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.steward_playbook import (
    compile_steward_intake,
    example_steward_request,
)
from hive_mind_os.foundation.steward_playbook_contracts import (
    OPEN_DEBT_IDS,
    OUTPUT_FIELDS,
    RESOLVED_DEBT_IDS,
    StewardContractError,
    validate_steward,
    validate_steward_request,
)


class StewardIntakeTests(unittest.TestCase):
    def test_example_compiles_deterministically_and_validates(self) -> None:
        request = example_steward_request()
        first = compile_steward_intake(request)
        second = compile_steward_intake(request)
        self.assertEqual(first, second)
        validate_steward(first)

    def test_exact_open_and_resolved_debt_is_preserved(self) -> None:
        envelope = compile_steward_intake(example_steward_request())
        snapshot = envelope["outputs"]["health_snapshot"]
        self.assertEqual(tuple(snapshot["open_debt_ids"]), OPEN_DEBT_IDS)
        self.assertEqual(tuple(snapshot["resolved_debt_ids"]), RESOLVED_DEBT_IDS)
        self.assertEqual(snapshot["health_status"], "degraded")
        self.assertEqual(snapshot["release_recommendation"], "defer")

    def test_plans_claim_no_execution_or_authority(self) -> None:
        envelope = compile_steward_intake(example_steward_request())
        maintenance = envelope["outputs"]["maintenance_plan"]
        recovery = envelope["outputs"]["recovery_plan"]
        handoff = envelope["outputs"]["optimizer_handoff"]
        self.assertEqual(maintenance["execution_status"], "not-run")
        self.assertFalse(maintenance["maintenance_authorized"])
        self.assertFalse(maintenance["dependency_mutation_authorized"])
        self.assertEqual(recovery["execution_status"], "not-run")
        self.assertFalse(recovery["recovery_authorized"])
        self.assertFalse(recovery["evidence_deletion_authorized"])
        self.assertFalse(handoff["eligible"])
        self.assertEqual(handoff["status"], "blocked")

    def test_recovery_steps_are_reversible_and_preserve_evidence(self) -> None:
        envelope = compile_steward_intake(example_steward_request())
        for step in envelope["outputs"]["recovery_plan"]["steps"]:
            self.assertEqual(step["status"], "not-run")
            self.assertTrue(step["reversible"])
            self.assertTrue(step["preserves_evidence"])

    def test_request_requires_exact_containers_and_fields(self) -> None:
        request = example_steward_request()
        validate_steward_request(request)
        hostile = deepcopy(request)
        hostile["unexpected"] = True
        with self.assertRaises(StewardContractError):
            validate_steward_request(hostile)
        with self.assertRaises(StewardContractError):
            validate_steward_request(dict(request) | {"open_debt_ids": tuple(OPEN_DEBT_IDS)})

    def test_scope_and_debt_substitution_fail_closed(self) -> None:
        request = example_steward_request()
        for field, replacement in (
            ("tenant_id", "tenant:other"),
            ("repository_id", "github:other/repository"),
            ("subject_commit", "0" * 40),
            ("requested_next_role", "integrator"),
            ("authority", "repository"),
            ("activation", "active"),
        ):
            hostile = deepcopy(request)
            hostile[field] = replacement
            with self.assertRaises(StewardContractError):
                validate_steward_request(hostile)
        hostile = deepcopy(request)
        hostile["open_debt_ids"].pop()
        with self.assertRaises(StewardContractError):
            validate_steward_request(hostile)

    def test_semantic_reseal_cannot_claim_health_or_release(self) -> None:
        envelope = compile_steward_intake(example_steward_request())
        for field, replacement in (
            ("health_status", "healthy"),
            ("release_recommendation", "approve"),
        ):
            hostile = deepcopy(envelope)
            hostile["outputs"]["health_snapshot"][field] = replacement
            hostile["output_digests"]["health_snapshot"] = digest(
                hostile["outputs"]["health_snapshot"]
            )
            body = {key: value for key, value in hostile.items() if key != "envelope_digest"}
            hostile["envelope_digest"] = digest(body)
            with self.assertRaises(StewardContractError):
                validate_steward(hostile)

    def test_every_output_and_envelope_digest_is_checked(self) -> None:
        envelope = compile_steward_intake(example_steward_request())
        for field in OUTPUT_FIELDS:
            hostile = deepcopy(envelope)
            hostile["output_digests"][field] = "sha256:" + ("0" * 64)
            with self.assertRaises(StewardContractError):
                validate_steward(hostile)
        hostile = deepcopy(envelope)
        hostile["envelope_digest"] = "sha256:" + ("0" * 64)
        with self.assertRaises(StewardContractError):
            validate_steward(hostile)

    def test_outputs_are_defensive_against_caller_mutation(self) -> None:
        request = example_steward_request()
        envelope = compile_steward_intake(request)
        request["open_debt_ids"].clear()
        self.assertEqual(tuple(envelope["request"]["open_debt_ids"]), OPEN_DEBT_IDS)
        envelope["outputs"]["health_snapshot"]["open_debt_ids"].clear()
        rebuilt = compile_steward_intake(example_steward_request())
        self.assertEqual(
            tuple(rebuilt["outputs"]["health_snapshot"]["open_debt_ids"]),
            OPEN_DEBT_IDS,
        )

    def test_modules_are_private_and_plan_is_present(self) -> None:
        self.assertFalse(hasattr(hive_mind_os, "compile_steward_intake"))
        self.assertFalse(hasattr(foundation, "compile_steward_intake"))
        root = Path(__file__).resolve().parents[1]
        plan = root / "docs" / "plan" / "PHASE5_CARRIED_FORWARD_DEBT.md"
        text = plan.read_text(encoding="utf-8")
        for debt_id in (*OPEN_DEBT_IDS, *RESOLVED_DEBT_IDS):
            self.assertIn(debt_id, text)


if __name__ == "__main__":
    unittest.main()
