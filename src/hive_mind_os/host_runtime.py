"""Durable, bounded supervision over the subject-neutral host adapter."""

from __future__ import annotations

import math
import queue
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator, Mapping, Protocol, TypeVar

from .activation_bundle import (
    ActivationBundleError,
    AuthorizedOneRun,
    validate_authorized_one_run,
)
from .dag_standard import compile_plan, load_bound_plan
from .host_adapter import (
    HOST_DEADLINE_CAPABILITY,
    HostAdapter,
    HostExecutionReceipt,
    HostIdentity,
    HostLease,
    HostObservation,
    HostReceiptState,
    canonical_checkpoint_digest,
)
from .portable_plan import (
    validate_activation_plan_binding,
    validate_runtime_plan_admission,
)
from .runtime_contracts import (
    ContractViolation,
    canonical_digest,
    canonical_json_bytes,
    raw_sha256,
    require_digest,
    require_identifier,
    require_time,
    strict_json_object,
)

# This process-local object is an encapsulation boundary, not a cryptographic
# secret.  It prevents callers of the public journal API from manufacturing
# runtime provenance.  Durable restart trust comes from custody of the journal
# store and its verified append-only history; hostile code in this interpreter
# or hostile storage are explicitly outside that trust claim.
_RUNTIME_JOURNAL_AUTHORITY = object()


class HostRuntimeError(RuntimeError):
    """A host operation is invalid, over budget, or contradicts durable state."""


class HostRecoveryRequired(HostRuntimeError):
    """A host effect may have happened and must be observed or explicitly adopted."""


class HostOperationState(StrEnum):
    INTENT_RECORDED = "INTENT_RECORDED"
    SUCCEEDED = "SUCCEEDED"
    DENIED = "DENIED"
    RECOVERABLE = "RECOVERABLE"


