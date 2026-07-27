import json
import tempfile
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
from hive_mind_os.receipts import FileReceiptValidator, ReceiptReference, sha256_digest


class ClassicGptSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = ClassicGptSourcePack()
        self.directory = tempfile.TemporaryDirectory()
        self.receipt_root = Path(self.directory.name)
        self.validator = FileReceiptValidator(self.receipt_root)
        self.gate = ClassicGptSimulationGate(self.pack, self.validator)

    def tearDown(self) -> None:
        self.directory.cleanup()

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

    def receipt_for(
        self,
        action: SimulatedAction,
        *,
        result: str = "succeeded",
        receipt_id: str = "receipt-1",
        **overrides,
    ) -> ReceiptReference:
        artifact_path = self.receipt_root / f"{action.id}.artifact"
        artifact_path.write_text("observed external state", encoding="utf-8")
        document = {
            "schema_version": 1,
            "receipt_id": receipt_id,
            "provider": "test-enforcement-point",
            "execution_id": f"execution-{action.id}",
            "mission_id": "mission-1",
            "state_ref": "MISSION_STATE:v1",
            "actor_id": action.actor_id,
            "policy_decision_ref": "policy:allow:test",
            "lease_id": "lease:test",
            "action_id": action.id,
            "action_kind": action.kind.value,
            "action_digest": action.digest,
            "executed": True,
            "result": result,
            "observed_at": "2026-07-27T12:00:00Z",
            "verified_by": "curator-pass-1",
            "artifacts": [
                {
                    "path": artifact_path.name,
                    "digest": sha256_digest(artifact_path.read_bytes()),
                }
            ],
        }
        document.update(overrides)
        receipt_path = self.receipt_root / f"{receipt_id}.json"
        receipt_path.write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        return ReceiptReference(
            receipt_path.name,
            sha256_digest(receipt_path.read_bytes()),
        )

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
                    "builder-pass-1",
                ),
            ),
        )
        decision = self.gate.evaluate(turn)
        self.assertFalse(decision.compliant)
        self.assertTrue(any("lacks an external tool receipt" in reason for reason in decision.reasons))

    def test_receipted_side_effect_is_allowed(self) -> None:
        proposed = SimulatedAction(
            "action-1",
            ActionKind.GIT,
            "Commit and push the generated patch.",
            "builder-pass-1",
        )
        receipted = SimulatedAction(
            proposed.id,
            proposed.kind,
            proposed.description,
            proposed.actor_id,
            receipt_ref=self.receipt_for(proposed),
        )
        turn = self.turn(
            phase=SimulationPhase.BUILD,
            active_role=Role.BUILDER,
            actor_id="builder-pass-1",
            actions=(receipted,),
        )
        self.assertTrue(self.gate.evaluate(turn).compliant)

    def test_legacy_receipt_string_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            SimulatedAction(
                "action-1",
                ActionKind.GIT,
                "Commit and push the generated patch.",
                "builder-pass-1",
                receipt_ref="github:commit:not-real",  # type: ignore[arg-type]
            )

    def test_receipt_cannot_be_reused_for_another_action(self) -> None:
        first = SimulatedAction(
            "action-1",
            ActionKind.WRITE,
            "Write the artifact.",
            "builder-pass-1",
        )
        reference = self.receipt_for(first)
        turn = self.turn(
            phase=SimulationPhase.BUILD,
            active_role=Role.BUILDER,
            actor_id="builder-pass-1",
            actions=(
                SimulatedAction(
                    first.id,
                    first.kind,
                    first.description,
                    first.actor_id,
                    reference,
                ),
                SimulatedAction(
                    "action-2",
                    ActionKind.WRITE,
                    "Write it again.",
                    "builder-pass-1",
                    reference,
                ),
            ),
        )
        decision = self.gate.evaluate(turn)
        self.assertFalse(decision.compliant)
        self.assertTrue(any("reuses another action receipt" in reason for reason in decision.reasons))

    def test_failed_receipt_cannot_support_completion(self) -> None:
        proposed = SimulatedAction(
            "action-1",
            ActionKind.COMMAND,
            "Run a command.",
            "builder-pass-1",
        )
        action = SimulatedAction(
            proposed.id,
            proposed.kind,
            proposed.description,
            proposed.actor_id,
            self.receipt_for(proposed, result="failed"),
        )
        build_decision = self.gate.evaluate(
            self.turn(
                phase=SimulationPhase.BUILD,
                active_role=Role.BUILDER,
                actor_id="builder-pass-1",
                actions=(action,),
            )
        )
        self.assertTrue(build_decision.compliant, build_decision.reasons)

        complete_decision = self.gate.evaluate(
            self.turn(
                phase=SimulationPhase.COMPLETE,
                active_role=Role.ORCHESTRATOR,
                actor_id="orchestrator-pass-2",
                actions=(action,),
                completed_roles=tuple(Role),
                verifier_ids=("curator-independent-1",),
                blockers=(),
                next_action="Archive the handoff.",
            )
        )
        self.assertFalse(complete_decision.compliant)
        self.assertTrue(
            any("lacks a successful receipt" in reason for reason in complete_decision.reasons)
        )

    def test_side_effect_receipt_fails_closed_without_validator(self) -> None:
        proposed = SimulatedAction(
            "action-1",
            ActionKind.WRITE,
            "Write the artifact.",
            "builder-pass-1",
        )
        action = SimulatedAction(
            proposed.id,
            proposed.kind,
            proposed.description,
            proposed.actor_id,
            self.receipt_for(proposed),
        )
        decision = ClassicGptSimulationGate(self.pack).evaluate(
            self.turn(actions=(action,))
        )
        self.assertFalse(decision.compliant)
        self.assertTrue(any("no independent validator" in reason for reason in decision.reasons))

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
