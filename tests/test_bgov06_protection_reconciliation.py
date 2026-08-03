from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from hive_mind_os.github_adapter import GitHubClient
from scripts.capture_bgov06_protection import _canonical_bytes, _digest_bytes

ROOT = Path(__file__).resolve().parents[1]
RECEIPT_ROOT = ROOT / "evidence" / "live" / "B-GOV-06"


class Bgov06ProtectionReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        paths = sorted((RECEIPT_ROOT / "reconciliation").glob("*.json"))
        self.assertEqual(len(paths), 1)
        self.receipt_path = paths[0]
        self.receipt = json.loads(paths[0].read_text(encoding="utf-8"))

    def test_receipt_is_content_addressed_and_digest_bound(self) -> None:
        encoded = self.receipt_path.read_bytes()
        self.assertEqual(self.receipt_path.stem, hashlib.sha256(encoded).hexdigest())
        body = {
            key: value for key, value in self.receipt.items() if key != "receipt_digest"
        }
        self.assertEqual(
            self.receipt["receipt_digest"], _digest_bytes(_canonical_bytes(body))
        )

    def test_adapter_report_is_present_and_digest_bound(self) -> None:
        adapter = self.receipt["adapter"]
        report_path = ROOT / adapter["report_path"]
        self.assertTrue(report_path.is_file())
        self.assertEqual(
            adapter["report_digest"], _digest_bytes(report_path.read_bytes())
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["matches"])
        self.assertEqual(report["mismatches"], [])
        self.assertTrue(report["observed"]["enforce_admins"])

    def test_two_methods_agree_on_all_declared_rules(self) -> None:
        desired = json.loads(
            (ROOT / ".github/governance/required-repository-rules.json").read_text(
                encoding="utf-8"
            )
        )["rules"]
        self.assertEqual(set(self.receipt["agreed_rule_fields"]), set(desired))
        self.assertEqual(
            GitHubClient._compare(
                desired, self.receipt["adapter"]["observed"], "adapter"
            ),
            [],
        )
        self.assertEqual(
            GitHubClient._compare(
                desired,
                self.receipt["curator_reproduction"]["observed"],
                "curator",
            ),
            [],
        )

    def test_curator_raw_response_is_preserved_and_digest_bound(self) -> None:
        curator = self.receipt["curator_reproduction"]
        raw_path = ROOT / curator["raw_response_path"]
        self.assertTrue(raw_path.is_file())
        self.assertEqual(
            curator["raw_response_digest"], _digest_bytes(raw_path.read_bytes())
        )
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        self.assertTrue(raw["enforce_admins"]["enabled"])

    def test_blocker_is_narrowed_but_remains_open(self) -> None:
        blocker_line = next(
            line
            for line in (ROOT / "docs/plan/BLOCKERS.md")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.startswith("| B-GOV-06 |")
        )
        self.assertIn("administrator enforcement verified", blocker_line)
        self.assertIn("protected delivery pending", blocker_line)
        self.assertNotIn("| resolved |", blocker_line)

    def test_claims_stop_before_blocker_resolution_or_release(self) -> None:
        claims = self.receipt["claims"]
        self.assertTrue(claims["enforce_admins_verified"])
        self.assertTrue(claims["all_declared_rules_match"])
        for field in (
            "protected_main_delivery_observed",
            "b_gov_06_resolved",
            "review_independence_established",
            "release_ready",
        ):
            self.assertFalse(claims[field])
        self.assertFalse(
            self.receipt["curator_reproduction"]["authenticated_independence_claimed"]
        )

    def test_rules_metadata_points_to_current_receipt(self) -> None:
        rules = json.loads(
            (ROOT / ".github/governance/required-repository-rules.json").read_text(
                encoding="utf-8"
            )
        )
        report_path = ROOT / rules["verification_evidence"]
        self.assertEqual(report_path, ROOT / self.receipt["adapter"]["report_path"])
        self.assertEqual(
            rules["verification_evidence_digest"],
            _digest_bytes(report_path.read_bytes()),
        )
        self.assertEqual(
            rules["verification_status"],
            "admin_enforcement_verified_pending_protected_delivery",
        )

    def test_hostile_claim_reseal_changes_receipt_digest(self) -> None:
        hostile = deepcopy(self.receipt)
        hostile["claims"]["b_gov_06_resolved"] = True
        body = {key: value for key, value in hostile.items() if key != "receipt_digest"}
        self.assertNotEqual(
            hostile["receipt_digest"], _digest_bytes(_canonical_bytes(body))
        )


if __name__ == "__main__":
    unittest.main()
