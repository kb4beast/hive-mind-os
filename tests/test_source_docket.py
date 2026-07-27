import unittest

from hive_mind_os.courtroom import Disposition
from hive_mind_os.source_docket import load_default_source_docket


class SourceDocketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.docket = load_default_source_docket()

    def test_every_source_has_claims_and_every_claim_has_a_verdict(self):
        audit = self.docket.audit()
        self.assertTrue(audit.inventory_complete)
        self.assertEqual(self.docket.source_count, 23)
        self.assertEqual(self.docket.claim_count, 84)
        self.assertEqual(len(self.docket.decisions), self.docket.claim_count)

    def test_unverified_videos_remain_explicit_blocking_evidence_obligations(self):
        audit = self.docket.audit()
        blockers = {issue.source_id for issue in audit.issues if issue.source_id}
        expected_video_blockers = {
            "SRC-005",
            "SRC-006",
            "SRC-016",
            "SRC-017",
            "SRC-018",
            "SRC-019",
            "SRC-020",
        }
        self.assertTrue(expected_video_blockers.issubset(blockers))
        self.assertFalse(audit.release_ready)
        self.assertTrue(expected_video_blockers.issubset({
            source_id
            for issue in audit.issues
            for source_id in (issue.source_id or "").split(",")
        }))

    def test_every_incomplete_source_machine_blocks_dependent_claims(self):
        audit = self.docket.audit()
        incomplete = {
            source.id
            for source in self.docket.sources
            if not source.provenance_complete
            or (
                source.requires_complete_ingestion
                and source.status.value != "verified"
            )
        }
        blocked = set(audit.machine_blocked_claim_ids)
        for claim in self.docket.claims:
            if set(claim.source_ids) & incomplete:
                self.assertIn(claim.id, blocked)

    def test_sibling_pack_is_separate_and_overlap_is_deferred(self):
        sources = {source.id: source for source in self.docket.sources}
        self.assertIn("SRC-023", sources)
        self.assertEqual(
            sources["SRC-023"].snapshot_ref,
            "evidence/sources/SRC-023-classic-gpt-pack/manifest.json",
        )
        decisions = {decision.claim_id: decision for decision in self.docket.decisions}
        for claim_id in ("CLM-081", "CLM-082", "CLM-083", "CLM-084"):
            self.assertEqual(decisions[claim_id].disposition, Disposition.DEFER)

    def test_capability_maturity_never_exceeds_structural_prototype(self):
        maturity = {claim.capability_maturity.value for claim in self.docket.claims}
        self.assertLessEqual(
            maturity,
            {"specified", "structurally_prototyped"},
        )

    def test_unknown_video_content_is_not_invented(self):
        for claim_id in ("CLM-023", "CLM-060"):
            decision = next(
                item for item in self.docket.decisions if item.claim_id == claim_id
            )
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

    def test_new_video_and_classic_gpt_claims_are_atomic_and_source_bound(self):
        claims = {claim.id: claim for claim in self.docket.claims}
        expected = {
            "CLM-058": "SRC-016",
            "CLM-059": "SRC-016",
            "CLM-060": "SRC-017",
            "CLM-061": "SRC-018",
            "CLM-062": "SRC-018",
            "CLM-063": "SRC-018",
            "CLM-064": "SRC-018",
            "CLM-065": "SRC-019",
            "CLM-066": "SRC-019",
            "CLM-067": "SRC-020",
            "CLM-068": "SRC-020",
            "CLM-069": "SRC-020",
            "CLM-070": "SRC-020",
            "CLM-071": "SRC-020",
            "CLM-072": "SRC-020",
            "CLM-073": "SRC-020",
            "CLM-074": "SRC-022",
            "CLM-075": "SRC-022",
            "CLM-076": "SRC-022",
            "CLM-077": "SRC-022",
            "CLM-078": "SRC-022",
            "CLM-079": "SRC-022",
            "CLM-080": "SRC-022",
        }
        for claim_id, source_id in expected.items():
            self.assertIn(claim_id, claims)
            self.assertIn(source_id, claims[claim_id].source_ids)

    def test_recursive_improvement_claims_have_code_and_test_receipts(self):
        claims = {claim.id: claim for claim in self.docket.claims}
        for claim_id in ("CLM-067", "CLM-068", "CLM-069", "CLM-070", "CLM-071", "CLM-072"):
            self.assertTrue(claims[claim_id].code_refs, claim_id)
            self.assertTrue(claims[claim_id].test_refs, claim_id)

    def test_classic_gpt_claims_have_code_and_test_receipts(self):
        claims = {claim.id: claim for claim in self.docket.claims}
        for claim_id in ("CLM-074", "CLM-075", "CLM-076", "CLM-077", "CLM-078", "CLM-079", "CLM-080"):
            self.assertTrue(claims[claim_id].code_refs, claim_id)
            self.assertTrue(claims[claim_id].test_refs, claim_id)


if __name__ == "__main__":
    unittest.main()
