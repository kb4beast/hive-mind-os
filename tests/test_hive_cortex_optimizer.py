"""Focused acceptance tests for the non-promoting Optimizer role."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from hive_mind_os.brain_kernel.optimizer import (
    Optimizer,
    OptimizerError,
    OutcomeAttribution,
    PromotionRecommendation,
)


def _attribution() -> OutcomeAttribution:
    expiry = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    return OutcomeAttribution(
        evidence_refs=("evidence:run-1", "evidence:run-2"),
        context_ref="context:fixture",
        outcome_ref="outcome:regression-fixed",
        error_class="incorrect-assumption",
        applicability=("python", "unit-tests"),
        confidence=0.8,
        expires_at=expiry,
        provenance_ref="ledger:event-42",
    )


class OptimizerLessonTests(unittest.TestCase):
    def test_optimizer_lesson_tests_bind_all_required_attribution_fields(self) -> None:
        lesson = Optimizer().attribute_outcome(_attribution())

        self.assertTrue(lesson.lesson_digest.startswith("sha256:"))
        self.assertEqual(lesson.attribution.outcome_ref, "outcome:regression-fixed")

    def test_optimizer_lesson_tests_reject_expired_or_missing_evidence(self) -> None:
        with self.assertRaisesRegex(OptimizerError, "retained evidence"):
            OutcomeAttribution(
                (), "context:x", "outcome:x", "error", ("scope",), 0.5,
                (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "ledger:x",
            )
        with self.assertRaisesRegex(OptimizerError, "expiry"):
            replace(
                _attribution(),
                expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            )


class ChallengerProposalTests(unittest.TestCase):
    def test_challenger_proposal_tests_do_not_mutate_champion(self) -> None:
        optimizer = Optimizer()
        lesson = optimizer.attribute_outcome(_attribution())
        proposal = optimizer.propose_challenger(
            lesson,
            challenger_id="candidate:v2",
            champion_id="champion:v1",
            change_ref="prompt:sha256:change",
            author_id="optimizer:author",
        )

        self.assertEqual(proposal.parent_champion_id, "champion:v1")
        self.assertNotEqual(proposal.challenger_id, proposal.parent_champion_id)
        self.assertTrue(proposal.proposal_digest.startswith("sha256:"))


class SelfPromotionDenialTests(unittest.TestCase):
    def test_self_promotion_denial_tests_reject_candidate_author_as_evaluator(self) -> None:
        optimizer = Optimizer()
        proposal = optimizer.propose_challenger(
            optimizer.attribute_outcome(_attribution()),
            challenger_id="candidate:v2",
            champion_id="champion:v1",
            change_ref="prompt:sha256:change",
            author_id="optimizer:author",
        )

        with self.assertRaisesRegex(OptimizerError, "cannot evaluate or promote"):
            optimizer.recommend_independent_review(
                proposal, evaluator_id="optimizer:author", evidence_complete=True
            )
        recommendation = optimizer.recommend_independent_review(
            proposal, evaluator_id="curator:reviewer", evidence_complete=True
        )
        self.assertEqual(
            recommendation.recommendation,
            PromotionRecommendation.REQUEST_INDEPENDENT_REVIEW,
        )


if __name__ == "__main__":
    unittest.main()
