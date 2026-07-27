import asyncio
import unittest
from dataclasses import replace

from hive_mind_os.autonomy import (
    AgentVariant,
    AutonomyBudget,
    AutonomousMissionLoop,
    EpisodeOutcome,
    EvolutionArena,
    MissionCharter,
)
from hive_mind_os.learning import LearningPromotionGate
from hive_mind_os.models import Role


class AutonomyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.charter = MissionCharter("Improve a repository", ("owner/repo",))
        self.champion = AgentVariant(Role.BUILDER, "stable")
        self.challenger = AgentVariant(
            Role.BUILDER,
            "experimental",
            generation=1,
            parent_id=self.champion.id,
        )

    def outcome(
        self,
        variant: AgentVariant,
        task: str,
        *,
        success: bool = True,
        quality: float = 0.9,
        trust: float = 0.9,
        violations: tuple[str, ...] = (),
        attempted: tuple[str, ...] = (),
        lessons: tuple[str, ...] = (),
    ) -> EpisodeOutcome:
        return EpisodeOutcome(
            variant_id=variant.id,
            task_id=task,
            success=success,
            customer_value=0.9,
            quality=quality,
            trust=trust,
            cooperation=0.8,
            cost_efficiency=0.8,
            evidence_count=3,
            tool_calls=1,
            compute_units=1.0,
            policy_violations=violations,
            attempted_capabilities=attempted,
            charter_fingerprint=self.charter.fingerprint,
            lessons=lessons,
        )

    def test_high_value_unsafe_variant_is_quarantined(self) -> None:
        arena = EvolutionArena(self.charter)
        arena.register(self.champion)
        unsafe = self.outcome(
            self.champion,
            "task",
            attempted=("self_replication",),
        )
        score = arena.record(unsafe)
        self.assertFalse(score.eligible)
        self.assertTrue(arena.state(self.champion.id).quarantined)

    def test_charter_mutation_is_detected(self) -> None:
        arena = EvolutionArena(self.charter)
        arena.register(self.champion)
        outcome = replace(
            self.outcome(self.champion, "task"),
            charter_fingerprint="changed",
        )
        score = arena.record(outcome)
        self.assertFalse(score.eligible)
        self.assertIn("mission charter changed", score.reasons)

    def test_challenger_requires_evidence_and_better_fitness(self) -> None:
        gate = LearningPromotionGate(
            minimum_runs=4,
            minimum_success_rate=0.75,
            maximum_regression_rate=0.25,
        )
        arena = EvolutionArena(self.charter, promotion_gate=gate)
        arena.register(self.champion)
        arena.register(self.challenger)
        for index in range(4):
            arena.record(
                self.outcome(
                    self.champion,
                    f"c{index}",
                    success=index != 0,
                    quality=0.7,
                    trust=0.7,
                )
            )
            arena.record(
                self.outcome(
                    self.challenger,
                    f"n{index}",
                    quality=0.95,
                    trust=0.95,
                )
            )
        decision = arena.recommend_promotion(self.champion.id)
        self.assertEqual(decision.candidate_id, self.challenger.id)
        self.assertTrue(decision.promotion.promote)

    def test_autonomous_loop_stops_at_budget(self) -> None:
        arena = EvolutionArena(
            self.charter,
            promotion_gate=LearningPromotionGate(minimum_runs=1),
        )
        arena.register(self.champion)
        budget = AutonomyBudget(
            max_episodes=2,
            max_tool_calls=2,
            max_compute_units=2,
        )
        loop = AutonomousMissionLoop(arena, budget, self.champion.id)

        async def execute(variant, task_id, charter, allowance):
            return self.outcome(variant, task_id)

        report = asyncio.run(loop.run(["a", "b", "c"], execute))
        self.assertEqual(report.completed_tasks, ("a", "b"))
        self.assertEqual(report.stopped_reason, "resource budget exhausted")

    def test_episode_cannot_exceed_issued_allowance(self) -> None:
        arena = EvolutionArena(self.charter)
        arena.register(self.champion)
        budget = AutonomyBudget(
            max_episodes=3,
            max_tool_calls=3,
            max_compute_units=3,
            max_tool_calls_per_episode=1,
            max_compute_units_per_episode=1,
        )
        loop = AutonomousMissionLoop(arena, budget, self.champion.id)

        async def execute(variant, task_id, charter, allowance):
            return replace(
                self.outcome(variant, task_id),
                tool_calls=allowance.tool_calls + 1,
            )

        report = asyncio.run(loop.run(["a"], execute))
        self.assertEqual(report.completed_tasks, ())
        self.assertEqual(report.stopped_reason, "resource budget exhausted")

    def test_teaching_packet_requires_repeated_support(self) -> None:
        arena = EvolutionArena(self.charter)
        arena.register(self.champion)
        arena.record(
            self.outcome(
                self.champion,
                "a",
                lessons=("run focused tests first", "one-off guess"),
            )
        )
        arena.record(
            self.outcome(
                self.champion,
                "b",
                lessons=("run focused tests first",),
            )
        )
        packet = arena.build_teaching_packet(minimum_support=2)
        self.assertEqual(packet.lessons, ("run focused tests first",))


if __name__ == "__main__":
    unittest.main()
