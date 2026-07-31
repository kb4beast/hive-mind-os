from __future__ import annotations

import re
from typing import Any, Mapping, cast

from .canonical import digest, reject_private_content

AGENT_ID = "hive-agent:integrator:v2-shadow-1"
DEFINITION_ID = "hive-agent-definition:integrator:v2-shadow-1"
BASE_DEFINITION_ID = "hive-agent-definition:integrator:v2-candidate"
REPOSITORY_ID = "github:kb4beast/hive-mind-os"
TENANT_ID = "tenant:kb4beast"
ACCEPTED_BASE_COMMIT = "38ecbd176f3ae5b63b116c6a182a2889cd5d16a6"

REQUEST_SCHEMA = "phase5e-integrator-request/v1"
ENVELOPE_SCHEMA = "phase5e-integrator-intake/v1"
OUTPUT_FIELDS = (
    "integration_scope",
    "compatibility_plan",
    "debt_register",
    "steward_handoff",
)
REQUIRED_DEBT_IDS = (
    "P5D-DEBT-01",
    "P5D-DEBT-02",
    "P5D-DEBT-03",
    "P5D-DEBT-04",
    "P5D-DEBT-05",
)
AFFECTED_BOUNDARIES = (
    "contracts",
    "dependencies",
    "data-lineage",
    "adapters",
    "migration",
    "rollback",
    "evidence",
    "temporary-workflows",
)
CHECK_IDS = (
    "exact-contract-versions",
    "undeclared-dependency-detection",
    "provenance-continuity",
    "data-lineage-continuity",
    "adapter-replaceability",
    "migration-order",
    "rollback-invertibility",
    "inherited-debt-closure",
    "temporary-workflow-removal",
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class IntegratorContractError(ValueError):
    pass


def _require_exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise IntegratorContractError(f"{label} must be an exact dict")
    return cast(dict[str, Any], value)


def _require_exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise IntegratorContractError(f"{label} must be an exact list")
    return cast(list[Any], value)


def _require_fields(document: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(document)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise IntegratorContractError(f"{label} fields differ: missing={missing}, extra={extra}")


def _require_text(value: Any, label: str, *, maximum: int = 16_000) -> str:
    if type(value) is not str:
        raise IntegratorContractError(f"{label} must be a string")
    text = cast(str, value)
    if not text or text != text.strip() or len(text) > maximum:
        raise IntegratorContractError(f"{label} must be non-empty, trimmed, and bounded")
    return text


def _require_identifier(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=256)
    if _IDENTIFIER.fullmatch(text) is None:
        raise IntegratorContractError(f"{label} is not a valid identifier")
    return text


def _require_digest(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=71)
    if _SHA256.fullmatch(text) is None:
        raise IntegratorContractError(f"{label} is not a canonical SHA-256 digest")
    return text


def _require_git_object(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=40)
    if _GIT_OBJECT.fullmatch(text) is None:
        raise IntegratorContractError(f"{label} is not a full Git object ID")
    return text


def _require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise IntegratorContractError(f"{label} must be a boolean")
    return cast(bool, value)


def _require_int(value: Any, label: str, *, minimum: int = 0, maximum: int = 10_000) -> int:
    if type(value) is not int:
        raise IntegratorContractError(f"{label} must be an integer")
    number = cast(int, value)
    if number < minimum or number > maximum:
        raise IntegratorContractError(f"{label} is outside its admitted range")
    return number


def _require_text_list(
    value: Any,
    label: str,
    *,
    minimum: int = 1,
    maximum: int = 128,
) -> list[str]:
    items = _require_exact_list(value, label)
    if len(items) < minimum or len(items) > maximum:
        raise IntegratorContractError(f"{label} has an invalid item count")
    result = [_require_text(item, f"{label}[{index}]") for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise IntegratorContractError(f"{label} contains duplicate values")
    return result


def _validate_debt_item(value: Any, index: int) -> dict[str, Any]:
    item = _require_exact_dict(value, f"inherited_debt[{index}]")
    _require_fields(
        item,
        {"debt_id", "status", "source_refs", "blocked_effects", "resolution_exit"},
        f"inherited_debt[{index}]",
    )
    _require_identifier(item["debt_id"], f"inherited_debt[{index}].debt_id")
    if item["status"] != "open":
        raise IntegratorContractError("inherited debt must remain open")
    _require_text_list(item["source_refs"], f"inherited_debt[{index}].source_refs")
    _require_text_list(item["blocked_effects"], f"inherited_debt[{index}].blocked_effects")
    _require_text(item["resolution_exit"], f"inherited_debt[{index}].resolution_exit")
    return item


def validate_integrator_request(value: Mapping[str, Any]) -> None:
    request = _require_exact_dict(value, "request")
    _require_fields(
        request,
        {
            "schema_version",
            "request_id",
            "tenant_id",
            "repository_id",
            "subject_commit",
            "subject_tree",
            "curator_envelope_digest",
            "inherited_debt",
            "requested_next_role",
            "authority",
            "activation",
        },
        "request",
    )
    reject_private_content(request)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise IntegratorContractError("unsupported Integrator request schema")
    _require_identifier(request["request_id"], "request.request_id")
    if request["tenant_id"] != TENANT_ID:
        raise IntegratorContractError("request tenant is outside the fixed Phase 5E scope")
    if request["repository_id"] != REPOSITORY_ID:
        raise IntegratorContractError("request repository is outside the fixed Phase 5E scope")
    if request["subject_commit"] != ACCEPTED_BASE_COMMIT:
        raise IntegratorContractError("request commit is not the accepted Phase 5A-5D merge")
    _require_git_object(request["subject_commit"], "request.subject_commit")
    _require_git_object(request["subject_tree"], "request.subject_tree")
    _require_digest(request["curator_envelope_digest"], "request.curator_envelope_digest")
    debt = _require_exact_list(request["inherited_debt"], "request.inherited_debt")
    if len(debt) != len(REQUIRED_DEBT_IDS):
        raise IntegratorContractError("request must carry every Phase 5D debt item")
    observed_ids = tuple(
        _validate_debt_item(item, index)["debt_id"] for index, item in enumerate(debt)
    )
    if observed_ids != REQUIRED_DEBT_IDS:
        raise IntegratorContractError("inherited debt IDs or order differ from the plan")
    if request["requested_next_role"] != "steward":
        raise IntegratorContractError("the only admitted next role is Steward")
    if request["authority"] != "none" or request["activation"] != "inert":
        raise IntegratorContractError("Integrator request cannot grant authority or activation")


def _validate_integration_scope(output: Any, request: dict[str, Any]) -> None:
    scope = _require_exact_dict(output, "outputs.integration_scope")
    _require_fields(
        scope,
        {
            "schema_version",
            "repository_id",
            "tenant_id",
            "request_id",
            "accepted_base_commit",
            "subject_tree",
            "curator_envelope_digest",
            "affected_boundaries",
            "release_recommendation",
            "authority",
            "activation",
        },
        "outputs.integration_scope",
    )
    if scope["schema_version"] != "phase5e-integration-scope/v1":
        raise IntegratorContractError("invalid integration-scope schema")
    expected = {
        "repository_id": request["repository_id"],
        "tenant_id": request["tenant_id"],
        "request_id": request["request_id"],
        "accepted_base_commit": request["subject_commit"],
        "subject_tree": request["subject_tree"],
        "curator_envelope_digest": request["curator_envelope_digest"],
        "release_recommendation": "defer",
        "authority": "none",
        "activation": "inert",
    }
    for key, expected_value in expected.items():
        if scope[key] != expected_value:
            raise IntegratorContractError(f"integration scope drifted at {key}")
    boundaries = _require_text_list(scope["affected_boundaries"], "affected_boundaries")
    if tuple(boundaries) != AFFECTED_BOUNDARIES:
        raise IntegratorContractError("affected integration boundaries differ from the contract")


def _validate_compatibility_plan(output: Any, request: dict[str, Any]) -> None:
    plan = _require_exact_dict(output, "outputs.compatibility_plan")
    _require_fields(
        plan,
        {
            "schema_version",
            "request_id",
            "checks",
            "execution_status",
            "implementation_authorized",
            "release_authorized",
        },
        "outputs.compatibility_plan",
    )
    if plan["schema_version"] != "phase5e-compatibility-plan/v1":
        raise IntegratorContractError("invalid compatibility-plan schema")
    if plan["request_id"] != request["request_id"] or plan["execution_status"] != "not-run":
        raise IntegratorContractError("compatibility plan overstates scope or execution")
    if _require_bool(plan["implementation_authorized"], "implementation_authorized"):
        raise IntegratorContractError("Integrator intake cannot authorize implementation")
    if _require_bool(plan["release_authorized"], "release_authorized"):
        raise IntegratorContractError("Integrator intake cannot authorize release")
    checks = _require_exact_list(plan["checks"], "outputs.compatibility_plan.checks")
    if len(checks) != len(CHECK_IDS):
        raise IntegratorContractError("compatibility plan is incomplete")
    observed: list[str] = []
    for index, raw_check in enumerate(checks):
        check = _require_exact_dict(raw_check, f"checks[{index}]")
        _require_fields(
            check,
            {"check_id", "boundary", "status", "required_evidence_refs"},
            f"checks[{index}]",
        )
        observed.append(_require_identifier(check["check_id"], f"checks[{index}].check_id"))
        if check["boundary"] not in AFFECTED_BOUNDARIES or check["status"] != "not-run":
            raise IntegratorContractError("compatibility check has invalid boundary or status")
        _require_text_list(check["required_evidence_refs"], f"checks[{index}].required_evidence_refs")
    if tuple(observed) != CHECK_IDS:
        raise IntegratorContractError("compatibility check IDs or order differ from the contract")


def _validate_debt_register(output: Any, request: dict[str, Any]) -> None:
    register = _require_exact_dict(output, "outputs.debt_register")
    _require_fields(
        register,
        {"schema_version", "items", "unresolved_count", "release_blocked"},
        "outputs.debt_register",
    )
    if register["schema_version"] != "phase5e-debt-register/v1":
        raise IntegratorContractError("invalid debt-register schema")
    items = _require_exact_list(register["items"], "outputs.debt_register.items")
    for index, item in enumerate(items):
        _validate_debt_item(item, index)
    if items != request["inherited_debt"]:
        raise IntegratorContractError("debt register does not exactly preserve inherited debt")
    if _require_int(register["unresolved_count"], "unresolved_count") != len(REQUIRED_DEBT_IDS):
        raise IntegratorContractError("debt register unresolved count is false")
    if not _require_bool(register["release_blocked"], "release_blocked"):
        raise IntegratorContractError("open inherited debt must keep release blocked")


def _validate_steward_handoff(output: Any, request: dict[str, Any]) -> None:
    handoff = _require_exact_dict(output, "outputs.steward_handoff")
    _require_fields(
        handoff,
        {
            "schema_version",
            "request_id",
            "next_role",
            "status",
            "required_debt_ids",
            "required_evidence_refs",
            "implementation_authorized",
            "release_authorized",
            "activation_authorized",
            "authority",
        },
        "outputs.steward_handoff",
    )
    if handoff["schema_version"] != "phase5e-steward-handoff/v1":
        raise IntegratorContractError("invalid Steward-handoff schema")
    if handoff["request_id"] != request["request_id"]:
        raise IntegratorContractError("Steward handoff request binding drifted")
    if handoff["next_role"] != "steward" or handoff["status"] != "blocked":
        raise IntegratorContractError("Steward handoff must remain a blocked advisory route")
    debt_ids = _require_text_list(handoff["required_debt_ids"], "required_debt_ids")
    if tuple(debt_ids) != REQUIRED_DEBT_IDS:
        raise IntegratorContractError("Steward handoff does not preserve every debt item")
    required_refs = _require_text_list(handoff["required_evidence_refs"], "required_evidence_refs")
    expected_refs = sorted(
        {
            ref
            for item in cast(list[dict[str, Any]], request["inherited_debt"])
            for ref in cast(list[str], item["source_refs"])
        }
    )
    if required_refs != expected_refs:
        raise IntegratorContractError("Steward handoff evidence references are incomplete")
    for field in (
        "implementation_authorized",
        "release_authorized",
        "activation_authorized",
    ):
        if _require_bool(handoff[field], field):
            raise IntegratorContractError(f"Steward handoff cannot set {field}")
    if handoff["authority"] != "none":
        raise IntegratorContractError("Steward handoff cannot grant authority")


def validate_integrator(value: Mapping[str, Any]) -> None:
    envelope = _require_exact_dict(value, "Integrator envelope")
    _require_fields(
        envelope,
        {
            "schema_version",
            "agent_id",
            "definition_id",
            "base_definition_id",
            "authority",
            "activation",
            "request_snapshot",
            "request_digest",
            "outputs",
            "output_digests",
            "envelope_digest",
        },
        "Integrator envelope",
    )
    reject_private_content(envelope)
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise IntegratorContractError("unsupported Integrator envelope schema")
    if envelope["agent_id"] != AGENT_ID or envelope["definition_id"] != DEFINITION_ID:
        raise IntegratorContractError("Integrator candidate identity drifted")
    if envelope["base_definition_id"] != BASE_DEFINITION_ID:
        raise IntegratorContractError("Integrator base definition drifted")
    if envelope["authority"] != "none" or envelope["activation"] != "inert":
        raise IntegratorContractError("Integrator envelope cannot grant authority or activation")

    request = _require_exact_dict(envelope["request_snapshot"], "request_snapshot")
    validate_integrator_request(request)
    if envelope["request_digest"] != digest(request):
        raise IntegratorContractError("request digest does not bind the request snapshot")

    outputs = _require_exact_dict(envelope["outputs"], "outputs")
    _require_fields(outputs, set(OUTPUT_FIELDS), "outputs")
    output_digests = _require_exact_dict(envelope["output_digests"], "output_digests")
    _require_fields(output_digests, set(OUTPUT_FIELDS), "output_digests")
    for field in OUTPUT_FIELDS:
        _require_digest(output_digests[field], f"output_digests.{field}")
        if output_digests[field] != digest(outputs[field]):
            raise IntegratorContractError(f"output digest mismatch for {field}")

    _validate_integration_scope(outputs["integration_scope"], request)
    _validate_compatibility_plan(outputs["compatibility_plan"], request)
    _validate_debt_register(outputs["debt_register"], request)
    _validate_steward_handoff(outputs["steward_handoff"], request)

    _require_digest(envelope["envelope_digest"], "envelope_digest")
    body = {key: value for key, value in envelope.items() if key != "envelope_digest"}
    if envelope["envelope_digest"] != digest(body):
        raise IntegratorContractError("Integrator envelope digest mismatch")
