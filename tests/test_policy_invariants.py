from __future__ import annotations

import unittest

from hive_mind_os.autonomy import (
    AgentVariant,
    EpisodeOutcome,
    EvolutionArena,
    FitnessEvaluator,
    MissionCharter,
)
from hive_mind_os.models import AutonomyLevel, RiskTier, Role
from hive_mind_os.policy import (
    ACTION_LEVEL,
    EXTERNAL_GRANT_ACTIONS,
    PROHIBITED_ACTIONS,
    Action,
    PolicyEngine,
)


class PolicyInvariantTests(unittest.TestCase):
    def test_every_action_has_an_explicit_policy_mapping(self) -> None:
        self.assertEqual(set(ACTION_LEVEL), set(Action))
        self.assertLessEqual(PROHIBITED_ACTIONS, set(Action))
        self.assertLessEqual(EXTERNAL_GRANT_ACTIONS, set(Action))

    def test_non_delegable_actions_are_denied_for_every_actor_risk_and_authority(self) -> None:
        for autonomy in AutonomyLevel:
            engine = PolicyEngine(autonomy)
            for role in Role:
                for risk in RiskTier:
                    for action in PROHIBITED_ACTIONS:
                        with self.subTest(
                            autonomy=autonomy,
                            role=role,
                            risk=risk,
                            action=action,
                        ):
                            decision = engine.decide(role, action, risk)
                            self.assertFalse(decision.allowed)
                            self.assertIn("non-delegable", decision.reason)

    def test_external_grant_actions_default_to_denied_without_a_grant_model(self) -> None:
        for autonomy in AutonomyLevel:
            engine = PolicyEngine(autonomy)
            for role in Role:
                for risk in RiskTier:
                    for action in EXTERNAL_GRANT_ACTIONS:
                        with self.subTest(
                            autonomy=autonomy,
                            role=role,
                            risk=risk,
                            action=action,
                        ):
                            self.assertFalse(engine.decide(role, action, risk).allowed)

    def test_explorer_remains_nonmutating_at_every_authority_level(self) -> None:
        nonmutating_actions = {
            Action.READ_REPOSITORY,
            Action.SEARCH_WEB,
            Action.RUN_COMMANDS,
        }
        for autonomy in AutonomyLevel:
            engine = PolicyEngine(autonomy)
            for action in set(Action) - nonmutating_actions:
                with self.subTest(autonomy=autonomy, action=action):
                    self.assertFalse(
                        engine.decide(Role.EXPLORER, action, RiskTier.LOW).allowed
                    )
            command = engine.decide(
                Role.EXPLORER,
                Action.RUN_COMMANDS,
                RiskTier.LOW,
            )
            self.assertEqual(
                command.allowed,
                autonomy >= AutonomyLevel.SANDBOX,
            )

    def test_actions_are_denied_below_their_required_authority(self) -> None:
        for action, required in ACTION_LEVEL.items():
            if action in PROHIBITED_ACTIONS or action in EXTERNAL_GRANT_ACTIONS:
                continue
            for autonomy in AutonomyLevel:
                if int(autonomy) >= int(required):
                    continue
                with self.subTest(action=action, autonomy=autonomy):
                    decision = PolicyEngine(autonomy).decide(
                        Role.BUILDER,
                        action,
                        RiskTier.LOW,
                    )
                    self.assertFalse(decision.allowed)
                    self.assertIn("requires autonomy level", decision.reason)

    def test_known_low_risk_actions_are_not_accidentally_denied(self) -> None:
        allowed_cases = (
            (AutonomyLevel.OBSERVE, Action.READ_REPOSITORY),
            (AutonomyLevel.OBSERVE, Action.SEARCH_WEB),
            (AutonomyLevel.SANDBOX, Action.WRITE_WORKSPACE),
            (AutonomyLevel.SANDBOX, Action.RUN_COMMANDS),
            (AutonomyLevel.REPOSITORY, Action.CREATE_BRANCH),
            (AutonomyLevel.REPOSITORY, Action.OPEN_PULL_REQUEST),
        )
        for autonomy, action in allowed_cases:
            with self.subTest(autonomy=autonomy, action=action):
                decision = PolicyEngine(autonomy).decide(
                    Role.BUILDER,
                    action,
                    RiskTier.LOW,
                )
                self.assertTrue(decision.allowed, decision.reason)

    def test_malformed_runtime_inputs_fail_closed(self) -> None:
        engine = PolicyEngine(AutonomyLevel.GOVERNED_FULL)
        malformed = (
            ("explorer", Action.DEPLOY, RiskTier.HIGH),
            (Role.BUILDER, "deploy", RiskTier.HIGH),
            (Role.BUILDER, Action.DEPLOY, 4),
            (None, Action.WRITE_WORKSPACE, RiskTier.LOW),
        )
        for role, action, risk in malformed:
            with self.subTest(role=role, action=action, risk=risk):
                decision = engine.decide(role, action, risk)  # type: ignore[arg-type]
                self.assertFalse(decision.allowed)

        for autonomy in (99, "repository", float("nan")):
            with self.subTest(autonomy=autonomy):
                with self.assertRaises(ValueError):
                    PolicyEngine(autonomy)  # type: ignore[arg-type]

    def test_blank_or_mismatched_charter_binding_is_ineligible_and_quarantined(self) -> None:
        charter = MissionCharter("Improve safely", ("owner/repo",))
        variant = AgentVariant(Role.BUILDER, "candidate")
        evaluator = FitnessEvaluator()
        for fingerprint in ("", "wrong"):
            outcome = EpisodeOutcome(
                variant_id=variant.id,
                task_id=f"task-{fingerprint or 'blank'}",
                success=True,
                customer_value=1.0,
                quality=1.0,
                trust=1.0,
                cooperation=1.0,
                cost_efficiency=1.0,
                evidence_count=10,
                charter_fingerprint=fingerprint,
            )
            with self.subTest(fingerprint=fingerprint):
                score = evaluator.evaluate(outcome, charter)
                self.assertFalse(score.eligible)
                self.assertIn("mission charter changed", score.reasons)
                arena = EvolutionArena(charter)
                arena.register(variant)
                arena.record(outcome)
                self.assertTrue(arena.state(variant.id).quarantined)

    def test_every_charter_forbidden_capability_is_a_hard_disqualifier(self) -> None:
        charter = MissionCharter("Improve safely", ("owner/repo",))
        for capability in charter.forbidden_capabilities:
            variant = AgentVariant(Role.BUILDER, f"candidate-{capability}")
            outcome = EpisodeOutcome(
                variant_id=variant.id,
                task_id=f"task-{capability}",
                success=True,
                customer_value=1.0,
                quality=1.0,
                trust=1.0,
                cooperation=1.0,
                cost_efficiency=1.0,
                evidence_count=10,
                attempted_capabilities=(capability,),
                charter_fingerprint=charter.fingerprint,
            )
            with self.subTest(capability=capability):
                score = FitnessEvaluator().evaluate(outcome, charter)
                self.assertFalse(score.eligible)
                self.assertTrue(
                    any("forbidden capability attempted" in reason for reason in score.reasons)
                )
                arena = EvolutionArena(charter)
                arena.register(variant)
                arena.record(outcome)
                self.assertTrue(arena.state(variant.id).quarantined)


if __name__ == "__main__":
    unittest.main()
