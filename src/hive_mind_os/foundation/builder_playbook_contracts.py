from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping, cast

from .canonical import canonical_bytes, digest
from .contracts import FoundationValidation, validate_document_against_schema

DIALECT = "https://json-schema.org/draft/2020-12/schema"
BUILDER_SCHEMA_NAMES = (
    "builder-agent-successor-v1",
    "builder-implementation-request-v1",
    "builder-requirement-trace-v1",
    "builder-implementation-scope-v1",
    "builder-change-plan-v1",
    "builder-workspace-plan-v1",
    "builder-dependency-plan-v1",
    "builder-test-plan-v1",
    "builder-execution-evidence-plan-v1",
    "builder-rollback-plan-v1",
    "builder-artifact-manifest-v1",
    "builder-curator-handoff-v1",
    "builder-implementation-envelope-v1",
)

AGENT_ID = "hive-agent:builder:v2-shadow-1"
DEFINITION_ID = "hive-agent-definition:builder:v2-shadow-1"
BASE_DEFINITION_ID = "hive-agent-definition:builder:v2-candidate"
# Replaced after the deterministic successor is first compiled.
EXPECTED_SUCCESSOR_DIGEST = "sha256:ac69c53464f7e24022b7c29d12889d0f80190d86e3d5650f00a15ae57ecfdccd"

