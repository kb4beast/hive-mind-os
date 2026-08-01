from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.external_adoption_evidence import (
    compile_external_adoption_evidence_intake,
    example_evidence_intake_request,
)
from hive_mind_os.foundation.external_adoption_evidence_contracts import (
    ACTIVE_DEBT_IDS,
    DECISION_OPTIONS,
    EVIDENCE_FIELDS,
    OUTPUT_FIELDS,
    PARTICIPANT_ROLES,
    REJECTION_CODES,
    ExternalAdoptionEvidenceError,
    validate_evidence_intake_request,
    validate_external_adoption_evidence_intake,
)


class ExternalAdoptionEvidenceIntakeTests(unittest.TestCase):
    def test_example_compiles_deterministically_and_validates(self) -> None:
        request = example_evidence_intake_request()
        first = compile_external_adoption_evidence_intake(request)
        second = compile_external_adoption_evidence_intake(request)
        self.assertEqual(first, second)
        validate_external_adoption_evidence_intake(first)

    def test_all_thirty_five_debts_remain_active(self) -> None:
        envelope = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        disposition = envelope["outputs"]["intake_disposition"]
        self.assertEqual(tuple(disposition["active_debt_ids"]), ACTIVE_DEBT_IDS)
        self.assertEqual(len(disposition["active_debt_ids"]), 35)
        self.assertIn("P5D-DEBT-03", disposition["active_debt_ids"])
        self.assertIn("P5J-DEBT-05", disposition["active_debt_ids"])

    def test_requirements_are_exact_and_unsatisfied(self) -> None:
        envelope = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        requirements = envelope["outputs"]["evidence_requirements"]
        self.assertEqual(tuple(requirements["participant_roles"]), PARTICIPANT_ROLES)
        self.assertEqual(tuple(requirements["required_fields"]), EVIDENCE_FIELDS)
        self.assertEqual(requirements["trust_anchor_status"], "missing")
        self.assertEqual(requirements["external_retention_status"], "missing")
        self.assertFalse(requirements["requirements_satisfied"])

    def test_policy_is_exact_and_not_executed(self) -> None:
        envelope = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        policy = envelope["outputs"]["verification_policy"]
        self.assertEqual(tuple(policy["decision_options"]), DECISION_OPTIONS)
        self.assertEqual(tuple(policy["required_distinct_roles"]), PARTICIPANT_ROLES)
        self.assertEqual(tuple(policy["rejection_codes"]), REJECTION_CODES)
        self.assertFalse(policy["self_issued_allowed"])
        self.assertFalse(policy["local_retention_sufficient"])
        self.assertEqual(policy["policy_status"], "defined-not-executed")

    def test_register_is_empty_and_awaiting_external_evidence(self) -> None:
        envelope = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        register = envelope["outputs"]["evidence_register"]
        self.assertEqual(register["submissions"], [])
        self.assertEqual(register["trust_anchor_refs"], [])
        self.assertEqual(register["verified_roles"], [])
        self.assertEqual(register["selected_decision"], "none")
        self.assertFalse(register["signed_decision_present"])
        self.assertEqual(register["register_status"], "awaiting-external-evidence")

    def test_disposition_blocks_adoption_and_every_authority_claim(self) -> None:
        envelope = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        disposition = envelope["outputs"]["intake_disposition"]
        self.assertEqual(disposition["disposition"], "awaiting-external-evidence")
        for field in (
            "external_evidence_received",
            "authenticated_participants",
            "adr_adopted",
            "p14_eligible",
            "p20_eligible",
            "release_ready",
            "production_ready",
            "deployment_authorized",
            "promotion_eligible",
            "superiority_established",
        ):
            self.assertFalse(disposition[field])
        self.assertEqual(disposition["authority"], "none")
        self.assertEqual(disposition["activation"], "inert")

    def test_request_requires_exact_containers_and_fields(self) -> None:
        request = example_evidence_intake_request()
        validate_evidence_intake_request(request)
        with self.assertRaises(ExternalAdoptionEvidenceError):
            compile_external_adoption_evidence_intake(MappingProxyType(request))
        hostile = deepcopy(request)
        hostile["unexpected"] = True
        with self.assertRaises(ExternalAdoptionEvidenceError):
            validate_evidence_intake_request(hostile)
        hostile = deepcopy(request)
        hostile["active_debt_ids"] = tuple(ACTIVE_DEBT_IDS)
        with self.assertRaises(ExternalAdoptionEvidenceError):
            validate_evidence_intake_request(hostile)

    def test_nonempty_evidence_and_trust_anchor_attempts_fail_closed(self) -> None:
        request = example_evidence_intake_request()
        hostile = deepcopy(request)
        hostile["evidence_submissions"].append({"decision": "adopt"})
        with self.assertRaises(ExternalAdoptionEvidenceError):
            validate_evidence_intake_request(hostile)
        hostile = deepcopy(request)
        hostile["trust_anchor_refs"].append("trust-anchor:self-issued")
        with self.assertRaises(ExternalAdoptionEvidenceError):
            validate_evidence_intake_request(hostile)

    def test_scope_debt_stage_authority_and_digest_tampering_fail(self) -> None:
        request = example_evidence_intake_request()
        for field, replacement in (
            ("repository_id", "github:other/repository"),
            ("tenant_id", "tenant:other"),
            ("subject_commit", "0" * 40),
            ("phase5j_source_head", "0" * 40),
            ("requested_next_stage", "p14"),
            ("authority", "repository"),
            ("activation", "active"),
            ("phase5j_packet_digest", "not-a-digest"),
        ):
            hostile = deepcopy(request)
            hostile[field] = replacement
            with self.assertRaises(ExternalAdoptionEvidenceError):
                validate_evidence_intake_request(hostile)
        hostile = deepcopy(request)
        hostile["active_debt_ids"].pop()
        with self.assertRaises(ExternalAdoptionEvidenceError):
            validate_evidence_intake_request(hostile)

    def test_semantic_reseal_cannot_claim_external_evidence_or_adoption(self) -> None:
        envelope = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        mutations = (
            ("evidence_requirements", "requirements_satisfied", True),
            ("verification_policy", "policy_status", "executed"),
            ("evidence_register", "signed_decision_present", True),
            ("evidence_register", "selected_decision", "adopt"),
            ("intake_disposition", "external_evidence_received", True),
            ("intake_disposition", "authenticated_participants", True),
            ("intake_disposition", "adr_adopted", True),
            ("intake_disposition", "p14_eligible", True),
        )
        for output_name, field, replacement in mutations:
            hostile = deepcopy(envelope)
            hostile["outputs"][output_name][field] = replacement
            hostile["output_digests"][output_name] = digest(
                hostile["outputs"][output_name]
            )
            body = {
                key: value
                for key, value in hostile.items()
                if key != "envelope_digest"
            }
            hostile["envelope_digest"] = digest(body)
            with self.assertRaises(ExternalAdoptionEvidenceError):
                validate_external_adoption_evidence_intake(hostile)

    def test_every_output_and_envelope_digest_is_checked(self) -> None:
        envelope = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        for field in OUTPUT_FIELDS:
            hostile = deepcopy(envelope)
            hostile["output_digests"][field] = "sha256:" + ("0" * 64)
            with self.assertRaises(ExternalAdoptionEvidenceError):
                validate_external_adoption_evidence_intake(hostile)
        hostile = deepcopy(envelope)
        hostile["envelope_digest"] = "sha256:" + ("0" * 64)
        with self.assertRaises(ExternalAdoptionEvidenceError):
            validate_external_adoption_evidence_intake(hostile)

    def test_outputs_are_defensive_private_and_debt_plans_are_present(self) -> None:
        request = example_evidence_intake_request()
        envelope = compile_external_adoption_evidence_intake(request)
        request["active_debt_ids"].clear()
        self.assertEqual(
            tuple(envelope["request"]["active_debt_ids"]),
            ACTIVE_DEBT_IDS,
        )
        envelope["outputs"]["intake_disposition"]["active_debt_ids"].clear()
        rebuilt = compile_external_adoption_evidence_intake(
            example_evidence_intake_request()
        )
        self.assertEqual(
            tuple(rebuilt["outputs"]["intake_disposition"]["active_debt_ids"]),
            ACTIVE_DEBT_IDS,
        )
        self.assertFalse(
            hasattr(hive_mind_os, "compile_external_adoption_evidence_intake")
        )
        self.assertFalse(
            hasattr(foundation, "compile_external_adoption_evidence_intake")
        )
        root = Path(__file__).resolve().parents[1]
        canonical_plan = root / "docs" / "plan" / "PHASE5_CARRIED_FORWARD_DEBT.md"
        phase5j_plan = root / "docs" / "plan" / "PHASE5J_CARRIED_FORWARD_DEBT.md"
        text = canonical_plan.read_text(encoding="utf-8") + phase5j_plan.read_text(
            encoding="utf-8"
        )
        for debt_id in ACTIVE_DEBT_IDS:
            self.assertIn(debt_id, text)


if __name__ == "__main__":
    unittest.main()
