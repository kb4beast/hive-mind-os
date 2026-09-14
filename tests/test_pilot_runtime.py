import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.pilot_runtime import PilotController, PilotPlan, PilotStore
from hive_mind_os.whole_os_qualification import Disposition, ExternalObligation

D = "sha256:" + "a" * 64


class PilotRuntimeTests(unittest.TestCase):
    def test_fresh_pilot_is_durable_and_deferred(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan("pilot", "self", D, ("subject",), 0, 259200, 1, 100, 4, D)
            controller = PilotController(PilotStore(Path(root)), plan)
            report = controller.report()
            self.assertEqual(report.elapsed_seconds, 0)
            self.assertEqual(report.disposition().value, "defer")

    def test_observation_watermark_is_monotonic_and_bounded(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan("pilot", "self", D, ("subject",), 10, 259210, 1, 100, 4, D)
            controller = PilotController(PilotStore(Path(root)), plan)
            controller.record_observation(20)
            self.assertEqual(controller.report().ended_at, 20)
            with self.assertRaisesRegex(ValueError, "backward"):
                controller.record_observation(19)
            with self.assertRaisesRegex(ValueError, "planned window"):
                controller.record_observation(259211)

    def test_retries_reconcile_one_external_obligation(self):
        with TemporaryDirectory() as root:
            plan = PilotPlan("pilot", "external", D, ("subject",), 0, 259200, 1, 100, 4, D)
            controller = PilotController(PilotStore(Path(root)), plan)
            obligation = ExternalObligation(
                "runtime",
                Disposition.BLOCKED_CAPABILITY,
                "runtime unavailable",
                ("R14",),
            )
            controller.record_controls(obligations=(obligation,))
            controller.record_controls(obligations=(obligation,))
            self.assertEqual(controller.report().obligations, (obligation,))
            changed = ExternalObligation(
                "runtime",
                Disposition.BLOCKED_CAPABILITY,
                "different content",
                ("R14",),
            )
            with self.assertRaisesRegex(ValueError, "different content"):
                controller.record_controls(obligations=(changed,))


if __name__ == "__main__":
    unittest.main()
