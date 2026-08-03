"""Authenticated external custody for configuration and receipt evidence.

This module deliberately contains verification and mediation only.  It never creates a
private key, reads one from the environment, or treats a local digest as an identity.  A
deployment supplies a non-agent-controlled attestor; the kernel retains only public trust
material and the signed envelopes it verified.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Mapping, Protocol, Sequence

from .contracts import validate_contract
from .receipts import ReceiptReference, sha256_digest

_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_B64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")
_RFC3339_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z"
)
_ATTESTATION_DOMAIN = b"hive-mind-os/custody-attestation/v1\0"
_KEYSET_DOMAIN = b"hive-mind-os/custody-keyset/v1\0"
CUSTODY_AUDIENCE = "hive-mind-os/custody/v1"


class CustodyError(RuntimeError):
    """A custody envelope or its provenance cannot be safely admitted."""


class CustodyCryptoUnavailable(CustodyError):
    """The optional public-key verifier dependency is not installed."""


class CustodyAttestor(Protocol):
    """A non-agent-controlled service that issues one detached signed envelope."""

    def attest(self, subject: Mapping[str, object]) -> Mapping[str, object]: ...


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise CustodyError("custody payload is not canonical JSON") from error


def custody_digest(value: object) -> str:
    """Return an integrity binding.  It is never an authentication claim."""

    return sha256_digest(_canonical_bytes(value))


def _required_string(document: Mapping[str, object], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CustodyError(f"custody {field} is required")
    return value


def _required_digest(document: Mapping[str, object], field: str) -> str:
    value = _required_string(document, field)
    if not _DIGEST_PATTERN.fullmatch(value):
        raise CustodyError(f"custody {field} must be lowercase sha256:<64 hex>")
    return value


def _parse_time(value: str, *, field: str) -> datetime:
    if not _RFC3339_PATTERN.fullmatch(value):
        raise CustodyError(f"custody {field} must be RFC 3339")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CustodyError(f"custody {field} must be RFC 3339") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CustodyError(f"custody {field} must include a timezone")
    return parsed.astimezone(UTC)


def _decode_b64url(value: str, *, field: str, expected_bytes: int) -> bytes:
    if not _B64URL_PATTERN.fullmatch(value):
        raise CustodyError(f"custody {field} must be unpadded base64url")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, binascii.Error) as error:
        raise CustodyError(f"custody {field} is not valid base64url") from error
    if len(decoded) != expected_bytes:
        raise CustodyError(f"custody {field} has an invalid length")
    return decoded


def _ed25519_verify(public_key: bytes, payload: bytes, signature: bytes) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ModuleNotFoundError as error:
        raise CustodyCryptoUnavailable(
            "authenticated custody requires the optional cryptography dependency"
        ) from error
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload)
    except InvalidSignature as error:
        raise CustodyError("custody signature verification failed") from error
    except ValueError as error:
        raise CustodyError("custody public key is malformed") from error


def _signed_payload(document: Mapping[str, object], *, domain: bytes) -> bytes:
    payload = {key: value for key, value in document.items() if key != "signature"}
    return domain + _canonical_bytes(payload)


def _ensure_contract(name: str, document: Mapping[str, object]) -> None:
    validation = validate_contract(name, dict(document))
    if not validation.valid:
        raise CustodyError(
            f"{name} violates its contract: " + "; ".join(validation.issues)
        )


@dataclass(frozen=True, slots=True)
class CustodySubject:
    """Exactly the thing an external authority is asked to attest."""

    kind: str
    mission_id: str
    state_ref: str
    subject_id: str
    digest: str
    bindings: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.kind not in {"mission-configuration", "tool-receipt"}:
            raise ValueError("custody subject kind is unsupported")
        for field, value in (
            ("mission_id", self.mission_id),
            ("state_ref", self.state_ref),
            ("subject_id", self.subject_id),
        ):
            if not value.strip():
                raise ValueError(f"custody subject {field} is required")
        if not _DIGEST_PATTERN.fullmatch(self.digest):
            raise ValueError("custody subject digest must be SHA-256")
        if any(not key.strip() or not value.strip() for key, value in self.bindings.items()):
            raise ValueError("custody subject bindings must be non-empty strings")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "mission_id": self.mission_id,
            "state_ref": self.state_ref,
            "subject_id": self.subject_id,
            "digest": self.digest,
            "bindings": dict(sorted(self.bindings.items())),
        }

    @classmethod
    def configuration(
        cls,
        mission_id: str,
        configuration: Mapping[str, object],
    ) -> CustodySubject:
        specifications = configuration.get("acceptance_specifications", ())
        if not isinstance(specifications, (list, tuple)):
            raise CustodyError("mission configuration acceptance specifications are malformed")
        bindings: dict[str, str] = {
            "acceptance_specifications_digest": custody_digest(list(specifications)),
        }
        for field in ("repository", "pin", "risk"):
            value = configuration.get(field)
            if isinstance(value, str) and value.strip():
                bindings[field] = value
        return cls(
            "mission-configuration",
            mission_id,
            f"MISSION_STATE:{mission_id}:1",
            f"configuration:{mission_id}",
            custody_digest(dict(configuration)),
            bindings,
        )

    @classmethod
    def receipt(
        cls,
        receipt: Mapping[str, object],
        reference: ReceiptReference,
    ) -> CustodySubject:
        required = {
            field: _required_string(receipt, field)
            for field in (
                "receipt_id",
                "mission_id",
                "state_ref",
                "action_id",
                "action_digest",
                "policy_decision_ref",
                "lease_id",
                "provider",
                "actor_id",
                "verified_by",
            )
        }
        if not _DIGEST_PATTERN.fullmatch(required["action_digest"]):
            raise CustodyError("receipt action_digest must be SHA-256")
        return cls(
            "tool-receipt",
            required["mission_id"],
            required["state_ref"],
            required["receipt_id"],
            reference.digest,
            {
                "action_digest": required["action_digest"],
                "action_id": required["action_id"],
                "actor_id": required["actor_id"],
                "lease_id": required["lease_id"],
                "policy_decision_ref": required["policy_decision_ref"],
                "provider": required["provider"],
                "verified_by": required["verified_by"],
            },
        )

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> CustodySubject:
        bindings = document.get("bindings")
        if not isinstance(bindings, Mapping) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in bindings.items()
        ):
            raise CustodyError("custody subject bindings must be a string object")
        return cls(
            _required_string(document, "kind"),
            _required_string(document, "mission_id"),
            _required_string(document, "state_ref"),
            _required_string(document, "subject_id"),
            _required_digest(document, "digest"),
            {str(key): str(value) for key, value in bindings.items()},
        )


@dataclass(frozen=True, slots=True)
class TrustAnchor:
    """An externally configured public root; never an agent or role identity."""

    authority_id: str
    key_id: str
    signer_identity: str
    public_key: str

    def __post_init__(self) -> None:
        for value in (self.authority_id, self.key_id, self.signer_identity):
            if not value.strip():
                raise ValueError("trust anchor identity fields are required")
        _decode_b64url(self.public_key, field="trust anchor public_key", expected_bytes=32)


class CustodyProvenanceStore:
    """Local append-only provenance for externally authenticated custody events.

    This preserves which external statement was admitted.  It does not claim external
    retention or hostile-host immutability; those are separate custody obligations.
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
                CREATE TABLE IF NOT EXISTS custody_keysets (
                    authority_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(authority_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS custody_attestations (
                    digest TEXT PRIMARY KEY,
                    authority_id TEXT NOT NULL,
                    attestation_id TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    subject_json TEXT NOT NULL,
                    document_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(authority_id, key_id, nonce),
                    UNIQUE(authority_id, attestation_id)
                );
                CREATE TRIGGER IF NOT EXISTS custody_keysets_no_update
                BEFORE UPDATE ON custody_keysets BEGIN
                    SELECT RAISE(ABORT, 'custody keysets are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS custody_keysets_no_delete
                BEFORE DELETE ON custody_keysets BEGIN
                    SELECT RAISE(ABORT, 'custody keysets are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS custody_attestations_no_update
                BEFORE UPDATE ON custody_attestations BEGIN
                    SELECT RAISE(ABORT, 'custody attestations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS custody_attestations_no_delete
                BEFORE DELETE ON custody_attestations BEGIN
                    SELECT RAISE(ABORT, 'custody attestations are append-only');
                END;
                """
            )
            columns = {
                str(row["name"])
                for row in self._connection.execute(
                    "PRAGMA table_info(custody_attestations)"
                )
            }
            if "attestation_id" not in columns:
                self._connection.execute(
                    "DROP TRIGGER IF EXISTS custody_attestations_no_update"
                )
                self._connection.execute(
                    "ALTER TABLE custody_attestations ADD COLUMN attestation_id TEXT"
                )
                rows = self._connection.execute(
                    "SELECT digest,document_json FROM custody_attestations"
                ).fetchall()
                for row in rows:
                    document = json.loads(row["document_json"])
                    if not isinstance(document, Mapping):
                        raise CustodyError("stored custody attestation is malformed")
                    self._connection.execute(
                        "UPDATE custody_attestations SET attestation_id=? WHERE digest=?",
                        (_required_string(document, "attestation_id"), row["digest"]),
                    )
                self._connection.execute(
                    "CREATE TRIGGER custody_attestations_no_update "
                    "BEFORE UPDATE ON custody_attestations BEGIN "
                    "SELECT RAISE(ABORT, 'custody attestations are append-only'); END"
                )
            self._connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "custody_attestations_authority_id_unique "
                "ON custody_attestations(authority_id,attestation_id)"
            )

    def close(self) -> None:
        self._connection.close()

    @property
    def is_durable(self) -> bool:
        """Whether SQLite was given a filesystem-backed, non-memory location."""

        candidate = self.path.strip()
        return bool(candidate) and candidate != ":memory:" and ":memory:" not in candidate

    def latest_keyset(self, authority_id: str) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT document_json FROM custody_keysets WHERE authority_id=? "
            "ORDER BY sequence DESC LIMIT 1",
            (authority_id,),
        ).fetchone()
        return json.loads(row["document_json"]) if row is not None else None

    def keyset(self, authority_id: str, sequence: int) -> dict[str, object] | None:
        row = self._connection.execute(
            "SELECT document_json FROM custody_keysets WHERE authority_id=? AND sequence=?",
            (authority_id, sequence),
        ).fetchone()
        return json.loads(row["document_json"]) if row is not None else None

    def keyset_history(self, authority_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            "SELECT document_json FROM custody_keysets WHERE authority_id=? "
            "ORDER BY sequence",
            (authority_id,),
        ).fetchall()
        return [json.loads(row["document_json"]) for row in rows]

    def record_keyset(self, document: Mapping[str, object]) -> None:
        authority_id = _required_string(document, "authority_id")
        sequence = document.get("sequence")
        if type(sequence) is not int or sequence < 1:
            raise CustodyError("custody keyset sequence must be a positive integer")
        encoded = _canonical_bytes(document).decode("utf-8")
        digest = sha256_digest(encoded.encode("utf-8"))
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT document_json FROM custody_keysets WHERE authority_id=? AND sequence=?",
                (authority_id, sequence),
            ).fetchone()
            if existing is not None:
                if existing["document_json"] != encoded:
                    raise CustodyError("custody keyset sequence was reused with different bytes")
                return
            self._connection.execute(
                "INSERT INTO custody_keysets(authority_id,sequence,digest,document_json,recorded_at) "
                "VALUES(?,?,?,?,?)",
                (authority_id, sequence, digest, encoded, datetime.now(UTC).isoformat()),
            )

    def record_attestation(
        self,
        document: Mapping[str, object],
        subject: CustodySubject,
    ) -> bool:
        digest = custody_digest(document)
        authority_id = _required_string(document, "authority_id")
        attestation_id = _required_string(document, "attestation_id")
        key_id = _required_string(document, "key_id")
        nonce = _required_string(document, "nonce")
        encoded = _canonical_bytes(document).decode("utf-8")
        subject_encoded = _canonical_bytes(subject.to_dict()).decode("utf-8")
        with self._lock, self._connection:
            existing_by_digest = self._connection.execute(
                "SELECT subject_json,document_json FROM custody_attestations WHERE digest=?",
                (digest,),
            ).fetchone()
            if existing_by_digest is not None:
                if (
                    existing_by_digest["document_json"] != encoded
                    or existing_by_digest["subject_json"] != subject_encoded
                ):
                    raise CustodyError("custody digest maps to different provenance")
                return False
            existing_nonce = self._connection.execute(
                "SELECT digest FROM custody_attestations "
                "WHERE authority_id=? AND key_id=? AND nonce=?",
                (authority_id, key_id, nonce),
            ).fetchone()
            existing_id = self._connection.execute(
                "SELECT digest FROM custody_attestations "
                "WHERE authority_id=? AND attestation_id=?",
                (authority_id, attestation_id),
            ).fetchone()
            if existing_id is not None:
                raise CustodyError("custody attestation ID was replayed")
            if existing_nonce is not None:
                raise CustodyError("custody attestation nonce was replayed")
            self._connection.execute(
                "INSERT INTO custody_attestations("
                "digest,authority_id,attestation_id,key_id,nonce,subject_json,"
                "document_json,recorded_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    digest,
                    authority_id,
                    attestation_id,
                    key_id,
                    nonce,
                    subject_encoded,
                    encoded,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return True

    def attestation_count(self) -> int:
        return int(
            self._connection.execute("SELECT COUNT(*) FROM custody_attestations").fetchone()[0]
        )


class Ed25519CustodyVerifier:
    """Verify signed external envelopes against a pinned root and keyset history."""

    def __init__(
        self,
        anchor: TrustAnchor,
        provenance: CustodyProvenanceStore,
        *,
        now: Callable[[], datetime] | None = None,
        max_keyset_age: timedelta = timedelta(hours=24),
    ) -> None:
        if max_keyset_age <= timedelta(0):
            raise ValueError("custody max_keyset_age must be positive")
        self.anchor = anchor
        self.provenance = provenance
        self._now = now or (lambda: datetime.now(UTC))
        self.max_keyset_age = max_keyset_age

    def install_keyset(self, document: Mapping[str, object]) -> None:
        self._authenticate_keyset(document)
        now = self._now().astimezone(UTC)
        self._require_fresh_keyset(document, now)
        history = self._verified_keyset_history()
        latest = history[-1] if history else None
        sequence = document.get("sequence")
        assert type(sequence) is int
        if latest is not None:
            current = latest.get("sequence")
            if type(current) is not int:
                raise CustodyError("stored custody keyset sequence is malformed")
            if sequence < current:
                raise CustodyError("custody keyset replay is stale")
            if sequence > current + 1:
                raise CustodyError("custody keyset history has a sequence gap")
        elif sequence != 1:
            raise CustodyError("first custody keyset must have sequence 1")
        self._enforce_key_history(document, history, latest)
        self.provenance.record_keyset(document)

    def _authenticate_keyset(self, document: Mapping[str, object]) -> None:
        _ensure_contract("custody-keyset", document)
        if _required_string(document, "authority_id") != self.anchor.authority_id:
            raise CustodyError("custody keyset belongs to another authority")
        if _required_string(document, "issuer_key_id") != self.anchor.key_id:
            raise CustodyError("custody keyset was not signed by the pinned root")
        if _required_string(document, "issuer_identity") != self.anchor.signer_identity:
            raise CustodyError("custody keyset issuer identity does not match the root")
        signature = _decode_b64url(
            _required_string(document, "signature"), field="keyset signature", expected_bytes=64
        )
        public_key = _decode_b64url(
            self.anchor.public_key, field="trust anchor public_key", expected_bytes=32
        )
        _ed25519_verify(public_key, _signed_payload(document, domain=_KEYSET_DOMAIN), signature)
        self._validate_keyset_keys(document)

    def _verified_keyset_history(self) -> list[dict[str, object]]:
        history = self.provenance.keyset_history(self.anchor.authority_id)
        for expected_sequence, keyset in enumerate(history, start=1):
            self._authenticate_keyset(keyset)
            if keyset.get("sequence") != expected_sequence:
                raise CustodyError("custody keyset history has a sequence gap")
        return history

    def _require_fresh_keyset(
        self,
        document: Mapping[str, object],
        now: datetime,
    ) -> None:
        issued_at = _parse_time(
            _required_string(document, "issued_at"), field="keyset issued_at"
        )
        expires_at = _parse_time(
            _required_string(document, "expires_at"), field="keyset expires_at"
        )
        if issued_at > now:
            raise CustodyError("custody keyset is not yet valid")
        if expires_at <= issued_at:
            raise CustodyError("custody keyset expiry must follow issuance")
        if expires_at < now:
            raise CustodyError("custody keyset has expired")
        if now - issued_at > self.max_keyset_age:
            raise CustodyError("custody keyset is stale")

    def _enforce_key_history(
        self,
        document: Mapping[str, object],
        history: Sequence[Mapping[str, object]],
        latest: Mapping[str, object] | None,
    ) -> None:
        historical: dict[str, list[Mapping[str, object]]] = {}
        for keyset in history:
            keys = keyset.get("keys")
            if not isinstance(keys, list):
                raise CustodyError("stored custody keyset is malformed")
            for key in keys:
                if not isinstance(key, Mapping):
                    raise CustodyError("stored custody keyset key is malformed")
                key_id = _required_string(key, "key_id")
                historical.setdefault(key_id, []).append(key)
        latest_ids: set[str] = set()
        if latest is not None:
            latest_keys = latest.get("keys")
            if not isinstance(latest_keys, list):
                raise CustodyError("stored custody keyset is malformed")
            for key in latest_keys:
                if not isinstance(key, Mapping):
                    raise CustodyError("stored custody keyset key is malformed")
                latest_ids.add(_required_string(key, "key_id"))
        keys = document.get("keys")
        assert isinstance(keys, list)
        for key in keys:
            assert isinstance(key, Mapping)
            key_id = _required_string(key, "key_id")
            earlier = historical.get(key_id, [])
            if earlier:
                if key_id not in latest_ids:
                    raise CustodyError("retired custody signer key cannot return")
                for prior in earlier:
                    if (
                        _required_string(prior, "signer_identity")
                        != _required_string(key, "signer_identity")
                        or _required_string(prior, "public_key")
                        != _required_string(key, "public_key")
                    ):
                        raise CustodyError("custody signer key identity cannot change")
                    if (
                        _required_string(prior, "status") == "revoked"
                        and _required_string(key, "status") == "active"
                    ):
                        raise CustodyError("revoked custody signer key cannot reactivate")

    @staticmethod
    def _validate_keyset_keys(document: Mapping[str, object]) -> None:
        keys = document.get("keys")
        if not isinstance(keys, list) or not keys:
            raise CustodyError("custody keyset must contain at least one key")
        identities: set[str] = set()
        key_ids: set[str] = set()
        for key in keys:
            if not isinstance(key, Mapping):
                raise CustodyError("custody keyset key must be an object")
            key_id = _required_string(key, "key_id")
            identity = _required_string(key, "signer_identity")
            if key_id in key_ids or identity in identities:
                raise CustodyError("custody keyset contains duplicate key identity")
            key_ids.add(key_id)
            identities.add(identity)
            _decode_b64url(
                _required_string(key, "public_key"),
                field="keyset public_key",
                expected_bytes=32,
            )
            status = _required_string(key, "status")
            if status not in {"active", "revoked"}:
                raise CustodyError("custody keyset status is unsupported")
            _parse_time(_required_string(key, "not_before"), field="key not_before")
            not_after = key.get("not_after")
            if not_after is not None:
                if not isinstance(not_after, str):
                    raise CustodyError("custody key not_after must be RFC 3339 or null")
                if _parse_time(not_after, field="key not_after") <= _parse_time(
                    _required_string(key, "not_before"), field="key not_before"
                ):
                    raise CustodyError("custody key validity window is empty")
            revoked_at = key.get("revoked_at")
            if status == "revoked":
                if not isinstance(revoked_at, str):
                    raise CustodyError("revoked custody key requires revoked_at")
                _parse_time(revoked_at, field="key revoked_at")
            elif revoked_at is not None:
                raise CustodyError("active custody key cannot declare revoked_at")

    def verify_configuration(
        self,
        mission_id: str,
        configuration: Mapping[str, object],
        attestation: Mapping[str, object],
    ) -> dict[str, object]:
        return self.verify(CustodySubject.configuration(mission_id, configuration), attestation)

    def verify_receipt(
        self,
        receipt: Mapping[str, object],
        reference: ReceiptReference,
        attestation: Mapping[str, object],
    ) -> dict[str, object]:
        return self.verify(CustodySubject.receipt(receipt, reference), attestation)

    def verify_signed_envelope(
        self,
        document: Mapping[str, object],
        *,
        audience: str,
        domain: bytes,
    ) -> dict[str, object]:
        """Verify a versioned external envelope after its domain schema is checked.

        This is intentionally limited to the common public-key/keyset boundary.  A
        caller still validates its own closed schema and semantic subject before using
        this primitive; it never treats a local document digest as authentication.
        """

        authority_id = _required_string(document, "authority_id")
        if authority_id != self.anchor.authority_id:
            raise CustodyError("custody envelope belongs to another authority")
        if _required_string(document, "algorithm") != "ed25519":
            raise CustodyError("custody envelope algorithm is not accepted")
        if _required_string(document, "audience") != audience:
            raise CustodyError("custody envelope audience is not accepted")
        issued_at = _parse_time(_required_string(document, "issued_at"), field="issued_at")
        expires_at = _parse_time(_required_string(document, "expires_at"), field="expires_at")
        now = self._now().astimezone(UTC)
        if expires_at <= issued_at:
            raise CustodyError("custody envelope expiry must follow issuance")
        if issued_at > now:
            raise CustodyError("custody envelope is not yet valid")
        if expires_at < now:
            raise CustodyError("custody envelope has expired")
        keyset_sequence = document.get("keyset_sequence")
        if type(keyset_sequence) is not int or keyset_sequence < 1:
            raise CustodyError("custody envelope keyset_sequence is invalid")
        history = self._verified_keyset_history()
        if not history:
            raise CustodyError("custody authority has no installed keyset")
        latest = history[-1]
        self._require_fresh_keyset(latest, now)
        if latest.get("sequence") != keyset_sequence:
            raise CustodyError("custody envelope uses a stale or unavailable keyset")
        key = self._attestation_key(latest, document, issued_at, now)
        signature = _decode_b64url(
            _required_string(document, "signature"),
            field="envelope signature",
            expected_bytes=64,
        )
        _ed25519_verify(
            _decode_b64url(
                _required_string(key, "public_key"),
                field="keyset public_key",
                expected_bytes=32,
            ),
            _signed_payload(document, domain=domain),
            signature,
        )
        return dict(document)

    def verify(
        self,
        expected_subject: CustodySubject,
        attestation: Mapping[str, object],
    ) -> dict[str, object]:
        _ensure_contract("custody-attestation", attestation)
        subject_value = attestation.get("subject")
        if not isinstance(subject_value, Mapping):
            raise CustodyError("custody attestation subject is required")
        observed_subject = CustodySubject.from_dict(subject_value)
        if observed_subject.to_dict() != expected_subject.to_dict():
            raise CustodyError("custody attestation does not bind the expected subject")
        if (
            expected_subject.kind == "tool-receipt"
            and _required_string(attestation, "signer_identity")
            == expected_subject.bindings["actor_id"]
        ):
            raise CustodyError("receipt custody signer must be external to the acting identity")
        self.verify_signed_envelope(
            attestation,
            audience=CUSTODY_AUDIENCE,
            domain=_ATTESTATION_DOMAIN,
        )
        self.provenance.record_attestation(attestation, expected_subject)
        return dict(attestation)

    @staticmethod
    def _attestation_key(
        keyset: Mapping[str, object],
        attestation: Mapping[str, object],
        issued_at: datetime,
        now: datetime,
    ) -> Mapping[str, object]:
        key_id = _required_string(attestation, "key_id")
        identity = _required_string(attestation, "signer_identity")
        keys = keyset.get("keys")
        if not isinstance(keys, list):
            raise CustodyError("installed custody keyset is malformed")
        for key in keys:
            if not isinstance(key, Mapping):
                continue
            if key.get("key_id") == key_id:
                if _required_string(key, "signer_identity") != identity:
                    raise CustodyError("custody signer identity does not match its key")
                if _required_string(key, "status") != "active":
                    raise CustodyError("custody signer key is revoked")
                valid_from = _parse_time(
                    _required_string(key, "not_before"), field="key not_before"
                )
                valid_until_value = key.get("not_after")
                valid_until = (
                    None
                    if valid_until_value is None
                    else _parse_time(str(valid_until_value), field="key not_after")
                )
                if issued_at < valid_from or now < valid_from or (
                    valid_until is not None
                    and (issued_at > valid_until or now > valid_until)
                ):
                    raise CustodyError("custody signer key is outside its validity window")
                return key
        raise CustodyError("custody signer key is unknown")


class ExternalCustodyAdapter:
    """Bounded request/verify adapter; signing material remains outside this process."""

    def __init__(self, attestor: CustodyAttestor, verifier: Ed25519CustodyVerifier) -> None:
        self.attestor = attestor
        self.verifier = verifier

    def attest_configuration(
        self,
        mission_id: str,
        configuration: Mapping[str, object],
    ) -> dict[str, object]:
        subject = CustodySubject.configuration(mission_id, configuration)
        return self.verifier.verify(subject, self.attestor.attest(subject.to_dict()))

    def attest_receipt(
        self,
        receipt: Mapping[str, object],
        reference: ReceiptReference,
    ) -> dict[str, object]:
        subject = CustodySubject.receipt(receipt, reference)
        return self.verifier.verify(subject, self.attestor.attest(subject.to_dict()))
