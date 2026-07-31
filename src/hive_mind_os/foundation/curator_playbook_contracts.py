from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping, cast

from .canonical import canonical_bytes, digest, reject_private_content
from .contracts import FoundationValidation, validate_document_against_schema

DIALECT = "https://json-schema.org/draft/2020-12/schema"
CURATOR_SCHEMA_NAMES = (
    "curator-agent-successor-v1",
    "curator-verification-request-v1",
    "curator-verification-scope-v1",
    "curator-claim-reconstruction-v1",
    "curator-clean-boundary-reproduction-v1",
    "curator-counterexample-search-v1",
    "curator-security-privacy-review-v1",
    "curator-provenance-license-review-v1",
    "curator-regression-analysis-v1",
    "curator-artifact-receipt-verification-v1",
    "curator-rollback-verification-v1",
    "curator-release-recommendation-v1",
    "curator-dissent-unresolved-evidence-v1",
    "curator-verification-envelope-v1",
)

AGENT_ID = "hive-agent:curator:v2-shadow-1"
DEFINITION_ID = "hive-agent-definition:curator:v2-shadow-1"
BASE_DEFINITION_ID = "hive-agent-definition:curator:v2-candidate"
EXPECTED_SUCCESSOR_DIGEST = "sha256:3ca6aa8d1f32b1377490c0a87afd4aee248641fe95231705cb4963ef2e7eaa7c"

OUTPUT_FIELDS = (
    "verification_scope",
    "claim_reconstruction",
    "clean_boundary_reproduction",
    "counterexample_search",
    "security_privacy_review",
    "provenance_license_review",
    "regression_analysis",
    "artifact_receipt_verification",
    "rollback_verification",
    "release_recommendation",
    "dissent_unresolved_evidence",
)
OUTPUT_SCHEMA_BY_FIELD: Mapping[str, str] = MappingProxyType(
    {
        "verification_scope": "curator-verification-scope-v1",
        "claim_reconstruction": "curator-claim-reconstruction-v1",
        "clean_boundary_reproduction": "curator-clean-boundary-reproduction-v1",
        "counterexample_search": "curator-counterexample-search-v1",
        "security_privacy_review": "curator-security-privacy-review-v1",
        "provenance_license_review": "curator-provenance-license-review-v1",
        "regression_analysis": "curator-regression-analysis-v1",
        "artifact_receipt_verification": "curator-artifact-receipt-verification-v1",
        "rollback_verification": "curator-rollback-verification-v1",
        "release_recommendation": "curator-release-recommendation-v1",
        "dissent_unresolved_evidence": "curator-dissent-unresolved-evidence-v1",
    }
)
COURT_ROLES = (
    "orchestrator",
    "explorer-advocate",
    "architect",
    "builder",
    "cross-examiner",
    "curator",
    "integrator",
    "steward",
    "optimizer",
    "judge",
)
RESOURCE_AXES = ("tokens", "cost_microunits", "elapsed_ms", "tool_calls")
RESOURCE_SECTIONS = OUTPUT_FIELDS
LAYER_KINDS = (
    "base",
    "prompt",
    "playbook",
    "skills",
    "input",
    "outputs",
    "governance",
    "lifecycle",
)
LAYER_IDS = (
    BASE_DEFINITION_ID,
    "generation-zero:curator",
    "curator:deep-playbook",
    "skill.curator",
    "curator:verification-request",
    "curator:typed-outputs",
    "curator:phase5d-governance",
    "generation-zero:lifecycle",
)

_DIGEST = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
_COMMIT = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
_ID = {"type": "string", "minLength": 1, "maxLength": 256}
_TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
_PATH = {
    "type": "string",
    "minLength": 1,
    "maxLength": 512,
    "pattern": r"^(?!/)(?!.*(?:^|/)\.\.?(?:/|$))(?!.*\\)[A-Za-z0-9._/\-]+$",
}
_REF_LIST = {
    "type": "array",
    "maxItems": 128,
    "uniqueItems": True,
    "items": _ID,
}
_NONEMPTY_REFS = {
    "type": "array",
    "minItems": 1,
    "maxItems": 128,
    "uniqueItems": True,
    "items": _ID,
}


def _object(name: str, required: tuple[str, ...], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "$schema": DIALECT,
        "$id": f"https://hive-mind-os.invalid/contracts/{name}",
        "type": "object",
        "required": list(required),
        "properties": properties,
        "additionalProperties": False,
    }


_LAYER = {
    "type": "object",
    "required": ["position", "layer_id", "kind", "version", "source_digests", "digest"],
    "properties": {
        "position": {"type": "integer", "minimum": 1, "maximum": 8},
        "layer_id": _ID,
        "kind": {"type": "string", "enum": list(LAYER_KINDS)},
        "version": _ID,
        "source_digests": {
            "type": "array",
            "minItems": 1,
            "maxItems": 16,
            "uniqueItems": True,
            "items": _DIGEST,
        },
        "digest": _DIGEST,
    },
    "additionalProperties": False,
}