OUTPUT_FIELDS = (
    "requirement_trace",
    "implementation_scope",
    "change_plan",
    "workspace_plan",
    "dependency_plan",
    "test_plan",
    "execution_evidence_plan",
    "rollback_plan",
    "artifact_manifest",
    "curator_handoff",
)
OUTPUT_SCHEMA_BY_FIELD: Mapping[str, str] = MappingProxyType(
    {
        "requirement_trace": "builder-requirement-trace-v1",
        "implementation_scope": "builder-implementation-scope-v1",
        "change_plan": "builder-change-plan-v1",
        "workspace_plan": "builder-workspace-plan-v1",
        "dependency_plan": "builder-dependency-plan-v1",
        "test_plan": "builder-test-plan-v1",
        "execution_evidence_plan": "builder-execution-evidence-plan-v1",
        "rollback_plan": "builder-rollback-plan-v1",
        "artifact_manifest": "builder-artifact-manifest-v1",
        "curator_handoff": "builder-curator-handoff-v1",
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
RESOURCE_SECTIONS = (
    "requirements",
    "scope",
    "changes",
    "workspace",
    "dependencies",
    "tests",
    "evidence",
    "rollback",
    "artifacts",
    "handoff",
)
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
    "generation-zero:builder",
    "builder:deep-playbook",
    "skill.builder",
    "builder:implementation-request",
    "builder:typed-outputs",
    "builder:phase5c-governance",
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
_PATH_LIST = {
    "type": "array",
    "minItems": 1,
    "maxItems": 128,
    "uniqueItems": True,
    "items": _PATH,
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

_ACCEPTANCE = {
    "type": "object",
    "required": ["acceptance_id", "statement"],
    "properties": {"acceptance_id": _ID, "statement": _TEXT},
    "additionalProperties": False,
}

_REQUIREMENT = {
    "type": "object",
    "required": [
        "requirement_id",
        "statement",
        "disposition",
        "source_claim_refs",
        "acceptance_refs",
        "architecture_refs",
        "evidence_refs",
    ],
    "properties": {
        "requirement_id": _ID,
        "statement": _TEXT,
        "disposition": {"type": "string", "enum": ["adopt", "adapt"]},
        "source_claim_refs": _NONEMPTY_REFS,
        "acceptance_refs": _NONEMPTY_REFS,
        "architecture_refs": _NONEMPTY_REFS,
        "evidence_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_ARCHITECTURE_DECISION = {
    "type": "object",
    "required": [
        "decision_id",
        "status",
        "design_digest",
        "subject_commit",
        "subject_tree",
        "architecture_refs",
        "unresolved_blocking_contradiction_refs",
    ],
    "properties": {
        "decision_id": _ID,
        "status": {"type": "string", "enum": ["adopted", "adapted"]},
        "design_digest": _DIGEST,
        "subject_commit": _COMMIT,
        "subject_tree": _COMMIT,
        "architecture_refs": _NONEMPTY_REFS,
        "unresolved_blocking_contradiction_refs": {
            "type": "array",
            "maxItems": 0,
            "items": _ID,
        },
    },
    "additionalProperties": False,
}

_SCOPE = {
    "type": "object",
    "required": [
        "worktree_id",
        "subject_commit",
        "subject_tree",
        "allowed_paths",
        "denied_paths",
        "max_files",
        "max_dependency_changes",
    ],
    "properties": {
        "worktree_id": _ID,
        "subject_commit": _COMMIT,
        "subject_tree": _COMMIT,
        "allowed_paths": _PATH_LIST,
        "denied_paths": {
            "type": "array",
            "maxItems": 128,
            "uniqueItems": True,
            "items": _PATH,
        },
        "max_files": {"type": "integer", "minimum": 1, "maximum": 256},
        "max_dependency_changes": {"type": "integer", "minimum": 0, "maximum": 32},
    },
    "additionalProperties": False,
}

_CHANGE = {
    "type": "object",
    "required": [
        "change_id",
        "path",
        "operation",
        "rationale",
        "requirement_refs",
        "acceptance_refs",
        "architecture_refs",
        "dependency_refs",
    ],
    "properties": {
        "change_id": _ID,
        "path": _PATH,
        "operation": {"type": "string", "enum": ["add", "modify", "delete"]},
        "rationale": _TEXT,
        "requirement_refs": _NONEMPTY_REFS,
        "acceptance_refs": _NONEMPTY_REFS,
        "architecture_refs": _NONEMPTY_REFS,
        "dependency_refs": _REF_LIST,
    },
    "additionalProperties": False,
}

_DEPENDENCY = {
    "type": "object",
    "required": [
        "dependency_id",
        "name",
        "ecosystem",
        "current_version",
        "proposed_version",
        "source_ref",
        "license_id",
        "status",
        "change_refs",
        "license_obligation_refs",
    ],
    "properties": {
        "dependency_id": _ID,
        "name": _ID,
        "ecosystem": _ID,
        "current_version": {"type": ["string", "null"], "maxLength": 256},
        "proposed_version": _ID,
        "source_ref": _ID,
        "license_id": _ID,
        "status": {"const": "known-admitted"},
        "change_refs": _NONEMPTY_REFS,
        "license_obligation_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_TEST = {
    "type": "object",
    "required": [
        "test_id",
        "kind",
        "command",
        "expected_before",
        "expected_after",
        "requirement_refs",
        "acceptance_refs",
        "change_refs",
        "hostile_case",
        "test_weakening",
    ],
    "properties": {
        "test_id": _ID,
        "kind": {
            "type": "string",
            "enum": ["unit", "contract", "integration", "security", "package", "recovery"],
        },
        "command": _TEXT,
        "expected_before": {"type": "string", "enum": ["fail", "not-applicable"]},
        "expected_after": {"const": "pass"},
        "requirement_refs": _NONEMPTY_REFS,
        "acceptance_refs": _NONEMPTY_REFS,
        "change_refs": _NONEMPTY_REFS,
        "hostile_case": {"type": "boolean"},
        "test_weakening": {"const": False},
    },
    "additionalProperties": False,
}

_EVIDENCE_ITEM = {
    "type": "object",
    "required": [
        "evidence_id",
        "kind",
        "change_refs",
        "test_refs",
        "required_receipt_fields",
    ],
    "properties": {
        "evidence_id": _ID,
        "kind": {
            "type": "string",
            "enum": [
                "failure-before",
                "pass-after",
                "command",
                "diff",
                "artifact",
                "security",
                "license",
                "rollback",
                "checkpoint",
            ],
        },
        "change_refs": _REF_LIST,
        "test_refs": _REF_LIST,
        "required_receipt_fields": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_CHECKPOINT = {
    "type": "object",
    "required": [
        "checkpoint_id",
        "after_change_refs",
        "restart_procedure",
        "evidence_refs",
    ],
    "properties": {
        "checkpoint_id": _ID,
        "after_change_refs": _NONEMPTY_REFS,
        "restart_procedure": _TEXT,
        "evidence_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_ROLLBACK_STEP = {
    "type": "object",
    "required": [
        "rollback_id",
        "change_refs",
        "inverse_operation",
        "checkpoint_ref",
        "verification_test_refs",
        "evidence_refs",
    ],
    "properties": {
        "rollback_id": _ID,
        "change_refs": _NONEMPTY_REFS,
        "inverse_operation": {"type": "string", "enum": ["add", "modify", "delete"]},
        "checkpoint_ref": _ID,
        "verification_test_refs": _NONEMPTY_REFS,
        "evidence_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_ARTIFACT = {
    "type": "object",
    "required": [
        "artifact_id",
        "kind",
        "path",
        "change_refs",
        "test_refs",
        "digest_required",
        "receipt_required",
    ],
    "properties": {
        "artifact_id": _ID,
        "kind": {
            "type": "string",
            "enum": ["source", "test", "manifest", "receipt", "package", "documentation"],
        },
        "path": _PATH,
        "change_refs": _REF_LIST,
        "test_refs": _REF_LIST,
        "digest_required": {"const": True},
        "receipt_required": {"const": True},
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
    "required": ["code_executed", "tests_passed", "completion_established"],
    "properties": {
        "code_executed": {"const": False},
        "tests_passed": {"const": False},
        "completion_established": {"const": False},
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
        "promotion_authorized": {"const": False},
    },
    "additionalProperties": False,
}

_REQUEST_SCHEMA = _object(
    "builder-implementation-request-v1",
    (
        "record_type",
        "schema_version",
        "request_id",
        "objective_id",
        "tenant_id",
        "repository_id",
        "objective",
        "objective_state",
        "constraints",
        "acceptance_criteria",
        "adjudicated_requirements",
        "architecture_decision",
        "scope",
        "changes",
        "dependencies",
        "tests",
        "evidence_plan",
        "checkpoints",
        "rollback_steps",
        "artifacts",
        "evidence_refs",
        "rollback_refs",
        "budgets",
        "checkpoint_reserve_ppm",
        "evidence_reserve_ppm",
        "rollback_reserve_ppm",
        "actors",
        "prior_fingerprints",
        "requested_next_role",
        "caller_claims",
    ),
    {
        "record_type": {"const": "builder-implementation-request"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "objective": _TEXT,
        "objective_state": {"const": "ready"},
        "constraints": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "uniqueItems": True,
            "items": _TEXT,
        },
        "acceptance_criteria": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _ACCEPTANCE,
        },
        "adjudicated_requirements": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _REQUIREMENT,
        },
        "architecture_decision": _ARCHITECTURE_DECISION,
        "scope": _SCOPE,
        "changes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _CHANGE,
        },
        "dependencies": {
            "type": "array",
            "maxItems": 32,
            "items": _DEPENDENCY,
        },
        "tests": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _TEST,
        },
        "evidence_plan": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _EVIDENCE_ITEM,
        },
        "checkpoints": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _CHECKPOINT,
        },
        "rollback_steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _ROLLBACK_STEP,
        },
        "artifacts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _ARTIFACT,
        },
        "evidence_refs": _NONEMPTY_REFS,
        "rollback_refs": _NONEMPTY_REFS,
        "budgets": _BUDGETS,
        "checkpoint_reserve_ppm": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 999999,
        },
        "evidence_reserve_ppm": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 999999,
        },
        "rollback_reserve_ppm": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 999999,
        },
        "actors": {
            "type": "array",
            "minItems": 10,
            "maxItems": 10,
            "items": _ACTOR,
        },
        "prior_fingerprints": {
            "type": "array",
            "maxItems": 32,
            "uniqueItems": True,
            "items": _DIGEST,
        },
        "requested_next_role": {"type": "string", "enum": ["curator", "steward"]},
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
    "builder_definition_id",
    "builder_version",
    "architecture_decision_id",
    "design_digest",
    "subject_commit",
    "subject_tree",
    "requirement_refs",
    "acceptance_refs",
    "authority_state",
    "budget_state",
    "evidence_refs",
    "rollback_refs",
    "output_digest",
)
_COMMON_OUTPUT_PROPERTIES = {
    "request_id": _ID,
    "request_digest": _DIGEST,
    "objective_id": _ID,
    "tenant_id": _ID,
    "repository_id": _ID,
    "builder_definition_id": {"const": DEFINITION_ID},
    "builder_version": {"const": "2-shadow-1"},
    "architecture_decision_id": _ID,
    "design_digest": _DIGEST,
    "subject_commit": _COMMIT,
    "subject_tree": _COMMIT,
    "requirement_refs": _NONEMPTY_REFS,
    "acceptance_refs": _NONEMPTY_REFS,
    "authority_state": _AUTHORITY_STATE,
    "budget_state": {"type": "string", "enum": ["known", "unknown"]},
    "evidence_refs": _NONEMPTY_REFS,
    "rollback_refs": _NONEMPTY_REFS,
    "output_digest": _DIGEST,
}


