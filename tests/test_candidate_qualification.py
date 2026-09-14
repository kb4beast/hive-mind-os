import unittest

from hive_mind_os.candidate_qualification import (
    CandidateQualifier,
    QualificationDisposition,
    QualificationRequest,
)


class CandidateQualificationTests(unittest.TestCase):
    def request(self, **changes):
        values = {
            "candidate_id": "candidate",
            "base_id": "base",
            "acceptance_manifest": ("unit", "security"),
            "changed_surfaces": ("src",),
            "risk_tier": "high",
            "sandbox_digest": "sha256:" + "1" * 64,
            "toolchain_digest": "sha256:" + "2" * 64,
            "environment_digest": "sha256:" + "3" * 64,
            "evaluator_id": "independent-curator",
        }
        values.update(changes)
        return QualificationRequest(**values)

    def test_exact_acceptance_receipts_are_candidate_bound(self):
        receipt = CandidateQualifier(lambda _: 1).qualify(self.request())
        self.assertEqual(receipt.disposition, QualificationDisposition.PASSED)
        self.assertEqual(len(receipt.checks), 2)
        self.assertEqual(
            CandidateQualifier.invalidated(
                receipt, self.request(), candidate_id="changed"
            ),
            ("candidate-changed",),
        )

    def test_missing_executor_zero_count_and_boolean_count_cannot_pass(self):
        self.assertEqual(
            CandidateQualifier().qualify(self.request()).disposition,
            QualificationDisposition.INCOMPLETE,
        )
        self.assertEqual(
            CandidateQualifier(lambda _: 0).qualify(self.request()).disposition,
            QualificationDisposition.INCOMPLETE,
        )
        self.assertEqual(
            CandidateQualifier(lambda _: True).qualify(self.request()).disposition,
            QualificationDisposition.QUARANTINED,
        )


if __name__ == "__main__":
    unittest.main()
