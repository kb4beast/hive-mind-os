"""Host-owned bootstrap registry for executable Whole-OS services.

The service configuration is deliberately inert.  It may name versioned adapter
identities, but it cannot provide an import path, command, callback, credential,
or secret.  A trusted launcher registers already-constructed factories in this
process; this module then binds exactly one independently admitted factory to the
sealed mission descriptor.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .cortex.repository.mission_bindings import ConfiguredMissionBindingsProvider
from .runtime_contracts import canonical_digest
from .whole_os_service import WholeOSHost, WholeOSServiceConfig

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class WholeOSBootstrapError(RuntimeError):
    """A host factory registration or resolution failed closed."""

    blocker = "blocked_authority"


class WholeOSHostUnavailable(WholeOSBootstrapError):
    """No independently admitted host provider matches the descriptor."""

    blocker = "blocked_capability"


@dataclass(frozen=True, slots=True)
class WholeOSHostBootstrap:
    """The two executable boundaries required by :class:`WholeOSService`."""

    bindings: ConfiguredMissionBindingsProvider
    host: WholeOSHost

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, ConfiguredMissionBindingsProvider):
            raise WholeOSBootstrapError(
                "host factory returned an invalid mission bindings provider"
            )
        if not callable(getattr(self.host, "execute_package", None)):
            raise WholeOSBootstrapError(
                "host factory returned no executable package boundary"
            )
        if not callable(getattr(self.host, "assess_terminal_candidate", None)):
            raise WholeOSBootstrapError(
                "host factory returned no independent terminal assessor"
            )


WholeOSHostFactory = Callable[[WholeOSServiceConfig], WholeOSHostBootstrap]


@dataclass(frozen=True, slots=True)
class WholeOSHostFactoryRegistration:
    """Sealed, non-secret identity of one host-owned executable factory."""

    provider_id: str
    provider_version: str
    configuration_digest: str
    implementation_digest: str
    authority_ref: str
    evidence_refs: tuple[str, ...]
    independently_validated: bool

    def __post_init__(self) -> None:
        for value, label in (
            (self.provider_id, "provider_id"),
            (self.provider_version, "provider_version"),
            (self.authority_ref, "authority_ref"),
        ):
            if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
                raise WholeOSBootstrapError(f"{label} must be a canonical identifier")
        for value, label in (
            (self.configuration_digest, "configuration_digest"),
            (self.implementation_digest, "implementation_digest"),
        ):
            if type(value) is not str or _DIGEST.fullmatch(value) is None:
                raise WholeOSBootstrapError(
                    f"{label} must be a lowercase sha256 digest"
                )
        if (
            type(self.evidence_refs) is not tuple
            or not self.evidence_refs
            or self.evidence_refs != tuple(sorted(set(self.evidence_refs)))
            or any(
                type(item) is not str or not item.strip() or item != item.strip()
                for item in self.evidence_refs
            )
        ):
            raise WholeOSBootstrapError(
                "factory evidence_refs must be a sorted nonempty tuple"
            )
        if self.independently_validated is not True:
            raise WholeOSBootstrapError(
                "executable host factory requires independent validation"
            )

    def to_document(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "configuration_digest": self.configuration_digest,
            "implementation_digest": self.implementation_digest,
            "authority_ref": self.authority_ref,
            "evidence_refs": list(self.evidence_refs),
            "independently_validated": self.independently_validated,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())


class WholeOSHostFactoryRegistry:
    """Process-local custody for factories registered by a trusted launcher."""

    def __init__(self) -> None:
        self._entries: dict[
            str, tuple[WholeOSHostFactoryRegistration, WholeOSHostFactory]
        ] = {}
        self._lock = RLock()

    @property
    def registrations(self) -> Mapping[str, WholeOSHostFactoryRegistration]:
        with self._lock:
            return MappingProxyType(
                {key: value[0] for key, value in self._entries.items()}
            )

    def register(
        self,
        registration: WholeOSHostFactoryRegistration,
        factory: WholeOSHostFactory,
    ) -> WholeOSHostFactoryRegistration:
        if not isinstance(registration, WholeOSHostFactoryRegistration):
            raise WholeOSBootstrapError("factory registration must be exact typed data")
        if not callable(factory):
            raise WholeOSBootstrapError("host factory must be callable")
        with self._lock:
            prior = self._entries.get(registration.provider_id)
            if prior is not None:
                if prior[0].digest != registration.digest or prior[1] is not factory:
                    raise WholeOSBootstrapError(
                        "host provider id is already bound to another factory"
                    )
                return prior[0]
            self._entries[registration.provider_id] = (registration, factory)
        return registration

    def resolve(self, config: WholeOSServiceConfig) -> WholeOSHostBootstrap:
        if not isinstance(config, WholeOSServiceConfig):
            raise WholeOSBootstrapError("host resolution requires typed service config")
        descriptor = config.binding_descriptor
        admitted_versions = set(descriptor.adapter_versions)
        with self._lock:
            candidates = tuple(
                entry
                for entry in self._entries.values()
                if (
                    entry[0].provider_id,
                    entry[0].provider_version,
                )
                in admitted_versions
                and entry[0].configuration_digest
                == descriptor.configuration_digest
                and entry[0].authority_ref == descriptor.authority_ref
            )
        if not candidates:
            raise WholeOSHostUnavailable(
                "no independently admitted host factory matches the sealed descriptor"
            )
        if len(candidates) != 1:
            raise WholeOSBootstrapError(
                "sealed descriptor ambiguously admits multiple host factories"
            )
        registration, factory = candidates[0]
        bootstrap = factory(config)
        if not isinstance(bootstrap, WholeOSHostBootstrap):
            raise WholeOSBootstrapError(
                f"host factory {registration.provider_id} returned an invalid bootstrap"
            )
        if bootstrap.bindings.descriptor.digest != descriptor.digest:
            raise WholeOSBootstrapError(
                "host factory bindings differ from the sealed descriptor"
            )
        return bootstrap


DEFAULT_WHOLE_OS_HOST_FACTORIES = WholeOSHostFactoryRegistry()


def register_whole_os_host_factory(
    registration: WholeOSHostFactoryRegistration,
    factory: WholeOSHostFactory,
) -> WholeOSHostFactoryRegistration:
    """Register a factory from trusted launcher code before invoking the CLI."""

    return DEFAULT_WHOLE_OS_HOST_FACTORIES.register(registration, factory)


def run_registered_whole_os(
    argv: Sequence[str],
    *,
    registration: WholeOSHostFactoryRegistration,
    factory: WholeOSHostFactory,
) -> int:
    """Run the public Whole-OS CLI with one launcher-owned factory.

    A deployment may expose this function as its own console script.  Registration
    and CLI execution occur in the same process, so a standalone stock shell never
    infers executable adapters or credentials from the inert service document.
    ``argv`` contains the arguments after ``hive-mind whole-os``.
    """

    from .cli import _run_whole_os, build_whole_os_parser

    registry = WholeOSHostFactoryRegistry()
    registry.register(registration, factory)
    args = build_whole_os_parser().parse_args(tuple(argv))
    return _run_whole_os(args, host_factories=registry)


__all__ = [
    "DEFAULT_WHOLE_OS_HOST_FACTORIES",
    "WholeOSBootstrapError",
    "WholeOSHostBootstrap",
    "WholeOSHostFactory",
    "WholeOSHostFactoryRegistration",
    "WholeOSHostFactoryRegistry",
    "WholeOSHostUnavailable",
    "register_whole_os_host_factory",
    "run_registered_whole_os",
]
