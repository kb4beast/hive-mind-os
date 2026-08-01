from __future__ import annotations

import re
from typing import Any, Mapping, cast

from .canonical import digest, reject_private_content

AGENT_ID = "hive-agent:steward:v2-shadow-1"
DEFINITION_ID = "hive-agent-definition:steward:v2-shadow-1"
BASE_DEFINITION_ID = "hive-agent-definition:steward:v2-candidate"
REPOSITORY_ID = "github:kb4beast/hive-mind-os"
TENANT_ID = "tenant:kb4beast"
ACCEPTED_BASE_COMMIT = "eccc8fce1bab5fb289279985198cb8753b3f171c"

REQUEST_SCHEMA = "phase5f-steward-request/v1"
ENVELOPE_SCHEMA = "phase5f-steward-intake/v1"
OUTPUT_FIELDS = (
    "health_snapshot",
    "maintenance_plan",
    "recovery_plan",
    "optimizer_handoff",
)
OPEN_DEBT_IDS = (
    "P5D-DEBT-01",
    "P5D-DEBT-02",
    "P5D-DEBT-04",
    "P5D-DEBT-05",
    "P5E-DEBT-01",
    "P5E-DEBT-02",
    "P5E-DEBT-03",
    "P5E-DEBT-04",
    "P5E-DEBT-05",
)
RESOLVED_DEBT_IDS = ("P5D-DEBT-03",)
SIGNAL_IDS = (
    "full-test-matrix",
    "static-validation",
    "type-validation",
    "build-evidence",
    "installed-wheel",
    "workflow-surface",
    "evidence-integrity",
    "recovery-readiness",
)
MAINTENANCE_CHECK_IDS = (
    "reliability-health",
    "dependency-health",
    "observability-coverage",
    "evidence-integrity",
    "temporary-workflow-surface",
    "runbook-completeness",
    "static-and-type-gates",
)
MAINTENANCE_EVIDENCE = {
    "reliability-health": ("full-test-matrix", "failure-history"),
    "dependency-health": ("dependency-review", "version-pins", "license-review"),
    "observability-coverage": ("health-signals", "failure-signals", "unknown-signals"),
    "evidence-integrity": ("append-only-ledger", "artifact-digests", "adverse-evidence"),
    "temporary-workflow-surface": ("workflow-inventory", "permission-inventory"),
    "runbook-completeness": ("recovery-procedure", "rollback-verification"),
    "static-and-type-gates": ("ruff-receipt", "pyright-receipt"),
}
RECOVERY_STEP_IDS = (
    "freeze-subject",
    "preserve-adverse-evidence",
    "remove-temporary-workflows",
    "repair-static-gates",
    "repair-type-gates",
    "rebuild-and-verify",
    "replay-rollback",
    "handoff-open-obligations",
)
RECOVERY_ACTIONS = {
    "freeze-subject": "Pin the exact commit, tree, debt register, and evidence inventory.",
    "preserve-adverse-evidence": "Copy no evidence; verify existing append-only adverse receipts remain reachable.",
    "remove-temporary-workflows": "Delete only the three recorded temporary Phase 5D workflows in a normal commit.",
    "repair-static-gates": "Apply deterministic Ruff repairs without changing behavior or weakening checks.",
    "repair-type-gates": "Correct mutable-container typing without weakening exact-container validation.",
    "rebuild-and-verify": "Run the full cross-version, security, build, wheel, SBOM, Ruff, and Pyright gates.",
    "replay-rollback": "Verify the inverse change path restores the prior bounded integration tree.",
    "handoff-open-obligations": "Carry every unresolved item into the Optimizer and release court.",
}

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class StewardContractError(ValueError):
    pass


def _require_exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise StewardContractError(f"{label} must be an exact dict")
    return cast(dict[str, Any], value)


def _require_exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise StewardContractError(f"{label} must be an exact list")
    return cast(list[Any], value)


