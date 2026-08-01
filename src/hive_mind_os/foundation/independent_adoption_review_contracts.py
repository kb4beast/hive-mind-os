from __future__ import annotations

import re
from typing import Any, Mapping, cast

from .canonical import digest, reject_private_content

PACKET_ID = "packet:phase5j-independent-adoption-review"
REPOSITORY_ID = "github:kb4beast/hive-mind-os"
TENANT_ID = "tenant:kb4beast"
ACCEPTED_BASE_COMMIT = "49b78e211053f8aec427351680c3fd683044420d"
REQUEST_SCHEMA = "phase5j-review-packet-request/v1"
ENVELOPE_SCHEMA = "phase5j-independent-adoption-review-packet/v1"

DOCUMENTS = (
    ("phase5i-merge", "git:49b78e211053f8aec427351680c3fd683044420d"),
    ("adr-015", "docs/architecture/ADR-015-POST-P13-PRODUCTION-AND-TRUST-PROGRAM.md"),
    ("post-p13-overview", "docs/plan/01_POST_P13_OVERVIEW.md"),
    ("phase5-debt-plan", "docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md"),
)
PARTICIPANT_ROLES = ("curator", "judge", "orchestrator")
DECISION_OPTIONS = ("adopt", "adapt", "reject", "defer", "abstain")
EXTERNAL_INPUT_IDS = (
    "provider-authority",
    "identity-and-signing",
    "external-retention",
    "deployment-and-rollback",
    "source-and-license",
    "comparator-access",
)
ACTIVE_DEBT_IDS = tuple(
    f"P5{phase}-DEBT-{index:02d}"
    for phase in ("D", "E", "F", "G", "H", "I")
    for index in range(1, 6)
)
OUTPUT_FIELDS = (
    "review_packet_manifest",
    "participant_requirements",
    "decision_templates",
    "external_handoff",
)
PARTICIPANT_REQUIREMENTS = (
    "non-self-issued-identity",
    "role-separation",
    "conflict-of-interest-disclosure",
    "exact-scope-binding",
    "signature-verification",
    "external-retention",
    "expiry",
    "revocation",
    "replay-protection",
)
HANDOFF_ACTIONS = (
    "appoint-distinct-external-curator-judge-and-orchestrator",
    "verify-identities-conflicts-authority-and-scope",
    "review-frozen-packet-and-all-adverse-evidence",
    "record-independent-curator-recommendation",
    "record-independent-judge-disposition",
    "record-independent-orchestrator-confirmation",
    "retain-signed-records-outside-agent-controlled-storage",
    "return-verifiable-result-with-expiry-and-revocation-data",
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class IndependentAdoptionReviewError(ValueError):
    pass


def _exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise IndependentAdoptionReviewError(f"{label} must be an exact dict")
    return cast(dict[str, Any], value)


def _exact_list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise IndependentAdoptionReviewError(f"{label} must be an exact list")
    return cast(list[Any], value)


def _fields(document: dict[str, Any], expected: set[str], label: str) -> None:
    observed = set(document)
    if observed != expected:
        raise IndependentAdoptionReviewError(
            f"{label} fields differ: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )


def _text(value: Any, label: str, *, maximum: int = 16_000) -> str:
    if type(value) is not str:
        raise IndependentAdoptionReviewError(f"{label} must be a string")
    result = cast(str, value)
    if not result or result != result.strip() or len(result) > maximum:
        raise IndependentAdoptionReviewError(
            f"{label} must be non-empty, trimmed, and bounded"
        )
    return result


def _identifier(value: Any, label: str) -> str:
    result = _text(value, label, maximum=256)
    if _IDENTIFIER.fullmatch(result) is None:
        raise IndependentAdoptionReviewError(f"{label} is not a valid identifier")
    return result


def _sha256(value: Any, label: str) -> str:
    result = _text(value, label, maximum=71)
    if _SHA256.fullmatch(result) is None:
        raise IndependentAdoptionReviewError(
            f"{label} is not a canonical SHA-256 digest"
        )
    return result


def _git_object(value: Any, label: str) -> str:
    result = _text(value, label, maximum=40)
    if _GIT_OBJECT.fullmatch(result) is None:
        raise IndependentAdoptionReviewError(f"{label} is not a full Git object ID")
    return result


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise IndependentAdoptionReviewError(f"{label} must be a boolean")
    return cast(bool, value)


def _text_list(
    value: Any,
    label: str,
    *,
    expected: tuple[str, ...] | None = None,
    maximum: int = 128,
) -> list[str]:
    items = _exact_list(value, label)
    if not items or len(items) > maximum:
        raise IndependentAdoptionReviewError(f"{label} has an invalid item count")
    result = [_text(item, f"{label}[{index}]") for index, item in enumerate(items)]
    if len(set(result)) != len(result):
        raise IndependentAdoptionReviewError(f"{label} contains duplicate values")
    if expected is not None and tuple(result) != expected:
        raise IndependentAdoptionReviewError(f"{label} differs from the fixed inventory")
    return result


def _validate_document(value: Any, index: int) -> dict[str, Any]:
    document = _exact_dict(value, f"documents[{index}]")
    _fields(
        document,
        {"document_id", "path", "digest", "status"},
        f"documents[{index}]",
    )
    expected_id, expected_path = DOCUMENTS[index]
    if document["document_id"] != expected_id or document["path"] != expected_path:
        raise IndependentAdoptionReviewError("document identity or path differs")
    _sha256(document["digest"], f"documents[{index}].digest")
    if document["status"] != "frozen-proposed":
        raise IndependentAdoptionReviewError("documents must remain frozen and proposed")
    return document


def validate_review_packet_request(value: Mapping[str, Any]) -> None:
    request = _exact_dict(value, "request")
    _fields(
        request,
        {
            "schema_version",
            "request_id",
            "packet_id",
            "repository_id",
            "tenant_id",
            "subject_commit",
            "subject_tree",
            "phase5i_envelope_digest",
            "documents",
            "active_debt_ids",
            "external_input_ids",
            "requested_next_stage",
            "authority",
            "activation",
        },
        "request",
    )
    reject_private_content(request)
    if request["schema_version"] != REQUEST_SCHEMA:
        raise IndependentAdoptionReviewError("unsupported review-packet request schema")
    _identifier(request["request_id"], "request.request_id")
    if request["packet_id"] != PACKET_ID:
        raise IndependentAdoptionReviewError("request packet identity differs")
    if request["repository_id"] != REPOSITORY_ID or request["tenant_id"] != TENANT_ID:
        raise IndependentAdoptionReviewError("request scope differs")
    if request["subject_commit"] != ACCEPTED_BASE_COMMIT:
        raise IndependentAdoptionReviewError("request commit is not the Phase 5I merge")
    _git_object(request["subject_commit"], "request.subject_commit")
    _git_object(request["subject_tree"], "request.subject_tree")
    _sha256(request["phase5i_envelope_digest"], "request.phase5i_envelope_digest")
    documents = _exact_list(request["documents"], "request.documents")
    if len(documents) != len(DOCUMENTS):
        raise IndependentAdoptionReviewError("request must contain every frozen document")
    for index, document in enumerate(documents):
        _validate_document(document, index)
    _text_list(
        request["active_debt_ids"],
        "request.active_debt_ids",
        expected=ACTIVE_DEBT_IDS,
    )
    _text_list(
        request["external_input_ids"],
        "request.external_input_ids",
        expected=EXTERNAL_INPUT_IDS,
    )
    if request["requested_next_stage"] != "external-independent-review":
        raise IndependentAdoptionReviewError("requested next stage differs")
    if request["authority"] != "none" or request["activation"] != "inert":
        raise IndependentAdoptionReviewError("request cannot grant authority or activation")


def _validate_manifest(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.review_packet_manifest")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "subject_commit",
            "subject_tree",
            "phase5i_envelope_digest",
            "documents",
            "active_debt_ids",
            "external_input_ids",
            "packet_status",
            "review_status",
        },
        "outputs.review_packet_manifest",
    )
    if output["schema_version"] != "phase5j-review-packet-manifest/v1":
        raise IndependentAdoptionReviewError("invalid packet-manifest schema")
    for field in (
        "request_id",
        "subject_commit",
        "subject_tree",
        "phase5i_envelope_digest",
        "documents",
        "active_debt_ids",
        "external_input_ids",
    ):
        if output[field] != request[field]:
            raise IndependentAdoptionReviewError(f"packet manifest {field} binding differs")
    if output["packet_status"] != "ready-for-external-review":
        raise IndependentAdoptionReviewError("packet status differs")
    if output["review_status"] != "not-run":
        raise IndependentAdoptionReviewError("review cannot be represented as executed")


def _validate_participants(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.participant_requirements")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "participants",
            "authenticated_participants",
            "requirements_satisfied",
        },
        "outputs.participant_requirements",
    )
    if output["schema_version"] != "phase5j-participant-requirements/v1":
        raise IndependentAdoptionReviewError("invalid participant-requirements schema")
    if output["request_id"] != request["request_id"]:
        raise IndependentAdoptionReviewError("participant request binding differs")
    participants = _exact_list(output["participants"], "participants")
    if len(participants) != len(PARTICIPANT_ROLES):
        raise IndependentAdoptionReviewError("participant inventory differs")
    for index, participant in enumerate(participants):
        item = _exact_dict(participant, f"participants[{index}]")
        _fields(
            item,
            {
                "role_id",
                "status",
                "requirements",
                "identity_evidence",
                "signature_evidence",
                "execution_evidence",
                "external_retention_evidence",
            },
            f"participants[{index}]",
        )
        if item["role_id"] != PARTICIPANT_ROLES[index]:
            raise IndependentAdoptionReviewError("participant order or identity differs")
        if item["status"] != "required-not-authenticated":
            raise IndependentAdoptionReviewError("participant cannot claim authentication")
        _text_list(
            item["requirements"],
            "participant.requirements",
            expected=PARTICIPANT_REQUIREMENTS,
        )
        for field in (
            "identity_evidence",
            "signature_evidence",
            "execution_evidence",
            "external_retention_evidence",
        ):
            if item[field] != "missing":
                raise IndependentAdoptionReviewError(
                    "participant evidence cannot be represented as present"
                )
    if _boolean(output["authenticated_participants"], "authenticated_participants"):
        raise IndependentAdoptionReviewError("authenticated participants are absent")
    if _boolean(output["requirements_satisfied"], "requirements_satisfied"):
        raise IndependentAdoptionReviewError("participant requirements are unsatisfied")


