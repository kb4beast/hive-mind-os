from __future__ import annotations

import unicodedata
from copy import deepcopy
from datetime import datetime
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
    if (
        type(value) is not str
        or not value.strip()
        or len(value) > limit
        or not value.isprintable()
        or unicodedata.normalize("NFC", value) != value
    ):
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


def _timestamp(value: Any, name: str) -> str:
    text = _bounded_string(value, name, limit=_MAX_TIME)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return text


def _relationship_basis(value: Any) -> dict[str, str]:
    fields = {
        "tenant_id",
        "repository_id",
        "source_record_id",
        "target_record_id",
        "relationship",
        "evidence_digest",
    }
    if type(value) is not dict or set(value) != fields:
        raise ValueError("relationship_basis fields are not exact")
    relationship = _bounded_string(value["relationship"], "relationship")
    if relationship not in RELATIONSHIP_CLASSIFICATIONS:
        raise ValueError("relationship classification is unsupported")
    return {
        "tenant_id": _bounded_string(value["tenant_id"], "tenant_id"),
        "repository_id": _bounded_string(value["repository_id"], "repository_id"),
        "source_record_id": _bounded_string(
            value["source_record_id"], "source_record_id"
        ),
        "target_record_id": _bounded_string(
            value["target_record_id"], "target_record_id"
        ),
        "relationship": relationship,
        "evidence_digest": _digest_string(
            value["evidence_digest"], "evidence_digest"
        ),
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
    body = _relationship_basis(
        {
            "tenant_id": tenant_id,
            "repository_id": repository_id,
            "source_record_id": source_record_id,
            "target_record_id": target_record_id,
            "relationship": relationship,
            "evidence_digest": evidence_digest,
        }
    )
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
    relationship_basis = receipt["relationship_basis"]
    if stage == "relationship":
        if classification not in RELATIONSHIP_CLASSIFICATIONS:
            raise ValueError("relationship event requires a classification")
        if opportunity_record_id is None:
            raise ValueError("relationship event requires an opportunity record")
        if relationship_basis is None:
            raise ValueError("relationship event requires its semantic preimage")
        expected_basis = {
            "tenant_id": receipt["tenant_id"],
            "repository_id": receipt["repository_id"],
            "source_record_id": receipt["encounter_record_id"],
            "target_record_id": opportunity_record_id,
            "relationship": classification,
            "evidence_digest": relationship_basis["evidence_digest"],
        }
        if relationship_basis != expected_basis:
            raise ValueError("relationship semantic preimage does not match event")
        expected_relation_ref = semantic_relationship_reference(
            **relationship_basis
        )
        if receipt["stage_reference"] != expected_relation_ref:
            raise ValueError(
                "relationship event requires a semantic relationship reference"
            )
    elif classification is not None or relationship_basis is not None:
        raise ValueError(
            "classification and relationship basis are valid only for relationship events"
        )
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
        "explorer-lifecycle-receipt:"
        + receipt["content_digest"].removeprefix(_DIGEST_PREFIX),
        "explorer-stage-reference-digest:"
        + receipt["stage_reference"]["digest"].removeprefix(_DIGEST_PREFIX),
        "explorer-subject-digest:"
        + receipt["subject_ref"]["digest"].removeprefix(_DIGEST_PREFIX),
    ]
    if opportunity_record_id is not None:
        claim_refs.append(f"foundation-record:{opportunity_record_id}")
    if receipt["classification"] is not None:
        claim_refs.append(f"explorer-relationship:{receipt['classification']}")
        claim_refs.append(
            "explorer-relationship-evidence-digest:"
            + receipt["relationship_basis"]["evidence_digest"].removeprefix(
                _DIGEST_PREFIX
            )
        )
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
        relation_refs.append(
            f"previous-lifecycle-event-id:{receipt['previous_event_id']}"
        )
        relation_refs.append(
            "previous-lifecycle-event-digest:"
            + receipt["previous_event_digest"].removeprefix(_DIGEST_PREFIX)
        )
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
    relationship_basis: Mapping[str, Any] | None = None,
    previous_event_id: str | None = None,
    previous_event_record_id: str | None = None,
    previous_event_digest: str | None = None,
    sensitivity: str = "private",
) -> dict[str, Any]:
    stage_value = _bounded_string(stage, "stage")
    if stage_value not in LIFECYCLE_STAGES:
        raise ValueError("lifecycle stage is unsupported")
    sensitivity_value = _bounded_string(sensitivity, "sensitivity")
    if sensitivity_value not in {"private", "safe-public"}:
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
        "observed_at": _timestamp(observed_at, "observed_at"),
        "recorded_at": _timestamp(recorded_at, "recorded_at"),
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
        "relationship_basis": (
            None
            if relationship_basis is None
            else _relationship_basis(relationship_basis)
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
        "sensitivity": sensitivity_value,
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
        "relationship_basis",
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
        relationship_basis=receipt["relationship_basis"],
        previous_event_id=receipt["previous_event_id"],
        previous_event_record_id=receipt["previous_event_record_id"],
        previous_event_digest=receipt["previous_event_digest"],
        sensitivity=receipt["sensitivity"],
    )
    if prepared != rebuilt:
        raise ValueError("prepared lifecycle event does not reproduce")
    return deepcopy(rebuilt["receipt"]), deepcopy(rebuilt["memory"])


