from __future__ import annotations

import copy
import inspect
import math
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os import cli
from hive_mind_os.foundation import curator_playbook as curator_module
from hive_mind_os.foundation.architect_playbook import (
    compile_architect_design,
    example_architect_request,
)
from hive_mind_os.foundation.architect_playbook_contracts import validate_architect
from hive_mind_os.foundation.builder_playbook import (
    compile_builder_implementation,
    example_builder_request,
)
from hive_mind_os.foundation.builder_playbook_contracts import validate_builder
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.curator_playbook import (
    CuratorContractError,
    _compile_unpinned_successor,
    _current_fingerprint,
    compile_curator_successor,
    compile_curator_verification,
    curator_successor_bytes,
    curator_verification_bytes,
    example_curator_request,
)
from hive_mind_os.foundation.curator_playbook_contracts import (
    AGENT_ID,
    BASE_DEFINITION_ID,
    COURT_ROLES,
    CURATOR_SCHEMA_NAMES,
    DEFINITION_ID,
    EXPECTED_SUCCESSOR_DIGEST,
    LAYER_IDS,
    LAYER_KINDS,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_curator,
    validate_curator_catalog,
)
from hive_mind_os.foundation.orchestrator_playbook import (
    compile_orchestrator_plan,
    example_orchestrator_request,
)
from hive_mind_os.foundation.orchestrator_playbook_contracts import (
    validate_orchestrator,
)

REPOSITORY = Path(__file__).parents[1]


class _HostileDict(dict):
    pass


class _HostileList(list):
    pass


def _request(**changes: object) -> dict[str, object]:
    request = copy.deepcopy(example_curator_request())
    request.update(changes)
    return request


def _resign_output(envelope: dict[str, object], field: str) -> None:
    outputs = envelope["outputs"]
    assert type(outputs) is dict
    output = outputs[field]
    assert type(output) is dict
    output["output_digest"] = digest(
        {key: value for key, value in output.items() if key != "output_digest"}
    )
    envelope["verification_digest"] = digest(
        {key: value for key, value in envelope.items() if key != "verification_digest"}
    )


def _set_path(document: object, path: tuple[object, ...], value: object) -> None:
    current = document
    for part in path[:-1]:
        current = current[part]  # type: ignore[index]
    current[path[-1]] = value  # type: ignore[index]


def _scalar_leaves(
    value: object, path: tuple[object, ...] = ()
) -> list[tuple[tuple[object, ...], object]]:
    leaves: list[tuple[tuple[object, ...], object]] = []
    if type(value) is dict:
        for key, child in value.items():  # type: ignore[union-attr]
            if key == "output_digest":
                continue
            leaves.extend(_scalar_leaves(child, (*path, key)))
    elif type(value) is list:
        for index, child in enumerate(value):  # type: ignore[arg-type]
            leaves.extend(_scalar_leaves(child, (*path, index)))
    else:
        leaves.append((path, value))
    return leaves


def _mutated_scalar(value: object) -> object:
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if type(value) is float:
        return value + 1.0
    if type(value) is str:
        if value.startswith("sha256:") and len(value) == 71:
            return "sha256:" + ("f" * 64)
        if len(value) == 40 and set(value) <= set("0123456789abcdef"):
            return "f" * 40
        return value + ":mutated"
    if value is None:
        return "mutated"
    raise TypeError(type(value).__name__)