def _output_schema(
    name: str,
    record_type: str,
    required: tuple[str, ...],
    properties: dict[str, Any],
) -> dict[str, Any]:
    return _object(
        name,
        (*_COMMON_OUTPUT_REQUIRED, *required),
        {
            "record_type": {"const": record_type},
            "schema_version": {"const": 1},
            **_COMMON_OUTPUT_PROPERTIES,
            **properties,
        },
    )

_TRACE_ITEM = {
    "type": "object",
    "required": [
        "requirement_id",
        "source_claim_refs",
        "acceptance_refs",
        "architecture_refs",
        "change_refs",
        "test_refs",
        "evidence_refs",
    ],
    "properties": {
        "requirement_id": _ID,
        "source_claim_refs": _NONEMPTY_REFS,
        "acceptance_refs": _NONEMPTY_REFS,
        "architecture_refs": _NONEMPTY_REFS,
        "change_refs": _NONEMPTY_REFS,
        "test_refs": _NONEMPTY_REFS,
        "evidence_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_REQUIREMENT_TRACE_SCHEMA = _output_schema(
    "builder-requirement-trace-v1",
    "builder-requirement-trace",
    ("traces", "complete", "traceability_authorized"),
    {
        "traces": {"type": "array", "minItems": 1, "maxItems": 64, "items": _TRACE_ITEM},
        "complete": {"const": True},
        "traceability_authorized": {"const": False},
    },
)

_IMPLEMENTATION_SCOPE_SCHEMA = _output_schema(
    "builder-implementation-scope-v1",
    "builder-implementation-scope",
    (
        "worktree_id",
        "allowed_paths",
        "denied_paths",
        "max_files",
        "change_refs",
        "outside_scope_refs",
        "bounded",
        "overwrite_unrelated_work",
        "implementation_authorized",
    ),
    {
        "worktree_id": _ID,
        "allowed_paths": _PATH_LIST,
        "denied_paths": {"type": "array", "maxItems": 128, "uniqueItems": True, "items": _PATH},
        "max_files": {"type": "integer", "minimum": 1, "maximum": 256},
        "change_refs": _NONEMPTY_REFS,
        "outside_scope_refs": {"type": "array", "maxItems": 0, "items": _ID},
        "bounded": {"const": True},
        "overwrite_unrelated_work": {"const": False},
        "implementation_authorized": {"const": False},
    },
)

_ORDERED_CHANGE = {
    "type": "object",
    "required": [
        "sequence",
        "change_id",
        "path",
        "operation",
        "requirement_refs",
        "acceptance_refs",
        "architecture_refs",
        "dependency_refs",
        "test_refs",
        "rollback_ref",
        "artifact_refs",
    ],
    "properties": {
        "sequence": {"type": "integer", "minimum": 1, "maximum": 256},
        "change_id": _ID,
        "path": _PATH,
        "operation": {"type": "string", "enum": ["add", "modify", "delete"]},
        "requirement_refs": _NONEMPTY_REFS,
        "acceptance_refs": _NONEMPTY_REFS,
        "architecture_refs": _NONEMPTY_REFS,
        "dependency_refs": _REF_LIST,
        "test_refs": _NONEMPTY_REFS,
        "rollback_ref": _ID,
        "artifact_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_CHANGE_PLAN_SCHEMA = _output_schema(
    "builder-change-plan-v1",
    "builder-change-plan",
    ("ordered_changes", "change_count", "execution_authorized", "completion_claimed"),
    {
        "ordered_changes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _ORDERED_CHANGE,
        },
        "change_count": {"type": "integer", "minimum": 1, "maximum": 256},
        "execution_authorized": {"const": False},
        "completion_claimed": {"const": False},
    },
)

_RECOVERY_ENTRY = {
    "type": "object",
    "required": ["checkpoint_id", "after_change_refs", "restart_procedure", "evidence_refs"],
    "properties": {
        "checkpoint_id": _ID,
        "after_change_refs": _NONEMPTY_REFS,
        "restart_procedure": _TEXT,
        "evidence_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_WORKSPACE_PLAN_SCHEMA = _output_schema(
    "builder-workspace-plan-v1",
    "builder-workspace-plan",
    (
        "workspace_id",
        "isolation",
        "checkpoint_refs",
        "interruption_recovery",
        "clean_start_required",
        "execution_authorized",
    ),
    {
        "workspace_id": _ID,
        "isolation": {"const": "separate-worktree-proposed"},
        "checkpoint_refs": _NONEMPTY_REFS,
        "interruption_recovery": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _RECOVERY_ENTRY,
        },
        "clean_start_required": {"const": True},
        "execution_authorized": {"const": False},
    },
)

_LICENSE_OBLIGATION = {
    "type": "object",
    "required": ["dependency_id", "license_id", "obligation_refs"],
    "properties": {
        "dependency_id": _ID,
        "license_id": _ID,
        "obligation_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_DEPENDENCY_PLAN_SCHEMA = _output_schema(
    "builder-dependency-plan-v1",
    "builder-dependency-plan",
    (
        "dependencies",
        "license_obligations",
        "unknown_dependency_refs",
        "quarantined_dependency_refs",
        "supply_chain_review_required",
        "dependency_change_authorized",
    ),
    {
        "dependencies": {"type": "array", "maxItems": 32, "items": _DEPENDENCY},
        "license_obligations": {
            "type": "array",
            "maxItems": 32,
            "items": _LICENSE_OBLIGATION,
        },
        "unknown_dependency_refs": {"type": "array", "maxItems": 0, "items": _ID},
        "quarantined_dependency_refs": {"type": "array", "maxItems": 0, "items": _ID},
        "supply_chain_review_required": {"const": True},
        "dependency_change_authorized": {"const": False},
    },
)

_TEST_PLAN_SCHEMA = _output_schema(
    "builder-test-plan-v1",
    "builder-test-plan",
    (
        "tests",
        "failure_before_required",
        "pass_after_required",
        "tests_executed",
        "test_results_authorized",
        "test_weakening_allowed",
    ),
    {
        "tests": {"type": "array", "minItems": 1, "maxItems": 256, "items": _TEST},
        "failure_before_required": {"const": True},
        "pass_after_required": {"const": True},
        "tests_executed": {"const": False},
        "test_results_authorized": {"const": False},
        "test_weakening_allowed": {"const": False},
    },
)

_EXECUTION_EVIDENCE_SCHEMA = _output_schema(
    "builder-execution-evidence-plan-v1",
    "builder-execution-evidence-plan",
    (
        "evidence_items",
        "required_receipt_fields",
        "code_executed_claim_accepted",
        "tests_passed_claim_accepted",
        "completion_claim_accepted",
        "evidence_sealed",
    ),
    {
        "evidence_items": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _EVIDENCE_ITEM,
        },
        "required_receipt_fields": _NONEMPTY_REFS,
        "code_executed_claim_accepted": {"const": False},
        "tests_passed_claim_accepted": {"const": False},
        "completion_claim_accepted": {"const": False},
        "evidence_sealed": {"const": False},
    },
)

_ROLLBACK_PLAN_SCHEMA = _output_schema(
    "builder-rollback-plan-v1",
    "builder-rollback-plan",
    (
        "steps",
        "checkpoints",
        "full_change_coverage",
        "rollback_required",
        "rollback_executed",
        "rollback_authorized",
    ),
    {
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _ROLLBACK_STEP,
        },
        "checkpoints": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": _CHECKPOINT,
        },
        "full_change_coverage": {"const": True},
        "rollback_required": {"const": True},
        "rollback_executed": {"const": False},
        "rollback_authorized": {"const": False},
    },
)

