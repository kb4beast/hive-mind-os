from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from .contracts import FoundationValidation, validate_document_against_schema

FEDERATION_SCHEMA_NAMES = (
    "federated-note-v1",
    "federation-manifest-v1",
    "federation-result-v1",
    "self-host-context-v1",
    "self-host-decision-v1",
)


def load_federation_schema(name: str) -> dict[str, Any]:
    if name not in FEDERATION_SCHEMA_NAMES:
        raise KeyError(f"unknown federation schema: {name}")
    resource = files("hive_mind_os.foundation").joinpath(
        "federation_schemas",
        f"{name}.schema.json",
    )
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{name} schema is not an object")
    return document


def validate_federation(name: str, document: Any) -> FoundationValidation:
    try:
        schema = load_federation_schema(name)
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return FoundationValidation(
            False,
            (f"schema unavailable: {type(error).__name__}: {error}",),
        )
    return validate_document_against_schema(document, schema)


def validate_federation_catalog() -> FoundationValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in FEDERATION_SCHEMA_NAMES:
        try:
            schema = load_federation_schema(name)
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
        if (
            schema.get("type") != "object"
            or schema.get("additionalProperties") is not False
        ):
            issues.append(f"{name}: root must be a fail-closed object")
    return FoundationValidation(not issues, tuple(issues))