_AUTHORITY_STATE = {
    "type": "object",
    "required": [
        "authority",
        "activation",
        "effective_capability_count",
        "tool_count",
        "implementation_authorized",
        "execution_authorized",
        "test_result_authorized",
        "completion_authorized",
        "release_authorized",
        "promotion_authorized",
    ],
    "properties": {
        "authority": {"const": "none"},
        "activation": {"const": "inert"},
        "effective_capability_count": {"const": 0},
        "tool_count": {"const": 0},
        "implementation_authorized": {"const": False},
        "execution_authorized": {"const": False},
        "test_result_authorized": {"const": False},
        "completion_authorized": {"const": False},
        "release_authorized": {"const": False},
        "promotion_authorized": {"const": False},
    },
    "additionalProperties": False,
}

_ACCEPTANCE = {
    "type": "object",
    "required": ["acceptance_id", "statement"],
    "properties": {"acceptance_id": _ID, "statement": _TEXT},
    "additionalProperties": False,
}

_IDENTITY = {
    "type": "object",
    "required": ["role", "actor_id", "authenticated"],
    "properties": {
        "role": {"type": "string", "enum": ["builder", "curator"]},
        "actor_id": _ID,
        "authenticated": {"const": False},
    },
    "additionalProperties": False,
}

_CLAIM = {
    "type": "object",
    "required": [
        "claim_id",
        "statement",
        "claim_type",
        "material",
        "acceptance_refs",
        "builder_evidence_refs",
        "source_refs",
    ],
    "properties": {
        "claim_id": _ID,
        "statement": _TEXT,
        "claim_type": {
            "type": "string",
            "enum": [
                "implementation",
                "test-result",
                "security",
                "privacy",
                "provenance",
                "license",
                "rollback",
                "compatibility",
                "completion",
                "release",
            ],
        },
        "material": {"type": "boolean"},
        "acceptance_refs": _NONEMPTY_REFS,
        "builder_evidence_refs": _NONEMPTY_REFS,
        "source_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_SEALED_CHECK = {
    "type": "object",
    "required": [
        "check_id",
        "command",
        "expected",
        "claim_refs",
        "acceptance_refs",
        "sealed_before_candidate_access",
    ],
    "properties": {
        "check_id": _ID,
        "command": _TEXT,
        "expected": {"type": "string", "enum": ["pass", "fail"]},
        "claim_refs": _NONEMPTY_REFS,
        "acceptance_refs": _NONEMPTY_REFS,
        "sealed_before_candidate_access": {"const": True},
    },
    "additionalProperties": False,
}

_EVIDENCE = {
    "type": "object",
    "required": [
        "evidence_id",
        "kind",
        "digest",
        "subject_commit",
        "subject_tree",
        "producer_role",
        "producer_actor_id",
        "integrity_status",
        "stale",
        "claim_refs",
        "acceptance_refs",
        "receipt_fields",
    ],
    "properties": {
        "evidence_id": _ID,
        "kind": {
            "type": "string",
            "enum": [
                "source",
                "diff",
                "test-before",
                "test-after",
                "security",
                "privacy",
                "license",
                "artifact",
                "receipt",
                "rollback",
                "inventory",
                "sbom",
            ],
        },
        "digest": _DIGEST,
        "subject_commit": _COMMIT,
        "subject_tree": _COMMIT,
        "producer_role": {
            "type": "string",
            "enum": ["builder", "curator", "integrator", "steward", "external-system"],
        },
        "producer_actor_id": _ID,
        "integrity_status": {
            "type": "string",
            "enum": ["digest-verified", "forged", "unknown"],
        },
        "stale": {"type": "boolean"},
        "claim_refs": _NONEMPTY_REFS,
        "acceptance_refs": _NONEMPTY_REFS,
        "receipt_fields": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "uniqueItems": True,
            "items": _ID,
        },
    },
    "additionalProperties": False,
}

