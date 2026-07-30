from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.release_integration_audit import (
    EXPECTED_ACCEPTED_STACK,
    EXPECTED_ROLES,
    audit_repository,
    load_json_strict,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "releases" / "version_1.1-manifest.json"


class ReleaseVersion11IntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_json_strict(MANIFEST)

    def test_manifest_separates_integration_train_from_distribution(self) -> None:
        self.assertEqual(self.manifest["integration_train"], "1.1")
        self.assertFalse(self.manifest["integration_train_is_distribution_version"])
        self.assertEqual(self.manifest["distribution"]["version"], "0.6.0")
        self.assertEqual(
            self.manifest["distribution"]["build_requirements"],
            ["setuptools==83.0.0"],
        )

    def test_accepted_stack_and_pr30_are_not_conflated(self) -> None:
        accepted = tuple(
            item["number"] for item in self.manifest["accepted_stacked_prs"]
        )
        self.assertEqual(accepted, EXPECTED_ACCEPTED_STACK)
        self.assertNotIn(30, accepted)
        superseded = self.manifest["superseded_historical_prs"]
        self.assertEqual(len(superseded), 1)
        self.assertEqual(superseded[0]["number"], 30)
        self.assertEqual(
            superseded[0]["head"],
            "39e07c9e3c3ce439911481be2d38d901d05d4824",
        )
        self.assertEqual(superseded[0]["posture"], "superseded-but-preserved")

    def test_losing_pr30_package_is_not_a_second_active_authority(self) -> None:
        for relative in self.manifest["forbidden_active_paths"]:
            self.assertFalse((ROOT / relative).exists(), relative)
        disposition = (
            ROOT / "docs" / "architecture" / "PR30_SUPERSESSION_AND_DISPOSITION.md"
        ).read_text(encoding="utf-8")
        for required in (
            "Separate `hive_mind_os_v2` namespace",
            "tree-neutral merge",
            "do not activate either design",
            "tests/test_v2_memory_usage_foundation.py",
        ):
            self.assertIn(required, disposition)

    def test_stale_handoff_is_fail_closed_and_phase5a_is_bounded(self) -> None:
        stale = (ROOT / self.manifest["handoffs"]["superseded"]).read_text(
            encoding="utf-8"
        )
        current = (ROOT / self.manifest["handoffs"]["current"]).read_text(
            encoding="utf-8"
        )
        self.assertTrue(stale.startswith("> **SUPERSEDED — DO NOT EXECUTE.**"))
        for required in (
            "conservative reconstruction",
            "B-OPS-09",
            "no Explorer v2 versus Generation Zero comparison",
            "procedural role labels",
            "P20",
        ):
            self.assertIn(required, current)

    def test_adr_registry_disambiguates_pr30_and_corrects_adr026(self) -> None:
        index = (ROOT / "docs" / "architecture" / "ADR_INDEX.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("three historical numeric collisions", index)
        self.assertIn("`ADR-021-PR30`", index)
        self.assertIn("`ADR-021-PR31`", index)
        self.assertRegex(
            index,
            r"\| `ADR-026` .* adapted for bounded stacked draft delivery",
        )

    def test_integrated_inventory_chain_is_reconciled_without_erasing_history(self) -> None:
        path = ROOT / self.manifest["evidence"]["inventory_reconciliation"]
        reconciliation = load_json_strict(path)
        self.assertFalse(reconciliation["historical_evidence_rewritten"])
        self.assertFalse(reconciliation["runtime_activation_changed"])
        self.assertEqual(len(reconciliation["entries"]), 8)
        for entry in reconciliation["entries"]:
            current = load_json_strict(ROOT / entry["path"])
            self.assertEqual(
                current["inventory_digest"],
                entry["integrated_tree_digest"],
                entry["path"],
            )
            self.assertNotEqual(
                entry["historical_digest"],
                entry["integrated_tree_digest"],
            )
        self.assertEqual(reconciliation["verification"]["result"], "pass")
        self.assertEqual(reconciliation["verification"]["affected_regression_tests"], 152)

    def test_procedural_hive_mind_review_is_complete_but_not_false_independence(self) -> None:
        review_path = ROOT / self.manifest["evidence"]["procedural_role_review"]
        review = load_json_strict(review_path)
        self.assertFalse(review["independence"]["authenticated_distinct_actors"])
        roles = tuple(item["role"] for item in review["roles"])
        self.assertEqual(roles, EXPECTED_ROLES)
        identities = tuple(item["identity"] for item in review["roles"])
        self.assertEqual(len(identities), len(set(identities)))
        self.assertTrue(all(item["disposition"] == "adapt" for item in review["roles"]))

    def test_manifest_denies_unsupported_claims(self) -> None:
        claims = self.manifest["claims"]
        self.assertTrue(claims)
        self.assertTrue(all(value is False for value in claims.values()))
        self.assertIn("B-OPS-09", self.manifest["open_blockers"])
        self.assertIn("P20-release-readiness-court", self.manifest["open_blockers"])

    def test_strict_json_loader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            duplicate = Path(temporary) / "duplicate.json"
            duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                load_json_strict(duplicate)

    def test_repository_contract_passes_without_pending_git_seal(self) -> None:
        result = audit_repository(
            ROOT,
            require_git_ancestry=False,
            allow_pending_pr30_merge=True,
            allow_bootstrap_workflow=True,
        )
        self.assertTrue(result.valid, result.issues)

    def test_exact_git_ancestry_after_the_preservation_merge_is_sealed(self) -> None:
        merge_commit = self.manifest["superseded_historical_prs"][0][
            "tree_neutral_merge_commit"
        ]
        if merge_commit is None:
            self.skipTest("tree-neutral PR #30 merge is sealed after implementation push")
        result = audit_repository(
            ROOT,
            require_git_ancestry=True,
            allow_pending_pr30_merge=False,
            allow_bootstrap_workflow=False,
        )
        self.assertTrue(result.valid, result.issues)


if __name__ == "__main__":
    unittest.main()
