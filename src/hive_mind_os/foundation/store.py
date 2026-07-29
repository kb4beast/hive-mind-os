from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator, Mapping

from hive_mind_os.models import utc_now

from .authority import AuthorityDecision, authority_decision_is_authentic
from .canonical import canonical_bytes, digest, reject_private_content, stable_id

FOUNDATION_SCHEMA_VERSION = 1
RECORD_ACTIONS = {
    "idea-encounter": "foundation.opportunity.write",
    "opportunity-record": "foundation.opportunity.write",
    "usage-event": "foundation.telemetry.write",
    "usage-reconciliation": "foundation.telemetry.write",
}


class IdempotencyConflict(RuntimeError):
    """Raised when an idempotency key is reused for different content."""


class ScopeError(ValueError):
    """Raised when tenant/repository scope is absent or inconsistent."""


@dataclass(frozen=True, slots=True)
class PublicMemorySnapshot:
    """One consistent, read-only safe-public memory view for a projector."""

    repository_identity: dict[str, Any] | None
    repository_identity_digest: str | None
    schema_version: int
    schema_digest: str
    records: tuple[dict[str, Any], ...]
    source_record_count: int
    omitted_sensitive_count: int
    omitted_unsupported_count: int
    integrity_issues: tuple[str, ...]


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
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            raise

    def _initialize(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version > FOUNDATION_SCHEMA_VERSION:
            raise RuntimeError(
                f"foundation schema {version} is newer than supported "
                f"{FOUNDATION_SCHEMA_VERSION}"
            )
        existing_tables = {
            str(row[0])
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        if version == 0 and existing_tables:
            raise RuntimeError(
                "refusing to initialize foundation tables in a non-empty "
                "unversioned database"
            )
        if version == FOUNDATION_SCHEMA_VERSION:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                PRAGMA synchronous=FULL;
                PRAGMA busy_timeout=5000;
                """
            )
            self._validate_shape()
            return
        with self._lock:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                PRAGMA synchronous=FULL;
                PRAGMA busy_timeout=5000;
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS foundation_metadata (
                    store_kind TEXT PRIMARY KEY CHECK(store_kind='hive-foundation'),
                    schema_version INTEGER NOT NULL,
                    schema_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE IF NOT EXISTS repositories (
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    identity_digest TEXT NOT NULL,
                    identity_json TEXT NOT NULL,
                    registered_by TEXT NOT NULL,
                    authority_decision_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
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
                    command_digest TEXT NOT NULL,
                    command_observed_at TEXT,
                    payload_json TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    authority_decision_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    public_release_decision_id TEXT,
                    public_release_decided_by TEXT,
                    public_release_subject_digest TEXT,
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
                    evidence_json TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    authority_decision_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
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
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    authority_decision_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES outbox_messages(message_id)
                );
                CREATE TABLE IF NOT EXISTS outbox_acknowledgements (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    sink_receipt_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    authority_decision_id TEXT NOT NULL,
                    lease_id TEXT NOT NULL,
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
            try:
                for table in (
                    "repositories",
                    "foundation_metadata",
                    "records",
                    "record_relations",
                    "opportunity_keys",
                    "outbox_messages",
                    "outbox_attempts",
                    "outbox_acknowledgements",
                ):
                    self._connection.execute(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_update "
                        f"BEFORE UPDATE ON {table} BEGIN SELECT "
                        f"RAISE(ABORT, '{table} is append-only'); END"
                    )
                    self._connection.execute(
                        f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete "
                        f"BEFORE DELETE ON {table} BEGIN SELECT "
                        f"RAISE(ABORT, '{table} is append-only'); END"
                    )
                schema_digest = self._schema_digest()
                self._connection.execute(
                    "INSERT INTO foundation_metadata VALUES(?,?,?,?)",
                    (
                        "hive-foundation",
                        FOUNDATION_SCHEMA_VERSION,
                        schema_digest,
                        self._clock(),
                    ),
                )
                self._connection.execute(
                    f"PRAGMA user_version={FOUNDATION_SCHEMA_VERSION}"
                )
                self._connection.execute("COMMIT")
            except BaseException:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise
        self._validate_shape()

    def _validate_shape(self) -> None:
        required_columns = {
            "foundation_metadata": {
                "store_kind",
                "schema_version",
                "schema_digest",
                "created_at",
            },
            "repositories": {
                "tenant_id",
                "repository_id",
                "identity_digest",
                "identity_json",
                "registered_by",
                "authority_decision_id",
                "lease_id",
                "registered_at",
            },
            "records": {
                "sequence",
                "record_id",
                "record_type",
                "schema_name",
                "tenant_id",
                "repository_id",
                "stream_id",
                "stream_version",
                "previous_digest",
                "semantic_digest",
                "command_digest",
                "command_observed_at",
                "payload_json",
                "actor_id",
                "authority_decision_id",
                "lease_id",
                "public_release_decision_id",
                "public_release_decided_by",
                "public_release_subject_digest",
                "observed_at",
                "recorded_at",
                "correlation_id",
                "causation_id",
                "sensitivity",
                "retention",
                "status",
                "idempotency_key",
            },
            "record_relations": {
                "sequence",
                "tenant_id",
                "repository_id",
                "source_record_id",
                "target_record_id",
                "relation",
                "evidence_digest",
                "evidence_json",
                "actor_id",
                "authority_decision_id",
                "lease_id",
                "created_at",
            },
            "opportunity_keys": {
                "tenant_id",
                "repository_id",
                "normalization_version",
                "exact_digest",
                "structured_digest",
                "opportunity_record_id",
                "created_at",
            },
            "outbox_messages": {
                "sequence",
                "message_id",
                "source_record_id",
                "projection_kind",
                "projection_version",
                "destination",
                "payload_json",
                "payload_digest",
                "created_at",
            },
            "outbox_attempts": {
                "sequence",
                "message_id",
                "destination",
                "outcome",
                "error_class",
                "tenant_id",
                "repository_id",
                "actor_id",
                "authority_decision_id",
                "lease_id",
                "attempted_at",
            },
            "outbox_acknowledgements": {
                "sequence",
                "message_id",
                "destination",
                "sink_receipt_id",
                "tenant_id",
                "repository_id",
                "actor_id",
                "authority_decision_id",
                "lease_id",
                "acknowledged_at",
            },
        }
        for table, expected in required_columns.items():
            observed = {
                str(row[1])
                for row in self._connection.execute(f"PRAGMA table_info({table})")
            }
            if observed != expected:
                raise RuntimeError(
                    f"foundation table {table} has incompatible columns: "
                    f"{sorted(observed)}"
                )
        marker = self._connection.execute(
            "SELECT store_kind,schema_version,schema_digest FROM foundation_metadata"
        ).fetchall()
        if len(marker) != 1 or tuple(marker[0][:2]) != (
            "hive-foundation",
            FOUNDATION_SCHEMA_VERSION,
        ):
            raise RuntimeError("foundation metadata marker is missing or incompatible")
        if marker[0]["schema_digest"] != self._schema_digest():
            raise RuntimeError("foundation schema digest is missing or incompatible")

    def _schema_digest(self) -> str:
        objects = [
            tuple(row)
            for row in self._connection.execute(
                "SELECT type,name,sql FROM sqlite_master "
                "WHERE type IN ('table','index','trigger') "
                "AND name != 'sqlite_sequence' ORDER BY type,name"
            )
        ]
        return digest(objects)

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

    @staticmethod
    def _require_authority(
        authority: AuthorityDecision,
        foundation_action: str,
        *,
        tenant_id: str | None = None,
        repository_id: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        if not authority_decision_is_authentic(authority):
            raise PermissionError("foundation authority decision is not authentic")
        if (
            not authority.allowed
            or authority.foundation_action != foundation_action
            or authority.mapped_action is None
        ):
            raise PermissionError(
                f"foundation authority denied for {foundation_action}: "
                f"{authority.reason}"
            )
        for field, expected in (
            ("tenant_id", tenant_id),
            ("repository_id", repository_id),
            ("actor_id", actor_id),
        ):
            if expected is not None and getattr(authority, field) != expected:
                raise PermissionError(
                    f"foundation authority {field} does not match the command"
                )

    def register_repository(
        self,
        identity: Mapping[str, Any],
        *,
        authority: AuthorityDecision,
    ) -> str:
        tenant_id = str(identity.get("tenant_id", ""))
        repository_id = str(identity.get("repository_id", ""))
        self._require_authority(
            authority,
            "foundation.repository.register",
            tenant_id=tenant_id,
            repository_id=repository_id,
        )
        from .contracts import validate_foundation

        validation = validate_foundation("repository-identity-v1", identity)
        if not validation.valid:
            raise ValueError(
                "invalid repository identity: " + "; ".join(validation.issues)
            )
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
                "INSERT INTO repositories VALUES(?,?,?,?,?,?,?,?)",
                (
                    tenant_id,
                    repository_id,
                    identity_digest,
                    encoded,
                    authority.actor_id,
                    authority.decision_id,
                    authority.lease_id,
                    self._clock(),
                ),
            )
        return identity_digest

    def append_record(
        self,
        *,
        authority: AuthorityDecision,
        foundation_action: str,
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
        from .contracts import PHASE2_SCHEMA_NAMES, validate_foundation

        self._require_authority(
            authority,
            foundation_action,
            tenant_id=tenant_id,
            repository_id=repository_id,
            actor_id=actor_id,
        )
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
        if sensitivity == "safe-public" and (
            authority.public_release_decision_id is None
            or authority.public_release_decided_by is None
            or authority.public_release_subject_digest != digest(payload)
        ):
            raise PermissionError(
                "safe-public requires an independent public-release decision"
            )
        required_action = RECORD_ACTIONS.get(
            record_type, "foundation.memory.write"
        )
        if foundation_action != required_action:
            raise PermissionError(
                f"{record_type} requires {required_action}, not {foundation_action}"
            )
        reject_private_content(payload)
        if schema_name not in PHASE2_SCHEMA_NAMES:
            raise ValueError("foundation records require a registered Phase 2 schema")
        validation = validate_foundation(schema_name, payload)
        if not validation.valid:
            raise ValueError(
                f"invalid {schema_name} contract: {'; '.join(validation.issues)}"
            )
        if payload.get("record_type") != record_type:
            raise ValueError("record_type must match the validated contract")
        for field, expected in (
            ("tenant_id", tenant_id),
            ("repository_id", repository_id),
            ("sensitivity", sensitivity),
            ("retention", retention),
        ):
            if field in payload and payload[field] != expected:
                raise ScopeError(f"payload {field} differs from storage command")
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
                command_observed_at=observed_at,
                authority_decision_id=str(authority.decision_id),
                lease_id=str(authority.lease_id),
                public_release_decision_id=authority.public_release_decision_id,
                public_release_decided_by=authority.public_release_decided_by,
                public_release_subject_digest=(
                    authority.public_release_subject_digest
                ),
                observed_at=observed_at or self._clock(),
                correlation_id=correlation_id,
                causation_id=causation_id,
                sensitivity=sensitivity,
                retention=retention,
                status=status,
                destination=destination,
                command_digest=self._command_digest(
                    tenant_id=tenant_id,
                    repository_id=repository_id,
                    record_type=record_type,
                    schema_name=schema_name,
                    stream_id=stream_id,
                    payload=payload,
                    actor_id=actor_id,
                    idempotency_key=idempotency_key,
                    command_observed_at=observed_at,
                    authority_decision_id=str(authority.decision_id),
                    lease_id=str(authority.lease_id),
                    public_release_decision_id=(
                        authority.public_release_decision_id
                    ),
                    public_release_decided_by=(
                        authority.public_release_decided_by
                    ),
                    public_release_subject_digest=(
                        authority.public_release_subject_digest
                    ),
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    sensitivity=sensitivity,
                    retention=retention,
                    status=status,
                    destination=destination,
                ),
            )

    def append_contract_record(
        self,
        schema_name: str,
        document: Mapping[str, Any],
        *,
        authority: AuthorityDecision,
        foundation_action: str,
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
            authority=authority,
            foundation_action=foundation_action,
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
        command_observed_at: str | None,
        authority_decision_id: str,
        lease_id: str,
        public_release_decision_id: str | None,
        public_release_decided_by: str | None,
        public_release_subject_digest: str | None,
        observed_at: str,
        correlation_id: str | None,
        causation_id: str | None,
        sensitivity: str,
        retention: str,
        status: str,
        destination: str,
        command_digest: str,
    ) -> dict[str, Any]:
        semantic_digest = digest(payload)
        existing = self._connection.execute(
            "SELECT * FROM records WHERE tenant_id=? AND repository_id=? "
            "AND idempotency_key=?",
            (tenant_id, repository_id, idempotency_key),
        ).fetchone()
        if existing is not None:
            if (
                existing["semantic_digest"] != semantic_digest
                or existing["command_digest"] != command_digest
            ):
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
                stream_id,stream_version,previous_digest,semantic_digest,command_digest,
                command_observed_at,payload_json,
                actor_id,authority_decision_id,lease_id,public_release_decision_id,
                public_release_decided_by,public_release_subject_digest,
                observed_at,recorded_at,correlation_id,causation_id,
                sensitivity,retention,status,idempotency_key
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                command_digest,
                command_observed_at,
                payload_json,
                actor_id,
                authority_decision_id,
                lease_id,
                public_release_decision_id,
                public_release_decided_by,
                public_release_subject_digest,
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
    def _command_digest(
        *,
        tenant_id: str,
        repository_id: str,
        record_type: str,
        schema_name: str,
        stream_id: str,
        payload: Mapping[str, Any],
        actor_id: str,
        idempotency_key: str,
        command_observed_at: str | None,
        authority_decision_id: str,
        lease_id: str,
        public_release_decision_id: str | None,
        public_release_decided_by: str | None,
        public_release_subject_digest: str | None,
        correlation_id: str | None,
        causation_id: str | None,
        sensitivity: str,
        retention: str,
        status: str,
        destination: str,
    ) -> str:
        return digest(
            {
                "tenant_id": tenant_id,
                "repository_id": repository_id,
                "record_type": record_type,
                "schema_name": schema_name,
                "stream_id": stream_id,
                "payload": payload,
                "actor_id": actor_id,
                "idempotency_key": idempotency_key,
                "observed_at": command_observed_at,
                "authority_decision_id": authority_decision_id,
                "lease_id": lease_id,
                "public_release_decision_id": public_release_decision_id,
                "public_release_decided_by": public_release_decided_by,
                "public_release_subject_digest": public_release_subject_digest,
                "correlation_id": correlation_id,
                "causation_id": causation_id,
                "sensitivity": sensitivity,
                "retention": retention,
                "status": status,
                "destination": destination,
            }
        )

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

    @classmethod
    def read_public_memory_snapshot(
        cls,
        path: str | Path,
        *,
        tenant_id: str,
        repository_id: str,
    ) -> PublicMemorySnapshot:
        """Read one verified projection snapshot without exposing private payloads."""

        cls._require_scope(tenant_id, repository_id)
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise RuntimeError("foundation store must be an existing regular file")
        resolved_source = source.resolve()
        wal_path = Path(f"{resolved_source}-wal")
        immutable = not wal_path.exists() or wal_path.stat().st_size == 0
        uri = resolved_source.as_uri() + (
            "?mode=ro&immutable=1" if immutable else "?mode=ro"
        )
        connection = sqlite3.connect(
            uri,
            uri=True,
            isolation_level=None,
            timeout=5.0,
        )
        connection.row_factory = sqlite3.Row
        reader = cls.__new__(cls)
        reader.path = str(source.resolve())
        reader._clock = utc_now
        reader._lock = RLock()
        reader._connection = connection
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            reader._validate_shape()
            metadata = connection.execute(
                "SELECT schema_version,schema_digest FROM foundation_metadata "
                "WHERE store_kind='hive-foundation'"
            ).fetchone()
            if metadata is None:
                raise RuntimeError("foundation ownership marker is missing")
            identity_row = connection.execute(
                "SELECT identity_digest,identity_json FROM repositories "
                "WHERE tenant_id=? AND repository_id=?",
                (tenant_id, repository_id),
            ).fetchone()
            identity: dict[str, Any] | None = None
            identity_digest: str | None = None
            if identity_row is not None:
                decoded = json.loads(identity_row["identity_json"])
                if not isinstance(decoded, dict):
                    raise RuntimeError("repository identity is not an object")
                identity = decoded
                identity_digest = str(identity_row["identity_digest"])
            source_record_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM records "
                    "WHERE tenant_id=? AND repository_id=?",
                    (tenant_id, repository_id),
                ).fetchone()[0]
            )
            omitted_sensitive_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM records "
                    "WHERE tenant_id=? AND repository_id=? "
                    "AND sensitivity!='safe-public'",
                    (tenant_id, repository_id),
                ).fetchone()[0]
            )
            omitted_unsupported_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM records "
                    "WHERE tenant_id=? AND repository_id=? "
                    "AND sensitivity='safe-public' "
                    "AND (record_type!='memory-record' "
                    "OR schema_name!='memory-record-v1')",
                    (tenant_id, repository_id),
                ).fetchone()[0]
            )
            records = tuple(
                reader._decode_record(row)
                for row in connection.execute(
                    "SELECT * FROM records WHERE tenant_id=? AND repository_id=? "
                    "AND sensitivity='safe-public' "
                    "AND record_type='memory-record' "
                    "AND schema_name='memory-record-v1' "
                    "ORDER BY sequence",
                    (tenant_id, repository_id),
                ).fetchall()
            )
            issues = reader.verify_integrity(
                tenant_id=tenant_id,
                repository_id=repository_id,
            )
            return PublicMemorySnapshot(
                repository_identity=identity,
                repository_identity_digest=identity_digest,
                schema_version=int(metadata["schema_version"]),
                schema_digest=str(metadata["schema_digest"]),
                records=records,
                source_record_count=source_record_count,
                omitted_sensitive_count=omitted_sensitive_count,
                omitted_unsupported_count=omitted_unsupported_count,
                integrity_issues=issues,
            )
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()

    def add_relation(
        self,
        *,
        authority: AuthorityDecision,
        foundation_action: str,
        tenant_id: str,
        repository_id: str,
        source_record_id: str,
        target_record_id: str,
        relation: str,
        evidence: Mapping[str, Any],
        actor_id: str,
    ) -> int:
        self._require_authority(
            authority,
            foundation_action,
            tenant_id=tenant_id,
            repository_id=repository_id,
            actor_id=actor_id,
        )
        self._require_scope(tenant_id, repository_id)
        reject_private_content(evidence)
        with self._lock, self._transaction():
            expected_count = len({source_record_id, target_record_id})
            scoped = self._connection.execute(
                "SELECT COUNT(*) FROM records WHERE tenant_id=? AND repository_id=? "
                "AND record_id IN (?,?)",
                (tenant_id, repository_id, source_record_id, target_record_id),
            ).fetchone()[0]
            if scoped != expected_count:
                raise ScopeError("relation endpoints must exist in the same scope")
            cursor = self._connection.execute(
                "INSERT INTO record_relations("
                "tenant_id,repository_id,source_record_id,target_record_id,"
                "relation,evidence_digest,evidence_json,actor_id,"
                "authority_decision_id,lease_id,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    tenant_id,
                    repository_id,
                    source_record_id,
                    target_record_id,
                    relation,
                    digest(evidence),
                    canonical_bytes(evidence).decode("utf-8").rstrip("\n"),
                    actor_id,
                    authority.decision_id,
                    authority.lease_id,
                    self._clock(),
                ),
            )
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def pending_outbox(
        self,
        *,
        tenant_id: str,
        repository_id: str,
        destination: str = "local",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_scope(tenant_id, repository_id)
        if limit < 1:
            raise ValueError("limit must be positive")
        rows = self._connection.execute(
            """
            SELECT message.* FROM outbox_messages AS message
            JOIN records AS source ON source.record_id=message.source_record_id
            WHERE message.destination=?
            AND source.tenant_id=? AND source.repository_id=?
            AND NOT EXISTS(
                SELECT 1 FROM outbox_acknowledgements AS acknowledgement
                WHERE acknowledgement.message_id=message.message_id
                AND acknowledgement.destination=message.destination
            )
            ORDER BY message.sequence LIMIT ?
            """,
            (destination, tenant_id, repository_id, limit),
        ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def record_delivery_attempt(
        self,
        message_id: str,
        destination: str,
        outcome: str,
        *,
        authority: AuthorityDecision,
        tenant_id: str,
        repository_id: str,
        actor_id: str,
        error_class: str | None = None,
    ) -> int:
        self._require_authority(
            authority,
            "foundation.outbox.deliver",
            tenant_id=tenant_id,
            repository_id=repository_id,
            actor_id=actor_id,
        )
        self._require_scope(tenant_id, repository_id)
        if outcome not in {"failed", "succeeded"}:
            raise ValueError("outbox attempt outcome must be failed or succeeded")
        if error_class is not None and (
            len(error_class) > 80 or not error_class.replace("_", "").isalnum()
        ):
            raise ValueError("error_class must be a bounded symbolic value")
        with self._lock, self._transaction():
            message = self._connection.execute(
                "SELECT message.destination FROM outbox_messages AS message "
                "JOIN records AS source ON source.record_id=message.source_record_id "
                "WHERE message.message_id=? AND source.tenant_id=? "
                "AND source.repository_id=?",
                (message_id, tenant_id, repository_id),
            ).fetchone()
            if message is None or message["destination"] != destination:
                raise ScopeError("outbox destination does not match immutable message")
            cursor = self._connection.execute(
                "INSERT INTO outbox_attempts("
                "message_id,destination,outcome,error_class,tenant_id,repository_id,"
                "actor_id,authority_decision_id,lease_id,attempted_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    message_id,
                    destination,
                    outcome,
                    error_class,
                    tenant_id,
                    repository_id,
                    actor_id,
                    authority.decision_id,
                    authority.lease_id,
                    self._clock(),
                ),
            )
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    def acknowledge(
        self,
        message_id: str,
        destination: str,
        sink_receipt_id: str,
        *,
        authority: AuthorityDecision,
        tenant_id: str,
        repository_id: str,
        actor_id: str,
    ) -> None:
        self._require_authority(
            authority,
            "foundation.outbox.deliver",
            tenant_id=tenant_id,
            repository_id=repository_id,
            actor_id=actor_id,
        )
        self._require_scope(tenant_id, repository_id)
        if not sink_receipt_id.strip():
            raise ValueError("sink_receipt_id is required")
        with self._lock, self._transaction():
            message = self._connection.execute(
                "SELECT message.destination FROM outbox_messages AS message "
                "JOIN records AS source ON source.record_id=message.source_record_id "
                "WHERE message.message_id=? AND source.tenant_id=? "
                "AND source.repository_id=?",
                (message_id, tenant_id, repository_id),
            ).fetchone()
            if message is None or message["destination"] != destination:
                raise ScopeError("outbox destination does not match immutable message")
            succeeded = self._connection.execute(
                "SELECT 1 FROM outbox_attempts WHERE message_id=? AND destination=? "
                "AND tenant_id=? AND repository_id=? AND outcome='succeeded' LIMIT 1",
                (message_id, destination, tenant_id, repository_id),
            ).fetchone()
            if succeeded is None:
                raise RuntimeError(
                    "outbox acknowledgement requires a successful delivery attempt"
                )
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
                "message_id,destination,sink_receipt_id,tenant_id,repository_id,"
                "actor_id,authority_decision_id,lease_id,acknowledged_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    message_id,
                    destination,
                    sink_receipt_id,
                    tenant_id,
                    repository_id,
                    actor_id,
                    authority.decision_id,
                    authority.lease_id,
                    self._clock(),
                ),
            )

    def verify_integrity(
        self,
        *,
        tenant_id: str,
        repository_id: str,
    ) -> tuple[str, ...]:
        issues: list[str] = []
        try:
            self._validate_shape()
        except RuntimeError as error:
            issues.append(f"store schema integrity failed: {error}")
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
            canonical_payload = canonical_bytes(payload).decode("utf-8").rstrip("\n")
            if canonical_payload != row["payload_json"]:
                issues.append(f"{record_id}: payload JSON is not canonical")
            if observed_digest != row["semantic_digest"]:
                issues.append(f"{record_id}: semantic digest mismatch")
            command_digest = self._command_digest(
                tenant_id=str(row["tenant_id"]),
                repository_id=str(row["repository_id"]),
                record_type=str(row["record_type"]),
                schema_name=str(row["schema_name"]),
                stream_id=str(row["stream_id"]),
                payload=payload,
                actor_id=str(row["actor_id"]),
                idempotency_key=str(row["idempotency_key"]),
                command_observed_at=row["command_observed_at"],
                authority_decision_id=str(row["authority_decision_id"]),
                lease_id=str(row["lease_id"]),
                public_release_decision_id=row["public_release_decision_id"],
                public_release_decided_by=row["public_release_decided_by"],
                public_release_subject_digest=row[
                    "public_release_subject_digest"
                ],
                correlation_id=row["correlation_id"],
                causation_id=row["causation_id"],
                sensitivity=str(row["sensitivity"]),
                retention=str(row["retention"]),
                status=str(row["status"]),
                destination=self._record_destination(record_id),
            )
            if command_digest != row["command_digest"]:
                issues.append(f"{record_id}: command digest mismatch")
            stream_id = str(row["stream_id"])
            expected_previous = prior_by_stream.get(stream_id)
            if row["previous_digest"] != expected_previous:
                issues.append(f"{record_id}: previous digest mismatch")
            prior_by_stream[stream_id] = str(row["semantic_digest"])
            from .contracts import PHASE2_SCHEMA_NAMES, validate_foundation

            if row["schema_name"] in PHASE2_SCHEMA_NAMES:
                validation = validate_foundation(str(row["schema_name"]), payload)
                if not validation.valid:
                    issues.append(f"{record_id}: schema validation failed")
                if payload.get("record_type") != row["record_type"]:
                    issues.append(f"{record_id}: record type differs from payload")
            else:
                issues.append(f"{record_id}: schema is not registered")
        for row in self._connection.execute(
            "SELECT * FROM repositories WHERE tenant_id=? AND repository_id=?",
            (tenant_id, repository_id),
        ):
            try:
                identity = json.loads(row["identity_json"])
            except json.JSONDecodeError:
                issues.append("repository identity is not JSON")
            else:
                canonical_identity = canonical_bytes(identity).decode("utf-8").rstrip(
                    "\n"
                )
                if canonical_identity != row["identity_json"]:
                    issues.append("repository identity JSON is not canonical")
                if digest(identity) != row["identity_digest"]:
                    issues.append("repository identity digest mismatch")
        for row in self._connection.execute(
            "SELECT * FROM record_relations WHERE tenant_id=? AND repository_id=?",
            (tenant_id, repository_id),
        ):
            try:
                evidence = json.loads(row["evidence_json"])
            except json.JSONDecodeError:
                issues.append(f"relation {row['sequence']}: evidence is not JSON")
            else:
                canonical_evidence = canonical_bytes(evidence).decode(
                    "utf-8"
                ).rstrip("\n")
                if canonical_evidence != row["evidence_json"]:
                    issues.append(
                        f"relation {row['sequence']}: evidence JSON is not canonical"
                    )
                if digest(evidence) != row["evidence_digest"]:
                    issues.append(f"relation {row['sequence']}: evidence digest mismatch")
            endpoint_count = self._connection.execute(
                "SELECT COUNT(*) FROM records WHERE tenant_id=? AND repository_id=? "
                "AND record_id IN (?,?)",
                (
                    tenant_id,
                    repository_id,
                    row["source_record_id"],
                    row["target_record_id"],
                ),
            ).fetchone()[0]
            if endpoint_count != len(
                {row["source_record_id"], row["target_record_id"]}
            ):
                issues.append(f"relation {row['sequence']}: cross-scope endpoint")
        for row in self._connection.execute(
            "SELECT key.*,record.record_type,record.payload_json,"
            "record.tenant_id AS target_tenant_id,"
            "record.repository_id AS target_repository_id "
            "FROM opportunity_keys AS key "
            "LEFT JOIN records AS record "
            "ON record.record_id=key.opportunity_record_id "
            "WHERE key.tenant_id=? AND key.repository_id=?",
            (tenant_id, repository_id),
        ):
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, TypeError):
                issues.append("opportunity key target is missing or invalid")
                continue
            if (
                row["record_type"] != "opportunity-record"
                or row["target_tenant_id"] != row["tenant_id"]
                or row["target_repository_id"] != row["repository_id"]
                or payload.get("normalization_version")
                != row["normalization_version"]
                or payload.get("exact_digest") != row["exact_digest"]
                or payload.get("structured_digest") != row["structured_digest"]
            ):
                issues.append(
                    f"opportunity key {row['exact_digest']}: target mismatch"
                )
        for row in self._connection.execute(
            "SELECT * FROM outbox_messages ORDER BY sequence"
        ):
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                issues.append(f"outbox {row['message_id']}: payload is not JSON")
            else:
                canonical_payload = canonical_bytes(payload).decode(
                    "utf-8"
                ).rstrip("\n")
                if canonical_payload != row["payload_json"]:
                    issues.append(
                        f"outbox {row['message_id']}: payload JSON is not canonical"
                    )
                if digest(payload) != row["payload_digest"]:
                    issues.append(f"outbox {row['message_id']}: payload digest mismatch")
                source = self._connection.execute(
                    "SELECT record_type,schema_name,tenant_id,repository_id,"
                    "semantic_digest FROM records WHERE record_id=?",
                    (row["source_record_id"],),
                ).fetchone()
                expected = (
                    None
                    if source is None
                    else {
                        "record_id": row["source_record_id"],
                        "record_type": source["record_type"],
                        "schema_name": source["schema_name"],
                        "tenant_id": source["tenant_id"],
                        "repository_id": source["repository_id"],
                        "semantic_digest": source["semantic_digest"],
                    }
                )
                if payload != expected:
                    issues.append(
                        f"outbox {row['message_id']}: source projection mismatch"
                    )
        for table in ("outbox_attempts", "outbox_acknowledgements"):
            for row in self._connection.execute(f"SELECT * FROM {table}"):
                destination = self._connection.execute(
                    "SELECT destination FROM outbox_messages WHERE message_id=?",
                    (row["message_id"],),
                ).fetchone()
                if destination is None or destination["destination"] != row["destination"]:
                    issues.append(
                        f"{table} {row['sequence']}: destination mismatch"
                    )
                source_scope = self._connection.execute(
                    "SELECT source.tenant_id,source.repository_id "
                    "FROM outbox_messages AS message JOIN records AS source "
                    "ON source.record_id=message.source_record_id "
                    "WHERE message.message_id=?",
                    (row["message_id"],),
                ).fetchone()
                if (
                    source_scope is None
                    or source_scope["tenant_id"] != row["tenant_id"]
                    or source_scope["repository_id"] != row["repository_id"]
                ):
                    issues.append(f"{table} {row['sequence']}: scope mismatch")
                if table == "outbox_acknowledgements":
                    succeeded = self._connection.execute(
                        "SELECT 1 FROM outbox_attempts WHERE message_id=? "
                        "AND destination=? AND outcome='succeeded' LIMIT 1",
                        (row["message_id"], row["destination"]),
                    ).fetchone()
                    if succeeded is None:
                        issues.append(
                            f"{table} {row['sequence']}: no successful attempt"
                        )
        return tuple(issues)

    def _record_destination(self, record_id: str) -> str:
        row = self._connection.execute(
            "SELECT destination FROM outbox_messages WHERE source_record_id=?",
            (record_id,),
        ).fetchone()
        return "" if row is None else str(row["destination"])

    def journal_mode(self) -> str:
        return str(self._connection.execute("PRAGMA journal_mode").fetchone()[0])

    def close(self) -> None:
        self._connection.close()
