from __future__ import annotations

from typing import Any

from .contracts import FoundationValidation, validate_document_against_schema

EXPLORER_SCHEMA_NAMES = (
    "explorer-context-selection-v1",
    "explorer-shadow-run-v1",
)
_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_DIGEST = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
_ID = {"type": "string", "minLength": 1, "maxLength": 200}
_ID_LIST = {
    "type": "array",
    "maxItems": 256,
    "uniqueItems": True,
    "items": _ID,
}
_OMISSION = {
    "type": "object",
    "required": ["memory_id", "reason"],
    "properties": {
        "memory_id": _ID,
        "reason": {
            "type": "string",
            "enum": [
                "budget",
                "quarantined",
                "same-run-recursion",
                "generated-recursion",
            ],
        },
    },
    "additionalProperties": False,
}
_OUTCOME = {
    "type": "object",
    "required": [
        "finding_id",
        "encounter_record_id",
        "opportunity_record_id",
        "classification",
    ],
    "properties": {
        "finding_id": _ID,
        "encounter_record_id": _ID,
        "opportunity_record_id": {"type": ["string", "null"], "maxLength": 200},
        "classification": _ID,
    },
    "additionalProperties": False,
}
_SCHEMAS: dict[str, dict[str, Any]] = {
    "explorer-context-selection-v1": {
        "$schema": _DIALECT,
        "$id": "https://hive-mind-os.invalid/contracts/explorer-context-selection/v1",
        "type": "object",
        "required": [
            "record_type",
            "schema_version",
            "run_id",
            "tenant_id",
            "repository_id",
            "request_digest",
            "cutoff_sequence",
            "inventory_digest",
            "selection_digest",
            "skill_bundle_digest",
            "selected_ids",
            "omitted",
            "ordering",
            "selected_bytes",
            "purpose",
            "critical_context_coverage",
            "status",
        ],
        "properties": {
            "record_type": {"const": "explorer-context-selection"},
            "schema_version": {"const": 1},
            "run_id": _ID,
            "tenant_id": _ID,
            "repository_id": _ID,
            "request_digest": _DIGEST,
            "cutoff_sequence": {"type": "integer", "minimum": 0},
            "inventory_digest": _DIGEST,
            "selection_digest": _DIGEST,
            "skill_bundle_digest": _DIGEST,
            "selected_ids": {**_ID_LIST, "minItems": 9},
            "omitted": {"type": "array", "maxItems": 256, "items": _OMISSION},
            "ordering": {**_ID_LIST, "minItems": 9},
            "selected_bytes": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
            },
            "purpose": {"type": "string", "minLength": 1, "maxLength": 500},
            "critical_context_coverage": {"const": "complete"},
            "status": {"const": "sealed"},
        },
        "additionalProperties": False,
    },
    "explorer-shadow-run-v1": {
        "$schema": _DIALECT,
        "$id": "https://hive-mind-os.invalid/contracts/explorer-shadow-run/v1",
        "type": "object",
        "required": [
            "record_type",
            "schema_version",
            "run_id",
            "tenant_id",
            "repository_id",
            "request_digest",
            "selection_record_id",
            "selection_digest",
            "skill_bundle_digest",
            "engine_id",
            "status",
            "outcomes",
            "error_code",
        ],
        "properties": {
            "record_type": {"const": "explorer-shadow-run"},
            "schema_version": {"const": 1},
            "run_id": _ID,
            "tenant_id": _ID,
            "repository_id": _ID,
            "request_digest": _DIGEST,
            "selection_record_id": {"type": ["string", "null"], "maxLength": 200},
            "selection_digest": {
                "type": ["string", "null"],
                "pattern": "^sha256:[0-9a-f]{64}$",
            },
            "skill_bundle_digest": _DIGEST,
            "engine_id": _ID,
            "status": {"type": "string", "enum": ["succeeded", "failed"]},
            "outcomes": {"type": "array", "maxItems": 64, "items": _OUTCOME},
            "error_code": {"type": ["string", "null"], "maxLength": 200},
        },
        "additionalProperties": False,
    },
}


def load_explorer_schema(name: str) -> dict[str, Any]:
    if name not in EXPLORER_SCHEMA_NAMES:
        raise KeyError(f"unknown Explorer schema: {name}")
    return _SCHEMAS[name]


def validate_explorer(name: str, document: Any) -> FoundationValidation:
    try:
        schema = load_explorer_schema(name)
    except KeyError as error:
        return FoundationValidation(False, (f"schema unavailable: KeyError: {error}",))
    return validate_document_against_schema(document, schema)


def validate_explorer_catalog() -> FoundationValidation:
    identifiers: set[str] = set()
    issues: list[str] = []
    for name in EXPLORER_SCHEMA_NAMES:
        schema = load_explorer_schema(name)
        identifier = schema.get("$id")
        if not isinstance(identifier, str) or not identifier:
            issues.append(f"{name}: missing $id")
        elif identifier in identifiers:
            issues.append(f"{name}: duplicate $id")
        else:
            identifiers.add(identifier)
        if schema.get("$schema") != _DIALECT:
            issues.append(f"{name}: wrong dialect")
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            issues.append(f"{name}: root must be a fail-closed object")
    return FoundationValidation(not issues, tuple(issues))
