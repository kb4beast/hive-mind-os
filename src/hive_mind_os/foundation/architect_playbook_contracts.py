from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import canonical_bytes, digest
from .contracts import FoundationValidation, validate_document_against_schema

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ARCHITECT_SCHEMA_NAMES = (
    "architect-agent-successor-v1",
    "architect-design-request-v1",
    "architect-claim-integration-v1",
    "architect-option-analysis-v1",
    "architect-architecture-v1",
    "architect-interface-contract-v1",
    "architect-threat-model-v1",
    "architect-migration-plan-v1",
    "architect-rollback-plan-v1",
    "architect-verification-plan-v1",
    "architect-resource-plan-v1",
    "architect-handoff-v1",
    "architect-design-envelope-v1",
)

AGENT_ID = "hive-agent:architect:v2-shadow-1"
DEFINITION_ID = "hive-agent-definition:architect:v2-shadow-1"
BASE_DEFINITION_ID = "hive-agent-definition:architect:v2-candidate"
# Replaced after the deterministic successor is first compiled.
EXPECTED_SUCCESSOR_DIGEST = (
    "sha256:ecc0ba88c036f1f041f390cc8c68c20d52ec0336eb182c624028290d67f39bda"
)

OUTPUT_FIELDS = (
    "claim_integration",
    "option_analysis",
    "architecture",
    "interface_contract",
    "threat_model",
    "migration_plan",
    "rollback_plan",
    "verification_plan",
    "resource_plan",
    "handoff",
)
OUTPUT_SCHEMA_BY_FIELD: Mapping[str, str] = MappingProxyType(
    {
        "claim_integration": "architect-claim-integration-v1",
        "option_analysis": "architect-option-analysis-v1",
        "architecture": "architect-architecture-v1",
        "interface_contract": "architect-interface-contract-v1",
        "threat_model": "architect-threat-model-v1",
        "migration_plan": "architect-migration-plan-v1",
        "rollback_plan": "architect-rollback-plan-v1",
        "verification_plan": "architect-verification-plan-v1",
        "resource_plan": "architect-resource-plan-v1",
        "handoff": "architect-handoff-v1",
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
    "claim-integration",
    "option-analysis",
    "architecture",
    "interfaces",
    "threat-model",
    "migration",
    "rollback",
    "verification",
    "handoff",
)
SCORE_FIELDS = (
    "constraint_fit_ppm",
    "reversibility_ppm",
    "security_ppm",
    "evolvability_ppm",
    "evidence_ppm",
    "resource_efficiency_ppm",
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
    "generation-zero:architect",
    "architect:deep-playbook",
    "skill.architect",
    "architect:design-request",
    "architect:typed-outputs",
    "architect:phase5b-governance",
    "generation-zero:lifecycle",
)

_DIGEST = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
_ID = {"type": "string", "minLength": 1, "maxLength": 256}
_TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
_BOOL_FALSE = {"const": False}
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
_OUTPUT_SCOPE_REQUIRED = (
    "request_id",
    "request_digest",
    "objective_id",
    "tenant_id",
    "repository_id",
)
_OUTPUT_SCOPE_PROPERTIES = {
    "request_id": _ID,
    "request_digest": _DIGEST,
    "objective_id": _ID,
    "tenant_id": _ID,
    "repository_id": _ID,
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

_CLAIM = {
    "type": "object",
    "required": [
        "claim_id",
        "statement",
        "disposition",
        "material",
        "evidence_refs",
        "acceptance_refs",
    ],
    "properties": {
        "claim_id": _ID,
        "statement": _TEXT,
        "disposition": {
            "type": "string",
            "enum": ["adopt", "adapt", "defer", "reject", "quarantine"],
        },
        "material": {"type": "boolean"},
        "evidence_refs": _REF_LIST,
        "acceptance_refs": _REF_LIST,
    },
    "additionalProperties": False,
}

_CLAIM_MAPPING = {
    "type": "object",
    "required": ["claim_id", "option_id", "design_refs"],
    "properties": {
        "claim_id": _ID,
        "option_id": _ID,
        "design_refs": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_COMPONENT = {
    "type": "object",
    "required": ["component_id", "responsibility", "authority", "data_classes"],
    "properties": {
        "component_id": _ID,
        "responsibility": _TEXT,
        "authority": {"const": "none"},
        "data_classes": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_INTERFACE = {
    "type": "object",
    "required": [
        "interface_id",
        "source_component_id",
        "target_component_id",
        "contract",
        "version",
        "compatibility",
    ],
    "properties": {
        "interface_id": _ID,
        "source_component_id": _ID,
        "target_component_id": _ID,
        "contract": _TEXT,
        "version": _ID,
        "compatibility": {
            "type": "string",
            "enum": ["compatible", "migration-required", "unknown"],
        },
    },
    "additionalProperties": False,
}

_INVARIANT = {
    "type": "object",
    "required": ["invariant_id", "statement"],
    "properties": {"invariant_id": _ID, "statement": _TEXT},
    "additionalProperties": False,
}

_TRUST_BOUNDARY = {
    "type": "object",
    "required": [
        "boundary_id",
        "source_component_id",
        "target_component_id",
        "data_classes",
        "threat_ids",
    ],
    "properties": {
        "boundary_id": _ID,
        "source_component_id": _ID,
        "target_component_id": _ID,
        "data_classes": _NONEMPTY_REFS,
        "threat_ids": _NONEMPTY_REFS,
    },
    "additionalProperties": False,
}

_THREAT = {
    "type": "object",
    "required": [
        "threat_id",
        "statement",
        "likelihood",
        "impact",
        "mitigation_refs",
        "residual_risk_ppm",
    ],
    "properties": {
        "threat_id": _ID,
        "statement": _TEXT,
        "likelihood": {"type": "string", "enum": ["low", "medium", "high", "unknown"]},
        "impact": {"type": "string", "enum": ["low", "medium", "high", "critical", "unknown"]},
        "mitigation_refs": _NONEMPTY_REFS,
        "residual_risk_ppm": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
    },
    "additionalProperties": False,
}

_MIGRATION_STEP = {
    "type": "object",
    "required": ["step_id", "description", "depends_on", "rollback_step_id"],
    "properties": {
        "step_id": _ID,
        "description": _TEXT,
        "depends_on": _REF_LIST,
        "rollback_step_id": _ID,
    },
    "additionalProperties": False,
}

_ROLLBACK_STEP = {
    "type": "object",
    "required": ["rollback_step_id", "description", "restores_ref"],
    "properties": {
        "rollback_step_id": _ID,
        "description": _TEXT,
        "restores_ref": _ID,
    },
    "additionalProperties": False,
}

_VERIFICATION_STEP = {
    "type": "object",
    "required": [
        "verification_id",
        "method",
        "acceptance_refs",
        "invariant_refs",
        "threat_refs",
        "migration_step_refs",
        "rollback_step_refs",
    ],
    "properties": {
        "verification_id": _ID,
        "method": _TEXT,
        "acceptance_refs": _REF_LIST,
        "invariant_refs": _REF_LIST,
        "threat_refs": _REF_LIST,
        "migration_step_refs": _REF_LIST,
        "rollback_step_refs": _REF_LIST,
    },
    "additionalProperties": False,
}

_SCORE_INPUTS = {
    "type": "object",
    "required": list(SCORE_FIELDS),
    "properties": {
        name: {"type": "integer", "minimum": 0, "maximum": 1_000_000}
        for name in SCORE_FIELDS
    },
    "additionalProperties": False,
}

_OPTION = {
    "type": "object",
    "required": [
        "option_id",
        "summary",
        "rationale",
        "unknowns",
        "violations",
        "components",
        "interfaces",
        "invariants",
        "trust_boundaries",
        "threats",
        "migration_steps",
        "rollback_steps",
        "verification_steps",
        "score_inputs",
    ],
    "properties": {
        "option_id": _ID,
        "summary": _TEXT,
        "rationale": _TEXT,
        "unknowns": _REF_LIST,
        "violations": _REF_LIST,
        "components": {
            "type": "array",
            "minItems": 1,
            "maxItems": 16,
            "items": _COMPONENT,
        },
        "interfaces": {
            "type": "array",
            "maxItems": 32,
            "items": _INTERFACE,
        },
        "invariants": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _INVARIANT,
        },
        "trust_boundaries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _TRUST_BOUNDARY,
        },
        "threats": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _THREAT,
        },
        "migration_steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _MIGRATION_STEP,
        },
        "rollback_steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _ROLLBACK_STEP,
        },
        "verification_steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _VERIFICATION_STEP,
        },
        "score_inputs": _SCORE_INPUTS,
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

_BUDGET_AXIS = {"type": ["integer", "null"], "minimum": 0, "maximum": 10**15}
_BUDGETS = {
    "type": "object",
    "required": list(RESOURCE_AXES),
    "properties": {name: _BUDGET_AXIS for name in RESOURCE_AXES},
    "additionalProperties": False,
}

_SUCCESSOR_SCHEMA = _object(
    "architect-agent-successor/v1",
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
        "content_digest",
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
        "governance",
        "activation",
        "authority",
        "public",
    ),
    {
        "record_type": {"const": "architect-agent-successor"},
        "schema_version": {"const": 1},
        "agent_id": {"const": AGENT_ID},
        "definition_id": {"const": DEFINITION_ID},
        "role_id": {"const": "architect"},
        "version": {"const": "2-shadow-1"},
        "status": {"const": "candidate"},
        "lineage_relation": {"const": "extends-inert"},
        "base_definition_ref": {"const": BASE_DEFINITION_ID},
        "rollback_ref": {"const": BASE_DEFINITION_ID},
        "content_digest": _DIGEST,
        "layers": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": _LAYER,
        },
        "requested_capabilities": _REF_LIST,
        "effective_capabilities": {"type": "array", "maxItems": 0},
        "unsupported_capabilities": _REF_LIST,
        "tool_refs": {"type": "array", "maxItems": 0},
        "input_contract_refs": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {"const": "architect-design-request-v1"},
        },
        "output_contract_refs": {
            "type": "array",
            "minItems": len(OUTPUT_FIELDS),
            "maxItems": len(OUTPUT_FIELDS),
            "uniqueItems": True,
            "items": _ID,
        },
        "workflow_refs": _NONEMPTY_REFS,
        "budgets": {
            "type": "object",
            "required": [
                "max_claims",
                "max_options",
                "max_design_records_per_option",
                "max_evidence_refs",
                "max_rollback_refs",
                "max_prior_fingerprints",
                "max_text",
                "max_nested_values",
            ],
            "properties": {
                "max_claims": {"type": "integer", "minimum": 1},
                "max_options": {"type": "integer", "minimum": 2},
                "max_design_records_per_option": {"type": "integer", "minimum": 1},
                "max_evidence_refs": {"type": "integer", "minimum": 1},
                "max_rollback_refs": {"type": "integer", "minimum": 1},
                "max_prior_fingerprints": {"type": "integer", "minimum": 1},
                "max_text": {"type": "integer", "minimum": 1},
                "max_nested_values": {"type": "integer", "minimum": 1},
            },
            "additionalProperties": False,
        },
        "playbook": {
            "type": "object",
            "required": [
                "responsibilities",
                "typed_outputs",
                "quality_gates",
                "stop_conditions",
                "prohibited_actions",
            ],
            "properties": {
                "responsibilities": _NONEMPTY_REFS,
                "typed_outputs": _NONEMPTY_REFS,
                "quality_gates": _NONEMPTY_REFS,
                "stop_conditions": _NONEMPTY_REFS,
                "prohibited_actions": _NONEMPTY_REFS,
            },
            "additionalProperties": False,
        },
        "governance": {
            "type": "object",
            "required": ["source_refs", "court_refs", "dissent_ref", "activation_prerequisites"],
            "properties": {
                "source_refs": _NONEMPTY_REFS,
                "court_refs": _NONEMPTY_REFS,
                "dissent_ref": _ID,
                "activation_prerequisites": _NONEMPTY_REFS,
            },
            "additionalProperties": False,
        },
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
    },
)

