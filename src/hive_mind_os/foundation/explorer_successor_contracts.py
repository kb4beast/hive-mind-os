from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import digest
from .contracts import FoundationValidation, validate_document_against_schema

EXPLORER_SUCCESSOR_SCHEMA_NAME = "explorer-agent-successor-v1"
EXPECTED_SUCCESSOR_DIGEST = (
    "sha256:0494c32237fbbe83b90444c9b0496646e8f0b27e7c20379320a6bd7241697463"
)
_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_DIGEST = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
_ID = {"type": "string", "minLength": 1, "maxLength": 200}
_STRING_LIST = {
    "type": "array",
    "minItems": 1,
    "maxItems": 64,
    "uniqueItems": True,
    "items": _ID,
}
_LAYER_KINDS = (
    "base",
    "prompt",
    "playbook",
    "skills",
    "context",
    "output",
    "admission",
    "lifecycle",
)
_LAYER = {
    "type": "object",
    "required": [
        "position",
        "layer_id",
        "kind",
        "version",
        "digest",
        "source_digests",
    ],
    "properties": {
        "position": {"type": "integer", "minimum": 1, "maximum": 8},
        "layer_id": _ID,
        "kind": {"type": "string", "enum": list(_LAYER_KINDS)},
        "version": _ID,
        "digest": _DIGEST,
        "source_digests": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "uniqueItems": True,
            "items": _DIGEST,
        },
    },
    "additionalProperties": False,
}
_SCHEMA: dict[str, Any] = {
    "$schema": _DIALECT,
    "$id": "https://hive-mind-os.invalid/contracts/explorer-agent-successor/v1",
    "type": "object",
    "required": [
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
    ],
    "properties": {
        "record_type": {"const": "explorer-agent-successor"},
        "schema_version": {"const": 1},
        "agent_id": {"const": "hive-agent:explorer:v2-shadow-1"},
        "definition_id": {
            "const": "hive-agent-definition:explorer:v2-shadow-1"
        },
        "role_id": {"const": "explorer"},
        "version": {"const": "2-shadow-1"},
        "status": {"const": "candidate"},
        "lineage_relation": {"const": "extends-inert"},
        "base_definition_ref": {
            "const": "hive-agent-definition:explorer:v2-candidate"
        },
        "rollback_ref": {
            "const": "hive-agent-definition:explorer:v2-candidate"
        },
        "content_digest": _DIGEST,
        "layers": {
            "type": "array",
            "minItems": 8,
            "maxItems": 8,
            "items": _LAYER,
        },
        "requested_capabilities": _STRING_LIST,
        "effective_capabilities": {"type": "array", "maxItems": 0},
        "unsupported_capabilities": _STRING_LIST,
        "tool_refs": {"type": "array", "maxItems": 0},
        "input_contract_refs": _STRING_LIST,
        "output_contract_refs": _STRING_LIST,
        "workflow_refs": _STRING_LIST,
        "budgets": {
            "type": "object",
            "required": [
                "max_context_records",
                "max_context_bytes",
                "max_findings",
                "max_nested_values",
                "max_engine_calls",
            ],
            "properties": {
                "max_context_records": {"const": 256},
                "max_context_bytes": {"const": 1_000_000},
                "max_findings": {"const": 64},
                "max_nested_values": {"const": 64},
                "max_engine_calls": {"const": 1},
            },
            "additionalProperties": False,
        },
        "playbook": {
            "type": "object",
            "required": [
                "lenses",
                "discovery_modes",
                "idea_lifecycle",
                "cross_domain_fields",
                "stop_conditions",
                "prohibited_actions",
            ],
            "properties": {
                "lenses": _STRING_LIST,
                "discovery_modes": _STRING_LIST,
                "idea_lifecycle": _STRING_LIST,
                "cross_domain_fields": _STRING_LIST,
                "stop_conditions": _STRING_LIST,
                "prohibited_actions": _STRING_LIST,
            },
            "additionalProperties": False,
        },
        "governance": {
            "type": "object",
            "required": [
                "source_refs",
                "court_refs",
                "dissent_ref",
                "activation_prerequisites",
            ],
            "properties": {
                "source_refs": _STRING_LIST,
                "court_refs": _STRING_LIST,
                "dissent_ref": _ID,
                "activation_prerequisites": _STRING_LIST,
            },
            "additionalProperties": False,
        },
        "activation": {"const": "inert"},
        "authority": {"const": "none"},
        "public": {"const": False},
    },
    "additionalProperties": False,
}


def load_explorer_successor_schema() -> dict[str, Any]:
    return deepcopy(_SCHEMA)


def validate_explorer_successor(document: Any) -> FoundationValidation:
    structural = validate_document_against_schema(
        document, load_explorer_successor_schema()
    )
    if not structural.valid:
        return structural
    issues: list[str] = []
    layers = document["layers"]
    if tuple(layer["kind"] for layer in layers) != _LAYER_KINDS:
        issues.append("successor layers must use the fixed canonical order")
    if tuple(layer["position"] for layer in layers) != tuple(range(1, 9)):
        issues.append("successor layer positions must be contiguous")
    if len({layer["layer_id"] for layer in layers}) != len(layers):
        issues.append("successor layer IDs must be unique")
    for layer in layers:
        layer_body = {
            key: value for key, value in layer.items() if key != "digest"
        }
        if layer["digest"] != digest(layer_body):
            issues.append(
                f"successor layer digest does not match its body: {layer['kind']}"
            )
    if document["requested_capabilities"] != document["unsupported_capabilities"]:
        issues.append("every inherited capability request must remain unsupported")
    if document["effective_capabilities"] or document["tool_refs"]:
        issues.append("inert successor cannot have effective capabilities or tools")
    body = {key: value for key, value in document.items() if key != "content_digest"}
    if document["content_digest"] != digest(body):
        issues.append("successor content_digest does not match its body")
    if document["content_digest"] != EXPECTED_SUCCESSOR_DIGEST:
        issues.append("successor differs from its reviewed fixed-identity digest")
    return FoundationValidation(not issues, tuple(issues))


def validate_explorer_successor_catalog() -> FoundationValidation:
    schema = load_explorer_successor_schema()
    issues: list[str] = []
    if schema.get("$schema") != _DIALECT:
        issues.append("successor schema uses the wrong dialect")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        issues.append("successor schema root must be a fail-closed object")
    return FoundationValidation(not issues, tuple(issues))
