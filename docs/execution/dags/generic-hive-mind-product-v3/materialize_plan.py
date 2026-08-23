#!/usr/bin/env python3
"""Deterministically materialize the inert Generic Hive Mind V3 DAG.

This tool consumes only checked-in JSON data in this directory.  It does not
import repository modules, V1 Python specifications, or the installed
controller.  Its default and only supported checked-in destination is the
external ``plan.json`` beside this file; every ``.autopilot`` destination is
refused.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
NODE_CONTRACTS_PATH = HERE / "node-contracts.json"
TRACEABILITY_PATH = HERE / "traceability.json"
OWNERSHIP_EFFECTS_PATH = HERE / "ownership-effects.json"
DEFAULT_OUTPUT = HERE / "plan.json"

MAX_JSON_BYTES = 1_000_000
MAX_JSON_DEPTH = 48

PLAN_ID = "generic-hive-mind-product-v3"
REQUEST_ID = "sha256:baa813bdcbd1b3bd459736cb65dccaf060758991a8a9b581fe8a1bf17dd65562"
OBJECTIVE_DIGEST = "sha256:36125297e861b0fea8d1be8b81e985445957f85378dc35c6712896b7b4d93c9c"
REPOSITORY_ID = "sha256:48eb2b11cd99bb34f430f5e1c7a39d9a32b9bbaac6a99db4736d2ac422915590"
TASK_KEY = "DAG-BUILD-48eb2b11cd99-baa813bdcbd1"
LAUNCH_DIGEST = "sha256:475c6908392956991faec25293170750e17fac70a97e62f550bb6d6164eb4461"
TARGET_BRANCH = "release/hive-mind-autopilot"
REQUEST_OBSERVED_HEAD = "44224532dc25b94a95c3184054ec81762a258259"
REQUEST_OBSERVED_TREE = "c2e7b983e9ed430ea8e3f7013ee2d8cb02a60e33"
QUALIFIED_PREREQUISITE_COMMIT = "ca43709591313c1c166a2e655b8982ccff16daf3"
QUALIFIED_PREREQUISITE_TREE = "22639258c7a524ffda25272ccf34fede176b2663"
AUTHORING_BASE_PARENT_COMMIT = "42b4aeef17f816430a7d8a435102635afea8761a"
AUTHORING_BASE_PARENT_TREE = "b896e16755a1d6864989757732fdc5ca9d2b5eed"
SOURCE_INTAKE_DIGEST = "sha256:dd884c72e2e587b4111dc9b6343296a52b3e87cc909ed2fa5d13141176a2782c"
STANDARD_DIGEST = "sha256:3b072fee295e75b8c28709d417f9036fa384e31dc53ca85526babd0881d0e90a"
STANDARD_BLOB = "2bc9c0fa3baf6fb5cc720ffdbf7528e93f4e7374"
COMPILER_DIGEST = "sha256:105674faf15aaf7b9f4c9db7ad4003fda404438eed2bf8cc3a1782c1cf321e6a"
COMPILER_BLOB = "f170ac4f388d265fcaafd32437e449945dcebee3"
V1_EXPECTED_PLAN_DIGEST = "sha256:b8879d09c5a42b0feeeec19b9c8f6a7523e4ef69b117eea1a18ef6dfaf35f977"


class MaterializationError(RuntimeError):
    """The inert source data cannot produce the declared V3 plan."""


def _reject_constant(value: str) -> None:
    raise MaterializationError(f"non-finite JSON number is forbidden: {value}")


def _pairs_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MaterializationError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _validate_depth_and_numbers(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 1)]
    while pending:
        current, depth = pending.pop()
        if depth > MAX_JSON_DEPTH:
            raise MaterializationError(
                f"JSON nesting exceeds maximum depth {MAX_JSON_DEPTH}"
            )
        if isinstance(current, float) and not math.isfinite(current):
            raise MaterializationError("non-finite JSON number is forbidden")
        if isinstance(current, dict):
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def load_strict_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise MaterializationError(f"cannot read {path}: {error}") from error
    if len(raw) > MAX_JSON_BYTES:
        raise MaterializationError(
            f"JSON source exceeds {MAX_JSON_BYTES} bytes: {path}"
        )
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise MaterializationError(f"cannot parse strict JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise MaterializationError(f"JSON document must be an object: {path}")
    _validate_depth_and_numbers(value)
    return value, raw


def canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise MaterializationError(f"value is not canonical JSON material: {error}") from error


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MaterializationError(message)


def _acceptance_ids(node: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    criteria = node.get("acceptance_criteria")
    _require(isinstance(criteria, list) and criteria, f"{node.get('id')} criteria missing")
    for criterion in criteria:
        _require(isinstance(criterion, str) and ":" in criterion, "criterion id missing")
        criterion_id = criterion.split(":", 1)[0]
        _require(criterion_id not in result, f"duplicate criterion id {criterion_id}")
        result.add(criterion_id)
    return result


def _validate_sources(
    contracts: dict[str, Any],
    traceability: dict[str, Any],
    ownership: dict[str, Any],
) -> None:
    _require(contracts.get("schema_version") == 3, "node contract version mismatch")
    _require(contracts.get("plan_id") == PLAN_ID, "node contract plan id mismatch")
    nodes = contracts.get("nodes")
    order = contracts.get("node_order")
    _require(isinstance(nodes, list) and len(nodes) == 20, "expected 20 node contracts")
    _require(isinstance(order, list) and len(order) == 20, "expected 20 node ids")
    observed_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    _require(observed_ids == order, "node order and node declarations differ")
    _require(len(set(observed_ids)) == 20, "node ids must be unique")
    _require(
        all(node.get("parallel_safe") is False for node in nodes),
        "exact manual-parent contract requires one serial round per node",
    )
    frozen_host = contracts.get("frozen_host_contract")
    _require(isinstance(frozen_host, dict), "frozen host contract missing")
    _require(frozen_host.get("file_count") == 16, "frozen host file count mismatch")
    _require(
        frozen_host.get("bundle_digest")
        == "sha256:76b89c6e83c9dc2c7ae4d41bbba0b2f6b1fdd8861e0a7c7aeda01602d1c89255",
        "frozen host bundle digest mismatch",
    )
    _require(
        isinstance(frozen_host.get("files"), list)
        and len(frozen_host["files"]) == 16,
        "frozen host per-file manifest missing",
    )

    write_owners: dict[str, str] = {}
    acceptance_ids: set[str] = set()
    for node in nodes:
        _require(isinstance(node, dict), "node contract must be an object")
        node_id = node.get("id")
        _require(isinstance(node_id, str) and node_id, "node id missing")
        for path in node.get("write_scope", []):
            _require(isinstance(path, str) and path, f"{node_id} write path malformed")
            _require(path not in write_owners, f"write path has multiple owners: {path}")
            write_owners[path] = node_id
        node_acceptance = _acceptance_ids(node)
        _require(not acceptance_ids.intersection(node_acceptance), "acceptance id collision")
        acceptance_ids.update(node_acceptance)
    _require(len(write_owners) == 85, "expected exactly 85 unique write paths")

    _require(traceability.get("schema_version") == 3, "traceability version mismatch")
    rows = traceability.get("rows")
    _require(isinstance(rows, dict) and len(rows) == 89, "expected 89 V1 mappings")
    for row_id, mapping in rows.items():
        _require(isinstance(row_id, str) and isinstance(mapping, dict), "bad trace row")
        targets = mapping.get("target_acceptance_ids")
        _require(isinstance(targets, list) and targets, f"{row_id} target mapping missing")
        _require(len(set(targets)) == len(targets), f"{row_id} target mapping duplicates")
        _require(set(targets).issubset(acceptance_ids), f"{row_id} target criterion unknown")
        _require(
            any(not target.endswith("-TRACE") for target in targets),
            f"{row_id} lacks a substantive acceptance mapping",
        )
    corners = traceability.get("v3_specific_corners")
    _require(isinstance(corners, list) and len(corners) >= 27, "V3 corner coverage missing")
    supplement = traceability.get("supplemental_execution_path_record")
    _require(isinstance(supplement, dict), "execution-path supplement missing")
    _require(
        supplement.get("bound_clerk_intake_sha256")
        == SOURCE_INTAKE_DIGEST.removeprefix("sha256:"),
        "execution-path supplement Clerk binding mismatch",
    )

    _require(ownership.get("schema_version") == 3, "ownership version mismatch")
    expected_count = ownership.get("path_ownership", {}).get(
        "expected_unique_write_path_count"
    )
    _require(expected_count == len(write_owners), "ownership path count mismatch")
    effects = ownership.get("node_effect_expectations")
    _require(isinstance(effects, dict) and set(effects) == set(observed_ids), "effect inventory mismatch")
    for node in nodes:
        expected = effects[node["id"]]
        _require(
            node.get("candidate_build_effects") == expected.get("candidate_build_effects"),
            f"candidate effect mismatch for {node['id']}",
        )
        _require(
            node.get("capabilities_under_test") == expected.get("capabilities_under_test"),
            f"capability-under-test mismatch for {node['id']}",
        )


def build_plan() -> dict[str, Any]:
    contracts, contracts_raw = load_strict_json(NODE_CONTRACTS_PATH)
    traceability, traceability_raw = load_strict_json(TRACEABILITY_PATH)
    ownership, ownership_raw = load_strict_json(OWNERSHIP_EFFECTS_PATH)
    _validate_sources(contracts, traceability, ownership)

    nodes_source = contracts["nodes"]
    common_forbidden = contracts["common_forbidden_scope"]
    all_write_paths = sorted(
        path for source in nodes_source for path in source["write_scope"]
    )
    nodes: list[dict[str, Any]] = []
    for source in nodes_source:
        node = dict(source)
        node_id = node["id"]
        own_paths = set(node["write_scope"])
        node["downstream_unlock_value"] = node["critical_path_importance"]
        node["file_locks"] = list(node["write_scope"])
        node["forbidden_scope"] = list(common_forbidden) + [
            path for path in all_write_paths if path not in own_paths
        ]
        node["ownership_contract"] = {
            "write_path_owner": node_id,
            "all_other_write_paths_forbidden": True,
        }
        node["contract_digest"] = digest(node)
        nodes.append(node)

    source_documents = {
        "node_contracts": {
            "path": "docs/execution/dags/generic-hive-mind-product-v3/node-contracts.json",
            "bytes": len(contracts_raw),
            "raw_sha256": bytes_digest(contracts_raw),
            "canonical_digest": digest(contracts),
        },
        "traceability": {
            "path": "docs/execution/dags/generic-hive-mind-product-v3/traceability.json",
            "bytes": len(traceability_raw),
            "raw_sha256": bytes_digest(traceability_raw),
            "canonical_digest": digest(traceability),
        },
        "ownership_effects": {
            "path": "docs/execution/dags/generic-hive-mind-product-v3/ownership-effects.json",
            "bytes": len(ownership_raw),
            "raw_sha256": bytes_digest(ownership_raw),
            "canonical_digest": digest(ownership),
        },
    }
    generation_material = {
        "schema": "external-plan-generation-v3",
        "plan_id": PLAN_ID,
        "request_id": REQUEST_ID,
        "objective_digest": OBJECTIVE_DIGEST,
        "repository_id": REPOSITORY_ID,
        "task_key": TASK_KEY,
        "launch_digest": LAUNCH_DIGEST,
        "target_branch": TARGET_BRANCH,
        "authoring_base_parent_commit": AUTHORING_BASE_PARENT_COMMIT,
        "authoring_base_parent_tree": AUTHORING_BASE_PARENT_TREE,
        "source_intake_digest": SOURCE_INTAKE_DIGEST,
        "standard_digest": STANDARD_DIGEST,
        "compiler_digest": COMPILER_DIGEST,
        "source_document_digests": {
            key: value["raw_sha256"] for key, value in source_documents.items()
        },
    }
    generation_id = digest(generation_material)
    resume_material = {
        "schema": "manual-parent-resume-v1",
        "plan_id": PLAN_ID,
        "generation_id": generation_id,
        "request_id": REQUEST_ID,
        "objective_digest": OBJECTIVE_DIGEST,
        "repository_id": REPOSITORY_ID,
        "task_key": TASK_KEY,
        "launch_digest": LAUNCH_DIGEST,
        "target_branch": TARGET_BRANCH,
        "authoring_base_parent_commit": AUTHORING_BASE_PARENT_COMMIT,
        "authoring_base_parent_tree": AUTHORING_BASE_PARENT_TREE,
    }

    plan: dict[str, Any] = {
        "schema_version": 3,
        "kind": "hive-mind-generic-product-overlay-v3",
        "plan_id": PLAN_ID,
        "title": "Bounded Generic Hive Mind Product Completion V3",
        "request_binding": {
            "request_id": REQUEST_ID,
            "objective_digest": OBJECTIVE_DIGEST,
            "repository_id": REPOSITORY_ID,
            "task_key": TASK_KEY,
            "launch_digest": LAUNCH_DIGEST,
            "target_branch": TARGET_BRANCH,
            "request_observed_head": REQUEST_OBSERVED_HEAD,
            "request_observed_tree": REQUEST_OBSERVED_TREE,
        },
        "repository_binding": {
            "repository": "kb4beast/hive-mind-os",
            "qualified_prerequisite_commit": QUALIFIED_PREREQUISITE_COMMIT,
            "qualified_prerequisite_tree": QUALIFIED_PREREQUISITE_TREE,
            "authoring_base_parent_commit": AUTHORING_BASE_PARENT_COMMIT,
            "authoring_base_parent_tree": AUTHORING_BASE_PARENT_TREE,
            "target_branch": TARGET_BRANCH,
        },
        "standard": {
            "version": 2,
            "path": "docs/execution/DAG_AUTHORING_STANDARD_V2.md",
            "bytes": 12312,
            "sha256": STANDARD_DIGEST,
            "git_blob_sha": STANDARD_BLOB,
        },
        "compiler": {
            "path": ".autopilot/bin/dag_standard.py",
            "bytes": 104317,
            "sha256": COMPILER_DIGEST,
            "git_blob_sha": COMPILER_BLOB,
            "execution_trust": "external_frozen_host_required",
        },
        "source_intake": {
            "path": "docs/execution/dags/generic-hive-mind-product-v3/source-intake.json",
            "bytes": 58463,
            "sha256": SOURCE_INTAKE_DIGEST,
        },
        "source_documents": source_documents,
        "generation": {
            "schema": "external-plan-generation-v3",
            "generation_id": generation_id,
            "material": generation_material,
        },
        "resume_identity": {
            "schema": "manual-parent-resume-v1",
            "resume_id": digest(resume_material),
            "material": resume_material,
            "required_runtime_bindings": [
                "manifest_expected_plan_digest",
                "one_run_nonce",
                "lease_deadline",
                "frozen_host_bundle_digest",
                "interpreter_digest",
                "parent_principal",
                "round_ledger_digest",
                "committed_payload_head",
                "committed_payload_tree",
                "caller_authenticated_manifest_digest",
            ],
        },
        "execution": {
            "mode": "manual-parent-v1",
            "external_plan": True,
            "external_plan_path": "docs/execution/dags/generic-hive-mind-product-v3/plan.json",
            "executable_dispatch_command_available": False,
            "round_command_policy": "all_null",
            "runnable_commands_embedded": False,
            "expected_round_count": 20,
            "expected_nodes_per_round": 1,
            "legacy_fallback": "PROHIBITED",
            "parent_consumption": "author_verified_not_dispatched_by_this_document",
        },
        "activation_contract": {
            "schema": "host-authenticated-external-plan-activation-v3",
            "checked_in_status": "REQUIRED_NOT_SATISFIED",
            "same_request_fast_path": "exact_request_on_persisted_target_before_new_target_protection_check",
            "signed_bundle_must_contain": [
                "complete_plan_bytes",
                "manifest_digest",
                "expected_plan_digest",
                "reviewer_identity_and_evidence_digest",
                "actor_identity",
                "issuer_identity",
                "request_id",
                "repository_id",
                "objective_digest",
                "target_branch",
                "authoring_base_parent_commit",
                "authoring_base_parent_tree",
                "committed_payload_head",
                "committed_payload_tree",
                "caller_authenticated_manifest_digest",
                "compiler_digest",
                "standard_digest",
                "one_run_nonce",
                "lease_deadline",
            ],
            "signature_boundary": "host_external_distinct_key",
            "path_reference_sufficient": False,
            "detached_digest_sufficient": False,
            "repeat_resume": "idempotent_only_for_exact_generation_and_resume_identity",
            "concurrent_activation": "single_winner_compare_and_swap_ledger",
            "strict_rejections": [
                "duplicate_json_key",
                "non_finite_number",
                "oversize_document",
                "excessive_nesting_depth",
                "path_swap",
                "detached_signature_or_digest_substitution",
                "request_repository_objective_or_generation_collision",
                "replay_or_expired_lease",
                "repeat_resume_identity_mismatch",
                "concurrent_activation_loser",
            ],
            "invalid_v3_legacy_fallback": "PROHIBITED",
        },
        "authority": {
            "execution_status": "DEFER_UNTIL_EXTERNAL_HOST_AND_AUTHORITY_EVIDENCE_SATISFIED",
            "remote_effect_default": "DENY",
            "protected_merge": "ALWAYS_SEPARATE_AUTHORITY_GATE",
            "typed_blockers": [
                "credentials_or_secret_acquisition",
                "legal_consent_signature_or_identity_attestation",
                "spending_or_financial_commitment",
                "production_mutation_or_deployment",
                "protected_branch_mutation_or_merge",
                "missing_or_quarantined_evidence",
                "unresolved_license_or_lineage",
                "destructive_or_irreversible_effect_without_explicit_scope",
                "unbounded_replication_or_authority_expansion",
            ],
            "fresh_host_requirements": [
                "distinct_signing_principal_or_enforced_outside_repository_deny_sandbox",
                "exact_ca437095_pristine_bytecode_free_read_only_sixteen_file_git_extraction",
                "short_lived_one_run_lease_nonce_and_deadline",
                "unchanged_ca437_derived_host_for_compile_schedule_integration_doctor_and_ci",
                "exact_interpreter_reviewer_predecessor_and_new_trust_receipts_and_one_run_ledger",
                "exactly_twenty_manual_parent_rounds_with_all_commands_null",
            ],
            "known_adverse_state": [
                "stored_controller_capability_is_stale_and_expired",
                "same_windows_sid_can_read_existing_authority_key",
                "legacy_continuation_release_publication_was_withheld_after_reconciliation_and_remote_snapshot_change",
            ],
        },
        "source_governance": {
            "SRC-024": "QUARANTINE_CONTENT_UNREAD_NO_DESIGN_AUTHORITY",
            "SRC-025": "DEFER_UNRESOLVED_PROVENANCE_LICENSE_AND_LINEAGE",
        },
        "frozen_host_contract": contracts["frozen_host_contract"],
        "supplemental_execution_path_provenance": {
            "source": "traceability.json#supplemental_execution_path_record",
            "status": traceability["supplemental_execution_path_record"]["status"],
            "bound_clerk_intake_sha256": traceability[
                "supplemental_execution_path_record"
            ]["bound_clerk_intake_sha256"],
            "court_required": True,
        },
        "vision_posture": {
            "A5": "NOT_READY",
            "active_gate_reference_only_conflict": "UNRESOLVED",
            "maximum_claim": "bounded_generic_candidate_subject_to_independent_court",
            "forbidden_claims": [
                "full_autonomy",
                "full_hardened_vision_compliance",
                "production_readiness",
                "release_readiness",
                "deployment_readiness",
                "protected_merge_readiness",
                "superiority",
            ],
        },
        "qualification_boundary": {
            "all_implementation_documentation_fixture_and_test_source_complete_before": "QUALIFICATION-PREP-625",
            "candidate_ci_node": "CANDIDATE-CI-627",
            "candidate_ci_exact_checks": [
                "FROZEN-HOST-FULL-DOCTOR",
                "FROZEN-HOST-REPOSITORY-CI",
            ],
            "evidence_only_judgment_node": "GENERIC-QUALIFICATION-630",
            "effect_only_handoff_node": "HANDOFF-700",
            "handoff_effect": "authorized_draft_pull_request_only",
            "merge_permitted": False,
            "candidate_and_evidence_lineage": ownership["phase_boundaries"][
                "candidate_and_evidence_lineage"
            ],
            "post_freeze_write_locations": ownership["phase_boundaries"][
                "post_freeze_write_locations"
            ],
        },
        "historical_v1": {
            "status": "provenance_only_no_execution_fallback",
            "expected_plan_digest": V1_EXPECTED_PLAN_DIGEST,
            "node_count": 16,
            "traceability_rows": 89,
        },
        "topology_contract": {
            "node_count": 20,
            "raw_edge_count": 28,
            "level_count": 17,
            "redundant_direct_edge_count": 6,
        },
        "ownership_contract": {
            "unique_write_path_count": 85,
            "all_other_node_write_paths_forbidden": True,
            "single_writer_surface_count": 7,
        },
        "nodes": nodes,
    }
    plan["plan_digest"] = digest(plan)
    return plan


def render_plan(plan: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            plan,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _refuse_autopilot_destination(path: Path) -> None:
    resolved = path.resolve()
    if any(part.lower() == ".autopilot" for part in resolved.parts):
        raise MaterializationError("materialization into .autopilot is forbidden")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stdout", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    plan = build_plan()
    rendered = render_plan(plan)
    output = args.output.resolve()
    _refuse_autopilot_destination(output)
    if args.stdout:
        print(rendered.decode("utf-8"), end="")
    elif args.check:
        try:
            current = output.read_bytes()
        except OSError as error:
            raise MaterializationError(f"cannot read materialized plan: {error}") from error
        if current != rendered:
            raise MaterializationError("materialized plan differs from deterministic output")
    else:
        if output != DEFAULT_OUTPUT.resolve():
            raise MaterializationError(
                "checked-in materialization may write only this overlay's external plan.json"
            )
        output.write_bytes(rendered)
    print(
        json.dumps(
            {
                "external_plan": str(output),
                "execution_mode": "manual-parent-v1",
                "node_count": len(plan["nodes"]),
                "plan_digest": plan["plan_digest"],
                "runnable_commands_embedded": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MaterializationError as error:
        print(json.dumps({"materialized": False, "error": str(error)}, sort_keys=True))
        raise SystemExit(2) from None
