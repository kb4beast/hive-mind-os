from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import controller  # noqa: E402

TARGET_A = "a" * 40
PARENT_A = "1" * 40
TREE_A = "2" * 40
PARENT_TREE_A = "3" * 40
TARGET_B = "b" * 40
PARENT_B = "4" * 40
TREE_B = "5" * 40
PARENT_TREE_B = "6" * 40


class InstrumentedStatusPlane(controller.ControlPlane):
    """Exercise the real status traversal against a deterministic Git graph."""

    def __init__(self, repo_root: Path) -> None:
        self.synthetic_target = TARGET_A
        self.git_calls: Counter[str] = Counter()
        self.node_evaluations: Counter[str] = Counter()
        self.commit_tree_fallbacks = 0
        self.commit_parent_fallbacks = 0
        super().__init__(repo_root)

    @property
    def graph(self) -> Mapping[str, tuple[str, str, str]]:
        return {
            TARGET_A: (PARENT_A, TREE_A, PARENT_TREE_A),
            TARGET_B: (PARENT_B, TREE_B, PARENT_TREE_B),
        }

    def _git(
        self,
        args: Sequence[str],
        *,
        check: bool = False,
        environment: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, environment
        command = args[0]
        self.git_calls[command] += 1
        if command == "rev-parse":
            return subprocess.CompletedProcess(args, 0, self.synthetic_target + "\n", "")
        if command == "log":
            parent, tree, parent_tree = self.graph[self.synthetic_target]
            output = (
                f"{self.synthetic_target}\x1f{parent}\x1f{tree}\x1fhead\x1e"
                f"{parent}\x1f\x1f{parent_tree}\x1froot\x1e"
            )
            return subprocess.CompletedProcess(args, 0, output, "")
        raise AssertionError(f"status bypassed its commit graph via git {command}")

    def reconciled_target_sha(self) -> str:
        return self.synthetic_target

    def _commit_tree(self, commit: str) -> str | None:
        self.commit_tree_fallbacks += 1
        raise AssertionError(f"status did not reuse the observed tree for {commit}")

    def _commit_parents(self, commit: str) -> tuple[str, ...]:
        self.commit_parent_fallbacks += 1
        raise AssertionError(f"status did not reuse the observed parents for {commit}")

    def node_view(self, node_id: str) -> controller.NodeView:
        self.node_evaluations[node_id] += 1
        parent, tree, _ = self.graph[self.synthetic_target]
        target = self.current_target_sha()
        if not self.git_object_exists(target):
            raise AssertionError("snapshot target unexpectedly disappeared")
        if not self.is_ancestor(parent, target):
            raise AssertionError("snapshot parent unexpectedly lost ancestry")
        if self._commit_tree(target) != tree:
            raise AssertionError("snapshot tree changed during status")
        if self._commit_parents(target) != (parent,):
            raise AssertionError("snapshot parents changed during status")
        return super().node_view(node_id)


class StatusPerformanceRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source, self.root / ".autopilot")
        shutil.rmtree(self.root / ".autopilot" / "state", ignore_errors=True)
        (self.root / ".autopilot" / "state").mkdir()
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = True
        control_path.write_text(
            json.dumps(control, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.plane = InstrumentedStatusPlane(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_status_memoizes_dag_and_git_only_within_each_snapshot(self) -> None:
        first = self.plane.observe_status()
        self.assertEqual(first["target_sha"], TARGET_A)
        self.assertEqual(set(self.plane.node_evaluations), set(self.plane._nodes))
        self.assertTrue(all(count == 1 for count in self.plane.node_evaluations.values()))
        self.assertEqual(self.plane.git_calls, Counter({"rev-parse": 2, "log": 1}))
        self.assertEqual(self.plane.commit_tree_fallbacks, 0)
        self.assertEqual(self.plane.commit_parent_fallbacks, 0)

        self.plane.synthetic_target = TARGET_B
        second = self.plane.observe_status()

        self.assertEqual(second["target_sha"], TARGET_B)
        self.assertTrue(all(count == 2 for count in self.plane.node_evaluations.values()))
        self.assertEqual(self.plane.git_calls, Counter({"rev-parse": 4, "log": 2}))
        self.assertEqual(self.plane.commit_tree_fallbacks, 0)
        self.assertEqual(self.plane.commit_parent_fallbacks, 0)


if __name__ == "__main__":
    unittest.main()
