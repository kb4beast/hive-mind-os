"""Focused acceptance tests for the non-promoting Optimizer role."""

from __future__ import annotations

import unittest
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.optimizer import (
    ChallengerProposal,
    Optimizer,
    OptimizerError,
    OutcomeAttribution,
    PromotionRecommendation,
    ScopedLesson,
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

    def test_optimizer_lesson_tests_reject_mutable_sequence_bindings(self) -> None:
        values = _attribution()
        with self.assertRaisesRegex(OptimizerError, "immutable tuples"):
            replace(values, evidence_refs=["evidence:mutable"])  # type: ignore[arg-type]
        with self.assertRaisesRegex(OptimizerError, "immutable tuples"):
            replace(values, applicability=["scope:mutable"])  # type: ignore[arg-type]

    def test_optimizer_lesson_tests_do_not_retain_original_mutable_containers(self) -> None:
        evidence = ["evidence:run-1", "evidence:run-2"]
        applicability = ["python", "unit-tests"]
        attribution = replace(
            _attribution(),
            evidence_refs=tuple(evidence),
            applicability=tuple(applicability),
        )
        lesson = Optimizer().attribute_outcome(attribution)

        evidence.append("evidence:mutated")
        applicability.append("scope:mutated")

        self.assertEqual(
            lesson.lesson_digest,
            canonical_digest(asdict(lesson.attribution)),
        )

    def test_optimizer_lesson_tests_reject_attribution_type_impersonation(self) -> None:
        @dataclass(frozen=True)
        class FakeAttribution:
            attacker_controlled: str

        fake = FakeAttribution("not retained evidence")
        with self.assertRaisesRegex(OptimizerError, "attribution type is invalid"):
            Optimizer().attribute_outcome(fake)  # type: ignore[arg-type]
        with self.assertRaisesRegex(OptimizerError, "attribution type is invalid"):
            ScopedLesson(fake, canonical_digest(asdict(fake)))  # type: ignore[arg-type]


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

    def test_challenger_proposal_tests_reject_forged_lesson_digest(self) -> None:
        with self.assertRaisesRegex(OptimizerError, "does not match its attribution"):
            ScopedLesson(_attribution(), "sha256:forged")

    def test_challenger_proposal_tests_reject_direct_construction_bypasses(self) -> None:
        values = {
            "challenger_id": "candidate:v2",
            "parent_champion_id": "champion:v1",
            "change_ref": "prompt:sha256:change",
            "author_id": "optimizer:author",
            "lesson_digest": "sha256:lesson",
        }
        with self.assertRaisesRegex(OptimizerError, "surrounding whitespace"):
            ChallengerProposal(
                **{**values, "author_id": " optimizer:author"},
                proposal_digest=canonical_digest(
                    {**values, "author_id": " optimizer:author"}
                ),
            )
        with self.assertRaisesRegex(OptimizerError, "does not match its bindings"):
            ChallengerProposal(**values, proposal_digest="sha256:forged")

    def test_challenger_proposal_tests_reject_lesson_type_impersonation(self) -> None:
        @dataclass(frozen=True)
        class FakeLesson:
            attribution: OutcomeAttribution
            lesson_digest: str

        attribution = _attribution()
        with self.assertRaisesRegex(OptimizerError, "scoped lesson type is invalid"):
            Optimizer().propose_challenger(
                FakeLesson(attribution, canonical_digest(asdict(attribution))),  # type: ignore[arg-type]
                challenger_id="candidate:v2",
                champion_id="champion:v1",
                change_ref="prompt:sha256:change",
                author_id="optimizer:author",
            )


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
        with self.assertRaisesRegex(OptimizerError, "surrounding whitespace"):
            optimizer.recommend_independent_review(
                proposal, evaluator_id=" optimizer:author", evidence_complete=True
            )
        with self.assertRaisesRegex(OptimizerError, "must be a boolean"):
            optimizer.recommend_independent_review(
                proposal, evaluator_id="curator:reviewer", evidence_complete=1  # type: ignore[arg-type]
            )
        recommendation = optimizer.recommend_independent_review(
            proposal, evaluator_id="curator:reviewer", evidence_complete=True
        )
        self.assertEqual(
            recommendation.recommendation,
            PromotionRecommendation.REQUEST_INDEPENDENT_REVIEW,
        )

    def test_self_promotion_denial_tests_reject_proposal_type_impersonation(self) -> None:
        @dataclass(frozen=True)
        class FakeProposal:
            proposal_digest: str
            author_id: str

        with self.assertRaisesRegex(OptimizerError, "proposal type is invalid"):
            Optimizer().recommend_independent_review(
                FakeProposal("sha256:forged", "attacker"),  # type: ignore[arg-type]
                evaluator_id="curator:reviewer",
                evidence_complete=True,
            )


if __name__ == "__main__":
    unittest.main()