class CuratorContractTests(unittest.TestCase):
    def test_catalog_is_strict_separate_and_complete(self) -> None:
        result = validate_curator_catalog()
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(len(CURATOR_SCHEMA_NAMES), 14)
        self.assertEqual(len(set(CURATOR_SCHEMA_NAMES)), 14)
        self.assertEqual(len(OUTPUT_FIELDS), 11)
        self.assertEqual(set(OUTPUT_SCHEMA_BY_FIELD), set(OUTPUT_FIELDS))
        self.assertEqual(RESOURCE_SECTIONS, OUTPUT_FIELDS)
        self.assertEqual(len(COURT_ROLES), 10)

    def test_successor_identity_lineage_and_digest_are_fixed(self) -> None:
        successor = compile_curator_successor()
        self.assertEqual(successor["agent_id"], AGENT_ID)
        self.assertEqual(successor["definition_id"], DEFINITION_ID)
        self.assertEqual(successor["base_definition_id"], BASE_DEFINITION_ID)
        self.assertEqual(successor["content_digest"], EXPECTED_SUCCESSOR_DIGEST)
        self.assertTrue(validate_curator("curator-agent-successor-v1", successor).valid)

    def test_successor_layers_are_fixed_ordered_and_sealed(self) -> None:
        successor = compile_curator_successor()
        self.assertEqual([item["position"] for item in successor["layers"]], list(range(1, 9)))
        self.assertEqual(tuple(item["layer_id"] for item in successor["layers"]), LAYER_IDS)
        self.assertEqual(tuple(item["kind"] for item in successor["layers"]), LAYER_KINDS)
        for item in successor["layers"]:
            self.assertEqual(
                item["digest"],
                digest({key: value for key, value in item.items() if key != "digest"}),
            )

    def test_successor_is_inert_private_authority_free_and_unbound(self) -> None:
        successor = compile_curator_successor()
        self.assertEqual(successor["activation"], "inert")
        self.assertEqual(successor["authority"], "none")
        self.assertFalse(successor["public"])
        self.assertEqual(successor["effective_capabilities"], [])
        self.assertEqual(successor["tool_refs"], [])
        for field in (
            "implementation_authorized",
            "execution_authorized",
            "test_result_authorized",
            "completion_authorized",
            "release_authorized",
            "approval_authorized",
            "promotion_authorized",
        ):
            self.assertFalse(successor[field])

    def test_successor_output_contracts_are_distinct_and_ordered(self) -> None:
        successor = compile_curator_successor()
        self.assertEqual(
            successor["output_contract_refs"],
            [OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS],
        )

    def test_successor_is_deterministic_and_defensive(self) -> None:
        first = compile_curator_successor()
        second = compile_curator_successor()
        self.assertEqual(first, second)
        self.assertEqual(curator_successor_bytes(), curator_successor_bytes())
        first["layers"][0]["layer_id"] = "mutated"
        self.assertNotEqual(first, compile_curator_successor())

    def test_phase2_projection_drift_fails_closed(self) -> None:
        with patch.object(curator_module, "BASE_PROJECTION_DIGEST", "sha256:" + ("0" * 64)):
            with self.assertRaisesRegex(ValueError, "projection drifted"):
                _compile_unpinned_successor()

    def test_resealed_successor_layer_drift_fails(self) -> None:
        successor = compile_curator_successor()
        successor["layers"][2]["layer_id"] = "curator:weakened"
        item = successor["layers"][2]
        item["digest"] = digest({key: value for key, value in item.items() if key != "digest"})
        successor["content_digest"] = digest(
            {key: value for key, value in successor.items() if key != "content_digest"}
        )
        result = validate_curator(
            "curator-agent-successor-v1", successor, enforce_reviewed_successor=False
        )
        self.assertFalse(result.valid)

    def test_authority_escalation_fails_even_when_resealed(self) -> None:
        mutations = {
            "activation": "active",
            "authority": "repository",
            "public": True,
            "effective_capabilities": ["approve_release"],
            "tool_refs": ["tool.release"],
            "approval_authorized": True,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                successor = compile_curator_successor()
                successor[field] = value
                successor["content_digest"] = digest(
                    {key: item for key, item in successor.items() if key != "content_digest"}
                )
                self.assertFalse(
                    validate_curator(
                        "curator-agent-successor-v1",
                        successor,
                        enforce_reviewed_successor=False,
                    ).valid
                )


class CuratorRequestTests(unittest.TestCase):
    def test_example_request_compiles_and_all_outputs_validate(self) -> None:
        envelope = compile_curator_verification(example_curator_request())
        self.assertTrue(
            validate_curator("curator-verification-envelope-v1", envelope).valid
        )
        self.assertEqual(tuple(envelope["outputs"]), OUTPUT_FIELDS)
        for field in OUTPUT_FIELDS:
            with self.subTest(field=field):
                result = validate_curator(
                    OUTPUT_SCHEMA_BY_FIELD[field], envelope["outputs"][field]
                )
                self.assertTrue(result.valid, result.issues)

    def test_request_requires_exact_builtin_containers(self) -> None:
        for value in (_HostileDict(example_curator_request()), _HostileList()):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(CuratorContractError):
                    compile_curator_verification(value)  # type: ignore[arg-type]

    def test_unknown_fields_and_private_content_fail_closed(self) -> None:
        request = _request()
        request["unknown"] = "field"
        with self.assertRaises(CuratorContractError):
            compile_curator_verification(request)
        request = _request(secret="private")
        with self.assertRaises(CuratorContractError):
            compile_curator_verification(request)

    def test_duplicate_identifiers_fail_closed(self) -> None:
        for field, id_field in (
            ("claims", "claim_id"),
            ("sealed_checks", "check_id"),
            ("observed_evidence", "evidence_id"),
            ("sources", "source_id"),
            ("regression_targets", "target_id"),
        ):
            with self.subTest(field=field):
                request = _request()
                request[field].append(copy.deepcopy(request[field][0]))  # type: ignore[index,union-attr]
                self.assertEqual(
                    request[field][0][id_field], request[field][-1][id_field]  # type: ignore[index]
                )
                with self.assertRaises(CuratorContractError):
                    compile_curator_verification(request)

    def test_same_identity_or_wrong_role_fails_closed(self) -> None:
        request = _request()
        request["curator_identity"]["actor_id"] = request["builder_identity"]["actor_id"]  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "same identity"):
            compile_curator_verification(request)
        request = _request()
        request["curator_identity"]["role"] = "builder"  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "incorrect roles"):
            compile_curator_verification(request)

    def test_blind_seal_must_precede_candidate_access(self) -> None:
        request = _request(blind_seal_sequence=2, candidate_access_sequence=2)
        with self.assertRaisesRegex(CuratorContractError, "not sealed"):
            compile_curator_verification(request)
        request = _request()
        request["sealed_checks"][0]["sealed_before_candidate_access"] = False  # type: ignore[index]
        with self.assertRaises(CuratorContractError):
            compile_curator_verification(request)

    def test_claim_acceptance_check_and_source_coverage_is_complete(self) -> None:
        mutations = []
        request = _request()
        request["claims"][0]["acceptance_refs"] = []  # type: ignore[index]
        mutations.append(request)
        request = _request()
        request["sealed_checks"][0]["claim_refs"] = []  # type: ignore[index]
        mutations.append(request)
        request = _request()
        request["sources"][0]["claim_refs"] = []  # type: ignore[index]
        request["sources"][1]["claim_refs"] = []  # type: ignore[index]
        mutations.append(request)
        for request in mutations:
            with self.subTest(index=mutations.index(request)):
                with self.assertRaises(CuratorContractError):
                    compile_curator_verification(request)

    def test_point_in_time_and_cross_scope_substitution_fail_closed(self) -> None:
        request = _request(repository_id="repository:foreign")
        with self.assertRaisesRegex(CuratorContractError, "scope"):
            compile_curator_verification(request)
        request = _request()
        request["point_in_time"]["future_commit_refs"] = ["f" * 40]  # type: ignore[index]
        with self.assertRaises(CuratorContractError):
            compile_curator_verification(request)
        request = _request()
        request["observed_evidence"][0]["subject_commit"] = "e" * 40  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "future or foreign"):
            compile_curator_verification(request)

    def test_known_and_unknown_resource_accounting(self) -> None:
        known = compile_curator_verification(example_curator_request())
        self.assertEqual(known["resource_accounting"]["accounting_status"], "known")
        for axis in RESOURCE_AXES:
            item = known["resource_accounting"]["axes"][axis]
            self.assertEqual(set(item["section_allocations"]), set(RESOURCE_SECTIONS))
            self.assertEqual(
                item["ceiling"],
                item["verification_reserve"]
                + item["evidence_reserve"]
                + item["rollback_reserve"]
                + sum(item["section_allocations"].values()),
            )
        unknown = compile_curator_verification(example_curator_request(known_budget=False))
        self.assertEqual(unknown["resource_accounting"]["accounting_status"], "unknown")
        for axis in RESOURCE_AXES:
            item = unknown["resource_accounting"]["axes"][axis]
            self.assertIsNone(item["ceiling"])
            self.assertTrue(all(value is None for value in item["section_allocations"].values()))

    def test_mixed_or_unfunded_resources_fail_closed(self) -> None:
        request = _request()
        request["budgets"]["tokens"] = None  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "wholly known or wholly unknown"):
            compile_curator_verification(request)
        request = _request()
        request["verification_reserve_ppm"] = 900_000
        request["evidence_reserve_ppm"] = 100_000
        with self.assertRaisesRegex(CuratorContractError, "consume the full"):
            compile_curator_verification(request)

    def test_caller_claims_and_repeated_progress_fail_closed(self) -> None:
        request = _request()
        request["caller_claims"]["tests_passed"] = True  # type: ignore[index]
        with self.assertRaises(CuratorContractError):
            compile_curator_verification(request)
        request = _request()
        request["prior_fingerprints"] = [_current_fingerprint(request)]
        with self.assertRaisesRegex(CuratorContractError, "repeats"):
            compile_curator_verification(request)

    def test_nonfinite_and_oversized_values_fail_closed(self) -> None:
        request = _request()
        request["budgets"]["tokens"] = math.inf  # type: ignore[index]
        with self.assertRaises(CuratorContractError):
            compile_curator_verification(request)
        request = _request(objective="x" * 20_000)
        with self.assertRaises(CuratorContractError):
            compile_curator_verification(request)


