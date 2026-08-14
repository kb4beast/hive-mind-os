"""SQLite event spine. Events are authority; views and snapshots are rebuildable."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Iterator, Mapping, cast

from .canonical import canonical_bytes
from .events import KernelEvent
from .projection import empty_state, reduce_event, state_digest

DATABASE_FILENAME = "brain-kernel.sqlite3"
_SCHEMA_VERSION = "1"


class KernelIntegrityError(RuntimeError):
    """The durable event history or an append precondition is invalid."""


class KernelStore:
    """A local, append-only event store for new kernel missions only.

    A writable constructor validates the event chain and rebuilds every mutable
    projection. A read-only constructor derives views directly from verified events.
    A corrupt event history therefore fails closed; a corrupt snapshot is discarded.
    """

    def __init__(self, path: str | Path = ":memory:", *, read_only: bool = False) -> None:
        self.path = str(path)
        self.read_only = read_only
        self._lock = RLock()
        if read_only:
            database_uri = Path(path).resolve().as_uri() + "?mode=ro"
            self.connection = sqlite3.connect(
                database_uri,
                check_same_thread=False,
                uri=True,
            )
        else:
            self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        try:
            if self.read_only:
                with self._lock:
                    self._validate_open_locked(require_schema=True)
                    list(self._events_locked())
            else:
                with self._lock, self.connection:
                    self._bootstrap_locked()
                    self._rebuild_locked()
        except Exception:
            self.connection.close()
            raise

    @staticmethod
    def database_path(state_dir: str | Path) -> Path:
        """Return the portable local database path below a kernel state directory."""

        return Path(str(state_dir).replace("\\", "/")) / DATABASE_FILENAME

    def _bootstrap_locked(self) -> None:
        self.connection.execute("PRAGMA foreign_keys=ON")
        tables = {
            str(row["name"])
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables:
            if "kernel_metadata" not in tables:
                raise KernelIntegrityError("kernel store has tables but no schema metadata")
            row = self.connection.execute(
                "SELECT value FROM kernel_metadata WHERE key='schema_version'"
            ).fetchone()
            if row is None or str(row["value"]) != _SCHEMA_VERSION:
                raise KernelIntegrityError("kernel store schema version is unsupported")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS kernel_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                mission_id TEXT NOT NULL,
                work_id TEXT,
                attempt_id TEXT,
                event_type TEXT NOT NULL,
                event_version INTEGER NOT NULL,
                actor_id TEXT NOT NULL,
                actor_role TEXT,
                occurred_at TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                previous_digest TEXT,
                digest TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS mission_projection (
                mission_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                last_sequence INTEGER NOT NULL,
                state_digest TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS work_projection (
                work_id TEXT PRIMARY KEY,
                mission_id TEXT NOT NULL,
                status TEXT NOT NULL,
                last_sequence INTEGER NOT NULL,
                state_digest TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                sequence INTEGER PRIMARY KEY,
                state_json TEXT NOT NULL,
                state_digest TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS idempotency (
                idempotency_key TEXT PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS effect_outbox (
                idempotency_key TEXT PRIMARY KEY,
                intent_digest TEXT NOT NULL UNIQUE,
                intent_json TEXT NOT NULL,
                state TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                reconciliation_reason TEXT,
                receipt_digest TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effect_receipts (
                receipt_digest TEXT PRIMARY KEY,
                intent_digest TEXT NOT NULL UNIQUE,
                receipt_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS effect_reconciliations (
                reconciliation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                intent_digest TEXT NOT NULL,
                state TEXT NOT NULL,
                reason TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS effect_receipts_no_update
            BEFORE UPDATE ON effect_receipts BEGIN
                SELECT RAISE(ABORT, 'effect receipts are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS effect_receipts_no_delete
            BEFORE DELETE ON effect_receipts BEGIN
                SELECT RAISE(ABORT, 'effect receipts are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS effect_reconciliations_no_update
            BEFORE UPDATE ON effect_reconciliations BEGIN
                SELECT RAISE(ABORT, 'effect reconciliations are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS effect_reconciliations_no_delete
            BEFORE DELETE ON effect_reconciliations BEGIN
                SELECT RAISE(ABORT, 'effect reconciliations are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS kernel_events_no_update
            BEFORE UPDATE ON events BEGIN
                SELECT RAISE(ABORT, 'events are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS kernel_events_no_delete
            BEFORE DELETE ON events BEGIN
                SELECT RAISE(ABORT, 'events are append-only');
            END;
            """
        )
        columns = {
            row["name"]
            for row in self.connection.execute("PRAGMA table_info(work_projection)")
        }
        if "mission_id" not in columns:
            self.connection.execute("DROP TABLE work_projection")
            self.connection.execute(
                """
                CREATE TABLE work_projection (
                    work_id TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    last_sequence INTEGER NOT NULL,
                    state_digest TEXT NOT NULL
                )
                """
            )
        self.connection.execute(
            "INSERT OR IGNORE INTO kernel_metadata VALUES('schema_version', ?)",
            (_SCHEMA_VERSION,),
        )
        self._validate_open_locked(require_schema=True)

    def _validate_open_locked(self, *, require_schema: bool) -> None:
        """Reject corrupt/incoherent durable state without repairing it."""

        quick = [str(row[0]) for row in self.connection.execute("PRAGMA quick_check")]
        if quick != ["ok"]:
            raise KernelIntegrityError("kernel store failed SQLite integrity check")
        foreign = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign:
            raise KernelIntegrityError("kernel store failed foreign-key validation")
        if require_schema:
            try:
                row = self.connection.execute(
                    "SELECT value FROM kernel_metadata WHERE key='schema_version'"
                ).fetchone()
            except sqlite3.DatabaseError as error:
                raise KernelIntegrityError("kernel store schema metadata is missing") from error
            if row is None or str(row["value"]) != _SCHEMA_VERSION:
                raise KernelIntegrityError("kernel store schema version is unsupported")
        allowed = {"pending", "executing", "receipt_recorded", "reconciliation_required"}
        try:
            outbox = self.connection.execute("SELECT * FROM effect_outbox").fetchall()
        except sqlite3.DatabaseError as error:
            raise KernelIntegrityError("kernel effect store schema is invalid") from error
        for row in outbox:
            state = str(row["state"])
            if state not in allowed:
                raise KernelIntegrityError("kernel effect store contains an invalid state")
            try:
                intent = json.loads(str(row["intent_json"]))
            except (TypeError, json.JSONDecodeError) as error:
                raise KernelIntegrityError("kernel effect intent JSON is corrupt") from error
            if canonical_bytes(intent).decode("utf-8") != str(row["intent_json"]):
                raise KernelIntegrityError("kernel effect intent JSON is not canonical")
            attempts = int(row["attempt_count"])
            receipt_digest = row["receipt_digest"]
            reason = row["reconciliation_reason"]
            if state == "pending" and (attempts != 0 or receipt_digest is not None):
                raise KernelIntegrityError("pending effect has incoherent execution state")
            if state == "executing" and (attempts < 1 or receipt_digest is not None):
                raise KernelIntegrityError("executing effect has incoherent execution state")
            if state == "receipt_recorded" and receipt_digest is None:
                raise KernelIntegrityError("recorded effect has no receipt digest")
            if state == "reconciliation_required" and not isinstance(reason, str):
                raise KernelIntegrityError("ambiguous effect has no reconciliation reason")
            if receipt_digest is not None:
                receipt = self.connection.execute(
                    "SELECT intent_digest FROM effect_receipts WHERE receipt_digest=?",
                    (receipt_digest,),
                ).fetchone()
                if receipt is None or receipt["intent_digest"] != row["intent_digest"]:
                    raise KernelIntegrityError("effect receipt linkage is corrupt")

    def append(
        self,
        event: KernelEvent,
        *,
        expected_sequence: int | None = None,
        recorded_at: str = "1970-01-01T00:00:00Z",
        idempotency_key: str | None = None,
    ) -> int:
        """Append one event and refresh projections atomically.

        Reusing an idempotency key with the exact same event is a read-only retry.
        Any competing event, stale expected sequence, invalid chain link, or reducer
        error aborts the entire transaction.
        """

        return self.append_batch(
            ((event, idempotency_key),),
            expected_sequence=expected_sequence,
            recorded_at=recorded_at,
        )[0]

    def append_batch(
        self,
        entries: Iterable[tuple[KernelEvent, str | None]],
        *,
        expected_sequence: int | None = None,
        recorded_at: str = "1970-01-01T00:00:00Z",
    ) -> tuple[int, ...]:
        """Append a complete ordered event batch in one SQLite transaction.

        The entire batch is validated before any durable mutation. A retry is
        read-only only when every idempotency key is already bound to the exact
        corresponding event. Partial retries, duplicate event ids, duplicate
        idempotency keys, stale sequence expectations, broken digest chains, and
        reducer failures all fail closed and roll back every event in the batch.
        """

        self._require_writable()
        batch = tuple(entries)
        if not batch:
            return ()
        event_ids = [event.event_id for event, _ in batch]
        if len(set(event_ids)) != len(event_ids):
            raise KernelIntegrityError("batch event ids must be unique")
        keys = [key for _, key in batch if key is not None]
        if len(set(keys)) != len(keys):
            raise KernelIntegrityError("batch idempotency keys must be unique")

        with self._lock, self.connection:
            last = self.connection.execute(
                "SELECT sequence, digest FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            current_sequence = 0 if last is None else int(last["sequence"])
            current_digest = None if last is None else str(last["digest"])
            if expected_sequence is not None and expected_sequence != current_sequence:
                raise KernelIntegrityError("optimistic sequence check failed")

            existing_sequences: list[int | None] = []
            for event, idempotency_key in batch:
                bound_event_id: str | None = None
                if idempotency_key is not None:
                    row = self.connection.execute(
                        "SELECT event_id FROM idempotency WHERE idempotency_key=?",
                        (idempotency_key,),
                    ).fetchone()
                    if row is not None:
                        bound_event_id = str(row["event_id"])
                        if bound_event_id != event.event_id:
                            raise KernelIntegrityError(
                                "idempotency key is already bound"
                            )
                event_row = self.connection.execute(
                    "SELECT * FROM events WHERE event_id=?", (event.event_id,)
                ).fetchone()
                if event_row is None:
                    if bound_event_id is not None:
                        raise KernelIntegrityError("idempotency record has no event")
                    existing_sequences.append(None)
                    continue
                if idempotency_key is None or bound_event_id is None:
                    raise KernelIntegrityError("event id is already bound")
                if not self._stored_event_matches_locked(event_row, event):
                    raise KernelIntegrityError(
                        "idempotency key is bound to a different event"
                    )
                existing_sequences.append(int(event_row["sequence"]))

            existing_count = sum(value is not None for value in existing_sequences)
            if existing_count:
                if existing_count != len(batch):
                    raise KernelIntegrityError("partial batch retry is not permitted")
                sequences = tuple(
                    int(value) for value in existing_sequences if value is not None
                )
                if sequences != tuple(
                    range(sequences[0], sequences[0] + len(sequences))
                ):
                    raise KernelIntegrityError(
                        "idempotent batch events are not contiguous"
                    )
                return sequences

            sequence = current_sequence
            previous = current_digest
            inserted: list[int] = []
            for event, idempotency_key in batch:
                sequence += 1
                if event.previous_digest != previous:
                    raise KernelIntegrityError(
                        "event previous digest does not match batch chain head"
                    )
                digest = event.digest_for(previous)
                self.connection.execute(
                    """
                    INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        sequence,
                        event.event_id,
                        event.mission_id,
                        event.work_id,
                        event.attempt_id,
                        event.event_type,
                        event.event_version,
                        event.actor_id,
                        event.actor_role,
                        event.occurred_at,
                        recorded_at,
                        canonical_bytes(dict(event.payload)).decode("utf-8"),
                        previous,
                        digest,
                    ),
                )
                if idempotency_key is not None:
                    self.connection.execute(
                        "INSERT INTO idempotency VALUES(?,?)",
                        (idempotency_key, event.event_id),
                    )
                inserted.append(sequence)
                previous = digest
            self._rebuild_locked()
            return tuple(inserted)

    def _stored_event_matches_locked(
        self, row: sqlite3.Row, event: KernelEvent
    ) -> bool:
        try:
            payload = json.loads(str(row["payload_json"]))
        except json.JSONDecodeError:
            return False
        fields = {
            "event_id": event.event_id,
            "mission_id": event.mission_id,
            "work_id": event.work_id,
            "attempt_id": event.attempt_id,
            "event_type": event.event_type,
            "event_version": event.event_version,
            "actor_id": event.actor_id,
            "actor_role": event.actor_role,
            "occurred_at": event.occurred_at,
        }
        stored_previous = cast(str | None, row["previous_digest"])
        return (
            all(row[name] == value for name, value in fields.items())
            and stored_previous == event.previous_digest
            and canonical_bytes(payload) == canonical_bytes(dict(event.payload))
            and row["digest"] == event.digest_for(stored_previous)
        )

    def enqueue_effect(
        self,
        *,
        idempotency_key: str,
        intent_digest: str,
        intent: Mapping[str, Any],
        recorded_at: str,
    ) -> dict[str, Any]:
        """Durably record an intent before a physical adapter can run.

        A retry with the same idempotency key is read-only only when it carries
        the exact same intent. A competing intent fails closed.
        """

        self._require_writable()
        encoded = canonical_bytes(dict(intent)).decode("utf-8")
        with self._lock, self.connection:
            row = self.connection.execute(
                "SELECT * FROM effect_outbox WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                if row["intent_digest"] != intent_digest or row["intent_json"] != encoded:
                    raise KernelIntegrityError("idempotency key is already bound to another effect")
                return dict(row)
            self.connection.execute(
                """
                INSERT INTO effect_outbox(
                    idempotency_key, intent_digest, intent_json, state,
                    attempt_count, last_error, reconciliation_reason,
                    receipt_digest, created_at, updated_at
                ) VALUES(?,?,?,'pending',0,NULL,NULL,NULL,?,?)
                """,
                (idempotency_key, intent_digest, encoded, recorded_at, recorded_at),
            )
            return dict(
                self.connection.execute(
                    "SELECT * FROM effect_outbox WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
            )

    def effect_entry(self, *, intent_digest: str) -> dict[str, Any] | None:
        """Return the durable outbox entry for an intent, if present."""

        with self._lock:
            row = self.connection.execute(
                "SELECT * FROM effect_outbox WHERE intent_digest=?", (intent_digest,)
            ).fetchone()
            return None if row is None else dict(row)

    def begin_effect(self, *, intent_digest: str, recorded_at: str) -> dict[str, Any]:
        """Claim a pending intent; stale execution is never silently retried."""

        self._require_writable()
        with self._lock, self.connection:
            row = self.connection.execute(
                "SELECT * FROM effect_outbox WHERE intent_digest=?", (intent_digest,)
            ).fetchone()
            if row is None:
                raise KernelIntegrityError("effect intent is not durable")
            state = str(row["state"])
            if state != "pending":
                return dict(row)
            self.connection.execute(
                """
                UPDATE effect_outbox
                   SET state='executing', attempt_count=attempt_count+1,
                       updated_at=?, last_error=NULL
                 WHERE intent_digest=? AND state='pending'
                """,
                (recorded_at, intent_digest),
            )
            return dict(
                self.connection.execute(
                    "SELECT * FROM effect_outbox WHERE intent_digest=?", (intent_digest,)
                ).fetchone()
            )

    def record_effect_receipt(
        self,
        *,
        intent_digest: str,
        receipt_digest: str,
        receipt: Mapping[str, Any],
        recorded_at: str,
    ) -> dict[str, Any]:
        """Append one receipt and atomically link it to the outbox entry."""

        self._require_writable()
        encoded = canonical_bytes(dict(receipt)).decode("utf-8")
        with self._lock, self.connection:
            entry = self.connection.execute(
                "SELECT * FROM effect_outbox WHERE intent_digest=?", (intent_digest,)
            ).fetchone()
            if entry is None:
                raise KernelIntegrityError("effect intent is not durable")
            existing = self.connection.execute(
                "SELECT * FROM effect_receipts WHERE intent_digest=?", (intent_digest,)
            ).fetchone()
            if existing is not None:
                if existing["receipt_digest"] != receipt_digest or existing["receipt_json"] != encoded:
                    raise KernelIntegrityError("effect intent already has a different receipt")
            else:
                self.connection.execute(
                    "INSERT INTO effect_receipts VALUES(?,?,?,?)",
                    (receipt_digest, intent_digest, encoded, recorded_at),
                )
            self.connection.execute(
                """
                UPDATE effect_outbox
                   SET state='receipt_recorded', receipt_digest=?,
                       reconciliation_reason=NULL, last_error=NULL, updated_at=?
                 WHERE intent_digest=?
                """,
                (receipt_digest, recorded_at, intent_digest),
            )
            return dict(
                self.connection.execute(
                    "SELECT * FROM effect_outbox WHERE intent_digest=?", (intent_digest,)
                ).fetchone()
            )

    def mark_effect_reconciliation_required(
        self,
        *,
        intent_digest: str,
        reason: str,
        recorded_at: str,
        evidence: Mapping[str, Any] | None = None,
        state: str = "reconciliation_required",
    ) -> dict[str, Any]:
        """Persist an ambiguous external outcome without permitting blind retry."""

        self._require_writable()
        if state not in {"reconciliation_required", "reconciled"}:
            raise KernelIntegrityError("invalid effect reconciliation state")
        evidence_json = canonical_bytes(dict(evidence or {})).decode("utf-8")
        with self._lock, self.connection:
            entry = self.connection.execute(
                "SELECT * FROM effect_outbox WHERE intent_digest=?", (intent_digest,)
            ).fetchone()
            if entry is None:
                raise KernelIntegrityError("effect intent is not durable")
            if entry["state"] != "receipt_recorded":
                self.connection.execute(
                    """
                    UPDATE effect_outbox
                       SET state='reconciliation_required', reconciliation_reason=?,
                           last_error=?, updated_at=?
                     WHERE intent_digest=?
                    """,
                    (reason, reason, recorded_at, intent_digest),
                )
            self.connection.execute(
                """
                INSERT INTO effect_reconciliations(
                    intent_digest, state, reason, evidence_json, recorded_at
                ) VALUES(?,?,?,?,?)
                """,
                (intent_digest, state, reason, evidence_json, recorded_at),
            )
            return dict(
                self.connection.execute(
                    "SELECT * FROM effect_outbox WHERE intent_digest=?", (intent_digest,)
                ).fetchone()
            )

    def recover_effects(self, *, recorded_at: str) -> list[str]:
        """Mark interrupted executions ambiguous on process restart."""

        self._require_writable()
        with self._lock, self.connection:
            rows = self.connection.execute(
                "SELECT intent_digest FROM effect_outbox WHERE state='executing'"
            ).fetchall()
            for row in rows:
                digest = str(row["intent_digest"])
                self.connection.execute(
                    """
                    UPDATE effect_outbox
                       SET state='reconciliation_required',
                           reconciliation_reason='process interrupted during effect execution',
                           last_error='process interrupted during effect execution',
                           updated_at=?
                     WHERE intent_digest=? AND state='executing'
                    """,
                    (recorded_at, digest),
                )
                self.connection.execute(
                    """
                    INSERT INTO effect_reconciliations(
                        intent_digest, state, reason, evidence_json, recorded_at
                    ) VALUES(?,?,?,?,?)
                    """,
                    (digest, "reconciliation_required", "process interrupted during effect execution", "{}", recorded_at),
                )
            return [str(row["intent_digest"]) for row in rows]

    def effect_reconciliations(self, *, intent_digest: str | None = None) -> list[dict[str, Any]]:
        """Return append-only ambiguity records for repair tooling."""

        with self._lock:
            if intent_digest is None:
                rows = self.connection.execute(
                    "SELECT * FROM effect_reconciliations ORDER BY reconciliation_id"
                ).fetchall()
            else:
                rows = self.connection.execute(
                    "SELECT * FROM effect_reconciliations WHERE intent_digest=? ORDER BY reconciliation_id",
                    (intent_digest,),
                ).fetchall()
            return [dict(row) for row in rows]

    def _sequence_for_event(self, event_id: str) -> int:
        row = self.connection.execute(
            "SELECT sequence FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None:
            raise KernelIntegrityError("idempotency record has no event")
        return int(row["sequence"])

    def events(self) -> list[dict[str, Any]]:
        """Return verified event records ordered by their authoritative sequence."""

        with self._lock:
            return list(self._events_locked())

    def _events_locked(self) -> Iterator[dict[str, Any]]:
        rows = self.connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        previous: str | None = None
        for row in rows:
            item = dict(row)
            try:
                payload = json.loads(item.pop("payload_json"))
                event = KernelEvent(
                    event_id=item["event_id"],
                    mission_id=item["mission_id"],
                    event_type=item["event_type"],
                    actor_id=item["actor_id"],
                    occurred_at=item["occurred_at"],
                    payload=payload,
                    work_id=item["work_id"],
                    attempt_id=item["attempt_id"],
                    actor_role=item["actor_role"],
                    event_version=item["event_version"],
                    previous_digest=item["previous_digest"],
                )
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise KernelIntegrityError("event payload is corrupt") from error
            if item["previous_digest"] != previous or item["digest"] != event.digest_for(previous):
                raise KernelIntegrityError("event chain is corrupt")
            previous = item["digest"]
            item["payload"] = payload
            yield item

    def rebuild_projections(self) -> dict[str, Any]:
        """Discard derived views and deterministically replay from sequence one."""

        self._require_writable()
        with self._lock, self.connection:
            return self._rebuild_locked()

    def _replay_locked(self, *, through_sequence: int | None = None) -> dict[str, Any]:
        state = empty_state()
        for row in self._events_locked():
            if through_sequence is not None and row["sequence"] > through_sequence:
                break
            try:
                state = reduce_event(state, row)
            except (KeyError, TypeError, ValueError) as error:
                raise KernelIntegrityError("event sequence cannot be reduced") from error
        return state

    def _rebuild_locked(self) -> dict[str, Any]:
        state = empty_state()
        self.connection.execute("DELETE FROM mission_projection")
        self.connection.execute("DELETE FROM work_projection")
        for row in self._events_locked():
            try:
                state = reduce_event(state, row)
            except (KeyError, TypeError, ValueError) as error:
                raise KernelIntegrityError("event sequence cannot be reduced") from error
            digest = state_digest(state)
            for mission_id, status in state["missions"].items():
                self.connection.execute(
                    "INSERT OR REPLACE INTO mission_projection VALUES(?,?,?,?)",
                    (mission_id, status, row["sequence"], digest),
                )
            for work_id, work in state["work"].items():
                self.connection.execute(
                    "INSERT OR REPLACE INTO work_projection VALUES(?,?,?,?,?)",
                    (
                        work_id,
                        work["mission_id"],
                        work["status"],
                        row["sequence"],
                        digest,
                    ),
                )
        return state

    def projection(self) -> dict[str, Any]:
        """Return the current read model, without trusting it as authority."""

        with self._lock:
            if self.read_only:
                return self._replay_locked()
            state = empty_state()
            for row in self.connection.execute(
                "SELECT mission_id, status FROM mission_projection ORDER BY mission_id"
            ):
                state["missions"][row["mission_id"]] = row["status"]
            for row in self.connection.execute(
                "SELECT work_id, mission_id, status FROM work_projection ORDER BY work_id"
            ):
                state["work"][row["work_id"]] = {
                    "mission_id": row["mission_id"],
                    "status": row["status"],
                }
            return state

    def status(self, mission_id: str) -> dict[str, Any]:
        """Return one truthful mission-control view derived only from events."""

        with self._lock:
            state = self.projection()
            if mission_id not in state["missions"]:
                raise KeyError(f"unknown kernel mission: {mission_id}")
            sequence = self.connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM events"
            ).fetchone()["sequence"]
            work = [
                {"work_id": work_id, "status": value["status"]}
                for work_id, value in state["work"].items()
                if value["mission_id"] == mission_id
            ]
            return {
                "mission_id": mission_id,
                "status": state["missions"][mission_id],
                "work": work,
                "last_sequence": int(sequence),
                "state_digest": state_digest(state),
            }

    def write_snapshot(self) -> int:
        """Persist a non-authoritative, self-verifying acceleration snapshot."""

        self._require_writable()
        state = self.projection()
        sequence = self.connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM events"
        ).fetchone()["sequence"]
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO snapshots VALUES(?,?,?)",
                (int(sequence), canonical_bytes(state).decode("utf-8"), state_digest(state)),
            )
        return int(sequence)

    def load_snapshot(self) -> dict[str, Any]:
        """Return a verified snapshot or rebuild it from the event spine.

        Snapshot rows are never accepted merely because their own digest matches: the
        state is replayed through the recorded sequence to reject paired data/digest
        tampering as well.
        """

        with self._lock, self.connection:
            row = self.connection.execute(
                "SELECT sequence, state_json, state_digest FROM snapshots "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                try:
                    snapshot = json.loads(row["state_json"])
                    replayed = self._replay_locked(through_sequence=int(row["sequence"]))
                    if (
                        state_digest(snapshot) == row["state_digest"]
                        and snapshot == replayed
                    ):
                        return snapshot
                except (TypeError, ValueError, json.JSONDecodeError, KernelIntegrityError):
                    pass
            state = self._replay_locked()
            if not self.read_only:
                self._rebuild_locked()
                self.write_snapshot()
            return state

    def _require_writable(self) -> None:
        if self.read_only:
            raise KernelIntegrityError("read-only kernel store cannot be mutated")

    def close(self) -> None:
        self.connection.close()
