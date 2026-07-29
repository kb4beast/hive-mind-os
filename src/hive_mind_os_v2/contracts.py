"""Additive, provider-neutral contracts for the quarantined Phase 2 foundation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from typing import TypeAlias, cast
from uuid import uuid4

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,254}$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_json(value: object, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} contains a non-string object key")
            _validate_json(item, f"{path}.{key}")
        return
    raise TypeError(f"{path} contains unsupported JSON value {type(value).__name__}")


def canonical_json(value: object) -> str:
    """Return the one canonical JSON representation used for content addressing."""

    _validate_json(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def contract_digest(value: object) -> str:
    return f"sha256:{sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def _copy_json_object(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], json.loads(canonical_json(value)))


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_identifier(value: str, field_name: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} is not a stable identifier: {value!r}")


def _require_digest(value: str | None, field_name: str) -> None:
    if value is not None and not _DIGEST_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_timestamp(value: str, field_name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


class Sensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class RetentionClass(str, Enum):
    TRANSIENT = "transient"
    STANDARD = "standard"
    LONG_TERM = "long-term"
    LEGAL_HOLD = "legal-hold"


@dataclass(frozen=True, slots=True)
class RepositoryIdentity:
    tenant_id: str
    repository_id: str
    canonical_uri: str
    default_branch: str | None = None
    vcs_type: str = "git"
    schema_version: int = 2
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_identifier(self.tenant_id, "tenant_id")
        _require_identifier(self.repository_id, "repository_id")
        _require_text(self.canonical_uri, "canonical_uri")
        _require_identifier(self.vcs_type, "vcs_type")
        if self.default_branch is not None:
            _require_text(self.default_branch, "default_branch")
        if self.schema_version != 2:
            raise ValueError("repository identity schema_version must be 2")
        _require_timestamp(self.created_at, "created_at")

    def identity_material(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "tenant_id": self.tenant_id,
            "repository_id": self.repository_id,
            "canonical_uri": self.canonical_uri,
            "default_branch": self.default_branch,
            "vcs_type": self.vcs_type,
        }

    @property
    def identity_digest(self) -> str:
        return contract_digest(self.identity_material())

    def to_contract(self) -> dict[str, object]:
        return {**self.identity_material(), "created_at": self.created_at}


@dataclass(frozen=True, slots=True)
class MemoryRelation:
    relation_type: str
    target_record_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.relation_type, "relation_type")
        _require_identifier(self.target_record_id, "target_record_id")

    def to_contract(self) -> dict[str, str]:
        return {
            "relation_type": self.relation_type,
            "target_record_id": self.target_record_id,
        }


class MemoryDisposition(str, Enum):
    ACTIVE = "active"
    SUPERSESSION = "supersession"
    TOMBSTONE = "tombstone"


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    tenant_id: str
    repository_id: str
    record_type: str
    actor_id: str
    source_uri: str
    payload: dict[str, JsonValue]
    source_digest: str | None = None
    relations: tuple[MemoryRelation, ...] = ()
    disposition: MemoryDisposition = MemoryDisposition.ACTIVE
    supersedes_record_id: str | None = None
    tombstone_reason: str | None = None
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    retention: RetentionClass = RetentionClass.STANDARD
    confidence: float | None = None
    record_id: str = field(default_factory=lambda: f"memory:{uuid4()}")
    occurred_at: str = field(default_factory=utc_now)
    observed_at: str = field(default_factory=utc_now)
    schema_version: int = 2

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "repository_id",
            "record_type",
            "actor_id",
            "record_id",
        ):
            _require_identifier(getattr(self, field_name), field_name)
        _require_text(self.source_uri, "source_uri")
        _require_digest(self.source_digest, "source_digest")
        _require_timestamp(self.occurred_at, "occurred_at")
        _require_timestamp(self.observed_at, "observed_at")
        if self.schema_version != 2:
            raise ValueError("memory record schema_version must be 2")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.disposition is MemoryDisposition.ACTIVE:
            if self.supersedes_record_id is not None or self.tombstone_reason is not None:
                raise ValueError("active records cannot supersede or tombstone another record")
        elif self.disposition is MemoryDisposition.SUPERSESSION:
            if self.supersedes_record_id is None:
                raise ValueError("supersession records require supersedes_record_id")
            if self.tombstone_reason is not None:
                raise ValueError("supersession records cannot carry a tombstone reason")
        else:
            if self.supersedes_record_id is None or not (self.tombstone_reason or "").strip():
                raise ValueError("tombstones require a target and non-empty reason")
        if self.supersedes_record_id is not None:
            _require_identifier(self.supersedes_record_id, "supersedes_record_id")
            if self.supersedes_record_id == self.record_id:
                raise ValueError("a memory record cannot supersede itself")
        seen_relations: set[tuple[str, str]] = set()
        for relation in self.relations:
            key = (relation.relation_type, relation.target_record_id)
            if key in seen_relations:
                raise ValueError(f"duplicate memory relation: {key!r}")
            if relation.target_record_id == self.record_id:
                raise ValueError("a memory record cannot relate to itself")
            seen_relations.add(key)
        object.__setattr__(self, "payload", _copy_json_object(self.payload))
        object.__setattr__(self, "relations", tuple(self.relations))

    @property
    def payload_digest(self) -> str:
        return contract_digest(self.payload)

    def to_contract(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "tenant_id": self.tenant_id,
            "repository_id": self.repository_id,
            "record_type": self.record_type,
            "actor_id": self.actor_id,
            "source_uri": self.source_uri,
            "source_digest": self.source_digest,
            "payload": self.payload,
            "payload_digest": self.payload_digest,
            "relations": [relation.to_contract() for relation in self.relations],
            "disposition": self.disposition.value,
            "supersedes_record_id": self.supersedes_record_id,
            "tombstone_reason": self.tombstone_reason,
            "sensitivity": self.sensitivity.value,
            "retention": self.retention.value,
            "confidence": self.confidence,
            "occurred_at": self.occurred_at,
            "observed_at": self.observed_at,
        }


class AttemptKind(str, Enum):
    MODEL = "model"
    TOOL = "tool"
    HOST = "host"


class UsageOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class UsagePurpose(str, Enum):
    ACTING = "acting"
    ADVOCACY = "advocacy"
    CROSS_EXAMINATION = "cross-examination"
    VERIFICATION = "verification"
    JUDGMENT = "judgment"
    NEUTRAL = "neutral"


class ReconciliationStatus(str, Enum):
    UNAVAILABLE = "unavailable"
    UNRECONCILED = "unreconciled"
    PARTIAL = "partial"
    RECONCILED = "reconciled"
    MISMATCH = "mismatch"


class UsageAxis(str, Enum):
    INPUT_TOKENS = "input-tokens"
    OUTPUT_TOKENS = "output-tokens"
    CACHE_READ_INPUT_TOKENS = "cache-read-input-tokens"
    CACHE_WRITE_INPUT_TOKENS = "cache-write-input-tokens"
    REASONING_TOKENS = "reasoning-tokens"
    AUDIO_INPUT_TOKENS = "audio-input-tokens"
    AUDIO_OUTPUT_TOKENS = "audio-output-tokens"
    IMAGE_INPUT_UNITS = "image-input-units"
    IMAGE_OUTPUT_UNITS = "image-output-units"
    TOOL_CALLS = "tool-calls"


@dataclass(frozen=True, slots=True)
class NativeUsageField:
    path: str
    value: JsonScalar
    unit: str | None = None
    semantics: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.path, "native usage path")
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            if self.value < 0 or (isinstance(self.value, float) and not math.isfinite(self.value)):
                raise ValueError("native usage numbers must be finite and non-negative")
        if isinstance(self.value, str) and len(self.value) > 512:
            raise ValueError("native usage string exceeds 512 characters")
        if self.unit is not None:
            _require_identifier(self.unit, "native usage unit")
        if self.semantics is not None:
            _require_text(self.semantics, "native usage semantics")

    def to_contract(self) -> dict[str, object]:
        return {
            "path": self.path,
            "value": self.value,
            "unit": self.unit,
            "semantics": self.semantics,
        }


@dataclass(frozen=True, slots=True)
class NormalizedUsageDimension:
    axis: UsageAxis
    value: int | float
    unit: str
    derivation: str
    estimated: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or self.value < 0:
            raise ValueError("normalized usage values must be non-negative numbers")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("normalized usage values must be finite")
        _require_identifier(self.unit, "normalized usage unit")
        _require_text(self.derivation, "normalized usage derivation")

    def to_contract(self) -> dict[str, object]:
        return {
            "axis": self.axis.value,
            "value": self.value,
            "unit": self.unit,
            "derivation": self.derivation,
            "estimated": self.estimated,
        }


@dataclass(frozen=True, slots=True)
class CostObservation:
    amount: str
    currency: str
    provenance: str
    price_card_version: str | None = None
    estimated: bool = False

    def __post_init__(self) -> None:
        try:
            parsed = Decimal(self.amount)
        except InvalidOperation as error:
            raise ValueError("cost amount must be a decimal string") from error
        if not parsed.is_finite() or parsed < 0:
            raise ValueError("cost amount must be finite and non-negative")
        if not _CURRENCY_PATTERN.fullmatch(self.currency):
            raise ValueError("currency must be an uppercase ISO-4217 code")
        _require_text(self.provenance, "cost provenance")
        if self.price_card_version is not None:
            _require_text(self.price_card_version, "price_card_version")

    def to_contract(self) -> dict[str, object]:
        return {
            "amount": self.amount,
            "currency": self.currency,
            "provenance": self.provenance,
            "price_card_version": self.price_card_version,
            "estimated": self.estimated,
        }


@dataclass(frozen=True, slots=True)
class UsageEvent:
    tenant_id: str
    repository_id: str
    mission_id: str
    run_id: str
    step_id: str
    role: str
    work_item_id: str
    actor_id: str
    purpose: UsagePurpose
    attempt_id: str
    attempt_kind: AttemptKind
    outcome: UsageOutcome
    trace_id: str
    span_id: str
    provider: str | None = None
    model: str | None = None
    model_version: str | None = None
    tool_name: str | None = None
    host: str | None = None
    provider_request_id: str | None = None
    budget_lease_id: str | None = None
    retry_index: int = 0
    latency_ms: int | None = None
    prompt_digest: str | None = None
    response_digest: str | None = None
    context_manifest_digest: str | None = None
    memory_selection_digest: str | None = None
    native_usage: tuple[NativeUsageField, ...] = ()
    normalized_usage: tuple[NormalizedUsageDimension, ...] = ()
    normalization_version: str | None = None
    cost: CostObservation | None = None
    invoice_reference: str | None = None
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.UNRECONCILED
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    retention: RetentionClass = RetentionClass.STANDARD
    policy_decision_id: str | None = None
    redaction_receipt_digest: str | None = None
    event_id: str = field(default_factory=lambda: f"usage:{uuid4()}")
    occurred_at: str = field(default_factory=utc_now)
    observed_at: str = field(default_factory=utc_now)
    schema_version: int = 2

    def __post_init__(self) -> None:
        for field_name in (
            "tenant_id",
            "repository_id",
            "mission_id",
            "run_id",
            "step_id",
            "role",
            "work_item_id",
            "actor_id",
            "attempt_id",
            "trace_id",
            "span_id",
            "event_id",
        ):
            _require_identifier(getattr(self, field_name), field_name)
        for field_name in (
            "provider_request_id",
            "budget_lease_id",
            "policy_decision_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field_name)
        if self.schema_version != 2:
            raise ValueError("usage event schema_version must be 2")
        if self.retry_index < 0:
            raise ValueError("retry_index must be non-negative")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        _require_timestamp(self.occurred_at, "occurred_at")
        _require_timestamp(self.observed_at, "observed_at")
        for field_name in (
            "prompt_digest",
            "response_digest",
            "context_manifest_digest",
            "memory_selection_digest",
            "redaction_receipt_digest",
        ):
            _require_digest(getattr(self, field_name), field_name)
        if self.attempt_kind is AttemptKind.MODEL:
            if not (self.provider or "").strip() or not (self.model or "").strip():
                raise ValueError("model attempts require provider and model")
        elif self.attempt_kind is AttemptKind.TOOL:
            if not (self.tool_name or "").strip():
                raise ValueError("tool attempts require tool_name")
        elif not (self.host or "").strip():
            raise ValueError("host attempts require host")
        native_paths = [field.path for field in self.native_usage]
        if len(native_paths) != len(set(native_paths)):
            raise ValueError("native usage paths must be unique per attempt")
        normalized_axes = [dimension.axis for dimension in self.normalized_usage]
        if len(normalized_axes) != len(set(normalized_axes)):
            raise ValueError("normalized usage axes must be unique per attempt")
        if self.normalized_usage and not (self.normalization_version or "").strip():
            raise ValueError("normalized usage requires normalization_version")
        if not self.normalized_usage and self.normalization_version is not None:
            raise ValueError("normalization_version requires normalized usage")
        if self.invoice_reference is not None:
            _require_text(self.invoice_reference, "invoice_reference")
        object.__setattr__(self, "native_usage", tuple(self.native_usage))
        object.__setattr__(self, "normalized_usage", tuple(self.normalized_usage))

    def to_contract(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "repository_id": self.repository_id,
            "mission_id": self.mission_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "role": self.role,
            "work_item_id": self.work_item_id,
            "actor_id": self.actor_id,
            "purpose": self.purpose.value,
            "attempt_id": self.attempt_id,
            "attempt_kind": self.attempt_kind.value,
            "outcome": self.outcome.value,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "tool_name": self.tool_name,
            "host": self.host,
            "provider_request_id": self.provider_request_id,
            "budget_lease_id": self.budget_lease_id,
            "retry_index": self.retry_index,
            "latency_ms": self.latency_ms,
            "prompt_digest": self.prompt_digest,
            "response_digest": self.response_digest,
            "context_manifest_digest": self.context_manifest_digest,
            "memory_selection_digest": self.memory_selection_digest,
            "native_usage": [field.to_contract() for field in self.native_usage],
            "normalized_usage": [
                dimension.to_contract() for dimension in self.normalized_usage
            ],
            "normalization_version": self.normalization_version,
            "cost": self.cost.to_contract() if self.cost is not None else None,
            "invoice_reference": self.invoice_reference,
            "reconciliation_status": self.reconciliation_status.value,
            "sensitivity": self.sensitivity.value,
            "retention": self.retention.value,
            "policy_decision_id": self.policy_decision_id,
            "redaction_receipt_digest": self.redaction_receipt_digest,
            "occurred_at": self.occurred_at,
            "observed_at": self.observed_at,
        }
