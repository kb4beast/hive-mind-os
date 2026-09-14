import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.pilot_runtime import PilotController, PilotPlan, PilotStore

D = "sha256:" + "a" * 64


class PilotRuntimeTests(unittest.TestCase):
    def test_fresh_pilot_is_durable_and_deferred(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan("pilot", "self", D, ("subject",), 0, 259200, 1, 100, 4, D)
            controller = PilotController(PilotStore(Path(root)), plan)
            self.assertEqual(controller.report().disposition().value, "defer")


if __name__ == "__main__":
    unittest.main()
