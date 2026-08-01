from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, cast

from .canonical import digest
from .external_adoption_evidence_contracts import (
    ACCEPTED_BASE_COMMIT,
    ACTIVE_DEBT_IDS,
    DECISION_OPTIONS,
    ENVELOPE_SCHEMA,
    EVIDENCE_FIELDS,
    INTAKE_ID,
    OUTPUT_FIELDS,
    PARTICIPANT_ROLES,
    PHASE5J_SOURCE_HEAD,
    REJECTION_CODES,
    REPOSITORY_ID,
    REQUEST_SCHEMA,
    TENANT_ID,
    validate_evidence_intake_request,
    validate_external_adoption_evidence_intake,
)


def example_evidence_intake_request() -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_id": "phase5k-external-adoption-evidence-001",
        "intake_id": INTAKE_ID,
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "subject_commit": ACCEPTED_BASE_COMMIT,
        "subject_tree": "1111111111111111111111111111111111111111",
        "phase5j_source_head": PHASE5J_SOURCE_HEAD,
        "phase5j_packet_tree": "2222222222222222222222222222222222222222",
        "phase5j_packet_digest": "sha256:" + ("3" * 64),
        "active_debt_ids": list(ACTIVE_DEBT_IDS),
        "evidence_submissions": [],
        "trust_anchor_refs": [],
        "requested_next_stage": "external-evidence-submission",
        "authority": "none",
        "activation": "inert",
    }


def _evidence_requirements(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5k-evidence-requirements/v1",
        "request_id": request["request_id"],
        "participant_roles": list(PARTICIPANT_ROLES),
        "required_fields": list(EVIDENCE_FIELDS),
        "trust_anchor_status": "missing",
        "external_retention_status": "missing",
        "requirements_satisfied": False,
    }


def _verification_policy(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5k-verification-policy/v1",
        "request_id": request["request_id"],
        "decision_options": list(DECISION_OPTIONS),
        "required_distinct_roles": list(PARTICIPANT_ROLES),
        "rejection_codes": list(REJECTION_CODES),
        "self_issued_allowed": False,
        "local_retention_sufficient": False,
        "policy_status": "defined-not-executed",
    }


def _evidence_register(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5k-evidence-register/v1",
        "request_id": request["request_id"],
        "submissions": [],
        "trust_anchor_refs": [],
        "verified_roles": [],
        "selected_decision": "none",
        "signed_decision_present": False,
        "register_status": "awaiting-external-evidence",
    }


def _intake_disposition(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5k-intake-disposition/v1",
        "request_id": request["request_id"],
        "disposition": "awaiting-external-evidence",
        "active_debt_ids": list(request["active_debt_ids"]),
        "external_evidence_received": False,
        "authenticated_participants": False,
        "adr_adopted": False,
        "p14_eligible": False,
        "p20_eligible": False,
        "release_ready": False,
        "production_ready": False,
        "deployment_authorized": False,
        "promotion_eligible": False,
        "superiority_established": False,
        "authority": "none",
        "activation": "inert",
        "required_next_stage": "external-evidence-submission",
    }


def compile_external_adoption_evidence_intake(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if type(value) is not dict:
        validate_evidence_intake_request(value)
        raise AssertionError("unreachable")
    request = deepcopy(cast(dict[str, Any], value))
    validate_evidence_intake_request(request)
    outputs = {
        "evidence_requirements": _evidence_requirements(request),
        "verification_policy": _verification_policy(request),
        "evidence_register": _evidence_register(request),
        "intake_disposition": _intake_disposition(request),
    }
    output_digests = {field: digest(outputs[field]) for field in OUTPUT_FIELDS}
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA,
        "intake_id": INTAKE_ID,
        "request": request,
        "outputs": outputs,
        "output_digests": output_digests,
    }
    body = deepcopy(envelope)
    envelope["envelope_digest"] = digest(body)
    validate_external_adoption_evidence_intake(envelope)
    return deepcopy(envelope)
