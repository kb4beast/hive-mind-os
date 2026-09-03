"""Append-only lifecycle state for exact, immutable wave candidates.

The journal is deliberately smaller than the general kernel event spine.  It is a
provider for the generic DAG runtime and has one job: retain enough sealed state
to verify or adopt a candidate after the worker claim, process, or parent session
has disappeared.  Mutable workspace bytes are never represented as a candidate.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from ..runtime_contracts import WaveState, strict_json_object
from ..wave_manifest import CandidateIdentity
from .canonical import canonical_bytes, canonical_digest


class CandidateStateError(RuntimeError):
    """The requested transition or durable candidate history is invalid."""


_TERMINAL_STATES = {
    WaveState.INTEGRATED,
    WaveState.FAILED,
    WaveState.CANCELLED,
}

_TRANSITIONS: Mapping[WaveState, frozenset[WaveState]] = {
    WaveState.CHECKPOINTED: frozenset(
        {
            WaveState.CHECKPOINTED,
            WaveState.CANDIDATE_SEALED,
            WaveState.RECOVERABLE,
            WaveState.REPLAN_REQUIRED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.CANDIDATE_SEALED: frozenset(
        {
            WaveState.CANDIDATE_SEALED,
            WaveState.VERIFYING,
            WaveState.RECOVERABLE,
            WaveState.REPLAN_REQUIRED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.VERIFYING: frozenset(
        {
            WaveState.VERIFYING,
            WaveState.INTEGRATION_READY,
            WaveState.RECOVERABLE,
            WaveState.REPLAN_REQUIRED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.INTEGRATION_READY: frozenset(
        {
            WaveState.INTEGRATION_READY,
            WaveState.RECOVERABLE,
            WaveState.REPLAN_REQUIRED,
            WaveState.INTEGRATED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.RECOVERABLE: frozenset(
        {
            WaveState.RECOVERABLE,
            WaveState.CANDIDATE_SEALED,
            WaveState.VERIFYING,
            WaveState.INTEGRATION_READY,
            WaveState.REPLAN_REQUIRED,
            WaveState.INTEGRATED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        }
    ),
    WaveState.REPLAN_REQUIRED: frozenset(
        {WaveState.REPLAN_REQUIRED, WaveState.CANCELLED}
    ),
    WaveState.INTEGRATED: frozenset({WaveState.INTEGRATED}),
    WaveState.FAILED: frozenset({WaveState.FAILED}),
    WaveState.CANCELLED: frozenset({WaveState.CANCELLED}),
}


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value


def _digest(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("sha256:")
        or len(value) != 71
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{label} must be a lowercase sha256 digest")
    return value


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """One immutable projection point in a candidate lifecycle."""

    candidate_id: str
    wave_id: str
    node_id: str
    generation: int
    state: WaveState
    manifest_digest: str
    authority_digest: str
    checkpoint_digest: str
    identity: CandidateIdentity | None
    sequence: int
    reason: str | None = None

    def __post_init__(self) -> None:
        _required(self.candidate_id, "candidate_id")
        _required(self.wave_id, "wave_id")
        _required(self.node_id, "node_id")
        if type(self.generation) is not int or self.generation < 1:
            raise ValueError("generation must be a positive integer")
        if not isinstance(self.state, WaveState):
            raise ValueError("state must be a WaveState")
        _digest(self.manifest_digest, "manifest_digest")
        _digest(self.authority_digest, "authority_digest")
        _digest(self.checkpoint_digest, "checkpoint_digest")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("sequence must be a positive integer")
        if self.state in {
            WaveState.CANDIDATE_SEALED,
            WaveState.VERIFYING,
            WaveState.INTEGRATION_READY,
            WaveState.INTEGRATED,
        } and self.identity is None:
            raise ValueError("sealed and adoption states require an exact candidate identity")
        if self.reason is not None:
            _required(self.reason, "reason")
        if self.state in {
            WaveState.RECOVERABLE,
            WaveState.REPLAN_REQUIRED,
            WaveState.FAILED,
            WaveState.CANCELLED,
        } and self.reason is None:
            raise ValueError(f"{self.state.value} candidate state requires a reason")

    @property
    def sealed(self) -> bool:
        return self.identity is not None

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_STATES

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "candidate_id": self.candidate_id,
            "wave_id": self.wave_id,
            "node_id": self.node_id,
            "generation": self.generation,
            "state": self.state.value,
            "manifest_digest": self.manifest_digest,
            "authority_digest": self.authority_digest,
            "checkpoint_digest": self.checkpoint_digest,
            "identity": None if self.identity is None else self.identity.to_document(),
            "sequence": self.sequence,
            "reason": self.reason,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> CandidateSnapshot:
        if set(value) != {
            "schema_version",
            "candidate_id",
            "wave_id",
            "node_id",
            "generation",
            "state",
            "manifest_digest",
            "authority_digest",
            "checkpoint_digest",
            "identity",
            "sequence",
            "reason",
        } or (
            type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
        ):
            raise CandidateStateError("candidate snapshot has an unknown shape")
        identity_value = value["identity"]
        if identity_value is not None and not isinstance(identity_value, Mapping):
            raise CandidateStateError("candidate identity is malformed")
        try:
            identity = (
                None
                if identity_value is None
                else CandidateIdentity.from_document(identity_value)
            )
            return cls(
                candidate_id=value["candidate_id"],
                wave_id=value["wave_id"],
                node_id=value["node_id"],
                generation=value["generation"],
                state=WaveState(value["state"]),
                manifest_digest=value["manifest_digest"],
                authority_digest=value["authority_digest"],
                checkpoint_digest=value["checkpoint_digest"],
                identity=identity,
                sequence=value["sequence"],
                reason=value["reason"],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CandidateStateError("candidate snapshot is invalid") from error


class CandidateStateJournal:
    """SQLite-backed append-only candidate state with optimistic transitions.

    The latest state is rebuilt from a verified hash chain.  There is no mutable
    projection to trust after a crash, and database triggers reject history
    rewriting even when a caller obtains the underlying connection.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        try:
            self.connection.row_factory = sqlite3.Row
            with self.connection:
                self.connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS candidate_events (
                        global_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        candidate_id TEXT NOT NULL,
                        candidate_sequence INTEGER NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        payload_json TEXT NOT NULL,
                        previous_digest TEXT,
                        event_digest TEXT NOT NULL UNIQUE,
                        UNIQUE(candidate_id, candidate_sequence)
                    );
                    CREATE TRIGGER IF NOT EXISTS candidate_events_no_update
                    BEFORE UPDATE ON candidate_events
                    BEGIN SELECT RAISE(ABORT, 'candidate history is append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS candidate_events_no_delete
                    BEFORE DELETE ON candidate_events
                    BEGIN SELECT RAISE(ABORT, 'candidate history is append-only'); END;
                    """
                )
            self.verify()
        except BaseException as error:
            try:
                self.connection.close()
            except BaseException as close_error:
                error.add_note(
                    "candidate journal constructor cleanup also failed: "
                    f"{type(close_error).__name__}: {close_error}"
                )
            raise

    def close(self) -> None:
        with self._lock:
            self.connection.close()

    def __enter__(self) -> CandidateStateJournal:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _rows(self, candidate_id: str | None = None) -> tuple[sqlite3.Row, ...]:
        query = "SELECT * FROM candidate_events"
        values: tuple[object, ...] = ()
        if candidate_id is not None:
            query += " WHERE candidate_id=?"
            values = (candidate_id,)
        query += " ORDER BY global_sequence"
        return tuple(self.connection.execute(query, values))

    @staticmethod
    def _decode(row: sqlite3.Row) -> CandidateSnapshot:
        try:
            value = strict_json_object(str(row["payload_json"]).encode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise CandidateStateError("candidate history contains invalid JSON") from error
        snapshot = CandidateSnapshot.from_document(value)
        if (
            snapshot.candidate_id != row["candidate_id"]
            or snapshot.sequence != row["candidate_sequence"]
        ):
            raise CandidateStateError("candidate history index disagrees with payload")
        return snapshot

    def verify(self) -> None:
        """Verify every per-candidate chain and canonical payload."""

        with self._lock:
            previous: dict[str, str | None] = {}
            expected_sequence: dict[str, int] = {}
            latest: dict[str, CandidateSnapshot] = {}
            for row in self._rows():
                snapshot = self._decode(row)
                candidate_id = snapshot.candidate_id
                expected = expected_sequence.get(candidate_id, 1)
                if snapshot.sequence != expected:
                    raise CandidateStateError(
                        "candidate history sequence is discontinuous"
                    )
                prior = previous.get(candidate_id)
                if row["previous_digest"] != prior:
                    raise CandidateStateError("candidate history hash chain is broken")
                if str(row["payload_json"]) != canonical_bytes(
                    snapshot.to_document()
                ).decode():
                    raise CandidateStateError(
                        "candidate history payload is not canonical"
                    )
                event_digest = canonical_digest(
                    {"previous_digest": prior, "snapshot": snapshot.to_document()}
                )
                if row["event_digest"] != event_digest:
                    raise CandidateStateError(
                        "candidate history event digest is invalid"
                    )
                prior_snapshot = latest.get(candidate_id)
                if prior_snapshot is None:
                    if (
                        snapshot.state is not WaveState.CHECKPOINTED
                        or snapshot.identity is not None
                    ):
                        raise CandidateStateError(
                            "candidate history must begin at CHECKPOINTED"
                        )
                else:
                    if snapshot.state not in _TRANSITIONS[prior_snapshot.state]:
                        raise CandidateStateError(
                            "candidate history contains an invalid transition"
                        )
                    immutable = (
                        "candidate_id",
                        "wave_id",
                        "node_id",
                        "generation",
                        "manifest_digest",
                        "authority_digest",
                    )
                    if any(
                        getattr(snapshot, name) != getattr(prior_snapshot, name)
                        for name in immutable
                    ):
                        raise CandidateStateError(
                            "candidate history changed immutable bindings"
                        )
                    if (
                        prior_snapshot.identity is not None
                        and snapshot.identity != prior_snapshot.identity
                    ):
                        raise CandidateStateError(
                            "candidate history changed sealed identity"
                        )
                previous[candidate_id] = event_digest
                expected_sequence[candidate_id] = expected + 1
                latest[candidate_id] = snapshot

    def latest(self, candidate_id: str) -> CandidateSnapshot | None:
        _required(candidate_id, "candidate_id")
        with self._lock:
            rows = self._rows(candidate_id)
            if not rows:
                return None
            # Verify the full journal, not just the selected final row, so an
            # earlier corrupted transition cannot silently become authority.
            self.verify()
            return self._decode(rows[-1])

    def history(self, candidate_id: str) -> tuple[CandidateSnapshot, ...]:
        _required(candidate_id, "candidate_id")
        with self._lock:
            self.verify()
            return tuple(self._decode(row) for row in self._rows(candidate_id))

    def checkpoint(
        self,
        *,
        candidate_id: str,
        wave_id: str,
        node_id: str,
        generation: int,
        manifest_digest: str,
        authority_digest: str,
        checkpoint_digest: str,
        idempotency_key: str,
    ) -> CandidateSnapshot:
        snapshot = CandidateSnapshot(
            candidate_id=candidate_id,
            wave_id=wave_id,
            node_id=node_id,
            generation=generation,
            state=WaveState.CHECKPOINTED,
            manifest_digest=manifest_digest,
            authority_digest=authority_digest,
            checkpoint_digest=checkpoint_digest,
            identity=None,
            sequence=1,
        )
        return self._append(snapshot, expected_sequence=0, idempotency_key=idempotency_key)

    def transition(
        self,
        candidate_id: str,
        *,
        expected_sequence: int,
        state: WaveState,
        idempotency_key: str,
        identity: CandidateIdentity | None = None,
        checkpoint_digest: str | None = None,
        reason: str | None = None,
    ) -> CandidateSnapshot:
        with self._lock:
            retry = self.connection.execute(
                "SELECT * FROM candidate_events WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if retry is not None:
                existing = self._decode(retry)
                if (
                    existing.candidate_id != candidate_id
                    or existing.sequence != expected_sequence + 1
                    or existing.state is not state
                    or (identity is not None and existing.identity != identity)
                    or (
                        checkpoint_digest is not None
                        and existing.checkpoint_digest != checkpoint_digest
                    )
                    or existing.reason != reason
                ):
                    raise CandidateStateError(
                        "idempotency key is bound to another candidate transition"
                    )
                return existing
            current = self.latest(candidate_id)
            if current is None:
                raise CandidateStateError("candidate has not been checkpointed")
            if state not in _TRANSITIONS[current.state]:
                raise CandidateStateError(
                    f"candidate cannot transition from {current.state.value} to {state.value}"
                )
            exact_identity = current.identity if identity is None else identity
            if current.identity is not None and exact_identity != current.identity:
                raise CandidateStateError("sealed candidate identity is immutable")
            if state is WaveState.CANDIDATE_SEALED and exact_identity is None:
                raise CandidateStateError("candidate sealing requires an exact identity")
            if current.terminal and state is not current.state:
                raise CandidateStateError("terminal candidate state is immutable")
            snapshot = CandidateSnapshot(
                candidate_id=current.candidate_id,
                wave_id=current.wave_id,
                node_id=current.node_id,
                generation=current.generation,
                state=state,
                manifest_digest=current.manifest_digest,
                authority_digest=current.authority_digest,
                checkpoint_digest=checkpoint_digest or current.checkpoint_digest,
                identity=exact_identity,
                sequence=expected_sequence + 1,
                reason=reason,
            )
            return self._append(
                snapshot,
                expected_sequence=expected_sequence,
                idempotency_key=idempotency_key,
            )

    def _append(
        self,
        snapshot: CandidateSnapshot,
        *,
        expected_sequence: int,
        idempotency_key: str,
    ) -> CandidateSnapshot:
        _required(idempotency_key, "idempotency_key")
        encoded = canonical_bytes(snapshot.to_document()).decode()
        with self._lock:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
                retry = self.connection.execute(
                    "SELECT * FROM candidate_events WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if retry is not None:
                    existing = self._decode(retry)
                    if encoded != retry["payload_json"]:
                        raise CandidateStateError(
                            "idempotency key is bound to another candidate transition"
                        )
                    self.connection.commit()
                    return existing
                last = self.connection.execute(
                    """
                    SELECT * FROM candidate_events
                     WHERE candidate_id=? ORDER BY candidate_sequence DESC LIMIT 1
                    """,
                    (snapshot.candidate_id,),
                ).fetchone()
                sequence = 0 if last is None else int(last["candidate_sequence"])
                if sequence != expected_sequence:
                    raise CandidateStateError("candidate compare-and-swap sequence failed")
                if snapshot.sequence != expected_sequence + 1:
                    raise CandidateStateError("candidate snapshot sequence is invalid")
                previous = None if last is None else str(last["event_digest"])
                event_digest = canonical_digest(
                    {"previous_digest": previous, "snapshot": snapshot.to_document()}
                )
                self.connection.execute(
                    """
                    INSERT INTO candidate_events(
                        candidate_id, candidate_sequence, idempotency_key,
                        payload_json, previous_digest, event_digest
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        snapshot.candidate_id,
                        snapshot.sequence,
                        idempotency_key,
                        encoded,
                        previous,
                        event_digest,
                    ),
                )
                self.connection.commit()
                return snapshot
            except BaseException:
                self.connection.rollback()
                raise


__all__ = [
    "CandidateSnapshot",
    "CandidateStateError",
    "CandidateStateJournal",
]
