"""Deterministic fixture planning and durable graph persistence for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .canonical import canonical_digest
from .contracts import MissionCharter, WorkItem, WorkState
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


def persist_plan(store: KernelStore, plan: FixturePlan) -> tuple[int, ...]:
    """Append a plan's typed work facts; identical retries are idempotent."""

    sequences: list[int] = []
    projected_work = store.projection()["work"]
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
        sequences.append(
            store.append(
                KernelEvent(
                    event_id=f"plan:{plan.digest}:{item.work_id}",
                    mission_id=item.mission_id,
                    event_type="work.created",
                    actor_id="kernel-fixture-planner",
                    occurred_at="1970-01-01T00:00:00Z",
                    payload={"work_item": item.to_document(), "plan_digest": plan.digest},
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