_SOURCE = {
    "type": "object",
    "required": [
        "source_id",
        "uri",
        "version",
        "digest",
        "license_status",
        "completeness",
        "claim_refs",
    ],
    "properties": {
        "source_id": _ID,
        "uri": _TEXT,
        "version": _ID,
        "digest": _DIGEST,
        "license_status": {
            "type": "string",
            "enum": ["admitted", "unknown", "quarantined"],
        },
        "completeness": {
            "type": "string",
            "enum": ["complete", "partial", "unavailable"],
        },
        "claim_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_REGRESSION_TARGET = {
    "type": "object",
    "required": [
        "target_id",
        "path",
        "baseline_digest",
        "candidate_digest",
        "test_refs",
        "assertions_before",
        "assertions_after",
        "test_functions_before",
        "test_functions_after",
    ],
    "properties": {
        "target_id": _ID,
        "path": _PATH,
        "baseline_digest": _DIGEST,
        "candidate_digest": _DIGEST,
        "test_refs": _NONEMPTY_REFS,
        "assertions_before": {"type": "integer", "minimum": 0, "maximum": 100000},
        "assertions_after": {"type": "integer", "minimum": 0, "maximum": 100000},
        "test_functions_before": {"type": "integer", "minimum": 0, "maximum": 100000},
        "test_functions_after": {"type": "integer", "minimum": 0, "maximum": 100000},
    },
    "additionalProperties": False,
}

_ACTOR = {
    "type": "object",
    "required": ["role", "actor_id", "authenticated"],
    "properties": {
        "role": {"type": "string", "enum": list(COURT_ROLES)},
        "actor_id": _ID,
        "authenticated": {"const": False},
    },
    "additionalProperties": False,
}

_BUDGETS = {
    "type": "object",
    "required": list(RESOURCE_AXES),
    "properties": {
        axis: {"type": ["integer", "null"], "minimum": 1, "maximum": 10**15}
        for axis in RESOURCE_AXES
    },
    "additionalProperties": False,
}

_CALLER_CLAIMS = {
    "type": "object",
    "required": [
        "builder_complete",
        "tests_passed",
        "release_ready",
        "independent_verification_complete",
    ],
    "properties": {
        "builder_complete": {"const": False},
        "tests_passed": {"const": False},
        "release_ready": {"const": False},
        "independent_verification_complete": {"const": False},
    },
    "additionalProperties": False,
}

_POINT_IN_TIME = {
    "type": "object",
    "required": ["knowledge_cutoff_commit", "target_commit", "future_commit_refs"],
    "properties": {
        "knowledge_cutoff_commit": _COMMIT,
        "target_commit": _COMMIT,
        "future_commit_refs": {
            "type": "array",
            "maxItems": 0,
            "items": _COMMIT,
        },
    },
    "additionalProperties": False,
}

_REQUEST_SCHEMA = _object(
    "curator-verification-request-v1",
    (
        "record_type",
        "schema_version",
        "request_id",
        "objective_id",
        "tenant_id",
        "repository_id",
        "objective",
        "objective_state",
        "base_commit",
        "base_tree",
        "subject_commit",
        "subject_tree",
        "builder_envelope",
        "builder_identity",
        "curator_identity",
        "blind_seal_sequence",
        "candidate_access_sequence",
        "acceptance_criteria",
        "claims",
        "sealed_checks",
        "observed_evidence",
        "sources",
        "regression_targets",
        "rollback_refs",
        "rollback_verification_test_refs",
        "point_in_time",
        "budgets",
        "verification_reserve_ppm",
        "evidence_reserve_ppm",
        "rollback_reserve_ppm",
        "actors",
        "prior_fingerprints",
        "requested_release_recommendation",
        "caller_claims",
    ),
    {
        "record_type": {"const": "curator-verification-request"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "objective": _TEXT,
        "objective_state": {"const": "ready"},
        "base_commit": _COMMIT,
        "base_tree": _COMMIT,
        "subject_commit": _COMMIT,
        "subject_tree": _COMMIT,
        "builder_envelope": {"type": "object"},
        "builder_identity": _IDENTITY,
        "curator_identity": _IDENTITY,
        "blind_seal_sequence": {"type": "integer", "minimum": 1},
        "candidate_access_sequence": {"type": "integer", "minimum": 2},
        "acceptance_criteria": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _ACCEPTANCE,
        },
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _CLAIM,
        },
        "sealed_checks": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _SEALED_CHECK,
        },
        "observed_evidence": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _EVIDENCE,
        },
        "sources": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _SOURCE,
        },
        "regression_targets": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _REGRESSION_TARGET,
        },
        "rollback_refs": _NONEMPTY_REFS,
        "rollback_verification_test_refs": _NONEMPTY_REFS,
        "point_in_time": _POINT_IN_TIME,
        "budgets": _BUDGETS,
        "verification_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 900000},
        "evidence_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 900000},
        "rollback_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 900000},
        "actors": {
            "type": "array",
            "minItems": len(COURT_ROLES),
            "maxItems": len(COURT_ROLES),
            "items": _ACTOR,
        },
        "prior_fingerprints": _REF_LIST,
        "requested_release_recommendation": {
            "type": "string",
            "enum": ["defer", "reject", "quarantine"],
        },
        "caller_claims": _CALLER_CLAIMS,
    },
)

_COMMON_OUTPUT_REQUIRED = (
    "record_type",
    "schema_version",
    "request_id",
    "request_digest",
    "objective_id",
    "tenant_id",
    "repository_id",
    "curator_definition_id",
    "curator_version",
    "builder_definition_id",
    "builder_successor_digest",
    "builder_implementation_digest",
    "base_commit",
    "base_tree",
    "subject_commit",
    "subject_tree",
    "claim_refs",
    "acceptance_refs",
    "evidence_refs",
    "rollback_refs",
    "authority_state",
    "budget_state",
    "authenticated_distinct_actors",
    "same_assistant_performed_procedural_passes",
    "independence_claimed",
    "output_digest",
)
_COMMON_OUTPUT_PROPERTIES: dict[str, Any] = {
    "record_type": _ID,
    "schema_version": {"const": 1},
    "request_id": _ID,
    "request_digest": _DIGEST,
    "objective_id": _ID,
    "tenant_id": _ID,
    "repository_id": _ID,
    "curator_definition_id": {"const": DEFINITION_ID},
    "curator_version": {"const": "2-shadow-1"},
    "builder_definition_id": _ID,
    "builder_successor_digest": _DIGEST,
    "builder_implementation_digest": _DIGEST,
    "base_commit": _COMMIT,
    "base_tree": _COMMIT,
    "subject_commit": _COMMIT,
    "subject_tree": _COMMIT,
    "claim_refs": _NONEMPTY_REFS,
    "acceptance_refs": _NONEMPTY_REFS,
    "evidence_refs": _NONEMPTY_REFS,
    "rollback_refs": _NONEMPTY_REFS,
    "authority_state": _AUTHORITY_STATE,
    "budget_state": {"type": "string", "enum": ["known", "unknown"]},
    "authenticated_distinct_actors": {"const": False},
    "same_assistant_performed_procedural_passes": {"const": True},
    "independence_claimed": {"const": False},
    "output_digest": _DIGEST,
}


