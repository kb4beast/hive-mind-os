from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path
from unittest.mock import patch

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation import architect_playbook as architect_module
from hive_mind_os.foundation.architect_playbook import (
    ArchitectContractError,
    _compile_unpinned_successor,
    architect_design_bytes,
    architect_successor_bytes,
    compile_architect_design,
    compile_architect_successor,
    example_architect_request,
)
from hive_mind_os.foundation.architect_playbook_contracts import (
    ARCHITECT_SCHEMA_NAMES,
    BASE_DEFINITION_ID,
    COURT_ROLES,
    EXPECTED_SUCCESSOR_DIGEST,
    OUTPUT_FIELDS,
    OUTPUT_SCHEMA_BY_FIELD,
    RESOURCE_AXES,
    RESOURCE_SECTIONS,
    validate_architect,
    validate_architect_catalog,
)
from hive_mind_os.foundation.canonical import digest
from scripts.phase1_surface_inventory import build_inventory, cli_inventory
from scripts.phase5b_architect_inventory import build_phase5b_inventory

REPOSITORY = Path(__file__).parents[1]


class _HostileDict(dict):
    pass


class _HostileList(list):
    pass


def _request(**changes: object) -> dict[str, object]:
    request = copy.deepcopy(example_architect_request())
    request.update(changes)
    return request


def _option(request: dict[str, object], option_id: str) -> dict[str, object]:
    return next(
        option
        for option in request["options"]  # type: ignore[index]
        if option["option_id"] == option_id
    )


def _claim(request: dict[str, object], claim_id: str) -> dict[str, object]:
    return next(
        claim
        for claim in request["claims"]  # type: ignore[index]
        if claim["claim_id"] == claim_id
    )


def _mapping(
    request: dict[str, object], claim_id: str, option_id: str
) -> dict[str, object]:
    return next(
        mapping
        for mapping in request["claim_mappings"]  # type: ignore[index]
        if mapping["claim_id"] == claim_id and mapping["option_id"] == option_id
    )


def _resign_output(plan: dict[str, object], field: str) -> None:
    output = plan["outputs"][field]  # type: ignore[index]
    output["output_digest"] = digest(  # type: ignore[index]
        {key: value for key, value in output.items() if key != "output_digest"}  # type: ignore[union-attr]
    )
    plan["design_digest"] = digest(
        {key: value for key, value in plan.items() if key != "design_digest"}
    )


def _set_path(document: object, path: tuple[object, ...], value: object) -> None:
    current = document
    for part in path[:-1]:
        current = current[part]  # type: ignore[index]
    current[path[-1]] = value  # type: ignore[index]


def _scalar_leaves(value: object, path: tuple[object, ...] = ()) -> list[tuple[tuple[object, ...], object]]:
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
        return value + ":mutated"
    if value is None:
        return "mutated"
    raise TypeError(type(value).__name__)


