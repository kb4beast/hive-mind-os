from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.phase5e_to_k_inventory import (
    PHASE5D_INVENTORY_PATH,
    _digest_json,
    _validate_inventory_digest,
    build_inventory_chain,
    phase_specs,
)

ROOT = Path(__file__).resolve().parents[1]


class Phase5EvidenceInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.specs = phase_specs()
        self.records = build_inventory_chain(ROOT)

    def test_committed_chain_matches_deterministic_rebuild(self) -> None:
        self.assertEqual(len(self.records), 7)
        for spec, record in zip(self.specs, self.records, strict=True):
            committed = json.loads((ROOT / spec.output_path).read_text(encoding="utf-8"))
            self.assertEqual(committed, record)
        self.assertEqual(build_inventory_chain(ROOT), self.records)

    def test_chain_starts_at_phase5d_and_links_every_successor(self) -> None:
        predecessor_path = PHASE5D_INVENTORY_PATH
        predecessor_record = json.loads(
            (ROOT / predecessor_path).read_text(encoding="utf-8")
        )
        predecessor_digest = predecessor_record["inventory_digest"]
        for spec, record in zip(self.specs, self.records, strict=True):
            self.assertEqual(
                record["predecessor"],
                {
                    "path": predecessor_path.as_posix(),
                    "inventory_digest": predecessor_digest,
                },
            )
            predecessor_path = spec.output_path
            predecessor_digest = record["inventory_digest"]

    def test_each_inventory_digest_covers_the_complete_body(self) -> None:
        for record in self.records:
            body = {key: value for key, value in record.items() if key != "inventory_digest"}
            self.assertEqual(record["inventory_digest"], _digest_json(body))
            hostile = deepcopy(record)
            hostile["boundary_assertions"].popitem()
            hostile_body = {
                key: value for key, value in hostile.items() if key != "inventory_digest"
            }
            self.assertNotEqual(hostile["inventory_digest"], _digest_json(hostile_body))

    def test_contracts_reproduce_and_authority_stays_closed(self) -> None:
        for spec, record in zip(self.specs, self.records, strict=True):
            contract = record["contract_reproduction"]
            self.assertEqual(tuple(contract["output_fields"]), spec.output_fields)
            self.assertTrue(contract["request_valid"])
            self.assertTrue(contract["envelope_valid"])
            self.assertEqual(
                set(record["boundary_assertions"]),
                {path for path, _ in spec.boundaries},
            )
            self.assertFalse(record["authority_added"])
            self.assertFalse(record["authenticated_independence_claimed"])
            self.assertFalse(record["release_ready"])
            self.assertFalse(record["production_ready"])
            self.assertFalse(record["deployment_authorized"])
            self.assertFalse(record["promotion_authorized"])
            self.assertFalse(record["superiority_claimed"])

    def test_predecessor_digest_tampering_fails_closed(self) -> None:
        predecessor = json.loads(
            (ROOT / PHASE5D_INVENTORY_PATH).read_text(encoding="utf-8")
        )
        predecessor["scope"] = "hostile-scope"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "hostile.json"
            path.write_text(json.dumps(predecessor), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                _validate_inventory_digest(predecessor, path)

    def test_all_implementation_receipts_are_real_files(self) -> None:
        for record in self.records:
            for path, claimed_digest in record["implementation"].items():
                self.assertTrue((ROOT / path).is_file())
                self.assertTrue(claimed_digest.startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
