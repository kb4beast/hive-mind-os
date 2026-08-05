from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from importlib.resources import files
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .receipts import portable_path_parts
from .roles import IMPLEMENTED_REPOSITORY_ROLES

LEGACY_SCHEMA_NAMES = (
    "acceptance-specification",
    "artifact-manifest",
    "capability-lease",
    "claim",
    "event",
    "handoff",
    "identity",
    "mission-state",
    "model-turn",
    "policy-decision",
    "source",
    "tool-intent",
    "tool-receipt",
)
EXTENSION_SCHEMA_NAMES = (
    "continuation-packet",
    "package-manifest",
    "agent-component",
    "skill-component",
    "tool-component",
    "workflow-component",
    "host-capability-profile",
    "ooda-state",
    "war-room-event",
)
SCHEMA_NAMES = (*LEGACY_SCHEMA_NAMES, *EXTENSION_SCHEMA_NAMES)
ROLE_NAMES = frozenset(
    {
        "orchestrator",
        "explorer",
        "architect",
        "builder",
        "curator",
        "integrator",
        "steward",
        "optimizer",
    }
)
SIDE_EFFECTING_ACTIONS = frozenset(
    {"write", "command", "network", "git", "message", "deploy"}
)
_RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)


@dataclass(frozen=True, slots=True)
class ContractValidation:
    valid: bool
    issues: tuple[str, ...] = ()


def load_schema(name: str) -> dict[str, Any]:
    if name not in SCHEMA_NAMES:
        raise KeyError(f"unknown contract schema: {name}")
    resource = files("hive_mind_os").joinpath("schemas", f"{name}.schema.json")
    document = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{name} schema is not an object")
    return document


def validate_schema_catalog() -> ContractValidation:
    issues: list[str] = []
    identifiers: set[str] = set()
    for name in SCHEMA_NAMES:
        try:
            schema = load_schema(name)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            issues.append(f"{name}: unreadable schema: {type(error).__name__}: {error}")
            continue
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            issues.append(f"{name}: unsupported or missing JSON Schema dialect")
        identifier = schema.get("$id")
        if not isinstance(identifier, str) or not identifier:
            issues.append(f"{name}: missing schema identifier")
        elif identifier in identifiers:
            issues.append(f"{name}: duplicate schema identifier")
        else:
            identifiers.add(identifier)
        if schema.get("type") != "object":
            issues.append(f"{name}: root contract must be an object")
        if schema.get("additionalProperties") is not False:
            issues.append(f"{name}: root contract must fail closed on unknown fields")
    return ContractValidation(not issues, tuple(issues))