_ARTIFACT_MANIFEST_SCHEMA = _output_schema(
    "builder-artifact-manifest-v1",
    "builder-artifact-manifest",
    (
        "artifacts",
        "every_change_covered",
        "every_test_covered",
        "digests_required",
        "artifacts_created",
    ),
    {
        "artifacts": {"type": "array", "minItems": 1, "maxItems": 256, "items": _ARTIFACT},
        "every_change_covered": {"const": True},
        "every_test_covered": {"const": True},
        "digests_required": {"const": True},
        "artifacts_created": {"const": False},
    },
)

_CURATOR_HANDOFF_SCHEMA = _output_schema(
    "builder-curator-handoff-v1",
    "builder-curator-handoff",
    (
        "next_role",
        "requested_next_role",
        "requested_role_eligible",
        "reason",
        "required_refs",
        "independent_reconstruction_required",
        "authenticated_distinct_actors",
        "same_assistant_performed_procedural_passes",
        "independence_claimed",
        "implementation_authorized",
        "completion_authorized",
        "promotion_authorized",
        "activation_authorized",
    ),
    {
        "next_role": {"const": "curator"},
        "requested_next_role": {"type": "string", "enum": ["curator", "steward"]},
        "requested_role_eligible": {"type": "boolean"},
        "reason": {"const": "independent-clean-boundary-reconstruction-required"},
        "required_refs": _NONEMPTY_REFS,
        "independent_reconstruction_required": {"const": True},
        "authenticated_distinct_actors": {"const": False},
        "same_assistant_performed_procedural_passes": {"const": True},
        "independence_claimed": {"const": False},
        "implementation_authorized": {"const": False},
        "completion_authorized": {"const": False},
        "promotion_authorized": {"const": False},
        "activation_authorized": {"const": False},
    },
)

