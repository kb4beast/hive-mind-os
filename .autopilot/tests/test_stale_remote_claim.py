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
if str(MODULE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = importlib.util.spec_from_file_location("stale_claim_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)

NODE = "MISSION-400"
BRANCH = "autopilot/mission-400"
OWNER = "codex:mission-400-fixture"


def git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(root)) + arguments,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


class StaleRemoteClaimTests(unittest.TestCase):
    """A session-local claim file must never be the only key to a remote ref."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.root = base / "work"
        self.origin = base / "origin.git"
        self.root.mkdir()
        subprocess.run(
            ("git", "init", "--bare", "--initial-branch=main", str(self.origin)),
            check=True,
            capture_output=True,
        )
        git(self.root, "init", "--initial-branch=main")
        git(self.root, "config", "user.name", "Fixture")
        git(self.root, "config", "user.email", "fixture@hive-mind.invalid")
        source = Path(__file__).resolve().parents[1]
        copy_autopilot_fixture(source, self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        controller.atomic_write_json(control_path, control)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "fixture base")
        git(self.root, "remote", "add", "origin", str(self.origin))
        git(self.root, "push", "-u", "origin", "main")
        self.target = git(self.root, "rev-parse", "HEAD")
        self.plane = controller.ControlPlane(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish_claim(self, *, expires_at: str, owner: str = OWNER) -> str:
        """Reproduce publish_remote_claim's commit shape: target tree, one parent."""

        tree = git(self.root, "rev-parse", f"{self.target}^{{tree}}")
        message = json.dumps(
            {
                "kind": "hive-mind-autopilot-remote-claim-v1",
                "node_id": NODE,
                "owner": owner,
                "expires_at": expires_at,
                "plan_fingerprint": self.plane.expected_plan_fingerprint,
                "target_sha": self.target,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        commit = git(
            self.root, "commit-tree", tree, "-p", self.target, "-m", message
        )
        git(self.root, "push", "origin", f"{commit}:refs/heads/{BRANCH}")
        return commit

    def remote_head(self) -> str | None:
        listed = git(self.root, "ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}")
        return listed.split()[0] if listed else None

    def test_expired_untouched_claim_is_retired(self) -> None:
        claim = self.publish_claim(expires_at="2020-01-01T00:00:00Z")
        self.assertEqual(self.remote_head(), claim)
        released = self.plane.reap_stale_remote_claim(
            NODE, OWNER, reason="worker session ended"
        )
        self.assertEqual(released["outcome"], "retired")
        self.assertEqual(released["claim_commit"], claim)
        self.assertIsNone(self.remote_head())
        recorded = (self.root / ".autopilot" / "state" / "releases.jsonl").read_text(
            encoding="utf-8"
        )
        self.assertIn(claim, recorded)

    def test_live_claim_is_never_reaped(self) -> None:
        claim = self.publish_claim(expires_at="2099-01-01T00:00:00Z")
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.reap_stale_remote_claim(NODE, OWNER, reason="impatient")
        self.assertIn("live", str(raised.exception))
        self.assertEqual(self.remote_head(), claim)

    def test_owner_mismatch_is_refused(self) -> None:
        claim = self.publish_claim(expires_at="2020-01-01T00:00:00Z")
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.reap_stale_remote_claim(
                NODE, "codex:someone-else", reason="guess"
            )
        self.assertIn("owner does not match", str(raised.exception))
        self.assertEqual(self.remote_head(), claim)

    def test_published_work_is_never_deleted(self) -> None:
        self.publish_claim(expires_at="2020-01-01T00:00:00Z")
        (self.root / "worker-output.txt").write_text("real work\n", encoding="utf-8")
        git(self.root, "add", "worker-output.txt")
        git(self.root, "commit", "-m", "worker implementation")
        advanced = git(self.root, "rev-parse", "HEAD")
        git(self.root, "push", "--force", "origin", f"{advanced}:refs/heads/{BRANCH}")
        with self.assertRaises(controller.ClaimError) as raised:
            self.plane.reap_stale_remote_claim(NODE, OWNER, reason="cleanup")
        self.assertIn("carries", str(raised.exception))
        self.assertEqual(self.remote_head(), advanced)

    def test_absent_branch_is_not_an_error(self) -> None:
        released = self.plane.reap_stale_remote_claim(
            NODE, OWNER, reason="nothing to retire"
        )
        self.assertEqual(released["outcome"], "absent")


if __name__ == "__main__":
    unittest.main()