_REQUEST_SCHEMA = _object(
    "architect-design-request/v1",
    (
        "record_type",
        "schema_version",
        "request_id",
        "objective_id",
        "tenant_id",
        "repository_id",
        "objective",
        "constraints",
        "acceptance_criteria",
        "evidence_refs",
        "rollback_refs",
        "claims",
        "claim_mappings",
        "options",
        "budgets",
        "rollback_reserve_ppm",
        "verification_reserve_ppm",
        "actors",
        "prior_design_fingerprints",
        "objective_state",
        "requested_option_id",
        "requested_next_role",
    ),
    {
        "record_type": {"const": "architect-design-request"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "objective": _TEXT,
        "constraints": _NONEMPTY_REFS,
        "acceptance_criteria": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _ACCEPTANCE,
        },
        "evidence_refs": _REF_LIST,
        "rollback_refs": _NONEMPTY_REFS,
        "claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "items": _CLAIM,
        },
        "claim_mappings": {
            "type": "array",
            "maxItems": 256,
            "items": _CLAIM_MAPPING,
        },
        "options": {
            "type": "array",
            "minItems": 2,
            "maxItems": 8,
            "items": _OPTION,
        },
        "budgets": _BUDGETS,
        "rollback_reserve_ppm": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 500_000,
        },
        "verification_reserve_ppm": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": 500_000,
        },
        "actors": {
            "type": "array",
            "minItems": len(COURT_ROLES),
            "maxItems": len(COURT_ROLES),
            "items": _ACTOR,
        },
        "prior_design_fingerprints": {
            "type": "array",
            "maxItems": 32,
            "uniqueItems": True,
            "items": _DIGEST,
        },
        "objective_state": {
            "type": "string",
            "enum": ["proposed", "blocked", "recovering"],
        },
        "requested_option_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 256},
        "requested_next_role": {
            "type": "string",
            "enum": ["explorer", "builder", "curator", "steward"],
        },
    },
)

