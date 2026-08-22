"""Fail-closed local capability validation for future kernel effects."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .canonical import canonical_digest
from .contracts import ConstraintEnvelope, normalize_portable_path

READ_ACTIONS = frozenset({"read"})

# A capability is only a capability if it cannot be minted by whoever wants to
# spend it.  ``authorize`` seals every token it issues with a process-local key,
# so a hand-built token -- the A5-F10 forgery -- fails at construction rather
# than travelling to a gateway that may or may not hold the issuing registry.
# Like the delivery grant ledger this is attribution by record, not a signature:
# it cannot stop a caller that is already inside the process from reading the key
# or writing the dataclass slots directly.
_ISSUANCE_KEY = secrets.token_hex(32)


class AuthorityDenied(PermissionError):
    """A requested capability is absent, expired, revoked, or out of scope."""


def _issuance_witness(envelope_digest: str, action: str, target: str) -> str:
    """Keyed seal proving some registry in this process issued these three fields."""

    return canonical_digest(
        {
            "envelope": envelope_digest,
            "action": action,
            "target": target,
            "issuance_key": _ISSUANCE_KEY,
        }
    )


@dataclass(frozen=True, slots=True)
class CapabilityToken:
    """One issued capability; a token no registry issued cannot be constructed."""

    envelope_digest: str
    action: str
    target: str
    token_digest: str
    issuance_witness: str = ""

    def __post_init__(self) -> None:
        if self.issuance_witness != _issuance_witness(
            self.envelope_digest, self.action, self.target
        ):
            raise AuthorityDenied(
                "capability token was not issued by an authority registry"
            )


def token_is_issued(token: CapabilityToken) -> bool:
    """Report whether a token still carries this process's issuance witness."""

    return token.issuance_witness == _issuance_witness(
        token.envelope_digest, token.action, token.target
    )


@dataclass(frozen=True, slots=True)
class RootProvenance:
    """The recorded act that admitted one root authority into a registry."""

    envelope_digest: str
    issuer: str
    authority_ref: str
    recorded_at: str
    record_digest: str


def _rfc3339(value: str, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise AuthorityDenied(f"{label} requires an RFC 3339 time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AuthorityDenied(f"{label} requires an RFC 3339 time") from error
    if parsed.tzinfo is None:
        raise AuthorityDenied(f"{label} requires an RFC 3339 time")
    return parsed


@dataclass(frozen=True, slots=True)
class ExternalRootAttestation:
    """Opaque owner-root statement prepared for an external verifier.

    The digest seals claims passed to the verifier. It is not a signature:
    authentication comes only from separately administered verifier custody.
    """

    envelope_digest: str
    issuer: str
    authority_ref: str
    issued_at: str
    expires_at: str
    attestation_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.envelope_digest, str)
            or not self.envelope_digest
            or not isinstance(self.issuer, str)
            or not self.issuer.strip()
            or not isinstance(self.authority_ref, str)
            or not self.authority_ref.strip()
        ):
            raise AuthorityDenied(
                "external root attestation requires bound authority claims"
            )
        issued = _rfc3339(self.issued_at, "external root attestation issued_at")
        expires = _rfc3339(self.expires_at, "external root attestation expires_at")
        if expires <= issued:
            raise AuthorityDenied("external root attestation must expire after issuance")
        if self.attestation_digest != canonical_digest(self._payload()):
            raise AuthorityDenied(
                "external root attestation digest does not seal its claims"
            )

    def _payload(self) -> dict[str, str]:
        return {
            "envelope": self.envelope_digest,
            "issuer": self.issuer,
            "authority_ref": self.authority_ref,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def issue(
        cls,
        *,
        envelope: ConstraintEnvelope,
        issuer: str,
        authority_ref: str,
        issued_at: str,
        expires_at: str,
    ) -> "ExternalRootAttestation":
        payload = {
            "envelope": envelope.digest_value,
            "issuer": issuer,
            "authority_ref": authority_ref,
            "issued_at": issued_at,
            "expires_at": expires_at,
        }
        return cls(
            envelope.digest_value,
            issuer,
            authority_ref,
            issued_at,
            expires_at,
            canonical_digest(payload),
        )


@dataclass(frozen=True, slots=True)
class ExternalRootVerification:
    """A verifier's receipted decision about one sealed root attestation."""

    attestation_digest: str
    verifier_id: str
    receipt_ref: str
    verified_at: str
    accepted: bool
    verification_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.attestation_digest, str)
            or not self.attestation_digest
            or not isinstance(self.verifier_id, str)
            or not self.verifier_id.strip()
            or not isinstance(self.receipt_ref, str)
            or not self.receipt_ref.strip()
        ):
            raise AuthorityDenied("external root verification requires verifier evidence")
        _rfc3339(self.verified_at, "external root verification verified_at")
        if type(self.accepted) is not bool:
            raise AuthorityDenied("external root verification acceptance must be boolean")
        if self.verification_digest != canonical_digest(self._payload()):
            raise AuthorityDenied(
                "external root verification digest does not seal its claims"
            )

    def _payload(self) -> dict[str, object]:
        return {
            "attestation": self.attestation_digest,
            "verifier": self.verifier_id,
            "receipt_ref": self.receipt_ref,
            "verified_at": self.verified_at,
            "accepted": self.accepted,
        }

    @classmethod
    def record(
        cls,
        attestation: ExternalRootAttestation,
        *,
        verifier_id: str,
        receipt_ref: str,
        verified_at: str,
        accepted: bool,
    ) -> "ExternalRootVerification":
        payload: dict[str, object] = {
            "attestation": attestation.attestation_digest,
            "verifier": verifier_id,
            "receipt_ref": receipt_ref,
            "verified_at": verified_at,
            "accepted": accepted,
        }
        return cls(
            attestation.attestation_digest,
            verifier_id,
            receipt_ref,
            verified_at,
            accepted,
            canonical_digest(payload),
        )