def _validate_decisions(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.decision_templates")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "options",
            "selected_decision",
            "review_completed",
            "signed_decision_present",
        },
        "outputs.decision_templates",
    )
    if output["schema_version"] != "phase5j-decision-templates/v1":
        raise IndependentAdoptionReviewError("invalid decision-template schema")
    if output["request_id"] != request["request_id"]:
        raise IndependentAdoptionReviewError("decision request binding differs")
    options = _exact_list(output["options"], "decision options")
    if len(options) != len(DECISION_OPTIONS):
        raise IndependentAdoptionReviewError("decision option inventory differs")
    for index, option in enumerate(options):
        item = _exact_dict(option, f"options[{index}]")
        _fields(
            item,
            {
                "decision_id",
                "selected",
                "signed",
                "participant_role",
                "scope_narrowing_required",
                "evidence_ref",
            },
            f"options[{index}]",
        )
        if item["decision_id"] != DECISION_OPTIONS[index]:
            raise IndependentAdoptionReviewError("decision option order differs")
        if _boolean(item["selected"], "option.selected"):
            raise IndependentAdoptionReviewError("no decision may be preselected")
        if _boolean(item["signed"], "option.signed"):
            raise IndependentAdoptionReviewError("no decision may be pre-signed")
        if item["participant_role"] != "judge":
            raise IndependentAdoptionReviewError("decision authority role differs")
        expected_narrowing = item["decision_id"] == "adapt"
        if _boolean(item["scope_narrowing_required"], "scope_narrowing_required") != expected_narrowing:
            raise IndependentAdoptionReviewError("scope-narrowing semantics differ")
        if item["evidence_ref"] != "missing":
            raise IndependentAdoptionReviewError("decision evidence is not present")
    if output["selected_decision"] != "none":
        raise IndependentAdoptionReviewError("packet cannot select a decision")
    if _boolean(output["review_completed"], "review_completed"):
        raise IndependentAdoptionReviewError("review is not completed")
    if _boolean(output["signed_decision_present"], "signed_decision_present"):
        raise IndependentAdoptionReviewError("signed decision is absent")


