"""The sole deterministic registry for subject and resource adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .subject_adapter import SubjectAdapterError, SubjectKind, contract_digest

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_NAME = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")


class AdapterRegistryError(SubjectAdapterError):
    """Adapter registration or deterministic selection failed closed."""


def _names(values: tuple[str, ...], label: str, *, required: bool = False) -> None:
    if type(values) is not tuple:
        raise AdapterRegistryError(f"{label} must be an immutable tuple")
    if required and not values:
        raise AdapterRegistryError(f"{label} must not be empty")
    if values != tuple(sorted(set(values))):
        raise AdapterRegistryError(f"{label} must be sorted and unique")
    if any(
        not isinstance(item, str) or _NAME.fullmatch(item) is None for item in values
    ):
        raise AdapterRegistryError(f"{label} contains an invalid name")


def _refs(values: tuple[str, ...], label: str) -> None:
    if type(values) is not tuple:
        raise AdapterRegistryError(f"{label} must be an immutable tuple")
    if not values or any(
        type(item) is not str or not item.strip() or item != item.strip()
        for item in values
    ):
        raise AdapterRegistryError(f"{label} must contain canonical non-empty refs")
    if values != tuple(sorted(set(values))):
        raise AdapterRegistryError(f"{label} must be sorted and unique")


@dataclass(frozen=True, slots=True)
class AdapterRegistration:
    adapter_id: str
    subject_kinds: tuple[SubjectKind, ...]
    capabilities: tuple[str, ...]
    required_authorities: tuple[str, ...]
    implementation_digest: str
    provenance_refs: tuple[str, ...]
    privilege_rank: int = 0
    vendor: str | None = None
    independently_validated: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.adapter_id, str)
            or _NAME.fullmatch(self.adapter_id) is None
        ):
            raise AdapterRegistryError("adapter_id must be a canonical name")
        if not self.subject_kinds:
            raise AdapterRegistryError("adapter must support at least one subject kind")
        try:
            normalized = tuple(SubjectKind(item) for item in self.subject_kinds)
        except (TypeError, ValueError) as error:
            raise AdapterRegistryError(
                "adapter supports an unknown subject kind"
            ) from error
        if normalized != tuple(sorted(set(normalized), key=lambda item: item.value)):
            raise AdapterRegistryError("subject_kinds must be sorted and unique")
        object.__setattr__(self, "subject_kinds", normalized)
        _names(self.capabilities, "adapter capabilities", required=True)
        _names(self.required_authorities, "required_authorities")
        if (
            not isinstance(self.implementation_digest, str)
            or _DIGEST.fullmatch(self.implementation_digest) is None
        ):
            raise AdapterRegistryError(
                "implementation_digest must be a lowercase sha256 digest"
            )
        _refs(self.provenance_refs, "adapter provenance_refs")
        if (
            not isinstance(self.privilege_rank, int)
            or isinstance(self.privilege_rank, bool)
            or self.privilege_rank < 0
        ):
            raise AdapterRegistryError("privilege_rank must be a non-negative integer")
        if self.vendor is not None and (
            not isinstance(self.vendor, str) or not self.vendor.strip()
        ):
            raise AdapterRegistryError("vendor must be absent or non-empty")
        if type(self.independently_validated) is not bool:
            raise AdapterRegistryError(
                "independently_validated must be a strict boolean"
            )

    @property
    def registration_digest(self) -> str:
        return contract_digest(
            {
                "adapter_id": self.adapter_id,
                "subject_kinds": tuple(item.value for item in self.subject_kinds),
                "capabilities": self.capabilities,
                "required_authorities": self.required_authorities,
                "implementation_digest": self.implementation_digest,
                "provenance_refs": self.provenance_refs,
                "privilege_rank": self.privilege_rank,
                "vendor": self.vendor,
                "independently_validated": self.independently_validated,
            }
        )


@dataclass(frozen=True, slots=True)
class CapabilityAuthority:
    allowed: tuple[str, ...]
    denied: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _names(self.allowed, "allowed capabilities")
        _names(self.denied, "denied capabilities")
        overlap = set(self.allowed) & set(self.denied)
        if overlap:
            raise AdapterRegistryError(
                "capability authority conflicts for " + ", ".join(sorted(overlap))
            )
        _refs(self.evidence_refs, "authority evidence_refs")

    def to_document(self) -> dict[str, tuple[str, ...]]:
        return {
            "allowed": self.allowed,
            "denied": self.denied,
            "evidence_refs": self.evidence_refs,
        }

    @property
    def authority_digest(self) -> str:
        """Canonical identity of every material grant field."""

        return contract_digest(self.to_document())


@dataclass(frozen=True, slots=True)
class AdapterSelection:
    registration: AdapterRegistration
    subject_kind: SubjectKind
    required_capabilities: tuple[str, ...]
    authority: CapabilityAuthority
    request_evidence_refs: tuple[str, ...]
    registry_digest: str

    def __post_init__(self) -> None:
        if type(self.registration) is not AdapterRegistration:
            raise AdapterRegistryError(
                "selection registration must be exact typed data"
            )
        if not isinstance(self.subject_kind, SubjectKind):
            raise AdapterRegistryError("selection subject kind is unknown")
        _names(self.required_capabilities, "required capabilities", required=True)
        if type(self.authority) is not CapabilityAuthority:
            raise AdapterRegistryError("selection authority must be exact typed data")
        _refs(self.request_evidence_refs, "adapter selection evidence_refs")
        if (
            type(self.registry_digest) is not str
            or _DIGEST.fullmatch(self.registry_digest) is None
        ):
            raise AdapterRegistryError(
                "selection registry_digest must be a lowercase sha256 digest"
            )
        requested = set(self.required_capabilities)
        allowed = set(self.authority.allowed)
        denied = set(self.authority.denied)
        if (
            self.subject_kind not in self.registration.subject_kinds
            or not requested.issubset(self.registration.capabilities)
            or not requested.issubset(allowed)
            or bool(requested & denied)
            or not set(self.registration.required_authorities).issubset(allowed)
            or bool(set(self.registration.required_authorities) & denied)
        ):
            raise AdapterRegistryError(
                "selection receipt contradicts its registration or authority"
            )

    @property
    def selection_digest(self) -> str:
        return contract_digest(
            {
                "registration_digest": self.registration.registration_digest,
                "subject_kind": self.subject_kind.value,
                "required_capabilities": self.required_capabilities,
                "authority": self.authority.to_document(),
                "request_evidence_refs": self.request_evidence_refs,
                "registry_digest": self.registry_digest,
            }
        )

    @property
    def authority_digest(self) -> str:
        return self.authority.authority_digest


class AdapterRegistry:
    """Append-only-in-process registration and evidence-bound selection.

    Registrations are data only: storing one here cannot invoke its implementation
    or grant an external effect.  A repeated byte-equivalent registration is
    idempotent; substitution under an existing id is rejected.
    """

    def __init__(self) -> None:
        self._registrations: dict[str, AdapterRegistration] = {}

    @property
    def registrations(self) -> Mapping[str, AdapterRegistration]:
        return MappingProxyType(dict(self._registrations))

    @property
    def registry_digest(self) -> str:
        return contract_digest(
            {
                adapter_id: registration.registration_digest
                for adapter_id, registration in sorted(self._registrations.items())
            }
        )

    def register(self, registration: AdapterRegistration) -> AdapterRegistration:
        if registration.vendor is not None and not registration.independently_validated:
            raise AdapterRegistryError(
                "third-party adapter is inert until independently validated"
            )
        prior = self._registrations.get(registration.adapter_id)
        if prior is not None:
            if prior.registration_digest != registration.registration_digest:
                raise AdapterRegistryError(
                    "adapter id is already bound to different bytes"
                )
            return prior
        self._registrations[registration.adapter_id] = registration
        return registration

    def select(
        self,
        subject_kind: SubjectKind,
        required_capabilities: tuple[str, ...],
        authority: CapabilityAuthority,
        *,
        evidence_refs: tuple[str, ...],
    ) -> AdapterSelection:
        try:
            kind = SubjectKind(subject_kind)
        except (TypeError, ValueError) as error:
            raise AdapterRegistryError("selection subject kind is unknown") from error
        _names(required_capabilities, "required capabilities", required=True)
        _refs(evidence_refs, "adapter selection evidence_refs")
        requested = set(required_capabilities)
        allowed = set(authority.allowed)
        denied = set(authority.denied)
        unauthorized = requested - allowed
        if unauthorized or requested & denied:
            names = sorted(unauthorized | (requested & denied))
            raise AdapterRegistryError(
                "capability authority is missing or denied for " + ", ".join(names)
            )
        candidates = [
            registration
            for registration in self._registrations.values()
            if kind in registration.subject_kinds
            and requested.issubset(registration.capabilities)
            and set(registration.required_authorities).issubset(allowed)
            and not (set(registration.required_authorities) & denied)
        ]
        if not candidates:
            raise AdapterRegistryError(
                "no registered adapter has sufficient authorized capability"
            )
        candidates.sort(
            key=lambda item: (
                item.privilege_rank,
                len(set(item.capabilities) - requested),
                item.vendor is not None,
                item.adapter_id,
            )
        )
        return AdapterSelection(
            registration=candidates[0],
            subject_kind=kind,
            required_capabilities=required_capabilities,
            authority=authority,
            request_evidence_refs=evidence_refs,
            registry_digest=self.registry_digest,
        )

    resolve = select


AuthorityGrant = CapabilityAuthority