class ExternalRootVerifier(Protocol):
    """Replaceable, owner-operated verifier boundary for a root attestation."""

    verifier_id: str

    def verify_root(
        self, attestation: ExternalRootAttestation
    ) -> ExternalRootVerification: ...


def intersect_envelopes(parent: ConstraintEnvelope, child: ConstraintEnvelope) -> ConstraintEnvelope:
    """Reject a broadening child; intersection itself grants no capability."""

    if child.parent_envelope_digest != parent.digest_value or not child.is_no_broader_than(parent):
        raise AuthorityDenied("child envelope broadens or is not bound to its parent")
    return child


class AuthorityRegistry:
    """In-memory local registry; callers must present a validated capability token."""

    def __init__(self) -> None:
        self._envelopes: dict[str, ConstraintEnvelope] = {}
        self._roots: dict[str, RootProvenance] = {}
        self._external_roots: dict[
            str, tuple[ExternalRootAttestation, ExternalRootVerification]
        ] = {}
        self._revoked: set[str] = set()
        self._revoked_authorities: set[str] = set()

    def mint_root(
        self,
        envelope: ConstraintEnvelope,
        *,
        issuer: str,
        authority_ref: str,
        recorded_at: str,
    ) -> RootProvenance:
        """Admit a root authority only through a recorded provenance ceremony."""

        if envelope.parent_envelope_digest is not None:
            raise AuthorityDenied("root authority must not declare a parent")
        for value, label in ((issuer, "issuer"), (authority_ref, "authority reference")):
            if not isinstance(value, str) or not value.strip():
                raise AuthorityDenied(f"root authority requires a recorded {label}")
        try:
            datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as error:
            raise AuthorityDenied("root provenance requires an RFC 3339 time") from error
        self._admit(envelope)
        record = RootProvenance(
            envelope.digest_value,
            issuer,
            authority_ref,
            recorded_at,
            canonical_digest(
                {
                    "envelope": envelope.digest_value,
                    "issuer": issuer,
                    "authority_ref": authority_ref,
                    "recorded_at": recorded_at,
                }
            ),
        )
        self._roots[envelope.digest_value] = record
        return record

    def admit_external_root(
        self,
        envelope: ConstraintEnvelope,
        *,
        attestation: ExternalRootAttestation,
        verifier: ExternalRootVerifier,
    ) -> RootProvenance:
        """Admit a root only after an injected external verifier accepts it.

        This method is an integration contract, not evidence that the supplied
        verifier is externally administered. Deployment must provide custody,
        identity, rotation, and independent witness evidence before this record
        can support an external-authority claim.
        """

        if envelope.parent_envelope_digest is not None:
            raise AuthorityDenied("external root authority must not declare a parent")
        if not isinstance(attestation, ExternalRootAttestation):
            raise AuthorityDenied("external root requires a sealed attestation")
        if (
            attestation.envelope_digest != envelope.digest_value
            or attestation.issuer != attestation.issuer.strip()
            or attestation.authority_ref != attestation.authority_ref.strip()
        ):
            raise AuthorityDenied("external root attestation does not bind this authority")
        verifier_id = getattr(verifier, "verifier_id", None)
        verify = getattr(verifier, "verify_root", None)
        if not isinstance(verifier_id, str) or not verifier_id.strip() or not callable(verify):
            raise AuthorityDenied("external root requires a configured verifier")
        try:
            verification = verify(attestation)
        except Exception as error:
            raise AuthorityDenied(
                "external root verifier failed closed: " + type(error).__name__
            ) from None
        if not isinstance(verification, ExternalRootVerification):
            raise AuthorityDenied("external root verifier returned no sealed verification")
        if (
            verification.attestation_digest != attestation.attestation_digest
            or verification.verifier_id != verifier_id
            or not verification.accepted
        ):
            raise AuthorityDenied("external root verification does not accept this attestation")
        verified_at = _rfc3339(
            verification.verified_at, "external root verification verified_at"
        )
        issued_at = _rfc3339(
            attestation.issued_at, "external root attestation issued_at"
        )
        expires_at = _rfc3339(
            attestation.expires_at, "external root attestation expires_at"
        )
        if verified_at < issued_at or verified_at >= expires_at:
            raise AuthorityDenied("external root verification is outside attestation validity")
        self._admit(envelope)
        record = RootProvenance(
            envelope.digest_value,
            attestation.issuer,
            attestation.authority_ref,
            verification.verified_at,
            canonical_digest(
                {
                    "envelope": envelope.digest_value,
                    "issuer": attestation.issuer,
                    "authority_ref": attestation.authority_ref,
                    "recorded_at": verification.verified_at,
                }
            ),
        )
        self._roots[envelope.digest_value] = record
        self._external_roots[envelope.digest_value] = (attestation, verification)
        return record

    def root_provenance(self, digest: str) -> RootProvenance | None:
        return self._roots.get(digest)

    def external_root_evidence(
        self, digest: str
    ) -> tuple[ExternalRootAttestation, ExternalRootVerification] | None:
        """Return the sealed external-verifier evidence recorded for one root."""

        return self._external_roots.get(digest)

    def require_external_root(
        self,
        digest: str,
        *,
        now: str,
    ) -> tuple[ExternalRootAttestation, ExternalRootVerification]:
        """Require a live, externally verified root before deployment wiring."""

        self.envelope(digest)
        evidence = self._external_roots.get(digest)
        if evidence is None:
            raise AuthorityDenied("authority root lacks external verifier evidence")
        attestation, verification = evidence
        moment = _rfc3339(now, "external root verification now")
        expires_at = _rfc3339(
            attestation.expires_at, "external root attestation expires_at"
        )
        if moment >= expires_at:
            raise AuthorityDenied("external root attestation is expired")
        if not verification.accepted:
            raise AuthorityDenied("external root verification is not accepted")
        return evidence

    def envelope(self, digest: str) -> ConstraintEnvelope:
        """Read one admitted authority; absence and revocation both fail closed.

        The public read the effect boundary needs, so no caller has to reach into
        the registry's private admission table to resolve an authorized digest.
        """

        envelope = self._envelopes.get(digest)
        if envelope is None or self._is_revoked(envelope):
            raise AuthorityDenied("authority envelope is unavailable")
        return envelope

    def register(self, envelope: ConstraintEnvelope, parent: ConstraintEnvelope | None = None) -> None:
        if envelope.parent_envelope_digest is None:
            raise AuthorityDenied("root envelope requires an explicit mint ceremony")
        admitted = self._envelopes.get(envelope.parent_envelope_digest)
        if admitted is None:
            raise AuthorityDenied("parent envelope is required")
        if parent is not None and parent != admitted:
            raise AuthorityDenied("parent envelope is not the admitted authority")
        intersect_envelopes(admitted, envelope)
        self._admit(envelope)

    def revoke(self, digest: str) -> None:
        """Revoke the authority itself, so re-minting under a new digest cannot restore it."""

        self._revoked.add(digest)
        envelope = self._envelopes.get(digest)
        if envelope is not None:
            self._revoked_authorities.add(envelope.authority_key())

    def authorize(self, digest: str, action: str, target: str, *, now: str) -> CapabilityToken:
        envelope = self.envelope(digest)
        if datetime.fromisoformat(now.replace("Z", "+00:00")) >= datetime.fromisoformat(envelope.expires_at.replace("Z", "+00:00")):
            raise AuthorityDenied("authority envelope is expired")
        normalized = normalize_portable_path(target)
        if action not in envelope.allowed_actions or action in envelope.denied_actions:
            raise AuthorityDenied("action is not granted")
        reading = action in READ_ACTIONS
        scope = envelope.path_read_scope if reading else envelope.path_write_scope
        if not any(
            normalized == path or normalized.startswith(path + "/") for path in scope
        ):
            raise AuthorityDenied(
                "target is outside read scope" if reading else "target is outside write scope"
            )
        token_digest = canonical_digest({"envelope": digest, "action": action, "target": normalized})
        return CapabilityToken(
            digest,
            action,
            normalized,
            token_digest,
            _issuance_witness(digest, action, normalized),
        )

    def _admit(self, envelope: ConstraintEnvelope) -> None:
        if envelope.digest_value != envelope.content_digest():
            raise AuthorityDenied("envelope digest does not seal its contents")
        if self._is_revoked(envelope):
            raise AuthorityDenied("authority is revoked")
        self._envelopes[envelope.digest_value] = envelope

    def _is_revoked(self, envelope: ConstraintEnvelope) -> bool:
        """Refuse a revoked authority, a re-mint of one, and any descendant of one."""

        seen: set[str] = set()
        current: ConstraintEnvelope | None = envelope
        while current is not None and current.digest_value not in seen:
            if (
                current.digest_value in self._revoked
                or current.authority_key() in self._revoked_authorities
            ):
                return True
            seen.add(current.digest_value)
            parent = current.parent_envelope_digest
            current = self._envelopes.get(parent) if parent is not None else None
        return False
