from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.post_p13_adoption import (
    compile_post_p13_adoption_docket,
    example_adoption_request,
)
from hive_mind_os.foundation.post_p13_adoption_contracts import (
    ACTIVE_DEBT_IDS,
    ADOPTION_ROLES,
    DOCUMENTS,
    EXTERNAL_INPUT_IDS,
    OUTPUT_FIELDS,
    AdoptionDocketError,
    validate_adoption_request,
    validate_post_p13_adoption_docket,
)


class PostP13AdoptionDocketTests(unittest.TestCase):
    def test_example_compiles_deterministically_and_validates(self) -> None:
        request = example_adoption_request()
        first = compile_post_p13_adoption_docket(request)
        second = compile_post_p13_adoption_docket(request)
        self.assertEqual(first, second)
        validate_post_p13_adoption_docket(first)

    def test_documents_remain_exact_proposed_and_request_bound(self) -> None:
        request = example_adoption_request()
        request["adr_digest"] = "sha256:" + ("5" * 64)
        request["program_digest"] = "sha256:" + ("6" * 64)
        request["debt_plan_digest"] = "sha256:" + ("7" * 64)
        envelope = compile_post_p13_adoption_docket(request)
        manifest = envelope["outputs"]["document_manifest"]
        self.assertEqual(manifest["overall_status"], "proposed")
        observed = [
            (item["document_id"], item["path"], item["status"])
            for item in manifest["documents"]
        ]
        expected = [
            (document_id, path, "proposed")
            for document_id, path in DOCUMENTS
        ]
        self.assertEqual(observed, expected)
        self.assertEqual(
            [item["digest"] for item in manifest["documents"]],
            [
                request["adr_digest"],
                request["program_digest"],
                request["debt_plan_digest"],
            ],
        )

    def test_all_twenty_five_debts_remain_active(self) -> None:
        envelope = compile_post_p13_adoption_docket(example_adoption_request())
        disposition = envelope["outputs"]["adoption_disposition"]
        self.assertEqual(tuple(disposition["active_debt_ids"]), ACTIVE_DEBT_IDS)
        self.assertEqual(len(disposition["active_debt_ids"]), 25)
        self.assertIn("P5D-DEBT-03", disposition["active_debt_ids"])

    def test_independent_roles_remain_required_and_unauthenticated(self) -> None:
        envelope = compile_post_p13_adoption_docket(example_adoption_request())
        requirements = envelope["outputs"]["adoption_requirements"]
        self.assertEqual(
            tuple(item["role_id"] for item in requirements["roles"]),
            ADOPTION_ROLES,
        )
        for role in requirements["roles"]:
            self.assertEqual(role["status"], "required-not-authenticated")
            self.assertEqual(role["identity_evidence"], "missing")
            self.assertEqual(role["execution_evidence"], "missing")
        self.assertFalse(requirements["authenticated_participants"])
        self.assertFalse(requirements["evidence_retained_externally"])
        self.assertFalse(requirements["requirements_complete"])

    def test_external_inputs_remain_missing(self) -> None:
        envelope = compile_post_p13_adoption_docket(example_adoption_request())
        register = envelope["outputs"]["external_input_register"]
        self.assertEqual(
            tuple(item["input_id"] for item in register["inputs"]),
            EXTERNAL_INPUT_IDS,
        )
        for item in register["inputs"]:
            self.assertEqual(item["status"], "missing")
            self.assertEqual(item["evidence_ref"], "missing")
        self.assertFalse(register["all_present"])

    def test_disposition_blocks_adoption_p14_p20_and_release(self) -> None:
        envelope = compile_post_p13_adoption_docket(example_adoption_request())
        disposition = envelope["outputs"]["adoption_disposition"]
        self.assertEqual(
            disposition["disposition"],
            "awaiting-independent-adoption",
        )
        for field in (
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
        request = example_adoption_request()
        validate_adoption_request(request)
        with self.assertRaises(AdoptionDocketError):
            compile_post_p13_adoption_docket(MappingProxyType(request))
        hostile = deepcopy(request)
        hostile["unexpected"] = True
        with self.assertRaises(AdoptionDocketError):
            validate_adoption_request(hostile)
        hostile = deepcopy(request)
        hostile["active_debt_ids"] = tuple(ACTIVE_DEBT_IDS)
        with self.assertRaises(AdoptionDocketError):
            validate_adoption_request(hostile)

    def test_scope_debt_stage_authority_and_malformed_digest_fail_closed(self) -> None:
        request = example_adoption_request()
        for field, replacement in (
            ("repository_id", "github:other/repository"),
            ("tenant_id", "tenant:other"),
            ("subject_commit", "0" * 40),
            ("requested_next_stage", "p14"),
            ("authority", "repository"),
            ("activation", "active"),
            ("adr_digest", "not-a-digest"),
        ):
            hostile = deepcopy(request)
            hostile[field] = replacement
            with self.assertRaises(AdoptionDocketError):
                validate_adoption_request(hostile)
        hostile = deepcopy(request)
        hostile["active_debt_ids"].pop()
        with self.assertRaises(AdoptionDocketError):
            validate_adoption_request(hostile)

    def test_semantic_reseal_cannot_claim_adoption_or_external_evidence(self) -> None:
        envelope = compile_post_p13_adoption_docket(example_adoption_request())
        mutations = (
            ("document_manifest", "overall_status", "adopted"),
            ("adoption_requirements", "authenticated_participants", True),
            ("external_input_register", "all_present", True),
            ("adoption_disposition", "adr_adopted", True),
            ("adoption_disposition", "p14_eligible", True),
            ("adoption_disposition", "p20_eligible", True),
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
            with self.assertRaises(AdoptionDocketError):
                validate_post_p13_adoption_docket(hostile)

    def test_every_output_and_envelope_digest_is_checked(self) -> None:
        envelope = compile_post_p13_adoption_docket(example_adoption_request())
        for field in OUTPUT_FIELDS:
            hostile = deepcopy(envelope)
            hostile["output_digests"][field] = "sha256:" + ("0" * 64)
            with self.assertRaises(AdoptionDocketError):
                validate_post_p13_adoption_docket(hostile)
        hostile = deepcopy(envelope)
        hostile["envelope_digest"] = "sha256:" + ("0" * 64)
        with self.assertRaises(AdoptionDocketError):
            validate_post_p13_adoption_docket(hostile)

    def test_outputs_are_defensive_private_and_plan_is_present(self) -> None:
        request = example_adoption_request()
        envelope = compile_post_p13_adoption_docket(request)
        request["active_debt_ids"].clear()
        self.assertEqual(
            tuple(envelope["request"]["active_debt_ids"]),
            ACTIVE_DEBT_IDS,
        )
        envelope["outputs"]["adoption_disposition"]["active_debt_ids"].clear()
        rebuilt = compile_post_p13_adoption_docket(example_adoption_request())
        self.assertEqual(
            tuple(rebuilt["outputs"]["adoption_disposition"]["active_debt_ids"]),
            ACTIVE_DEBT_IDS,
        )
        self.assertFalse(hasattr(hive_mind_os, "compile_post_p13_adoption_docket"))
        self.assertFalse(
            hasattr(foundation, "compile_post_p13_adoption_docket")
        )
        root = Path(__file__).resolve().parents[1]
        plan = root / "docs" / "plan" / "PHASE5_CARRIED_FORWARD_DEBT.md"
        text = plan.read_text(encoding="utf-8")
        for debt_id in ACTIVE_DEBT_IDS:
            self.assertIn(debt_id, text)


if __name__ == "__main__":
    unittest.main()
