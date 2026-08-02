from __future__ import annotations

import re
from typing import Any, Mapping, cast

from .canonical import digest, reject_private_content

INTAKE_ID = "intake:phase5k-external-adoption-evidence"
REPOSITORY_ID = "github:kb4beast/hive-mind-os"
TENANT_ID = "tenant:kb4beast"
ACCEPTED_BASE_COMMIT = "6c2e76b0e07c038724c39bebf4ab2ad8394e72a7"
PHASE5J_SOURCE_HEAD = "06b81ee7ae38da9c2050e92b16dfcb1fbc65a97d"
REQUEST_SCHEMA = "phase5k-evidence-intake-request/v1"
ENVELOPE_SCHEMA = "phase5k-external-adoption-evidence-intake/v1"

PARTICIPANT_ROLES = ("curator", "judge", "orchestrator")
DECISION_OPTIONS = ("adopt", "adapt", "reject", "defer", "abstain")
ACTIVE_DEBT_IDS = tuple(
    f"P5{phase}-DEBT-{index:02d}"
    for phase in ("D", "E", "F", "G", "H", "I", "J")
    for index in range(1, 6)
)
EVIDENCE_FIELDS = (
    "participant_id",
    "role_id",
    "issuer_id",
    "key_id",
    "signature",
    "signed_payload_digest",
    "repository_id",
    "tenant_id",
    "phase5j_merge_commit",
    "packet_head",
    "packet_tree",
    "decision",
    "scope_digest",
    "evidence_index_digest",
    "issued_at",
    "expires_at",
    "replay_nonce",
    "retention_ref",
    "revocation_ref",
    "conflict_disclosure",
    "authority_ref",
)
REJECTION_CODES = (
    "self-issued-identity",
    "unknown-issuer",
    "unsigned",
    "invalid-signature",
    "replayed",
    "expired",
    "revoked",
    "scope-mismatch",
    "role-conflict",
    "missing-external-retention",
    "incomplete-evidence",
    "unsupported-decision",
)
OUTPUT_FIELDS = (
    "evidence_requirements",
    "verification_policy",
    "evidence_register",
    "intake_disposition",
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class ExternalAdoptionEvidenceError(ValueError):
    pass


def _exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ExternalAdoptionEvidenceError(f"{label} must be an exact dict")
    return cast(dict[str, Any], value)


def _exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ExternalAdoptionEvidenceError(f"{label} must be an exact list")
    return cast(list[Any], value)


def _fields(document: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(document)
    if observed != expected:
        raise ExternalAdoptionEvidenceError(
            f"{label} fields differ: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _text(value: Any, label: str, *, maximum: int = 16_000) -> str:
    if type(value) is not str:
        raise ExternalAdoptionEvidenceError(f"{label} must be a string")
    result = cast(str, value)
    if not result or result != result.strip() or len(result) > maximum:
        raise ExternalAdoptionEvidenceError(
            f"{label} must be non-empty, trimmed, and bounded"
        )
    return result


def _identifier(value: Any, label: str) -> str:
    result = _text(value, label, maximum=256)
    if _IDENTIFIER.fullmatch(result) is None:
        raise ExternalAdoptionEvidenceError(f"{label} is not a valid identifier")
    return result


def _sha256(value: Any, label: str) -> str:
    result = _text(value, label, maximum=71)
    if _SHA256.fullmatch(result) is None:
        raise ExternalAdoptionEvidenceError(
            f"{label} is not a canonical SHA-256 digest"
        )
    return result


def _git_object(value: Any, label: str) -> str:
    result = _text(value, label, maximum=40)
    if _GIT_OBJECT.fullmatch(result) is None:
        raise ExternalAdoptionEvidenceError(f"{label} is not a full Git object ID")
    return result


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ExternalAdoptionEvidenceError(f"{label} must be a boolean")
    return cast(bool, value)


def _text_list(
    value: Any,
    label: str,
    *,
    expected: tuple[str, ...] | None = None,
    allow_empty: bool = False,
    maximum: int = 128,
) -> list[str]:
    items = _exact_list(value, label)
    if len(items) > maximum or (not allow_empty and not items):
        raise ExternalAdoptionEvidenceError(f"{label} has an invalid item count")
    result = [_text(item, f"{label}[{index}]") for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise ExternalAdoptionEvidenceError(f"{label} contains duplicate values")
    if expected is not None and tuple(result) != expected:
        raise ExternalAdoptionEvidenceError(f"{label} differs from the fixed inventory")
    return result


def validate_evidence_intake_request(value: Mapping[str, Any]) -> None:
    request = _exact_dict(value, "request")
    _fields(
        request,
        {
            "schema_version",
            "request_id",
            "intake_id",
            "repository_id",
            "tenant_id",
            "subject_commit",
            "subject_tree",
            "phase5j_source_head",
            "phase5j_packet_tree",
            "phase5j_packet_digest",
            "active_debt_ids",
            "evidence_submissions",
            "trust_anchor_refs",
            "requested_next_stage",
            "authority",
            "activation",
        },
        "request",
    )
    reject_private_content(request)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise ExternalAdoptionEvidenceError("unsupported evidence-intake request schema")
    _identifier(request["request_id"], "request.request_id")
    if request["intake_id"] != INTAKE_ID:
        raise ExternalAdoptionEvidenceError("request intake identity differs")
    if request["repository_id"] != REPOSITORY_ID or request["tenant_id"] != TENANT_ID:
        raise ExternalAdoptionEvidenceError("request scope differs")
    if request["subject_commit"] != ACCEPTED_BASE_COMMIT:
        raise ExternalAdoptionEvidenceError("request commit is not the Phase 5J merge")
    _git_object(request["subject_commit"], "request.subject_commit")
    _git_object(request["subject_tree"], "request.subject_tree")
    if request["phase5j_source_head"] != PHASE5J_SOURCE_HEAD:
        raise ExternalAdoptionEvidenceError("Phase 5J source head differs")
    _git_object(request["phase5j_source_head"], "request.phase5j_source_head")
    _git_object(request["phase5j_packet_tree"], "request.phase5j_packet_tree")
    _sha256(request["phase5j_packet_digest"], "request.phase5j_packet_digest")
    _text_list(
        request["active_debt_ids"],
        "request.active_debt_ids",
        expected=ACTIVE_DEBT_IDS,
    )
    submissions = _exact_list(request["evidence_submissions"], "request.evidence_submissions")
    if submissions:
        raise ExternalAdoptionEvidenceError(
            "external evidence cannot be admitted before trust-anchor verification exists"
        )
    anchors = _exact_list(request["trust_anchor_refs"], "request.trust_anchor_refs")
    if anchors:
        raise ExternalAdoptionEvidenceError(
            "trust anchors cannot be caller-declared by the procedural intake"
        )
    if request["requested_next_stage"] != "external-evidence-submission":
        raise ExternalAdoptionEvidenceError("requested next stage differs")
    if request["authority"] != "none" or request["activation"] != "inert":
        raise ExternalAdoptionEvidenceError("request cannot grant authority or activation")


def _validate_requirements(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.evidence_requirements")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "participant_roles",
            "required_fields",
            "trust_anchor_status",
            "external_retention_status",
            "requirements_satisfied",
        },
        "outputs.evidence_requirements",
    )
    if output["schema_version"] != "phase5k-evidence-requirements/v1":
        raise ExternalAdoptionEvidenceError("invalid evidence-requirements schema")
    if output["request_id"] != request["request_id"]:
        raise ExternalAdoptionEvidenceError("evidence requirements request binding differs")
    _text_list(
        output["participant_roles"],
        "participant_roles",
        expected=PARTICIPANT_ROLES,
    )
    _text_list(
        output["required_fields"],
        "required_fields",
        expected=EVIDENCE_FIELDS,
    )
    if output["trust_anchor_status"] != "missing":
        raise ExternalAdoptionEvidenceError("trust anchors are not established")
    if output["external_retention_status"] != "missing":
        raise ExternalAdoptionEvidenceError("external retention is not established")
    if _boolean(output["requirements_satisfied"], "requirements_satisfied"):
        raise ExternalAdoptionEvidenceError("evidence requirements are not satisfied")


def _validate_policy(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.verification_policy")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "decision_options",
            "required_distinct_roles",
            "rejection_codes",
            "self_issued_allowed",
            "local_retention_sufficient",
            "policy_status",
        },
        "outputs.verification_policy",
    )
    if output["schema_version"] != "phase5k-verification-policy/v1":
        raise ExternalAdoptionEvidenceError("invalid verification-policy schema")
    if output["request_id"] != request["request_id"]:
        raise ExternalAdoptionEvidenceError("verification policy request binding differs")
    _text_list(output["decision_options"], "decision_options", expected=DECISION_OPTIONS)
    _text_list(
        output["required_distinct_roles"],
        "required_distinct_roles",
        expected=PARTICIPANT_ROLES,
    )
    _text_list(output["rejection_codes"], "rejection_codes", expected=REJECTION_CODES)
    if _boolean(output["self_issued_allowed"], "self_issued_allowed"):
        raise ExternalAdoptionEvidenceError("self-issued identities are prohibited")
    if _boolean(output["local_retention_sufficient"], "local_retention_sufficient"):
        raise ExternalAdoptionEvidenceError("local retention is insufficient")
    if output["policy_status"] != "defined-not-executed":
        raise ExternalAdoptionEvidenceError("verification policy status differs")


def _validate_register(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.evidence_register")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "submissions",
            "trust_anchor_refs",
            "verified_roles",
            "selected_decision",
            "signed_decision_present",
            "register_status",
        },
        "outputs.evidence_register",
    )
    if output["schema_version"] != "phase5k-evidence-register/v1":
        raise ExternalAdoptionEvidenceError("invalid evidence-register schema")
    if output["request_id"] != request["request_id"]:
        raise ExternalAdoptionEvidenceError("evidence register request binding differs")
    if _exact_list(output["submissions"], "submissions"):
        raise ExternalAdoptionEvidenceError("no evidence submission has been admitted")
    if _exact_list(output["trust_anchor_refs"], "trust_anchor_refs"):
        raise ExternalAdoptionEvidenceError("no trust anchor has been admitted")
    if _exact_list(output["verified_roles"], "verified_roles"):
        raise ExternalAdoptionEvidenceError("no participant role has been verified")
    if output["selected_decision"] != "none":
        raise ExternalAdoptionEvidenceError("no decision may be selected")
    if _boolean(output["signed_decision_present"], "signed_decision_present"):
        raise ExternalAdoptionEvidenceError("no signed decision is present")
    if output["register_status"] != "awaiting-external-evidence":
        raise ExternalAdoptionEvidenceError("evidence register status differs")


def _validate_disposition(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.intake_disposition")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "disposition",
            "active_debt_ids",
            "external_evidence_received",
            "authenticated_participants",
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
            "required_next_stage",
        },
        "outputs.intake_disposition",
    )
    if output["schema_version"] != "phase5k-intake-disposition/v1":
        raise ExternalAdoptionEvidenceError("invalid intake-disposition schema")
    if output["request_id"] != request["request_id"]:
        raise ExternalAdoptionEvidenceError("intake disposition request binding differs")
    if output["disposition"] != "awaiting-external-evidence":
        raise ExternalAdoptionEvidenceError("intake disposition differs")
    _text_list(
        output["active_debt_ids"],
        "active_debt_ids",
        expected=ACTIVE_DEBT_IDS,
    )
    for field in (
        "external_evidence_received",
        "authenticated_participants",
        "adr_adopted",
        "p14_eligible",
        "p20_eligible",
        "release_ready",
        "production_ready",
        "deployment_authorized",
        "promotion_eligible",
        "superiority_established",
    ):
        if _boolean(output[field], field):
            raise ExternalAdoptionEvidenceError(f"{field} cannot be true")
    if output["authority"] != "none" or output["activation"] != "inert":
        raise ExternalAdoptionEvidenceError("intake cannot grant authority or activation")
    if output["required_next_stage"] != "external-evidence-submission":
        raise ExternalAdoptionEvidenceError("required next stage differs")


