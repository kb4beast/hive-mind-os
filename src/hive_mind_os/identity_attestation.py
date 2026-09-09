"""Replaceable principal attestation and role-separation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Mapping, Protocol, Sequence

from .runtime_contracts import require_digest, require_identifier, require_time


class IdentityError(ValueError):
    pass


class TrustProfile(StrEnum):
    LOCAL_SINGLE_OPERATOR = "local-single-operator"
    INDEPENDENT_PRINCIPALS = "independent-principals"


@dataclass(frozen=True, slots=True)
class PrincipalAttestation:
    principal_id: str
    administrator_id: str
    trust_domain: str
    credential_digest: str
    roles: tuple[str, ...]
    expires_at: str
    attestation_digest: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.principal_id, "principal_id"),
            (self.administrator_id, "administrator_id"),
            (self.trust_domain, "trust_domain"),
        ):
            require_identifier(value, label)
        require_digest(self.credential_digest, "credential_digest")
        require_digest(self.attestation_digest, "attestation_digest")
        require_time(self.expires_at, "attestation expiry")
        if not self.roles or any(not isinstance(role, str) or not role for role in self.roles):
            raise IdentityError("attestation roles are required")


class AttestationVerifier(Protocol):
    profile: TrustProfile

    def verify(self, attestation: PrincipalAttestation) -> bool: ...


class LocalAssertionVerifier:
    """Explicitly non-independent profile for one operator-owned host."""

    profile = TrustProfile.LOCAL_SINGLE_OPERATOR

    def verify(self, attestation: PrincipalAttestation) -> bool:
        return require_time(attestation.expires_at, "attestation expiry") > datetime.now(UTC)


class PinnedAttestationVerifier:
    """Verify attestations against independently supplied pinned digests."""

    profile = TrustProfile.INDEPENDENT_PRINCIPALS

    def __init__(self, pinned_attestations: Mapping[str, str]) -> None:
        self._pins = dict(pinned_attestations)
        if not self._pins:
            raise IdentityError("independent profile requires pinned attestations")
        for principal, digest in self._pins.items():
            require_identifier(principal, "pinned principal")
            require_digest(digest, "pinned attestation digest")

    def verify(self, attestation: PrincipalAttestation) -> bool:
        return (
            self._pins.get(attestation.principal_id) == attestation.attestation_digest
            and require_time(attestation.expires_at, "attestation expiry") > datetime.now(UTC)
        )


def verify_role_assignments(
    assignments: Mapping[str, PrincipalAttestation], *, verifier: AttestationVerifier,
    independently_administered: Sequence[tuple[str, ...]] = (),
) -> dict[str, str]:
    """Return verified role→principal bindings or fail closed.

    In the independent profile, changing actor-id strings is insufficient: each
    role needs a pinned attestation and every requested separation group needs
    distinct principal, credential, administrator, and trust-domain identities.
    """

    if not assignments:
        raise IdentityError("at least one role assignment is required")
    for role, attestation in assignments.items():
        require_identifier(role, "role")
        if role not in attestation.roles or not verifier.verify(attestation):
            raise IdentityError(f"role {role} lacks a valid principal attestation")
    if verifier.profile is TrustProfile.INDEPENDENT_PRINCIPALS:
        for group in independently_administered:
            try:
                values = [assignments[role] for role in group]
            except KeyError as error:
                raise IdentityError(f"missing independently required role: {error.args[0]}") from error
            for attribute in ("principal_id", "credential_digest", "administrator_id", "trust_domain"):
                observed = [getattr(item, attribute) for item in values]
                if len(set(observed)) != len(observed):
                    raise IdentityError(
                        f"independent roles {group} share {attribute}; actor labels are not principals"
                    )
    return {role: attestation.principal_id for role, attestation in assignments.items()}


__all__ = [
    "AttestationVerifier", "IdentityError", "LocalAssertionVerifier",
    "PinnedAttestationVerifier", "PrincipalAttestation", "TrustProfile",
    "verify_role_assignments",
]
