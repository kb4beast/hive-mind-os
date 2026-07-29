from __future__ import annotations

import json
import os
import shutil
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterator, Mapping, Sequence

from hive_mind_os.models import utc_now

from .authority import AuthorityDecision, authority_decision_is_authentic
from .canonical import canonical_bytes, digest
from .public_memory_contracts import validate_public_memory
from .store import FoundationStore, PublicMemorySnapshot

PUBLIC_MEMORY_STORE_SCHEMA_VERSION = 1
PUBLIC_MEMORY_STORE_KIND = "hive-public-memory-release"
PUBLIC_MEMORY_ENVELOPE_VERSION = "hive-public-memory-envelope/v1"
PUBLIC_MEMORY_RELEASE_POLICY = "hive-safe-public-memory-release/v1"
PUBLIC_MEMORY_RELEASE_ACTION = "foundation.public-memory.release"
PUBLIC_MEMORY_RELEASER = "foundation-public-memory-releaser-v1"
MAX_PUBLIC_RECORDS = 100_000
MAX_ENVELOPE_BYTES = 1 << 20
MAX_ROW_METADATA_BYTES = 64 << 10
MAX_RECEIPT_BYTES = 16 << 20
MAX_PENDING_TRANSACTIONS = 1_024
_WINDOWS_REPARSE_ATTRIBUTE = 0x400
_MATERIALIZATION_SEAL = object()

PUBLIC_PAYLOAD_FIELDS = (
    "record_type",
    "schema_version",
    "memory_id",
    "memory_kind",
    "repository_id",
    "tenant_id",
    "mission_id",
    "run_id",
    "step_id",
    "actor_id",
    "payload_digest",
    "previous_record_id",
    "supersedes_record_id",
    "observed_at",
    "recorded_at",
    "causation_id",
    "correlation_id",
    "source_refs",
    "claim_refs",
    "evidence_refs",
    "court_refs",
    "code_receipt_refs",
    "generation_refs",
    "status",
    "confidence_ppm",
    "freshness_expires_at",
    "contradiction_refs",
    "relation_refs",
    "owner_id",
    "sensitivity",
    "access_purpose",
    "retention",
    "deletion_policy",
    "quarantine_state",
    "appeal_state",
    "content_digest",
)
PUBLIC_MEMORY_RELEASE_POLICY_DIGEST = digest(
    {
        "policy": PUBLIC_MEMORY_RELEASE_POLICY,
        "envelope_version": PUBLIC_MEMORY_ENVELOPE_VERSION,
        "public_payload_fields": PUBLIC_PAYLOAD_FIELDS,
        "required_null_fields": (
            "protected_content_ref",
            "retrieval_receipt",
        ),
    }
)


class PublicMemorySeparationError(RuntimeError):
    """Raised when public/private separation cannot be proven."""


@dataclass(frozen=True, slots=True)
class PublicMemoryMaterializationResult:
    schema_version: str
    status: str
    tenant_id: str
    repository_id: str
    source_cursor: str
    released_record_count: int
    existing_record_count: int
    public_store_logical_digest: str
    receipt_locator: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "tenant_id": self.tenant_id,
            "repository_id": self.repository_id,
            "source_cursor": self.source_cursor,
            "released_record_count": self.released_record_count,
            "existing_record_count": self.existing_record_count,
            "public_store_logical_digest": self.public_store_logical_digest,
            "receipt_locator": self.receipt_locator,
        }


