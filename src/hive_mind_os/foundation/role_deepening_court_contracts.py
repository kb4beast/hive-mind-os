from __future__ import annotations

import re
from typing import Any, Mapping, cast

from .canonical import digest, reject_private_content

COURT_ID = "court:phase5h-role-deepening-consolidation"
REPOSITORY_ID = "github:kb4beast/hive-mind-os"
TENANT_ID = "tenant:kb4beast"
ACCEPTED_BASE_COMMIT = "e65be29ae1380743dfb6804e12c83af43abd291d"
REQUEST_SCHEMA = "phase5h-consolidation-request/v1"
ENVELOPE_SCHEMA = "phase5h-consolidation-court/v1"

ROLE_SEQUENCE = (
    ("phase4", "explorer"),
    ("phase5a", "orchestrator"),
    ("phase5b", "architect"),
    ("phase5c", "builder"),
    ("phase5d", "curator"),
    ("phase5e", "integrator"),
    ("phase5f", "steward"),
    ("phase5g", "optimizer"),
)
ACTIVE_DEBT_IDS = (
    "P5D-DEBT-01",
    "P5D-DEBT-02",
    "P5D-DEBT-03",
    "P5D-DEBT-04",
    "P5D-DEBT-05",
    "P5E-DEBT-01",
    "P5E-DEBT-02",
    "P5E-DEBT-03",
    "P5E-DEBT-04",
    "P5E-DEBT-05",
    "P5F-DEBT-01",
    "P5F-DEBT-02",
    "P5F-DEBT-03",
    "P5F-DEBT-04",
    "P5F-DEBT-05",
    "P5G-DEBT-01",
    "P5G-DEBT-02",
    "P5G-DEBT-03",
    "P5G-DEBT-04",
    "P5G-DEBT-05",
)
REOPENED_DEBT_IDS = ("P5D-DEBT-03",)
OUTPUT_FIELDS = (
    "role_inventory",
    "evidence_coverage",
    "conflict_register",
    "court_disposition",
)
EVIDENCE_CATEGORIES = (
    "role-contracts",
    "focused-tests",
    "cross-version-tests",
    "static-validation",
    "type-validation",
    "installed-wheel-verification",
    "external-retention",
    "authenticated-independence",
    "operational-recovery",
    "held-out-evaluation",
)
CONFLICT_IDS = (
    "active-debt",
    "static-type-gate",
    "temporary-workflows",
    "worker-determinism",
    "inventory-packaging-gap",
    "external-evidence-gap",
    "independence-gap",
    "p20-prerequisites",
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class ConsolidationCourtError(ValueError):
    pass


def _exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ConsolidationCourtError(f"{label} must be an exact dict")
    return cast(dict[str, Any], value)


def _exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ConsolidationCourtError(f"{label} must be an exact list")
    return cast(list[Any], value)


def _fields(document: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(document)
    if observed != expected:
        raise ConsolidationCourtError(
            f"{label} fields differ: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _text(value: Any, label: str, *, maximum: int = 16_000) -> str:
    if type(value) is not str:
        raise ConsolidationCourtError(f"{label} must be a string")
    result = cast(str, value)
    if not result or result != result.strip() or len(result) > maximum:
        raise ConsolidationCourtError(f"{label} must be non-empty, trimmed, and bounded")
    return result


def _identifier(value: Any, label: str) -> str:
    result = _text(value, label, maximum=256)
    if _IDENTIFIER.fullmatch(result) is None:
        raise ConsolidationCourtError(f"{label} is not a valid identifier")
    return result


def _digest(value: Any, label: str) -> str:
    result = _text(value, label, maximum=71)
    if _SHA256.fullmatch(result) is None:
        raise ConsolidationCourtError(f"{label} is not a canonical SHA-256 digest")
    return result


def _git_object(value: Any, label: str) -> str:
    result = _text(value, label, maximum=40)
    if _GIT_OBJECT.fullmatch(result) is None:
        raise ConsolidationCourtError(f"{label} is not a full Git object ID")
    return result


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ConsolidationCourtError(f"{label} must be a boolean")
    return cast(bool, value)


def _text_list(value: Any, label: str, *, maximum: int = 128) -> list[str]:
    items = _exact_list(value, label)
    if not items or len(items) > maximum:
        raise ConsolidationCourtError(f"{label} has an invalid item count")
    result = [_text(item, f"{label}[{index}]") for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise ConsolidationCourtError(f"{label} contains duplicate values")
    return result


def _validate_role_entry(value: Any, index: int) -> dict[str, Any]:
    entry = _exact_dict(value, f"role_entries[{index}]")
    _fields(
        entry,
        {
            "phase_id",
            "role_id",
            "status",
            "authority",
            "activation",
            "release_eligible",
            "evidence_refs",
        },
        f"role_entries[{index}]",
    )
    expected_phase, expected_role = ROLE_SEQUENCE[index]
    if entry["phase_id"] != expected_phase or entry["role_id"] != expected_role:
        raise ConsolidationCourtError("role sequence differs from the admitted lifecycle")
    if entry["status"] != "bounded-candidate":
        raise ConsolidationCourtError("every role must remain a bounded candidate")
    if entry["authority"] != "none" or entry["activation"] != "inert":
        raise ConsolidationCourtError("role entries cannot grant authority or activation")
    if _boolean(entry["release_eligible"], "role.release_eligible"):
        raise ConsolidationCourtError("role entries cannot be release eligible")
    _text_list(entry["evidence_refs"], "role.evidence_refs")
    return entry


def _validate_debt_item(value: Any, index: int) -> dict[str, Any]:
    item = _exact_dict(value, f"debt_items[{index}]")
    _fields(item, {"debt_id", "status", "evidence_refs", "exit_condition"}, "debt_item")
    expected_id = ACTIVE_DEBT_IDS[index]
    if item["debt_id"] != expected_id:
        raise ConsolidationCourtError("debt IDs or order differ from the carry-forward plan")
    expected_status = "reopened" if expected_id in REOPENED_DEBT_IDS else "open"
    if item["status"] != expected_status:
        raise ConsolidationCourtError("debt status differs from the carry-forward plan")
    _text_list(item["evidence_refs"], "debt.evidence_refs")
    _text(item["exit_condition"], "debt.exit_condition")
    return item


def validate_consolidation_request(value: Mapping[str, Any]) -> None:
    request = _exact_dict(value, "request")
    _fields(
        request,
        {
            "schema_version",
            "request_id",
            "court_id",
            "repository_id",
            "tenant_id",
            "subject_commit",
            "subject_tree",
            "role_entries",
            "debt_items",
            "source_index_digest",
            "authority",
            "activation",
        },
        "request",
    )
    reject_private_content(request)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise ConsolidationCourtError("unsupported consolidation request schema")
    _identifier(request["request_id"], "request.request_id")
    if request["court_id"] != COURT_ID:
        raise ConsolidationCourtError("request court differs from the fixed Phase 5H court")
    if request["repository_id"] != REPOSITORY_ID or request["tenant_id"] != TENANT_ID:
        raise ConsolidationCourtError("request scope differs from the fixed repository and tenant")
    if request["subject_commit"] != ACCEPTED_BASE_COMMIT:
        raise ConsolidationCourtError("request commit is not the Phase 5G merge")
    _git_object(request["subject_commit"], "request.subject_commit")
    _git_object(request["subject_tree"], "request.subject_tree")
    _digest(request["source_index_digest"], "request.source_index_digest")
    roles = _exact_list(request["role_entries"], "request.role_entries")
    if len(roles) != len(ROLE_SEQUENCE):
        raise ConsolidationCourtError("request must contain every admitted role exactly once")
    for index, entry in enumerate(roles):
        _validate_role_entry(entry, index)
    debt = _exact_list(request["debt_items"], "request.debt_items")
    if len(debt) != len(ACTIVE_DEBT_IDS):
        raise ConsolidationCourtError("request must contain every active debt item exactly once")
    for index, item in enumerate(debt):
        _validate_debt_item(item, index)
    if request["authority"] != "none" or request["activation"] != "inert":
        raise ConsolidationCourtError("request cannot grant authority or activation")


def _validate_role_inventory(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.role_inventory")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "subject_commit",
            "roles",
            "complete_role_sequence",
            "release_eligible",
            "authority",
            "activation",
        },
        "outputs.role_inventory",
    )
    if output["schema_version"] != "phase5h-role-inventory/v1":
        raise ConsolidationCourtError("invalid role-inventory schema")
    if output["request_id"] != request["request_id"]:
        raise ConsolidationCourtError("role inventory request binding differs")
    if output["subject_commit"] != request["subject_commit"]:
        raise ConsolidationCourtError("role inventory commit binding differs")
    if output["roles"] != request["role_entries"]:
        raise ConsolidationCourtError("role inventory differs from the admitted request")
    if not _boolean(output["complete_role_sequence"], "complete_role_sequence"):
        raise ConsolidationCourtError("role inventory must retain the complete sequence")
    if _boolean(output["release_eligible"], "release_eligible"):
        raise ConsolidationCourtError("role inventory cannot be release eligible")
    if output["authority"] != "none" or output["activation"] != "inert":
        raise ConsolidationCourtError("role inventory authority or activation drifted")


def _validate_evidence_coverage(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.evidence_coverage")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "source_index_digest",
            "categories",
            "overall_status",
            "independently_verified",
        },
        "outputs.evidence_coverage",
    )
    if output["schema_version"] != "phase5h-evidence-coverage/v1":
        raise ConsolidationCourtError("invalid evidence-coverage schema")
    if output["request_id"] != request["request_id"]:
        raise ConsolidationCourtError("evidence coverage request binding differs")
    if output["source_index_digest"] != request["source_index_digest"]:
        raise ConsolidationCourtError("evidence coverage source binding differs")
    categories = _exact_list(output["categories"], "evidence_coverage.categories")
    if len(categories) != len(EVIDENCE_CATEGORIES):
        raise ConsolidationCourtError("evidence coverage must include every category")
    for index, category in enumerate(categories):
        item = _exact_dict(category, f"categories[{index}]")
        _fields(item, {"category_id", "status", "evidence_refs"}, "evidence_category")
        if item["category_id"] != EVIDENCE_CATEGORIES[index]:
            raise ConsolidationCourtError("evidence category order differs")
        if item["status"] not in {"partial", "missing", "blocked"}:
            raise ConsolidationCourtError("evidence category cannot claim completion")
        _text_list(item["evidence_refs"], "evidence_category.evidence_refs")
    if output["overall_status"] != "incomplete":
        raise ConsolidationCourtError("overall evidence status must remain incomplete")
    if _boolean(output["independently_verified"], "independently_verified"):
        raise ConsolidationCourtError("authenticated independent verification is not established")


def _validate_conflict_register(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.conflict_register")
    _fields(
        output,
        {"schema_version", "request_id", "debt_items", "conflicts", "all_resolved"},
        "outputs.conflict_register",
    )
    if output["schema_version"] != "phase5h-conflict-register/v1":
        raise ConsolidationCourtError("invalid conflict-register schema")
    if output["request_id"] != request["request_id"] or output["debt_items"] != request["debt_items"]:
        raise ConsolidationCourtError("conflict register request or debt binding differs")
    conflicts = _exact_list(output["conflicts"], "conflicts")
    if len(conflicts) != len(CONFLICT_IDS):
        raise ConsolidationCourtError("conflict register must include every fixed conflict")
    for index, conflict in enumerate(conflicts):
        item = _exact_dict(conflict, f"conflicts[{index}]")
        _fields(item, {"conflict_id", "status", "evidence_refs", "exit_condition"}, "conflict")
        if item["conflict_id"] != CONFLICT_IDS[index] or item["status"] != "unresolved":
            raise ConsolidationCourtError("conflict identity or status differs")
        _text_list(item["evidence_refs"], "conflict.evidence_refs")
        _text(item["exit_condition"], "conflict.exit_condition")
    if _boolean(output["all_resolved"], "all_resolved"):
        raise ConsolidationCourtError("conflicts cannot be marked resolved")


def _validate_disposition(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.court_disposition")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "disposition",
            "p20_eligible",
            "release_ready",
            "production_ready",
            "promotion_eligible",
            "authenticated_independence",
            "superiority_established",
            "authority",
            "activation",
            "required_successor",
        },
        "outputs.court_disposition",
    )
    if output["schema_version"] != "phase5h-court-disposition/v1":
        raise ConsolidationCourtError("invalid court-disposition schema")
    if output["request_id"] != request["request_id"]:
        raise ConsolidationCourtError("court disposition request binding differs")
    if output["disposition"] != "defer-non-release":
        raise ConsolidationCourtError("the only admitted disposition is defer-non-release")
    for field in (
        "p20_eligible",
        "release_ready",
        "production_ready",
        "promotion_eligible",
        "authenticated_independence",
        "superiority_established",
    ):
        if _boolean(output[field], field):
            raise ConsolidationCourtError(f"{field} cannot be true")
    if output["authority"] != "none" or output["activation"] != "inert":
        raise ConsolidationCourtError("court disposition authority or activation drifted")
    if output["required_successor"] != "explicit-remediation-or-p14-p20-adoption":
        raise ConsolidationCourtError("court successor differs from the fixed non-release route")


def validate_role_deepening_court(value: Mapping[str, Any]) -> None:
    envelope = _exact_dict(value, "envelope")
    _fields(
        envelope,
        {
            "schema_version",
            "court_id",
            "request",
            "outputs",
            "output_digests",
            "envelope_digest",
        },
        "envelope",
    )
    reject_private_content(envelope)
    if envelope["schema_version"] != ENVELOPE_SCHEMA or envelope["court_id"] != COURT_ID:
        raise ConsolidationCourtError("court envelope identity differs")
    request = _exact_dict(envelope["request"], "envelope.request")
    validate_consolidation_request(request)
    outputs = _exact_dict(envelope["outputs"], "envelope.outputs")
    if tuple(outputs) != OUTPUT_FIELDS:
        raise ConsolidationCourtError("court outputs differ from the fixed ordered set")
    digests = _exact_dict(envelope["output_digests"], "envelope.output_digests")
    if set(digests) != set(OUTPUT_FIELDS):
        raise ConsolidationCourtError("output digest fields differ")
    validators = (
        _validate_role_inventory,
        _validate_evidence_coverage,
        _validate_conflict_register,
        _validate_disposition,
    )
    for field, validator in zip(OUTPUT_FIELDS, validators, strict=True):
        validator(outputs[field], request)
        _digest(digests[field], f"output_digests.{field}")
        if digests[field] != digest(outputs[field]):
            raise ConsolidationCourtError(f"output digest mismatch for {field}")
    _digest(envelope["envelope_digest"], "envelope.envelope_digest")
    body = {key: item for key, item in envelope.items() if key != "envelope_digest"}
    if envelope["envelope_digest"] != digest(body):
        raise ConsolidationCourtError("court envelope digest mismatch")
