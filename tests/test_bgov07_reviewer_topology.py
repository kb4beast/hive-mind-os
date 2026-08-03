from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.capture_bgov07_reviewer_topology import _canonical_bytes, _digest_bytes

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_ROOT = ROOT / "evidence/live/B-GOV-07"


class Bgov07ReviewerTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        paths = sorted((RECEIPT_ROOT / "reconciliation").glob("*.json"))
        self.assertEqual(len(paths), 1)
        self.path = paths[0]
        self.receipt = json.loads(self.path.read_text(encoding="utf-8"))

    def test_receipt_and_raw_response_are_content_addressed(self) -> None:
        self.assertEqual(
            self.path.stem, hashlib.sha256(self.path.read_bytes()).hexdigest()
        )
        body = {
            key: value for key, value in self.receipt.items() if key != "receipt_digest"
        }
        self.assertEqual(
            self.receipt["receipt_digest"], _digest_bytes(_canonical_bytes(body))
        )
        raw = ROOT / self.receipt["collaborator_response"]["path"]
        self.assertTrue(raw.is_file())
        self.assertEqual(
            self.receipt["collaborator_response"]["digest"],
            _digest_bytes(raw.read_bytes()),
        )

    def test_topology_is_narrowly_and_truthfully_recorded(self) -> None:
        self.assertEqual(
            self.receipt["write_capable_accounts"],
            ["VivaLaRoy", "beespinosa04", "kb4beast"],
        )
        self.assertEqual(
            self.receipt["non_author_write_capable_accounts"],
            ["VivaLaRoy", "beespinosa04"],
        )
        self.assertEqual(self.receipt["codeowners"]["owners"], ["@kb4beast"])
        self.assertEqual(self.receipt["codeowners"]["non_author_owners"], [])

    def test_claims_do_not_infer_consent_independence_or_approval(self) -> None:
        claims = self.receipt["claims"]
        self.assertTrue(claims["two_non_author_write_capable_accounts_observed"])
        for field in (
            "non_author_codeowner_coverage_observed",
            "reviewer_consent_observed",
            "human_independence_authenticated",
            "required_approvals_observed",
            "b_gov_07_resolved",
            "release_ready",
        ):
            self.assertFalse(claims[field])

    def test_codeowners_digest_binds_current_file(self) -> None:
        codeowners = ROOT / self.receipt["codeowners"]["path"]
        self.assertEqual(
            self.receipt["codeowners"]["digest"],
            _digest_bytes(codeowners.read_bytes()),
        )

    def test_blocker_remains_open_and_hostile_reseal_fails(self) -> None:
        blocker_line = next(
            line
            for line in (ROOT / "docs/plan/BLOCKERS.md")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.startswith("| B-GOV-07 |")
        )
        self.assertIn("reviewer topology refreshed", blocker_line)
        self.assertNotIn("| resolved |", blocker_line)
        hostile = deepcopy(self.receipt)
        hostile["claims"]["b_gov_07_resolved"] = True
        body = {key: value for key, value in hostile.items() if key != "receipt_digest"}
        self.assertNotEqual(
            hostile["receipt_digest"], _digest_bytes(_canonical_bytes(body))
        )


if __name__ == "__main__":
    unittest.main()