def _validate_handoff(value: Any, request: dict[str, Any]) -> None:
    output = _exact_dict(value, "outputs.external_handoff")
    _fields(
        output,
        {
            "schema_version",
            "request_id",
            "handoff_status",
            "actions",
            "external_submission_received",
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
        },
        "outputs.external_handoff",
    )
    if output["schema_version"] != "phase5j-external-handoff/v1":
        raise IndependentAdoptionReviewError("invalid external-handoff schema")
    if output["request_id"] != request["request_id"]:
        raise IndependentAdoptionReviewError("handoff request binding differs")
    if output["handoff_status"] != "external-action-required":
        raise IndependentAdoptionReviewError("handoff must require external action")
    _text_list(output["actions"], "handoff.actions", expected=HANDOFF_ACTIONS)
    for field in (
        "external_submission_received",
        "adr_adopted",
        "p14_eligible",
        "p20_eligible",
        "release_ready",
        "production_ready",
        "deployment_authorized",
        "promotion_eligible",
        "superiority_established",
    ):
        if _boolean(output[field], f"handoff.{field}"):
            raise IndependentAdoptionReviewError(f"handoff {field} must remain false")
    if output["authority"] != "none" or output["activation"] != "inert":
        raise IndependentAdoptionReviewError("handoff cannot grant authority or activation")


