from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.phase5o_governance_records import (
    DOCUMENTS,
    OUTPUT_PATH,
    _digest_json,
    build_records,
)

ROOT = Path(__file__).resolve().parents[1]


class Phase5OGovernanceRecordTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = build_records(ROOT)

    def test_committed_record_matches_deterministic_rebuild(self) -> None:
        committed = json.loads((ROOT / OUTPUT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(committed, self.record)
        self.assertEqual(build_records(ROOT), self.record)

    def test_all_named_documents_are_present_and_sealed(self) -> None:
        self.assertEqual(set(self.record["documents"]), set(DOCUMENTS))
        for phase, paths in DOCUMENTS.items():
            self.assertEqual(set(self.record["documents"][phase]), set(paths))
            for path in paths:
                self.assertTrue((ROOT / path).is_file())
                self.assertTrue(self.record["documents"][phase][path].startswith("sha256:"))

    def test_procedural_reviews_do_not_claim_independence(self) -> None:
        for phase in "efg":
            review = self.record[f"phase5{phase}"]["procedural_role_review"]
            self.assertEqual(len(review["actors"]), 5)
            self.assertEqual(len({item["actor_id"] for item in review["actors"]}), 5)
            self.assertTrue(review["same_assistant_performed_procedural_passes"])
            self.assertFalse(review["authenticated_distinct_actors"])
            self.assertFalse(review["independence_claimed"])
            self.assertFalse(review["release_authorized"])

    def test_recovery_record_is_explicitly_not_executed(self) -> None:
        exercise = self.record["phase5f"]["recovery_exercise"]
        self.assertEqual(exercise["status"], "designed-not-executed")
        self.assertFalse(exercise["authority_supplied"])
        self.assertFalse(exercise["commands_executed"])
        self.assertFalse(exercise["recovery_claimed"])
        self.assertIn("B-OPS-08", exercise["known_blockers"])

    def test_optimizer_records_preserve_empty_and_blocked_states(self) -> None:
        optimizer = self.record["phase5g"]
        self.assertEqual(optimizer["protected_holdout_custody"]["status"], "sealed-not-accessed")
        self.assertEqual(optimizer["comparator_manifest"]["comparators"], [])
        self.assertEqual(optimizer["losing_result_archive"]["results"], [])
        self.assertEqual(
            optimizer["independent_evaluator_record"]["status"],
            "required-not-authenticated",
        )
        self.assertEqual(optimizer["promotion_court_disposition"]["disposition"], "defer")
        self.assertFalse(
            optimizer["promotion_court_disposition"]["promotion_authorized"]
        )

    def test_digest_and_all_material_claims_fail_closed(self) -> None:
        body = {key: value for key, value in self.record.items() if key != "record_digest"}
        self.assertEqual(self.record["record_digest"], _digest_json(body))
        self.assertTrue(all(value is False for value in self.record["claims"].values()))
        hostile = deepcopy(self.record)
        hostile["phase5g"]["promotion_court_disposition"]["promotion_authorized"] = True
        hostile_body = {
            key: value for key, value in hostile.items() if key != "record_digest"
        }
        self.assertNotEqual(hostile["record_digest"], _digest_json(hostile_body))


if __name__ == "__main__":
    unittest.main()