class CuratorAdversarialTests(unittest.TestCase):
    def test_false_green_builder_test_evidence_is_rejected(self) -> None:
        request = _request()
        request["observed_evidence"][3]["producer_role"] = "builder"  # type: ignore[index]
        request["observed_evidence"][3]["producer_actor_id"] = "procedural:builder"  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "self-verification"):
            compile_curator_verification(request)

    def test_forged_and_stale_evidence_is_rejected(self) -> None:
        request = _request()
        request["observed_evidence"][0]["integrity_status"] = "forged"  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "forged or unverifiable"):
            compile_curator_verification(request)
        request = _request()
        request["observed_evidence"][0]["stale"] = True  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "stale"):
            compile_curator_verification(request)

    def test_required_receipt_fields_cannot_be_forged_or_omitted(self) -> None:
        request = _request()
        request["observed_evidence"][3]["receipt_fields"].remove("subject_tree")  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "lacks complete receipt"):
            compile_curator_verification(request)

    def test_source_and_license_gaps_block_material_claims(self) -> None:
        for field, value in (("license_status", "unknown"), ("completeness", "partial")):
            with self.subTest(field=field):
                request = _request()
                request["sources"][0][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(CuratorContractError, "cannot support"):
                    compile_curator_verification(request)

    def test_test_weakening_and_test_removal_fail_closed(self) -> None:
        request = _request()
        request["regression_targets"][1]["assertions_after"] = 0  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "weakens assertions"):
            compile_curator_verification(request)
        request = _request()
        request["regression_targets"][1]["test_functions_after"] = 0  # type: ignore[index]
        with self.assertRaisesRegex(CuratorContractError, "removes tests"):
            compile_curator_verification(request)

    def test_builder_envelope_tenant_repository_subject_and_handoff_are_bound(self) -> None:
        mutations = []
        request = _request()
        request["builder_envelope"]["tenant_id"] = "tenant:foreign"  # type: ignore[index]
        mutations.append(request)
        request = _request()
        request["builder_envelope"]["request_snapshot"]["scope"]["subject_tree"] = "f" * 40  # type: ignore[index]
        mutations.append(request)
        request = _request()
        handoff = request["builder_envelope"]["outputs"]["curator_handoff"]  # type: ignore[index]
        handoff["next_role"] = "integrator"
        handoff["output_digest"] = digest(
            {key: value for key, value in handoff.items() if key != "output_digest"}
        )
        request["builder_envelope"]["implementation_digest"] = digest(  # type: ignore[index]
            {
                key: value
                for key, value in request["builder_envelope"].items()  # type: ignore[union-attr]
                if key != "implementation_digest"
            }
        )
        mutations.append(request)
        for request in mutations:
            with self.subTest(index=mutations.index(request)):
                with self.assertRaises(CuratorContractError):
                    compile_curator_verification(request)

    def test_direct_output_and_envelope_digest_mutations_fail(self) -> None:
        envelope = compile_curator_verification(example_curator_request())
        envelope["outputs"]["verification_scope"]["output_digest"] = "sha256:" + ("f" * 64)
        self.assertFalse(validate_curator("curator-verification-envelope-v1", envelope).valid)
        envelope = compile_curator_verification(example_curator_request())
        envelope["verification_digest"] = "sha256:" + ("f" * 64)
        self.assertFalse(validate_curator("curator-verification-envelope-v1", envelope).valid)

    def test_resealed_cross_request_repository_tenant_and_subject_mutations_fail(self) -> None:
        mutations = (
            ("verification_scope", ("repository_id",), "repository:foreign"),
            ("claim_reconstruction", ("tenant_id",), "tenant:foreign"),
            ("clean_boundary_reproduction", ("subject_commit",), "f" * 40),
            ("release_recommendation", ("authority_state", "approval_authorized"), True),
        )
        for field, path, value in mutations:
            with self.subTest(field=field, path=path):
                envelope = compile_curator_verification(example_curator_request())
                _set_path(envelope["outputs"][field], path, value)
                _resign_output(envelope, field)
                result = validate_curator("curator-verification-envelope-v1", envelope)
                self.assertFalse(result.valid)

    def test_all_scalar_leaf_reseals_are_rejected(self) -> None:
        baseline = compile_curator_verification(example_curator_request())
        mutation_count = 0
        for field in OUTPUT_FIELDS:
            leaves = _scalar_leaves(baseline["outputs"][field])
            self.assertTrue(leaves)
            for path, value in leaves:
                with self.subTest(field=field, path=path):
                    envelope = copy.deepcopy(baseline)
                    _set_path(envelope["outputs"][field], path, _mutated_scalar(value))
                    _resign_output(envelope, field)
                    result = validate_curator("curator-verification-envelope-v1", envelope)
                    self.assertFalse(result.valid)
                    mutation_count += 1
        self.assertGreater(mutation_count, 700)


