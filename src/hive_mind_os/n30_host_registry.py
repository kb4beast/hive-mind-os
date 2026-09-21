"""Durable host-owned N30 admission registry on local SQLite (ADR-094).

This adapter implements the existing nine-method ``AdmissionRegistry`` protocol. It
stores canonical bytes, owns opaque handles and enforces compare-and-swap, single
consumption and audit; it never signs, mints authority or verifies signatures.
Authority comes only from three injected, read-only, bounded host ports
(current admission / round outcome / execution measurement). No approved N30
external mapping or provider exists: a missing or unreviewed mapping blocks every
positive use. Test providers must say so through ``ReviewedMapping.synthetic``.

Unsupported: network filesystems, coherent privileged database rollback detection
(a local hash chain cannot see it without an independently retained checkpoint) and
any migration guess. External revocation and the SQLite commit are not one atomic
operation; the adapter claims fresh checks before each positive use and commit only.

Provider lifecycle (ADR-094): ports are *trusted, read-only, self-bounded* adapters that
receive an absolute monotonic deadline and finite byte/row limits and must enforce their
own bounded I/O and release. The registry runs one call at a time with no backlog; a
timeout poisons the instance, and a process-local ownership guard keeps the timed-out
worker accounted for across close/collection/reopen of the same store. Nothing here
terminates a noncooperative provider: that remains a deployment blocker requiring an
externally supervised process boundary with kill/reap custody.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, Sequence, cast

from .benchmark_adapters import (
    AdmittedBenchmarkInvocation,
    BenchmarkAdapterError,
    BenchmarkAdapterManifest,
    BenchmarkResponse,
    build_admitted_invocation,
)
from .campaign_metrics import (
    BRACKET_CODEC_ID,
    OPERATIONS,
    STAGES,
    AdmissionSnapshot,
    AdmissionUse,
    AggregateEvidence,
    AggregateReceipt,
    AuthorityBinding,
    BracketSnapshot,
    BracketState,
    BracketTransition,
    CampaignMetricsError,
    ConsumeRoundRequest,
    DescriptiveInterval,
    FamilyObservation,
    FinalistBinding,
    IssuedReceipt,
    LeaseExhausted,
    LeaseRecord,
    MatchProtocol,
    ObservationShapeEntry,
    ReceiptOutcome,
    RoundPlanEntry,
    StageEvidence,
    TaskBinding,
    VariantSeal,
    active_variants_for,
    bracket_from_document,
    build_aggregate_evidence,
    canonical_digest,
    canonical_document,
    check_seal_append,
    decide_match,
    expected_admission_digest,
    observation_shape_for,
    plan_next_round,
    transition_after_round,
    validate_admission_snapshot,
)

# Schema 2 binds the versioned bracket codec (BRACKET_CODEC_ID). Schema 1 stores used the
# removed versionless bracket identity; they are refused for operation, never migrated.
SCHEMA_VERSION = 2
APPLICATION_ID = 0x4E333052  # "N30R"
MAX_DOCUMENT_BYTES = 2_000_000
MAX_RESPONSE_BYTES = 4_000_000
MAX_MEASUREMENT_ROWS = 90
MAX_PROVIDER_SECONDS = 30.0
MAX_BUSY_TIMEOUT_MS = 30_000
PURPOSES = ("n30.current", "n30.outcome", "n30.measurement")
METRICS = ("success_difference", "cost_ratio", "time_ratio")
DERIVATIONS = ("aggregates_required", "direct_permitted")
_BOUNDED_DIRECTIONS = ("higher-is-better", "lower-is-better", "paired-difference")


class N30HostError(CampaignMetricsError):
    """Base class for adapter refusals; never a confirmed lease exhaustion."""


class N30StoreError(N30HostError):
    """The database is corrupt, foreign, unsupported or fails verification."""


class AuthorityBlocked(N30HostError):
    """Authority is unavailable, unknown, stale, future-dated or unmapped."""


# --------------------------------------------------------------------------------------
# Normalized read-only host ports. These are proposed interfaces, not approved schemas.
# --------------------------------------------------------------------------------------


def _text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(char.isspace() for char in value)
    ):
        raise N30HostError(f"{name} must be an exact identifier")
    return value


def _sha(value: object, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 71
        or not value.startswith("sha256:")
        or set(value[7:]) - set("0123456789abcdef")
    ):
        raise N30HostError(f"{name} must be a lowercase sha256 digest")
    return value


def _int(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise N30HostError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class ReviewedMapping:
    """One explicitly reviewed external mapping/purpose; absence blocks."""

    purpose: str
    mapping_id: str
    review_ref: str
    synthetic: bool
    max_status_age: int
    # The reviewed *adapter* this mapping qualifies. Both must be present and must equal
    # the identifiers the injected port declares; they pin a reviewed qualification
    # record, they do not prove a port bounded (that is external review). ``None``
    # (unqualified) blocks every call.
    adapter_id: str | None = None
    qualification_ref: str | None = None
    max_response_bytes: int = 1_000_000

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise N30HostError("unknown N30 purpose")
        _text(self.mapping_id, "mapping_id")
        _text(self.review_ref, "review_ref")
        if type(self.synthetic) is not bool:
            raise N30HostError("mapping must declare synthetic true/false")
        _int(self.max_status_age, "max_status_age", minimum=1)
        for name in ("adapter_id", "qualification_ref"):
            value = getattr(self, name)
            if value is not None:
                _text(value, name)
        _int(self.max_response_bytes, "max_response_bytes", minimum=1)
        if self.max_response_bytes > MAX_RESPONSE_BYTES:
            raise N30HostError("response byte limit exceeds the supported ceiling")

    @property
    def qualified(self) -> bool:
        return self.adapter_id is not None and self.qualification_ref is not None


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric: str
    unit: str
    direction: str
    denominator: str

    def __post_init__(self) -> None:
        if self.metric not in METRICS or self.direction not in _BOUNDED_DIRECTIONS:
            raise N30HostError("invalid metric definition")
        _text(self.unit, "unit")
        _text(self.denominator, "denominator")

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class HostPolicy:
    """Host-configured bounds and reviewed mappings; callers cannot supply these."""

    mappings: Mapping[str, ReviewedMapping]
    metric_definitions: Mapping[str, MetricDefinition]
    gate_definition: str
    outcome_dependency: str
    provider_timeout_seconds: float = 5.0
    busy_timeout_ms: int = 5000

    def __post_init__(self) -> None:
        mappings = dict(self.mappings)
        if any(
            purpose not in PURPOSES or mapping.purpose != purpose
            for purpose, mapping in mappings.items()
        ):
            raise N30HostError("mapping purposes must match their keys")
        definitions = dict(self.metric_definitions)
        if set(definitions) != set(METRICS) or any(
            definition.metric != metric for metric, definition in definitions.items()
        ):
            raise N30HostError("exact reviewed metric definitions required")
        _text(self.gate_definition, "gate_definition")
        if self.outcome_dependency not in DERIVATIONS:
            raise N30HostError("outcome dependency policy must be reviewed")
        if (
            isinstance(self.provider_timeout_seconds, bool)
            or not isinstance(self.provider_timeout_seconds, (int, float))
            or not 0 < self.provider_timeout_seconds <= MAX_PROVIDER_SECONDS
        ):
            raise N30HostError("provider timeout must be finite and bounded")
        _int(self.busy_timeout_ms, "busy_timeout_ms", minimum=1)
        if self.busy_timeout_ms > MAX_BUSY_TIMEOUT_MS:
            raise N30HostError("busy timeout is unbounded")
        object.__setattr__(self, "mappings", MappingProxyType(mappings))
        object.__setattr__(self, "metric_definitions", MappingProxyType(definitions))

    @property
    def synthetic(self) -> bool:
        return any(mapping.synthetic for mapping in self.mappings.values())


@dataclass(frozen=True, slots=True)
class StatusObservation:
    """An authoritative status read; finite freshness is mandatory."""

    authority_id: str
    mapping_id: str
    generation: int
    observed_at: int
    max_age: int
    state: str
    effective_at: int | None = None

    def __post_init__(self) -> None:
        _text(self.authority_id, "authority_id")
        _text(self.mapping_id, "mapping_id")
        _int(self.generation, "generation")
        _int(self.observed_at, "observed_at")
        _int(self.max_age, "max_age", minimum=1)
        if self.state not in {"active", "revoked", "unknown"}:
            raise N30HostError("status state must be active, revoked or unknown")
        if (self.state == "revoked") != (self.effective_at is not None):
            raise N30HostError("only a revoked status carries an effective time")
        if self.effective_at is not None:
            _int(self.effective_at, "effective_at")

    def revoked_by(self, now: int) -> bool:
        """True only for a confirmed revocation already effective at ``now``."""
        return (
            self.state == "revoked"
            and self.effective_at is not None
            and self.effective_at <= now
        )

    def to_document(self) -> Mapping[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class CurrentAdmissionEvidence:
    admission_ref: str
    stage_evidence: StageEvidence
    lease: LeaseRecord
    trusted_lease_issuers: frozenset[str]
    source_digest: str
    status: StatusObservation


@dataclass(frozen=True, slots=True)
class AuthenticatedOutcome:
    plan_digest: str
    receipt_digest: str
    evaluator_id: str
    custodian_id: str
    outcome: str
    derivation: str
    aggregate_digests: tuple[str, ...]
    evidence_digest: str
    observed_at: int
    signed_at: int
    status: StatusObservation


@dataclass(frozen=True, slots=True)
class VariantExpectation:
    variant_id: str
    invocation: AdmittedBenchmarkInvocation


@dataclass(frozen=True, slots=True)
class MeasurementBinding:
    """Metric-independent expectation the measurement port must satisfy exactly."""

    admission_digest: str
    protocol_digest: str
    stage: str
    track: str
    regime_id: str
    block_id: str
    block_digest: str
    task_manifest_digest: str
    family_manifest_digest: str
    task_id: str
    family_id: str
    repetition: int
    seed: int
    left: VariantExpectation
    right: VariantExpectation

    def to_document(self) -> Mapping[str, object]:
        document: dict[str, object] = {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name not in {"left", "right"}
        }
        for side in ("left", "right"):
            expectation = getattr(self, side)
            document[side] = {
                "variant_id": expectation.variant_id,
                "invocation": invocation_document(expectation.invocation),
            }
        return document

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class MeasuredExecution:
    invocation: AdmittedBenchmarkInvocation
    response: BenchmarkResponse
    raw_result_digest: str


@dataclass(frozen=True, slots=True)
class AuthenticatedMeasurement:
    evidence_digest: str
    binding_digest: str
    executions: tuple[MeasuredExecution, MeasuredExecution]
    values: Mapping[str, float]
    definitions: Mapping[str, MetricDefinition]
    gate_definition: str
    left_hard_gates: bool
    right_hard_gates: bool
    observed_at: int
    signed_at: int
    status: StatusObservation


@dataclass(frozen=True, slots=True)
class PortLimits:
    """Finite limits every port call receives; the adapter must honour them itself."""

    max_bytes: int
    max_rows: int


# Trusted, read-only, self-bounded adapters. Each declares the reviewed identifiers that
# must equal its ReviewedMapping. It must enforce ``deadline`` (an absolute
# ``time.monotonic()`` instant) and ``limits`` in its own I/O, release promptly, and never
# call back into the registry, touch SQLite, mutate state, acquire credentials or spawn
# work. Monotonic time schedules the call only; authority freshness always uses a newly
# sampled trusted UTC time after the call returns.


class CurrentAuthorityPort(Protocol):
    adapter_id: str
    qualification_ref: str

    def current(
        self,
        use: AdmissionUse,
        immutable_context: Mapping[str, object],
        now: int,
        deadline: float,
        limits: PortLimits,
    ) -> CurrentAdmissionEvidence: ...


class OutcomePort(Protocol):
    adapter_id: str
    qualification_ref: str

    def outcome(
        self, issued_receipt: IssuedReceipt, now: int, deadline: float, limits: PortLimits
    ) -> AuthenticatedOutcome: ...


class MeasurementPort(Protocol):
    adapter_id: str
    qualification_ref: str

    def measurement(
        self,
        evidence_digest: str,
        expected_binding: MeasurementBinding,
        now: int,
        deadline: float,
        limits: PortLimits,
    ) -> AuthenticatedMeasurement: ...


@dataclass(frozen=True, slots=True)
class HostPorts:
    """Exactly three ports; ``None`` means the external mapping is unsupported."""

    current: CurrentAuthorityPort | None = None
    outcome: OutcomePort | None = None
    measurement: MeasurementPort | None = None


# --------------------------------------------------------------------------------------
# Canonical bytes and decoders. Python id() is never persisted.
# --------------------------------------------------------------------------------------


def _bytes(value: object) -> bytes:
    data = json.dumps(
        canonical_document(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise N30HostError("document exceeds the bounded canonical size")
    return data


def _source_digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def request_document(request: object) -> Mapping[str, object]:
    fields = (
        "operation_id",
        "experiment_id",
        "stage",
        "task_id",
        "family_id",
        "candidate_digest",
        "recipe_digest",
        "budget_digest",
        "environment_digest",
        "lease_handle",
        "argv",
        "environment",
        "execution_binding_digest",
    )
    return {name: getattr(request, name) for name in fields}


def invocation_document(invocation: AdmittedBenchmarkInvocation) -> Mapping[str, object]:
    return {
        "request": request_document(invocation.request),
        "variant_id": invocation.variant_id,
        "admission_digest": invocation.admission_digest,
        "stage_evidence_digest": invocation.stage_evidence_digest,
        "lease_digest": invocation.lease_digest,
        "variant_seal_digest": invocation.variant_seal_digest,
        "repetition": invocation.repetition,
        "seed": invocation.seed,
        "execution_binding_digest": invocation.execution_binding_digest,
    }


def response_document(response: BenchmarkResponse) -> Mapping[str, object]:
    return {name: getattr(response, name) for name in response.__dataclass_fields__}


def _load(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise N30StoreError("stored canonical document is unreadable") from error


def decode_protocol(document: Mapping[str, object]) -> MatchProtocol:
    return MatchProtocol(**cast(Any, dict(document)))


def decode_stage_evidence(document: Mapping[str, Any]) -> StageEvidence:
    principals = dict(document["principals"])
    values = dict(document)
    values["tasks"] = tuple(
        TaskBinding(
            task["task_id"],
            task["family_id"],
            tuple(task["strata"]),
            tuple(task["repetition_seeds"]),
        )
        for task in document["tasks"]
    )
    values["principals"] = AuthorityBinding(
        principals["evaluator_id"],
        principals["custodian_id"],
        tuple(principals["builder_ids"]),
        tuple(principals["affected_champion_ids"]),
        principals["evaluator_signature_ref"],
        principals["custody_signature_ref"],
    )
    values["final_pair"] = tuple(FinalistBinding(**pair) for pair in document["final_pair"])
    return StageEvidence(**values)


def decode_lease(document: Mapping[str, Any]) -> LeaseRecord:
    values = dict(document)
    values["operations"] = frozenset(document["operations"])
    return LeaseRecord(**values)


def decode_bracket(document: object) -> BracketSnapshot:
    """Strict versioned decode; legacy/versionless/unknown documents are refused."""
    try:
        return bracket_from_document(document)
    except N30StoreError:
        raise
    except CampaignMetricsError as error:
        raise N30StoreError(f"bracket document refused: {error}") from error


def decode_aggregate(document: Mapping[str, Any]) -> AggregateEvidence:
    values = dict(document)
    values["observation_shape"] = tuple(
        ObservationShapeEntry(**entry) for entry in document["observation_shape"]
    )
    values["interval"] = DescriptiveInterval(**document["interval"])
    return AggregateEvidence(**values)


def _measurement_definitions_document(
    definitions: Mapping[str, MetricDefinition],
) -> Mapping[str, object]:
    return {metric: definition.to_document() for metric, definition in definitions.items()}


# --------------------------------------------------------------------------------------
# Schema. Verified byte-for-byte on reopen; unknown schemas are refused, never migrated.
# --------------------------------------------------------------------------------------

_DDL: tuple[tuple[str, str], ...] = (
    ("meta", "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"),
    (
        "audit",
        "CREATE TABLE audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL,"
        " kind TEXT NOT NULL, subject TEXT NOT NULL, request_digest TEXT,"
        " result_digest TEXT, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL UNIQUE)",
    ),
    (
        "clock_mark",
        "CREATE TABLE clock_mark (id INTEGER PRIMARY KEY CHECK (id = 1),"
        " high_water INTEGER NOT NULL)",
    ),
    (
        "protocols",
        "CREATE TABLE protocols (protocol_digest TEXT PRIMARY KEY,"
        " canonical BLOB NOT NULL, source_digest TEXT NOT NULL)",
    ),
    (
        "status_observations",
        "CREATE TABLE status_observations (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " subject TEXT NOT NULL, authority_id TEXT NOT NULL, mapping_id TEXT NOT NULL,"
        " synthetic INTEGER NOT NULL, generation INTEGER NOT NULL,"
        " observed_at INTEGER NOT NULL, max_age INTEGER NOT NULL, state TEXT NOT NULL,"
        " effective_at INTEGER, recorded_at INTEGER NOT NULL,"
        " content_digest TEXT NOT NULL)",
    ),
    (
        "admissions",
        "CREATE TABLE admissions (admission_digest TEXT PRIMARY KEY,"
        " admission_ref TEXT NOT NULL UNIQUE,"
        " protocol_digest TEXT NOT NULL REFERENCES protocols(protocol_digest),"
        " stage TEXT NOT NULL, evidence_canonical BLOB NOT NULL,"
        " lease_canonical BLOB NOT NULL, issuers_canonical BLOB NOT NULL,"
        " authority_source_digest TEXT NOT NULL, enrolled_at INTEGER NOT NULL,"
        " observation_id INTEGER NOT NULL REFERENCES status_observations(id),"
        " UNIQUE (protocol_digest, stage))",
    ),
    (
        "seals",
        "CREATE TABLE seals (protocol_digest TEXT NOT NULL"
        " REFERENCES protocols(protocol_digest), sequence INTEGER NOT NULL,"
        " seal_digest TEXT NOT NULL, canonical BLOB NOT NULL, sealed_at INTEGER NOT NULL,"
        " txn_seq INTEGER NOT NULL REFERENCES audit(seq),"
        " PRIMARY KEY (protocol_digest, sequence), UNIQUE (protocol_digest, seal_digest))",
    ),
    (
        "brackets",
        "CREATE TABLE brackets (bracket_id TEXT PRIMARY KEY,"
        " admission_digest TEXT NOT NULL REFERENCES admissions(admission_digest),"
        " protocol_digest TEXT NOT NULL, stage TEXT NOT NULL, track TEXT NOT NULL,"
        " UNIQUE (admission_digest, stage, track))",
    ),
    (
        "bracket_versions",
        "CREATE TABLE bracket_versions (bracket_id TEXT NOT NULL"
        " REFERENCES brackets(bracket_id), version INTEGER NOT NULL,"
        " bracket_digest TEXT NOT NULL UNIQUE, canonical BLOB NOT NULL, prev_digest TEXT,"
        " txn_seq INTEGER NOT NULL REFERENCES audit(seq), PRIMARY KEY (bracket_id, version))",
    ),
    (
        "bracket_current",
        "CREATE TABLE bracket_current (bracket_id TEXT PRIMARY KEY"
        " REFERENCES brackets(bracket_id), version INTEGER NOT NULL,"
        " bracket_digest TEXT NOT NULL,"
        " FOREIGN KEY (bracket_id, version) REFERENCES bracket_versions(bracket_id, version))",
    ),
    (
        "issuances",
        "CREATE TABLE issuances (issuance_id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " bracket_id TEXT NOT NULL REFERENCES brackets(bracket_id),"
        " bracket_digest TEXT NOT NULL REFERENCES bracket_versions(bracket_digest),"
        " round_number INTEGER NOT NULL, plans_digest TEXT NOT NULL,"
        " observation_id INTEGER NOT NULL REFERENCES status_observations(id),"
        " issued_at INTEGER NOT NULL, validated_at INTEGER NOT NULL,"
        " txn_seq INTEGER NOT NULL REFERENCES audit(seq),"
        " UNIQUE (bracket_digest, round_number))",
    ),
    (
        "receipts",
        "CREATE TABLE receipts (receipt_digest TEXT PRIMARY KEY,"
        " plan_digest TEXT NOT NULL UNIQUE,"
        " issuance_id INTEGER NOT NULL REFERENCES issuances(issuance_id),"
        " pair_index INTEGER NOT NULL, plan_canonical BLOB NOT NULL,"
        " issued_at INTEGER NOT NULL, UNIQUE (issuance_id, pair_index))",
    ),
    (
        "consumptions",
        "CREATE TABLE consumptions (receipt_digest TEXT PRIMARY KEY"
        " REFERENCES receipts(receipt_digest),"
        " txn_seq INTEGER NOT NULL REFERENCES audit(seq), outcome TEXT NOT NULL,"
        " derivation TEXT NOT NULL, evidence_digest TEXT, aggregate_digests TEXT NOT NULL)",
    ),
    (
        "measurements",
        "CREATE TABLE measurements (measurement_digest TEXT PRIMARY KEY,"
        " binding_digest TEXT NOT NULL,"
        " admission_digest TEXT NOT NULL REFERENCES admissions(admission_digest),"
        " canonical BLOB NOT NULL, observation_id INTEGER NOT NULL"
        " REFERENCES status_observations(id),"
        " txn_seq INTEGER NOT NULL REFERENCES audit(seq))",
    ),
    (
        "aggregates",
        "CREATE TABLE aggregates (aggregate_digest TEXT PRIMARY KEY,"
        " admission_digest TEXT NOT NULL REFERENCES admissions(admission_digest),"
        " metric TEXT NOT NULL, canonical BLOB NOT NULL,"
        " txn_seq INTEGER NOT NULL REFERENCES audit(seq))",
    ),
    (
        "aggregate_uses",
        "CREATE TABLE aggregate_uses (aggregate_digest TEXT NOT NULL"
        " REFERENCES aggregates(aggregate_digest), measurement_digest TEXT NOT NULL"
        " REFERENCES measurements(measurement_digest), family_id TEXT NOT NULL,"
        " task_id TEXT NOT NULL, repetition INTEGER NOT NULL, value_json TEXT NOT NULL,"
        " position INTEGER NOT NULL,"
        " PRIMARY KEY (aggregate_digest, measurement_digest),"
        " UNIQUE (aggregate_digest, position),"
        " UNIQUE (aggregate_digest, family_id, task_id, repetition))",
    ),
    (
        "request_results",
        "CREATE TABLE request_results (request_digest TEXT PRIMARY KEY,"
        " kind TEXT NOT NULL,"
        " admission_digest TEXT NOT NULL REFERENCES admissions(admission_digest),"
        " result_kind TEXT NOT NULL, result_ref TEXT NOT NULL,"
        " result_digest TEXT NOT NULL, txn_seq INTEGER NOT NULL REFERENCES audit(seq))",
    ),
)
_GENESIS = "sha256:" + "0" * 64


def _normal_sql(sql: str | None) -> str:
    return " ".join((sql or "").split())


class _Handle:
    """Opaque wrapper. It has no fields, so it can carry no authoritative state."""

    __slots__ = ()


class _AdmissionHandle(_Handle):
    __slots__ = ()


class _BracketHandle(_Handle):
    __slots__ = ()


class _ReceiptHandle(_Handle):
    __slots__ = ()


class _AggregateHandle(_Handle):
    __slots__ = ()


class _Interner:
    """Thread-safe per-instance wrapper identity map holding strong references.

    campaign_metrics compares ``id(opaque_handle)``; holding every wrapper keeps that
    id unique and stable. The durable key is a record identity, never ``id()``.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_key: dict[tuple[type, tuple[object, ...]], _Handle] = {}
        self._by_id: dict[int, tuple[_Handle, type, tuple[object, ...]]] = {}

    def wrapper(self, kind: type, key: tuple[object, ...]) -> _Handle:
        with self._lock:
            existing = self._by_key.get((kind, key))
            if existing is None:
                existing = kind()
                self._by_key[(kind, key)] = existing
                self._by_id[id(existing)] = (existing, kind, key)
            return existing

    def key(self, obj: object, kind: type) -> tuple[object, ...]:
        with self._lock:
            entry = self._by_id.get(id(obj))
        if entry is None or entry[0] is not obj or entry[1] is not kind:
            raise CampaignMetricsError("foreign, edited, or stale opaque handle")
        return entry[2]

    def text_key(self, obj: object, kind: type) -> str:
        """The durable text identity of a one-part key (validated, not cast)."""
        key = self.key(obj, kind)
        if len(key) == 1:
            (first,) = key
            if isinstance(first, str):
                return first
        raise CampaignMetricsError("opaque handle has no durable text identity")

    def bracket_key(self, obj: object) -> tuple[str, int]:
        key = self.key(obj, _BracketHandle)
        if len(key) == 2:
            first, second = key
            if isinstance(first, str) and type(second) is int:
                return first, second
        raise CampaignMetricsError("opaque bracket handle has no durable identity")


