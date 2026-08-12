from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping, cast
from unittest.mock import patch

from hive_mind_os.brain_kernel.contracts import (
    Budget,
    MissionCharter,
    MissionState,
    WorkItem,
    WorkState,
)
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.planner import (
    DeterministicFixturePlanner,
    OrchestrationPlan,
    OrchestratorPlanner,
    WorkSchedule,
    graph_from_events,
    orchestration_plan_from_events,
    persist_plan,
)
from hive_mind_os.brain_kernel.store import KernelIntegrityError, KernelStore

DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40
TIME = "2026-08-11T04:00:00Z"


def budget(
    wall: int = 400,
    model: int = 20,
    input_tokens: int = 1000,
    output_tokens: int = 1000,
    cost: int = 1000,
    tools: int = 40,
    work_items: int = 12,
    depth: int = 4,
) -> Budget:
    return Budget(wall, model, input_tokens, output_tokens, cost, tools, work_items, depth)


def charter(
    mission_id: str = "MISSION-orchestrator",
    *,
    charter_budget: Budget | None = None,
    base_commit: str = SHA,
    target_branch: str = "release/hive-mind-os-singleton-20260810-r2",
    policy_fingerprint: str = DIGEST,
    status: MissionState = MissionState.CREATED,
) -> MissionCharter:
    return MissionCharter(
        1,
        mission_id,
        TIME,
        "deliver a bounded change",
        ("ACCEPT-1",),
        "repo",
        base_commit,
        target_branch,
        policy_fingerprint,
        DIGEST,
        DIGEST,
        charter_budget or budget(),
        (),
        (),
        ("HUMAN-RELEASE",),
        status,
    )


def work(
    work_id: str,
    *,
    mission_id: str = "MISSION-orchestrator",
    role: str = "builder",
    risk: str = "R1",
    dependencies: tuple[str, ...] = (),
    title: str | None = None,
    status: WorkState = WorkState.PROPOSED,
    scope: tuple[str, ...] | None = None,
) -> WorkItem:
    return WorkItem(
        work_id,
        mission_id,
        None,
        0,
        title or work_id,
        "deliver a bounded change",
        role,
        risk,
        dependencies,
        (),
        (),
        ("ACCEPT-1",),
        scope or (f"work/{work_id}.txt",),
        (),
        {},
        2,
        status,
        DIGEST,
        DIGEST,
    )


def consultation_roles(requesting_role: str) -> tuple[str, str]:
    return cast(
        tuple[str, str],
        tuple(role for role in ("curator", "architect", "steward") if role != requesting_role)[:2],
    )


def schedule(
    item: WorkItem | str,
    risk: str | None = None,
    *,
    gate: bool = False,
    schedule_budget: Budget | None = None,
    roles: tuple[str, ...] | None = None,
) -> WorkSchedule:
    if isinstance(item, WorkItem):
        work_id = item.work_id
        item_risk = item.risk_tier
        item_role = item.role
    else:
        work_id = item
        item_risk = risk or "R1"
        item_role = "builder"
    return WorkSchedule(
        work_id,
        schedule_budget or budget(40, 2, 100, 100, 100, 4, 2, 1),
        risk or item_risk,
        ("stop when the acceptance boundary or assigned budget is reached",),
        roles or consultation_roles(item_role),
        ("HUMAN-RELEASE",) if gate else (),
    )


def mission_created(mission_id: str) -> KernelEvent:
    return KernelEvent(
        f"{mission_id}-created",
        mission_id,
        "mission.created",
        "test",
        TIME,
        {},
        previous_digest=None,
    )


def append_transition(
    store: KernelStore,
    mission_id: str,
    *,
    event_id: str,
    event_type: str,
    payload: Mapping[str, object],
    work_id: str | None = None,
) -> None:
    events = store.events()
    store.append(
        KernelEvent(
            event_id,
            mission_id,
            event_type,
            "test",
            TIME,
            payload,
            work_id=work_id,
            previous_digest=events[-1]["digest"] if events else None,
        )
    )