@dataclass(frozen=True, slots=True)
class HostUsage:
    """Honest operation accounting; unavailable model usage remains ``None``."""

    wall_milliseconds: int
    input_bytes: int
    output_bytes: int
    model_input_tokens: int | None = None
    model_output_tokens: int | None = None

    def __post_init__(self) -> None:
        for label in ("wall_milliseconds", "input_bytes", "output_bytes"):
            value = getattr(self, label)
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be non-negative")
        for label in ("model_input_tokens", "model_output_tokens"):
            value = getattr(self, label)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{label} must be non-negative or unavailable")

    def to_document(self) -> dict[str, Any]:
        return {
            "wall_milliseconds": self.wall_milliseconds,
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "model_input_tokens": self.model_input_tokens,
            "model_output_tokens": self.model_output_tokens,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> HostUsage:
        if set(value) != {
            "wall_milliseconds",
            "input_bytes",
            "output_bytes",
            "model_input_tokens",
            "model_output_tokens",
        }:
            raise HostRuntimeError("host usage has an unknown shape")
        try:
            return cls(**value)
        except (TypeError, ValueError) as error:
            raise HostRuntimeError("host usage is invalid") from error


@dataclass(frozen=True, slots=True)
class HostCheckpoint:
    lease_id: str
    node_id: str
    input_digest: str
    checkpoint_digest: str
    candidate_digest: str | None

    def __post_init__(self) -> None:
        require_identifier(self.lease_id, "checkpoint lease_id")
        require_identifier(self.node_id, "checkpoint node_id")
        require_digest(self.input_digest, "checkpoint input_digest")
        require_digest(self.checkpoint_digest, "checkpoint_digest")
        if self.candidate_digest is not None:
            require_digest(self.candidate_digest, "candidate_digest")

    def to_document(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "node_id": self.node_id,
            "input_digest": self.input_digest,
            "checkpoint_digest": self.checkpoint_digest,
            "candidate_digest": self.candidate_digest,
        }


@dataclass(frozen=True, slots=True)
class HostOperationRecord:
    idempotency_key: str
    action: str
    request_digest: str
    state: HostOperationState
    sequence: int
    response_type: str | None
    response: Mapping[str, Any] | None
    usage: HostUsage | None
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        require_identifier(self.action, "host action")
        require_digest(self.request_digest, "host request_digest")
        if not isinstance(self.state, HostOperationState):
            raise ValueError("host operation state must be typed")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("host operation sequence must be positive")
        if self.state is HostOperationState.INTENT_RECORDED:
            if any(value is not None for value in (self.response_type, self.response, self.usage, self.reason)):
                raise ValueError("host intent cannot claim an outcome")
        elif self.state is HostOperationState.SUCCEEDED:
            if self.response_type is None or self.response is None or self.usage is None:
                raise ValueError("successful host operation requires response and usage")
        elif self.reason is None or self.usage is None:
            raise ValueError("non-success host outcome requires reason and usage")

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "idempotency_key": self.idempotency_key,
            "action": self.action,
            "request_digest": self.request_digest,
            "state": self.state.value,
            "sequence": self.sequence,
            "response_type": self.response_type,
            "response": None if self.response is None else dict(self.response),
            "usage": None if self.usage is None else self.usage.to_document(),
            "reason": self.reason,
        }


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _closed(value: Mapping[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise HostRuntimeError(f"{label} has an unknown shape")


def _identity_from_document(value: Mapping[str, Any]) -> HostIdentity:
    _closed(
        value,
        {
            "host_id",
            "platform",
            "architecture",
            "runtime_version",
            "executable_digest",
            "adapter_digest",
        },
        "host identity",
    )
    return HostIdentity(
        host_id=value["host_id"],
        platform=value["platform"],
        architecture=value["architecture"],
        runtime_version=value["runtime_version"],
        executable_digest=value["executable_digest"],
        adapter_digest=value["adapter_digest"],
    )


def _observation_from_document(value: Mapping[str, Any]) -> HostObservation:
    _closed(
        value,
        {
            "identity",
            "subject_id",
            "observed_at",
            "capabilities",
            "trust_evidence_digest",
            "clean",
        },
        "host observation",
    )
    identity = value.get("identity")
    capabilities = value.get("capabilities")
    if not isinstance(identity, Mapping) or not isinstance(capabilities, list):
        raise HostRuntimeError("durable host observation is malformed")
    return HostObservation(
        identity=_identity_from_document(identity),
        subject_id=value["subject_id"],
        observed_at=value["observed_at"],
        capabilities=tuple(capabilities),
        trust_evidence_digest=value["trust_evidence_digest"],
        clean=value["clean"],
    )


def _lease_from_document(value: Mapping[str, Any]) -> HostLease:
    _closed(
        value,
        {
            "lease_id",
            "host_id",
            "subject_id",
            "generation_id",
            "authority_digest",
            "adapter_inventory_digest",
            "external_effects_required",
            "compilation_digest",
            "activation_digest",
            "activation_proof_digest",
            "candidate_commit",
            "candidate_tree",
            "candidate_content_sha256",
            "candidate_parent_commit",
            "candidate_parent_tree",
            "manifest_sha256",
            "repository_id",
            "request_sha256",
            "target_branch",
            "execution_client_sha256",
            "activation_issued_at",
            "protected_merge_authorized",
            "host_identity_digest",
            "trust_evidence_digest",
            "required_capabilities",
            "issued_at",
            "expires_at",
            "allowed_node_ids",
            "nonce_digest",
        },
        "host lease",
    )
    nodes = value.get("allowed_node_ids")
    capabilities = value.get("required_capabilities")
    if not isinstance(nodes, list) or not isinstance(capabilities, list):
        raise HostRuntimeError("durable host lease is malformed")
    return HostLease(
        lease_id=value["lease_id"],
        host_id=value["host_id"],
        subject_id=value["subject_id"],
        generation_id=value["generation_id"],
        authority_digest=value["authority_digest"],
        adapter_inventory_digest=value["adapter_inventory_digest"],
        external_effects_required=value["external_effects_required"],
        compilation_digest=value["compilation_digest"],
        activation_digest=value["activation_digest"],
        activation_proof_digest=value["activation_proof_digest"],
        candidate_commit=value["candidate_commit"],
        candidate_tree=value["candidate_tree"],
        candidate_content_sha256=value["candidate_content_sha256"],
        candidate_parent_commit=value["candidate_parent_commit"],
        candidate_parent_tree=value["candidate_parent_tree"],
        manifest_sha256=value["manifest_sha256"],
        repository_id=value["repository_id"],
        request_sha256=value["request_sha256"],
        target_branch=value["target_branch"],
        execution_client_sha256=value["execution_client_sha256"],
        activation_issued_at=value["activation_issued_at"],
        protected_merge_authorized=value["protected_merge_authorized"],
        host_identity_digest=value["host_identity_digest"],
        trust_evidence_digest=value["trust_evidence_digest"],
        required_capabilities=tuple(capabilities),
        issued_at=value["issued_at"],
        expires_at=value["expires_at"],
        allowed_node_ids=tuple(nodes),
        nonce_digest=value["nonce_digest"],
    )


def _receipt_from_document(value: Mapping[str, Any]) -> HostExecutionReceipt:
    _closed(
        value,
        {
            "receipt_id",
            "lease_id",
            "node_id",
            "state",
            "input_digest",
            "output_digest",
            "evidence_digest",
            "observed_at",
        },
        "host execution receipt",
    )
    return HostExecutionReceipt(
        receipt_id=value["receipt_id"],
        lease_id=value["lease_id"],
        node_id=value["node_id"],
        state=HostReceiptState(value["state"]),
        input_digest=value["input_digest"],
        output_digest=value["output_digest"],
        evidence_digest=value["evidence_digest"],
        observed_at=value["observed_at"],
    )


def _checkpoint_from_document(value: Mapping[str, Any]) -> HostCheckpoint:
    _closed(
        value,
        {
            "lease_id",
            "node_id",
            "input_digest",
            "checkpoint_digest",
            "candidate_digest",
        },
        "host checkpoint",
    )
    return HostCheckpoint(
        lease_id=value["lease_id"],
        node_id=value["node_id"],
        input_digest=value["input_digest"],
        checkpoint_digest=value["checkpoint_digest"],
        candidate_digest=value["candidate_digest"],
    )


def _create_scope(authorization: AuthorizedOneRun) -> str:
    return authorization.activation_digest


def _message_scope(lease: HostLease, node_id: str) -> str:
    return canonical_digest(
        {
            "lease_digest": canonical_digest(lease.to_document()),
            "node_id": node_id,
        }
    )


def _checkpoint_scope(lease: HostLease, receipt: HostExecutionReceipt) -> str:
    return canonical_digest(
        {
            "lease_digest": canonical_digest(lease.to_document()),
            "node_id": receipt.node_id,
            "input_digest": receipt.input_digest,
        }
    )


def _cancel_scope(lease: HostLease) -> str:
    return canonical_digest(lease.to_document())


class HostOperationJournal:
    """Append-only pre-effect intents and post-effect observations."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        try:
            with self.connection:
                self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS host_operation_events (
                    global_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT NOT NULL,
                    operation_sequence INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_digest TEXT,
                    event_digest TEXT NOT NULL UNIQUE,
                    UNIQUE(idempotency_key, operation_sequence)
                );
                CREATE TRIGGER IF NOT EXISTS host_operation_events_no_update
                BEFORE UPDATE ON host_operation_events
                BEGIN SELECT RAISE(ABORT, 'host operation history is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_operation_events_no_delete
                BEFORE DELETE ON host_operation_events
                BEGIN SELECT RAISE(ABORT, 'host operation history is append-only'); END;
                CREATE TABLE IF NOT EXISTS host_semantic_operation_claims (
                    claim_kind TEXT NOT NULL,
                    scope_digest TEXT NOT NULL,
                    action TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    canonical_idempotency_key TEXT NOT NULL UNIQUE,
                    PRIMARY KEY(claim_kind, scope_digest)
                );
                CREATE TRIGGER IF NOT EXISTS host_semantic_operation_claims_no_update
                BEFORE UPDATE ON host_semantic_operation_claims
                BEGIN SELECT RAISE(ABORT, 'host semantic operation claims are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_semantic_operation_claims_no_delete
                BEFORE DELETE ON host_semantic_operation_claims
                BEGIN SELECT RAISE(ABORT, 'host semantic operation claims are append-only'); END;
                CREATE TABLE IF NOT EXISTS host_operation_aliases (
                    idempotency_key TEXT PRIMARY KEY,
                    canonical_idempotency_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    request_digest TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS host_operation_aliases_no_update
                BEFORE UPDATE ON host_operation_aliases
                BEGIN SELECT RAISE(ABORT, 'host operation aliases are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_operation_aliases_no_delete
                BEFORE DELETE ON host_operation_aliases
                BEGIN SELECT RAISE(ABORT, 'host operation aliases are append-only'); END;
                CREATE TABLE IF NOT EXISTS host_adoption_claims (
                    canonical_idempotency_key TEXT PRIMARY KEY,
                    response_type TEXT NOT NULL,
                    response_digest TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS host_adoption_claims_no_update
                BEFORE UPDATE ON host_adoption_claims
                BEGIN SELECT RAISE(ABORT, 'host adoption claims are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_adoption_claims_no_delete
                BEFORE DELETE ON host_adoption_claims
                BEGIN SELECT RAISE(ABORT, 'host adoption claims are append-only'); END;
                CREATE TABLE IF NOT EXISTS host_activation_claims (
                    activation_digest TEXT PRIMARY KEY,
                    proof_digest TEXT NOT NULL,
                    nonce_digest TEXT NOT NULL UNIQUE,
                    create_idempotency_key TEXT NOT NULL UNIQUE,
                    create_request_digest TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    host_identity_digest TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS host_activation_claims_no_update
                BEFORE UPDATE ON host_activation_claims
                BEGIN SELECT RAISE(ABORT, 'host activation claims are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_activation_claims_no_delete
                BEFORE DELETE ON host_activation_claims
                BEGIN SELECT RAISE(ABORT, 'host activation claims are append-only'); END;
                CREATE TABLE IF NOT EXISTS host_lease_cancel_claims (
                    lease_digest TEXT PRIMARY KEY,
                    activation_digest TEXT NOT NULL,
                    activation_proof_digest TEXT NOT NULL,
                    nonce_digest TEXT NOT NULL,
                    cancel_idempotency_key TEXT NOT NULL UNIQUE,
                    cancel_request_digest TEXT NOT NULL,
                    cancel_reason TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS host_lease_cancel_claims_no_update
                BEFORE UPDATE ON host_lease_cancel_claims
                BEGIN SELECT RAISE(ABORT, 'host lease cancellation claims are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_lease_cancel_claims_no_delete
                BEFORE DELETE ON host_lease_cancel_claims
                BEGIN SELECT RAISE(ABORT, 'host lease cancellation claims are append-only'); END;
                CREATE TABLE IF NOT EXISTS host_lease_cancel_commits (
                    lease_digest TEXT PRIMARY KEY,
                    cancel_idempotency_key TEXT NOT NULL UNIQUE,
                    receipt_digest TEXT NOT NULL,
                    committed_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS host_lease_cancel_commits_no_update
                BEFORE UPDATE ON host_lease_cancel_commits
                BEGIN SELECT RAISE(ABORT, 'host lease cancellation commits are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_lease_cancel_commits_no_delete
                BEFORE DELETE ON host_lease_cancel_commits
                BEGIN SELECT RAISE(ABORT, 'host lease cancellation commits are append-only'); END;
                CREATE TABLE IF NOT EXISTS host_lease_completion_claims (
                    lease_digest TEXT PRIMARY KEY,
                    activation_digest TEXT NOT NULL,
                    activation_proof_digest TEXT NOT NULL,
                    nonce_digest TEXT NOT NULL,
                    claimed_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS host_lease_completion_claims_no_update
                BEFORE UPDATE ON host_lease_completion_claims
                BEGIN SELECT RAISE(ABORT, 'host lease completion claims are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS host_lease_completion_claims_no_delete
                BEFORE DELETE ON host_lease_completion_claims
                BEGIN SELECT RAISE(ABORT, 'host lease completion claims are append-only'); END;
                """
                )
            cancel_columns = {
                str(row["name"])
                for row in self.connection.execute(
                    "PRAGMA table_info(host_lease_cancel_claims)"
                )
            }
            if "cancel_reason" not in cancel_columns:
                # Pre-activation journals cannot synthesize a missing reason.
                # The nullable migration preserves the store for inspection;
                # verification below fails closed if an old claim exists.
                self.connection.execute(
                    "ALTER TABLE host_lease_cancel_claims "
                    "ADD COLUMN cancel_reason TEXT"
                )
                self.connection.commit()
            self.verify()
        except BaseException:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> HostOperationJournal:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> HostOperationRecord:
        try:
            value = strict_json_object(str(row["payload_json"]).encode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise HostRuntimeError("host operation journal contains invalid JSON") from error
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version",
            "idempotency_key",
            "action",
            "request_digest",
            "state",
            "sequence",
            "response_type",
            "response",
            "usage",
            "reason",
        } or type(value.get("schema_version")) is not int or value.get(
            "schema_version"
        ) != 1:
            raise HostRuntimeError("host operation event has an unknown shape")
        usage_value = value["usage"]
        response = value["response"]
        if usage_value is not None and not isinstance(usage_value, Mapping):
            raise HostRuntimeError("host usage is malformed")
        if response is not None and not isinstance(response, Mapping):
            raise HostRuntimeError("host response is malformed")
        try:
            record = HostOperationRecord(
                idempotency_key=value["idempotency_key"],
                action=value["action"],
                request_digest=value["request_digest"],
                state=HostOperationState(value["state"]),
                sequence=value["sequence"],
                response_type=value["response_type"],
                response=None if response is None else dict(response),
                usage=None if usage_value is None else HostUsage.from_document(usage_value),
                reason=value["reason"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise HostRuntimeError("host operation event is invalid") from error
        if (
            record.idempotency_key != row["idempotency_key"]
            or record.sequence != row["operation_sequence"]
            or record.action != row["action"]
            or record.request_digest != row["request_digest"]
        ):
            raise HostRuntimeError("host operation index disagrees with payload")
        return record

    def _rows(self, key: str | None = None) -> tuple[sqlite3.Row, ...]:
        query = "SELECT * FROM host_operation_events"
        values: tuple[object, ...] = ()
        if key is not None:
            query += " WHERE idempotency_key=?"
            values = (key,)
        query += " ORDER BY global_sequence"
        return tuple(self.connection.execute(query, values))

    @contextmanager
    def _read_snapshot(self) -> Iterator[None]:
        """Hold one SQLite snapshot across a compound journal read."""

        owns_transaction = not self.connection.in_transaction
        if owns_transaction:
            self.connection.execute("BEGIN")
        try:
            yield
            if owns_transaction:
                self.connection.commit()
        except BaseException:
            if owns_transaction:
                self.connection.rollback()
            raise

    def verify(self) -> None:
        """Verify every related table against one consistent DB snapshot."""

        with self._lock, self._read_snapshot():
            self._verify_snapshot()

    def _verify_snapshot(self) -> None:
        previous: dict[str, str | None] = {}
        sequences: dict[str, int] = {}
        identities: dict[str, tuple[str, str]] = {}
        states: dict[str, HostOperationState] = {}
        for row in self._rows():
            record = self._decode(row)
            identity = identities.setdefault(
                record.idempotency_key, (record.action, record.request_digest)
            )
            if identity != (record.action, record.request_digest):
                raise HostRuntimeError("host operation intent changed after recording")
            expected = sequences.get(record.idempotency_key, 1)
            if record.sequence != expected:
                raise HostRuntimeError("host operation sequence is discontinuous")
            prior = previous.get(record.idempotency_key)
            if row["previous_digest"] != prior:
                raise HostRuntimeError("host operation hash chain is broken")
            if row["payload_json"] != canonical_json_bytes(record.to_document()).decode():
                raise HostRuntimeError("host operation payload is not canonical")
            event_digest = canonical_digest(
                {"previous_digest": prior, "record": record.to_document()}
            )
            if row["event_digest"] != event_digest:
                raise HostRuntimeError("host operation event digest is invalid")
            prior_state = states.get(record.idempotency_key)
            if prior_state is None:
                if record.state is not HostOperationState.INTENT_RECORDED:
                    raise HostRuntimeError("host operation history must begin with an intent")
            elif prior_state is HostOperationState.INTENT_RECORDED:
                if record.state is HostOperationState.INTENT_RECORDED:
                    raise HostRuntimeError("host operation history repeats its intent")
            elif prior_state is HostOperationState.RECOVERABLE:
                if record.state is not HostOperationState.SUCCEEDED:
                    raise HostRuntimeError("host recovery must end in explicit adoption")
            elif prior_state is HostOperationState.DENIED:
                raise HostRuntimeError("denied host operation has later events")
            else:
                raise HostRuntimeError("successful host operation has later events")
            previous[record.idempotency_key] = event_digest
            sequences[record.idempotency_key] = expected + 1
            states[record.idempotency_key] = record.state
        try:
            event_keys = set(identities)
            aliases = tuple(
                self.connection.execute(
                    "SELECT * FROM host_operation_aliases ORDER BY idempotency_key"
                )
            )
            canonical_aliases: set[str] = set()
            for alias in aliases:
                alias_key = str(alias["idempotency_key"])
                canonical_key = str(alias["canonical_idempotency_key"])
                action = str(alias["action"])
                request_digest = str(alias["request_digest"])
                if not alias_key.strip() or not canonical_key.strip() or not action.strip():
                    raise HostRuntimeError("host operation alias is malformed")
                require_digest(request_digest, "host operation alias request_digest")
                first = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events
                     WHERE idempotency_key=? AND operation_sequence=1
                    """,
                    (canonical_key,),
                ).fetchone()
                if first is None:
                    raise HostRuntimeError("host operation alias lacks its intent")
                intent = self._decode(first)
                if (
                    intent.action != action
                    or intent.request_digest != request_digest
                ):
                    raise HostRuntimeError(
                        "host operation alias differs from its durable intent"
                    )
                if alias_key == canonical_key:
                    canonical_aliases.add(canonical_key)
            if event_keys != canonical_aliases:
                raise HostRuntimeError(
                    "host operation history lacks exact canonical aliases"
                )

            semantic_claims = tuple(
                self.connection.execute(
                    """
                    SELECT * FROM host_semantic_operation_claims
                     ORDER BY claim_kind, scope_digest
                    """
                )
            )
            semantic_keys: set[str] = set()
            for claim in semantic_claims:
                kind = str(claim["claim_kind"])
                scope_digest = str(claim["scope_digest"])
                action = str(claim["action"])
                request_digest = str(claim["request_digest"])
                canonical_key = str(claim["canonical_idempotency_key"])
                if kind not in {"create", "message", "cancel", "checkpoint"}:
                    raise HostRuntimeError("host semantic operation kind is invalid")
                require_digest(scope_digest, "host semantic scope_digest")
                require_digest(request_digest, "host semantic request_digest")
                if action != kind or not canonical_key.strip():
                    raise HostRuntimeError("host semantic operation claim is malformed")
                first = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events
                     WHERE idempotency_key=? AND operation_sequence=1
                    """,
                    (canonical_key,),
                ).fetchone()
                if first is None:
                    raise HostRuntimeError(
                        "host semantic operation claim lacks its intent"
                    )
                intent = self._decode(first)
                if (
                    intent.action != action
                    or intent.request_digest != request_digest
                ):
                    raise HostRuntimeError(
                        "host semantic operation claim differs from its intent"
                    )
                semantic_keys.add(canonical_key)
            effect_keys = {
                key
                for key, (action, _request_digest) in identities.items()
                if action in {"create", "message", "cancel", "checkpoint"}
            }
            if effect_keys != semantic_keys:
                raise HostRuntimeError(
                    "host effect history lacks a unique semantic claim"
                )

            for adoption in self.connection.execute(
                "SELECT * FROM host_adoption_claims ORDER BY canonical_idempotency_key"
            ):
                canonical_key = str(adoption["canonical_idempotency_key"])
                response_type = str(adoption["response_type"])
                response_digest = str(adoption["response_digest"])
                evidence_digest = str(adoption["evidence_digest"])
                if response_type not in {"lease", "execution-receipt"}:
                    raise HostRuntimeError("host adoption response type is invalid")
                require_digest(response_digest, "host adoption response_digest")
                require_digest(evidence_digest, "host adoption evidence_digest")
                rows = self._rows(canonical_key)
                if not rows:
                    raise HostRuntimeError("host adoption claim lacks its intent")
                final = self._decode(rows[-1])
                if final.state is HostOperationState.SUCCEEDED and (
                    final.response_type != response_type
                    or final.response is None
                    or canonical_digest(dict(final.response)) != response_digest
                ):
                    raise HostRuntimeError(
                        "host adoption claim differs from its durable result"
                    )

            claims = tuple(
                self.connection.execute(
                    "SELECT * FROM host_activation_claims ORDER BY activation_digest"
                )
            )
            for claim in claims:
                for field in (
                    "activation_digest",
                    "proof_digest",
                    "nonce_digest",
                    "create_request_digest",
                    "subject_id",
                    "host_identity_digest",
                ):
                    require_digest(str(claim[field]), f"activation claim {field}")
                key = str(claim["create_idempotency_key"])
                if not key.strip():
                    raise HostRuntimeError("activation claim lacks a create identity")
                require_time(str(claim["claimed_at"]), "activation claim claimed_at")
                first = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events
                     WHERE idempotency_key=? AND operation_sequence=1
                    """,
                    (key,),
                ).fetchone()
                if first is None:
                    raise HostRuntimeError("activation claim lacks its durable create intent")
                intent = self._decode(first)
                if (
                    intent.action != "create"
                    or intent.request_digest != claim["create_request_digest"]
                ):
                    raise HostRuntimeError("activation claim differs from its create intent")
            cancel_claims = tuple(
                self.connection.execute(
                    "SELECT * FROM host_lease_cancel_claims ORDER BY lease_digest"
                )
            )
            cancel_by_lease: dict[str, sqlite3.Row] = {}
            for claim in cancel_claims:
                for field in (
                    "lease_digest",
                    "activation_digest",
                    "activation_proof_digest",
                    "nonce_digest",
                    "cancel_request_digest",
                ):
                    require_digest(str(claim[field]), f"cancel claim {field}")
                cancel_key = str(claim["cancel_idempotency_key"])
                if not cancel_key.strip():
                    raise HostRuntimeError("cancel claim lacks an operation identity")
                cancel_reason = claim["cancel_reason"]
                if type(cancel_reason) is not str or not cancel_reason.strip():
                    raise HostRuntimeError("cancel claim lacks its exact reason")
                require_time(str(claim["claimed_at"]), "cancel claim claimed_at")
                intent_row = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events
                     WHERE idempotency_key=? AND operation_sequence=1
                    """,
                    (cancel_key,),
                ).fetchone()
                if intent_row is None:
                    raise HostRuntimeError("cancel claim lacks its durable intent")
                intent = self._decode(intent_row)
                if (
                    intent.action != "cancel"
                    or intent.request_digest != claim["cancel_request_digest"]
                ):
                    raise HostRuntimeError("cancel claim differs from its intent")
                authenticated_lease: HostLease | None = None
                for row in self._rows():
                    candidate = self._decode(row)
                    if (
                        candidate.action != "create"
                        or candidate.state is not HostOperationState.SUCCEEDED
                        or candidate.response_type != "lease"
                        or candidate.response is None
                    ):
                        continue
                    lease = _lease_from_document(candidate.response)
                    if (
                        canonical_digest(lease.to_document())
                        == claim["lease_digest"]
                        and lease.activation_digest == claim["activation_digest"]
                        and lease.activation_proof_digest
                        == claim["activation_proof_digest"]
                        and lease.nonce_digest == claim["nonce_digest"]
                    ):
                        authenticated_lease = lease
                        break
                if authenticated_lease is None:
                    raise HostRuntimeError(
                        "cancel claim lacks an authenticated durable lease"
                    )
                if claim["cancel_request_digest"] != canonical_digest(
                    {
                        "lease": authenticated_lease.to_document(),
                        "reason": cancel_reason,
                    }
                ):
                    raise HostRuntimeError(
                        "cancel claim reason differs from its durable request"
                    )
                cancel_by_lease[str(claim["lease_digest"])] = claim
            for claim in self.connection.execute(
                "SELECT * FROM host_lease_completion_claims ORDER BY lease_digest"
            ):
                for field in (
                    "lease_digest",
                    "activation_digest",
                    "activation_proof_digest",
                    "nonce_digest",
                ):
                    require_digest(str(claim[field]), f"completion claim {field}")
                require_time(str(claim["claimed_at"]), "completion claim claimed_at")
                lease_digest = str(claim["lease_digest"])
                if lease_digest in cancel_by_lease:
                    raise HostRuntimeError(
                        "lease has conflicting completion and cancellation claims"
                    )
                authenticated = False
                for row in self._rows():
                    candidate = self._decode(row)
                    if (
                        candidate.action != "create"
                        or candidate.state is not HostOperationState.SUCCEEDED
                        or candidate.response_type != "lease"
                        or candidate.response is None
                    ):
                        continue
                    lease = _lease_from_document(candidate.response)
                    if (
                        canonical_digest(lease.to_document()) == lease_digest
                        and lease.activation_digest == claim["activation_digest"]
                        and lease.activation_proof_digest
                        == claim["activation_proof_digest"]
                        and lease.nonce_digest == claim["nonce_digest"]
                    ):
                        authenticated = True
                        break
                if not authenticated:
                    raise HostRuntimeError(
                        "completion claim lacks an authenticated durable lease"
                    )
            for commit in self.connection.execute(
                "SELECT * FROM host_lease_cancel_commits ORDER BY lease_digest"
            ):
                lease_digest = str(commit["lease_digest"])
                require_digest(lease_digest, "cancel commit lease_digest")
                require_digest(
                    str(commit["receipt_digest"]), "cancel commit receipt_digest"
                )
                require_time(str(commit["committed_at"]), "cancel committed_at")
                claim = cancel_by_lease.get(lease_digest)
                if (
                    claim is None
                    or commit["cancel_idempotency_key"]
                    != claim["cancel_idempotency_key"]
                ):
                    raise HostRuntimeError("cancel commit lacks its exact claim")
                final = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events
                     WHERE idempotency_key=?
                     ORDER BY operation_sequence DESC LIMIT 1
                    """,
                    (str(commit["cancel_idempotency_key"]),),
                ).fetchone()
                if final is None:
                    raise HostRuntimeError("cancel commit lacks its exact receipt")
                final_record = self._decode(final)
                receipt = (
                    _receipt_from_document(final_record.response)
                    if final_record.response is not None
                    else None
                )
                if (
                    final_record.action != "cancel"
                    or final_record.state is not HostOperationState.SUCCEEDED
                    or final_record.response_type != "execution-receipt"
                    or receipt is None
                    or receipt.state is not HostReceiptState.CANCELLED
                    or canonical_digest(receipt.to_document())
                    != commit["receipt_digest"]
                ):
                    raise HostRuntimeError("cancel commit receipt is invalid")
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, HostRuntimeError):
                raise
            raise HostRuntimeError("host activation claim is malformed") from error

    def claim_activation(
        self,
        *,
        authorization: AuthorizedOneRun,
        create_idempotency_key: str,
        create_request: Mapping[str, Any],
        host_identity_digest: str,
        claimed_at: str,
        _runtime_authority: object | None = None,
    ) -> None:
        """Bind a genuine one-run capability to one host create identity.

        An exact retry is idempotent. Any competing create identity, proof,
        nonce, subject, or observed host is denied before ``prepare``.

        The security-sensitive values are derived from the validated
        ``AuthorizedOneRun`` and exact create request.  Callers cannot supply
        free-standing activation, proof, nonce, candidate, or request digests.
        """

        if _runtime_authority is not _RUNTIME_JOURNAL_AUTHORITY:
            raise HostRuntimeError("activation claims are runtime-owned")
        try:
            authorization = validate_authorized_one_run(authorization)
        except ActivationBundleError as error:
            raise HostRuntimeError(
                "activation claim requires a sealed one-run authorization"
            ) from error
        request = dict(create_request)
        if set(request) != {
            "plan_digest",
            "generation_id",
            "authority_digest",
            "adapter_inventory_digest",
            "external_effects_required",
            "compilation_receipt",
            "subject_id",
            "node_ids",
            "nonce_digest",
            "lease_deadline",
            "activation_proof",
            "required_capabilities",
        }:
            raise HostRuntimeError("activation claim create request has an unknown shape")
        proof = authorization.proof_document()
        nonce_digest = _bytes_digest(authorization.nonce.encode("utf-8"))
        if (
            request.get("activation_proof") != proof
            or request.get("plan_digest") != authorization.plan_sha256
            or request.get("nonce_digest") != nonce_digest
        ):
            raise HostRuntimeError(
                "activation claim request differs from the one-run authorization"
            )
        subject_id = request.get("subject_id")
        if type(subject_id) is not str:
            raise HostRuntimeError("activation claim request lacks a subject")
        create_request_digest = canonical_digest(request)
        activation_digest = authorization.activation_digest
        proof_digest = authorization.proof_digest
        values = (
            activation_digest,
            proof_digest,
            nonce_digest,
            create_idempotency_key,
            create_request_digest,
            subject_id,
            host_identity_digest,
            claimed_at,
        )
        for value, label in (
            (activation_digest, "activation_digest"),
            (proof_digest, "proof_digest"),
            (nonce_digest, "nonce_digest"),
            (create_request_digest, "create_request_digest"),
            (subject_id, "subject_id"),
            (host_identity_digest, "host_identity_digest"),
        ):
            require_digest(value, f"activation claim {label}")
        if not create_idempotency_key.strip():
            raise HostRuntimeError("activation claim requires a create identity")
        require_time(claimed_at, "activation claim claimed_at")
        with self._lock:
            try:
                self.verify()
                self.connection.execute("BEGIN IMMEDIATE")
                rows = tuple(
                    self.connection.execute(
                        """
                        SELECT * FROM host_activation_claims
                         WHERE activation_digest=? OR nonce_digest=?
                            OR create_idempotency_key=?
                        """,
                        (
                            activation_digest,
                            nonce_digest,
                            create_idempotency_key,
                        ),
                    )
                )
                if rows:
                    row_values = {
                        tuple(row[field] for field in tuple(row.keys())[:-1])
                        for row in rows
                    }
                    if row_values != {values[:-1]}:
                        raise HostRuntimeError(
                            "activation or nonce is claimed by a competing host create"
                        )
                    self.connection.commit()
                    return
                intent = self.connection.execute(
                    """
                    SELECT action, request_digest FROM host_operation_events
                     WHERE idempotency_key=? AND operation_sequence=1
                    """,
                    (create_idempotency_key,),
                ).fetchone()
                if (
                    intent is None
                    or intent["action"] != "create"
                    or intent["request_digest"] != create_request_digest
                ):
                    raise HostRuntimeError(
                        "activation claim requires its exact durable create intent"
                    )
                self.connection.execute(
                    """
                    INSERT INTO host_activation_claims(
                        activation_digest, proof_digest, nonce_digest,
                        create_idempotency_key, create_request_digest, subject_id,
                        host_identity_digest, claimed_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    values,
                )
                self.connection.commit()
            except sqlite3.IntegrityError as error:
                self.connection.rollback()
                raise HostRuntimeError(
                    "activation or nonce is claimed by a competing host create"
                ) from error
            except BaseException:
                self.connection.rollback()
                raise

    def history(self, key: str) -> tuple[HostOperationRecord, ...]:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key is required")
        with self._lock, self._read_snapshot():
            self.verify()
            alias = self.connection.execute(
                """
                SELECT canonical_idempotency_key FROM host_operation_aliases
                 WHERE idempotency_key=?
                """,
                (key,),
            ).fetchone()
            canonical_key = key if alias is None else str(alias[0])
            return tuple(self._decode(row) for row in self._rows(canonical_key))

    def records(self) -> tuple[HostOperationRecord, ...]:
        """Return the complete verified append-only operation history."""

        with self._lock, self._read_snapshot():
            self.verify()
            return tuple(self._decode(row) for row in self._rows())

    def latest(self, key: str) -> HostOperationRecord | None:
        history = self.history(key)
        return None if not history else history[-1]

    def semantic_latest(
        self,
        *,
        kind: str,
        scope_digest: str,
        request: Mapping[str, Any],
    ) -> HostOperationRecord | None:
        """Resolve an operation alias through its unique semantic claim."""

        require_digest(scope_digest, "host semantic operation scope_digest")
        request_digest = canonical_digest(dict(request))
        with self._lock, self._read_snapshot():
            self.verify()
            claim = self.connection.execute(
                """
                SELECT * FROM host_semantic_operation_claims
                 WHERE claim_kind=? AND scope_digest=?
                """,
                (kind, scope_digest),
            ).fetchone()
            if claim is None:
                return None
            if (
                claim["action"] != kind
                or claim["request_digest"] != request_digest
            ):
                raise HostRuntimeError(
                    "host semantic operation is bound to another request"
                )
            rows = self._rows(str(claim["canonical_idempotency_key"]))
            if not rows:
                raise HostRuntimeError(
                    "host semantic operation claim lacks its intent"
                )
            return self._decode(rows[-1])

    def bind_semantic_alias(
        self,
        *,
        alias_key: str,
        kind: str,
        scope_digest: str,
        request: Mapping[str, Any],
        _runtime_authority: object | None = None,
    ) -> HostOperationRecord:
        """Atomically bind a new caller alias to one existing semantic intent."""

        if _runtime_authority is not _RUNTIME_JOURNAL_AUTHORITY:
            raise HostRuntimeError("host operation aliases are runtime-owned")
        if type(alias_key) is not str or not alias_key.strip():
            raise HostRuntimeError("host operation alias is required")
        require_digest(scope_digest, "host semantic operation scope_digest")
        request_digest = canonical_digest(dict(request))
        with self._lock:
            try:
                self.verify()
                self.connection.execute("BEGIN IMMEDIATE")
                claim = self.connection.execute(
                    """
                    SELECT * FROM host_semantic_operation_claims
                     WHERE claim_kind=? AND scope_digest=?
                    """,
                    (kind, scope_digest),
                ).fetchone()
                if claim is None:
                    raise HostRuntimeError(
                        "host semantic operation has no durable claim"
                    )
                canonical_key = str(claim["canonical_idempotency_key"])
                if (
                    claim["action"] != kind
                    or claim["request_digest"] != request_digest
                ):
                    raise HostRuntimeError(
                        "host semantic operation is bound to another request"
                    )
                alias = self.connection.execute(
                    "SELECT * FROM host_operation_aliases WHERE idempotency_key=?",
                    (alias_key,),
                ).fetchone()
                if alias is None:
                    self.connection.execute(
                        """
                        INSERT INTO host_operation_aliases(
                            idempotency_key, canonical_idempotency_key,
                            action, request_digest
                        ) VALUES(?,?,?,?)
                        """,
                        (alias_key, canonical_key, kind, request_digest),
                    )
                elif (
                    alias["canonical_idempotency_key"] != canonical_key
                    or alias["action"] != kind
                    or alias["request_digest"] != request_digest
                ):
                    raise HostRuntimeError(
                        "host operation alias is bound to another request"
                    )
                rows = self._rows(canonical_key)
                if not rows:
                    raise HostRuntimeError(
                        "host semantic operation claim lacks its intent"
                    )
                current = self._decode(rows[-1])
                self.connection.commit()
                return current
            except BaseException:
                self.connection.rollback()
                raise

    @contextmanager
    def adoption_guard(self) -> Iterator[None]:
        """Serialize process-local adoption over the durable CAS boundary."""

        with self._lock:
            yield

    def claim_adoption(
        self,
        *,
        operation: HostOperationRecord,
        response_type: str,
        response: Mapping[str, Any],
        evidence_digest: str,
        _runtime_authority: object | None = None,
    ) -> None:
        """Durably bind one ambiguous operation to one externally proven result."""

        if _runtime_authority is not _RUNTIME_JOURNAL_AUTHORITY:
            raise HostRuntimeError("host adoption claims are runtime-owned")
        if response_type not in {"lease", "execution-receipt"}:
            raise HostRuntimeError("host adoption response type is invalid")
        require_digest(evidence_digest, "host adoption evidence_digest")
        response_digest = canonical_digest(dict(response))
        values = (
            operation.idempotency_key,
            response_type,
            response_digest,
            evidence_digest,
        )
        with self._lock:
            try:
                self.verify()
                self.connection.execute("BEGIN IMMEDIATE")
                existing = self.connection.execute(
                    """
                    SELECT * FROM host_adoption_claims
                     WHERE canonical_idempotency_key=?
                    """,
                    (operation.idempotency_key,),
                ).fetchone()
                if existing is not None:
                    if tuple(existing) != values:
                        raise HostRuntimeError(
                            "host adoption proof is bound to another result"
                        )
                    self.connection.commit()
                    return
                latest = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events
                     WHERE idempotency_key=?
                     ORDER BY operation_sequence DESC LIMIT 1
                    """,
                    (operation.idempotency_key,),
                ).fetchone()
                if latest is None:
                    raise HostRuntimeError("host adoption lacks its durable intent")
                current = self._decode(latest)
                if (
                    current.request_digest != operation.request_digest
                    or current.action != operation.action
                    or current.state
                    not in {
                        HostOperationState.INTENT_RECORDED,
                        HostOperationState.RECOVERABLE,
                    }
                ):
                    raise HostRuntimeError("host operation is not adoptable")
                self.connection.execute(
                    "INSERT INTO host_adoption_claims VALUES(?,?,?,?)",
                    values,
                )
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise

    def adoption_matches(
        self,
        *,
        operation: HostOperationRecord,
        response_type: str,
        response: Mapping[str, Any],
        evidence_digest: str,
    ) -> bool:
        """Whether a terminal result carries this exact durable adoption proof."""

        with self._lock, self._read_snapshot():
            self.verify()
            claim = self.connection.execute(
                """
                SELECT * FROM host_adoption_claims
                 WHERE canonical_idempotency_key=?
                """,
                (operation.idempotency_key,),
            ).fetchone()
            return claim is not None and tuple(claim) == (
                operation.idempotency_key,
                response_type,
                canonical_digest(dict(response)),
                evidence_digest,
            )

    def wait_for_terminal(
        self,
        key: str,
        *,
        timeout_seconds: float,
        monotonic: Callable[[], float],
    ) -> HostOperationRecord:
        """Wait briefly for another atomic owner to publish its durable result."""

        if (
            type(timeout_seconds) not in {int, float}
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise HostRuntimeError("host alias wait timeout must be positive")
        deadline = monotonic() + float(timeout_seconds)
        while True:
            current = self.latest(key)
            if current is None:
                raise HostRecoveryRequired("host operation intent disappeared")
            if current.state is not HostOperationState.INTENT_RECORDED:
                return current
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise HostRecoveryRequired(
                    "host operation owner has not published a durable result"
                )
            threading.Event().wait(min(0.01, remaining))

    def begin(
        self,
        *,
        idempotency_key: str,
        action: str,
        request: Mapping[str, Any],
        lease: HostLease | None = None,
        deny_after_cancellation: bool = False,
        claim_cancellation_at: str | None = None,
        semantic_kind: str | None = None,
        semantic_scope_digest: str | None = None,
        _runtime_authority: object | None = None,
    ) -> tuple[HostOperationRecord, bool]:
        """Atomically acquire one exact idempotent operation intent.

        The boolean is true only for the transaction that inserted the intent.
        An identical concurrent caller receives the latest existing record and
        therefore never owns the adapter call.
        """

        if _runtime_authority is not _RUNTIME_JOURNAL_AUTHORITY:
            raise HostRuntimeError("host operation journal writes are runtime-owned")
        if type(idempotency_key) is not str or not idempotency_key.strip():
            raise HostRuntimeError("host idempotency key is required")
        if (semantic_kind is None) != (semantic_scope_digest is None):
            raise HostRuntimeError(
                "semantic operation kind and scope must be supplied together"
            )
        if semantic_kind is not None:
            assert semantic_scope_digest is not None
            if semantic_kind != action or semantic_kind not in {
                "create",
                "message",
                "cancel",
                "checkpoint",
            }:
                raise HostRuntimeError("host semantic operation kind is invalid")
            require_digest(
                semantic_scope_digest,
                "host semantic operation scope_digest",
            )
        if deny_after_cancellation or claim_cancellation_at is not None:
            if type(lease) is not HostLease:
                raise HostRuntimeError("lease-level operation requires a typed lease")
        if claim_cancellation_at is not None:
            if action != "cancel":
                raise HostRuntimeError("only cancellation may claim a lease stop")
            require_time(claim_cancellation_at, "cancel claim claimed_at")
            assert lease is not None
            cancel_reason = request.get("reason")
            if (
                set(request) != {"lease", "reason"}
                or request.get("lease") != lease.to_document()
                or type(cancel_reason) is not str
                or not cancel_reason.strip()
            ):
                raise HostRuntimeError(
                    "cancellation claim requires the exact lease and reason"
                )
        request_digest = canonical_digest(dict(request))
        with self._lock:
            try:
                self.verify()
                self.connection.execute("BEGIN IMMEDIATE")
                alias = self.connection.execute(
                    """
                    SELECT * FROM host_operation_aliases WHERE idempotency_key=?
                    """,
                    (idempotency_key,),
                ).fetchone()
                if alias is not None:
                    if (
                        alias["action"] != action
                        or alias["request_digest"] != request_digest
                    ):
                        raise HostRuntimeError(
                            "host idempotency key is bound to another request"
                        )
                    canonical_key = str(alias["canonical_idempotency_key"])
                    last = self.connection.execute(
                        """
                        SELECT * FROM host_operation_events
                         WHERE idempotency_key=?
                         ORDER BY operation_sequence DESC LIMIT 1
                        """,
                        (canonical_key,),
                    ).fetchone()
                    if last is None:
                        raise HostRuntimeError("host operation alias lacks its intent")
                    current = self._decode(last)
                    self.connection.commit()
                    return current, False

                semantic_claim = None
                if semantic_kind is not None:
                    semantic_claim = self.connection.execute(
                        """
                        SELECT * FROM host_semantic_operation_claims
                         WHERE claim_kind=? AND scope_digest=?
                        """,
                        (semantic_kind, semantic_scope_digest),
                    ).fetchone()
                if semantic_claim is not None:
                    if (
                        semantic_claim["action"] != action
                        or semantic_claim["request_digest"] != request_digest
                    ):
                        raise HostRuntimeError(
                            "host semantic operation is bound to another request"
                        )
                    canonical_key = str(
                        semantic_claim["canonical_idempotency_key"]
                    )
                    self.connection.execute(
                        """
                        INSERT INTO host_operation_aliases(
                            idempotency_key, canonical_idempotency_key,
                            action, request_digest
                        ) VALUES(?,?,?,?)
                        """,
                        (idempotency_key, canonical_key, action, request_digest),
                    )
                    last = self.connection.execute(
                        """
                        SELECT * FROM host_operation_events
                         WHERE idempotency_key=?
                         ORDER BY operation_sequence DESC LIMIT 1
                        """,
                        (canonical_key,),
                    ).fetchone()
                    if last is None:
                        raise HostRuntimeError(
                            "host semantic operation claim lacks its intent"
                        )
                    current = self._decode(last)
                    self.connection.commit()
                    return current, False

                canonical_key = idempotency_key
                intent = HostOperationRecord(
                    idempotency_key=canonical_key,
                    action=action,
                    request_digest=request_digest,
                    state=HostOperationState.INTENT_RECORDED,
                    sequence=1,
                    response_type=None,
                    response=None,
                    usage=None,
                    reason=None,
                )
                encoded = canonical_json_bytes(intent.to_document()).decode()
                lease_digest = (
                    canonical_digest(lease.to_document())
                    if lease is not None
                    else None
                )
                existing_cancel = (
                    self.connection.execute(
                        """
                        SELECT * FROM host_lease_cancel_claims
                         WHERE lease_digest=?
                        """,
                        (lease_digest,),
                    ).fetchone()
                    if lease_digest is not None
                    else None
                )
                if deny_after_cancellation and existing_cancel is not None:
                    raise HostRuntimeError(
                        "durable lease cancellation blocks new host effects"
                    )
                if claim_cancellation_at is not None:
                    assert lease is not None and lease_digest is not None
                    if existing_cancel is not None:
                        raise HostRuntimeError(
                            "durable lease cancellation is already claimed"
                        )
                    existing_completion = self.connection.execute(
                        """
                        SELECT * FROM host_lease_completion_claims
                         WHERE lease_digest=?
                        """,
                        (lease_digest,),
                    ).fetchone()
                    if existing_completion is not None:
                        raise HostRuntimeError(
                            "durable lease completion blocks cancellation"
                        )
                    self.connection.execute(
                        """
                        INSERT INTO host_lease_cancel_claims(
                            lease_digest, activation_digest,
                            activation_proof_digest, nonce_digest,
                            cancel_idempotency_key, cancel_request_digest,
                            cancel_reason, claimed_at
                        ) VALUES(?,?,?,?,?,?,?,?)
                        """,
                        (
                            lease_digest,
                            lease.activation_digest,
                            lease.activation_proof_digest,
                            lease.nonce_digest,
                            idempotency_key,
                            intent.request_digest,
                            cancel_reason,
                            claim_cancellation_at,
                        ),
                    )
                if semantic_kind is not None:
                    self.connection.execute(
                        """
                        INSERT INTO host_semantic_operation_claims(
                            claim_kind, scope_digest, action, request_digest,
                            canonical_idempotency_key
                        ) VALUES(?,?,?,?,?)
                        """,
                        (
                            semantic_kind,
                            semantic_scope_digest,
                            action,
                            request_digest,
                            canonical_key,
                        ),
                    )
                self.connection.execute(
                    """
                    INSERT INTO host_operation_aliases(
                        idempotency_key, canonical_idempotency_key,
                        action, request_digest
                    ) VALUES(?,?,?,?)
                    """,
                    (idempotency_key, canonical_key, action, request_digest),
                )
                event_digest = canonical_digest(
                    {"previous_digest": None, "record": intent.to_document()}
                )
                self.connection.execute(
                    """
                    INSERT INTO host_operation_events(
                        idempotency_key, operation_sequence, action, request_digest,
                        payload_json, previous_digest, event_digest
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        intent.idempotency_key,
                        intent.sequence,
                        intent.action,
                        intent.request_digest,
                        encoded,
                        None,
                        event_digest,
                    ),
                )
                self.connection.commit()
                return intent, True
            except BaseException:
                self.connection.rollback()
                raise

    def authenticates_message_receipt(
        self, lease: HostLease, receipt: HostExecutionReceipt
    ) -> bool:
        """Authenticate a receipt against the exact successful message request."""

        if type(lease) is not HostLease or type(receipt) is not HostExecutionReceipt:
            return False
        expected = receipt.to_document()
        expected_request_digest = canonical_digest(
            {
                "lease": lease.to_document(),
                "node_id": receipt.node_id,
                "input_digest": receipt.input_digest,
            }
        )
        with self._lock, self._read_snapshot():
            self.verify()
            for row in self._rows():
                record = self._decode(row)
                if (
                    record.action == "message"
                    and record.request_digest == expected_request_digest
                    and record.state is HostOperationState.SUCCEEDED
                    and record.response_type == "execution-receipt"
                    and record.response is not None
                    and dict(record.response) == expected
                ):
                    return True
        return False

    def cancellation_claimed(self, lease: HostLease) -> bool:
        """Whether an exact authenticated lease has entered cancellation."""

        return self.cancellation_result(lease) is not None

    def cancellation_result(
        self, lease: HostLease
    ) -> tuple[str, HostExecutionReceipt | None] | None:
        """Return the exact reason and optional committed cancellation receipt."""

        if type(lease) is not HostLease:
            return None
        lease_digest = canonical_digest(lease.to_document())
        with self._lock, self._read_snapshot():
            self.verify()
            claim = self.connection.execute(
                """
                SELECT * FROM host_lease_cancel_claims WHERE lease_digest=?
                """,
                (lease_digest,),
            ).fetchone()
            if claim is None:
                return None
            if not (
                claim["activation_digest"] == lease.activation_digest
                and claim["activation_proof_digest"]
                == lease.activation_proof_digest
                and claim["nonce_digest"] == lease.nonce_digest
            ):
                raise HostRuntimeError(
                    "cancellation claim differs from the authenticated lease"
                )
            reason = str(claim["cancel_reason"])
            commit = self.connection.execute(
                """
                SELECT * FROM host_lease_cancel_commits WHERE lease_digest=?
                """,
                (lease_digest,),
            ).fetchone()
            if commit is None:
                return reason, None
            final = self.connection.execute(
                """
                SELECT * FROM host_operation_events WHERE idempotency_key=?
                 ORDER BY operation_sequence DESC LIMIT 1
                """,
                (str(claim["cancel_idempotency_key"]),),
            ).fetchone()
            if final is None:
                raise HostRuntimeError("cancel commit lacks its exact receipt")
            record = self._decode(final)
            if record.response is None:
                raise HostRuntimeError("cancel commit lacks its exact receipt")
            return reason, _receipt_from_document(record.response)

    def claim_completion(
        self,
        lease: HostLease,
        *,
        claimed_at: str,
        _runtime_authority: object | None = None,
    ) -> bool:
        """Atomically order proven completion before or after cancellation.

        ``True`` means completion owns the lease terminal. ``False`` means a
        cancellation claim already owns it and must be reconciled instead.
        """

        if _runtime_authority is not _RUNTIME_JOURNAL_AUTHORITY:
            raise HostRuntimeError("host completion claims are runtime-owned")
        if type(lease) is not HostLease or not self.authenticates_lease(lease):
            raise HostRuntimeError(
                "host completion requires the exact journal-authenticated lease"
            )
        require_time(claimed_at, "completion claim claimed_at")
        lease_digest = canonical_digest(lease.to_document())
        values = (
            lease_digest,
            lease.activation_digest,
            lease.activation_proof_digest,
            lease.nonce_digest,
            claimed_at,
        )
        with self._lock:
            try:
                self.verify()
                self.connection.execute("BEGIN IMMEDIATE")
                existing = self.connection.execute(
                    """
                    SELECT * FROM host_lease_completion_claims
                     WHERE lease_digest=?
                    """,
                    (lease_digest,),
                ).fetchone()
                if existing is not None:
                    if tuple(existing)[:4] != values[:4]:
                        raise HostRuntimeError(
                            "host completion claim differs from the lease"
                        )
                    self.connection.commit()
                    return True
                cancellation = self.connection.execute(
                    """
                    SELECT * FROM host_lease_cancel_claims WHERE lease_digest=?
                    """,
                    (lease_digest,),
                ).fetchone()
                if cancellation is not None:
                    self.connection.commit()
                    return False
                self.connection.execute(
                    "INSERT INTO host_lease_completion_claims VALUES(?,?,?,?,?)",
                    values,
                )
                self.connection.commit()
                return True
            except BaseException:
                self.connection.rollback()
                raise

    def finish_cancellation(
        self,
        intent: HostOperationRecord,
        *,
        lease: HostLease,
        receipt: HostExecutionReceipt,
        usage: HostUsage,
        committed_at: str,
        reason: str | None = None,
        _runtime_authority: object | None = None,
    ) -> HostOperationRecord:
        """Atomically retain a successful cancel receipt and lease stop commit."""

        if _runtime_authority is not _RUNTIME_JOURNAL_AUTHORITY:
            raise HostRuntimeError("host cancellation commits are runtime-owned")
        if (
            type(lease) is not HostLease
            or type(receipt) is not HostExecutionReceipt
            or receipt.state is not HostReceiptState.CANCELLED
        ):
            raise HostRuntimeError("cancellation commit requires a cancelled receipt")
        require_time(committed_at, "cancel committed_at")
        lease_digest = canonical_digest(lease.to_document())
        receipt_digest = canonical_digest(receipt.to_document())
        with self._lock:
            try:
                self.verify()
                self.connection.execute("BEGIN IMMEDIATE")
                claim = self.connection.execute(
                    """
                    SELECT * FROM host_lease_cancel_claims WHERE lease_digest=?
                    """,
                    (lease_digest,),
                ).fetchone()
                last = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events WHERE idempotency_key=?
                     ORDER BY operation_sequence DESC LIMIT 1
                    """,
                    (intent.idempotency_key,),
                ).fetchone()
                if claim is None or last is None:
                    raise HostRuntimeError(
                        "cancellation commit lacks its durable lease claim"
                    )
                prior = self._decode(last)
                if (
                    claim["cancel_idempotency_key"] != intent.idempotency_key
                    or claim["cancel_request_digest"] != intent.request_digest
                    or prior.action != "cancel"
                    or prior.request_digest != intent.request_digest
                    or prior.state
                    not in {
                        HostOperationState.INTENT_RECORDED,
                        HostOperationState.RECOVERABLE,
                    }
                ):
                    raise HostRuntimeError(
                        "cancellation commit differs from its durable claim"
                    )
                record = HostOperationRecord(
                    idempotency_key=intent.idempotency_key,
                    action="cancel",
                    request_digest=intent.request_digest,
                    state=HostOperationState.SUCCEEDED,
                    sequence=prior.sequence + 1,
                    response_type="execution-receipt",
                    response=receipt.to_document(),
                    usage=usage,
                    reason=reason,
                )
                encoded = canonical_json_bytes(record.to_document()).decode()
                previous = str(last["event_digest"])
                event_digest = canonical_digest(
                    {"previous_digest": previous, "record": record.to_document()}
                )
                self.connection.execute(
                    """
                    INSERT INTO host_operation_events(
                        idempotency_key, operation_sequence, action, request_digest,
                        payload_json, previous_digest, event_digest
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        record.idempotency_key,
                        record.sequence,
                        record.action,
                        record.request_digest,
                        encoded,
                        previous,
                        event_digest,
                    ),
                )
                self.connection.execute(
                    """
                    INSERT INTO host_lease_cancel_commits(
                        lease_digest, cancel_idempotency_key,
                        receipt_digest, committed_at
                    ) VALUES(?,?,?,?)
                    """,
                    (
                        lease_digest,
                        intent.idempotency_key,
                        receipt_digest,
                        committed_at,
                    ),
                )
                self.connection.commit()
                return record
            except BaseException:
                self.connection.rollback()
                raise

    def authenticates_create_claim(
        self,
        *,
        create_idempotency_key: str,
        create_request: Mapping[str, Any],
        lease: HostLease,
    ) -> bool:
        """Authenticate an adopted lease against a prior runtime-issued claim."""

        if type(lease) is not HostLease:
            return False
        request = dict(create_request)
        proof = request.get("activation_proof")
        if not isinstance(proof, Mapping):
            return False
        with self._lock, self._read_snapshot():
            self.verify()
            claim = self.connection.execute(
                """
                SELECT * FROM host_activation_claims
                 WHERE create_idempotency_key=?
                """,
                (create_idempotency_key,),
            ).fetchone()
            return claim is not None and (
                claim["activation_digest"] == lease.activation_digest
                and claim["proof_digest"] == lease.activation_proof_digest
                and claim["proof_digest"] == canonical_digest(dict(proof))
                and claim["nonce_digest"] == lease.nonce_digest
                and claim["nonce_digest"] == request.get("nonce_digest")
                and claim["create_request_digest"] == canonical_digest(request)
                and claim["subject_id"] == lease.subject_id
                and claim["subject_id"] == request.get("subject_id")
                and claim["host_identity_digest"] == lease.host_identity_digest
            )

    def authenticates_lease(self, lease: HostLease) -> bool:
        """Verify an exact create/adoption lease and its durable activation claim."""

        if type(lease) is not HostLease:
            return False
        expected = lease.to_document()
        with self._lock, self._read_snapshot():
            self.verify()
            for row in self._rows():
                record = self._decode(row)
                if not (
                    record.action == "create"
                    and record.state is HostOperationState.SUCCEEDED
                    and record.response_type == "lease"
                    and record.response is not None
                    and dict(record.response) == expected
                ):
                    continue
                claim = self.connection.execute(
                    """
                    SELECT * FROM host_activation_claims
                     WHERE create_idempotency_key=?
                    """,
                    (record.idempotency_key,),
                ).fetchone()
                if claim is not None and (
                    claim["activation_digest"] == lease.activation_digest
                    and claim["proof_digest"] == lease.activation_proof_digest
                    and claim["nonce_digest"] == lease.nonce_digest
                    and claim["create_request_digest"] == record.request_digest
                    and claim["subject_id"] == lease.subject_id
                    and claim["host_identity_digest"]
                    == lease.host_identity_digest
                ):
                    return True
        return False

    def append(
        self,
        record: HostOperationRecord,
        *,
        _runtime_authority: object | None = None,
    ) -> HostOperationRecord:
        """Append a runtime-issued event.

        Direct callers cannot manufacture durable authorization by assembling
        records.  The private process authority is intentionally only an
        in-process encapsulation boundary; trusted storage custody remains a
        deployment obligation for restart authentication.
        """

        if _runtime_authority is not _RUNTIME_JOURNAL_AUTHORITY:
            raise HostRuntimeError("host operation journal writes are runtime-owned")
        encoded = canonical_json_bytes(record.to_document()).decode()
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                last = self.connection.execute(
                    """
                    SELECT * FROM host_operation_events WHERE idempotency_key=?
                     ORDER BY operation_sequence DESC LIMIT 1
                    """,
                    (record.idempotency_key,),
                ).fetchone()
                expected = 1 if last is None else int(last["operation_sequence"]) + 1
                if record.sequence != expected:
                    # Exact retry of an already-recorded event is idempotent.
                    existing = self.connection.execute(
                        """
                        SELECT * FROM host_operation_events
                         WHERE idempotency_key=? AND operation_sequence=?
                        """,
                        (record.idempotency_key, record.sequence),
                    ).fetchone()
                    if existing is not None and existing["payload_json"] == encoded:
                        result = self._decode(existing)
                        self.connection.commit()
                        return result
                    raise HostRuntimeError("host operation compare-and-swap sequence failed")
                if last is None:
                    if record.state is not HostOperationState.INTENT_RECORDED:
                        raise HostRuntimeError("host operation must begin with a durable intent")
                    previous = None
                else:
                    prior = self._decode(last)
                    if (record.action, record.request_digest) != (
                        prior.action,
                        prior.request_digest,
                    ):
                        raise HostRuntimeError("host operation intent is immutable")
                    if prior.state is HostOperationState.SUCCEEDED:
                        raise HostRuntimeError("successful host operation is terminal")
                    if record.state is HostOperationState.INTENT_RECORDED:
                        raise HostRuntimeError("host intent cannot be recorded twice")
                    if prior.state is HostOperationState.DENIED:
                        raise HostRuntimeError("denied host operation is terminal")
                    if prior.state is HostOperationState.RECOVERABLE and record.state is not HostOperationState.SUCCEEDED:
                        raise HostRuntimeError("only explicit adoption may resolve a host outcome")
                    previous = str(last["event_digest"])
                event_digest = canonical_digest(
                    {"previous_digest": previous, "record": record.to_document()}
                )
                self.connection.execute(
                    """
                    INSERT INTO host_operation_events(
                        idempotency_key, operation_sequence, action, request_digest,
                        payload_json, previous_digest, event_digest
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        record.idempotency_key,
                        record.sequence,
                        record.action,
                        record.request_digest,
                        encoded,
                        previous,
                        event_digest,
                    ),
                )
                self.connection.commit()
                return record
            except BaseException:
                self.connection.rollback()
                raise


_T = TypeVar("_T")


class AdoptionVerifier(Protocol):
    """Externally anchored witness verifier for ambiguous host outcomes."""

    def __call__(
        self,
        *,
        action: str,
        request: Mapping[str, Any],
        response_type: str,
        response: Mapping[str, Any],
        evidence_digest: str,
    ) -> bool: ...


class _HistoricalHostObserver:
    """Read-only recovery surface for an already-issued durable lease.

    The object deliberately retains only the adapter's bound ``observe``
    callable.  It has no route to ``prepare``, ``execute``, or ``cancel`` and
    does not use the expired execution deadline as authority.  Its own bounded
    wait limits only a fresh, read-only observation used to authenticate
    historical evidence.
    """

    def __init__(
        self,
        observe: Callable[..., HostObservation],
        journal: HostOperationJournal,
        *,
        clock: Callable[[], datetime],
        monotonic: Callable[[], float],
    ) -> None:
        self._observe = observe
        self._journal = journal
        self._clock = clock
        self._monotonic = monotonic

    @staticmethod
    def _timeout(value: float) -> float:
        if (
            type(value) not in {int, float}
            or not math.isfinite(value)
            or value <= 0
        ):
            raise HostRuntimeError("historical observation timeout must be positive")
        return float(value)

    def _bounded_observe(
        self, *, subject_id: str, timeout_seconds: float
    ) -> tuple[HostObservation, int]:
        bounded_wait = self._timeout(timeout_seconds)
        result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
        started = self._monotonic()

        def invoke() -> None:
            try:
                result.put((True, self._observe(subject_id=subject_id)))
            except BaseException as error:
                result.put((False, error))

        worker = threading.Thread(
            target=invoke,
            daemon=True,
            name="hive-host-historical-observation",
        )
        worker.start()
        worker.join(bounded_wait)
        elapsed = max(0, round((self._monotonic() - started) * 1000))
        if worker.is_alive():
            raise HostRecoveryRequired("historical host observation timed out")
        succeeded, value = result.get_nowait()
        if not succeeded:
            assert isinstance(value, BaseException)
            raise value
        if type(value) is not HostObservation:
            raise HostRuntimeError("host returned an untyped historical observation")
        return value, elapsed

    @staticmethod
    def _lease_from_record(record: HostOperationRecord) -> HostLease:
        if record.state is HostOperationState.DENIED:
            raise HostRuntimeError(record.reason or "host operation was denied")
        if record.state is HostOperationState.RECOVERABLE:
            raise HostRecoveryRequired(record.reason or "host operation is ambiguous")
        if (
            record.state is not HostOperationState.SUCCEEDED
            or record.response_type != "lease"
            or record.response is None
        ):
            raise HostRuntimeError("durable host response has an unexpected type")
        return _lease_from_document(record.response)

    def resume(
        self,
        *,
        create_idempotency_key: str,
        poll_idempotency_key: str,
        timeout_seconds: float,
    ) -> HostLease:
        """Authenticate a historical lease using one fresh read-only observation."""

        if not isinstance(poll_idempotency_key, str) or not poll_idempotency_key.strip():
            raise HostRuntimeError("reconciliation poll idempotency key is required")
        self._timeout(timeout_seconds)
        record = self._journal.latest(create_idempotency_key)
        if record is None:
            raise HostRuntimeError("no durable host lease exists")
        lease = self._lease_from_record(record)
        if not self._journal.authenticates_lease(lease):
            raise HostRecoveryRequired("durable host lease authentication failed")

        # Never reuse a stable poll identity: doing so could replay a cached
        # pre-restart observation and conceal host identity or trust drift.
        fresh_poll_key = canonical_digest(
            {
                "historical_resume_poll_base": poll_idempotency_key,
                "create_idempotency_key": create_idempotency_key,
                "attempt_nonce": secrets.token_hex(32),
            }
        )
        request = {
            "subject_id": lease.subject_id,
            "create_idempotency_key": create_idempotency_key,
            "mode": "historical-reconciliation",
        }
        intent, fresh = self._journal.begin(
            idempotency_key=fresh_poll_key,
            action="historical-poll",
            request=request,
            _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
        )
        if not fresh:
            raise HostRecoveryRequired(
                "historical observation identity was unexpectedly reused"
            )
        try:
            admitted_at = self._clock()
            if admitted_at.tzinfo is None or admitted_at.utcoffset() is None:
                raise HostRuntimeError("host runtime clock must be timezone-aware")
            observation, elapsed = self._bounded_observe(
                subject_id=lease.subject_id,
                timeout_seconds=timeout_seconds,
            )
            observed = require_time(observation.observed_at, "host observed_at")
            now = self._clock()
            if observation.subject_id != lease.subject_id:
                raise HostRuntimeError(
                    "host returned an observation for another subject"
                )
            if observed < admitted_at:
                raise HostRuntimeError("host returned a stale cached observation")
            if observed > now:
                raise HostRuntimeError("host returned an observation from the future")
            if (
                observed < require_time(lease.issued_at, "lease issued_at")
                or observation.identity.host_id != lease.host_id
                or observation.identity.digest != lease.host_identity_digest
                or observation.identity.adapter_digest
                != lease.adapter_inventory_digest
                or observation.trust_evidence_digest
                != lease.trust_evidence_digest
                or not set(lease.required_capabilities).issubset(
                    observation.capabilities
                )
                or not observation.clean
            ):
                raise HostRecoveryRequired("durable lease host identity drifted")
            response = observation.to_document()
            self._journal.append(
                HostOperationRecord(
                    idempotency_key=intent.idempotency_key,
                    action=intent.action,
                    request_digest=intent.request_digest,
                    state=HostOperationState.SUCCEEDED,
                    sequence=2,
                    response_type="observation",
                    response=response,
                    usage=HostUsage(
                        elapsed,
                        0,
                        len(canonical_json_bytes(response)),
                    ),
                    reason=None,
                ),
                _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
            )
            return lease
        except BaseException as error:
            self._journal.append(
                HostOperationRecord(
                    idempotency_key=intent.idempotency_key,
                    action=intent.action,
                    request_digest=intent.request_digest,
                    state=HostOperationState.RECOVERABLE,
                    sequence=2,
                    response_type=None,
                    response=None,
                    usage=HostUsage(round(float(timeout_seconds) * 1000), 0, 0),
                    reason=(
                        "historical host observation is unavailable: "
                        f"{type(error).__name__}"
                    ),
                ),
                _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
            )
            if isinstance(error, HostRecoveryRequired):
                raise
            raise HostRecoveryRequired(
                "historical host observation requires recovery"
            ) from error


class HostRuntime:
    """Apply one-run deadlines and durable idempotency to a ``HostAdapter``."""

    def __init__(
        self,
        adapter: HostAdapter,
        journal: HostOperationJournal,
        *,
        one_run_deadline: str,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        adoption_verifier: AdoptionVerifier | None = None,
    ) -> None:
        self.adapter = adapter
        self.journal = journal
        self.deadline = require_time(one_run_deadline, "one_run_deadline")
        self.clock = clock or (lambda: datetime.now(UTC))
        self.monotonic = monotonic
        self.adoption_verifier = adoption_verifier
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise HostRuntimeError("host runtime clock must be timezone-aware")
        self._historical_observer = _HistoricalHostObserver(
            adapter.observe,
            journal,
            clock=self.clock,
            monotonic=monotonic,
        )

    def _remaining(
        self,
        requested_seconds: float,
        *,
        operation_deadline: datetime | None = None,
    ) -> float:
        if (
            type(requested_seconds) not in {int, float}
            or not math.isfinite(requested_seconds)
            or requested_seconds <= 0
        ):
            raise HostRuntimeError("host operation timeout must be positive")
        effective_deadline = self.deadline
        if operation_deadline is not None:
            if (
                operation_deadline.tzinfo is None
                or operation_deadline.utcoffset() is None
            ):
                raise HostRuntimeError("host operation deadline must be timezone-aware")
            effective_deadline = min(effective_deadline, operation_deadline)
        remaining = (effective_deadline - self.clock()).total_seconds()
        if remaining <= 0:
            raise HostRuntimeError("one-run deadline has expired")
        return min(float(requested_seconds), remaining)

    def _bounded(
        self,
        operation: Callable[[], _T],
        timeout_seconds: float,
        *,
        operation_deadline: datetime | None = None,
    ) -> tuple[_T, int]:
        result: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
        bounded_wait = self._remaining(
            timeout_seconds,
            operation_deadline=operation_deadline,
        )
        started = self.monotonic()

        def invoke() -> None:
            try:
                result.put((True, operation()))
            except BaseException as error:
                result.put((False, error))

        worker = threading.Thread(target=invoke, daemon=True, name="hive-host-operation")
        worker.start()
        worker.join(bounded_wait)
        elapsed = max(0, round((self.monotonic() - started) * 1000))
        if worker.is_alive():
            raise HostRecoveryRequired("host operation exceeded its bounded wait")
        succeeded, value = result.get_nowait()
        if not succeeded:
            assert isinstance(value, BaseException)
            raise value
        return value, elapsed  # type: ignore[return-value]

    def _begin(
        self,
        *,
        key: str,
        action: str,
        request: Mapping[str, Any],
        lease: HostLease | None = None,
        deny_after_cancellation: bool = False,
        claim_cancellation_at: str | None = None,
        semantic_kind: str | None = None,
        semantic_scope_digest: str | None = None,
        settle_timeout_seconds: float = 30,
    ) -> tuple[HostOperationRecord, bool]:
        current, fresh = self.journal.begin(
            idempotency_key=key,
            action=action,
            request=request,
            lease=lease,
            deny_after_cancellation=deny_after_cancellation,
            claim_cancellation_at=claim_cancellation_at,
            semantic_kind=semantic_kind,
            semantic_scope_digest=semantic_scope_digest,
            _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
        )
        if not fresh:
            if current.state is HostOperationState.RECOVERABLE:
                raise HostRecoveryRequired("host operation requires explicit observation or adoption")
            if current.state is HostOperationState.INTENT_RECORDED:
                current = self.journal.wait_for_terminal(
                    current.idempotency_key,
                    timeout_seconds=settle_timeout_seconds,
                    monotonic=self.monotonic,
                )
                if current.state is HostOperationState.RECOVERABLE:
                    raise HostRecoveryRequired(
                        "host operation requires explicit observation or adoption"
                    )
            return current, False
        return current, True

    def _finish(
        self,
        intent: HostOperationRecord,
        *,
        state: HostOperationState,
        response_type: str | None,
        response: Mapping[str, Any] | None,
        usage: HostUsage,
        reason: str | None = None,
    ) -> HostOperationRecord:
        return self.journal.append(
            HostOperationRecord(
                idempotency_key=intent.idempotency_key,
                action=intent.action,
                request_digest=intent.request_digest,
                state=state,
                sequence=(self.journal.latest(intent.idempotency_key) or intent).sequence + 1,
                response_type=response_type,
                response=response,
                usage=usage,
                reason=reason,
            ),
            _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
        )

    @staticmethod
    def _response(record: HostOperationRecord, expected_type: str) -> Mapping[str, Any]:
        if record.state is HostOperationState.DENIED:
            raise HostRuntimeError(record.reason or "host operation was denied")
        if record.state is HostOperationState.RECOVERABLE:
            raise HostRecoveryRequired(record.reason or "host operation is ambiguous")
        if record.state is not HostOperationState.SUCCEEDED or record.response_type != expected_type or record.response is None:
            raise HostRuntimeError("durable host response has an unexpected type")
        return record.response

    def _receipt_time_is_bound(
        self, receipt: HostExecutionReceipt, lease: HostLease
    ) -> bool:
        """Validate immutable receipt evidence against its authority interval."""

        observed = require_time(receipt.observed_at, "receipt observed_at")
        issued = require_time(lease.issued_at, "lease issued_at")
        expires = require_time(lease.expires_at, "lease expires_at")
        return (
            issued <= observed < expires
            and observed < self.deadline
        )

    def _fresh_receipt_time_is_bound(
        self, receipt: HostExecutionReceipt, lease: HostLease
    ) -> bool:
        """Additionally reject a fresh adapter return dated after the live clock."""

        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise HostRuntimeError("host runtime clock must be timezone-aware")
        return self._receipt_time_is_bound(receipt, lease) and (
            require_time(receipt.observed_at, "receipt observed_at") <= now
        )

    def _live_lease_deadline(self, lease: HostLease) -> datetime:
        """Admit effects only inside the lease and runtime's exclusive interval."""

        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise HostRuntimeError("host runtime clock must be timezone-aware")
        issued = require_time(lease.issued_at, "lease issued_at")
        effective_deadline = min(
            require_time(lease.expires_at, "lease expires_at"),
            self.deadline,
        )
        if now < issued:
            raise HostRuntimeError("host lease is not yet valid")
        if now >= effective_deadline:
            raise HostRuntimeError("host lease has expired")
        return effective_deadline

    def _live_activation_deadline(
        self,
        authorization: AuthorizedOneRun,
        lease_deadline: datetime,
    ) -> datetime:
        """Recheck the full activation interval immediately before prepare."""

        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise HostRuntimeError("host runtime clock must be timezone-aware")
        effective_deadline = min(
            authorization.expires_at,
            lease_deadline,
            self.deadline,
        )
        if now < authorization.issued_at:
            raise HostRuntimeError("one-run authorization is not yet valid")
        if now >= effective_deadline:
            raise HostRuntimeError("one-run authorization deadline has expired")
        return effective_deadline

    def _validate_fresh_observation(
        self,
        observation: object,
        *,
        subject_id: str,
        admitted_at: datetime,
    ) -> HostObservation:
        if type(observation) is not HostObservation:
            raise HostRuntimeError("host returned an untyped observation")
        if observation.subject_id != subject_id:
            raise HostRuntimeError("host returned an observation for another subject")
        observed = require_time(observation.observed_at, "host observed_at")
        now = self.clock()
        if observed < admitted_at:
            raise HostRuntimeError("host returned a stale cached observation")
        if observed > now or observed > self.deadline:
            raise HostRuntimeError("host returned an observation from the future")
        return observation

    def poll(
        self,
        *,
        subject_id: str,
        idempotency_key: str,
        timeout_seconds: float = 30,
    ) -> HostObservation:
        require_digest(subject_id, "subject_id")
        self._remaining(timeout_seconds)
        intent, fresh = self._begin(
            key=idempotency_key,
            action="poll",
            request={"subject_id": subject_id},
            settle_timeout_seconds=timeout_seconds,
        )
        if not fresh:
            return _observation_from_document(self._response(intent, "observation"))
        try:
            admitted_at = self.clock()
            observation, elapsed = self._bounded(
                lambda: self.adapter.observe(subject_id=subject_id), timeout_seconds
            )
            observation = self._validate_fresh_observation(
                observation,
                subject_id=subject_id,
                admitted_at=admitted_at,
            )
            usage = HostUsage(
                elapsed,
                0,
                len(canonical_json_bytes(observation.to_document())),
            )
            record = self._finish(
                intent,
                state=HostOperationState.SUCCEEDED,
                response_type="observation",
                response=observation.to_document(),
                usage=usage,
            )
            return _observation_from_document(self._response(record, "observation"))
        except BaseException as error:
            usage = HostUsage(round(timeout_seconds * 1000), 0, 0)
            self._finish(
                intent,
                state=HostOperationState.RECOVERABLE,
                response_type=None,
                response=None,
                usage=usage,
                reason=f"poll outcome is unavailable: {type(error).__name__}",
            )
            if isinstance(error, HostRecoveryRequired):
                raise
            raise HostRecoveryRequired("host poll requires a new observation") from error

    def create(
        self,
        *,
        plan_bytes: bytes,
        standard_bytes: bytes,
        generation_id: str,
        lease_deadline: str,
        authorization: AuthorizedOneRun,
        idempotency_key: str,
        timeout_seconds: float = 30,
    ) -> HostLease:
        self._remaining(timeout_seconds)
        require_digest(generation_id, "generation_id")
        try:
            authorization = validate_authorized_one_run(authorization)
        except ActivationBundleError as error:
            raise HostRuntimeError(
                "host create requires a sealed one-run authorization"
            ) from error
        if type(plan_bytes) is not bytes or not plan_bytes:
            raise HostRuntimeError("host create requires immutable plan bytes")
        plan_digest = raw_sha256(plan_bytes)
        if authorization.plan_sha256 != plan_digest:
            raise HostRuntimeError("one-run authorization names another plan")
        try:
            plan = load_bound_plan(
                plan_bytes,
                expected_plan_digest=plan_digest,
                standard_bytes=standard_bytes,
            )
            compilation = compile_plan(
                plan_bytes,
                expected_plan_digest=plan_digest,
                standard_bytes=standard_bytes,
            )
            validate_activation_plan_binding(
                plan,
                request_sha256=authorization.request_sha256,
                repository_id=authorization.repository_id,
                candidate_parent_commit=authorization.candidate_parent_commit,
                candidate_parent_tree=authorization.candidate_parent_tree,
                target_branch=authorization.target_branch,
            )
        except (ContractViolation, TypeError, ValueError) as error:
            raise HostRuntimeError(
                "host create plan, standard, or activation binding is invalid: "
                + str(error)
            ) from error
        compilation_receipt = compilation.to_document()
        compilation_digest = compilation.digest
        subject_id = plan.subject.subject_id
        node_ids = tuple(node.node_id for node in plan.nodes)
        authority_digest = canonical_digest(
            [item.to_document() for item in plan.authority]
        )
        adapter_inventory_digest = canonical_digest(
            [item.to_document() for item in plan.adapters]
        )
        now = self.clock()
        if authorization.issued_at > now or authorization.expires_at <= now:
            raise HostRuntimeError("one-run authorization is outside its validity interval")
        if authorization.protected_merge_authorized is not False:
            raise HostRuntimeError("one-run authorization cannot permit protected merge")
        deadline = require_time(lease_deadline, "lease_deadline")
        if deadline <= now:
            raise HostRuntimeError("host lease deadline has expired")
        if deadline > self.deadline:
            raise HostRuntimeError("host lease exceeds the one-run deadline")
        if deadline > authorization.expires_at:
            raise HostRuntimeError("host lease exceeds the activation deadline")
        try:
            external_effects_required, required_capabilities = (
                validate_runtime_plan_admission(
                    plan,
                    execution_deadline=authorization.expires_at,
                )
            )
        except ContractViolation as error:
            raise HostRuntimeError(
                "signed plan authority or static budget is invalid: " + str(error)
            ) from error
        bound_capabilities = tuple(
            sorted({*required_capabilities, HOST_DEADLINE_CAPABILITY})
        )
        nonce_digest = "sha256:" + sha256(
            authorization.nonce.encode("utf-8")
        ).hexdigest()
        activation_proof = authorization.proof_document()
        request = {
            "plan_digest": plan_digest,
            "generation_id": generation_id,
            "authority_digest": authority_digest,
            "adapter_inventory_digest": adapter_inventory_digest,
            "external_effects_required": external_effects_required,
            "compilation_receipt": compilation_receipt,
            "subject_id": subject_id,
            "node_ids": list(node_ids),
            "nonce_digest": nonce_digest,
            "lease_deadline": lease_deadline,
            "activation_proof": activation_proof,
            "required_capabilities": list(bound_capabilities),
        }
        intent, fresh = self._begin(
            key=idempotency_key,
            action="create",
            request=request,
            semantic_kind="create",
            semantic_scope_digest=_create_scope(authorization),
            settle_timeout_seconds=timeout_seconds,
        )
        if not fresh:
            cached_lease = _lease_from_document(self._response(intent, "lease"))
            if not self.journal.authenticates_lease(cached_lease):
                raise HostRecoveryRequired(
                    "durable host lease authentication failed"
                )
            if self.journal.cancellation_claimed(cached_lease):
                raise HostRuntimeError(
                    "durable lease cancellation blocks create resume"
                )
            return self._freshly_validate_lease(
                cached_lease,
                poll_idempotency_key=canonical_digest(
                    {
                        "cached_create": idempotency_key,
                        "activation_proof_digest": authorization.proof_digest,
                    }
                ),
                timeout_seconds=timeout_seconds,
            )
        input_bytes = len(canonical_json_bytes(request))
        prepare_started = False
        try:
            admitted_at = self.clock()
            observation, first_elapsed = self._bounded(
                lambda: self.adapter.observe(subject_id=subject_id),
                timeout_seconds,
                operation_deadline=deadline,
            )
            observation = self._validate_fresh_observation(
                observation,
                subject_id=subject_id,
                admitted_at=admitted_at,
            )
            if not observation.clean:
                raise HostRuntimeError("host is dirty or bound to another subject")
            if observation.identity.adapter_digest != adapter_inventory_digest:
                raise HostRuntimeError(
                    "host adapter inventory differs from the signed plan"
                )
            missing = set(bound_capabilities) - set(observation.capabilities)
            if missing:
                raise HostRuntimeError("host lacks required capabilities: " + ", ".join(sorted(missing)))
            claim_time = self.clock().astimezone(UTC).isoformat().replace("+00:00", "Z")
            self.journal.claim_activation(
                authorization=authorization,
                create_idempotency_key=intent.idempotency_key,
                create_request=request,
                host_identity_digest=observation.identity.digest,
                claimed_at=claim_time,
                _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
            )
            def prepare_host() -> HostLease:
                nonlocal prepare_started
                self._live_activation_deadline(authorization, deadline)
                prepare_started = True
                return self.adapter.prepare(
                    plan_digest=plan_digest,
                    generation_id=generation_id,
                    authority_digest=authority_digest,
                    adapter_inventory_digest=adapter_inventory_digest,
                    external_effects_required=external_effects_required,
                    compilation_receipt=compilation_receipt,
                    subject_id=subject_id,
                    node_ids=node_ids,
                    nonce_digest=nonce_digest,
                    lease_deadline=lease_deadline,
                    authorization=authorization,
                    required_capabilities=bound_capabilities,
                )

            lease, second_elapsed = self._bounded(
                prepare_host,
                max(0.001, timeout_seconds - first_elapsed / 1000),
                operation_deadline=deadline,
            )
            if (
                type(lease) is not HostLease
                or lease.host_id != observation.identity.host_id
                or lease.subject_id != subject_id
                or lease.generation_id != generation_id
                or lease.authority_digest != authority_digest
                or lease.adapter_inventory_digest != adapter_inventory_digest
                or lease.external_effects_required is not external_effects_required
                or lease.compilation_digest != compilation_digest
                or lease.activation_digest != authorization.activation_digest
                or lease.activation_proof_digest != authorization.proof_digest
                or lease.candidate_commit != authorization.candidate_commit
                or lease.candidate_tree != authorization.candidate_tree
                or lease.candidate_content_sha256
                != authorization.candidate_content_sha256
                or lease.candidate_parent_commit
                != authorization.candidate_parent_commit
                or lease.candidate_parent_tree
                != authorization.candidate_parent_tree
                or lease.manifest_sha256 != authorization.manifest_sha256
                or lease.repository_id != authorization.repository_id
                or lease.request_sha256 != authorization.request_sha256
                or lease.target_branch != authorization.target_branch
                or lease.execution_client_sha256
                != authorization.execution_client_sha256
                or lease.activation_issued_at
                != authorization.issued_at.astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z")
                or lease.protected_merge_authorized
                is not authorization.protected_merge_authorized
                or lease.host_identity_digest != observation.identity.digest
                or lease.trust_evidence_digest
                != observation.trust_evidence_digest
                or lease.required_capabilities != bound_capabilities
                or lease.allowed_node_ids != node_ids
                or lease.nonce_digest != nonce_digest
                or require_time(lease.issued_at, "lease issued_at")
                < require_time(observation.observed_at, "host observed_at")
                or require_time(lease.issued_at, "lease issued_at") > self.clock()
                or require_time(lease.expires_at, "lease expires_at") > deadline
            ):
                raise HostRuntimeError("host returned a lease outside the exact request")
            usage = HostUsage(
                first_elapsed + second_elapsed,
                input_bytes,
                len(canonical_json_bytes(lease.to_document())),
            )
            record = self._finish(
                intent,
                state=HostOperationState.SUCCEEDED,
                response_type="lease",
                response=lease.to_document(),
                usage=usage,
            )
            return _lease_from_document(self._response(record, "lease"))
        except HostRuntimeError as error:
            # A local precondition failure before prepare is DENIED. Once
            # prepare starts, even a malformed response can hide a completed
            # reservation and therefore requires external adoption.
            usage = HostUsage(0, input_bytes, 0)
            self._finish(
                intent,
                state=(
                    HostOperationState.RECOVERABLE
                    if prepare_started or isinstance(error, HostRecoveryRequired)
                    else HostOperationState.DENIED
                ),
                response_type=None,
                response=None,
                usage=usage,
                reason=str(error),
            )
            if prepare_started or isinstance(error, HostRecoveryRequired):
                raise HostRecoveryRequired("host lease outcome requires adoption") from error
            raise
        except BaseException as error:
            usage = HostUsage(0, input_bytes, 0)
            self._finish(
                intent,
                state=HostOperationState.RECOVERABLE,
                response_type=None,
                response=None,
                usage=usage,
                reason=f"host lease outcome is ambiguous: {type(error).__name__}",
            )
            raise HostRecoveryRequired("host lease outcome requires adoption") from error

    def message(
        self,
        *,
        lease: HostLease,
        node_id: str,
        input_bytes: bytes,
        idempotency_key: str,
        timeout_seconds: float = 60,
    ) -> HostExecutionReceipt:
        """Deliver one exact node envelope; this is the host message boundary."""

        self._remaining(timeout_seconds)
        if type(input_bytes) is not bytes or not input_bytes:
            raise HostRuntimeError("host input must be non-empty immutable bytes")
        if not self.journal.authenticates_lease(lease):
            raise HostRuntimeError(
                "host message requires the exact journal-authenticated lease"
            )
        if node_id not in lease.allowed_node_ids:
            raise HostRuntimeError("node is outside the host lease")
        effect_deadline = self._live_lease_deadline(lease)
        input_digest = _bytes_digest(input_bytes)
        request = {
            "lease": lease.to_document(),
            "node_id": node_id,
            "input_digest": input_digest,
        }
        intent, fresh = self._begin(
            key=idempotency_key,
            action="message",
            request=request,
            lease=lease,
            deny_after_cancellation=True,
            semantic_kind="message",
            semantic_scope_digest=_message_scope(lease, node_id),
            settle_timeout_seconds=timeout_seconds,
        )
        if not fresh:
            return _receipt_from_document(self._response(intent, "execution-receipt"))
        try:
            receipt, elapsed = self._bounded(
                lambda: self.adapter.execute(
                    node_id=node_id,
                    input_bytes=input_bytes,
                    lease=lease,
                ),
                timeout_seconds,
                operation_deadline=effect_deadline,
            )
            if (
                type(receipt) is not HostExecutionReceipt
                or receipt.lease_id != lease.lease_id
                or receipt.node_id != node_id
                or receipt.input_digest != input_digest
                or not self._fresh_receipt_time_is_bound(receipt, lease)
            ):
                raise HostRecoveryRequired("host execution receipt is not bound to the request")
            usage = HostUsage(
                elapsed,
                len(input_bytes),
                len(canonical_json_bytes(receipt.to_document())),
            )
            record = self._finish(
                intent,
                state=HostOperationState.SUCCEEDED,
                response_type="execution-receipt",
                response=receipt.to_document(),
                usage=usage,
            )
            return _receipt_from_document(self._response(record, "execution-receipt"))
        except BaseException as error:
            usage = HostUsage(round(timeout_seconds * 1000), len(input_bytes), 0)
            self._finish(
                intent,
                state=HostOperationState.RECOVERABLE,
                response_type=None,
                response=None,
                usage=usage,
                reason=f"host execution outcome is ambiguous: {type(error).__name__}",
            )
            raise HostRecoveryRequired("host execution outcome requires adoption") from error

    execute = message

    def checkpoint(
        self,
        *,
        lease: HostLease,
        receipt: HostExecutionReceipt,
        checkpoint_digest: str,
        candidate_digest: str | None,
        idempotency_key: str,
    ) -> HostCheckpoint:
        """Seal executor evidence for an exact durable host message receipt.

        This is a journal-local operation: it never invokes the host adapter and
        remains available after lease expiry so an interrupted executor can
        close the message-to-checkpoint crash window without repeating an
        effect.
        """

        if not self.journal.authenticates_lease(lease):
            raise HostRuntimeError(
                "checkpoint requires the exact journal-authenticated lease"
            )
        if receipt.lease_id != lease.lease_id or receipt.node_id not in lease.allowed_node_ids:
            raise HostRuntimeError("checkpoint receipt is outside the host lease")
        if receipt.state is not HostReceiptState.SUCCEEDED:
            raise HostRuntimeError("only a successful host result may checkpoint")
        if candidate_digest != receipt.output_digest:
            raise HostRuntimeError(
                "checkpoint candidate must equal the authenticated host output"
            )
        if not self.journal.authenticates_message_receipt(lease, receipt):
            raise HostRuntimeError(
                "checkpoint requires a journal-authenticated host message receipt"
            )
        expected_checkpoint_digest = canonical_checkpoint_digest(lease, receipt)
        if checkpoint_digest != expected_checkpoint_digest:
            raise HostRuntimeError(
                "checkpoint digest differs from the canonical host result"
            )
        checkpoint = HostCheckpoint(
            lease_id=lease.lease_id,
            node_id=receipt.node_id,
            input_digest=receipt.input_digest,
            checkpoint_digest=checkpoint_digest,
            candidate_digest=candidate_digest,
        )
        request = checkpoint.to_document()
        intent, fresh = self._begin(
            key=idempotency_key,
            action="checkpoint",
            request=request,
            semantic_kind="checkpoint",
            semantic_scope_digest=_checkpoint_scope(lease, receipt),
        )
        if not fresh:
            return _checkpoint_from_document(self._response(intent, "checkpoint"))
        encoded = canonical_json_bytes(request)
        record = self._finish(
            intent,
            state=HostOperationState.SUCCEEDED,
            response_type="checkpoint",
            response=request,
            usage=HostUsage(0, len(encoded), len(encoded)),
        )
        return _checkpoint_from_document(self._response(record, "checkpoint"))

    def cancel(
        self,
        *,
        lease: HostLease,
        reason: str,
        idempotency_key: str,
        timeout_seconds: float = 30,
    ) -> HostExecutionReceipt:
        self._remaining(timeout_seconds)
        if not isinstance(reason, str) or not reason.strip():
            raise HostRuntimeError("cancellation reason is required")
        if not self.journal.authenticates_lease(lease):
            raise HostRuntimeError(
                "host cancellation requires the exact journal-authenticated lease"
            )
        effect_deadline = self._live_lease_deadline(lease)
        request = {"lease": lease.to_document(), "reason": reason}
        intent, fresh = self._begin(
            key=idempotency_key,
            action="cancel",
            request=request,
            lease=lease,
            claim_cancellation_at=self.clock()
            .astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            semantic_kind="cancel",
            semantic_scope_digest=_cancel_scope(lease),
            settle_timeout_seconds=timeout_seconds,
        )
        if not fresh:
            return _receipt_from_document(self._response(intent, "execution-receipt"))
        try:
            receipt, elapsed = self._bounded(
                lambda: self.adapter.cancel(lease=lease, reason=reason),
                timeout_seconds,
                operation_deadline=effect_deadline,
            )
            if (
                type(receipt) is not HostExecutionReceipt
                or receipt.lease_id != lease.lease_id
                or receipt.node_id not in lease.allowed_node_ids
                or receipt.state is not HostReceiptState.CANCELLED
                or receipt.input_digest != canonical_digest({"reason": reason})
                or not self._fresh_receipt_time_is_bound(receipt, lease)
            ):
                raise HostRecoveryRequired("host cancellation receipt is invalid")
            record = self.journal.finish_cancellation(
                intent,
                lease=lease,
                receipt=receipt,
                usage=HostUsage(
                    elapsed,
                    len(canonical_json_bytes(request)),
                    len(canonical_json_bytes(receipt.to_document())),
                ),
                committed_at=self.clock()
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
            )
            return _receipt_from_document(self._response(record, "execution-receipt"))
        except BaseException as error:
            self._finish(
                intent,
                state=HostOperationState.RECOVERABLE,
                response_type=None,
                response=None,
                usage=HostUsage(round(timeout_seconds * 1000), len(canonical_json_bytes(request)), 0),
                reason=f"host cancellation outcome is ambiguous: {type(error).__name__}",
            )
            raise HostRecoveryRequired("host cancellation outcome requires adoption") from error

    def _freshly_validate_lease(
        self,
        lease: HostLease,
        *,
        poll_idempotency_key: str,
        timeout_seconds: float,
    ) -> HostLease:
        self._live_lease_deadline(lease)
        if self.journal.cancellation_claimed(lease):
            raise HostRuntimeError("durable lease cancellation blocks resume")
        # Observation is read-only, so every validation attempt deliberately
        # gets a new journal identity. Reusing a stable caller key could replay
        # a cached observation and conceal host drift across process restarts.
        fresh_poll_key = canonical_digest(
            {
                "resume_poll_base": poll_idempotency_key,
                "attempt_nonce": secrets.token_hex(32),
            }
        )
        observation = self.poll(
            subject_id=lease.subject_id,
            idempotency_key=fresh_poll_key,
            timeout_seconds=timeout_seconds,
        )
        if (
            require_time(observation.observed_at, "host observed_at")
            < require_time(lease.issued_at, "lease issued_at")
            or observation.identity.host_id != lease.host_id
            or observation.identity.digest != lease.host_identity_digest
            or observation.identity.adapter_digest
            != lease.adapter_inventory_digest
            or observation.trust_evidence_digest != lease.trust_evidence_digest
            or not set(lease.required_capabilities).issubset(
                observation.capabilities
            )
            or not observation.clean
        ):
            raise HostRecoveryRequired("durable lease host identity drifted")
        if self.journal.cancellation_claimed(lease):
            raise HostRuntimeError("durable lease cancellation blocks resume")
        return lease

    def resume(
        self,
        *,
        create_idempotency_key: str,
        poll_idempotency_key: str,
        timeout_seconds: float = 30,
    ) -> HostLease:
        """Rehydrate a durable lease and verify the same clean host still owns it."""

        if not isinstance(poll_idempotency_key, str) or not poll_idempotency_key.strip():
            raise HostRuntimeError("resume poll idempotency key is required")
        record = self.journal.latest(create_idempotency_key)
        if record is None:
            raise HostRuntimeError("no durable host lease exists")
        lease = _lease_from_document(self._response(record, "lease"))
        if not self.journal.authenticates_lease(lease):
            raise HostRecoveryRequired("durable host lease authentication failed")
        return self._freshly_validate_lease(
            lease,
            poll_idempotency_key=poll_idempotency_key,
            timeout_seconds=timeout_seconds,
        )

    def resume_for_reconciliation(
        self,
        *,
        create_idempotency_key: str,
        poll_idempotency_key: str,
        timeout_seconds: float = 30,
    ) -> HostLease:
        """Re-observe a historical lease without granting a new host effect.

        Expiry still blocks ``create``, ``message``, ``cancel``, and ordinary
        ``resume``.  This path exists only so an already-recorded ambiguous
        effect can be authenticated, adopted, and checkpointed after expiry.
        """

        return self._historical_observer.resume(
            create_idempotency_key=create_idempotency_key,
            poll_idempotency_key=poll_idempotency_key,
            timeout_seconds=timeout_seconds,
        )

    def historical_message_success(
        self,
        *,
        lease: HostLease,
        node_id: str,
        input_digest: str,
    ) -> HostExecutionReceipt | None:
        """Read one exact durable successful message without a host effect."""

        require_identifier(node_id, "historical node_id")
        require_digest(input_digest, "historical input_digest")
        if not self.journal.authenticates_lease(lease):
            raise HostRuntimeError(
                "historical recovery requires the exact authenticated lease"
            )
        message_request_digest = canonical_digest(
            {
                "lease": lease.to_document(),
                "node_id": node_id,
                "input_digest": input_digest,
            }
        )
        for record in self.journal.records():
            if (
                record.action == "message"
                and record.request_digest == message_request_digest
                and record.state is HostOperationState.SUCCEEDED
                and record.response_type == "execution-receipt"
                and record.response is not None
            ):
                candidate = _receipt_from_document(record.response)
                if (
                    candidate.state is HostReceiptState.SUCCEEDED
                    and candidate.lease_id == lease.lease_id
                    and candidate.node_id == node_id
                    and candidate.input_digest == input_digest
                    and candidate.output_digest is not None
                    and self._receipt_time_is_bound(candidate, lease)
                    and self.journal.authenticates_message_receipt(
                        lease, candidate
                    )
                ):
                    return candidate
        return None

    def historical_checkpoint(
        self,
        *,
        lease: HostLease,
        receipt: HostExecutionReceipt,
        checkpoint_digest: str,
        candidate_digest: str | None,
    ) -> HostCheckpoint | None:
        """Read one exact durable checkpoint without mutating the journal."""

        require_digest(checkpoint_digest, "historical checkpoint_digest")
        if candidate_digest is not None:
            require_digest(candidate_digest, "historical candidate_digest")
        if (
            not self.journal.authenticates_lease(lease)
            or receipt.lease_id != lease.lease_id
            or receipt.node_id not in lease.allowed_node_ids
            or receipt.state is not HostReceiptState.SUCCEEDED
            or candidate_digest != receipt.output_digest
            or not self.journal.authenticates_message_receipt(lease, receipt)
        ):
            raise HostRuntimeError(
                "historical checkpoint requires an authenticated message receipt"
            )
        expected = HostCheckpoint(
            lease_id=lease.lease_id,
            node_id=receipt.node_id,
            input_digest=receipt.input_digest,
            checkpoint_digest=checkpoint_digest,
            candidate_digest=candidate_digest,
        )
        expected_document = expected.to_document()
        expected_request_digest = canonical_digest(expected_document)
        for record in self.journal.records():
            if (
                record.action == "checkpoint"
                and record.request_digest == expected_request_digest
                and record.state is HostOperationState.SUCCEEDED
                and record.response_type == "checkpoint"
                and record.response is not None
            ):
                checkpoint = _checkpoint_from_document(record.response)
                if checkpoint.to_document() == expected_document:
                    return checkpoint
        return None

    def historical_success(
        self,
        *,
        lease: HostLease,
        node_id: str,
        input_digest: str,
    ) -> tuple[HostExecutionReceipt, HostCheckpoint] | None:
        """Read the sole canonical durable message/checkpoint pair, if complete."""

        receipt = self.historical_message_success(
            lease=lease,
            node_id=node_id,
            input_digest=input_digest,
        )
        if receipt is None or receipt.output_digest is None:
            return None
        checkpoint = self.historical_checkpoint(
            lease=lease,
            receipt=receipt,
            checkpoint_digest=canonical_checkpoint_digest(lease, receipt),
            candidate_digest=receipt.output_digest,
        )
        return None if checkpoint is None else (receipt, checkpoint)

    def historical_cancellation(
        self,
        *,
        lease: HostLease,
        reason: str,
    ) -> HostExecutionReceipt | None:
        """Read one committed exact cancellation without calling the adapter."""

        if type(reason) is not str or not reason.strip():
            raise HostRuntimeError("historical cancellation reason is required")
        cancellation = self.committed_cancellation(lease)
        if cancellation is None:
            raise HostRuntimeError(
                "historical cancellation requires an authenticated lease stop"
            )
        durable_reason, receipt = cancellation
        if durable_reason != reason:
            raise HostRuntimeError(
                "historical cancellation reason differs from the durable claim"
            )
        return receipt

    def committed_cancellation(
        self, lease: HostLease
    ) -> tuple[str, HostExecutionReceipt] | None:
        """Return an exact committed cancellation, or fail on ambiguity."""

        if not self.journal.authenticates_lease(lease):
            raise HostRuntimeError(
                "historical cancellation requires an authenticated lease"
            )
        result = self.journal.cancellation_result(lease)
        if result is None:
            return None
        reason, receipt = result
        if receipt is None:
            raise HostRecoveryRequired(
                "durable lease cancellation is claimed but not committed"
            )
        if (
            receipt.state is not HostReceiptState.CANCELLED
            or receipt.lease_id != lease.lease_id
            or receipt.node_id not in lease.allowed_node_ids
            or receipt.input_digest != canonical_digest({"reason": reason})
            or not self._receipt_time_is_bound(receipt, lease)
        ):
            raise HostRuntimeError(
                "committed cancellation is not bound to its lease and reason"
            )
        return reason, receipt

    def seal_completion(self, lease: HostLease) -> str | None:
        """Atomically choose proven completion or an earlier cancellation.

        ``None`` means completion owns the lease terminal. A string is the
        exact durable reason of a committed cancellation. An ambiguous
        cancellation raises ``HostRecoveryRequired`` and can never be
        overwritten by completion.
        """

        if not self.journal.authenticates_lease(lease):
            raise HostRuntimeError(
                "host completion requires the exact authenticated lease"
            )
        cancellation = self.committed_cancellation(lease)
        if cancellation is not None:
            return cancellation[0]

        successful_nodes: set[str] = set()
        for record in self.journal.records():
            if (
                record.action != "message"
                or record.state is not HostOperationState.SUCCEEDED
                or record.response_type != "execution-receipt"
                or record.response is None
            ):
                continue
            receipt = _receipt_from_document(record.response)
            if receipt.lease_id != lease.lease_id:
                continue
            if (
                receipt.node_id not in lease.allowed_node_ids
                or receipt.state is not HostReceiptState.SUCCEEDED
                or receipt.output_digest is None
                or not self._receipt_time_is_bound(receipt, lease)
                or not self.journal.authenticates_message_receipt(lease, receipt)
            ):
                raise HostRuntimeError(
                    "host completion contains an invalid message result"
                )
            checkpoint = self.historical_checkpoint(
                lease=lease,
                receipt=receipt,
                checkpoint_digest=canonical_checkpoint_digest(lease, receipt),
                candidate_digest=receipt.output_digest,
            )
            if checkpoint is None:
                raise HostRuntimeError(
                    "host completion lacks the canonical checkpoint proof"
                )
            successful_nodes.add(receipt.node_id)
        if successful_nodes != set(lease.allowed_node_ids):
            raise HostRuntimeError(
                "host completion lacks a successful result for every leased node"
            )

        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise HostRuntimeError("host runtime clock must be timezone-aware")
        owns_completion = self.journal.claim_completion(
            lease,
            claimed_at=now.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
        )
        if owns_completion:
            return None
        cancellation = self.committed_cancellation(lease)
        if cancellation is None:
            raise HostRuntimeError(
                "host terminal ordering changed without a cancellation claim"
            )
        return cancellation[0]

    def adopt(
        self,
        *,
        operation_idempotency_key: str,
        request: Mapping[str, Any],
        response_type: str,
        response: HostLease | HostExecutionReceipt,
        evidence_digest: str,
    ) -> HostLease | HostExecutionReceipt:
        with self.journal.adoption_guard():
            return self._adopt_locked(
                operation_idempotency_key=operation_idempotency_key,
                request=request,
                response_type=response_type,
                response=response,
                evidence_digest=evidence_digest,
            )

    def _adopt_locked(
        self,
        *,
        operation_idempotency_key: str,
        request: Mapping[str, Any],
        response_type: str,
        response: HostLease | HostExecutionReceipt,
        evidence_digest: str,
    ) -> HostLease | HostExecutionReceipt:
        """Resolve an ambiguous operation from explicit exact host evidence."""

        require_digest(evidence_digest, "adoption evidence_digest")
        request_lease: HostLease | None = None
        lease_value = request.get("lease")
        if isinstance(lease_value, Mapping):
            try:
                request_lease = _lease_from_document(lease_value)
            except (HostRuntimeError, TypeError, ValueError):
                request_lease = None
        current = self.journal.latest(operation_idempotency_key)
        if current is None:
            semantic_kind: str | None = None
            semantic_scope: str | None = None
            if response_type == "lease":
                proof = request.get("activation_proof")
                activation_digest = (
                    proof.get("activation_digest")
                    if isinstance(proof, Mapping)
                    else None
                )
                if type(activation_digest) is str:
                    semantic_kind = "create"
                    semantic_scope = activation_digest
            elif response_type == "execution-receipt" and request_lease is not None:
                if "node_id" in request and "input_digest" in request:
                    semantic_kind = "message"
                    semantic_scope = _message_scope(
                        request_lease, str(request.get("node_id"))
                    )
                elif "reason" in request:
                    semantic_kind = "cancel"
                    semantic_scope = _cancel_scope(request_lease)
            if semantic_kind is not None and semantic_scope is not None:
                current = self.journal.bind_semantic_alias(
                    alias_key=operation_idempotency_key,
                    kind=semantic_kind,
                    scope_digest=semantic_scope,
                    request=request,
                    _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
                )
        if current is not None and current.state is HostOperationState.SUCCEEDED:
            if (
                canonical_digest(dict(request)) != current.request_digest
                or current.response_type != response_type
                or current.response is None
                or dict(current.response) != response.to_document()
            ):
                raise HostRuntimeError(
                    "completed host adoption cannot be rebound"
                )
            if not self.journal.adoption_matches(
                operation=current,
                response_type=response_type,
                response=response.to_document(),
                evidence_digest=evidence_digest,
            ):
                raise HostRuntimeError(
                    "completed host adoption lacks the exact durable evidence proof"
                )
            if response_type == "lease":
                return _lease_from_document(current.response)
            if response_type == "execution-receipt":
                return _receipt_from_document(current.response)
            raise HostRuntimeError("completed host adoption has an unknown response type")
        if current is None or current.state not in {
            HostOperationState.INTENT_RECORDED,
            HostOperationState.RECOVERABLE,
        }:
            raise HostRuntimeError("host operation is not adoptable")
        if canonical_digest(dict(request)) != current.request_digest:
            raise HostRuntimeError("adoption request differs from the durable host intent")
        if response_type == "lease" and type(response) is HostLease:
            document = response.to_document()
            activation_proof = request.get("activation_proof")
            proof_nonce = (
                activation_proof.get("nonce")
                if isinstance(activation_proof, Mapping)
                else None
            )
            compilation_receipt = request.get("compilation_receipt")
            if (
                current.action != "create"
                or not isinstance(activation_proof, Mapping)
                or not isinstance(compilation_receipt, Mapping)
                or type(proof_nonce) is not str
                or request.get("plan_digest")
                != activation_proof.get("plan_sha256")
                or request.get("nonce_digest")
                != _bytes_digest(proof_nonce.encode("utf-8"))
                or response.subject_id != request.get("subject_id")
                or response.generation_id != request.get("generation_id")
                or response.authority_digest != request.get("authority_digest")
                or response.adapter_inventory_digest
                != request.get("adapter_inventory_digest")
                or response.external_effects_required
                is not request.get("external_effects_required")
                or response.compilation_digest
                != canonical_digest(dict(compilation_receipt))
                or response.activation_digest
                != activation_proof.get("activation_digest")
                or response.activation_proof_digest
                != canonical_digest(dict(activation_proof))
                or response.candidate_commit
                != activation_proof.get("candidate_commit")
                or response.candidate_tree != activation_proof.get("candidate_tree")
                or response.candidate_content_sha256
                != activation_proof.get("candidate_content_sha256")
                or response.candidate_parent_commit
                != activation_proof.get("candidate_parent_commit")
                or response.candidate_parent_tree
                != activation_proof.get("candidate_parent_tree")
                or response.manifest_sha256
                != activation_proof.get("manifest_sha256")
                or response.repository_id != activation_proof.get("repository_id")
                or response.request_sha256 != activation_proof.get("request_sha256")
                or response.target_branch != activation_proof.get("target_branch")
                or response.execution_client_sha256
                != activation_proof.get("execution_client_sha256")
                or response.activation_issued_at
                != activation_proof.get("issued_at")
                or response.protected_merge_authorized
                is not activation_proof.get("protected_merge_authorized")
                or list(response.required_capabilities)
                != request.get("required_capabilities")
                or list(response.allowed_node_ids) != request.get("node_ids")
                or response.nonce_digest != request.get("nonce_digest")
                or require_time(response.expires_at, "adopted lease expires_at")
                > require_time(str(request.get("lease_deadline")), "lease_deadline")
                or require_time(response.expires_at, "adopted lease expires_at")
                > require_time(
                    str(activation_proof.get("expires_at")),
                    "activation expires_at",
                )
                or require_time(response.issued_at, "adopted lease issued_at")
                > self.clock()
            ):
                raise HostRuntimeError("adopted lease is not bound to the durable request")
            result: HostLease | HostExecutionReceipt = response
        elif response_type == "execution-receipt" and type(response) is HostExecutionReceipt:
            document = response.to_document()
            if (
                current.action not in {"message", "cancel"}
                or request_lease is None
                or not self.journal.authenticates_lease(request_lease)
                or response.lease_id != request_lease.lease_id
                or not self._receipt_time_is_bound(response, request_lease)
                or (
                    current.action == "message"
                    and (
                        response.node_id != request.get("node_id")
                        or response.input_digest != request.get("input_digest")
                    )
                )
                or (
                    current.action == "cancel"
                    and (
                        response.state is not HostReceiptState.CANCELLED
                        or response.node_id not in request_lease.allowed_node_ids
                        or response.input_digest
                        != canonical_digest({"reason": request.get("reason")})
                    )
                )
            ):
                raise HostRuntimeError("adopted receipt is not bound to the durable request")
            result = response
        else:
            raise HostRuntimeError("adopted response type does not match response")
        if self.adoption_verifier is None or not self.adoption_verifier(
            action=current.action,
            request=dict(request),
            response_type=response_type,
            response=document,
            evidence_digest=evidence_digest,
        ):
            raise HostRuntimeError("adoption evidence was not authenticated")
        if current.action == "create":
            assert isinstance(result, HostLease)
            if not self.journal.authenticates_create_claim(
                create_idempotency_key=current.idempotency_key,
                create_request=request,
                lease=result,
            ):
                raise HostRuntimeError(
                    "adopted lease lacks its runtime-issued activation claim"
                )
        self.journal.claim_adoption(
            operation=current,
            response_type=response_type,
            response=document,
            evidence_digest=evidence_digest,
            _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
        )
        adoption_reason = (
            "ambiguous host outcome adopted from exact external evidence "
            + evidence_digest
        )
        adoption_usage = HostUsage(0, 0, len(canonical_json_bytes(document)))
        if current.action == "cancel":
            assert isinstance(result, HostExecutionReceipt)
            assert request_lease is not None
            self.journal.finish_cancellation(
                current,
                lease=request_lease,
                receipt=result,
                usage=adoption_usage,
                committed_at=self.clock()
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                reason=adoption_reason,
                _runtime_authority=_RUNTIME_JOURNAL_AUTHORITY,
            )
        else:
            self._finish(
                current,
                state=HostOperationState.SUCCEEDED,
                response_type=response_type,
                response=document,
                usage=adoption_usage,
                reason=adoption_reason,
            )
        # Store only contract fields in the typed return; the evidence digest is
        # retained in the journal response and does not alter the host contract.
        return result

    def usage(self) -> HostUsage:
        wall = inputs = outputs = 0
        model_input: int | None = 0
        model_output: int | None = 0
        seen: set[str] = set()
        for row in self.journal._rows():
            record = self.journal._decode(row)
            if record.idempotency_key in seen or record.usage is None:
                continue
            # Latest final usage wins; intents have no usage. Build via public
            # history to keep tamper verification in the accounting path.
            final = self.journal.latest(record.idempotency_key)
            if final is None or final.usage is None:
                continue
            seen.add(record.idempotency_key)
            usage = final.usage
            wall += usage.wall_milliseconds
            inputs += usage.input_bytes
            outputs += usage.output_bytes
            if usage.model_input_tokens is None:
                model_input = None
            elif model_input is not None:
                model_input += usage.model_input_tokens
            if usage.model_output_tokens is None:
                model_output = None
            elif model_output is not None:
                model_output += usage.model_output_tokens
        return HostUsage(wall, inputs, outputs, model_input, model_output)


__all__ = [
    "HostCheckpoint",
    "HostOperationJournal",
    "HostOperationRecord",
    "HostOperationState",
    "HostRecoveryRequired",
    "HostRuntime",
    "HostRuntimeError",
    "HostUsage",
    "AdoptionVerifier",
]
