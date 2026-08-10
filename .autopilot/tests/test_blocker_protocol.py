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
            stored = root / ".autopilot" / "state" / "blockers" / "ARCH-100.jsonl"
            self.assertIn("retry_when", stored.read_text(encoding="utf-8"))
