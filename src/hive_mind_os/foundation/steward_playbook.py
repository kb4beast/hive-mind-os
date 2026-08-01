from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, cast

from .canonical import digest
from .steward_playbook_contracts import (
    ACCEPTED_BASE_COMMIT,
    AGENT_ID,
    BASE_DEFINITION_ID,
    DEFINITION_ID,
    ENVELOPE_SCHEMA,
    MAINTENANCE_CHECK_IDS,
    MAINTENANCE_EVIDENCE,
    OPEN_DEBT_IDS,
    OUTPUT_FIELDS,
    RECOVERY_ACTIONS,
    RECOVERY_STEP_IDS,
    REPOSITORY_ID,
    REQUEST_SCHEMA,
    RESOLVED_DEBT_IDS,
    SIGNAL_IDS,
    TENANT_ID,
    validate_steward,
    validate_steward_request,
)


def example_steward_request() -> dict[str, Any]:
    observations = [
        {
            "signal_id": signal_id,
            "status": "unknown",
            "evidence_refs": [],
        }
        for signal_id in SIGNAL_IDS
    ]
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_id": "phase5f-steward-intake-001",
        "tenant_id": TENANT_ID,
        "repository_id": REPOSITORY_ID,
        "subject_commit": ACCEPTED_BASE_COMMIT,
        "subject_tree": "1111111111111111111111111111111111111111",
        "integrator_envelope_digest": "sha256:" + ("2" * 64),
        "open_debt_ids": list(OPEN_DEBT_IDS),
        "resolved_debt_ids": list(RESOLVED_DEBT_IDS),
        "health_observations": observations,
        "requested_next_role": "optimizer",
        "authority": "none",
        "activation": "inert",
    }


def _health_snapshot(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5f-health-snapshot/v1",
        "request_id": request["request_id"],
        "repository_id": request["repository_id"],
        "tenant_id": request["tenant_id"],
        "accepted_base_commit": request["subject_commit"],
        "subject_tree": request["subject_tree"],
        "integrator_envelope_digest": request["integrator_envelope_digest"],
        "health_status": "degraded",
        "release_recommendation": "defer",
        "open_debt_ids": list(OPEN_DEBT_IDS),
        "resolved_debt_ids": list(RESOLVED_DEBT_IDS),
        "authority": "none",
        "activation": "inert",
    }


def _maintenance_plan(request: dict[str, Any]) -> dict[str, Any]:
    checks = [
        {
            "check_id": check_id,
            "status": "not-run",
            "evidence_required": list(MAINTENANCE_EVIDENCE[check_id]),
        }
        for check_id in MAINTENANCE_CHECK_IDS
    ]
    return {
        "schema_version": "phase5f-maintenance-plan/v1",
        "request_id": request["request_id"],
        "checks": checks,
        "execution_status": "not-run",
        "maintenance_authorized": False,
        "dependency_mutation_authorized": False,
    }


def _recovery_plan(request: dict[str, Any]) -> dict[str, Any]:
    steps = [
        {
            "step_id": step_id,
            "action": RECOVERY_ACTIONS[step_id],
            "status": "not-run",
            "reversible": True,
            "preserves_evidence": True,
        }
        for step_id in RECOVERY_STEP_IDS
    ]
    return {
        "schema_version": "phase5f-recovery-plan/v1",
        "request_id": request["request_id"],
        "steps": steps,
        "execution_status": "not-run",
        "recovery_authorized": False,
        "evidence_deletion_authorized": False,
    }


def _optimizer_handoff(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5f-optimizer-handoff/v1",
        "request_id": request["request_id"],
        "next_role": "optimizer",
        "eligible": False,
        "status": "blocked",
        "open_debt_ids": list(OPEN_DEBT_IDS),
        "resolved_debt_ids": list(RESOLVED_DEBT_IDS),
        "reason": "open-carried-debt-and-unexecuted-health-checks",
        "release_recommendation": "defer",
        "authority": "none",
        "activation": "inert",
    }


def compile_steward_intake(request: Mapping[str, Any]) -> dict[str, Any]:
    validate_steward_request(request)
    request_snapshot = cast(dict[str, Any], deepcopy(request))
    outputs = {
        "health_snapshot": _health_snapshot(request_snapshot),
        "maintenance_plan": _maintenance_plan(request_snapshot),
        "recovery_plan": _recovery_plan(request_snapshot),
        "optimizer_handoff": _optimizer_handoff(request_snapshot),
    }
    output_digests = {field: digest(outputs[field]) for field in OUTPUT_FIELDS}
    body = {
        "schema_version": ENVELOPE_SCHEMA,
        "agent_id": AGENT_ID,
        "definition_id": DEFINITION_ID,
        "base_definition_id": BASE_DEFINITION_ID,
        "request": request_snapshot,
        "outputs": outputs,
        "output_digests": output_digests,
    }
    envelope = {**body, "envelope_digest": digest(body)}
    validate_steward(envelope)
    return cast(dict[str, Any], deepcopy(envelope))
