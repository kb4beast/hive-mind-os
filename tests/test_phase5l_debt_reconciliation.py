from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.phase5_debt_reconciliation import (
    ALL_DEBT_IDS,
    CURRENT_ACTIVE_DEBT_IDS,
    EXTERNAL_INPUT_DEBT_IDS,
    NEXT_INTERNAL_DEBT_IDS,
    OUTPUT_PATH,
    RELEASE_RUNS,
    RELEASE_SUBJECT_COMMIT,
    RESOLUTIONS,
    _digest_json,
    build_reconciliation,
)

ROOT = Path(__file__).resolve().parents[1]


class Phase5DebtReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = build_reconciliation(ROOT)

    def test_committed_record_matches_deterministic_rebuild(self) -> None:
        committed = json.loads((ROOT / OUTPUT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(committed, self.record)
        self.assertEqual(build_reconciliation(ROOT), self.record)

    def test_resolved_and_active_sets_exactly_partition_all_debt(self) -> None:
        resolved = tuple(item["debt_id"] for item in self.record["resolved"])
        active = tuple(self.record["current_active_debt_ids"])
        self.assertEqual(resolved, tuple(RESOLUTIONS))
        self.assertEqual(active, CURRENT_ACTIVE_DEBT_IDS)
        self.assertFalse(set(resolved) & set(active))
        self.assertEqual(set(resolved) | set(active), set(ALL_DEBT_IDS))
        self.assertEqual(
            self.record["counts"],
            {"prior_active": 35, "resolved": 10, "current_active": 25},
        )

    def test_each_resolution_has_specific_receipts(self) -> None:
        for resolution in self.record["resolved"]:
            self.assertTrue(resolution["reason"])
            self.assertTrue(resolution["evidence"])
            self.assertTrue(
                all(
                    item.startswith(("commit:", "run:", "local:"))
                    for item in resolution["evidence"]
                )
            )
        integrated = {
            "P5D-DEBT-05",
            "P5E-DEBT-04",
            "P5F-DEBT-04",
            "P5G-DEBT-04",
            "P5I-DEBT-04",
            "P5J-DEBT-04",
        }
        by_id = {item["debt_id"]: item for item in self.record["resolved"]}
        for debt_id in integrated:
            self.assertEqual(
                by_id[debt_id]["evidence"],
                [
                    f"commit:{RELEASE_SUBJECT_COMMIT}",
                    *(f"run:{run_id}" for run_id in RELEASE_RUNS),
                ],
            )

    def test_external_and_internal_work_remain_active(self) -> None:
        self.assertEqual(
            tuple(self.record["external_input_debt_ids"]),
            EXTERNAL_INPUT_DEBT_IDS,
        )
        self.assertEqual(
            tuple(self.record["next_internal_debt_ids"]),
            NEXT_INTERNAL_DEBT_IDS,
        )
        self.assertTrue(set(EXTERNAL_INPUT_DEBT_IDS).issubset(CURRENT_ACTIVE_DEBT_IDS))
        self.assertTrue(set(NEXT_INTERNAL_DEBT_IDS).issubset(CURRENT_ACTIVE_DEBT_IDS))
        self.assertIn("P5H-DEBT-04", CURRENT_ACTIVE_DEBT_IDS)
        self.assertIn("P5J-DEBT-01", CURRENT_ACTIVE_DEBT_IDS)

    def test_known_windows_failure_is_preserved_without_phase5_blame(self) -> None:
        local = self.record["local_release_validation"]
        self.assertEqual(local["result"], "failed-known-blocker")
        self.assertEqual(local["blocker_ids"], ["B-OPS-08"])
        self.assertEqual(local["tests_run"], 946)
        self.assertEqual(local["new_phase5_failures"], 0)

    def test_no_external_or_release_claim_is_promoted(self) -> None:
        claims = self.record["claims"]
        self.assertTrue(claims)
        self.assertTrue(all(value is False for value in claims.values()))

    def test_digest_covers_the_complete_record(self) -> None:
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
        self.assertNotEqual(hostile["reconciliation_digest"], _digest_json(hostile_body))


if __name__ == "__main__":
    unittest.main()
