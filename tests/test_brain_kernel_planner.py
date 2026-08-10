from __future__ import annotations

import json
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
from hive_mind_os.brain_kernel.objectives import ObjectiveGraph, PlanLimits
from hive_mind_os.brain_kernel.planner import (
    DeterministicFixturePlanner,
    graph_from_events,
    persist_plan,
)
from hive_mind_os.brain_kernel.store import KernelStore
from hive_mind_os.cli import _run_kernel_graph, _run_kernel_plan

DIGEST = "sha256:" + "0" * 64
SHA = "0" * 40
TIME = "2026-08-07T12:00:00Z"


def charter(*, acceptance: tuple[str, ...] = ("ACCEPT-1",)) -> MissionCharter:
    return MissionCharter(1, "MISSION-plan", TIME, "deliver a bounded change", acceptance, "repo", SHA, "codex/phase", DIGEST, DIGEST, DIGEST, Budget(1, 0, 0, 0, 0, 0, 8, 3), (), (), (), MissionState.CREATED)


def work(work_id: str, *, dependencies: tuple[str, ...] = (), parent: str | None = None, depth: int = 0, scope: tuple[str, ...] = (), acceptance: tuple[str, ...] = ("ACCEPT-1",)) -> WorkItem:
    return WorkItem(work_id, "MISSION-plan", parent, depth, work_id, "do work", "builder", "R1", dependencies, (), (), acceptance, scope, (), {}, 1, WorkState.PROPOSED, DIGEST, DIGEST)


class KernelPlannerTests(unittest.TestCase):
    def test_fixture_kinds_are_deterministic_and_identify_leaf_ready_work(self) -> None:
        planner = DeterministicFixturePlanner()
        for kind in ("bugfix", "feature", "refactor", "docs", "integration"):
            first = planner.plan(charter(), kind)
            second = planner.plan(charter(), kind)
            self.assertEqual(first.digest, second.digest)
            self.assertEqual(first.graph.digest, second.graph.digest)
            self.assertEqual(1, len(first.graph.ready_items()))
            self.assertIn("implementation", first.graph.ready_items()[0].work_id)

    def test_graph_rejects_cycles_orphans_missing_acceptance_limits_and_write_races(self) -> None:
        with self.assertRaisesRegex(ValueError, "cycle"):
            ObjectiveGraph(charter(), (work("WORK-one", dependencies=("WORK-two",)), work("WORK-two", dependencies=("WORK-one",))))
        with self.assertRaisesRegex(ValueError, "orphan"):
            ObjectiveGraph(charter(), (work("WORK-one", parent="WORK-missing", depth=1),))
        with self.assertRaisesRegex(ValueError, "missing charter acceptance"):
            ObjectiveGraph(charter(), (work("WORK-one", acceptance=()),))
        with self.assertRaisesRegex(ValueError, "work item limit"):
            ObjectiveGraph(charter(), (work("WORK-one"), work("WORK-two")), limits=PlanLimits(1, 3))
        with self.assertRaisesRegex(ValueError, "overlapping write scopes"):
            ObjectiveGraph(charter(), (work("WORK-one", scope=("src",)), work("WORK-two", scope=("src/main.py",))))
        graph = ObjectiveGraph(charter(), (work("WORK-one", scope=("src",)), work("WORK-two", dependencies=("WORK-one",), scope=("src/main.py",))))
        self.assertEqual(("WORK-one", "WORK-two"), tuple(item.work_id for item in graph.ordered_items()))

    def test_persisted_plan_survives_restart_and_replanning_supersedes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "brain-kernel.sqlite3"
            store = KernelStore(database)
            store.append(KernelEvent("MISSION-plan-created", "MISSION-plan", "mission.created", "test", TIME, {}, previous_digest=None))
            initial = DeterministicFixturePlanner().plan(charter(), "bugfix")
            self.assertEqual(2, len(persist_plan(store, initial)))
            store.close()
            reopened = KernelStore(database)
            restored = graph_from_events(charter(), reopened.events())
            self.assertEqual(initial.graph.digest, restored.digest)
            revised_charter = charter(acceptance=("ACCEPT-1", "ACCEPT-2"))
            revised = DeterministicFixturePlanner().plan(revised_charter, "bugfix")
            persist_plan(reopened, revised)
            self.assertEqual(revised.graph.digest, graph_from_events(revised_charter, reopened.events()).digest)
            self.assertEqual(2, sum(1 for value in reopened.projection()["work"].values() if value["status"] == "SUPERSEDED"))
            reopened.close()

    def test_plan_and_graph_cli_use_only_local_fixture_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / "state"
            state_dir.mkdir()
            store = KernelStore(KernelStore.database_path(state_dir))
            store.append(
                KernelEvent(
                    "MISSION-plan-created",
                    "MISSION-plan",
                    "mission.created",
                    "test",
                    TIME,
                    {},
                    previous_digest=None,
                )
            )
            store.close()
            charter_path = root / "charter.json"
            charter_path.write_text(
                json.dumps(charter().to_document()), encoding="utf-8"
            )
            plan_args = type("Args", (), {"charter": str(charter_path), "mission_id": "MISSION-plan", "fixture": "docs", "state_dir": str(state_dir), "json_output": True})()
            self.assertEqual(0, _run_kernel_plan(plan_args))
            graph_args = type("Args", (), {"charter": str(charter_path), "mission_id": "MISSION-plan", "state_dir": str(state_dir), "json_output": True})()
            self.assertEqual(0, _run_kernel_graph(graph_args))