def validate_external_adoption_evidence_intake(value: Mapping[str, Any]) -> None:
    envelope = _exact_dict(value, "envelope")
    _fields(
        envelope,
        {
            "schema_version",
            "intake_id",
            "request",
            "outputs",
            "output_digests",
            "envelope_digest",
        },
        "envelope",
    )
    reject_private_content(envelope)
    if envelope["schema_version"] != ENVELOPE_SCHEMA:
        raise ExternalAdoptionEvidenceError("unsupported intake envelope schema")
    if envelope["intake_id"] != INTAKE_ID:
        raise ExternalAdoptionEvidenceError("intake envelope identity differs")
    request = _exact_dict(envelope["request"], "envelope.request")
    validate_evidence_intake_request(request)
    outputs = _exact_dict(envelope["outputs"], "envelope.outputs")
    if tuple(outputs) != OUTPUT_FIELDS:
        raise ExternalAdoptionEvidenceError("output fields or order differ")
    _validate_requirements(outputs["evidence_requirements"], request)
    _validate_policy(outputs["verification_policy"], request)
    _validate_register(outputs["evidence_register"], request)
    _validate_disposition(outputs["intake_disposition"], request)
    output_digests = _exact_dict(envelope["output_digests"], "output_digests")
    if tuple(output_digests) != OUTPUT_FIELDS:
        raise ExternalAdoptionEvidenceError("output digest fields or order differ")
    for field in OUTPUT_FIELDS:
        _sha256(output_digests[field], f"output_digests.{field}")
        if output_digests[field] != digest(outputs[field]):
            raise ExternalAdoptionEvidenceError(f"output digest mismatch: {field}")
    _sha256(envelope["envelope_digest"], "envelope.envelope_digest")
    body = {key: value for key, value in envelope.items() if key != "envelope_digest"}
    if envelope["envelope_digest"] != digest(body):
        raise ExternalAdoptionEvidenceError("envelope digest mismatch")