class CuratorOutputTests(unittest.TestCase):
    def test_outputs_bind_request_builder_scope_authority_budget_evidence_and_rollback(self) -> None:
        request = example_curator_request()
        envelope = compile_curator_verification(request)
        expected_claims = sorted(item["claim_id"] for item in request["claims"])
        expected_acceptance = sorted(item["acceptance_id"] for item in request["acceptance_criteria"])
        expected_evidence = sorted(item["evidence_id"] for item in request["observed_evidence"])
        for field in OUTPUT_FIELDS:
            with self.subTest(field=field):
                output = envelope["outputs"][field]
                self.assertEqual(output["request_id"], request["request_id"])
                self.assertEqual(output["request_digest"], envelope["request_digest"])
                self.assertEqual(output["tenant_id"], request["tenant_id"])
                self.assertEqual(output["repository_id"], request["repository_id"])
                self.assertEqual(output["subject_commit"], request["subject_commit"])
                self.assertEqual(output["subject_tree"], request["subject_tree"])
                self.assertEqual(output["curator_definition_id"], DEFINITION_ID)
                self.assertEqual(output["claim_refs"], expected_claims)
                self.assertEqual(output["acceptance_refs"], expected_acceptance)
                self.assertEqual(output["evidence_refs"], expected_evidence)
                self.assertEqual(output["rollback_refs"], request["rollback_refs"])
                self.assertEqual(output["authority_state"]["authority"], "none")
                self.assertFalse(output["authenticated_distinct_actors"])
                self.assertTrue(output["same_assistant_performed_procedural_passes"])
                self.assertFalse(output["independence_claimed"])

    def test_release_recommendation_is_bounded_to_defer(self) -> None:
        output = compile_curator_verification(example_curator_request())["outputs"][
            "release_recommendation"
        ]
        self.assertEqual(output["structural_status"], "pass")
        self.assertEqual(output["recommendation"], "defer")
        self.assertTrue(output["requested_recommendation_eligible"])
        self.assertFalse(output["release_ready"])
        self.assertFalse(output["release_authorized"])
        self.assertFalse(output["approval_authorized"])

    def test_playbook_claims_no_execution_completion_release_or_artifact_creation(self) -> None:
        outputs = compile_curator_verification(example_curator_request())["outputs"]
        self.assertFalse(outputs["clean_boundary_reproduction"]["commands_executed_by_playbook"])
        self.assertFalse(outputs["clean_boundary_reproduction"]["test_results_authorized"])
        self.assertFalse(outputs["counterexample_search"]["counterexamples_executed_by_playbook"])
        self.assertFalse(outputs["artifact_receipt_verification"]["artifacts_created_by_playbook"])
        self.assertFalse(outputs["artifact_receipt_verification"]["verification_authorized"])
        self.assertFalse(outputs["rollback_verification"]["rollback_executed_by_playbook"])
        self.assertFalse(outputs["rollback_verification"]["rollback_verified_by_playbook"])
        self.assertFalse(outputs["rollback_verification"]["rollback_authorized"])

    def test_dissent_and_unresolved_evidence_are_preserved(self) -> None:
        output = compile_curator_verification(example_curator_request())["outputs"][
            "dissent_unresolved_evidence"
        ]
        self.assertTrue(output["dissent_preserved"])
        self.assertFalse(output["missing_evidence_is_permission"])
        unresolved = {item["issue_id"] for item in output["unresolved"]}
        self.assertIn("unresolved:authenticated-independence", unresolved)
        self.assertIn("unresolved:real-execution-receipts", unresolved)

    def test_outputs_and_envelope_are_deterministic_and_defensive(self) -> None:
        request = example_curator_request()
        first = compile_curator_verification(request)
        second = compile_curator_verification(request)
        self.assertEqual(first, second)
        self.assertEqual(curator_verification_bytes(request), curator_verification_bytes(request))
        first["outputs"]["verification_scope"]["claim_refs"].append("claim:mutated")
        self.assertNotEqual(first, compile_curator_verification(request))

    def test_outputs_are_distinct_not_one_prose_blob(self) -> None:
        envelope = compile_curator_verification(example_curator_request())
        record_types = {envelope["outputs"][field]["record_type"] for field in OUTPUT_FIELDS}
        self.assertEqual(len(record_types), len(OUTPUT_FIELDS))
        self.assertEqual(len({OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS}), 11)