def _output_schema(
    name: str,
    record_type: str,
    required: tuple[str, ...],
    properties: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(_COMMON_OUTPUT_PROPERTIES)
    merged["record_type"] = {"const": record_type}
    merged.update(properties)
    return _object(name, _COMMON_OUTPUT_REQUIRED + required, merged)


_FINDING = {
    "type": "object",
    "required": ["finding_id", "status", "severity", "reason", "evidence_refs"],
    "properties": {
        "finding_id": _ID,
        "status": {"type": "string", "enum": ["pass", "fail", "not-evaluated"]},
        "severity": {"type": "string", "enum": ["info", "minor", "major", "blocker"]},
        "reason": _TEXT,
        "evidence_refs": _REF_LIST,
    },
    "additionalProperties": False,
}

_VERIFICATION_SCOPE_SCHEMA = _output_schema(
    "curator-verification-scope-v1",
    "curator-verification-scope",
    (
        "blind_checks_sealed",
        "sealed_before_candidate_access",
        "clean_boundary_required",
        "builder_summary_is_proof",
        "implementation_authorized",
        "verification_scope_complete",
    ),
    {
        "blind_checks_sealed": {"const": True},
        "sealed_before_candidate_access": {"const": True},
        "clean_boundary_required": {"const": True},
        "builder_summary_is_proof": {"const": False},
        "implementation_authorized": {"const": False},
        "verification_scope_complete": {"const": True},
    },
)

_RECONSTRUCTED_CLAIM = {
    "type": "object",
    "required": [
        "claim_id",
        "statement_digest",
        "claim_type",
        "material",
        "acceptance_refs",
        "source_refs",
        "builder_evidence_refs",
        "reconstructed_without_builder_rationale",
    ],
    "properties": {
        "claim_id": _ID,
        "statement_digest": _DIGEST,
        "claim_type": _ID,
        "material": {"type": "boolean"},
        "acceptance_refs": _NONEMPTY_REFS,
        "source_refs": _NONEMPTY_REFS,
        "builder_evidence_refs": _NONEMPTY_REFS,
        "reconstructed_without_builder_rationale": {"const": True},
    },
    "additionalProperties": False,
}

_CLAIM_RECONSTRUCTION_SCHEMA = _output_schema(
    "curator-claim-reconstruction-v1",
    "curator-claim-reconstruction",
    ("claims", "complete", "self_verification_detected"),
    {
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _RECONSTRUCTED_CLAIM,
        },
        "complete": {"const": True},
        "self_verification_detected": {"const": False},
    },
)

_REPRODUCTION_SCHEMA = _output_schema(
    "curator-clean-boundary-reproduction-v1",
    "curator-clean-boundary-reproduction",
    (
        "sealed_check_refs",
        "reproduction_status",
        "commands_executed_by_playbook",
        "test_results_authorized",
        "fresh_workspace_required",
    ),
    {
        "sealed_check_refs": _NONEMPTY_REFS,
        "reproduction_status": {"const": "planned-not-executed"},
        "commands_executed_by_playbook": {"const": False},
        "test_results_authorized": {"const": False},
        "fresh_workspace_required": {"const": True},
    },
)

_ATTACK = {
    "type": "object",
    "required": ["attack_id", "category", "target_refs", "required_evidence_refs", "status"],
    "properties": {
        "attack_id": _ID,
        "category": {
            "type": "string",
            "enum": [
                "false-green",
                "self-verification",
                "forged-receipt",
                "stale-evidence",
                "point-in-time-leakage",
                "test-weakening",
                "source-license-gap",
                "unsupported-completion",
                "scope-substitution",
            ],
        },
        "target_refs": _NONEMPTY_REFS,
        "required_evidence_refs": _NONEMPTY_REFS,
        "status": {"const": "required"},
    },
    "additionalProperties": False,
}

_COUNTEREXAMPLE_SCHEMA = _output_schema(
    "curator-counterexample-search-v1",
    "curator-counterexample-search",
    ("attacks", "coverage_complete", "counterexamples_executed_by_playbook"),
    {
        "attacks": {
            "type": "array",
            "minItems": 9,
            "maxItems": 32,
            "items": _ATTACK,
        },
        "coverage_complete": {"const": True},
        "counterexamples_executed_by_playbook": {"const": False},
    },
)

_SECURITY_SCHEMA = _output_schema(
    "curator-security-privacy-review-v1",
    "curator-security-privacy-review",
    ("findings", "sast_status", "private_content_exposed", "security_approval_authorized"),
    {
        "findings": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _FINDING,
        },
        "sast_status": {"const": "not-evaluated"},
        "private_content_exposed": {"const": False},
        "security_approval_authorized": {"const": False},
    },
)