class ArchitectSuccessorTests(unittest.TestCase):
    def test_catalog_is_strict_separate_and_complete(self) -> None:
        result = validate_architect_catalog()
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(len(ARCHITECT_SCHEMA_NAMES), 13)
        self.assertEqual(len(set(ARCHITECT_SCHEMA_NAMES)), 13)
        self.assertEqual(len(OUTPUT_FIELDS), 10)

    def test_successor_is_fixed_ordered_and_authority_free(self) -> None:
        successor = compile_architect_successor()
        self.assertEqual(successor["content_digest"], EXPECTED_SUCCESSOR_DIGEST)
        self.assertEqual(successor["agent_id"], "hive-agent:architect:v2-shadow-1")
        self.assertEqual(successor["definition_id"], "hive-agent-definition:architect:v2-shadow-1")
        self.assertEqual(successor["base_definition_ref"], BASE_DEFINITION_ID)
        self.assertEqual(successor["rollback_ref"], BASE_DEFINITION_ID)
        self.assertEqual(successor["effective_capabilities"], [])
        self.assertEqual(successor["tool_refs"], [])
        self.assertEqual(successor["activation"], "inert")
        self.assertEqual(successor["authority"], "none")
        self.assertFalse(successor["public"])
        self.assertEqual([layer["position"] for layer in successor["layers"]], list(range(1, 9)))
        self.assertEqual(
            [layer["kind"] for layer in successor["layers"]],
            ["base", "prompt", "playbook", "skills", "input", "outputs", "governance", "lifecycle"],
        )
        self.assertEqual(
            successor["output_contract_refs"],
            [OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS],
        )
        self.assertTrue(
            validate_architect("architect-agent-successor-v1", successor).valid
        )

    def test_compiler_is_deterministic_pinned_and_defensive(self) -> None:
        first = compile_architect_successor()
        second = compile_architect_successor()
        self.assertEqual(first, second)
        self.assertEqual(architect_successor_bytes(), architect_successor_bytes())
        first["layers"][0]["layer_id"] = "mutated"
        self.assertNotEqual(first, compile_architect_successor())

    def test_phase2_projection_drift_fails_closed(self) -> None:
        with patch.object(architect_module, "BASE_PROJECTION_DIGEST", "sha256:" + ("0" * 64)):
            with self.assertRaisesRegex(ValueError, "projection drifted"):
                _compile_unpinned_successor()

    def test_successor_contract_rejects_resealed_layer_drift(self) -> None:
        successor = compile_architect_successor()
        successor["layers"][2]["layer_id"] = "architect:weakened-playbook"
        layer = successor["layers"][2]
        layer["digest"] = digest({key: value for key, value in layer.items() if key != "digest"})
        successor["content_digest"] = digest(
            {key: value for key, value in successor.items() if key != "content_digest"}
        )
        result = validate_architect(
            "architect-agent-successor-v1",
            successor,
            enforce_reviewed_successor=False,
        )
        self.assertFalse(result.valid)
        self.assertIn("successor layer identities differ from the fixed order", result.issues)

    def test_successor_contract_rejects_capability_or_tool_escalation(self) -> None:
        for field, value in (
            ("effective_capabilities", ["write_design"]),
            ("tool_refs", ["tool.repository-inspect"]),
        ):
            with self.subTest(field=field):
                successor = compile_architect_successor()
                successor[field] = value
                successor["content_digest"] = digest(
                    {key: item for key, item in successor.items() if key != "content_digest"}
                )
                result = validate_architect(
                    "architect-agent-successor-v1",
                    successor,
                    enforce_reviewed_successor=False,
                )
                self.assertFalse(result.valid)


