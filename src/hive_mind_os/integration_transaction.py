"""One-shot, compare-and-swap integration of ordered sealed candidates.

The module does not implement Git merging.  A caller supplies an adapter whose
single atomic primitive advances an exact target identity.  The runtime records
the complete intent before that primitive is invoked and resolves every lost
response by observation; it never guesses that an effect did or did not happen.

The caller-supplied wave manifest is content-addressed and self-consistent; its
self-hash does not authenticate its origin.  The supplied candidate journal
likewise proves internal append-only consistency, not an external issuer.  Their
order can shape evidence metadata, but cannot authorize or change the exact CAS
target, which comes from ``AuthorizedOneRun``.  The target protocol advances
only that exact identity; it does not merge the supplied contributions.

The wave manifest also does not claim to carry per-wave copies of every plan
contract, resource, context, test, budget, effect policy, or authenticated
``GenerationRecord``.  Those remain signed-plan/runtime-receipt obligations.
Adding such fields requires a versioned wave-manifest contract and an
authenticated runtime receipt chain.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from threading import Condition, RLock
from time import monotonic
from typing import Any, Callable, Iterator, Mapping, Protocol, Sequence

from .activation_bundle import (
    ActivationBundleError,
    AuthorizedOneRun,
    validate_authorized_one_run,
)
from .brain_kernel.candidate_state import (
    CandidateSnapshot,
    CandidateStateError,
    CandidateStateJournal,
)
from .brain_kernel.canonical import canonical_bytes, canonical_digest
from .dag_standard import load_bound_plan
from .runtime_contracts import (
    ContractViolation,
    WaveState,
    require_identifier,
    require_time,
    requires_external_authority,
    strict_json_object,
)
from .wave_manifest import CandidateIdentity, WaveManifest, WaveNodeState


class IntegrationError(RuntimeError):
    """An integration precondition, history, or target observation is invalid."""


class IntegrationState(StrEnum):
    PREPARED = "PREPARED"
    EXECUTING = "EXECUTING"
    COMMITTED = "COMMITTED"
    RECOVERABLE = "RECOVERABLE"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"
    CANCELLED = "CANCELLED"


_TERMINAL = {
    IntegrationState.COMMITTED,
    IntegrationState.REPLAN_REQUIRED,
    IntegrationState.CANCELLED,
}

_TRANSITIONS: Mapping[IntegrationState, frozenset[IntegrationState]] = {
    IntegrationState.PREPARED: frozenset(
        {
            IntegrationState.EXECUTING,
            IntegrationState.REPLAN_REQUIRED,
            IntegrationState.CANCELLED,
        }
    ),
    IntegrationState.EXECUTING: frozenset(
        {
            IntegrationState.COMMITTED,
            IntegrationState.RECOVERABLE,
            IntegrationState.REPLAN_REQUIRED,
        }
    ),
    IntegrationState.RECOVERABLE: frozenset(
        {
            IntegrationState.COMMITTED,
            IntegrationState.RECOVERABLE,
            IntegrationState.REPLAN_REQUIRED,
            IntegrationState.CANCELLED,
        }
    ),
    IntegrationState.COMMITTED: frozenset({IntegrationState.COMMITTED}),
    IntegrationState.REPLAN_REQUIRED: frozenset(
        {IntegrationState.REPLAN_REQUIRED, IntegrationState.CANCELLED}
    ),
    IntegrationState.CANCELLED: frozenset({IntegrationState.CANCELLED}),
}

_COORDINATOR_EVENT_AUTHORITY = object()


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 digest")
    return value


def _target_snapshot_digest(identity: CandidateIdentity) -> str:
    return canonical_digest({"commit": identity.commit, "tree": identity.tree})


def _raw_digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _require_authorization(
    value: object,
    *,
    now: datetime,
    require_live: bool = True,
) -> AuthorizedOneRun:
    try:
        authorization = validate_authorized_one_run(value)
    except ActivationBundleError as error:
        raise IntegrationError(
            "integration requires a genuine AuthorizedOneRun capability"
        ) from error
    if require_live:
        if now.tzinfo is None or now.utcoffset() is None:
            raise IntegrationError("integration clock must be timezone-aware")
        current_time = now.astimezone(UTC)
        if current_time < authorization.issued_at.astimezone(UTC):
            raise IntegrationError("integration authorization is not yet valid")
        if current_time >= authorization.expires_at.astimezone(UTC):
            raise IntegrationError("integration authorization is stale")
    return authorization


@dataclass(frozen=True, slots=True)
class CandidateContribution:
    candidate_id: str
    node_id: str
    identity: CandidateIdentity
    verification_receipt_digest: str

    def __post_init__(self) -> None:
        _required(self.candidate_id, "candidate_id")
        _required(self.node_id, "node_id")
        if not isinstance(self.identity, CandidateIdentity):
            raise ValueError("identity must be a CandidateIdentity")
        _digest(self.verification_receipt_digest, "verification_receipt_digest")

    def to_document(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "node_id": self.node_id,
            "identity": self.identity.to_document(),
            "verification_receipt_digest": self.verification_receipt_digest,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> CandidateContribution:
        if set(value) != {
            "candidate_id",
            "node_id",
            "identity",
            "verification_receipt_digest",
        } or not isinstance(value.get("identity"), Mapping):
            raise IntegrationError("candidate contribution is malformed")
        try:
            return cls(
                candidate_id=value["candidate_id"],
                node_id=value["node_id"],
                identity=CandidateIdentity.from_document(value["identity"]),
                verification_receipt_digest=value["verification_receipt_digest"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrationError("candidate contribution is invalid") from error


@dataclass(frozen=True, slots=True)
class IntegrationTargetBinding:
    """Host-observed identity for the adapter holding the mutating primitive."""

    adapter_id: str
    interface: str
    version: str
    configuration_digest: str
    trust_digest: str
    protected_target: bool | None

    def __post_init__(self) -> None:
        require_identifier(self.adapter_id, "adapter_id")
        require_identifier(self.interface, "adapter interface")
        require_identifier(self.version, "adapter version")
        _digest(self.configuration_digest, "configuration_digest")
        _digest(self.trust_digest, "trust_digest")
        if self.protected_target is not None and type(self.protected_target) is not bool:
            raise ValueError("protected_target must be a boolean or unknown")

    def to_document(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "interface": self.interface,
            "version": self.version,
            "configuration_digest": self.configuration_digest,
            "trust_digest": self.trust_digest,
            "protected_target": self.protected_target,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class IntegrationTransaction:
    transaction_id: str
    round_id: str
    target_ref: str
    expected_target: CandidateIdentity
    proposed_target: CandidateIdentity
    contributions: tuple[CandidateContribution, ...]
    plan_digest: str
    activation_manifest_digest: str
    manifest_digest: str
    target_binding_digest: str
    integration_policy_digest: str
    integration_authority_expires_at: str
    validation_receipt_digest: str
    lease_digest: str
    state: IntegrationState
    sequence: int
    reason: str | None = None

    def __post_init__(self) -> None:
        _required(self.transaction_id, "transaction_id")
        _required(self.round_id, "round_id")
        _required(self.target_ref, "target_ref")
        if not isinstance(self.expected_target, CandidateIdentity):
            raise ValueError("expected_target must be a CandidateIdentity")
        if not isinstance(self.proposed_target, CandidateIdentity):
            raise ValueError("proposed_target must be a CandidateIdentity")
        if self.expected_target.subject_id != self.proposed_target.subject_id:
            raise ValueError("integration cannot cross subject identity")
        if not self.contributions:
            raise ValueError("integration requires at least one candidate")
        candidate_ids = tuple(item.candidate_id for item in self.contributions)
        node_ids = tuple(item.node_id for item in self.contributions)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("integration candidates must be unique")
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("integration node order must be unique")
        if any(
            item.identity.subject_id != self.expected_target.subject_id
            for item in self.contributions
        ):
            raise ValueError("candidate belongs to another subject")
        for label in (
            "plan_digest",
            "activation_manifest_digest",
            "manifest_digest",
            "target_binding_digest",
            "integration_policy_digest",
            "validation_receipt_digest",
            "lease_digest",
        ):
            _digest(getattr(self, label), label)
        require_time(
            self.integration_authority_expires_at,
            "integration authority expiry",
        )
        if not isinstance(self.state, IntegrationState):
            raise ValueError("state must be an IntegrationState")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if self.reason is not None:
            _required(self.reason, "reason")
        if (
            self.state
            in {
                IntegrationState.RECOVERABLE,
                IntegrationState.REPLAN_REQUIRED,
                IntegrationState.CANCELLED,
            }
            and self.reason is None
        ):
            raise ValueError(f"{self.state.value} integration state requires a reason")

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL

    @property
    def intent_digest(self) -> str:
        document = self.to_document()
        for name in ("state", "sequence", "reason"):
            document.pop(name)
        return canonical_digest(document)

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "transaction_id": self.transaction_id,
            "round_id": self.round_id,
            "target_ref": self.target_ref,
            "expected_target": self.expected_target.to_document(),
            "proposed_target": self.proposed_target.to_document(),
            "contributions": [item.to_document() for item in self.contributions],
            "plan_digest": self.plan_digest,
            "activation_manifest_digest": self.activation_manifest_digest,
            "manifest_digest": self.manifest_digest,
            "target_binding_digest": self.target_binding_digest,
            "integration_policy_digest": self.integration_policy_digest,
            "integration_authority_expires_at": self.integration_authority_expires_at,
            "validation_receipt_digest": self.validation_receipt_digest,
            "lease_digest": self.lease_digest,
            "state": self.state.value,
            "sequence": self.sequence,
            "reason": self.reason,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> IntegrationTransaction:
        fields = {
            "schema_version",
            "transaction_id",
            "round_id",
            "target_ref",
            "expected_target",
            "proposed_target",
            "contributions",
            "plan_digest",
            "activation_manifest_digest",
            "manifest_digest",
            "target_binding_digest",
            "integration_policy_digest",
            "integration_authority_expires_at",
            "validation_receipt_digest",
            "lease_digest",
            "state",
            "sequence",
            "reason",
        }
        if (
            set(value) != fields
            or type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
        ):
            raise IntegrationError("integration transaction has an unknown shape")
        if not isinstance(value.get("expected_target"), Mapping) or not isinstance(
            value.get("proposed_target"), Mapping
        ):
            raise IntegrationError("integration target identity is malformed")
        contributions = value.get("contributions")
        if not isinstance(contributions, list) or not all(
            isinstance(item, Mapping) for item in contributions
        ):
            raise IntegrationError("integration contributions are malformed")
        try:
            return cls(
                transaction_id=value["transaction_id"],
                round_id=value["round_id"],
                target_ref=value["target_ref"],
                expected_target=CandidateIdentity.from_document(
                    value["expected_target"]
                ),
                proposed_target=CandidateIdentity.from_document(
                    value["proposed_target"]
                ),
                contributions=tuple(
                    CandidateContribution.from_document(item) for item in contributions
                ),
                plan_digest=value["plan_digest"],
                activation_manifest_digest=value["activation_manifest_digest"],
                manifest_digest=value["manifest_digest"],
                target_binding_digest=value["target_binding_digest"],
                integration_policy_digest=value["integration_policy_digest"],
                integration_authority_expires_at=value[
                    "integration_authority_expires_at"
                ],
                validation_receipt_digest=value["validation_receipt_digest"],
                lease_digest=value["lease_digest"],
                state=IntegrationState(value["state"]),
                sequence=value["sequence"],
                reason=value["reason"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise IntegrationError("integration transaction is invalid") from error


class IntegrationTarget(Protocol):
    """Adapter boundary containing the only target-mutating primitive."""

    def binding(self) -> IntegrationTargetBinding:
        """Return the host-observed immutable adapter and trust identity."""

        ...

    def observe_target(self, target_ref: str) -> CandidateIdentity:
        """Return the exact current target identity."""

        ...

    def compare_and_swap(
        self,
        *,
        transaction_id: str,
        target_ref: str,
        expected_target: CandidateIdentity,
        proposed_target: CandidateIdentity,
        ordered_candidates: Sequence[CandidateContribution],
        expected_binding: IntegrationTargetBinding,
        authorization: AuthorizedOneRun,
        effect_deadline: datetime,
        integration_authority_expires_at: str,
        protected_merge_authorized: bool,
    ) -> bool:
        """Atomically advance only when target equals ``expected_target``.

        Implementations must atomically reject a changed ``expected_binding``;
        a protected or unknown target; a forged, substituted, or protected-merge
        authorization; and execution at or after the earlier of the activation
        and plan-authority deadlines. They must bind ``transaction_id`` to that
        exact canonical request and make retries of that request idempotent.
        """

        ...


class IntegrationJournal:
    """Append-only transaction intent and outcome history."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        self._changed = Condition(self._lock)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        try:
            self.connection.row_factory = sqlite3.Row
            with self.connection:
                self.connection.executescript(
                    """
                CREATE TABLE IF NOT EXISTS integration_events (
                    global_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL,
                    transaction_sequence INTEGER NOT NULL,
                    round_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    previous_digest TEXT,
                    event_digest TEXT NOT NULL UNIQUE,
                    UNIQUE(transaction_id, transaction_sequence)
                );
                CREATE TABLE IF NOT EXISTS integration_preparations (
                    transaction_id TEXT PRIMARY KEY,
                    prepared_transaction_digest TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS integration_events_no_update
                BEFORE UPDATE ON integration_events
                BEGIN SELECT RAISE(ABORT, 'integration history is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS integration_events_no_delete
                BEFORE DELETE ON integration_events
                BEGIN SELECT RAISE(ABORT, 'integration history is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS integration_preparations_no_update
                BEFORE UPDATE ON integration_preparations
                BEGIN SELECT RAISE(ABORT, 'integration preparation is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS integration_preparations_no_delete
                BEFORE DELETE ON integration_preparations
                BEGIN SELECT RAISE(ABORT, 'integration preparation is append-only'); END;
                    """
                )
            self.connection.set_authorizer(self._authorize_database)
            self.verify()
        except BaseException:
            self.connection.close()
            raise

    def _authorize_database(
        self,
        action_code: int,
        table_name: str | None,
        _column_name: str | None,
        _database_name: str | None,
        _trigger_name: str | None,
    ) -> int:
        if action_code in {
            sqlite3.SQLITE_INSERT,
            sqlite3.SQLITE_UPDATE,
            sqlite3.SQLITE_DELETE,
        } and table_name in {"integration_events", "integration_preparations"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> IntegrationJournal:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _decode(row: sqlite3.Row) -> IntegrationTransaction:
        try:
            value = strict_json_object(str(row["payload_json"]).encode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise IntegrationError(
                "integration journal contains invalid JSON"
            ) from error
        transaction = IntegrationTransaction.from_document(value)
        if (
            transaction.transaction_id != row["transaction_id"]
            or transaction.round_id != row["round_id"]
            or transaction.sequence != row["transaction_sequence"]
        ):
            raise IntegrationError("integration journal index disagrees with payload")
        return transaction

    def _rows(self, transaction_id: str | None = None) -> tuple[sqlite3.Row, ...]:
        query = "SELECT * FROM integration_events"
        values: tuple[object, ...] = ()
        if transaction_id is not None:
            query += " WHERE transaction_id=?"
            values = (transaction_id,)
        query += " ORDER BY global_sequence"
        return tuple(self.connection.execute(query, values))

    @contextmanager
    def _read_snapshot(self) -> Iterator[None]:
        """Hold one SQLite snapshot across events and preparation receipts."""

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
        with self._lock, self._read_snapshot():
            self._verify_snapshot()

    def _verify_snapshot(self) -> None:
        previous: dict[str, str | None] = {}
        sequences: dict[str, int] = {}
        rounds: dict[str, str] = {}
        latest: dict[str, IntegrationTransaction] = {}
        for row in self._rows():
            transaction = self._decode(row)
            owner = rounds.setdefault(transaction.round_id, transaction.transaction_id)
            if owner != transaction.transaction_id:
                raise IntegrationError("round has competing integration transactions")
            expected = sequences.get(transaction.transaction_id, 1)
            if transaction.sequence != expected:
                raise IntegrationError("integration sequence is discontinuous")
            prior = previous.get(transaction.transaction_id)
            if row["previous_digest"] != prior:
                raise IntegrationError("integration hash chain is broken")
            if (
                row["payload_json"]
                != canonical_bytes(transaction.to_document()).decode()
            ):
                raise IntegrationError("integration payload is not canonical")
            event_digest = canonical_digest(
                {"previous_digest": prior, "transaction": transaction.to_document()}
            )
            if row["event_digest"] != event_digest:
                raise IntegrationError("integration event digest is invalid")
            prior_transaction = latest.get(transaction.transaction_id)
            if prior_transaction is None:
                if transaction.state is not IntegrationState.PREPARED:
                    raise IntegrationError("integration history must begin at PREPARED")
                preparation = self.connection.execute(
                    """
                    SELECT prepared_transaction_digest
                      FROM integration_preparations WHERE transaction_id=?
                    """,
                    (transaction.transaction_id,),
                ).fetchone()
                if preparation is None or preparation[
                    "prepared_transaction_digest"
                ] != canonical_digest(transaction.to_document()):
                    raise IntegrationError(
                        "prepared integration lacks a matching journal preparation receipt"
                    )
            else:
                if transaction.state not in _TRANSITIONS[prior_transaction.state]:
                    raise IntegrationError(
                        "integration history contains an invalid transition"
                    )
                if transaction.intent_digest != prior_transaction.intent_digest:
                    raise IntegrationError(
                        "integration history changed its immutable intent"
                    )
            previous[transaction.transaction_id] = event_digest
            sequences[transaction.transaction_id] = expected + 1
            latest[transaction.transaction_id] = transaction

    def latest(self, transaction_id: str) -> IntegrationTransaction | None:
        _required(transaction_id, "transaction_id")
        with self._lock, self._read_snapshot():
            rows = self._rows(transaction_id)
            if not rows:
                return None
            self.verify()
            return self._decode(rows[-1])

    def for_round(self, round_id: str) -> IntegrationTransaction | None:
        _required(round_id, "round_id")
        with self._lock, self._read_snapshot():
            self.verify()
            row = self.connection.execute(
                """
                SELECT * FROM integration_events WHERE round_id=?
                ORDER BY global_sequence DESC LIMIT 1
                """,
                (round_id,),
            ).fetchone()
            return None if row is None else self._decode(row)

    def append(
        self, transaction: IntegrationTransaction, *, idempotency_key: str
    ) -> IntegrationTransaction:
        """Reject event injection outside the trusted in-process journal path."""

        raise IntegrationError("integration events require the trusted journal path")

    def _append_coordinator_event(
        self,
        transaction: IntegrationTransaction,
        *,
        idempotency_key: str,
        authority: object,
    ) -> IntegrationTransaction:
        result, _ = self._append_coordinator_event_with_ownership(
            transaction,
            idempotency_key=idempotency_key,
            authority=authority,
        )
        return result

    def _append_coordinator_event_with_ownership(
        self,
        transaction: IntegrationTransaction,
        *,
        idempotency_key: str,
        authority: object,
    ) -> tuple[IntegrationTransaction, bool]:
        if authority is not _COORDINATOR_EVENT_AUTHORITY:
            raise IntegrationError("integration events require the trusted journal path")
        _required(idempotency_key, "idempotency_key")
        encoded = canonical_bytes(transaction.to_document()).decode()
        with self._lock:
            self.connection.set_authorizer(None)
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                retry = self.connection.execute(
                    "SELECT * FROM integration_events WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if retry is not None:
                    if retry["payload_json"] != encoded:
                        raise IntegrationError(
                            "idempotency key is bound to another integration event"
                        )
                    result = self._decode(retry)
                    self.connection.commit()
                    return result, False
                round_owner = self.connection.execute(
                    """
                    SELECT transaction_id FROM integration_events
                     WHERE round_id=? LIMIT 1
                    """,
                    (transaction.round_id,),
                ).fetchone()
                if (
                    round_owner is not None
                    and round_owner["transaction_id"] != transaction.transaction_id
                ):
                    raise IntegrationError(
                        "round already has an integration transaction"
                    )
                last = self.connection.execute(
                    """
                    SELECT * FROM integration_events WHERE transaction_id=?
                     ORDER BY transaction_sequence DESC LIMIT 1
                    """,
                    (transaction.transaction_id,),
                ).fetchone()
                if (
                    last is not None
                    and transaction.state is IntegrationState.PREPARED
                    and transaction.sequence == 1
                ):
                    existing = self._decode(last)
                    if existing.intent_digest != transaction.intent_digest:
                        raise IntegrationError(
                            "transaction id is bound to another integration intent"
                        )
                    self.connection.commit()
                    return existing, False
                expected = 1 if last is None else int(last["transaction_sequence"]) + 1
                if transaction.sequence != expected:
                    raise IntegrationError(
                        "integration compare-and-swap sequence failed"
                    )
                if last is not None:
                    previous_transaction = self._decode(last)
                    if (
                        transaction.state
                        not in _TRANSITIONS[previous_transaction.state]
                    ):
                        raise IntegrationError("invalid integration state transition")
                    if transaction.intent_digest != previous_transaction.intent_digest:
                        raise IntegrationError("integration intent is immutable")
                elif transaction.state is not IntegrationState.PREPARED:
                    raise IntegrationError("integration must begin in PREPARED")
                if last is None:
                    self.connection.execute(
                        """
                        INSERT INTO integration_preparations(
                            transaction_id, prepared_transaction_digest
                        ) VALUES(?,?)
                        """,
                        (
                            transaction.transaction_id,
                            canonical_digest(transaction.to_document()),
                        ),
                    )
                previous = None if last is None else str(last["event_digest"])
                event_digest = canonical_digest(
                    {
                        "previous_digest": previous,
                        "transaction": transaction.to_document(),
                    }
                )
                self.connection.execute(
                    """
                    INSERT INTO integration_events(
                        transaction_id, transaction_sequence, round_id,
                        idempotency_key, payload_json, previous_digest, event_digest
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        transaction.transaction_id,
                        transaction.sequence,
                        transaction.round_id,
                        idempotency_key,
                        encoded,
                        previous,
                        event_digest,
                    ),
                )
                self.connection.commit()
                self._changed.notify_all()
                return transaction, True
            except BaseException:
                self.connection.rollback()
                raise
            finally:
                # Reinstalling the authorizer also invalidates statements prepared
                # while coordinator writes were enabled.
                self.connection.set_authorizer(self._authorize_database)

    def _wait_for_change(
        self,
        transaction_id: str,
        *,
        after_sequence: int,
        timeout: float,
    ) -> IntegrationTransaction | None:
        with self._changed:
            current = self.latest(transaction_id)
            if current is None or current.sequence > after_sequence:
                return current
            self._changed.wait(timeout)
            return self.latest(transaction_id)


class IntegrationCoordinator:
    """Prepare, execute once, and reconcile an integration transaction."""

    def __init__(
        self,
        journal: IntegrationJournal,
        target: IntegrationTarget,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.journal = journal
        self.target = target
        self.clock = clock or (lambda: datetime.now(UTC))

    def prepare(
        self,
        *,
        transaction_id: str | None = None,
        round_id: str,
        target_ref: str,
        expected_target: CandidateIdentity,
        proposed_target: CandidateIdentity,
        candidates: Sequence[CandidateSnapshot],
        integration_order: Sequence[str] | None = None,
        manifest_digest: str | None = None,
        integration_policy_digest: str | None = None,
        validation_receipt_digest: str | None = None,
        lease_digest: str | None = None,
        idempotency_key: str,
        authorization: AuthorizedOneRun | None = None,
        integration_policy: object | None = None,
        plan_digest: str | None = None,
        plan_bytes: bytes | None = None,
        standard_bytes: bytes | None = None,
        wave_manifest_bytes: bytes | None = None,
        candidate_journal: CandidateStateJournal | None = None,
    ) -> IntegrationTransaction:
        authorized = _require_authorization(authorization, now=self.clock())
        _required(round_id, "round_id")
        if not isinstance(expected_target, CandidateIdentity) or not isinstance(
            proposed_target, CandidateIdentity
        ):
            raise IntegrationError("integration targets must be typed identities")
        if (
            proposed_target.commit != authorized.candidate_commit
            or proposed_target.tree != authorized.candidate_tree
        ):
            raise IntegrationError("proposed integration target was substituted")
        if transaction_id is not None:
            raise IntegrationError("caller-supplied transaction ids are forbidden")
        if integration_policy is not None or plan_digest is not None:
            raise IntegrationError(
                "caller-supplied plan digests or integration policies are forbidden"
            )
        if any(
            value is not None
            for value in (
                integration_policy_digest,
                validation_receipt_digest,
                lease_digest,
            )
        ):
            raise IntegrationError(
                "caller-supplied integration evidence digests are forbidden"
            )
        if manifest_digest is not None:
            raise IntegrationError(
                "caller-supplied wave-manifest digests are forbidden"
            )
        if integration_order is not None:
            raise IntegrationError("caller-supplied integration order is forbidden")
        if type(plan_bytes) is not bytes:
            raise IntegrationError("exact portable plan bytes are required")
        if _raw_digest(plan_bytes) != authorized.plan_sha256:
            raise IntegrationError("integration plan bytes were substituted")
        if type(standard_bytes) is not bytes:
            raise IntegrationError("exact authoring-standard bytes are required")
        try:
            plan = load_bound_plan(
                plan_bytes,
                expected_plan_digest=authorized.plan_sha256,
                standard_bytes=standard_bytes,
                expected_request_id=authorized.request_sha256,
                expected_subject_id=expected_target.subject_id,
            )
        except (ContractViolation, TypeError, ValueError) as error:
            raise IntegrationError(
                f"integration plan/standard binding is invalid: {error}"
            ) from error
        integration_policy = plan.integration
        repository = plan.subject.repository
        if repository is None:
            raise IntegrationError("integration target requires a repository plan")
        if integration_policy.protected_target:
            raise IntegrationError(
                "AuthorizedOneRun does not authorize protected-target integration"
            )
        if (
            plan.subject.subject_id != expected_target.subject_id
            or repository.commit != expected_target.commit
            or repository.tree != expected_target.tree
            or repository.target_branch != target_ref
        ):
            raise IntegrationError("integration plan subject was substituted")
        if (
            plan.request_id != authorized.request_sha256
            or repository.repository_id != authorized.repository_id
            or repository.commit != authorized.candidate_parent_commit
            or repository.tree != authorized.candidate_parent_tree
        ):
            raise IntegrationError(
                "activation manifest does not authorize this plan subject"
            )
        if authorized.target_branch != target_ref:
            raise IntegrationError("activation manifest target was substituted")
        if integration_policy.strategy != "compare-and-swap":
            raise IntegrationError("integration policy strategy is unsupported")
        if not integration_policy.compare_and_swap:
            raise IntegrationError("integration policy denies compare-and-swap")
        if integration_policy.target != target_ref:
            raise IntegrationError("integration policy target was substituted")
        if integration_policy.expected_base != _target_snapshot_digest(expected_target):
            raise IntegrationError("integration policy expected base was substituted")
        if type(wave_manifest_bytes) is not bytes:
            raise IntegrationError("exact wave manifest bytes are required")
        try:
            wave_manifest = WaveManifest.from_bytes(wave_manifest_bytes)
        except (ContractViolation, TypeError, ValueError) as error:
            raise IntegrationError("wave manifest bytes are invalid") from error
        if wave_manifest.state is not WaveState.INTEGRATION_READY:
            raise IntegrationError("wave manifest is not integration-ready")
        if (
            wave_manifest.plan_digest != plan.digest()
            or wave_manifest.subject_id != plan.subject.subject_id
            or wave_manifest.candidate != proposed_target
        ):
            raise IntegrationError("wave manifest activation binding was substituted")
        if any(
            node.state is not WaveNodeState.COMPLETED for node in wave_manifest.nodes
        ):
            raise IntegrationError("wave manifest contains an incomplete node")
        derived_order = tuple(node.node_id for node in wave_manifest.nodes)
        if not candidates:
            raise IntegrationError("integration requires at least one candidate")
        by_node = {candidate.node_id: candidate for candidate in candidates}
        if len(by_node) != len(candidates) or tuple(by_node) != derived_order:
            raise IntegrationError(
                "sealed candidates do not match manifest-derived order"
            )
        if type(candidate_journal) is not CandidateStateJournal:
            raise IntegrationError("an exact candidate-state journal is required")
        try:
            candidate_journal.verify()
        except (CandidateStateError, sqlite3.DatabaseError) as error:
            raise IntegrationError("candidate-state journal is invalid") from error
        candidate_manifest_digest = wave_manifest.manifest_digest
        canonical_round_id = canonical_digest(
            {
                "schema_version": 1,
                "kind": "hive-mind-integration-round-v1",
                "authorization_proof_digest": authorized.proof_digest,
                "wave_manifest_digest": candidate_manifest_digest,
            }
        )
        expected_authority_digest = canonical_digest(
            [item.to_document() for item in plan.authority]
        )
        generations = {candidate.generation for candidate in candidates}
        if len(generations) != 1:
            raise IntegrationError("candidate generation is inconsistent")
        contributions: list[CandidateContribution] = []
        for node, node_id in zip(wave_manifest.nodes, derived_order, strict=True):
            candidate = by_node[node_id]
            if candidate.state is not WaveState.INTEGRATION_READY:
                raise IntegrationError(
                    f"candidate {candidate.candidate_id} is not integration-ready"
                )
            if candidate.identity is None:
                raise IntegrationError("integration-ready candidate has no identity")
            if candidate_journal.latest(candidate.candidate_id) != candidate:
                raise IntegrationError(
                    "candidate snapshot is not present in the supplied candidate-state journal"
                )
            if candidate.manifest_digest != candidate_manifest_digest:
                raise IntegrationError("candidate belongs to another wave manifest")
            if (
                candidate.wave_id != wave_manifest.wave_id
                or candidate.authority_digest != expected_authority_digest
                or candidate.identity.subject_id != wave_manifest.subject_id
                or node.result_digest != candidate.checkpoint_digest
            ):
                raise IntegrationError(
                    "candidate provenance disagrees with wave manifest"
                )
            contributions.append(
                CandidateContribution(
                    candidate_id=candidate.candidate_id,
                    node_id=node_id,
                    identity=candidate.identity,
                    verification_receipt_digest=candidate.checkpoint_digest,
                )
            )
        authorities = {item.authority_id: item for item in plan.authority}
        eligible_deadlines: dict[str, list[tuple[datetime, str]]] = {}
        authority_check_time = self.clock()
        if (
            authority_check_time.tzinfo is None
            or authority_check_time.utcoffset() is None
        ):
            raise IntegrationError("integration clock must be timezone-aware")
        for capability in plan.capabilities:
            authority = authorities.get(capability.authority_id)
            authority_deadline = (
                require_time(authority.expires_at, "integration authority expiry")
                if authority is not None
                else None
            )
            if (
                capability.operation != "integrate"
                or not requires_external_authority(capability.effect_class)
                or authority is None
                or not authority.external_effects
                or "integrate" not in authority.allowed_actions
                or {"integrate", "merge", "protected-merge"}
                & set(authority.denied_actions)
                or authority_deadline is None
                or authority_deadline <= authority_check_time
            ):
                continue
            eligible_deadlines.setdefault(capability.adapter_id, []).append(
                (authority_deadline, authority.expires_at)
            )
        if not eligible_deadlines:
            raise IntegrationError("portable plan denies external integration effects")
        target_binding = self._read_target_binding()
        if target_binding.protected_target is not False:
            raise IntegrationError("integration target is protected or protection is unknown")
        adapter = next(
            (
                item
                for item in plan.adapters
                if item.adapter_id == target_binding.adapter_id
            ),
            None,
        )
        if (
            adapter is None
            or target_binding.adapter_id not in eligible_deadlines
            or target_binding.interface != "integration.target"
            or adapter.interface != target_binding.interface
            or adapter.version != target_binding.version
            or adapter.configuration_digest != target_binding.configuration_digest
            or target_binding.trust_digest != authorized.execution_client_sha256
        ):
            raise IntegrationError("integration target adapter was substituted")
        integration_authority_expires_at = min(
            eligible_deadlines[target_binding.adapter_id], key=lambda item: item[0]
        )[1]
        policy_digest = canonical_digest(integration_policy.to_document())
        validation_digest = canonical_digest(
            {
                "schema_version": 1,
                "kind": "hive-mind-integration-validation-set-v1",
                "manifest_digest": candidate_manifest_digest,
                "ordered_contributions": [item.to_document() for item in contributions],
            }
        )
        intent = {
            "schema_version": 1,
            "kind": "hive-mind-integration-intent-v1",
            "authorization_proof_digest": authorized.proof_digest,
            "round_id": canonical_round_id,
            "target_ref": target_ref,
            "expected_target": expected_target.to_document(),
            "proposed_target": proposed_target.to_document(),
            "contributions": [item.to_document() for item in contributions],
            "plan_digest": authorized.plan_sha256,
            "activation_manifest_digest": authorized.manifest_sha256,
            "manifest_digest": candidate_manifest_digest,
            "target_binding_digest": target_binding.digest,
            "integration_policy_digest": policy_digest,
            "integration_authority_expires_at": integration_authority_expires_at,
            "validation_receipt_digest": validation_digest,
        }
        derived_transaction_id = canonical_digest(intent)
        transaction = IntegrationTransaction(
            transaction_id=derived_transaction_id,
            round_id=canonical_round_id,
            target_ref=target_ref,
            expected_target=expected_target,
            proposed_target=proposed_target,
            contributions=tuple(contributions),
            plan_digest=authorized.plan_sha256,
            activation_manifest_digest=authorized.manifest_sha256,
            manifest_digest=candidate_manifest_digest,
            target_binding_digest=target_binding.digest,
            integration_policy_digest=policy_digest,
            integration_authority_expires_at=integration_authority_expires_at,
            validation_receipt_digest=validation_digest,
            lease_digest=authorized.proof_digest,
            state=IntegrationState.PREPARED,
            sequence=1,
        )
        existing = self.journal.latest(derived_transaction_id)
        if existing is not None:
            if existing.intent_digest != transaction.intent_digest:
                raise IntegrationError(
                    "transaction id is bound to another integration intent"
                )
            return existing
        round_owner = self.journal.for_round(canonical_round_id)
        if round_owner is not None:
            raise IntegrationError("round already has an integration transaction")
        # The target boundary is last: all local values, signed bindings,
        # candidate evidence, and existing journal state are settled first.
        if self._read_target_binding() != target_binding:
            raise IntegrationError("integration target adapter was substituted")
        initial_target = self.target.observe_target(target_ref)
        if self._read_target_binding() != target_binding:
            raise IntegrationError("integration target adapter was substituted")
        if initial_target != expected_target:
            raise IntegrationError("target drifted before transaction preparation")
        return self.journal._append_coordinator_event(
            transaction,
            idempotency_key=idempotency_key,
            authority=_COORDINATOR_EVENT_AUTHORITY,
        )

    def commit(
        self,
        transaction_id: str,
        *,
        idempotency_key: str,
        authorization: AuthorizedOneRun | None = None,
    ) -> IntegrationTransaction:
        transaction = self.journal.latest(transaction_id)
        if transaction is None:
            raise IntegrationError("unknown integration transaction")
        if transaction.state is IntegrationState.COMMITTED:
            self._validate_transaction_authorization(
                transaction,
                authorization,
                require_live=False,
            )
            return transaction
        authorized = self._validate_transaction_authorization(
            transaction, authorization
        )
        self._require_effect_live(transaction, authorized)
        if transaction.state is IntegrationState.EXECUTING:
            return self._await_execution_owner(
                transaction,
                idempotency_key=idempotency_key,
                authorization=authorized,
            )
        if transaction.state is not IntegrationState.PREPARED:
            raise IntegrationError("only a prepared transaction may execute")
        self._validate_target_binding(transaction)
        observed = self.target.observe_target(transaction.target_ref)
        self._validate_target_binding(transaction)
        if observed != transaction.expected_target:
            return self._record(
                transaction,
                IntegrationState.REPLAN_REQUIRED,
                idempotency_key=idempotency_key + ":drift",
                reason="target drifted before compare-and-swap",
            )
        executing, owns_execution = self.journal._append_coordinator_event_with_ownership(
            replace(
                transaction,
                state=IntegrationState.EXECUTING,
                sequence=transaction.sequence + 1,
            ),
            idempotency_key=idempotency_key + ":executing",
            authority=_COORDINATOR_EVENT_AUTHORITY,
        )
        if not owns_execution:
            return self._await_execution_owner(
                executing,
                idempotency_key=idempotency_key,
                authorization=authorized,
            )
        expected_binding = self._validate_target_binding(executing)
        authorized = self._validate_transaction_authorization(
            executing,
            authorized,
        )
        effect_deadline = self._require_effect_live(executing, authorized)
        try:
            advanced = self.target.compare_and_swap(
                transaction_id=executing.transaction_id,
                target_ref=executing.target_ref,
                expected_target=executing.expected_target,
                proposed_target=executing.proposed_target,
                ordered_candidates=executing.contributions,
                expected_binding=expected_binding,
                authorization=authorized,
                effect_deadline=effect_deadline,
                integration_authority_expires_at=(
                    executing.integration_authority_expires_at
                ),
                protected_merge_authorized=authorized.protected_merge_authorized,
            )
        except BaseException:
            # The adapter may have completed before the exception crossed the
            # process boundary, so observation—not a blind retry—is authoritative.
            return self.reconcile(
                transaction_id,
                idempotency_key=idempotency_key + ":exception",
                reason="integration response was lost",
                authorization=authorized,
            )
        try:
            self._validate_target_binding(executing)
            observed = self.target.observe_target(executing.target_ref)
            self._validate_target_binding(executing)
        except BaseException as error:
            return self._record(
                executing,
                IntegrationState.RECOVERABLE,
                idempotency_key=idempotency_key + ":observation-unavailable",
                reason=f"post-CAS target observation failed: {type(error).__name__}",
            )
        if advanced and observed == executing.proposed_target:
            return self._record(
                executing,
                IntegrationState.COMMITTED,
                idempotency_key=idempotency_key + ":committed",
            )
        return self._classify_observation(
            executing,
            observed,
            idempotency_key=idempotency_key + ":observed",
            reason="compare-and-swap did not produce its exact proposed target",
        )

    def _await_execution_owner(
        self,
        transaction: IntegrationTransaction,
        *,
        idempotency_key: str,
        authorization: AuthorizedOneRun,
    ) -> IntegrationTransaction:
        """Wait briefly for the durable outcome without acquiring CAS ownership."""

        current = transaction
        wait_deadline = monotonic() + 5.0
        while current.state is IntegrationState.EXECUTING:
            remaining = wait_deadline - monotonic()
            if remaining <= 0:
                return self.reconcile(
                    transaction.transaction_id,
                    idempotency_key=idempotency_key + ":competing-owner-timeout",
                    reason="integration owner outcome required reconciliation",
                    authorization=authorization,
                )
            observed = self.journal._wait_for_change(
                transaction.transaction_id,
                after_sequence=current.sequence,
                timeout=min(remaining, 0.05),
            )
            if observed is None:
                raise IntegrationError("integration transaction disappeared")
            current = observed
        return current

    def reconcile(
        self,
        transaction_id: str,
        *,
        idempotency_key: str,
        reason: str = "integration outcome reconciled after restart",
        authorization: AuthorizedOneRun | None = None,
    ) -> IntegrationTransaction:
        transaction = self.journal.latest(transaction_id)
        if transaction is None:
            raise IntegrationError("unknown integration transaction")
        if transaction.state is IntegrationState.COMMITTED:
            return transaction
        if transaction.state not in {
            IntegrationState.EXECUTING,
            IntegrationState.RECOVERABLE,
        }:
            raise IntegrationError("transaction has no ambiguous outcome to reconcile")
        if authorization is not None:
            self._validate_transaction_authorization(
                transaction,
                authorization,
                require_live=False,
            )
        try:
            self._validate_target_binding(transaction)
            observed = self.target.observe_target(transaction.target_ref)
            self._validate_target_binding(transaction)
        except BaseException as error:
            return self._record(
                transaction,
                IntegrationState.RECOVERABLE,
                idempotency_key=idempotency_key + ":observation-unavailable",
                reason=f"target observation failed: {type(error).__name__}",
            )
        return self._classify_observation(
            transaction,
            observed,
            idempotency_key=idempotency_key,
            reason=reason,
        )

    def _classify_observation(
        self,
        transaction: IntegrationTransaction,
        observed: CandidateIdentity,
        *,
        idempotency_key: str,
        reason: str,
    ) -> IntegrationTransaction:
        if observed == transaction.proposed_target:
            state = IntegrationState.COMMITTED
            outcome_reason = "exact proposed target observed"
        elif observed == transaction.expected_target:
            state = IntegrationState.RECOVERABLE
            outcome_reason = reason
        else:
            state = IntegrationState.REPLAN_REQUIRED
            outcome_reason = "target has an unrecognized identity"
        return self._record(
            transaction,
            state,
            idempotency_key=idempotency_key,
            reason=outcome_reason,
        )

    def _validate_transaction_authorization(
        self,
        transaction: IntegrationTransaction,
        authorization: object,
        *,
        require_live: bool = True,
    ) -> AuthorizedOneRun:
        authorized = _require_authorization(
            authorization,
            now=self.clock(),
            require_live=require_live,
        )
        if authorized.proof_digest != transaction.lease_digest:
            raise IntegrationError("integration authorization was substituted")
        if authorized.plan_sha256 != transaction.plan_digest:
            raise IntegrationError("integration authorization plan was substituted")
        if authorized.manifest_sha256 != transaction.activation_manifest_digest:
            raise IntegrationError("integration activation manifest was substituted")
        if authorized.target_branch != transaction.target_ref:
            raise IntegrationError("integration authorization target was substituted")
        if (
            authorized.candidate_parent_commit != transaction.expected_target.commit
            or authorized.candidate_parent_tree != transaction.expected_target.tree
        ):
            raise IntegrationError("integration authorization base was substituted")
        if (
            authorized.candidate_commit != transaction.proposed_target.commit
            or authorized.candidate_tree != transaction.proposed_target.tree
        ):
            raise IntegrationError(
                "integration authorization candidate was substituted"
            )
        if authorized.protected_merge_authorized:
            raise IntegrationError("protected-target integration is not authorized")
        return authorized

    def _require_effect_live(
        self,
        transaction: IntegrationTransaction,
        authorization: AuthorizedOneRun,
    ) -> datetime:
        plan_deadline = require_time(
            transaction.integration_authority_expires_at,
            "integration authority expiry",
        )
        effect_deadline = min(
            authorization.expires_at.astimezone(UTC),
            plan_deadline.astimezone(UTC),
        )
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise IntegrationError("integration clock must be timezone-aware")
        if now.astimezone(UTC) >= effect_deadline:
            raise IntegrationError("integration effect authority is stale")
        return effect_deadline

    def _validate_target_binding(
        self, transaction: IntegrationTransaction
    ) -> IntegrationTargetBinding:
        binding = self._read_target_binding()
        if binding.digest != transaction.target_binding_digest:
            raise IntegrationError("integration target adapter was substituted")
        if binding.protected_target is not False:
            raise IntegrationError("integration target is protected or protection is unknown")
        return binding

    def _read_target_binding(self) -> IntegrationTargetBinding:
        try:
            binding = self.target.binding()
        except (AttributeError, TypeError, ValueError) as error:
            raise IntegrationError(
                "integration target binding is unavailable"
            ) from error
        if type(binding) is not IntegrationTargetBinding:
            raise IntegrationError("integration target binding is invalid")
        return binding

    def _record(
        self,
        current: IntegrationTransaction,
        state: IntegrationState,
        *,
        idempotency_key: str,
        reason: str | None = None,
    ) -> IntegrationTransaction:
        latest = self.journal.latest(current.transaction_id)
        if latest is None:
            raise IntegrationError("integration transaction disappeared")
        return self.journal._append_coordinator_event(
            replace(latest, state=state, sequence=latest.sequence + 1, reason=reason),
            idempotency_key=idempotency_key,
            authority=_COORDINATOR_EVENT_AUTHORITY,
        )


__all__ = [
    "CandidateContribution",
    "IntegrationCoordinator",
    "IntegrationError",
    "IntegrationJournal",
    "IntegrationState",
    "IntegrationTarget",
    "IntegrationTargetBinding",
    "IntegrationTransaction",
]
