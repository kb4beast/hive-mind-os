import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.models import Role
from hive_mind_os.receipts import FileReceiptValidator, ReceiptReference, sha256_digest
from hive_mind_os.reference.classic_gpt import (
    ActionKind,
    ClassicGptSimulationGate,
    ClassicGptSourcePack,
    ClassicGptTurn,
    SimulatedAction,
    SimulationPhase,
)


class ClassicGptSimulationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).resolve().parents[1]
        self.pack = ClassicGptSourcePack.load(self.repository)
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
            item.path: (self.repository / item.path).read_bytes()
            for item in self.pack.files
        }
        audit = self.pack.audit(documents)
        self.assertTrue(audit.valid, audit.issues)

        manifest = json.loads(documents["gpt_sources/manifest.json"])
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(manifest["pack_id"], "hive-mind-os-classic-gpt-simulation-v3")
        self.assertEqual(
            manifest["load_order"],
            [item.path for item in self.pack.files if item.path != "gpt_sources/manifest.json"],
        )
        runtime_state = json.loads(documents["gpt_sources/01_RUNTIME_STATE_SCHEMA.json"])
        self.assertEqual(runtime_state["schema_version"], 3)
        action = runtime_state["proposed_actions"][0]
        self.assertIn("actor_id", action)
        self.assertIn("action_digest", action)
        receipt = runtime_state["tool_receipts"][0]
        for field in (
            "schema_version",
            "execution_id",
            "mission_id",
            "state_ref",
            "actor_id",
            "policy_decision_ref",
            "lease_id",
            "action_digest",
            "executed",
            "result",
            "artifacts",
            "verified_by",
        ):
            self.assertIn(field, receipt)

        proposed = SimulatedAction(
            id=action["action_id"],
            kind=ActionKind(action["kind"]),
            description=action["description"] or "Documented action",
            actor_id=action["actor_id"],
        )
        artifact_path = self.receipt_root / "artifacts" / "ART-000.bin"
        artifact_path.parent.mkdir()
        artifact_path.write_bytes(b"observed example artifact")
        receipt_document = dict(receipt)
        receipt_document.update(
            {
                "provider": "example-provider",
                "mission_id": runtime_state["mission"]["id"],
                "state_ref": runtime_state["handoff"]["state_ref"],
                "actor_id": proposed.actor_id,
                "action_id": proposed.id,
                "action_kind": proposed.kind.value,
                "action_digest": proposed.digest,
                "artifacts": [
                    {
                        "path": "artifacts/ART-000.bin",
                        "digest": sha256_digest(artifact_path.read_bytes()),
                    }
                ],
                "verified_by": "curator-pass-1",
            }
        )
        receipt_path = self.receipt_root / "receipts" / "REC-000.json"
        receipt_path.parent.mkdir()
        receipt_path.write_text(
            json.dumps(receipt_document, sort_keys=True),
            encoding="utf-8",
        )
        validation = self.validator.validate(
            ReceiptReference(
                "receipts/REC-000.json",
                sha256_digest(receipt_path.read_bytes()),
            ),
            mission_id=runtime_state["mission"]["id"],
            state_ref=runtime_state["handoff"]["state_ref"],
            actor_id=proposed.actor_id,
            action_id=proposed.id,
            action_kind=proposed.kind.value,
            action_digest=proposed.digest,
        )
        self.assertTrue(validation.valid, validation.issues)
        self.assertTrue(validation.succeeded)

    def test_byte_inventory_fails_on_add_remove_substitute_and_reorder(self) -> None:
        documents = {
            item.path: (self.repository / item.path).read_bytes()
            for item in self.pack.files
        }
        removed = dict(documents)
        removed.pop(self.pack.records[0].path)
        self.assertFalse(self.pack.audit(removed).valid)

        added = dict(documents)
        added["gpt_sources/uninventoried.md"] = b"extra"
        self.assertFalse(self.pack.audit(added).valid)

        substituted = dict(documents)
        substituted[self.pack.records[0].path] += b"\nsubstitution"
        self.assertFalse(self.pack.audit(substituted).valid)

        manifest = json.loads(documents["gpt_sources/manifest.json"])
        manifest["load_order"] = list(reversed(manifest["load_order"]))
        invalid_manifest = json.dumps(manifest).encode()
        reordered = dict(documents)
        reordered["gpt_sources/manifest.json"] = invalid_manifest
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "gpt_sources").mkdir()
            for path, content in reordered.items():
                (root / path).write_bytes(content)
            with self.assertRaisesRegex(ValueError, "load_order"):
                ClassicGptSourcePack.load(root)

    def test_manifest_schema_incompatibility_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "gpt_sources").mkdir()
            for item in self.pack.files:
                (root / item.path).write_bytes((self.repository / item.path).read_bytes())
            manifest_path = root / "gpt_sources" / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["schema_version"] = 4
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                ClassicGptSourcePack.load(root)

    def test_manifest_semantics_and_unknown_fields_are_fingerprint_bound(self) -> None:
        baseline_fingerprint = self.pack.fingerprint
        for field, value, expected in (
            ("invented_authority", True, "invalid shape"),
            ("authority_model", "unbounded execution", "not authorized"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copytree(self.repository / "gpt_sources", root / "gpt_sources")
                manifest_path = root / "gpt_sources" / "manifest.json"
                manifest = json.loads(manifest_path.read_text())
                manifest[field] = value
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected):
                    ClassicGptSourcePack.load(root)
        self.assertEqual(self.pack.fingerprint, baseline_fingerprint)

    def test_manifest_matches_lf_bytes_used_by_clean_checkouts(self) -> None:
        manifest = json.loads(
            (self.repository / "gpt_sources" / "manifest.json").read_text()
        )
        for record in manifest["files"]:
            content = (self.repository / record["path"]).read_bytes()
            self.assertNotIn(b"\r\n", content, record["path"])
            self.assertEqual(len(content), record["bytes"])

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
                    id="action-1",
                    kind=ActionKind.GIT,
                    description="Commit and push the generated patch.",
                    actor_id="builder-pass-1",
                ),
            ),
        )
        decision = self.gate.evaluate(turn)
        self.assertFalse(decision.compliant)
        self.assertTrue(any("lacks an external tool receipt" in reason for reason in decision.reasons))

    def test_receipted_side_effect_is_allowed(self) -> None:
        proposed = SimulatedAction(
            id="action-1",
            kind=ActionKind.GIT,
            description="Commit and push the generated patch.",
            actor_id="builder-pass-1",
        )
        receipted = SimulatedAction(
            id=proposed.id,
            kind=proposed.kind,
            description=proposed.description,
            actor_id=proposed.actor_id,
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
                id="action-1",
                kind=ActionKind.GIT,
                description="Commit and push the generated patch.",
                actor_id="builder-pass-1",
                receipt_ref="github:commit:not-real",  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            SimulatedAction(  # type: ignore[misc]
                "action-1",
                ActionKind.GIT,
                "Commit and push the generated patch.",
                "github:commit:not-real",
            )

    def test_receipt_cannot_be_reused_for_another_action(self) -> None:
        first = SimulatedAction(
            id="action-1",
            kind=ActionKind.WRITE,
            description="Write the artifact.",
            actor_id="builder-pass-1",
        )
        reference = self.receipt_for(first)
        turn = self.turn(
            phase=SimulationPhase.BUILD,
            active_role=Role.BUILDER,
            actor_id="builder-pass-1",
            actions=(
                SimulatedAction(
                    id=first.id,
                    kind=first.kind,
                    description=first.description,
                    actor_id=first.actor_id,
                    receipt_ref=reference,
                ),
                SimulatedAction(
                    id="action-2",
                    kind=ActionKind.WRITE,
                    description="Write it again.",
                    actor_id="builder-pass-1",
                    receipt_ref=reference,
                ),
            ),
        )
        decision = self.gate.evaluate(turn)
        self.assertFalse(decision.compliant)
        self.assertTrue(any("reuses another action receipt" in reason for reason in decision.reasons))

    def test_duplicate_action_ids_cannot_mask_a_failed_side_effect(self) -> None:
        failed = SimulatedAction(
            id="action-1",
            kind=ActionKind.COMMAND,
            description="First execution fails.",
            actor_id="builder-pass-1",
        )
        succeeded = SimulatedAction(
            id="action-1",
            kind=ActionKind.WRITE,
            description="Different execution succeeds.",
            actor_id="builder-pass-1",
        )
        actions = (
            SimulatedAction(
                id=failed.id,
                kind=failed.kind,
                description=failed.description,
                actor_id=failed.actor_id,
                receipt_ref=self.receipt_for(
                    failed,
                    result="failed",
                    receipt_id="receipt-failed",
                ),
            ),
            SimulatedAction(
                id=succeeded.id,
                kind=succeeded.kind,
                description=succeeded.description,
                actor_id=succeeded.actor_id,
                receipt_ref=self.receipt_for(
                    succeeded,
                    result="succeeded",
                    receipt_id="receipt-succeeded",
                ),
            ),
        )
        decision = self.gate.evaluate(
            self.turn(
                phase=SimulationPhase.COMPLETE,
                active_role=Role.ORCHESTRATOR,
                actor_id="orchestrator-pass-2",
                actions=actions,
                completed_roles=tuple(Role),
                verifier_ids=("curator-independent-1",),
                blockers=(),
                next_action="Archive the handoff.",
            )
        )
        self.assertFalse(decision.compliant)
        self.assertIn("turn contains duplicate action ids: action-1", decision.reasons)
        self.assertTrue(any("lacks a successful receipt" in reason for reason in decision.reasons))

    def test_failed_receipt_cannot_support_completion(self) -> None:
        proposed = SimulatedAction(
            id="action-1",
            kind=ActionKind.COMMAND,
            description="Run a command.",
            actor_id="builder-pass-1",
        )
        action = SimulatedAction(
            id=proposed.id,
            kind=proposed.kind,
            description=proposed.description,
            actor_id=proposed.actor_id,
            receipt_ref=self.receipt_for(proposed, result="failed"),
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
            id="action-1",
            kind=ActionKind.WRITE,
            description="Write the artifact.",
            actor_id="builder-pass-1",
        )
        action = SimulatedAction(
            id=proposed.id,
            kind=proposed.kind,
            description=proposed.description,
            actor_id=proposed.actor_id,
            receipt_ref=self.receipt_for(proposed),
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

    def test_runtime_enum_type_confusion_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            self.turn(phase="complete")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            self.turn(active_role="architect")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            self.turn(completed_roles=("builder",))  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            SimulatedAction(
                id="action-1",
                kind="git",  # type: ignore[arg-type]
                description="Do work.",
                actor_id="builder-pass-1",
            )


if __name__ == "__main__":
    unittest.main()