def validate_independent_adoption_review_packet(value: Mapping[str, Any]) -> None:
    envelope = _exact_dict(value, "envelope")
    _fields(
        envelope,
        {
            "schema_version",
            "packet_id",
            "request",
            "outputs",
            "output_digests",
            "envelope_digest",
        },
        "envelope",
    )
    reject_private_content(envelope)
    if envelope["schema_version"] != ENVELOPE_SCHEMA or envelope["packet_id"] != PACKET_ID:
        raise IndependentAdoptionReviewError("envelope identity differs")
    request = _exact_dict(envelope["request"], "envelope.request")
    validate_review_packet_request(request)
    outputs = _exact_dict(envelope["outputs"], "envelope.outputs")
    _fields(outputs, set(OUTPUT_FIELDS), "envelope.outputs")
    _validate_manifest(outputs["review_packet_manifest"], request)
    _validate_participants(outputs["participant_requirements"], request)
    _validate_decisions(outputs["decision_templates"], request)
    _validate_handoff(outputs["external_handoff"], request)
    output_digests = _exact_dict(envelope["output_digests"], "output_digests")
    _fields(output_digests, set(OUTPUT_FIELDS), "output_digests")
    for field in OUTPUT_FIELDS:
        if output_digests[field] != digest(outputs[field]):
            raise IndependentAdoptionReviewError(f"{field} digest differs")
    supplied_envelope_digest = _sha256(envelope["envelope_digest"], "envelope_digest")
    unsigned = dict(envelope)
    del unsigned["envelope_digest"]
    if supplied_envelope_digest != digest(unsigned):
        raise IndependentAdoptionReviewError("envelope digest differs")
