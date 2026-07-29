from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from .contracts import FoundationValidation, validate_document_against_schema

PROJECTION_SCHEMA_NAMES = (
    "brain-conflict-v1",
    "brain-failure-v1",
    "brain-manifest-v1",
    "brain-note-v1",
    "brain-receipt-v1",
    "brain-result-v1",
    "brain-transaction-v1",
)


def load_projection_schema(name: str) -> dict[str, Any]:
    if name not in PROJECTION_SCHEMA_NAMES:
        raise KeyError(f"unknown projection schema: {name}")
    resource = files("hive_mind_os.foundation").joinpath(
        "projection_schemas",
        f"{name}.schema.json",
    )
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{name} schema is not an object")
    return document


def validate_projection(name: str, document: Any) -> FoundationValidation:
    try:
        schema = load_projection_schema(name)
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return FoundationValidation(
            False,
            (f"schema unavailable: {type(error).__name__}: {error}",),
        )
    return validate_document_against_schema(document, schema)


def validate_projection_catalog() -> FoundationValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in PROJECTION_SCHEMA_NAMES:
        try:
            schema = load_projection_schema(name)
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
