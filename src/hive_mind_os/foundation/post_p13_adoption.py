from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .canonical import digest
from .post_p13_adoption_contracts import (
    ACCEPTED_BASE_COMMIT,
    ACTIVE_DEBT_IDS,
    ADOPTION_ROLES,
    DOCKET_ID,
    DOCUMENTS,
    ENVELOPE_SCHEMA,
    EXTERNAL_INPUT_IDS,
    OUTPUT_FIELDS,
    REPOSITORY_ID,
    REQUEST_SCHEMA,
    TENANT_ID,
    validate_adoption_request,
    validate_post_p13_adoption_docket,
)


def example_adoption_request() -> dict[str, Any]:
    return {
        "schema_version": REQUEST_SCHEMA,
        "request_id": "phase5i-post-p13-adoption-001",
        "docket_id": DOCKET_ID,
        "repository_id": REPOSITORY_ID,
        "tenant_id": TENANT_ID,
        "subject_commit": ACCEPTED_BASE_COMMIT,
        "subject_tree": "1111111111111111111111111111111111111111",
        "adr_digest": "sha256:" + ("2" * 64),
        "program_digest": "sha256:" + ("3" * 64),
        "debt_plan_digest": "sha256:" + ("4" * 64),
        "active_debt_ids": list(ACTIVE_DEBT_IDS),
        "requested_next_stage": "independent-adoption-review",
        "authority": "none",
        "activation": "inert",
    }


def _document_manifest(request: dict[str, Any]) -> dict[str, Any]:
    digests = (
        request["adr_digest"],
        request["program_digest"],
        request["debt_plan_digest"],
    )
    documents = [
        {
            "document_id": document_id,
            "path": path,
            "digest": digests[index],
            "status": "proposed",
        }
        for index, (document_id, path) in enumerate(DOCUMENTS)
    ]
    return {
        "schema_version": "phase5i-document-manifest/v1",
        "request_id": request["request_id"],
        "subject_commit": request["subject_commit"],
        "documents": documents,
        "overall_status": "proposed",
    }


def _adoption_requirements(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5i-adoption-requirements/v1",
        "request_id": request["request_id"],
        "roles": [
            {
                "role_id": role_id,
                "status": "required-not-authenticated",
                "identity_evidence": "missing",
                "execution_evidence": "missing",
            }
            for role_id in ADOPTION_ROLES
        ],
        "authenticated_participants": False,
        "evidence_retained_externally": False,
        "requirements_complete": False,
    }


def _external_input_register(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5i-external-input-register/v1",
        "request_id": request["request_id"],
        "inputs": [
            {
                "input_id": input_id,
                "status": "missing",
                "evidence_ref": "missing",
            }
            for input_id in EXTERNAL_INPUT_IDS
        ],
        "all_present": False,
    }


def _adoption_disposition(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "phase5i-adoption-disposition/v1",
        "request_id": request["request_id"],
        "disposition": "awaiting-independent-adoption",
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
        "active_debt_ids": list(request["active_debt_ids"]),
        "required_next_stage": "independent-adoption-review",
    }


def compile_post_p13_adoption_docket(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    request = deepcopy(dict(value))
    validate_adoption_request(request)
    outputs = {
        "document_manifest": _document_manifest(request),
        "adoption_requirements": _adoption_requirements(request),
        "external_input_register": _external_input_register(request),
        "adoption_disposition": _adoption_disposition(request),
    }
    output_digests = {field: digest(outputs[field]) for field in OUTPUT_FIELDS}
    envelope: dict[str, Any] = {
        "schema_version": ENVELOPE_SCHEMA,
        "docket_id": DOCKET_ID,
        "request": request,
        "outputs": outputs,
        "output_digests": output_digests,
    }
    envelope["envelope_digest"] = digest(envelope)
    validate_post_p13_adoption_docket(envelope)
    return deepcopy(envelope)
