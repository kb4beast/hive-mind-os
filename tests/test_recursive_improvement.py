import unittest

from hive_mind_os.recursive_improvement import (
    ExperimentCandidate,
    ExperimentEvidence,
    ExperimentVerdict,
    MetricDirection,
    MetricObservation,
    MetricSpec,
    RecursiveImprovementContract,
    RecursiveImprovementController,
    RecursiveImprovementGate,
)


class RecursiveImprovementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = RecursiveImprovementContract(
            primary=MetricSpec(
                "task_score",
                MetricDirection.MAXIMIZE,
                minimum_effect=0.05,
            ),
            guardrails=(
                MetricSpec(
                    "latency_ms",
                    MetricDirection.MINIMIZE,
                    maximum_regression=5.0,
                    hard_guardrail=True,
                ),
                MetricSpec(
                    "trust_score",
                    MetricDirection.MAXIMIZE,
                    maximum_regression=0.01,
                    hard_guardrail=True,
                ),
            ),
            minimum_repetitions=3,
            noise_multiplier=2.0,
            patience=3,
            max_experiments=10,
        )
        self.candidate = ExperimentCandidate(
            id="challenger-1",
            parent_champion_id="champion-1",
            hypothesis="Use a more precise retrieval strategy",
            changed_paths=("src/retrieval.py",),
            rollback_ref="git:champion-1",
        )

    def evidence(
        self,
        *,
        task_candidate=(1.20, 1.21, 1.19),
        latency_candidate=(99.0, 100.0, 98.0),
        trust_candidate=(0.91, 0.91, 0.90),
        evaluator="curator-1",
        artifacts=("artifact:test-report", "artifact:diff"),
        gaming=(),
        violations=(),
        accessed_holdout=False,
        fingerprint=None,
    ) -> ExperimentEvidence:
        return ExperimentEvidence(
            candidate=self.candidate,
            contract_fingerprint=fingerprint or self.contract.fingerprint,
            proposer_id="optimizer-1",
            builder_id="builder-1",
            evaluator_id=evaluator,
            observations=(
                MetricObservation("task_score", (1.0, 1.0, 1.0), task_candidate),
                MetricObservation("latency_ms", (100.0, 100.0, 100.0), latency_candidate),
                MetricObservation("trust_score", (0.90, 0.90, 0.90), trust_candidate),
            ),
            artifact_refs=artifacts,
            metric_gaming_signals=gaming,
            policy_violations=violations,
            accessed_holdout=accessed_holdout,
        )

    def test_significant_reproduced_improvement_is_kept(self) -> None:
        decision = RecursiveImprovementGate(self.contract).evaluate(self.evidence())
        self.assertEqual(decision.verdict, ExperimentVerdict.KEEP)
        primary_effect = decision.primary_effect
        required_effect = decision.required_effect
        self.assertIsNotNone(primary_effect)
        self.assertIsNotNone(required_effect)
        assert primary_effect is not None and required_effect is not None
        self.assertGreater(primary_effect, required_effect)
        self.assertEqual(decision.next_non_improvement_count, 0)

    def test_metric_gaming_or_holdout_access_quarantines_candidate(self) -> None:
        decision = RecursiveImprovementGate(self.contract).evaluate(
            self.evidence(gaming=("candidate substituted cached expected output",))
        )
        self.assertEqual(decision.verdict, ExperimentVerdict.QUARANTINE)
        self.assertTrue(any("metric gaming" in reason for reason in decision.reasons))

        holdout = RecursiveImprovementGate(self.contract).evaluate(
            self.evidence(accessed_holdout=True)
        )
        self.assertEqual(holdout.verdict, ExperimentVerdict.QUARANTINE)

    def test_actor_cannot_evaluate_its_own_candidate(self) -> None:
        decision = RecursiveImprovementGate(self.contract).evaluate(
            self.evidence(evaluator="builder-1")
        )
        self.assertEqual(decision.verdict, ExperimentVerdict.QUARANTINE)
        self.assertTrue(any("own candidate" in reason for reason in decision.reasons))

    def test_hard_guardrail_regression_discards_candidate(self) -> None:
        decision = RecursiveImprovementGate(self.contract).evaluate(
            self.evidence(latency_candidate=(108.0, 109.0, 107.0))
        )
        self.assertEqual(decision.verdict, ExperimentVerdict.DISCARD)
        self.assertTrue(any("guardrail" in reason for reason in decision.reasons))

    def test_tiny_noisy_lift_is_retested_not_promoted(self) -> None:
        evidence = self.evidence(task_candidate=(1.01, 1.03, 0.99))
        decision = RecursiveImprovementGate(self.contract).evaluate(evidence)
        self.assertEqual(decision.verdict, ExperimentVerdict.RETEST)
        primary_effect = decision.primary_effect
        required_effect = decision.required_effect
        self.assertIsNotNone(primary_effect)
        self.assertIsNotNone(required_effect)
        assert primary_effect is not None and required_effect is not None
        self.assertLessEqual(primary_effect, required_effect)

    def test_diminishing_returns_stop_after_patience(self) -> None:
        evidence = self.evidence(task_candidate=(1.01, 1.03, 0.99))
        decision = RecursiveImprovementGate(self.contract).evaluate(
            evidence,
            consecutive_non_improvements=2,
            experiments_completed=4,
        )
        self.assertEqual(decision.verdict, ExperimentVerdict.STOP)
        self.assertTrue(any("diminishing returns" in reason for reason in decision.reasons))

    def test_contract_mutation_and_missing_artifacts_quarantine(self) -> None:
        changed = RecursiveImprovementGate(self.contract).evaluate(
            self.evidence(fingerprint="mutated")
        )
        self.assertEqual(changed.verdict, ExperimentVerdict.QUARANTINE)

        missing = RecursiveImprovementGate(self.contract).evaluate(
            self.evidence(artifacts=())
        )
        self.assertEqual(missing.verdict, ExperimentVerdict.QUARANTINE)

    def test_controller_evaluates_without_mutating_authoritative_champion(self) -> None:
        controller = RecursiveImprovementController(self.contract, "champion-1")
        decision = controller.evaluate(self.evidence())
        self.assertEqual(decision.verdict, ExperimentVerdict.KEEP)
        self.assertEqual(controller.champion_id, "champion-1")
        self.assertEqual(controller.pending_candidate_id, "challenger-1")
        self.assertEqual(controller.evaluated_candidate_ids, ["challenger-1"])
        self.assertEqual(len(controller.decisions), 1)

        stale_candidate = ExperimentCandidate(
            id="challenger-2",
            parent_champion_id="challenger-1",
            hypothesis="Built from a stale baseline",
            changed_paths=("src/stale.py",),
            rollback_ref="git:champion-1",
        )
        stale_evidence = ExperimentEvidence(
            candidate=stale_candidate,
            contract_fingerprint=self.contract.fingerprint,
            proposer_id="optimizer-2",
            builder_id="builder-2",
            evaluator_id="curator-2",
            observations=self.evidence().observations,
            artifact_refs=("artifact:stale",),
        )
        stale = controller.evaluate(stale_evidence)
        self.assertEqual(stale.verdict, ExperimentVerdict.QUARANTINE)
        self.assertEqual(controller.champion_id, "champion-1")
        self.assertEqual(controller.pending_candidate_id, "challenger-1")
        self.assertEqual(
            controller.evaluated_candidate_ids,
            ["challenger-1", "challenger-2"],
        )
        self.assertEqual(len(controller.decisions), 2)


if __name__ == "__main__":
    unittest.main()