@dataclass(frozen=True, slots=True)
class _Admission:
    admission_digest: str
    admission_ref: str
    protocol: MatchProtocol
    stage: str
    evidence: StageEvidence
    lease: LeaseRecord
    issuers: frozenset[str]
    authority_source_digest: str
    enrolled_at: int
    observation_id: int


@dataclass(frozen=True, slots=True)
class _Auth:
    admission: _Admission
    now: int
    status: StatusObservation
    observation_id: int
    exhausted: str | None
    snapshot: AdmissionSnapshot | None


@dataclass(frozen=True, slots=True)
class RecoveredResult:
    """Immutable recorded result of one exact request digest.

    ``state``/``receipts``/``aggregate`` are populated only when the recorded result is
    still current; a superseded bracket version is reported but never revived.
    """

    request_digest: str
    kind: str
    result_digest: str
    current: bool
    state: BracketState | None = None
    receipts: tuple[IssuedReceipt, ...] = ()
    aggregate: AggregateReceipt | None = None


class _ProviderCall:
    """One provider invocation on its own thread.

    The thread is deliberately **non-daemon**: daemonization or ``Future.cancel`` would only
    hide a noncooperative provider, not terminate it, and a hidden worker could keep
    touching external resources. A noncooperative provider therefore still prevents
    interpreter exit; that is the documented deployment blocker, not something this
    class solves. A value or error arriving after the caller abandoned the call, or
    after its deadline, is discarded and never earns authority.
    """

    def __init__(self, label: str, deadline: float) -> None:
        self.label = label
        self.deadline = deadline
        self.lock = threading.Lock()
        self.finished = threading.Event()
        self.abandoned = False
        self.late = False
        self.value: object = None
        self.error: BaseException | None = None
        self.thread: threading.Thread | None = None

    def start(self, function: Callable[..., object], args: tuple[object, ...]) -> None:
        self.thread = threading.Thread(
            target=self._run, args=(function, args), name=f"n30-port-{self.label}"
        )
        self.thread.start()

    def _run(self, function: Callable[..., object], args: tuple[object, ...]) -> None:
        value: object = None
        error: BaseException | None = None
        try:
            value = function(*args)
        except BaseException as caught:  # provider failures are data, never crashes
            error = caught
        completed = time.monotonic()
        with self.lock:
            if completed > self.deadline:
                self.late = True
            if not self.abandoned and not self.late:
                self.value, self.error = value, error
            self.finished.set()

    def settle(self, timeout: float) -> bool:
        """Wait, then decide atomically: True = usable answer, False = abandoned."""
        self.finished.wait(max(0.0, timeout))
        with self.lock:
            if self.finished.is_set() and not self.late:
                return True
            self.abandoned = True
            return False

    @property
    def alive(self) -> bool:
        return not self.finished.is_set()


