from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.contracts import (
    Budget,
    MissionCharter,
    MissionState,
    WorkItem,
    WorkState,
)
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.objectives import ObjectiveGraph
from hive_mind_os.brain_kernel.planner import (
    DeterministicFixturePlanner,
    OrchestrationPlan,
    OrchestratorPlanner,
    WorkSchedule,
    graph_from_events,
    orchestration_plan_from_events,
    persist_plan,
)
from hive_mind_os.brain_kernel.store import KernelStore

DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40
TIME = "2026-08-11T04:00:00Z"


def charter(
    *,
    mission_id: str = "MISSION-orchestrator",
    base_commit: str = SHA,
    budget: Budget | None = None,
) -> MissionCharter:
    return MissionCharter(
        1,
        mission_id,
        TIME,
        "deliver a bounded change",
        ("ACCEPT-1",),
        "repo",
        base_commit,
        "release/hive-mind-os-singleton-20260810-r2",
        DIGEST,
        DIGEST,
        DIGEST,
        budget or Budget(120, 4, 100, 100, 100, 8, 4, 2),
        (),
        (),
        ("HUMAN-RELEASE",),
        MissionState.CREATED,
    )


def work(
    work_id: str,
    *,
    role: str,
    risk: str,
    dependencies: tuple[str, ...] = (),
    title: str | None = None,
    mission_id: str = "MISSION-orchestrator",
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


def schedule(
    work_id: str,
    risk: str,
    *,
    gate: bool = False,
    budget: Budget | None = None,
    consultations: tuple[str, ...] = ("curator", "architect"),
) -> WorkSchedule:
    return WorkSchedule(
        work_id,
        budget or Budget(60, 2, 50, 50, 50, 4, 2, 1),
        risk,
        ("stop when the attempt budget or acceptance boundary is reached",),
        consultations,
        ("HUMAN-RELEASE",) if gate else (),
    )


class OrchestratorPlannerTests(unittest.TestCase):
    @staticmethod
    def create_mission(store: KernelStore, mission_id: str = "MISSION-orchestrator") -> None:
        previous = store.events()[-1]["digest"] if store.events() else None
        store.append(
            KernelEvent(
                f"mission-created:{mission_id}",
                mission_id,
                "mission.created",
                "test",
                TIME,
                {},
                previous_digest=previous,
            )
        )

    @staticmethod
    def transition_mission(store: KernelStore, mission_id: str, status: MissionState) -> None:
        previous = store.events()[-1]["digest"]
        store.append(
            KernelEvent(
                f"mission-transition:{mission_id}:{status.value}",
                mission_id,
                "mission.transition",
                "test",
                TIME,
                {"status": status.value},
                previous_digest=previous,
            )
        )

    @staticmethod
    def transition_work(store: KernelStore, work_id: str, status: WorkState) -> None:
        previous = store.events()[-1]["digest"]
        store.append(
            KernelEvent(
                f"work-transition:{work_id}:{status.value}",
                "MISSION-orchestrator",
                "work.transition",
                "test",
                TIME,
                {"status": status.value},
                work_id=work_id,
                previous_digest=previous,
            )
        )

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
            (schedule(release.work_id, "R2", gate=True), schedule(prepare.work_id, "R1")),
        )

        self.assertEqual((prepare.work_id, release.work_id), tuple(
            item.work_id for item in plan.graph.ordered_items()
        ))
        release_schedule = next(item for item in plan.schedules if item.work_id == release.work_id)
        release_work = plan.graph.item(release.work_id)
        self.assertEqual(("HUMAN-RELEASE",), release_schedule.human_gates)
        self.assertEqual("R2", release_schedule.risk_lane)
        self.assertEqual(60, release_schedule.budget.max_wall_seconds)
        self.assertTrue(release_schedule.stop_conditions)
        self.assertEqual((prepare.work_id,), release_work.dependencies)
        self.assertEqual((f"work/{release.work_id}.txt",), release_work.write_scope)

    def test_budget_stop_tests_fail_closed_for_unbounded_or_unchartered_schedule(self) -> None:
        item = work("WORK-prepare", role="builder", risk="R1")
        with self.assertRaisesRegex(ValueError, "stop conditions"):
            OrchestratorPlanner().plan(
                charter(),
                (item,),
                (WorkSchedule(item.work_id, Budget(1, 1, 1, 1, 1, 1, 1, 1), "R1", (), ("curator", "architect"), ()),),
            )
        with self.assertRaisesRegex(ValueError, "chartered"):
            OrchestratorPlanner().plan(
                charter(),
                (item,),
                (WorkSchedule(item.work_id, Budget(1, 1, 1, 1, 1, 1, 1, 1), "R1", ("stop",), ("curator", "architect"), ("HUMAN-UNAPPROVED",)),),
            )

    def test_budget_tests_reject_aggregate_overflow_and_replan_budget_reset(self) -> None:
        planner = OrchestratorPlanner()
        first = work("WORK-first", role="builder", risk="R1")
        second = work("WORK-second", role="builder", risk="R1")
        with self.assertRaisesRegex(ValueError, "aggregate"):
            planner.plan(
                charter(),
                (first, second),
                (
                    schedule(first.work_id, "R1", budget=Budget(70, 2, 50, 50, 50, 4, 2, 1)),
                    schedule(second.work_id, "R1", budget=Budget(70, 2, 50, 50, 50, 4, 2, 1)),
                ),
            )
        initial = planner.plan(
            charter(),
            (first,),
            (schedule(first.work_id, "R1", budget=Budget(80, 2, 50, 50, 50, 4, 2, 1)),),
        )
        with self.assertRaisesRegex(ValueError, "aggregate"):
            planner.replan(
                initial,
                (work("WORK-replacement", role="builder", risk="R1"),),
                (schedule("WORK-replacement", "R1", budget=Budget(60, 2, 50, 50, 50, 4, 2, 1)),),
                reason="new evidence",
                evidence_refs=("event:new",),
            )
        structural_charter = charter(
            budget=Budget(120, 4, 100, 100, 100, 8, 2, 1)
        )
        structural_plan = planner.plan(
            structural_charter,
            (first, second),
            (
                schedule(first.work_id, "R1", budget=Budget(60, 2, 50, 50, 50, 4, 2, 1)),
                schedule(second.work_id, "R1", budget=Budget(60, 2, 50, 50, 50, 4, 2, 1)),
            ),
        )
        self.assertEqual(2, len(structural_plan.graph.work_items))

    def test_consultation_and_new_work_status_invariants_fail_closed(self) -> None:
        item = work("WORK-consult", role="builder", risk="R1")
        with self.assertRaisesRegex(ValueError, "two distinct"):
            schedule(item.work_id, "R1", consultations=("curator",))
        with self.assertRaisesRegex(ValueError, "requesting role"):
            OrchestratorPlanner().plan(
                charter(),
                (item,),
                (schedule(item.work_id, "R1", consultations=("builder", "curator")),),
            )
        ready = work(
            "WORK-ready", role="builder", risk="R1", status=WorkState.READY
        )
        with self.assertRaisesRegex(ValueError, "PROPOSED"):
            OrchestratorPlanner().plan(
                charter(), (ready,), (schedule(ready.work_id, "R1"),)
            )

    def test_plan_digest_binds_the_complete_charter(self) -> None:
        item = work("WORK-bind", role="builder", risk="R1")
        first = OrchestratorPlanner().plan(
            charter(), (item,), (schedule(item.work_id, "R1"),)
        )
        second = OrchestratorPlanner().plan(
            charter(base_commit="1" * 40),
            (item,),
            (schedule(item.work_id, "R1"),),
        )
        self.assertNotEqual(first.digest, second.digest)

    def test_replan_tests_append_reasoned_revision_before_new_work_facts(self) -> None:
        first = work("WORK-prepare", role="builder", risk="R1")
        planner = OrchestratorPlanner()
        initial = planner.plan(charter(), (first,), (schedule(first.work_id, "R1"),))
        revised = planner.replan(
            initial,
            (work("WORK-prepare-revised", role="builder", risk="R1", title="revised preparation"),),
            (schedule("WORK-prepare-revised", "R1"),),
            reason="new verifier evidence requires a narrower preparation step",
            evidence_refs=("event:verification:WORK-prepare",),
        )

        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            persist_plan(store, initial)
            persist_plan(store, revised)
            revisions = [
                event["payload"]
                for event in store.events()
                if event["event_type"] == "work.created"
                and event["payload"].get("plan_digest") == revised.digest
            ]
            self.assertTrue(revisions)
            self.assertEqual(initial.digest, revisions[0]["replan"]["from_plan_digest"])
            self.assertEqual(
                "new verifier evidence requires a narrower preparation step",
                revisions[0]["replan"]["reason"],
            )
            restored = graph_from_events(charter(), store.events())
            self.assertEqual(revised.graph.digest, restored.digest)
            restored_plan = orchestration_plan_from_events(charter(), store.events())
            self.assertEqual(revised.digest, restored_plan.digest)
            self.assertEqual(revised.schedules, restored_plan.schedules)
            revised_rows = [
                event
                for event in store.events()
                if event["event_type"] == "work.created"
                and event["payload"].get("plan_digest") == revised.digest
            ]
            self.assertTrue(all(event["payload"].get("schedule") for event in revised_rows))
            supersessions = [
                event for event in store.events() if event["event_type"] == "work.transition"
            ]
            self.assertEqual("kernel-orchestrator-planner", supersessions[0]["actor_id"])
            store.close()

    def test_replan_tests_reject_a_revision_without_a_semantic_change(self) -> None:
        item = work("WORK-prepare", role="builder", risk="R1")
        initial = OrchestratorPlanner().plan(
            charter(), (item,), (schedule(item.work_id, "R1"),)
        )
        with self.assertRaisesRegex(ValueError, "must change"):
            OrchestratorPlanner().replan(
                initial,
                (item,),
                (schedule(item.work_id, "R1"),),
                reason="duplicate evidence receipt",
                evidence_refs=("event:duplicate",),
            )

    def test_persistence_is_mission_scoped_and_rehydration_ignores_other_missions(self) -> None:
        planner = OrchestratorPlanner()
        item_a = work("WORK-a", role="builder", risk="R1")
        plan_a = planner.plan(charter(), (item_a,), (schedule(item_a.work_id, "R1"),))
        item_b = work(
            "WORK-b",
            role="builder",
            risk="R1",
            mission_id="MISSION-other",
        )
        plan_b = planner.plan(
            charter(mission_id="MISSION-other"),
            (item_b,),
            (schedule(item_b.work_id, "R1"),),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            self.create_mission(store, "MISSION-other")
            persist_plan(store, plan_a)
            persist_plan(store, plan_b)
            self.assertEqual(
                WorkState.PROPOSED.value,
                store.projection()["work"][item_a.work_id]["status"],
            )
            self.assertEqual(plan_a.graph.digest, graph_from_events(charter(), store.events()).digest)
            self.assertEqual(
                plan_b.graph.digest,
                graph_from_events(charter(mission_id="MISSION-other"), store.events()).digest,
            )
            store.close()

    def test_second_initial_plan_is_refused_and_exact_retries_are_read_only(self) -> None:
        planner = OrchestratorPlanner()
        first = work("WORK-first", role="builder", risk="R1")
        initial = planner.plan(charter(), (first,), (schedule(first.work_id, "R1"),))
        second = work("WORK-second", role="builder", risk="R1")
        competing = planner.plan(charter(), (second,), (schedule(second.work_id, "R1"),))
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            sequences = persist_plan(store, initial)
            head = store.events()[-1]["digest"]
            self.assertEqual(sequences, persist_plan(store, initial))
            self.assertEqual(head, store.events()[-1]["digest"])
            with self.assertRaisesRegex(ValueError, "already has"):
                persist_plan(store, competing)
            self.assertEqual(head, store.events()[-1]["digest"])
            store.close()

    def test_failed_changed_schedule_and_stale_retry_leave_history_unchanged(self) -> None:
        planner = OrchestratorPlanner()
        first = work("WORK-stable", role="builder", risk="R1")
        initial = planner.plan(charter(), (first,), (schedule(first.work_id, "R1"),))
        revised = planner.replan(
            initial,
            (work("WORK-revised", role="builder", risk="R1"),),
            (schedule("WORK-revised", "R1"),),
            reason="new evidence",
            evidence_refs=("event:new",),
        )
        changed_schedule = OrchestrationPlan(
            initial.graph,
            (schedule(first.work_id, "R1", budget=Budget(59, 2, 50, 50, 50, 4, 2, 1)),),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            persist_plan(store, initial)
            before = store.events()[-1]["digest"]
            with self.assertRaisesRegex(ValueError, "already has"):
                persist_plan(store, changed_schedule)
            self.assertEqual(before, store.events()[-1]["digest"])
            initial_sequences = persist_plan(store, initial)
            persist_plan(store, revised)
            revised_head = store.events()[-1]["digest"]
            self.assertEqual(initial_sequences, persist_plan(store, initial))
            self.assertEqual(revised_head, store.events()[-1]["digest"])
            self.assertEqual(
                WorkState.PROPOSED.value,
                store.projection()["work"]["WORK-revised"]["status"],
            )
            store.close()

    def test_replan_rejects_ready_or_running_predecessors_before_append(self) -> None:
        for target_state in (WorkState.READY, WorkState.RUNNING):
            with self.subTest(target_state=target_state):
                planner = OrchestratorPlanner()
                first = work("WORK-active", role="builder", risk="R1", scope=("src/shared.py",))
                initial = planner.plan(charter(), (first,), (schedule(first.work_id, "R1"),))
                revised = planner.replan(
                    initial,
                    (work("WORK-replacement", role="builder", risk="R1", scope=("src/shared.py",)),),
                    (schedule("WORK-replacement", "R1"),),
                    reason="active work changed",
                    evidence_refs=("event:active",),
                )
                with tempfile.TemporaryDirectory() as temporary:
                    store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
                    self.create_mission(store)
                    persist_plan(store, initial)
                    self.transition_work(store, first.work_id, WorkState.READY)
                    if target_state is WorkState.RUNNING:
                        self.transition_work(store, first.work_id, WorkState.LEASED)
                        self.transition_work(store, first.work_id, WorkState.RUNNING)
                    head = store.events()[-1]["digest"]
                    with self.assertRaisesRegex(ValueError, "active predecessor"):
                        persist_plan(store, revised)
                    self.assertEqual(head, store.events()[-1]["digest"])
                    store.close()

    def test_terminal_mission_states_reject_new_work_without_events(self) -> None:
        item = work("WORK-late", role="builder", risk="R1")
        plan = OrchestratorPlanner().plan(
            charter(), (item,), (schedule(item.work_id, "R1"),)
        )
        terminal_paths = {
            MissionState.FAILED: (MissionState.FAILED,),
            MissionState.CANCELLED: (MissionState.CANCELLED,),
            MissionState.COMPLETED: (
                MissionState.PLANNING,
                MissionState.READY,
                MissionState.RUNNING,
                MissionState.VERIFYING,
                MissionState.INTEGRATING,
                MissionState.COMPLETED,
            ),
        }
        for state, transitions in terminal_paths.items():
            with self.subTest(state=state), tempfile.TemporaryDirectory() as temporary:
                store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
                self.create_mission(store)
                for transition in transitions:
                    self.transition_mission(store, "MISSION-orchestrator", transition)
                head = store.events()[-1]["digest"]
                with self.assertRaisesRegex(ValueError, "planning-eligible"):
                    persist_plan(store, plan)
                self.assertEqual(head, store.events()[-1]["digest"])
                store.close()

    def test_durable_replans_are_consumptive_and_limited_to_two(self) -> None:
        small = Budget(40, 1, 20, 20, 20, 2, 1, 0)
        planner = OrchestratorPlanner()
        initial_item = work("WORK-r0", role="builder", risk="R1")
        initial = planner.plan(charter(), (initial_item,), (schedule(initial_item.work_id, "R1", budget=small),))
        first = planner.replan(
            initial,
            (work("WORK-r1", role="builder", risk="R1"),),
            (schedule("WORK-r1", "R1", budget=small),),
            reason="first revision",
            evidence_refs=("event:r1",),
        )
        second = OrchestrationPlan(
            ObjectiveGraph(charter(), (work("WORK-r2", role="builder", risk="R1"),)),
            (schedule("WORK-r2", "R1", budget=small),),
            replaces_digest=first.digest,
            replan_reason="second revision",
            replan_evidence_refs=("event:r2",),
        )
        third = OrchestrationPlan(
            ObjectiveGraph(charter(), (work("WORK-r3", role="builder", risk="R1"),)),
            (schedule("WORK-r3", "R1", budget=Budget(0, 0, 0, 0, 0, 0, 0, 0)),),
            replaces_digest=second.digest,
            replan_reason="third revision",
            replan_evidence_refs=("event:r3",),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            persist_plan(store, initial)
            persist_plan(store, first)
            persist_plan(store, second)
            head = store.events()[-1]["digest"]
            with self.assertRaisesRegex(ValueError, "replan limit"):
                persist_plan(store, third)
            self.assertEqual(head, store.events()[-1]["digest"])
            store.close()

    def test_restart_rejects_a_different_charter_and_preserves_schedule_exactness(self) -> None:
        item = work("WORK-restart", role="builder", risk="R1")
        plan = OrchestratorPlanner().plan(
            charter(), (item,), (schedule(item.work_id, "R1", gate=True),)
        )
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "brain-kernel.sqlite3"
            store = KernelStore(database)
            self.create_mission(store)
            persist_plan(store, plan)
            store.close()
            reopened = KernelStore(database)
            restored = orchestration_plan_from_events(charter(), reopened.events())
            self.assertEqual(plan.schedules, restored.schedules)
            with self.assertRaisesRegex(ValueError, "another charter"):
                orchestration_plan_from_events(
                    charter(base_commit="1" * 40), reopened.events()
                )
            reopened.close()

    def test_fixture_and_operational_plans_cannot_replace_each_other(self) -> None:
        item = work("WORK-operational", role="builder", risk="R1")
        operational = OrchestratorPlanner().plan(
            charter(), (item,), (schedule(item.work_id, "R1"),)
        )
        fixture = DeterministicFixturePlanner().plan(charter(), "bugfix")
        for first, second in ((operational, fixture), (fixture, operational)):
            with self.subTest(first=type(first).__name__), tempfile.TemporaryDirectory() as temporary:
                store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
                self.create_mission(store)
                persist_plan(store, first)
                before_events = store.events()
                before_projection = store.projection()
                with self.assertRaisesRegex(ValueError, "planner kinds"):
                    persist_plan(store, second)
                self.assertEqual(before_events, store.events())
                self.assertEqual(before_projection, store.projection())
                store.close()

    def test_plan_batch_rolls_back_at_every_append_boundary(self) -> None:
        tiny = Budget(20, 1, 10, 10, 10, 1, 1, 0)
        planner = OrchestratorPlanner()
        original = work("WORK-atomic-old", role="builder", risk="R1")
        initial = planner.plan(
            charter(),
            (original,),
            (schedule(original.work_id, "R1", budget=tiny),),
        )
        first = work("WORK-atomic-first", role="builder", risk="R1")
        second = work("WORK-atomic-second", role="builder", risk="R1")
        revised = planner.replan(
            initial,
            (first, second),
            (
                schedule(first.work_id, "R1", budget=tiny),
                schedule(second.work_id, "R1", budget=tiny),
            ),
            reason="atomic replacement",
            evidence_refs=("event:atomic",),
        )
        fail_ids = (
            f"supersede:{revised.digest}:{original.work_id}",
            f"plan:{revised.digest}:{first.work_id}",
            f"plan:{revised.digest}:{second.work_id}",
        )
        for fail_id in fail_ids:
            with self.subTest(fail_id=fail_id), tempfile.TemporaryDirectory() as temporary:
                store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
                self.create_mission(store)
                persist_plan(store, initial)
                before_events = store.events()
                before_projection = store.projection()
                store.connection.execute(
                    """
                    CREATE TRIGGER inject_plan_failure
                    BEFORE INSERT ON events
                    WHEN NEW.event_id = ?
                    BEGIN SELECT RAISE(ABORT, 'injected plan failure'); END
                    """.replace("?", "'" + fail_id + "'")
                )
                store.connection.commit()
                with self.assertRaises(sqlite3.IntegrityError):
                    persist_plan(store, revised)
                self.assertEqual(before_events, store.events())
                self.assertEqual(before_projection, store.projection())
                self.assertEqual(initial.digest, orchestration_plan_from_events(charter(), store.events()).digest)
                store.close()

    def test_mid_batch_idempotency_conflict_changes_nothing(self) -> None:
        tiny = Budget(20, 1, 10, 10, 10, 1, 1, 0)
        planner = OrchestratorPlanner()
        original = work("WORK-conflict-old", role="builder", risk="R1")
        initial = planner.plan(
            charter(), (original,), (schedule(original.work_id, "R1", budget=tiny),)
        )
        first = work("WORK-conflict-a", role="builder", risk="R1")
        second = work("WORK-conflict-b", role="builder", risk="R1")
        revised = planner.replan(
            initial,
            (first, second),
            (
                schedule(first.work_id, "R1", budget=tiny),
                schedule(second.work_id, "R1", budget=tiny),
            ),
            reason="conflict regression",
            evidence_refs=("event:conflict",),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            persist_plan(store, initial)
            previous = store.events()[-1]["digest"]
            store.append(
                KernelEvent(
                    "unrelated-idempotency-owner",
                    "MISSION-orchestrator",
                    "planner.test.conflict",
                    "test",
                    TIME,
                    {},
                    previous_digest=previous,
                ),
                idempotency_key=canonical_digest(
                    {"plan_digest": revised.digest, "work_id": second.work_id}
                ),
            )
            before_events = store.events()
            before_projection = store.projection()
            with self.assertRaises(KernelIntegrityError):
                persist_plan(store, revised)
            self.assertEqual(before_events, store.events())
            self.assertEqual(before_projection, store.projection())
            store.close()

    def test_retry_and_restart_reject_counterfeit_planner_provenance(self) -> None:
        item = work("WORK-genuine", role="builder", risk="R1")
        item_schedule = schedule(item.work_id, "R1")
        plan = OrchestratorPlanner().plan(charter(), (item,), (item_schedule,))
        payload = {
            "charter_digest": charter().digest(),
            "work_item": item.to_document(),
            "plan_digest": plan.digest,
            "schedule": item_schedule.to_document(),
        }
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            previous = store.events()[-1]["digest"]
            store.append(
                KernelEvent(
                    f"plan:{plan.digest}:{item.work_id}",
                    "MISSION-orchestrator",
                    "work.created",
                    "untrusted-preclaimer",
                    "1970-01-01T00:00:00Z",
                    payload,
                    work_id=item.work_id,
                    actor_role="builder",
                    previous_digest=previous,
                ),
                idempotency_key=canonical_digest(
                    {"plan_digest": plan.digest, "work_id": item.work_id}
                ),
            )
            head = store.events()[-1]["digest"]
            with self.assertRaisesRegex(ValueError, "retry conflicts"):
                persist_plan(store, plan)
            self.assertEqual(head, store.events()[-1]["digest"])
            with self.assertRaisesRegex(ValueError, "provenance"):
                orchestration_plan_from_events(charter(), store.events())
            store.close()

    def test_restart_rejects_event_payload_work_id_split_brain(self) -> None:
        item = work("WORK-payload", role="builder", risk="R1")
        item_schedule = schedule(item.work_id, "R1")
        plan = OrchestratorPlanner().plan(charter(), (item,), (item_schedule,))
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            previous = store.events()[-1]["digest"]
            store.append(
                KernelEvent(
                    f"plan:{plan.digest}:WORK-alias",
                    "MISSION-orchestrator",
                    "work.created",
                    "kernel-orchestrator-planner",
                    "1970-01-01T00:00:00Z",
                    {
                        "charter_digest": charter().digest(),
                        "work_item": item.to_document(),
                        "plan_digest": plan.digest,
                        "schedule": item_schedule.to_document(),
                    },
                    work_id="WORK-alias",
                    actor_role="orchestrator",
                    previous_digest=previous,
                )
            )
            self.assertIn("WORK-alias", store.projection()["work"])
            for restore in (orchestration_plan_from_events, graph_from_events):
                with self.assertRaisesRegex(ValueError, "provenance"):
                    restore(charter(), store.events())
            store.close()

    def test_replan_cannot_change_the_durable_charter(self) -> None:
        item = work("WORK-charter-old", role="builder", risk="R1")
        initial = OrchestratorPlanner().plan(
            charter(), (item,), (schedule(item.work_id, "R1"),)
        )
        changed_charter = charter(base_commit="1" * 40)
        replacement = work("WORK-charter-new", role="builder", risk="R1")
        forged = OrchestrationPlan(
            ObjectiveGraph(changed_charter, (replacement,)),
            (schedule(replacement.work_id, "R1"),),
            replaces_digest=initial.digest,
            replan_reason="attempted authority change",
            replan_evidence_refs=("event:forged",),
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            persist_plan(store, initial)
            before = store.events()
            with self.assertRaisesRegex(ValueError, "charter differs"):
                persist_plan(store, forged)
            self.assertEqual(before, store.events())
            store.close()

    def test_fixture_payload_and_exact_retry_remain_legacy_compatible(self) -> None:
        fixture = DeterministicFixturePlanner().plan(charter(), "docs")
        with tempfile.TemporaryDirectory() as temporary:
            store = KernelStore(Path(temporary) / "brain-kernel.sqlite3")
            self.create_mission(store)
            sequences = persist_plan(store, fixture)
            rows = [
                row
                for row in store.events()
                if row["event_type"] == "work.created"
            ]
            self.assertTrue(
                all(set(row["payload"]) == {"work_item", "plan_digest"} for row in rows)
            )
            head = store.events()[-1]["digest"]
            self.assertEqual(sequences, persist_plan(store, fixture))
            self.assertEqual(head, store.events()[-1]["digest"])
            store.close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
