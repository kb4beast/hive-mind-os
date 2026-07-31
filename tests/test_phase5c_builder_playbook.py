from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os import cli
from hive_mind_os.foundation import builder_playbook as builder_module
from hive_mind_os.foundation.builder_playbook import (
    BuilderContractError,
    _compile_unpinned_successor,
    _current_fingerprint,
    builder_implementation_bytes,
    builder_successor_bytes,
    compile_builder_implementation,
    compile_builder_successor,
    example_builder_request,
)
from hive_mind_os.foundation.builder_playbook_contracts import (
    AGENT_ID,
    BASE_DEFINITION_ID,
    BUILDER_SCHEMA_NAMES,
    COURT_ROLES,
    DEFINITION_ID,
    EXPECTED_SUCCESSOR_DIGEST,
    LAYER_IDS,
    LAYER_KINDS,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_builder,
    validate_builder_catalog,
)
from hive_mind_os.foundation.canonical import digest
from scripts.phase5c_builder_inventory import build_phase5c_inventory

REPOSITORY = Path(__file__).parents[1]


class _HostileDict(dict):
    pass


class _HostileList(list):
    pass


def _request(**changes: object) -> dict[str, object]:
    request = copy.deepcopy(example_builder_request())
    request.update(changes)
    return request


def _resign_output(envelope: dict[str, object], field: str) -> None:
    output = envelope["outputs"][field]  # type: ignore[index]
    output["output_digest"] = digest(  # type: ignore[index]
        {key: value for key, value in output.items() if key != "output_digest"}  # type: ignore[union-attr]
    )
    envelope["implementation_digest"] = digest(
        {key: value for key, value in envelope.items() if key != "implementation_digest"}
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


def _dependency_request() -> dict[str, object]:
    request = _request()
    dependency_id = "dependency:example"
    request["scope"]["max_dependency_changes"] = 1  # type: ignore[index]
    request["dependencies"] = [
        {
            "dependency_id": dependency_id,
            "name": "example-package",
            "ecosystem": "python",
            "current_version": None,
            "proposed_version": "1.0.0",
            "source_ref": "source:example-package-1.0.0",
            "license_id": "MIT",
            "status": "known-admitted",
            "change_refs": ["change:compiler"],
            "license_obligation_refs": ["obligation:retain-license"],
        }
    ]
    for change in request["changes"]:  # type: ignore[index]
        if change["change_id"] == "change:compiler":
            change["dependency_refs"] = [dependency_id]
    request["evidence_plan"].append(  # type: ignore[index]
        {
            "evidence_id": "evidence-plan:license",
            "kind": "license",
            "change_refs": ["change:compiler"],
            "test_refs": [],
            "required_receipt_fields": copy.deepcopy(
                request["evidence_plan"][0]["required_receipt_fields"]  # type: ignore[index]
            ),
        }
    )
    return request


class BuilderSuccessorTests(unittest.TestCase):
    def test_catalog_is_strict_separate_and_complete(self) -> None:
        result = validate_builder_catalog()
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(len(BUILDER_SCHEMA_NAMES), 13)
        self.assertEqual(len(set(BUILDER_SCHEMA_NAMES)), 13)
        self.assertEqual(len(OUTPUT_FIELDS), 10)
        self.assertEqual(set(OUTPUT_SCHEMA_BY_FIELD), set(OUTPUT_FIELDS))

    def test_successor_identity_lineage_and_digest_are_fixed(self) -> None:
        successor = compile_builder_successor()
        self.assertEqual(successor["agent_id"], AGENT_ID)
        self.assertEqual(successor["definition_id"], DEFINITION_ID)
        self.assertEqual(successor["base_definition_ref"], BASE_DEFINITION_ID)
        self.assertEqual(successor["rollback_ref"], BASE_DEFINITION_ID)
        self.assertEqual(successor["content_digest"], EXPECTED_SUCCESSOR_DIGEST)
        self.assertTrue(validate_builder("builder-agent-successor-v1", successor).valid)

    def test_successor_has_fixed_ordered_layers(self) -> None:
        successor = compile_builder_successor()
        self.assertEqual([layer["position"] for layer in successor["layers"]], list(range(1, 9)))
        self.assertEqual(tuple(layer["layer_id"] for layer in successor["layers"]), LAYER_IDS)
        self.assertEqual(tuple(layer["kind"] for layer in successor["layers"]), LAYER_KINDS)

    def test_successor_is_inert_authority_free_private_and_unbound(self) -> None:
        successor = compile_builder_successor()
        self.assertEqual(successor["activation"], "inert")
        self.assertEqual(successor["authority"], "none")
        self.assertFalse(successor["public"])
        self.assertEqual(successor["effective_capabilities"], [])
        self.assertEqual(successor["tool_refs"], [])
        self.assertEqual(
            successor["unsupported_capabilities"], successor["requested_capabilities"]
        )
        for field in (
            "implementation_authorized",
            "execution_authorized",
            "test_result_authorized",
            "completion_authorized",
            "promotion_authorized",
        ):
            self.assertFalse(successor[field])

    def test_successor_output_contracts_are_separate_and_ordered(self) -> None:
        successor = compile_builder_successor()
        self.assertEqual(
            successor["output_contract_refs"],
            [OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS],
        )

    def test_successor_compilation_is_deterministic_and_defensive(self) -> None:
        first = compile_builder_successor()
        second = compile_builder_successor()
        self.assertEqual(first, second)
        self.assertEqual(builder_successor_bytes(), builder_successor_bytes())
        first["layers"][0]["layer_id"] = "mutated"
        self.assertNotEqual(first, compile_builder_successor())

    def test_phase2_projection_drift_fails_closed(self) -> None:
        with patch.object(builder_module, "BASE_PROJECTION_DIGEST", "sha256:" + ("0" * 64)):
            with self.assertRaisesRegex(ValueError, "projection drifted"):
                _compile_unpinned_successor()

    def test_successor_rejects_resealed_layer_drift(self) -> None:
        successor = compile_builder_successor()
        successor["layers"][2]["layer_id"] = "builder:weakened-playbook"
        layer = successor["layers"][2]
        layer["digest"] = digest({key: value for key, value in layer.items() if key != "digest"})
        successor["content_digest"] = digest(
            {key: value for key, value in successor.items() if key != "content_digest"}
        )
        result = validate_builder(
            "builder-agent-successor-v1", successor, enforce_reviewed_successor=False
        )
        self.assertFalse(result.valid)

    def test_successor_rejects_capability_tool_authority_or_activation_escalation(self) -> None:
        mutations = (
            ("effective_capabilities", ["write_workspace"]),
            ("tool_refs", ["tool.repository-write"]),
            ("authority", "repository"),
            ("activation", "active"),
            ("public", True),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                successor = compile_builder_successor()
                successor[field] = value
                successor["content_digest"] = digest(
                    {key: item for key, item in successor.items() if key != "content_digest"}
                )
                self.assertFalse(
                    validate_builder(
                        "builder-agent-successor-v1",
                        successor,
                        enforce_reviewed_successor=False,
                    ).valid
                )


class BuilderRequestContractTests(unittest.TestCase):
    def test_request_must_be_exact_builtin_mapping(self) -> None:
        with self.assertRaisesRegex(BuilderContractError, "exact object"):
            compile_builder_implementation(_HostileDict(example_builder_request()))

    def test_nested_hostile_mapping_and_sequence_fail_closed(self) -> None:
        request = _request()
        request["changes"] = _HostileList(request["changes"])  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "unsupported type"):
            compile_builder_implementation(request)
        request = _request()
        request["scope"] = _HostileDict(request["scope"])  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "unsupported type"):
            compile_builder_implementation(request)

    def test_unknown_fields_fail_closed(self) -> None:
        request = _request()
        request["unexpected"] = True
        with self.assertRaisesRegex(BuilderContractError, "unknown properties"):
            compile_builder_implementation(request)

    def test_private_content_fields_fail_closed(self) -> None:
        for field in ("prompt", "response", "hidden_reasoning", "secret"):
            with self.subTest(field=field):
                request = _request()
                request[field] = "private"
                with self.assertRaisesRegex(BuilderContractError, "private content field"):
                    compile_builder_implementation(request)

    def test_nonfinite_and_oversized_values_fail_closed(self) -> None:
        request = _request()
        request["budgets"]["tokens"] = math.inf  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "non-finite"):
            compile_builder_implementation(request)
        with self.assertRaisesRegex(BuilderContractError, "text limit"):
            compile_builder_implementation(_request(objective="x" * 4001))

    def test_duplicate_ids_fail_closed(self) -> None:
        collections = (
            ("acceptance_criteria", "acceptance_id"),
            ("adjudicated_requirements", "requirement_id"),
            ("changes", "change_id"),
            ("tests", "test_id"),
            ("evidence_plan", "evidence_id"),
            ("checkpoints", "checkpoint_id"),
            ("rollback_steps", "rollback_id"),
            ("artifacts", "artifact_id"),
        )
        for collection, _ in collections:
            with self.subTest(collection=collection):
                request = _request()
                request[collection].append(copy.deepcopy(request[collection][0]))  # type: ignore[index]
                with self.assertRaises(BuilderContractError):
                    compile_builder_implementation(request)

    def test_duplicate_actor_role_and_identity_fail_closed(self) -> None:
        request = _request()
        request["actors"][1]["role"] = request["actors"][0]["role"]  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)
        request = _request()
        request["actors"][1]["actor_id"] = request["actors"][0]["actor_id"]  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)

    def test_caller_supplied_authentication_fails_closed(self) -> None:
        request = _request()
        request["actors"][0]["authenticated"] = True  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "const"):
            compile_builder_implementation(request)

    def test_complete_procedural_role_catalog_is_required(self) -> None:
        request = _request()
        request["actors"].pop()  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)
        request = _request()
        self.assertEqual(tuple(item["role"] for item in request["actors"]), COURT_ROLES)  # type: ignore[index]

    def test_caller_execution_test_and_completion_claims_fail_closed(self) -> None:
        for field in ("code_executed", "tests_passed", "completion_established"):
            with self.subTest(field=field):
                request = _request()
                request["caller_claims"][field] = True  # type: ignore[index]
                with self.assertRaises(BuilderContractError):
                    compile_builder_implementation(request)

    def test_subject_commit_tree_and_architecture_scope_must_match(self) -> None:
        request = _request()
        request["scope"]["subject_commit"] = "f" * 40  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "subject differ"):
            compile_builder_implementation(request)
        request = _request()
        request["scope"]["subject_tree"] = "f" * 40  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "subject differ"):
            compile_builder_implementation(request)

    def test_unresolved_architecture_contradictions_block_planning(self) -> None:
        request = _request()
        request["architecture_decision"]["unresolved_blocking_contradiction_refs"] = [  # type: ignore[index]
            "contradiction:blocking"
        ]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)

    def test_cross_repository_tenant_and_request_substitution_change_digests(self) -> None:
        base = compile_builder_implementation(_request())
        for field, value in (
            ("request_id", "request:foreign"),
            ("repository_id", "repository:foreign"),
            ("tenant_id", "tenant:foreign"),
        ):
            with self.subTest(field=field):
                candidate = compile_builder_implementation(_request(**{field: value}))
                self.assertNotEqual(base["request_digest"], candidate["request_digest"])
                self.assertNotEqual(base["implementation_digest"], candidate["implementation_digest"])
                for output in candidate["outputs"].values():
                    self.assertEqual(output[field], value)

    def test_cross_design_substitution_changes_digests(self) -> None:
        base = compile_builder_implementation(_request())
        request = _request()
        request["architecture_decision"]["design_digest"] = "sha256:" + ("3" * 64)  # type: ignore[index]
        candidate = compile_builder_implementation(request)
        self.assertNotEqual(base["request_digest"], candidate["request_digest"])
        self.assertNotEqual(base["implementation_digest"], candidate["implementation_digest"])
        for output in candidate["outputs"].values():
            self.assertEqual(output["design_digest"], "sha256:" + ("3" * 64))


