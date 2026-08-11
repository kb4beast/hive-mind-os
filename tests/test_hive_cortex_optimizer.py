"""Focused acceptance tests for the non-promoting Optimizer role."""

from __future__ import annotations

import unittest
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import cast

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.optimizer import (
    ChallengerProposal,
    Optimizer,
    OptimizerError,
    OutcomeAttribution,
    PromotionRecommendation,
    ScopedLesson,
)


class _StringImpersonator(str):
    def strip(self, chars: str | None = None) -> str:
        return self

    def __eq__(self, other: object) -> bool:
        return False

    def __ne__(self, other: object) -> bool:
        return False

    __hash__ = str.__hash__


class _TupleImpersonator(tuple):  # type: ignore[type-arg]
    pass


class _FloatImpersonator(float):
    pass


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


def _attribution_material(value: OutcomeAttribution) -> dict[str, object]:
    return {
        "evidence_refs": value.evidence_refs,
        "context_ref": value.context_ref,
        "outcome_ref": value.outcome_ref,
        "error_class": value.error_class,
        "applicability": value.applicability,
        "confidence": value.confidence,
        "expires_at": value.expires_at,
        "provenance_ref": value.provenance_ref,
    }


def _replace_attribution(
    value: OutcomeAttribution, **updates: object
) -> OutcomeAttribution:
    bindings = _attribution_material(value)
    bindings.update(updates)
    return OutcomeAttribution(
        evidence_refs=cast(tuple[str, ...], bindings["evidence_refs"]),
        context_ref=cast(str, bindings["context_ref"]),
        outcome_ref=cast(str, bindings["outcome_ref"]),
        error_class=cast(str, bindings["error_class"]),
        applicability=cast(tuple[str, ...], bindings["applicability"]),
        confidence=cast(float, bindings["confidence"]),
        expires_at=cast(str, bindings["expires_at"]),
        provenance_ref=cast(str, bindings["provenance_ref"]),
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
            _replace_attribution(
                _attribution(),
                expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            )

    def test_optimizer_lesson_tests_reject_mutable_sequence_bindings(self) -> None:
        values = _attribution()
        with self.assertRaisesRegex(OptimizerError, "immutable tuples"):
            _replace_attribution(values, evidence_refs=["evidence:mutable"])
        with self.assertRaisesRegex(OptimizerError, "immutable tuples"):
            _replace_attribution(values, applicability=["scope:mutable"])

    def test_optimizer_lesson_tests_reject_scalar_and_container_subclasses(self) -> None:
        values = _attribution()
        with self.assertRaisesRegex(OptimizerError, "immutable tuples"):
            _replace_attribution(
                values,
                evidence_refs=_TupleImpersonator(("evidence:subclass",)),
            )
        with self.assertRaisesRegex(OptimizerError, "exact trimmed string"):
            _replace_attribution(
                values, evidence_refs=(_StringImpersonator("evidence:1"),)
            )
        with self.assertRaisesRegex(OptimizerError, "exact trimmed string"):
            _replace_attribution(
                values, context_ref=_StringImpersonator("context:1")
            )
        with self.assertRaisesRegex(OptimizerError, "confidence"):
            _replace_attribution(values, confidence=_FloatImpersonator(0.8))

    def test_optimizer_lesson_tests_do_not_retain_original_mutable_containers(self) -> None:
        evidence = ["evidence:run-1", "evidence:run-2"]
        applicability = ["python", "unit-tests"]
        attribution = _replace_attribution(
            _attribution(),
            evidence_refs=tuple(evidence),
            applicability=tuple(applicability),
        )
        lesson = Optimizer().attribute_outcome(attribution)

        evidence.append("evidence:mutated")
        applicability.append("scope:mutated")

        self.assertEqual(
            lesson.lesson_digest,
            canonical_digest(_attribution_material(lesson.attribution)),
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

    def test_optimizer_lesson_tests_revalidate_mutated_attribution_at_use(self) -> None:
        attribution = _attribution()
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(
                attribution, "evidence_refs", ("evidence:replacement",)
            )

        bypassed = tuple.__new__(
            OutcomeAttribution,
            (
                (),
                attribution.context_ref,
                attribution.outcome_ref,
                attribution.error_class,
                attribution.applicability,
                attribution.confidence,
                attribution.expires_at,
                attribution.provenance_ref,
            ),
        )
        with self.assertRaisesRegex(OptimizerError, "retained evidence"):
            Optimizer().attribute_outcome(bypassed)


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
        lesson = Optimizer().attribute_outcome(_attribution())
        bindings = {
            "challenger_id": "candidate:v2",
            "parent_champion_id": "champion:v1",
            "change_ref": "prompt:sha256:change",
            "author_id": "optimizer:author",
            "lesson_digest": lesson.lesson_digest,
        }
        with self.assertRaisesRegex(OptimizerError, "exact trimmed string"):
            ChallengerProposal(
                challenger_id="candidate:v2",
                parent_champion_id="champion:v1",
                change_ref="prompt:sha256:change",
                author_id=" optimizer:author",
                lesson=lesson,
                proposal_digest=canonical_digest(
                    {**bindings, "author_id": " optimizer:author"}
                ),
            )
        with self.assertRaisesRegex(OptimizerError, "does not match its bindings"):
            ChallengerProposal(
                challenger_id="candidate:v2",
                parent_champion_id="champion:v1",
                change_ref="prompt:sha256:change",
                author_id="optimizer:author",
                lesson=lesson,
                proposal_digest="sha256:forged",
            )
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(lesson, "lesson_digest", "sha256:unattested")
        unattested_lesson = tuple.__new__(
            ScopedLesson, (lesson.attribution, "sha256:unattested")
        )
        with self.assertRaisesRegex(OptimizerError, "does not match its attribution"):
            ChallengerProposal(
                challenger_id="candidate:v2",
                parent_champion_id="champion:v1",
                change_ref="prompt:sha256:change",
                author_id="optimizer:author",
                lesson=unattested_lesson,
                proposal_digest=canonical_digest(
                    {**bindings, "lesson_digest": "sha256:unattested"}
                ),
            )

    def test_challenger_proposal_tests_reject_lesson_type_impersonation(self) -> None:
        @dataclass(frozen=True)
        class FakeLesson:
            attribution: OutcomeAttribution
            lesson_digest: str

        attribution = _attribution()
        with self.assertRaisesRegex(OptimizerError, "scoped lesson type is invalid"):
            Optimizer().propose_challenger(
                FakeLesson(
                    attribution, canonical_digest(_attribution_material(attribution))
                ),  # type: ignore[arg-type]
                challenger_id="candidate:v2",
                champion_id="champion:v1",
                change_ref="prompt:sha256:change",
                author_id="optimizer:author",
            )

    def test_challenger_proposal_tests_reject_string_subclass_bindings(self) -> None:
        with self.assertRaisesRegex(OptimizerError, "exact trimmed string"):
            Optimizer().propose_challenger(
                Optimizer().attribute_outcome(_attribution()),
                challenger_id="candidate:v2",
                champion_id="champion:v1",
                change_ref="prompt:sha256:change",
                author_id=_StringImpersonator("optimizer:author"),
            )

    def test_challenger_proposal_tests_reject_mutated_and_spaced_bindings(self) -> None:
        optimizer = Optimizer()
        lesson = optimizer.attribute_outcome(_attribution())
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(
                lesson.attribution,
                "evidence_refs",
                ("evidence:replacement",),
            )
        replacement_attribution = _replace_attribution(
            lesson.attribution, evidence_refs=("evidence:replacement",)
        )
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(lesson, "attribution", replacement_attribution)
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(
                lesson,
                "lesson_digest",
                canonical_digest(_attribution_material(replacement_attribution)),
            )
        invalid_attribution = tuple.__new__(
            OutcomeAttribution,
            (
                (),
                lesson.attribution.context_ref,
                lesson.attribution.outcome_ref,
                lesson.attribution.error_class,
                lesson.attribution.applicability,
                lesson.attribution.confidence,
                lesson.attribution.expires_at,
                lesson.attribution.provenance_ref,
            ),
        )
        bypassed_lesson = tuple.__new__(
            ScopedLesson,
            (
                invalid_attribution,
                canonical_digest(_attribution_material(invalid_attribution)),
            ),
        )
        with self.assertRaisesRegex(OptimizerError, "retained evidence"):
            optimizer.propose_challenger(
                bypassed_lesson,
                challenger_id="candidate:v2",
                champion_id="champion:v1",
                change_ref="prompt:sha256:change",
                author_id="optimizer:author",
            )

        with self.assertRaisesRegex(OptimizerError, "exact trimmed string"):
            optimizer.propose_challenger(
                optimizer.attribute_outcome(_attribution()),
                challenger_id="champion:v1 ",
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
        with self.assertRaisesRegex(OptimizerError, "exact trimmed string"):
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

    def test_self_promotion_denial_tests_reject_string_subclass_impersonation(self) -> None:
        optimizer = Optimizer()
        proposal = optimizer.propose_challenger(
            optimizer.attribute_outcome(_attribution()),
            challenger_id="candidate:v2",
            champion_id="champion:v1",
            change_ref="prompt:sha256:change",
            author_id="optimizer:author",
        )
        with self.assertRaisesRegex(OptimizerError, "exact trimmed string"):
            optimizer.recommend_independent_review(
                proposal,
                evaluator_id=_StringImpersonator("optimizer:author"),
                evidence_complete=True,
            )

    def test_self_promotion_denial_tests_revalidate_mutated_proposal(self) -> None:
        optimizer = Optimizer()
        proposal = optimizer.propose_challenger(
            optimizer.attribute_outcome(_attribution()),
            challenger_id="candidate:v2",
            champion_id="champion:v1",
            change_ref="prompt:sha256:change",
            author_id="optimizer:author",
        )
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(proposal, "author_id", "curator:reviewer")
        recomputed_bindings = {
            "challenger_id": proposal.challenger_id,
            "parent_champion_id": proposal.parent_champion_id,
            "change_ref": proposal.change_ref,
            "author_id": "curator:reviewer",
            "lesson_digest": proposal.lesson_digest,
        }
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(
                proposal,
                "proposal_digest",
                canonical_digest(recomputed_bindings),
            )
        bypassed_proposal = tuple.__new__(
            ChallengerProposal,
            (
                proposal.challenger_id,
                proposal.parent_champion_id,
                proposal.change_ref,
                proposal.author_id,
                proposal.lesson,
                "sha256:forged",
            ),
        )
        with self.assertRaisesRegex(OptimizerError, "does not match its bindings"):
            optimizer.recommend_independent_review(
                bypassed_proposal,
                evaluator_id="optimizer:author",
                evidence_complete=True,
            )

        proposal = optimizer.propose_challenger(
            optimizer.attribute_outcome(_attribution()),
            challenger_id="candidate:v2",
            champion_id="champion:v1",
            change_ref="prompt:sha256:change",
            author_id="optimizer:author",
        )
        with self.assertRaises((AttributeError, TypeError)):
            object.__setattr__(proposal, "proposal_digest", "sha256:forged")
        bypassed_proposal = tuple.__new__(
            ChallengerProposal,
            (
                proposal.challenger_id,
                proposal.parent_champion_id,
                proposal.change_ref,
                proposal.author_id,
                proposal.lesson,
                "sha256:forged",
            ),
        )
        with self.assertRaisesRegex(OptimizerError, "does not match its bindings"):
            optimizer.recommend_independent_review(
                bypassed_proposal,
                evaluator_id="curator:reviewer",
                evidence_complete=True,
            )


if __name__ == "__main__":
    unittest.main()