class _StoreGuard:
    """Process-local ownership guard for one store (normalized aliases share it).

    It outlives every registry instance: closing or garbage-collecting a registry never
    releases it while an abandoned (timed-out or closed-during-call) provider worker is
    still alive, so reopening the same store cannot create a second worker farm. It is
    process-local only; cross-process custody is a deployment obligation.
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        # Every registered provider call still alive. Ownership starts *before* a call's
        # thread does, and "abandoned" is a flag the call itself carries (set atomically
        # under the call's lock when a timeout or close decides to give it up), so there
        # is no instant at which an outstanding worker is invisible to this guard.
        self.calls: list[_ProviderCall] = []

    def start(self, call: _ProviderCall) -> bool:
        """Atomically refuse (False) while abandoned work lives, else take ownership."""
        with self.lock:
            self.calls = [item for item in self.calls if item.alive]
            if any(item.abandoned for item in self.calls):
                return False
            self.calls.append(call)
            return True

    def adopt(self, call: _ProviderCall) -> None:
        """Idempotent confirmation of ownership; never needed for correctness."""
        with self.lock:
            if call.alive and call not in self.calls:
                self.calls.append(call)

    def live(self) -> list[_ProviderCall]:
        """Abandoned (timed-out or closed-during-call) workers that are still alive."""
        with self.lock:
            self.calls = [item for item in self.calls if item.alive]
            return [item for item in self.calls if item.abandoned]


_GUARDS: dict[str, _StoreGuard] = {}
_GUARDS_LOCK = threading.Lock()


def _guard_for(path: Path) -> _StoreGuard:
    key = os.path.normcase(os.path.realpath(path))
    with _GUARDS_LOCK:
        guard = _GUARDS.get(key)
        if guard is None:
            for other in list(_GUARDS.values()):
                try:  # hard links, short names or junctions naming the same file
                    if os.path.exists(path) and os.path.samefile(path, other.path):
                        guard = other
                        break
                except OSError:
                    continue
        if guard is None:
            guard = _StoreGuard(key)
        _GUARDS[key] = guard
        return guard


@dataclass(frozen=True, slots=True)
class CloseReport:
    """Honest result of an idempotent close: it never claims a provider was stopped."""

    already_closed: bool
    outstanding_provider_calls: int
    poisoned: str | None

    @property
    def provider_work_outstanding(self) -> bool:
        return self.outstanding_provider_calls > 0


def _local_path(path: str | Path) -> Path:
    text = str(path)
    if text.startswith(("\\\\", "//")):
        raise N30StoreError("network filesystem paths are unsupported")
    return Path(text).resolve()


def _rowid(cursor: sqlite3.Cursor) -> int:
    rowid = cursor.lastrowid
    if type(rowid) is not int:
        raise N30StoreError("SQLite reported no row id for an insert")
    return rowid


_RESPONSE_TYPES: Mapping[str, type] = MappingProxyType(
    {
        "n30.current": CurrentAdmissionEvidence,
        "n30.outcome": AuthenticatedOutcome,
        "n30.measurement": AuthenticatedMeasurement,
    }
)


def _wire(value: object) -> object:
    """Plain wire form of a provider answer, with shape limits checked first."""
    if isinstance(value, CurrentAdmissionEvidence):
        if len(value.trusted_lease_issuers) > 64:
            raise ValueError("too many trusted issuers")
        return {
            "admission_ref": value.admission_ref,
            "stage_evidence": value.stage_evidence,
            "lease": value.lease,
            "issuers": sorted(value.trusted_lease_issuers),
            "source_digest": value.source_digest,
            "status": value.status,
        }
    if isinstance(value, AuthenticatedOutcome):
        if len(value.aggregate_digests) > len(METRICS):
            raise ValueError("too many aggregate dependencies")
        return {name: getattr(value, name) for name in value.__dataclass_fields__}
    if isinstance(value, AuthenticatedMeasurement):
        if (
            len(value.executions) != 2
            or len(value.values) > 2 * len(METRICS)
            or len(value.definitions) > 2 * len(METRICS)
        ):
            raise ValueError("measurement shape exceeds the reviewed bound")
        return {
            "evidence_digest": value.evidence_digest,
            "binding_digest": value.binding_digest,
            "executions": [
                {
                    "invocation": invocation_document(execution.invocation),
                    "response": response_document(execution.response),
                    "raw_result_digest": execution.raw_result_digest,
                }
                for execution in value.executions
            ],
            "values": dict(value.values),
            "definitions": _measurement_definitions_document(value.definitions),
            "gate_definition": value.gate_definition,
            "left_hard_gates": value.left_hard_gates,
            "right_hard_gates": value.right_hard_gates,
            "observed_at": value.observed_at,
            "signed_at": value.signed_at,
            "status": value.status,
        }
    raise TypeError("unsupported provider answer")


def _check_response(purpose: str, value: object, mapping: ReviewedMapping) -> None:
    """Shape and size gate, applied before the answer can be used or persisted."""
    if not isinstance(value, _RESPONSE_TYPES[purpose]):
        raise AuthorityBlocked(f"{purpose} provider returned no typed evidence")
    try:
        size = len(
            json.dumps(
                canonical_document(_wire(value)),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
    except (TypeError, ValueError, AttributeError, RecursionError) as error:
        raise AuthorityBlocked(f"{purpose} provider answer is malformed") from error
    if size > mapping.max_response_bytes:
        raise AuthorityBlocked(
            f"{purpose} provider answer exceeds the reviewed byte limit"
        )


def _observation_content(
    subject: str, status: StatusObservation, synthetic: bool
) -> str:
    return canonical_digest(
        {"subject": subject, "synthetic": synthetic, **status.to_document()}
    )


def _check_progress(prev: Mapping[str, Any] | None, new: Mapping[str, Any]) -> None:
    """Reject generation rollback, observation-time regression and un-revocation."""
    if prev is None:
        return
    if new["generation"] < prev["generation"]:
        raise AuthorityBlocked("status generation rollback")
    if new["observed_at"] < prev["observed_at"]:
        raise AuthorityBlocked("status observation time regressed")
    if new["generation"] == prev["generation"] and (
        new["state"] != prev["state"]
        or new["effective_at"] != prev["effective_at"]
        or new["authority_id"] != prev["authority_id"]
        or new["mapping_id"] != prev["mapping_id"]
    ):
        raise AuthorityBlocked("status changed within one generation")
    if prev["state"] == "revoked" and new["state"] != "revoked":
        raise AuthorityBlocked("revocation cannot be undone by a later status")
    if (
        prev["state"] == "revoked"
        and new["effective_at"] is not None
        and new["effective_at"] > prev["effective_at"]
    ):
        raise AuthorityBlocked("revocation effective time moved later")


class N30HostRegistry:
    """The durable nine-method ``AdmissionRegistry`` plus host-only recovery.

    Construct with :meth:`create` (new store only) or :meth:`open` (existing store
    only). Neither can recreate a store that failed verification.
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        policy: HostPolicy,
        ports: HostPorts,
        clock: Callable[[], int],
        adapter_manifest: BenchmarkAdapterManifest | None,
        fault_hook: Callable[[str], None] | None,
        guard: _StoreGuard,
    ) -> None:
        self._conn = connection
        self._policy = policy
        self._ports = ports
        self._clock = clock
        self._adapter_manifest = adapter_manifest
        self._fault_hook = fault_hook
        self._guard = guard
        self._lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._interner = _Interner()
        self._inflight: _ProviderCall | None = None
        self._poison: str | None = None
        self._closed = False
        self._in_transaction = False

    # -- lifecycle ----------------------------------------------------------------

    @classmethod
    def create(
        cls,
        path: str | Path,
        *,
        policy: HostPolicy,
        ports: HostPorts,
        clock: Callable[[], int],
        adapter_manifest: BenchmarkAdapterManifest | None = None,
        _fault_hook: Callable[[str], None] | None = None,
    ) -> "N30HostRegistry":
        target = _local_path(path)
        if target.exists():
            raise N30StoreError("refusing to create a store over an existing file")
        if not target.parent.is_dir():
            raise N30StoreError("store directory does not exist")
        guard = _guard_for(target)
        cls._require_released(guard)
        connection = cls._connect(target, policy, create=True)
        registry = cls(
            connection,
            policy=policy,
            ports=ports,
            clock=clock,
            adapter_manifest=adapter_manifest,
            fault_hook=_fault_hook,
            guard=guard,
        )
        try:
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            with registry._transaction("create"):
                for _, ddl in _DDL:
                    connection.execute(ddl)
                connection.execute(
                    "INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),)
                )
                connection.execute(
                    "INSERT INTO meta VALUES ('bracket_codec', ?)", (BRACKET_CODEC_ID,)
                )
                connection.execute(
                    "INSERT INTO meta VALUES ('store_id', ?)", (os.urandom(16).hex(),)
                )
                connection.execute("INSERT INTO clock_mark VALUES (1, 0)")
                registry._audit("create", "store", 0, None, None)
        except BaseException:
            connection.close()
            raise
        registry._verify()
        return registry

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        policy: HostPolicy,
        ports: HostPorts,
        clock: Callable[[], int],
        adapter_manifest: BenchmarkAdapterManifest | None = None,
        _fault_hook: Callable[[str], None] | None = None,
    ) -> "N30HostRegistry":
        target = _local_path(path)
        if not target.is_file():
            raise N30StoreError("store does not exist; it is never recreated on open")
        guard = _guard_for(target)
        cls._require_released(guard)
        connection = cls._connect(target, policy, create=False)
        registry = cls(
            connection,
            policy=policy,
            ports=ports,
            clock=clock,
            adapter_manifest=adapter_manifest,
            fault_hook=_fault_hook,
            guard=guard,
        )
        try:
            registry._verify()
        except BaseException:
            connection.close()
            raise
        return registry

    @staticmethod
    def _require_released(guard: _StoreGuard) -> None:
        """Refuse a (re)open while abandoned provider work still runs for this store."""
        if guard.live():
            raise AuthorityBlocked(
                "a timed-out or abandoned provider call is still running for this store;"
                " reopening cannot create another worker"
            )

    @staticmethod
    def _connect(path: Path, policy: HostPolicy, *, create: bool) -> sqlite3.Connection:
        uri = path.as_uri() + ("?mode=rwc" if create else "?mode=rw")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=policy.busy_timeout_ms / 1000,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.execute(f"PRAGMA busy_timeout={int(policy.busy_timeout_ms)}")
            if (
                not create
                and connection.execute("PRAGMA application_id").fetchone()[0]
                != APPLICATION_ID
            ):
                # Refuse a foreign file before any pragma can modify it.
                raise N30StoreError("store refused: foreign application id")
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            if (
                mode is None
                or str(mode[0]).lower() != "wal"
                or connection.execute("PRAGMA synchronous").fetchone()[0] != 2
                or connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1
            ):
                raise N30StoreError("filesystem cannot provide WAL/FULL/foreign keys")
        except sqlite3.DatabaseError as error:
            if connection is not None:
                connection.close()
            raise N30StoreError("store cannot be opened as an SQLite database") from error
        except N30StoreError:
            if connection is not None:
                connection.close()
            raise
        return connection

    def close(self) -> CloseReport:
        """Idempotently release local resources and report outstanding provider work.

        Closing never terminates a provider. A call in flight is abandoned (its late
        answer is discarded) and handed to the process-local store guard, which keeps
        refusing reopen and new submissions until that worker actually ends.
        """
        with self._state_lock:
            already = self._closed
            self._closed = True
            call = self._inflight
            self._inflight = None
            if call is not None:
                # Abandonment is published in the same critical section as ``_closed``;
                # the guard already owns the call, so there is no handoff gap.
                with call.lock:
                    if not call.finished.is_set():
                        call.abandoned = True
        if call is not None and call.alive:
            self._guard.adopt(call)
        if not already:
            with self._lock:
                self._conn.close()
        return CloseReport(already, len(self._guard.live()), self._poison)

    @property
    def synthetic(self) -> bool:
        return self._policy.synthetic

    # -- primitives ---------------------------------------------------------------

    def _fault(self, point: str) -> None:
        if self._fault_hook is not None:
            self._fault_hook(point)

    def _now(self) -> int:
        try:
            value = self._clock()
        except Exception as error:
            raise AuthorityBlocked("trusted clock unavailable") from error
        if type(value) is not int or value < 0:
            raise AuthorityBlocked("trusted clock must return an epoch second")
        return value

    class _Txn:
        def __init__(self, registry: "N30HostRegistry", kind: str) -> None:
            self.registry = registry
            self.kind = kind

        def __enter__(self) -> None:
            registry = self.registry
            registry._lock.acquire()
            if registry._closed:
                registry._lock.release()
                raise AuthorityBlocked("registry is closed")
            try:
                registry._conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as error:
                registry._lock.release()
                raise AuthorityBlocked("store is busy or locked") from error
            # Lock order is always _lock -> _state_lock. The lifecycle lock is taken only
            # after the (possibly slow) SQLite write lock is held and is kept through COMMIT,
            # so no poison/close can be published between this check and the commit.
            registry._state_lock.acquire()
            message = registry._lifecycle_error()
            if message is not None:
                registry._state_lock.release()
                if registry._conn.in_transaction:
                    registry._conn.execute("ROLLBACK")
                registry._lock.release()
                raise AuthorityBlocked(message)
            registry._in_transaction = True

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            registry = self.registry
            try:
                if exc_type is not None:
                    if registry._conn.in_transaction:
                        registry._conn.execute("ROLLBACK")
                    if isinstance(exc, sqlite3.IntegrityError):
                        raise N30HostError(
                            "a uniqueness or reference constraint rejected the write"
                        ) from exc
                    return False
                try:
                    registry._fault(f"pre_commit:{self.kind}")
                    registry._conn.execute("COMMIT")
                except BaseException:
                    if registry._conn.in_transaction:
                        registry._conn.execute("ROLLBACK")
                    raise
                registry._fault(f"post_commit:{self.kind}")
                return False
            finally:
                registry._in_transaction = False
                registry._state_lock.release()
                registry._lock.release()

    def _transaction(self, kind: str) -> "_Txn":
        return self._Txn(self, kind)

    def _query(self, sql: str, params: Sequence[object] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            if self._closed:
                raise AuthorityBlocked("registry is closed")
            return self._conn.execute(sql, tuple(params)).fetchall()

    def _one(self, sql: str, params: Sequence[object] = ()) -> tuple[Any, ...] | None:
        rows = self._query(sql, params)
        return rows[0] if rows else None

    def _audit(
        self,
        kind: str,
        subject: str,
        at: int,
        request_digest: str | None,
        result_digest: str | None,
    ) -> int:
        row = self._conn.execute(
            "SELECT entry_hash FROM audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev = row[0] if row else _GENESIS
        entry = canonical_digest([prev, at, kind, subject, request_digest, result_digest])
        cursor = self._conn.execute(
            "INSERT INTO audit (at, kind, subject, request_digest, result_digest,"
            " prev_hash, entry_hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (at, kind, subject, request_digest, result_digest, prev, entry),
        )
        return _rowid(cursor)

    def _advance_clock(self, now: int) -> None:
        (high,) = self._conn.execute("SELECT high_water FROM clock_mark").fetchone()
        if now < high:
            raise AuthorityBlocked("trusted clock regressed below the recorded high water")
        if now > high:
            self._conn.execute("UPDATE clock_mark SET high_water = ?", (now,))

    def audit_history(self) -> tuple[Mapping[str, object], ...]:
        """Audit-only history. It returns no handle and admits nothing."""
        rows = self._query(
            "SELECT seq, at, kind, subject, request_digest, result_digest"
            " FROM audit ORDER BY seq"
        )
        names = ("seq", "at", "kind", "subject", "request_digest", "result_digest")
        return tuple(MappingProxyType(dict(zip(names, row))) for row in rows)

    # -- lifecycle linearization --------------------------------------------------

    def _lifecycle_error(self) -> str | None:
        """Why this instance may not grant positive credit now. Hold ``_state_lock``.

        A provider call whose timeout/close decision was already published (``abandoned``)
        counts as poison even before the ``_poison`` text is written.
        """
        if self._closed:
            return "registry is closed"
        if self._poison is not None:
            return f"registry instance is poisoned: {self._poison}"
        call = self._inflight
        if call is not None and call.abandoned:
            return "registry instance is poisoned: a provider call was abandoned"
        return None

    def _ensure_live(self) -> None:
        """Final gate for a positive return that involves no write transaction.

        Write transactions hold ``_state_lock`` from their lifecycle check through COMMIT
        (see ``_Txn``); poison publication takes the same lock, so poison and any positive
        commit are totally ordered. A read-only positive result is likewise linearized at
        this check: an operation paused before the poison cannot return positive after it.
        """
        with self._state_lock:
            message = self._lifecycle_error()
            if message is not None:
                raise AuthorityBlocked(message)

    # -- bounded provider calls ---------------------------------------------------

    def _call(
        self, purpose: str, method: str, *args: object
    ) -> tuple[Any, ReviewedMapping, int]:
        """One trusted, read-only, self-bounded provider call.

        Returns ``(value, mapping, returned_at)`` where ``returned_at`` is a **newly
        sampled trusted UTC time after the provider returned**; monotonic time only
        schedules the deadline and never supplies authority freshness.
        """
        mapping = self._policy.mappings.get(purpose)
        port = {
            "n30.current": self._ports.current,
            "n30.outcome": self._ports.outcome,
            "n30.measurement": self._ports.measurement,
        }[purpose]
        if mapping is None or port is None:
            raise AuthorityBlocked(f"no reviewed external mapping for {purpose}")
        if (
            not mapping.qualified
            or getattr(port, "adapter_id", None) != mapping.adapter_id
            or getattr(port, "qualification_ref", None) != mapping.qualification_ref
        ):
            raise AuthorityBlocked(
                f"{purpose} port is not the reviewed, qualified adapter for its mapping"
            )
        sent_at = self._now()
        with self._state_lock:
            message = self._lifecycle_error()
            if message is not None:
                raise AuthorityBlocked(message)
            if self._inflight is not None and self._inflight.alive:
                raise AuthorityBlocked("a provider call is already in flight; no backlog")
            deadline = time.monotonic() + self._policy.provider_timeout_seconds
            call = _ProviderCall(purpose, deadline)
            # Atomic check-and-own against abandoned work of *any* instance on this store.
            if not self._guard.start(call):
                raise AuthorityBlocked(
                    "timed-out provider work is still running for this store"
                )
            self._inflight = call
        limits = PortLimits(mapping.max_response_bytes, MAX_MEASUREMENT_ROWS)
        try:
            call.start(getattr(port, method), (*args, sent_at, deadline, limits))
        except BaseException:
            call.finished.set()  # the thread never ran; release the guard's ownership
            with self._state_lock:
                self._inflight = None
            raise
        usable = call.settle(deadline - time.monotonic())
        with self._state_lock:
            if not usable:
                self._poison = f"{purpose} provider exceeded its deadline"
            elif self._inflight is call:
                self._inflight = None
            closed, poison = self._closed, self._poison
        if not usable:
            self._guard.adopt(call)
            raise AuthorityBlocked(
                f"{purpose} provider exceeded its deadline; the instance is poisoned and"
                " any late answer is discarded"
            )
        if closed or poison is not None:
            raise AuthorityBlocked("registry closed or poisoned during a provider call")
        returned_at = self._now()
        if returned_at < sent_at:
            raise AuthorityBlocked("trusted clock regressed during a provider call")
        if call.error is not None:
            if isinstance(call.error, CampaignMetricsError):
                raise call.error
            raise AuthorityBlocked(f"{purpose} provider unavailable") from call.error
        _check_response(purpose, call.value, mapping)
        return call.value, mapping, returned_at

    @staticmethod
    def _check_status(
        status: object, mapping: ReviewedMapping, now: int
    ) -> StatusObservation:
        if not isinstance(status, StatusObservation):
            raise AuthorityBlocked("provider returned no typed status observation")
        if status.mapping_id != mapping.mapping_id:
            raise AuthorityBlocked("status observation uses an unreviewed mapping")
        if status.max_age > mapping.max_status_age:
            raise AuthorityBlocked("status freshness exceeds the reviewed limit")
        if status.state == "unknown":
            raise AuthorityBlocked("authoritative status is unknown")
        if status.observed_at > now:
            raise AuthorityBlocked("status observation is from the future")
        if now >= status.observed_at + status.max_age:
            raise AuthorityBlocked("authoritative status is stale")
        return status

    def _record_status(
        self, subject: str, status: StatusObservation, mapping: ReviewedMapping, now: int
    ) -> int:
        """Append one observation inside the caller's transaction; returns its id."""
        content = _observation_content(subject, status, mapping.synthetic)
        last = self._conn.execute(
            "SELECT id, generation, observed_at, state, effective_at, authority_id,"
            " mapping_id, content_digest FROM status_observations WHERE subject = ?"
            " ORDER BY id DESC LIMIT 1",
            (subject,),
        ).fetchone()
        previous = (
            None
            if last is None
            else {
                "generation": last[1],
                "observed_at": last[2],
                "state": last[3],
                "effective_at": last[4],
                "authority_id": last[5],
                "mapping_id": last[6],
            }
        )
        if last is not None and last[7] == content:
            return int(last[0])
        _check_progress(previous, status.to_document())
        cursor = self._conn.execute(
            "INSERT INTO status_observations (subject, authority_id, mapping_id,"
            " synthetic, generation, observed_at, max_age, state, effective_at,"
            " recorded_at, content_digest) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                subject,
                status.authority_id,
                status.mapping_id,
                int(mapping.synthetic),
                status.generation,
                status.observed_at,
                status.max_age,
                status.state,
                status.effective_at,
                now,
                content,
            ),
        )
        return _rowid(cursor)

    def _observe(
        self, kind: str, subject: str, status: StatusObservation, mapping: ReviewedMapping, now: int
    ) -> int:
        with self._transaction(f"observe:{kind}"):
            self._advance_clock(now)
            observation_id = self._record_status(subject, status, mapping, now)
            self._audit(f"status:{kind}", subject, now, None, canonical_digest(status))
        return observation_id

    # -- reopen verification ------------------------------------------------------

    @staticmethod
    def _refuse(message: str) -> "N30StoreError":
        return N30StoreError(f"store refused: {message}")

    def _verify(self) -> None:
        with self._lock:
            c = self._conn
            try:
                if c.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                    raise self._refuse("foreign application id")
                if c.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                    raise self._refuse("unsupported schema version; no migration is guessed")
                expected = dict(_DDL)
                seen: set[str] = set()
                for kind, name, sql in c.execute(
                    "SELECT type, name, sql FROM sqlite_master"
                ).fetchall():
                    if kind == "table" and name in expected:
                        if _normal_sql(sql) != _normal_sql(expected[name]):
                            raise self._refuse(f"table {name} differs from schema")
                        seen.add(name)
                    elif kind == "table" and name == "sqlite_sequence":
                        continue
                    elif (
                        kind == "index"
                        and str(name).startswith("sqlite_autoindex_")
                        and sql is None
                    ):
                        continue
                    else:
                        raise self._refuse(f"unexpected schema object {kind}:{name}")
                if seen != set(expected):
                    raise self._refuse("required tables are missing")
                if c.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise self._refuse("SQLite integrity check failed")
                if c.execute("PRAGMA foreign_key_check").fetchall():
                    raise self._refuse("foreign key violation")
                self._verify_content()
            except N30StoreError:
                raise
            except (
                sqlite3.DatabaseError,
                KeyError,
                TypeError,
                ValueError,
                AttributeError,
                IndexError,
            ) as error:
                raise self._refuse(f"content failed verification ({error})") from error

    @staticmethod
    def _successor_ok(prev: BracketSnapshot, nxt: BracketSnapshot) -> bool:
        if prev.terminal is not None:
            return False
        if nxt.round_number not in (prev.round_number, prev.round_number + 1):
            return False
        if nxt.round_number == prev.round_number and nxt.terminal is None:
            return False
        for old, new in ((prev.losses, nxt.losses), (prev.byes, nxt.byes)):
            if any(new.get(key, 0) < value for key, value in old.items()):
                return False
        if any(
            nxt.inconclusive.get(key, 0) < value for key, value in prev.inconclusive.items()
        ):
            return False
        return prev.quarantined <= nxt.quarantined and (
            prev.applied_receipt_digests <= nxt.applied_receipt_digests
        )

    def _verify_content(self) -> None:
        q = self._query
        refuse = self._refuse
        prev_hash = _GENESIS
        count = 0
        for seq, at, kind, subject, req, res, stored_prev, entry in q(
            "SELECT seq, at, kind, subject, request_digest, result_digest, prev_hash,"
            " entry_hash FROM audit ORDER BY seq"
        ):
            count += 1
            if (
                seq != count
                or stored_prev != prev_hash
                or entry != canonical_digest([stored_prev, at, kind, subject, req, res])
            ):
                raise refuse("audit hash chain is broken")
            prev_hash = entry
        audit_seqs = set(range(1, count + 1))
        if count == 0 or q("SELECT value FROM meta WHERE key = 'schema_version'") != [
            (str(SCHEMA_VERSION),)
        ]:
            raise refuse("store metadata/audit genesis missing")
        if q("SELECT value FROM meta WHERE key = 'bracket_codec'") != [(BRACKET_CODEC_ID,)]:
            raise refuse("store is not bound to the supported bracket codec")
        (high,) = q("SELECT high_water FROM clock_mark")[0]

        protocols: dict[str, MatchProtocol] = {}
        for digest, data, source in q(
            "SELECT protocol_digest, canonical, source_digest FROM protocols"
        ):
            data = bytes(data)
            protocol = decode_protocol(_load(data))
            if (
                _source_digest(data) != source
                or protocol.protocol_digest != digest
                or _bytes(protocol) != data
            ):
                raise refuse("protocol bytes/digest mismatch")
            protocols[digest] = protocol

        observations: dict[int, tuple[str, StatusObservation]] = {}
        latest: dict[str, Mapping[str, Any]] = {}
        for row in q(
            "SELECT id, subject, authority_id, mapping_id, synthetic, generation,"
            " observed_at, max_age, state, effective_at, recorded_at, content_digest"
            " FROM status_observations ORDER BY id"
        ):
            (oid, subject, authority, mapping_id, synthetic, generation) = row[:6]
            (observed_at, max_age, state, effective_at, recorded_at, content) = row[6:]
            status = StatusObservation(
                authority, mapping_id, generation, observed_at, max_age, state, effective_at
            )
            if content != _observation_content(subject, status, bool(synthetic)):
                raise refuse("status observation content digest mismatch")
            if recorded_at > high:
                raise refuse("clock high water is below a recorded observation")
            try:
                _check_progress(latest.get(subject), status.to_document())
            except AuthorityBlocked as error:
                raise refuse(f"status history regressed ({error})") from error
            latest[subject] = status.to_document()
            observations[oid] = (subject, status)

        admissions: dict[str, _Admission] = {}
        for row in q(
            "SELECT admission_digest, admission_ref, protocol_digest, stage,"
            " evidence_canonical, lease_canonical, issuers_canonical,"
            " authority_source_digest, enrolled_at, observation_id FROM admissions"
        ):
            (digest, ref, pdigest, stage, evb, leb, isb, source, enrolled, oid) = row
            protocol = protocols.get(pdigest)
            if protocol is None:
                raise refuse("admission references a missing protocol")
            evidence = decode_stage_evidence(_load(bytes(evb)))
            lease = decode_lease(_load(bytes(leb)))
            issuers = frozenset(_load(bytes(isb)))
            if (
                _bytes(evidence) != bytes(evb)
                or _bytes(lease) != bytes(leb)
                or _bytes(sorted(issuers)) != bytes(isb)
                or expected_admission_digest(protocol, evidence, lease) != digest
                or evidence.stage != stage
                or evidence.protocol_document_digest != pdigest
            ):
                raise refuse("admission bytes/digest mismatch")
            recorded = observations.get(oid)
            if (
                recorded is None
                or recorded[0] != f"admission:{digest}"
                or not lease.issued_at
                <= recorded[1].observed_at
                <= enrolled
                < lease.expires_at
                or recorded[1].revoked_by(enrolled)
            ):
                raise refuse("admission enrollment provenance is inconsistent")
            admissions[digest] = _Admission(
                digest, ref, protocol, stage, evidence, lease, issuers, source, enrolled, oid
            )

        seal_lists: dict[str, list[VariantSeal]] = {}
        for pdigest, seq, sdigest, data, sealed_at, txn in q(
            "SELECT protocol_digest, sequence, seal_digest, canonical, sealed_at, txn_seq"
            " FROM seals ORDER BY protocol_digest, sequence"
        ):
            seal = VariantSeal(**_load(bytes(data)))
            rows = seal_lists.setdefault(pdigest, [])
            if (
                seal.seal_digest != sdigest
                or _bytes(seal) != bytes(data)
                or seal.sequence != seq
                or seq != len(rows) + 1
                or seal.sealed_at != sealed_at
                or seal.protocol_digest != pdigest
                or pdigest not in protocols
                or txn not in audit_seqs
                or (rows and rows[-1].sealed_at >= sealed_at)
            ):
                raise refuse("seal history is inconsistent")
            rows.append(seal)

        chains: dict[str, list[BracketSnapshot]] = {}
        bracket_admission: dict[str, str] = {}
        for bid, adm_digest, pdigest, stage, track in q(
            "SELECT bracket_id, admission_digest, protocol_digest, stage, track FROM brackets"
        ):
            adm = admissions.get(adm_digest)
            if (
                adm is None
                or (adm.protocol.protocol_digest, adm.stage) != (pdigest, stage)
                or bid
                != canonical_digest(
                    {"admission_digest": adm_digest, "stage": stage, "track": track}
                )
            ):
                raise refuse("bracket identity is inconsistent")
            versions = q(
                "SELECT version, bracket_digest, canonical, prev_digest, txn_seq"
                " FROM bracket_versions WHERE bracket_id = ? ORDER BY version",
                (bid,),
            )
            chain: list[BracketSnapshot] = []
            for index, (version, bdigest, data, prev_digest, txn) in enumerate(versions):
                snap = decode_bracket(_load(bytes(data)))
                previous = chain[-1] if chain else None
                if (
                    version != index
                    or txn not in audit_seqs
                    or snap.bracket_digest != bdigest
                    or _bytes(snap) != bytes(data)
                    or (snap.protocol_digest, snap.admission_digest, snap.stage, snap.track)
                    != (pdigest, adm_digest, stage, track)
                    or prev_digest != (previous.bracket_digest if previous else None)
                ):
                    raise refuse("bracket version lineage is inconsistent")
                if previous is None:
                    if (
                        snap.round_number
                        or snap.losses
                        or snap.byes
                        or snap.inconclusive
                        or snap.quarantined
                        or snap.terminal
                        or snap.applied_receipt_digests
                    ):
                        raise refuse("initial bracket version is not empty")
                elif not self._successor_ok(previous, snap):
                    raise refuse("bracket version is not a legal successor")
                chain.append(snap)
            if not chain or q(
                "SELECT version, bracket_digest FROM bracket_current WHERE bracket_id = ?",
                (bid,),
            ) != [(len(chain) - 1, chain[-1].bracket_digest)]:
                raise refuse("bracket current pointer disagrees with lineage")
            chains[bid] = chain
            bracket_admission[bid] = adm_digest
        if q("SELECT COUNT(*) FROM bracket_current")[0][0] != len(chains):
            raise refuse("orphan bracket pointer")

        receipt_bracket: dict[str, str] = {}
        for row in q(
            "SELECT issuance_id, bracket_id, bracket_digest, round_number, plans_digest,"
            " observation_id, issued_at, validated_at, txn_seq FROM issuances"
            " ORDER BY issuance_id"
        ):
            (iid, bid, bdigest, rnd, plans_digest, oid, issued_at, validated_at, txn) = row
            lineage = chains.get(bid)
            snap = next(
                (s for s in lineage or () if s.bracket_digest == bdigest), None
            )
            adm = admissions.get(bracket_admission.get(bid, ""))
            issued_obs = observations.get(oid)
            if (
                snap is None
                or adm is None
                or issued_obs is None
                or txn not in audit_seqs
                or rnd != snap.round_number + 1
                or issued_obs[0] != f"admission:{adm.admission_digest}"
                or not (
                    adm.lease.issued_at
                    <= issued_obs[1].observed_at
                    <= issued_at
                    <= validated_at
                    < adm.lease.expires_at
                )
                or issued_obs[1].revoked_by(issued_at)
            ):
                raise refuse("issuance provenance is inconsistent")
            plans = []
            for index, (rdigest, pdigest, pair, data, r_issued) in enumerate(
                q(
                    "SELECT receipt_digest, plan_digest, pair_index, plan_canonical,"
                    " issued_at FROM receipts WHERE issuance_id = ? ORDER BY pair_index",
                    (iid,),
                )
            ):
                plan = RoundPlanEntry(**_load(bytes(data)))
                if (
                    pair != index
                    or r_issued != issued_at
                    or plan.plan_digest != pdigest
                    or _bytes(plan) != bytes(data)
                    or rdigest
                    != canonical_digest({"plan": plan, "issued_at": issued_at})
                    or (plan.bracket_digest, plan.round_number, plan.pair_index)
                    != (bdigest, rnd, index)
                    or (plan.admission_digest, plan.stage)
                    != (adm.admission_digest, adm.stage)
                ):
                    raise refuse("issued receipt bytes/digest mismatch")
                receipt_bracket[rdigest] = bid
                plans.append(pdigest)
            if not plans or plans_digest != canonical_digest(plans):
                raise refuse("issuance plan set digest mismatch")

        consumed: dict[str, set[str]] = {}
        for rdigest, txn, outcome, derivation, _evidence, aggregates in q(
            "SELECT receipt_digest, txn_seq, outcome, derivation, evidence_digest,"
            " aggregate_digests FROM consumptions"
        ):
            bid = receipt_bracket.get(rdigest)
            if (
                bid is None
                or txn not in audit_seqs
                or derivation not in {"plan", "evaluator", "aggregates"}
                or not isinstance(json.loads(aggregates), list)
            ):
                raise refuse("consumption record is inconsistent")
            consumed.setdefault(bid, set()).add(rdigest)
        for bid, chain in chains.items():
            if chain[-1].applied_receipt_digests != consumed.get(bid, set()):
                raise refuse("consumed receipts disagree with bracket history")

        for digest, binding, adm_digest, data, oid, txn in q(
            "SELECT measurement_digest, binding_digest, admission_digest, canonical,"
            " observation_id, txn_seq FROM measurements"
        ):
            document = _load(bytes(data))
            if (
                document.get("evidence_digest") != digest
                or document.get("binding_digest") != binding
                or canonical_digest(document.get("binding")) != binding
                or adm_digest not in admissions
                or oid not in observations
                or txn not in audit_seqs
            ):
                raise refuse("measurement record is inconsistent")

        for adigest, adm_digest, metric, data, txn in q(
            "SELECT aggregate_digest, admission_digest, metric, canonical, txn_seq"
            " FROM aggregates"
        ):
            evidence = decode_aggregate(_load(bytes(data)))
            uses = q(
                "SELECT measurement_digest, family_id, task_id, repetition, value_json,"
                " position FROM aggregate_uses WHERE aggregate_digest = ? ORDER BY position",
                (adigest,),
            )
            rows = tuple(
                FamilyObservation(f, t, r, m, json.loads(v)) for m, f, t, r, v, _ in uses
            )
            if (
                canonical_digest(evidence) != adigest
                or _bytes(evidence) != bytes(data)
                or evidence.admission_digest != adm_digest
                or evidence.metric != metric
                or adm_digest not in admissions
                or txn not in audit_seqs
                or [u[5] for u in uses] != list(range(len(uses)))
                or {(r.family_id, r.task_id, r.repetition) for r in rows}
                != {(s.family_id, s.task_id, s.repetition) for s in evidence.observation_shape}
                or len(rows) != len(evidence.observation_shape)
                or canonical_digest(rows) != evidence.observation_digest
            ):
                raise refuse("aggregate record is inconsistent")

        seal_results: dict[str, list[tuple[int, str]]] = {}
        for req, kind, adm_digest, rkind, ref, rdigest, txn in q(
            "SELECT request_digest, kind, admission_digest, result_kind, result_ref,"
            " result_digest, txn_seq FROM request_results"
        ):
            if adm_digest not in admissions or txn not in audit_seqs:
                raise refuse("recorded request result is orphaned")
            if rkind == "bracket":
                bid, _, version = ref.rpartition(":")
                recorded_chain = chains.get(bid)
                if (
                    recorded_chain is None
                    or not version.isdigit()
                    or int(version) >= len(recorded_chain)
                ):
                    raise refuse("recorded bracket result is missing")
                if recorded_chain[int(version)].bracket_digest != rdigest:
                    raise refuse("recorded bracket result changed")
            elif rkind == "receipts":
                if not q("SELECT 1 FROM issuances WHERE issuance_id = ? AND plans_digest = ?", (ref, rdigest)):
                    raise refuse("recorded issuance result changed")
            elif rkind == "aggregate":
                if ref != rdigest or not q(
                    "SELECT 1 FROM aggregates WHERE aggregate_digest = ?", (ref,)
                ):
                    raise refuse("recorded aggregate result changed")
            elif rkind == "seals":
                history = seal_lists.get(ref)
                if ref not in protocols or history is None:
                    raise refuse("recorded seal result is orphaned")
                if not any(
                    canonical_digest(history[:size]) == rdigest
                    for size in range(1, len(history) + 1)
                ):
                    raise refuse("recorded seal result no longer matches the history")
                seal_results.setdefault(ref, []).append((txn, rdigest))
            else:
                raise refuse("unknown recorded result kind")
        for ref, recorded in seal_results.items():
            if max(recorded)[1] != canonical_digest(seal_lists[ref]):
                raise refuse("seal history is shorter than its latest recorded append")

    # -- verified loaders ---------------------------------------------------------

    def _load_protocol(self, digest: str) -> MatchProtocol:
        row = self._one(
            "SELECT canonical, source_digest FROM protocols WHERE protocol_digest = ?",
            (digest,),
        )
        if row is None:
            raise CampaignMetricsError("unknown protocol")
        data = bytes(row[0])
        protocol = decode_protocol(_load(data))
        if (
            _source_digest(data) != row[1]
            or protocol.protocol_digest != digest
            or _bytes(protocol) != data
        ):
            raise N30StoreError("stored protocol bytes changed")
        return protocol

    def _load_admission(self, digest: str) -> _Admission:
        row = self._one(
            "SELECT admission_ref, protocol_digest, stage, evidence_canonical,"
            " lease_canonical, issuers_canonical, authority_source_digest, enrolled_at,"
            " observation_id FROM admissions WHERE admission_digest = ?",
            (digest,),
        )
        if row is None:
            raise CampaignMetricsError("unknown admission")
        protocol = self._load_protocol(row[1])
        evidence = decode_stage_evidence(_load(bytes(row[3])))
        lease = decode_lease(_load(bytes(row[4])))
        issuers = frozenset(_load(bytes(row[5])))
        if (
            expected_admission_digest(protocol, evidence, lease) != digest
            or _bytes(evidence) != bytes(row[3])
            or _bytes(lease) != bytes(row[4])
            or evidence.stage != row[2]
        ):
            raise N30StoreError("stored admission bytes changed")
        return _Admission(
            digest, row[0], protocol, row[2], evidence, lease, issuers, row[6], row[7], row[8]
        )

    def _seal_history(self, protocol_digest: str) -> tuple[VariantSeal, ...]:
        seals = []
        for sequence, digest, data in self._query(
            "SELECT sequence, seal_digest, canonical FROM seals WHERE protocol_digest = ?"
            " ORDER BY sequence",
            (protocol_digest,),
        ):
            seal = VariantSeal(**_load(bytes(data)))
            if (
                seal.seal_digest != digest
                or seal.sequence != sequence
                or sequence != len(seals) + 1
            ):
                raise N30StoreError("stored seal history changed")
            seals.append(seal)
        return tuple(seals)

    def _bracket_current(self, bracket_id: str) -> tuple[int, BracketSnapshot]:
        row = self._one(
            "SELECT c.version, v.canonical, v.bracket_digest FROM bracket_current c"
            " JOIN bracket_versions v ON v.bracket_id = c.bracket_id"
            " AND v.version = c.version WHERE c.bracket_id = ?",
            (bracket_id,),
        )
        if row is None:
            raise CampaignMetricsError("unknown bracket")
        snapshot = decode_bracket(_load(bytes(row[1])))
        if snapshot.bracket_digest != row[2] or _bytes(snapshot) != bytes(row[1]):
            raise N30StoreError("stored bracket bytes changed")
        return int(row[0]), snapshot

    def _admission_digest(self, handle: object) -> str:
        return self._interner.text_key(handle, _AdmissionHandle)

    def _state(
        self, state_handle: object, admission_digest: str
    ) -> tuple[str, int, BracketSnapshot]:
        bracket_id, version = self._interner.bracket_key(state_handle)
        current, snapshot = self._bracket_current(bracket_id)
        if version != current:
            raise CampaignMetricsError("foreign, forged, or superseded bracket handle")
        if snapshot.admission_digest != admission_digest:
            raise CampaignMetricsError("bracket is not bound to this admission handle")
        return bracket_id, current, snapshot

    def _bracket_state(self, bracket_id: str, version: int) -> BracketState:
        return BracketState(self._interner.wrapper(_BracketHandle, (bracket_id, version)))

    def _record_result(
        self,
        seq: int,
        kind: str,
        request_digest: str,
        admission_digest: str,
        result_kind: str,
        ref: str,
        result_digest: str,
    ) -> None:
        row = self._conn.execute(
            "SELECT kind, admission_digest, result_kind, result_ref, result_digest"
            " FROM request_results WHERE request_digest = ?",
            (request_digest,),
        ).fetchone()
        wanted = (kind, admission_digest, result_kind, ref, result_digest)
        if row is not None:
            if tuple(row) != wanted:
                raise N30StoreError("an immutable recorded result would change")
            return
        self._conn.execute(
            "INSERT INTO request_results VALUES (?,?,?,?,?,?,?)",
            (request_digest, kind, admission_digest, result_kind, ref, result_digest, seq),
        )

    # -- authority ----------------------------------------------------------------

    @staticmethod
    def _enrol_operation(evidence: StageEvidence, lease: LeaseRecord, now: int) -> str:
        candidates: list[str] = []
        if (
            evidence.stage == "final"
            and evidence.holdout_opened_at is not None
            and now < evidence.holdout_opened_at
        ):
            candidates.append("seal")
        candidates += ["schedule", *sorted(lease.operations)]
        for operation in candidates:
            if operation in lease.operations:
                return operation
        raise CampaignMetricsError("lease permits no operation")

    @staticmethod
    def _independent_authority(evidence: StageEvidence, status: StatusObservation) -> None:
        principals = evidence.principals
        identities = {
            principals.evaluator_id,
            principals.custodian_id,
            *principals.builder_ids,
            *principals.affected_champion_ids,
        }
        if status.authority_id in identities:
            raise AuthorityBlocked("status authority is not independent of the principals")

    def _authorize(
        self,
        admission_digest: str,
        operation: str,
        *,
        state_digest: str | None = None,
        allow_exhausted: bool = False,
    ) -> _Auth:
        """Fresh current authority for one positive use (or authenticated closure).

        The trusted UTC time used for freshness, expiry and observation recording is
        sampled again *after* the provider returns.
        """
        adm = self._load_admission(admission_digest)
        use = AdmissionUse(
            adm.protocol.protocol_digest, adm.stage, operation, state_digest
        )
        context = MappingProxyType(
            {
                "admission_ref": adm.admission_ref,
                "admission_digest": adm.admission_digest,
                "authority_source_digest": adm.authority_source_digest,
                "lease_digest": adm.lease.lease_digest,
                "stage_evidence_digest": adm.evidence.evidence_digest,
            }
        )
        evidence, mapping, now = self._call("n30.current", "current", use, context)
        if (
            not isinstance(evidence, CurrentAdmissionEvidence)
            or evidence.admission_ref != adm.admission_ref
            or evidence.source_digest != adm.authority_source_digest
            or evidence.stage_evidence != adm.evidence
            or evidence.lease != adm.lease
            or frozenset(evidence.trusted_lease_issuers) != adm.issuers
        ):
            raise CampaignMetricsError(
                "current authority disagrees with the immutable admission"
            )
        status = self._check_status(evidence.status, mapping, now)
        self._independent_authority(adm.evidence, status)
        observation_id = self._observe(
            "admission", f"admission:{adm.admission_digest}", status, mapping, now
        )
        return self._classify(
            adm, status, observation_id, now, operation, state_digest, allow_exhausted
        )

    def _classify(
        self,
        adm: _Admission,
        status: StatusObservation,
        observation_id: int,
        now: int,
        operation: str,
        state_digest: str | None,
        allow_exhausted: bool,
    ) -> _Auth:
        lease = adm.lease
        if now < lease.issued_at:
            raise AuthorityBlocked("lease is not yet active at trusted time")
        exhausted = None
        if status.revoked_by(now):
            exhausted = "revoked"
        elif now >= lease.expires_at:
            exhausted = "expired"
        if exhausted is not None:
            if allow_exhausted:
                return _Auth(adm, now, status, observation_id, exhausted, None)
            raise LeaseExhausted(f"lease {exhausted}")
        snapshot = AdmissionSnapshot(
            adm.admission_digest,
            adm.protocol.protocol_digest,
            adm.evidence,
            lease,
            adm.issuers,
            now,
            self._seal_history(adm.protocol.protocol_digest),
        )
        validate_admission_snapshot(
            snapshot, adm.protocol, adm.stage, operation, state_digest
        )
        return _Auth(adm, now, status, observation_id, None, snapshot)

    def _recheck(self, auth: _Auth, operation: str) -> int:
        """Inside a write transaction: fresh clock/lease/status immediately pre-commit.

        ``auth`` must be the *final* authority read of the public call, taken after every
        provider dependency and before this transaction opened (no provider call may run
        inside a write transaction). This check only re-validates that read against a newly
        sampled trusted UTC time; it cannot see a revocation that happens after that read,
        and no atomicity with an external service is claimed.
        """
        now = self._now()
        self._advance_clock(now)
        status = auth.status
        if now < auth.now:
            raise AuthorityBlocked("trusted clock regressed since the final authority read")
        if now >= status.observed_at + status.max_age:
            raise AuthorityBlocked("authoritative status went stale before commit")
        if auth.exhausted is None:
            if status.revoked_by(now):
                raise LeaseExhausted("lease revoked before commit")
            if now >= auth.admission.lease.expires_at:
                raise LeaseExhausted("lease expired before commit")
            evidence = auth.admission.evidence
            holdout = evidence.holdout_opened_at
            if (
                operation == "seal"
                and evidence.stage == "final"
                and (holdout is None or now >= holdout)
            ):
                raise CampaignMetricsError("final seal window closed before commit")
        return now

    @staticmethod
    def _snapshot(auth: _Auth) -> AdmissionSnapshot:
        if auth.snapshot is None:
            raise CampaignMetricsError("no positive admission snapshot is available")
        return auth.snapshot

    def _final_read(
        self, prior: _Auth, operation: str, *, state_digest: str | None = None
    ) -> _Auth:
        """Reread operation/admission/state authority after every provider dependency.

        Runs outside any write transaction (a provider call never holds the SQLite write
        lock, and ``_authorize`` opens its own short observation transaction, so it is
        never nested). Unknown, unavailable, stale, future or regressed answers block; a
        confirmed revocation or expiry raises ``LeaseExhausted`` with no positive
        effect. The original issuance provenance is untouched; only a new observation is
        appended.
        """
        final = self._authorize(
            prior.admission.admission_digest, operation, state_digest=state_digest
        )
        if (
            prior.snapshot is not None
            and final.snapshot is not None
            and final.snapshot.seal_history != prior.snapshot.seal_history
        ):
            raise CampaignMetricsError("seal history changed while dependencies ran")
        return final

    # -- host enrollment/recovery -------------------------------------------------

    def admit(self, protocol: MatchProtocol, stage: str, admission_ref: str) -> object:
        """Enroll (or host-recover) one admission; wrappers exist only after authority.

        The immutable StageEvidence/LeaseRecord come from the current-admission port,
        never from the caller. Repeating the call after restart re-authenticates and
        returns a fresh owned wrapper for the same durable record.
        """
        if not isinstance(protocol, MatchProtocol) or stage not in STAGES:
            raise CampaignMetricsError("admission requires a protocol and known stage")
        _text(admission_ref, "admission_ref")
        existing = self._one(
            "SELECT admission_digest FROM admissions WHERE admission_ref = ?",
            (admission_ref,),
        )
        if existing is not None:
            adm = self._load_admission(existing[0])
            if (
                adm.protocol.protocol_digest != protocol.protocol_digest
                or adm.stage != stage
            ):
                raise CampaignMetricsError("admission reference names another protocol/stage")
            self._authorize(
                adm.admission_digest,
                self._enrol_operation(adm.evidence, adm.lease, self._now()),
                allow_exhausted=True,
            )
            self._ensure_live()
            return self._interner.wrapper(_AdmissionHandle, (adm.admission_digest,))
        use = AdmissionUse(protocol.protocol_digest, stage, "schedule")
        context = MappingProxyType(
            {
                "admission_ref": admission_ref,
                "protocol_digest": protocol.protocol_digest,
                "stage": stage,
                "enrolment": True,
            }
        )
        evidence, mapping, now = self._call("n30.current", "current", use, context)
        if (
            not isinstance(evidence, CurrentAdmissionEvidence)
            or evidence.admission_ref != admission_ref
            or not isinstance(evidence.stage_evidence, StageEvidence)
            or not isinstance(evidence.lease, LeaseRecord)
        ):
            raise CampaignMetricsError("current-admission port returned invalid evidence")
        _sha(evidence.source_digest, "authority source digest")
        status = self._check_status(evidence.status, mapping, now)
        self._independent_authority(evidence.stage_evidence, status)
        issuers = frozenset(evidence.trusted_lease_issuers)
        digest = expected_admission_digest(protocol, evidence.stage_evidence, evidence.lease)
        snapshot = AdmissionSnapshot(
            digest,
            protocol.protocol_digest,
            evidence.stage_evidence,
            evidence.lease,
            issuers,
            now,
            self._seal_history(protocol.protocol_digest),
        )
        validate_admission_snapshot(
            snapshot,
            protocol,
            stage,
            self._enrol_operation(evidence.stage_evidence, evidence.lease, now),
        )
        if not evidence.lease.issued_at <= status.observed_at:
            raise AuthorityBlocked("status observation predates the lease")
        with self._transaction("admit"):
            self._advance_clock(now)
            if now >= evidence.lease.expires_at or status.revoked_by(now):
                raise LeaseExhausted("cannot enroll an exhausted admission")
            conflict = self._conn.execute(
                "SELECT 1 FROM admissions WHERE admission_digest = ? OR admission_ref = ?"
                " OR (protocol_digest = ? AND stage = ?)",
                (digest, admission_ref, protocol.protocol_digest, stage),
            ).fetchone()
            if conflict is not None:
                raise N30StoreError("admission identity already stored with other content")
            protocol_bytes = _bytes(protocol)
            stored = self._conn.execute(
                "SELECT canonical FROM protocols WHERE protocol_digest = ?",
                (protocol.protocol_digest,),
            ).fetchone()
            if stored is None:
                self._conn.execute(
                    "INSERT INTO protocols VALUES (?,?,?)",
                    (
                        protocol.protocol_digest,
                        protocol_bytes,
                        _source_digest(protocol_bytes),
                    ),
                )
            elif bytes(stored[0]) != protocol_bytes:
                raise N30StoreError("protocol identity already stored with other bytes")
            observation_id = self._record_status(
                f"admission:{digest}", status, mapping, now
            )
            self._conn.execute(
                "INSERT INTO admissions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    digest,
                    admission_ref,
                    protocol.protocol_digest,
                    stage,
                    _bytes(evidence.stage_evidence),
                    _bytes(evidence.lease),
                    _bytes(sorted(issuers)),
                    evidence.source_digest,
                    now,
                    observation_id,
                ),
            )
            self._audit("admit", f"admission:{digest}", now, None, digest)
        return self._interner.wrapper(_AdmissionHandle, (digest,))

    # -- AdmissionRegistry: resolve / brackets ------------------------------------

    def resolve(self, handle: object, use: AdmissionUse) -> AdmissionSnapshot:
        if (
            not isinstance(use, AdmissionUse)
            or use.operation not in OPERATIONS
            or use.stage not in STAGES
        ):
            raise CampaignMetricsError("invalid admission use")
        _sha(use.protocol_digest, "use protocol")
        if use.state_admission_digest is not None:
            _sha(use.state_admission_digest, "use state admission")
        digest = self._admission_digest(handle)
        adm = self._load_admission(digest)
        if (
            use.protocol_digest != adm.protocol.protocol_digest
            or use.stage != adm.stage
            or use.state_admission_digest not in (None, digest)
        ):
            raise CampaignMetricsError("foreign use")
        auth = self._authorize(
            digest, use.operation, state_digest=use.state_admission_digest
        )
        snapshot = self._snapshot(auth)
        self._ensure_live()  # linearize the positive return with poison/close
        return snapshot

    def open_bracket(
        self, handle: object, protocol_digest: str, stage: str, track: str
    ) -> BracketState:
        digest = self._admission_digest(handle)
        _sha(protocol_digest, "protocol")
        _text(track, "track")
        auth = self._authorize(digest, "schedule")
        adm = auth.admission
        if protocol_digest != adm.protocol.protocol_digest or stage != adm.stage:
            raise CampaignMetricsError("foreign bracket open")
        if not active_variants_for(adm.protocol, adm.evidence, track):
            raise CampaignMetricsError("track has no admitted entrants")
        bracket_id = canonical_digest(
            {"admission_digest": digest, "stage": stage, "track": track}
        )
        initial = BracketSnapshot(protocol_digest, digest, stage, track)
        request = canonical_digest({"op": "open_bracket", "bracket_id": bracket_id})
        with self._transaction("open_bracket"):
            now = self._recheck(auth, "schedule")
            seq = self._audit("open_bracket", bracket_id, now, request, initial.bracket_digest)
            row = self._conn.execute(
                "SELECT version FROM bracket_current WHERE bracket_id = ?", (bracket_id,)
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO brackets VALUES (?,?,?,?,?)",
                    (bracket_id, digest, protocol_digest, stage, track),
                )
                self._conn.execute(
                    "INSERT INTO bracket_versions VALUES (?,?,?,?,?,?)",
                    (bracket_id, 0, initial.bracket_digest, _bytes(initial), None, seq),
                )
                self._conn.execute(
                    "INSERT INTO bracket_current VALUES (?,?,?)",
                    (bracket_id, 0, initial.bracket_digest),
                )
            elif row[0] != 0:
                raise CampaignMetricsError(
                    "bracket already progressed; ordinary open cannot reset or revive it"
                )
            self._record_result(
                seq, "open_bracket", request, digest, "bracket", f"{bracket_id}:0",
                initial.bracket_digest,
            )
        return self._bracket_state(bracket_id, 0)

    def resolve_bracket(
        self, handle: object, state_handle: object, protocol_digest: str, operation: str
    ) -> BracketSnapshot:
        digest = self._admission_digest(handle)
        _sha(protocol_digest, "protocol")
        if operation not in OPERATIONS:
            raise CampaignMetricsError("unknown operation")
        _, _, snapshot = self._state(state_handle, digest)
        if snapshot.protocol_digest != protocol_digest:
            raise CampaignMetricsError("foreign bracket protocol")
        # Confirmed expiry/revocation still yields authenticated history, but only
        # commit_bracket may use it, and only for unchanged-history closure.
        self._authorize(
            digest, operation, state_digest=snapshot.admission_digest, allow_exhausted=True
        )
        self._ensure_live()
        return snapshot

    # -- AdmissionRegistry: rounds ------------------------------------------------

    def issue_round(
        self, handle: object, plans: tuple[RoundPlanEntry, ...]
    ) -> tuple[IssuedReceipt, ...]:
        digest = self._admission_digest(handle)
        entries = tuple(plans)
        if not entries or any(not isinstance(plan, RoundPlanEntry) for plan in entries):
            raise CampaignMetricsError("issuance requires the complete plan entries")
        first = entries[0]
        if any(
            plan.admission_digest != digest
            or plan.bracket_digest != first.bracket_digest
            or plan.round_number != first.round_number
            for plan in entries
        ):
            raise CampaignMetricsError("plan entries are not one exact admitted round")
        row = self._one(
            "SELECT bracket_id FROM bracket_current WHERE bracket_digest = ?",
            (first.bracket_digest,),
        )
        if row is None:
            raise CampaignMetricsError("plan is not bound to a current bracket version")
        bracket_id = str(row[0])
        _, bracket = self._bracket_current(bracket_id)
        if bracket.admission_digest != digest:
            raise CampaignMetricsError("bracket is not bound to this admission handle")
        auth = self._authorize(digest, "schedule", state_digest=bracket.admission_digest)
        adm = auth.admission
        terminal, expected = plan_next_round(adm.protocol, bracket, self._snapshot(auth))
        if terminal is not None or expected != entries:
            raise CampaignMetricsError("plans differ from the canonical admitted round")
        plans_digest = canonical_digest([plan.plan_digest for plan in entries])
        request = issue_request_digest(entries)
        with self._transaction("issue_round"):
            now = self._recheck(auth, "schedule")
            current = self._conn.execute(
                "SELECT bracket_digest FROM bracket_current WHERE bracket_id = ?",
                (bracket_id,),
            ).fetchone()
            if current is None or current[0] != first.bracket_digest:
                raise CampaignMetricsError("bracket changed before issuance")
            seq = self._audit("issue_round", bracket_id, now, request, plans_digest)
            issuance = self._conn.execute(
                "SELECT issuance_id, plans_digest FROM issuances"
                " WHERE bracket_digest = ? AND round_number = ?",
                (first.bracket_digest, first.round_number),
            ).fetchone()
            if issuance is not None:
                if issuance[1] != plans_digest:
                    raise CampaignMetricsError("conflicting plan for an issued round")
                issuance_id = int(issuance[0])
            else:
                status = auth.status
                if not (
                    adm.lease.issued_at <= status.observed_at <= now < adm.lease.expires_at
                ):
                    raise AuthorityBlocked("issuance provenance violates lease/status order")
                cursor = self._conn.execute(
                    "INSERT INTO issuances (bracket_id, bracket_digest, round_number,"
                    " plans_digest, observation_id, issued_at, validated_at, txn_seq)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        bracket_id,
                        first.bracket_digest,
                        first.round_number,
                        plans_digest,
                        auth.observation_id,
                        now,
                        now,
                        seq,
                    ),
                )
                issuance_id = _rowid(cursor)
                for index, plan in enumerate(entries):
                    self._conn.execute(
                        "INSERT INTO receipts VALUES (?,?,?,?,?,?)",
                        (
                            canonical_digest({"plan": plan, "issued_at": now}),
                            plan.plan_digest,
                            issuance_id,
                            index,
                            _bytes(plan),
                            now,
                        ),
                    )
            self._record_result(
                seq, "issue_round", request, digest, "receipts", str(issuance_id), plans_digest
            )
        return self._receipts_for(issuance_id, entries)

    def _receipts_for(
        self, issuance_id: int, expected: tuple[RoundPlanEntry, ...] | None = None
    ) -> tuple[IssuedReceipt, ...]:
        rows = self._query(
            "SELECT receipt_digest, plan_canonical, issued_at FROM receipts"
            " WHERE issuance_id = ? ORDER BY pair_index",
            (issuance_id,),
        )
        receipts = []
        for rdigest, data, issued_at in rows:
            plan = RoundPlanEntry(**_load(bytes(data)))
            receipts.append(
                IssuedReceipt(
                    self._interner.wrapper(_ReceiptHandle, (rdigest,)), plan, issued_at
                )
            )
        if expected is not None and tuple(r.plan for r in receipts) != expected:
            raise N30StoreError("stored issuance differs from the requested plans")
        return tuple(receipts)

    def _authenticate_outcome(
        self,
        handle: object,
        adm: _Admission,
        stored: IssuedReceipt,
        result: ReceiptOutcome,
    ) -> tuple[str, str | None, tuple[str, ...], StatusObservation | None, ReviewedMapping | None]:
        """Return (derivation, evidence digest, aggregate digests, status, mapping).

        Freshness and the event window use the trusted UTC time sampled after the
        outcome provider returned.
        """
        plan = stored.plan
        if plan.bye:
            if result.outcome != "BYE":
                raise CampaignMetricsError("BYE derives only from the canonical plan")
            return "plan", None, (), None, None
        if result.outcome == "BYE":
            raise CampaignMetricsError("only a canonical BYE plan can produce BYE")
        outcome, mapping, now = self._call("n30.outcome", "outcome", stored)
        if (
            not isinstance(outcome, AuthenticatedOutcome)
            or outcome.plan_digest != plan.plan_digest
            or outcome.receipt_digest != stored.receipt_digest
            or outcome.evaluator_id != plan.evaluator_id
            or outcome.custodian_id != plan.custodian_id
            or outcome.evaluator_id != adm.evidence.principals.evaluator_id
            or outcome.custodian_id != adm.evidence.principals.custodian_id
            or outcome.outcome != result.outcome
        ):
            raise CampaignMetricsError("authenticated outcome does not bind the exact receipt")
        _sha(outcome.evidence_digest, "outcome evidence")
        lease, evidence = adm.lease, adm.evidence
        floor = max(lease.issued_at, evidence.stage_opened_at, stored.issued_at)
        if evidence.holdout_opened_at is not None:
            floor = max(floor, evidence.holdout_opened_at)
        if not (
            floor <= outcome.observed_at <= outcome.signed_at <= now
            and outcome.signed_at < lease.expires_at
        ):
            raise AuthorityBlocked("outcome lies outside its reviewed event window")
        status = self._check_status(outcome.status, mapping, now)
        self._independent_authority(evidence, status)
        if outcome.derivation not in {"aggregates", "evaluator"}:
            raise CampaignMetricsError("unknown outcome derivation")
        if (
            self._policy.outcome_dependency == "aggregates_required"
            and outcome.derivation != "aggregates"
        ):
            raise CampaignMetricsError(
                "reviewed remit requires aggregate dependencies; relabelling is refused"
            )
        aggregates = tuple(outcome.aggregate_digests)
        if outcome.derivation == "evaluator":
            if aggregates:
                raise CampaignMetricsError("direct outcome cannot cite aggregates")
        else:
            if len(aggregates) != 3:
                raise CampaignMetricsError("aggregate derivation needs all three metrics")
            receipts = []
            for aggregate_digest in aggregates:
                _sha(aggregate_digest, "aggregate dependency")
                if self._one(
                    "SELECT 1 FROM aggregates WHERE aggregate_digest = ?",
                    (aggregate_digest,),
                ) is None:
                    raise CampaignMetricsError("outcome cites an unrecorded aggregate")
                receipts.append(
                    AggregateReceipt(
                        self._interner.wrapper(_AggregateHandle, (aggregate_digest,)),
                        aggregate_digest,
                    )
                )
            decided = decide_match(
                adm.protocol,
                receipts[0],
                receipts[1],
                receipts[2],
                registry=self,  # type: ignore[arg-type]
                admission_handle=handle,
            )
            first = self._load_aggregate(aggregates[0])
            if decided != result.outcome or (first.left, first.right) != (
                plan.left,
                plan.right,
            ):
                raise CampaignMetricsError(
                    "recomputed aggregate decision differs from the outcome"
                )
        return outcome.derivation, outcome.evidence_digest, aggregates, status, mapping

    def consume_round(
        self, handle: object, state_handle: object, request: ConsumeRoundRequest
    ) -> BracketState:
        digest = self._admission_digest(handle)
        if (
            not isinstance(request, ConsumeRoundRequest)
            or not isinstance(request.transition, BracketTransition)
            or any(not isinstance(item, ReceiptOutcome) for item in request.results)
        ):
            raise CampaignMetricsError("malformed consume request")
        bracket_id, version, bracket = self._state(state_handle, digest)
        if (
            request.admission_digest != digest
            or request.protocol_digest != bracket.protocol_digest
            or request.stage != bracket.stage
            or request.expected_bracket_digest != bracket.bracket_digest
            or request.round_number != bracket.round_number + 1
        ):
            raise CampaignMetricsError("round consumption is not bound to bracket state")
        results = tuple(request.results)
        issuance = self._one(
            "SELECT issuance_id FROM issuances WHERE bracket_digest = ? AND round_number = ?",
            (bracket.bracket_digest, request.round_number),
        )
        if issuance is None:
            raise CampaignMetricsError("no issued round exists for this bracket state")
        issued = {
            receipt.receipt_digest: receipt for receipt in self._receipts_for(issuance[0])
        }
        submitted: dict[str, ReceiptOutcome] = {}
        for result in results:
            rdigest = self._interner.text_key(result.receipt.opaque_handle, _ReceiptHandle)
            stored = issued.get(rdigest)
            if stored is None:
                raise CampaignMetricsError("receipt is not in the issued set")
            if (
                result.receipt.plan != stored.plan
                or result.receipt.receipt_digest != stored.receipt_digest
                or result.receipt.issued_at != stored.issued_at
            ):
                raise CampaignMetricsError("receipt mutated or substituted")
            if rdigest in submitted:
                raise CampaignMetricsError("duplicate receipt in one consumption")
            submitted[rdigest] = result
        if set(submitted) != set(issued):
            raise CampaignMetricsError("results must exactly cover every issued receipt")
        if any(
            self._one("SELECT 1 FROM consumptions WHERE receipt_digest = ?", (rdigest,))
            for rdigest in submitted
        ):
            raise CampaignMetricsError("append-only receipt replay")
        auth = self._authorize(digest, "apply", state_digest=bracket.admission_digest)
        adm = auth.admission
        expected = transition_after_round(adm.protocol, bracket, results)
        if canonical_digest(expected) != canonical_digest(request.transition):
            raise CampaignMetricsError("transition differs from the recomputed successor")
        verified = {
            rdigest: self._authenticate_outcome(
                handle, adm, issued[rdigest], submitted[rdigest]
            )
            for rdigest in sorted(submitted)
        }
        # Final authority read, after every provider dependency and outside any write
        # transaction: a revocation/expiry/unknown/stale answer here blocks the commit.
        auth = self._final_read(auth, "apply", state_digest=bracket.admission_digest)
        successor = BracketSnapshot(
            bracket.protocol_digest,
            bracket.admission_digest,
            bracket.stage,
            bracket.track,
            expected.round_number,
            expected.losses,
            expected.byes,
            expected.inconclusive,
            expected.quarantined,
            expected.terminal,
            expected.applied_receipt_digests,
        )
        request_digest = consume_request_digest(bracket_id, request)
        with self._transaction("consume_round"):
            now = self._recheck(auth, "apply")
            for _, _, _, status, _ in verified.values():
                if status is not None and now >= status.observed_at + status.max_age:
                    raise AuthorityBlocked("outcome status went stale before commit")
            current = self._conn.execute(
                "SELECT version, bracket_digest FROM bracket_current WHERE bracket_id = ?",
                (bracket_id,),
            ).fetchone()
            if current is None or tuple(current) != (version, bracket.bracket_digest):
                raise CampaignMetricsError("bracket compare-and-swap failed")
            for rdigest in verified:
                if self._conn.execute(
                    "SELECT 1 FROM consumptions WHERE receipt_digest = ?", (rdigest,)
                ).fetchone():
                    raise CampaignMetricsError("append-only receipt replay")
            seq = self._audit(
                "consume_round", bracket_id, now, request_digest, successor.bracket_digest
            )
            for rdigest, (derivation, evidence, aggregates, status, mapping) in verified.items():
                if status is not None and mapping is not None:
                    self._record_status(f"outcome:{rdigest}", status, mapping, now)
                self._conn.execute(
                    "INSERT INTO consumptions VALUES (?,?,?,?,?,?)",
                    (
                        rdigest,
                        seq,
                        submitted[rdigest].outcome,
                        derivation,
                        evidence,
                        json.dumps(list(aggregates)),
                    ),
                )
            self._install_version(bracket_id, version, bracket, successor, seq)
            self._record_result(
                seq,
                "consume_round",
                request_digest,
                digest,
                "bracket",
                f"{bracket_id}:{version + 1}",
                successor.bracket_digest,
            )
        return self._bracket_state(bracket_id, version + 1)

    def _install_version(
        self,
        bracket_id: str,
        version: int,
        prior: BracketSnapshot,
        successor: BracketSnapshot,
        seq: int,
    ) -> None:
        self._conn.execute(
            "INSERT INTO bracket_versions VALUES (?,?,?,?,?,?)",
            (
                bracket_id,
                version + 1,
                successor.bracket_digest,
                _bytes(successor),
                prior.bracket_digest,
                seq,
            ),
        )
        cursor = self._conn.execute(
            "UPDATE bracket_current SET version = ?, bracket_digest = ?"
            " WHERE bracket_id = ? AND version = ? AND bracket_digest = ?",
            (
                version + 1,
                successor.bracket_digest,
                bracket_id,
                version,
                prior.bracket_digest,
            ),
        )
        if cursor.rowcount != 1:
            raise CampaignMetricsError("bracket compare-and-swap failed")

    def commit_bracket(
        self,
        handle: object,
        state_handle: object,
        expected_bracket_digest: str,
        transition: BracketTransition,
    ) -> BracketState:
        digest = self._admission_digest(handle)
        _sha(expected_bracket_digest, "expected bracket")
        if not isinstance(transition, BracketTransition):
            raise CampaignMetricsError("malformed terminal transition")
        bracket_id, version, bracket = self._state(state_handle, digest)
        if bracket.bracket_digest != expected_bracket_digest:
            raise CampaignMetricsError("bracket compare-and-swap failed")
        unchanged = (
            transition.round_number == bracket.round_number
            and dict(transition.losses) == dict(bracket.losses)
            and dict(transition.byes) == dict(bracket.byes)
            and dict(transition.inconclusive) == dict(bracket.inconclusive)
            and transition.quarantined == bracket.quarantined
            and transition.applied_receipt_digests == bracket.applied_receipt_digests
        )
        if not unchanged or transition.terminal is None:
            raise CampaignMetricsError(
                "commit is terminal-only and must preserve counters and history"
            )
        auth = self._authorize(
            digest, "schedule", state_digest=bracket.admission_digest, allow_exhausted=True
        )
        if bracket.terminal is not None:
            if transition.terminal != bracket.terminal:
                raise CampaignMetricsError("a recorded terminal reason cannot be overwritten")
            self._ensure_live()
            return self._bracket_state(bracket_id, version)
        if transition.terminal == "lease_exhausted":
            if auth.exhausted is None:
                raise CampaignMetricsError("lease exhaustion is not confirmed")
        else:
            if auth.exhausted is not None:
                raise LeaseExhausted(f"lease {auth.exhausted}; only closure is permitted")
            terminal, _ = plan_next_round(
                auth.admission.protocol, bracket, self._snapshot(auth)
            )
            if terminal != transition.terminal:
                raise CampaignMetricsError(
                    "terminal reason is not justified by the canonical plan"
                )
        successor = BracketSnapshot(
            bracket.protocol_digest,
            bracket.admission_digest,
            bracket.stage,
            bracket.track,
            bracket.round_number,
            bracket.losses,
            bracket.byes,
            bracket.inconclusive,
            bracket.quarantined,
            transition.terminal,
            bracket.applied_receipt_digests,
        )
        request = commit_request_digest(bracket_id, expected_bracket_digest, transition)
        with self._transaction("commit_bracket"):
            now = self._recheck(auth, "schedule")
            current = self._conn.execute(
                "SELECT version, bracket_digest FROM bracket_current WHERE bracket_id = ?",
                (bracket_id,),
            ).fetchone()
            if current is None or tuple(current) != (version, bracket.bracket_digest):
                raise CampaignMetricsError("bracket compare-and-swap failed")
            seq = self._audit(
                "commit_bracket", bracket_id, now, request, successor.bracket_digest
            )
            self._install_version(bracket_id, version, bracket, successor, seq)
            self._record_result(
                seq, "commit_bracket", request, digest, "bracket",
                f"{bracket_id}:{version + 1}", successor.bracket_digest,
            )
        return self._bracket_state(bracket_id, version + 1)

    # -- host-only recovery (never an ordinary AdmissionRegistry method) -----------

    def state_identity(self, state_handle: object) -> tuple[str, int]:
        """Durable (bracket_id, version) of an owned wrapper, for request digests."""
        return self._interner.bracket_key(state_handle)

    def recover_bracket(
        self, handle: object, protocol_digest: str, stage: str, track: str
    ) -> BracketState:
        """After restart: an owned wrapper for the *current* bracket version."""
        digest = self._admission_digest(handle)
        adm = self._load_admission(digest)
        if protocol_digest != adm.protocol.protocol_digest or stage != adm.stage:
            raise CampaignMetricsError("foreign bracket recovery")
        self._authorize(
            digest,
            self._enrol_operation(adm.evidence, adm.lease, self._now()),
            allow_exhausted=True,
        )
        bracket_id = canonical_digest(
            {"admission_digest": digest, "stage": stage, "track": track}
        )
        version, _ = self._bracket_current(bracket_id)
        self._ensure_live()
        return self._bracket_state(bracket_id, version)

    def recover(self, handle: object, request_digest: str) -> RecoveredResult:
        """Authenticated lookup of the immutable result of one exact request digest.

        It never consumes, never issues a second token and never revives a superseded
        bracket version: such a result is reported with ``current=False``. The returned
        objects are linearized with poison/close like every other positive return.
        """
        recovered = self._recover(handle, request_digest)
        self._ensure_live()
        return recovered

    def _recover(self, handle: object, request_digest: str) -> RecoveredResult:
        digest = self._admission_digest(handle)
        _sha(request_digest, "request digest")
        row = self._one(
            "SELECT kind, admission_digest, result_kind, result_ref, result_digest"
            " FROM request_results WHERE request_digest = ?",
            (request_digest,),
        )
        if row is None or row[1] != digest:
            raise CampaignMetricsError("no recorded result for this admission")
        adm = self._load_admission(digest)
        recovery_auth = self._authorize(
            digest,
            self._enrol_operation(adm.evidence, adm.lease, self._now()),
            allow_exhausted=True,
        )
        kind, _, result_kind, ref, result_digest = row
        if recovery_auth.exhausted is not None and result_kind in {"receipts", "aggregate"}:
            # Confirmed revocation/expiry: the immutable record is reported, but no usable
            # positive object (receipts, aggregate receipt) is handed back. Bracket handles
            # are still returned so the bracket can be closed; they carry no permission.
            return RecoveredResult(request_digest, kind, result_digest, False)
        if result_kind == "bracket":
            bracket_id, _, version_text = ref.rpartition(":")
            current_version, snapshot = self._bracket_current(bracket_id)
            current = int(version_text) == current_version
            return RecoveredResult(
                request_digest,
                kind,
                result_digest,
                current,
                self._bracket_state(bracket_id, current_version) if current else None,
            )
        if result_kind == "receipts":
            return RecoveredResult(
                request_digest, kind, result_digest, True, receipts=self._receipts_for(int(ref))
            )
        if result_kind == "aggregate":
            return RecoveredResult(
                request_digest,
                kind,
                result_digest,
                True,
                aggregate=AggregateReceipt(
                    self._interner.wrapper(_AggregateHandle, (ref,)), ref
                ),
            )
        return RecoveredResult(request_digest, kind, result_digest, True)

    # -- AdmissionRegistry: seals -------------------------------------------------

    def append_seals(
        self,
        handle: object,
        expected_history_digest: str,
        expected_observed_at: int,
        seals: tuple[VariantSeal, ...],
    ) -> None:
        digest = self._admission_digest(handle)
        _sha(expected_history_digest, "expected seal history")
        _int(expected_observed_at, "expected_observed_at")
        rows = tuple(seals)
        if not rows or any(not isinstance(seal, VariantSeal) for seal in rows):
            raise CampaignMetricsError("no seals supplied")
        auth = self._authorize(digest, "seal")
        adm = auth.admission
        snapshot = self._snapshot(auth)
        history = snapshot.seal_history
        if canonical_digest(history) != expected_history_digest:
            raise CampaignMetricsError("seal compare-and-swap failed")
        if not max(seal.sealed_at for seal in rows) <= expected_observed_at <= auth.now:
            raise CampaignMetricsError("seal observation time is not the verified time")
        check_seal_append(adm.protocol, snapshot, rows)
        protocol_digest = adm.protocol.protocol_digest
        request = seal_request_digest(protocol_digest, expected_history_digest, rows)
        combined = canonical_digest(history + rows)
        with self._transaction("append_seals"):
            now = self._recheck(auth, "seal")
            if canonical_digest(self._seal_history(protocol_digest)) != expected_history_digest:
                raise CampaignMetricsError("seal compare-and-swap failed")
            seq = self._audit("append_seals", protocol_digest, now, request, combined)
            for seal in rows:
                if seal.sealed_at > now:
                    raise CampaignMetricsError("seal is later than trusted time")
                self._conn.execute(
                    "INSERT INTO seals VALUES (?,?,?,?,?,?)",
                    (
                        protocol_digest,
                        seal.sequence,
                        seal.seal_digest,
                        _bytes(seal),
                        seal.sealed_at,
                        seq,
                    ),
                )
            self._record_result(
                seq, "append_seals", request, digest, "seals", protocol_digest, combined
            )

    # -- measurements and aggregates ----------------------------------------------

    def _load_aggregate(self, aggregate_digest: str) -> AggregateEvidence:
        row = self._one(
            "SELECT canonical FROM aggregates WHERE aggregate_digest = ?",
            (aggregate_digest,),
        )
        if row is None:
            raise CampaignMetricsError("foreign aggregate")
        evidence = decode_aggregate(_load(bytes(row[0])))
        if canonical_digest(evidence) != aggregate_digest or _bytes(evidence) != bytes(row[0]):
            raise N30StoreError("stored aggregate bytes changed")
        return evidence

    def _binding_for(
        self, auth: _Auth, evidence: AggregateEvidence, row: FamilyObservation
    ) -> MeasurementBinding:
        manifest = self._adapter_manifest
        if manifest is None:
            raise AuthorityBlocked(
                "no admitted adapter manifest is configured; measurement authentication"
                " is unsupported"
            )
        adm = auth.admission
        snapshot = self._snapshot(auth)
        try:
            manifest.validate_for(adm.protocol, adm.evidence)
            task = next(
                item
                for item in adm.evidence.tasks
                if item.task_id == row.task_id and item.family_id == row.family_id
            )
            invocations = tuple(
                build_admitted_invocation(
                    adm.protocol,
                    manifest,
                    snapshot,
                    stage=adm.stage,
                    variant_id=variant,
                    task_id=row.task_id,
                    repetition=row.repetition,
                )
                for variant in (evidence.left, evidence.right)
            )
        except (BenchmarkAdapterError, StopIteration, IndexError) as error:
            raise CampaignMetricsError(f"measurement lane is not admitted: {error}") from error
        return MeasurementBinding(
            adm.admission_digest,
            adm.protocol.protocol_digest,
            adm.stage,
            evidence.track,
            evidence.regime_id,
            adm.evidence.block_id,
            adm.evidence.block_digest,
            adm.evidence.task_manifest_digest,
            adm.evidence.family_manifest_digest,
            row.task_id,
            row.family_id,
            row.repetition,
            task.repetition_seeds[row.repetition],
            VariantExpectation(evidence.left, invocations[0]),
            VariantExpectation(evidence.right, invocations[1]),
        )

    def _bind_measurement(
        self,
        auth: _Auth,
        evidence: AggregateEvidence,
        row: FamilyObservation,
        binding: MeasurementBinding,
        measured: object,
        mapping: ReviewedMapping,
        now: int,
    ) -> StatusObservation:
        """Bind one answer; ``now`` is the trusted UTC sampled after the provider returned."""
        if not isinstance(measured, AuthenticatedMeasurement):
            raise CampaignMetricsError("measurement port returned no typed evidence")
        adm = auth.admission
        if (
            measured.evidence_digest != row.receipt_digest
            or measured.binding_digest != binding.digest
            or len(measured.executions) != 2
        ):
            raise CampaignMetricsError("measurement does not bind the exact expected lane")
        for execution, expected in zip(
            measured.executions, (binding.left, binding.right)
        ):
            if (
                not isinstance(execution, MeasuredExecution)
                or not isinstance(execution.response, BenchmarkResponse)
                or execution.invocation != expected.invocation
                or execution.invocation.execution_binding_digest
                != expected.invocation.execution_binding_digest
                or execution.response.operation_id != expected.invocation.request.operation_id
                or execution.raw_result_digest != execution.response.result_digest
            ):
                raise CampaignMetricsError("execution ancestry differs from the admitted lane")
        if (
            measured.executions[0].invocation.request.operation_id
            == measured.executions[1].invocation.request.operation_id
        ):
            raise CampaignMetricsError("left and right executions must be distinct")
        if (
            dict(measured.definitions) != dict(self._policy.metric_definitions)
            or measured.gate_definition != self._policy.gate_definition
        ):
            raise CampaignMetricsError("units/denominators/gate definitions are not reviewed")
        values = dict(measured.values)
        if set(values) != set(METRICS) or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values.values()
        ):
            raise CampaignMetricsError("measurement values must cover every reviewed metric")
        if values[evidence.metric] != row.value:
            raise CampaignMetricsError("caller value differs from the authenticated value")
        if (
            type(measured.left_hard_gates) is not bool
            or type(measured.right_hard_gates) is not bool
        ):
            raise CampaignMetricsError("hard gates must be authenticated booleans")
        floor = max(adm.lease.issued_at, adm.evidence.stage_opened_at)
        if adm.evidence.holdout_opened_at is not None:
            floor = max(floor, adm.evidence.holdout_opened_at)
        if not (
            type(measured.observed_at) is int
            and type(measured.signed_at) is int
            and floor <= measured.observed_at <= measured.signed_at <= now
            and measured.signed_at < adm.lease.expires_at
        ):
            raise AuthorityBlocked("measurement lies outside its reviewed execution window")
        status = self._check_status(measured.status, mapping, now)
        self._independent_authority(adm.evidence, status)
        return status

    def _authenticate_rows(
        self, auth: _Auth, evidence: AggregateEvidence, rows: tuple[FamilyObservation, ...]
    ) -> list["_Measured"]:
        if len(rows) > MAX_MEASUREMENT_ROWS:
            raise CampaignMetricsError("aggregate exceeds the bounded measurement count")
        found: list[_Measured] = []
        operations: set[str] = set()
        for row in rows:
            binding = self._binding_for(auth, evidence, row)
            measured, mapping, returned_at = self._call(
                "n30.measurement", "measurement", row.receipt_digest, binding
            )
            status = self._bind_measurement(
                auth, evidence, row, binding, measured, mapping, returned_at
            )
            ids = {
                execution.invocation.request.operation_id
                for execution in measured.executions
            }
            if ids & operations:
                raise CampaignMetricsError("execution ancestry is reused within an aggregate")
            operations |= ids
            found.append(_Measured(row, measured, status, mapping, binding))
        left = all(item.measurement.left_hard_gates for item in found)
        right = all(item.measurement.right_hard_gates for item in found)
        if (left, right) != (evidence.left_hard_gates, evidence.right_hard_gates):
            raise CampaignMetricsError("hard gates differ from the authenticated results")
        return found

    @staticmethod
    def _measurement_document(item: "_Measured") -> Mapping[str, object]:
        measured = item.measurement
        return {
            "evidence_digest": measured.evidence_digest,
            "binding_digest": item.binding.digest,
            "binding": item.binding.to_document(),
            "executions": [
                {
                    "invocation": invocation_document(execution.invocation),
                    "response": response_document(execution.response),
                    "raw_result_digest": execution.raw_result_digest,
                }
                for execution in measured.executions
            ],
            "values": dict(measured.values),
            "definitions": _measurement_definitions_document(measured.definitions),
            "gate_definition": measured.gate_definition,
            "left_hard_gates": measured.left_hard_gates,
            "right_hard_gates": measured.right_hard_gates,
            "observed_at": measured.observed_at,
            "signed_at": measured.signed_at,
        }

    def record_aggregate(
        self,
        handle: object,
        evidence: AggregateEvidence,
        observations: tuple[FamilyObservation, ...],
    ) -> AggregateReceipt:
        digest = self._admission_digest(handle)
        rows = tuple(observations)
        if not isinstance(evidence, AggregateEvidence) or any(
            not isinstance(row, FamilyObservation) for row in rows
        ):
            raise CampaignMetricsError("malformed aggregate request")
        auth = self._authorize(digest, "aggregate")
        adm = auth.admission
        recomputed = build_aggregate_evidence(
            adm.protocol,
            self._snapshot(auth),
            evidence.metric,
            evidence.left,
            evidence.right,
            rows,
            left_hard_gates=evidence.left_hard_gates,
            right_hard_gates=evidence.right_hard_gates,
        )
        if recomputed != evidence or canonical_digest(recomputed) != canonical_digest(evidence):
            raise CampaignMetricsError("aggregate differs from the recomputed evidence")
        measured = self._authenticate_rows(auth, evidence, rows)
        # Final authority read after the last measurement dependency; a revoked, expired,
        # unknown, stale or regressed answer blocks persistence of the aggregate.
        auth = self._final_read(auth, "aggregate")
        aggregate_digest = canonical_digest(evidence)
        request = aggregate_request_digest(evidence, rows)
        data = _bytes(evidence)
        with self._transaction("record_aggregate"):
            now = self._recheck(auth, "aggregate")
            for item in measured:
                if now >= item.status.observed_at + item.status.max_age:
                    raise AuthorityBlocked("measurement status went stale before commit")
            seq = self._audit("record_aggregate", aggregate_digest, now, request, aggregate_digest)
            observation_ids = {}
            for item in measured:
                observation_ids[item.row.receipt_digest] = self._record_status(
                    f"measurement:{item.row.receipt_digest}", item.status, item.mapping, now
                )
                document = _bytes(self._measurement_document(item))
                stored = self._conn.execute(
                    "SELECT binding_digest, canonical FROM measurements"
                    " WHERE measurement_digest = ?",
                    (item.row.receipt_digest,),
                ).fetchone()
                if stored is None:
                    self._conn.execute(
                        "INSERT INTO measurements VALUES (?,?,?,?,?,?)",
                        (
                            item.row.receipt_digest,
                            item.binding.digest,
                            digest,
                            document,
                            observation_ids[item.row.receipt_digest],
                            seq,
                        ),
                    )
                elif stored[0] != item.binding.digest or bytes(stored[1]) != document:
                    raise N30StoreError("measurement identity is stored with other content")
            stored_aggregate = self._conn.execute(
                "SELECT canonical FROM aggregates WHERE aggregate_digest = ?",
                (aggregate_digest,),
            ).fetchone()
            if stored_aggregate is None:
                self._conn.execute(
                    "INSERT INTO aggregates VALUES (?,?,?,?,?)",
                    (aggregate_digest, digest, evidence.metric, data, seq),
                )
                for position, item in enumerate(measured):
                    self._conn.execute(
                        "INSERT INTO aggregate_uses VALUES (?,?,?,?,?,?,?)",
                        (
                            aggregate_digest,
                            item.row.receipt_digest,
                            item.row.family_id,
                            item.row.task_id,
                            item.row.repetition,
                            json.dumps(item.row.value),
                            position,
                        ),
                    )
            elif bytes(stored_aggregate[0]) != data:
                raise N30StoreError("aggregate identity is stored with other content")
            self._record_result(
                seq, "record_aggregate", request, digest, "aggregate",
                aggregate_digest, aggregate_digest,
            )
        return AggregateReceipt(
            self._interner.wrapper(_AggregateHandle, (aggregate_digest,)), aggregate_digest
        )

    def resolve_aggregate(
        self, handle: object, receipt: AggregateReceipt
    ) -> AggregateEvidence:
        digest = self._admission_digest(handle)
        if not isinstance(receipt, AggregateReceipt):
            raise CampaignMetricsError("aggregate receipt required")
        aggregate_digest = self._interner.text_key(receipt.opaque_handle, _AggregateHandle)
        if receipt.aggregate_digest != aggregate_digest:
            raise CampaignMetricsError("aggregate receipt substituted")
        owner = self._one(
            "SELECT admission_digest FROM aggregates WHERE aggregate_digest = ?",
            (aggregate_digest,),
        )
        if owner is None or owner[0] != digest:
            raise CampaignMetricsError("foreign aggregate")
        evidence = self._load_aggregate(aggregate_digest)
        auth = self._authorize(digest, "decide")
        adm = auth.admission
        if (
            evidence.admission_digest != digest
            or evidence.protocol_digest != adm.protocol.protocol_digest
            or evidence.stage != adm.stage
            or evidence.block_digest != adm.evidence.block_digest
            or evidence.task_manifest_digest != adm.evidence.task_manifest_digest
            or evidence.family_manifest_digest != adm.evidence.family_manifest_digest
            or evidence.observation_shape != observation_shape_for(adm.evidence)
        ):
            raise CampaignMetricsError("aggregate context changed since it was recorded")
        rows = tuple(
            FamilyObservation(family, task, repetition, measurement, json.loads(value))
            for measurement, family, task, repetition, value in self._query(
                "SELECT measurement_digest, family_id, task_id, repetition, value_json"
                " FROM aggregate_uses WHERE aggregate_digest = ? ORDER BY position",
                (aggregate_digest,),
            )
        )
        if canonical_digest(rows) != evidence.observation_digest:
            raise N30StoreError("stored aggregate observations changed")
        measured = self._authenticate_rows(auth, evidence, rows)
        for item in measured:
            stored = self._one(
                "SELECT binding_digest FROM measurements WHERE measurement_digest = ?",
                (item.row.receipt_digest,),
            )
            if stored is None or stored[0] != item.binding.digest:
                raise CampaignMetricsError("aggregate reference no longer matches its evidence")
        # Final authority read after the last re-authentication; positive evidence is never
        # returned on a revoked/expired/unknown/stale/regressed answer.
        auth = self._final_read(auth, "decide")
        with self._transaction("observe:aggregate"):
            now = self._recheck(auth, "decide")
            for item in measured:
                if now >= item.status.observed_at + item.status.max_age:
                    raise AuthorityBlocked("measurement status went stale")
                self._record_status(
                    f"measurement:{item.row.receipt_digest}", item.status, item.mapping, now
                )
            self._audit("resolve_aggregate", aggregate_digest, now, None, aggregate_digest)
        return evidence