def _json_identity(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return type(value) is bool
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return type(value) in {int, float}
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


def _resolve_ref(reference: str) -> Mapping[str, Any]:
    path = PurePosixPath(reference)
    if path.is_absolute() or len(path.parts) != 1 or path.suffix != ".json":
        raise ValueError(f"non-local schema reference is prohibited: {reference}")
    stem = path.name.removesuffix(".schema.json")
    if stem not in SCHEMA_NAMES:
        raise ValueError(f"unknown local schema reference: {reference}")
    return load_schema(stem)


def _validate_node(
    value: Any,
    schema: Mapping[str, Any],
    path: str,
    issues: list[str],
) -> None:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        try:
            _validate_node(value, _resolve_ref(reference), path, issues)
        except ValueError as error:
            issues.append(f"{path}: {error}")
        return

    expected = schema.get("type")
    if isinstance(expected, str) and not _matches_type(value, expected):
        issues.append(f"{path}: expected {expected}")
        return
    if isinstance(expected, list) and not any(
        isinstance(item, str) and _matches_type(value, item) for item in expected
    ):
        issues.append(f"{path}: expected one of {expected}")
        return

    if "const" in schema and (
        type(value) is not type(schema["const"]) or value != schema["const"]
    ):
        issues.append(f"{path}: value does not match const")
    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        issues.append(f"{path}: value is not in enum")

    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        if type(minimum_length) is int and len(value) < minimum_length:
            issues.append(f"{path}: string is shorter than {minimum_length}")
        maximum_length = schema.get("maxLength")
        if type(maximum_length) is int and len(value) > maximum_length:
            issues.append(f"{path}: string is longer than {maximum_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            issues.append(f"{path}: string does not match required pattern")
        if schema.get("format") == "date-time":
            try:
                if _RFC3339_PATTERN.fullmatch(value) is None:
                    raise ValueError("not RFC 3339")
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError("offset is required")
            except ValueError:
                issues.append(f"{path}: invalid date-time")
        if schema.get("format") == "portable-relative-path":
            try:
                portable_path_parts(value)
            except ValueError:
                issues.append(f"{path}: invalid portable relative path")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            issues.append(f"{path}: number must be finite")
            return
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and value < minimum:
            issues.append(f"{path}: number is below minimum {minimum}")

    if isinstance(value, list):
        minimum_items = schema.get("minItems")
        maximum_items = schema.get("maxItems")
        if type(minimum_items) is int and len(value) < minimum_items:
            issues.append(f"{path}: array has fewer than {minimum_items} items")
        if type(maximum_items) is int and len(value) > maximum_items:
            issues.append(f"{path}: array has more than {maximum_items} items")
        if schema.get("uniqueItems") is True:
            identities = [_json_identity(item) for item in value]
            if len(identities) != len(set(identities)):
                issues.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(value):
                _validate_node(item, item_schema, f"{path}[{index}]", issues)

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    issues.append(f"{path}: missing required property {key}")
        properties = schema.get("properties", {})
        if isinstance(properties, Mapping):
            for key, child in properties.items():
                if key in value and isinstance(child, Mapping):
                    _validate_node(value[key], child, f"{path}.{key}", issues)
            unknown = set(value) - set(properties)
            additional = schema.get("additionalProperties")
            if additional is False and unknown:
                issues.append(
                    f"{path}: unknown properties: {', '.join(sorted(unknown))}"
                )
            elif isinstance(additional, Mapping):
                for key in sorted(unknown):
                    _validate_node(value[key], additional, f"{path}.{key}", issues)

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for branch in all_of:
            if not isinstance(branch, Mapping):
                continue
            condition = branch.get("if")
            consequence = branch.get("then")
            if isinstance(condition, Mapping) and isinstance(consequence, Mapping):
                condition_issues: list[str] = []
                _validate_node(value, condition, path, condition_issues)
                if not condition_issues:
                    _validate_node(value, consequence, path, issues)
            else:
                _validate_node(value, branch, path, issues)


def validate_contract(name: str, document: Any) -> ContractValidation:
    issues: list[str] = []
    try:
        schema = load_schema(name)
    except (KeyError, OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return ContractValidation(False, (f"schema unavailable: {type(error).__name__}: {error}",))
    _validate_node(document, schema, "$", issues)
    return ContractValidation(not issues, tuple(dict.fromkeys(issues)))


def tool_intent_digest(document: Mapping[str, Any]) -> str:
    """Bind every declared tool-intent field except the digest field itself."""

    payload = {key: value for key, value in document.items() if key != "action_digest"}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def validate_runtime_state(
    document: Any,
    *,
    expected_source_pack_fingerprint: str | None = None,
) -> ContractValidation:
    structural = validate_contract("mission-state", document)
    issues = list(structural.issues)
    if not isinstance(document, Mapping):
        return ContractValidation(False, tuple(issues))
    mission = document.get("mission")
    if not isinstance(mission, Mapping):
        return ContractValidation(False, tuple(issues))

    mission_id = mission.get("id")
    state_version = mission.get("state_version")
    expected_state_ref = f"MISSION_STATE:{mission_id}:{state_version}"
    fingerprint = mission.get("source_pack_fingerprint")
    if (
        expected_source_pack_fingerprint is not None
        and fingerprint != expected_source_pack_fingerprint
    ):
        issues.append("mission source-pack fingerprint does not match validated bytes")

    role_runs = document.get("role_runs")
    role_actors: set[str] = set()
    role_names: list[str] = []
    if isinstance(role_runs, Sequence) and not isinstance(role_runs, (str, bytes)):
        for run in role_runs:
            if isinstance(run, Mapping):
                role = run.get("role")
                actor = run.get("actor_id")
                if isinstance(role, str):
                    role_names.append(role)
                if isinstance(actor, str):
                    role_actors.add(actor)
        if len(role_names) != len(set(role_names)):
            issues.append("role_runs contain duplicate roles")

    actions = document.get("proposed_actions")
    action_map: dict[str, Mapping[str, Any]] = {}
    if isinstance(actions, Sequence) and not isinstance(actions, (str, bytes)):
        for action in actions:
            if not isinstance(action, Mapping):
                continue
            action_id = action.get("action_id")
            if not isinstance(action_id, str):
                continue
            if action_id in action_map:
                issues.append(f"duplicate action id: {action_id}")
            else:
                action_map[action_id] = action
            if action.get("mission_id") != mission_id:
                issues.append(f"action {action_id} belongs to another mission")
            if action.get("state_ref") != expected_state_ref:
                issues.append(f"action {action_id} references another mission state")
            if action.get("actor_id") not in role_actors:
                issues.append(f"action {action_id} actor lacks a role run")
            try:
                expected_digest = tool_intent_digest(action)
            except (TypeError, ValueError, UnicodeError):
                issues.append(f"action {action_id} cannot be canonically digested")
            else:
                if action.get("action_digest") != expected_digest:
                    issues.append(f"action {action_id} digest does not bind its intent")

    receipt_map: dict[str, Mapping[str, Any]] = {}
    receipts = document.get("tool_receipts")
    receipt_ids: set[str] = set()
    execution_ids: set[str] = set()
    if isinstance(receipts, Sequence) and not isinstance(receipts, (str, bytes)):
        for receipt in receipts:
            if not isinstance(receipt, Mapping):
                continue
            receipt_id = receipt.get("receipt_id")
            execution_id = receipt.get("execution_id")
            action_id = receipt.get("action_id")
            if isinstance(receipt_id, str):
                if receipt_id in receipt_ids:
                    issues.append(f"duplicate receipt id: {receipt_id}")
                receipt_ids.add(receipt_id)
            if isinstance(execution_id, str):
                if execution_id in execution_ids:
                    issues.append(f"duplicate execution id: {execution_id}")
                execution_ids.add(execution_id)
            action = action_map.get(action_id) if isinstance(action_id, str) else None
            if action is None:
                issues.append(f"receipt references unknown action: {action_id}")
                continue
            for field, action_field in (
                ("mission_id", None),
                ("state_ref", None),
                ("actor_id", "actor_id"),
                ("action_kind", "kind"),
                ("action_digest", "action_digest"),
                ("policy_decision_ref", "policy_decision_ref"),
                ("lease_id", "lease_id"),
            ):
                if field == "mission_id":
                    expected_value = mission_id
                elif field == "state_ref":
                    expected_value = expected_state_ref
                elif action_field is not None:
                    expected_value = action.get(action_field)
                else:
                    expected_value = None
                if receipt.get(field) != expected_value:
                    issues.append(f"receipt {receipt_id} has foreign {field}")
            if receipt.get("verified_by") == receipt.get("actor_id"):
                issues.append(f"receipt {receipt_id} was self-verified")
            if isinstance(action_id, str):
                if action_id in receipt_map:
                    issues.append(f"action has multiple receipts: {action_id}")
                else:
                    receipt_map[action_id] = receipt

    verification = document.get("independent_verification")
    verifier_ids: set[str] = set()
    if isinstance(verification, Sequence) and not isinstance(verification, (str, bytes)):
        verifier_ids = {
            item["actor_id"]
            for item in verification
            if isinstance(item, Mapping) and isinstance(item.get("actor_id"), str)
        }
    if role_actors & verifier_ids:
        issues.append("acting role identity attempted to verify mission completion")

    handoff = document.get("handoff")
    if isinstance(handoff, Mapping):
        if handoff.get("mission_id") != mission_id:
            issues.append("handoff belongs to another mission")
        if handoff.get("state_ref") != expected_state_ref:
            issues.append("handoff references another mission state")

    if mission.get("status") == "complete":
        succeeded_roles = {
            run.get("role")
            for run in role_runs or ()
            if isinstance(run, Mapping) and run.get("status") == "succeeded"
        }
        missing_roles = {
            role.value for role in IMPLEMENTED_REPOSITORY_ROLES
        } - succeeded_roles
        if missing_roles:
            issues.append(
                "completion is missing successful role runs: "
                + ", ".join(sorted(missing_roles))
            )
        if document.get("blockers"):
            issues.append("completion declared while blockers remain")
        if not verifier_ids:
            issues.append("completion lacks independent verification")
        for action_id, action in action_map.items():
            if action.get("kind") not in SIDE_EFFECTING_ACTIONS:
                continue
            receipt = receipt_map.get(action_id)
            if receipt is None or receipt.get("result") != "succeeded":
                issues.append(
                    f"completion lacks successful receipt for side-effecting action {action_id}"
                )

    return ContractValidation(not issues, tuple(dict.fromkeys(issues)))