_SOURCE_REVIEW = {
    "type": "object",
    "required": [
        "source_id",
        "digest",
        "license_status",
        "completeness",
        "claim_refs",
        "admitted_for_material_claims",
    ],
    "properties": {
        "source_id": _ID,
        "digest": _DIGEST,
        "license_status": {"type": "string", "enum": ["admitted", "unknown", "quarantined"]},
        "completeness": {"type": "string", "enum": ["complete", "partial", "unavailable"]},
        "claim_refs": _NONEMPTY_REFS,
        "admitted_for_material_claims": {"type": "boolean"},
    },
    "additionalProperties": False,
}

_PROVENANCE_SCHEMA = _output_schema(
    "curator-provenance-license-review-v1",
    "curator-provenance-license-review",
    ("sources", "material_claims_fully_sourced", "license_gaps", "provenance_approval_authorized"),
    {
        "sources": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _SOURCE_REVIEW,
        },
        "material_claims_fully_sourced": {"const": True},
        "license_gaps": {"type": "array", "maxItems": 0, "items": _ID},
        "provenance_approval_authorized": {"const": False},
    },
)

_REGRESSION_ITEM = {
    "type": "object",
    "required": [
        "target_id",
        "path",
        "baseline_digest",
        "candidate_digest",
        "test_refs",
        "assertion_delta",
        "test_function_delta",
        "weakened",
    ],
    "properties": {
        "target_id": _ID,
        "path": _PATH,
        "baseline_digest": _DIGEST,
        "candidate_digest": _DIGEST,
        "test_refs": _NONEMPTY_REFS,
        "assertion_delta": {"type": "integer", "minimum": 0},
        "test_function_delta": {"type": "integer", "minimum": 0},
        "weakened": {"const": False},
    },
    "additionalProperties": False,
}

_REGRESSION_SCHEMA = _output_schema(
    "curator-regression-analysis-v1",
    "curator-regression-analysis",
    ("targets", "tests_weakened", "regression_clearance_authorized"),
    {
        "targets": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _REGRESSION_ITEM,
        },
        "tests_weakened": {"const": False},
        "regression_clearance_authorized": {"const": False},
    },
)

_EVIDENCE_REVIEW = {
    "type": "object",
    "required": [
        "evidence_id",
        "kind",
        "digest",
        "integrity_status",
        "stale",
        "producer_role",
        "receipt_fields_complete",
    ],
    "properties": {
        "evidence_id": _ID,
        "kind": _ID,
        "digest": _DIGEST,
        "integrity_status": {"const": "digest-verified"},
        "stale": {"const": False},
        "producer_role": _ID,
        "receipt_fields_complete": {"const": True},
    },
    "additionalProperties": False,
}

_ARTIFACT_SCHEMA = _output_schema(
    "curator-artifact-receipt-verification-v1",
    "curator-artifact-receipt-verification",
    (
        "evidence",
        "all_digests_verified",
        "all_receipt_fields_present",
        "artifacts_created_by_playbook",
        "verification_authorized",
    ),
    {
        "evidence": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _EVIDENCE_REVIEW,
        },
        "all_digests_verified": {"const": True},
        "all_receipt_fields_present": {"const": True},
        "artifacts_created_by_playbook": {"const": False},
        "verification_authorized": {"const": False},
    },
)

_ROLLBACK_SCHEMA = _output_schema(
    "curator-rollback-verification-v1",
    "curator-rollback-verification",
    (
        "rollback_verification_test_refs",
        "rollback_required",
        "rollback_executed_by_playbook",
        "rollback_verified_by_playbook",
        "rollback_authorized",
    ),
    {
        "rollback_verification_test_refs": _NONEMPTY_REFS,
        "rollback_required": {"const": True},
        "rollback_executed_by_playbook": {"const": False},
        "rollback_verified_by_playbook": {"const": False},
        "rollback_authorized": {"const": False},
    },
)

_RELEASE_SCHEMA = _output_schema(
    "curator-release-recommendation-v1",
    "curator-release-recommendation",
    (
        "structural_status",
        "recommendation",
        "requested_recommendation",
        "requested_recommendation_eligible",
        "reason",
        "release_ready",
        "release_authorized",
        "approval_authorized",
    ),
    {
        "structural_status": {"type": "string", "enum": ["pass", "fail", "quarantine"]},
        "recommendation": {"type": "string", "enum": ["defer", "reject", "quarantine"]},
        "requested_recommendation": {"type": "string", "enum": ["defer", "reject", "quarantine"]},
        "requested_recommendation_eligible": {"type": "boolean"},
        "reason": _TEXT,
        "release_ready": {"const": False},
        "release_authorized": {"const": False},
        "approval_authorized": {"const": False},
    },
)

_UNRESOLVED = {
    "type": "object",
    "required": ["issue_id", "category", "reason", "blocking", "required_evidence_refs"],
    "properties": {
        "issue_id": _ID,
        "category": _ID,
        "reason": _TEXT,
        "blocking": {"type": "boolean"},
        "required_evidence_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_DISSENT_SCHEMA = _output_schema(
    "curator-dissent-unresolved-evidence-v1",
    "curator-dissent-unresolved-evidence",
    ("unresolved", "dissent_preserved", "missing_evidence_is_permission"),
    {
        "unresolved": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _UNRESOLVED,
        },
        "dissent_preserved": {"const": True},
        "missing_evidence_is_permission": {"const": False},
    },
)

