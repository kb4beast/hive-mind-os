from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, Mapping

PHASE2_SCHEMA_NAMES = (
    "agent-definition-v2",
    "budget-lease-record-v1",
    "decision-record-v1",
    "idea-encounter-v1",
    "loop-signal-v1",
    "memory-record-v1",
    "opportunity-record-v1",
    "outcome-attribution-record-v1",
    "outbox-record-v1",
    "prompt-composition-v2",
    "quarantine-record-v1",
    "repository-identity-v1",
    "role-constitution-v2",
    "skill-definition-v2",
    "typed-output-v1",
    "usage-event-v1",
    "usage-reconciliation-v1",
)


@dataclass(frozen=True, slots=True)
class FoundationValidation:
    valid: bool
    issues: tuple[str, ...] = ()


def load_foundation_schema(name: str) -> dict[str, Any]:
    if name not in PHASE2_SCHEMA_NAMES:
        raise KeyError(f"unknown foundation schema: {name}")
    resource = files("hive_mind_os.foundation").joinpath("schemas", f"{name}.schema.json")
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{name} schema is not an object")
    return document


def _type_matches(value: Any, expected: str) -> bool:
    return {
        "array": isinstance(value, list),
        "boolean": type(value) is bool,
        "integer": type(value) is int,
        "null": value is None,
        "number": type(value) in {int, float},
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
    }.get(expected, False)


def _validate(value: Any, schema: Mapping[str, Any], path: str, issues: list[str]) -> None:
    expected = schema.get("type")
    if isinstance(expected, str) and not _type_matches(value, expected):
        issues.append(f"{path}: expected {expected}")
        return
    if isinstance(expected, list) and not any(
        isinstance(item, str) and _type_matches(value, item) for item in expected
    ):
        issues.append(f"{path}: expected one of {expected}")
        return
    if "const" in schema and value != schema["const"]:
        issues.append(f"{path}: value does not match const")
    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        issues.append(f"{path}: value is not in enum")
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            issues.append(f"{path}: string is too short")
        if isinstance(schema.get("maxLength"), int) and len(value) > schema["maxLength"]:
            issues.append(f"{path}: string is too long")
        if isinstance(schema.get("pattern"), str) and re.search(schema["pattern"], value) is None:
            issues.append(f"{path}: string does not match pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if (
            isinstance(minimum, (int, float))
            and not isinstance(minimum, bool)
            and value < minimum
        ):
            issues.append(f"{path}: number is below minimum {minimum}")
        maximum = schema.get("maximum")
        if (
            isinstance(maximum, (int, float))
            and not isinstance(maximum, bool)
            and value > maximum
        ):
            issues.append(f"{path}: number is above maximum {maximum}")
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            issues.append(f"{path}: array has too few items")
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            issues.append(f"{path}: array has too many items")
        if schema.get("uniqueItems") is True:
            encoded = [json.dumps(item, sort_keys=True, separators=(",", ":")) for item in value]
            if len(encoded) != len(set(encoded)):
                issues.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate(item, item_schema, f"{path}[{index}]", issues)
    if isinstance(value, dict):
        required = schema.get("required", ())
        if isinstance(required, list):
            for name in required:
                if isinstance(name, str) and name not in value:
                    issues.append(f"{path}: missing required property {name}")
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for name, child_schema in properties.items():
                if name in value and isinstance(child_schema, Mapping):
                    _validate(value[name], child_schema, f"{path}.{name}", issues)
            if schema.get("additionalProperties") is False:
                unknown = sorted(set(value) - set(properties))
                if unknown:
                    issues.append(f"{path}: unknown properties: {', '.join(unknown)}")


def validate_foundation(name: str, document: Any) -> FoundationValidation:
    try:
        schema = load_foundation_schema(name)
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return FoundationValidation(False, (f"schema unavailable: {type(error).__name__}: {error}",))
    result = validate_document_against_schema(document, schema)
    issues = list(result.issues)
    if name == "outcome-attribution-record-v1" and isinstance(document, Mapping):
        for field in ("purpose_allocations_ppm", "resource_allocations_ppm"):
            allocations = document.get(field)
            if allocations == {"unknown": True}:
                continue
            if not isinstance(allocations, Mapping) or not allocations:
                issues.append(f"$.{field}: allocations must total 1000000 ppm or be unknown")
                continue
            values = list(allocations.values())
            if not all(type(value) is int and value >= 0 for value in values):
                issues.append(f"$.{field}: allocations must be nonnegative integers")
            elif sum(values) != 1_000_000:
                issues.append(f"$.{field}: allocations must total 1000000 ppm")
        if document.get("outcome") == "avoidable-waste" and not document.get(
            "reviewed_by"
        ):
            issues.append("$: avoidable-waste requires independent review")
    return FoundationValidation(not issues, tuple(dict.fromkeys(issues)))


def validate_document_against_schema(
    document: Any,
    schema: Mapping[str, Any],
) -> FoundationValidation:
    issues: list[str] = []
    _validate(document, schema, "$", issues)
    return FoundationValidation(not issues, tuple(dict.fromkeys(issues)))


def validate_foundation_catalog() -> FoundationValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in PHASE2_SCHEMA_NAMES:
        try:
            schema = load_foundation_schema(name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            issues.append(f"{name}: {type(error).__name__}: {error}")
            continue
        identifier = schema.get("$id")
        if not isinstance(identifier, str) or not identifier:
            issues.append(f"{name}: missing $id")
        elif identifier in identifiers:
            issues.append(f"{name}: duplicate $id")
        else:
            identifiers.add(identifier)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            issues.append(f"{name}: wrong dialect")
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            issues.append(f"{name}: root must be a fail-closed object")
    return FoundationValidation(not issues, tuple(issues))
