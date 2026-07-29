from __future__ import annotations

import json
import re
from importlib.resources import files
from typing import Any

from .contracts import FoundationValidation, validate_document_against_schema

COGNITIVE_VIEW_SCHEMA_NAMES = (
    "cognitive-view-base-v1",
    "cognitive-view-canvas-v1",
    "cognitive-view-conflict-v1",
    "cognitive-view-failure-v1",
    "cognitive-view-manifest-v1",
    "cognitive-view-receipt-v1",
    "cognitive-view-result-v1",
    "cognitive-view-transaction-v1",
)
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_BASE_FOLDERS = {
    "hive-mind/generated-cognitive",
    "hive-mind/generated-cognitive/agents",
    "hive-mind/generated-cognitive/ideas",
    "hive-mind/generated-cognitive/telemetry",
}
_BASE_CONSTANT_FILTERS = {
    'schema_version == "hive-cognitive-note/v1"',
    'generator_version == "hive-cognitive-projector/v1"',
    'mapping_version == "hive-cognitive-mapping/v1"',
    'sensitivity == "safe-public"',
    "is_generated == true",
    "is_authoritative == false",
}
_CANVAS_FILES = {
    "hive-mind/generated-cognitive-views/bases/agent-records.base",
    "hive-mind/generated-cognitive-views/bases/ideas.base",
    "hive-mind/generated-cognitive-views/bases/released-war-room.base",
    "hive-mind/generated-cognitive-views/bases/telemetry-metadata.base",
}
_MANIFEST_FILES = {
    "bases/agent-records.base": ("base", "agent-records"),
    "bases/ideas.base": ("base", "ideas"),
    "bases/released-war-room.base": ("base", "released-war-room"),
    "bases/telemetry-metadata.base": ("base", "telemetry-metadata"),
    "canvases/war-room.canvas": (
        "canvas",
        "war-room-navigation-and-limitations",
    ),
}


def load_cognitive_view_schema(name: str) -> dict[str, Any]:
    if name not in COGNITIVE_VIEW_SCHEMA_NAMES:
        raise KeyError(f"unknown cognitive view schema: {name}")
    resource = files("hive_mind_os.foundation").joinpath(
        "generated",
        f"{name}.schema.json",
    )
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{name} schema is not an object")
    return document


def validate_cognitive_view(name: str, document: Any) -> FoundationValidation:
    try:
        schema = load_cognitive_view_schema(name)
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return FoundationValidation(
            False,
            (f"schema unavailable: {type(error).__name__}: {error}",),
        )
    validation = validate_document_against_schema(document, schema)
    if not validation.valid or not isinstance(document, dict):
        return validation
    issues = list(validation.issues)
    if name == "cognitive-view-base-v1":
        filters = document["filters"]["and"]
        folder_filters = [
            item
            for item in filters
            if item.startswith('file.inFolder("') and item.endswith('")')
        ]
        identity_filters = [
            item
            for item in filters
            if item.startswith('repository_identity_digest == "') and item.endswith('"')
        ]
        folder_value = (
            folder_filters[0].removeprefix('file.inFolder("').removesuffix('")')
            if len(folder_filters) == 1
            else ""
        )
        identity_value = (
            identity_filters[0]
            .removeprefix('repository_identity_digest == "')
            .removesuffix('"')
            if len(identity_filters) == 1
            else ""
        )
        if (
            len(folder_filters) != 1
            or folder_value not in _BASE_FOLDERS
            or len(identity_filters) != 1
            or not _DIGEST.fullmatch(identity_value)
            or set(filters)
            != _BASE_CONSTANT_FILTERS | {folder_filters[0], identity_filters[0]}
        ):
            issues.append("Base filters are outside the owned fixed subset")
        order = document["views"][0]["order"]
        if len(order) != len(set(order)) or any(
            item not in document["properties"] for item in order
        ):
            issues.append("Base order is inconsistent with declared properties")
    elif name == "cognitive-view-canvas-v1":
        nodes = document["nodes"]
        identifiers = [node["id"] for node in nodes]
        if len(identifiers) != len(set(identifiers)):
            issues.append("Canvas node IDs are not unique")
        file_targets = {node["file"] for node in nodes if node["type"] == "file"}
        if file_targets != _CANVAS_FILES:
            issues.append("Canvas file targets are outside the owned Base set")
        if any(
            (
                node["type"] == "text"
                and set(node) != {"id", "type", "x", "y", "width", "height", "text"}
            )
            or (
                node["type"] == "file"
                and set(node) != {"id", "type", "x", "y", "width", "height", "file"}
            )
            for node in nodes
        ):
            issues.append("Canvas node keys do not match their type")
    elif name == "cognitive-view-manifest-v1":
        entries = document["files"]
        observed = {
            entry["path"]: (entry["kind"], entry["semantic_role"]) for entry in entries
        }
        if observed != _MANIFEST_FILES or len(entries) != len(observed):
            issues.append("view manifest file roles are not exact")
    elif name in {
        "cognitive-view-receipt-v1",
        "cognitive-view-transaction-v1",
    }:
        paths = [operation["path"] for operation in document["operations"]]
        if len(paths) != len(set(paths)) or paths[-1] != "manifest.json":
            issues.append("view operation paths are duplicate or manifest is not last")
    return FoundationValidation(not issues, tuple(issues))


def validate_cognitive_view_catalog() -> FoundationValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in COGNITIVE_VIEW_SCHEMA_NAMES:
        try:
            schema = load_cognitive_view_schema(name)
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
