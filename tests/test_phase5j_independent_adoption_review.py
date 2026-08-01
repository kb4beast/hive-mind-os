from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.independent_adoption_review import (
    compile_independent_adoption_review_packet,
    example_review_packet_request,
)
from hive_mind_os.foundation.independent_adoption_review_contracts import (
    ACTIVE_DEBT_IDS,
    DECISION_OPTIONS,
    DOCUMENTS,
    EXTERNAL_INPUT_IDS,
    HANDOFF_ACTIONS,
    OUTPUT_FIELDS,
    PARTICIPANT_REQUIREMENTS,
    PARTICIPANT_ROLES,
    IndependentAdoptionReviewError,
    validate_independent_adoption_review_packet,
    validate_review_packet_request,
)


class IndependentAdoptionReviewPacketTests(unittest.TestCase):
    def test_example_compiles_deterministically_and_validates(self) -> None:
        request = example_review_packet_request()
        first = compile_independent_adoption_review_packet(request)
        second = compile_independent_adoption_review_packet(request)
        self.assertEqual(first, second)
        validate_independent_adoption_review_packet(first)

    def test_exact_frozen_documents_and_request_bindings_are_preserved(self) -> None:
        request = example_review_packet_request()
        envelope = compile_independent_adoption_review_packet(request)
        manifest = envelope["outputs"]["review_packet_manifest"]
        self.assertEqual(manifest["subject_commit"], request["subject_commit"])
        self.assertEqual(manifest["subject_tree"], request["subject_tree"])
        self.assertEqual(
            manifest["phase5i_envelope_digest"],
            request["phase5i_envelope_digest"],
        )
        observed = [
            (item["document_id"], item["path"], item["status"])
            for item in manifest["documents"]
        ]
        expected = [
            (document_id, path, "frozen-proposed")
            for document_id, path in DOCUMENTS
        ]
        self.assertEqual(observed, expected)
        self.assertEqual(manifest["packet_status"], "ready-for-external-review")
        self.assertEqual(manifest["review_status"], "not-run")

    def test_all_thirty_debts_and_external_inputs_remain_exact(self) -> None:
        envelope = compile_independent_adoption_review_packet(
            example_review_packet_request()
        )
        manifest = envelope["outputs"]["review_packet_manifest"]
        self.assertEqual(tuple(manifest["active_debt_ids"]), ACTIVE_DEBT_IDS)
        self.assertEqual(len(manifest["active_debt_ids"]), 30)
        self.assertEqual(tuple(manifest["external_input_ids"]), EXTERNAL_INPUT_IDS)
        self.assertIn("P5D-DEBT-03", manifest["active_debt_ids"])
        self.assertIn("P5I-DEBT-05", manifest["active_debt_ids"])

    def test_participants_remain_required_unsigned_and_unauthenticated(self) -> None:
        envelope = compile_independent_adoption_review_packet(
            example_review_packet_request()
        )
        requirements = envelope["outputs"]["participant_requirements"]
        self.assertEqual(
            tuple(item["role_id"] for item in requirements["participants"]),
            PARTICIPANT_ROLES,
        )
        for participant in requirements["participants"]:
            self.assertEqual(participant["status"], "required-not-authenticated")
            self.assertEqual(
                tuple(participant["requirements"]),
                PARTICIPANT_REQUIREMENTS,
            )
            for field in (
                "identity_evidence",
                "signature_evidence",
                "execution_evidence",
                "external_retention_evidence",
            ):
                self.assertEqual(participant[field], "missing")
        self.assertFalse(requirements["authenticated_participants"])
        self.assertFalse(requirements["requirements_satisfied"])

    def test_decision_templates_are_complete_unselected_and_unsigned(self) -> None:
        envelope = compile_independent_adoption_review_packet(
            example_review_packet_request()
        )
        templates = envelope["outputs"]["decision_templates"]
        self.assertEqual(
            tuple(option["decision_id"] for option in templates["options"]),
            DECISION_OPTIONS,
        )
        for option in templates["options"]:
            self.assertFalse(option["selected"])
            self.assertFalse(option["signed"])
            self.assertEqual(option["participant_role"], "judge")
            self.assertEqual(
                option["scope_narrowing_required"],
                option["decision_id"] == "adapt",
            )
            self.assertEqual(option["evidence_ref"], "missing")
        self.assertEqual(templates["selected_decision"], "none")
        self.assertFalse(templates["review_completed"])
        self.assertFalse(templates["signed_decision_present"])

    def test_external_handoff_is_explicit_and_grants_nothing(self) -> None:
        envelope = compile_independent_adoption_review_packet(
            example_review_packet_request()
        )
        handoff = envelope["outputs"]["external_handoff"]
        self.assertEqual(handoff["handoff_status"], "external-action-required")
        self.assertEqual(tuple(handoff["actions"]), HANDOFF_ACTIONS)
        for field in (
            "external_submission_received",
            "adr_adopted",
            "p14_eligible",
            "p20_eligible",
            "release_ready",
            "production_ready",
            "deployment_authorized",
            "promotion_eligible",
            "superiority_established",
        ):
            self.assertFalse(handoff[field])
        self.assertEqual(handoff["authority"], "none")
        self.assertEqual(handoff["activation"], "inert")

    def test_request_requires_exact_containers_and_fields(self) -> None:
        request = example_review_packet_request()
        validate_review_packet_request(request)
        with self.assertRaises(IndependentAdoptionReviewError):
            compile_independent_adoption_review_packet(MappingProxyType(request))
        hostile = deepcopy(request)
        hostile["unexpected"] = True
        with self.assertRaises(IndependentAdoptionReviewError):
            validate_review_packet_request(hostile)
        hostile = deepcopy(request)
        hostile["active_debt_ids"] = tuple(ACTIVE_DEBT_IDS)
        with self.assertRaises(IndependentAdoptionReviewError):
            validate_review_packet_request(hostile)
        hostile = deepcopy(request)
        hostile["documents"] = tuple(hostile["documents"])
        with self.assertRaises(IndependentAdoptionReviewError):
            validate_review_packet_request(hostile)

    def test_scope_debt_stage_authority_and_malformed_digest_fail_closed(self) -> None:
        request = example_review_packet_request()
        for field, replacement in (
            ("repository_id", "github:other/repository"),
            ("tenant_id", "tenant:other"),
            ("subject_commit", "0" * 40),
            ("requested_next_stage", "p14"),
            ("authority", "repository"),
            ("activation", "active"),
            ("phase5i_envelope_digest", "not-a-digest"),
        ):
            hostile = deepcopy(request)
            hostile[field] = replacement
            with self.assertRaises(IndependentAdoptionReviewError):
                validate_review_packet_request(hostile)
        hostile = deepcopy(request)
        hostile["active_debt_ids"].pop()
        with self.assertRaises(IndependentAdoptionReviewError):
            validate_review_packet_request(hostile)
        hostile = deepcopy(request)
        hostile["external_input_ids"].reverse()
        with self.assertRaises(IndependentAdoptionReviewError):
            validate_review_packet_request(hostile)

    def test_semantic_reseal_cannot_claim_review_adoption_or_eligibility(self) -> None:
        envelope = compile_independent_adoption_review_packet(
            example_review_packet_request()
        )
        mutations = (
            ("review_packet_manifest", "review_status", "completed"),
            ("participant_requirements", "authenticated_participants", True),
            ("participant_requirements", "requirements_satisfied", True),
            ("decision_templates", "selected_decision", "adopt"),
            ("decision_templates", "review_completed", True),
            ("external_handoff", "external_submission_received", True),
            ("external_handoff", "adr_adopted", True),
            ("external_handoff", "p14_eligible", True),
            ("external_handoff", "p20_eligible", True),
        )
        for output_name, field, replacement in mutations:
            hostile = deepcopy(envelope)
            hostile["outputs"][output_name][field] = replacement
            hostile["output_digests"][output_name] = digest(
                hostile["outputs"][output_name]
            )
            unsigned = {
                key: value
                for key, value in hostile.items()
                if key != "envelope_digest"
            }
            hostile["envelope_digest"] = digest(unsigned)
            with self.assertRaises(IndependentAdoptionReviewError):
                validate_independent_adoption_review_packet(hostile)

    def test_every_output_and_envelope_digest_is_checked(self) -> None:
        envelope = compile_independent_adoption_review_packet(
            example_review_packet_request()
        )
        for field in OUTPUT_FIELDS:
            hostile = deepcopy(envelope)
            hostile["output_digests"][field] = "sha256:" + ("0" * 64)
            with self.assertRaises(IndependentAdoptionReviewError):
                validate_independent_adoption_review_packet(hostile)
        hostile = deepcopy(envelope)
        hostile["envelope_digest"] = "sha256:" + ("0" * 64)
        with self.assertRaises(IndependentAdoptionReviewError):
            validate_independent_adoption_review_packet(hostile)

    def test_outputs_are_defensive_private_and_plan_is_present(self) -> None:
        request = example_review_packet_request()
        envelope = compile_independent_adoption_review_packet(request)
        request["active_debt_ids"].clear()
        request["documents"].clear()
        self.assertEqual(
            tuple(envelope["request"]["active_debt_ids"]),
            ACTIVE_DEBT_IDS,
        )
        self.assertEqual(len(envelope["request"]["documents"]), len(DOCUMENTS))
        envelope["outputs"]["review_packet_manifest"]["active_debt_ids"].clear()
        rebuilt = compile_independent_adoption_review_packet(
            example_review_packet_request()
        )
        self.assertEqual(
            tuple(rebuilt["outputs"]["review_packet_manifest"]["active_debt_ids"]),
            ACTIVE_DEBT_IDS,
        )
        self.assertFalse(
            hasattr(hive_mind_os, "compile_independent_adoption_review_packet")
        )
        self.assertFalse(
            hasattr(foundation, "compile_independent_adoption_review_packet")
        )
        root = Path(__file__).resolve().parents[1]
        plan = root / "docs" / "plan" / "PHASE5_CARRIED_FORWARD_DEBT.md"
        text = plan.read_text(encoding="utf-8")
        for debt_id in ACTIVE_DEBT_IDS:
            self.assertIn(debt_id, text)
        self.assertIn("Phase 5J Independent Adoption Review Packet", text)


if __name__ == "__main__":
    unittest.main()
