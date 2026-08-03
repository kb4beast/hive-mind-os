from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.phase5_debt_reconciliation import ALL_DEBT_IDS, _digest_json
from scripts.phase5p_debt_reconciliation import (
    EXTERNAL_INPUT_DEBT_IDS,
    NEW_RESOLUTIONS,
    NEXT_INTERNAL_DEBT_IDS,
    OUTPUT_PATH,
    PREDECESSOR_DIGEST,
    SUBJECT_COMMIT,
    SUBJECT_RUNS,
    build_reconciliation,
)

ROOT = Path(__file__).resolve().parents[1]


class Phase5PDebtReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = build_reconciliation(ROOT)

    def test_committed_record_matches_rebuild(self) -> None:
        committed = json.loads((ROOT / OUTPUT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(committed, self.record)

    def test_final_three_internal_debts_close_and_eleven_remain(self) -> None:
        self.assertEqual(tuple(self.record["resolved_in_phase5p"]), NEW_RESOLUTIONS)
        self.assertEqual(
            self.record["counts"],
            {
                "total": 35,
                "prior_resolved": 21,
                "resolved_in_phase5p": 3,
                "resolved": 24,
                "current_active": 11,
            },
        )

    def test_exact_hosted_receipts_support_each_resolution(self) -> None:
        by_id = {item["debt_id"]: item for item in self.record["resolved"]}
        for debt_id in NEW_RESOLUTIONS:
            evidence = by_id[debt_id]["evidence"]
            self.assertEqual(evidence[0], f"commit:{SUBJECT_COMMIT}")
            self.assertEqual(
                evidence[1:3], [f"run:{run_id}" for run_id in SUBJECT_RUNS]
            )
            self.assertEqual(len(evidence), 5)

    def test_only_external_input_debts_remain(self) -> None:
        active = set(self.record["current_active_debt_ids"])
        self.assertEqual(active, set(EXTERNAL_INPUT_DEBT_IDS))
        self.assertEqual(
            tuple(self.record["next_internal_debt_ids"]), NEXT_INTERNAL_DEBT_IDS
        )
        self.assertEqual(
            {item["debt_id"] for item in self.record["resolved"]} | active,
            set(ALL_DEBT_IDS),
        )

    def test_predecessor_digest_and_all_claims_are_preserved(self) -> None:
        self.assertEqual(
            self.record["predecessor"]["reconciliation_digest"], PREDECESSOR_DIGEST
        )
        self.assertTrue(all(value is False for value in self.record["claims"].values()))
        body = {
            key: value
            for key, value in self.record.items()
            if key != "reconciliation_digest"
        }
        self.assertEqual(self.record["reconciliation_digest"], _digest_json(body))


if __name__ == "__main__":
    unittest.main()
