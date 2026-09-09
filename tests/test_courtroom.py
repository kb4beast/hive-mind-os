import unittest
from dataclasses import replace

from hive_mind_os.courtroom import (
    BurdenOfProof,
    CaseParticipants,
    CourtCase,
    Courtroom,
    Disposition,
    EvidenceStance,
    EvidenceStrength,
    Exhibit,
    ExpertTestimony,
    IdeaClaim,
    ImplementationState,
    SourceRecord,
    SourceStatus,
)


class CourtroomTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SourceRecord(
            id="source",
            title="Pinned source",
            uri="https://example.test/source",
            kind="repository",
            status=SourceStatus.VERIFIED,
            version_ref="a" * 40,
            object_type="commit",
            license_spdx="MIT",
        )
        self.participants = CaseParticipants("advocate", "cross", ("judge-a", "judge-b"))

    def claim(self, burden=BurdenOfProof.DESIGN, **overrides):
        values = dict(
            id="claim",
            case_id="case",
            proposition="Use durable workflows",
            source_ids=("source",),
            category="runtime",
            burden=burden,
            architecture_refs=("docs/architecture.md",),
            acceptance_tests=("workflow resumes after interruption",),
            outcome_metrics=("recovery_rate",),
            code_refs=("src/runtime.py",),
            test_refs=("tests/test_runtime.py",),
            benchmark_refs=("benchmarks/result.json",),
            comparator_source_ids=("source", "other"),
            implementation_state=ImplementationState.VALIDATED,
        )
        values.update(overrides)
        return IdeaClaim(**values)

    def exhibits(self, claim_id="claim"):
        return (
            Exhibit(
                "support",
                claim_id,
                "source",
                EvidenceStance.SUPPORTS,
                EvidenceStrength.REPRODUCED,
                "README:10-20",
                "digest-support",
            ),
            Exhibit(
                "oppose",
                claim_id,
                "source",
                EvidenceStance.OPPOSES,
                EvidenceStrength.ASSERTION,
                "threat-model:1",
                "digest-oppose",
            ),
        )

    def expert_testimony(self, claim_id="claim"):
        return (
            ExpertTestimony(
                "expert-support",
                claim_id,
                "SRE",
                EvidenceStance.SUPPORTS,
                "Recovery is measurable.",
                "sre-agent",
                ("support",),
            ),
            ExpertTestimony(
                "expert-oppose",
                claim_id,
                "Security",
                EvidenceStance.OPPOSES,
                "Retries need idempotency.",
                "security-agent",
                ("oppose",),
            ),
        )

    def test_independent_participants_are_required(self):
        with self.assertRaises(ValueError):
            CaseParticipants("same", "cross", ("same",))

    def test_prohibited_finding_quarantines_even_high_value_idea(self):
        case = CourtCase(
            self.claim(),
            self.participants,
            self.exhibits(),
            self.expert_testimony(),
            prohibited_findings=("requires policy mutation",),
        )
        verdict = Courtroom((self.source,)).hear(case)
        self.assertEqual(verdict.disposition, Disposition.QUARANTINE)

    def test_pending_source_is_deferred_for_design(self):
        pending = SourceRecord(
            id="source",
            title="Untranscribed video",
            uri="https://example.test/video",
            kind="video",
            status=SourceStatus.PENDING_INGESTION,
            version_ref="video-id",
        )
        case = CourtCase(self.claim(), self.participants, self.exhibits(), self.expert_testimony())
        verdict = Courtroom((pending,)).hear(case)
        self.assertEqual(verdict.disposition, Disposition.DEFER)
        self.assertTrue(any("incomplete" in reason for reason in verdict.reasons))

    def test_no_adversarial_evidence_defers_design(self):
        support_only = (self.exhibits()[0],)
        support_testimony = (self.expert_testimony()[0],)
        case = CourtCase(self.claim(), self.participants, support_only, support_testimony)
        verdict = Courtroom((self.source,)).hear(case)
        self.assertEqual(verdict.disposition, Disposition.DEFER)
        self.assertIn("no adversarial cross-examination evidence", verdict.reasons)

    def test_unresolved_objection_produces_adapt_verdict(self):
        case = CourtCase(
            self.claim(),
            self.participants,
            self.exhibits(),
            self.expert_testimony(),
            unresolved_objections=("add idempotency keys",),
        )
        verdict = Courtroom((self.source,)).hear(case)
        self.assertEqual(verdict.disposition, Disposition.ADAPT)
        self.assertIn("add idempotency keys", verdict.obligations)

    def neutral_cross(self, **overrides):
        return replace(
            ExpertTestimony(
                "cross-result", "claim", "adversarial review",
                EvidenceStance.CONTEXT,
                "Examined duplicate retries and crash recovery; reproduction found no counterexample.",
                "cross", ("support",),
            ),
            **overrides,
        )

    def test_completed_cross_examination_need_not_invent_an_objection(self):
        case = CourtCase(
            self.claim(), self.participants, (self.exhibits()[0],),
            (self.expert_testimony()[0], self.neutral_cross()),
        )
        verdict = Courtroom((self.source,)).hear(case)
        self.assertEqual(Disposition.ADOPT, verdict.disposition)
        self.assertEqual(1.0, verdict.score)

    def test_neutral_cross_must_be_assigned_and_cite_independent_case_evidence(self):
        for testimony, exhibit in (
            (self.neutral_cross(actor_id="advocate"), self.exhibits()[0]),
            (self.neutral_cross(actor_id="judge-a"), self.exhibits()[0]),
            (self.neutral_cross(evidence_refs=("unknown",)), self.exhibits()[0]),
            (self.neutral_cross(), replace(self.exhibits()[0], independent=False)),
        ):
            with self.subTest(testimony=testimony, exhibit=exhibit):
                case = CourtCase(self.claim(), self.participants, (exhibit,), (testimony,))
                verdict = Courtroom((self.source,)).hear(case)
                self.assertEqual(Disposition.DEFER, verdict.disposition)
                self.assertIn("no adversarial cross-examination evidence", verdict.reasons)

    def test_neutral_review_adds_no_weight_and_retains_real_dissent(self):
        original = CourtCase(
            self.claim(), self.participants, self.exhibits(), self.expert_testimony(),
            unresolved_objections=("add idempotency keys",),
        )
        neutral = replace(original, testimony=(*original.testimony, self.neutral_cross()))
        before = Courtroom((self.source,)).hear(original)
        after = Courtroom((self.source,)).hear(neutral)
        self.assertEqual(before, after)

    def test_neutral_review_does_not_supply_missing_later_stage_evidence(self):
        for claim in (
            self.claim(BurdenOfProof.IMPLEMENT, acceptance_tests=()),
            self.claim(BurdenOfProof.PROMOTE, code_refs=()),
            self.claim(BurdenOfProof.SUPERIORITY, benchmark_refs=()),
        ):
            with self.subTest(burden=claim.burden):
                verdict = Courtroom((self.source,)).hear(CourtCase(
                    claim, self.participants, (self.exhibits()[0],), (self.neutral_cross(),),
                ))
                self.assertEqual(Disposition.DEFER, verdict.disposition)

    def test_superiority_requires_comparators_and_benchmarks(self):
        weak_claim = self.claim(
            burden=BurdenOfProof.SUPERIORITY,
            benchmark_refs=(),
            comparator_source_ids=("source",),
        )
        case = CourtCase(weak_claim, self.participants, self.exhibits(), self.expert_testimony())
        verdict = Courtroom((self.source,)).hear(case)
        self.assertEqual(verdict.disposition, Disposition.DEFER)
        self.assertTrue(any("superiority" in reason for reason in verdict.reasons))


if __name__ == "__main__":
    unittest.main()