class ArchitectRequestTests(unittest.TestCase):
    def test_request_must_be_an_exact_object(self) -> None:
        with self.assertRaisesRegex(ArchitectContractError, "exact object"):
            compile_architect_design(_HostileDict(example_architect_request()))

    def test_nested_hostile_containers_fail_closed(self) -> None:
        request = _request()
        request["options"] = _HostileList(request["options"])  # type: ignore[index]
        with self.assertRaisesRegex(ArchitectContractError, "unsupported type"):
            compile_architect_design(request)

    def test_private_content_is_rejected(self) -> None:
        request = _request()
        request["prompt"] = "private"
        with self.assertRaisesRegex(ArchitectContractError, "private content field"):
            compile_architect_design(request)

    def test_unknown_fields_fail_closed(self) -> None:
        request = _request()
        request["unexpected"] = True
        with self.assertRaisesRegex(ArchitectContractError, "unknown properties"):
            compile_architect_design(request)

    def test_nonfinite_and_oversized_values_fail_closed(self) -> None:
        request = _request()
        request["budgets"]["tokens"] = math.inf  # type: ignore[index]
        with self.assertRaisesRegex(ArchitectContractError, "non-finite"):
            compile_architect_design(request)
        request = _request(objective="x" * 4001)
        with self.assertRaisesRegex(ArchitectContractError, "text limit"):
            compile_architect_design(request)

    def test_duplicate_acceptance_claim_option_and_actor_ids_fail(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        request = _request()
        request["acceptance_criteria"].append(copy.deepcopy(request["acceptance_criteria"][0]))  # type: ignore[index]
        cases.append(("acceptance", request, "duplicate acceptance"))
        request = _request()
        request["claims"].append(copy.deepcopy(request["claims"][0]))  # type: ignore[index]
        cases.append(("claim", request, "duplicate claim"))
        request = _request()
        request["options"].append(copy.deepcopy(request["options"][0]))  # type: ignore[index]
        cases.append(("option", request, "duplicate option"))
        request = _request()
        request["actors"][1]["role"] = request["actors"][0]["role"]  # type: ignore[index]
        cases.append(("actor-role", request, "duplicate procedural actor role"))
        request = _request()
        request["actors"][1]["actor_id"] = request["actors"][0]["actor_id"]  # type: ignore[index]
        cases.append(("actor-id", request, "duplicate procedural actor"))
        for name, request, expected in cases:
            with self.subTest(name=name):
                with self.assertRaisesRegex(ArchitectContractError, expected):
                    compile_architect_design(request)

    def test_caller_supplied_authentication_is_rejected(self) -> None:
        request = _request()
        request["actors"][0]["authenticated"] = True  # type: ignore[index]
        with self.assertRaisesRegex(ArchitectContractError, "const"):
            compile_architect_design(request)

    def test_requested_option_must_be_admitted(self) -> None:
        with self.assertRaisesRegex(ArchitectContractError, "requested option"):
            compile_architect_design(_request(requested_option_id="option:missing"))

    def test_resource_axes_must_be_wholly_known_or_unknown(self) -> None:
        request = _request()
        request["budgets"]["tool_calls"] = None  # type: ignore[index]
        with self.assertRaisesRegex(ArchitectContractError, "wholly known or wholly unknown"):
            compile_architect_design(request)

    def test_unknown_resources_cannot_manufacture_reserves(self) -> None:
        request = copy.deepcopy(example_architect_request(known_budget=False))
        request["rollback_reserve_ppm"] = 100_000
        with self.assertRaisesRegex(ArchitectContractError, "cannot manufacture"):
            compile_architect_design(request)

    def test_known_resources_require_room_after_reserves(self) -> None:
        request = _request(rollback_reserve_ppm=500_000, verification_reserve_ppm=500_000)
        with self.assertRaises(ArchitectContractError):
            compile_architect_design(request)

    def test_known_axis_must_fund_reserves_and_all_sections(self) -> None:
        request = _request()
        request["budgets"]["tool_calls"] = 10  # type: ignore[index]
        with self.assertRaisesRegex(ArchitectContractError, "all design sections"):
            compile_architect_design(request)

    def test_adopted_claim_requires_evidence_even_when_material_false(self) -> None:
        request = _request()
        claim = _claim(request, "claim:typed-contracts")
        self.assertFalse(claim["material"])
        claim["evidence_refs"] = []
        with self.assertRaisesRegex(ArchitectContractError, "adopted claim lacks evidence"):
            compile_architect_design(request)

    def test_adopted_claim_requires_acceptance_even_when_material_false(self) -> None:
        request = _request()
        claim = _claim(request, "claim:resource-reserves")
        self.assertFalse(claim["material"])
        claim["acceptance_refs"] = []
        with self.assertRaisesRegex(ArchitectContractError, "lacks acceptance criteria"):
            compile_architect_design(request)

    def test_claim_evidence_and_acceptance_must_be_admitted(self) -> None:
        request = _request()
        _claim(request, "claim:typed-contracts")["evidence_refs"] = ["evidence:foreign"]
        with self.assertRaisesRegex(ArchitectContractError, "unadmitted evidence"):
            compile_architect_design(request)
        request = _request()
        _claim(request, "claim:typed-contracts")["acceptance_refs"] = ["acceptance:foreign"]
        with self.assertRaisesRegex(ArchitectContractError, "unknown acceptance"):
            compile_architect_design(request)

    def test_nonadopted_claim_cannot_be_integrated(self) -> None:
        request = _request()
        local_ref = _option(request, "option:modular-inert")["components"][0]["component_id"]
        request["claim_mappings"].append(  # type: ignore[index]
            {
                "claim_id": "claim:live-runtime-binding",
                "option_id": "option:modular-inert",
                "design_refs": [local_ref],
            }
        )
        with self.assertRaisesRegex(ArchitectContractError, "non-adopted claim"):
            compile_architect_design(request)

    def test_every_adopted_claim_requires_one_mapping_per_option(self) -> None:
        request = _request()
        request["claim_mappings"] = [  # type: ignore[index]
            item
            for item in request["claim_mappings"]  # type: ignore[index]
            if not (
                item["claim_id"] == "claim:typed-contracts"
                and item["option_id"] == "option:monolithic-active"
            )
        ]
        with self.assertRaisesRegex(ArchitectContractError, "exactly one option-local mapping"):
            compile_architect_design(request)

    def test_duplicate_claim_mapping_fails_closed(self) -> None:
        request = _request()
        request["claim_mappings"].append(copy.deepcopy(request["claim_mappings"][0]))  # type: ignore[index]
        with self.assertRaisesRegex(ArchitectContractError, "duplicate claim-to-option mapping"):
            compile_architect_design(request)

    def test_claim_mapping_must_reference_known_claim_and_option(self) -> None:
        for field, value in (("claim_id", "claim:missing"), ("option_id", "option:missing")):
            with self.subTest(field=field):
                request = _request()
                request["claim_mappings"][0][field] = value  # type: ignore[index]
                with self.assertRaisesRegex(ArchitectContractError, "unknown claim or option"):
                    compile_architect_design(request)

    def test_claim_mapping_cannot_borrow_another_options_design(self) -> None:
        request = _request()
        foreign_ref = _option(request, "option:monolithic-active")["components"][0]["component_id"]
        _mapping(
            request,
            "claim:typed-contracts",
            "option:modular-inert",
        )["design_refs"] = [foreign_ref]
        with self.assertRaisesRegex(ArchitectContractError, "borrows design records"):
            compile_architect_design(request)

    def test_interfaces_and_boundaries_must_stay_inside_the_option(self) -> None:
        request = _request()
        option = _option(request, "option:modular-inert")
        option["interfaces"][0]["target_component_id"] = _option(  # type: ignore[index]
            request, "option:monolithic-active"
        )["components"][0]["component_id"]
        with self.assertRaisesRegex(ArchitectContractError, "interface crosses"):
            compile_architect_design(request)
        request = _request()
        option = _option(request, "option:modular-inert")
        option["trust_boundaries"][0]["target_component_id"] = _option(  # type: ignore[index]
            request, "option:monolithic-active"
        )["components"][0]["component_id"]
        with self.assertRaisesRegex(ArchitectContractError, "trust boundary crosses"):
            compile_architect_design(request)

    def test_interface_and_boundary_must_connect_distinct_components(self) -> None:
        request = _request()
        interface = _option(request, "option:modular-inert")["interfaces"][0]
        interface["target_component_id"] = interface["source_component_id"]
        with self.assertRaisesRegex(ArchitectContractError, "interface must connect distinct"):
            compile_architect_design(request)
        request = _request()
        boundary = _option(request, "option:modular-inert")["trust_boundaries"][0]
        boundary["target_component_id"] = boundary["source_component_id"]
        with self.assertRaisesRegex(ArchitectContractError, "boundary must connect distinct"):
            compile_architect_design(request)

    def test_trust_boundary_data_and_threats_are_option_local_and_complete(self) -> None:
        request = _request()
        boundary = _option(request, "option:modular-inert")["trust_boundaries"][0]
        boundary["data_classes"] = ["private-secret"]
        with self.assertRaisesRegex(ArchitectContractError, "undeclared data"):
            compile_architect_design(request)
        request = _request()
        boundary = _option(request, "option:modular-inert")["trust_boundaries"][0]
        boundary["threat_ids"] = [boundary["threat_ids"][0]]
        with self.assertRaisesRegex(ArchitectContractError, "cover exactly"):
            compile_architect_design(request)
        request = _request()
        boundary = _option(request, "option:modular-inert")["trust_boundaries"][0]
        boundary["threat_ids"] = [
            _option(request, "option:monolithic-active")["threats"][0]["threat_id"]
        ]
        with self.assertRaisesRegex(ArchitectContractError, "borrows another option"):
            compile_architect_design(request)

    def test_migration_dependencies_must_be_prior_and_local(self) -> None:
        request = _request()
        steps = _option(request, "option:modular-inert")["migration_steps"]
        steps[0]["depends_on"] = [steps[1]["step_id"]]
        with self.assertRaisesRegex(ArchitectContractError, "not an earlier local step"):
            compile_architect_design(request)

    def test_migration_and_rollback_are_exactly_bound(self) -> None:
        request = _request()
        option = _option(request, "option:modular-inert")
        option["migration_steps"][0]["rollback_step_id"] = "rollback:missing"
        with self.assertRaisesRegex(ArchitectContractError, "lacks a local rollback"):
            compile_architect_design(request)
        request = _request()
        option = _option(request, "option:modular-inert")
        option["rollback_steps"].append(
            {
                "rollback_step_id": "rollback:orphan",
                "description": "Unbound rollback.",
                "restores_ref": BASE_DEFINITION_ID,
            }
        )
        with self.assertRaisesRegex(ArchitectContractError, "not exactly migration-bound"):
            compile_architect_design(request)

    def test_each_option_must_independently_cover_all_verification_axes(self) -> None:
        fields = (
            "acceptance_refs",
            "invariant_refs",
            "threat_refs",
            "migration_step_refs",
            "rollback_step_refs",
        )
        for field in fields:
            with self.subTest(field=field):
                request = _request()
                verification = _option(request, "option:modular-inert")["verification_steps"][0]
                verification[field] = verification[field][:-1]
                with self.assertRaisesRegex(ArchitectContractError, f"verification {field}"):
                    compile_architect_design(request)

    def test_option_cannot_borrow_verification_from_another_option(self) -> None:
        request = _request()
        verification = _option(request, "option:modular-inert")["verification_steps"][0]
        verification["threat_refs"] = [
            threat["threat_id"]
            for threat in _option(request, "option:monolithic-active")["threats"]
        ]
        with self.assertRaisesRegex(ArchitectContractError, "verification threat_refs"):
            compile_architect_design(request)

    def test_design_identifiers_are_globally_unique_across_options(self) -> None:
        request = _request()
        modular = _option(request, "option:modular-inert")
        monolithic = _option(request, "option:monolithic-active")
        monolithic["components"][0]["component_id"] = modular["components"][0]["component_id"]
        with self.assertRaises(ArchitectContractError):
            compile_architect_design(request)


class ArchitectDesignTests(unittest.TestCase):
    def test_design_is_deterministic_and_all_outputs_validate(self) -> None:
        request = _request()
        first = compile_architect_design(request)
        second = compile_architect_design(request)
        self.assertEqual(first, second)
        self.assertEqual(architect_design_bytes(request), architect_design_bytes(request))
        self.assertEqual(tuple(first["outputs"]), OUTPUT_FIELDS)
        for field in OUTPUT_FIELDS:
            with self.subTest(field=field):
                result = validate_architect(
                    OUTPUT_SCHEMA_BY_FIELD[field],
                    first["outputs"][field],
                )
                self.assertTrue(result.valid, result.issues)
        envelope = validate_architect("architect-design-envelope-v1", first)
        self.assertTrue(envelope.valid, envelope.issues)

    def test_high_score_blocked_option_cannot_be_preferred(self) -> None:
        plan = compile_architect_design(_request())
        analysis = plan["outputs"]["option_analysis"]
        rankings = analysis["rankings"]
        self.assertEqual(rankings[0]["option_id"], "option:modular-inert")
        self.assertEqual(rankings[0]["viability_status"], "viable")
        blocked = next(item for item in rankings if item["option_id"] == "option:monolithic-active")
        self.assertEqual(blocked["weighted_score_ppm"], 999_000)
        self.assertEqual(blocked["viability_status"], "blocked")
        self.assertEqual(analysis["provisional_preferred_option_id"], "option:modular-inert")
        self.assertEqual(analysis["selection_status"], "defer")
        self.assertFalse(analysis["selection_authorized"])

    def test_all_blocked_options_produce_no_preference_and_steward_handoff(self) -> None:
        request = _request()
        _option(request, "option:modular-inert")["violations"] = ["violation:new"]
        plan = compile_architect_design(request)
        self.assertIsNone(plan["outputs"]["option_analysis"]["provisional_preferred_option_id"])
        self.assertEqual(plan["outputs"]["handoff"]["next_role"], "steward")
        self.assertEqual(plan["outputs"]["handoff"]["reason"], "no-viable-option-review")

    def test_requested_option_and_next_role_are_advisory_only(self) -> None:
        plan = compile_architect_design(_request())
        analysis = plan["outputs"]["option_analysis"]
        handoff = plan["outputs"]["handoff"]
        self.assertEqual(analysis["requested_option_id"], "option:monolithic-active")
        self.assertFalse(analysis["requested_option_eligible"])
        self.assertEqual(handoff["requested_next_role"], "builder")
        self.assertEqual(handoff["next_role"], "curator")
        self.assertFalse(handoff["requested_role_eligible"])
        self.assertFalse(handoff["implementation_authorized"])
        self.assertFalse(handoff["activation_authorized"])

    def test_known_resource_plan_has_positive_exact_reserves_and_sections(self) -> None:
        plan = compile_architect_design(_request())
        resource = plan["outputs"]["resource_plan"]
        self.assertEqual(resource["accounting_status"], "known")
        self.assertEqual(resource["lease_status"], "not-issued")
        self.assertEqual(tuple(resource["sections"]), RESOURCE_SECTIONS)
        for axis in RESOURCE_AXES:
            with self.subTest(axis=axis):
                allocation = resource["axes"][axis]
                self.assertGreater(allocation["rollback_reserve"], 0)
                self.assertGreater(allocation["verification_reserve"], 0)
                self.assertTrue(
                    all(value > 0 for value in allocation["section_allocations"].values())
                )
                self.assertEqual(
                    allocation["rollback_reserve"]
                    + allocation["verification_reserve"]
                    + sum(allocation["section_allocations"].values()),
                    allocation["ceiling"],
                )
        self.assertFalse(resource["budget_authorized"])

    def test_unknown_resource_plan_remains_unknown(self) -> None:
        plan = compile_architect_design(example_architect_request(known_budget=False))
        resource = plan["outputs"]["resource_plan"]
        self.assertEqual(resource["accounting_status"], "unknown")
        self.assertIsNone(resource["rollback_reserve_ppm"])
        self.assertIsNone(resource["verification_reserve_ppm"])
        for axis in RESOURCE_AXES:
            allocation = resource["axes"][axis]
            self.assertIsNone(allocation["ceiling"])
            self.assertIsNone(allocation["rollback_reserve"])
            self.assertIsNone(allocation["verification_reserve"])
            self.assertTrue(all(value is None for value in allocation["section_allocations"].values()))
        self.assertEqual(plan["outputs"]["handoff"]["next_role"], "steward")

    def test_repeated_design_fingerprint_is_visible_and_routes_to_steward(self) -> None:
        request = _request()
        first = compile_architect_design(request)
        request["prior_design_fingerprints"] = [
            first["outputs"]["option_analysis"]["design_fingerprint"]
        ]
        repeated = compile_architect_design(request)
        self.assertEqual(repeated["outputs"]["option_analysis"]["iteration_status"], "repeated")
        self.assertEqual(repeated["outputs"]["architecture"]["architecture_status"], "repeated")
        self.assertEqual(repeated["outputs"]["handoff"]["next_role"], "steward")
        self.assertEqual(repeated["outputs"]["handoff"]["reason"], "repeated-design-review")

    def test_blocked_and_recovering_objectives_have_canonical_statuses(self) -> None:
        cases = (
            ("blocked", "blocked", "blocked", "blocked"),
            ("recovering", "recovery-required", "recovery-required", "recovery-required"),
        )
        for objective_state, architecture_status, migration_status, rollback_status in cases:
            with self.subTest(objective_state=objective_state):
                plan = compile_architect_design(_request(objective_state=objective_state))
                self.assertEqual(plan["outputs"]["architecture"]["architecture_status"], architecture_status)
                self.assertTrue(
                    all(
                        option["status"] == migration_status
                        for option in plan["outputs"]["migration_plan"]["options"]
                    )
                )
                self.assertTrue(
                    all(
                        option["status"] == rollback_status
                        for option in plan["outputs"]["rollback_plan"]["options"]
                    )
                )
                self.assertEqual(plan["outputs"]["handoff"]["next_role"], "steward")

    def test_outputs_are_defensive_against_caller_mutation(self) -> None:
        request = _request()
        plan = compile_architect_design(request)
        request["options"][0]["summary"] = "caller mutation"  # type: ignore[index]
        plan["outputs"]["architecture"]["options"][0]["summary"] = "result mutation"
        fresh = compile_architect_design(_request())
        self.assertNotEqual(request, fresh["request_snapshot"])
        self.assertNotEqual(plan, fresh)

    def test_output_and_envelope_digests_detect_tampering(self) -> None:
        plan = compile_architect_design(_request())
        plan["outputs"]["architecture"]["objective"] = "tampered"
        result = validate_architect("architect-design-envelope-v1", plan)
        self.assertFalse(result.valid)
        self.assertTrue(any("output digest mismatch" in issue for issue in result.issues))
        plan = compile_architect_design(_request())
        plan["design_digest"] = "sha256:" + ("f" * 64)
        result = validate_architect("architect-design-envelope-v1", plan)
        self.assertFalse(result.valid)
        self.assertIn("design digest mismatch", result.issues)

    def test_scope_and_request_snapshot_cannot_be_resealed_to_another_request(self) -> None:
        plan = compile_architect_design(_request())
        plan["request_snapshot"]["objective"] = "forged"
        plan["request_digest"] = digest(plan["request_snapshot"])
        for output in plan["outputs"].values():
            output["request_digest"] = plan["request_digest"]
            output["output_digest"] = digest(
                {key: value for key, value in output.items() if key != "output_digest"}
            )
        plan["design_digest"] = digest(
            {key: value for key, value in plan.items() if key != "design_digest"}
        )
        result = validate_architect("architect-design-envelope-v1", plan)
        self.assertFalse(result.valid)
        self.assertIn("design envelope differs from the canonical request-bound result", result.issues)

    def test_schema_valid_semantic_reseals_are_rejected(self) -> None:
        cases: list[tuple[str, str, object]] = [
            ("option_analysis", "selection_reasons", ["authenticated-independent-review-unavailable", "forged"]),
            ("architecture", "architecture_status", "blocked"),
            ("threat_model", "risk_status", "blocked"),
            ("migration_plan", "migration_authorized", False),
            ("rollback_plan", "rollback_authorized", False),
            ("verification_plan", "verification_status", "planned"),
            ("handoff", "reason", "forged-review"),
        ]
        for field, key, value in cases:
            with self.subTest(field=field, key=key):
                plan = compile_architect_design(_request())
                output = plan["outputs"][field]
                if output[key] == value:
                    if key == "migration_authorized":
                        output["options"][0]["status"] = "blocked"
                    elif key == "rollback_authorized":
                        output["options"][0]["status"] = "blocked"
                    elif key == "verification_status":
                        output["options"][0]["steps"][0]["method"] = "Forged alternate verification method."
                else:
                    output[key] = value
                _resign_output(plan, field)
                result = validate_architect("architect-design-envelope-v1", plan)
                self.assertFalse(result.valid)
                self.assertIn(
                    "design envelope differs from the canonical request-bound result",
                    result.issues,
                )

    def test_442_resealed_leaf_mutations_cannot_escape_canonical_validation(self) -> None:
        baseline = compile_architect_design(_request())
        leaves = _scalar_leaves(baseline["outputs"])
        self.assertGreaterEqual(len(leaves), 442)
        for index, (path, value) in enumerate(leaves[:442]):
            with self.subTest(index=index, path=path):
                plan = copy.deepcopy(baseline)
                _set_path(plan["outputs"], path, _mutated_scalar(value))
                field = str(path[0])
                _resign_output(plan, field)
                result = validate_architect("architect-design-envelope-v1", plan)
                self.assertFalse(result.valid)

    def test_handoff_retains_evidence_rollback_and_selection_reasons(self) -> None:
        request = _request()
        plan = compile_architect_design(request)
        required = set(plan["outputs"]["handoff"]["required_refs"])
        self.assertTrue(set(request["evidence_refs"]).issubset(required))
        self.assertTrue(set(request["rollback_refs"]).issubset(required))
        self.assertTrue(
            set(plan["outputs"]["option_analysis"]["selection_reasons"]).issubset(required)
        )

    def test_procedural_actor_labels_never_authorize_selection_or_implementation(self) -> None:
        plan = compile_architect_design(_request())
        self.assertEqual(
            tuple(actor["role"] for actor in plan["request_snapshot"]["actors"]),
            COURT_ROLES,
        )
        self.assertTrue(
            all(actor["authenticated"] is False for actor in plan["request_snapshot"]["actors"])
        )
        self.assertFalse(plan["outputs"]["option_analysis"]["selection_authorized"])
        self.assertFalse(plan["outputs"]["architecture"]["implementation_authorized"])
        self.assertFalse(plan["outputs"]["handoff"]["implementation_authorized"])

    def test_committed_phase5b_inventory_matches_current_tree(self) -> None:
        observed = build_phase5b_inventory(REPOSITORY)
        committed = json.loads(
            (
                REPOSITORY
                / "evidence/phase5b/phase5b_architect_inventory.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(observed, committed)

    def test_no_supported_surface_or_runtime_activation_delta(self) -> None:
        inventory = build_inventory(REPOSITORY)
        self.assertEqual(len(hive_mind_os.__all__), 131)
        self.assertEqual(len(package_system.__all__), 33)
        self.assertEqual(cli_inventory()["parser_count"], 13)
        self.assertEqual(inventory["observable_module_surface"]["definition_count"], 304)
        self.assertEqual(inventory["runtime_effects"]["unclassified_candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