_RESOURCE_ALLOCATION = {
    "type": "object",
    "required": [
        "ceiling",
        "checkpoint_reserve",
        "evidence_reserve",
        "rollback_reserve",
        "section_allocations",
    ],
    "properties": {
        "ceiling": {"type": ["integer", "null"], "minimum": 1, "maximum": 10**15},
        "checkpoint_reserve": {"type": ["integer", "null"], "minimum": 1, "maximum": 10**15},
        "evidence_reserve": {"type": ["integer", "null"], "minimum": 1, "maximum": 10**15},
        "rollback_reserve": {"type": ["integer", "null"], "minimum": 1, "maximum": 10**15},
        "section_allocations": {
            "type": "object",
            "required": list(RESOURCE_SECTIONS),
            "properties": {
                section: {"type": ["integer", "null"], "minimum": 1, "maximum": 10**15}
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
            "properties": {axis: _RESOURCE_ALLOCATION for axis in RESOURCE_AXES},
            "additionalProperties": False,
        },
        "budget_authorized": {"const": False},
    },
    "additionalProperties": False,
}

_OUTPUTS_OBJECT = {
    "type": "object",
    "required": list(OUTPUT_FIELDS),
    "properties": {
        "requirement_trace": _REQUIREMENT_TRACE_SCHEMA,
        "implementation_scope": _IMPLEMENTATION_SCOPE_SCHEMA,
        "change_plan": _CHANGE_PLAN_SCHEMA,
        "workspace_plan": _WORKSPACE_PLAN_SCHEMA,
        "dependency_plan": _DEPENDENCY_PLAN_SCHEMA,
        "test_plan": _TEST_PLAN_SCHEMA,
        "execution_evidence_plan": _EXECUTION_EVIDENCE_SCHEMA,
        "rollback_plan": _ROLLBACK_PLAN_SCHEMA,
        "artifact_manifest": _ARTIFACT_MANIFEST_SCHEMA,
        "curator_handoff": _CURATOR_HANDOFF_SCHEMA,
    },
    "additionalProperties": False,
}

_SUCCESSOR_SCHEMA = _object(
    "builder-agent-successor-v1",
    (
        "record_type",
        "schema_version",
        "agent_id",
        "definition_id",
        "role_id",
        "version",
        "status",
        "lineage_relation",
        "base_definition_ref",
        "rollback_ref",
        "layers",
        "requested_capabilities",
        "effective_capabilities",
        "unsupported_capabilities",
        "tool_refs",
        "input_contract_refs",
        "output_contract_refs",
        "workflow_refs",
        "budgets",
        "playbook",
        "constitutional_lifecycle",
        "activation",
        "authority",
        "public",
        "implementation_authorized",
        "execution_authorized",
        "test_result_authorized",
        "completion_authorized",
        "promotion_authorized",
        "content_digest",
    ),
    {
        "record_type": {"const": "builder-agent-successor"},
        "schema_version": {"const": 1},
        "agent_id": {"const": AGENT_ID},
        "definition_id": {"const": DEFINITION_ID},
        "role_id": {"const": "builder"},
        "version": {"const": "2-shadow-1"},
        "status": {"const": "candidate"},
        "lineage_relation": {"const": "extends-inert"},
        "base_definition_ref": {"const": BASE_DEFINITION_ID},
        "rollback_ref": {"const": BASE_DEFINITION_ID},
        "layers": {"type": "array", "minItems": 8, "maxItems": 8, "items": _LAYER},
        "requested_capabilities": _REF_LIST,
        "effective_capabilities": {"type": "array", "maxItems": 0, "items": _ID},
        "unsupported_capabilities": _REF_LIST,
        "tool_refs": {"type": "array", "maxItems": 0, "items": _ID},
        "input_contract_refs": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {"const": "builder-implementation-request-v1"},
        },
        "output_contract_refs": {
            "type": "array",
            "minItems": 10,
            "maxItems": 10,
            "items": _ID,
        },
        "workflow_refs": _NONEMPTY_REFS,
        "budgets": {
            "type": "object",
            "required": [
                "max_requirements",
                "max_changes",
                "max_dependencies",
                "max_tests",
                "max_evidence_items",
                "max_checkpoints",
                "max_rollback_steps",
                "max_artifacts",
            ],
            "properties": {
                "max_requirements": {"const": 64},
                "max_changes": {"const": 256},
                "max_dependencies": {"const": 32},
                "max_tests": {"const": 256},
                "max_evidence_items": {"const": 256},
                "max_checkpoints": {"const": 64},
                "max_rollback_steps": {"const": 256},
                "max_artifacts": {"const": 256},
            },
            "additionalProperties": False,
        },
        "playbook": {
            "type": "object",
            "required": ["responsibilities", "typed_outputs", "quality_gates", "stop_conditions", "prohibited_actions"],
            "properties": {
                "responsibilities": _NONEMPTY_REFS,
                "typed_outputs": _NONEMPTY_REFS,
                "quality_gates": _NONEMPTY_REFS,
                "stop_conditions": _NONEMPTY_REFS,
                "prohibited_actions": _NONEMPTY_REFS,
            },
            "additionalProperties": False,
        },
        "constitutional_lifecycle": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": _ID,
        },
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
        "implementation_authorized": {"const": False},
        "execution_authorized": {"const": False},
        "test_result_authorized": {"const": False},
        "completion_authorized": {"const": False},
        "promotion_authorized": {"const": False},
        "content_digest": _DIGEST,
    },
)

