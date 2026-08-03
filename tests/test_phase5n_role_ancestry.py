from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from scripts.phase5h_role_ancestry_index import (
    OUTPUT_PATH,
    SUBJECT_COMMIT,
    _digest_json,
    build_index,
)
from scripts.verify_phase5_role_ancestry_installed_wheel import verify_installed

ROOT = Path(__file__).resolve().parents[1]


class Phase5RoleAncestryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = build_index(ROOT)

    def test_committed_index_matches_git_reconstruction(self) -> None:
        committed = json.loads((ROOT / OUTPUT_PATH).read_text(encoding="utf-8"))
        self.assertEqual(committed, self.index)
        self.assertEqual(build_index(ROOT), self.index)

    def test_all_eight_roles_have_exact_git_and_pr_receipts(self) -> None:
        self.assertEqual(self.index["role_count"], 8)
        self.assertEqual(
            [role["role"] for role in self.index["roles"]],
            [
                "Orchestrator",
                "Architect",
                "Builder",
                "Curator",
                "Integrator",
                "Steward",
                "Optimizer",
                "Consolidation Court",
            ],
        )
        for role in self.index["roles"]:
            self.assertTrue(role["merge_ancestry_verified"])
            self.assertTrue(role["current_tree_verified"])
            self.assertEqual(len(role["pull_request"]["merge_commit"]), 40)
            self.assertEqual(len(role["pull_request"]["merge_tree"]), 40)
            self.assertEqual(len(role["implementation"]["git_blob"]), 40)
            self.assertEqual(len(role["contract"]["git_blob"]), 40)

    def test_missing_governance_evidence_is_explicit(self) -> None:
        by_item = {role["phase_item"]: role for role in self.index["roles"]}
        for item in "ABCD":
            self.assertEqual(by_item[item]["missing_evidence"], [])
        for item in "EFGH":
            self.assertEqual(
                by_item[item]["missing_evidence"],
                ["dedicated-procedural-court-record"],
            )

    def test_source_tree_reproduces_the_package_hash_boundary(self) -> None:
        result = verify_installed(self.index, ROOT / "src")
        self.assertEqual(result["role_count"], 8)
        self.assertTrue(all(role["matches_git_subject"] for role in result["verified_roles"]))
        self.assertFalse(result["authenticated_independence_claimed"])
        self.assertFalse(result["release_ready"])

    def test_tampered_index_and_package_fail_closed(self) -> None:
        hostile = deepcopy(self.index)
        hostile["roles"][0]["implementation"]["sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(RuntimeError, "index digest"):
            verify_installed(hostile, ROOT / "src")

    def test_index_digest_and_authority_boundaries(self) -> None:
        body = {key: value for key, value in self.index.items() if key != "index_digest"}
        self.assertEqual(self.index["index_digest"], _digest_json(body))
        self.assertEqual(self.index["subject_commit"], SUBJECT_COMMIT)
        self.assertFalse(self.index["authenticated_independence_claimed"])
        self.assertFalse(self.index["release_ready"])
        self.assertFalse(self.index["production_ready"])
        self.assertFalse(self.index["promotion_authorized"])
        self.assertFalse(self.index["superiority_claimed"])


if __name__ == "__main__":
    unittest.main()
