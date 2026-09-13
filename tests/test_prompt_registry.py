from __future__ import annotations

import json
import os
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from promotion_auth_fixtures import verifier_for
from promotion_fixtures import authenticated_rollback, decision_payload

from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import (
    PromotionAdmissionError,
    PromptRegistry,
    canonical_prompt_bytes,
    generation_zero_prompt,
    prompt_digest,
)
from hive_mind_os.roles import ROLE_CONTRACTS


class PromptRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.ledger = EvidenceLedger()
        self.registry = PromptRegistry(self.root, ledger=self.ledger, principal_verifier=verifier_for())

    def tearDown(self) -> None:
        self.registry.close()
        self.ledger.close()
        self.temporary.cleanup()

    def _register(
        self,
        content: str,
        parent: str | None = None,
        *,
        experiment_id: str | None = None,
    ) -> str:
        return self.registry.register(
            Role.BUILDER,
            content,
            parent_digest=parent,
            created_by="author:test",
            experiment_id=experiment_id,
        )

    def _decision(
        self,
        *,
        experiment_id: str,
        candidate: str,
        current: str,
        actor: str = "judge:test",
        **overrides: object,
    ) -> int:
        payload = decision_payload(self.root, candidate_digest=candidate, parent=current,
                                   experiment_id=experiment_id)
        payload["judge_id"] = actor
        payload.update(overrides)
        return self.ledger.append_event(
            experiment_id,
            "experiment.decision",
            actor,
            payload,
        )

    def _bootstrap_builder(self) -> str:
        content = generation_zero_prompt(ROLE_CONTRACTS[Role.BUILDER])
        digest = self.registry.register(
            Role.BUILDER,
            content,
            parent_digest=None,
            created_by="repository:generation-0",
        )
        self.registry.promote(
            Role.BUILDER,
            digest,
            promoted_by="repository:generation-0",
            experiment_id="generation-0",
            expected_current=None,
        )
        return digest

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

    def test_repeated_trailing_newlines_register_hash_and_read_identically(self) -> None:
        for content in ("x", "x\n", "x\n\n", "x\n\n\n", "x\r\n\r\n", "x\r\r\n",
                        b"x\r\n\r\n\r\n", "x\n\ninside \t\r\n\r\n", "\r\n\r\n"):
            with self.subTest(content=content):
                canonical = canonical_prompt_bytes(content)
                self.assertEqual(canonical_prompt_bytes(canonical), canonical)
                digest = self.registry.register("builder", content, parent_digest=None, created_by="author:test")
                self.assertEqual(digest, prompt_digest(content))
                self.assertEqual(digest, "sha256:" + sha256(canonical).hexdigest())
                self.assertEqual(self.registry.artifact_path(digest).read_bytes(), canonical)
                self.assertEqual(self.registry.read(digest).encode("utf-8"), canonical)
        self.assertEqual(canonical_prompt_bytes("x\n\ninside \t\r\n\r\n"), b"x\n\ninside \t")

    def test_legacy_newline_artifacts_are_preserved_for_explicit_migration(self) -> None:
        for trailing in (2, 3):
            with self.subTest(trailing=trailing):
                # Pinned legacy registration removed one LF before hashing,
                # then its digest helper removed another LF from stored bytes.
                content = "legacy-" + str(trailing) + "\r\n" * trailing
                stored = content.replace("\r\n", "\n").removesuffix("\n").encode()
                legacy_digest = "sha256:" + sha256(stored.removesuffix(b"\n")).hexdigest()
                path = self.registry.artifact_path(legacy_digest)
                path.write_bytes(stored)
                self.registry._atomic_json(self.registry.pointer_path,
                                           {"schema_version": 1, "champions": {"builder": legacy_digest}})
                before = self.registry.pointer_path.read_bytes()
                with self.assertRaises(PromotionAdmissionError) as caught:
                    self.registry.read(legacy_digest)
                self.assertEqual(caught.exception.code, "artifact-noncanonical")
                self.assertEqual(self.registry.migration_status()["roles"]["builder"], "blocked:artifact-noncanonical")
                if trailing == 2:  # New canonical digest collides with the legacy path.
                    with self.assertRaisesRegex(PromotionAdmissionError, "explicit migration review"):
                        self._register(content)
                else:
                    fresh = self._register(content)
                    self.assertNotEqual(fresh, legacy_digest)
                    self.assertEqual(self.registry.read(fresh), "legacy-3")
                self.assertEqual(path.read_bytes(), stored)
                self.assertEqual(self.registry.pointer_path.read_bytes(), before)

    def test_atomic_promotion_failure_preserves_valid_pointer(self) -> None:
        champion = self._bootstrap_builder()
        challenger = self._register(
            "challenger",
            champion,
            experiment_id="EXP-crash",
        )
        with patch(
            "hive_mind_os.prompt_registry.os.replace",
            side_effect=OSError("simulated crash"),
        ):
            decision_sequence = self._decision(
                experiment_id="EXP-crash",
                candidate=challenger,
                current=champion,
            )
            with self.assertRaises(OSError):
                self.registry.promote(
                    Role.BUILDER,
                    challenger,
                    promoted_by="promoter:test",
                    experiment_id="EXP-crash",
                    expected_current=champion,
                    decision_event_sequence=decision_sequence,
                )
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), champion)
        self.assertEqual(
            self.registry.read(champion),
            generation_zero_prompt(ROLE_CONTRACTS[Role.BUILDER]),
        )
        self.assertEqual(tuple(self.root.glob(".*.tmp")), ())

    def test_lineage_rollback_and_quarantine_are_retained(self) -> None:
        champion = self._bootstrap_builder()
        challenger = self._register(
            "challenger",
            champion,
            experiment_id="EXP-keep",
        )
        decision_sequence = self._decision(
            experiment_id="EXP-keep",
            candidate=challenger,
            current=champion,
        )
        self.registry.promote(
            Role.BUILDER,
            challenger,
            promoted_by="promoter:test",
            experiment_id="EXP-keep",
            expected_current=champion,
            decision_event_sequence=decision_sequence,
        )
        promotion = [
            item
            for item in self.registry.lineage(challenger)
            if item["kind"] == "promotion"
        ][0]
        self.assertEqual(promotion["parent_digest"], champion)
        prior = authenticated_rollback(self.registry, champion)
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

    def test_non_generation_zero_promotion_requires_a_decision_event(self) -> None:
        champion = self._bootstrap_builder()
        challenger = self._register(
            "challenger",
            champion,
            experiment_id="EXP-no-decision",
        )
        with self.assertRaisesRegex(RuntimeError, "requires an experiment.decision"):
            self.registry.promote(
                Role.BUILDER,
                challenger,
                promoted_by="promoter:test",
                experiment_id="EXP-no-decision",
                expected_current=champion,
            )

    def test_generation_zero_bootstrap_requires_registration_author(self) -> None:
        champion = self.registry.register(
            Role.BUILDER,
            generation_zero_prompt(ROLE_CONTRACTS[Role.BUILDER]),
            parent_digest=None,
            created_by="repository:generation-0",
        )
        with self.assertRaisesRegex(RuntimeError, "matching artifact registration"):
            self.registry.promote(
                Role.BUILDER,
                champion,
                promoted_by="intruder:test",
                experiment_id="generation-0",
                expected_current=None,
            )
        self.assertIsNone(self.registry.champion_digest(Role.BUILDER))

    def test_raw_pointer_write_without_promotion_is_rejected(self) -> None:
        rogue = self.registry.register(
            Role.BUILDER,
            "attacker-selected prompt",
            parent_digest=self._bootstrap_builder(),
            created_by="attacker:test",
        )
        self.registry.pointer_path.write_text(
            json.dumps(
                {"schema_version": 1, "champions": {Role.BUILDER.value: rogue}}
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(RuntimeError, "resolving promotion"):
            self.registry.champion_prompt(Role.BUILDER)

    def test_generation_zero_bootstrap_rejects_noncanonical_content_and_actor(self) -> None:
        invalid = self.registry.register(
            Role.BUILDER,
            "attacker-selected bootstrap prompt",
            parent_digest=None,
            created_by="repository:generation-0",
        )
        with self.assertRaisesRegex(RuntimeError, "experiment.decision"):
            self.registry.promote(
                Role.BUILDER,
                invalid,
                promoted_by="repository:generation-0",
                experiment_id="generation-0",
                expected_current=None,
            )

        canonical = self.registry.register(
            Role.BUILDER,
            generation_zero_prompt(ROLE_CONTRACTS[Role.BUILDER]),
            parent_digest=None,
            created_by="attacker:generation-0",
        )
        with self.assertRaisesRegex(RuntimeError, "experiment.decision"):
            self.registry.promote(
                Role.BUILDER,
                canonical,
                promoted_by="attacker:generation-0",
                experiment_id="generation-0",
                expected_current=None,
            )
        self.assertIsNone(self.registry.champion_digest(Role.BUILDER))

    def test_self_promotion_and_forged_decision_fail_closed(self) -> None:
        champion = self._bootstrap_builder()
        challenger = self._register(
            "challenger",
            champion,
            experiment_id="EXP-forged",
        )
        self_sequence = self._decision(
            experiment_id="EXP-forged",
            candidate=challenger,
            current=champion,
            actor="author:test",
            judge_id="author:test",
        )
        with self.assertRaisesRegex(RuntimeError, "four distinct"):
            self.registry.promote(
                Role.BUILDER,
                challenger,
                promoted_by="author:test",
                experiment_id="EXP-forged",
                expected_current=champion,
                decision_event_sequence=self_sequence,
            )

        forged_sequence = self._decision(
            experiment_id="EXP-forged",
            candidate=challenger,
            current=champion,
            candidate_digest="sha256:" + "f" * 64,
        )
        with self.assertRaisesRegex(RuntimeError, "mismatched candidate_digest"):
            self.registry.promote(
                Role.BUILDER,
                challenger,
                promoted_by="promoter:test",
                experiment_id="EXP-forged",
                expected_current=champion,
                decision_event_sequence=forged_sequence,
            )

    def test_registered_artifact_cannot_be_overwritten_through_registry(self) -> None:
        digest = self._register("immutable")
        path = self.registry.artifact_path(digest)
        with self.assertRaises(FileExistsError):
            with path.open("xb") as handle:
                handle.write(b"replacement")
        self.assertEqual(self.registry.read(digest), "immutable")
        self.assertEqual(os.path.getsize(path), len(b"immutable"))

    def test_rollback_rejects_never_promoted_and_quarantined_targets(self) -> None:
        champion = self._bootstrap_builder()
        never_promoted = self._register("unreviewed", champion)
        with self.assertRaisesRegex(RuntimeError, "never a promoted champion"):
            self.registry.rollback_champion(
                Role.BUILDER,
                never_promoted,
                actor="attacker",
                reason="activation bypass",
            )
        self.registry.quarantine(
            Role.BUILDER,
            champion,
            actor="curator:test",
            experiment_id="EXP-quarantine-champion",
            reasons=("unsafe",),
        )
        with self.assertRaisesRegex(RuntimeError, "quarantined"):
            self.registry.rollback_champion(
                Role.BUILDER,
                champion,
                actor="attacker",
                reason="restore quarantined artifact",
            )

    def test_promotion_rejects_quarantined_candidate(self) -> None:
        champion = self._bootstrap_builder()
        candidate = self._register(
            "candidate",
            champion,
            experiment_id="EXP-quarantined-promotion",
        )
        decision_sequence = self._decision(
            experiment_id="EXP-quarantined-promotion",
            candidate=candidate,
            current=champion,
        )
        self.registry.quarantine(
            Role.BUILDER,
            candidate,
            actor="curator:test",
            experiment_id="EXP-quarantined-promotion",
            reasons=("unsafe",),
        )
        with self.assertRaisesRegex(RuntimeError, "quarantined"):
            self.registry.promote(
                Role.BUILDER,
                candidate,
                promoted_by="promoter:test",
                experiment_id="EXP-quarantined-promotion",
                expected_current=champion,
                decision_event_sequence=decision_sequence,
            )
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), champion)

    def test_quarantined_active_champion_cannot_be_served(self) -> None:
        champion = self._bootstrap_builder()
        self.registry.quarantine(
            Role.BUILDER,
            champion,
            actor="curator:test",
            experiment_id="EXP-active-quarantine",
            reasons=("unsafe",),
        )
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), champion)
        with self.assertRaisesRegex(RuntimeError, "active champion is quarantined"):
            self.registry.champion_prompt(Role.BUILDER)

    def test_quarantine_rejects_incomplete_provenance_without_side_effect(self) -> None:
        champion = self._bootstrap_builder()
        for actor, experiment_id, reasons in (
            ("", "EXP-x", ("reason",)),
            ("curator", " ", ("reason",)),
            ("curator", "EXP-x", ()),
            ("curator", "EXP-x", (" ",)),
            ("curator", "EXP-x", ("same", "same")),
        ):
            with self.assertRaises(ValueError):
                self.registry.quarantine(
                    Role.BUILDER,
                    champion,
                    actor=actor,
                    experiment_id=experiment_id,
                    reasons=reasons,
                )
        self.assertFalse(self.registry.is_quarantined(champion))
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), champion)


if __name__ == "__main__":
    unittest.main()
