from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "controller.py"
SPEC = importlib.util.spec_from_file_location("blocker_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


class BlockerProtocolTests(unittest.TestCase):
    def test_blocker_packet_names_cause_fix_and_retry_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            shutil.copytree(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            packet = plane.record_blocker(
                "ARCH-100",
                category="remote-authority",
                cause="remote TLS revocation validation failed",
                fix="restore certificate revocation validation or provide a trusted network path",
                retry_when="remote inspection succeeds without disabling TLS controls",
                attempted_command=["git", "ls-remote", "origin"],
                evidence_refs=["test:evidence"],
            )
            self.assertTrue(packet["blocker_id"])
            self.assertEqual(packet["status"], "OPEN")
            self.assertTrue(plane.safe_retry_allowed(packet))
            self.assertEqual(packet["recovery_action"]["action"], "REPORT_BLOCKER")
            stored = root / ".autopilot" / "state" / "blockers" / "ARCH-100.jsonl"
            self.assertIn("retry_when", stored.read_text(encoding="utf-8"))

    def test_permission_does_not_authorize_security_bypass(self) -> None:
        self.assertFalse(
            controller.ControlPlane.safe_retry_allowed(
                {"fix": "disable TLS certificate revocation", "retry_when": "retry"}
            )
        )

    def test_stale_dispatcher_release_requests_orchestrator_subtask(self) -> None:
        action = controller.ControlPlane.recovery_action(
            {"category": "dispatcher", "cause": "dispatcher release is stale", "fix": "rerun dispatch"}
        )
        self.assertEqual(action["action"], "SPAWN_SUBTASK")
        self.assertEqual(action["role"], "orchestrator")