@dataclass(frozen=True, slots=True)
class _Measured:
    row: FamilyObservation
    measurement: AuthenticatedMeasurement
    status: StatusObservation
    mapping: ReviewedMapping
    binding: MeasurementBinding


# --------------------------------------------------------------------------------------
# Exact request digests. A host that lost an acknowledgment recomputes the digest of the
# request it sent and calls ``N30HostRegistry.recover``; nothing here grants authority.
# --------------------------------------------------------------------------------------


def issue_request_digest(plans: Sequence[RoundPlanEntry]) -> str:
    first = plans[0]
    return canonical_digest(
        {
            "op": "issue_round",
            "bracket_digest": first.bracket_digest,
            "round": first.round_number,
            "plans": canonical_digest([plan.plan_digest for plan in plans]),
        }
    )


def consume_request_digest(bracket_id: str, request: ConsumeRoundRequest) -> str:
    return canonical_digest(
        {
            "op": "consume_round",
            "bracket_id": bracket_id,
            "expected": request.expected_bracket_digest,
            "admission": request.admission_digest,
            "round": request.round_number,
            "results": sorted(
                [result.receipt.receipt_digest, result.outcome] for result in request.results
            ),
            "transition": request.transition,
        }
    )


def commit_request_digest(
    bracket_id: str, expected_bracket_digest: str, transition: BracketTransition
) -> str:
    return canonical_digest(
        {
            "op": "commit_bracket",
            "bracket_id": bracket_id,
            "expected": expected_bracket_digest,
            "transition": transition,
        }
    )