def _is_linklike(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
        details = path.lstat()
    except OSError:
        return False
    attributes = int(getattr(details, "st_file_attributes", 0))
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return bool(attributes & (reparse_flag or _WINDOWS_REPARSE_ATTRIBUTE))


def _is_multilink_file(path: Path) -> bool:
    try:
        details = path.stat(follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(details.st_mode) and int(details.st_nlink) != 1


def _require_scope(tenant_id: str, repository_id: str) -> None:
    if not tenant_id.strip() or not repository_id.strip():
        raise PublicMemorySeparationError("tenant and repository scope are required")


def _require_regular_file(path: Path, label: str) -> Path:
    supplied = path.absolute()
    if _is_linklike(supplied) or not supplied.is_file():
        raise PublicMemorySeparationError(f"{label} must be a regular non-link file")
    resolved = supplied.resolve(strict=True)
    if resolved != supplied or _is_multilink_file(resolved):
        raise PublicMemorySeparationError(
            f"{label} must not be linked, escaped, or hard-linked"
        )
    return resolved


def _validate_parent_for_new_file(path: Path, label: str) -> None:
    parent = path.absolute().parent
    if not parent.is_dir() or _is_linklike(parent):
        raise PublicMemorySeparationError(
            f"{label} parent must be an existing regular directory"
        )
    if parent.resolve(strict=True) != parent:
        raise PublicMemorySeparationError(f"{label} parent is linked or escaped")


def _resolve_repository(path: str | Path) -> Path:
    supplied = Path(path).absolute()
    if _is_linklike(supplied) or not supplied.is_dir():
        raise PublicMemorySeparationError(
            "repository root must be an existing regular directory"
        )
    resolved = supplied.resolve(strict=True)
    if resolved != supplied:
        raise PublicMemorySeparationError("repository root is linked or escaped")
    return resolved


def _resolve_protected_root(path: str | Path, repository: Path) -> Path:
    supplied = Path(path).absolute()
    if supplied.parent == supplied:
        raise PublicMemorySeparationError("protected state root cannot be a filesystem root")
    if supplied.exists():
        if not supplied.is_dir() or _is_linklike(supplied):
            raise PublicMemorySeparationError(
                "protected state root must be a regular directory"
            )
        resolved = supplied.resolve(strict=True)
        if resolved != supplied:
            raise PublicMemorySeparationError(
                "protected state root is linked or escaped"
            )
    else:
        parent = supplied.parent
        if not parent.is_dir() or _is_linklike(parent):
            raise PublicMemorySeparationError(
                "protected state parent must be an existing regular directory"
            )
        if parent.resolve(strict=True) != parent:
            raise PublicMemorySeparationError(
                "protected state parent is linked or escaped"
            )
        resolved = supplied
    if resolved.is_relative_to(repository) or repository.is_relative_to(resolved):
        raise PublicMemorySeparationError(
            "protected state and repository must be disjoint"
        )
    return resolved


def _source_cursor(records: Sequence[Mapping[str, Any]]) -> str:
    body = [
        {
            "record_id": str(record["record_id"]),
            "semantic_digest": str(record["semantic_digest"]),
        }
        for record in sorted(records, key=lambda item: str(item["record_id"]))
    ]
    encoded = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"memory-set:{sha256(encoded).hexdigest()}"


def _public_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if set(payload) - set(PUBLIC_PAYLOAD_FIELDS) != {
        "protected_content_ref",
        "retrieval_receipt",
    }:
        raise PublicMemorySeparationError(
            "memory payload fields differ from the public release allowlist"
        )
    if payload.get("protected_content_ref") is not None:
        raise PublicMemorySeparationError(
            "separated release forbids protected content references"
        )
    if payload.get("retrieval_receipt") is not None:
        raise PublicMemorySeparationError(
            "separated release forbids retrieval receipts"
        )
    return {field: payload[field] for field in PUBLIC_PAYLOAD_FIELDS}


def _public_envelope(
    record: Mapping[str, Any],
    *,
    tenant_id: str,
    repository_id: str,
) -> dict[str, Any]:
    payload = record.get("payload")
    if not isinstance(payload, Mapping):
        raise PublicMemorySeparationError("released memory payload is not an object")
    source_digest = str(record.get("semantic_digest", ""))
    if (
        record.get("record_type") != "memory-record"
        or record.get("schema_name") != "memory-record-v1"
        or record.get("tenant_id") != tenant_id
        or record.get("repository_id") != repository_id
        or record.get("sensitivity") != "safe-public"
        or payload.get("sensitivity") != "safe-public"
        or payload.get("quarantine_state") != "none"
        or payload.get("status") == "quarantined"
        or not record.get("public_release_decision_id")
        or not record.get("public_release_decided_by")
        or record.get("public_release_subject_digest") != source_digest
    ):
        raise PublicMemorySeparationError(
            "record does not satisfy the separated safe-public release boundary"
        )
    envelope = {
        "schema_version": PUBLIC_MEMORY_ENVELOPE_VERSION,
        "release_policy": PUBLIC_MEMORY_RELEASE_POLICY,
        "record_id": record["record_id"],
        "record_type": record["record_type"],
        "source_schema": record["schema_name"],
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "source_digest": source_digest,
        "source_previous_digest": record["previous_digest"],
        "actor_id": record["actor_id"],
        "observed_at": record["observed_at"],
        "recorded_at": record["recorded_at"],
        "status": record["status"],
        "sensitivity": record["sensitivity"],
        "public_release_decision_id": record["public_release_decision_id"],
        "public_release_decided_by": record["public_release_decided_by"],
        "public_release_subject_digest": record[
            "public_release_subject_digest"
        ],
        "payload": _public_payload(payload),
    }
    validation = validate_public_memory("public-memory-envelope-v1", envelope)
    if not validation.valid:
        raise PublicMemorySeparationError(
            "public memory envelope is invalid: " + "; ".join(validation.issues)
        )
    if len(canonical_bytes(envelope)) > MAX_ENVELOPE_BYTES:
        raise PublicMemorySeparationError("public memory envelope exceeds size bound")
    return envelope


class PublicMemoryReleaseStore:
    """Single-scope, append-only, safe-public release persistence."""

    def __init__(
        self,
        path: str | Path,
        *,
        tenant_id: str,
        repository_id: str,
        repository_identity_digest: str,
        source_foundation_schema_version: int,
        source_foundation_schema_digest: str,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        _require_scope(tenant_id, repository_id)
        self.path = str(Path(path))
        self.tenant_id = tenant_id
        self.repository_id = repository_id
        self.repository_identity_digest = repository_identity_digest
        self.source_foundation_schema_version = source_foundation_schema_version
        self.source_foundation_schema_digest = source_foundation_schema_digest
        self._clock = clock
        self._lock = RLock()
        target = Path(path)
        if target.exists():
            _require_regular_file(target, "public release store")
        else:
            _validate_parent_for_new_file(target, "public release store")
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
        existing_tables = {
            str(row[0])
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        if version > PUBLIC_MEMORY_STORE_SCHEMA_VERSION:
            raise PublicMemorySeparationError(
                f"public memory schema {version} is newer than supported "
                f"{PUBLIC_MEMORY_STORE_SCHEMA_VERSION}"
            )
        if version == 0 and existing_tables:
            raise PublicMemorySeparationError(
                "refusing to initialize a non-empty unversioned public store"
            )
        if version == PUBLIC_MEMORY_STORE_SCHEMA_VERSION:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                PRAGMA synchronous=FULL;
                PRAGMA busy_timeout=5000;
                """
            )
            self._validate_shape()
            self._validate_scope_metadata()
            return
        self._connection.executescript(
            """
                BEGIN IMMEDIATE;
                CREATE TABLE public_memory_metadata (
                    store_kind TEXT PRIMARY KEY
                        CHECK(store_kind='hive-public-memory-release'),
                    schema_version INTEGER NOT NULL,
                    schema_digest TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    repository_id TEXT NOT NULL,
                    repository_identity_digest TEXT NOT NULL,
                    source_foundation_schema_version INTEGER NOT NULL,
                    source_foundation_schema_digest TEXT NOT NULL,
                    release_policy TEXT NOT NULL,
                    release_policy_digest TEXT NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE released_memory (
                    release_id TEXT PRIMARY KEY,
                    source_record_id TEXT NOT NULL UNIQUE,
                    source_digest TEXT NOT NULL,
                    envelope_digest TEXT NOT NULL UNIQUE,
                    envelope_json TEXT NOT NULL,
                    release_decision_id TEXT NOT NULL,
                    release_decided_by TEXT NOT NULL,
                    released_at TEXT NOT NULL
                ) WITHOUT ROWID;
            """
        )
        try:
            for table in ("public_memory_metadata", "released_memory"):
                self._connection.execute(
                    f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
                    f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
                )
                self._connection.execute(
                    f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
                    f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
                )
            schema_digest = self._schema_digest()
            self._connection.execute(
                "INSERT INTO public_memory_metadata VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    PUBLIC_MEMORY_STORE_KIND,
                    PUBLIC_MEMORY_STORE_SCHEMA_VERSION,
                    schema_digest,
                    self.tenant_id,
                    self.repository_id,
                    self.repository_identity_digest,
                    self.source_foundation_schema_version,
                    self.source_foundation_schema_digest,
                    PUBLIC_MEMORY_RELEASE_POLICY,
                    PUBLIC_MEMORY_RELEASE_POLICY_DIGEST,
                ),
            )
            self._connection.execute(
                f"PRAGMA user_version={PUBLIC_MEMORY_STORE_SCHEMA_VERSION}"
            )
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            PRAGMA synchronous=FULL;
            PRAGMA busy_timeout=5000;
            """
        )
        self._validate_shape()
        self._validate_scope_metadata()

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

    def _schema_digest(self) -> str:
        rows = self._connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE type IN ('table','index','trigger') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
        normalized = [
            {
                "type": str(row["type"]),
                "name": str(row["name"]),
                "table": str(row["tbl_name"]),
                "sql": " ".join(str(row["sql"]).split()),
            }
            for row in rows
        ]
        return digest(normalized)

    def _validate_shape(self) -> None:
        metadata = self._connection.execute(
            "SELECT * FROM public_memory_metadata "
            "WHERE store_kind=?",
            (PUBLIC_MEMORY_STORE_KIND,),
        ).fetchone()
        if metadata is None:
            raise PublicMemorySeparationError(
                "public release store ownership marker is missing"
            )
        if int(metadata["schema_version"]) != PUBLIC_MEMORY_STORE_SCHEMA_VERSION:
            raise PublicMemorySeparationError("public release schema version mismatch")
        if str(metadata["schema_digest"]) != self._schema_digest():
            raise PublicMemorySeparationError("public release schema digest mismatch")

    def _validate_scope_metadata(self) -> None:
        row = self._connection.execute(
            "SELECT * FROM public_memory_metadata "
            "WHERE store_kind=?",
            (PUBLIC_MEMORY_STORE_KIND,),
        ).fetchone()
        assert row is not None
        expected = {
            "tenant_id": self.tenant_id,
            "repository_id": self.repository_id,
            "repository_identity_digest": self.repository_identity_digest,
            "source_foundation_schema_version": self.source_foundation_schema_version,
            "source_foundation_schema_digest": self.source_foundation_schema_digest,
            "release_policy": PUBLIC_MEMORY_RELEASE_POLICY,
            "release_policy_digest": PUBLIC_MEMORY_RELEASE_POLICY_DIGEST,
        }
        for field, value in expected.items():
            if row[field] != value:
                raise PublicMemorySeparationError(
                    f"public release store {field} mismatch"
                )

    def _validate_content_bounds(self) -> None:
        bounds = self._connection.execute(
            """
            SELECT
                COUNT(*) AS record_count,
                COALESCE(MAX(length(CAST(envelope_json AS BLOB))), 0)
                    AS envelope_bytes,
                COALESCE(MAX(
                    length(CAST(release_id AS BLOB))
                    + length(CAST(source_record_id AS BLOB))
                    + length(CAST(source_digest AS BLOB))
                    + length(CAST(envelope_digest AS BLOB))
                    + length(CAST(release_decision_id AS BLOB))
                    + length(CAST(release_decided_by AS BLOB))
                    + length(CAST(released_at AS BLOB))
                ), 0) AS metadata_bytes
            FROM released_memory
            """
        ).fetchone()
        assert bounds is not None
        if int(bounds["record_count"]) > MAX_PUBLIC_RECORDS:
            raise PublicMemorySeparationError(
                "public release store exceeds record bound"
            )
        if int(bounds["envelope_bytes"]) > MAX_ENVELOPE_BYTES:
            raise PublicMemorySeparationError(
                "public memory envelope exceeds size bound"
            )
        if int(bounds["metadata_bytes"]) > MAX_ROW_METADATA_BYTES:
            raise PublicMemorySeparationError(
                "public memory row metadata exceeds size bound"
            )

    @staticmethod
    def _require_release_authority(
        authority: AuthorityDecision,
        *,
        tenant_id: str,
        repository_id: str,
    ) -> None:
        if not authority_decision_is_authentic(authority):
            raise PublicMemorySeparationError(
                "public release authority is not authentic"
            )
        if (
            not authority.allowed
            or authority.foundation_action != PUBLIC_MEMORY_RELEASE_ACTION
            or authority.tenant_id != tenant_id
            or authority.repository_id != repository_id
            or authority.actor_id != PUBLIC_MEMORY_RELEASER
            or not authority.decision_id
            or not authority.lease_id
        ):
            raise PublicMemorySeparationError(
                "public release authority does not allow this scope"
            )

    @staticmethod
    def _release_entry(envelope: Mapping[str, Any]) -> dict[str, str]:
        envelope_json = canonical_bytes(envelope).decode("utf-8").rstrip("\n")
        envelope_digest = digest(envelope)
        release_id = "release:" + sha256(
            canonical_bytes(
                {
                    "tenant_id": envelope["tenant_id"],
                    "repository_id": envelope["repository_id"],
                    "source_record_id": envelope["record_id"],
                    "source_digest": envelope["source_digest"],
                    "release_policy": PUBLIC_MEMORY_RELEASE_POLICY,
                    "envelope_digest": envelope_digest,
                }
            )
        ).hexdigest()
        return {
            "release_id": release_id,
            "source_record_id": str(envelope["record_id"]),
            "source_digest": str(envelope["source_digest"]),
            "envelope_digest": envelope_digest,
            "envelope_json": envelope_json,
            "release_decision_id": str(envelope["public_release_decision_id"]),
            "release_decided_by": str(envelope["public_release_decided_by"]),
            "released_at": str(envelope["recorded_at"]),
        }

    def _plan_envelopes(
        self,
        envelopes: Sequence[Mapping[str, Any]],
    ) -> tuple[tuple[dict[str, str], ...], str]:
        if len(envelopes) > MAX_PUBLIC_RECORDS:
            raise PublicMemorySeparationError("public release exceeds record bound")
        self._validate_content_bounds()
        current = {
            str(row["source_record_id"]): dict(row)
            for row in self._connection.execute(
                "SELECT release_id,source_record_id,source_digest,envelope_digest "
                "FROM released_memory ORDER BY source_record_id"
            )
        }
        entries: list[dict[str, str]] = []
        for envelope in envelopes:
            validation = validate_public_memory(
                "public-memory-envelope-v1",
                envelope,
            )
            if not validation.valid:
                raise PublicMemorySeparationError(
                    "public memory envelope is invalid: "
                    + "; ".join(validation.issues)
                )
            if (
                envelope["tenant_id"] != self.tenant_id
                or envelope["repository_id"] != self.repository_id
            ):
                raise PublicMemorySeparationError(
                    "public memory envelope scope mismatch"
                )
            entry = self._release_entry(envelope)
            if len(entry["envelope_json"].encode("utf-8")) > MAX_ENVELOPE_BYTES:
                raise PublicMemorySeparationError(
                    "public memory envelope exceeds size bound"
                )
            prior = current.get(entry["source_record_id"])
            comparable = {
                key: entry[key]
                for key in (
                    "release_id",
                    "source_record_id",
                    "source_digest",
                    "envelope_digest",
                )
            }
            if prior is not None and prior != comparable:
                raise PublicMemorySeparationError(
                    "released source record conflicts with existing bytes"
                )
            current[entry["source_record_id"]] = comparable
            entries.append(entry)
        if len(current) > MAX_PUBLIC_RECORDS:
            raise PublicMemorySeparationError("public release exceeds record bound")
        logical_digest = digest(
            [current[key] for key in sorted(current)]
        )
        return tuple(entries), logical_digest

    def _append_verified_envelopes(
        self,
        envelopes: Sequence[Mapping[str, Any]],
        *,
        authority: AuthorityDecision,
        materialization_seal: object,
        expected_logical_digest: str,
    ) -> tuple[int, int]:
        if materialization_seal is not _MATERIALIZATION_SEAL:
            raise PublicMemorySeparationError(
                "public envelopes lack a verified Foundation materialization seal"
            )
        self._require_release_authority(
            authority,
            tenant_id=self.tenant_id,
            repository_id=self.repository_id,
        )
        inserted = 0
        existing = 0
        with self._transaction():
            entries, planned_digest = self._plan_envelopes(envelopes)
            if planned_digest != expected_logical_digest:
                raise PublicMemorySeparationError(
                    "public release store changed after the protected journal"
                )
            for entry in entries:
                prior = self._connection.execute(
                    "SELECT release_id,source_digest,envelope_digest,envelope_json "
                    "FROM released_memory WHERE source_record_id=?",
                    (entry["source_record_id"],),
                ).fetchone()
                if prior is not None:
                    if (
                        prior["release_id"] != entry["release_id"]
                        or prior["source_digest"] != entry["source_digest"]
                        or prior["envelope_digest"] != entry["envelope_digest"]
                        or prior["envelope_json"] != entry["envelope_json"]
                    ):
                        raise PublicMemorySeparationError(
                            "released source record conflicts with existing bytes"
                        )
                    existing += 1
                    continue
                existing_count = int(
                    self._connection.execute(
                        "SELECT COUNT(*) FROM released_memory"
                    ).fetchone()[0]
                )
                if existing_count >= MAX_PUBLIC_RECORDS:
                    raise PublicMemorySeparationError(
                        "public release exceeds record bound"
                    )
                self._connection.execute(
                    "INSERT INTO released_memory VALUES(?,?,?,?,?,?,?,?)",
                    (
                        entry["release_id"],
                        entry["source_record_id"],
                        entry["source_digest"],
                        entry["envelope_digest"],
                        entry["envelope_json"],
                        entry["release_decision_id"],
                        entry["release_decided_by"],
                        entry["released_at"],
                    ),
                )
                inserted += 1
        return inserted, existing

    def logical_digest(self) -> str:
        self._validate_content_bounds()
        rows = self._connection.execute(
            "SELECT release_id,source_record_id,source_digest,envelope_digest "
            "FROM released_memory ORDER BY source_record_id"
        )
        return digest([dict(row) for row in rows])

    def public_snapshot(self) -> PublicMemorySnapshot:
        self._validate_shape()
        self._validate_scope_metadata()
        self._validate_content_bounds()
        records: list[dict[str, Any]] = []
        for row in self._connection.execute(
            "SELECT * FROM released_memory ORDER BY source_record_id"
        ):
            try:
                envelope = json.loads(row["envelope_json"])
            except json.JSONDecodeError as error:
                raise PublicMemorySeparationError(
                    "public memory envelope is not JSON"
                ) from error
            validation = validate_public_memory(
                "public-memory-envelope-v1",
                envelope,
            )
            if (
                not validation.valid
                or canonical_bytes(envelope).decode("utf-8").rstrip("\n")
                != row["envelope_json"]
                or digest(envelope) != row["envelope_digest"]
                or envelope["record_id"] != row["source_record_id"]
                or envelope["source_digest"] != row["source_digest"]
                or envelope["public_release_decision_id"]
                != row["release_decision_id"]
                or envelope["public_release_decided_by"]
                != row["release_decided_by"]
            ):
                raise PublicMemorySeparationError(
                    "public memory envelope integrity failed"
                )
            records.append(
                {
                    "record_id": envelope["record_id"],
                    "record_type": envelope["record_type"],
                    "schema_name": envelope["source_schema"],
                    "tenant_id": envelope["tenant_id"],
                    "repository_id": envelope["repository_id"],
                    "semantic_digest": envelope["source_digest"],
                    "previous_digest": envelope["source_previous_digest"],
                    "actor_id": envelope["actor_id"],
                    "observed_at": envelope["observed_at"],
                    "recorded_at": envelope["recorded_at"],
                    "status": envelope["status"],
                    "sensitivity": envelope["sensitivity"],
                    "public_release_decision_id": envelope[
                        "public_release_decision_id"
                    ],
                    "public_release_decided_by": envelope[
                        "public_release_decided_by"
                    ],
                    "public_release_subject_digest": envelope[
                        "public_release_subject_digest"
                    ],
                    "payload": {
                        **envelope["payload"],
                        "protected_content_ref": None,
                        "retrieval_receipt": None,
                    },
                }
            )
        return PublicMemorySnapshot(
            repository_identity={
                "tenant_id": self.tenant_id,
                "repository_id": self.repository_id,
            },
            repository_identity_digest=self.repository_identity_digest,
            schema_version=self.source_foundation_schema_version,
            schema_digest=self.source_foundation_schema_digest,
            records=tuple(records),
            source_record_count=len(records),
            omitted_sensitive_count=0,
            omitted_unsupported_count=0,
            integrity_issues=(),
        )

    def close(self) -> None:
        self._connection.close()


def read_public_memory_release_snapshot(
    path: str | Path,
    *,
    tenant_id: str,
    repository_id: str,
) -> PublicMemorySnapshot:
    source = _require_regular_file(Path(path), "public release store")
    uri = source.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, isolation_level=None, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != PUBLIC_MEMORY_STORE_SCHEMA_VERSION:
            raise PublicMemorySeparationError(
                f"public memory schema {version} is not supported"
            )
        metadata = connection.execute(
            "SELECT * FROM public_memory_metadata WHERE store_kind=?",
            (PUBLIC_MEMORY_STORE_KIND,),
        ).fetchone()
        if metadata is None:
            raise PublicMemorySeparationError(
                "public release store ownership marker is missing"
            )
        reader = PublicMemoryReleaseStore.__new__(PublicMemoryReleaseStore)
        reader.path = str(source)
        reader.tenant_id = tenant_id
        reader.repository_id = repository_id
        reader.repository_identity_digest = str(
            metadata["repository_identity_digest"]
        )
        reader.source_foundation_schema_version = int(
            metadata["source_foundation_schema_version"]
        )
        reader.source_foundation_schema_digest = str(
            metadata["source_foundation_schema_digest"]
        )
        reader._clock = utc_now
        reader._lock = RLock()
        reader._connection = connection
        return reader.public_snapshot()
    except sqlite3.Error as error:
        raise PublicMemorySeparationError(
            f"public release store read failed: {error}"
        ) from error
    finally:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        connection.close()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _validate_protected_tree(root: Path) -> None:
    if not root.exists():
        return
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(directory)
        for name in (*directory_names, *file_names):
            candidate = current / name
            if _is_linklike(candidate) or _is_multilink_file(candidate):
                raise PublicMemorySeparationError(
                    "protected release state contains a linked or multi-link path"
                )


def _read_private_json(path: Path) -> Any:
    if (
        not path.is_file()
        or _is_linklike(path)
        or _is_multilink_file(path)
        or path.stat(follow_symlinks=False).st_size > MAX_RECEIPT_BYTES
    ):
        raise PublicMemorySeparationError("protected release document is unsafe")
    with path.open("rb") as handle:
        content = handle.read(MAX_RECEIPT_BYTES + 1)
    if len(content) > MAX_RECEIPT_BYTES:
        raise PublicMemorySeparationError("protected release document exceeds bound")
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublicMemorySeparationError(
            "protected release document is invalid"
        ) from error


def _write_durable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (
        not path.is_file() or _is_linklike(path) or _is_multilink_file(path)
    ):
        raise PublicMemorySeparationError("protected receipt path is unsafe")
    temporary = path.with_suffix(path.suffix + ".tmp")
    if temporary.exists():
        if (
            not temporary.is_file()
            or _is_linklike(temporary)
            or _is_multilink_file(temporary)
        ):
            raise PublicMemorySeparationError("protected temporary path is unsafe")
        temporary.unlink()
    with temporary.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


@contextmanager
def _release_lock(protected_root: Path) -> Iterator[None]:
    lock = protected_root / "public-memory-release.lock"
    if lock.exists() and (
        not lock.is_file() or _is_linklike(lock) or _is_multilink_file(lock)
    ):
        raise PublicMemorySeparationError("public-memory release lock is unsafe")
    handle = lock.open("a+b")
    try:
        if handle.seek(0) == 0 and handle.read(1) == b"":
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise PublicMemorySeparationError(
                "another public-memory release holds the protected lock"
            ) from error
        yield
    finally:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _release_receipt_from_journal(
    journal: Mapping[str, Any],
    *,
    committed_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "hive-public-memory-release-receipt/v1",
        "status": "committed",
        "batch_id": journal["batch_id"],
        "tenant_id": journal["tenant_id"],
        "repository_id": journal["repository_id"],
        "repository_identity_digest": journal["repository_identity_digest"],
        "source_foundation_schema_version": journal[
            "source_foundation_schema_version"
        ],
        "source_foundation_schema_digest": journal[
            "source_foundation_schema_digest"
        ],
        "release_policy": journal["release_policy"],
        "release_policy_digest": journal["release_policy_digest"],
        "source_cursor": journal["source_cursor"],
        "source_record_count": journal["source_record_count"],
        "omitted_sensitive_count": journal["omitted_sensitive_count"],
        "omitted_unsupported_count": journal["omitted_unsupported_count"],
        "release_entries": journal["release_entries"],
        "release_ids": journal["release_ids"],
        "public_envelope_digests": journal["public_envelope_digests"],
        "public_store_logical_digest": journal["public_store_logical_digest"],
        "authority_decision_id": journal["authority_decision_id"],
        "authority_actor_id": journal["authority_actor_id"],
        "authority_lease_id": journal["authority_lease_id"],
        "committed_at": committed_at,
    }


def _validate_pending_journal(
    journal: Any,
    *,
    public_store: PublicMemoryReleaseStore,
    authority: AuthorityDecision,
) -> tuple[tuple[Mapping[str, Any], ...], str]:
    stable_keys = {
        "tenant_id",
        "repository_id",
        "repository_identity_digest",
        "source_foundation_schema_version",
        "source_foundation_schema_digest",
        "release_policy",
        "release_policy_digest",
        "source_cursor",
        "source_record_count",
        "omitted_sensitive_count",
        "omitted_unsupported_count",
        "envelopes",
        "release_entries",
        "release_ids",
        "public_envelope_digests",
        "public_store_logical_digest",
        "authority_decision_id",
        "authority_actor_id",
        "authority_lease_id",
    }
    if (
        not isinstance(journal, dict)
        or set(journal) != stable_keys | {"batch_id", "status"}
        or journal.get("status") != "pending"
    ):
        raise PublicMemorySeparationError(
            "pending public-memory release journal is invalid"
        )
    stable_batch = {key: journal[key] for key in stable_keys}
    expected_batch_id = sha256(canonical_bytes(stable_batch)).hexdigest()
    if journal["batch_id"] != expected_batch_id:
        raise PublicMemorySeparationError(
            "pending public-memory release journal digest mismatch"
        )
    expected_metadata = {
        "tenant_id": public_store.tenant_id,
        "repository_id": public_store.repository_id,
        "repository_identity_digest": public_store.repository_identity_digest,
        "source_foundation_schema_version": (
            public_store.source_foundation_schema_version
        ),
        "source_foundation_schema_digest": (
            public_store.source_foundation_schema_digest
        ),
        "release_policy": PUBLIC_MEMORY_RELEASE_POLICY,
        "release_policy_digest": PUBLIC_MEMORY_RELEASE_POLICY_DIGEST,
        "authority_decision_id": authority.decision_id,
        "authority_actor_id": authority.actor_id,
        "authority_lease_id": authority.lease_id,
    }
    if any(journal.get(key) != value for key, value in expected_metadata.items()):
        raise PublicMemorySeparationError(
            "pending public-memory release journal scope or authority mismatch"
        )
    receipt_validation = validate_public_memory(
        "public-memory-release-receipt-v1",
        _release_receipt_from_journal(
            journal,
            committed_at="pending-recovery-validation",
        ),
    )
    if not receipt_validation.valid:
        raise PublicMemorySeparationError(
            "pending public-memory release receipt basis is invalid"
        )
    envelopes_value = journal["envelopes"]
    if not isinstance(envelopes_value, list) or not all(
        isinstance(envelope, Mapping) for envelope in envelopes_value
    ):
        raise PublicMemorySeparationError(
            "pending public-memory release envelopes are invalid"
        )
    envelopes = tuple(envelopes_value)
    entries, planned_digest = public_store._plan_envelopes(envelopes)
    if (
        journal["release_entries"]
        != [
            {
                key: entry[key]
                for key in (
                    "release_id",
                    "source_record_id",
                    "source_digest",
                    "envelope_digest",
                )
            }
            for entry in entries
        ]
        or journal["release_ids"]
        != [entry["release_id"] for entry in entries]
        or journal["public_envelope_digests"]
        != [entry["envelope_digest"] for entry in entries]
        or journal["public_store_logical_digest"] != planned_digest
    ):
        raise PublicMemorySeparationError(
            "pending public-memory release plan is inconsistent"
        )
    return envelopes, planned_digest


def _publish_release_receipt(
    journal: Mapping[str, Any],
    *,
    receipt_path: Path,
    clock: Callable[[], str],
) -> None:
    receipt = _release_receipt_from_journal(journal, committed_at=clock())
    validation = validate_public_memory(
        "public-memory-release-receipt-v1",
        receipt,
    )
    receipt_bytes = _json_bytes(receipt)
    if not validation.valid or len(receipt_bytes) > MAX_RECEIPT_BYTES:
        raise PublicMemorySeparationError(
            "private public-memory release receipt is invalid"
        )
    if receipt_path.exists():
        prior = _read_private_json(receipt_path)
        comparable_prior = dict(prior)
        comparable_receipt = dict(receipt)
        comparable_prior.pop("committed_at", None)
        comparable_receipt.pop("committed_at", None)
        if comparable_prior != comparable_receipt:
            raise PublicMemorySeparationError(
                "existing private release receipt is inconsistent"
            )
    else:
        _write_durable(receipt_path, receipt_bytes)


def _recover_pending_releases(
    *,
    transactions: Path,
    receipts: Path,
    public_store: PublicMemoryReleaseStore,
    authority: AuthorityDecision,
    clock: Callable[[], str],
) -> None:
    if not transactions.exists():
        return
    pending: list[Path] = []
    for candidate in transactions.iterdir():
        if candidate.suffix == ".tmp":
            continue
        if (
            len(pending) >= MAX_PENDING_TRANSACTIONS
            or candidate.suffix != ".json"
            or not candidate.stem
        ):
            raise PublicMemorySeparationError(
                "protected release transaction set is invalid or exceeds bound"
            )
        pending.append(candidate)
    for transaction in sorted(pending):
        journal = _read_private_json(transaction)
        envelopes, planned_digest = _validate_pending_journal(
            journal,
            public_store=public_store,
            authority=authority,
        )
        public_store._append_verified_envelopes(
            envelopes,
            authority=authority,
            materialization_seal=_MATERIALIZATION_SEAL,
            expected_logical_digest=planned_digest,
        )
        if public_store.logical_digest() != planned_digest:
            raise PublicMemorySeparationError(
                "recovered public-memory release digest mismatch"
            )
        _publish_release_receipt(
            journal,
            receipt_path=receipts / f"{journal['batch_id']}.json",
            clock=clock,
        )
        transaction.unlink()
    if transactions.exists() and not any(transactions.iterdir()):
        transactions.rmdir()


def materialize_public_memory(
    foundation_store_path: str | Path,
    public_store_path: str | Path,
    repository_root: str | Path,
    protected_state_root: str | Path,
    *,
    tenant_id: str,
    repository_id: str,
    authority: AuthorityDecision,
    clock: Callable[[], str] = utc_now,
    fail_after_public_commit: bool = False,
) -> PublicMemoryMaterializationResult:
    _require_scope(tenant_id, repository_id)
    repository = _resolve_repository(repository_root)
    source = _require_regular_file(
        Path(foundation_store_path),
        "private Foundation store",
    )
    if source.is_relative_to(repository):
        raise PublicMemorySeparationError(
            "private Foundation store must be outside the repository"
        )
    public_path = Path(public_store_path).absolute()
    if public_path.exists():
        public_resolved = _require_regular_file(
            public_path,
            "public release store",
        )
        if public_resolved.samefile(source):
            raise PublicMemorySeparationError(
                "public and private stores must be distinct files"
            )
    else:
        _validate_parent_for_new_file(public_path, "public release store")
        if public_path == source:
            raise PublicMemorySeparationError(
                "public and private stores must be distinct files"
            )
    PublicMemoryReleaseStore._require_release_authority(
        authority,
        tenant_id=tenant_id,
        repository_id=repository_id,
    )
    protected = _resolve_protected_root(protected_state_root, repository)
    public_parent = public_path.parent.resolve(strict=True)
    if (
        public_parent == source.parent
        or public_path.is_relative_to(protected)
        or protected == public_parent
        or protected.is_relative_to(public_parent)
        or public_parent.is_relative_to(protected)
    ):
        raise PublicMemorySeparationError(
            "public store must not share the private or protected persistence root"
        )
    snapshot = FoundationStore.read_public_memory_snapshot(
        source,
        tenant_id=tenant_id,
        repository_id=repository_id,
    )
    if snapshot.integrity_issues:
        raise PublicMemorySeparationError(
            "private Foundation integrity failed: "
            + "; ".join(snapshot.integrity_issues)
        )
    if (
        snapshot.repository_identity is None
        or snapshot.repository_identity_digest is None
    ):
        raise PublicMemorySeparationError("private repository scope is not registered")
    eligible_records = tuple(
        record
        for record in snapshot.records
        if isinstance(record.get("payload"), Mapping)
        and record["payload"].get("status") != "quarantined"
        and record["payload"].get("quarantine_state") == "none"
    )
    envelopes = tuple(
        _public_envelope(
            record,
            tenant_id=tenant_id,
            repository_id=repository_id,
        )
        for record in eligible_records
    )
    cursor = _source_cursor(eligible_records)
    transactions = protected / "transactions"
    receipts = protected / "receipts"
    if not protected.exists():
        try:
            protected.mkdir(mode=0o700)
        except FileExistsError:
            pass
    protected = _resolve_protected_root(protected, repository)
    with _release_lock(protected):
        _validate_protected_tree(protected)
        public_store = PublicMemoryReleaseStore(
            public_path,
            tenant_id=tenant_id,
            repository_id=repository_id,
            repository_identity_digest=snapshot.repository_identity_digest,
            source_foundation_schema_version=snapshot.schema_version,
            source_foundation_schema_digest=snapshot.schema_digest,
            clock=clock,
        )
        try:
            _recover_pending_releases(
                transactions=transactions,
                receipts=receipts,
                public_store=public_store,
                authority=authority,
                clock=clock,
            )
            release_entries, planned_digest = public_store._plan_envelopes(
                envelopes,
            )
            stable_batch = {
                "tenant_id": tenant_id,
                "repository_id": repository_id,
                "repository_identity_digest": (
                    snapshot.repository_identity_digest
                ),
                "source_foundation_schema_version": snapshot.schema_version,
                "source_foundation_schema_digest": snapshot.schema_digest,
                "release_policy": PUBLIC_MEMORY_RELEASE_POLICY,
                "release_policy_digest": PUBLIC_MEMORY_RELEASE_POLICY_DIGEST,
                "source_cursor": cursor,
                "source_record_count": snapshot.source_record_count,
                "omitted_sensitive_count": snapshot.omitted_sensitive_count,
                "omitted_unsupported_count": snapshot.omitted_unsupported_count,
                "envelopes": list(envelopes),
                "release_entries": [
                    {
                        key: entry[key]
                        for key in (
                            "release_id",
                            "source_record_id",
                            "source_digest",
                            "envelope_digest",
                        )
                    }
                    for entry in release_entries
                ],
                "release_ids": [
                    entry["release_id"] for entry in release_entries
                ],
                "public_envelope_digests": [
                    entry["envelope_digest"] for entry in release_entries
                ],
                "public_store_logical_digest": planned_digest,
                "authority_decision_id": authority.decision_id,
                "authority_actor_id": authority.actor_id,
                "authority_lease_id": authority.lease_id,
            }
            batch_id = sha256(canonical_bytes(stable_batch)).hexdigest()
            transaction = transactions / f"{batch_id}.json"
            receipt_path = receipts / f"{batch_id}.json"
            journal = {
                **stable_batch,
                "batch_id": batch_id,
                "status": "pending",
            }
            journal_bytes = _json_bytes(journal)
            if len(journal_bytes) > MAX_RECEIPT_BYTES:
                raise PublicMemorySeparationError(
                    "private public-memory release journal exceeds size bound"
                )
            _write_durable(transaction, journal_bytes)
            inserted, existing_count = public_store._append_verified_envelopes(
                envelopes,
                authority=authority,
                materialization_seal=_MATERIALIZATION_SEAL,
                expected_logical_digest=planned_digest,
            )
            logical_digest = public_store.logical_digest()
            if logical_digest != planned_digest:
                raise PublicMemorySeparationError(
                    "public-memory release digest mismatch"
                )
            if fail_after_public_commit:
                raise InterruptedError("injected post-public-commit interruption")
            _publish_release_receipt(
                journal,
                receipt_path=receipt_path,
                clock=clock,
            )
            transaction.unlink()
            if transactions.exists() and not any(transactions.iterdir()):
                transactions.rmdir()
        finally:
            public_store.close()
    result = PublicMemoryMaterializationResult(
        schema_version="hive-public-memory-materialization-result/v1",
        status="materialized" if inserted else "unchanged",
        tenant_id=tenant_id,
        repository_id=repository_id,
        source_cursor=cursor,
        released_record_count=inserted,
        existing_record_count=existing_count,
        public_store_logical_digest=logical_digest,
        receipt_locator=f"protected-state:receipts/{batch_id}.json",
    )
    validation = validate_public_memory(
        "public-memory-materialization-result-v1",
        result.to_dict(),
    )
    if not validation.valid:
        raise PublicMemorySeparationError(
            "public-memory materialization result is invalid"
        )
    return result


def remove_incomplete_public_store(path: str | Path) -> None:
    """Test-only-safe cleanup helper for an empty, newly failed initialization."""

    target = Path(path)
    if target.exists() and target.stat().st_size == 0 and not _is_linklike(target):
        target.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(target) + suffix)
        if sidecar.exists() and sidecar.stat().st_size == 0 and not _is_linklike(
            sidecar
        ):
            sidecar.unlink()
    parent = target.parent
    if parent.exists() and not any(parent.iterdir()):
        shutil.rmtree(parent)