class BuilderSemanticContractTests(unittest.TestCase):
    def test_requirements_must_cover_every_acceptance_criterion(self) -> None:
        request = _request()
        request["adjudicated_requirements"][2]["acceptance_refs"] = [  # type: ignore[index]
            "acceptance:authority-free"
        ]
        with self.assertRaisesRegex(BuilderContractError, "do not cover every acceptance"):
            compile_builder_implementation(request)

    def test_requirement_references_must_be_admitted(self) -> None:
        request = _request()
        request["adjudicated_requirements"][0]["evidence_refs"] = ["evidence:foreign"]  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "unknown identifiers"):
            compile_builder_implementation(request)
        request = _request()
        request["adjudicated_requirements"][0]["architecture_refs"] = [  # type: ignore[index]
            "architecture:foreign"
        ]
        with self.assertRaisesRegex(BuilderContractError, "unknown identifiers"):
            compile_builder_implementation(request)

    def test_every_requirement_must_map_to_a_change(self) -> None:
        request = _request()
        acceptance_by_requirement = {
            item["requirement_id"]: item["acceptance_refs"]
            for item in request["adjudicated_requirements"]
        }
        for change in request["changes"]:  # type: ignore[index]
            retained = [
                ref
                for ref in change["requirement_refs"]
                if ref != "requirement:installed-wheel-evidence"
            ]
            change["requirement_refs"] = retained or [
                "requirement:authority-isolation"
            ]
            change["acceptance_refs"] = sorted(
                {
                    acceptance
                    for requirement in change["requirement_refs"]
                    for acceptance in acceptance_by_requirement[requirement]
                }
            )
        with self.assertRaisesRegex(BuilderContractError, "every requirement"):
            compile_builder_implementation(request)

    def test_change_acceptance_must_derive_from_its_requirements(self) -> None:
        request = _request()
        request["changes"][0]["acceptance_refs"] = ["acceptance:installed-wheel"]  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "borrows acceptance"):
            compile_builder_implementation(request)

    def test_change_path_must_stay_inside_allowed_scope(self) -> None:
        request = _request()
        request["changes"][0]["path"] = "README.md"  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "outside the admitted scope"):
            compile_builder_implementation(request)

    def test_denied_root_api_cli_and_store_paths_fail_closed(self) -> None:
        for path in (
            "src/hive_mind_os/__init__.py",
            "src/hive_mind_os/cli.py",
            "src/hive_mind_os/foundation/store.py",
        ):
            with self.subTest(path=path):
                request = _request()
                request["changes"][0]["path"] = path  # type: ignore[index]
                with self.assertRaisesRegex(BuilderContractError, "denied"):
                    compile_builder_implementation(request)

    def test_duplicate_change_paths_and_unbounded_file_count_fail_closed(self) -> None:
        request = _request()
        request["changes"][1]["path"] = request["changes"][0]["path"]  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "duplicate or conflicting"):
            compile_builder_implementation(request)
        request = _request()
        request["scope"]["max_files"] = 3  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "exceeds"):
            compile_builder_implementation(request)

    def test_change_dependency_references_must_be_complete(self) -> None:
        request = _request()
        request["changes"][0]["dependency_refs"] = ["dependency:missing"]  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)
        request = _dependency_request()
        request["changes"][1]["dependency_refs"] = []  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "unreferenced or missing"):
            compile_builder_implementation(request)

    def test_known_dependency_and_license_obligations_compile(self) -> None:
        implementation = compile_builder_implementation(_dependency_request())
        dependency = implementation["outputs"]["dependency_plan"]
        self.assertEqual(len(dependency["dependencies"]), 1)
        self.assertEqual(dependency["unknown_dependency_refs"], [])
        self.assertEqual(dependency["quarantined_dependency_refs"], [])
        self.assertTrue(dependency["supply_chain_review_required"])
        self.assertFalse(dependency["dependency_change_authorized"])

    def test_unknown_or_quarantined_dependency_status_fails_closed(self) -> None:
        for status in ("unknown", "quarantined"):
            with self.subTest(status=status):
                request = _dependency_request()
                request["dependencies"][0]["status"] = status  # type: ignore[index]
                with self.assertRaises(BuilderContractError):
                    compile_builder_implementation(request)

    def test_dependency_change_count_and_license_evidence_are_bounded(self) -> None:
        request = _dependency_request()
        request["scope"]["max_dependency_changes"] = 0  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "dependency change count"):
            compile_builder_implementation(request)
        request = _dependency_request()
        request["evidence_plan"] = [  # type: ignore[index]
            item for item in request["evidence_plan"] if item["kind"] != "license"  # type: ignore[index]
        ]
        with self.assertRaisesRegex(BuilderContractError, "license evidence"):
            compile_builder_implementation(request)

    def test_tests_must_cover_every_acceptance_and_change(self) -> None:
        request = _request()
        acceptance_by_requirement = {
            item["requirement_id"]: item["acceptance_refs"]
            for item in request["adjudicated_requirements"]
        }
        for test in request["tests"]:  # type: ignore[index]
            retained = [
                ref
                for ref in test["requirement_refs"]
                if ref != "requirement:installed-wheel-evidence"
            ]
            test["requirement_refs"] = retained or [
                "requirement:authority-isolation"
            ]
            test["acceptance_refs"] = sorted(
                {
                    acceptance
                    for requirement in test["requirement_refs"]
                    for acceptance in acceptance_by_requirement[requirement]
                }
            )
        with self.assertRaisesRegex(BuilderContractError, "tests do not cover every acceptance"):
            compile_builder_implementation(request)
        request = _request()
        for test in request["tests"]:  # type: ignore[index]
            test["change_refs"] = [
                ref for ref in test["change_refs"] if ref != "change:evidence"
            ]
        with self.assertRaisesRegex(BuilderContractError, "tests do not cover every change"):
            compile_builder_implementation(request)

    def test_test_weakening_or_nonpassing_after_state_fails_closed(self) -> None:
        request = _request()
        request["tests"][0]["test_weakening"] = True  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)
        request = _request()
        request["tests"][0]["expected_after"] = "skip"  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)

    def test_failure_before_and_pass_after_evidence_are_required(self) -> None:
        request = _request()
        for test in request["tests"]:  # type: ignore[index]
            test["expected_before"] = "not-applicable"
        with self.assertRaisesRegex(BuilderContractError, "failure-before requirement"):
            compile_builder_implementation(request)
        request = _request()
        request["evidence_plan"] = [  # type: ignore[index]
            item for item in request["evidence_plan"] if item["kind"] != "pass-after"  # type: ignore[index]
        ]
        with self.assertRaisesRegex(BuilderContractError, "pass-after evidence"):
            compile_builder_implementation(request)

    def test_required_receipt_fields_are_exact_and_complete(self) -> None:
        request = _request()
        request["evidence_plan"][0]["required_receipt_fields"].pop()  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "receipt fields"):
            compile_builder_implementation(request)
        request = _request()
        request["evidence_plan"][0]["required_receipt_fields"].append("private_reasoning")  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "receipt fields"):
            compile_builder_implementation(request)

    def test_complete_diff_evidence_is_required(self) -> None:
        request = _request()
        request["evidence_plan"] = [  # type: ignore[index]
            item for item in request["evidence_plan"] if item["kind"] != "diff"  # type: ignore[index]
        ]
        with self.assertRaisesRegex(BuilderContractError, "complete diff evidence"):
            compile_builder_implementation(request)

    def test_checkpoints_cover_all_changes_and_reference_evidence(self) -> None:
        request = _request()
        request["checkpoints"][1]["after_change_refs"] = ["change:tests"]  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "checkpoints do not cover"):
            compile_builder_implementation(request)
        request = _request()
        request["checkpoints"][0]["evidence_refs"] = ["evidence-plan:missing"]  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)

    def test_interruption_recovery_and_restart_plans_are_preserved(self) -> None:
        implementation = compile_builder_implementation(_request())
        workspace = implementation["outputs"]["workspace_plan"]
        self.assertTrue(workspace["clean_start_required"])
        self.assertTrue(workspace["interruption_recovery"])
        self.assertEqual(
            set(workspace["checkpoint_refs"]),
            {"checkpoint:contracts-and-compiler", "checkpoint:tests-and-evidence"},
        )
        rollback = implementation["outputs"]["rollback_plan"]
        self.assertTrue(all(item["restart_procedure"] for item in rollback["checkpoints"]))

    def test_rollback_must_cover_each_change_exactly_once(self) -> None:
        request = _request()
        request["rollback_steps"].pop()  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "cover every change"):
            compile_builder_implementation(request)
        request = _request()
        request["rollback_steps"][1]["change_refs"] = ["change:contracts"]  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "more than one rollback"):
            compile_builder_implementation(request)

    def test_rollback_inverse_operation_and_verification_are_required(self) -> None:
        request = _request()
        request["rollback_steps"][0]["inverse_operation"] = "modify"  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "inverse operation"):
            compile_builder_implementation(request)
        request = _request()
        request["rollback_steps"][0]["verification_test_refs"] = ["test:missing"]  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)

    def test_artifact_manifest_covers_every_change_and_test(self) -> None:
        request = _request()
        request["artifacts"] = [  # type: ignore[index]
            item for item in request["artifacts"] if item["artifact_id"] != "artifact:builder-tests"  # type: ignore[index]
        ]
        with self.assertRaisesRegex(BuilderContractError, "artifact manifest does not cover"):
            compile_builder_implementation(request)

    def test_manifest_and_receipt_artifacts_are_required(self) -> None:
        for kind in ("manifest", "receipt"):
            with self.subTest(kind=kind):
                request = _request()
                request["artifacts"] = [  # type: ignore[index]
                    item for item in request["artifacts"] if item["kind"] != kind  # type: ignore[index]
                ]
                with self.assertRaises(BuilderContractError):
                    compile_builder_implementation(request)

    def test_artifacts_must_require_digest_and_receipt(self) -> None:
        for field in ("digest_required", "receipt_required"):
            with self.subTest(field=field):
                request = _request()
                request["artifacts"][0][field] = False  # type: ignore[index]
                with self.assertRaises(BuilderContractError):
                    compile_builder_implementation(request)

    def test_known_resource_accounting_reconciles_reserves_and_sections(self) -> None:
        implementation = compile_builder_implementation(_request())
        resource = implementation["resource_accounting"]
        self.assertEqual(resource["accounting_status"], "known")
        self.assertEqual(resource["lease_status"], "not-issued")
        self.assertFalse(resource["budget_authorized"])
        for axis in RESOURCE_AXES:
            allocation = resource["axes"][axis]
            self.assertGreater(allocation["checkpoint_reserve"], 0)
            self.assertGreater(allocation["evidence_reserve"], 0)
            self.assertGreater(allocation["rollback_reserve"], 0)
            self.assertEqual(set(allocation["section_allocations"]), set(RESOURCE_SECTIONS))
            self.assertTrue(all(value > 0 for value in allocation["section_allocations"].values()))
            observed = (
                allocation["checkpoint_reserve"]
                + allocation["evidence_reserve"]
                + allocation["rollback_reserve"]
                + sum(allocation["section_allocations"].values())
            )
            self.assertEqual(observed, allocation["ceiling"])

    def test_unknown_budgets_remain_unknown_and_issue_no_lease(self) -> None:
        implementation = compile_builder_implementation(example_builder_request(known_budget=False))
        resource = implementation["resource_accounting"]
        self.assertEqual(resource["accounting_status"], "unknown")
        self.assertEqual(resource["lease_status"], "not-issued")
        for axis in RESOURCE_AXES:
            allocation = resource["axes"][axis]
            self.assertIsNone(allocation["ceiling"])
            self.assertIsNone(allocation["checkpoint_reserve"])
            self.assertIsNone(allocation["evidence_reserve"])
            self.assertIsNone(allocation["rollback_reserve"])
            self.assertTrue(all(value is None for value in allocation["section_allocations"].values()))

    def test_mixed_or_unfunded_resource_accounting_fails_closed(self) -> None:
        request = _request()
        request["budgets"]["tool_calls"] = None  # type: ignore[index]
        with self.assertRaisesRegex(BuilderContractError, "wholly known or wholly unknown"):
            compile_builder_implementation(request)
        request = _request()
        request["budgets"]["tool_calls"] = 10  # type: ignore[index]
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)
        request = _request()
        request["checkpoint_reserve_ppm"] = 0
        with self.assertRaises(BuilderContractError):
            compile_builder_implementation(request)

    def test_prior_progress_fingerprint_prevents_semantic_repeat(self) -> None:
        request = _request()
        request["prior_fingerprints"] = [_current_fingerprint(request)]
        with self.assertRaisesRegex(BuilderContractError, "repeated implementation fingerprint"):
            compile_builder_implementation(request)


