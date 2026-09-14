import unittest

from hive_mind_os.functional_evaluation import (
    CheckOutcome,
    EvaluationVerdict,
    FunctionalEvaluation,
    verdict_for,
)


class FunctionalEvaluationTests(unittest.TestCase):
    def evaluation(self, **changes):
        values = {
            "episode_id": "episode-1",
            "candidate_digest": "sha256:" + "1" * 64,
            "rubric_digest": "sha256:" + "2" * 64,
            "environment_digest": "sha256:" + "3" * 64,
            "reference_health": CheckOutcome.PASS,
            "required_checks": ("core-loop", "hostile-input"),
            "capability_results": {"core-loop": CheckOutcome.PASS},
            "quality_metrics": {"latency_ms": 4.0},
            "security_results": {"hostile-input": CheckOutcome.PASS},
            "resource_use": {"seconds": 1.0},
            "contamination_status": "CLEAR",
            "evaluator_id": "independent-evaluator",
            "verdict": EvaluationVerdict.PASS,
            "evidence_refs": ("ref:evaluation/1",),
        }
        values.update(changes)
        return FunctionalEvaluation(**values)

    def test_complete_observable_contract_can_pass(self):
        self.assertEqual(self.evaluation().verdict, EvaluationVerdict.PASS)

    def test_empty_or_missing_required_checks_cannot_pass(self):
        self.assertEqual(verdict_for({}), EvaluationVerdict.INCONCLUSIVE)
        with self.assertRaises(ValueError):
            self.evaluation(required_checks=())
        with self.assertRaises(ValueError):
            self.evaluation(security_results={})

    def test_unavailable_and_nonfinite_measurements_fail_closed(self):
        self.assertEqual(
            verdict_for({"runtime": CheckOutcome.UNAVAILABLE}),
            EvaluationVerdict.BLOCKED_ENVIRONMENT,
        )
        with self.assertRaises(ValueError):
            self.evaluation(quality_metrics={"score": float("nan")})


if __name__ == "__main__":
    unittest.main()
