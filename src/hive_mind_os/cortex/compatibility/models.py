"""Typed records shared by the legacy-runtime compatibility boundary.

The compatibility layer is deliberately an outer projection.  It can describe a
legacy operation and its evidence, but it cannot mint authority or execute an
effect on behalf of the canonical kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from ...brain_kernel.canonical import canonical_digest, canonical_document


class CompatibilityError(RuntimeError):
    """A compatibility request cannot be handled without weakening a gate."""


class AuthorityPath(StrEnum):
    LEGACY = "legacy"
    CANONICAL = "canonical"
    SHADOW = "shadow"


class AdapterMode(StrEnum):
    LEGACY = "legacy"
    SHADOW = "shadow"
    CANONICAL = "canonical"


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is required")
    return value.strip()


def _digest(value: str, label: str) -> str:
    value = _required(value, label)
    if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
        raise ValueError(f"{label} must be a sha256 digest")
    return value


@dataclass(frozen=True, slots=True)
class CompatibilityRequest:
    """A non-authoritative description of one legacy entry-point invocation."""

    entry_point: str
    operation: str
    mission_id: str
    authority_path: AuthorityPath
    payload_digest: str
    rollback_ref: str

    def __post_init__(self) -> None:
        _required(self.entry_point, "entry_point")
        _required(self.operation, "operation")
        _required(self.mission_id, "mission_id")
        _digest(self.payload_digest, "payload_digest")
        _required(self.rollback_ref, "rollback_ref")
        if not isinstance(self.authority_path, AuthorityPath):
            object.__setattr__(self, "authority_path", AuthorityPath(self.authority_path))

    @classmethod
    def from_payload(
        cls,
        entry_point: str,
        operation: str,
        mission_id: str,
        payload: Mapping[str, Any] | None = None,
        *,
        authority_path: AuthorityPath = AuthorityPath.LEGACY,
        rollback_ref: str = "route:legacy",
    ) -> "CompatibilityRequest":
        return cls(
            entry_point,
            operation,
            mission_id,
            authority_path,
            canonical_digest(dict(payload or {})),
            rollback_ref,
        )

    def to_dict(self) -> dict[str, Any]:
        return canonical_document(self)


@dataclass(frozen=True, slots=True)
class CompatibilityObservation:
    """Normalized behavior/evidence returned by one authority path."""

    entry_point: str
    operation: str
    authority_path: AuthorityPath
    status: str
    behavior: Mapping[str, Any]
    evidence: Mapping[str, Any]
    effect_count: int = 0

    def __post_init__(self) -> None:
        _required(self.entry_point, "entry_point")
        _required(self.operation, "operation")
        _required(self.status, "status")
        if not isinstance(self.authority_path, AuthorityPath):
            object.__setattr__(self, "authority_path", AuthorityPath(self.authority_path))
        if self.effect_count < 0:
            raise ValueError("effect_count cannot be negative")
        canonical_digest(dict(self.behavior))
        canonical_digest(dict(self.evidence))

    @property
    def behavior_digest(self) -> str:
        return canonical_digest(dict(self.behavior))

    @property
    def evidence_digest(self) -> str:
        return canonical_digest(dict(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return canonical_document(
            {
                "entry_point": self.entry_point,
                "operation": self.operation,
                "authority_path": self.authority_path,
                "status": self.status,
                "behavior": dict(self.behavior),
                "evidence": dict(self.evidence),
                "effect_count": self.effect_count,
                "behavior_digest": self.behavior_digest,
                "evidence_digest": self.evidence_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class RetirementBlocker:
    """A typed reason a legacy path must remain available."""

    entry_point: str
    reason: str
    required_evidence: tuple[str, ...]
    rollback_ref: str

    def __post_init__(self) -> None:
        _required(self.entry_point, "entry_point")
        _required(self.reason, "reason")
        if not self.required_evidence:
            raise ValueError("required_evidence is required")
        _required(self.rollback_ref, "rollback_ref")

    def to_dict(self) -> dict[str, Any]:
        return canonical_document(self)


@dataclass(frozen=True, slots=True)
class AdapterDescriptor:
    """Stable registry metadata for one compatibility adapter."""

    entry_point: str
    legacy_type: str
    canonical_destination: str
    authority_path: AuthorityPath
    retirement_blocker: RetirementBlocker

    def to_dict(self) -> dict[str, Any]:
        return canonical_document(self)