class BuilderOutputAndAdversarialTests(unittest.TestCase):
    def test_all_outputs_bind_request_design_scope_authority_budget_evidence_and_rollback(self) -> None:
        implementation = compile_builder_implementation(_request())
        expected = {
            "request_id": implementation["request_id"],
            "request_digest": implementation["request_digest"],
            "objective_id": implementation["objective_id"],
            "tenant_id": implementation["tenant_id"],
            "repository_id": implementation["repository_id"],
            "builder_definition_id": DEFINITION_ID,
            "builder_version": "2-shadow-1",
            "architecture_decision_id": implementation["request_snapshot"]["architecture_decision"]["decision_id"],
            "design_digest": implementation["request_snapshot"]["architecture_decision"]["design_digest"],
            "subject_commit": implementation["request_snapshot"]["scope"]["subject_commit"],
            "subject_tree": implementation["request_snapshot"]["scope"]["subject_tree"],
        }
        for field, output in implementation["outputs"].items():
            with self.subTest(field=field):
                for key, value in expected.items():
                    self.assertEqual(output[key], value)
                self.assertEqual(output["authority_state"]["authority"], "none")
                self.assertEqual(output["authority_state"]["activation"], "inert")
                self.assertFalse(output["authority_state"]["implementation_authorized"])
                self.assertEqual(output["budget_state"], "known")
                self.assertEqual(output["evidence_refs"], implementation["request_snapshot"]["evidence_refs"])
                self.assertEqual(output["rollback_refs"], implementation["request_snapshot"]["rollback_refs"])
                self.assertTrue(validate_builder(OUTPUT_SCHEMA_BY_FIELD[field], output).valid)

    def test_outputs_are_distinct_not_one_prose_blob(self) -> None:
        implementation = compile_builder_implementation(_request())
        self.assertEqual(tuple(implementation["outputs"]), OUTPUT_FIELDS)
        self.assertEqual(len({item["record_type"] for item in implementation["outputs"].values()}), 10)
        self.assertEqual(len({item["output_digest"] for item in implementation["outputs"].values()}), 10)

    def test_outputs_and_envelope_are_deterministic_and_defensive(self) -> None:
        request = _request()
        first = compile_builder_implementation(request)
        second = compile_builder_implementation(request)
        self.assertEqual(first, second)
        self.assertEqual(
            builder_implementation_bytes(request), builder_implementation_bytes(request)
        )
        first["outputs"]["change_plan"]["change_count"] = 999
        self.assertNotEqual(first, compile_builder_implementation(request))

    def test_direct_output_digest_mutation_fails_validation(self) -> None:
        implementation = compile_builder_implementation(_request())
        implementation["outputs"]["change_plan"]["change_count"] += 1
        result = validate_builder("builder-implementation-envelope-v1", implementation)
        self.assertFalse(result.valid)

    def test_envelope_digest_mutation_fails_validation(self) -> None:
        implementation = compile_builder_implementation(_request())
        implementation["implementation_digest"] = "sha256:" + ("f" * 64)
        self.assertFalse(
            validate_builder("builder-implementation-envelope-v1", implementation).valid
        )

    def test_resealed_cross_request_scope_and_authority_mutations_fail(self) -> None:
        cases = (
            ("requirement_trace", ("request_id",), "request:foreign"),
            ("implementation_scope", ("repository_id",), "repository:foreign"),
            ("change_plan", ("subject_commit",), "f" * 40),
            ("workspace_plan", ("authority_state", "authority"), "repository"),
            ("test_plan", ("tests_executed",), True),
            ("curator_handoff", ("completion_authorized",), True),
        )
        for field, path, value in cases:
            with self.subTest(field=field, path=path):
                implementation = compile_builder_implementation(_request())
                _set_path(implementation["outputs"][field], path, value)
                _resign_output(implementation, field)
                self.assertFalse(
                    validate_builder("builder-implementation-envelope-v1", implementation).valid
                )

    def test_semantically_resealed_mutations_fail_across_every_typed_output_leaf(self) -> None:
        pristine = compile_builder_implementation(_request())
        mutation_count = 0
        for field in OUTPUT_FIELDS:
            leaves = _scalar_leaves(pristine["outputs"][field])
            self.assertGreater(len(leaves), 0)
            for path, value in leaves:
                with self.subTest(field=field, path=path):
                    mutated = copy.deepcopy(pristine)
                    _set_path(mutated["outputs"][field], path, _mutated_scalar(value))
                    _resign_output(mutated, field)
                    result = validate_builder(
                        "builder-implementation-envelope-v1", mutated
                    )
                    self.assertFalse(result.valid)
                    mutation_count += 1
        self.assertGreater(mutation_count, 400)

    def test_curator_handoff_discloses_procedural_nonindependence(self) -> None:
        implementation = compile_builder_implementation(_request())
        handoff = implementation["outputs"]["curator_handoff"]
        self.assertEqual(handoff["next_role"], "curator")
        self.assertTrue(handoff["requested_role_eligible"])
        self.assertTrue(handoff["independent_reconstruction_required"])
        self.assertFalse(handoff["authenticated_distinct_actors"])
        self.assertTrue(handoff["same_assistant_performed_procedural_passes"])
        self.assertFalse(handoff["independence_claimed"])
        for field in (
            "implementation_authorized",
            "completion_authorized",
            "promotion_authorized",
            "activation_authorized",
        ):
            self.assertFalse(handoff[field])

    def test_requested_noncurator_handoff_is_advisory_and_ineligible(self) -> None:
        implementation = compile_builder_implementation(
            _request(requested_next_role="steward")
        )
        handoff = implementation["outputs"]["curator_handoff"]
        self.assertEqual(handoff["requested_next_role"], "steward")
        self.assertFalse(handoff["requested_role_eligible"])
        self.assertEqual(handoff["next_role"], "curator")

    def test_no_output_claims_execution_test_results_completion_or_artifact_creation(self) -> None:
        implementation = compile_builder_implementation(_request())
        self.assertFalse(implementation["outputs"]["change_plan"]["execution_authorized"])
        self.assertFalse(implementation["outputs"]["change_plan"]["completion_claimed"])
        self.assertFalse(implementation["outputs"]["test_plan"]["tests_executed"])
        self.assertFalse(implementation["outputs"]["test_plan"]["test_results_authorized"])
        evidence = implementation["outputs"]["execution_evidence_plan"]
        self.assertFalse(evidence["code_executed_claim_accepted"])
        self.assertFalse(evidence["tests_passed_claim_accepted"])
        self.assertFalse(evidence["completion_claim_accepted"])
        self.assertFalse(evidence["evidence_sealed"])
        self.assertFalse(implementation["outputs"]["artifact_manifest"]["artifacts_created"])


