"""Subject-neutral, effect-free adapter contracts.

A subject is the thing a plan is about.  Repositories are one subject kind,
not a privileged assumption.  The contracts here describe immutable snapshots
and adapter capabilities; they do not open files, call networks, or execute an
adapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .runtime_contracts import canonical_digest as contract_digest

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_UTC_INSTANT = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)


class SubjectAdapterError(ValueError):
    """A subject or adapter contract is incomplete or ambiguous."""


class SubjectKind(StrEnum):
    REPOSITORY = "repository"
    ARTIFACT = "artifact"
    SOURCE = "source"
    DATASET = "dataset"
    API = "api"
    TICKET = "ticket"
    DATABASE = "database"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


def _required_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise SubjectAdapterError(f"{label} must be a trimmed non-empty string")
    if "\x00" in value:
        raise SubjectAdapterError(f"{label} must not contain NUL")


def _required_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise SubjectAdapterError(f"{label} must be a lowercase sha256 digest")


def _required_utc_instant(value: str, label: str) -> None:
    if type(value) is not str or _UTC_INSTANT.fullmatch(value) is None:
        raise SubjectAdapterError(f"{label} must be a canonical UTC RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise SubjectAdapterError(
            f"{label} must be a canonical UTC RFC 3339 timestamp"
        ) from error
    if parsed.utcoffset() != timedelta(0):
        raise SubjectAdapterError(f"{label} must be UTC")


def _string_set(values: tuple[str, ...], label: str) -> None:
    if type(values) is not tuple:
        raise SubjectAdapterError(f"{label} must be an immutable tuple")
    if values != tuple(sorted(set(values))):
        raise SubjectAdapterError(f"{label} must be sorted and unique")
    if any(
        not isinstance(item, str) or _CAPABILITY.fullmatch(item) is None
        for item in values
    ):
        raise SubjectAdapterError(f"{label} contains an invalid capability")


@dataclass(frozen=True, slots=True)
class SubjectDescriptor:
    """Stable identity and declared needs for any supported subject."""

    subject_id: str
    kind: SubjectKind
    locator: str
    required_capabilities: tuple[str, ...]
    authority_digest: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _required_text(self.subject_id, "subject_id")
        if not isinstance(self.kind, SubjectKind):
            try:
                object.__setattr__(self, "kind", SubjectKind(self.kind))
            except (TypeError, ValueError) as error:
                raise SubjectAdapterError("subject kind is unknown") from error
        _required_text(self.locator, "subject locator")
        _string_set(self.required_capabilities, "required_capabilities")
        _required_digest(self.authority_digest, "authority_digest")
        if type(self.provenance_refs) is not tuple or not self.provenance_refs or any(
            type(item) is not str or not item.strip() or item != item.strip()
            for item in self.provenance_refs
        ):
            raise SubjectAdapterError(
                "subject provenance_refs must be an immutable tuple of trimmed strings"
            )
        if len(set(self.provenance_refs)) != len(self.provenance_refs):
            raise SubjectAdapterError("subject provenance_refs must be unique")

    @property
    def identity_digest(self) -> str:
        return contract_digest(
            {
                "subject_id": self.subject_id,
                "kind": self.kind.value,
                "locator": self.locator,
                "required_capabilities": self.required_capabilities,
                "authority_digest": self.authority_digest,
                "provenance_refs": self.provenance_refs,
            }
        )


@dataclass(frozen=True, slots=True)
class SubjectSnapshot:
    """An immutable point-in-time subject observation."""

    subject: SubjectDescriptor
    snapshot_id: str
    content_digest: str
    observed_at: str
    evidence_refs: tuple[str, ...]
    immutable: bool = True

    def __post_init__(self) -> None:
        _required_text(self.snapshot_id, "snapshot_id")
        _required_digest(self.content_digest, "content_digest")
        _required_utc_instant(self.observed_at, "observed_at")
        if type(self.evidence_refs) is not tuple or not self.evidence_refs or any(
            type(item) is not str or not item.strip() or item != item.strip()
            for item in self.evidence_refs
        ):
            raise SubjectAdapterError(
                "snapshot evidence_refs must be an immutable tuple of trimmed strings"
            )
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise SubjectAdapterError("snapshot evidence_refs must be unique")
        if self.immutable is not True:
            raise SubjectAdapterError(
                "mutable subject state cannot be used as a snapshot"
            )

    @property
    def snapshot_digest(self) -> str:
        return contract_digest(
            {
                "subject_identity_digest": self.subject.identity_digest,
                "snapshot_id": self.snapshot_id,
                "content_digest": self.content_digest,
                "observed_at": self.observed_at,
                "evidence_refs": self.evidence_refs,
                "immutable": self.immutable,
            }
        )


@runtime_checkable
class SubjectAdapter(Protocol):
    """The inert shape an implementation must satisfy before registration."""

    adapter_id: str
    supported_kinds: tuple[SubjectKind, ...]
    capabilities: tuple[str, ...]
    required_authorities: tuple[str, ...]

    def snapshot(self, subject: SubjectDescriptor) -> SubjectSnapshot:
        """Return an exact observation without performing an external effect."""

        ...


def require_snapshot_binding(
    subject: SubjectDescriptor, snapshot: SubjectSnapshot
) -> SubjectSnapshot:
    """Fail closed when an adapter substitutes a different subject."""

    if snapshot.subject.identity_digest != subject.identity_digest:
        raise SubjectAdapterError("snapshot is not bound to the requested subject")
    return snapshot


# Short aliases keep public call sites readable without creating a second type.
Subject = SubjectDescriptor
Snapshot = SubjectSnapshot
