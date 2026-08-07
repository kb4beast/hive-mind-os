"""Fail-closed local capability validation for future kernel effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .canonical import canonical_digest
from .contracts import ConstraintEnvelope, normalize_portable_path


class AuthorityDenied(PermissionError):
    """A requested capability is absent, expired, revoked, or out of scope."""


@dataclass(frozen=True, slots=True)
class CapabilityToken:
    envelope_digest: str
    action: str
    target: str
    token_digest: str


def intersect_envelopes(parent: ConstraintEnvelope, child: ConstraintEnvelope) -> ConstraintEnvelope:
    """Reject a broadening child; intersection itself grants no capability."""

    if child.parent_envelope_digest != parent.digest_value or not child.is_no_broader_than(parent):
        raise AuthorityDenied("child envelope broadens or is not bound to its parent")
    return child


class AuthorityRegistry:
    """In-memory local registry; callers must present a validated capability token."""

    def __init__(self) -> None:
        self._envelopes: dict[str, ConstraintEnvelope] = {}
        self._revoked: set[str] = set()

    def register(self, envelope: ConstraintEnvelope, parent: ConstraintEnvelope | None = None) -> None:
        if parent is not None:
            intersect_envelopes(parent, envelope)
        elif envelope.parent_envelope_digest is not None:
            raise AuthorityDenied("parent envelope is required")
        self._envelopes[envelope.digest_value] = envelope

    def revoke(self, digest: str) -> None:
        self._revoked.add(digest)

    def authorize(self, digest: str, action: str, target: str, *, now: str) -> CapabilityToken:
        envelope = self._envelopes.get(digest)
        if envelope is None or digest in self._revoked:
            raise AuthorityDenied("authority envelope is unavailable")
        if datetime.fromisoformat(now.replace("Z", "+00:00")) >= datetime.fromisoformat(envelope.expires_at.replace("Z", "+00:00")):
            raise AuthorityDenied("authority envelope is expired")
        normalized = normalize_portable_path(target)
        if action not in envelope.allowed_actions or action in envelope.denied_actions:
            raise AuthorityDenied("action is not granted")
        if action == "write" and not any(
            normalized == path or normalized.startswith(path + "/")
            for path in envelope.path_write_scope
        ):
            raise AuthorityDenied("target is outside write scope")
        token_digest = canonical_digest({"envelope": digest, "action": action, "target": normalized})
        return CapabilityToken(digest, action, normalized, token_digest)
