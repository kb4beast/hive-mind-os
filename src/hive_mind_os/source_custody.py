"""Authenticated external repository-source locks.

This module deliberately separates an immutable Git object identifier from source
authentication.  A full commit or tree SHA is a reproducibility locator only.  A
trusted external custody authority must sign the exact source identity and lock before
the materialization adapter may treat a remote source as authenticated.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Mapping, Protocol, Sequence
from urllib.parse import urlsplit

from .contracts import validate_contract
from .custody import CustodyError, Ed25519CustodyVerifier, custody_digest

_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
_STATE_REF = re.compile(r"MISSION_STATE:[^:\s]+:[1-9][0-9]*\Z")
_SOURCE_LOCK_DOMAIN = b"hive-mind-os/source-lock-attestation/v1\0"
SOURCE_CUSTODY_AUDIENCE = "hive-mind-os/source-custody/v1"


class SourceCustodyError(CustodyError):
    """A source identity, signed source lock, or its provenance was not admitted."""


class SourceLockAttestor(Protocol):
    """A non-agent-controlled service that signs an externally verified source lock."""

    def attest_source_lock(self, source_lock: Mapping[str, object]) -> Mapping[str, object]: ...


def _ensure_contract(name: str, document: Mapping[str, object]) -> None:
    validation = validate_contract(name, dict(document))
    if not validation.valid:
        raise SourceCustodyError(
            f"{name} violates its contract: " + "; ".join(validation.issues)
        )


def canonical_repository_url(
    value: str,
    *,
    allowed_hosts: Sequence[str] = ("github.com",),
) -> str:
    """Normalize the small, credential-free remote URL surface this tranche admits."""

    parsed = urlsplit(value)
    hosts = {host.casefold() for host in allowed_hosts}
    path_parts = tuple(part for part in parsed.path.split("/") if part)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() not in hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or len(path_parts) != 2
        or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path_parts)
    ):
        raise SourceCustodyError(
            "source lock repository must be a credential-free HTTPS GitHub repository URL"
        )
    repository = path_parts[1].removesuffix(".git")
    if not repository:
        raise SourceCustodyError("source lock repository name is required")
    return f"https://{parsed.hostname.casefold()}/{path_parts[0]}/{repository}.git"


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Identity assertion that the external custody authority signs with the lock."""

    provider: str
    repository_id: str
    principal_id: str

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> SourceIdentity:
        values: dict[str, str] = {}
        for field in ("provider", "repository_id", "principal_id"):
            value = document.get(field)
            if not isinstance(value, str) or not value.strip():
                raise SourceCustodyError(f"source identity {field} is required")
            values[field] = value
        return cls(**values)

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "repository_id": self.repository_id,
            "principal_id": self.principal_id,
        }


@dataclass(frozen=True, slots=True)
class SourceLock:
    """A typed immutable source revision; not an authentication assertion by itself."""

    lock_id: str
    mission_id: str
    state_ref: str
    repository_url: str
    commit_sha: str
    tree_sha: str
    source_identity: SourceIdentity

    @classmethod
    def from_dict(
        cls,
        document: Mapping[str, object],
        *,
        allowed_hosts: Sequence[str] = ("github.com",),
    ) -> SourceLock:
        _ensure_contract("source-lock", document)
        identity_value = document.get("source_identity")
        if not isinstance(identity_value, Mapping):
            raise SourceCustodyError("source lock source_identity is required")
        strings: dict[str, str] = {}
        for field in (
            "lock_id",
            "mission_id",
            "state_ref",
            "repository_url",
            "commit_sha",
            "tree_sha",
        ):
            value = document.get(field)
            if not isinstance(value, str) or not value.strip():
                raise SourceCustodyError(f"source lock {field} is required")
            strings[field] = value
        repository_url = canonical_repository_url(
            strings["repository_url"], allowed_hosts=allowed_hosts
        )
        if repository_url != strings["repository_url"]:
            raise SourceCustodyError("source lock repository URL is not canonical")
        for field in ("commit_sha", "tree_sha"):
            if not _FULL_SHA.fullmatch(strings[field]):
                raise SourceCustodyError(f"source lock {field} must be a lowercase full SHA")
        identity = SourceIdentity.from_dict(identity_value)
        if not _STATE_REF.fullmatch(strings["state_ref"]):
            raise SourceCustodyError("source lock state_ref is malformed")
        if not strings["state_ref"].startswith(
            f"MISSION_STATE:{strings['mission_id']}:"
        ):
            raise SourceCustodyError("source lock state_ref does not bind its mission")
        expected_repository_id = repository_url.removeprefix("https://").removesuffix(
            ".git"
        )
        if identity.provider != urlsplit(repository_url).hostname:
            raise SourceCustodyError("source identity provider does not match repository URL")
        if identity.repository_id != expected_repository_id:
            raise SourceCustodyError(
                "source identity repository does not match repository URL"
            )
        return cls(
            strings["lock_id"],
            strings["mission_id"],
            strings["state_ref"],
            repository_url,
            strings["commit_sha"],
            strings["tree_sha"],
            identity,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "lock_id": self.lock_id,
            "mission_id": self.mission_id,
            "state_ref": self.state_ref,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "tree_sha": self.tree_sha,
            "source_identity": self.source_identity.to_dict(),
        }

    def require_materialization(
        self,
        repository_url: str,
        commit_sha: str,
        *,
        mission_id: str,
        state_ref: str,
        allowed_hosts: Sequence[str],
    ) -> None:
        expected_url = canonical_repository_url(repository_url, allowed_hosts=allowed_hosts)
        if self.repository_url != expected_url:
            raise SourceCustodyError("source lock repository does not match materialization")
        if self.commit_sha != commit_sha:
            raise SourceCustodyError("source lock commit does not match materialization pin")
        if self.mission_id != mission_id:
            raise SourceCustodyError("source lock mission does not match materialization")
        if self.state_ref != state_ref:
            raise SourceCustodyError("source lock state does not match materialization")

    def require_tree(self, tree_sha: str) -> None:
        if not _FULL_SHA.fullmatch(tree_sha):
            raise SourceCustodyError("materialized tree must be a lowercase full SHA")
        if self.tree_sha != tree_sha:
            raise SourceCustodyError("materialized tree does not match authenticated source lock")


