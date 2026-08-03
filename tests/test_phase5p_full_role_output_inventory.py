from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.phase5p_full_role_output_inventory import (
    IMPLEMENTATION_PATHS,
    OUTPUT_PATH,
    _digest_json,
    build_inventory,
)

ROOT = Path(__file__).resolve().parents[1]


class Phase5PFullRoleOutputInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = build_inventory(ROOT)

    def test_committed_inventory_matches_deterministic_rebuild(self) -> None:
        committed = json.loads((ROOT / OUTPUT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(committed, self.inventory)
        self.assertEqual(build_inventory(ROOT), self.inventory)

    def test_all_twenty_two_contracts_and_files_are_sealed(self) -> None:
        self.assertEqual(self.inventory["role_count"], 3)
        self.assertEqual(self.inventory["output_count"], 22)
        self.assertEqual(
            set(self.inventory["implementation"]), set(IMPLEMENTATION_PATHS)
        )
        versions = {
            version
            for role in self.inventory["roles"].values()
            for version in role["output_schema_versions"].values()
        }
        self.assertEqual(len(versions), 22)
        self.assertTrue(
            all(
                value.startswith("sha256:")
                for value in self.inventory["implementation"].values()
            )
        )

    def test_inventory_preserves_all_fail_closed_boundaries(self) -> None:
        boundary_fields = (
            "authority_added",
            "execution_performed",
            "authenticated_independence_claimed",
            "release_ready",
            "production_ready",
            "deployment_authorized",
            "promotion_authorized",
            "superiority_claimed",
        )
        self.assertTrue(
            all(self.inventory[field] is False for field in boundary_fields)
        )
        for role in self.inventory["roles"].values():
            self.assertTrue(all(value is False for value in role["claims"].values()))

    def test_inventory_digest_detects_resealed_claim_escalation(self) -> None:
        hostile = deepcopy(self.inventory)
        hostile["release_ready"] = True
        body = {
            key: value for key, value in hostile.items() if key != "inventory_digest"
        }
        self.assertNotEqual(hostile["inventory_digest"], _digest_json(body))


if __name__ == "__main__":
    unittest.main()