_AGENT_SCHEMA = _object(
    "curator-agent-successor-v1",
    (
        "record_type",
        "schema_version",
        "agent_id",
        "definition_id",
        "base_definition_id",
        "role_id",
        "version",
        "mission",
        "layers",
        "output_contract_refs",
        "effective_capabilities",
        "tool_refs",
        "activation",
        "authority",
        "public",
        "implementation_authorized",
        "execution_authorized",
        "test_result_authorized",
        "completion_authorized",
        "release_authorized",
        "approval_authorized",
        "promotion_authorized",
        "content_digest",
    ),
    {
        "record_type": {"const": "curator-agent-successor"},
        "schema_version": {"const": 1},
        "agent_id": {"const": AGENT_ID},
        "definition_id": {"const": DEFINITION_ID},
        "base_definition_id": {"const": BASE_DEFINITION_ID},
        "role_id": {"const": "curator"},
        "version": {"const": "2-shadow-1"},
        "mission": _TEXT,
        "layers": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": _LAYER,
        },
        "output_contract_refs": {
            "type": "array",
            "minItems": len(OUTPUT_FIELDS),
            "maxItems": len(OUTPUT_FIELDS),
            "uniqueItems": True,
            "items": _ID,
        },
        "effective_capabilities": {"type": "array", "maxItems": 0, "items": _ID},
        "tool_refs": {"type": "array", "maxItems": 0, "items": _ID},
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
        "implementation_authorized": {"const": False},
        "execution_authorized": {"const": False},
        "test_result_authorized": {"const": False},
        "completion_authorized": {"const": False},
        "release_authorized": {"const": False},
        "approval_authorized": {"const": False},
        "promotion_authorized": {"const": False},
        "content_digest": _DIGEST,
    },
)

