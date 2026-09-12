"""Explicit trust and signed, version-bound promotion attestations.

Trust is supplied by the host, never inferred from candidate evidence. No keys,
credentials or permissive verifier are created by this module. Administration
independence is checked against that trusted configuration; software cannot prove
that two real-world administrators are independent merely from their labels.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Protocol

from .canonical import canonical_bytes, canonical_digest

_STAGES = ("builder", "verifier", "judge", "promoter")
_HEX = frozenset("0123456789abcdef")


class PromotionAuthenticationError(RuntimeError):
    """A stable diagnostic, not an assertion that a rejection was persisted."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _fail(code: str, message: str) -> None:
    raise PromotionAuthenticationError(code, message)


def _text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("authentication-malformed", f"{label} must be an exact identifier")
    return value


def _digest(value: Any, label: str) -> str:
    value = _text(value, label)
    if not value.startswith("sha256:") or len(value) != 71 or set(value[7:]) - _HEX:
        _fail("authentication-malformed", f"{label} must be a full SHA-256 digest")
    return value


def _object(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("authentication-malformed", f"{label} has an invalid field set")
    return dict(value)


def _time(value: Any) -> datetime:
    value = _text(value, "timestamp")
    if not value.endswith("Z"):
        _fail("authentication-malformed", "timestamp must use explicit UTC Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise PromotionAuthenticationError("authentication-malformed", "invalid UTC timestamp") from error
    if parsed.tzinfo != timezone.utc:
        _fail("authentication-malformed", "timestamp must be UTC")
    return parsed


def _signature(value: Any) -> bytes:
    value = _text(value, "signature")
    if len(value) > 8192:
        _fail("authentication-malformed", "signature exceeds the supported size")
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise PromotionAuthenticationError("authentication-malformed", "invalid signature encoding") from error
    if not raw or base64.b64encode(raw).decode("ascii") != value:
        _fail("authentication-malformed", "signature must be canonical base64")
    return raw


@dataclass(frozen=True, slots=True)
class PrincipalBinding:
    principal_id: str
    stage: str
    administration_id: str
    key_id: str
    public_key_digest: str

    def __post_init__(self) -> None:
        for name in ("principal_id", "administration_id", "key_id"):
            _text(getattr(self, name), name)
        if self.stage not in (*_STAGES, "receipt"):
            _fail("authentication-policy-invalid", "unknown principal stage")
        _digest(self.public_key_digest, "public key digest")

    def document(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in (
            "principal_id", "stage", "administration_id", "key_id", "public_key_digest"
        )}


class SignatureVerifier(Protocol):
    def verify(self, principal: PrincipalBinding, message: bytes, signature: bytes) -> bool:
        """Verify against the configured public-key pin, not a document key."""
        ...


class ReceiptSigner(Protocol):
    principal_id: str
    key_id: str

    def sign(self, message: bytes) -> bytes:
        """Sign through host-provided custody; never obtain keys from evidence."""
        ...


@dataclass(frozen=True, slots=True)
class SignedAttestation:
    stage: str
    principal_id: str
    key_id: str
    policy_digest: str
    subject_digest: str
    record_digest: str | None
    decision_digest: str | None
    nonce: str
    issued_at: str
    expires_at: str
    signature: str

    def __post_init__(self) -> None:
        if self.stage not in _STAGES:
            _fail("authentication-malformed", "unknown attestation stage")
        for name in ("principal_id", "key_id", "nonce"):
            _text(getattr(self, name), name)
        for name in ("policy_digest", "subject_digest"):
            _digest(getattr(self, name), name)
        for name in ("record_digest", "decision_digest"):
            value = getattr(self, name)
            if value is not None:
                _digest(value, name)
        if self.stage == "builder":
            if self.record_digest is not None or self.decision_digest is not None:
                _fail("authentication-malformed", "builder signs the subject before evaluation")
        elif self.record_digest is None:
            _fail("authentication-malformed", "evaluation evidence binding is missing")
        if self.stage == "verifier" and self.decision_digest is not None:
            _fail("authentication-malformed", "verifier must not pre-authorize a judgment")
        if self.stage in ("judge", "promoter") and self.decision_digest is None:
            _fail("authentication-malformed", "decision binding is missing")
        if _time(self.issued_at) >= _time(self.expires_at):
            _fail("authentication-malformed", "attestation validity interval is empty")
        _signature(self.signature)

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "kind": "promotion-attestation",
            **{name: getattr(self, name) for name in (
                "stage", "principal_id", "key_id", "policy_digest", "subject_digest",
                "record_digest", "decision_digest", "nonce", "issued_at", "expires_at"
            )},
        }

    def document(self) -> dict[str, Any]:
        return {**self.payload(), "signature": self.signature}

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> SignedAttestation:
        fields = {
            "stage", "principal_id", "key_id", "policy_digest", "subject_digest",
            "record_digest", "decision_digest", "nonce", "issued_at", "expires_at", "signature"
        }
        data = _object(value, fields | {"schema_version", "kind"}, "attestation")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["kind"] != "promotion-attestation":
            _fail("authentication-malformed", "unsupported attestation schema")
        return cls(**{name: data[name] for name in fields})


@dataclass(frozen=True, slots=True)
class PromotionAuthorization:
    attestations: tuple[SignedAttestation, ...]

    def __post_init__(self) -> None:
        if type(self.attestations) is not tuple or len(self.attestations) != 4:
            _fail("authentication-malformed", "exactly four stage attestations are required")
        if any(not isinstance(item, SignedAttestation) for item in self.attestations):
            _fail("authentication-malformed", "invalid attestation value")
        if tuple(item.stage for item in self.attestations) != _STAGES:
            _fail("authentication-malformed", "attestations must cover each stage in order")
        if len({item.nonce for item in self.attestations}) != 4:
            _fail("authentication-replayed", "attestation nonces must be distinct")

    def document(self) -> dict[str, Any]:
        return {"schema_version": 1, "attestations": [item.document() for item in self.attestations]}

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> PromotionAuthorization:
        data = _object(value, {"schema_version", "attestations"}, "authorization")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1 or type(data["attestations"]) is not list:
            _fail("authentication-malformed", "unsupported authorization schema")
        return cls(tuple(SignedAttestation.from_document(item) for item in data["attestations"]))


@dataclass(frozen=True, slots=True)
class VerifiedAuthorization:
    authorization_digest: str
    policy_digest: str
    principals: tuple[str, ...]
    nonce_ids: tuple[str, ...]


class PromotionPrincipalVerifier:
    """Require trusted, separately administered stage principals and signatures.

    This object validates attestations; the registry owns durable nonce/evaluation
    consumption and the atomic live-parent transition. No verification result is
    a bearer token or permission to skip that transaction.
    """

    def __init__(
        self, principals: Sequence[PrincipalBinding], signature_verifier: SignatureVerifier,
        receipt_signer: ReceiptSigner, *, maximum_age_seconds: int = 3600,
    ) -> None:
        bound = tuple(principals)
        if not bound or any(not isinstance(item, PrincipalBinding) for item in bound):
            _fail("authentication-policy-invalid", "trusted principal bindings are required")
        if len({p.principal_id for p in bound}) != len(bound) or len({p.key_id for p in bound}) != len(bound):
            _fail("authentication-policy-invalid", "principal and key identifiers must be unique")
        if type(maximum_age_seconds) is not int or maximum_age_seconds < 1:
            _fail("authentication-policy-invalid", "maximum age must be a positive integer")
        if not callable(getattr(signature_verifier, "verify", None)) or not callable(getattr(receipt_signer, "sign", None)):
            _fail("authentication-policy-invalid", "explicit signature verifier and receipt signer are required")
        receipt = next((p for p in bound if p.principal_id == receipt_signer.principal_id), None)
        if receipt is None or receipt.stage != "receipt" or receipt.key_id != receipt_signer.key_id:
            _fail("authentication-policy-invalid", "receipt signer is not in the trusted policy")
        self._principals = MappingProxyType({p.principal_id: p for p in bound})
        self._verifier = signature_verifier
        self._signer = receipt_signer
        self._receipt = receipt
        self._maximum_age = maximum_age_seconds
        self._policy_bytes = canonical_bytes({
            "schema_version": 1, "kind": "promotion-principal-policy",
            "maximum_age_seconds": maximum_age_seconds,
            "principals": [p.document() for p in sorted(bound, key=lambda p: p.principal_id)],
        })

    @property
    def policy_digest(self) -> str:
        return "sha256:" + hashlib.sha256(self._policy_bytes).hexdigest()

    def policy_document(self) -> dict[str, Any]:
        """A detached inspection copy of the exact trusted policy preimage."""
        return json.loads(self._policy_bytes)

    def _verify(self, principal: PrincipalBinding, payload: Mapping[str, Any], signature: str) -> None:
        try:
            accepted = self._verifier.verify(principal, canonical_bytes(dict(payload)), _signature(signature))
        except PromotionAuthenticationError:
            raise
        except Exception as error:
            raise PromotionAuthenticationError("authentication-unavailable", "signature provider failed") from error
        if accepted is not True:
            _fail("authentication-signature-invalid", "signature does not match its trusted principal")

    def verify_authorization(
        self, document: Mapping[str, Any] | PromotionAuthorization, *,
        subject_digest: str, record_digest: str, builder_id: str, evaluator_id: str,
        judge_id: str, promoter_id: str, decision_digest: str,
        now: datetime | None = None,
    ) -> VerifiedAuthorization:
        authorization = document if isinstance(document, PromotionAuthorization) else PromotionAuthorization.from_document(document)
        for value in (subject_digest, record_digest, decision_digest):
            _digest(value, "expected binding")
        identities = (builder_id, evaluator_id, judge_id, promoter_id)
        if len(set(identities)) != 4:
            _fail("authentication-independence", "builder, verifier, judge and promoter must be different principals")
        current = now if now is not None else datetime.now(timezone.utc)
        if not isinstance(current, datetime) or current.tzinfo is None or current.utcoffset() != timedelta(0):
            _fail("authentication-malformed", "verification time must be an aware UTC datetime")
        administrations: set[str] = set()
        keys: set[str] = set()
        issued_before: datetime | None = None
        nonces: list[str] = []
        for stage, expected_id, attestation in zip(_STAGES, identities, authorization.attestations):
            principal = self._principals.get(expected_id)
            if principal is None or principal.stage != stage:
                _fail("authentication-principal-unknown", "expected principal is not trusted for this stage")
            if principal.administration_id in administrations or principal.public_key_digest in keys:
                _fail("authentication-independence", "stage principals require distinct trusted administrations and keys")
            administrations.add(principal.administration_id)
            keys.add(principal.public_key_digest)
            if attestation.principal_id != expected_id or attestation.key_id != principal.key_id:
                _fail("authentication-principal-mismatch", "attestation substituted a principal or key")
            if attestation.policy_digest != self.policy_digest:
                _fail("authentication-policy-mismatch", "attestation uses another trust policy")
            if attestation.subject_digest != subject_digest:
                _fail("authentication-subject-mismatch", "attestation uses another immutable subject")
            if stage != "builder" and attestation.record_digest != record_digest:
                _fail("authentication-record-mismatch", "attestation uses another evaluation record")
            if stage in ("judge", "promoter") and attestation.decision_digest != decision_digest:
                _fail("authentication-decision-mismatch", "attestation uses another decision")
            issued, expires = _time(attestation.issued_at), _time(attestation.expires_at)
            if issued > current or current >= expires or current - issued > timedelta(seconds=self._maximum_age):
                _fail("authentication-stale", "attestation is future-dated, expired or too old")
            if expires - issued > timedelta(seconds=self._maximum_age):
                _fail("authentication-stale", "attestation validity exceeds trusted policy")
            if issued_before is not None and issued < issued_before:
                _fail("authentication-ordering", "stage timestamps contradict builder/verifier/judge/promoter ordering")
            issued_before = issued
            self._verify(principal, attestation.payload(), attestation.signature)
            nonces.append(canonical_digest({"policy": self.policy_digest, "principal": expected_id, "nonce": attestation.nonce}))
        return VerifiedAuthorization(canonical_digest(authorization.document()), self.policy_digest, identities, tuple(nonces))

    def sign_rejection(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return authenticated bytes; caller must durably retain them."""
        if not isinstance(payload, Mapping):
            _fail("authentication-malformed", "rejection payload must be an object")
        # Freeze the caller's document before invoking external signing custody.
        frozen = json.loads(canonical_bytes(dict(payload)))
        unsigned = {
            "schema_version": 1, "kind": "promotion-rejection",
            "policy_digest": self.policy_digest,
            "principal_id": self._receipt.principal_id, "key_id": self._receipt.key_id,
            "payload": frozen,
        }
        try:
            raw = self._signer.sign(canonical_bytes(unsigned))
        except Exception as error:
            raise PromotionAuthenticationError("rejection-signing-unavailable", "rejection signer failed") from error
        if type(raw) is not bytes or not raw:
            _fail("rejection-signing-unavailable", "rejection signer returned no signature")
        encoded = base64.b64encode(raw).decode("ascii")
        self._verify(self._receipt, unsigned, encoded)
        return {**unsigned, "signature": encoded}

    def verify_rejection_receipt(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        data = _object(receipt, {"schema_version", "kind", "policy_digest", "principal_id", "key_id", "payload", "signature"}, "rejection receipt")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["kind"] != "promotion-rejection":
            _fail("authentication-malformed", "unsupported rejection receipt schema")
        if data["policy_digest"] != self.policy_digest or data["principal_id"] != self._receipt.principal_id or data["key_id"] != self._receipt.key_id:
            _fail("authentication-policy-mismatch", "rejection receipt does not match trusted custody")
        if not isinstance(data["payload"], dict):
            _fail("authentication-malformed", "rejection payload must be an object")
        signature = data.pop("signature")
        self._verify(self._receipt, data, signature)
        return json.loads(canonical_bytes(data["payload"]))


class Ed25519SignatureVerifier:
    """Optional cryptography-backed adapter using host-pinned raw public keys.

    The optional provider is loaded only when used. Missing cryptography fails
    closed; installing it or provisioning private keys is an operator concern.
    """

    def __init__(self, public_keys: Mapping[str, bytes]) -> None:
        self._keys = MappingProxyType(dict(public_keys))
        if any(type(key) is not str or type(raw) is not bytes or len(raw) != 32 for key, raw in self._keys.items()):
            _fail("authentication-policy-invalid", "Ed25519 public keys must be 32 raw bytes")

    def verify(self, principal: PrincipalBinding, message: bytes, signature: bytes) -> bool:
        raw = self._keys.get(principal.key_id)
        if raw is None or "sha256:" + hashlib.sha256(raw).hexdigest() != principal.public_key_digest:
            return False
        try:
            provider = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
        except ImportError as error:
            raise PromotionAuthenticationError("authentication-unavailable", "Ed25519 requires the optional cryptography provider") from error
        try:
            provider.Ed25519PublicKey.from_public_bytes(raw).verify(signature, message)
        except (ValueError, TypeError):
            return False
        except Exception as error:
            # Avoid a hard import of an optional provider merely to name its
            # InvalidSignature type, while not concealing provider failures.
            if type(error).__name__ == "InvalidSignature":
                return False
            raise
        return True


class Ed25519ReceiptSigner:
    """In-memory raw-key adapter; external custody can implement ReceiptSigner."""

    def __init__(self, principal_id: str, key_id: str, private_key: bytes) -> None:
        self.principal_id = _text(principal_id, "receipt principal")
        self.key_id = _text(key_id, "receipt key")
        if type(private_key) is not bytes or len(private_key) != 32:
            _fail("authentication-policy-invalid", "Ed25519 private key must be 32 raw bytes")
        self._private_key = private_key

    def sign(self, message: bytes) -> bytes:
        try:
            provider = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
        except ImportError as error:
            raise PromotionAuthenticationError("rejection-signing-unavailable", "Ed25519 requires the optional cryptography provider") from error
        return provider.Ed25519PrivateKey.from_private_bytes(self._private_key).sign(message)
