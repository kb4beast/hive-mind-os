from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import digest, stable_id
from .contracts import FoundationValidation, validate_document_against_schema

DIALECT = "https://json-schema.org/draft/2020-12/schema"
ORCHESTRATOR_SCHEMA_NAMES = (
    "orchestrator-agent-successor-v1",
    "orchestrator-plan-request-v1",
    "orchestrator-objective-decomposition-v1",
    "orchestrator-dependency-graph-v1",
    "orchestrator-budget-plan-v1",
    "orchestrator-court-schedule-v1",
    "orchestrator-recovery-plan-v1",
    "orchestrator-stop-decision-v1",
    "orchestrator-handoff-v1",
    "orchestrator-plan-envelope-v1",
)

AGENT_ID = "hive-agent:orchestrator:v2-shadow-1"
DEFINITION_ID = "hive-agent-definition:orchestrator:v2-shadow-1"
BASE_DEFINITION_ID = "hive-agent-definition:orchestrator:v2-candidate"
EXPECTED_SUCCESSOR_DIGEST = (
    "sha256:e2e6f8ee8975db17a002fafc7d78aa5e2f696540e2ce4404d4548785643528fc"
)

WORK_ROLES = (
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)
ROLE_INSTRUCTIONS: Mapping[str, str] = MappingProxyType(
    {
        "explorer": (
            "Investigate the objective and admitted evidence; preserve unknowns and "
            "alternatives."
        ),
        "architect": (
            "Define interfaces, invariants, threats, migration, and rollback for the "
            "bounded objective."
        ),
        "builder": (
            "Implement only the approved bounded change with executable verification "
            "and no authority expansion."
        ),
        "curator": (
            "Reproduce the claims, tests, provenance, and package contents without "
            "using Builder rationale as proof."
        ),
        "integrator": (
            "Verify compatibility, data lineage, and absence of unintended root API, "
            "CLI, store, or host drift."
        ),
        "steward": (
            "Verify recovery, interruption, boundedness, maintainability, and durable "
            "operational evidence."
        ),
        "optimizer": (
            "Evaluate honest stopping, resource accounting, and unsupported value or "
            "superiority claims."
        ),
    }
)
MAX_HANDOFF_REFS = 128
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

