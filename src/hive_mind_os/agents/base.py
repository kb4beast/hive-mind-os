"""Common execution behavior for the repository's direct agent classes."""

from __future__ import annotations

from typing import Protocol

from ..models import AgentResult, Objective, Role, WorkItem, WorkStatus
from .contracts import RoleCapabilities, RoleContract


class AgentBackend(Protocol):
    """The provider boundary shared by every direct agent implementation."""

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult: ...


class Agent:
    """Base class for one constitutional agent.

    The class owns role identity and behavior metadata.  A runtime may call it,
    but does not define or route the role's contract.
    """

    role: Role
    contract: RoleContract
    capabilities: RoleCapabilities
    next_role: Role | None = None
    requires_evaluator_mode = False

    def __init__(self, backend: AgentBackend) -> None:
        self.backend = backend

    async def run(
        self,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        """Run the role through the configured backend and record local state."""

        if work_item.role is not self.role:
            raise ValueError(
                f"{type(self).__name__} cannot run work for {work_item.role.value}"
            )
        work_item.status = WorkStatus.RUNNING
        result = await self.backend.execute(
            self.contract, work_item, objective, context
        )
        if result.role is not self.role:
            raise ValueError(
                f"{type(self).__name__} returned {result.role.value}, expected {self.role.value}"
            )
        work_item.status = WorkStatus.SUCCEEDED if result.success else WorkStatus.FAILED
        return result

    def allows(self, action: str) -> bool:
        """Return the role-owned capability decision without causing an effect."""

        return self.capabilities.allows(action)

    def accepts_evaluator_mode(self, evaluator_mode: bool) -> bool:
        """State whether this role accepts the supplied evaluator isolation mode."""

        return evaluator_mode is self.requires_evaluator_mode
