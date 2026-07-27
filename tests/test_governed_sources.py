from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.governed_sources import (
    audit_governed_source,
    generate_classic_gpt_all_in_one,
)

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "evidence" / "sources" / "SRC-023-classic-gpt-pack"


class GovernedSourceTests(unittest.TestCase):
    def test_sibling_pack_snapshot_inventories_every_byte(self) -> None:
        result = audit_governed_source(SNAPSHOT)
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.source_id, "SRC-023")
        self.assertEqual(
            result.inventory_digest,
            "sha256:9d55be7e5d4e18fc77473e50afe8cb17dccb4e866f3c24317d300e1594455369",
        )

    def test_original_stale_manifest_is_preserved_but_superseded(self) -> None:
        governed = json.loads((SNAPSHOT / "manifest.json").read_text())
        historical = json.loads((SNAPSHOT / "raw" / "manifest.json").read_text())
        self.assertEqual(historical["instruction_file"], "HIVE_OS_GPT_INSTRUCTIONS.txt")
        self.assertFalse((SNAPSHOT / "raw" / historical["instruction_file"]).exists())
        self.assertEqual(
            governed["canonical_instruction_file"],
            "raw/HIVE_MIND_OS_INSTRUCTIONS_V2.txt",
        )
        inventoried = {entry["path"] for entry in governed["files"]}
        self.assertIn("raw/imgo.jpg", inventoried)
        self.assertIn("raw/Logo.png", inventoried)
        self.assertIn("raw/manifest.json", inventoried)

    def test_all_in_one_is_reproducible_from_canonical_modules(self) -> None:
        manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
        historical = json.loads((SNAPSHOT / "raw" / "manifest.json").read_text())
        modules = {
            path: SNAPSHOT.joinpath(*Path(path).parts).read_bytes()
            for path in manifest["module_load_order"]
        }
        generated = generate_classic_gpt_all_in_one(
            modules,
            repository=historical["repository"],
            pull_request=historical["pull_request"],
            analyzed_head=historical["analyzed_head"],
            load_order=tuple(manifest["module_load_order"]),
        )
        self.assertEqual(
            generated,
            (SNAPSHOT / manifest["generated_all_in_one"]).read_bytes(),
        )

    def test_extra_missing_and_modified_snapshot_bytes_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            candidate = Path(directory) / "snapshot"
            shutil.copytree(SNAPSHOT, candidate)
            (candidate / "raw" / "extra.txt").write_text("extra", encoding="utf-8")
            self.assertFalse(audit_governed_source(candidate).valid)
            (candidate / "raw" / "extra.txt").unlink()
            (candidate / "raw" / "00_CONSTITUTION.md").write_text(
                "substituted",
                encoding="utf-8",
            )
            result = audit_governed_source(candidate)
            self.assertFalse(result.valid)
            self.assertTrue(any("mismatch" in issue for issue in result.issues))

    def test_images_are_non_independent_and_chain_of_custody_is_explicit(self) -> None:
        manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
        exhibits = {entry["path"]: entry for entry in manifest["image_exhibits"]}
        self.assertEqual(set(exhibits), {"raw/imgo.jpg", "raw/Logo.png"})
        self.assertFalse(exhibits["raw/imgo.jpg"]["independent"])
        self.assertEqual(exhibits["raw/imgo.jpg"]["chain_of_custody"], "unresolved")
        self.assertFalse(exhibits["raw/Logo.png"]["independent"])
        self.assertIn("not_independent_proof", exhibits["raw/Logo.png"]["evidence_use"])


if __name__ == "__main__":
    unittest.main()