_MAPPING_OUTPUT = {
    "type": "object",
    "required": [
        "claim_id",
        "option_id",
        "disposition",
        "status",
        "evidence_refs",
        "acceptance_refs",
        "design_refs",
    ],
    "properties": {
        "claim_id": _ID,
        "option_id": _ID,
        "disposition": {
            "type": "string",
            "enum": ["adopt", "adapt", "defer", "reject", "quarantine"],
        },
        "status": {"type": "string", "enum": ["mapped", "not-applicable"]},
        "evidence_refs": _REF_LIST,
        "acceptance_refs": _REF_LIST,
        "design_refs": _REF_LIST,
    },
    "additionalProperties": False,
}

_CLAIM_INTEGRATION_SCHEMA = _object(
    "architect-claim-integration/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "mappings", "unresolved_claim_ids", "completion_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-claim-integration"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "mappings": {"type": "array", "maxItems": 256, "items": _MAPPING_OUTPUT},
        "unresolved_claim_ids": _REF_LIST,
        "completion_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_RANKING = {
    "type": "object",
    "required": [
        "option_id",
        "rank",
        "weighted_score_ppm",
        "viability_status",
        "blocking_reasons",
        "residual_risk_ppm",
    ],
    "properties": {
        "option_id": _ID,
        "rank": {"type": "integer", "minimum": 1, "maximum": 8},
        "weighted_score_ppm": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
        "viability_status": {"type": "string", "enum": ["viable", "blocked"]},
        "blocking_reasons": _REF_LIST,
        "residual_risk_ppm": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
    },
    "additionalProperties": False,
}