class CuratorCompatibilityTests(unittest.TestCase):
    def test_builder_envelope_normalization_accepts_read_only_mapping(self) -> None:
        source = example_curator_request()["builder_envelope"]
        normalized = curator_module._normalized_builder_envelope(MappingProxyType(source))

        self.assertIsInstance(normalized, dict)
        self.assertEqual(normalized, source)
        self.assertIsNot(normalized, source)

    def test_builder_architect_and_orchestrator_still_compile_and_validate(self) -> None:
        builder = compile_builder_implementation(example_builder_request())
        self.assertTrue(validate_builder("builder-implementation-envelope-v1", builder).valid)
        architect = compile_architect_design(example_architect_request())
        self.assertTrue(validate_architect("architect-design-envelope-v1", architect).valid)
        orchestrator = compile_orchestrator_plan(example_orchestrator_request())
        self.assertTrue(validate_orchestrator("orchestrator-plan-envelope-v1", orchestrator).valid)

    def test_curator_modules_are_package_private_explicit_imports_only(self) -> None:
        self.assertNotIn("compile_curator_successor", hive_mind_os.__all__)
        self.assertNotIn("compile_curator_verification", hive_mind_os.__all__)
        self.assertNotIn("compile_curator_successor", package_system.__all__)
        self.assertNotIn("compile_curator_verification", package_system.__all__)

    def test_cli_contract_is_unchanged_and_curator_has_no_command(self) -> None:
        source = inspect.getsource(cli)
        self.assertNotIn("phase5d", source.lower())
        self.assertNotIn("curator-playbook", source.lower())

    def test_no_curator_json_resource_is_added(self) -> None:
        resources = tuple((REPOSITORY / "src/hive_mind_os").rglob("*.json"))
        self.assertEqual(len(resources), 133)
        self.assertFalse(any("phase5d" in path.name.lower() for path in resources))
        self.assertFalse(any("curator_playbook" in path.name.lower() for path in resources))

    def test_example_unittest_targets_resolve(self) -> None:
        commands = [
            item["command"]
            for item in example_curator_request()["sealed_checks"]
            if item["command"].startswith("python -m unittest ")
        ]
        self.assertTrue(commands)
        for command in commands:
            with self.subTest(command=command):
                target = command.removeprefix("python -m unittest ")
                module_name, class_name = target.rsplit(".", 1)
                self.assertEqual(module_name, "tests.test_phase5d_curator_playbook")
                test_case = globals().get(class_name)
                self.assertIsInstance(test_case, type)
                self.assertTrue(issubclass(test_case, unittest.TestCase))


if __name__ == "__main__":
    unittest.main()