class BuilderCompatibilityTests(unittest.TestCase):
    def test_no_root_or_package_api_export_is_added(self) -> None:
        self.assertEqual(len(hive_mind_os.__all__), 131)
        self.assertEqual(len(package_system.__all__), 33)
        self.assertFalse(any("builder_playbook" in name for name in hive_mind_os.__all__))
        self.assertFalse(any("builder_playbook" in name for name in package_system.__all__))

    def test_cli_contract_is_unchanged_and_builder_has_no_command(self) -> None:
        parsers = (
            cli.build_parser(),
            cli.build_audit_parser(),
            cli.build_benchmark_parser(),
            cli.build_defer_parser(),
            cli.build_deliver_parser(),
            cli.build_enqueue_parser(),
            cli.build_experiment_parser(),
            cli.build_ingest_parser(),
            cli.build_missions_parser(),
            cli.build_pit_episode_parser(),
            cli.build_resume_parser(),
            cli.build_serve_parser(),
            cli.build_status_parser(),
        )
        self.assertEqual(len(parsers), 13)
        rendered = json.dumps(
            [
                {
                    "prog": parser.prog,
                    "options": sorted(
                        option
                        for action in parser._actions
                        for option in action.option_strings
                    ),
                }
                for parser in parsers
            ],
            sort_keys=True,
        )
        self.assertNotIn("builder-playbook", rendered)
        self.assertNotIn("phase5c", rendered)

    def test_package_resources_remain_133_and_no_builder_json_resource_is_added(self) -> None:
        root = Path(hive_mind_os.__file__).parent
        resources = tuple(root.rglob("*.json"))
        self.assertEqual(len(resources), 133)
        self.assertFalse(any("builder_playbook" in path.name for path in resources))

    def test_phase5a_and_phase5b_candidates_still_import_and_validate(self) -> None:
        from hive_mind_os.foundation.architect_playbook import (
            compile_architect_design,
            compile_architect_successor,
            example_architect_request,
        )
        from hive_mind_os.foundation.architect_playbook_contracts import validate_architect
        from hive_mind_os.foundation.orchestrator_playbook import (
            compile_orchestrator_plan,
            compile_orchestrator_successor,
            example_orchestrator_request,
        )
        from hive_mind_os.foundation.orchestrator_playbook_contracts import validate_orchestrator

        self.assertTrue(
            validate_orchestrator(
                "orchestrator-agent-successor-v1", compile_orchestrator_successor()
            ).valid
        )
        self.assertTrue(
            validate_orchestrator(
                "orchestrator-plan-envelope-v1",
                compile_orchestrator_plan(example_orchestrator_request()),
            ).valid
        )
        self.assertTrue(
            validate_architect(
                "architect-agent-successor-v1", compile_architect_successor()
            ).valid
        )
        self.assertTrue(
            validate_architect(
                "architect-design-envelope-v1",
                compile_architect_design(example_architect_request()),
            ).valid
        )


    def test_committed_phase5c_inventory_matches_current_tree(self) -> None:
        observed = build_phase5c_inventory(REPOSITORY)
        committed = json.loads(
            (
                REPOSITORY
                / "evidence/phase5c/phase5c_builder_inventory.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(observed, committed)

    def test_builder_modules_are_package_private_explicit_imports_only(self) -> None:
        self.assertTrue(builder_module.__name__.endswith("foundation.builder_playbook"))
        self.assertNotIn("compile_builder_implementation", hive_mind_os.__dict__)
        self.assertNotIn("compile_builder_implementation", package_system.__dict__)


if __name__ == "__main__":
    unittest.main()