_OPTION_ANALYSIS_SCHEMA = _object(
    "architect-option-analysis/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "rankings", "provisional_preferred_option_id", "requested_option_id", "requested_option_eligible", "selection_status", "selection_reasons", "iteration_status", "design_fingerprint", "selection_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-option-analysis"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "rankings": {"type": "array", "minItems": 2, "maxItems": 8, "items": _RANKING},
        "provisional_preferred_option_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 256},
        "requested_option_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 256},
        "requested_option_eligible": {"type": "boolean"},
        "selection_status": {"const": "defer"},
        "selection_reasons": _NONEMPTY_REFS,
        "iteration_status": {"type": "string", "enum": ["new", "repeated"]},
        "design_fingerprint": _DIGEST,
        "selection_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_ARCHITECTURE_OPTION = {
    "type": "object",
    "required": ["option_id", "summary", "rationale", "components", "invariants", "trust_boundaries"],
    "properties": {
        "option_id": _ID,
        "summary": _TEXT,
        "rationale": _TEXT,
        "components": {"type": "array", "minItems": 1, "maxItems": 16, "items": _COMPONENT},
        "invariants": {"type": "array", "minItems": 1, "maxItems": 32, "items": _INVARIANT},
        "trust_boundaries": {"type": "array", "minItems": 1, "maxItems": 32, "items": _TRUST_BOUNDARY},
    },
    "additionalProperties": False,
}

