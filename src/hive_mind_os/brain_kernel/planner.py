"""Deterministic fixture planning and durable graph persistence for Phase 3."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from ..contracts import ROLE_NAMES
from .canonical import canonical_digest
from .contracts import Budget, MissionCharter, MissionState, WorkItem, WorkState
from .events import KernelEvent
from .objectives import ObjectiveGraph
from .projection import reduce_event
from .store import KernelStore

_FIXTURE_KINDS = frozenset({"bugfix", "feature", "refactor", "docs", "integration"})
_EMPTY_DIGEST = "sha256:" + "0" * 64
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_REPLANS = 2
_CONSUMPTIVE_BUDGET_FIELDS = (
    "max_wall_seconds",
    "max_model_calls",
    "max_input_tokens",
    "max_output_tokens",
    "max_cost_microunits",
    "max_tool_calls",
)
_STRUCTURAL_BUDGET_FIELDS = ("max_work_items", "max_depth")
_TERMINAL_WORK_STATES = frozenset(
    {
        WorkState.INTEGRATED,
        WorkState.TERMINAL_FAILED,
        WorkState.CANCELLED,
        WorkState.SUPERSEDED,
    }
)
_INITIAL_MISSION_STATES = frozenset({MissionState.CREATED, MissionState.PLANNING})
_REPLAN_MISSION_STATES = frozenset(
    {
        MissionState.CREATED,
        MissionState.PLANNING,
        MissionState.READY,
        MissionState.RUNNING,
        MissionState.WAITING_HUMAN,
        MissionState.PAUSED,
    }
)


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
        if len(self.consultation_roles) < 2:
            raise ValueError("scheduled consultation needs two distinct roles")
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

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> WorkSchedule:
        if set(document) != {
            "work_id",
            "budget",
            "risk_lane",
            "stop_conditions",
            "consultation_roles",
            "human_gates",
        }:
            raise ValueError("durable work schedule has an invalid shape")
        budget = document.get("budget")
        if not isinstance(budget, Mapping) or set(budget) != set(Budget.__dataclass_fields__):
            raise ValueError("durable work schedule budget has an invalid shape")
        if any(
            not isinstance(document.get(name), list)
            for name in ("stop_conditions", "consultation_roles", "human_gates")
        ):
            raise ValueError("durable work schedule collections must be lists")
        try:
            return cls(
                work_id=cast(str, document["work_id"]),
                budget=Budget(**{name: budget[name] for name in Budget.__dataclass_fields__}),
                risk_lane=cast(str, document["risk_lane"]),
                stop_conditions=tuple(cast(Iterable[str], document["stop_conditions"])),
                consultation_roles=tuple(cast(Iterable[str], document["consultation_roles"])),
                human_gates=tuple(cast(Iterable[str], document["human_gates"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("durable work schedule is invalid") from error


def _validate_total_budget(
    charter_budget: Budget,
    schedules: Iterable[WorkSchedule],
) -> None:
    schedules = tuple(schedules)
    for name in _CONSUMPTIVE_BUDGET_FIELDS:
        if sum(getattr(schedule.budget, name) for schedule in schedules) > getattr(
            charter_budget, name
        ):
            raise ValueError("aggregate scheduled budget exceeds charter budget")
    for schedule in schedules:
        if any(
            getattr(schedule.budget, name) > getattr(charter_budget, name)
            for name in _STRUCTURAL_BUDGET_FIELDS
        ):
            raise ValueError("scheduled structural limit exceeds charter budget")


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
            if item.status is not WorkState.PROPOSED:
                raise ValueError("newly planned work must be PROPOSED")
            schedule = by_id[item.work_id]
            if schedule.risk_lane != item.risk_tier:
                raise ValueError("scheduled risk lane must match work item risk tier")
            if not set(schedule.human_gates).issubset(self.graph.charter.human_gates):
                raise ValueError("scheduled human gate is not chartered")
            if item.role in schedule.consultation_roles:
                raise ValueError("scheduled consultation cannot include the requesting role")
        _validate_total_budget(self.graph.charter.budget, schedules)
        revising = self.replaces_digest is not None
        if revising != (self.replan_reason is not None):
            raise ValueError("replan digest and reason must be supplied together")
        if revising:
            if not isinstance(self.replaces_digest, str) or _DIGEST.fullmatch(
                self.replaces_digest
            ) is None:
                raise ValueError("replan digest is invalid")
            if not isinstance(self.replan_reason, str) or not self.replan_reason.strip():
                raise ValueError("replan reason is required")
            if not self.replan_evidence_refs or any(
                not isinstance(value, str) or not value.strip()
                for value in self.replan_evidence_refs
            ):
                raise ValueError("replan evidence is required")
            if len(set(self.replan_evidence_refs)) != len(self.replan_evidence_refs):
                raise ValueError("replan evidence must be unique")
        elif self.replan_evidence_refs:
            raise ValueError("initial plan cannot contain replan evidence")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> dict[str, object]:
        return {
            "charter_digest": self.graph.charter.digest(),
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
        _validate_total_budget(
            previous.graph.charter.budget,
            (*previous.schedules, *candidate.schedules),
        )
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


def _plan_rows(
    events: Iterable[Mapping[str, Any]], mission_id: str
) -> list[Mapping[str, Any]]:
    return [
        row
        for row in events
        if row.get("event_type") == "work.created"
        and row.get("mission_id") == mission_id
        and isinstance(row.get("payload"), Mapping)
        and isinstance(cast(Mapping[str, object], row["payload"]).get("plan_digest"), str)
    ]


def _is_orchestration_row(row: Mapping[str, Any]) -> bool:
    payload = row.get("payload")
    return row.get("actor_id") == "kernel-orchestrator-planner" or (
        isinstance(payload, Mapping) and isinstance(payload.get("schedule"), Mapping)
    )


def _payload_for_item(
    plan: FixturePlan | OrchestrationPlan,
    item: WorkItem,
    schedules: Mapping[str, WorkSchedule],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "work_item": item.to_document(),
        "plan_digest": plan.digest,
    }
    if isinstance(plan, OrchestrationPlan):
        payload["charter_digest"] = plan.graph.charter.digest()
        payload["schedule"] = schedules[item.work_id].to_document()
        if plan.replaces_digest is not None:
            payload["replan"] = {
                "from_plan_digest": plan.replaces_digest,
                "reason": plan.replan_reason,
                "evidence_refs": list(plan.replan_evidence_refs),
            }
    return payload


def _event_document(event: KernelEvent) -> dict[str, object]:
    return {
        "event_type": event.event_type,
        "mission_id": event.mission_id,
        "work_id": event.work_id,
        "actor_role": event.actor_role,
        "payload": dict(event.payload),
    }


def persist_plan(store: KernelStore, plan: FixturePlan | OrchestrationPlan) -> tuple[int, ...]:
    """Preflight and append one mission-bound plan; exact retries are read-only."""

    events = store.events()
    projection = store.projection()
    mission_id = plan.graph.charter.mission_id
    mission_status_value = projection["missions"].get(mission_id)
    if mission_status_value is None:
        raise ValueError("plan belongs to an unknown durable mission")
    operational = isinstance(plan, OrchestrationPlan)
    actor_id = "kernel-orchestrator-planner" if operational else "kernel-fixture-planner"
    ordered_items = plan.graph.ordered_items()
    schedules = {schedule.work_id: schedule for schedule in plan.schedules} if operational else {}
    desired_payloads = {
        item.work_id: _payload_for_item(plan, item, schedules) for item in ordered_items
    }
    event_ids = {f"plan:{plan.digest}:{item.work_id}" for item in ordered_items}
    matching = [row for row in events if row.get("event_id") in event_ids]
    if matching:
        if len(matching) != len(ordered_items):
            raise ValueError("durable plan is incomplete")
        by_work = {str(row["work_id"]): row for row in matching}
        if set(by_work) != set(desired_payloads) or any(
            row.get("mission_id") != mission_id
            or row.get("event_type") != "work.created"
            or row.get("actor_id") != actor_id
            or row.get("actor_role") != "orchestrator"
            or row.get("occurred_at") != "1970-01-01T00:00:00Z"
            or row.get("recorded_at") != "1970-01-01T00:00:00Z"
            or row.get("payload") != desired_payloads[work_id]
            for work_id, row in by_work.items()
        ):
            raise ValueError("durable plan retry conflicts with existing evidence")
        for item in ordered_items:
            row = by_work[item.work_id]
            try:
                sequence = store.append(
                    KernelEvent(
                        event_id=str(row["event_id"]),
                        mission_id=str(row["mission_id"]),
                        event_type=str(row["event_type"]),
                        actor_id=str(row["actor_id"]),
                        occurred_at=str(row["occurred_at"]),
                        payload=cast(Mapping[str, object], row["payload"]),
                        work_id=str(row["work_id"]),
                        actor_role=str(row["actor_role"]),
                        previous_digest=cast(str | None, row["previous_digest"]),
                    ),
                    idempotency_key=canonical_digest(
                        {"plan_digest": plan.digest, "work_id": item.work_id}
                    ),
                )
            except Exception as error:
                raise ValueError("durable plan retry lacks its exact idempotency binding") from error
            if sequence != int(row["sequence"]):
                raise ValueError("durable plan retry idempotency sequence is invalid")
        return tuple(int(by_work[item.work_id]["sequence"]) for item in ordered_items)

    mission_status = MissionState(mission_status_value)
    allowed_states = (
        _REPLAN_MISSION_STATES
        if operational and plan.replaces_digest is not None
        else _INITIAL_MISSION_STATES
    )
    if mission_status not in allowed_states:
        raise ValueError("durable mission state is not planning-eligible")

    mission_rows = _plan_rows(events, mission_id)
    operational_rows = [row for row in mission_rows if _is_orchestration_row(row)]
    fixture_rows = [row for row in mission_rows if not _is_orchestration_row(row)]
    operational_digests = list(
        dict.fromkeys(str(cast(Mapping[str, object], row["payload"])["plan_digest"]) for row in operational_rows)
    )
    superseded_rows: list[Mapping[str, Any]] = []
    if operational:
        if fixture_rows:
            raise ValueError("mission cannot mix fixture and operational planner kinds")
        if plan.replaces_digest is None:
            if operational_digests:
                raise ValueError("mission already has a durable operational plan")
        else:
            if not operational_digests or plan.replaces_digest != operational_digests[-1]:
                raise ValueError("replan must replace the current same-mission durable plan")
            if len(operational_digests) - 1 >= _MAX_REPLANS:
                raise ValueError("mission replan limit is exhausted")
            previous_rows = [
                row
                for row in operational_rows
                if cast(Mapping[str, object], row["payload"])["plan_digest"]
                == plan.replaces_digest
            ]
            prior_schedules: list[WorkSchedule] = []
            for row in operational_rows:
                payload = cast(Mapping[str, object], row["payload"])
                if payload.get("charter_digest") != plan.graph.charter.digest():
                    raise ValueError("replan charter differs from durable predecessor")
                schedule_document = payload.get("schedule")
                if not isinstance(schedule_document, Mapping):
                    raise ValueError("durable prior plan omits its work schedule")
                prior_schedules.append(WorkSchedule.from_document(schedule_document))
            _validate_total_budget(
                plan.graph.charter.budget,
                (*prior_schedules, *plan.schedules),
            )
            for row in previous_rows:
                work_id = str(row["work_id"])
                state = WorkState(projection["work"][work_id]["status"])
                if state is WorkState.PROPOSED:
                    superseded_rows.append(row)
                elif state not in _TERMINAL_WORK_STATES:
                    raise ValueError("replan requires every active predecessor to be reconciled")
            for row in operational_rows:
                if row in previous_rows:
                    continue
                work_id = str(row["work_id"])
                state = WorkState(projection["work"][work_id]["status"])
                if state not in _TERMINAL_WORK_STATES:
                    raise ValueError("durable operational plan history has active stale work")
    else:
        if operational_rows:
            raise ValueError("mission cannot mix fixture and operational planner kinds")
        superseded_rows = [
            row
            for row in mission_rows
            if not _is_orchestration_row(row)
            and cast(Mapping[str, object], row["payload"])["plan_digest"] != plan.digest
            and projection["work"].get(str(row["work_id"]), {}).get("status")
            == WorkState.PROPOSED.value
        ]

    reused_ids = sorted(
        set(projection["work"]).intersection(item.work_id for item in ordered_items)
    )
    if reused_ids:
        raise ValueError("plan must use new work ids to remain append-only")
    existing_event_ids = {str(row["event_id"]) for row in events}
    transition_ids = {
        f"supersede:{plan.digest}:{row['work_id']}" for row in superseded_rows
    }
    if existing_event_ids.intersection(event_ids | transition_ids):
        raise ValueError("plan event identity is already bound")

    previous = str(events[-1]["digest"]) if events else None
    pending: list[tuple[KernelEvent, str, bool]] = []
    for row in superseded_rows:
        event = KernelEvent(
            event_id=f"supersede:{plan.digest}:{row['work_id']}",
            mission_id=mission_id,
            event_type="work.transition",
            actor_id=actor_id,
            occurred_at="1970-01-01T00:00:00Z",
            payload={"status": "SUPERSEDED", "superseded_by": plan.digest},
            work_id=str(row["work_id"]),
            actor_role="orchestrator",
            previous_digest=previous,
        )
        previous = event.digest_for(previous)
        pending.append(
            (event, canonical_digest({"plan_digest": plan.digest, "supersedes": row["work_id"]}), False)
        )
    for item in ordered_items:
        event = KernelEvent(
            event_id=f"plan:{plan.digest}:{item.work_id}",
            mission_id=mission_id,
            event_type="work.created",
            actor_id=actor_id,
            occurred_at="1970-01-01T00:00:00Z",
            payload=desired_payloads[item.work_id],
            work_id=item.work_id,
            actor_role="orchestrator",
            previous_digest=previous,
        )
        previous = event.digest_for(previous)
        pending.append(
            (event, canonical_digest({"plan_digest": plan.digest, "work_id": item.work_id}), True)
        )

    simulated = {
        "missions": dict(projection["missions"]),
        "work": {key: dict(value) for key, value in projection["work"].items()},
    }
    try:
        for event, _, _ in pending:
            simulated = reduce_event(simulated, _event_document(event))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("plan cannot be reduced without partial persistence") from error

    sequences: list[int] = []
    expected_sequence = int(events[-1]["sequence"]) if events else 0
    for event, idempotency_key, is_creation in pending:
        sequence = store.append(
            event,
            expected_sequence=expected_sequence,
            idempotency_key=idempotency_key,
        )
        expected_sequence = sequence
        if is_creation:
            sequences.append(sequence)
    return tuple(sequences)


def graph_from_events(charter: MissionCharter, events: Iterable[dict[str, object]]) -> ObjectiveGraph:
    """Rehydrate the planner graph from typed, durable work-created event payloads."""

    events = tuple(events)
    mission_rows = _plan_rows(events, charter.mission_id)
    if any(_is_orchestration_row(row) for row in mission_rows):
        return orchestration_plan_from_events(charter, events).graph
    documents_by_plan: dict[str, list[dict[str, object]]] = {}
    latest_plan: str | None = None
    for event in events:
        if (
            event.get("event_type") != "work.created"
            or event.get("mission_id") != charter.mission_id
        ):
            continue
        payload = event.get("payload")
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("work_item"), dict)
            and isinstance(payload.get("plan_digest"), str)
        ):
            plan_digest = payload["plan_digest"]
            work_document = payload["work_item"]
            work_id = work_document.get("work_id")
            if (
                not isinstance(work_id, str)
                or event.get("work_id") != work_id
                or event.get("event_id") != f"plan:{plan_digest}:{work_id}"
                or event.get("actor_id") != "kernel-fixture-planner"
                or event.get("actor_role") != "orchestrator"
                or event.get("occurred_at") != "1970-01-01T00:00:00Z"
            ):
                raise ValueError("durable fixture plan event provenance is invalid")
            documents_by_plan.setdefault(plan_digest, []).append(payload["work_item"])
            latest_plan = plan_digest
    if latest_plan is None:
        raise ValueError("kernel mission has no durable plan")
    return ObjectiveGraph.from_documents(charter, documents_by_plan[latest_plan])


def orchestration_plan_from_events(
    charter: MissionCharter,
    events: Iterable[dict[str, object]],
) -> OrchestrationPlan:
    """Restore the latest complete mission-bound operational plan and schedules."""

    rows = [
        row
        for row in _plan_rows(events, charter.mission_id)
        if _is_orchestration_row(row)
    ]
    if not rows:
        raise ValueError("kernel mission has no durable orchestration plan")
    latest_digest = cast(Mapping[str, object], rows[-1]["payload"])["plan_digest"]
    selected = [
        row
        for row in rows
        if cast(Mapping[str, object], row["payload"])["plan_digest"] == latest_digest
    ]
    work_documents: list[Mapping[str, object]] = []
    schedules: list[WorkSchedule] = []
    replan_document: Mapping[str, object] | None = None
    for row in selected:
        payload = cast(Mapping[str, object], row["payload"])
        if payload.get("charter_digest") != charter.digest():
            raise ValueError("durable plan is bound to another charter")
        work_document = payload.get("work_item")
        schedule_document = payload.get("schedule")
        if not isinstance(work_document, Mapping) or not isinstance(schedule_document, Mapping):
            raise ValueError("durable orchestration plan is incomplete")
        work_id = work_document.get("work_id")
        schedule_work_id = schedule_document.get("work_id")
        if (
            not isinstance(work_id, str)
            or schedule_work_id != work_id
            or row.get("work_id") != work_id
            or row.get("event_id") != f"plan:{latest_digest}:{work_id}"
            or row.get("actor_id") != "kernel-orchestrator-planner"
            or row.get("actor_role") != "orchestrator"
            or row.get("occurred_at") != "1970-01-01T00:00:00Z"
        ):
            raise ValueError("durable orchestration event provenance is invalid")
        work_documents.append(work_document)
        schedules.append(WorkSchedule.from_document(schedule_document))
        row_replan = payload.get("replan")
        if row_replan is not None:
            if not isinstance(row_replan, Mapping):
                raise ValueError("durable replan evidence is invalid")
            if replan_document is not None and row_replan != replan_document:
                raise ValueError("durable replan evidence is inconsistent")
            replan_document = row_replan
    graph = ObjectiveGraph.from_documents(charter, work_documents)
    if replan_document is None:
        restored = OrchestrationPlan(graph, tuple(schedules))
    else:
        evidence = replan_document.get("evidence_refs")
        if not isinstance(evidence, list):
            raise ValueError("durable replan evidence is invalid")
        restored = OrchestrationPlan(
            graph,
            tuple(schedules),
            replaces_digest=cast(str, replan_document.get("from_plan_digest")),
            replan_reason=cast(str, replan_document.get("reason")),
            replan_evidence_refs=tuple(cast(list[str], evidence)),
        )
    if restored.digest != latest_digest:
        raise ValueError("durable orchestration plan digest is invalid")
    return restored
