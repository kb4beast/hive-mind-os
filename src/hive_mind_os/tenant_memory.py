"""Subject-bound memory and artifact namespace (N19)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .brain_kernel.canonical import canonical_digest
from .durable_contracts import ContractStore


class BoundaryError(ValueError):
    pass


class BoundaryState(StrEnum):
    BOUND = "BOUND"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class SubjectMemoryBoundary:
    tenant_id: str
    repository_id: str
    private_store_id: str
    cache_partition_id: str
    logging_partition_id: str
    provider_policy_digest: str
    encryption_profile_id: str
    retention_policy_digest: str
    state: BoundaryState = BoundaryState.BOUND

    def __post_init__(self):
        if any(
            type(x) is not str or not x.strip()
            for x in (
                self.tenant_id,
                self.repository_id,
                self.private_store_id,
                self.cache_partition_id,
                self.logging_partition_id,
            )
        ):
            raise BoundaryError("subject identity fields are required")

    @property
    def digest(self):
        return canonical_digest(self)

    def to_dict(self):
        from .brain_kernel.canonical import canonical_document

        return canonical_document(self)

    @classmethod
    def from_dict(cls, value):
        required = {
            "tenant_id",
            "repository_id",
            "private_store_id",
            "cache_partition_id",
            "logging_partition_id",
            "provider_policy_digest",
            "encryption_profile_id",
            "retention_policy_digest",
            "state",
        }
        if set(value) != required:
            raise BoundaryError("closed boundary schema")
        return cls(**{**value, "state": BoundaryState(value["state"])})


@dataclass(frozen=True, slots=True)
class ScopedMemoryHandle:
    boundary_digest: str
    role: str
    mission_id: str
    permitted_scopes: tuple[str, ...]
    state: BoundaryState = BoundaryState.ACTIVE

    def assert_usable(self, boundary: SubjectMemoryBoundary):
        if (
            self.boundary_digest != boundary.digest
            or self.state is not BoundaryState.ACTIVE
            or boundary.state is not BoundaryState.ACTIVE
        ):
            raise BoundaryError("memory handle is not valid for this subject")


class SubjectNamespace:
    def __init__(self, path=None):
        self._data: dict[tuple[str, str, str], Any] = {}
        self._states: dict[str, BoundaryState] = {}
        self._boundaries = (
            ContractStore(path, SubjectMemoryBoundary.from_dict) if path else None
        )

    def key(self, boundary, name):
        return (boundary.tenant_id, boundary.repository_id, name)

    def put(self, boundary: SubjectMemoryBoundary, name: str, value: Any):
        effective_state = self._states.get(boundary.digest, boundary.state)
        if effective_state not in (BoundaryState.BOUND, BoundaryState.ACTIVE):
            raise BoundaryError("boundary is inactive")
        if (
            type(name) is not str
            or not name
            or name.startswith("/")
            or ".." in name.split("/")
        ):
            raise BoundaryError("invalid namespace key")
        self._data[self.key(boundary, name)] = value
        if self._boundaries:
            self._boundaries.put(boundary.digest, boundary)

    def get(
        self, handle: ScopedMemoryHandle, boundary: SubjectMemoryBoundary, name: str
    ):
        handle.assert_usable(boundary)
        if self._states.get(boundary.digest, boundary.state) in {
            BoundaryState.REVOKED,
            BoundaryState.QUARANTINED,
        }:
            raise BoundaryError("memory boundary has been revoked or quarantined")
        return self._data.get(self.key(boundary, name))

    def revoke(self, boundary):
        self._states[boundary.digest] = BoundaryState.REVOKED

    def migrate_legacy(self, name):
        raise BoundaryError("LEGACY_UNBOUND data requires trusted import")
