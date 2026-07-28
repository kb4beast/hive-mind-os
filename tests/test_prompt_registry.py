from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import PromptRegistry, generation_zero_prompt
from hive_mind_os.roles import ROLE_CONTRACTS


class PromptRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = EvidenceLedger()
        self.registry = PromptRegistry(self.root, ledger=self.ledger)

    def tearDown(self) -> None:
        self.registry.close()
        self.ledger.close()
        self.temporary.cleanup()

    def _register(self, content: str, parent: str | None = None) -> str:
        return self.registry.register(
            Role.BUILDER,
            content,
            parent_digest=parent,
            created_by="author:test",
        )

    def test_content_addressing_deduplicates_storage(self) -> None:
        first = self._register("same prompt\r\n")
        second = self._register("same prompt\n")
        different = self._register("different prompt")
        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
        self.assertEqual(len(tuple(self.registry.artifact_root.glob("*.prompt"))), 2)

    def test_committed_generation_zero_prompts_match_p02_rendering(self) -> None:
        prompt_root = Path(__file__).parents[1] / "prompts"
        digests = self.registry.bootstrap(prompt_root)
        for role in Role:
            self.assertEqual(
                self.registry.read(digests[role.value]),
                generation_zero_prompt(ROLE_CONTRACTS[role]),
            )

    def test_atomic_promotion_failure_preserves_valid_pointer(self) -> None:
        champion = self._register("champion")
        challenger = self._register("challenger", champion)
        self.registry.promote(
            Role.BUILDER,
            champion,
            promoted_by="evaluator:test",
            experiment_id="generation-0",
            expected_current=None,
        )
        with patch(
            "hive_mind_os.prompt_registry.os.replace",
            side_effect=OSError("simulated crash"),
        ):
            with self.assertRaises(OSError):
                self.registry.promote(
                    Role.BUILDER,
                    challenger,
                    promoted_by="evaluator:test",
                    experiment_id="EXP-crash",
                    expected_current=champion,
                )
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), champion)
        self.assertEqual(self.registry.read(champion), "champion")
        self.assertEqual(tuple(self.root.glob(".*.tmp")), ())

    def test_lineage_rollback_and_quarantine_are_retained(self) -> None:
        champion = self._register("champion")
        challenger = self._register("challenger", champion)
        self.registry.promote(
            Role.BUILDER,
            champion,
            promoted_by="evaluator:test",
            experiment_id="generation-0",
            expected_current=None,
        )
        self.registry.promote(
            Role.BUILDER,
            challenger,
            promoted_by="evaluator:test",
            experiment_id="EXP-keep",
            expected_current=champion,
        )
        promotion = [
            item
            for item in self.registry.lineage(challenger)
            if item["kind"] == "promotion"
        ][0]
        self.assertEqual(promotion["parent_digest"], champion)
        prior = self.registry.rollback_champion(
            Role.BUILDER,
            champion,
            actor="steward:test",
            reason="regression",
        )
        self.assertEqual(prior, challenger)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), champion)
        self.registry.quarantine(
            Role.BUILDER,
            challenger,
            actor="evaluator:test",
            experiment_id="EXP-quarantine",
            reasons=("conflict",),
        )
        self.assertTrue(self.registry.is_quarantined(challenger))
        self.assertEqual(self.registry.read(challenger), "challenger")
        event_types = [event["event_type"] for event in self.ledger.events()]
        self.assertIn("prompt.promoted", event_types)
        self.assertIn("prompt.rollback", event_types)
        self.assertIn("prompt.quarantined", event_types)

    def test_registered_artifact_cannot_be_overwritten_through_registry(self) -> None:
        digest = self._register("immutable")
        path = self.registry.artifact_path(digest)
        with self.assertRaises(FileExistsError):
            with path.open("xb") as handle:
                handle.write(b"replacement")
        self.assertEqual(self.registry.read(digest), "immutable")
        self.assertEqual(os.path.getsize(path), len(b"immutable"))


if __name__ == "__main__":
    unittest.main()
