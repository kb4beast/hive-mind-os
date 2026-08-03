from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.phase5_debt_reconciliation import ALL_DEBT_IDS
from scripts.phase5m_debt_reconciliation import (
    EXTERNAL_INPUT_DEBT_IDS,
    INVENTORY_TAIL,
    NEW_RESOLUTIONS,
    NEXT_INTERNAL_DEBT_IDS,
    OUTPUT_PATH,
    PREDECESSOR_DIGEST,
    SUBJECT_COMMIT,
    SUBJECT_RUNS,
    _digest_json,
    build_reconciliation,
)

ROOT = Path(__file__).resolve().parents[1]


class Phase5MDebtReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = build_reconciliation(ROOT)

    def test_committed_record_matches_deterministic_rebuild(self) -> None:
        committed = json.loads((ROOT / OUTPUT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(committed, self.record)
        self.assertEqual(build_reconciliation(ROOT), self.record)

    def test_phase5m_adds_seven_narrow_resolutions(self) -> None:
        self.assertEqual(
            tuple(self.record["resolved_in_phase5m"]), tuple(NEW_RESOLUTIONS)
        )
        self.assertEqual(
            self.record["counts"],
            {
                "total": 35,
                "prior_resolved": 10,
                "resolved_in_phase5m": 7,
                "resolved": 17,
                "current_active": 18,
            },
        )
        self.assertEqual(len(self.record["resolved"]), 17)
        self.assertEqual(len(self.record["current_active_debt_ids"]), 18)

    def test_every_new_resolution_has_exact_hosted_and_artifact_receipts(self) -> None:
        by_id = {item["debt_id"]: item for item in self.record["resolved"]}
        for debt_id in NEW_RESOLUTIONS:
            evidence = by_id[debt_id]["evidence"]
            self.assertEqual(evidence[0], f"commit:{SUBJECT_COMMIT}")
            self.assertEqual(evidence[1:3], [f"run:{run_id}" for run_id in SUBJECT_RUNS])
            self.assertTrue(all(item.startswith("artifact:") for item in evidence[3:]))

    def test_external_and_remaining_internal_debt_stay_active(self) -> None:
        active = set(self.record["current_active_debt_ids"])
        self.assertTrue(set(EXTERNAL_INPUT_DEBT_IDS).issubset(active))
        self.assertTrue(set(NEXT_INTERNAL_DEBT_IDS).issubset(active))
        self.assertFalse(set(NEW_RESOLUTIONS) & active)
        self.assertEqual(
            {item["debt_id"] for item in self.record["resolved"]} | active,
            set(ALL_DEBT_IDS),
        )

    def test_predecessor_tail_and_claim_boundaries_are_preserved(self) -> None:
        self.assertEqual(
            self.record["predecessor"]["reconciliation_digest"],
            PREDECESSOR_DIGEST,
        )
        self.assertEqual(self.record["inventory_tail_digest"], INVENTORY_TAIL)
        self.assertTrue(all(value is False for value in self.record["claims"].values()))
        self.assertEqual(
            self.record["local_release_validation"]["blocker_ids"], ["B-OPS-08"]
        )

    def test_digest_covers_complete_successor_record(self) -> None:
        body = {
            key: value
            for key, value in self.record.items()
            if key != "reconciliation_digest"
        }
        self.assertEqual(self.record["reconciliation_digest"], _digest_json(body))
        hostile = deepcopy(self.record)
        hostile["current_active_debt_ids"].pop()
        hostile_body = {
            key: value
            for key, value in hostile.items()
            if key != "reconciliation_digest"
        }
        self.assertNotEqual(
            hostile["reconciliation_digest"], _digest_json(hostile_body)
        )


if __name__ == "__main__":
    unittest.main()