_DIGEST = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
_ID = {"type": "string", "minLength": 1, "maxLength": 256}
_TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
_REF_LIST = {
    "type": "array",
    "maxItems": 64,
    "uniqueItems": True,
    "items": _ID,
}
_NONEMPTY_REFS = {
    "type": "array",
    "minItems": 1,
    "maxItems": 64,
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

_SUCCESSOR_SCHEMA = _object(
    "orchestrator-agent-successor/v1",
    (
        "record_type", "schema_version", "agent_id", "definition_id", "role_id",
        "version", "status", "lineage_relation", "base_definition_ref", "rollback_ref",
        "content_digest", "layers", "requested_capabilities", "effective_capabilities",
        "unsupported_capabilities", "tool_refs", "input_contract_refs",
        "output_contract_refs", "workflow_refs", "budgets", "playbook", "governance",
        "activation", "authority", "public",
    ),
    {
        "record_type": {"const": "orchestrator-agent-successor"},
        "schema_version": {"const": 1},
        "agent_id": {"const": AGENT_ID},
        "definition_id": {"const": DEFINITION_ID},
        "role_id": {"const": "orchestrator"},
        "version": {"const": "2-shadow-1"},
        "status": {"const": "candidate"},
        "lineage_relation": {"const": "extends-inert"},
        "base_definition_ref": {"const": BASE_DEFINITION_ID},
        "rollback_ref": {"const": BASE_DEFINITION_ID},
        "content_digest": _DIGEST,
        "layers": {"type": "array", "minItems": 8, "maxItems": 8, "items": _LAYER},
        "requested_capabilities": _NONEMPTY_REFS,
        "effective_capabilities": {"type": "array", "maxItems": 0},
        "unsupported_capabilities": _NONEMPTY_REFS,
        "tool_refs": {"type": "array", "maxItems": 0},
        "input_contract_refs": _NONEMPTY_REFS,
        "output_contract_refs": _NONEMPTY_REFS,
        "workflow_refs": _NONEMPTY_REFS,
        "budgets": {
            "type": "object",
            "required": [
                "max_work_items", "max_dependencies", "max_evidence_refs", "max_rollback_refs",
                "max_handoff_refs", "max_ancestry_depth", "max_progress_fingerprints",
                "max_text", "max_nested_values",
            ],
            "properties": {
                "max_work_items": {"const": 7},
                "max_dependencies": {"const": 21},
                "max_evidence_refs": {"const": 64},
                "max_rollback_refs": {"const": 32},
                "max_handoff_refs": {"const": MAX_HANDOFF_REFS},
                "max_ancestry_depth": {"const": 8},
                "max_progress_fingerprints": {"const": 32},
                "max_text": {"const": 4000},
                "max_nested_values": {"const": 2048},
            },
            "additionalProperties": False,
        },
        "playbook": {
            "type": "object",
            "required": [
                "responsibilities",
                "role_instructions",
                "typed_outputs",
                "stop_conditions",
                "prohibited_actions",
            ],
            "properties": {
                "responsibilities": _NONEMPTY_REFS,
                "role_instructions": {
                    "type": "array",
                    "minItems": len(WORK_ROLES),
                    "maxItems": len(WORK_ROLES),
                    "items": {
                        "type": "object",
                        "required": ["role", "instruction"],
                        "properties": {
                            "role": {"type": "string", "enum": list(WORK_ROLES)},
                            "instruction": _TEXT,
                        },
                        "additionalProperties": False,
                    },
                },
                "typed_outputs": _NONEMPTY_REFS,
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

_BUDGET_AXIS = {"type": ["integer", "null"], "minimum": 0, "maximum": 10**15}
_ACTOR = {
    "type": "object",
    "required": ["role", "actor_id", "authenticated"],
    "properties": {
        "role": {"type": "string", "enum": list(COURT_ROLES)},
        "actor_id": _ID,
        "authenticated": {"type": "boolean"},
    },
    "additionalProperties": False,
}
_REQUEST_SCHEMA = _object(
    "orchestrator-plan-request/v1",
    (
        "record_type", "schema_version", "request_id", "objective_id", "tenant_id",
        "repository_id", "objective", "acceptance_criteria", "constraints", "evidence_refs",
        "verification_claim_refs", "rollback_refs", "budgets", "rollback_reserve_ppm",
        "verification_reserve_ppm", "actors", "ancestry", "recursion_depth",
        "progress_fingerprints", "objective_state", "requested_next_role",
    ),
    {
        "record_type": {"const": "orchestrator-plan-request"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "objective": _TEXT,
        "acceptance_criteria": {"type": "array", "minItems": 1, "maxItems": 32, "uniqueItems": True, "items": _TEXT},
        "constraints": {"type": "array", "maxItems": 32, "uniqueItems": True, "items": _TEXT},
        "evidence_refs": _REF_LIST,
        "verification_claim_refs": _REF_LIST,
        "rollback_refs": {"type": "array", "minItems": 1, "maxItems": 32, "uniqueItems": True, "items": _ID},
        "budgets": {
            "type": "object",
            "required": ["tokens", "cost_microunits", "elapsed_ms", "tool_calls"],
            "properties": {
                "tokens": _BUDGET_AXIS,
                "cost_microunits": _BUDGET_AXIS,
                "elapsed_ms": _BUDGET_AXIS,
                "tool_calls": _BUDGET_AXIS,
            },
            "additionalProperties": False,
        },
        "rollback_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 500_000},
        "verification_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 500_000},
        "actors": {"type": "array", "maxItems": len(COURT_ROLES), "items": _ACTOR},
        "ancestry": {"type": "array", "maxItems": 8, "uniqueItems": True, "items": _ID},
        "recursion_depth": {"type": "integer", "minimum": 0, "maximum": 8},
        "progress_fingerprints": {"type": "array", "maxItems": 32, "items": _ID},
        "objective_state": {"type": "string", "enum": ["proposed", "blocked", "recovering"]},
        "requested_next_role": {"type": ["string", "null"], "enum": [None, *WORK_ROLES, "orchestrator"]},
    },
)

_WORK_ITEM = {
    "type": "object",
    "required": [
        "work_item_id", "request_id", "objective_id", "request_digest", "tenant_id",
        "repository_id", "objective", "constraints", "role", "instruction",
        "dependencies", "evidence_refs", "rollback_refs", "acceptance_criteria",
    ],
    "properties": {
        "work_item_id": _ID,
        "request_id": _ID,
        "objective_id": _ID,
        "request_digest": _DIGEST,
        "tenant_id": _ID,
        "repository_id": _ID,
        "objective": _TEXT,
        "constraints": {
            "type": "array",
            "maxItems": 32,
            "uniqueItems": True,
            "items": _TEXT,
        },
        "role": {"type": "string", "enum": list(WORK_ROLES)},
        "instruction": _TEXT,
        "dependencies": _REF_LIST,
        "evidence_refs": _REF_LIST,
        "rollback_refs": _NONEMPTY_REFS,
        "acceptance_criteria": {"type": "array", "minItems": 1, "maxItems": 32, "uniqueItems": True, "items": _TEXT},
    },
    "additionalProperties": False,
}
_DECOMPOSITION_SCHEMA = _object(
    "orchestrator-objective-decomposition/v1",
    (
        "record_type", "schema_version", *_OUTPUT_SCOPE_REQUIRED, "objective",
        "constraints", "status", "work_items", "unknowns", "completion_authorized",
        "output_digest",
    ),
    {
        "record_type": {"const": "orchestrator-objective-decomposition"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "objective": _TEXT,
        "constraints": {
            "type": "array",
            "maxItems": 32,
            "uniqueItems": True,
            "items": _TEXT,
        },
        "status": {"type": "string", "enum": ["decomposed", "deferred", "blocked"]},
        "work_items": {"type": "array", "minItems": 7, "maxItems": 7, "items": _WORK_ITEM},
        "unknowns": _REF_LIST,
        "completion_authorized": {"const": False},
        "output_digest": _DIGEST,
    },
)

_NODE = {
    "type": "object",
    "required": ["work_item_id", "role", "position"],
    "properties": {"work_item_id": _ID, "role": {"type": "string", "enum": list(WORK_ROLES)}, "position": {"type": "integer", "minimum": 1, "maximum": 7}},
    "additionalProperties": False,
}
_EDGE = {
    "type": "object",
    "required": ["from", "to"],
    "properties": {"from": _ID, "to": _ID},
    "additionalProperties": False,
}
_GRAPH_SCHEMA = _object(
    "orchestrator-dependency-graph/v1",
    (
        "record_type", "schema_version", *_OUTPUT_SCOPE_REQUIRED, "nodes", "edges",
        "acyclic", "complete_predecessor_binding", "output_digest",
    ),
    {
        "record_type": {"const": "orchestrator-dependency-graph"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "nodes": {"type": "array", "minItems": 7, "maxItems": 7, "items": _NODE},
        "edges": {"type": "array", "minItems": 21, "maxItems": 21, "items": _EDGE},
        "acyclic": {"const": True},
        "complete_predecessor_binding": {"const": True},
        "output_digest": _DIGEST,
    },
)

_ALLOCATION = {
    "type": "object",
    "required": [*WORK_ROLES],
    "properties": {role: {"type": ["integer", "null"], "minimum": 0, "maximum": 1_000_000} for role in WORK_ROLES},
    "additionalProperties": False,
}
_BUDGET_SCHEMA = _object(
    "orchestrator-budget-plan/v1",
    (
        "record_type", "schema_version", *_OUTPUT_SCOPE_REQUIRED, "accounting_status",
        "ceilings", "rollback_reserve_ppm", "verification_reserve_ppm",
        "role_allocation_ppm", "lease_status", "completion_authorized", "output_digest",
    ),
    {
        "record_type": {"const": "orchestrator-budget-plan"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "accounting_status": {"type": "string", "enum": ["proposed", "unknown", "exhausted"]},
        "ceilings": _REQUEST_SCHEMA["properties"]["budgets"],
        "rollback_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 500_000},
        "verification_reserve_ppm": {"type": ["integer", "null"], "minimum": 1, "maximum": 500_000},
        "role_allocation_ppm": _ALLOCATION,
        "lease_status": {"const": "not-issued"},
        "completion_authorized": {"const": False},
        "output_digest": _DIGEST,
    },
)

_COURT_STAGE = {
    "type": "object",
    "required": [
        "position", "role", "actor_id", "actor_status", "required_before", "status",
    ],
    "properties": {
        "position": {"type": "integer", "minimum": 1, "maximum": 10},
        "role": {"type": "string", "enum": list(COURT_ROLES)},
        "actor_id": {"type": ["string", "null"], "minLength": 1, "maxLength": 256},
        "actor_status": {
            "type": "string",
            "enum": ["procedural-unverified", "unassigned"],
        },
        "required_before": _REF_LIST,
        "status": {"const": "pending"},
    },
    "additionalProperties": False,
}
_COURT_SCHEMA = _object(
    "orchestrator-court-schedule/v1",
    (
        "record_type", "schema_version", *_OUTPUT_SCOPE_REQUIRED, "stages",
        "independence_status", "authenticated_distinct_actors",
        "completion_authorized", "output_digest",
    ),
    {
        "record_type": {"const": "orchestrator-court-schedule"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "stages": {"type": "array", "minItems": 10, "maxItems": 10, "items": _COURT_STAGE},
        "independence_status": {"type": "string", "enum": ["procedural-only", "unknown"]},
        "authenticated_distinct_actors": {"const": False},
        "completion_authorized": {"const": False},
        "output_digest": _DIGEST,
    },
)

_RECOVERY_SCHEMA = _object(
    "orchestrator-recovery-plan/v1",
    (
        "record_type", "schema_version", *_OUTPUT_SCOPE_REQUIRED, "rollback_refs",
        "checkpoint_required", "preserve_evidence", "resume_authority",
        "activation_authorized", "output_digest",
    ),
    {
        "record_type": {"const": "orchestrator-recovery-plan"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "rollback_refs": _NONEMPTY_REFS,
        "checkpoint_required": {"const": True},
        "preserve_evidence": {"const": True},
        "resume_authority": {"const": "external-required"},
        "activation_authorized": {"const": False},
        "output_digest": _DIGEST,
    },
)

_STOP_SCHEMA = _object(
    "orchestrator-stop-decision/v1",
    (
        "record_type", "schema_version", *_OUTPUT_SCOPE_REQUIRED, "objective_state",
        "decision", "reasons", "progress_status", "budget_status", "recursion_status",
        "evidence_status", "completion_authorized", "output_digest",
    ),
    {
        "record_type": {"const": "orchestrator-stop-decision"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "objective_state": {
            "type": "string",
            "enum": ["proposed", "blocked", "recovering"],
        },
        "decision": {"type": "string", "enum": ["continue", "defer", "stop", "recover"]},
        "reasons": _NONEMPTY_REFS,
        "progress_status": {"type": "string", "enum": ["progressing", "stalled", "unknown"]},
        "budget_status": {"type": "string", "enum": ["available", "unknown", "exhausted"]},
        "recursion_status": {"type": "string", "enum": ["bounded", "limit-reached"]},
        "evidence_status": {
            "type": "string",
            "enum": ["claimed-unverified", "claims-incomplete", "unknown"],
        },
        "completion_authorized": {"const": False},
        "output_digest": _DIGEST,
    },
)

_HANDOFF_SCHEMA = _object(
    "orchestrator-handoff/v1",
    (
        "record_type", "schema_version", *_OUTPUT_SCOPE_REQUIRED, "next_role",
        "requested_next_role", "requested_role_eligible", "reason", "required_refs",
        "activation_authorized", "output_digest",
    ),
    {
        "record_type": {"const": "orchestrator-handoff"},
        "schema_version": {"const": 1},
        **_OUTPUT_SCOPE_PROPERTIES,
        "next_role": {"type": "string", "enum": [*WORK_ROLES, "orchestrator"]},
        "requested_next_role": {"type": ["string", "null"], "enum": [None, *WORK_ROLES, "orchestrator"]},
        "requested_role_eligible": {"type": "boolean"},
        "reason": _ID,
        "required_refs": {
            "type": "array",
            "maxItems": MAX_HANDOFF_REFS,
            "uniqueItems": True,
            "items": _ID,
        },
        "activation_authorized": {"const": False},
        "output_digest": _DIGEST,
    },
)

_OUTPUTS = {
    "type": "object",
    "required": ["objective_decomposition", "dependency_graph", "budget_plan", "court_schedule", "recovery_plan", "stop_decision", "handoff"],
    "properties": {
        "objective_decomposition": _DECOMPOSITION_SCHEMA,
        "dependency_graph": _GRAPH_SCHEMA,
        "budget_plan": _BUDGET_SCHEMA,
        "court_schedule": _COURT_SCHEMA,
        "recovery_plan": _RECOVERY_SCHEMA,
        "stop_decision": _STOP_SCHEMA,
        "handoff": _HANDOFF_SCHEMA,
    },
    "additionalProperties": False,
}
_ENVELOPE_SCHEMA = _object(
    "orchestrator-plan-envelope/v1",
    (
        "record_type", "schema_version", "request_id", "objective_id", "tenant_id",
        "repository_id", "successor_digest", "request_digest", "request_snapshot",
        "outputs", "plan_digest", "activation", "authority", "public",
    ),
    {
        "record_type": {"const": "orchestrator-plan-envelope"},
        "schema_version": {"const": 1},
        "request_id": _ID,
        "objective_id": _ID,
        "tenant_id": _ID,
        "repository_id": _ID,
        "successor_digest": _DIGEST,
        "request_digest": _DIGEST,
        "request_snapshot": _REQUEST_SCHEMA,
        "outputs": _OUTPUTS,
        "plan_digest": _DIGEST,
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
    },
)

_SCHEMAS: dict[str, dict[str, Any]] = {
    "orchestrator-agent-successor-v1": _SUCCESSOR_SCHEMA,
    "orchestrator-plan-request-v1": _REQUEST_SCHEMA,
    "orchestrator-objective-decomposition-v1": _DECOMPOSITION_SCHEMA,
    "orchestrator-dependency-graph-v1": _GRAPH_SCHEMA,
    "orchestrator-budget-plan-v1": _BUDGET_SCHEMA,
    "orchestrator-court-schedule-v1": _COURT_SCHEMA,
    "orchestrator-recovery-plan-v1": _RECOVERY_SCHEMA,
    "orchestrator-stop-decision-v1": _STOP_SCHEMA,
    "orchestrator-handoff-v1": _HANDOFF_SCHEMA,
    "orchestrator-plan-envelope-v1": _ENVELOPE_SCHEMA,
}


def load_orchestrator_schema(name: str) -> dict[str, Any]:
    if name not in _SCHEMAS:
        raise KeyError(f"unknown Orchestrator schema: {name}")
    return deepcopy(_SCHEMAS[name])


def _validate_digest(document: Mapping[str, Any], issues: list[str]) -> None:
    observed = document.get("output_digest")
    if observed is None:
        return
    body = {key: value for key, value in document.items() if key != "output_digest"}
    if observed != digest(body):
        issues.append("output digest does not bind the document")


def has_bounded_progress_cycle(values: list[str]) -> bool:
    length = len(values)
    if length < 2:
        return False
    for period in range(1, (length // 2) + 1):
        exact = values[-(2 * period) :]
        if len(exact) == 2 * period and all(
            exact[index] == exact[index - period]
            for index in range(period, len(exact))
        ):
            return True
        if length >= (2 * period) + 1:
            partial = values[-((2 * period) + 1) :]
            if all(
                partial[index] == partial[index - period]
                for index in range(period, len(partial))
            ):
                return True
    return False


def validate_orchestrator(
    name: str,
    document: Any,
    *,
    enforce_reviewed_successor: bool = True,
) -> FoundationValidation:
    try:
        schema = load_orchestrator_schema(name)
    except KeyError as error:
        return FoundationValidation(False, (str(error),))
    result = validate_document_against_schema(document, schema)
    issues = list(result.issues)
    if not isinstance(document, Mapping):
        return FoundationValidation(False, tuple(issues))

    if name == "orchestrator-agent-successor-v1" and not issues:
        layers = document["layers"]
        if tuple(layer["kind"] for layer in layers) != LAYER_KINDS:
            issues.append("successor layers must use the fixed canonical order")
        if tuple(layer["position"] for layer in layers) != tuple(range(1, 9)):
            issues.append("successor layer positions must be contiguous")
        if document["requested_capabilities"] != document["unsupported_capabilities"]:
            issues.append("requested capabilities must remain unsupported")
        expected_role_instructions = [
            {"role": role, "instruction": ROLE_INSTRUCTIONS[role]}
            for role in WORK_ROLES
        ]
        if document["playbook"]["role_instructions"] != expected_role_instructions:
            issues.append("successor role instructions differ from the canonical playbook")
        for layer in layers:
            layer_body = {
                key: value for key, value in layer.items() if key != "digest"
            }
            if layer["digest"] != digest(layer_body):
                issues.append(
                    f"successor layer {layer['position']} digest mismatch"
                )
        body = {key: value for key, value in document.items() if key != "content_digest"}
        if document["content_digest"] != digest(body):
            issues.append("successor content digest mismatch")
        if (
            enforce_reviewed_successor
            and document["content_digest"] != EXPECTED_SUCCESSOR_DIGEST
        ):
            issues.append("successor digest differs from the reviewed candidate")
    elif name == "orchestrator-plan-request-v1" and not issues:
        evidence = set(document["evidence_refs"])
        claim_refs = set(document["verification_claim_refs"])
        if not claim_refs.issubset(evidence):
            issues.append(
                "verification claims must be a subset of admitted evidence"
            )
        if any(actor["authenticated"] for actor in document["actors"]):
            issues.append("caller-supplied actor authentication is not admissible")
        actor_roles = [actor["role"] for actor in document["actors"]]
        actor_ids = [actor["actor_id"] for actor in document["actors"]]
        if len(actor_roles) != len(set(actor_roles)):
            issues.append("procedural actor roles must be unique")
        if len(actor_ids) != len(set(actor_ids)):
            issues.append("procedural actor identifiers must be unique")
        if document["recursion_depth"] != len(document["ancestry"]):
            issues.append("recursion depth must equal retained ancestry length")
        axes = tuple(document["budgets"].values())
        known = tuple(value is not None for value in axes)
        if any(known) and not all(known):
            issues.append("budget axes must be wholly known or wholly unknown")
        if all(known):
            if document["rollback_reserve_ppm"] is None or document["verification_reserve_ppm"] is None:
                issues.append("known budgets require rollback and verification reserves")
            else:
                available = (
                    1_000_000
                    - document["rollback_reserve_ppm"]
                    - document["verification_reserve_ppm"]
                )
                if available < len(WORK_ROLES):
                    issues.append("budget reserves must leave a positive allocation for every role")
        elif document["rollback_reserve_ppm"] is not None or document["verification_reserve_ppm"] is not None:
            issues.append("unknown budgets cannot claim exact reserves")
    elif name == "orchestrator-objective-decomposition-v1" and not issues:
        work_items = document["work_items"]
        roles = tuple(item["role"] for item in work_items)
        if roles != WORK_ROLES:
            issues.append("work items must use the fixed constitutional role order")
        work_ids = [item["work_item_id"] for item in work_items]
        if len(work_ids) != len(set(work_ids)):
            issues.append("work item identifiers must be unique")
        expected_evidence = work_items[0]["evidence_refs"]
        expected_rollback = work_items[0]["rollback_refs"]
        expected_acceptance = work_items[0]["acceptance_criteria"]
        expected_constraints = work_items[0]["constraints"]
        prior_ids: list[str] = []
        for item in work_items:
            if item["request_id"] != document["request_id"]:
                issues.append("work item request differs from decomposition request")
            if item["objective_id"] != document["objective_id"]:
                issues.append("work item objective differs from decomposition objective")
            if item["request_digest"] != document["request_digest"]:
                issues.append("work item request digest differs from decomposition request")
            if item["tenant_id"] != document["tenant_id"]:
                issues.append("work item tenant differs from decomposition tenant")
            if item["repository_id"] != document["repository_id"]:
                issues.append("work item repository differs from decomposition repository")
            if item["objective"] != document["objective"]:
                issues.append("work item objective text differs from decomposition objective")
            if item["instruction"] != ROLE_INSTRUCTIONS[item["role"]]:
                issues.append("work item instruction differs from the canonical role playbook")
            expected_id = stable_id(
                "phase5a-work",
                {
                    "request_digest": document["request_digest"],
                    "role": item["role"],
                },
            )
            if item["work_item_id"] != expected_id:
                issues.append("work item identifier is not bound to request and role")
            if item["dependencies"] != prior_ids:
                issues.append("work item dependencies must bind every prior role in order")
            if item["evidence_refs"] != expected_evidence:
                issues.append("work item evidence sets must remain identical")
            if item["rollback_refs"] != expected_rollback:
                issues.append("work item rollback sets must remain identical")
            if item["acceptance_criteria"] != expected_acceptance:
                issues.append("work item acceptance criteria must remain identical")
            if item["constraints"] != expected_constraints:
                issues.append("work item constraints must remain identical")
            prior_ids.append(item["work_item_id"])
    elif name == "orchestrator-dependency-graph-v1" and not issues:
        nodes = document["nodes"]
        if tuple(node["role"] for node in nodes) != WORK_ROLES:
            issues.append("dependency nodes must use the fixed constitutional role order")
        if tuple(node["position"] for node in nodes) != tuple(range(1, 8)):
            issues.append("dependency node positions must be contiguous")
        node_ids = [node["work_item_id"] for node in nodes]
        if len(node_ids) != len(set(node_ids)):
            issues.append("dependency node identifiers must be unique")
        expected_ids = {node["work_item_id"] for node in nodes}
        positions = {node["work_item_id"]: node["position"] for node in nodes}
        edges = {(edge["from"], edge["to"]) for edge in document["edges"]}
        if len(edges) != len(document["edges"]):
            issues.append("dependency edges must be unique")
        if any(source not in expected_ids or target not in expected_ids for source, target in edges):
            issues.append("dependency edge references an unknown node")
        if any(positions[source] >= positions[target] for source, target in edges if source in positions and target in positions):
            issues.append("dependency graph violates lifecycle order")
        expected_edges = {
            (source["work_item_id"], target["work_item_id"])
            for source in nodes
            for target in nodes
            if source["position"] < target["position"]
        }
        if edges != expected_edges:
            issues.append("dependency graph must bind every earlier role to every later role")
    elif name == "orchestrator-budget-plan-v1" and not issues:
        allocations = document["role_allocation_ppm"]
        values = tuple(allocations[role] for role in WORK_ROLES)
        ceilings = tuple(document["ceilings"].values())
        if document["accounting_status"] == "proposed":
            if any(value is None or value <= 0 for value in ceilings):
                issues.append("proposed budget requires positive known ceilings")
            if any(value is None for value in values):
                issues.append("proposed budget requires all role allocations")
            elif any(value <= 0 for value in values):
                issues.append("proposed budget requires a positive allocation for every role")
            elif (
                document["rollback_reserve_ppm"] is None
                or document["verification_reserve_ppm"] is None
            ):
                issues.append("proposed budget requires rollback and verification reserves")
            elif sum(values) + document["rollback_reserve_ppm"] + document["verification_reserve_ppm"] != 1_000_000:
                issues.append("budget allocations and reserves must total 1000000 ppm")
        elif document["accounting_status"] == "unknown":
            if any(value is not None for value in ceilings):
                issues.append("unknown budget requires all ceilings to remain null")
            if (
                document["rollback_reserve_ppm"] is not None
                or document["verification_reserve_ppm"] is not None
            ):
                issues.append("unknown budget cannot claim exact reserves")
            if any(value is not None for value in values):
                issues.append("unknown budget cannot fabricate allocations")
        else:
            if any(value is None for value in ceilings) or not any(
                value == 0 for value in ceilings
            ):
                issues.append("exhausted budget requires known ceilings with a zero axis")
            if any(value is not None for value in values):
                issues.append("exhausted budget cannot fabricate allocations")
    elif name == "orchestrator-court-schedule-v1" and not issues:
        stages = document["stages"]
        if tuple(stage["role"] for stage in stages) != COURT_ROLES:
            issues.append("court schedule must use the fixed constitutional order")
        if tuple(stage["position"] for stage in stages) != tuple(range(1, 11)):
            issues.append("court stage positions must be contiguous")
        prior_roles: list[str] = []
        actor_ids: list[str] = []
        for stage in stages:
            if stage["required_before"] != prior_roles:
                issues.append("court stages must bind every prior purpose in order")
            if stage["actor_id"] is None:
                if stage["actor_status"] != "unassigned":
                    issues.append("unassigned court stages must retain unassigned status")
            else:
                actor_ids.append(stage["actor_id"])
                if stage["actor_status"] != "procedural-unverified":
                    issues.append("assigned court actors must remain procedural and unverified")
            prior_roles.append(stage["role"])
        if len(actor_ids) != len(set(actor_ids)):
            issues.append("court actor identifiers must be unique")
        expected_independence = (
            "procedural-only" if len(actor_ids) == len(COURT_ROLES) else "unknown"
        )
        if document["independence_status"] != expected_independence:
            issues.append("court independence status differs from actor coverage")
    elif name == "orchestrator-stop-decision-v1" and not issues:
        if document["objective_state"] == "recovering":
            expected_decision = "recover"
        elif (
            document["objective_state"] == "blocked"
            or document["recursion_status"] == "limit-reached"
            or document["progress_status"] == "stalled"
            or document["budget_status"] == "exhausted"
        ):
            expected_decision = "stop"
        else:
            expected_decision = "defer"
        if document["decision"] != expected_decision:
            issues.append("stop decision differs from the controlling status fields")
    elif name == "orchestrator-plan-envelope-v1" and not issues:
        outputs = document["outputs"]
        for schema_name, field in (
            ("orchestrator-objective-decomposition-v1", "objective_decomposition"),
            ("orchestrator-dependency-graph-v1", "dependency_graph"),
            ("orchestrator-budget-plan-v1", "budget_plan"),
            ("orchestrator-court-schedule-v1", "court_schedule"),
            ("orchestrator-recovery-plan-v1", "recovery_plan"),
            ("orchestrator-stop-decision-v1", "stop_decision"),
            ("orchestrator-handoff-v1", "handoff"),
        ):
            nested = validate_orchestrator(schema_name, outputs[field])
            issues.extend(f"{field}: {issue}" for issue in nested.issues)
        if document["successor_digest"] != EXPECTED_SUCCESSOR_DIGEST:
            issues.append("plan successor digest differs from the reviewed candidate")
        request_snapshot = document["request_snapshot"]
        request_validation = validate_orchestrator(
            "orchestrator-plan-request-v1", request_snapshot
        )
        issues.extend(
            f"request_snapshot: {issue}" for issue in request_validation.issues
        )
        if digest(request_snapshot) != document["request_digest"]:
            issues.append("request snapshot does not match the envelope request digest")
        for scope_field in (
            "request_id",
            "objective_id",
            "tenant_id",
            "repository_id",
        ):
            if request_snapshot[scope_field] != document[scope_field]:
                issues.append(
                    f"request snapshot {scope_field} differs from the plan envelope"
                )
        expected_scope = {
            "request_id": request_snapshot["request_id"],
            "request_digest": document["request_digest"],
            "objective_id": request_snapshot["objective_id"],
            "tenant_id": request_snapshot["tenant_id"],
            "repository_id": request_snapshot["repository_id"],
        }
        for field, output in outputs.items():
            for scope_field, expected in expected_scope.items():
                if output[scope_field] != expected:
                    issues.append(
                        f"{field}: {scope_field} differs from the canonical request"
                    )

        decomposition = outputs["objective_decomposition"]
        graph = outputs["dependency_graph"]
        budget = outputs["budget_plan"]
        court = outputs["court_schedule"]
        recovery = outputs["recovery_plan"]
        stop = outputs["stop_decision"]
        handoff = outputs["handoff"]

        if decomposition["objective"] != request_snapshot["objective"]:
            issues.append("objective decomposition text differs from the canonical request")
        if decomposition["constraints"] != request_snapshot["constraints"]:
            issues.append("objective decomposition constraints differ from the canonical request")
        for item in decomposition["work_items"]:
            if item["objective"] != request_snapshot["objective"]:
                issues.append("work item objective text differs from the canonical request")
            if item["constraints"] != request_snapshot["constraints"]:
                issues.append("work item constraints differ from the canonical request")
            if item["acceptance_criteria"] != request_snapshot["acceptance_criteria"]:
                issues.append("work item acceptance criteria differ from the canonical request")
            if item["evidence_refs"] != request_snapshot["evidence_refs"]:
                issues.append("work item evidence differs from the canonical request")
            if item["rollback_refs"] != request_snapshot["rollback_refs"]:
                issues.append("work item rollback differs from the canonical request")

        expected_nodes = [
            {
                "work_item_id": item["work_item_id"],
                "role": item["role"],
                "position": index + 1,
            }
            for index, item in enumerate(decomposition["work_items"])
        ]
        if graph["nodes"] != expected_nodes:
            issues.append("dependency graph nodes differ from the objective decomposition")

        if budget["ceilings"] != request_snapshot["budgets"]:
            issues.append("budget ceilings differ from the canonical request")
        if budget["rollback_reserve_ppm"] != request_snapshot["rollback_reserve_ppm"]:
            issues.append("rollback reserve differs from the canonical request")
        if budget["verification_reserve_ppm"] != request_snapshot["verification_reserve_ppm"]:
            issues.append("verification reserve differs from the canonical request")
        request_budget_values = tuple(request_snapshot["budgets"].values())
        expected_allocations: dict[str, int | None] = {
            role: None for role in WORK_ROLES
        }
        if all(value is None for value in request_budget_values):
            expected_accounting = "unknown"
        elif any(value == 0 for value in request_budget_values):
            expected_accounting = "exhausted"
        else:
            expected_accounting = "proposed"
            available = (
                1_000_000
                - request_snapshot["rollback_reserve_ppm"]
                - request_snapshot["verification_reserve_ppm"]
            )
            quotient, remainder = divmod(available, len(WORK_ROLES))
            expected_allocations = {
                role: quotient + (1 if index < remainder else 0)
                for index, role in enumerate(WORK_ROLES)
            }
        if budget["accounting_status"] != expected_accounting:
            issues.append("budget accounting status differs from the canonical request")
        if budget["role_allocation_ppm"] != expected_allocations:
            issues.append("budget allocations differ from the canonical request")
        expected_budget_status = {
            "proposed": "available",
            "unknown": "unknown",
            "exhausted": "exhausted",
        }[expected_accounting]

        actors = {
            actor["role"]: actor["actor_id"] for actor in request_snapshot["actors"]
        }
        expected_actor_ids: list[str] = []
        for stage in court["stages"]:
            expected_actor = actors.get(stage["role"])
            if stage["actor_id"] != expected_actor:
                issues.append("court actor assignment differs from the canonical request")
            expected_actor_status = (
                "procedural-unverified" if expected_actor is not None else "unassigned"
            )
            if stage["actor_status"] != expected_actor_status:
                issues.append("court actor status differs from the canonical request")
            if expected_actor is not None:
                expected_actor_ids.append(expected_actor)
        expected_independence = (
            "procedural-only"
            if len(expected_actor_ids) == len(COURT_ROLES)
            else "unknown"
        )
        if court["independence_status"] != expected_independence:
            issues.append("court independence differs from the canonical request")

        progress_values = list(request_snapshot["progress_fingerprints"])
        expected_progress = (
            "unknown"
            if not progress_values
            else "stalled"
            if has_bounded_progress_cycle(progress_values)
            else "progressing"
        )
        expected_recursion = (
            "limit-reached"
            if request_snapshot["recursion_depth"] >= 8
            else "bounded"
        )
        evidence_refs = set(request_snapshot["evidence_refs"])
        claim_refs = set(request_snapshot["verification_claim_refs"])
        expected_evidence = (
            "unknown"
            if not evidence_refs
            else "claimed-unverified"
            if claim_refs == evidence_refs
            else "claims-incomplete"
        )
        if stop["objective_state"] != request_snapshot["objective_state"]:
            issues.append("stop objective state differs from the canonical request")
        if stop["progress_status"] != expected_progress:
            issues.append("stop progress status differs from the canonical request")
        if stop["budget_status"] != expected_budget_status:
            issues.append("stop budget status differs from the canonical request")
        if stop["recursion_status"] != expected_recursion:
            issues.append("stop recursion status differs from the canonical request")
        if stop["evidence_status"] != expected_evidence:
            issues.append("stop evidence status differs from the canonical request")

        expected_reasons: list[str] = []
        if expected_progress == "unknown":
            expected_reasons.append("progress-evidence-unknown")
        if expected_budget_status == "unknown":
            expected_reasons.append("budget-accounting-unknown")
        elif expected_budget_status == "exhausted":
            expected_reasons.append("budget-exhausted")
        expected_reasons.append(
            {
                "claimed-unverified": "evidence-verification-unavailable",
                "claims-incomplete": "evidence-claims-incomplete",
                "unknown": "evidence-unknown",
            }[expected_evidence]
        )
        if expected_independence != "procedural-only":
            expected_reasons.append("required-role-labels-incomplete")
        expected_reasons.append("authenticated-independence-unavailable")

        objective_state = request_snapshot["objective_state"]
        if objective_state == "recovering":
            expected_decision = "recover"
            expected_reasons.insert(0, "objective-recovery-required")
        elif objective_state == "blocked":
            expected_decision = "stop"
            expected_reasons.insert(0, "objective-blocked")
        elif expected_recursion == "limit-reached":
            expected_decision = "stop"
            expected_reasons.insert(0, "recursion-limit-reached")
        elif expected_progress == "stalled":
            expected_decision = "stop"
            expected_reasons.insert(0, "progress-loop-or-stall")
        elif expected_budget_status == "exhausted":
            expected_decision = "stop"
        else:
            expected_decision = "defer"
        if stop["decision"] != expected_decision:
            issues.append("stop decision differs from the canonical request")
        if stop["reasons"] != expected_reasons:
            issues.append("stop reasons differ from the canonical request")

        expected_decomposition_status = {
            "stop": "blocked",
            "defer": "deferred",
            "recover": "deferred",
            "continue": "decomposed",
        }[expected_decision]
        if decomposition["status"] != expected_decomposition_status:
            issues.append("objective decomposition status differs from the stop decision")
        expected_unknowns = [
            reason
            for reason in expected_reasons
            if (
                "unknown" in reason
                or "unavailable" in reason
                or "incomplete" in reason
            )
        ]
        if decomposition["unknowns"] != expected_unknowns:
            issues.append("objective decomposition unknowns differ from the stop reasons")

        if recovery["rollback_refs"] != request_snapshot["rollback_refs"]:
            issues.append("recovery rollback set differs from the canonical request")
        if handoff["requested_next_role"] != request_snapshot["requested_next_role"]:
            issues.append("handoff requested role differs from the canonical request")
        if (
            expected_decision in {"stop", "recover"}
            or expected_progress == "stalled"
            or expected_recursion == "limit-reached"
        ):
            expected_role, expected_reason = "steward", "recovery-or-stop-review"
        elif expected_evidence in {"unknown", "claims-incomplete"}:
            expected_role, expected_reason = "explorer", "evidence-gap-review"
        elif expected_budget_status != "available":
            expected_role, expected_reason = "steward", "budget-boundary-review"
        elif expected_evidence == "claimed-unverified" or expected_independence in {
            "procedural-only",
            "unknown",
        }:
            expected_role, expected_reason = (
                "curator",
                "independence-and-evidence-review",
            )
        else:
            expected_role, expected_reason = "explorer", "next-lifecycle-stage"
        if (handoff["next_role"], handoff["reason"]) != (
            expected_role,
            expected_reason,
        ):
            issues.append("handoff differs from the canonical request and stop state")
        if handoff["requested_role_eligible"] != (
            request_snapshot["requested_next_role"] == expected_role
        ):
            issues.append("handoff eligibility differs from the canonical request")
        expected_required_refs = sorted(
            set(request_snapshot["evidence_refs"])
            | set(request_snapshot["rollback_refs"])
            | set(expected_reasons)
        )
        if handoff["required_refs"] != expected_required_refs:
            issues.append("handoff required refs differ from the canonical request")
        body = {key: value for key, value in document.items() if key != "plan_digest"}
        if document["plan_digest"] != digest(body):
            issues.append("plan digest mismatch")
    _validate_digest(document, issues)

    return FoundationValidation(not issues, tuple(dict.fromkeys(issues)))


def validate_orchestrator_catalog() -> FoundationValidation:
    issues: list[str] = []
    ids: set[str] = set()
    for name in ORCHESTRATOR_SCHEMA_NAMES:
        schema = load_orchestrator_schema(name)
        schema_id = schema.get("$id")
        if schema_id in ids:
            issues.append(f"{name}: duplicate $id")
        ids.add(str(schema_id))
        if schema.get("$schema") != DIALECT:
            issues.append(f"{name}: wrong dialect")
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            issues.append(f"{name}: root must be a fail-closed object")
    return FoundationValidation(not issues, tuple(issues))
