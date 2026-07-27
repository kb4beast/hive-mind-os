from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Role(str, Enum):
    ORCHESTRATOR = "orchestrator"
    EXPLORER = "explorer"
    ARCHITECT = "architect"
    BUILDER = "builder"
    CURATOR = "curator"
    OPTIMIZER = "optimizer"
    STEWARD = "steward"
    INTEGRATOR = "integrator"


class RiskTier(IntEnum):
    LOW = 1
    MODERATE = 2
    HIGH = 3
    CRITICAL = 4


class AutonomyLevel(IntEnum):
    """Increasing authority. Policy still constrains every action."""

    OBSERVE = 0
    ADVISE = 1
    SANDBOX = 2
    REPOSITORY = 3
    DELIVERY = 4
    GOVERNED_FULL = 5


class WorkStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Objective:
    goal: str
    repository: str | None = None
    acceptance_criteria: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    risk: RiskTier = RiskTier.MODERATE
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("objective goal cannot be empty")


@dataclass(slots=True)
class WorkItem:
    objective_id: str
    role: Role
    instruction: str
    dependencies: tuple[str, ...] = ()
    id: str = field(default_factory=lambda: str(uuid4()))
    status: WorkStatus = WorkStatus.PENDING
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: str
    summary: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.kind or not self.summary or not self.source:
            raise ValueError("evidence requires kind, summary, and source")


@dataclass(frozen=True, slots=True)
class AgentResult:
    role: Role
    work_item_id: str
    summary: str
    evidence: tuple[Evidence, ...]
    proposed_actions: tuple[str, ...] = ()
    lessons: tuple[str, ...] = ()
    success: bool = True
    completed_at: str = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class RunReport:
    run_id: str
    objective_id: str
    results: tuple[AgentResult, ...]
    status: WorkStatus
    started_at: str
    completed_at: str

    @property
    def evidence_count(self) -> int:
        return sum(len(result.evidence) for result in self.results)