def seal_request_digest(
    protocol_digest: str, expected_history_digest: str, seals: Sequence[VariantSeal]
) -> str:
    return canonical_digest(
        {
            "op": "append_seals",
            "protocol_digest": protocol_digest,
            "expected_history": expected_history_digest,
            "seals": [seal.seal_digest for seal in seals],
        }
    )


def aggregate_request_digest(
    evidence: AggregateEvidence, observations: Sequence[FamilyObservation]
) -> str:
    return canonical_digest(
        {
            "op": "record_aggregate",
            "aggregate": canonical_digest(evidence),
            "observations": list(observations),
        }
    )


def open_bracket_request_digest(admission_digest: str, stage: str, track: str) -> str:
    return canonical_digest(
        {
            "op": "open_bracket",
            "bracket_id": canonical_digest(
                {"admission_digest": admission_digest, "stage": stage, "track": track}
            ),
        }
    )


__all__ = [
    "APPLICATION_ID",
    "AuthenticatedMeasurement",
    "AuthenticatedOutcome",
    "AuthorityBlocked",
    "CloseReport",
    "CurrentAdmissionEvidence",
    "CurrentAuthorityPort",
    "HostPolicy",
    "HostPorts",
    "MeasuredExecution",
    "MeasurementBinding",
    "MeasurementPort",
    "MetricDefinition",
    "N30HostError",
    "N30HostRegistry",
    "N30StoreError",
    "OutcomePort",
    "PortLimits",
    "RecoveredResult",
    "ReviewedMapping",
    "SCHEMA_VERSION",
    "StatusObservation",
    "VariantExpectation",
    "aggregate_request_digest",
    "commit_request_digest",
    "consume_request_digest",
    "issue_request_digest",
    "open_bracket_request_digest",
    "seal_request_digest",
]