def _require_fields(document: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(document)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise StewardContractError(f"{label} fields differ: missing={missing}, extra={extra}")


def _require_text(value: Any, label: str, *, maximum: int = 16_000) -> str:
    if type(value) is not str:
        raise StewardContractError(f"{label} must be a string")
    text = cast(str, value)
    if not text or text != text.strip() or len(text) > maximum:
        raise StewardContractError(f"{label} must be non-empty, trimmed, and bounded")
    return text


def _require_identifier(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=256)
    if _IDENTIFIER.fullmatch(text) is None:
        raise StewardContractError(f"{label} is not a valid identifier")
    return text


def _require_digest(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=71)
    if _SHA256.fullmatch(text) is None:
        raise StewardContractError(f"{label} is not a canonical SHA-256 digest")
    return text


def _require_git_object(value: Any, label: str) -> str:
    text = _require_text(value, label, maximum=40)
    if _GIT_OBJECT.fullmatch(text) is None:
        raise StewardContractError(f"{label} is not a full Git object ID")
    return text


def _require_bool(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise StewardContractError(f"{label} must be a boolean")
    return cast(bool, value)


def _require_text_list(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = 128,
) -> list[str]:
    items = _require_exact_list(value, label)
    if len(items) < minimum or len(items) > maximum:
        raise StewardContractError(f"{label} has an invalid item count")
    result = [_require_text(item, f"{label}[{index}]") for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise StewardContractError(f"{label} contains duplicate values")
    return result


def _validate_observation(value: Any, index: int) -> dict[str, Any]:
    item = _require_exact_dict(value, f"health_observations[{index}]")
    _require_fields(
        item,
        {"signal_id", "status", "evidence_refs"},
        f"health_observations[{index}]",
    )
    _require_identifier(item["signal_id"], f"health_observations[{index}].signal_id")
    if item["status"] not in {"passing", "failing", "unknown"}:
        raise StewardContractError("health observation status is unsupported")
    _require_text_list(
        item["evidence_refs"],
        f"health_observations[{index}].evidence_refs",
        maximum=32,
    )
    return item


def validate_steward_request(value: Mapping[str, Any]) -> None:
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
            "integrator_envelope_digest",
            "open_debt_ids",
            "resolved_debt_ids",
            "health_observations",
            "requested_next_role",
            "authority",
            "activation",
        },
        "request",
    )
    reject_private_content(request)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise StewardContractError("unsupported Steward request schema")
    _require_identifier(request["request_id"], "request.request_id")
    if request["tenant_id"] != TENANT_ID or request["repository_id"] != REPOSITORY_ID:
        raise StewardContractError("request is outside the fixed Phase 5F scope")
    if request["subject_commit"] != ACCEPTED_BASE_COMMIT:
        raise StewardContractError("request commit is not the accepted Phase 5A-5E merge")
    _require_git_object(request["subject_commit"], "request.subject_commit")
    _require_git_object(request["subject_tree"], "request.subject_tree")
    _require_digest(request["integrator_envelope_digest"], "request.integrator_envelope_digest")
    open_ids = tuple(_require_text_list(request["open_debt_ids"], "request.open_debt_ids"))
    resolved_ids = tuple(
        _require_text_list(request["resolved_debt_ids"], "request.resolved_debt_ids")
    )
    if open_ids != OPEN_DEBT_IDS or resolved_ids != RESOLVED_DEBT_IDS:
        raise StewardContractError("debt inventory differs from the carry-forward plan")
    observations = _require_exact_list(request["health_observations"], "health_observations")
    if len(observations) != len(SIGNAL_IDS):
        raise StewardContractError("every required health signal must be present")
    observed_signal_ids = tuple(
        _validate_observation(item, index)["signal_id"]
        for index, item in enumerate(observations)
    )
    if observed_signal_ids != SIGNAL_IDS:
        raise StewardContractError("health signal IDs or order differ from the contract")
    if request["requested_next_role"] != "optimizer":
        raise StewardContractError("the only admitted next role is Optimizer")
    if request["authority"] != "none" or request["activation"] != "inert":
        raise StewardContractError("Steward request cannot grant authority or activation")


def _validate_health_snapshot(output: Any, request: dict[str, Any]) -> None:
    snapshot = _require_exact_dict(output, "outputs.health_snapshot")
    _require_fields(
        snapshot,
        {
            "schema_version",
            "request_id",
            "repository_id",
            "tenant_id",
            "accepted_base_commit",
            "subject_tree",
            "integrator_envelope_digest",
            "health_status",
            "release_recommendation",
            "open_debt_ids",
            "resolved_debt_ids",
            "authority",
            "activation",
        },
        "outputs.health_snapshot",
    )
    if snapshot["schema_version"] != "phase5f-health-snapshot/v1":
        raise StewardContractError("invalid health-snapshot schema")
    expected = {
        "request_id": request["request_id"],
        "repository_id": request["repository_id"],
        "tenant_id": request["tenant_id"],
        "accepted_base_commit": request["subject_commit"],
        "subject_tree": request["subject_tree"],
        "integrator_envelope_digest": request["integrator_envelope_digest"],
        "health_status": "degraded",
        "release_recommendation": "defer",
        "authority": "none",
        "activation": "inert",
    }
    for key, expected_value in expected.items():
        if snapshot[key] != expected_value:
            raise StewardContractError(f"health snapshot drifted at {key}")
    if tuple(_require_text_list(snapshot["open_debt_ids"], "open_debt_ids")) != OPEN_DEBT_IDS:
        raise StewardContractError("health snapshot open debt differs")
    if (
        tuple(_require_text_list(snapshot["resolved_debt_ids"], "resolved_debt_ids"))
        != RESOLVED_DEBT_IDS
    ):
        raise StewardContractError("health snapshot resolved debt differs")


def _validate_maintenance_plan(output: Any, request: dict[str, Any]) -> None:
    plan = _require_exact_dict(output, "outputs.maintenance_plan")
    _require_fields(
        plan,
        {
            "schema_version",
            "request_id",
            "checks",
            "execution_status",
            "maintenance_authorized",
            "dependency_mutation_authorized",
        },
        "outputs.maintenance_plan",
    )
    if plan["schema_version"] != "phase5f-maintenance-plan/v1":
        raise StewardContractError("invalid maintenance-plan schema")
    if plan["request_id"] != request["request_id"] or plan["execution_status"] != "not-run":
        raise StewardContractError("maintenance plan status or scope drifted")
    if _require_bool(plan["maintenance_authorized"], "maintenance_authorized"):
        raise StewardContractError("maintenance cannot be authorized")
    if _require_bool(plan["dependency_mutation_authorized"], "dependency_mutation_authorized"):
        raise StewardContractError("dependency mutation cannot be authorized")
    checks = _require_exact_list(plan["checks"], "maintenance checks")
    if len(checks) != len(MAINTENANCE_CHECK_IDS):
        raise StewardContractError("maintenance check count differs")
    for index, (item, check_id) in enumerate(zip(checks, MAINTENANCE_CHECK_IDS, strict=True)):
        check = _require_exact_dict(item, f"maintenance checks[{index}]")
        _require_fields(check, {"check_id", "status", "evidence_required"}, "maintenance check")
        if check["check_id"] != check_id or check["status"] != "not-run":
            raise StewardContractError("maintenance check identity or status drifted")
        evidence = tuple(
            _require_text_list(check["evidence_required"], "maintenance evidence", minimum=1)
        )
        if evidence != MAINTENANCE_EVIDENCE[check_id]:
            raise StewardContractError("maintenance evidence requirements drifted")


def _validate_recovery_plan(output: Any, request: dict[str, Any]) -> None:
    plan = _require_exact_dict(output, "outputs.recovery_plan")
    _require_fields(
        plan,
        {
            "schema_version",
            "request_id",
            "steps",
            "execution_status",
            "recovery_authorized",
            "evidence_deletion_authorized",
        },
        "outputs.recovery_plan",
    )
    if plan["schema_version"] != "phase5f-recovery-plan/v1":
        raise StewardContractError("invalid recovery-plan schema")
    if plan["request_id"] != request["request_id"] or plan["execution_status"] != "not-run":
        raise StewardContractError("recovery plan status or scope drifted")
    if _require_bool(plan["recovery_authorized"], "recovery_authorized"):
        raise StewardContractError("recovery cannot be authorized")
    if _require_bool(plan["evidence_deletion_authorized"], "evidence_deletion_authorized"):
        raise StewardContractError("evidence deletion cannot be authorized")
    steps = _require_exact_list(plan["steps"], "recovery steps")
    if len(steps) != len(RECOVERY_STEP_IDS):
        raise StewardContractError("recovery step count differs")
    for index, (item, step_id) in enumerate(zip(steps, RECOVERY_STEP_IDS, strict=True)):
        step = _require_exact_dict(item, f"recovery steps[{index}]")
        _require_fields(
            step,
            {"step_id", "action", "status", "reversible", "preserves_evidence"},
            "recovery step",
        )
        if step["step_id"] != step_id or step["action"] != RECOVERY_ACTIONS[step_id]:
            raise StewardContractError("recovery step identity or action drifted")
        if step["status"] != "not-run":
            raise StewardContractError("recovery step cannot claim execution")
        if not _require_bool(step["reversible"], "reversible"):
            raise StewardContractError("recovery step must be reversible")
        if not _require_bool(step["preserves_evidence"], "preserves_evidence"):
            raise StewardContractError("recovery step must preserve evidence")


def _validate_optimizer_handoff(output: Any, request: dict[str, Any]) -> None:
    handoff = _require_exact_dict(output, "outputs.optimizer_handoff")
    _require_fields(
        handoff,
        {
            "schema_version",
            "request_id",
            "next_role",
            "eligible",
            "status",
            "open_debt_ids",
            "resolved_debt_ids",
            "reason",
            "release_recommendation",
            "authority",
            "activation",
        },
        "outputs.optimizer_handoff",
    )
    if handoff["schema_version"] != "phase5f-optimizer-handoff/v1":
        raise StewardContractError("invalid Optimizer handoff schema")
    expected = {
        "request_id": request["request_id"],
        "next_role": "optimizer",
        "eligible": False,
        "status": "blocked",
        "reason": "open-carried-debt-and-unexecuted-health-checks",
        "release_recommendation": "defer",
        "authority": "none",
        "activation": "inert",
    }
    for key, expected_value in expected.items():
        if handoff[key] != expected_value:
            raise StewardContractError(f"Optimizer handoff drifted at {key}")
    if tuple(_require_text_list(handoff["open_debt_ids"], "handoff open debt")) != OPEN_DEBT_IDS:
        raise StewardContractError("Optimizer handoff open debt differs")
    if (
        tuple(_require_text_list(handoff["resolved_debt_ids"], "handoff resolved debt"))
        != RESOLVED_DEBT_IDS
    ):
        raise StewardContractError("Optimizer handoff resolved debt differs")


def validate_steward(value: Mapping[str, Any]) -> None:
    envelope = _require_exact_dict(value, "envelope")
    _require_fields(
        envelope,
        {
            "schema_version",
            "agent_id",
            "definition_id",
            "base_definition_id",
            "request",
            "outputs",
            "output_digests",
            "envelope_digest",
        },
        "envelope",
    )
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise StewardContractError("unsupported Steward envelope schema")
    if envelope["agent_id"] != AGENT_ID or envelope["definition_id"] != DEFINITION_ID:
        raise StewardContractError("Steward identity drifted")
    if envelope["base_definition_id"] != BASE_DEFINITION_ID:
        raise StewardContractError("Steward base definition drifted")
    request = _require_exact_dict(envelope["request"], "envelope.request")
    validate_steward_request(request)
    outputs = _require_exact_dict(envelope["outputs"], "envelope.outputs")
    _require_fields(outputs, set(OUTPUT_FIELDS), "envelope.outputs")
    validators = {
        "health_snapshot": _validate_health_snapshot,
        "maintenance_plan": _validate_maintenance_plan,
        "recovery_plan": _validate_recovery_plan,
        "optimizer_handoff": _validate_optimizer_handoff,
    }
    for field in OUTPUT_FIELDS:
        validators[field](outputs[field], request)
    output_digests = _require_exact_dict(envelope["output_digests"], "output_digests")
    _require_fields(output_digests, set(OUTPUT_FIELDS), "output_digests")
    for field in OUTPUT_FIELDS:
        if output_digests[field] != digest(outputs[field]):
            raise StewardContractError(f"output digest mismatch for {field}")
        _require_digest(output_digests[field], f"output_digests.{field}")
    body = {key: value for key, value in envelope.items() if key != "envelope_digest"}
    if envelope["envelope_digest"] != digest(body):
        raise StewardContractError("Steward envelope digest mismatch")
    _require_digest(envelope["envelope_digest"], "envelope.envelope_digest")
