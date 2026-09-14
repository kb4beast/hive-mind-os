from __future__ import annotations

import unittest

from hive_mind_os.cohort_policy import (
    CheckpointDisposition,
    CohortExecutionMode,
    CohortExecutionPolicy,
    CohortPhase,
    CohortPolicyError,
    DeferredObligation,
    EffectClass,
)
from hive_mind_os.policy import Action


class CohortExecutionPolicyTests(unittest.TestCase):
    def test_cohort_is_the_high_throughput_default(self) -> None:
        policy = CohortExecutionPolicy()

        self.assertEqual(CohortExecutionMode.COHORT, policy.mode)
        self.assertEqual(8, policy.max_parallel_packages)

    def test_closed_configuration_round_trips_and_is_digest_bound(self) -> None:
        document = {
            "schema_version": 1,
            "execution_mode": "cohort",
            "max_parallel_packages": 8,
            "convergence_gate": "all_runnable_packages_terminal",
        }
        policy = CohortExecutionPolicy.from_document(document)
        self.assertEqual(CohortExecutionMode.COHORT, policy.mode)
        self.assertEqual(8, policy.max_parallel_packages)
        self.assertEqual(document, policy.to_document())
        self.assertTrue(policy.digest.startswith("sha256:"))

        with self.assertRaisesRegex(CohortPolicyError, "unknown shape"):
            CohortExecutionPolicy.from_document({**document, "skip_review": True})
        with self.assertRaisesRegex(CohortPolicyError, "cannot be weakened"):
            CohortExecutionPolicy.from_document(
                {**document, "convergence_gate": "first_package_finished"}
            )

    def test_cohort_mode_defers_complete_assurance_bundle_until_convergence(
        self,
    ) -> None:
        policy = CohortExecutionPolicy(CohortExecutionMode.COHORT, 12)
        decision = policy.checkpoint(
            EffectClass.ROUTINE_REVERSIBLE, CohortPhase.IMPLEMENTATION
        )
        self.assertEqual(
            CheckpointDisposition.DEFER_TO_COHORT_END, decision.disposition
        )
        self.assertTrue(decision.may_continue)
        self.assertEqual(
            {
                DeferredObligation.ROUTINE_REVIEW,
                DeferredObligation.EVIDENCE_AGGREGATION,
                DeferredObligation.INDEPENDENT_VERIFICATION,
            },
            set(decision.obligations),
        )

        for phase in (CohortPhase.CONVERGENCE, CohortPhase.CLOSEOUT):
            with self.subTest(phase=phase):
                convergence = policy.checkpoint(EffectClass.ROUTINE_REVERSIBLE, phase)
                self.assertEqual(
                    CheckpointDisposition.REQUIRE_NOW, convergence.disposition
                )
                self.assertFalse(convergence.may_continue)

    def test_strict_mode_keeps_routine_assurance_inline(self) -> None:
        policy = CohortExecutionPolicy(CohortExecutionMode.STRICT, 1)
        decision = policy.checkpoint(
            EffectClass.ROUTINE_REVERSIBLE, CohortPhase.IMPLEMENTATION
        )
        self.assertEqual(CheckpointDisposition.REQUIRE_NOW, decision.disposition)
        self.assertFalse(decision.may_continue)

    def test_every_hard_gate_fails_closed_in_every_mode_and_phase(self) -> None:
        for mode in CohortExecutionMode:
            policy = CohortExecutionPolicy(mode, 8)
            for phase in CohortPhase:
                for effect in policy.HARD_GATE_EFFECTS:
                    with self.subTest(mode=mode, phase=phase, effect=effect):
                        decision = policy.checkpoint(effect, phase)
                        self.assertEqual(
                            CheckpointDisposition.BLOCKED, decision.disposition
                        )
                        self.assertFalse(decision.may_continue)

    def test_existing_effect_actions_map_to_immediate_gates(self) -> None:
        policy = CohortExecutionPolicy(CohortExecutionMode.COHORT, 8)
        cases = (
            (Action.MANAGE_SECRETS, {}, EffectClass.SECRET_ACCESS),
            (Action.SPEND_MONEY, {}, EffectClass.SPENDING),
            (Action.DEPLOY, {}, EffectClass.DEPLOYMENT),
            (
                Action.MERGE_PULL_REQUEST,
                {"protected_target": True},
                EffectClass.PROTECTED_MERGE,
            ),
            (Action.WRITE_WORKSPACE, {"destructive": True}, EffectClass.DESTRUCTIVE),
            (Action.RUN_COMMANDS, {"irreversible": True}, EffectClass.IRREVERSIBLE),
            (
                Action.WRITE_WORKSPACE,
                {"authority_present": False},
                EffectClass.MISSING_AUTHORITY,
            ),
        )
        for action, flags, expected in cases:
            with self.subTest(action=action, flags=flags):
                decision = policy.checkpoint_action(
                    action, CohortPhase.IMPLEMENTATION, **flags
                )
                self.assertEqual(expected, decision.effect)
                self.assertEqual(CheckpointDisposition.BLOCKED, decision.disposition)

    def test_routine_action_does_not_bypass_underlying_policy_engine(self) -> None:
        policy = CohortExecutionPolicy(CohortExecutionMode.COHORT, 8)
        decision = policy.checkpoint_action(
            Action.RUN_TESTS, CohortPhase.IMPLEMENTATION
        )
        self.assertEqual(EffectClass.ROUTINE_REVERSIBLE, decision.effect)
        self.assertEqual(
            CheckpointDisposition.DEFER_TO_COHORT_END, decision.disposition
        )
        self.assertIn("assurance", decision.reason)

    def test_untyped_input_and_invalid_parallelism_fail_closed(self) -> None:
        with self.assertRaises(CohortPolicyError):
            CohortExecutionPolicy(CohortExecutionMode.COHORT, 0)
        policy = CohortExecutionPolicy(CohortExecutionMode.COHORT, 2)
        decision = policy.checkpoint("routine_reversible", CohortPhase.IMPLEMENTATION)  # type: ignore[arg-type]
        self.assertEqual(CheckpointDisposition.BLOCKED, decision.disposition)
        self.assertEqual(EffectClass.MISSING_AUTHORITY, decision.effect)


if __name__ == "__main__":
    unittest.main()
