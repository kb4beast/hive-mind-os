"""Deterministic, bounded Phase 2 repository mission loop.

This runtime deliberately separates model/role proposals from state transition,
policy, execution, receipts, and Curator verification.  It is local-only: it never
pushes, opens pull requests, merges, or deploys.  The older ``RepositoryMission``
remains available for its historical fixture and durable-store contracts; new callers
use :class:`MissionLoop` for the iterative Phase 2 lifecycle.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4

from .acceptance import AcceptanceSpecification, normalize_acceptance_specifications
from .model_action_adapter import ModelProviderActionAdapter
from .models import AutonomyLevel, RiskTier, Role
from .policy import Action, PolicyEngine
from .receipts import portable_path_parts, sha256_digest
from .verify import VerificationError, VerificationReport, verify_repository


class MissionLoopError(RuntimeError):
    """A bounded mission cannot safely continue."""


class StaleMissionState(MissionLoopError):
    """A proposed event was based on an older immutable state revision."""


class MissionStatus(StrEnum):
    INTAKE = "intake"
    PLANNING = "planning"
    DISCOVERING = "discovering"
    DESIGNING = "designing"
    BUILDING = "building"
    VERIFYING = "verifying"
    INTEGRATING = "integrating"
    OPERATING = "operating"
    EVALUATING = "evaluating"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"


_TERMINAL = frozenset(
    {
        MissionStatus.SUCCEEDED,
        MissionStatus.BLOCKED,
        MissionStatus.FAILED,
        MissionStatus.CANCELLED,
        MissionStatus.QUARANTINED,
    }
)
_EVENT_TYPES = frozenset(
    {
        "mission.intake",
        "mission.planned",
        "work.created",
        "role.started",
        "role.action.proposed",
        "policy.decided",
        "tool.executed",
        "role.completed",
        "role.remanded",
        "claim.disputed",
        "court.decided",
        "budget.consumed",
        "mission.blocked",
        "mission.failed",
        "mission.cancelled",
        "mission.succeeded",
    }
)
_FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
_PROMPT_INJECTION = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:prior|previous)\s+instructions|"
    r"system\s+prompt|(?:push|exfiltrate)\s+(?:this|the)\s+repository)",
    re.IGNORECASE,
)
_DEPENDENCY_FILES = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "poetry.lock",
        "pyproject.toml",
        "Pipfile.lock",
        "*.csproj",
        "packages.lock.json",
    }
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return f"sha256:{sha256(_canonical(value)).hexdigest()}"


@dataclass(frozen=True, slots=True)
class BudgetState:
    max_role_turns: int
    max_tool_calls: int
    max_repeated_progress: int
    role_turns_used: int = 0
    tool_calls_used: int = 0

    def __post_init__(self) -> None:
        if min(
            self.max_role_turns,
            self.max_tool_calls,
            self.max_repeated_progress,
            self.role_turns_used,
            self.tool_calls_used,
        ) < 0:
            raise ValueError("mission budgets cannot be negative")


@dataclass(frozen=True, slots=True)
class MissionBudget:
    """A non-renewable envelope for role turns and executor calls."""

    max_role_turns: int = 16
    max_tool_calls: int = 48
    max_repeated_progress: int = 2

    def state(self) -> BudgetState:
        return BudgetState(
            self.max_role_turns,
            self.max_tool_calls,
            self.max_repeated_progress,
        )


@dataclass(frozen=True, slots=True)
class WorkItemState:
    id: str
    role: Role
    instruction: str
    allowed_paths: tuple[str, ...] = ()
    parent_id: str | None = None
    status: str = "pending"

    def __post_init__(self) -> None:
        if not self.id or not self.instruction.strip():
            raise ValueError("work items require an id and instruction")
        if self.status not in {"pending", "running", "succeeded", "remanded"}:
            raise ValueError("work item state is invalid")


@dataclass(frozen=True, slots=True)
class MissionState:
    mission_id: str
    revision: int
    objective_ref: str
    status: MissionStatus
    risk_lane: str
    work_items: tuple[WorkItemState, ...]
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...]
    dissent_refs: tuple[str, ...]
    budgets: BudgetState
    grants: tuple[str, ...]
    active_leases: tuple[str, ...]
    current_role: str | None
    terminal_reason: str | None

    @classmethod
    def intake(
        cls,
        mission_id: str,
        objective_ref: str,
        *,
        risk_lane: str,
        budget: BudgetState | None = None,
    ) -> MissionState:
        if not mission_id or not objective_ref:
            raise ValueError("mission and objective references are required")
        return cls(
            mission_id=mission_id,
            revision=0,
            objective_ref=objective_ref,
            status=MissionStatus.INTAKE,
            risk_lane=risk_lane,
            work_items=(),
            artifact_refs=(),
            evidence_refs=(),
            blockers=(),
            dissent_refs=(),
            budgets=budget or MissionBudget().state(),
            grants=(),
            active_leases=(),
            current_role=None,
            terminal_reason=None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "mission_id": self.mission_id,
            "revision": self.revision,
            "objective_ref": self.objective_ref,
            "status": self.status.value,
            "risk_lane": self.risk_lane,
            "work_items": [
                {
                    "id": item.id,
                    "role": item.role.value,
                    "instruction": item.instruction,
                    "allowed_paths": list(item.allowed_paths),
                    "parent_id": item.parent_id,
                    "status": item.status,
                }
                for item in self.work_items
            ],
            "artifact_refs": list(self.artifact_refs),
            "evidence_refs": list(self.evidence_refs),
            "blockers": list(self.blockers),
            "dissent_refs": list(self.dissent_refs),
            "budgets": asdict(self.budgets),
            "grants": list(self.grants),
            "active_leases": list(self.active_leases),
            "current_role": self.current_role,
            "terminal_reason": self.terminal_reason,
        }


@dataclass(frozen=True, slots=True)
class MissionEvent:
    event_type: str
    actor: Role
    expected_revision: int
    payload: Mapping[str, object]
    sequence: int | None = None

    def __post_init__(self) -> None:
        if self.event_type not in _EVENT_TYPES:
            raise ValueError(f"unsupported mission event type: {self.event_type}")
        if self.expected_revision < 0:
            raise ValueError("event revision cannot be negative")

    @property
    def digest(self) -> str:
        return _digest(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, object]:
        document: dict[str, object] = {
            "sequence": self.sequence,
            "event_type": self.event_type,
            "actor": self.actor.value,
            "expected_revision": self.expected_revision,
            "payload": dict(self.payload),
        }
        if include_digest:
            document["digest"] = self.digest
        return document


def _event_work_item(payload: Mapping[str, object]) -> WorkItemState:
    try:
        role = Role(str(payload["role"]))
        allowed_paths = tuple(
            "/".join(portable_path_parts(str(item)))
            for item in payload.get("allowed_paths", ())
        )
        return WorkItemState(
            id=str(payload["work_item_id"]),
            role=role,
            instruction=str(payload["instruction"]),
            allowed_paths=allowed_paths,
            parent_id=(None if payload.get("parent_id") is None else str(payload["parent_id"])),
        )
    except (KeyError, ValueError) as error:
        raise MissionLoopError(f"invalid work item event: {error}") from None


def _find_item(state: MissionState, work_item_id: str) -> tuple[int, WorkItemState]:
    for index, item in enumerate(state.work_items):
        if item.id == work_item_id:
            return index, item
    raise MissionLoopError(f"unknown work item: {work_item_id}")


def _replace_item(state: MissionState, index: int, item: WorkItemState) -> tuple[WorkItemState, ...]:
    return (*state.work_items[:index], item, *state.work_items[index + 1 :])


def _role_status(role: Role) -> MissionStatus:
    return {
        Role.ORCHESTRATOR: MissionStatus.PLANNING,
        Role.EXPLORER: MissionStatus.DISCOVERING,
        Role.ARCHITECT: MissionStatus.DESIGNING,
        Role.BUILDER: MissionStatus.BUILDING,
        Role.CURATOR: MissionStatus.VERIFYING,
        Role.INTEGRATOR: MissionStatus.INTEGRATING,
        Role.STEWARD: MissionStatus.OPERATING,
        Role.OPTIMIZER: MissionStatus.EVALUATING,
    }[role]


def reduce_mission_state(state: MissionState, event: MissionEvent) -> MissionState:
    """Apply one legal, revision-bound transition without mutating prior state."""

    if event.expected_revision != state.revision:
        raise StaleMissionState(
            f"event expects revision {event.expected_revision}; current revision is {state.revision}"
        )
    if state.status in _TERMINAL:
        raise MissionLoopError("no transition is allowed after a terminal mission state")
    payload = event.payload
    next_state = state

    if event.event_type == "mission.intake":
        if state.revision != 0 or state.status is not MissionStatus.INTAKE:
            raise MissionLoopError("mission intake is allowed exactly once")
    elif event.event_type == "mission.planned":
        if state.status is not MissionStatus.INTAKE:
            raise MissionLoopError("mission planning is only allowed from intake")
        item = _event_work_item(payload)
        next_state = replace(
            state,
            status=MissionStatus.PLANNING,
            work_items=(item,),
            artifact_refs=(*state.artifact_refs, str(payload.get("plan_ref", "plan"))),
        )
    elif event.event_type == "work.created":
        item = _event_work_item(payload)
        if any(existing.id == item.id for existing in state.work_items):
            raise MissionLoopError("work item ids are append-only and unique")
        next_state = replace(state, work_items=(*state.work_items, item))
    elif event.event_type == "role.started":
        index, item = _find_item(state, str(payload.get("work_item_id", "")))
        if item.role is not event.actor or item.status != "pending":
            raise MissionLoopError("role start requires its pending work item")
        next_state = replace(
            state,
            status=_role_status(event.actor),
            current_role=event.actor.value,
            work_items=_replace_item(state, index, replace(item, status="running")),
        )
    elif event.event_type == "role.completed":
        index, item = _find_item(state, str(payload.get("work_item_id", "")))
        if item.role is not event.actor or item.status != "running":
            raise MissionLoopError("role completion requires its running work item")
        completed_status = state.status
        if event.actor is Role.EXPLORER:
            completed_status = MissionStatus.DESIGNING if any(
                work.role is Role.ARCHITECT and work.status == "pending" for work in state.work_items
            ) else MissionStatus.BUILDING
        elif event.actor is Role.ARCHITECT:
            completed_status = MissionStatus.BUILDING
        elif event.actor is Role.BUILDER:
            completed_status = MissionStatus.VERIFYING
        elif event.actor is Role.CURATOR:
            completed_status = MissionStatus.INTEGRATING
        evidence_ref = payload.get("evidence_ref")
        next_state = replace(
            state,
            status=completed_status,
            current_role=None,
            work_items=_replace_item(state, index, replace(item, status="succeeded")),
            evidence_refs=(
                *state.evidence_refs,
                str(evidence_ref),
            )
            if isinstance(evidence_ref, str) and evidence_ref
            else state.evidence_refs,
        )
    elif event.event_type == "role.remanded":
        index, item = _find_item(state, str(payload.get("work_item_id", "")))
        if event.actor is not Role.CURATOR or item.status != "succeeded":
            raise MissionLoopError("only Curator may remand a completed work item")
        try:
            target = Role(str(payload["target_role"]))
            new_id = str(payload["new_work_item_id"])
            reason = str(payload["reason"])
        except (KeyError, ValueError) as error:
            raise MissionLoopError(f"invalid remand: {error}") from None
        if not reason.strip() or any(work.id == new_id for work in state.work_items):
            raise MissionLoopError("remand requires a unique work item and reason")
        remand = WorkItemState(
            id=new_id,
            role=target,
            instruction=f"Remand: {reason}",
            allowed_paths=item.allowed_paths,
            parent_id=item.id,
        )
        next_state = replace(
            state,
            status=_role_status(target),
            current_role=None,
            work_items=(*_replace_item(state, index, replace(item, status="remanded")), remand),
            blockers=(*state.blockers, reason),
            dissent_refs=(*state.dissent_refs, f"remand:{new_id}"),
        )
    elif event.event_type == "budget.consumed":
        kind = payload.get("kind")
        amount = payload.get("amount")
        if kind not in {"role_turn", "tool_call"} or not isinstance(amount, int) or amount < 1:
            raise MissionLoopError("budget consumption must name a positive known unit")
        budgets = state.budgets
        if kind == "role_turn":
            if budgets.role_turns_used + amount > budgets.max_role_turns:
                raise MissionLoopError("mission role-turn budget exhausted")
            budgets = replace(budgets, role_turns_used=budgets.role_turns_used + amount)
        else:
            if budgets.tool_calls_used + amount > budgets.max_tool_calls:
                raise MissionLoopError("mission tool-call budget exhausted")
            budgets = replace(budgets, tool_calls_used=budgets.tool_calls_used + amount)
        next_state = replace(state, budgets=budgets)
    elif event.event_type == "tool.executed":
        if event.actor.value != state.current_role:
            raise MissionLoopError("tool execution must belong to the active role")
        blocker = payload.get("blocker")
        next_state = replace(
            state,
            blockers=(*state.blockers, str(blocker))
            if isinstance(blocker, str) and blocker
            else state.blockers,
            evidence_refs=(
                *state.evidence_refs,
                str(payload["receipt_ref"]),
            )
            if isinstance(payload.get("receipt_ref"), str)
            else state.evidence_refs,
        )
    elif event.event_type == "claim.disputed":
        claim = payload.get("claim_ref")
        if not isinstance(claim, str) or not claim:
            raise MissionLoopError("disputed claims require a reference")
        next_state = replace(state, dissent_refs=(*state.dissent_refs, claim))
    elif event.event_type in {"role.action.proposed", "policy.decided", "court.decided"}:
        if event.actor.value != state.current_role and event.actor is not Role.ORCHESTRATOR:
            raise MissionLoopError("action and policy events require the active role")
    elif event.event_type in {"mission.blocked", "mission.failed", "mission.cancelled"}:
        reason = payload.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise MissionLoopError("terminal mission transitions require a reason")
        status = {
            "mission.blocked": MissionStatus.BLOCKED,
            "mission.failed": MissionStatus.FAILED,
            "mission.cancelled": MissionStatus.CANCELLED,
        }[event.event_type]
        next_state = replace(state, status=status, terminal_reason=reason, current_role=None)
    elif event.event_type == "mission.succeeded":
        if state.status is not MissionStatus.INTEGRATING:
            raise MissionLoopError("mission success is not allowed before Curator adoption")
        next_state = replace(state, status=MissionStatus.SUCCEEDED, current_role=None)
    else:  # pragma: no cover - guarded by the event-type constructor
        raise MissionLoopError("event is not handled by the mission reducer")
    return replace(next_state, revision=state.revision + 1)


@dataclass(frozen=True, slots=True)
class MissionObjective:
    goal: str
    acceptance: tuple[AcceptanceSpecification, ...] = ()
    constraints: tuple[str, ...] = ()
    risk: RiskTier = RiskTier.MODERATE
    task_class: str = "repository-change"
    repository_identity: str | None = None

    def __post_init__(self) -> None:
        if not self.goal.strip():
            raise ValueError("mission objective is required")
        if not isinstance(self.risk, RiskTier):
            raise ValueError("mission risk must be a RiskTier")
        normalized = normalize_acceptance_specifications(self.acceptance)
        object.__setattr__(self, "acceptance", normalized)
        object.__setattr__(self, "constraints", tuple(item.strip() for item in self.constraints if item.strip()))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "goal": self.goal,
                "acceptance": [item.to_dict() for item in self.acceptance],
                "constraints": list(self.constraints),
                "risk": int(self.risk),
                "task_class": self.task_class,
                "repository_identity": self.repository_identity,
            }
        )


@dataclass(frozen=True, slots=True)
class MissionPlan:
    risk_lane: str
    roles: tuple[Role, ...]
    dependencies: Mapping[Role, tuple[Role, ...]]
    evidence_requirements: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    rollback_reserve: str
    verification_reserve: str
    human_gates: tuple[str, ...]
    allowed_paths: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "risk_lane": self.risk_lane,
            "roles": [role.value for role in self.roles],
            "dependencies": {role.value: [item.value for item in values] for role, values in self.dependencies.items()},
            "evidence_requirements": list(self.evidence_requirements),
            "stop_conditions": list(self.stop_conditions),
            "rollback_reserve": self.rollback_reserve,
            "verification_reserve": self.verification_reserve,
            "human_gates": list(self.human_gates),
            "allowed_paths": list(self.allowed_paths),
        }


class Orchestrator:
    """Deterministic intake validator and minimum-role planner."""

    def plan(self, objective: MissionObjective) -> MissionPlan:
        if not objective.acceptance:
            raise MissionLoopError("acceptance criteria must be executable before planning")
        allowed: set[str] = set()
        denied: set[str] = set()
        for constraint in objective.constraints:
            lowered = constraint.casefold()
            if lowered.startswith("allow "):
                allowed.add(constraint[6:].strip())
            elif lowered.startswith("deny "):
                denied.add(constraint[5:].strip())
        contradiction = sorted(item for item in allowed & denied if item)
        if contradiction:
            raise MissionLoopError("contradictory constraints: " + ", ".join(contradiction))
        allowed_paths = tuple(sorted({path for spec in objective.acceptance for path in spec.declared_paths}))
        if not allowed_paths:
            raise MissionLoopError("acceptance specifications must declare allowed change paths")
        if objective.risk is RiskTier.LOW and objective.task_class == "documentation":
            roles = (Role.ORCHESTRATOR, Role.EXPLORER, Role.BUILDER, Role.CURATOR)
            lane = "low"
            gates: tuple[str, ...] = ()
        elif objective.risk in {RiskTier.HIGH, RiskTier.CRITICAL}:
            roles = (
                Role.ORCHESTRATOR,
                Role.EXPLORER,
                Role.ARCHITECT,
                Role.BUILDER,
                Role.CURATOR,
                Role.STEWARD,
            )
            lane = "high" if objective.risk is RiskTier.HIGH else "critical"
            gates = ("external steward review", "human authority gate")
        else:
            roles = (Role.ORCHESTRATOR, Role.EXPLORER, Role.ARCHITECT, Role.BUILDER, Role.CURATOR)
            lane = "moderate"
            gates = ()
        dependencies: dict[Role, tuple[Role, ...]] = {
            Role.EXPLORER: (Role.ORCHESTRATOR,),
            Role.ARCHITECT: (Role.EXPLORER,),
            Role.BUILDER: ((Role.ARCHITECT,) if Role.ARCHITECT in roles else (Role.EXPLORER,)),
            Role.CURATOR: (Role.BUILDER,),
        }
        if Role.STEWARD in roles:
            dependencies[Role.STEWARD] = (Role.CURATOR,)
        return MissionPlan(
            risk_lane=lane,
            roles=roles,
            dependencies=dependencies,
            evidence_requirements=(
                "sealed acceptance specifications",
                "read-only discovery evidence",
                "typed action receipts",
                "fresh immutable Curator bundle",
            ),
            stop_conditions=(
                "budget exhausted",
                "repeated semantic progress fingerprint",
                "authority violation",
                "untestable acceptance",
            ),
            rollback_reserve="revert the candidate commit in the isolated Builder workspace",
            verification_reserve="one fresh Phase 1 immutable verification bundle",
            human_gates=gates,
            allowed_paths=allowed_paths,
        )


@dataclass(frozen=True, slots=True)
class DiscoveryAction:
    name: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class DiscoveryReport:
    hypotheses: tuple[str, ...]
    supporting_evidence: tuple[str, ...]
    conflicting_evidence: tuple[str, ...]
    unknowns: tuple[str, ...]
    relevant_paths: tuple[str, ...]
    suspected_test_commands: tuple[tuple[str, ...], ...]
    alternatives: tuple[str, ...]
    recommended_next_role: Role
    confidence: float
    sufficient_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "hypotheses": list(self.hypotheses),
            "supporting_evidence": list(self.supporting_evidence),
            "conflicting_evidence": list(self.conflicting_evidence),
            "unknowns": list(self.unknowns),
            "relevant_paths": list(self.relevant_paths),
            "suspected_test_commands": [list(item) for item in self.suspected_test_commands],
            "alternatives": list(self.alternatives),
            "recommended_next_role": self.recommended_next_role.value,
            "confidence": self.confidence,
            "sufficient_reason": self.sufficient_reason,
        }


@dataclass(frozen=True, slots=True)
class ArchitectDesign:
    options: tuple[str, ...]
    selected: str
    constraints: tuple[str, ...]
    invariants: tuple[str, ...]
    threat_model: tuple[str, ...]
    data_classifications: tuple[str, ...]
    migration_plan: str
    rollback_plan: str
    compatibility_impact: str
    acceptance_mapping: Mapping[str, str]
    unknowns: tuple[str, ...]

    def validate(self, acceptance: Sequence[AcceptanceSpecification]) -> None:
        if len(self.options) < 2 or self.selected not in self.options:
            raise MissionLoopError("Architect requires at least two options and a selected option")
        if not all(
            (
                self.constraints,
                self.invariants,
                self.threat_model,
                self.data_classifications,
                self.migration_plan.strip(),
                self.rollback_plan.strip(),
                self.compatibility_impact.strip(),
            )
        ):
            raise MissionLoopError("Architect design lacks a required risk or rollback output")
        expected = {item.identifier for item in acceptance}
        if set(self.acceptance_mapping) != expected:
            raise MissionLoopError("Architect acceptance mapping must cover every sealed specification")

    def to_dict(self) -> dict[str, object]:
        return {
            "options": list(self.options),
            "selected": self.selected,
            "constraints": list(self.constraints),
            "invariants": list(self.invariants),
            "threat_model": list(self.threat_model),
            "data_classifications": list(self.data_classifications),
            "migration_plan": self.migration_plan,
            "rollback_plan": self.rollback_plan,
            "compatibility_impact": self.compatibility_impact,
            "acceptance_mapping": dict(self.acceptance_mapping),
            "unknowns": list(self.unknowns),
        }


@dataclass(frozen=True, slots=True)
class BuilderAction:
    name: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class BuilderLimits:
    max_turns: int = 8
    max_tool_calls: int = 32
    max_files_changed: int = 12
    max_diff_bytes: int = 200_000
    max_command_seconds: float = 30.0
    max_total_seconds: float = 300.0
    max_dependency_changes: int = 0
    max_retry_count: int = 4

    def __post_init__(self) -> None:
        if min(
            self.max_turns,
            self.max_tool_calls,
            self.max_files_changed,
            self.max_diff_bytes,
            self.max_dependency_changes,
            self.max_retry_count,
        ) < 0 or self.max_command_seconds <= 0 or self.max_total_seconds <= 0:
            raise ValueError("Builder limits must be non-negative and timeouts positive")


@dataclass(frozen=True, slots=True)
class ToolReceipt:
    index: int
    role: Role
    action: str
    payload_digest: str
    outcome: str
    observation_digest: str
    details: Mapping[str, object]

    @property
    def ref(self) -> str:
        return f"receipt:{self.index}:{self.observation_digest}"

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "role": self.role.value,
            "action": self.action,
            "payload_digest": self.payload_digest,
            "outcome": self.outcome,
            "observation_digest": self.observation_digest,
            "details": dict(self.details),
            "ref": self.ref,
        }


@dataclass(frozen=True, slots=True)
class CuratorResult:
    verdict: str
    candidate_commit: str | None
    candidate_tree: str | None
    bundle: Path | None
    findings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "candidate_commit": self.candidate_commit,
            "candidate_tree": self.candidate_tree,
            "bundle": None if self.bundle is None else str(self.bundle),
            "findings": list(self.findings),
        }


@dataclass(frozen=True, slots=True)
class MissionReport:
    mission_id: str
    status: MissionStatus
    bundle: Path
    state: MissionState
    events: tuple[MissionEvent, ...]
    receipts: tuple[ToolReceipt, ...]
    curator: CuratorResult


def _git_environment() -> dict[str, str]:
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if os.name == "nt":
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC"):
            if name in os.environ:
                environment[name] = os.environ[name]
    return environment


class MissionLoop:
    """Execute the Phase 2 role loop through typed, locally bounded actions."""

    def __init__(
        self,
        repository: str | Path,
        objective: MissionObjective,
        *,
        output: str | Path,
        base_commit: str,
        builder_limits: BuilderLimits | None = None,
        budget: MissionBudget | None = None,
        policy: PolicyEngine | None = None,
    ) -> None:
        self.repository = Path(repository).resolve()
        if not self.repository.is_dir() or not (self.repository / ".git").exists():
            raise ValueError("mission loop requires a local Git repository")
        if _FULL_SHA.fullmatch(base_commit) is None:
            raise ValueError("mission loop base commit must be a full lowercase SHA")
        self.base_commit = base_commit
        self.objective = objective
        self.output = Path(os.path.abspath(output))
        if self.output.exists():
            raise ValueError("mission output must not already exist")
        try:
            self.output.relative_to(self.repository)
        except ValueError:
            pass
        else:
            raise ValueError("mission output must be outside the caller repository")
        if not self.output.parent.is_dir():
            raise ValueError("mission output parent must exist")
        self.plan = Orchestrator().plan(objective)
        self.limits = builder_limits or BuilderLimits()
        # Local commits are required to form an immutable candidate.  This is still
        # repository-scoped authority only: the loop has no push, PR, merge, deploy,
        # credential, or spending action.
        self.policy = policy or PolicyEngine(AutonomyLevel.REPOSITORY)
        self._state = MissionState.intake(
            f"MISSION-{uuid4()}",
            objective.digest,
            risk_lane=self.plan.risk_lane,
            budget=(budget or MissionBudget()).state(),
        )
        self._events: list[MissionEvent] = []
        self._receipts: list[ToolReceipt] = []
        self._workspace_root = Path(tempfile.mkdtemp(prefix="hive-mind-phase2-"))
        self._explorer_workspace: Path | None = None
        self._builder_workspace: Path | None = None
        self._builder_turns = 0
        self._builder_calls = 0
        self._changed_paths: set[str] = set()
        self._write_digests: set[tuple[str, str]] = set()
        self._progress_fingerprints: dict[str, int] = {}
        self._candidate: str | None = None
        self._discovery: DiscoveryReport | None = None
        self._design: ArchitectDesign | None = None
        self._curator: CuratorResult | None = None
        self._record(MissionEvent("mission.intake", Role.ORCHESTRATOR, 0, {"objective_ref": objective.digest}))
        self._record(
            MissionEvent(
                "mission.planned",
                Role.ORCHESTRATOR,
                self._state.revision,
                {
                    "work_item_id": "W-orchestrator",
                    "role": Role.ORCHESTRATOR.value,
                    "instruction": "validate intake and plan bounded work",
                    "allowed_paths": list(self.plan.allowed_paths),
                    "plan_ref": f"plan:{_digest(self.plan.to_dict())}",
                },
            )
        )
        for role in self.plan.roles:
            if role is Role.ORCHESTRATOR:
                continue
            self._record(
                MissionEvent(
                    "work.created",
                    Role.ORCHESTRATOR,
                    self._state.revision,
                    {
                        "work_item_id": f"W-{role.value}",
                        "role": role.value,
                        "instruction": f"perform bounded {role.value} work",
                        "allowed_paths": list(self.plan.allowed_paths),
                    },
                )
            )

    @property
    def state(self) -> MissionState:
        return self._state

    @property
    def tool_receipts(self) -> tuple[ToolReceipt, ...]:
        return tuple(self._receipts)

    def _record(self, event: MissionEvent) -> MissionState:
        if event.expected_revision != self._state.revision:
            raise StaleMissionState("runtime attempted to append an event from stale state")
        self._state = reduce_mission_state(self._state, event)
        self._events.append(replace(event, sequence=len(self._events) + 1))
        return self._state

    def _work(self, role: Role) -> WorkItemState:
        pending = [item for item in self._state.work_items if item.role is role and item.status == "pending"]
        if not pending:
            raise MissionLoopError(f"no pending {role.value} work item")
        return pending[-1]

    def _start_role(self, role: Role) -> WorkItemState:
        self._consume("role_turn", 1, role)
        item = self._work(role)
        self._record(
            MissionEvent("role.started", role, self._state.revision, {"work_item_id": item.id})
        )
        return item

    def _resume_or_start_builder(self) -> WorkItemState:
        """A failed test keeps the same Builder work item active for the next turn."""

        running = [
            item
            for item in self._state.work_items
            if item.role is Role.BUILDER and item.status == "running"
        ]
        if running:
            if self._state.current_role != Role.BUILDER.value:
                raise MissionLoopError("Builder work item is active under another role")
            self._consume("role_turn", 1, Role.BUILDER)
            return running[-1]
        return self._start_role(Role.BUILDER)

    def _complete_role(self, role: Role, item: WorkItemState, evidence_ref: str) -> None:
        self._record(
            MissionEvent(
                "role.completed",
                role,
                self._state.revision,
                {"work_item_id": item.id, "evidence_ref": evidence_ref},
            )
        )

    def _consume(self, kind: str, amount: int, actor: Role) -> None:
        try:
            self._record(
                MissionEvent(
                    "budget.consumed",
                    actor,
                    self._state.revision,
                    {"kind": kind, "amount": amount},
                )
            )
        except MissionLoopError as error:
            if self._state.status not in _TERMINAL:
                self._record(
                    MissionEvent(
                        "mission.blocked",
                        Role.ORCHESTRATOR,
                        self._state.revision,
                        {"reason": str(error)},
                    )
                )
            raise

    def _policy(self, role: Role, action: Action, name: str, payload: Mapping[str, object]) -> None:
        self._record(
            MissionEvent(
                "role.action.proposed",
                role,
                self._state.revision,
                {"action": name, "payload_digest": _digest(dict(payload))},
            )
        )
        decision = self.policy.decide(role, action, self.objective.risk)
        self._record(
            MissionEvent(
                "policy.decided",
                role,
                self._state.revision,
                {"action": action.value, "allowed": decision.allowed, "reason": decision.reason},
            )
        )
        if not decision.allowed:
            raise MissionLoopError(f"policy denied {name}: {decision.reason}")

    def _receipt(
        self,
        role: Role,
        name: str,
        payload: Mapping[str, object],
        outcome: str,
        observation: Mapping[str, object],
        *,
        blocker: str | None = None,
    ) -> ToolReceipt:
        receipt = ToolReceipt(
            index=len(self._receipts) + 1,
            role=role,
            action=name,
            payload_digest=_digest(dict(payload)),
            outcome=outcome,
            observation_digest=_digest(dict(observation)),
            details=dict(observation),
        )
        self._receipts.append(receipt)
        self._record(
            MissionEvent(
                "tool.executed",
                role,
                self._state.revision,
                {
                    "receipt_ref": receipt.ref,
                    "outcome": outcome,
                    **({"blocker": blocker} if blocker else {}),
                },
            )
        )
        return receipt

    def _tool(
        self,
        role: Role,
        name: str,
        action: Action,
        payload: Mapping[str, object],
        operation: callable,
    ) -> ToolReceipt:
        self._policy(role, action, name, payload)
        self._consume("tool_call", 1, role)
        try:
            outcome, observation = operation()
        except MissionLoopError:
            raise
        except Exception as error:  # executor failures are evidence, not hidden
            outcome, observation = "failed", {"error": str(error)}
        blocker = (
            str(observation.get("error") or f"{name} returned {outcome}")
            if outcome != "succeeded"
            else None
        )
        return self._receipt(role, name, payload, outcome, observation, blocker=blocker)

    @staticmethod
    def _safe_relative(raw: object) -> str:
        if not isinstance(raw, str):
            raise MissionLoopError("path must be a string")
        try:
            return "/".join(portable_path_parts(raw))
        except ValueError as error:
            raise MissionLoopError(f"unsafe repository path: {error}") from None

    @staticmethod
    def _allowed_command(value: object) -> tuple[str, ...]:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise MissionLoopError("command argv must be a non-empty string list")
        argv = tuple(str(item) for item in value)
        if not argv or any(not item or "\x00" in item for item in argv):
            raise MissionLoopError("command argv must be a non-empty string list")
        executable = Path(argv[0]).name.casefold().removesuffix(".exe")
        if executable not in {"python", "py", Path(sys.executable).name.casefold().removesuffix(".exe"), "node", "dotnet"}:
            raise MissionLoopError("command executable is outside the local mission allowlist")
        if any(item in {"-c", "--eval", "-e"} for item in argv[1:]):
            raise MissionLoopError("inline command execution is not allowed")
        return argv

    def _path(self, root: Path, relative: str) -> Path:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            raise MissionLoopError("path escapes isolated workspace") from None
        current = root / relative
        if current.exists() and current.is_symlink():
            raise MissionLoopError("symlink paths are not supported by the mission loop")
        return candidate

    def _clone(self, destination: Path, commit: str) -> Path:
        if destination.exists():
            raise MissionLoopError("isolated workspace destination already exists")
        source = (self.repository / ".git").resolve().as_uri()
        hooks = destination.parent / f"disabled-hooks-{uuid4()}"
        hooks.mkdir(parents=True)
        git = shutil.which("git")
        if git is None:
            raise MissionLoopError("Git executable is unavailable")
        clone = subprocess.run(
            (
                git,
                "-c",
                f"core.hooksPath={hooks}",
                "-c",
                "core.autocrlf=false",
                "clone",
                "--no-local",
                "--no-hardlinks",
                "--no-checkout",
                source,
                str(destination),
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
            check=False,
            timeout=60,
        )
        if clone.returncode != 0:
            raise MissionLoopError("isolated clone failed: " + clone.stderr.decode("utf-8", "replace").strip())
        self._git(destination, ("checkout", "--detach", "--force", commit), timeout=60)
        observed = self._git(destination, ("rev-parse", "HEAD"), timeout=30)[1].strip()
        if observed != commit:
            raise MissionLoopError("isolated workspace did not materialize the sealed base commit")
        return destination

    def _git(self, root: Path, argv: Sequence[str], *, timeout: float) -> tuple[int, str, str]:
        git = shutil.which("git")
        if git is None:
            raise MissionLoopError("Git executable is unavailable")
        hooks = root.parent / "disabled-hooks"
        hooks.mkdir(exist_ok=True)
        completed = subprocess.run(
            (
                git,
                "-C",
                str(root),
                "-c",
                f"core.hooksPath={hooks}",
                "-c",
                "core.autocrlf=false",
                "-c",
                "commit.gpgsign=false",
                *argv,
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
            check=False,
            timeout=timeout,
        )
        return (
            completed.returncode,
            completed.stdout.decode("utf-8", "replace"),
            completed.stderr.decode("utf-8", "replace"),
        )

    def _command(self, root: Path, argv: Sequence[str]) -> tuple[str, dict[str, object]]:
        allowed = self._allowed_command(argv)
        try:
            completed = subprocess.run(
                allowed,
                cwd=root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_git_environment(),
                check=False,
                timeout=self.limits.max_command_seconds,
            )
        except subprocess.TimeoutExpired as error:
            return "timeout", {"argv": list(allowed), "stdout_digest": sha256_digest(error.stdout or b""), "stderr_digest": sha256_digest(error.stderr or b"")}
        stdout = completed.stdout[:1_000_000]
        stderr = completed.stderr[:1_000_000]
        return (
            "succeeded" if completed.returncode == 0 else "failed",
            {
                "argv": list(allowed),
                "exit_code": completed.returncode,
                "stdout_digest": sha256_digest(stdout),
                "stderr_digest": sha256_digest(stderr),
                "output_truncated": len(completed.stdout) > len(stdout) or len(completed.stderr) > len(stderr),
            },
        )

    @staticmethod
    def _validate_discovery_actions(actions: Sequence[DiscoveryAction]) -> None:
        readonly = {
            "list_tree", "read_file", "read_file_range", "search_text", "search_symbol",
            "inspect_git_status", "inspect_git_history", "inspect_commit", "inspect_build_configuration",
            "run_read_only_command", "record_evidence", "propose_hypothesis", "request_more_evidence", "finish_discovery",
        }
        for action in actions:
            if action.name not in readonly:
                if action.name in {"write_file", "apply_patch", "delete_path", "move_path", "commit", "push"}:
                    raise MissionLoopError("Explorer is read-only")
                raise MissionLoopError(f"unsupported discovery action: {action.name}")
            if not isinstance(action.payload, Mapping):
                raise MissionLoopError("discovery action payload must be an object")

    def discover(self, actions: Sequence[DiscoveryAction]) -> DiscoveryReport:
        self._validate_discovery_actions(actions)
        item = self._start_role(Role.EXPLORER)
        if self._explorer_workspace is None:
            self._explorer_workspace = self._clone(self._workspace_root / "explorer", self.base_commit)
        supporting: list[str] = []
        conflicting: list[str] = []
        relevant: set[str] = set()
        commands: list[tuple[str, ...]] = []
        hypotheses: list[str] = []
        sufficient: str | None = None
        for proposal in actions:
            payload = dict(proposal.payload)
            if proposal.name == "finish_discovery":
                reason = payload.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise MissionLoopError("discovery completion requires an explicit reason")
                sufficient = reason
                continue
            if proposal.name in {"record_evidence", "propose_hypothesis", "request_more_evidence"}:
                text = payload.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise MissionLoopError(f"{proposal.name} requires non-empty text")
                if proposal.name == "propose_hypothesis":
                    hypotheses.append(text)
                self._tool(Role.EXPLORER, proposal.name, Action.READ_REPOSITORY, payload, lambda text=text: ("succeeded", {"text_digest": sha256_digest(text.encode())}))
                continue
            if proposal.name == "list_tree":
                def list_tree() -> tuple[str, dict[str, object]]:
                    paths = sorted(
                        path.relative_to(self._explorer_workspace).as_posix()
                        for path in self._explorer_workspace.rglob("*")
                        if path.is_file() and ".git" not in path.parts
                    )[:500]
                    relevant.update(paths)
                    return "succeeded", {"count": len(paths), "tree_digest": _digest(paths)}
                self._tool(Role.EXPLORER, proposal.name, Action.READ_REPOSITORY, payload, list_tree)
            elif proposal.name in {"read_file", "read_file_range"}:
                relative = self._safe_relative(payload.get("path"))
                def read_file(relative: str = relative) -> tuple[str, dict[str, object]]:
                    file = self._path(self._explorer_workspace, relative)
                    if not file.is_file():
                        return "failed", {"error": "file does not exist", "path": relative}
                    raw = file.read_bytes()
                    if proposal.name == "read_file_range":
                        start = payload.get("start", 1)
                        end = payload.get("end", start)
                        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                            raise MissionLoopError("file ranges must be positive ordered line numbers")
                        raw = b"\n".join(raw.splitlines()[start - 1 : end])
                    relevant.add(relative)
                    text = raw.decode("utf-8", "replace")
                    if _PROMPT_INJECTION.search(text):
                        conflicting.append("prompt-injection text treated as repository data")
                    supporting.append(f"read {relative}")
                    return "succeeded", {"path": relative, "content_digest": sha256_digest(raw), "bytes": len(raw)}
                self._tool(Role.EXPLORER, proposal.name, Action.READ_REPOSITORY, payload, read_file)
            elif proposal.name in {"search_text", "search_symbol"}:
                query = payload.get("query")
                if not isinstance(query, str) or not query:
                    raise MissionLoopError("search requires a non-empty query")
                def search(query: str = query) -> tuple[str, dict[str, object]]:
                    matches: list[str] = []
                    for file in self._explorer_workspace.rglob("*"):
                        if not file.is_file() or ".git" in file.parts or file.is_symlink():
                            continue
                        try:
                            if query in file.read_text(encoding="utf-8", errors="ignore"):
                                matches.append(file.relative_to(self._explorer_workspace).as_posix())
                        except OSError:
                            continue
                    relevant.update(matches)
                    supporting.append(f"search {query} returned {len(matches)} paths")
                    return "succeeded", {"query_digest": sha256_digest(query.encode()), "matches": sorted(matches)[:200]}
                self._tool(Role.EXPLORER, proposal.name, Action.READ_REPOSITORY, payload, search)
            elif proposal.name == "run_read_only_command":
                argv = self._allowed_command(payload.get("argv"))
                outcome_holder: dict[str, object] = {}
                def run_command(argv: tuple[str, ...] = argv) -> tuple[str, dict[str, object]]:
                    outcome, observation = self._command(self._explorer_workspace, argv)
                    outcome_holder.update(observation)
                    return outcome, observation
                receipt = self._tool(Role.EXPLORER, proposal.name, Action.RUN_COMMANDS, payload, run_command)
                commands.append(argv)
                supporting.append(f"read-only command {receipt.outcome}")
            elif proposal.name == "inspect_git_status":
                self._tool(Role.EXPLORER, proposal.name, Action.INSPECT_HISTORY, payload, lambda: self._git_observation(self._explorer_workspace, ("status", "--porcelain")))
            elif proposal.name == "inspect_git_history":
                self._tool(Role.EXPLORER, proposal.name, Action.INSPECT_HISTORY, payload, lambda: self._git_observation(self._explorer_workspace, ("log", "--oneline", "-n", "20")))
            elif proposal.name == "inspect_commit":
                commit = payload.get("commit", self.base_commit)
                if commit != self.base_commit:
                    raise MissionLoopError("Explorer may inspect only the sealed base commit")
                self._tool(Role.EXPLORER, proposal.name, Action.INSPECT_HISTORY, payload, lambda: self._git_observation(self._explorer_workspace, ("show", "--no-patch", str(commit))))
            elif proposal.name == "inspect_build_configuration":
                def inspect_config() -> tuple[str, dict[str, object]]:
                    names = ("pyproject.toml", "package.json", "*.csproj", "Directory.Build.props")
                    found = [name for name in names if list(self._explorer_workspace.glob(name))]
                    relevant.update(found)
                    return "succeeded", {"configuration": found}
                self._tool(Role.EXPLORER, proposal.name, Action.READ_REPOSITORY, payload, inspect_config)
        if sufficient is None:
            raise MissionLoopError("Explorer must explicitly finish discovery")
        if not hypotheses:
            hypotheses.append("sealed acceptance command identifies the repository behavior to repair")
        recommended = Role.ARCHITECT if Role.ARCHITECT in self.plan.roles else Role.BUILDER
        self._discovery = DiscoveryReport(
            hypotheses=tuple(hypotheses),
            supporting_evidence=tuple(supporting),
            conflicting_evidence=tuple(dict.fromkeys(conflicting)),
            unknowns=(),
            relevant_paths=tuple(sorted(relevant)),
            suspected_test_commands=tuple(commands),
            alternatives=("repository text is untrusted data",),
            recommended_next_role=recommended,
            confidence=min(1.0, 0.2 + 0.2 * len(supporting)),
            sufficient_reason=sufficient,
        )
        self._complete_role(Role.EXPLORER, item, f"discovery:{_digest(self._discovery.to_dict())}")
        return self._discovery

    def _git_observation(self, root: Path, argv: Sequence[str]) -> tuple[str, dict[str, object]]:
        code, stdout, stderr = self._git(root, argv, timeout=self.limits.max_command_seconds)
        return (
            "succeeded" if code == 0 else "failed",
            {"argv": list(argv), "exit_code": code, "stdout_digest": sha256_digest(stdout.encode()), "stderr_digest": sha256_digest(stderr.encode())},
        )

    def design(self, design: ArchitectDesign) -> ArchitectDesign:
        if self._discovery is None:
            raise MissionLoopError("Architect requires completed Explorer evidence")
        item = self._start_role(Role.ARCHITECT)
        design.validate(self.objective.acceptance)
        self._policy(Role.ARCHITECT, Action.WRITE_DESIGN, "write_design", design.to_dict())
        self._receipt(Role.ARCHITECT, "write_design", design.to_dict(), "succeeded", {"design_digest": _digest(design.to_dict())})
        self._design = design
        self._complete_role(Role.ARCHITECT, item, f"design:{_digest(design.to_dict())}")
        return design

    def _builder_workspace_for_turn(self) -> Path:
        if self._builder_workspace is None:
            self._builder_workspace = self._clone(self._workspace_root / "builder", self.base_commit)
            self._git(self._builder_workspace, ("config", "user.name", "Hive Mind Builder"), timeout=30)
            self._git(self._builder_workspace, ("config", "user.email", "builder@hive-mind.invalid"), timeout=30)
        return self._builder_workspace

    def _builder_path(self, raw: object) -> str:
        path = self._safe_relative(raw)
        if path in self._sealed_test_paths():
            raise MissionLoopError("Builder may not edit a sealed acceptance test")
        if path not in self.plan.allowed_paths:
            raise MissionLoopError("Builder path is outside allowed paths")
        if Path(path).name in _DEPENDENCY_FILES or path.endswith(".csproj"):
            if self.limits.max_dependency_changes == 0:
                raise MissionLoopError("dependency changes require explicit authorization")
        return path

    def _sealed_test_paths(self) -> set[str]:
        paths: set[str] = set()
        for specification in self.objective.acceptance:
            for argument in specification.argv[1:]:
                if argument.endswith((".py", ".js", ".ts", ".cs", ".sh")) and "/" not in argument and "\\" not in argument:
                    paths.add(argument)
        return paths

    def _check_builder_limits(self) -> None:
        if self._builder_turns >= self.limits.max_turns:
            raise MissionLoopError("Builder turn budget exhausted")
        if self._builder_calls >= self.limits.max_tool_calls:
            raise MissionLoopError("Builder tool-call budget exhausted")

    def _record_builder_action(
        self,
        name: str,
        payload: Mapping[str, object],
        action: Action,
        operation: callable,
    ) -> ToolReceipt:
        self._check_builder_limits()
        self._builder_calls += 1
        return self._tool(Role.BUILDER, name, action, payload, operation)

    def _ensure_diff_limit(self) -> None:
        assert self._builder_workspace is not None
        code, diff, error = self._git(self._builder_workspace, ("diff", "--binary"), timeout=30)
        if code != 0:
            raise MissionLoopError("could not inspect Builder diff: " + error.strip())
        if len(diff.encode("utf-8")) > self.limits.max_diff_bytes:
            raise MissionLoopError("Builder diff exceeds its declared limit")
        if len(self._changed_paths) > self.limits.max_files_changed:
            raise MissionLoopError("Builder changed too many files")

    def _validate_builder_actions(self, actions: Sequence[BuilderAction]) -> None:
        known = {
            "read_file", "read_file_range", "search_text", "search_symbol", "apply_patch", "write_file",
            "delete_path", "move_path", "run_command", "run_tests", "inspect_diff", "inspect_status",
            "checkpoint_candidate", "request_architect_remand", "finish_candidate",
        }
        if not actions:
            raise MissionLoopError("Builder requires at least one typed action")
        for proposed in actions:
            if proposed.name not in known:
                raise MissionLoopError("unknown Builder action")
            if not isinstance(proposed.payload, Mapping):
                raise MissionLoopError("Builder action is malformed")
            payload = proposed.payload
            if proposed.name in {"read_file", "read_file_range", "delete_path"}:
                self._safe_relative(payload.get("path"))
            elif proposed.name == "write_file":
                self._builder_path(payload.get("path"))
                if not isinstance(payload.get("content"), str):
                    raise MissionLoopError("Builder write_file action is malformed")
            elif proposed.name == "apply_patch":
                self._builder_path(payload.get("path"))
                if not isinstance(payload.get("before"), str) or not isinstance(payload.get("after"), str) or not payload.get("before"):
                    raise MissionLoopError("Builder apply_patch action is malformed")
            elif proposed.name == "move_path":
                self._builder_path(payload.get("source"))
                self._builder_path(payload.get("destination"))
            elif proposed.name in {"run_command", "run_tests"}:
                self._allowed_command(payload.get("argv"))
            elif proposed.name == "checkpoint_candidate":
                if not isinstance(payload.get("message"), str) or not str(payload.get("message")).strip():
                    raise MissionLoopError("Builder checkpoint_candidate action is malformed")
            elif proposed.name == "request_architect_remand":
                if not isinstance(payload.get("reason"), str) or not str(payload.get("reason")).strip():
                    raise MissionLoopError("Builder remand requires a reason")

    def _model_context(self) -> dict[str, object]:
        """Return bounded, digest-safe Builder context for one provider action turn."""

        return {
            "mission_id": self._state.mission_id,
            "state_revision": self._state.revision,
            "objective": self.objective.goal,
            "objective_digest": self.objective.digest,
            "base_commit": self.base_commit,
            "candidate_commit": self._candidate,
            "allowed_paths": list(self.plan.allowed_paths),
            "acceptance": [item.to_dict() for item in self.objective.acceptance],
            "discovery": None if self._discovery is None else self._discovery.to_dict(),
            "architecture": None if self._design is None else self._design.to_dict(),
            "prior_receipts": [
                {
                    "ref": receipt.ref,
                    "action": receipt.action,
                    "outcome": receipt.outcome,
                    "observation_digest": receipt.observation_digest,
                }
                for receipt in self._receipts[-16:]
            ],
        }

    def build_from_provider(self, adapter: ModelProviderActionAdapter) -> MissionState:
        """Request one receipted Builder action turn, then execute only valid proposals."""

        if not isinstance(adapter, ModelProviderActionAdapter):
            raise TypeError("Builder model action adapter is required")
        item = self._resume_or_start_builder()
        self._builder_turns += 1
        context = self._model_context()
        proposal_holder: dict[str, object] = {}

        def request_actions() -> tuple[str, dict[str, object]]:
            proposal = adapter.propose(context)
            proposal_holder["proposal"] = proposal
            outcome = "succeeded" if proposal.outcome == "proposed" else (
                "refused" if proposal.outcome == "refused" else "failed"
            )
            return outcome, proposal.observation()

        self._record_builder_action(
            "model_provider_turn",
            {
                "context_digest": _digest(context),
                **adapter.identity,
            },
            Action.MODEL_SYSTEM,
            request_actions,
        )
        proposal = proposal_holder.get("proposal")
        if proposal is None:  # pragma: no cover - executor closure always assigns
            raise MissionLoopError("model provider did not produce an attempt receipt")
        if proposal.outcome != "proposed":
            return self._state
        actions = tuple(
            BuilderAction(action.name, dict(action.payload))
            for action in proposal.actions
        )
        return self._build_actions(actions, item=item)

    def build(self, actions: Sequence[BuilderAction]) -> MissionState:
        return self._build_actions(actions)

    def _build_actions(
        self,
        actions: Sequence[BuilderAction],
        *,
        item: WorkItemState | None = None,
    ) -> MissionState:
        self._validate_builder_actions(actions)
        fingerprint = _digest(
            [
                {"action": action.name, "payload": dict(action.payload)}
                for action in actions
            ]
        )
        repeats = self._progress_fingerprints.get(fingerprint, 0) + 1
        if repeats > self._state.budgets.max_repeated_progress:
            reason = "repeated semantic progress fingerprint stopped the Builder loop"
            self._record(
                MissionEvent(
                    "mission.blocked",
                    Role.ORCHESTRATOR,
                    self._state.revision,
                    {"reason": reason},
                )
            )
            raise MissionLoopError(reason)
        self._progress_fingerprints[fingerprint] = repeats
        if item is None:
            item = self._resume_or_start_builder()
            self._builder_turns += 1
        workspace = self._builder_workspace_for_turn()
        finish = False
        for proposed in actions:
            name = proposed.name
            payload = dict(proposed.payload)
            if name in {"read_file", "read_file_range"}:
                relative = self._safe_relative(payload.get("path"))
                def read(relative: str = relative) -> tuple[str, dict[str, object]]:
                    file = self._path(workspace, relative)
                    if not file.is_file():
                        return "failed", {"error": "file does not exist", "path": relative}
                    raw = file.read_bytes()
                    return "succeeded", {"path": relative, "content_digest": sha256_digest(raw)}
                self._record_builder_action(name, payload, Action.READ_REPOSITORY, read)
            elif name in {"search_text", "search_symbol"}:
                query = payload.get("query")
                if not isinstance(query, str) or not query:
                    raise MissionLoopError("Builder search action is malformed")
                self._record_builder_action(name, payload, Action.READ_REPOSITORY, lambda query=query: self._search_workspace(workspace, query))
            elif name == "write_file":
                path = self._builder_path(payload.get("path"))
                content = payload.get("content")
                if not isinstance(content, str):
                    raise MissionLoopError("Builder write_file action is malformed")
                digest = sha256_digest(content.encode("utf-8"))
                if (path, digest) in self._write_digests:
                    raise MissionLoopError("duplicate Builder write is not meaningful progress")
                def write(path: str = path, content: str = content, digest: str = digest) -> tuple[str, dict[str, object]]:
                    target = self._path(workspace, path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8", newline="")
                    self._write_digests.add((path, digest))
                    self._changed_paths.add(path)
                    self._ensure_diff_limit()
                    return "succeeded", {"path": path, "content_digest": digest}
                self._record_builder_action(name, payload, Action.WRITE_WORKSPACE, write)
            elif name == "apply_patch":
                path = self._builder_path(payload.get("path"))
                before = payload.get("before")
                after = payload.get("after")
                if not isinstance(before, str) or not isinstance(after, str) or not before:
                    raise MissionLoopError("Builder apply_patch action is malformed")
                def patch(path: str = path, before: str = before, after: str = after) -> tuple[str, dict[str, object]]:
                    target = self._path(workspace, path)
                    if not target.is_file():
                        return "failed", {"error": "patch target does not exist", "path": path}
                    current = target.read_text(encoding="utf-8")
                    if before not in current:
                        return "failed", {"error": "patch conflict", "path": path}
                    target.write_text(current.replace(before, after, 1), encoding="utf-8", newline="")
                    self._changed_paths.add(path)
                    self._ensure_diff_limit()
                    return "succeeded", {"path": path, "after_digest": sha256_digest(after.encode())}
                self._record_builder_action(name, payload, Action.WRITE_WORKSPACE, patch)
            elif name == "delete_path":
                path = self._builder_path(payload.get("path"))
                def delete(path: str = path) -> tuple[str, dict[str, object]]:
                    target = self._path(workspace, path)
                    if not target.is_file():
                        return "failed", {"error": "delete target does not exist", "path": path}
                    target.unlink()
                    self._changed_paths.add(path)
                    self._ensure_diff_limit()
                    return "succeeded", {"path": path}
                self._record_builder_action(name, payload, Action.WRITE_WORKSPACE, delete)
            elif name == "move_path":
                source = self._builder_path(payload.get("source"))
                destination = self._builder_path(payload.get("destination"))
                def move(source: str = source, destination: str = destination) -> tuple[str, dict[str, object]]:
                    origin = self._path(workspace, source)
                    target = self._path(workspace, destination)
                    if not origin.is_file() or target.exists():
                        return "failed", {"error": "move source/destination is invalid"}
                    target.parent.mkdir(parents=True, exist_ok=True)
                    origin.replace(target)
                    self._changed_paths.update((source, destination))
                    self._ensure_diff_limit()
                    return "succeeded", {"source": source, "destination": destination}
                self._record_builder_action(name, payload, Action.WRITE_WORKSPACE, move)
            elif name in {"run_command", "run_tests"}:
                argv = self._allowed_command(payload.get("argv"))
                receipt = self._record_builder_action(name, payload, Action.RUN_COMMANDS, lambda argv=argv: self._command(workspace, argv))
                if receipt.outcome != "succeeded":
                    # The failure is retained as a receipt and visible blocker; a later Builder turn may correct it.
                    continue
            elif name == "inspect_diff":
                self._record_builder_action(name, payload, Action.INSPECT_DIFF, lambda: self._git_observation(workspace, ("diff", "--binary")))
            elif name == "inspect_status":
                self._record_builder_action(name, payload, Action.READ_REPOSITORY, lambda: self._git_observation(workspace, ("status", "--porcelain")))
            elif name == "checkpoint_candidate":
                message = payload.get("message")
                if not isinstance(message, str) or not message.strip():
                    raise MissionLoopError("Builder checkpoint_candidate action is malformed")
                def checkpoint(message: str = message) -> tuple[str, dict[str, object]]:
                    dirty, _, error = self._git(workspace, ("diff", "--quiet"), timeout=30)
                    if dirty == 0:
                        return "failed", {"error": "candidate has no meaningful change"}
                    if dirty not in {0, 1}:
                        return "failed", {"error": error.strip() or "could not inspect candidate diff"}
                    status, _, error = self._git(workspace, ("add", "--", *sorted(self._changed_paths)), timeout=30)
                    if status != 0:
                        return "failed", {"error": error.strip()}
                    status, _, error = self._git(workspace, ("commit", "-m", message), timeout=30)
                    if status != 0:
                        return "failed", {"error": error.strip()}
                    code, head, error = self._git(workspace, ("rev-parse", "HEAD"), timeout=30)
                    if code != 0 or _FULL_SHA.fullmatch(head.strip()) is None:
                        return "failed", {"error": error.strip() or "candidate commit did not resolve"}
                    if head.strip() == self.base_commit:
                        return "failed", {"error": "candidate has no meaningful change"}
                    self._candidate = head.strip()
                    code, tree, _ = self._git(workspace, ("rev-parse", "HEAD^{tree}"), timeout=30)
                    return "succeeded", {"candidate_commit": self._candidate, "candidate_tree": tree.strip() if code == 0 else None}
                self._record_builder_action(name, payload, Action.CREATE_BRANCH, checkpoint)
            elif name == "request_architect_remand":
                reason = payload.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    raise MissionLoopError("Builder remand requires a reason")
                self._record_builder_action(name, payload, Action.READ_REPOSITORY, lambda reason=reason: ("succeeded", {"remand_reason": reason}))
                self._record(MissionEvent("claim.disputed", Role.BUILDER, self._state.revision, {"claim_ref": f"architect-remand:{sha256_digest(reason.encode())}"}))
            elif name == "finish_candidate":
                if self._candidate is None:
                    raise MissionLoopError("Builder cannot finish without a checkpointed candidate")
                code, _, error = self._git(workspace, ("status", "--porcelain"), timeout=30)
                if code != 0 or error:
                    raise MissionLoopError("Builder could not inspect final candidate status")
                if self._git(workspace, ("status", "--porcelain"), timeout=30)[1].strip():
                    raise MissionLoopError("Builder must checkpoint every candidate change")
                self._record_builder_action(name, payload, Action.READ_REPOSITORY, lambda: ("succeeded", {"candidate_commit": self._candidate}))
                finish = True
        if not finish:
            return self._state
        self._complete_role(Role.BUILDER, item, f"candidate:{self._candidate}")
        return self._state

    @staticmethod
    def _search_workspace(root: Path, query: str) -> tuple[str, dict[str, object]]:
        matches: list[str] = []
        for file in root.rglob("*"):
            if file.is_file() and ".git" not in file.parts and not file.is_symlink():
                if query in file.read_text(encoding="utf-8", errors="ignore"):
                    matches.append(file.relative_to(root).as_posix())
        return "succeeded", {"query_digest": sha256_digest(query.encode()), "matches": sorted(matches)[:200]}

    def curate(self) -> CuratorResult:
        if self._candidate is None or self._builder_workspace is None:
            raise MissionLoopError("Curator requires an immutable Builder candidate")
        item = self._start_role(Role.CURATOR)
        curator_output = self._workspace_root / f"curator-bundle-{len([r for r in self._receipts if r.role is Role.CURATOR]) + 1}"
        curator_output.mkdir(parents=True, exist_ok=False)
        payload = {"candidate_commit": self._candidate, "base_commit": self.base_commit, "specifications": [item.to_dict() for item in self.objective.acceptance]}
        reports: list[VerificationReport] = []
        candidate_trees: list[str] = []
        findings: list[str] = []
        for specification in self.objective.acceptance:
            bundle = curator_output / specification.identifier
            try:
                report = verify_repository(self._builder_workspace, self._spec_file(specification), bundle, self._candidate)
            except (VerificationError, OSError, ValueError) as error:
                findings.append(f"verification-error:{error}")
                self._receipt(Role.CURATOR, "verify_candidate", payload, "failed", {"error": str(error), "candidate_commit": self._candidate})
                reports = []
                break
            reports.append(report)
            try:
                report_document = json.loads(report.report_path.read_text(encoding="utf-8"))
                candidate_document = report_document["candidate"]
                candidate_tree = str(candidate_document["tree"])
                candidate_commit = str(candidate_document["commit"])
            except (OSError, ValueError, KeyError, TypeError) as error:
                findings.append(f"verification-report-invalid:{error}")
                reports = []
                break
            if candidate_commit != self._candidate or _FULL_SHA.fullmatch(candidate_tree) is None:
                findings.append("verification report is not bound to the candidate commit and tree")
                reports = []
                break
            candidate_trees.append(candidate_tree)
            self._receipt(Role.CURATOR, "verify_candidate", payload, report.verdict, {"candidate_commit": self._candidate, "candidate_tree": candidate_tree, "bundle": str(report.report_path.parent)})
        adopted = bool(reports) and all(report.verdict == "adopt" for report in reports)
        candidate_tree = candidate_trees[0] if candidate_trees else None
        if adopted:
            result = CuratorResult("ADOPT", self._candidate, candidate_tree, curator_output, tuple(findings))
            self._curator = result
            self._complete_role(Role.CURATOR, item, f"curator:{_digest(result.to_dict())}")
            return result
        result = CuratorResult("REMAND_BUILDER", self._candidate, candidate_tree, curator_output if curator_output.exists() else None, tuple(findings or ("sealed acceptance did not adopt candidate",)))
        self._curator = result
        self._complete_role(Role.CURATOR, item, f"curator:{_digest(result.to_dict())}")
        builder_item = next(
            (
                candidate
                for candidate in reversed(self._state.work_items)
                if candidate.role is Role.BUILDER and candidate.status == "succeeded"
            ),
            None,
        )
        if builder_item is None:
            raise MissionLoopError("Curator cannot remand without a completed Builder work item")
        self._record(
            MissionEvent(
                "role.remanded",
                Role.CURATOR,
                self._state.revision,
                {
                    "work_item_id": builder_item.id,
                    "new_work_item_id": f"W-builder-remand-{len(self._events)}",
                    "target_role": Role.BUILDER.value,
                    "reason": "; ".join(result.findings),
                },
            )
        )
        self._record(
            MissionEvent(
                "work.created",
                Role.ORCHESTRATOR,
                self._state.revision,
                {
                    "work_item_id": f"W-curator-remand-{len(self._events)}",
                    "role": Role.CURATOR.value,
                    "instruction": "independently verify the remanded candidate",
                    "allowed_paths": list(self.plan.allowed_paths),
                    "parent_id": builder_item.id,
                },
            )
        )
        return result

    def _spec_file(self, specification: AcceptanceSpecification) -> Path:
        directory = self._workspace_root / "sealed-specifications"
        directory.mkdir(exist_ok=True)
        path = directory / f"{specification.identifier}.json"
        if not path.exists():
            path.write_bytes(_canonical(specification.to_dict()))
        return path

    def complete(self) -> MissionReport:
        if self._curator is None or self._curator.verdict != "ADOPT":
            raise MissionLoopError("mission cannot complete without Curator adoption")
        if self.plan.human_gates:
            raise MissionLoopError(
                "mission completion is blocked by required human gates: "
                + ", ".join(self.plan.human_gates)
            )
        self._record(MissionEvent("mission.succeeded", Role.ORCHESTRATOR, self._state.revision, {}))
        stage = Path(tempfile.mkdtemp(dir=self.output.parent, prefix=f".{self.output.name}-"))
        try:
            (stage / "mission-state.json").write_bytes(_canonical(self._state.to_dict()))
            (stage / "mission-plan.json").write_bytes(_canonical(self.plan.to_dict()))
            (stage / "events.json").write_bytes(_canonical([event.to_dict() for event in self._events]))
            (stage / "tool-receipts.json").write_bytes(_canonical([receipt.to_dict() for receipt in self._receipts]))
            if self._discovery is not None:
                (stage / "discovery.json").write_bytes(_canonical(self._discovery.to_dict()))
            if self._design is not None:
                (stage / "architecture.json").write_bytes(_canonical(self._design.to_dict()))
            (stage / "curator.json").write_bytes(_canonical(self._curator.to_dict()))
            if self._curator.bundle is not None and self._curator.bundle.exists():
                shutil.copytree(self._curator.bundle, stage / "curator-verification")
            manifest = self._integrity_manifest(stage)
            (stage / "integrity.json").write_bytes(_canonical(manifest))
            self.verify_bundle(stage)
            if self.output.exists():
                raise MissionLoopError("mission output appeared during atomic publication")
            os.replace(stage, self.output)
        except BaseException:
            if stage.exists():
                shutil.rmtree(stage)
            raise
        return MissionReport(
            self._state.mission_id,
            self._state.status,
            self.output,
            self._state,
            tuple(self._events),
            tuple(self._receipts),
            self._curator,
        )

    @staticmethod
    def _integrity_manifest(root: Path) -> dict[str, object]:
        files: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != "integrity.json":
                files[path.relative_to(root).as_posix()] = sha256_digest(path.read_bytes())
        return {"schema_version": 1, "files": files, "digest_algorithm": "sha256"}

    @staticmethod
    def verify_bundle(bundle: str | Path) -> None:
        root = Path(bundle)
        integrity = root / "integrity.json"
        if not root.is_dir() or not integrity.is_file():
            raise MissionLoopError("mission bundle has no integrity manifest")
        try:
            document = json.loads(integrity.read_text(encoding="utf-8"))
            expected = document["files"]
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise MissionLoopError(f"mission integrity manifest is invalid: {error}") from None
        if not isinstance(expected, dict):
            raise MissionLoopError("mission integrity files must be an object")
        actual = MissionLoop._integrity_manifest(root)["files"]
        if actual != expected:
            raise MissionLoopError("mission bundle integrity does not self-verify")
        try:
            state = json.loads((root / "mission-state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise MissionLoopError(f"mission state is unavailable: {error}") from None
        if state.get("status") != MissionStatus.SUCCEEDED.value:
            raise MissionLoopError("published mission bundle is not successful")
        try:
            raw_budget = state["budgets"]
            reconstructed = MissionState.intake(
                str(state["mission_id"]),
                str(state["objective_ref"]),
                risk_lane=str(state["risk_lane"]),
                budget=BudgetState(
                    int(raw_budget["max_role_turns"]),
                    int(raw_budget["max_tool_calls"]),
                    int(raw_budget["max_repeated_progress"]),
                ),
            )
            raw_events = json.loads((root / "events.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise MissionLoopError(f"mission transition evidence is invalid: {error}") from None
        if not isinstance(raw_events, list):
            raise MissionLoopError("mission event evidence must be a list")
        for expected_sequence, record in enumerate(raw_events, start=1):
            if not isinstance(record, Mapping):
                raise MissionLoopError("mission event evidence must contain objects")
            try:
                event = MissionEvent(
                    str(record["event_type"]),
                    Role(str(record["actor"])),
                    int(record["expected_revision"]),
                    dict(record["payload"]),
                    int(record["sequence"]),
                )
                recorded_digest = str(record["digest"])
            except (KeyError, TypeError, ValueError) as error:
                raise MissionLoopError(f"mission event record is malformed: {error}") from None
            if event.sequence != expected_sequence or event.digest != recorded_digest:
                raise MissionLoopError("mission event ordering or digest is invalid")
            reconstructed = reduce_mission_state(reconstructed, event)
        if reconstructed.to_dict() != state:
            raise MissionLoopError("mission event history does not reconstruct the published state")
