from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.phase5_debt_reconciliation import ALL_DEBT_IDS, _digest_json
from scripts.phase5n_debt_reconciliation import (
    EXTERNAL_INPUT_DEBT_IDS,
    NEXT_INTERNAL_DEBT_IDS,
    OUTPUT_PATH,
    PREDECESSOR_DIGEST,
    RESOLVED_DEBT_ID,
    SUBJECT_COMMIT,
    SUBJECT_RUNS,
    build_reconciliation,
)

ROOT = Path(__file__).resolve().parents[1]


class Phase5NDebtReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = build_reconciliation(ROOT)

    def test_committed_record_matches_rebuild(self) -> None:
        committed = json.loads((ROOT / OUTPUT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(committed, self.record)

    def test_one_narrow_resolution_leaves_seventeen_active(self) -> None:
        self.assertEqual(self.record["resolved_in_phase5n"], [RESOLVED_DEBT_ID])
        self.assertEqual(
            self.record["counts"],
            {
                "total": 35,
                "prior_resolved": 17,
                "resolved_in_phase5n": 1,
                "resolved": 18,
                "current_active": 17,
            },
        )
        self.assertNotIn(RESOLVED_DEBT_ID, self.record["current_active_debt_ids"])

    def test_resolution_has_exact_receipts(self) -> None:
        resolution = next(
            item for item in self.record["resolved"] if item["debt_id"] == RESOLVED_DEBT_ID
        )
        self.assertEqual(resolution["evidence"][0], f"commit:{SUBJECT_COMMIT}")
        self.assertEqual(
            resolution["evidence"][1:3], [f"run:{run_id}" for run_id in SUBJECT_RUNS]
        )
        self.assertTrue(
            all(item.startswith("artifact:") for item in resolution["evidence"][3:])
        )

    def test_remaining_and_external_debt_stays_active(self) -> None:
        active = set(self.record["current_active_debt_ids"])
        self.assertTrue(set(EXTERNAL_INPUT_DEBT_IDS).issubset(active))
        self.assertTrue(set(NEXT_INTERNAL_DEBT_IDS).issubset(active))
        self.assertEqual(
            {item["debt_id"] for item in self.record["resolved"]} | active,
            set(ALL_DEBT_IDS),
        )

    def test_digest_predecessor_and_claims_fail_closed(self) -> None:
        self.assertEqual(
            self.record["predecessor"]["reconciliation_digest"], PREDECESSOR_DIGEST
        )
        self.assertTrue(all(value is False for value in self.record["claims"].values()))
        body = {key: value for key, value in self.record.items() if key != "reconciliation_digest"}
        self.assertEqual(self.record["reconciliation_digest"], _digest_json(body))
        hostile = deepcopy(self.record)
        hostile["current_active_debt_ids"].pop()
        hostile_body = {
            key: value for key, value in hostile.items() if key != "reconciliation_digest"
        }
        self.assertNotEqual(hostile["reconciliation_digest"], _digest_json(hostile_body))


if __name__ == "__main__":
    unittest.main()
