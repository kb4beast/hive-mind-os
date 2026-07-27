import json
import unittest
from pathlib import Path

from hive_mind_os.classic_gpt import (
    ActionKind,
    ClassicGptSimulationGate,
    ClassicGptSourcePack,
    ClassicGptTurn,
    SimulatedAction,
    SimulationPhase,
)
from hive_mind_os.models import Role


class ClassicGptSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = ClassicGptSourcePack()
        self.gate = ClassicGptSimulationGate(self.pack)

    def turn(self, **overrides) -> ClassicGptTurn:
        values = dict(
            mission_id="mission-1",
            phase=SimulationPhase.DESIGN,
            active_role=Role.ARCHITECT,
            actor_id="architect-pass-1",
            state_ref="MISSION_STATE:v1",
            evidence_refs=("source:SRC-022",),
            next_action="Run the Builder pass against the accepted design.",
            confidence=0.8,
            source_pack_fingerprint=self.pack.fingerprint,
        )
        values.update(overrides)
        return ClassicGptTurn(**values)

    def test_source_pack_files_exist_and_pass_marker_audit(self) -> None:
        documents = {
            item.path: Path(item.path).read_text(encoding="utf-8")
            for item in self.pack.files
        }
        audit = self.pack.audit(documents)
        self.assertTrue(audit.valid, audit.issues)

        manifest = json.loads(documents["gpt_sources/manifest.json"])
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["load_order"],
            [item.path for item in self.pack.files if item.path != "gpt_sources/manifest.json"],
        )

    def test_missing_source_or_required_marker_fails_closed(self) -> None:
        documents = {item.path: "placeholder" for item in self.pack.files[:-1]}
        audit = self.pack.audit(documents)
        self.assertFalse(audit.valid)
        self.assertTrue(any("missing source file" in issue for issue in audit.issues))
        self.assertTrue(any("missing required marker" in issue for issue in audit.issues))

    def test_side_effect_remains_unverified_without_external_receipt(self) -> None:
        turn = self.turn(
            phase=SimulationPhase.BUILD,
            active_role=Role.BUILDER,
            actor_id="builder-pass-1",
            actions=(
                SimulatedAction(
                    "action-1",
                    ActionKind.GIT,
                    "Commit and push the generated patch.",
                ),
            ),
        )
        decision = self.gate.evaluate(turn)
        self.assertFalse(decision.compliant)
        self.assertTrue(any("lacks an external tool receipt" in reason for reason in decision.reasons))

    def test_receipted_side_effect_is_allowed(self) -> None:
        turn = self.turn(
            phase=SimulationPhase.BUILD,
            active_role=Role.BUILDER,
            actor_id="builder-pass-1",
            actions=(
                SimulatedAction(
                    "action-1",
                    ActionKind.GIT,
                    "Commit and push the generated patch.",
                    receipt_ref="github:commit:abc123",
                ),
            ),
        )
        self.assertTrue(self.gate.evaluate(turn).compliant)

    def test_actor_cannot_verify_its_own_work(self) -> None:
        decision = self.gate.evaluate(self.turn(verifier_ids=("architect-pass-1",)))
        self.assertFalse(decision.compliant)
        self.assertIn("acting identity attempted to verify its own work", decision.reasons)

    def test_completion_requires_every_role_verifier_and_resolved_blockers(self) -> None:
        incomplete = self.turn(
            phase=SimulationPhase.COMPLETE,
            completed_roles=(Role.ORCHESTRATOR, Role.EXPLORER),
            verifier_ids=(),
            blockers=("security review pending",),
            next_action="Resolve the remaining blocker.",
        )
        decision = self.gate.evaluate(incomplete)
        self.assertFalse(decision.compliant)
        self.assertTrue(any("missing role passes" in reason for reason in decision.reasons))
        self.assertIn("completion lacks independent verification", decision.reasons)
        self.assertIn("completion declared while blockers remain", decision.reasons)

        complete = self.turn(
            phase=SimulationPhase.COMPLETE,
            active_role=Role.ORCHESTRATOR,
            actor_id="orchestrator-pass-2",
            completed_roles=tuple(Role),
            verifier_ids=("curator-independent-1",),
            blockers=(),
            next_action="Archive the final handoff packet and observe outcomes.",
        )
        self.assertTrue(self.gate.evaluate(complete).compliant)

    def test_state_and_next_action_are_mandatory(self) -> None:
        with self.assertRaises(ValueError):
            self.turn(state_ref="")
        with self.assertRaises(ValueError):
            self.turn(next_action="")


if __name__ == "__main__":
    unittest.main()
