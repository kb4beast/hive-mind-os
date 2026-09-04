"""Shared, DAG-free contracts for independently implemented agents."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import Role


@dataclass(frozen=True, slots=True)
class RoleContract:
    """The stable public contract owned by one constitutional agent."""

    role: Role
    mission: str
    required_outputs: tuple[str, ...]
    default_capabilities: tuple[str, ...]
    quality_gates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoleCapabilities:
    """The closed kernel capability envelope owned by one agent class."""

    allowed_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    required_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.required_outputs:
            raise ValueError("agent capabilities require declared outputs")
        if set(self.allowed_actions) & set(self.forbidden_actions):
            raise ValueError("agent action sets overlap")

    def allows(self, action: str) -> bool:
        """Return whether this agent may request the bounded action."""

        return action in self.allowed_actions and action not in self.forbidden_actions
