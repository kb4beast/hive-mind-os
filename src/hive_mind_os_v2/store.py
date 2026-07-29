"""Append-only SQLite/WAL authority and transactional outbox for Phase 2 records."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Iterator, Mapping, cast

from .contracts import (
    MemoryRecord,
    RepositoryIdentity,
    UsageEvent,
    canonical_json,
    contract_digest,
    utc_now,
)

STORE_SCHEMA_VERSION = 2
STORE_APPLICATION_ID = 0x484D5632  # ASCII-ish "HMV2" marker for this database.
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXPECTED_TRIGGERS = frozenset(
    {
        "metadata_no_update",
        "metadata_no_delete",
        "repositories_no_update",
        "repositories_no_delete",
        "memory_records_no_update",
        "memory_records_no_delete",
        "memory_relations_no_update",
        "memory_relations_no_delete",
        "usage_events_no_update",
        "usage_events_no_delete",
        "outbox_messages_no_update",
        "outbox_messages_no_delete",
        "outbox_deliveries_no_update",
        "outbox_deliveries_no_delete",
    }
)


class FoundationStoreError(RuntimeError):
    """Base error for the quarantined Phase 2 authority."""


class StoreVersionError(FoundationStoreError):
    """The store schema is not the exact supported version."""


class RepositoryConflictError(FoundationStoreError):
    """A repository ID was reused for different identity material."""


class DuplicateRecordError(FoundationStoreError):
    """A stable record or attempt identifier was reused."""


class ScopeViolationError(FoundationStoreError):
    """A record crossed its declared tenant/repository scope."""


class DeliveryConflictError(FoundationStoreError):
    """A consumer tried to replace an existing delivery receipt."""


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    sequence: int
    message_id: str
    aggregate_kind: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    payload_digest: str
    created_at: str


@dataclass(frozen=True, slots=True)
class IntegrityReport:
    valid: bool
    repositories_checked: int
    memory_records_checked: int
    usage_events_checked: int
    outbox_messages_checked: int
    outbox_deliveries_checked: int
    journal_mode: str
    errors: tuple[str, ...]


class FoundationStore:
    """An additive authority that does not activate generation-zero runtime paths."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        raw_path = str(path)
        if raw_path == ":memory:":
            self.path = raw_path
        else:
            normalized = Path(path).expanduser().resolve()
            normalized.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(normalized)
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            raise

    def _pragma_scalar(self, statement: str) -> object:
        row = self._connection.execute(statement).fetchone()
        if row is None:
            raise FoundationStoreError(f"SQLite returned no value for {statement}")
        return row[0]

    def _initialize(self) -> None:
        with self._lock:
            application_id = int(self._pragma_scalar("PRAGMA application_id"))
            user_version = int(self._pragma_scalar("PRAGMA user_version"))
            if application_id not in {0, STORE_APPLICATION_ID}:
                raise StoreVersionError(
                    f"database application_id {application_id!r} is not a Phase 2 store"
                )
            if user_version not in {0, STORE_SCHEMA_VERSION}:
                raise StoreVersionError(
                    f"unsupported foundation user_version {user_version!r}"
                )

            existing_tables = {
                str(row["name"])
                for row in self._connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchall()
            }
            metadata_exists = "metadata" in existing_tables
            if not metadata_exists and existing_tables:
                raise StoreVersionError(
                    "refusing to initialize an unmarked non-empty SQLite database"
                )
            if metadata_exists:
                try:
                    row = self._connection.execute(
                        "SELECT value FROM metadata WHERE key = 'schema_version'"
                    ).fetchone()
                except sqlite3.DatabaseError as error:
                    raise StoreVersionError(
                        "foundation metadata table is unreadable"
                    ) from error
                if row is None or row["value"] != str(STORE_SCHEMA_VERSION):
                    observed = None if row is None else row["value"]
                    raise StoreVersionError(
                        f"unsupported foundation schema version {observed!r}"
                    )

            self._connection.executescript(
                f"""
                PRAGMA busy_timeout=5000;
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                PRAGMA synchronous=FULL;
                PRAGMA application_id={STORE_APPLICATION_ID};
                PRAGMA user_version={STORE_SCHEMA_VERSION};

                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS repositories (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    identity_json TEXT NOT NULL,
                    identity_digest TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    UNIQUE(tenant_id, repository_id)
                );

                CREATE TABLE IF NOT EXISTS memory_records (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    record_type TEXT NOT NULL,
                    disposition TEXT NOT NULL,
                    contract_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    previous_record_digest TEXT,
                    record_digest TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    supersedes_record_id TEXT,
                    FOREIGN KEY(tenant_id, repository_id)
                        REFERENCES repositories(tenant_id, repository_id),
                    FOREIGN KEY(supersedes_record_id)
                        REFERENCES memory_records(record_id)
                );

                CREATE TABLE IF NOT EXISTS memory_relations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    target_record_id TEXT NOT NULL,
                    FOREIGN KEY(record_id) REFERENCES memory_records(record_id),
                    UNIQUE(record_id, relation_type, target_record_id)
                );

                CREATE TABLE IF NOT EXISTS usage_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    attempt_kind TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    contract_json TEXT NOT NULL,
                    previous_usage_digest TEXT,
                    event_digest TEXT NOT NULL UNIQUE,
                    occurred_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    FOREIGN KEY(tenant_id, repository_id)
                        REFERENCES repositories(tenant_id, repository_id),
                    UNIQUE(tenant_id, repository_id, attempt_id)
                );

                CREATE TABLE IF NOT EXISTS outbox_messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    aggregate_kind TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outbox_deliveries (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    consumer_id TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    delivered_at TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES outbox_messages(message_id),
                    UNIQUE(message_id, consumer_id)
                );

                CREATE INDEX IF NOT EXISTS memory_scope_sequence
                    ON memory_records(tenant_id, repository_id, sequence);
                CREATE INDEX IF NOT EXISTS usage_scope_sequence
                    ON usage_events(tenant_id, repository_id, sequence);
                CREATE INDEX IF NOT EXISTS outbox_event_sequence
                    ON outbox_messages(event_type, sequence);

                CREATE TRIGGER IF NOT EXISTS metadata_no_update
                    BEFORE UPDATE ON metadata
                    BEGIN SELECT RAISE(ABORT, 'metadata is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS metadata_no_delete
                    BEFORE DELETE ON metadata
                    BEGIN SELECT RAISE(ABORT, 'metadata is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS repositories_no_update
                    BEFORE UPDATE ON repositories
                    BEGIN SELECT RAISE(ABORT, 'repositories are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS repositories_no_delete
                    BEFORE DELETE ON repositories
                    BEGIN SELECT RAISE(ABORT, 'repositories are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS memory_records_no_update
                    BEFORE UPDATE ON memory_records
                    BEGIN SELECT RAISE(ABORT, 'memory records are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS memory_records_no_delete
                    BEFORE DELETE ON memory_records
                    BEGIN SELECT RAISE(ABORT, 'memory records are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS memory_relations_no_update
                    BEFORE UPDATE ON memory_relations
                    BEGIN SELECT RAISE(ABORT, 'memory relations are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS memory_relations_no_delete
                    BEFORE DELETE ON memory_relations
                    BEGIN SELECT RAISE(ABORT, 'memory relations are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS usage_events_no_update
                    BEFORE UPDATE ON usage_events
                    BEGIN SELECT RAISE(ABORT, 'usage events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS usage_events_no_delete
                    BEFORE DELETE ON usage_events
                    BEGIN SELECT RAISE(ABORT, 'usage events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS outbox_messages_no_update
                    BEFORE UPDATE ON outbox_messages
                    BEGIN SELECT RAISE(ABORT, 'outbox messages are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS outbox_messages_no_delete
                    BEFORE DELETE ON outbox_messages
                    BEGIN SELECT RAISE(ABORT, 'outbox messages are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS outbox_deliveries_no_update
                    BEFORE UPDATE ON outbox_deliveries
                    BEGIN SELECT RAISE(ABORT, 'outbox deliveries are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS outbox_deliveries_no_delete
                    BEFORE DELETE ON outbox_deliveries
                    BEGIN SELECT RAISE(ABORT, 'outbox deliveries are append-only'); END;
                """
            )
            row = self._connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO metadata(key,value) VALUES('schema_version',?)",
                    (str(STORE_SCHEMA_VERSION),),
                )
            elif row["value"] != str(STORE_SCHEMA_VERSION):
                raise StoreVersionError(
                    f"unsupported foundation schema version {row['value']!r}"
                )

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")

    @staticmethod
    def _message_id(payload: Mapping[str, object]) -> str:
        digest = contract_digest(dict(payload))
        return f"outbox:{digest.removeprefix('sha256:')}"

    def _append_outbox(
        self,
        aggregate_kind: str,
        aggregate_id: str,
        event_type: str,
        payload: Mapping[str, object],
    ) -> int:
        rendered = canonical_json(dict(payload))
        payload_digest = contract_digest(dict(payload))
        message_id = self._message_id(payload)
        cursor = self._connection.execute(
            """
            INSERT INTO outbox_messages(
                message_id,aggregate_kind,aggregate_id,event_type,
                payload_json,payload_digest,created_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                message_id,
                aggregate_kind,
                aggregate_id,
                event_type,
                rendered,
                payload_digest,
                utc_now(),
            ),
        )
        if cursor.lastrowid is None:
            raise FoundationStoreError("SQLite did not return an outbox sequence")
        return int(cursor.lastrowid)

    def register_repository(self, identity: RepositoryIdentity) -> int:
        with self._transaction():
            existing = self._connection.execute(
                """
                SELECT sequence,identity_digest FROM repositories
                WHERE tenant_id = ? AND repository_id = ?
                """,
                (identity.tenant_id, identity.repository_id),
            ).fetchone()
            if existing is not None:
                if existing["identity_digest"] != identity.identity_digest:
                    raise RepositoryConflictError(
                        "repository identity material changed for an existing stable ID"
                    )
                return int(existing["sequence"])
            contract = identity.to_contract()
            cursor = self._connection.execute(
                """
                INSERT INTO repositories(
                    tenant_id,repository_id,identity_json,identity_digest,created_at
                ) VALUES(?,?,?,?,?)
                """,
                (
                    identity.tenant_id,
                    identity.repository_id,
                    canonical_json(contract),
                    identity.identity_digest,
                    identity.created_at,
                ),
            )
            if cursor.lastrowid is None:
                raise FoundationStoreError("SQLite did not return a repository sequence")
            self._append_outbox(
                "repository",
                f"{identity.tenant_id}/{identity.repository_id}",
                "repository.registered.v2",
                {
                    "identity": contract,
                    "identity_digest": identity.identity_digest,
                },
            )
            return int(cursor.lastrowid)

    def _require_repository(self, tenant_id: str, repository_id: str) -> None:
        row = self._connection.execute(
            """
            SELECT 1 FROM repositories
            WHERE tenant_id = ? AND repository_id = ?
            """,
            (tenant_id, repository_id),
        ).fetchone()
        if row is None:
            raise ScopeViolationError(
                f"repository scope is not registered: {tenant_id}/{repository_id}"
            )

    def append_memory(self, record: MemoryRecord) -> int:
        with self._transaction():
            self._require_repository(record.tenant_id, record.repository_id)
            if self._connection.execute(
                "SELECT 1 FROM memory_records WHERE record_id = ?",
                (record.record_id,),
            ).fetchone() is not None:
                raise DuplicateRecordError(f"memory record already exists: {record.record_id}")
            if record.supersedes_record_id is not None:
                target = self._connection.execute(
                    """
                    SELECT tenant_id,repository_id FROM memory_records
                    WHERE record_id = ?
                    """,
                    (record.supersedes_record_id,),
                ).fetchone()
                if target is None:
                    raise ScopeViolationError("superseded memory record does not exist")
                if (
                    target["tenant_id"] != record.tenant_id
                    or target["repository_id"] != record.repository_id
                ):
                    raise ScopeViolationError("memory supersession cannot cross repository scope")
            previous = self._connection.execute(
                """
                SELECT record_digest FROM memory_records
                WHERE tenant_id = ? AND repository_id = ?
                ORDER BY sequence DESC LIMIT 1
                """,
                (record.tenant_id, record.repository_id),
            ).fetchone()
            previous_digest = previous["record_digest"] if previous is not None else None
            contract = record.to_contract()
            envelope = {
                "kind": "memory-record.v2",
                "previous_record_digest": previous_digest,
                "record": contract,
            }
            record_digest = contract_digest(envelope)
            cursor = self._connection.execute(
                """
                INSERT INTO memory_records(
                    record_id,tenant_id,repository_id,record_type,disposition,
                    contract_json,payload_digest,previous_record_digest,record_digest,
                    occurred_at,observed_at,supersedes_record_id
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    record.record_id,
                    record.tenant_id,
                    record.repository_id,
                    record.record_type,
                    record.disposition.value,
                    canonical_json(contract),
                    record.payload_digest,
                    previous_digest,
                    record_digest,
                    record.occurred_at,
                    record.observed_at,
                    record.supersedes_record_id,
                ),
            )
            if cursor.lastrowid is None:
                raise FoundationStoreError("SQLite did not return a memory sequence")
            self._connection.executemany(
                """
                INSERT INTO memory_relations(record_id,relation_type,target_record_id)
                VALUES(?,?,?)
                """,
                (
                    (record.record_id, relation.relation_type, relation.target_record_id)
                    for relation in record.relations
                ),
            )
            self._append_outbox(
                "memory",
                record.record_id,
                "memory.recorded.v2",
                {
                    **envelope,
                    "record_digest": record_digest,
                },
            )
            return int(cursor.lastrowid)

    def append_usage(self, event: UsageEvent) -> int:
        with self._transaction():
            self._require_repository(event.tenant_id, event.repository_id)
            duplicate = self._connection.execute(
                """
                SELECT event_id,attempt_id FROM usage_events
                WHERE event_id = ? OR (
                    tenant_id = ? AND repository_id = ? AND attempt_id = ?
                )
                """,
                (
                    event.event_id,
                    event.tenant_id,
                    event.repository_id,
                    event.attempt_id,
                ),
            ).fetchone()
            if duplicate is not None:
                raise DuplicateRecordError(
                    "usage event_id and attempt_id must both be unique within scope"
                )
            previous = self._connection.execute(
                """
                SELECT event_digest FROM usage_events
                WHERE tenant_id = ? AND repository_id = ?
                ORDER BY sequence DESC LIMIT 1
                """,
                (event.tenant_id, event.repository_id),
            ).fetchone()
            previous_digest = previous["event_digest"] if previous is not None else None
            contract = event.to_contract()
            envelope = {
                "kind": "usage-event.v2",
                "previous_usage_digest": previous_digest,
                "event": contract,
            }
            event_digest = contract_digest(envelope)
            cursor = self._connection.execute(
                """
                INSERT INTO usage_events(
                    event_id,tenant_id,repository_id,attempt_id,attempt_kind,outcome,
                    contract_json,previous_usage_digest,event_digest,occurred_at,observed_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event.event_id,
                    event.tenant_id,
                    event.repository_id,
                    event.attempt_id,
                    event.attempt_kind.value,
                    event.outcome.value,
                    canonical_json(contract),
                    previous_digest,
                    event_digest,
                    event.occurred_at,
                    event.observed_at,
                ),
            )
            if cursor.lastrowid is None:
                raise FoundationStoreError("SQLite did not return a usage sequence")
            self._append_outbox(
                "usage",
                event.event_id,
                "usage.recorded.v2",
                {
                    **envelope,
                    "event_digest": event_digest,
                },
            )
            return int(cursor.lastrowid)

    def pending_outbox(
        self,
        consumer_id: str,
        *,
        limit: int = 100,
    ) -> tuple[OutboxMessage, ...]:
        if not consumer_id.strip():
            raise ValueError("consumer_id cannot be empty")
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT message.*
                FROM outbox_messages AS message
                LEFT JOIN outbox_deliveries AS delivery
                  ON delivery.message_id = message.message_id
                 AND delivery.consumer_id = ?
                WHERE delivery.sequence IS NULL
                ORDER BY message.sequence
                LIMIT ?
                """,
                (consumer_id, limit),
            ).fetchall()
        return tuple(
            OutboxMessage(
                sequence=int(row["sequence"]),
                message_id=str(row["message_id"]),
                aggregate_kind=str(row["aggregate_kind"]),
                aggregate_id=str(row["aggregate_id"]),
                event_type=str(row["event_type"]),
                payload=cast(dict[str, Any], json.loads(row["payload_json"])),
                payload_digest=str(row["payload_digest"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        )

    def record_delivery(
        self,
        message_id: str,
        consumer_id: str,
        receipt_digest: str,
    ) -> int:
        if not message_id.strip() or not consumer_id.strip():
            raise ValueError("message_id and consumer_id cannot be empty")
        if not _DIGEST_PATTERN.fullmatch(receipt_digest):
            raise ValueError("receipt_digest must be a lowercase sha256 digest")
        with self._transaction():
            if self._connection.execute(
                "SELECT 1 FROM outbox_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone() is None:
                raise ScopeViolationError("outbox message does not exist")
            existing = self._connection.execute(
                """
                SELECT sequence,receipt_digest FROM outbox_deliveries
                WHERE message_id = ? AND consumer_id = ?
                """,
                (message_id, consumer_id),
            ).fetchone()
            if existing is not None:
                if existing["receipt_digest"] != receipt_digest:
                    raise DeliveryConflictError(
                        "an existing delivery receipt cannot be replaced"
                    )
                return int(existing["sequence"])
            cursor = self._connection.execute(
                """
                INSERT INTO outbox_deliveries(
                    message_id,consumer_id,receipt_digest,delivered_at
                ) VALUES(?,?,?,?)
                """,
                (message_id, consumer_id, receipt_digest, utc_now()),
            )
            if cursor.lastrowid is None:
                raise FoundationStoreError("SQLite did not return a delivery sequence")
            return int(cursor.lastrowid)

    def memory_records(
        self,
        tenant_id: str,
        repository_id: str,
    ) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT contract_json,previous_record_digest,record_digest
                FROM memory_records
                WHERE tenant_id = ? AND repository_id = ?
                ORDER BY sequence
                """,
                (tenant_id, repository_id),
            ).fetchall()
        return tuple(
            {
                "record": cast(dict[str, Any], json.loads(row["contract_json"])),
                "previous_record_digest": row["previous_record_digest"],
                "record_digest": row["record_digest"],
            }
            for row in rows
        )

    def usage_events(
        self,
        tenant_id: str,
        repository_id: str,
    ) -> tuple[dict[str, Any], ...]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT contract_json,previous_usage_digest,event_digest
                FROM usage_events
                WHERE tenant_id = ? AND repository_id = ?
                ORDER BY sequence
                """,
                (tenant_id, repository_id),
            ).fetchall()
        return tuple(
            {
                "event": cast(dict[str, Any], json.loads(row["contract_json"])),
                "previous_usage_digest": row["previous_usage_digest"],
                "event_digest": row["event_digest"],
            }
            for row in rows
        )

    def verify_integrity(self) -> IntegrityReport:
        errors: list[str] = []

        def load_object(raw: object, label: str) -> dict[str, Any] | None:
            try:
                value = json.loads(str(raw))
            except (TypeError, ValueError):
                errors.append(f"{label}:invalid-json")
                return None
            if not isinstance(value, dict):
                errors.append(f"{label}:not-object")
                return None
            return cast(dict[str, Any], value)

        def expect_row_fields(
            row: sqlite3.Row,
            contract: Mapping[str, object],
            names: tuple[str, ...],
            label: str,
        ) -> None:
            for name in names:
                if row[name] != contract.get(name):
                    errors.append(f"{label}:column-{name}")

        with self._lock:
            self._connection.execute("BEGIN")
            try:
                journal_mode = str(self._pragma_scalar("PRAGMA journal_mode")).lower()
                application_id = int(self._pragma_scalar("PRAGMA application_id"))
                user_version = int(self._pragma_scalar("PRAGMA user_version"))
                foreign_keys = int(self._pragma_scalar("PRAGMA foreign_keys"))
                synchronous = int(self._pragma_scalar("PRAGMA synchronous"))
                integrity_check = str(self._pragma_scalar("PRAGMA integrity_check"))
                foreign_key_errors = self._connection.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
                trigger_rows = self._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'trigger'"
                ).fetchall()
                metadata_rows = self._connection.execute(
                    "SELECT key,value FROM metadata ORDER BY key"
                ).fetchall()
                repository_rows = self._connection.execute(
                    "SELECT * FROM repositories ORDER BY sequence"
                ).fetchall()
                memory_rows = self._connection.execute(
                    """
                    SELECT * FROM memory_records
                    ORDER BY tenant_id,repository_id,sequence
                    """
                ).fetchall()
                relation_rows = self._connection.execute(
                    """
                    SELECT record_id,relation_type,target_record_id
                    FROM memory_relations
                    ORDER BY record_id,relation_type,target_record_id
                    """
                ).fetchall()
                usage_rows = self._connection.execute(
                    """
                    SELECT * FROM usage_events
                    ORDER BY tenant_id,repository_id,sequence
                    """
                ).fetchall()
                outbox_rows = self._connection.execute(
                    "SELECT * FROM outbox_messages ORDER BY sequence"
                ).fetchall()
                delivery_rows = self._connection.execute(
                    "SELECT * FROM outbox_deliveries ORDER BY sequence"
                ).fetchall()
            finally:
                self._connection.execute("COMMIT")

        if self.path != ":memory:" and journal_mode != "wal":
            errors.append(f"database:journal-mode-{journal_mode}")
        if self.path == ":memory:" and journal_mode not in {"memory", "wal"}:
            errors.append(f"database:journal-mode-{journal_mode}")
        if application_id != STORE_APPLICATION_ID:
            errors.append("database:application-id")
        if user_version != STORE_SCHEMA_VERSION:
            errors.append("database:user-version")
        if foreign_keys != 1:
            errors.append("database:foreign-keys-disabled")
        if synchronous != 2:
            errors.append(f"database:synchronous-{synchronous}")
        if integrity_check.lower() != "ok":
            errors.append("database:integrity-check")
        if foreign_key_errors:
            errors.append("database:foreign-key-check")
        triggers = {str(row["name"]) for row in trigger_rows}
        for missing in sorted(_EXPECTED_TRIGGERS - triggers):
            errors.append(f"database:missing-trigger-{missing}")
        metadata = {str(row["key"]): str(row["value"]) for row in metadata_rows}
        if metadata != {"schema_version": str(STORE_SCHEMA_VERSION)}:
            errors.append("database:metadata")

        expected_outbox: dict[
            str,
            tuple[str, str, str, dict[str, object]],
        ] = {}
        repository_scopes: set[tuple[str, str]] = set()
        for row in repository_rows:
            label = f"repository:{row['sequence']}"
            contract = load_object(row["identity_json"], label)
            if contract is None:
                continue
            identity_material = {
                key: contract.get(key)
                for key in (
                    "schema_version",
                    "tenant_id",
                    "repository_id",
                    "canonical_uri",
                    "default_branch",
                    "vcs_type",
                )
            }
            if contract_digest(identity_material) != row["identity_digest"]:
                errors.append(f"{label}:identity-digest")
            expect_row_fields(
                row,
                contract,
                ("tenant_id", "repository_id", "created_at"),
                label,
            )
            tenant_id = str(row["tenant_id"])
            repository_id = str(row["repository_id"])
            repository_scopes.add((tenant_id, repository_id))
            payload: dict[str, object] = {
                "identity": contract,
                "identity_digest": str(row["identity_digest"]),
            }
            message_id = self._message_id(payload)
            expected_outbox[message_id] = (
                "repository",
                f"{tenant_id}/{repository_id}",
                "repository.registered.v2",
                payload,
            )

        memory_by_id = {
            str(row["record_id"]): (str(row["tenant_id"]), str(row["repository_id"]))
            for row in memory_rows
        }
        relations_by_record: dict[str, set[tuple[str, str]]] = {}
        for relation in relation_rows:
            relations_by_record.setdefault(str(relation["record_id"]), set()).add(
                (str(relation["relation_type"]), str(relation["target_record_id"]))
            )

        memory_previous: dict[tuple[str, str], str | None] = {}
        for row in memory_rows:
            label = f"memory:{row['sequence']}"
            scope = (str(row["tenant_id"]), str(row["repository_id"]))
            expected_previous = memory_previous.get(scope)
            contract = load_object(row["contract_json"], label)
            if contract is None:
                memory_previous[scope] = str(row["record_digest"])
                continue
            expect_row_fields(
                row,
                contract,
                (
                    "record_id",
                    "tenant_id",
                    "repository_id",
                    "record_type",
                    "disposition",
                    "occurred_at",
                    "observed_at",
                    "supersedes_record_id",
                ),
                label,
            )
            if scope not in repository_scopes:
                errors.append(f"{label}:unregistered-scope")
            if row["previous_record_digest"] != expected_previous:
                errors.append(f"{label}:previous-digest")
            payload = contract.get("payload")
            if contract_digest(payload) != row["payload_digest"]:
                errors.append(f"{label}:payload-digest")
            if contract.get("payload_digest") != row["payload_digest"]:
                errors.append(f"{label}:contract-payload-digest")
            expected_digest = contract_digest(
                {
                    "kind": "memory-record.v2",
                    "previous_record_digest": expected_previous,
                    "record": contract,
                }
            )
            if expected_digest != row["record_digest"]:
                errors.append(f"{label}:record-digest")

            expected_relations: set[tuple[str, str]] = set()
            raw_relations = contract.get("relations")
            if isinstance(raw_relations, list):
                for index, relation in enumerate(raw_relations):
                    if not isinstance(relation, dict):
                        errors.append(f"{label}:relation-{index}-not-object")
                        continue
                    relation_type = relation.get("relation_type")
                    target = relation.get("target_record_id")
                    if not isinstance(relation_type, str) or not isinstance(target, str):
                        errors.append(f"{label}:relation-{index}-shape")
                        continue
                    expected_relations.add((relation_type, target))
            else:
                errors.append(f"{label}:relations-not-list")
            observed_relations = relations_by_record.get(str(row["record_id"]), set())
            if expected_relations != observed_relations:
                errors.append(f"{label}:relation-index")

            supersedes = row["supersedes_record_id"]
            if supersedes is not None and memory_by_id.get(str(supersedes)) != scope:
                errors.append(f"{label}:supersession-scope")

            outbox_payload: dict[str, object] = {
                "kind": "memory-record.v2",
                "previous_record_digest": expected_previous,
                "record": contract,
                "record_digest": str(row["record_digest"]),
            }
            message_id = self._message_id(outbox_payload)
            expected_outbox[message_id] = (
                "memory",
                str(row["record_id"]),
                "memory.recorded.v2",
                outbox_payload,
            )
            memory_previous[scope] = str(row["record_digest"])

        usage_previous: dict[tuple[str, str], str | None] = {}
        for row in usage_rows:
            label = f"usage:{row['sequence']}"
            scope = (str(row["tenant_id"]), str(row["repository_id"]))
            expected_previous = usage_previous.get(scope)
            contract = load_object(row["contract_json"], label)
            if contract is None:
                usage_previous[scope] = str(row["event_digest"])
                continue
            expect_row_fields(
                row,
                contract,
                (
                    "event_id",
                    "tenant_id",
                    "repository_id",
                    "attempt_id",
                    "attempt_kind",
                    "outcome",
                    "occurred_at",
                    "observed_at",
                ),
                label,
            )
            if scope not in repository_scopes:
                errors.append(f"{label}:unregistered-scope")
            if row["previous_usage_digest"] != expected_previous:
                errors.append(f"{label}:previous-digest")
            expected_digest = contract_digest(
                {
                    "kind": "usage-event.v2",
                    "previous_usage_digest": expected_previous,
                    "event": contract,
                }
            )
            if expected_digest != row["event_digest"]:
                errors.append(f"{label}:event-digest")
            outbox_payload = {
                "kind": "usage-event.v2",
                "previous_usage_digest": expected_previous,
                "event": contract,
                "event_digest": str(row["event_digest"]),
            }
            message_id = self._message_id(outbox_payload)
            expected_outbox[message_id] = (
                "usage",
                str(row["event_id"]),
                "usage.recorded.v2",
                outbox_payload,
            )
            usage_previous[scope] = str(row["event_digest"])

        observed_message_ids: set[str] = set()
        for row in outbox_rows:
            label = f"outbox:{row['sequence']}"
            message_id = str(row["message_id"])
            observed_message_ids.add(message_id)
            payload = load_object(row["payload_json"], label)
            if payload is None:
                continue
            payload_digest = contract_digest(payload)
            if payload_digest != row["payload_digest"]:
                errors.append(f"{label}:payload-digest")
            if self._message_id(payload) != message_id:
                errors.append(f"{label}:message-id")
            expected = expected_outbox.get(message_id)
            if expected is None:
                errors.append(f"{label}:unexpected-message")
                continue
            aggregate_kind, aggregate_id, event_type, expected_payload = expected
            if row["aggregate_kind"] != aggregate_kind:
                errors.append(f"{label}:aggregate-kind")
            if row["aggregate_id"] != aggregate_id:
                errors.append(f"{label}:aggregate-id")
            if row["event_type"] != event_type:
                errors.append(f"{label}:event-type")
            if canonical_json(payload) != canonical_json(expected_payload):
                errors.append(f"{label}:payload-record-link")
        for missing_message_id in sorted(expected_outbox.keys() - observed_message_ids):
            errors.append(f"outbox:missing-{missing_message_id}")

        outbox_message_ids = {str(row["message_id"]) for row in outbox_rows}
        for row in delivery_rows:
            label = f"delivery:{row['sequence']}"
            if str(row["message_id"]) not in outbox_message_ids:
                errors.append(f"{label}:missing-message")
            if not str(row["consumer_id"]).strip():
                errors.append(f"{label}:consumer-id")
            if not _DIGEST_PATTERN.fullmatch(str(row["receipt_digest"])):
                errors.append(f"{label}:receipt-digest")

        return IntegrityReport(
            valid=not errors,
            repositories_checked=len(repository_rows),
            memory_records_checked=len(memory_rows),
            usage_events_checked=len(usage_rows),
            outbox_messages_checked=len(outbox_rows),
            outbox_deliveries_checked=len(delivery_rows),
            journal_mode=journal_mode,
            errors=tuple(errors),
        )

    def close(self) -> None:
        with self._lock:
            self._connection.close()
