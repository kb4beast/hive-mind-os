"""Evidence-bound, effect-free operational stewardship for the kernel.

The Steward receives observations from adapters rather than probing a live system
itself.  It refuses incomplete or corrupt evidence, then derives maintenance
proposals.  A proposal is intentionally not an instruction to execute a repair:
authority, effects, and verification remain separate boundaries.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping

from .canonical import canonical_digest
from .reconciler import RepairKind


class StewardIntegrityError(ValueError):
    """An operational observation is incomplete, corrupt, or unrecoverable."""


class HealthSurface(StrEnum):
    """The complete, fixed operational surface owned by Steward assessment."""

    QUEUES = "queues"
    LEASES = "leases"
    EVENT_CHAINS = "event_chains"
    SNAPSHOTS = "snapshots"
    WORKSPACES = "workspaces"
    RECEIPTS = "receipts"
    PROVIDERS = "providers"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"


class OperationalReadiness(StrEnum):
    READY = "ready"
    REPAIR_REQUIRED = "repair_required"
    QUARANTINED = "quarantined"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StewardIntegrityError(f"{label} is required")
    return value.strip()


def _sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 71 or not value.startswith("sha256:"):
        raise StewardIntegrityError(f"{label} must be a SHA-256 digest")
    try:
        int(value[7:], 16)
    except ValueError as error:
        raise StewardIntegrityError(f"{label} must be a SHA-256 digest") from error
    return value


class _FrozenEvidence(Mapping[str, object]):
    """A JSON-shaped mapping which cannot be mutated after validation."""

    __slots__ = ("_items",)

    def __init__(self, values: Mapping[str, object]) -> None:
        object.__setattr__(self, "_items", tuple((str(key), _freeze(value)) for key, value in values.items()))

    def __setattr__(self, _: str, __: object) -> None:
        raise AttributeError("health evidence is immutable")

    def __getitem__(self, key: str) -> object:
        for item_key, value in self._items:
            if item_key == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return _FrozenEvidence({str(key): item for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class HealthObservation:
    """One adapter-produced health observation with content-bound evidence."""

    surface: HealthSurface
    status: HealthStatus
    subject_id: str
    evidence: Mapping[str, object]
    evidence_digest: str
    recovery_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "surface", HealthSurface(self.surface))
        object.__setattr__(self, "status", HealthStatus(self.status))
        object.__setattr__(self, "subject_id", _text(self.subject_id, "observation subject"))
        if not isinstance(self.evidence, Mapping) or not self.evidence:
            raise StewardIntegrityError("observation evidence is required")
        evidence = _FrozenEvidence(self.evidence)
        object.__setattr__(self, "evidence", evidence)
        expected = canonical_digest(_thaw(evidence))
        if self.evidence_digest != expected:
            raise StewardIntegrityError("observation evidence digest does not match its content")
        object.__setattr__(self, "evidence_digest", _sha256(self.evidence_digest, "observation evidence digest"))
        if self.status is HealthStatus.HEALTHY:
            if self.recovery_ref is not None:
                object.__setattr__(self, "recovery_ref", _text(self.recovery_ref, "recovery reference"))
            return
        if self.recovery_ref is None:
            raise StewardIntegrityError("unhealthy observation requires a recovery reference")
        object.__setattr__(self, "recovery_ref", _text(self.recovery_ref, "recovery reference"))

    def to_document(self) -> dict[str, object]:
        return {
            "surface": self.surface.value,
            "status": self.status.value,
            "subject_id": self.subject_id,
            "evidence": _thaw(self.evidence),
            "evidence_digest": self.evidence_digest,
            "recovery_ref": self.recovery_ref,
        }


@dataclass(frozen=True, slots=True)
class MaintenanceProposal:
    """A finite recovery request; it neither acquires authority nor performs work."""

    repair_kind: RepairKind
    surface: HealthSurface
    subject_id: str
    reason: str
    recovery_ref: str
    rollback_ref: str
    max_attempts: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "repair_kind", RepairKind(self.repair_kind))
        object.__setattr__(self, "surface", HealthSurface(self.surface))
        for label in ("subject_id", "reason", "recovery_ref", "rollback_ref"):
            object.__setattr__(self, label, _text(getattr(self, label), label.replace("_", " ")))
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 3:
            raise StewardIntegrityError("maintenance proposal attempt bound must be between one and three")

    @property
    def proposal_id(self) -> str:
        return f"{self.repair_kind.value}:{self.surface.value}:{self.subject_id}"

    def to_document(self) -> dict[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "repair_kind": self.repair_kind.value,
            "surface": self.surface.value,
            "subject_id": self.subject_id,
            "reason": self.reason,
            "recovery_ref": self.recovery_ref,
            "rollback_ref": self.rollback_ref,
            "max_attempts": self.max_attempts,
        }


@dataclass(frozen=True, slots=True)
class StewardReport:
    """Deterministic Steward handoff with retained coverage and recovery proof."""

    readiness: OperationalReadiness
    observations: tuple[HealthObservation, ...]
    proposals: tuple[MaintenanceProposal, ...]
    observed_digest: str
    report_digest: str

    def to_document(self) -> dict[str, object]:
        return {
            "readiness": self.readiness.value,
            "observations": [item.to_document() for item in self.observations],
            "proposals": [item.to_document() for item in self.proposals],
            "observed_digest": self.observed_digest,
        }


_RECOVERY_KIND = {
    HealthSurface.QUEUES: RepairKind.REMAND,
    HealthSurface.LEASES: RepairKind.RELEASE_STALE_LEASE,
    HealthSurface.EVENT_CHAINS: RepairKind.QUARANTINE,
    HealthSurface.SNAPSHOTS: RepairKind.QUARANTINE,
    HealthSurface.WORKSPACES: RepairKind.REBUILD_WORKSPACE,
    HealthSurface.RECEIPTS: RepairKind.QUARANTINE,
    HealthSurface.PROVIDERS: RepairKind.RETRY,
}


class Steward:
    """Assess all required operational surfaces without executing a repair."""

    def assess(self, observations: Iterable[HealthObservation]) -> StewardReport:
        records = tuple(observations)
        if not records or any(not isinstance(item, HealthObservation) for item in records):
            raise StewardIntegrityError("Steward requires HealthObservation values")
        by_surface = {item.surface: item for item in records}
        if len(by_surface) != len(records):
            raise StewardIntegrityError("health surfaces must not be observed more than once")
        missing = set(HealthSurface) - set(by_surface)
        if missing:
            raise StewardIntegrityError("health assessment is missing: " + ", ".join(sorted(item.value for item in missing)))
        ordered = tuple(by_surface[item] for item in HealthSurface)
        proposals = tuple(
            MaintenanceProposal(
                _RECOVERY_KIND[item.surface],
                item.surface,
                item.subject_id,
                f"{item.surface.value} is {item.status.value}; require bounded independent recovery",
                item.recovery_ref or "",
                f"rollback:{item.surface.value}:{item.subject_id}",
            )
            for item in ordered
            if item.status is not HealthStatus.HEALTHY
        )
        critical = any(item.status is HealthStatus.CRITICAL for item in ordered)
        readiness = (
            OperationalReadiness.QUARANTINED
            if critical
            else OperationalReadiness.REPAIR_REQUIRED
            if proposals
            else OperationalReadiness.READY
        )
        observed_digest = canonical_digest([item.to_document() for item in ordered])
        document = {
            "readiness": readiness.value,
            "observations": [item.to_document() for item in ordered],
            "proposals": [item.to_document() for item in proposals],
            "observed_digest": observed_digest,
        }
        return StewardReport(
            readiness,
            ordered,
            proposals,
            observed_digest,
            canonical_digest(document),
        )