def _prefixed(
    values: list[Any],
    prefix: str,
    *,
    required: bool = True,
) -> str | None:
    matches = [
        value.removeprefix(prefix)
        for value in values
        if type(value) is str and value.startswith(prefix)
    ]
    if len(matches) != (1 if required else min(1, len(matches))):
        raise ValueError(f"predecessor {prefix} identity is not exact")
    return matches[0] if matches else None


def _reconstruct_predecessor(
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    payload = previous["payload"]
    validation = validate_foundation("memory-record-v1", payload)
    if not validation.valid:
        raise ValueError("previous lifecycle memory contract is invalid")
    previous_event_id = current["previous_event_id"]
    previous_digest = current["previous_event_digest"]
    if (
        previous["record_type"] != "memory-record"
        or previous["schema_name"] != "memory-record-v1"
        or previous["tenant_id"] != current["tenant_id"]
        or previous["repository_id"] != current["repository_id"]
        or previous["actor_id"] != payload["actor_id"]
        or previous["observed_at"] != payload["observed_at"]
        or payload["memory_id"]
        != f"explorer-lifecycle:{current['lifecycle_id']}:{previous_event_id}"
        or payload["payload_digest"] != previous_digest
        or payload["content_digest"] != previous_digest
        or payload["correlation_id"] != current["lifecycle_id"]
        or payload["access_purpose"] != "explorer-lifecycle-reference"
        or payload["memory_kind"] != "opportunity"
        or payload["status"] != "active"
        or payload["sensitivity"] != current["sensitivity"]
        or payload["owner_id"] != current["owner_id"]
        or payload["mission_id"] != current["mission_id"]
        or payload["run_id"] != current["run_id"]
    ):
        raise ValueError("previous lifecycle memory identity does not match")
    claim_refs = payload["claim_refs"]
    relation_refs = payload["relation_refs"]
    stage = payload["step_id"]
    if stage not in LIFECYCLE_STAGES:
        raise ValueError("previous lifecycle stage is unsupported")
    receipt_digest = _digest_string(
        _DIGEST_PREFIX
        + str(_prefixed(claim_refs, "explorer-lifecycle-receipt:")),
        "previous receipt digest",
    )
    if receipt_digest != previous_digest:
        raise ValueError("previous lifecycle receipt digest does not match")
    stage_digest = _digest_string(
        _DIGEST_PREFIX
        + str(_prefixed(claim_refs, "explorer-stage-reference-digest:")),
        "previous stage reference digest",
    )
    subject_digest = _digest_string(
        _DIGEST_PREFIX
        + str(_prefixed(claim_refs, "explorer-subject-digest:")),
        "previous subject digest",
    )
    if "explorer-lifecycle:reference-only" not in claim_refs:
        raise ValueError("previous lifecycle reference-only boundary is missing")
    if f"explorer-lifecycle-stage:{stage}" not in claim_refs:
        raise ValueError("previous lifecycle stage marker is missing")
    encounter_prefix = "foundation-record:"
    if not payload["source_refs"] or not payload["source_refs"][0].startswith(
        encounter_prefix
    ):
        raise ValueError("previous encounter identity is missing")
    encounter_record_id = payload["source_refs"][0].removeprefix(encounter_prefix)
    subject_ref = {
        "ref": payload["generation_refs"][0],
        "digest": subject_digest,
    }
    if stage == "encounter":
        if len(payload["source_refs"]) != 2:
            raise ValueError("encounter predecessor source references are not exact")
        stage_reference = {
            "ref": payload["source_refs"][1],
            "digest": stage_digest,
        }
    elif stage == "relationship":
        relation_ref = _prefixed(relation_refs, "explorer-relationship:")
        stage_reference = {
            "ref": "explorer-relationship:" + str(relation_ref),
            "digest": stage_digest,
        }
    elif stage == "court":
        if len(payload["court_refs"]) != 1:
            raise ValueError("court predecessor reference is not exact")
        stage_reference = {"ref": payload["court_refs"][0], "digest": stage_digest}
    elif stage == "experiment":
        if len(payload["generation_refs"]) != 2:
            raise ValueError("experiment predecessor reference is not exact")
        stage_reference = {
            "ref": payload["generation_refs"][1],
            "digest": stage_digest,
        }
    else:
        if len(payload["evidence_refs"]) != 1:
            raise ValueError("outcome predecessor reference is not exact")
        stage_reference = {
            "ref": payload["evidence_refs"][0],
            "digest": stage_digest,
        }
    opportunity = _prefixed(claim_refs, "foundation-record:", required=False)
    classification = _prefixed(
        claim_refs, "explorer-relationship:", required=False
    )
    court_disposition = _prefixed(
        claim_refs, "court-disposition:", required=False
    )
    terminal_disposition = _prefixed(
        claim_refs, "explorer-terminal:", required=False
    )
    relationship_basis = None
    if stage == "relationship":
        evidence_digest = _digest_string(
            _DIGEST_PREFIX
            + str(
                _prefixed(
                    claim_refs,
                    "explorer-relationship-evidence-digest:",
                )
            ),
            "previous relationship evidence digest",
        )
        relationship_basis = {
            "tenant_id": payload["tenant_id"],
            "repository_id": payload["repository_id"],
            "source_record_id": encounter_record_id,
            "target_record_id": opportunity,
            "relationship": classification,
            "evidence_digest": evidence_digest,
        }
    prior_event_id = _prefixed(
        relation_refs, "previous-lifecycle-event-id:", required=False
    )
    prior_event_digest_text = _prefixed(
        relation_refs, "previous-lifecycle-event-digest:", required=False
    )
    prior_event_digest = (
        None
        if prior_event_digest_text is None
        else _digest_string(
            _DIGEST_PREFIX + prior_event_digest_text,
            "predecessor previous event digest",
        )
    )
    rebuilt = compile_explorer_idea_lifecycle_event(
        lifecycle_id=current["lifecycle_id"],
        event_id=previous_event_id,
        stage=stage,
        tenant_id=payload["tenant_id"],
        repository_id=payload["repository_id"],
        mission_id=payload["mission_id"],
        run_id=payload["run_id"],
        actor_id=payload["actor_id"],
        owner_id=payload["owner_id"],
        observed_at=payload["observed_at"],
        recorded_at=payload["recorded_at"],
        subject_ref=subject_ref,
        stage_reference=stage_reference,
        encounter_record_id=encounter_record_id,
        opportunity_record_id=opportunity,
        classification=classification,
        court_disposition=court_disposition,
        terminal_disposition=terminal_disposition,
        relationship_basis=relationship_basis,
        previous_event_id=prior_event_id,
        previous_event_record_id=payload["previous_record_id"],
        previous_event_digest=prior_event_digest,
        sensitivity=payload["sensitivity"],
    )
    if rebuilt["memory"] != payload or rebuilt["receipt"]["content_digest"] != previous_digest:
        raise ValueError("previous lifecycle event is not reconstructable")
    return rebuilt["receipt"]


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
        previous_receipt = _reconstruct_predecessor(previous, receipt)
        previous_payload = previous["payload"]
        if (
            previous["stream_id"] != prepared["stream_id"]
            or previous["record_id"] != receipt["previous_event_record_id"]
        ):
            raise ValueError("previous lifecycle event identity does not match")
        previous_stage = previous_receipt["stage"]
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