_ENVELOPE_SCHEMA = _object(
    "builder-implementation-envelope-v1",
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
        "implementation_digest",
    ),
    {
        "record_type": {"const": "builder-implementation-envelope"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "successor_digest": _DIGEST,
        "request_digest": _DIGEST,
        "request_snapshot": _REQUEST_SCHEMA,
        "outputs": _OUTPUTS_OBJECT,
        "resource_accounting": _RESOURCE_ACCOUNTING,
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
        "implementation_digest": _DIGEST,
    },
)

_SCHEMAS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "builder-agent-successor-v1": _SUCCESSOR_SCHEMA,
        "builder-implementation-request-v1": _REQUEST_SCHEMA,
        "builder-requirement-trace-v1": _REQUIREMENT_TRACE_SCHEMA,
        "builder-implementation-scope-v1": _IMPLEMENTATION_SCOPE_SCHEMA,
        "builder-change-plan-v1": _CHANGE_PLAN_SCHEMA,
        "builder-workspace-plan-v1": _WORKSPACE_PLAN_SCHEMA,
        "builder-dependency-plan-v1": _DEPENDENCY_PLAN_SCHEMA,
        "builder-test-plan-v1": _TEST_PLAN_SCHEMA,
        "builder-execution-evidence-plan-v1": _EXECUTION_EVIDENCE_SCHEMA,
        "builder-rollback-plan-v1": _ROLLBACK_PLAN_SCHEMA,
        "builder-artifact-manifest-v1": _ARTIFACT_MANIFEST_SCHEMA,
        "builder-curator-handoff-v1": _CURATOR_HANDOFF_SCHEMA,
        "builder-implementation-envelope-v1": _ENVELOPE_SCHEMA,
    }
)


