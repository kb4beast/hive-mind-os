"""Conservative resource metadata adapters for subject snapshots.

Resource observations retain identities, digests, sizes, media types, and
provenance.  They intentionally never retain source bodies or credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from .subject_adapter import contract_digest

_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_INSTANT = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)
_SECRET_PATTERNS = (
    re.compile(rb"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
DEFAULT_MAX_RESOURCE_BYTES = 8 * 1024 * 1024


class ResourceAdapterError(ValueError):
    """A resource cannot be safely observed or represented."""


class ResourceKind(StrEnum):
    REPOSITORY_PATH = "repository_path"
    ARTIFACT = "artifact"
    SOURCE = "source"
    DATASET = "dataset"
    API = "api"
    TICKET = "ticket"
    DATABASE = "database"
    WORKFLOW = "workflow"
    CUSTOM = "custom"


def _text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ResourceAdapterError(f"{label} must be a trimmed non-empty string")
    if "\x00" in value:
        raise ResourceAdapterError(f"{label} must not contain NUL")


def _digest(value: str, label: str) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ResourceAdapterError(f"{label} must be a lowercase sha256 digest")


def _utc_instant(value: str, label: str) -> None:
    if type(value) is not str or _UTC_INSTANT.fullmatch(value) is None:
        raise ResourceAdapterError(f"{label} must be a canonical UTC RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ResourceAdapterError(
            f"{label} must be a canonical UTC RFC 3339 timestamp"
        ) from error
    if parsed.utcoffset() != timedelta(0):
        raise ResourceAdapterError(f"{label} must be UTC")


def _validate_locator(locator: str) -> None:
    _text(locator, "resource locator")
    parsed = urlsplit(locator)
    if parsed.query or parsed.fragment:
        raise ResourceAdapterError(
            "resource locators must not contain queries or fragments"
        )
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.hostname:
            raise ResourceAdapterError("network resource locators must use HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ResourceAdapterError("resource locators must not contain credentials")
        return
    normalized = locator.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ResourceAdapterError("relative resource locators must stay within the subject")


@dataclass(frozen=True, slots=True)
class ResourceDescriptor:
    subject_id: str
    resource_id: str
    kind: ResourceKind
    locator: str
    media_type: str
    mutable: bool
    version: str | None
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.subject_id, "subject_id")
        _text(self.resource_id, "resource_id")
        if not isinstance(self.kind, ResourceKind):
            try:
                object.__setattr__(self, "kind", ResourceKind(self.kind))
            except (TypeError, ValueError) as error:
                raise ResourceAdapterError("resource kind is unknown") from error
        _validate_locator(self.locator)
        _text(self.media_type, "media_type")
        if type(self.mutable) is not bool:
            raise ResourceAdapterError("mutable must be a strict boolean")
        if self.mutable and (not isinstance(self.version, str) or not self.version.strip()):
            raise ResourceAdapterError("mutable resources require an exact version")
        if self.version is not None:
            _text(self.version, "resource version")
        if type(self.provenance_refs) is not tuple or not self.provenance_refs or any(
            type(item) is not str or not item.strip() or item != item.strip()
            for item in self.provenance_refs
        ):
            raise ResourceAdapterError(
                "resource provenance_refs must be an immutable tuple of trimmed strings"
            )
        if len(set(self.provenance_refs)) != len(self.provenance_refs):
            raise ResourceAdapterError("resource provenance_refs must be unique")

    @property
    def identity_digest(self) -> str:
        return contract_digest(
            {
                "subject_id": self.subject_id,
                "resource_id": self.resource_id,
                "kind": self.kind.value,
                "locator": self.locator,
                "media_type": self.media_type,
                "mutable": self.mutable,
                "version": self.version,
                "provenance_refs": self.provenance_refs,
            }
        )


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Content-addressed metadata; raw content is deliberately absent."""

    resource: ResourceDescriptor
    content_digest: str
    byte_length: int
    observed_at: str
    evidence_refs: tuple[str, ...]
    binary: bool = False

    def __post_init__(self) -> None:
        _digest(self.content_digest, "content_digest")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise ResourceAdapterError("byte_length must be a non-negative integer")
        _utc_instant(self.observed_at, "observed_at")
        if type(self.evidence_refs) is not tuple or not self.evidence_refs or any(
            type(item) is not str or not item.strip() or item != item.strip()
            for item in self.evidence_refs
        ):
            raise ResourceAdapterError(
                "resource snapshot evidence_refs must be an immutable tuple of trimmed strings"
            )
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ResourceAdapterError("resource snapshot evidence_refs must be unique")
        if type(self.binary) is not bool:
            raise ResourceAdapterError("binary must be a strict boolean")

    @property
    def snapshot_digest(self) -> str:
        return contract_digest(
            {
                "resource_identity_digest": self.resource.identity_digest,
                "content_digest": self.content_digest,
                "byte_length": self.byte_length,
                "observed_at": self.observed_at,
                "evidence_refs": self.evidence_refs,
                "binary": self.binary,
            }
        )


class ConservativeResourceAdapter:
    """Build a digest-only observation after bounded safety checks."""

    adapter_id = "builtin.conservative-resource.v1"

    def __init__(self, *, max_bytes: int = DEFAULT_MAX_RESOURCE_BYTES) -> None:
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
            raise ResourceAdapterError("max_bytes must be a positive integer")
        self.max_bytes = max_bytes

    def observe(
        self,
        resource: ResourceDescriptor,
        body: bytes,
        *,
        observed_at: str,
        evidence_refs: tuple[str, ...],
    ) -> ResourceSnapshot:
        if not isinstance(body, bytes):
            raise ResourceAdapterError("resource observation body must be bytes")
        if len(body) > self.max_bytes:
            raise ResourceAdapterError("resource exceeds the bounded observation limit")
        if any(pattern.search(body) for pattern in _SECRET_PATTERNS):
            raise ResourceAdapterError("secret-like content cannot be indexed")
        binary = b"\x00" in body
        if binary and len(body) > min(self.max_bytes, 1024 * 1024):
            raise ResourceAdapterError("oversized binary resource cannot be indexed")
        return ResourceSnapshot(
            resource=resource,
            content_digest=f"sha256:{sha256(body).hexdigest()}",
            byte_length=len(body),
            observed_at=observed_at,
            evidence_refs=evidence_refs,
            binary=binary,
        )


Resource = ResourceDescriptor
