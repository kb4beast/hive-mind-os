"""Executable admission/recovery specifications. Auth keys are test fixtures only."""
from __future__ import annotations

import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.brain_kernel.canonical import canonical_bytes
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import (
    PromptRegistry, PromotionAdmissionError, PromotionCommittedEvidencePending,
    RejectionPersistenceError, generation_zero_prompt,
)
from hive_mind_os.roles import ROLE_CONTRACTS
from promotion_auth_fixtures import verifier_for
from promotion_fixtures import decision_payload


class PromptPromotionAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.verifier = verifier_for()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.registry.close)
        self.parent = self.registry.register(
            Role.BUILDER, generation_zero_prompt(ROLE_CONTRACTS[Role.BUILDER]),
            parent_digest=None, created_by="repository:generation-0",
        )
        self.registry.promote(Role.BUILDER, self.parent, promoted_by="repository:generation-0",
                              experiment_id="generation-0", expected_current=None)

    def candidate(self, experiment="EXP-bound", parent=None):
        parent = self.parent if parent is None else parent
        digest = self.registry.register(Role.BUILDER, "prompt " + experiment,
                                        parent_digest=parent, created_by="author:test",
                                        experiment_id=experiment)
        payload = decision_payload(self.root, candidate_digest=digest, parent=parent,
                                   experiment_id=experiment)
        return digest, payload

    def publish(self, payload):
        return self.registry.ledger.append_event(payload["registration_experiment_id"],
                                                "experiment.decision", payload["judge_id"], payload)

    def promote(self, digest, payload):
        return self.registry.promote(Role.BUILDER, digest, promoted_by="promoter:test",
                                     experiment_id=payload["registration_experiment_id"],
                                     expected_current=payload["current_digest"],
                                     decision_event_sequence=self.publish(payload))

    def rejection(self):
        return [event["payload"] for event in self.registry.ledger.events()
                if event["event_type"] == "prompt.promotion_rejected"][-1]

    def test_keep_co_commits_binding_record_and_principal_nonces(self):
        digest, payload = self.candidate()
        self.assertEqual(self.promote(digest, payload), self.parent)
        pointer = json.loads(self.registry.pointer_path.read_text())
        binding = pointer["promotion_bindings"]["builder"]
        self.assertEqual(pointer["schema_version"], 2)
        self.assertEqual(pointer["consumed_evaluations"][payload["evaluation_record"]["record_digest"]], binding)
        self.assertEqual(set(pointer["consumed_nonces"].values()), {binding})
        self.assertEqual(len(pointer["consumed_nonces"]), 4)
        # Serving uses committed history, not unused evidence or current-parent admission.
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), digest)
        self.registry.close()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.registry.close)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), digest)

    def test_missing_evidence_is_durable_authenticated_rejection(self):
        digest, payload = self.candidate()
        payload.pop("evaluation_record")
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaisesRegex(PromotionAdmissionError, "exact evaluation"):
            self.promote(digest, payload)
        self.assertEqual(self.registry.pointer_path.read_bytes(), before)
        receipt = self.rejection()
        self.assertEqual(receipt["code"], "evaluation-missing")
        self.assertTrue(receipt["pointer_unchanged"])
        self.verifier.verify_rejection_receipt(receipt["authentication"])

    def test_absent_trust_disables_new_keep(self):
        digest, payload = self.candidate()
        self.registry.principal_verifier = None
        with self.assertRaisesRegex(PromotionAdmissionError, "trusted principal"):
            self.promote(digest, payload)
        self.assertEqual(self.rejection()["code"], "authority-unconfigured")
        self.assertEqual(self.rejection()["authentication_status"], "unconfigured")
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.parent)

    def test_subject_substitution_is_rejected_before_pointer_commit(self):
        digest, payload = self.candidate()
        payload["evaluation_subject"]["artifact_digest"] = self.parent
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaises((ValueError, RuntimeError)):
            self.promote(digest, payload)
        self.assertEqual(self.registry.pointer_path.read_bytes(), before)
        self.assertTrue(self.rejection()["pointer_unchanged"])

    def test_record_replay_after_rollback_and_restart_is_refused(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        self.registry.rollback_champion(Role.BUILDER, self.parent, actor="steward:test", reason="regression")
        before = self.registry.pointer_path.read_bytes()
        self.registry.close()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.registry.close)
        with self.assertRaisesRegex(PromotionAdmissionError, "already consumed"):
            self.promote(digest, payload)
        self.assertEqual(self.registry.pointer_path.read_bytes(), before)
        self.assertEqual(self.rejection()["code"], "evaluation-replayed")

    def test_nonce_reuse_with_another_record_is_refused(self):
        first, original = self.candidate("EXP-first")
        self.promote(first, original)
        self.registry.rollback_champion(Role.BUILDER, self.parent, actor="steward:test", reason="regression")
        digest, payload = self.candidate("EXP-second")
        attestation = payload["authorization"]["attestations"][0]
        attestation["nonce"] = original["authorization"]["attestations"][0]["nonce"]
        unsigned = {key: value for key, value in attestation.items() if key != "signature"}
        attestation["signature"] = base64.b64encode(
            self.verifier.test_only_backend.sign(attestation["principal_id"], canonical_bytes(unsigned))
        ).decode("ascii")
        with self.assertRaisesRegex(PromotionAdmissionError, "nonce was already consumed"):
            self.promote(digest, payload)
        self.assertEqual(self.rejection()["code"], "authorization-replayed")

    def test_manifest_failure_preserves_pointer_and_consumption(self):
        digest, payload = self.candidate()
        before = self.registry.pointer_path.read_bytes()
        with patch.object(self.registry, "_persist_manifest", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.promote(digest, payload)
        self.assertEqual(self.registry.pointer_path.read_bytes(), before)
        self.assertTrue(self.rejection()["pointer_unchanged"])

    def test_postcommit_failure_is_pending_and_recovery_is_idempotent(self):
        digest, payload = self.candidate()
        with patch.object(self.registry, "_observe_promotion", side_effect=OSError("observation unavailable")):
            with self.assertRaises(PromotionCommittedEvidencePending) as raised:
                self.promote(digest, payload)
        admission = raised.exception.admission_digest
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), digest)
        before = self.registry.pointer_path.read_bytes()
        self.registry.recover_promotion_observation(admission, actor="steward:test")
        self.registry.recover_promotion_observation(admission, actor="steward:test")
        self.assertEqual(self.registry.pointer_path.read_bytes(), before)
        matching = [event for event in self.registry.ledger.events()
                    if event["event_type"] == "prompt.promoted"
                    and event["payload"].get("admission_digest") == admission]
        self.assertEqual(len(matching), 1)
        self.assertFalse(any(event["event_type"] == "prompt.promotion_rejected"
                             for event in self.registry.ledger.events()))

    def test_old_admission_observation_recovers_after_later_promotion(self):
        first, payload = self.candidate("EXP-first")
        with patch.object(self.registry, "_observe_promotion", side_effect=OSError("pending")):
            with self.assertRaises(PromotionCommittedEvidencePending) as raised:
                self.promote(first, payload)
        second, later = self.candidate("EXP-second", first)
        self.promote(second, later)
        before = self.registry.pointer_path.read_bytes()
        self.registry.recover_promotion_observation(raised.exception.admission_digest, actor="steward:test")
        self.assertEqual(self.registry.pointer_path.read_bytes(), before)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), second)

    def test_abandoned_preparation_is_not_activation_evidence(self):
        digest, payload = self.candidate()
        original = self.registry._atomic_json
        def fail_pointer(path, document):
            if path == self.registry.pointer_path:
                raise OSError("replace refused")
            original(path, document)
        with patch.object(self.registry, "_atomic_json", side_effect=fail_pointer):
            with self.assertRaises(OSError):
                self.promote(digest, payload)
        self.assertEqual(self.registry.champion_digest(Role.BUILDER), self.parent)
        admission = next(self.registry.admission_root.glob("*.json")).stem
        with self.assertRaisesRegex(PromotionAdmissionError, "no committed consumption"):
            self.registry.recover_promotion_observation("sha256:" + admission, actor="steward:test")

    def test_unknown_pointer_state_is_durable_service_blocker(self):
        digest, payload = self.candidate()
        original = self.registry._atomic_json
        def ambiguous(path, document):
            if path == self.registry.pointer_path:
                changed = copy.deepcopy(document)
                changed["champions"]["builder"] = self.parent
                original(path, changed)
                raise OSError("ambiguous replace")
            original(path, document)
        with patch.object(self.registry, "_atomic_json", side_effect=ambiguous):
            with self.assertRaisesRegex(PromotionAdmissionError, "unknown"):
                self.promote(digest, payload)
        self.assertTrue(self.registry.unknown_commit_path.exists())
        self.registry.close()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.registry.close)
        with self.assertRaisesRegex(PromotionAdmissionError, "unresolved"):
            self.registry.champion_digest(Role.BUILDER)

    def test_rejection_signing_failure_does_not_claim_receipt_persistence(self):
        digest, payload = self.candidate()
        payload.pop("evaluation_record")
        before = self.registry.pointer_path.read_bytes()
        with patch.object(self.verifier, "sign_rejection", side_effect=RuntimeError("signer unavailable")):
            with self.assertRaises(RejectionPersistenceError) as raised:
                self.promote(digest, payload)
        self.assertEqual(raised.exception.code, "rejection-persistence-failed")
        self.assertEqual(self.registry.pointer_path.read_bytes(), before)
