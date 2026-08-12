"""Deterministic, mission-scoped planning and atomic durable graph persistence."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, cast

from ..contracts import ROLE_NAMES
from .canonical import canonical_digest
from .contracts import Budget, MissionCharter, MissionState, WorkItem, WorkState
from .events import KernelEvent
from .objectives import ObjectiveGraph
from .store import KernelStore

_FIXTURE_KINDS = frozenset({"bugfix", "feature", "refactor", "docs", "integration"})
_EMPTY_DIGEST = "sha256:" + "0" * 64
_PLAN_SCHEMA_VERSION = 1
_FIXTURE_PLANNER_KIND = "fixture-v1"
_ORCHESTRATOR_PLANNER_KIND = "orchestration-v1"
_MAX_REVISIONS = 2
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_TERMINAL_MISSION_STATES = {
    MissionState.COMPLETED.value,
    MissionState.FAILED.value,
    MissionState.CANCELLED.value,
}
_PLANNING_MISSION_STATES = {
    MissionState.CREATED.value,
    MissionState.PLANNING.value,
    MissionState.READY.value,
    MissionState.PAUSED.value,
}
_CONSUMPTIVE_BUDGET_FIELDS = (
    "max_wall_seconds",
    "max_model_calls",
    "max_input_tokens",
    "max_output_tokens",
    "max_cost_microunits",
    "max_tool_calls",
)


def _budget_document(budget: Budget) -> dict[str, int]:
    return {name: cast(int, getattr(budget, name)) for name in budget.__dataclass_fields__}


def _budget_from_document(document: Mapping[str, object]) -> Budget:
    try:
        return Budget(**{name: document[name] for name in Budget.__dataclass_fields__})
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("scheduled budget is invalid") from error


def _require_trimmed_unique(values: Iterable[str], label: str, *, minimum: int = 0) -> tuple[str, ...]:
    result = tuple(values)
    if len(result) < minimum:
        raise ValueError(f"{label} requires at least {minimum} values")
    if any(type(value) is not str or not value.strip() or value != value.strip() for value in result):
        raise ValueError(f"{label} must contain exact non-empty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} must be unique")
    return result


def _schedule_budget_totals(schedules: Iterable[WorkSchedule]) -> dict[str, int]:
    totals = {name: 0 for name in _CONSUMPTIVE_BUDGET_FIELDS}
    for schedule in schedules:
        for name in totals:
            totals[name] += cast(int, getattr(schedule.budget, name))
    return totals


def _assert_budget_within(used: Mapping[str, int], limit: Budget, *, label: str) -> None:
    for name, value in used.items():
        if value > cast(int, getattr(limit, name)):
            raise ValueError(f"{label} exceeds charter {name}")


@dataclass(frozen=True, slots=True)
class FixturePlan:
    graph: ObjectiveGraph
    kind: str

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "schema_version": _PLAN_SCHEMA_VERSION,
                "planner_kind": _FIXTURE_PLANNER_KIND,
                "kind": self.kind,
                "charter_digest": self.graph.charter.digest(),
                "graph_digest": self.graph.digest,
            }
        )


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
        if type(self.work_id) is not str or not self.work_id.strip() or self.work_id != self.work_id.strip():
            raise ValueError("scheduled work id is required")
        if self.risk_lane not in {"R0", "R1", "R2", "R3", "R4"}:
            raise ValueError("scheduled risk lane is invalid")
        object.__setattr__(
            self,
            "stop_conditions",
            _require_trimmed_unique(self.stop_conditions, "scheduled stop conditions", minimum=1),
        )
        roles = _require_trimmed_unique(
            self.consultation_roles,
            "scheduled consultation roles",
            minimum=2,
        )
        if any(role not in ROLE_NAMES for role in roles):
            raise ValueError("scheduled work needs registered consultation roles")
        object.__setattr__(self, "consultation_roles", roles)
        object.__setattr__(
            self,
            "human_gates",
            _require_trimmed_unique(self.human_gates, "scheduled human gates"),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "work_id": self.work_id,
            "budget": _budget_document(self.budget),
            "risk_lane": self.risk_lane,
            "stop_conditions": list(self.stop_conditions),
            "consultation_roles": list(self.consultation_roles),
            "human_gates": list(self.human_gates),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> WorkSchedule:
        try:
            budget = document["budget"]
            if not isinstance(budget, Mapping):
                raise ValueError("scheduled budget is invalid")
            return cls(
                work_id=cast(str, document["work_id"]),
                budget=_budget_from_document(budget),
                risk_lane=cast(str, document["risk_lane"]),
                stop_conditions=tuple(cast(Iterable[str], document["stop_conditions"])),
                consultation_roles=tuple(cast(Iterable[str], document["consultation_roles"])),
                human_gates=tuple(cast(Iterable[str], document["human_gates"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("scheduled work document is invalid") from error


@dataclass(frozen=True, slots=True)
class OrchestrationPlan:
    """A deterministic DAG plus the non-improvised execution schedule for it."""

    graph: ObjectiveGraph
    schedules: tuple[WorkSchedule, ...]
    replaces_digest: str | None = None
    replan_reason: str | None = None
    replan_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        schedules = tuple(sorted(tuple(self.schedules), key=lambda value: value.work_id))
        object.__setattr__(self, "schedules", schedules)
        by_id = {schedule.work_id: schedule for schedule in schedules}
        if len(by_id) != len(schedules) or set(by_id) != {
            item.work_id for item in self.graph.work_items
        }:
            raise ValueError("each planned work item needs exactly one schedule")
        for item in self.graph.work_items:
            if item.status is not WorkState.PROPOSED:
                raise ValueError("new plans require PROPOSED work items")
            schedule = by_id[item.work_id]
            if schedule.risk_lane != item.risk_tier:
                raise ValueError("scheduled risk lane must match work item risk tier")
            if item.role in schedule.consultation_roles:
                raise ValueError("consultation route cannot include the requesting work role")
            if not set(schedule.human_gates).issubset(self.graph.charter.human_gates):
                raise ValueError("scheduled human gate is not chartered")
            for name in schedule.budget.__dataclass_fields__:
                if getattr(schedule.budget, name) > getattr(self.graph.charter.budget, name):
                    raise ValueError("scheduled budget exceeds charter budget")
        _assert_budget_within(
            _schedule_budget_totals(schedules),
            self.graph.charter.budget,
            label="total consumptive schedule budget",
        )

        revising = self.replaces_digest is not None
        if revising != (self.replan_reason is not None):
            raise ValueError("replan digest and reason must be supplied together")
        if self.replaces_digest is not None:
            if type(self.replaces_digest) is not str or _DIGEST.fullmatch(self.replaces_digest) is None:
                raise ValueError("replan digest must be lowercase sha256:<64 hex>")
            if type(self.replan_reason) is not str or not self.replan_reason.strip() or self.replan_reason != self.replan_reason.strip():
                raise ValueError("replan reason is required")
            evidence = _require_trimmed_unique(
                self.replan_evidence_refs,
                "replan evidence",
                minimum=1,
            )
            object.__setattr__(self, "replan_evidence_refs", evidence)
        elif self.replan_evidence_refs:
            raise ValueError("initial plan cannot contain replan evidence")

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_document())

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": _PLAN_SCHEMA_VERSION,
            "planner_kind": _ORCHESTRATOR_PLANNER_KIND,
            "mission_id": self.graph.charter.mission_id,
            "charter_digest": self.graph.charter.digest(),
            "graph_digest": self.graph.digest,
            "work_items": [item.to_document() for item in self.graph.ordered_items()],
            "schedules": [schedule.to_document() for schedule in self.schedules],
            "replaces_digest": self.replaces_digest,
            "replan_reason": self.replan_reason,
            "replan_evidence_refs": list(self.replan_evidence_refs),
        }


class OrchestratorPlanner:
    """Build and revise bounded work DAGs without executing scheduled work."""

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


@dataclass(frozen=True, slots=True)
class _DurablePlanGroup:
    mission_id: str
    plan_digest: str
    planner_kind: str
    metadata: Mapping[str, object]
    rows: tuple[Mapping[str, object], ...]

    @property
    def latest_sequence(self) -> int:
        return max(cast(int, row["sequence"]) for row in self.rows)

    @property
    def work_ids(self) -> tuple[str, ...]:
        raw = self.metadata.get("work_ids")
        if not isinstance(raw, list) or any(type(value) is not str for value in raw):
            raise ValueError("durable plan work manifest is invalid")
        values = tuple(cast(list[str], raw))
        if values != tuple(sorted(values)) or len(values) != len(set(values)):
            raise ValueError("durable plan work manifest is not canonical")
        return values


def _durable_plan_groups(events: Iterable[Mapping[str, object]]) -> dict[tuple[str, str], _DurablePlanGroup]:
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for row in events:
        if row.get("event_type") != "work.created":
            continue
        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            continue
        plan_digest = payload.get("plan_digest")
        metadata = payload.get("plan")
        mission_id = row.get("mission_id")
        if not isinstance(plan_digest, str) or not isinstance(metadata, Mapping) or not isinstance(mission_id, str):
            continue
        grouped.setdefault((mission_id, plan_digest), []).append(row)

    result: dict[tuple[str, str], _DurablePlanGroup] = {}
    for key, rows in grouped.items():
        payloads = [cast(Mapping[str, object], row["payload"]) for row in rows]
        metadata = payloads[0]["plan"]
        if not isinstance(metadata, Mapping) or any(payload.get("plan") != metadata for payload in payloads):
            raise ValueError("durable plan metadata differs across work facts")
        planner_kind = metadata.get("planner_kind")
        if planner_kind not in {_FIXTURE_PLANNER_KIND, _ORCHESTRATOR_PLANNER_KIND}:
            raise ValueError("durable plan kind is invalid")
        group = _DurablePlanGroup(key[0], key[1], cast(str, planner_kind), metadata, tuple(rows))
        expected = set(group.work_ids)
        observed = [cast(str, row.get("work_id")) for row in rows]
        if set(observed) != expected or len(observed) != len(expected):
            raise ValueError("durable plan is incomplete or duplicated")
        if metadata.get("plan_digest") != key[1] or metadata.get("mission_id") != key[0]:
            raise ValueError("durable plan identity is inconsistent")
        result[key] = group
    return result


def _exact_plan_retry(group: _DurablePlanGroup | None) -> tuple[int, ...] | None:
    if group is None:
        return None
    by_work = {cast(str, row["work_id"]): cast(int, row["sequence"]) for row in group.rows}
    return tuple(by_work[work_id] for work_id in group.work_ids)


def _mission_plan_groups(
    groups: Mapping[tuple[str, str], _DurablePlanGroup], mission_id: str
) -> tuple[_DurablePlanGroup, ...]:
    return tuple(
        sorted(
            (group for (group_mission, _), group in groups.items() if group_mission == mission_id),
            key=lambda group: group.latest_sequence,
        )
    )


def _plan_metadata(
    plan: FixturePlan | OrchestrationPlan,
    *,
    revision: int,
    lineage_reserved: Mapping[str, int],
) -> dict[str, object]:
    planner_kind = (
        _ORCHESTRATOR_PLANNER_KIND if isinstance(plan, OrchestrationPlan) else _FIXTURE_PLANNER_KIND
    )
    reserved = (
        _schedule_budget_totals(plan.schedules)
        if isinstance(plan, OrchestrationPlan)
        else {name: 0 for name in _CONSUMPTIVE_BUDGET_FIELDS}
    )
    return {
        "schema_version": _PLAN_SCHEMA_VERSION,
        "planner_kind": planner_kind,
        "mission_id": plan.graph.charter.mission_id,
        "plan_digest": plan.digest,
        "charter_digest": plan.graph.charter.digest(),
        "graph_digest": plan.graph.digest,
        "work_ids": sorted(item.work_id for item in plan.graph.work_items),
        "revision": revision,
        "replaces_digest": getattr(plan, "replaces_digest", None),
        "replan_reason": getattr(plan, "replan_reason", None),
        "replan_evidence_refs": list(getattr(plan, "replan_evidence_refs", ())),
        "reserved_budget": reserved,
        "lineage_reserved_budget": dict(lineage_reserved),
        "fixture_kind": plan.kind if isinstance(plan, FixturePlan) else None,
    }


def _lineage_groups(
    current: _DurablePlanGroup,
    groups: Mapping[tuple[str, str], _DurablePlanGroup],
) -> tuple[_DurablePlanGroup, ...]:
    lineage: list[_DurablePlanGroup] = []
    seen: set[str] = set()
    node: _DurablePlanGroup | None = current
    while node is not None:
        if node.plan_digest in seen:
            raise ValueError("durable replan lineage contains a cycle")
        seen.add(node.plan_digest)
        lineage.append(node)
        replaced = node.metadata.get("replaces_digest")
        if replaced is None:
            break
        if not isinstance(replaced, str):
            raise ValueError("durable replan lineage digest is invalid")
        node = groups.get((current.mission_id, replaced))
        if node is None:
            raise ValueError("durable replan lineage is incomplete")
    return tuple(reversed(lineage))


def _stored_reserved_budget(group: _DurablePlanGroup) -> dict[str, int]:
    raw = group.metadata.get("reserved_budget")
    if not isinstance(raw, Mapping):
        raise ValueError("durable plan budget evidence is missing")
    result: dict[str, int] = {}
    for name in _CONSUMPTIVE_BUDGET_FIELDS:
        value = raw.get(name)
        if type(value) is not int or value < 0:
            raise ValueError("durable plan budget evidence is invalid")
        result[name] = cast(int, value)
    return result


def persist_plan(store: KernelStore, plan: FixturePlan | OrchestrationPlan) -> tuple[int, ...]:
    """Atomically append one mission-scoped plan; exact retries are read-only."""

    mission_id = plan.graph.charter.mission_id
    events = store.events()
    groups = _durable_plan_groups(events)
    exact = _exact_plan_retry(groups.get((mission_id, plan.digest)))
    if exact is not None:
        return exact

    projection = store.projection()
    mission_status = projection["missions"].get(mission_id)
    if mission_status is None:
        raise ValueError("plan belongs to an unknown mission")
    if mission_status in _TERMINAL_MISSION_STATES:
        raise ValueError("terminal mission rejects new plans")
    if mission_status not in _PLANNING_MISSION_STATES:
        raise ValueError("mission is not in an explicit planning state")

    candidate_kind = (
        _ORCHESTRATOR_PLANNER_KIND if isinstance(plan, OrchestrationPlan) else _FIXTURE_PLANNER_KIND
    )
    mission_groups = _mission_plan_groups(groups, mission_id)
    if any(group.planner_kind != candidate_kind for group in mission_groups):
        raise ValueError("planner kind crossover is forbidden for a mission")
    latest = mission_groups[-1] if mission_groups else None

    predecessor: _DurablePlanGroup | None = None
    revision = 0
    previous_reserved = {name: 0 for name in _CONSUMPTIVE_BUDGET_FIELDS}
    if isinstance(plan, OrchestrationPlan):
        if plan.replaces_digest is None:
            if latest is not None:
                raise ValueError("an initial orchestration plan already exists for the mission")
        else:
            predecessor = groups.get((mission_id, plan.replaces_digest))
            if predecessor is None:
                raise ValueError("replan does not reference a durable prior plan")
            if latest is None or predecessor.plan_digest != latest.plan_digest:
                raise ValueError("replan must replace the latest same-mission plan")
            lineage = _lineage_groups(predecessor, groups)
            revision = len(lineage)
            if revision > _MAX_REVISIONS:
                raise ValueError("replan revision limit exceeded")
            for prior in lineage:
                reserved = _stored_reserved_budget(prior)
                for name, value in reserved.items():
                    previous_reserved[name] += value
    elif latest is not None:
        predecessor = latest
        revision = cast(int, latest.metadata.get("revision", 0)) + 1

    current_reserved = (
        _schedule_budget_totals(plan.schedules)
        if isinstance(plan, OrchestrationPlan)
        else {name: 0 for name in _CONSUMPTIVE_BUDGET_FIELDS}
    )
    lineage_reserved = {
        name: previous_reserved[name] + current_reserved[name]
        for name in _CONSUMPTIVE_BUDGET_FIELDS
    }
    if isinstance(plan, OrchestrationPlan):
        _assert_budget_within(
            lineage_reserved,
            plan.graph.charter.budget,
            label="replan lineage reserved budget",
        )

    projected_work = cast(Mapping[str, Mapping[str, object]], projection["work"])
    new_ids = {item.work_id for item in plan.graph.work_items}
    if new_ids.intersection(projected_work):
        raise ValueError("new plan work ids must not reuse durable work ids")

    predecessor_rows: tuple[Mapping[str, object], ...] = ()
    if predecessor is not None:
        predecessor_rows = predecessor.rows
        for row in predecessor_rows:
            work_id = cast(str, row["work_id"])
            status = projected_work.get(work_id, {}).get("status")
            if status != WorkState.PROPOSED.value:
                raise ValueError("active predecessor work must be reconciled before replan")

    metadata = _plan_metadata(plan, revision=revision, lineage_reserved=lineage_reserved)
    schedules = (
        {schedule.work_id: schedule for schedule in plan.schedules}
        if isinstance(plan, OrchestrationPlan)
        else {}
    )
    actor_id = (
        "kernel-orchestrator-planner"
        if isinstance(plan, OrchestrationPlan)
        else "kernel-fixture-planner"
    )

    last_digest = cast(str | None, events[-1]["digest"] if events else None)
    batch: list[tuple[KernelEvent, str]] = []
    for row in sorted(predecessor_rows, key=lambda item: cast(str, item["work_id"])):
        work_id = cast(str, row["work_id"])
        event = KernelEvent(
            event_id=f"supersede:{plan.digest}:{work_id}",
            mission_id=mission_id,
            event_type="work.transition",
            actor_id=actor_id,
            actor_role="orchestrator",
            occurred_at="1970-01-01T00:00:00Z",
            payload={
                "status": WorkState.SUPERSEDED.value,
                "superseded_by": plan.digest,
                "supersedes_plan_digest": predecessor.plan_digest if predecessor else None,
            },
            work_id=work_id,
            previous_digest=last_digest,
        )
        batch.append(
            (
                event,
                canonical_digest(
                    {"plan_digest": plan.digest, "supersedes_work_id": work_id}
                ),
            )
        )
        last_digest = event.digest_for(last_digest)

    for item in plan.graph.ordered_items():
        payload: dict[str, object] = {
            "planner_kind": candidate_kind,
            "plan_digest": plan.digest,
            "plan": metadata,
            "work_item": item.to_document(),
        }
        if isinstance(plan, OrchestrationPlan):
            payload["schedule"] = schedules[item.work_id].to_document()
            if plan.replaces_digest is not None:
                payload["replan"] = {
                    "from_plan_digest": plan.replaces_digest,
                    "reason": plan.replan_reason,
                    "evidence_refs": list(plan.replan_evidence_refs),
                }
        event = KernelEvent(
            event_id=f"plan:{plan.digest}:{item.work_id}",
            mission_id=mission_id,
            event_type="work.created",
            actor_id=actor_id,
            actor_role="orchestrator",
            occurred_at="1970-01-01T00:00:00Z",
            payload=payload,
            work_id=item.work_id,
            previous_digest=last_digest,
        )
        batch.append(
            (
                event,
                canonical_digest(
                    {"plan_digest": plan.digest, "work_id": item.work_id}
                ),
            )
        )
        last_digest = event.digest_for(last_digest)

    sequences = store.append_batch(batch, expected_sequence=len(events))
    return tuple(sequences[-len(plan.graph.work_items) :])


def _latest_group_for_mission(
    mission_id: str, events: Iterable[Mapping[str, object]]
) -> _DurablePlanGroup:
    groups = _durable_plan_groups(events)
    mission_groups = _mission_plan_groups(groups, mission_id)
    if not mission_groups:
        raise ValueError("kernel mission has no durable plan")
    return mission_groups[-1]


def _graph_for_group(charter: MissionCharter, group: _DurablePlanGroup) -> ObjectiveGraph:
    if group.mission_id != charter.mission_id:
        raise ValueError("durable plan belongs to another mission")
    if group.metadata.get("charter_digest") != charter.digest():
        raise ValueError("durable plan charter binding differs")
    documents: dict[str, Mapping[str, object]] = {}
    for row in group.rows:
        payload = row.get("payload")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("work_item"), Mapping):
            raise ValueError("durable plan work payload is invalid")
        work_id = cast(str, row["work_id"])
        if work_id in documents:
            raise ValueError("durable plan contains duplicate work payloads")
        documents[work_id] = cast(Mapping[str, object], payload["work_item"])
    if set(documents) != set(group.work_ids):
        raise ValueError("durable plan work payloads are incomplete")
    graph = ObjectiveGraph.from_documents(
        charter, (documents[work_id] for work_id in group.work_ids)
    )
    if group.metadata.get("graph_digest") != graph.digest:
        raise ValueError("durable plan graph digest differs")
    return graph


def graph_from_events(
    charter: MissionCharter, events: Iterable[Mapping[str, object]]
) -> ObjectiveGraph:
    """Rehydrate the latest complete plan for exactly one mission."""

    rows = tuple(events)
    return _graph_for_group(
        charter, _latest_group_for_mission(charter.mission_id, rows)
    )


def orchestration_plan_from_events(
    charter: MissionCharter, events: Iterable[Mapping[str, object]]
) -> OrchestrationPlan:
    """Rehydrate the latest exact orchestration plan including every schedule."""

    rows = tuple(events)
    group = _latest_group_for_mission(charter.mission_id, rows)
    if group.planner_kind != _ORCHESTRATOR_PLANNER_KIND:
        raise ValueError("latest durable plan is not an orchestration plan")
    graph = _graph_for_group(charter, group)
    schedules: dict[str, WorkSchedule] = {}
    for row in group.rows:
        payload = row.get("payload")
        if not isinstance(payload, Mapping) or not isinstance(payload.get("schedule"), Mapping):
            raise ValueError("durable orchestration schedule is missing")
        schedule = WorkSchedule.from_document(
            cast(Mapping[str, object], payload["schedule"])
        )
        if schedule.work_id in schedules:
            raise ValueError("durable orchestration schedule is duplicated")
        schedules[schedule.work_id] = schedule
    if set(schedules) != set(group.work_ids):
        raise ValueError("durable orchestration schedules are incomplete")
    plan = OrchestrationPlan(
        graph,
        tuple(schedules.values()),
        replaces_digest=cast(str | None, group.metadata.get("replaces_digest")),
        replan_reason=cast(str | None, group.metadata.get("replan_reason")),
        replan_evidence_refs=tuple(
            cast(Iterable[str], group.metadata.get("replan_evidence_refs", ()))
        ),
    )
    if plan.digest != group.plan_digest:
        raise ValueError("durable orchestration plan digest differs")
    return plan
