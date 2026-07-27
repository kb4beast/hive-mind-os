import unittest

from hive_mind_os.courtroom import Disposition
from hive_mind_os.source_docket import load_default_source_docket


class SourceDocketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.docket = load_default_source_docket()

    def test_every_source_has_claims_and_every_claim_has_a_verdict(self):
        audit = self.docket.audit()
        self.assertTrue(audit.inventory_complete)
        self.assertEqual(self.docket.source_count, 15)
        self.assertEqual(self.docket.claim_count, 57)
        self.assertEqual(len(self.docket.decisions), self.docket.claim_count)

    def test_unverified_videos_remain_explicit_blocking_evidence_obligations(self):
        audit = self.docket.audit()
        blockers = {issue.source_id for issue in audit.issues if issue.source_id}
        self.assertIn("SRC-005", blockers)
        self.assertIn("SRC-006", blockers)
        self.assertFalse(audit.release_ready)

    def test_unknown_video_content_is_not_invented(self):
        decision = next(item for item in self.docket.decisions if item.claim_id == "CLM-023")
        self.assertEqual(decision.disposition, Disposition.DEFER)
        self.assertIn("transcript", decision.rationale.lower())

    def test_all_adopted_or_adapted_claims_map_to_architecture_and_tests(self):
        decisions = {item.claim_id: item for item in self.docket.decisions}
        for claim in self.docket.claims:
            decision = decisions[claim.id]
            if decision.disposition in {Disposition.ADOPT, Disposition.ADAPT}:
                self.assertTrue(claim.architecture_refs, claim.id)
                self.assertTrue(claim.acceptance_tests, claim.id)

    def test_superiority_case_has_multiple_comparators_and_benchmark_manifest(self):
        claim = next(item for item in self.docket.claims if item.id == "CLM-005")
        self.assertGreaterEqual(len(set(claim.comparator_source_ids)), 2)
        self.assertTrue(claim.benchmark_refs)


if __name__ == "__main__":
    unittest.main()
