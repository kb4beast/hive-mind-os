from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from .authority import AuthorityDecision
from .canonical import digest
from .contracts import validate_foundation
from .store import FoundationStore

LIFECYCLE_STAGES = ("encounter", "relationship", "court", "experiment", "outcome")
RELATIONSHIP_CLASSIFICATIONS = frozenset(
    {
        "appeal",
        "complement",
        "contradiction",
        "duplicate",
        "new",
        "not-duplicate",
        "refinement",
        "reinforcement",
        "variant",
    }
)
TERMINAL_DISPOSITIONS = frozenset(
    {
        "abandoned",
        "duplicate",
        "filtered",
        "invalid",
        "non-material",
        "policy-blocked",
    }
)
COURT_DISPOSITIONS = frozenset({"adopt", "adapt", "defer", "reject", "quarantine"})
_DIGEST_PREFIX = "sha256:"
_MAX_ID = 200
_MAX_TIME = 100


def _bounded_string(value: Any, name: str, *, limit: int = _MAX_ID) -> str:
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a bounded nonempty built-in string")
    return value


def _optional_string(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _bounded_string(value, name)


def _digest_string(value: Any, name: str) -> str:
    text = _bounded_string(value, name, limit=71)
    if (
        len(text) != 71
        or not text.startswith(_DIGEST_PREFIX)
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        raise ValueError(f"{name} must be a SHA-256 digest")
    return text


def _reference(value: Any, name: str) -> dict[str, str]:
    if type(value) is not dict or set(value) != {"ref", "digest"}:
        raise ValueError(f"{name} must contain exactly ref and digest")
    return {
        "ref": _bounded_string(value["ref"], f"{name}.ref"),
        "digest": _digest_string(value["digest"], f"{name}.digest"),
    }


def semantic_relationship_reference(
    *,
    tenant_id: str,
    repository_id: str,
    source_record_id: str,
    target_record_id: str,
    relationship: str,
    evidence_digest: str,
) -> dict[str, str]:
    relationship_value = _bounded_string(relationship, "relationship")
    if relationship_value not in RELATIONSHIP_CLASSIFICATIONS:
        raise ValueError("relationship classification is unsupported")
    body = {
        "tenant_id": _bounded_string(tenant_id, "tenant_id"),
        "repository_id": _bounded_string(repository_id, "repository_id"),
        "source_record_id": _bounded_string(source_record_id, "source_record_id"),
        "target_record_id": _bounded_string(target_record_id, "target_record_id"),
        "relationship": relationship_value,
        "evidence_digest": _digest_string(evidence_digest, "evidence_digest"),
    }
    identity = digest(body)
    return {
        "ref": f"explorer-relationship:{identity.removeprefix(_DIGEST_PREFIX)}",
        "digest": identity,
    }


def _validate_stage_fields(receipt: Mapping[str, Any]) -> None:
    stage = receipt["stage"]
    classification = receipt["classification"]
    court_disposition = receipt["court_disposition"]
    terminal_disposition = receipt["terminal_disposition"]
    opportunity_record_id = receipt["opportunity_record_id"]
    if stage == "relationship":
        if classification not in RELATIONSHIP_CLASSIFICATIONS:
            raise ValueError("relationship event requires a classification")
        if opportunity_record_id is None:
            raise ValueError("relationship event requires an opportunity record")
        expected_relation_ref = (
            "explorer-relationship:"
            + receipt["stage_reference"]["digest"].removeprefix(_DIGEST_PREFIX)
        )
        if receipt["stage_reference"]["ref"] != expected_relation_ref:
            raise ValueError(
                "relationship event requires a semantic relationship reference"
            )
    elif classification is not None:
        raise ValueError("classification is valid only for relationship events")
    if stage == "court":
        if court_disposition not in COURT_DISPOSITIONS:
            raise ValueError("court event requires a courtroom disposition")
        if opportunity_record_id is None:
            raise ValueError("court event requires an opportunity record")
    elif court_disposition is not None:
        raise ValueError("court disposition is valid only for court events")
    if stage in {"experiment", "outcome"} and opportunity_record_id is None:
        raise ValueError(f"{stage} event requires an opportunity record")
    if terminal_disposition is not None:
        if terminal_disposition not in TERMINAL_DISPOSITIONS:
            raise ValueError("terminal disposition is unsupported")
        if stage not in {"encounter", "relationship"}:
            raise ValueError("terminal disposition is limited to early lifecycle events")
    if stage == "relationship" and classification == "duplicate":
        if terminal_disposition != "duplicate":
            raise ValueError("duplicate relationship must be explicitly terminal")
    if terminal_disposition == "duplicate" and classification != "duplicate":
        raise ValueError("duplicate disposition requires duplicate classification")


def _seal(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "content_digest": digest(body)}


def _memory_payload(receipt: Mapping[str, Any]) -> dict[str, Any]:
    stage = receipt["stage"]
    stage_reference = receipt["stage_reference"]
    opportunity_record_id = receipt["opportunity_record_id"]
    previous_record_id = receipt["previous_event_record_id"]
    claim_refs = [
        "explorer-lifecycle:reference-only",
        f"explorer-lifecycle-stage:{stage}",
    ]
    if opportunity_record_id is not None:
        claim_refs.append(f"foundation-record:{opportunity_record_id}")
    if receipt["classification"] is not None:
        claim_refs.append(f"explorer-relationship:{receipt['classification']}")
    if receipt["court_disposition"] is not None:
        claim_refs.append(f"court-disposition:{receipt['court_disposition']}")
    if receipt["terminal_disposition"] is not None:
        claim_refs.append(f"explorer-terminal:{receipt['terminal_disposition']}")
    claim_refs.append(
        f"explorer-lifecycle-remaining:{receipt['remaining_stage_status']}"
    )
    relation_refs = [f"explorer-lifecycle:{receipt['lifecycle_id']}"]
    if previous_record_id is not None:
        relation_refs.append(f"previous-lifecycle-event:{previous_record_id}")
    source_refs = [f"foundation-record:{receipt['encounter_record_id']}"]
    evidence_refs: list[str] = []
    court_refs: list[str] = []
    generation_refs = [receipt["subject_ref"]["ref"]]
    if stage == "encounter":
        source_refs.append(stage_reference["ref"])
    elif stage == "relationship":
        relation_refs.append(stage_reference["ref"])
    elif stage == "court":
        court_refs.append(stage_reference["ref"])
    elif stage == "experiment":
        generation_refs.append(stage_reference["ref"])
    else:
        evidence_refs.append(stage_reference["ref"])
    lifecycle_digest = receipt["content_digest"]
    payload = {
        "record_type": "memory-record",
        "schema_version": 1,
        "memory_id": f"explorer-lifecycle:{receipt['lifecycle_id']}:{receipt['event_id']}",
        "memory_kind": "opportunity",
        "repository_id": receipt["repository_id"],
        "tenant_id": receipt["tenant_id"],
        "mission_id": receipt["mission_id"],
        "run_id": receipt["run_id"],
        "step_id": stage,
        "actor_id": receipt["actor_id"],
        "payload_digest": lifecycle_digest,
        "previous_record_id": previous_record_id,
        "supersedes_record_id": None,
        "observed_at": receipt["observed_at"],
        "recorded_at": receipt["recorded_at"],
        "causation_id": receipt["encounter_record_id"],
        "correlation_id": receipt["lifecycle_id"],
        "source_refs": source_refs,
        "claim_refs": claim_refs,
        "evidence_refs": evidence_refs,
        "court_refs": court_refs,
        "code_receipt_refs": [],
        "generation_refs": generation_refs,
        "status": "active",
        "confidence_ppm": None,
        "freshness_expires_at": None,
        "contradiction_refs": [],
        "relation_refs": relation_refs,
        "owner_id": receipt["owner_id"],
        "sensitivity": receipt["sensitivity"],
        "access_purpose": "explorer-lifecycle-reference",
        "retention": "governed",
        "deletion_policy": "tombstone",
        "quarantine_state": "none",
        "appeal_state": "available",
        "content_digest": lifecycle_digest,
        "protected_content_ref": None,
        "retrieval_receipt": None,
    }
    validation = validate_foundation("memory-record-v1", payload)
    if not validation.valid:
        raise ValueError("invalid lifecycle memory: " + "; ".join(validation.issues))
    return payload


def compile_explorer_idea_lifecycle_event(
    *,
    lifecycle_id: str,
    event_id: str,
    stage: str,
    tenant_id: str,
    repository_id: str,
    mission_id: str,
    run_id: str,
    actor_id: str,
    owner_id: str,
    observed_at: str,
    recorded_at: str,
    subject_ref: Mapping[str, Any],
    stage_reference: Mapping[str, Any],
    encounter_record_id: str,
    opportunity_record_id: str | None = None,
    classification: str | None = None,
    court_disposition: str | None = None,
    terminal_disposition: str | None = None,
    previous_event_id: str | None = None,
    previous_event_record_id: str | None = None,
    previous_event_digest: str | None = None,
    sensitivity: str = "private",
) -> dict[str, Any]:
    stage_value = _bounded_string(stage, "stage")
    if stage_value not in LIFECYCLE_STAGES:
        raise ValueError("lifecycle stage is unsupported")
    if sensitivity not in {"private", "safe-public"}:
        raise ValueError("lifecycle events support private or safe-public metadata")
    previous = (
        previous_event_id,
        previous_event_record_id,
        previous_event_digest,
    )
    if any(item is None for item in previous) and any(item is not None for item in previous):
        raise ValueError("previous lifecycle identity must be jointly present")
    body = {
        "record_type": "explorer-idea-lifecycle-event",
        "schema_version": 1,
        "lifecycle_id": _bounded_string(lifecycle_id, "lifecycle_id"),
        "event_id": _bounded_string(event_id, "event_id"),
        "stage": stage_value,
        "tenant_id": _bounded_string(tenant_id, "tenant_id"),
        "repository_id": _bounded_string(repository_id, "repository_id"),
        "mission_id": _bounded_string(mission_id, "mission_id"),
        "run_id": _bounded_string(run_id, "run_id"),
        "actor_id": _bounded_string(actor_id, "actor_id"),
        "owner_id": _bounded_string(owner_id, "owner_id"),
        "observed_at": _bounded_string(observed_at, "observed_at", limit=_MAX_TIME),
        "recorded_at": _bounded_string(recorded_at, "recorded_at", limit=_MAX_TIME),
        "subject_ref": _reference(subject_ref, "subject_ref"),
        "stage_reference": _reference(stage_reference, "stage_reference"),
        "encounter_record_id": _bounded_string(
            encounter_record_id, "encounter_record_id"
        ),
        "opportunity_record_id": _optional_string(
            opportunity_record_id, "opportunity_record_id"
        ),
        "classification": _optional_string(classification, "classification"),
        "court_disposition": _optional_string(
            court_disposition, "court_disposition"
        ),
        "terminal_disposition": _optional_string(
            terminal_disposition, "terminal_disposition"
        ),
        "previous_event_id": _optional_string(previous_event_id, "previous_event_id"),
        "previous_event_record_id": _optional_string(
            previous_event_record_id, "previous_event_record_id"
        ),
        "previous_event_digest": (
            None
            if previous_event_digest is None
            else _digest_string(previous_event_digest, "previous_event_digest")
        ),
        "reference_status": "pinned-unverified",
        "remaining_stage_status": (
            "not-applicable-terminal"
            if terminal_disposition is not None
            else "unknown"
        ),
        "sensitivity": sensitivity,
        "comparison_status": "not-run",
        "lifecycle_complete_claimed": False,
        "value_claimed": False,
        "promotion_authorized": False,
        "activation_authorized": False,
    }
    expected_event_prefix = f"{body['lifecycle_id']}:{stage_value}"
    if (
        stage_value == "encounter"
        and body["event_id"] != expected_event_prefix
    ) or (
        stage_value != "encounter"
        and not body["event_id"].startswith(expected_event_prefix + ":")
    ):
        raise ValueError("event_id must be scoped to its lifecycle and stage")
    if stage_value == "encounter" and previous_event_id is not None:
        raise ValueError("encounter must be the first lifecycle event")
    if stage_value != "encounter" and previous_event_id is None:
        raise ValueError("later lifecycle events require an exact predecessor")
    _validate_stage_fields(body)
    receipt = _seal(body)
    memory = _memory_payload(receipt)
    return {
        "receipt": deepcopy(receipt),
        "memory": deepcopy(memory),
        "stream_id": f"explorer-lifecycle:{receipt['lifecycle_id']}",
        "idempotency_key": f"explorer-lifecycle-event:{receipt['event_id']}",
    }


def _validate_prepared(prepared: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if (
        type(prepared) is not dict
        or set(prepared) != {"receipt", "memory", "stream_id", "idempotency_key"}
        or type(prepared["receipt"]) is not dict
        or type(prepared["memory"]) is not dict
    ):
        raise ValueError("prepared lifecycle event has an invalid shape")
    receipt = prepared["receipt"]
    if set(receipt) != {
        "record_type",
        "schema_version",
        "lifecycle_id",
        "event_id",
        "stage",
        "tenant_id",
        "repository_id",
        "mission_id",
        "run_id",
        "actor_id",
        "owner_id",
        "observed_at",
        "recorded_at",
        "subject_ref",
        "stage_reference",
        "encounter_record_id",
        "opportunity_record_id",
        "classification",
        "court_disposition",
        "terminal_disposition",
        "previous_event_id",
        "previous_event_record_id",
        "previous_event_digest",
        "reference_status",
        "remaining_stage_status",
        "sensitivity",
        "comparison_status",
        "lifecycle_complete_claimed",
        "value_claimed",
        "promotion_authorized",
        "activation_authorized",
        "content_digest",
    }:
        raise ValueError("lifecycle receipt fields are not exact")
    rebuilt = compile_explorer_idea_lifecycle_event(
        lifecycle_id=receipt["lifecycle_id"],
        event_id=receipt["event_id"],
        stage=receipt["stage"],
        tenant_id=receipt["tenant_id"],
        repository_id=receipt["repository_id"],
        mission_id=receipt["mission_id"],
        run_id=receipt["run_id"],
        actor_id=receipt["actor_id"],
        owner_id=receipt["owner_id"],
        observed_at=receipt["observed_at"],
        recorded_at=receipt["recorded_at"],
        subject_ref=receipt["subject_ref"],
        stage_reference=receipt["stage_reference"],
        encounter_record_id=receipt["encounter_record_id"],
        opportunity_record_id=receipt["opportunity_record_id"],
        classification=receipt["classification"],
        court_disposition=receipt["court_disposition"],
        terminal_disposition=receipt["terminal_disposition"],
        previous_event_id=receipt["previous_event_id"],
        previous_event_record_id=receipt["previous_event_record_id"],
        previous_event_digest=receipt["previous_event_digest"],
        sensitivity=receipt["sensitivity"],
    )
    if prepared != rebuilt:
        raise ValueError("prepared lifecycle event does not reproduce")
    return deepcopy(rebuilt["receipt"]), deepcopy(rebuilt["memory"])


def append_explorer_idea_lifecycle_event(
    store: FoundationStore,
    prepared: Mapping[str, Any],
    *,
    authority: AuthorityDecision,
) -> dict[str, Any]:
    receipt, memory = _validate_prepared(prepared)
    previous_id = receipt["previous_event_id"]
    if previous_id is not None:
        previous = store.record_by_idempotency_key(
            tenant_id=receipt["tenant_id"],
            repository_id=receipt["repository_id"],
            idempotency_key=f"explorer-lifecycle-event:{previous_id}",
        )
        if previous is None:
            raise ValueError("previous lifecycle event is unavailable")
        previous_payload = previous["payload"]
        if (
            previous["record_type"] != "memory-record"
            or previous["schema_name"] != "memory-record-v1"
            or previous["stream_id"] != prepared["stream_id"]
            or previous["record_id"] != receipt["previous_event_record_id"]
            or previous_payload["content_digest"] != receipt["previous_event_digest"]
            or previous_payload["correlation_id"] != receipt["lifecycle_id"]
        ):
            raise ValueError("previous lifecycle event identity does not match")
        previous_stage = previous_payload["step_id"]
        allowed = {
            "encounter": {"relationship"},
            "relationship": {"court"},
            "court": {"court", "experiment"},
            "experiment": {"experiment", "outcome"},
            "outcome": {"outcome"},
        }
        if receipt["stage"] not in allowed[previous_stage]:
            raise ValueError("lifecycle stage transition is invalid")
        if any(
            str(value).startswith("explorer-terminal:")
            for value in previous_payload["claim_refs"]
        ):
            raise ValueError("terminal lifecycle event cannot have a successor")
    return store.append_record(
        authority=authority,
        foundation_action="foundation.memory.write",
        tenant_id=receipt["tenant_id"],
        repository_id=receipt["repository_id"],
        record_type="memory-record",
        schema_name="memory-record-v1",
        stream_id=prepared["stream_id"],
        payload=memory,
        actor_id=receipt["actor_id"],
        idempotency_key=prepared["idempotency_key"],
        observed_at=receipt["observed_at"],
        correlation_id=receipt["lifecycle_id"],
        causation_id=receipt["encounter_record_id"],
        sensitivity=receipt["sensitivity"],
        retention="governed",
        status="active",
    )