def load_builder_schema(name: str) -> dict[str, Any]:
    if name not in BUILDER_SCHEMA_NAMES:
        raise KeyError(f"unknown Builder schema: {name}")
    return dict(deepcopy(_SCHEMAS[name]))


def _exact_json_issues(value: Any, path: str, issues: list[str], *, depth: int = 0) -> None:
    if depth > 24:
        issues.append(f"{path}: nesting exceeds validation bound")
        return
    if value is None or type(value) in {bool, int, float, str}:
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _exact_json_issues(item, f"{path}[{index}]", issues, depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                issues.append(f"{path}: non-string key")
                continue
            _exact_json_issues(item, f"{path}.{key}", issues, depth=depth + 1)
        return
    issues.append(f"{path}: non-exact JSON container or unsupported type {type(value).__name__}")


def _validate_seal(document: Mapping[str, Any], field: str, issues: list[str]) -> None:
    body = {key: value for key, value in document.items() if key != field}
    if document.get(field) != digest(body):
        issues.append(f"{field.replace('_', ' ')} mismatch")


def _validate_layers(document: Mapping[str, Any], issues: list[str]) -> None:
    layers = document.get("layers")
    if not isinstance(layers, list):
        return
    positions = [item.get("position") for item in layers if isinstance(item, Mapping)]
    kinds = [item.get("kind") for item in layers if isinstance(item, Mapping)]
    layer_ids = [item.get("layer_id") for item in layers if isinstance(item, Mapping)]
    if positions != list(range(1, 9)):
        issues.append("successor layer positions differ from the fixed order")
    if kinds != list(LAYER_KINDS):
        issues.append("successor layer kinds differ from the fixed order")
    if layer_ids != list(LAYER_IDS):
        issues.append("successor layer identities differ from the fixed order")
    for index, layer in enumerate(layers):
        if not isinstance(layer, Mapping):
            continue
        body = {key: value for key, value in layer.items() if key != "digest"}
        if layer.get("digest") != digest(body):
            issues.append(f"successor layer {index + 1} digest mismatch")


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
            allocation.get("checkpoint_reserve"),
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
        checkpoint_reserve = cast(int, allocation.get("checkpoint_reserve"))
        evidence_reserve = cast(int, allocation.get("evidence_reserve"))
        rollback_reserve = cast(int, allocation.get("rollback_reserve"))
        section_values = [cast(int, sections[section]) for section in RESOURCE_SECTIONS]
        observed = (
            checkpoint_reserve
            + evidence_reserve
            + rollback_reserve
            + sum(section_values)
        )
        if observed != ceiling:
            issues.append(f"resource axis {axis} does not reconcile to its ceiling")


@lru_cache(maxsize=32)
def _canonical_envelope_bytes(request_json: str) -> bytes:
    from .builder_playbook import compile_builder_implementation

    request = json.loads(request_json)
    return canonical_bytes(compile_builder_implementation(request))


def validate_builder(
    name: str,
    document: Any,
    *,
    enforce_reviewed_successor: bool = True,
    enforce_canonical_envelope: bool = True,
) -> FoundationValidation:
    try:
        schema = load_builder_schema(name)
    except (KeyError, ValueError) as error:
        return FoundationValidation(False, (f"schema unavailable: {type(error).__name__}: {error}",))
    result = validate_document_against_schema(document, schema)
    issues = list(result.issues)
    _exact_json_issues(document, "$", issues)
    if not isinstance(document, Mapping):
        return FoundationValidation(False, tuple(dict.fromkeys(issues)))

    if name == "builder-agent-successor-v1":
        _validate_layers(document, issues)
        _validate_seal(document, "content_digest", issues)
        if enforce_reviewed_successor and document.get("content_digest") != EXPECTED_SUCCESSOR_DIGEST:
            issues.append("successor digest differs from the reviewed Builder candidate")
        if document.get("requested_capabilities") != document.get("unsupported_capabilities"):
            issues.append("requested capabilities are not preserved as unsupported metadata")
        if document.get("effective_capabilities") != [] or document.get("tool_refs") != []:
            issues.append("Builder candidate acquired capability or tool authority")
        if document.get("output_contract_refs") != [
            OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS
        ]:
            issues.append("Builder output contract order drifted")
        for field in (
            "implementation_authorized",
            "execution_authorized",
            "test_result_authorized",
            "completion_authorized",
            "promotion_authorized",
        ):
            if document.get(field) is not False:
                issues.append(f"Builder successor escalated {field}")
    elif name.endswith("-v1") and name not in {
        "builder-implementation-request-v1",
        "builder-implementation-envelope-v1",
    }:
        _validate_seal(document, "output_digest", issues)
    elif name == "builder-implementation-envelope-v1":
        _validate_seal(document, "implementation_digest", issues)
        snapshot = document.get("request_snapshot")
        if isinstance(snapshot, Mapping):
            expected_request_digest = digest(snapshot)
            if document.get("request_digest") != expected_request_digest:
                issues.append("request snapshot does not match the envelope request digest")
            for field in ("request_id", "objective_id", "tenant_id", "repository_id"):
                if document.get(field) != snapshot.get(field):
                    issues.append(f"envelope {field} differs from the request snapshot")
        if document.get("successor_digest") != EXPECTED_SUCCESSOR_DIGEST:
            issues.append("envelope successor digest differs from the reviewed Builder candidate")
        resource = document.get("resource_accounting")
        if isinstance(resource, Mapping):
            _validate_resource_accounting(resource, issues)
        outputs = document.get("outputs")
        if isinstance(outputs, Mapping):
            if tuple(outputs) != OUTPUT_FIELDS:
                issues.append("typed output order or membership drifted")
            expected_requirement_refs: list[Any] = []
            expected_acceptance_refs: list[Any] = []
            architecture: Mapping[str, Any] | None = None
            if isinstance(snapshot, Mapping):
                requirements = snapshot.get("adjudicated_requirements")
                acceptance = snapshot.get("acceptance_criteria")
                candidate_architecture = snapshot.get("architecture_decision")
                if isinstance(requirements, list):
                    expected_requirement_refs = sorted(
                        item.get("requirement_id")
                        for item in requirements
                        if isinstance(item, Mapping)
                    )
                if isinstance(acceptance, list):
                    expected_acceptance_refs = sorted(
                        item.get("acceptance_id")
                        for item in acceptance
                        if isinstance(item, Mapping)
                    )
                if isinstance(candidate_architecture, Mapping):
                    architecture = candidate_architecture
            expected_budget_state = (
                resource.get("accounting_status") if isinstance(resource, Mapping) else None
            )
            for field in OUTPUT_FIELDS:
                output = outputs.get(field)
                if not isinstance(output, Mapping):
                    continue
                validation = validate_builder(
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
                    "builder_definition_id": DEFINITION_ID,
                    "builder_version": "2-shadow-1",
                    "budget_state": expected_budget_state,
                }
                if architecture is not None:
                    expected_scope.update(
                        {
                            "architecture_decision_id": architecture.get("decision_id"),
                            "design_digest": architecture.get("design_digest"),
                            "subject_commit": architecture.get("subject_commit"),
                            "subject_tree": architecture.get("subject_tree"),
                        }
                    )
                for scope_field, expected in expected_scope.items():
                    if output.get(scope_field) != expected:
                        issues.append(f"outputs.{field}.{scope_field} differs from the envelope")
                if output.get("requirement_refs") != expected_requirement_refs:
                    issues.append(f"outputs.{field}.requirement_refs is not the complete requirement set")
                if output.get("acceptance_refs") != expected_acceptance_refs:
                    issues.append(f"outputs.{field}.acceptance_refs is not the complete acceptance set")
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
                    "canonical implementation reconstruction failed: "
                    f"{type(error).__name__}: {error}"
                )
            else:
                if canonical_bytes(document) != expected:
                    issues.append("implementation envelope differs from the canonical request-bound result")

    return FoundationValidation(not issues, tuple(dict.fromkeys(issues)))


def validate_builder_catalog() -> FoundationValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in BUILDER_SCHEMA_NAMES:
        schema = load_builder_schema(name)
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
