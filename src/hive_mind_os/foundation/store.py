from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator, Mapping

from hive_mind_os.models import utc_now

from .canonical import canonical_bytes, digest, reject_private_content, stable_id

FOUNDATION_SCHEMA_VERSION = 1


class IdempotencyConflict(RuntimeError):
    """Raised when an idempotency key is reused for different content."""


class ScopeError(ValueError):
    """Raised when tenant/repository scope is absent or inconsistent."""


class FoundationStore:
    """Private, opt-in, append-only Phase 2 authority and transactional outbox."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.path = str(path)
        self._clock = clock
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version > FOUNDATION_SCHEMA_VERSION:
            raise RuntimeError(
                f"foundation schema {version} is newer than supported "
                f"{FOUNDATION_SCHEMA_VERSION}"
            )
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                PRAGMA synchronous=FULL;
                PRAGMA busy_timeout=5000;
                CREATE TABLE IF NOT EXISTS repositories (
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    identity_digest TEXT NOT NULL,
                    identity_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    PRIMARY KEY(tenant_id, repository_id)
                ) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS records (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL UNIQUE,
                    record_type TEXT NOT NULL,
                    schema_name TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    stream_id TEXT NOT NULL,
                    stream_version INTEGER NOT NULL,
                    previous_digest TEXT,
                    semantic_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    correlation_id TEXT,
                    causation_id TEXT,
                    sensitivity TEXT NOT NULL,
                    retention TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    FOREIGN KEY(tenant_id, repository_id)
                        REFERENCES repositories(tenant_id, repository_id),
                    UNIQUE(tenant_id, repository_id, idempotency_key),
                    UNIQUE(tenant_id, repository_id, stream_id, stream_version)
                );
                CREATE TABLE IF NOT EXISTS record_relations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    target_record_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(source_record_id) REFERENCES records(record_id),
                    FOREIGN KEY(target_record_id) REFERENCES records(record_id)
                );
                CREATE TABLE IF NOT EXISTS opportunity_keys (
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    normalization_version TEXT NOT NULL,
                    exact_digest TEXT NOT NULL,
                    structured_digest TEXT NOT NULL,
                    opportunity_record_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(
                        tenant_id, repository_id, normalization_version, exact_digest
                    ),
                    FOREIGN KEY(opportunity_record_id) REFERENCES records(record_id)
                ) WITHOUT ROWID;
                CREATE UNIQUE INDEX IF NOT EXISTS opportunity_structured_key
                ON opportunity_keys(
                    tenant_id, repository_id, normalization_version, structured_digest
                );
                CREATE TABLE IF NOT EXISTS outbox_messages (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    source_record_id TEXT NOT NULL,
                    projection_kind TEXT NOT NULL,
                    projection_version TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(source_record_id) REFERENCES records(record_id),
                    UNIQUE(
                        source_record_id, destination, projection_kind, projection_version
                    )
                );
                CREATE TABLE IF NOT EXISTS outbox_attempts (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    error_class TEXT,
                    attempted_at TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES outbox_messages(message_id)
                );
                CREATE TABLE IF NOT EXISTS outbox_acknowledgements (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    sink_receipt_id TEXT NOT NULL,
                    acknowledged_at TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES outbox_messages(message_id),
                    UNIQUE(message_id, destination)
                );
                CREATE INDEX IF NOT EXISTS records_scope_type_time
                ON records(tenant_id, repository_id, record_type, recorded_at);
                CREATE INDEX IF NOT EXISTS records_correlation
                ON records(tenant_id, repository_id, correlation_id);
                CREATE INDEX IF NOT EXISTS relations_source
                ON record_relations(tenant_id, repository_id, source_record_id);
                CREATE INDEX IF NOT EXISTS relations_target
                ON record_relations(tenant_id, repository_id, target_record_id);
                CREATE INDEX IF NOT EXISTS outbox_destination
                ON outbox_messages(destination, sequence);
                """
            )
            for table in (
                "repositories",
                "records",
                "record_relations",
                "opportunity_keys",
                "outbox_messages",
                "outbox_attempts",
                "outbox_acknowledgements",
            ):
                self._connection.executescript(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_no_update
                    BEFORE UPDATE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS {table}_no_delete
                    BEFORE DELETE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
                    """
                )
            self._connection.execute(f"PRAGMA user_version={FOUNDATION_SCHEMA_VERSION}")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self._connection.execute("COMMIT")

    @staticmethod
    def _require_scope(tenant_id: str, repository_id: str) -> None:
        if not tenant_id.strip() or not repository_id.strip():
            raise ScopeError("tenant_id and repository_id are required")

    def register_repository(self, identity: Mapping[str, Any]) -> str:
        from .contracts import validate_foundation

        validation = validate_foundation("repository-identity-v1", identity)
        if not validation.valid:
            raise ValueError(
                "invalid repository identity: " + "; ".join(validation.issues)
            )
        tenant_id = str(identity.get("tenant_id", ""))
        repository_id = str(identity.get("repository_id", ""))
        self._require_scope(tenant_id, repository_id)
        reject_private_content(identity)
        encoded = canonical_bytes(identity).decode("utf-8").rstrip("\n")
        identity_digest = digest(identity)
        with self._lock, self._transaction():
            existing = self._connection.execute(
                "SELECT identity_digest FROM repositories "
                "WHERE tenant_id=? AND repository_id=?",
                (tenant_id, repository_id),
            ).fetchone()
            if existing is not None:
                if existing["identity_digest"] != identity_digest:
                    raise IdempotencyConflict("repository identity is immutable")
                return identity_digest
            self._connection.execute(
                "INSERT INTO repositories VALUES(?,?,?,?,?)",
                (tenant_id, repository_id, identity_digest, encoded, self._clock()),
            )
        return identity_digest

    def append_record(
        self,
        *,
        tenant_id: str,
        repository_id: str,
        record_type: str,
        schema_name: str,
        stream_id: str,
        payload: Mapping[str, Any],
        actor_id: str,
        idempotency_key: str,
        observed_at: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        sensitivity: str = "private",
        retention: str = "governed",
        status: str = "recorded",
        destination: str = "local",
    ) -> dict[str, Any]:
        self._require_scope(tenant_id, repository_id)
        if not all(
            item.strip()
            for item in (
                record_type,
                schema_name,
                stream_id,
                actor_id,
                idempotency_key,
                destination,
            )
        ):
            raise ValueError("record identity fields cannot be empty")
        if sensitivity not in {"private", "internal", "safe-public"}:
            raise ValueError("unsupported sensitivity")
        reject_private_content(payload)
        with self._lock, self._transaction():
            return self._append_record_in_transaction(
                tenant_id=tenant_id,
                repository_id=repository_id,
                record_type=record_type,
                schema_name=schema_name,
                stream_id=stream_id,
                payload=payload,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                observed_at=observed_at or self._clock(),
                correlation_id=correlation_id,
                causation_id=causation_id,
                sensitivity=sensitivity,
                retention=retention,
                status=status,
                destination=destination,
            )

    def append_contract_record(
        self,
        schema_name: str,
        document: Mapping[str, Any],
        *,
        tenant_id: str,
        repository_id: str,
        stream_id: str,
        actor_id: str,
        idempotency_key: str,
        sensitivity: str = "private",
        status: str = "recorded",
    ) -> dict[str, Any]:
        from .contracts import validate_foundation

        validation = validate_foundation(schema_name, document)
        if not validation.valid:
            raise ValueError(
                f"invalid {schema_name} contract: {'; '.join(validation.issues)}"
            )
        for field, expected in (
            ("tenant_id", tenant_id),
            ("repository_id", repository_id),
        ):
            if field in document and document[field] != expected:
                raise ScopeError(f"contract {field} differs from storage scope")
        record_type = str(document.get("record_type", "")).strip()
        if not record_type:
            raise ValueError("contract record_type is required")
        return self.append_record(
            tenant_id=tenant_id,
            repository_id=repository_id,
            record_type=record_type,
            schema_name=schema_name,
            stream_id=stream_id,
            payload=document,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            sensitivity=sensitivity,
            status=status,
        )

    def _append_record_in_transaction(
        self,
        *,
        tenant_id: str,
        repository_id: str,
        record_type: str,
        schema_name: str,
        stream_id: str,
        payload: Mapping[str, Any],
        actor_id: str,
        idempotency_key: str,
        observed_at: str,
        correlation_id: str | None,
        causation_id: str | None,
        sensitivity: str,
        retention: str,
        status: str,
        destination: str,
    ) -> dict[str, Any]:
        semantic_digest = digest(payload)
        existing = self._connection.execute(
            "SELECT * FROM records WHERE tenant_id=? AND repository_id=? "
            "AND idempotency_key=?",
            (tenant_id, repository_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            if existing["semantic_digest"] != semantic_digest:
                raise IdempotencyConflict("idempotency key reused for different content")
            return self._decode_record(existing)
        repository = self._connection.execute(
            "SELECT 1 FROM repositories WHERE tenant_id=? AND repository_id=?",
            (tenant_id, repository_id),
        ).fetchone()
        if repository is None:
            raise ScopeError("repository identity must be registered first")
        prior = self._connection.execute(
            "SELECT stream_version,semantic_digest FROM records "
            "WHERE tenant_id=? AND repository_id=? AND stream_id=? "
            "ORDER BY stream_version DESC LIMIT 1",
            (tenant_id, repository_id, stream_id),
        ).fetchone()
        stream_version = 1 if prior is None else int(prior["stream_version"]) + 1
        previous_digest = None if prior is None else str(prior["semantic_digest"])
        record_id = stable_id(
            "record",
            {
                "tenant_id": tenant_id,
                "repository_id": repository_id,
                "idempotency_key": idempotency_key,
                "semantic_digest": semantic_digest,
            },
        )
        recorded_at = self._clock()
        payload_json = canonical_bytes(payload).decode("utf-8").rstrip("\n")
        self._connection.execute(
            """
            INSERT INTO records(
                record_id,record_type,schema_name,tenant_id,repository_id,
                stream_id,stream_version,previous_digest,semantic_digest,payload_json,
                actor_id,observed_at,recorded_at,correlation_id,causation_id,
                sensitivity,retention,status,idempotency_key
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record_id,
                record_type,
                schema_name,
                tenant_id,
                repository_id,
                stream_id,
                stream_version,
                previous_digest,
                semantic_digest,
                payload_json,
                actor_id,
                observed_at,
                recorded_at,
                correlation_id,
                causation_id,
                sensitivity,
                retention,
                status,
                idempotency_key,
            ),
        )
        outbox_payload = {
            "record_id": record_id,
            "record_type": record_type,
            "schema_name": schema_name,
            "tenant_id": tenant_id,
            "repository_id": repository_id,
            "semantic_digest": semantic_digest,
        }
        message_id = stable_id(
            "outbox",
            {
                "source_record_id": record_id,
                "destination": destination,
                "projection_kind": record_type,
                "projection_version": "1",
            },
        )
        outbox_json = canonical_bytes(outbox_payload).decode("utf-8").rstrip("\n")
        self._connection.execute(
            """
            INSERT INTO outbox_messages(
                message_id,source_record_id,projection_kind,projection_version,
                destination,payload_json,payload_digest,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                message_id,
                record_id,
                record_type,
                "1",
                destination,
                outbox_json,
                digest(outbox_payload),
                recorded_at,
            ),
        )
        row = self._connection.execute(
            "SELECT * FROM records WHERE record_id=?", (record_id,)
        ).fetchone()
        assert row is not None
        return self._decode_record(row)

    @staticmethod
    def _decode_record(row: sqlite3.Row) -> dict[str, Any]:
        return {**dict(row), "payload": json.loads(row["payload_json"])}

    def records(
        self,
        *,
        tenant_id: str,
        repository_id: str,
        record_type: str | None = None,
    ) -> list[dict[str, Any]]:
        self._require_scope(tenant_id, repository_id)
        query = "SELECT * FROM records WHERE tenant_id=? AND repository_id=?"
        parameters: list[Any] = [tenant_id, repository_id]
        if record_type is not None:
            query += " AND record_type=?"
            parameters.append(record_type)
        query += " ORDER BY sequence"
        return [
            self._decode_record(row)
            for row in self._connection.execute(query, parameters).fetchall()
        ]

    def add_relation(
        self,
        *,
        tenant_id: str,
        repository_id: str,
        source_record_id: str,
        target_record_id: str,
        relation: str,
        evidence: Mapping[str, Any],
    ) -> int:
        self._require_scope(tenant_id, repository_id)
        reject_private_content(evidence)
        with self._lock, self._transaction():
            scoped = self._connection.execute(
                "SELECT COUNT(*) FROM records WHERE tenant_id=? AND repository_id=? "
                "AND record_id IN (?,?)",
                (tenant_id, repository_id, source_record_id, target_record_id),
            ).fetchone()[0]
            if scoped != 2 and source_record_id != target_record_id:
                raise ScopeError("relation endpoints must exist in the same scope")
            cursor = self._connection.execute(
                "INSERT INTO record_relations("
                "tenant_id,repository_id,source_record_id,target_record_id,"
                "relation,evidence_digest,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    tenant_id,
                    repository_id,
                    source_record_id,
                    target_record_id,
                    relation,
                    digest(evidence),
                    self._clock(),
                ),
            )
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def pending_outbox(self, destination: str = "local", limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = self._connection.execute(
            """
            SELECT message.* FROM outbox_messages AS message
            WHERE message.destination=?
            AND NOT EXISTS(
                SELECT 1 FROM outbox_acknowledgements AS acknowledgement
                WHERE acknowledgement.message_id=message.message_id
                AND acknowledgement.destination=message.destination
            )
            ORDER BY message.sequence LIMIT ?
            """,
            (destination, limit),
        ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def record_delivery_attempt(
        self,
        message_id: str,
        destination: str,
        outcome: str,
        *,
        error_class: str | None = None,
    ) -> int:
        if error_class is not None and (
            len(error_class) > 80 or not error_class.replace("_", "").isalnum()
        ):
            raise ValueError("error_class must be a bounded symbolic value")
        with self._lock, self._transaction():
            cursor = self._connection.execute(
                "INSERT INTO outbox_attempts("
                "message_id,destination,outcome,error_class,attempted_at) "
                "VALUES(?,?,?,?,?)",
                (message_id, destination, outcome, error_class, self._clock()),
            )
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def acknowledge(self, message_id: str, destination: str, sink_receipt_id: str) -> None:
        with self._lock, self._transaction():
            existing = self._connection.execute(
                "SELECT sink_receipt_id FROM outbox_acknowledgements "
                "WHERE message_id=? AND destination=?",
                (message_id, destination),
            ).fetchone()
            if existing is not None:
                if existing["sink_receipt_id"] != sink_receipt_id:
                    raise IdempotencyConflict(
                        "outbox acknowledgement conflicts with prior receipt"
                    )
                return
            self._connection.execute(
                "INSERT INTO outbox_acknowledgements("
                "message_id,destination,sink_receipt_id,acknowledged_at) VALUES(?,?,?,?)",
                (message_id, destination, sink_receipt_id, self._clock()),
            )

    def verify_integrity(
        self,
        *,
        tenant_id: str,
        repository_id: str,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        prior_by_stream: dict[str, str] = {}
        rows = self._connection.execute(
            "SELECT * FROM records WHERE tenant_id=? AND repository_id=? "
            "ORDER BY stream_id,stream_version",
            (tenant_id, repository_id),
        ).fetchall()
        for row in rows:
            record_id = str(row["record_id"])
            try:
                payload = json.loads(row["payload_json"])
                observed_digest = digest(payload)
            except (json.JSONDecodeError, TypeError, ValueError):
                issues.append(f"{record_id}: payload is not canonical JSON")
                continue
            if observed_digest != row["semantic_digest"]:
                issues.append(f"{record_id}: semantic digest mismatch")
            stream_id = str(row["stream_id"])
            expected_previous = prior_by_stream.get(stream_id)
            if row["previous_digest"] != expected_previous:
                issues.append(f"{record_id}: previous digest mismatch")
            prior_by_stream[stream_id] = str(row["semantic_digest"])
        return tuple(issues)

    def journal_mode(self) -> str:
        return str(self._connection.execute("PRAGMA journal_mode").fetchone()[0])

    def close(self) -> None:
        self._connection.close()
