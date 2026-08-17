from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import copy_autopilot_fixture

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "controller.py"
SPEC = importlib.util.spec_from_file_location("autopilot_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)

NODE = "ARCH-100"


def git(*args: str, cwd: Path) -> None:
    subprocess.run(("git", *args), cwd=cwd, check=True, capture_output=True)


class WorktreeCoordinationTests(unittest.TestCase):
    """Every worktree of one repository must share one authority location.

    A linked worktree that keeps claims and the repository-wide validation lease
    under its own ``.autopilot/state`` grants authority the other worktrees
    cannot observe, so two checkouts validate the same target concurrently.
    """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        scratch = Path(self.temporary.name)
        self.primary = scratch / "primary"
        self.primary.mkdir()
        copy_autopilot_fixture(
            Path(__file__).resolve().parents[1], self.primary / ".autopilot"
        )
        control_path = self.primary / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(
            json.dumps(control, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (self.primary / ".gitignore").write_text(
            ".autopilot/state/\n", encoding="utf-8"
        )
        git("init", "-q", "-b", "main", cwd=self.primary)
        git("config", "user.email", "tests@example.invalid", cwd=self.primary)
        git("config", "user.name", "tests", cwd=self.primary)
        git("add", "-A", cwd=self.primary)
        git("commit", "-q", "-m", "fixture", cwd=self.primary)
        (self.primary / ".autopilot" / "state").mkdir(exist_ok=True)

        self.linked = scratch / "linked"
        git("worktree", "add", "-q", str(self.linked), "-b", "linked", cwd=self.primary)
        (self.linked / ".autopilot" / "state").mkdir(exist_ok=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_a_linked_worktree_shares_the_primary_authority_location(self) -> None:
        primary_plane = controller.ControlPlane(self.primary)
        linked_plane = controller.ControlPlane(self.linked)
        expected = (self.primary / ".autopilot" / "state").resolve()
        self.assertEqual(primary_plane.coordination_dir.resolve(), expected)
        self.assertEqual(linked_plane.coordination_dir.resolve(), expected)

    def test_the_validation_lease_is_exclusive_across_worktrees(self) -> None:
        primary_plane = controller.ControlPlane(self.primary)
        linked_plane = controller.ControlPlane(self.linked)
        primary_plane.acquire_global_validation_lease(NODE, "owner-primary")
        with self.assertRaisesRegex(controller.AutopilotError, "lease is active"):
            linked_plane.acquire_global_validation_lease(NODE, "owner-linked")
        primary_plane.release_global_validation_lease(NODE, "owner-primary")
        regained = linked_plane.acquire_global_validation_lease(NODE, "owner-linked")
        self.assertEqual(regained["owner"], "owner-linked")

    def test_a_claim_taken_in_one_worktree_is_authority_in_the_other(self) -> None:
        primary_plane = controller.ControlPlane(self.primary)
        linked_plane = controller.ControlPlane(self.linked)
        self.assertEqual(
            primary_plane.claim_path(NODE), linked_plane.claim_path(NODE)
        )
        held = primary_plane.claim_path(NODE)
        held.parent.mkdir(parents=True, exist_ok=True)
        held.write_text(
            json.dumps(
                {
                    "node_id": NODE,
                    "owner": "worker-primary",
                    "expires_at": "2999-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        self.assertIn(NODE, linked_plane.active_claims())

    def test_a_claim_on_another_node_does_not_block_a_second_worktree(self) -> None:
        primary_plane = controller.ControlPlane(self.primary)
        linked_plane = controller.ControlPlane(self.linked)
        other = "CONTRACT-110"
        self.assertNotEqual(
            primary_plane.claim_path(NODE), linked_plane.claim_path(other)
        )
        self.assertEqual(
            primary_plane.claim_path(NODE).parent,
            linked_plane.claim_path(other).parent,
        )

    def test_every_shared_authority_path_resolves_identically(self) -> None:
        """Pin the full shared set so a regression cannot silently localize one.

        Claims and the lease are covered behaviorally above; these paths are
        equally load-bearing -- the reconciliation watermark, the snapshot a
        release binds by digest, and release history read for eligibility.
        """

        primary_plane = controller.ControlPlane(self.primary)
        linked_plane = controller.ControlPlane(self.linked)
        for attribute in (
            "target_record_path",
            "github_snapshot_path",
            "release_history_path",
        ):
            self.assertEqual(
                getattr(primary_plane, attribute),
                getattr(linked_plane, attribute),
                attribute,
            )

    def test_a_reconciled_target_is_visible_from_the_linked_worktree(self) -> None:
        primary_plane = controller.ControlPlane(self.primary)
        linked_plane = controller.ControlPlane(self.linked)
        advanced = "d" * 40
        primary_plane.target_record_path.parent.mkdir(parents=True, exist_ok=True)
        primary_plane.target_record_path.write_text(
            json.dumps({"target_sha": advanced}), encoding="utf-8"
        )
        self.assertEqual(linked_plane.reconciled_target_sha(), advanced)

    def test_evidence_directories_remain_worktree_local(self) -> None:
        linked_plane = controller.ControlPlane(self.linked)
        for directory in (
            linked_plane.receipts_dir,
            linked_plane.blockers_dir,
            linked_plane.questions_dir,
            linked_plane.failures_dir,
            linked_plane.quarantine_dir,
        ):
            self.assertEqual(
                directory.parent.resolve(),
                (self.linked / ".autopilot" / "state").resolve(),
            )

    def test_a_directory_outside_any_worktree_coordinates_with_itself(self) -> None:
        with tempfile.TemporaryDirectory() as isolated:
            root = Path(isolated)
            copy_autopilot_fixture(
                Path(__file__).resolve().parents[1], root / ".autopilot"
            )
            control_path = root / ".autopilot" / "control-plane.json"
            control = json.loads(control_path.read_text(encoding="utf-8"))
            control["verify_git_objects"] = False
            control_path.write_text(
                json.dumps(control, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            plane = controller.ControlPlane(root)
            self.assertEqual(plane.coordination_dir, plane.state_dir)


if __name__ == "__main__":
    unittest.main()
