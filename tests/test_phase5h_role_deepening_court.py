from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.role_deepening_court import (
    compile_role_deepening_court,
    example_consolidation_request,
)
from hive_mind_os.foundation.role_deepening_court_contracts import (
    ACTIVE_DEBT_IDS,
    CONFLICT_IDS,
    EVIDENCE_CATEGORIES,
    OUTPUT_FIELDS,
    REOPENED_DEBT_IDS,
    ROLE_SEQUENCE,
    ConsolidationCourtError,
    validate_consolidation_request,
    validate_role_deepening_court,
)


class RoleDeepeningCourtTests(unittest.TestCase):
    def test_example_compiles_deterministically_and_validates(self) -> None:
        request = example_consolidation_request()
        first = compile_role_deepening_court(request)
        second = compile_role_deepening_court(request)
        self.assertEqual(first, second)
        validate_role_deepening_court(first)

    def test_exact_eight_role_sequence_is_preserved(self) -> None:
        envelope = compile_role_deepening_court(example_consolidation_request())
        roles = envelope["outputs"]["role_inventory"]["roles"]
        observed = tuple((item["phase_id"], item["role_id"]) for item in roles)
        self.assertEqual(observed, ROLE_SEQUENCE)
        self.assertTrue(envelope["outputs"]["role_inventory"]["complete_role_sequence"])
        for item in roles:
            self.assertEqual(item["status"], "bounded-candidate")
            self.assertEqual(item["authority"], "none")
            self.assertEqual(item["activation"], "inert")
            self.assertFalse(item["release_eligible"])

    def test_all_twenty_active_debts_and_reopened_status_are_preserved(self) -> None:
        envelope = compile_role_deepening_court(example_consolidation_request())
        debts = envelope["outputs"]["conflict_register"]["debt_items"]
        self.assertEqual(tuple(item["debt_id"] for item in debts), ACTIVE_DEBT_IDS)
        for item in debts:
            expected = "reopened" if item["debt_id"] in REOPENED_DEBT_IDS else "open"
            self.assertEqual(item["status"], expected)
        self.assertFalse(envelope["outputs"]["conflict_register"]["all_resolved"])

    def test_evidence_and_conflicts_cannot_claim_completion(self) -> None:
        envelope = compile_role_deepening_court(example_consolidation_request())
        coverage = envelope["outputs"]["evidence_coverage"]
        self.assertEqual(
            tuple(item["category_id"] for item in coverage["categories"]),
            EVIDENCE_CATEGORIES,
        )
        self.assertEqual(coverage["overall_status"], "incomplete")
        self.assertFalse(coverage["independently_verified"])
        conflicts = envelope["outputs"]["conflict_register"]["conflicts"]
        self.assertEqual(tuple(item["conflict_id"] for item in conflicts), CONFLICT_IDS)
        self.assertTrue(all(item["status"] == "unresolved" for item in conflicts))

    def test_disposition_is_non_release_and_p20_ineligible(self) -> None:
        disposition = compile_role_deepening_court(example_consolidation_request())["outputs"][
            "court_disposition"
        ]
        self.assertEqual(disposition["disposition"], "defer-non-release")
        for field in (
            "p20_eligible",
            "release_ready",
            "production_ready",
            "promotion_eligible",
            "authenticated_independence",
            "superiority_established",
        ):
            self.assertFalse(disposition[field])
        self.assertEqual(disposition["authority"], "none")
        self.assertEqual(disposition["activation"], "inert")

    def test_request_rejects_scope_role_and_debt_substitution(self) -> None:
        request = example_consolidation_request()
        validate_consolidation_request(request)
        for field, replacement in (
            ("repository_id", "github:other/repository"),
            ("tenant_id", "tenant:other"),
            ("subject_commit", "0" * 40),
            ("authority", "release"),
            ("activation", "active"),
        ):
            hostile = deepcopy(request)
            hostile[field] = replacement
            with self.assertRaises(ConsolidationCourtError):
                validate_consolidation_request(hostile)
        hostile = deepcopy(request)
        hostile["role_entries"].reverse()
        with self.assertRaises(ConsolidationCourtError):
            validate_consolidation_request(hostile)
        hostile = deepcopy(request)
        hostile["debt_items"].pop()
        with self.assertRaises(ConsolidationCourtError):
            validate_consolidation_request(hostile)

    def test_request_requires_exact_containers_and_rejects_private_content(self) -> None:
        request = example_consolidation_request()
        hostile = deepcopy(request)
        hostile["role_entries"] = tuple(hostile["role_entries"])
        with self.assertRaises(ConsolidationCourtError):
            validate_consolidation_request(hostile)
        hostile = deepcopy(request)
        hostile["secret"] = "not-admitted"
        with self.assertRaises((ConsolidationCourtError, ValueError)):
            validate_consolidation_request(hostile)

    def test_semantic_resealing_cannot_escalate_disposition_or_evidence(self) -> None:
        envelope = compile_role_deepening_court(example_consolidation_request())
        mutations = (
            ("court_disposition", "p20_eligible", True),
            ("court_disposition", "release_ready", True),
            ("court_disposition", "disposition", "adopt-release"),
            ("evidence_coverage", "overall_status", "complete"),
            ("conflict_register", "all_resolved", True),
        )
        for output_name, field, replacement in mutations:
            hostile = deepcopy(envelope)
            hostile["outputs"][output_name][field] = replacement
            hostile["output_digests"][output_name] = digest(
                hostile["outputs"][output_name]
            )
            body = {key: value for key, value in hostile.items() if key != "envelope_digest"}
            hostile["envelope_digest"] = digest(body)
            with self.assertRaises(ConsolidationCourtError):
                validate_role_deepening_court(hostile)

    def test_every_output_and_envelope_digest_is_checked(self) -> None:
        envelope = compile_role_deepening_court(example_consolidation_request())
        for field in OUTPUT_FIELDS:
            hostile = deepcopy(envelope)
            hostile["output_digests"][field] = "sha256:" + ("0" * 64)
            with self.assertRaises(ConsolidationCourtError):
                validate_role_deepening_court(hostile)
        hostile = deepcopy(envelope)
        hostile["envelope_digest"] = "sha256:" + ("0" * 64)
        with self.assertRaises(ConsolidationCourtError):
            validate_role_deepening_court(hostile)

    def test_outputs_are_defensive_private_and_plan_is_present(self) -> None:
        request = example_consolidation_request()
        envelope = compile_role_deepening_court(request)
        request["role_entries"].clear()
        request["debt_items"].clear()
        self.assertEqual(len(envelope["request"]["role_entries"]), len(ROLE_SEQUENCE))
        self.assertEqual(len(envelope["request"]["debt_items"]), len(ACTIVE_DEBT_IDS))
        rebuilt = compile_role_deepening_court(example_consolidation_request())
        self.assertEqual(
            tuple(item["debt_id"] for item in rebuilt["request"]["debt_items"]),
            ACTIVE_DEBT_IDS,
        )
        self.assertFalse(hasattr(hive_mind_os, "compile_role_deepening_court"))
        self.assertFalse(hasattr(foundation, "compile_role_deepening_court"))
        root = Path(__file__).resolve().parents[1]
        plan = root / "docs" / "plan" / "PHASE5_CARRIED_FORWARD_DEBT.md"
        self.assertTrue(plan.is_file())
        text = plan.read_text(encoding="utf-8")
        for debt_id in ACTIVE_DEBT_IDS:
            self.assertIn(debt_id, text)


if __name__ == "__main__":
    unittest.main()
