import unittest
from tempfile import TemporaryDirectory

from hive_mind_os.scoped_learning import (
    DurableChampionRegistry,
    LearningRoute,
    LearningScope,
    PromotionState,
    ScopedChallenger,
)


class ScopedLearningTests(unittest.TestCase):
    def challenger(self, **changes):
        values = {
            "subject_boundary_digest": "sha256:" + "1" * 64,
            "champion_id": "builder",
            "parent_digest": "sha256:" + "2" * 64,
            "candidate_digest": "sha256:" + "3" * 64,
            "evaluation_plan_digest": "sha256:" + "4" * 64,
            "evaluator_id": "independent-evaluator",
            "verdict_ref": "ref:verdict/1",
            "promotion_state": PromotionState.ELIGIBLE,
        }
        values.update(changes)
        return ScopedChallenger(**values)

    def test_target_learning_cannot_cross_subjects(self):
        with self.assertRaises(ValueError):
            LearningRoute(
                "subject-a",
                LearningScope.TARGET_APP,
                "subject-b",
                ("ref:evidence/1",),
                "strategy",
                "sha256:" + "5" * 64,
                "sha256:" + "6" * 64,
            )

    def test_only_eligible_independent_challenger_promotes_once(self):
        challenger = self.challenger()
        with TemporaryDirectory() as directory:
            path = f"{directory}/champions.json"
            registry = DurableChampionRegistry(path)
            promoted = registry.promote(
                challenger.subject_boundary_digest,
                challenger,
                challenger.parent_digest,
            )
            self.assertEqual(promoted.promotion_state, PromotionState.PROMOTED)
            restored = DurableChampionRegistry(path).current(
                challenger.subject_boundary_digest
            )
            self.assertEqual(restored, promoted)
            with self.assertRaises(ValueError):
                registry.promote(
                    challenger.subject_boundary_digest,
                    self.challenger(candidate_digest="sha256:" + "7" * 64),
                    challenger.parent_digest,
                )

    def test_draft_or_self_evaluated_challenger_is_denied(self):
        with self.assertRaises(ValueError):
            self.challenger(evaluator_id="builder")
        with TemporaryDirectory() as directory:
            registry = DurableChampionRegistry(f"{directory}/champions.json")
            with self.assertRaises(ValueError):
                registry.promote(
                    "sha256:" + "1" * 64,
                    self.challenger(promotion_state=PromotionState.PROPOSED),
                    "sha256:" + "2" * 64,
                )


if __name__ == "__main__":
    unittest.main()
