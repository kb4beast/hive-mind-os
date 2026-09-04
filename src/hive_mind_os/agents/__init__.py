"""One direct, standardized class per constitutional Hive Mind OS agent."""

from .architect import ArchitectAgent
from .base import Agent, AgentBackend
from .builder import BuilderAgent
from .catalog import AGENT_TYPES, agent_type_for, canonical_roles, create_agents
from .contracts import RoleCapabilities, RoleContract
from .curator import CuratorAgent
from .explorer import ExplorerAgent
from .integrator import IntegratorAgent
from .optimizer import OptimizerAgent
from .orchestrator import OrchestratorAgent
from .steward import StewardAgent

__all__ = (
    "AGENT_TYPES",
    "Agent",
    "AgentBackend",
    "ArchitectAgent",
    "BuilderAgent",
    "CuratorAgent",
    "ExplorerAgent",
    "IntegratorAgent",
    "OptimizerAgent",
    "OrchestratorAgent",
    "RoleCapabilities",
    "RoleContract",
    "StewardAgent",
    "agent_type_for",
    "canonical_roles",
    "create_agents",
)
