import asyncio
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from hive_mind_os.learning import (
    CommitSnapshot,
    EvaluationSummary,
    LearningPromotionGate,
    PointInTimeReplay,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import AutonomyLevel, Objective, RiskTier, Role, WorkStatus
from hive_mind_os.policy import Action, PolicyEngine
from hive_mind_os.roles import DEFAULT_LIFECYCLE
from hive_mind_os.runtime import HiveKernel


class KernelTests(unittest.TestCase):
    def test_complete_lifecycle_produces_evidence(self) -> None:
        kernel = HiveKernel()
        report = asyncio.run(kernel.run_objective(Objective("Build a verified repository improvement")))
        self.assertEqual(report.status, WorkStatus.SUCCEEDED)
        self.assertEqual(tuple(result.role for result in report.results), DEFAULT_LIFECYCLE)
        self.assertGreaterEqual(report.evidence_count, len(DEFAULT_LIFECYCLE))

    def test_ledger_is_append_only(self) -> None:
        ledger = EvidenceLedger()
        sequence = ledger.append_event("run", "test", "curator", {"ok": True})
        with self.assertRaises(sqlite3.IntegrityError):
            ledger._connection.execute("UPDATE events SET actor='x' WHERE sequence=?", (sequence,))

    def test_policy_denies_merge_at_sandbox_level(self) -> None:
        decision = PolicyEngine(AutonomyLevel.SANDBOX).decide(
            Role.BUILDER, Action.MERGE_PULL_REQUEST, RiskTier.MODERATE
        )
        self.assertFalse(decision.allowed)

    def test_non_delegable_invariant_cannot_be_overridden_by_full_autonomy(self) -> None:
        decision = PolicyEngine(AutonomyLevel.GOVERNED_FULL).decide(
            Role.OPTIMIZER,
            Action.MUTATE_POLICY,
            RiskTier.LOW,
        )
        self.assertFalse(decision.allowed)
        self.assertIn("non-delegable", decision.reason)

    def test_point_in_time_replay_never_exposes_target_or_future(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        commits = [
            CommitSnapshot(str(index), start + timedelta(days=index), (f"{index}.py",))
            for index in range(4)
        ]
        frames = list(PointInTimeReplay(reversed(commits)).frames())
        for index, frame in enumerate(frames):
            self.assertEqual(len(frame.visible_history), index)
            self.assertNotIn(frame.target, frame.visible_history)

    def test_learning_candidate_must_beat_champion(self) -> None:
        gate = LearningPromotionGate(minimum_runs=10)
        champion = EvaluationSummary(runs=50, successes=40, regressions=1)
        weak_candidate = EvaluationSummary(runs=20, successes=16, regressions=0)
        strong_candidate = EvaluationSummary(runs=20, successes=18, regressions=0)
        self.assertFalse(gate.evaluate(weak_candidate, champion).promote)
        self.assertTrue(gate.evaluate(strong_candidate, champion).promote)


if __name__ == "__main__":
    unittest.main()
