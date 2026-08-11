from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import copy_autopilot_fixture

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "controller.py"
SPEC = importlib.util.spec_from_file_location("singleton_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


class SingletonReleaseTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = Path(__file__).resolve().parents[1]
        copy_autopilot_fixture(source, self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        self.plane = controller.ControlPlane(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_execution_target_is_singleton_release_branch(self) -> None:
        self.assertEqual(self.plane.execution_mode, "singleton-release-branch")
        self.assertEqual(self.plane.target_branch, "release/hive-mind-os-singleton-20260811-r4")
        self.assertEqual(self.plane.final_integration_branch, "main")
        self.assertEqual(
            self.plane.control["target"]["protected_until_final_integration"],
            ["main"],
        )

    def test_configuration_rejects_main_as_singleton_target(self) -> None:
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["target"]["branch"] = "main"
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        plane = controller.ControlPlane(self.root)
        self.assertTrue(
            any("must not equal final integration branch" in issue for issue in plane.validate_configuration())
        )


if __name__ == "__main__":
    unittest.main()
