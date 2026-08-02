from __future__ import annotations

import re
from typing import Any, Mapping, cast

from .canonical import digest, reject_private_content

DOCKET_ID = "docket:phase5i-post-p13-adoption"
REPOSITORY_ID = "github:kb4beast/hive-mind-os"
TENANT_ID = "tenant:kb4beast"
ACCEPTED_BASE_COMMIT = "522d04fe76b53574a4f93256466df69de42f747a"
REQUEST_SCHEMA = "phase5i-adoption-request/v1"
ENVELOPE_SCHEMA = "phase5i-adoption-docket/v1"

DOCUMENTS = (
    (
        "adr-015",
        "docs/architecture/ADR-015-POST-P13-PRODUCTION-AND-TRUST-PROGRAM.md",
    ),
    ("post-p13-program", "docs/plan/01_POST_P13_OVERVIEW.md"),
    ("phase5-debt-plan", "docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md"),
)
ADOPTION_ROLES = ("curator", "judge", "orchestrator")
EXTERNAL_INPUT_IDS = (
    "provider-authority",
    "identity-and-signing",
    "external-retention",
    "deployment-and-rollback",
    "source-and-license",
    "comparator-access",
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
    "P5H-DEBT-01",
    "P5H-DEBT-02",
    "P5H-DEBT-03",
    "P5H-DEBT-04",
    "P5H-DEBT-05",
)
REOPENED_DEBT_IDS = ("P5D-DEBT-03",)
OUTPUT_FIELDS = (
    "document_manifest",
    "adoption_requirements",
    "external_input_register",
    "adoption_disposition",
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class AdoptionDocketError(ValueError):
    pass


def _exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise AdoptionDocketError(f"{label} must be an exact dict")
    return cast(dict[str, Any], value)


def _exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise AdoptionDocketError(f"{label} must be an exact list")
    return cast(list[Any], value)


def _fields(document: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(document)
    if observed != expected:
        raise AdoptionDocketError(
            f"{label} fields differ: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _text(value: Any, label: str, *, maximum: int = 16_000) -> str:
    if type(value) is not str:
        raise AdoptionDocketError(f"{label} must be a string")
    result = cast(str, value)
    if not result or result != result.strip() or len(result) > maximum:
        raise AdoptionDocketError(f"{label} must be non-empty, trimmed, and bounded")
    return result


def _identifier(value: Any, label: str) -> str:
    result = _text(value, label, maximum=256)
    if _IDENTIFIER.fullmatch(result) is None:
        raise AdoptionDocketError(f"{label} is not a valid identifier")
    return result


def _digest(value: Any, label: str) -> str:
    result = _text(value, label, maximum=71)
    if _SHA256.fullmatch(result) is None:
        raise AdoptionDocketError(f"{label} is not a canonical SHA-256 digest")
    return result


def _git_object(value: Any, label: str) -> str:
    result = _text(value, label, maximum=40)
    if _GIT_OBJECT.fullmatch(result) is None:
        raise AdoptionDocketError(f"{label} is not a full Git object ID")
    return result


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise AdoptionDocketError(f"{label} must be a boolean")
    return cast(bool, value)


def _text_list(value: Any, label: str, *, maximum: int = 128) -> list[str]:
    items = _exact_list(value, label)
    if not items or len(items) > maximum:
        raise AdoptionDocketError(f"{label} has an invalid item count")
    result = [_text(item, f"{label}[{index}]") for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise AdoptionDocketError(f"{label} contains duplicate values")
    return result


def validate_adoption_request(value: Mapping[str, Any]) -> None:
    request = _exact_dict(value, "request")
    _fields(
        request,
        {
            "schema_version",
            "request_id",
            "docket_id",
            "repository_id",
            "tenant_id",
            "subject_commit",
            "subject_tree",
            "adr_digest",
            "program_digest",
            "debt_plan_digest",
            "active_debt_ids",
            "requested_next_stage",
            "authority",
            "activation",
        },
        "request",
    )
    reject_private_content(request)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise AdoptionDocketError("unsupported adoption request schema")
    _identifier(request["request_id"], "request.request_id")
    if request["docket_id"] != DOCKET_ID:
        raise AdoptionDocketError("request docket differs from the fixed Phase 5I docket")
    if request["repository_id"] != REPOSITORY_ID or request["tenant_id"] != TENANT_ID:
        raise AdoptionDocketError("request scope differs from the fixed repository and tenant")
    if request["subject_commit"] != ACCEPTED_BASE_COMMIT:
        raise AdoptionDocketError("request commit is not the Phase 5H merge")
    _git_object(request["subject_commit"], "request.subject_commit")
    _git_object(request["subject_tree"], "request.subject_tree")
    _digest(request["adr_digest"], "request.adr_digest")
    _digest(request["program_digest"], "request.program_digest")
    _digest(request["debt_plan_digest"], "request.debt_plan_digest")
    debt = _text_list(request["active_debt_ids"], "request.active_debt_ids")
    if tuple(debt) != ACTIVE_DEBT_IDS:
        raise AdoptionDocketError("active debt IDs or order differ from the carry-forward plan")
    if request["requested_next_stage"] != "independent-adoption-review":
        raise AdoptionDocketError("the only admitted next stage is independent adoption review")
    if request["authority"] != "none" or request["activation"] != "inert":
        raise AdoptionDocketError("request cannot grant authority or activation")


def _validate_document_manifest(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.document_manifest")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "subject_commit",
            "documents",
            "overall_status",
        },
        "outputs.document_manifest",
    )
    if output["schema_version"] != "phase5i-document-manifest/v1":
        raise AdoptionDocketError("invalid document-manifest schema")
    if output["request_id"] != request["request_id"]:
        raise AdoptionDocketError("document manifest request binding differs")
    if output["subject_commit"] != request["subject_commit"]:
        raise AdoptionDocketError("document manifest commit binding differs")
    documents = _exact_list(output["documents"], "document_manifest.documents")
    if len(documents) != len(DOCUMENTS):
        raise AdoptionDocketError("document manifest must contain every proposed document")
    request_digests = (
        request["adr_digest"],
        request["program_digest"],
        request["debt_plan_digest"],
    )
    for index, document in enumerate(documents):
        item = _exact_dict(document, f"documents[{index}]")
        _fields(item, {"document_id", "path", "digest", "status"}, "document")
        expected_id, expected_path = DOCUMENTS[index]
        if item["document_id"] != expected_id or item["path"] != expected_path:
            raise AdoptionDocketError("document identity or order differs")
        if item["digest"] != request_digests[index]:
            raise AdoptionDocketError("document digest differs from the request binding")
        _digest(item["digest"], "document.digest")
        if item["status"] != "proposed":
            raise AdoptionDocketError("adoption documents must remain proposed")
    if output["overall_status"] != "proposed":
        raise AdoptionDocketError("document manifest cannot claim adoption")


def _validate_adoption_requirements(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.adoption_requirements")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "roles",
            "authenticated_participants",
            "evidence_retained_externally",
            "requirements_complete",
        },
        "outputs.adoption_requirements",
    )
    if output["schema_version"] != "phase5i-adoption-requirements/v1":
        raise AdoptionDocketError("invalid adoption-requirements schema")
    if output["request_id"] != request["request_id"]:
        raise AdoptionDocketError("adoption requirements request binding differs")
    roles = _exact_list(output["roles"], "adoption_requirements.roles")
    if len(roles) != len(ADOPTION_ROLES):
        raise AdoptionDocketError("every independent adoption role is required")
    for index, role in enumerate(roles):
        item = _exact_dict(role, f"roles[{index}]")
        _fields(
            item,
            {"role_id", "status", "identity_evidence", "execution_evidence"},
            "adoption_role",
        )
        if item["role_id"] != ADOPTION_ROLES[index]:
            raise AdoptionDocketError("adoption role identity or order differs")
        if item["status"] != "required-not-authenticated":
            raise AdoptionDocketError("adoption role cannot claim authentication")
        if item["identity_evidence"] != "missing":
            raise AdoptionDocketError("identity evidence must remain missing")
        if item["execution_evidence"] != "missing":
            raise AdoptionDocketError("execution evidence must remain missing")
    if _boolean(output["authenticated_participants"], "authenticated_participants"):
        raise AdoptionDocketError("authenticated participants are not established")
    if _boolean(
        output["evidence_retained_externally"],
        "evidence_retained_externally",
    ):
        raise AdoptionDocketError("external evidence retention is not established")
    if _boolean(output["requirements_complete"], "requirements_complete"):
        raise AdoptionDocketError("adoption requirements cannot be complete")


def _validate_external_input_register(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.external_input_register")
    _fields(
        output,
        {"schema_version", "request_id", "inputs", "all_present"},
        "outputs.external_input_register",
    )
    if output["schema_version"] != "phase5i-external-input-register/v1":
        raise AdoptionDocketError("invalid external-input-register schema")
    if output["request_id"] != request["request_id"]:
        raise AdoptionDocketError("external input register request binding differs")
    inputs = _exact_list(output["inputs"], "external_input_register.inputs")
    if len(inputs) != len(EXTERNAL_INPUT_IDS):
        raise AdoptionDocketError("external input register must contain every input class")
    for index, external_input in enumerate(inputs):
        item = _exact_dict(external_input, f"inputs[{index}]")
        _fields(item, {"input_id", "status", "evidence_ref"}, "external_input")
        if item["input_id"] != EXTERNAL_INPUT_IDS[index]:
            raise AdoptionDocketError("external input identity or order differs")
        if item["status"] != "missing" or item["evidence_ref"] != "missing":
            raise AdoptionDocketError("external inputs cannot be represented as present")
    if _boolean(output["all_present"], "all_present"):
        raise AdoptionDocketError("external inputs are not all present")


def _validate_adoption_disposition(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.adoption_disposition")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "disposition",
            "adr_adopted",
            "p14_eligible",
            "p20_eligible",
            "release_ready",
            "production_ready",
            "deployment_authorized",
            "promotion_eligible",
            "superiority_established",
            "authority",
            "activation",
            "active_debt_ids",
            "required_next_stage",
        },
        "outputs.adoption_disposition",
    )
    if output["schema_version"] != "phase5i-adoption-disposition/v1":
        raise AdoptionDocketError("invalid adoption-disposition schema")
    if output["request_id"] != request["request_id"]:
        raise AdoptionDocketError("adoption disposition request binding differs")
    if output["disposition"] != "awaiting-independent-adoption":
        raise AdoptionDocketError("adoption disposition must remain awaiting independent adoption")
    false_claims = (
        "adr_adopted",
        "p14_eligible",
        "p20_eligible",
        "release_ready",
        "production_ready",
        "deployment_authorized",
        "promotion_eligible",
        "superiority_established",
    )
    for field in false_claims:
        if _boolean(output[field], field):
            raise AdoptionDocketError(f"{field} cannot be true")
    if output["authority"] != "none" or output["activation"] != "inert":
        raise AdoptionDocketError("adoption disposition cannot grant authority or activation")
    debt = _text_list(output["active_debt_ids"], "disposition.active_debt_ids")
    if tuple(debt) != ACTIVE_DEBT_IDS:
        raise AdoptionDocketError("adoption disposition debt differs from the plan")
    if output["required_next_stage"] != "independent-adoption-review":
        raise AdoptionDocketError("adoption disposition next stage differs")


def validate_post_p13_adoption_docket(value: Mapping[str, Any]) -> None:
    envelope = _exact_dict(value, "envelope")
    _fields(
        envelope,
        {
            "schema_version",
            "docket_id",
            "request",
            "outputs",
            "output_digests",
            "envelope_digest",
        },
        "envelope",
    )
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise AdoptionDocketError("unsupported adoption docket schema")
    if envelope["docket_id"] != DOCKET_ID:
        raise AdoptionDocketError("adoption docket identity differs")
    request = _exact_dict(envelope["request"], "envelope.request")
    validate_adoption_request(request)
    outputs = _exact_dict(envelope["outputs"], "envelope.outputs")
    _fields(outputs, set(OUTPUT_FIELDS), "envelope.outputs")
    _validate_document_manifest(outputs["document_manifest"], request)
    _validate_adoption_requirements(outputs["adoption_requirements"], request)
    _validate_external_input_register(outputs["external_input_register"], request)
    _validate_adoption_disposition(outputs["adoption_disposition"], request)
    output_digests = _exact_dict(envelope["output_digests"], "output_digests")
    _fields(output_digests, set(OUTPUT_FIELDS), "output_digests")
    for field in OUTPUT_FIELDS:
        observed = _digest(output_digests[field], f"output_digests.{field}")
        if observed != digest(outputs[field]):
            raise AdoptionDocketError(f"output digest differs for {field}")
    body = {key: item for key, item in envelope.items() if key != "envelope_digest"}
    observed_envelope_digest = _digest(envelope["envelope_digest"], "envelope_digest")
    if observed_envelope_digest != digest(body):
        raise AdoptionDocketError("envelope digest differs")
