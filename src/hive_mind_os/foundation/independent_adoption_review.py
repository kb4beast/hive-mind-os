from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, cast

from .canonical import digest
from .independent_adoption_review_contracts import (
    ACCEPTED_BASE_COMMIT,
    ACTIVE_DEBT_IDS,
    DECISION_OPTIONS,
    DOCUMENTS,
    ENVELOPE_SCHEMA,
    EXTERNAL_INPUT_IDS,
    HANDOFF_ACTIONS,
    OUTPUT_FIELDS,
    PACKET_ID,
    PARTICIPANT_REQUIREMENTS,
    PARTICIPANT_ROLES,
    REPOSITORY_ID,
    REQUEST_SCHEMA,
    TENANT_ID,
    IndependentAdoptionReviewError,
    validate_independent_adoption_review_packet,
    validate_review_packet_request,
)


def example_review_packet_request() -> dict[str, Any]:
    document_digests = (
        "sha256:" + ("1" * 64),
        "sha256:" + ("2" * 64),
        "sha256:" + ("3" * 64),
        "sha256:" + ("4" * 64),
    )
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_id": "phase5j-independent-adoption-review-001",
        "packet_id": PACKET_ID,
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "subject_commit": ACCEPTED_BASE_COMMIT,
        "subject_tree": "1111111111111111111111111111111111111111",
        "phase5i_envelope_digest": "sha256:" + ("5" * 64),
        "documents": [
            {
                "document_id": document_id,
                "path": path,
                "digest": document_digests[index],
                "status": "frozen-proposed",
            }
            for index, (document_id, path) in enumerate(DOCUMENTS)
        ],
        "active_debt_ids": list(ACTIVE_DEBT_IDS),
        "external_input_ids": list(EXTERNAL_INPUT_IDS),
        "requested_next_stage": "external-independent-review",
        "authority": "none",
        "activation": "inert",
    }


def _review_packet_manifest(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5j-review-packet-manifest/v1",
        "request_id": request["request_id"],
        "subject_commit": request["subject_commit"],
        "subject_tree": request["subject_tree"],
        "phase5i_envelope_digest": request["phase5i_envelope_digest"],
        "documents": deepcopy(request["documents"]),
        "active_debt_ids": list(request["active_debt_ids"]),
        "external_input_ids": list(request["external_input_ids"]),
        "packet_status": "ready-for-external-review",
        "review_status": "not-run",
    }


def _participant_requirements(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5j-participant-requirements/v1",
        "request_id": request["request_id"],
        "participants": [
            {
                "role_id": role_id,
                "status": "required-not-authenticated",
                "requirements": list(PARTICIPANT_REQUIREMENTS),
                "identity_evidence": "missing",
                "signature_evidence": "missing",
                "execution_evidence": "missing",
                "external_retention_evidence": "missing",
            }
            for role_id in PARTICIPANT_ROLES
        ],
        "authenticated_participants": False,
        "requirements_satisfied": False,
    }


def _decision_templates(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5j-decision-templates/v1",
        "request_id": request["request_id"],
        "options": [
            {
                "decision_id": decision_id,
                "selected": False,
                "signed": False,
                "participant_role": "judge",
                "scope_narrowing_required": decision_id == "adapt",
                "evidence_ref": "missing",
            }
            for decision_id in DECISION_OPTIONS
        ],
        "selected_decision": "none",
        "review_completed": False,
        "signed_decision_present": False,
    }


def _external_handoff(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5j-external-handoff/v1",
        "request_id": request["request_id"],
        "handoff_status": "external-action-required",
        "actions": list(HANDOFF_ACTIONS),
        "external_submission_received": False,
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
    }


def compile_independent_adoption_review_packet(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if type(value) is not dict:
        raise IndependentAdoptionReviewError("request must be an exact dict")
    request = deepcopy(cast(dict[str, Any], value))
    validate_review_packet_request(request)
    outputs = {
        "review_packet_manifest": _review_packet_manifest(request),
        "participant_requirements": _participant_requirements(request),
        "decision_templates": _decision_templates(request),
        "external_handoff": _external_handoff(request),
    }
    output_digests = {field: digest(outputs[field]) for field in OUTPUT_FIELDS}
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA,
        "packet_id": PACKET_ID,
        "request": request,
        "outputs": outputs,
        "output_digests": output_digests,
    }
    envelope["envelope_digest"] = digest(envelope)
    validate_independent_adoption_review_packet(envelope)
    return deepcopy(envelope)