_RESOURCE_AXIS = {
    "type": "object",
    "required": [
        "ceiling",
        "verification_reserve",
        "evidence_reserve",
        "rollback_reserve",
        "section_allocations",
    ],
    "properties": {
        "ceiling": {"type": ["integer", "null"], "minimum": 1},
        "verification_reserve": {"type": ["integer", "null"], "minimum": 1},
        "evidence_reserve": {"type": ["integer", "null"], "minimum": 1},
        "rollback_reserve": {"type": ["integer", "null"], "minimum": 1},
        "section_allocations": {
            "type": "object",
            "required": list(RESOURCE_SECTIONS),
            "properties": {
                section: {"type": ["integer", "null"], "minimum": 1}
                for section in RESOURCE_SECTIONS
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}
_RESOURCE_ACCOUNTING = {
    "type": "object",
    "required": ["accounting_status", "lease_status", "axes", "budget_authorized"],
    "properties": {
        "accounting_status": {"type": "string", "enum": ["known", "unknown"]},
        "lease_status": {"const": "not-issued"},
        "axes": {
            "type": "object",
            "required": list(RESOURCE_AXES),
            "properties": {axis: _RESOURCE_AXIS for axis in RESOURCE_AXES},
            "additionalProperties": False,
        },
        "budget_authorized": {"const": False},
    },
    "additionalProperties": False,
}

_ENVELOPE_SCHEMA = _object(
    "curator-verification-envelope-v1",
    (
        "record_type",
        "schema_version",
        "request_id",
        "objective_id",
        "tenant_id",
        "repository_id",
        "successor_digest",
        "request_digest",
        "request_snapshot",
        "outputs",
        "resource_accounting",
        "activation",
        "authority",
        "public",
        "verification_digest",
    ),
    {
        "record_type": {"const": "curator-verification-envelope"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "successor_digest": _DIGEST,
        "request_digest": _DIGEST,
        "request_snapshot": {"type": "object"},
        "outputs": {
            "type": "object",
            "required": list(OUTPUT_FIELDS),
            "properties": {
                field: {"type": "object"} for field in OUTPUT_FIELDS
            },
            "additionalProperties": False,
        },
        "resource_accounting": _RESOURCE_ACCOUNTING,
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
        "verification_digest": _DIGEST,
    },
)

CURATOR_SCHEMAS: Mapping[str, dict[str, Any]] = MappingProxyType(
    {
        "curator-agent-successor-v1": _AGENT_SCHEMA,
        "curator-verification-request-v1": _REQUEST_SCHEMA,
        "curator-verification-scope-v1": _VERIFICATION_SCOPE_SCHEMA,
        "curator-claim-reconstruction-v1": _CLAIM_RECONSTRUCTION_SCHEMA,
        "curator-clean-boundary-reproduction-v1": _REPRODUCTION_SCHEMA,
        "curator-counterexample-search-v1": _COUNTEREXAMPLE_SCHEMA,
        "curator-security-privacy-review-v1": _SECURITY_SCHEMA,
        "curator-provenance-license-review-v1": _PROVENANCE_SCHEMA,
        "curator-regression-analysis-v1": _REGRESSION_SCHEMA,
        "curator-artifact-receipt-verification-v1": _ARTIFACT_SCHEMA,
        "curator-rollback-verification-v1": _ROLLBACK_SCHEMA,
        "curator-release-recommendation-v1": _RELEASE_SCHEMA,
        "curator-dissent-unresolved-evidence-v1": _DISSENT_SCHEMA,
        "curator-verification-envelope-v1": _ENVELOPE_SCHEMA,
    }
)


def load_curator_schema(name: str) -> dict[str, Any]:
    if name not in CURATOR_SCHEMA_NAMES:
        raise KeyError(f"unknown Curator schema: {name}")
    return deepcopy(CURATOR_SCHEMAS[name])


def _validate_seal(document: Mapping[str, Any], field: str, issues: list[str]) -> None:
    body = {key: deepcopy(value) for key, value in document.items() if key != field}
    if document.get(field) != digest(body):
        issues.append(f"{field} does not seal the canonical document")


def _validate_resource_accounting(document: Mapping[str, Any], issues: list[str]) -> None:
    status = document.get("accounting_status")
    axes = document.get("axes")
    if not isinstance(axes, Mapping):
        return
    for axis in RESOURCE_AXES:
        allocation = axes.get(axis)
        if not isinstance(allocation, Mapping):
            continue
        sections = allocation.get("section_allocations")
        if not isinstance(sections, Mapping):
            continue
        values = [
            allocation.get("ceiling"),
            allocation.get("verification_reserve"),
            allocation.get("evidence_reserve"),
            allocation.get("rollback_reserve"),
            *[sections.get(section) for section in RESOURCE_SECTIONS],
        ]
        if status == "unknown":
            if any(value is not None for value in values):
                issues.append(f"resource axis {axis} manufactures values under unknown accounting")
            continue
        if status != "known":
            continue
        if not all(type(value) is int and value > 0 for value in values):
            issues.append(f"resource axis {axis} does not fund reserves and every section")
            continue
        ceiling = cast(int, allocation.get("ceiling"))
        reserve_values = [
            cast(int, allocation.get("verification_reserve")),
            cast(int, allocation.get("evidence_reserve")),
            cast(int, allocation.get("rollback_reserve")),
        ]
        section_values = [cast(int, sections[section]) for section in RESOURCE_SECTIONS]
        if sum(reserve_values) + sum(section_values) != ceiling:
            issues.append(f"resource axis {axis} does not reconcile to its ceiling")


@lru_cache(maxsize=32)
def _canonical_envelope_bytes(request_json: str) -> bytes:
    from .curator_playbook import compile_curator_verification

    request = json.loads(request_json)
    return canonical_bytes(compile_curator_verification(request))


def validate_curator(
    name: str,
    document: Any,
    *,
    enforce_reviewed_successor: bool = True,
    enforce_canonical_envelope: bool = True,
) -> FoundationValidation:
    try:
        schema = load_curator_schema(name)
    except KeyError as error:
        return FoundationValidation(False, (str(error),))
    result = validate_document_against_schema(document, schema)
    issues = list(result.issues)
    if not isinstance(document, Mapping):
        return FoundationValidation(False, tuple(issues))
    try:
        reject_private_content(document)
    except ValueError as error:
        issues.append(str(error))

    if name == "curator-agent-successor-v1":
        _validate_seal(document, "content_digest", issues)
        if enforce_reviewed_successor and document.get("content_digest") != EXPECTED_SUCCESSOR_DIGEST:
            issues.append("Curator successor differs from the reviewed digest")
        layers = document.get("layers")
        if isinstance(layers, list):
            observed_ids = tuple(
                item.get("layer_id") for item in layers if isinstance(item, Mapping)
            )
            observed_kinds = tuple(
                item.get("kind") for item in layers if isinstance(item, Mapping)
            )
            if observed_ids != LAYER_IDS:
                issues.append("Curator successor layer identities or order drifted")
            if observed_kinds != LAYER_KINDS:
                issues.append("Curator successor layer kinds or order drifted")
            for index, item in enumerate(layers, start=1):
                if not isinstance(item, Mapping):
                    continue
                if item.get("position") != index:
                    issues.append("Curator successor layer positions drifted")
                body = {key: value for key, value in item.items() if key != "digest"}
                if item.get("digest") != digest(body):
                    issues.append(f"Curator successor layer {index} digest drifted")
        expected_contracts = [OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS]
        if document.get("output_contract_refs") != expected_contracts:
            issues.append("Curator output contract order drifted")
        for field in (
            "implementation_authorized",
            "execution_authorized",
            "test_result_authorized",
            "completion_authorized",
            "release_authorized",
            "approval_authorized",
            "promotion_authorized",
        ):
            if document.get(field) is not False:
                issues.append(f"Curator successor escalated {field}")
    elif name.endswith("-v1") and name not in {
        "curator-verification-request-v1",
        "curator-verification-envelope-v1",
    }:
        _validate_seal(document, "output_digest", issues)
    elif name == "curator-verification-envelope-v1":
        _validate_seal(document, "verification_digest", issues)
        snapshot = document.get("request_snapshot")
        if isinstance(snapshot, Mapping):
            if document.get("request_digest") != digest(snapshot):
                issues.append("request snapshot does not match request digest")
            for field in ("request_id", "objective_id", "tenant_id", "repository_id"):
                if document.get(field) != snapshot.get(field):
                    issues.append(f"envelope {field} differs from request snapshot")
        if document.get("successor_digest") != EXPECTED_SUCCESSOR_DIGEST:
            issues.append("envelope successor digest differs from reviewed Curator candidate")
        resource = document.get("resource_accounting")
        if isinstance(resource, Mapping):
            _validate_resource_accounting(resource, issues)
        outputs = document.get("outputs")
        if isinstance(outputs, Mapping):
            if tuple(outputs) != OUTPUT_FIELDS:
                issues.append("typed output order or membership drifted")
            expected_claim_refs: list[Any] = []
            expected_acceptance_refs: list[Any] = []
            expected_evidence_refs: list[Any] = []
            builder_definition_id: Any = None
            builder_successor_digest: Any = None
            builder_implementation_digest: Any = None
            if isinstance(snapshot, Mapping):
                claims = snapshot.get("claims")
                acceptance = snapshot.get("acceptance_criteria")
                evidence = snapshot.get("observed_evidence")
                builder = snapshot.get("builder_envelope")
                if isinstance(claims, list):
                    expected_claim_refs = sorted(
                        item.get("claim_id") for item in claims if isinstance(item, Mapping)
                    )
                if isinstance(acceptance, list):
                    expected_acceptance_refs = sorted(
                        item.get("acceptance_id") for item in acceptance if isinstance(item, Mapping)
                    )
                if isinstance(evidence, list):
                    expected_evidence_refs = sorted(
                        item.get("evidence_id") for item in evidence if isinstance(item, Mapping)
                    )
                if isinstance(builder, Mapping):
                    builder_successor_digest = builder.get("successor_digest")
                    builder_implementation_digest = builder.get("implementation_digest")
                    builder_snapshot = builder.get("request_snapshot")
                    if isinstance(builder_snapshot, Mapping):
                        builder_definition_id = DEFINITION_ID.replace("curator", "builder")
            expected_budget_state = (
                resource.get("accounting_status") if isinstance(resource, Mapping) else None
            )
            for field in OUTPUT_FIELDS:
                output = outputs.get(field)
                if not isinstance(output, Mapping):
                    continue
                validation = validate_curator(
                    OUTPUT_SCHEMA_BY_FIELD[field],
                    output,
                    enforce_reviewed_successor=enforce_reviewed_successor,
                    enforce_canonical_envelope=False,
                )
                issues.extend(f"outputs.{field}: {issue}" for issue in validation.issues)
                expected_scope = {
                    "request_id": document.get("request_id"),
                    "request_digest": document.get("request_digest"),
                    "objective_id": document.get("objective_id"),
                    "tenant_id": document.get("tenant_id"),
                    "repository_id": document.get("repository_id"),
                    "curator_definition_id": DEFINITION_ID,
                    "curator_version": "2-shadow-1",
                    "builder_definition_id": builder_definition_id,
                    "builder_successor_digest": builder_successor_digest,
                    "builder_implementation_digest": builder_implementation_digest,
                    "base_commit": snapshot.get("base_commit") if isinstance(snapshot, Mapping) else None,
                    "base_tree": snapshot.get("base_tree") if isinstance(snapshot, Mapping) else None,
                    "subject_commit": snapshot.get("subject_commit") if isinstance(snapshot, Mapping) else None,
                    "subject_tree": snapshot.get("subject_tree") if isinstance(snapshot, Mapping) else None,
                    "budget_state": expected_budget_state,
                    "authenticated_distinct_actors": False,
                    "same_assistant_performed_procedural_passes": True,
                    "independence_claimed": False,
                }
                for scope_field, expected in expected_scope.items():
                    if output.get(scope_field) != expected:
                        issues.append(f"outputs.{field}.{scope_field} differs from envelope")
                if output.get("claim_refs") != expected_claim_refs:
                    issues.append(f"outputs.{field}.claim_refs is not complete")
                if output.get("acceptance_refs") != expected_acceptance_refs:
                    issues.append(f"outputs.{field}.acceptance_refs is not complete")
                if output.get("evidence_refs") != expected_evidence_refs:
                    issues.append(f"outputs.{field}.evidence_refs is not complete")
        if enforce_canonical_envelope and isinstance(snapshot, Mapping):
            try:
                request_json = json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                expected = _canonical_envelope_bytes(request_json)
            except (TypeError, ValueError, RuntimeError) as error:
                issues.append(
                    "canonical verification reconstruction failed: "
                    f"{type(error).__name__}: {error}"
                )
            else:
                if canonical_bytes(document) != expected:
                    issues.append("verification envelope differs from canonical request-bound result")

    return FoundationValidation(not issues, tuple(dict.fromkeys(issues)))


def validate_curator_catalog() -> FoundationValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in CURATOR_SCHEMA_NAMES:
        schema = load_curator_schema(name)
        identifier = schema.get("$id")
        if not isinstance(identifier, str) or not identifier:
            issues.append(f"{name}: missing $id")
        elif identifier in identifiers:
            issues.append(f"{name}: duplicate $id")
        else:
            identifiers.add(identifier)
        if schema.get("$schema") != DIALECT:
            issues.append(f"{name}: wrong dialect")
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            issues.append(f"{name}: root must be a fail-closed object")
    return FoundationValidation(not issues, tuple(issues))