_ARCHITECTURE_SCHEMA = _object(
    "architect-architecture/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "objective", "constraints", "options", "provisional_preferred_option_id", "architecture_status", "implementation_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-architecture"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "objective": _TEXT,
        "constraints": _NONEMPTY_REFS,
        "options": {"type": "array", "minItems": 2, "maxItems": 8, "items": _ARCHITECTURE_OPTION},
        "provisional_preferred_option_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 256},
        "architecture_status": {"type": "string", "enum": ["proposed", "blocked", "recovery-required", "repeated"]},
        "implementation_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_INTERFACE_OPTION = {
    "type": "object",
    "required": ["option_id", "interfaces", "compatibility_status"],
    "properties": {
        "option_id": _ID,
        "interfaces": {"type": "array", "maxItems": 32, "items": _INTERFACE},
        "compatibility_status": {"type": "string", "enum": ["compatible", "migration-required", "unknown"]},
    },
    "additionalProperties": False,
}

_INTERFACE_SCHEMA = _object(
    "architect-interface-contract/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "options", "implementation_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-interface-contract"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "options": {"type": "array", "minItems": 2, "maxItems": 8, "items": _INTERFACE_OPTION},
        "implementation_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_THREAT_OPTION = {
    "type": "object",
    "required": ["option_id", "threats", "residual_risk_ppm", "blocking_threat_ids"],
    "properties": {
        "option_id": _ID,
        "threats": {"type": "array", "minItems": 1, "maxItems": 32, "items": _THREAT},
        "residual_risk_ppm": {"type": "integer", "minimum": 0, "maximum": 1_000_000},
        "blocking_threat_ids": _REF_LIST,
    },
    "additionalProperties": False,
}

_THREAT_MODEL_SCHEMA = _object(
    "architect-threat-model/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "options", "risk_status", "risk_acceptance_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-threat-model"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "options": {"type": "array", "minItems": 2, "maxItems": 8, "items": _THREAT_OPTION},
        "risk_status": {"type": "string", "enum": ["bounded", "blocked", "unknown"]},
        "risk_acceptance_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_MIGRATION_OPTION = {
    "type": "object",
    "required": ["option_id", "steps", "status"],
    "properties": {
        "option_id": _ID,
        "steps": {"type": "array", "minItems": 1, "maxItems": 32, "items": _MIGRATION_STEP},
        "status": {"type": "string", "enum": ["proposed", "blocked", "recovery-required"]},
    },
    "additionalProperties": False,
}

_MIGRATION_SCHEMA = _object(
    "architect-migration-plan/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "options", "migration_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-migration-plan"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "options": {"type": "array", "minItems": 2, "maxItems": 8, "items": _MIGRATION_OPTION},
        "migration_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_ROLLBACK_OPTION = {
    "type": "object",
    "required": ["option_id", "steps", "status"],
    "properties": {
        "option_id": _ID,
        "steps": {"type": "array", "minItems": 1, "maxItems": 32, "items": _ROLLBACK_STEP},
        "status": {"type": "string", "enum": ["required", "blocked", "recovery-required"]},
    },
    "additionalProperties": False,
}

_ROLLBACK_SCHEMA = _object(
    "architect-rollback-plan/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "options", "rollback_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-rollback-plan"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "options": {"type": "array", "minItems": 2, "maxItems": 8, "items": _ROLLBACK_OPTION},
        "rollback_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_VERIFICATION_OPTION = {
    "type": "object",
    "required": ["option_id", "steps", "coverage_complete"],
    "properties": {
        "option_id": _ID,
        "steps": {"type": "array", "minItems": 1, "maxItems": 32, "items": _VERIFICATION_STEP},
        "coverage_complete": {"const": True},
    },
    "additionalProperties": False,
}