class OrchestratorPlannerTests(unittest.TestCase):
    def test_orchestrator_dag_tests_schedule_dependencies_scopes_budgets_and_gates(self) -> None:
        prepare = work("WORK-prepare", role="builder", risk="R1")
        release = work(
            "WORK-release",
            role="orchestrator",
            risk="R2",
            dependencies=(prepare.work_id,),
        )
        plan = OrchestratorPlanner().plan(
            charter(),
            (release, prepare),
            (schedule(release, gate=True), schedule(prepare)),
        )

        self.assertEqual(
            (prepare.work_id, release.work_id),
            tuple(item.work_id for item in plan.graph.ordered_items()),
        )
        document = plan.to_document()
        schedules = cast(list[dict[str, Any]], document["schedules"])
        work_items = cast(list[dict[str, Any]], document["work_items"])
        release_schedule = next(item for item in schedules if item["work_id"] == release.work_id)
        release_work = next(item for item in work_items if item["work_id"] == release.work_id)
        self.assertEqual(1, document["schema_version"])
        self.assertEqual(charter().digest(), document["charter_digest"])
        self.assertEqual(["HUMAN-RELEASE"], release_schedule["human_gates"])
        self.assertEqual("R2", release_schedule["risk_lane"])
        self.assertTrue(release_schedule["stop_conditions"])
        self.assertEqual([prepare.work_id], release_work["dependencies"])
        self.assertEqual([f"work/{release.work_id}.txt"], release_work["write_scope"])

    def test_budget_stop_tests_fail_closed_for_unbounded_or_unchartered_schedule(self) -> None:
        item = work("WORK-prepare")
        with self.assertRaisesRegex(ValueError, "stop conditions"):
            WorkSchedule(
                item.work_id,
                budget(1, 1, 1, 1, 1, 1, 1, 1),
                "R1",
                (),
                ("curator", "architect"),
                (),
            )
        with self.assertRaisesRegex(ValueError, "chartered"):
            OrchestratorPlanner().plan(
                charter(),
                (item,),
                (
                    WorkSchedule(
                        item.work_id,
                        budget(1, 1, 1, 1, 1, 1, 1, 1),
                        "R1",
                        ("stop",),
                        ("curator", "architect"),
                        ("HUMAN-UNAPPROVED",),
                    ),
                ),
            )

    def test_second_initial_plan_cannot_supersede_existing_same_mission_plan(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        first = work("WORK-first")
        second = work("WORK-second")
        first_plan = OrchestratorPlanner().plan(charter(), (first,), (schedule(first),))
        second_plan = OrchestratorPlanner().plan(charter(), (second,), (schedule(second),))
        persist_plan(store, first_plan)
        before_events = store.events()
        before_projection = store.projection()
        with self.assertRaisesRegex(ValueError, "initial orchestration plan already exists"):
            persist_plan(store, second_plan)
        self.assertEqual(before_events, store.events())
        self.assertEqual(before_projection, store.projection())
        store.close()

    def test_replan_supersedes_only_exact_latest_same_mission_predecessor(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        first = work("WORK-first")
        planner = OrchestratorPlanner()
        initial = planner.plan(charter(), (first,), (schedule(first, schedule_budget=budget(30, 1, 20, 20, 20, 1, 1, 1)),))
        revised_item = work("WORK-revised")
        revised = planner.replan(
            initial,
            (revised_item,),
            (schedule(revised_item, schedule_budget=budget(30, 1, 20, 20, 20, 1, 1, 1)),),
            reason="evidence requires a narrower implementation",
            evidence_refs=("event:curator:1",),
        )
        persist_plan(store, initial)
        persist_plan(store, revised)
        projection = store.projection()["work"]
        self.assertEqual("SUPERSEDED", projection[first.work_id]["status"])
        self.assertEqual("PROPOSED", projection[revised_item.work_id]["status"])

        foreign = OrchestrationPlan(
            revised.graph,
            revised.schedules,
            replaces_digest="sha256:" + "1" * 64,
            replan_reason="foreign predecessor",
            replan_evidence_refs=("event:foreign",),
        )
        before = store.events()
        with self.assertRaisesRegex(ValueError, "durable prior plan"):
            persist_plan(store, foreign)
        self.assertEqual(before, store.events())
        store.close()

    def test_cross_mission_plan_persistence_and_restoration_are_isolated(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-a"))
        head = store.events()[-1]["digest"]
        store.append(
            KernelEvent(
                "MISSION-b-created",
                "MISSION-b",
                "mission.created",
                "test",
                TIME,
                {},
                previous_digest=head,
            )
        )
        item_a = work("WORK-a", mission_id="MISSION-a")
        item_b = work("WORK-b", mission_id="MISSION-b")
        plan_a = OrchestratorPlanner().plan(
            charter("MISSION-a"), (item_a,), (schedule(item_a),)
        )
        plan_b = OrchestratorPlanner().plan(
            charter("MISSION-b"), (item_b,), (schedule(item_b),)
        )
        persist_plan(store, plan_a)
        persist_plan(store, plan_b)
        projection = store.projection()["work"]
        self.assertEqual("PROPOSED", projection[item_a.work_id]["status"])
        self.assertEqual("PROPOSED", projection[item_b.work_id]["status"])
        self.assertEqual(plan_a.graph.digest, graph_from_events(charter("MISSION-a"), store.events()).digest)
        self.assertEqual(plan_b.graph.digest, graph_from_events(charter("MISSION-b"), store.events()).digest)
        store.close()

    def test_failed_persist_is_atomic_under_mid_batch_reducer_failure(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        first = work("WORK-first")
        second = work("WORK-second", dependencies=(first.work_id,))
        plan = OrchestratorPlanner().plan(
            charter(), (first, second), (schedule(first), schedule(second))
        )
        before_events = store.events()
        before_projection = store.projection()

        from hive_mind_os.brain_kernel import store as store_module

        original = store_module.reduce_event
        seen = 0

        def fail_second_work(state: Mapping[str, object], event: Mapping[str, object]) -> dict[str, Any]:
            nonlocal seen
            if event["event_type"] == "work.created":
                seen += 1
                if seen == 2:
                    raise ValueError("injected reducer failure")
            return original(state, event)

        with patch.object(store_module, "reduce_event", side_effect=fail_second_work):
            with self.assertRaises(KernelIntegrityError):
                persist_plan(store, plan)
        self.assertEqual(before_events, store.events())
        self.assertEqual(before_projection, store.projection())
        store.close()

    def test_stale_plan_retry_is_idempotent_after_a_newer_revision(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        planner = OrchestratorPlanner()
        first = work("WORK-first")
        initial = planner.plan(
            charter(),
            (first,),
            (schedule(first, schedule_budget=budget(20, 1, 20, 20, 20, 1, 1, 1)),),
        )
        replacement = work("WORK-replacement")
        revised = planner.replan(
            initial,
            (replacement,),
            (schedule(replacement, schedule_budget=budget(20, 1, 20, 20, 20, 1, 1, 1)),),
            reason="new evidence",
            evidence_refs=("event:new",),
        )
        initial_sequences = persist_plan(store, initial)
        persist_plan(store, revised)
        before = store.events()
        self.assertEqual(initial_sequences, persist_plan(store, initial))
        self.assertEqual(before, store.events())
        self.assertEqual("PROPOSED", store.projection()["work"][replacement.work_id]["status"])
        store.close()

    def test_active_predecessor_replan_is_rejected_without_mutation(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        planner = OrchestratorPlanner()
        first = work("WORK-first", scope=("src",))
        initial = planner.plan(charter(), (first,), (schedule(first),))
        persist_plan(store, initial)
        append_transition(
            store,
            "MISSION-orchestrator",
            event_id="work-ready",
            event_type="work.transition",
            payload={"status": "READY"},
            work_id=first.work_id,
        )
        replacement = work("WORK-replacement", scope=("src/main.py",))
        revised = planner.replan(
            initial,
            (replacement,),
            (schedule(replacement),),
            reason="replace active work",
            evidence_refs=("event:active",),
        )
        before = store.events()
        with self.assertRaisesRegex(ValueError, "active predecessor"):
            persist_plan(store, revised)
        self.assertEqual(before, store.events())
        self.assertEqual("READY", store.projection()["work"][first.work_id]["status"])
        store.close()

    def test_new_plans_require_proposed_work_and_terminal_missions_reject_planning(self) -> None:
        with self.assertRaisesRegex(ValueError, "PROPOSED"):
            OrchestratorPlanner().plan(
                charter(),
                (work("WORK-ready", status=WorkState.READY),),
                (schedule("WORK-ready", "R1"),),
            )

        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        append_transition(
            store,
            "MISSION-orchestrator",
            event_id="mission-failed",
            event_type="mission.transition",
            payload={"status": "FAILED"},
        )
        item = work("WORK-never")
        plan = OrchestratorPlanner().plan(charter(), (item,), (schedule(item),))
        before = store.events()
        with self.assertRaisesRegex(ValueError, "terminal mission"):
            persist_plan(store, plan)
        self.assertEqual(before, store.events())
        store.close()

    def test_orchestration_plan_digest_binds_complete_charter(self) -> None:
        item = work("WORK-bind")
        planner = OrchestratorPlanner()
        baseline = planner.plan(charter(), (item,), (schedule(item),))
        variants = (
            charter(base_commit="1" * 40),
            charter(target_branch="release/other"),
            charter(policy_fingerprint="sha256:" + "2" * 64),
            charter(charter_budget=budget(wall=401)),
        )
        for variant in variants:
            with self.subTest(variant=variant.target_branch, base=variant.base_commit):
                candidate = planner.plan(variant, (item,), (schedule(item),))
                self.assertNotEqual(baseline.digest, candidate.digest)

    def test_total_consumptive_schedule_budgets_must_fit_charter(self) -> None:
        limited = charter(charter_budget=budget(100, 4, 100, 100, 100, 8, 4, 2))
        first = work("WORK-first")
        second = work("WORK-second")
        each = budget(60, 2, 60, 60, 60, 4, 2, 1)
        with self.assertRaisesRegex(ValueError, "total consumptive.*max_wall_seconds"):
            OrchestratorPlanner().plan(
                limited,
                (first, second),
                (schedule(first, schedule_budget=each), schedule(second, schedule_budget=each)),
            )

    def test_replan_respects_remaining_budget_and_revision_limit(self) -> None:
        limited = charter(charter_budget=budget(100, 10, 100, 100, 100, 10, 10, 3))
        planner = OrchestratorPlanner()
        first = work("WORK-first")
        initial = planner.plan(
            limited,
            (first,),
            (schedule(first, schedule_budget=budget(60, 1, 10, 10, 10, 1, 1, 1)),),
        )
        replacement = work("WORK-replacement")
        too_expensive = planner.replan(
            initial,
            (replacement,),
            (schedule(replacement, schedule_budget=budget(50, 1, 10, 10, 10, 1, 1, 1)),),
            reason="too expensive",
            evidence_refs=("event:budget",),
        )
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        persist_plan(store, initial)
        before = store.events()
        with self.assertRaisesRegex(ValueError, "lineage reserved.*max_wall_seconds"):
            persist_plan(store, too_expensive)
        self.assertEqual(before, store.events())
        store.close()

        zero = budget(0, 0, 0, 0, 0, 0, 1, 1)
        large_structural = charter(charter_budget=budget(0, 0, 0, 0, 0, 0, 10, 3))
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        plans: list[OrchestrationPlan] = []
        item = work("WORK-r0")
        plans.append(planner.plan(large_structural, (item,), (schedule(item, schedule_budget=zero),)))
        persist_plan(store, plans[-1])
        for index in (1, 2):
            item = work(f"WORK-r{index}")
            plans.append(
                planner.replan(
                    plans[-1],
                    (item,),
                    (schedule(item, schedule_budget=zero),),
                    reason=f"revision {index}",
                    evidence_refs=(f"event:revision:{index}",),
                )
            )
            persist_plan(store, plans[-1])
        third_item = work("WORK-r3")
        third = planner.replan(
            plans[-1],
            (third_item,),
            (schedule(third_item, schedule_budget=zero),),
            reason="revision 3",
            evidence_refs=("event:revision:3",),
        )
        before = store.events()
        with self.assertRaisesRegex(ValueError, "revision limit"):
            persist_plan(store, third)
        self.assertEqual(before, store.events())
        store.close()

    def test_replan_metadata_is_canonical_and_semantically_changes_plan(self) -> None:
        item = work("WORK-first")
        initial = OrchestratorPlanner().plan(charter(), (item,), (schedule(item),))
        with self.assertRaisesRegex(ValueError, "lowercase sha256"):
            OrchestrationPlan(
                initial.graph,
                initial.schedules,
                replaces_digest="SHA256:" + "A" * 64,
                replan_reason="bad digest",
                replan_evidence_refs=("event:1",),
            )
        with self.assertRaisesRegex(ValueError, "reason"):
            OrchestrationPlan(
                initial.graph,
                initial.schedules,
                replaces_digest=initial.digest,
                replan_reason=" padded ",
                replan_evidence_refs=("event:1",),
            )
        with self.assertRaisesRegex(ValueError, "unique"):
            OrchestrationPlan(
                initial.graph,
                initial.schedules,
                replaces_digest=initial.digest,
                replan_reason="valid",
                replan_evidence_refs=("event:1", "event:1"),
            )
        with self.assertRaisesRegex(ValueError, "must change"):
            OrchestratorPlanner().replan(
                initial,
                (item,),
                (schedule(item),),
                reason="duplicate",
                evidence_refs=("event:duplicate",),
            )

    def test_schedule_round_trip_is_exact_complete_and_mission_scoped(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        first = work("WORK-first")
        second = work("WORK-second", role="orchestrator", risk="R2", dependencies=(first.work_id,))
        plan = OrchestratorPlanner().plan(
            charter(),
            (first, second),
            (schedule(first), schedule(second, gate=True)),
        )
        persist_plan(store, plan)
        restored = orchestration_plan_from_events(charter(), store.events())
        self.assertEqual(plan.digest, restored.digest)
        self.assertEqual(plan.to_document(), restored.to_document())

        incomplete = [
            row for row in store.events() if row.get("work_id") != second.work_id
        ]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            orchestration_plan_from_events(charter(), incomplete)
        store.close()

    def test_consultation_route_requires_two_distinct_nonrequesting_roles(self) -> None:
        item = work("WORK-builder", role="builder")
        with self.assertRaisesRegex(ValueError, "at least 2"):
            schedule(item, roles=("curator",))
        with self.assertRaisesRegex(ValueError, "unique"):
            schedule(item, roles=("curator", "curator"))
        with self.assertRaisesRegex(ValueError, "requesting work role"):
            OrchestratorPlanner().plan(
                charter(),
                (item,),
                (schedule(item, roles=("builder", "curator")),),
            )

    def test_operational_supersession_actor_is_orchestrator(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        planner = OrchestratorPlanner()
        first = work("WORK-first")
        initial = planner.plan(charter(), (first,), (schedule(first),))
        replacement = work("WORK-replacement")
        revised = planner.replan(
            initial,
            (replacement,),
            (schedule(replacement),),
            reason="replace",
            evidence_refs=("event:replace",),
        )
        persist_plan(store, initial)
        persist_plan(store, revised)
        relevant = [
            row
            for row in store.events()
            if row["event_type"] in {"work.created", "work.transition"}
        ]
        self.assertTrue(relevant)
        self.assertEqual(
            {"kernel-orchestrator-planner"},
            {row["actor_id"] for row in relevant},
        )
        store.close()

    def test_planner_kind_crossover_and_every_rejection_preserve_prior_evidence(self) -> None:
        store = KernelStore()
        store.append(mission_created("MISSION-orchestrator"))
        fixture = DeterministicFixturePlanner().plan(charter(), "bugfix")
        persist_plan(store, fixture)
        before_events = store.events()
        before_projection = store.projection()
        item = work("WORK-orchestrated")
        orchestration = OrchestratorPlanner().plan(
            charter(), (item,), (schedule(item),)
        )
        with self.assertRaisesRegex(ValueError, "kind crossover"):
            persist_plan(store, orchestration)
        self.assertEqual(before_events, store.events())
        self.assertEqual(before_projection, store.projection())
        store.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
