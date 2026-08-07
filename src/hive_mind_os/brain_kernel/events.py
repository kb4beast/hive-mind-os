"""Append-only kernel event values and their deterministic hash-chain binding."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .canonical import canonical_digest


@dataclass(frozen=True, slots=True)
class KernelEvent:
    """One durable kernel fact, bound to its predecessor by :meth:`digest_for`."""

    event_id: str
    mission_id: str
    event_type: str
    actor_id: str
    occurred_at: str
    payload: Mapping[str, Any]
    work_id: str | None = None
    attempt_id: str | None = None
    actor_role: str | None = None
    event_version: int = 1
    previous_digest: str | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.event_id, "event_id"),
            (self.mission_id, "mission_id"),
            (self.event_type, "event_type"),
            (self.actor_id, "actor_id"),
            (self.occurred_at, "occurred_at"),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{label} is required")
        if type(self.event_version) is not int or self.event_version < 1:
            raise ValueError("event_version must be a positive integer")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a mapping")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def digest_for(self, previous_digest: str | None) -> str:
        return canonical_digest(
            {
                "event_id": self.event_id,
                "mission_id": self.mission_id,
                "work_id": self.work_id,
                "attempt_id": self.attempt_id,
                "event_type": self.event_type,
                "event_version": self.event_version,
                "actor_id": self.actor_id,
                "actor_role": self.actor_role,
                "occurred_at": self.occurred_at,
                "payload": dict(self.payload),
                "previous_digest": previous_digest,
            }
        )