_VERIFICATION_SCHEMA = _object(
    "architect-verification-plan/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "options", "verification_status", "verification_executed", "output_digest"),
    {
        "record_type": {"const": "architect-verification-plan"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "options": {"type": "array", "minItems": 2, "maxItems": 8, "items": _VERIFICATION_OPTION},
        "verification_status": {"const": "planned"},
        "verification_executed": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_AXIS_ALLOCATION = {
    "type": "object",
    "required": ["ceiling", "rollback_reserve", "verification_reserve", "section_allocations"],
    "properties": {
        "ceiling": _BUDGET_AXIS,
        "rollback_reserve": _BUDGET_AXIS,
        "verification_reserve": _BUDGET_AXIS,
        "section_allocations": {
            "type": "object",
            "required": list(RESOURCE_SECTIONS),
            "properties": {name: _BUDGET_AXIS for name in RESOURCE_SECTIONS},
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
}

_RESOURCE_SCHEMA = _object(
    "architect-resource-plan/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "accounting_status", "lease_status", "rollback_reserve_ppm", "verification_reserve_ppm", "sections", "axes", "budget_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-resource-plan"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "accounting_status": {"type": "string", "enum": ["known", "unknown"]},
        "lease_status": {"const": "not-issued"},
        "rollback_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 500_000},
        "verification_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 500_000},
        "sections": {
            "type": "array",
            "minItems": len(RESOURCE_SECTIONS),
            "maxItems": len(RESOURCE_SECTIONS),
            "uniqueItems": True,
            "items": {"type": "string", "enum": list(RESOURCE_SECTIONS)},
        },
        "axes": {
            "type": "object",
            "required": list(RESOURCE_AXES),
            "properties": {name: _AXIS_ALLOCATION for name in RESOURCE_AXES},
            "additionalProperties": False,
        },
        "budget_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_HANDOFF_SCHEMA = _object(
    "architect-handoff/v1",
    (*_OUTPUT_SCOPE_REQUIRED, "record_type", "schema_version", "next_role", "requested_next_role", "requested_role_eligible", "reason", "provisional_option_id", "required_refs", "implementation_authorized", "activation_authorized", "output_digest"),
    {
        "record_type": {"const": "architect-handoff"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "next_role": {"type": "string", "enum": ["explorer", "builder", "curator", "steward"]},
        "requested_next_role": {"type": "string", "enum": ["explorer", "builder", "curator", "steward"]},
        "requested_role_eligible": {"type": "boolean"},
        "reason": _ID,
        "provisional_option_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 256},
        "required_refs": _NONEMPTY_REFS,
        "implementation_authorized": _BOOL_FALSE,
        "activation_authorized": _BOOL_FALSE,
        "output_digest": _DIGEST,
    },
)

_OUTPUTS_OBJECT = {
    "type": "object",
    "required": list(OUTPUT_FIELDS),
    "properties": {
        "claim_integration": _CLAIM_INTEGRATION_SCHEMA,
        "option_analysis": _OPTION_ANALYSIS_SCHEMA,
        "architecture": _ARCHITECTURE_SCHEMA,
        "interface_contract": _INTERFACE_SCHEMA,
        "threat_model": _THREAT_MODEL_SCHEMA,
        "migration_plan": _MIGRATION_SCHEMA,
        "rollback_plan": _ROLLBACK_SCHEMA,
        "verification_plan": _VERIFICATION_SCHEMA,
        "resource_plan": _RESOURCE_SCHEMA,
        "handoff": _HANDOFF_SCHEMA,
    },
    "additionalProperties": False,
}

_ENVELOPE_SCHEMA = _object(
    "architect-design-envelope/v1",
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
        "activation",
        "authority",
        "public",
        "design_digest",
    ),
    {
        "record_type": {"const": "architect-design-envelope"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "successor_digest": _DIGEST,
        "request_digest": _DIGEST,
        "request_snapshot": _REQUEST_SCHEMA,
        "outputs": _OUTPUTS_OBJECT,
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
        "design_digest": _DIGEST,
    },
)

_SCHEMAS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "architect-agent-successor-v1": _SUCCESSOR_SCHEMA,
        "architect-design-request-v1": _REQUEST_SCHEMA,
        "architect-claim-integration-v1": _CLAIM_INTEGRATION_SCHEMA,
        "architect-option-analysis-v1": _OPTION_ANALYSIS_SCHEMA,
        "architect-architecture-v1": _ARCHITECTURE_SCHEMA,
        "architect-interface-contract-v1": _INTERFACE_SCHEMA,
        "architect-threat-model-v1": _THREAT_MODEL_SCHEMA,
        "architect-migration-plan-v1": _MIGRATION_SCHEMA,
        "architect-rollback-plan-v1": _ROLLBACK_SCHEMA,
        "architect-verification-plan-v1": _VERIFICATION_SCHEMA,
        "architect-resource-plan-v1": _RESOURCE_SCHEMA,
        "architect-handoff-v1": _HANDOFF_SCHEMA,
        "architect-design-envelope-v1": _ENVELOPE_SCHEMA,
    }
)


def load_architect_schema(name: str) -> dict[str, Any]:
    if name not in ARCHITECT_SCHEMA_NAMES:
        raise KeyError(f"unknown Architect schema: {name}")
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


@lru_cache(maxsize=32)
def _canonical_envelope_bytes(request_json: str) -> bytes:
    from .architect_playbook import compile_architect_design

    request = json.loads(request_json)
    return canonical_bytes(compile_architect_design(request))


def validate_architect(
    name: str,
    document: Any,
    *,
    enforce_reviewed_successor: bool = True,
    enforce_canonical_envelope: bool = True,
) -> FoundationValidation:
    try:
        schema = load_architect_schema(name)
    except (KeyError, ValueError) as error:
        return FoundationValidation(False, (f"schema unavailable: {type(error).__name__}: {error}",))
    result = validate_document_against_schema(document, schema)
    issues = list(result.issues)
    _exact_json_issues(document, "$", issues)
    if not isinstance(document, Mapping):
        return FoundationValidation(False, tuple(dict.fromkeys(issues)))

    if name == "architect-agent-successor-v1":
        _validate_layers(document, issues)
        _validate_seal(document, "content_digest", issues)
        if enforce_reviewed_successor and document.get("content_digest") != EXPECTED_SUCCESSOR_DIGEST:
            issues.append("successor digest differs from the reviewed Architect candidate")
        if document.get("requested_capabilities") != document.get("unsupported_capabilities"):
            issues.append("requested capabilities are not preserved as unsupported metadata")
        if document.get("effective_capabilities") != [] or document.get("tool_refs") != []:
            issues.append("Architect candidate acquired capability or tool authority")
        if document.get("output_contract_refs") != [
            OUTPUT_SCHEMA_BY_FIELD[field] for field in OUTPUT_FIELDS
        ]:
            issues.append("Architect output contract order drifted")
    elif name.endswith("-v1") and name not in {
        "architect-design-request-v1",
        "architect-design-envelope-v1",
    }:
        _validate_seal(document, "output_digest", issues)
    elif name == "architect-design-envelope-v1":
        _validate_seal(document, "design_digest", issues)
        snapshot = document.get("request_snapshot")
        if isinstance(snapshot, Mapping):
            expected_request_digest = digest(snapshot)
            if document.get("request_digest") != expected_request_digest:
                issues.append("request snapshot does not match the envelope request digest")
            for field in ("request_id", "objective_id", "tenant_id", "repository_id"):
                if document.get(field) != snapshot.get(field):
                    issues.append(f"envelope {field} differs from the request snapshot")
        if document.get("successor_digest") != EXPECTED_SUCCESSOR_DIGEST:
            issues.append("envelope successor digest differs from the reviewed Architect candidate")
        outputs = document.get("outputs")
        if isinstance(outputs, Mapping):
            if tuple(outputs) != OUTPUT_FIELDS:
                issues.append("typed output order or membership drifted")
            for field in OUTPUT_FIELDS:
                output = outputs.get(field)
                if not isinstance(output, Mapping):
                    continue
                validation = validate_architect(
                    OUTPUT_SCHEMA_BY_FIELD[field],
                    output,
                    enforce_reviewed_successor=enforce_reviewed_successor,
                    enforce_canonical_envelope=False,
                )
                issues.extend(f"outputs.{field}: {issue}" for issue in validation.issues)
                for scope_field in _OUTPUT_SCOPE_REQUIRED:
                    expected = document.get(scope_field) if scope_field != "request_digest" else document.get("request_digest")
                    if output.get(scope_field) != expected:
                        issues.append(f"outputs.{field}.{scope_field} differs from the envelope")
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
                issues.append(f"canonical design reconstruction failed: {type(error).__name__}: {error}")
            else:
                if canonical_bytes(document) != expected:
                    issues.append("design envelope differs from the canonical request-bound result")

    return FoundationValidation(not issues, tuple(dict.fromkeys(issues)))


def validate_architect_catalog() -> FoundationValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in ARCHITECT_SCHEMA_NAMES:
        schema = load_architect_schema(name)
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
