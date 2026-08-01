from __future__ import annotations

import unittest
from copy import deepcopy
from pathlib import Path

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.integrator_playbook import (
    compile_integrator_intake,
    example_integrator_request,
)
from hive_mind_os.foundation.integrator_playbook_contracts import (
    ACCEPTED_BASE_COMMIT,
    OUTPUT_FIELDS,
    REQUIRED_DEBT_IDS,
    IntegratorContractError,
    validate_integrator,
    validate_integrator_request,
)


def _reseal(envelope: dict[str, object]) -> None:
    request = envelope["request_snapshot"]
    outputs = envelope["outputs"]
    if type(request) is not dict or type(outputs) is not dict:
        raise AssertionError("test fixture lost exact container types")
    envelope["request_digest"] = digest(request)
    envelope["output_digests"] = {
        field: digest(outputs[field])
        for field in OUTPUT_FIELDS
    }
    body = {key: value for key, value in envelope.items() if key != "envelope_digest"}
    envelope["envelope_digest"] = digest(body)


class IntegratorIntakeTests(unittest.TestCase):
    def test_example_compiles_deterministically_and_validates(self) -> None:
        request = example_integrator_request()
        first = compile_integrator_intake(request)
        second = compile_integrator_intake(request)
        self.assertEqual(first, second)
        validate_integrator(first)
        self.assertEqual(first["request_snapshot"]["subject_commit"], ACCEPTED_BASE_COMMIT)

    def test_all_inherited_debt_is_exact_open_and_release_blocking(self) -> None:
        envelope = compile_integrator_intake(example_integrator_request())
        debt = envelope["outputs"]["debt_register"]
        self.assertEqual(
            tuple(item["debt_id"] for item in debt["items"]),
            REQUIRED_DEBT_IDS,
        )
        self.assertTrue(all(item["status"] == "open" for item in debt["items"]))
        self.assertEqual(debt["unresolved_count"], len(REQUIRED_DEBT_IDS))
        self.assertTrue(debt["release_blocked"])

    def test_request_requires_exact_containers_and_rejects_unknown_fields(self) -> None:
        request = example_integrator_request()
        with self.assertRaises(IntegratorContractError):
            validate_integrator_request(dict(request, unknown=True))
        hostile = deepcopy(request)
        hostile["inherited_debt"] = tuple(hostile["inherited_debt"])
        with self.assertRaises(IntegratorContractError):
            validate_integrator_request(hostile)

    def test_scope_authority_activation_and_next_role_are_fixed(self) -> None:
        mutations = {
            "repository_id": "github:other/repository",
            "tenant_id": "tenant:other",
            "subject_commit": "0" * 40,
            "requested_next_role": "optimizer",
            "authority": "repository",
            "activation": "active",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                request = example_integrator_request()
                request[field] = value
                with self.assertRaises(IntegratorContractError):
                    validate_integrator_request(request)

    def test_resealed_release_authority_and_debt_escalation_fail(self) -> None:
        envelope = compile_integrator_intake(example_integrator_request())
        cases: list[dict[str, object]] = []

        release = deepcopy(envelope)
        release["outputs"]["integration_scope"]["release_recommendation"] = "adopt"
        cases.append(release)

        authority = deepcopy(envelope)
        authority["authority"] = "repository"
        cases.append(authority)

        debt = deepcopy(envelope)
        debt["request_snapshot"]["inherited_debt"][0]["status"] = "resolved"
        debt["outputs"]["debt_register"]["items"][0]["status"] = "resolved"
        cases.append(debt)

        execution = deepcopy(envelope)
        execution["outputs"]["compatibility_plan"]["execution_status"] = "passed"
        cases.append(execution)

        for index, candidate in enumerate(cases):
            with self.subTest(case=index):
                _reseal(candidate)
                with self.assertRaises(IntegratorContractError):
                    validate_integrator(candidate)

    def test_each_output_digest_and_envelope_digest_are_checked(self) -> None:
        envelope = compile_integrator_intake(example_integrator_request())
        for field in OUTPUT_FIELDS:
            with self.subTest(field=field):
                candidate = deepcopy(envelope)
                candidate["output_digests"][field] = "sha256:" + "0" * 64
                with self.assertRaises(IntegratorContractError):
                    validate_integrator(candidate)
        candidate = deepcopy(envelope)
        candidate["envelope_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(IntegratorContractError):
            validate_integrator(candidate)

    def test_outputs_are_defensive_against_caller_mutation(self) -> None:
        request = example_integrator_request()
        envelope = compile_integrator_intake(request)
        request["inherited_debt"][0]["status"] = "caller-mutated"
        self.assertEqual(
            envelope["request_snapshot"]["inherited_debt"][0]["status"],
            "open",
        )
        envelope["outputs"]["debt_register"]["items"][0]["status"] = "output-mutated"
        fresh = compile_integrator_intake(example_integrator_request())
        self.assertEqual(fresh["outputs"]["debt_register"]["items"][0]["status"], "open")

    def test_intake_claims_no_execution_release_or_activation(self) -> None:
        envelope = compile_integrator_intake(example_integrator_request())
        scope = envelope["outputs"]["integration_scope"]
        plan = envelope["outputs"]["compatibility_plan"]
        handoff = envelope["outputs"]["steward_handoff"]
        self.assertEqual(scope["release_recommendation"], "defer")
        self.assertEqual(plan["execution_status"], "not-run")
        self.assertFalse(plan["implementation_authorized"])
        self.assertFalse(plan["release_authorized"])
        self.assertEqual(handoff["status"], "blocked")
        self.assertFalse(handoff["implementation_authorized"])
        self.assertFalse(handoff["release_authorized"])
        self.assertFalse(handoff["activation_authorized"])

    def test_modules_are_package_private_and_plan_debt_is_present(self) -> None:
        self.assertFalse(hasattr(hive_mind_os, "compile_integrator_intake"))
        self.assertFalse(hasattr(foundation, "compile_integrator_intake"))
        plan = Path(__file__).resolve().parents[1] / "docs" / "plan" / "PHASE5_CARRIED_FORWARD_DEBT.md"
        text = plan.read_text(encoding="utf-8")
        for debt_id in REQUIRED_DEBT_IDS:
            self.assertIn(debt_id, text)


if __name__ == "__main__":
    unittest.main()
