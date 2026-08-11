from __future__ import annotations

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
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.planner import (
    OrchestratorPlanner,
    WorkSchedule,
    graph_from_events,
    persist_plan,
)
from hive_mind_os.brain_kernel.store import KernelStore


DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40
TIME = "2026-08-11T04:00:00Z"


def charter() -> MissionCharter:
    return MissionCharter(
        1,
        "MISSION-orchestrator",
        TIME,
        "deliver a bounded change",
        ("ACCEPT-1",),
        "repo",
        SHA,
        "release/hive-mind-os-singleton-20260810-r2",
        DIGEST,
        DIGEST,
        DIGEST,
        Budget(120, 4, 100, 100, 100, 8, 4, 2),
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
) -> WorkItem:
    return WorkItem(
        work_id,
        "MISSION-orchestrator",
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
        (f"work/{work_id}.txt",),
        (),
        {},
        2,
        WorkState.PROPOSED,
        DIGEST,
        DIGEST,
    )


def schedule(work_id: str, risk: str, *, gate: bool = False) -> WorkSchedule:
    return WorkSchedule(
        work_id,
        Budget(60, 2, 50, 50, 50, 4, 2, 1),
        risk,
        ("stop when the attempt budget or acceptance boundary is reached",),
        ("curator", "architect"),
        ("HUMAN-RELEASE",) if gate else (),
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
            (schedule(release.work_id, "R2", gate=True), schedule(prepare.work_id, "R1")),
        )

        self.assertEqual((prepare.work_id, release.work_id), tuple(
            item.work_id for item in plan.graph.ordered_items()
        ))
        document = plan.to_document()
        release_schedule = next(item for item in document["schedules"] if item["work_id"] == release.work_id)
        release_work = next(item for item in document["work_items"] if item["work_id"] == release.work_id)
        self.assertEqual(["HUMAN-RELEASE"], release_schedule["human_gates"])
        self.assertEqual("R2", release_schedule["risk_lane"])
        self.assertEqual(60, release_schedule["budget"]["max_wall_seconds"])
        self.assertTrue(release_schedule["stop_conditions"])
        self.assertEqual([prepare.work_id], release_work["dependencies"])
        self.assertEqual([f"work/{release.work_id}.txt"], release_work["write_scope"])

    def test_budget_stop_tests_fail_closed_for_unbounded_or_unchartered_schedule(self) -> None:
        item = work("WORK-prepare", role="builder", risk="R1")
        with self.assertRaisesRegex(ValueError, "stop conditions"):
            OrchestratorPlanner().plan(
                charter(),
                (item,),
                (WorkSchedule(item.work_id, Budget(1, 1, 1, 1, 1, 1, 1, 1), "R1", (), ("curator",), ()),),
            )
        with self.assertRaisesRegex(ValueError, "chartered"):
            OrchestratorPlanner().plan(
                charter(),
                (item,),
                (WorkSchedule(item.work_id, Budget(1, 1, 1, 1, 1, 1, 1, 1), "R1", ("stop",), ("curator",), ("HUMAN-UNAPPROVED",)),),
            )

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
            store.append(KernelEvent("mission-created", "MISSION-orchestrator", "mission.created", "test", TIME, {}, previous_digest=None))
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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
