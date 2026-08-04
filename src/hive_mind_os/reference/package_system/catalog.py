from __future__ import annotations

import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .models import (
    AgentManifest,
    CatalogSnapshot,
    ComponentKind,
    ComponentManifest,
    ComponentRef,
    FileRecord,
    LicenseStatus,
    LoadedPackage,
    PackageManifest,
    PackagePin,
    SkillManifest,
    ToolManifest,
    TrustState,
    WorkflowManifest,
    WorkflowTransition,
    canonical_json_bytes,
    content_digest,
)

_MANIFEST_NAME = "package.json"
_MAX_JSON_BYTES = 4 * 1024 * 1024


class PackageValidationError(ValueError):
    """A fail-closed rejection of an inert package."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PackageValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise PackageValidationError(
            f"could not read {path.name}: {type(error).__name__}"
        ) from error
    if len(content) > _MAX_JSON_BYTES:
        raise PackageValidationError(f"{path.name} exceeds the JSON size limit")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PackageValidationError(f"{path.name} is not UTF-8") from error
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(
                PackageValidationError(f"non-finite JSON number: {value}")
            ),
        )
    except (json.JSONDecodeError, RecursionError) as error:
        raise PackageValidationError(f"{path.name} is not strict JSON") from error
    if not isinstance(document, dict):
        raise PackageValidationError(f"{path.name} must contain a JSON object")
    return document, content


def _expect_keys(
    document: dict[str, Any],
    *,
    required: frozenset[str],
    label: str,
) -> None:
    missing = required - document.keys()
    unknown = document.keys() - required
    if missing:
        raise PackageValidationError(
            f"{label} missing fields: {', '.join(sorted(missing))}"
        )
    if unknown:
        raise PackageValidationError(
            f"{label} unknown fields: {', '.join(sorted(unknown))}"
        )


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise PackageValidationError(f"{label} must be a string")
    return value


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise PackageValidationError(f"{label} must be a boolean")
    return value


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PackageValidationError(f"{label} must be an array of strings")
    return tuple(value)


def _pin(document: Any, label: str) -> PackagePin:
    if not isinstance(document, dict):
        raise PackageValidationError(f"{label} must be an object")
    _expect_keys(
        document,
        required=frozenset({"package_id", "version", "manifest_digest"}),
        label=label,
    )
    try:
        return PackagePin(
            package_id=_string(document["package_id"], f"{label}.package_id"),
            version=_string(document["version"], f"{label}.version"),
            manifest_digest=_string(
                document["manifest_digest"], f"{label}.manifest_digest"
            ),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


def _pins(value: Any, label: str) -> tuple[PackagePin, ...]:
    if not isinstance(value, list):
        raise PackageValidationError(f"{label} must be an array")
    return tuple(_pin(item, f"{label}[{index}]") for index, item in enumerate(value))


def _component_ref(document: Any, label: str) -> ComponentRef:
    if not isinstance(document, dict):
        raise PackageValidationError(f"{label} must be an object")
    _expect_keys(
        document,
        required=frozenset({"component_id", "kind", "manifest_path"}),
        label=label,
    )
    try:
        kind = ComponentKind(_string(document["kind"], f"{label}.kind"))
        return ComponentRef(
            component_id=_string(document["component_id"], f"{label}.component_id"),
            kind=kind,
            manifest_path=_string(document["manifest_path"], f"{label}.manifest_path"),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


def _file_record(document: Any, label: str) -> FileRecord:
    if not isinstance(document, dict):
        raise PackageValidationError(f"{label} must be an object")
    _expect_keys(
        document,
        required=frozenset({"path", "digest", "media_type"}),
        label=label,
    )
    try:
        return FileRecord(
            path=_string(document["path"], f"{label}.path"),
            digest=_string(document["digest"], f"{label}.digest"),
            media_type=_string(document["media_type"], f"{label}.media_type"),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


def _package_manifest(document: dict[str, Any]) -> PackageManifest:
    required = frozenset(
        {
            "schema_version",
            "package_id",
            "version",
            "license",
            "license_status",
            "trust_state",
            "source_refs",
            "court_case_refs",
            "components",
            "files",
            "requires",
            "replaces",
            "rollback_to",
        }
    )
    _expect_keys(document, required=required, label="package manifest")
    if type(document["schema_version"]) is not int:
        raise PackageValidationError("schema_version must be an integer")
    raw_components = document["components"]
    raw_files = document["files"]
    if not isinstance(raw_components, list) or not isinstance(raw_files, list):
        raise PackageValidationError("components and files must be arrays")
    rollback = document["rollback_to"]
    if rollback is not None:
        rollback = _pin(rollback, "rollback_to")
    try:
        license_status = LicenseStatus(
            _string(document["license_status"], "license_status")
        )
        trust_state = TrustState(_string(document["trust_state"], "trust_state"))
        return PackageManifest(
            schema_version=document["schema_version"],
            package_id=_string(document["package_id"], "package_id"),
            version=_string(document["version"], "version"),
            license=_string(document["license"], "license"),
            license_status=license_status,
            trust_state=trust_state,
            source_refs=_strings(document["source_refs"], "source_refs"),
            court_case_refs=_strings(document["court_case_refs"], "court_case_refs"),
            components=tuple(
                _component_ref(item, f"components[{index}]")
                for index, item in enumerate(raw_components)
            ),
            files=tuple(
                _file_record(item, f"files[{index}]")
                for index, item in enumerate(raw_files)
            ),
            requires=_pins(document["requires"], "requires"),
            replaces=_pins(document["replaces"], "replaces"),
            rollback_to=rollback,
        )
    except ValueError as error:
        raise PackageValidationError(str(error)) from error


def _component_header(
    document: dict[str, Any],
    required: frozenset[str],
    label: str,
) -> str:
    _expect_keys(
        document,
        required=required | {"schema_version", "component_id"},
        label=label,
    )
    if document["schema_version"] != 1 or type(document["schema_version"]) is not int:
        raise PackageValidationError(f"{label} has unsupported schema_version")
    return _string(document["component_id"], f"{label}.component_id")


def _agent_manifest(document: dict[str, Any]) -> AgentManifest:
    label = "agent component"
    component_id = _component_header(
        document,
        frozenset(
            {
                "role_binding",
                "mission",
                "required_outputs",
                "requested_capabilities",
                "quality_gates",
                "prompt_path",
                "skill_ids",
                "tool_ids",
            }
        ),
        label,
    )
    try:
        return AgentManifest(
            component_id=component_id,
            role_binding=_string(document["role_binding"], "role_binding"),
            mission=_string(document["mission"], "mission"),
            required_outputs=_strings(document["required_outputs"], "required_outputs"),
            requested_capabilities=_strings(
                document["requested_capabilities"], "requested_capabilities"
            ),
            quality_gates=_strings(document["quality_gates"], "quality_gates"),
            prompt_path=_string(document["prompt_path"], "prompt_path"),
            skill_ids=_strings(document["skill_ids"], "skill_ids"),
            tool_ids=_strings(document["tool_ids"], "tool_ids"),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


def _skill_manifest(document: dict[str, Any]) -> SkillManifest:
    label = "skill component"
    component_id = _component_header(
        document,
        frozenset(
            {
                "name",
                "description",
                "instruction_path",
                "requested_capabilities",
                "reference_paths",
                "test_refs",
            }
        ),
        label,
    )
    try:
        return SkillManifest(
            component_id=component_id,
            name=_string(document["name"], "name"),
            description=_string(document["description"], "description"),
            instruction_path=_string(document["instruction_path"], "instruction_path"),
            requested_capabilities=_strings(
                document["requested_capabilities"], "requested_capabilities"
            ),
            reference_paths=_strings(document["reference_paths"], "reference_paths"),
            test_refs=_strings(document["test_refs"], "test_refs"),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


def _tool_manifest(document: dict[str, Any]) -> ToolManifest:
    label = "tool component"
    component_id = _component_header(
        document,
        frozenset(
            {
                "capability_id",
                "input_schema_ref",
                "output_schema_ref",
                "side_effecting",
                "idempotency_required",
                "rollback_required",
            }
        ),
        label,
    )
    try:
        return ToolManifest(
            component_id=component_id,
            capability_id=_string(document["capability_id"], "capability_id"),
            input_schema_ref=_string(document["input_schema_ref"], "input_schema_ref"),
            output_schema_ref=_string(
                document["output_schema_ref"], "output_schema_ref"
            ),
            side_effecting=_boolean(document["side_effecting"], "side_effecting"),
            idempotency_required=_boolean(
                document["idempotency_required"], "idempotency_required"
            ),
            rollback_required=_boolean(
                document["rollback_required"], "rollback_required"
            ),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


def _workflow_transition(document: Any, label: str) -> WorkflowTransition:
    if not isinstance(document, dict):
        raise PackageValidationError(f"{label} must be an object")
    _expect_keys(
        document,
        required=frozenset(
            {
                "from_state",
                "to_state",
                "event",
                "allowed_role_bindings",
                "required_evidence",
            }
        ),
        label=label,
    )
    try:
        return WorkflowTransition(
            from_state=_string(document["from_state"], f"{label}.from_state"),
            to_state=_string(document["to_state"], f"{label}.to_state"),
            event=_string(document["event"], f"{label}.event"),
            allowed_role_bindings=_strings(
                document["allowed_role_bindings"],
                f"{label}.allowed_role_bindings",
            ),
            required_evidence=_strings(
                document["required_evidence"], f"{label}.required_evidence"
            ),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


def _workflow_manifest(document: dict[str, Any]) -> WorkflowManifest:
    label = "workflow component"
    component_id = _component_header(
        document,
        frozenset({"initial_state", "terminal_states", "transitions"}),
        label,
    )
    raw_transitions = document["transitions"]
    if not isinstance(raw_transitions, list):
        raise PackageValidationError("transitions must be an array")
    try:
        return WorkflowManifest(
            component_id=component_id,
            initial_state=_string(document["initial_state"], "initial_state"),
            terminal_states=_strings(document["terminal_states"], "terminal_states"),
            transitions=tuple(
                _workflow_transition(item, f"transitions[{index}]")
                for index, item in enumerate(raw_transitions)
            ),
        )
    except ValueError as error:
        raise PackageValidationError(f"{label}: {error}") from error


_COMPONENT_LOADERS = {
    ComponentKind.AGENT: _agent_manifest,
    ComponentKind.SKILL: _skill_manifest,
    ComponentKind.TOOL: _tool_manifest,
    ComponentKind.WORKFLOW: _workflow_manifest,
}


def _assert_no_symlinks(root: Path) -> None:
    if root.is_symlink() or _is_reparse_point(root):
        raise PackageValidationError(
            "package root cannot be a symlink or reparse point"
        )
    for entry in root.rglob("*"):
        if entry.is_symlink() or _is_reparse_point(entry):
            raise PackageValidationError(
                "package contains a prohibited symlink or reparse point: "
                f"{entry.relative_to(root)}"
            )


def _is_reparse_point(path: Path) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    if not flag:
        return False
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError as error:
        raise PackageValidationError(
            f"could not inspect package path attributes: {type(error).__name__}"
        ) from error
    return bool(attributes & flag)


def _listed_regular_files(root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if not path.is_file():
            raise PackageValidationError("package contains a non-regular file")
        relative = path.relative_to(root).as_posix()
        result[relative] = path
    return result


def _validate_component_file_refs(
    component: ComponentManifest,
    listed_paths: frozenset[str],
) -> None:
    paths: tuple[str, ...]
    if isinstance(component, AgentManifest):
        paths = (component.prompt_path,)
    elif isinstance(component, SkillManifest):
        paths = (component.instruction_path, *component.reference_paths)
    elif isinstance(component, ToolManifest):
        paths = (component.input_schema_ref, component.output_schema_ref)
    else:
        paths = ()
    missing = sorted(set(paths) - listed_paths)
    if missing:
        raise PackageValidationError(
            f"component {component.component_id} references unlisted files: "
            + ", ".join(missing)
        )


def _validate_skill_instruction(
    component: SkillManifest,
    document: dict[str, Any],
) -> None:
    label = f"skill instruction for {component.component_id}"
    _expect_keys(
        document,
        required=frozenset(
            {
                "schema_version",
                "skill_id",
                "procedure",
                "fail_closed_on",
                "source_refs",
                "deferred_obligations",
            }
        ),
        label=label,
    )
    if document["schema_version"] != 1 or type(document["schema_version"]) is not int:
        raise PackageValidationError(f"{label} has unsupported schema_version")
    if document["skill_id"] != component.component_id:
        raise PackageValidationError(f"{label} has a mismatched skill_id")
    procedure = _strings(document["procedure"], f"{label}.procedure")
    fail_closed_on = _strings(
        document["fail_closed_on"], f"{label}.fail_closed_on"
    )
    source_refs = _strings(document["source_refs"], f"{label}.source_refs")
    deferred = _strings(
        document["deferred_obligations"], f"{label}.deferred_obligations"
    )
    if not procedure or any(not item.strip() for item in procedure):
        raise PackageValidationError(f"{label} requires nonempty procedure steps")
    if not fail_closed_on or any(not item.strip() for item in fail_closed_on):
        raise PackageValidationError(f"{label} requires fail-closed conditions")
    for values, field in (
        (source_refs, "source_refs"),
        (deferred, "deferred_obligations"),
    ):
        if (
            not values
            or len(values) != len(set(values))
            or any(not item.strip() for item in values)
        ):
            raise PackageValidationError(
                f"{label} requires unique nonempty {field}"
            )


_SCHEMA_REFERENCE_KEYWORDS = frozenset({"$ref", "$dynamicRef", "$recursiveRef"})
_SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "type",
        "additionalProperties",
        "required",
        "properties",
        "items",
        "uniqueItems",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "pattern",
        "enum",
        "const",
    }
)
_SUPPORTED_SCHEMA_TYPES = frozenset(
    {"object", "array", "string", "integer", "number", "boolean", "null"}
)


def _contains_ref(value: object) -> bool:
    if isinstance(value, dict):
        return bool(_SCHEMA_REFERENCE_KEYWORDS & value.keys()) or any(
            _contains_ref(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_ref(item) for item in value)
    return False


def _validate_schema_node(value: object, label: str, *, root: bool = False) -> None:
    if isinstance(value, bool):
        return
    if not isinstance(value, dict):
        raise PackageValidationError(f"{label} must be an object or boolean schema")

    unknown = value.keys() - _SUPPORTED_SCHEMA_KEYWORDS
    if unknown:
        raise PackageValidationError(
            f"{label} contains unsupported schema keywords: "
            + ", ".join(sorted(unknown))
        )
    if not root and ("$schema" in value or "$id" in value):
        raise PackageValidationError(
            f"{label} cannot declare a nested schema dialect or identifier"
        )
    for field in ("title", "description"):
        if field in value and not isinstance(value[field], str):
            raise PackageValidationError(f"{label}.{field} must be a string")

    schema_type = value.get("type")
    if schema_type is not None and (
        not isinstance(schema_type, str)
        or schema_type not in _SUPPORTED_SCHEMA_TYPES
    ):
        raise PackageValidationError(f"{label}.type is unsupported")

    properties = value.get("properties")
    if properties is not None:
        if not isinstance(properties, dict) or any(
            not isinstance(name, str) for name in properties
        ):
            raise PackageValidationError(f"{label}.properties must be an object")
        for name, child in properties.items():
            _validate_schema_node(child, f"{label}.properties.{name}")

    required = value.get("required")
    if required is not None:
        if not isinstance(required, list) or any(
            not isinstance(item, str) for item in required
        ):
            raise PackageValidationError(
                f"{label}.required must be an array of strings"
            )
        if len(required) != len(set(required)):
            raise PackageValidationError(
                f"{label}.required fields cannot contain duplicates"
            )
        if properties is None or set(required) - properties.keys():
            raise PackageValidationError(
                f"{label}.required fields must be declared properties"
            )

    additional = value.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        _validate_schema_node(additional, f"{label}.additionalProperties")

    if "items" in value:
        _validate_schema_node(value["items"], f"{label}.items")
    if "uniqueItems" in value and not isinstance(value["uniqueItems"], bool):
        raise PackageValidationError(f"{label}.uniqueItems must be a boolean")

    for field in ("minItems", "maxItems", "minLength", "maxLength"):
        if field in value and (
            type(value[field]) is not int or value[field] < 0
        ):
            raise PackageValidationError(
                f"{label}.{field} must be a nonnegative integer"
            )
    for minimum_name, maximum_name in (
        ("minItems", "maxItems"),
        ("minLength", "maxLength"),
    ):
        if (
            minimum_name in value
            and maximum_name in value
            and value[minimum_name] > value[maximum_name]
        ):
            raise PackageValidationError(
                f"{label}.{minimum_name} cannot exceed {maximum_name}"
            )

    for field in ("minimum", "maximum"):
        number = value.get(field)
        if field in value and (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
        ):
            raise PackageValidationError(f"{label}.{field} must be a finite number")
    if (
        "minimum" in value
        and "maximum" in value
        and value["minimum"] > value["maximum"]
    ):
        raise PackageValidationError(
            f"{label}.minimum cannot exceed maximum"
        )

    pattern = value.get("pattern")
    if pattern is not None:
        if not isinstance(pattern, str):
            raise PackageValidationError(f"{label}.pattern must be a string")
        try:
            re.compile(pattern)
        except re.error as error:
            raise PackageValidationError(
                f"{label}.pattern must be a valid regular expression"
            ) from error

    enumeration = value.get("enum")
    if enumeration is not None:
        if not isinstance(enumeration, list) or not enumeration:
            raise PackageValidationError(f"{label}.enum must be a nonempty array")
        identities = [canonical_json_bytes(item) for item in enumeration]
        if len(identities) != len(set(identities)):
            raise PackageValidationError(
                f"{label}.enum values cannot contain duplicates"
            )


def _validate_tool_schema(
    component: ToolManifest,
    document: dict[str, Any],
    *,
    direction: str,
) -> None:
    label = f"{direction} schema for {component.component_id}"
    if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise PackageValidationError(f"{label} must declare draft 2020-12")
    if not isinstance(document.get("$id"), str) or not document["$id"].strip():
        raise PackageValidationError(f"{label} requires a schema identifier")
    if document.get("type") != "object":
        raise PackageValidationError(f"{label} root must be an object")
    if document.get("additionalProperties") is not False:
        raise PackageValidationError(
            f"{label} must fail closed on unknown root properties"
        )
    if _contains_ref(document):
        raise PackageValidationError(
            f"{label} must be standalone and cannot contain schema references"
        )
    identifier = urlsplit(document["$id"])
    if identifier.scheme not in {"http", "https"} or not identifier.netloc:
        raise PackageValidationError(
            f"{label} requires an absolute HTTP(S) schema identifier"
        )
    _validate_schema_node(document, label, root=True)
    properties = document.get("properties")
    required = document.get("required")
    if not isinstance(properties, dict):
        raise PackageValidationError(f"{label} requires object properties")
    if not isinstance(required, list) or any(
        not isinstance(item, str) for item in required
    ):
        raise PackageValidationError(f"{label} requires a string required-array")
    if len(required) != len(set(required)):
        raise PackageValidationError(f"{label} required fields cannot duplicate")
    unknown_required = set(required) - properties.keys()
    if unknown_required:
        raise PackageValidationError(
            f"{label} requires undeclared properties: "
            + ", ".join(sorted(unknown_required))
        )


def load_package(root: str | Path) -> LoadedPackage:
    """Load and validate a JSON-only package without importing or executing it."""

    unresolved = Path(root)
    if not unresolved.is_absolute():
        raise PackageValidationError("package root must be an explicit absolute path")
    if not unresolved.is_dir():
        raise PackageValidationError("package root must be an existing directory")
    _assert_no_symlinks(unresolved)
    resolved = unresolved.resolve()
    files_on_disk = _listed_regular_files(resolved)
    manifest_path = resolved / _MANIFEST_NAME
    if _MANIFEST_NAME not in files_on_disk:
        raise PackageValidationError("package root is missing package.json")
    manifest_document, _ = _read_json(manifest_path)
    manifest = _package_manifest(manifest_document)
    manifest_digest = content_digest(canonical_json_bytes(manifest_document))

    declared = {item.path: item for item in manifest.files}
    observed = set(files_on_disk) - {_MANIFEST_NAME}
    if observed != set(declared):
        missing = sorted(set(declared) - observed)
        unlisted = sorted(observed - set(declared))
        details = []
        if missing:
            details.append("missing: " + ", ".join(missing))
        if unlisted:
            details.append("unlisted: " + ", ".join(unlisted))
        raise PackageValidationError("package file inventory mismatch (" + "; ".join(details) + ")")

    loaded_documents: dict[str, dict[str, Any]] = {}
    for relative, record in declared.items():
        path = files_on_disk[relative]
        if path.suffix != ".json":
            raise PackageValidationError(f"v1 package file is not JSON: {relative}")
        document, content = _read_json(path)
        if content_digest(content) != record.digest:
            raise PackageValidationError(f"file digest mismatch: {relative}")
        loaded_documents[relative] = document

    components: list[ComponentManifest] = []
    component_refs = {item.component_id: item for item in manifest.components}
    for reference in manifest.components:
        loader = _COMPONENT_LOADERS[reference.kind]
        component = loader(loaded_documents[reference.manifest_path])
        if component.component_id != reference.component_id:
            raise PackageValidationError(
                f"component id mismatch in {reference.manifest_path}"
            )
        if component.kind is not reference.kind:
            raise PackageValidationError(
                f"component kind mismatch in {reference.manifest_path}"
            )
        components.append(component)
    if len(component_refs) != len(components):
        raise PackageValidationError("duplicate component ids")

    listed_paths = frozenset(declared)
    for component in components:
        _validate_component_file_refs(component, listed_paths)
        if isinstance(component, SkillManifest):
            _validate_skill_instruction(
                component,
                loaded_documents[component.instruction_path],
            )
        elif isinstance(component, ToolManifest):
            _validate_tool_schema(
                component,
                loaded_documents[component.input_schema_ref],
                direction="input",
            )
            _validate_tool_schema(
                component,
                loaded_documents[component.output_schema_ref],
                direction="output",
            )
    return LoadedPackage(
        manifest=manifest,
        manifest_digest=manifest_digest,
        root=resolved,
        components=tuple(components),
    )


class PackageCatalog:
    """An immutable, inert catalog; it has no install or activation API."""

    def __init__(self, packages: tuple[LoadedPackage, ...]) -> None:
        by_id: dict[str, LoadedPackage] = {}
        components: dict[str, ComponentManifest] = {}
        component_owners: dict[str, str] = {}
        for package in packages:
            package_id = package.manifest.package_id
            if package_id in by_id:
                raise PackageValidationError(f"duplicate package id: {package_id}")
            by_id[package_id] = package
            for component in package.components:
                if component.component_id in components:
                    raise PackageValidationError(
                        f"duplicate component id: {component.component_id}"
                    )
                components[component.component_id] = component
                component_owners[component.component_id] = package_id
        self._packages = by_id
        self._components = components
        self._component_owners = component_owners
        self._dependency_order = self._validate_dependencies()
        self._validate_agent_bindings()

    @classmethod
    def from_roots(cls, roots: Iterable[str | Path]) -> PackageCatalog:
        package_roots = tuple(roots)
        if not package_roots:
            raise PackageValidationError("catalog requires explicit package roots")
        return cls(tuple(load_package(root) for root in package_roots))

    def package(self, package_id: str) -> LoadedPackage:
        try:
            return self._packages[package_id]
        except KeyError as error:
            raise KeyError(f"unknown package: {package_id}") from error

    def component(self, component_id: str) -> ComponentManifest:
        try:
            return self._components[component_id]
        except KeyError as error:
            raise KeyError(f"unknown component: {component_id}") from error

    def dependency_order(self) -> tuple[LoadedPackage, ...]:
        return self._dependency_order

    def snapshot(self) -> CatalogSnapshot:
        pins = tuple(
            PackagePin(
                package_id=package.manifest.package_id,
                version=package.manifest.version,
                manifest_digest=package.manifest_digest,
            )
            for package in sorted(
                self._packages.values(), key=lambda item: item.manifest.package_id
            )
        )
        fingerprint = content_digest(
            canonical_json_bytes([pin.to_contract() for pin in pins])
        )
        return CatalogSnapshot(packages=pins, fingerprint=fingerprint)

    def _validate_dependencies(self) -> tuple[LoadedPackage, ...]:
        for package in self._packages.values():
            for required in package.manifest.requires:
                dependency = self._packages.get(required.package_id)
                if dependency is None:
                    raise PackageValidationError(
                        f"{package.manifest.package_id} requires missing package "
                        f"{required.package_id}"
                    )

        visiting: set[str] = set()
        visited: set[str] = set()
        result: list[LoadedPackage] = []

        def visit(package_id: str) -> None:
            if package_id in visiting:
                raise PackageValidationError("package dependency cycle detected")
            if package_id in visited:
                return
            visiting.add(package_id)
            package = self._packages[package_id]
            for required in sorted(
                package.manifest.requires, key=lambda item: item.package_id
            ):
                visit(required.package_id)
            visiting.remove(package_id)
            visited.add(package_id)
            result.append(package)

        for package_id in sorted(self._packages):
            visit(package_id)

        for package in self._packages.values():
            for required in package.manifest.requires:
                dependency = self._packages[required.package_id]
                if dependency.manifest.version != required.version:
                    raise PackageValidationError(
                        f"dependency version mismatch for {required.package_id}"
                    )
                if dependency.manifest_digest != required.manifest_digest:
                    raise PackageValidationError(
                        f"dependency digest mismatch for {required.package_id}"
                    )
            for label, pins in (
                ("replaces", package.manifest.replaces),
                (
                    "rollback_to",
                    ()
                    if package.manifest.rollback_to is None
                    else (package.manifest.rollback_to,),
                ),
            ):
                for pin in pins:
                    referenced = self._packages.get(pin.package_id)
                    resolved = (
                        referenced is not None
                        and referenced.manifest.version == pin.version
                        and referenced.manifest_digest == pin.manifest_digest
                    )
                    if (
                        not resolved
                        and package.manifest.trust_state is not TrustState.QUARANTINED
                    ):
                        raise PackageValidationError(
                            f"unresolved {label} pin {pin.package_id} must remain "
                            "quarantined"
                        )
        return tuple(result)

    def _dependency_closure(self, package_id: str) -> frozenset[str]:
        closure = {package_id}
        pending = [package_id]
        while pending:
            current = self._packages[pending.pop()]
            for required in current.manifest.requires:
                if required.package_id not in closure:
                    closure.add(required.package_id)
                    pending.append(required.package_id)
        return frozenset(closure)

    def _bound_component(
        self,
        *,
        agent: AgentManifest,
        owner_package_id: str,
        component_id: str,
        expected_kind: type[SkillManifest] | type[ToolManifest],
    ) -> SkillManifest | ToolManifest:
        component = self._components.get(component_id)
        if component is None:
            raise PackageValidationError(
                f"agent {agent.component_id} references missing component "
                f"{component_id}"
            )
        component_owner = self._component_owners[component_id]
        if component_owner not in self._dependency_closure(owner_package_id):
            raise PackageValidationError(
                f"agent {agent.component_id} reaches undeclared package component "
                f"{component_id}"
            )
        if not isinstance(component, expected_kind):
            expected = (
                ComponentKind.SKILL.value
                if expected_kind is SkillManifest
                else ComponentKind.TOOL.value
            )
            raise PackageValidationError(
                f"agent {agent.component_id} expected {component_id} to be {expected}"
            )
        return component

    def _validate_agent_bindings(self) -> None:
        for package_id, package in self._packages.items():
            for component in package.components:
                if not isinstance(component, AgentManifest):
                    continue
                requested = set(component.requested_capabilities)
                for skill_id in component.skill_ids:
                    skill = self._bound_component(
                        agent=component,
                        owner_package_id=package_id,
                        component_id=skill_id,
                        expected_kind=SkillManifest,
                    )
                    if not isinstance(skill, SkillManifest):
                        raise AssertionError("validated skill kind changed")
                    escalated = set(skill.requested_capabilities) - requested
                    if escalated:
                        raise PackageValidationError(
                            f"skill {skill.component_id} escalates agent "
                            f"{component.component_id} capabilities: "
                            + ", ".join(sorted(escalated))
                        )
                for tool_id in component.tool_ids:
                    tool = self._bound_component(
                        agent=component,
                        owner_package_id=package_id,
                        component_id=tool_id,
                        expected_kind=ToolManifest,
                    )
                    if not isinstance(tool, ToolManifest):
                        raise AssertionError("validated tool kind changed")
                    if tool.capability_id not in requested:
                        raise PackageValidationError(
                            f"tool {tool.component_id} escalates agent "
                            f"{component.component_id} capability "
                            f"{tool.capability_id}"
                        )


__all__ = ["PackageCatalog", "PackageValidationError", "load_package"]
