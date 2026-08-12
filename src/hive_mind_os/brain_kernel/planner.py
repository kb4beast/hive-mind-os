"""Deterministic fixture planning and durable graph persistence for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..contracts import ROLE_NAMES
from .canonical import canonical_digest
from .contracts import Budget, MissionCharter, WorkItem, WorkState
from .events import KernelEvent
from .objectives import ObjectiveGraph
from .store import KernelStore

_FIXTURE_KINDS = frozenset({"bugfix", "feature", "refactor", "docs", "integration"})
_EMPTY_DIGEST = "sha256:" + "0" * 64


@dataclass(frozen=True, slots=True)
class FixturePlan:
    graph: ObjectiveGraph
    kind: str

    @property
    def digest(self) -> str:
        return canonical_digest({"kind": self.kind, "graph_digest": self.graph.digest})


@dataclass(frozen=True, slots=True)
class WorkSchedule:
    """The bounded execution lane for one explicitly planned work item."""

    work_id: str
    budget: Budget
    risk_lane: str
    stop_conditions: tuple[str, ...]
    consultation_roles: tuple[str, ...]
    human_gates: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.work_id.strip():
            raise ValueError("scheduled work id is required")
        if self.risk_lane not in {"R0", "R1", "R2", "R3", "R4"}:
            raise ValueError("scheduled risk lane is invalid")
        if not self.stop_conditions or any(
            not isinstance(value, str) or not value.strip()
            for value in self.stop_conditions
        ):
            raise ValueError("scheduled work needs explicit stop conditions")
        if not self.consultation_roles or any(
            not isinstance(value, str) or value not in ROLE_NAMES
            for value in self.consultation_roles
        ):
            raise ValueError("scheduled work needs registered consultation roles")
        if len(set(self.consultation_roles)) != len(self.consultation_roles):
            raise ValueError("scheduled consultation roles must be unique")
        if any(not isinstance(value, str) or not value.strip() for value in self.human_gates):
            raise ValueError("scheduled human gates must be non-empty strings")
        if len(set(self.human_gates)) != len(self.human_gates):
            raise ValueError("scheduled human gates must be unique")

    def to_document(self) -> dict[str, object]:
        return {
            "work_id": self.work_id,
            "budget": {
                name: getattr(self.budget, name)
                for name in self.budget.__dataclass_fields__
            },
            "risk_lane": self.risk_lane,
            "stop_conditions": list(self.stop_conditions),
            "consultation_roles": list(self.consultation_roles),
            "human_gates": list(self.human_gates),
        }


@dataclass(frozen=True, slots=True)
class OrchestrationPlan:
    """A deterministic DAG plus the non-improvised execution schedule for it."""

    graph: ObjectiveGraph
    schedules: tuple[WorkSchedule, ...]
    replaces_digest: str | None = None
    replan_reason: str | None = None
    replan_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        schedules = tuple(sorted(self.schedules, key=lambda value: value.work_id))
        object.__setattr__(self, "schedules", schedules)
        by_id = {schedule.work_id: schedule for schedule in schedules}
        if len(by_id) != len(schedules) or set(by_id) != {
            item.work_id for item in self.graph.work_items
        }:
            raise ValueError("each planned work item needs exactly one schedule")
        for item in self.graph.work_items:
            schedule = by_id[item.work_id]
            if schedule.risk_lane != item.risk_tier:
                raise ValueError("scheduled risk lane must match work item risk tier")
            if not set(schedule.human_gates).issubset(self.graph.charter.human_gates):
                raise ValueError("scheduled human gate is not chartered")
            for name in schedule.budget.__dataclass_fields__:
                if getattr(schedule.budget, name) > getattr(self.graph.charter.budget, name):
                    raise ValueError("scheduled budget exceeds charter budget")
        revising = self.replaces_digest is not None
        if revising != (self.replan_reason is not None):
            raise ValueError("replan digest and reason must be supplied together")
        if self.replaces_digest is not None:
            if not self.replaces_digest.startswith("sha256:"):
                raise ValueError("replan digest is invalid")
            if not self.replan_reason or not self.replan_reason.strip():
                raise ValueError("replan reason is required")
            if not self.replan_evidence_refs:
                raise ValueError("replan evidence is required")
        elif self.replan_evidence_refs:
            raise ValueError("initial plan cannot contain replan evidence")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> dict[str, object]:
        return {
            "graph_digest": self.graph.digest,
            "work_items": [
                item.to_document() for item in self.graph.ordered_items()
            ],
            "schedules": [schedule.to_document() for schedule in self.schedules],
            "replaces_digest": self.replaces_digest,
            "replan_reason": self.replan_reason,
            "replan_evidence_refs": list(self.replan_evidence_refs),
        }


class OrchestratorPlanner:
    """Build and revise bounded work DAGs without executing any scheduled work."""

    def plan(
        self,
        charter: MissionCharter,
        work_items: Iterable[WorkItem],
        schedules: Iterable[WorkSchedule],
    ) -> OrchestrationPlan:
        return OrchestrationPlan(ObjectiveGraph(charter, work_items), tuple(schedules))

    def replan(
        self,
        previous: OrchestrationPlan,
        work_items: Iterable[WorkItem],
        schedules: Iterable[WorkSchedule],
        *,
        reason: str,
        evidence_refs: Iterable[str],
    ) -> OrchestrationPlan:
        candidate = self.plan(previous.graph.charter, work_items, schedules)
        evidence = tuple(evidence_refs)
        if (
            candidate.graph.digest == previous.graph.digest
            and candidate.schedules == previous.schedules
        ):
            raise ValueError("replan must change the planned graph or schedule")
        return OrchestrationPlan(
            candidate.graph,
            candidate.schedules,
            replaces_digest=previous.digest,
            replan_reason=reason,
            replan_evidence_refs=evidence,
        )


class DeterministicFixturePlanner:
    """A local-only planner; it accepts no model output and grants no authority."""

    def plan(self, charter: MissionCharter, kind: str) -> FixturePlan:
        if kind not in _FIXTURE_KINDS:
            raise ValueError("unsupported fixture plan kind")
        seed = canonical_digest(
            {
                "mission_id": charter.mission_id,
                "objective": charter.objective,
                "acceptance_specs": charter.acceptance_specs,
                "kind": kind,
            }
        )[-12:]
        root_id = f"WORK-{kind}-aggregate-{seed}"
        leaf_id = f"WORK-{kind}-implementation-{seed}"
        leaf = WorkItem(
            work_id=leaf_id,
            mission_id=charter.mission_id,
            parent_work_id=root_id,
            depth=1,
            title=f"{kind} implementation",
            objective=charter.objective,
            role="builder",
            risk_tier="R1",
            dependencies=(),
            required_inputs=(),
            expected_outputs=(f"fixture:{kind}",),
            acceptance_specs=charter.acceptance_specs,
            write_scope=(f"fixtures/{kind}.txt",),
            requested_actions=(),
            context_request={"fixture_kind": kind},
            max_attempts=1,
            status=WorkState.PROPOSED,
            authority_envelope_digest=_EMPTY_DIGEST,
            idempotency_key=canonical_digest({"work_id": leaf_id}),
        )
        aggregate = WorkItem(
            work_id=root_id,
            mission_id=charter.mission_id,
            parent_work_id=None,
            depth=0,
            title=f"{kind} aggregate",
            objective=charter.objective,
            role="orchestrator",
            risk_tier="R0",
            dependencies=(leaf_id,),
            required_inputs=(f"fixture:{kind}",),
            expected_outputs=(),
            acceptance_specs=(),
            write_scope=(),
            requested_actions=(),
            context_request={"fixture_kind": kind},
            max_attempts=1,
            status=WorkState.PROPOSED,
            authority_envelope_digest=_EMPTY_DIGEST,
            idempotency_key=canonical_digest({"work_id": root_id}),
        )
        return FixturePlan(ObjectiveGraph(charter, (aggregate, leaf)), kind)


def persist_plan(store: KernelStore, plan: FixturePlan | OrchestrationPlan) -> tuple[int, ...]:
    """Append a plan's typed work facts; identical retries are idempotent."""

    sequences: list[int] = []
    replaces_digest = getattr(plan, "replaces_digest", None)
    if replaces_digest is not None:
        known_digests = {
            payload["plan_digest"]
            for row in store.events()
            if row["event_type"] == "work.created"
            and isinstance((payload := row["payload"]), dict)
            and isinstance(payload.get("plan_digest"), str)
        }
        if replaces_digest not in known_digests:
            raise ValueError("replan does not reference a durable prior plan")
    projected_work = store.projection()["work"]
    if replaces_digest is not None:
        reused_ids = sorted(
            set(projected_work).intersection(item.work_id for item in plan.graph.work_items)
        )
        if reused_ids:
            raise ValueError("replan must use replacement work ids to remain append-only")
    existing_plan_items: list[dict[str, object]] = []
    for row in store.events():
        payload = row["payload"]
        if (
            row["event_type"] == "work.created"
            and isinstance(payload, dict)
            and "plan_digest" in payload
            and payload["plan_digest"] != plan.digest
            and row["work_id"] in projected_work
            and projected_work[row["work_id"]]["status"] == WorkState.PROPOSED.value
        ):
            existing_plan_items.append(row)
    for row in existing_plan_items:
        previous = store.events()[-1]["digest"]
        store.append(
            KernelEvent(
                event_id=f"supersede:{plan.digest}:{row['work_id']}",
                mission_id=str(row["mission_id"]),
                event_type="work.transition",
                actor_id="kernel-fixture-planner",
                occurred_at="1970-01-01T00:00:00Z",
                payload={"status": "SUPERSEDED", "superseded_by": plan.digest},
                work_id=str(row["work_id"]),
                actor_role="orchestrator",
                previous_digest=previous,
            ),
            idempotency_key=canonical_digest(
                {"plan_digest": plan.digest, "supersedes": row["work_id"]}
            ),
        )
    for item in plan.graph.ordered_items():
        existing = [row for row in store.events() if row["event_id"] == f"plan:{plan.digest}:{item.work_id}"]
        if existing:
            sequences.append(int(existing[0]["sequence"]))
            continue
        previous = store.events()[-1]["digest"] if store.events() else None
        payload: dict[str, object] = {
            "work_item": item.to_document(),
            "plan_digest": plan.digest,
        }
        if isinstance(plan, OrchestrationPlan) and plan.replaces_digest is not None:
            payload["replan"] = {
                "from_plan_digest": plan.replaces_digest,
                "reason": plan.replan_reason,
                "evidence_refs": list(plan.replan_evidence_refs),
            }
        sequences.append(
            store.append(
                KernelEvent(
                    event_id=f"plan:{plan.digest}:{item.work_id}",
                    mission_id=item.mission_id,
                    event_type="work.created",
                    actor_id=(
                        "kernel-orchestrator-planner"
                        if isinstance(plan, OrchestrationPlan)
                        else "kernel-fixture-planner"
                    ),
                    occurred_at="1970-01-01T00:00:00Z",
                    payload=payload,
                    work_id=item.work_id,
                    actor_role="orchestrator",
                    previous_digest=previous,
                ),
                idempotency_key=canonical_digest({"plan_digest": plan.digest, "work_id": item.work_id}),
            )
        )
    return tuple(sequences)


def graph_from_events(charter: MissionCharter, events: Iterable[dict[str, object]]) -> ObjectiveGraph:
    """Rehydrate the planner graph from typed, durable work-created event payloads."""

    documents_by_plan: dict[str, list[dict[str, object]]] = {}
    latest_plan: str | None = None
    for event in events:
        if event.get("event_type") != "work.created":
            continue
        payload = event.get("payload")
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("work_item"), dict)
            and isinstance(payload.get("plan_digest"), str)
        ):
            plan_digest = payload["plan_digest"]
            documents_by_plan.setdefault(plan_digest, []).append(payload["work_item"])
            latest_plan = plan_digest
    if latest_plan is None:
        raise ValueError("kernel mission has no durable plan")
    return ObjectiveGraph.from_documents(charter, documents_by_plan[latest_plan])