@dataclass(frozen=True, slots=True)
class SourceLockEvidence:
    """The immutable lock and the external signature attesting to exactly that lock."""

    source_lock: SourceLock
    attestation: Mapping[str, object]

    def digest(self) -> str:
        return custody_digest(
            {
                "source_lock": self.source_lock.to_dict(),
                "attestation": dict(self.attestation),
            }
        )


class SourceLockProvenanceStore:
    """Append-only local evidence of verified external source-lock assertions.

    The database is durable provenance, not the root of trust.  Its digest columns are
    integrity locators only; verification is always repeated against the external
    authority's current trusted keyset before a lock is admitted.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            raise

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS source_lock_attestations (
                    digest TEXT PRIMARY KEY,
                    lock_id TEXT NOT NULL UNIQUE,
                    authority_id TEXT NOT NULL,
                    attestation_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    repository_url TEXT NOT NULL,
                    commit_sha TEXT NOT NULL,
                    tree_sha TEXT NOT NULL,
                    source_identity_json TEXT NOT NULL,
                    lock_json TEXT NOT NULL,
                    attestation_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(authority_id, attestation_id),
                    UNIQUE(authority_id, key_id, nonce)
                );
                CREATE TRIGGER IF NOT EXISTS source_lock_attestations_no_update
                BEFORE UPDATE ON source_lock_attestations BEGIN
                    SELECT RAISE(ABORT, 'source lock attestations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS source_lock_attestations_no_delete
                BEFORE DELETE ON source_lock_attestations BEGIN
                    SELECT RAISE(ABORT, 'source lock attestations are append-only');
                END;
                """
            )

    def close(self) -> None:
        self._connection.close()

    @property
    def is_durable(self) -> bool:
        """Whether SQLite was given a filesystem-backed, non-memory location."""

        candidate = self.path.strip()
        return bool(candidate) and candidate != ":memory:" and ":memory:" not in candidate

    def record(self, evidence: SourceLockEvidence) -> bool:
        lock_json = _canonical_json(evidence.source_lock.to_dict())
        attestation_json = _canonical_json(evidence.attestation)
        digest = evidence.digest()
        authority_id = _required_string(evidence.attestation, "authority_id")
        attestation_id = _required_string(evidence.attestation, "attestation_id")
        key_id = _required_string(evidence.attestation, "key_id")
        nonce = _required_string(evidence.attestation, "nonce")
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT lock_json,attestation_json FROM source_lock_attestations "
                "WHERE digest=?",
                (digest,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["lock_json"] != lock_json
                    or existing["attestation_json"] != attestation_json
                ):
                    raise SourceCustodyError("source lock digest maps to different provenance")
                return False
            for clause, value, label in (
                ("lock_id=?", evidence.source_lock.lock_id, "source lock ID"),
                (
                    "authority_id=? AND attestation_id=?",
                    (authority_id, attestation_id),
                    "source lock attestation ID",
                ),
                (
                    "authority_id=? AND key_id=? AND nonce=?",
                    (authority_id, key_id, nonce),
                    "source lock attestation nonce",
                ),
            ):
                arguments = value if isinstance(value, tuple) else (value,)
                existing = self._connection.execute(
                    "SELECT digest FROM source_lock_attestations WHERE " + clause,
                    arguments,
                ).fetchone()
                if existing is not None:
                    raise SourceCustodyError(f"{label} was replayed")
            self._connection.execute(
                "INSERT INTO source_lock_attestations("
                "digest,lock_id,authority_id,attestation_id,key_id,nonce,repository_url,"
                "commit_sha,tree_sha,source_identity_json,lock_json,attestation_json,recorded_at"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    digest,
                    evidence.source_lock.lock_id,
                    authority_id,
                    attestation_id,
                    key_id,
                    nonce,
                    evidence.source_lock.repository_url,
                    evidence.source_lock.commit_sha,
                    evidence.source_lock.tree_sha,
                    _canonical_json(evidence.source_lock.source_identity.to_dict()),
                    lock_json,
                    attestation_json,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return True

    def count(self) -> int:
        return int(
            self._connection.execute(
                "SELECT COUNT(*) FROM source_lock_attestations"
            ).fetchone()[0]
        )


class SourceCustodyVerifier:
    """Verify signed source-lock evidence using an externally pinned custody authority."""

    def __init__(
        self,
        custody_verifier: Ed25519CustodyVerifier,
        provenance: SourceLockProvenanceStore,
        *,
        allowed_hosts: Sequence[str] = ("github.com",),
    ) -> None:
        if not allowed_hosts:
            raise ValueError("source custody must allow at least one remote host")
        self.custody_verifier = custody_verifier
        self.provenance = provenance
        self.allowed_hosts = tuple(host.casefold() for host in allowed_hosts)

    def verify(self, evidence: SourceLockEvidence) -> SourceLock:
        lock = SourceLock.from_dict(
            evidence.source_lock.to_dict(), allowed_hosts=self.allowed_hosts
        )
        _ensure_contract("source-lock-attestation", evidence.attestation)
        observed_lock = evidence.attestation.get("source_lock")
        if not isinstance(observed_lock, Mapping):
            raise SourceCustodyError("source lock attestation source_lock is required")
        signed_lock = SourceLock.from_dict(observed_lock, allowed_hosts=self.allowed_hosts)
        if signed_lock.to_dict() != lock.to_dict():
            raise SourceCustodyError(
                "source lock attestation does not bind the expected source lock"
            )
        if _required_string(evidence.attestation, "signer_identity") == (
            lock.source_identity.principal_id
        ):
            raise SourceCustodyError(
                "source lock signer must be distinct from the asserted source principal"
            )
        try:
            self.custody_verifier.verify_signed_envelope(
                evidence.attestation,
                audience=SOURCE_CUSTODY_AUDIENCE,
                domain=_SOURCE_LOCK_DOMAIN,
            )
        except CustodyError as error:
            raise SourceCustodyError(
                f"external source-lock authentication failed: {error}"
            ) from error
        self.provenance.record(evidence)
        return lock

    def verify_for_materialization(
        self,
        evidence: SourceLockEvidence,
        repository_url: str,
        commit_sha: str,
        *,
        mission_id: str,
        state_ref: str,
        allowed_hosts: Sequence[str],
    ) -> SourceLock:
        lock = self.verify(evidence)
        lock.require_materialization(
            repository_url,
            commit_sha,
            mission_id=mission_id,
            state_ref=state_ref,
            allowed_hosts=allowed_hosts,
        )
        return lock


class ExternalSourceCustodyAdapter:
    """Bounded request/verify adapter; source-authentication private keys stay external."""

    def __init__(
        self,
        attestor: SourceLockAttestor,
        verifier: SourceCustodyVerifier,
    ) -> None:
        self.attestor = attestor
        self.verifier = verifier

    def attest_source_lock(self, source_lock: Mapping[str, object]) -> SourceLockEvidence:
        lock = SourceLock.from_dict(
            source_lock, allowed_hosts=self.verifier.allowed_hosts
        )
        evidence = SourceLockEvidence(
            lock,
            self.attestor.attest_source_lock(lock.to_dict()),
        )
        self.verifier.verify(evidence)
        return evidence


def _required_string(document: Mapping[str, object], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SourceCustodyError(f"source custody {field} is required")
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise SourceCustodyError("source custody provenance is not canonical JSON") from error
