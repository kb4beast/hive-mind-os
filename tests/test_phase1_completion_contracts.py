from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]
INVENTORY_PATH = (
    REPOSITORY_ROOT / "evidence" / "phase1" / "phase1_completion_inventory.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Phase1CompletionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    def test_generation_zero_contract_remains_frozen(self) -> None:
        generation_zero = self.inventory["generation_zero"]
        self.assertEqual(generation_zero["root_api_count"], 131)
        self.assertEqual(generation_zero["package_api_count"], 33)
        self.assertEqual(generation_zero["cli_parser_count"], 13)
        self.assertFalse(generation_zero["production_runtime_changed"])
        self.assertEqual(
            generation_zero["inventory_digest"],
            "sha256:57ad3e54934f2f1315f71e1d994253ce"
            "5d9100e2f161d430354039592e6ec037",
        )
        for key in ("fixture", "surface_inventory"):
            path = REPOSITORY_ROOT / generation_zero[f"{key}_path"]
            self.assertEqual(_sha256(path), generation_zero[f"{key}_sha256"])

    def test_atomic_claim_register_is_complete_and_unique(self) -> None:
        receipt = self.inventory["claim_register"]
        path = REPOSITORY_ROOT / receipt["path"]
        text = path.read_text(encoding="utf-8")
        claim_ids = re.findall(
            r"\| `((?:OB|MEM|AG|TEL|GOV)-\d{3})` \|",
            text,
        )
        self.assertEqual(len(claim_ids), receipt["count"])
        self.assertEqual(len(claim_ids), len(set(claim_ids)))
        self.assertEqual(_sha256(path), receipt["sha256"])

    def test_every_registered_source_has_a_disposition(self) -> None:
        source_register = (
            REPOSITORY_ROOT
            / "evidence"
            / "sources"
            / "PHASE1_PRIMARY_SOURCE_REGISTER.md"
        ).read_text(encoding="utf-8")
        registered = set(re.findall(r"^## `(P1SRC-[^`]+)`", source_register, re.M))
        dispositions = self.inventory["source_admission"]["dispositions"]
        self.assertEqual(registered, set(dispositions) - {"P1SRC-ARMORY-UNIDENTIFIED"})
        self.assertEqual(
            set(dispositions.values()),
            {"adopt", "adapt", "defer", "reject", "quarantine"},
        )
        court_path = REPOSITORY_ROOT / self.inventory["source_admission"]["path"]
        self.assertEqual(
            _sha256(court_path),
            self.inventory["source_admission"]["sha256"],
        )

    def test_adrs_and_canonical_contracts_are_adopted_without_activation(self) -> None:
        for number, filename in (
            (
                "ADR-018",
                "ADR-018-CANONICAL-AGENT-DEFINITIONS-AND-PROJECTIONS.md",
            ),
            ("ADR-019", "ADR-019-OPEN-MEMORY-AND-OBSIDIAN-BRAIN.md"),
            (
                "ADR-020",
                "ADR-020-USAGE-TELEMETRY-PRIVACY-AND-FAIR-LEARNING.md",
            ),
        ):
            text = (
                REPOSITORY_ROOT / "docs" / "architecture" / filename
            ).read_text(encoding="utf-8")
            self.assertIn("Status: adopted as the Phase 1 architecture contract", text)
            self.assertEqual(
                self.inventory["adrs"][number]["status"],
                "adopted-architecture",
            )

        contracts = (
            REPOSITORY_ROOT
            / "docs"
            / "architecture"
            / "PHASE1_CANONICAL_CONTRACTS.md"
        ).read_text(encoding="utf-8")
        for contract in self.inventory["contracts"]:
            self.assertIn(f"`{contract['id']}`", contracts)
        self.assertIn(
            "Phase 1 changes no file under `src/hive_mind_os`",
            contracts,
        )

    def test_obsidian_configuration_is_local_only(self) -> None:
        ignore_rules = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertRegex(ignore_rules, r"(?m)^\.obsidian/$")
        self.assertFalse((REPOSITORY_ROOT / ".obsidian").exists())

    def test_handoff_and_stack_receipts_are_pinned(self) -> None:
        handoff = REPOSITORY_ROOT / self.inventory["handoff"]["path"]
        self.assertEqual(_sha256(handoff), self.inventory["handoff"]["sha256"])
        self.assertEqual(self.inventory["previous_head"], "ee00967610df9e7d0ec4a5150bac751cc6880105")
        self.assertEqual(self.inventory["pr"]["number"], 29)
        self.assertTrue(self.inventory["pr"]["draft"])
        self.assertEqual(
            self.inventory["pr"]["base_branch"],
            "codex/repair-ci-test-contract",
        )
        self.assertEqual(
            self.inventory["pr"]["base_sha"],
            "0948f7ec385238f5825ce7c39dd25de2e9a1035d",
        )


if __name__ == "__main__":
    unittest.main()
