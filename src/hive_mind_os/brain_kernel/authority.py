"""Fail-closed local capability validation for future kernel effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .canonical import canonical_digest
from .contracts import ConstraintEnvelope, normalize_portable_path

READ_ACTIONS = frozenset({"read"})


class AuthorityDenied(PermissionError):
    """A requested capability is absent, expired, revoked, or out of scope."""


@dataclass(frozen=True, slots=True)
class CapabilityToken:
    envelope_digest: str
    action: str
    target: str
    token_digest: str


@dataclass(frozen=True, slots=True)
class RootProvenance:
    """The recorded act that admitted one root authority into a registry."""

    envelope_digest: str
    issuer: str
    authority_ref: str
    recorded_at: str
    record_digest: str


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

    def root_provenance(self, digest: str) -> RootProvenance | None:
        return self._roots.get(digest)

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
        envelope = self._envelopes.get(digest)
        if envelope is None or self._is_revoked(envelope):
            raise AuthorityDenied("authority envelope is unavailable")
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
        return CapabilityToken(digest, action, normalized, token_digest)

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
