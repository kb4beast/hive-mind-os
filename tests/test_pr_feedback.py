import unittest

from hive_mind_os.pr_feedback import (
    FeedbackDecision,
    FeedbackObservation,
    FeedbackObserver,
)


class FeedbackDurabilityTests(unittest.TestCase):
    def test_restore_preserves_repair_chain_and_duplicate_identity(self):
        observation = FeedbackObservation(
            "github", "1", "head", "event", "bot", 1, "test failed", "digest"
        )
        first = FeedbackObserver()
        result = first.observe(observation, "head")
        self.assertEqual(result.decision, FeedbackDecision.ACTIONABLE)
        restored = FeedbackObserver()
        restored.restore(first.snapshot())
        self.assertIn(result.package_id, restored.repairs)
        self.assertEqual(
            restored.observe(observation, "head").decision,
            FeedbackDecision.DUPLICATE,
        )


if __name__ == "__main__":
    unittest.main()
