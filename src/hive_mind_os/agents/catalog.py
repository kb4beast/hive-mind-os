"""Direct discovery of the repository's standardized agent implementations."""

from __future__ import annotations

from collections.abc import Iterable

from ..models import Role
from .architect import ArchitectAgent
from .base import Agent, AgentBackend
from .builder import BuilderAgent
from .curator import CuratorAgent
from .explorer import ExplorerAgent
from .integrator import IntegratorAgent
from .optimizer import OptimizerAgent
from .orchestrator import OrchestratorAgent
from .steward import StewardAgent

AGENT_TYPES: tuple[type[Agent], ...] = (
    OrchestratorAgent,
    ExplorerAgent,
    ArchitectAgent,
    BuilderAgent,
    CuratorAgent,
    IntegratorAgent,
    StewardAgent,
    OptimizerAgent,
)


def canonical_roles() -> tuple[Role, ...]:
    """Return the stable role order from the direct implementations."""

    return tuple(agent_type.role for agent_type in AGENT_TYPES)


def agent_type_for(role: Role | str) -> type[Agent]:
    """Return the direct implementation for one supported role."""

    normalized = Role(role)
    for agent_type in AGENT_TYPES:
        if agent_type.role is normalized:
            return agent_type
    raise ValueError(f"no direct implementation is registered for {normalized.value}")


def create_agents(
    backend: AgentBackend, roles: Iterable[Role] | None = None
) -> tuple[Agent, ...]:
    """Construct direct agent objects, optionally for a supplied role sequence."""

    selected = canonical_roles() if roles is None else tuple(roles)
    return tuple(agent_type_for(role)(backend) for role in selected)
