import unittest

from hive_mind_os.lesson_drafts import DraftError, ProcessingState, create_draft


class LessonDraftTests(unittest.TestCase):
    def draft(self):
        return create_draft(
            draft_id="draft-1",
            processing_state=ProcessingState.CAPTURED_PRIVATE,
            origin_subject_token="subject-token",
            origin_mission_token="mission-token",
            statement="Prefer an idempotent intent before a remote effect.",
            applicability=("remote-delivery",),
            outcome_class="positive",
            evidence_tokens=("evidence:private:1",),
            private_custody_token="custody:private:1",
            confidence_basis="one reproduced interruption",
            counterexamples=("non-idempotent provider",),
            disposition_refs=("court:1",),
            generator_id="optimizer",
            export_policy_digest="sha256:" + "a" * 64,
            withheld_reason_code=None,
        )

    def test_review_requires_order_receipt_and_independent_identity(self):
        draft = self.draft().transition(ProcessingState.CANDIDATE_PRIVATE)
        draft = draft.transition(
            ProcessingState.SANITIZED_DRAFT,
            sanitization_receipt_digest="sha256:" + "b" * 64,
        )
        with self.assertRaisesRegex(DraftError, "cannot review"):
            draft.transition(ProcessingState.REVIEWED_DRAFT, reviewer_id="optimizer")
        reviewed = draft.transition(
            ProcessingState.REVIEWED_DRAFT, reviewer_id="curator"
        )
        self.assertEqual(reviewed.document_status, "DRAFT")

    def test_state_skips_and_post_quarantine_revival_are_denied(self):
        with self.assertRaises(DraftError):
            self.draft().transition(
                ProcessingState.SANITIZED_DRAFT,
                sanitization_receipt_digest="sha256:" + "b" * 64,
            )
        quarantined = self.draft().transition(ProcessingState.QUARANTINED_EXPORT)
        with self.assertRaises(DraftError):
            quarantined.transition(ProcessingState.CANDIDATE_PRIVATE)


if __name__ == "__main__":
    unittest.main()
