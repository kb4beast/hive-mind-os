"""Executable admission/recovery specifications. Auth keys are test fixtures only."""
from __future__ import annotations

import base64
import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from promotion_auth_fixtures import authorize, verifier_for
from promotion_fixtures import (
    authenticated_rollback,
    bound_decision,
    decision_payload,
    rollback_payload,
)

from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.promotion import PromotionAuthority, PromotionCandidate
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import (
    PromotionAdmissionError,
    PromotionCommittedEvidencePending,
    PromptRegistry,
    RejectionPersistenceError,
    generation_zero_prompt,
)
from hive_mind_os.recursive_improvement import ExperimentVerdict
from hive_mind_os.roles import ROLE_CONTRACTS


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

    def adverse(self, verdict, experiment="EXP-adverse"):
        digest, original = self.candidate(experiment)
        subject = original["evaluation_subject"]
        candidate = PromotionCandidate(subject["candidate_id"], subject["role"], subject["experiment_id"],
                                       digest, subject["parent_champion_digest"], subject["proposer_id"],
                                       subject["builder_id"], tuple(subject["evidence_refs"]))
        decision = bound_decision(candidate, verdict, "case:" + experiment, "decision:" + experiment,
                                  judge="judge:test", evaluator="evaluator:test", promoter="promoter:test")
        return digest, PromotionAuthority.decision_payload(decision)

    def apply_adverse(self, payload):
        return self.registry.apply_adverse_decision("builder", actor=payload["promoter_id"],
                                                    experiment_id=payload["registration_experiment_id"],
                                                    decision_event_sequence=self.publish(payload))

    def rollback(self, payload, **overrides):
        arguments = {"actor": payload["promoter_id"], "reason": "; ".join(payload["reasons"]),
                     "expected_current": payload["candidate_digest"],
                     "experiment_id": payload["registration_experiment_id"],
                     "decision_event_sequence": self.publish(payload)}
        arguments.update(overrides)
        return self.registry.rollback_champion("builder", payload["current_digest"], **arguments)

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
        authenticated_rollback(self.registry, self.parent)
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
        authenticated_rollback(self.registry, self.parent)
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
        admission = next(path.stem for path in self.registry.admission_root.glob("*.json")
                         if json.loads(path.read_bytes())["kind"] == "prompt-promotion-admission")
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
        unavailable = [item for item in self.registry.events() if item["kind"] == "promotion-rejection-unavailable"]
        self.assertEqual(unavailable[-1]["authentication_status"], "unavailable")
        self.assertNotIn("authentication", unavailable[-1])

    def test_all_non_keep_actions_authenticate_and_consume_durably(self):
        for verdict in (ExperimentVerdict.RETEST, ExperimentVerdict.DISCARD, ExperimentVerdict.QUARANTINE,
                        ExperimentVerdict.STOP):
            with self.subTest(verdict=verdict):
                digest, payload = self.adverse(verdict, "EXP-" + verdict.value)
                self.assertEqual(self.apply_adverse(payload), self.parent)
                self.assertEqual(self.registry.champion_digest("builder"), self.parent)
                self.assertEqual(self.registry.is_quarantined(digest), verdict is ExperimentVerdict.QUARANTINE)
                pointers = self.registry._read_pointers()
                self.assertIn(payload["evaluation_record"]["record_digest"], pointers["consumed_evaluations"])
                before = self.registry.pointer_path.read_bytes()
                with self.assertRaisesRegex(PromotionAdmissionError, "already consumed"):
                    self.apply_adverse(payload)
                self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_stop_validates_retained_outcome_and_requires_its_own_signatures(self):
        for verdict in (ExperimentVerdict.KEEP, ExperimentVerdict.RETEST, ExperimentVerdict.DISCARD,
                        ExperimentVerdict.QUARANTINE):
            with self.subTest(verdict=verdict):
                digest, payload = self.adverse(verdict, "EXP-stop-" + verdict.value)
                record_path = Path(payload["evaluation_record"]["record_path"])
                record_bytes = record_path.read_bytes()
                payload["verdict"] = "stop"
                before = self.registry.pointer_path.read_bytes()
                with self.assertRaisesRegex(RuntimeError, "another decision"):
                    self.apply_adverse(payload)
                self.assertEqual(before, self.registry.pointer_path.read_bytes())
                payload["authorization"] = None
                with self.assertRaises(RuntimeError):
                    self.apply_adverse(payload)
                self.assertEqual(before, self.registry.pointer_path.read_bytes())
                payload["authorization"] = authorize(payload, self.verifier)
                self.assertEqual(self.apply_adverse(payload), self.parent)
                self.assertFalse(self.registry.is_quarantined(digest))
                self.assertEqual(record_path.read_bytes(), record_bytes)
                self.assertEqual(json.loads(record_bytes)["verdict"], verdict.value)
                self.assertEqual(self.registry.champion_digest("builder"), self.parent)

    def test_stop_recovery_and_replay_after_restart(self):
        _, payload = self.adverse(ExperimentVerdict.STOP)
        with patch.object(self.registry, "_observe_adverse", side_effect=OSError("stop observation unavailable")):
            with self.assertRaises(PromotionCommittedEvidencePending) as caught:
                self.apply_adverse(payload)
        before = self.registry.pointer_path.read_bytes()
        self.registry.close()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.registry.close)
        admission = caught.exception.admission_digest
        self.registry.recover_promotion_observation(admission, actor="steward:test")
        self.registry.recover_promotion_observation(admission, actor="steward:test")
        with self.assertRaisesRegex(PromotionAdmissionError, "already consumed"):
            self.apply_adverse(payload)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())
        observations = [item for item in self.registry.ledger.events()
                        if item["event_type"] == "prompt.adverse_decision"
                        and item["payload"].get("admission_digest") == admission]
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["payload"]["verdict"], "stop")

    def test_stop_still_recomputes_rehashed_evaluation_metrics(self):
        _, payload = self.adverse(ExperimentVerdict.STOP)
        reference = payload["evaluation_record"]
        path = Path(reference["record_path"])
        document = json.loads(path.read_bytes())
        document["primary_effect"] = 0.99
        document.pop("evaluation_id")
        document["evaluation_id"] = "EVAL-" + canonical_digest(document)[7:23]
        path.write_bytes(canonical_bytes(document) + b"\n")
        reference.update(evaluation_id=document["evaluation_id"], record_digest=canonical_digest(document))
        payload["authorization"] = authorize(payload, self.verifier)
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "retained scores or selection differ"):
            self.apply_adverse(payload)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_stop_cannot_replace_rollback_authorization(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        adverse = rollback_payload(self.registry, self.parent)
        adverse["verdict"] = "stop"
        adverse["authorization"] = authorize(adverse, self.verifier)
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaises(PromotionAdmissionError):
            self.rollback(adverse)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_unsigned_non_keep_cannot_quarantine_and_rejection_is_signed(self):
        digest, payload = self.adverse(ExperimentVerdict.QUARANTINE)
        payload["authorization"] = None
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaises(RuntimeError):
            self.apply_adverse(payload)
        self.assertFalse(self.registry.is_quarantined(digest))
        self.assertEqual(before, self.registry.pointer_path.read_bytes())
        receipt = self.rejection()
        signed = self.verifier.verify_rejection_receipt(receipt["authentication"])
        self.assertEqual(signed["actor"], "promoter:test")
        self.assertEqual(signed["experiment_id"], payload["registration_experiment_id"])

    def test_unsigned_rollback_and_keep_authorization_cannot_restore_parent(self):
        digest, keep = self.candidate()
        self.promote(digest, keep)
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaisesRegex(PromotionAdmissionError, "experiment.decision"):
            self.registry.rollback_champion("builder", self.parent, actor="steward:test", reason="regression")
        with self.assertRaises(PromotionAdmissionError):
            self.rollback(keep)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())
        self.verifier.verify_rejection_receipt(self.rejection()["authentication"])

    def test_rollback_binds_actor_reason_live_candidate_and_action(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        adverse = rollback_payload(self.registry, self.parent)
        before = self.registry.pointer_path.read_bytes()
        for overrides in ({"actor": "judge:test"}, {"reason": "substituted"}, {"expected_current": self.parent}):
            with self.subTest(overrides=overrides), self.assertRaises(RuntimeError):
                self.rollback(adverse, **overrides)
            self.assertEqual(before, self.registry.pointer_path.read_bytes())
        changed = copy.deepcopy(adverse)
        changed["action"] = "apply"
        with self.assertRaises(PromotionAdmissionError):
            self.rollback(changed)
        changed = copy.deepcopy(adverse)
        changed["reasons"] = ["forged reason"]
        with self.assertRaisesRegex(RuntimeError, "another decision"):
            self.rollback(changed)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_adverse_verdict_cannot_be_relabelled_even_with_new_signatures(self):
        _, payload = self.adverse(ExperimentVerdict.DISCARD)
        payload["verdict"] = "quarantine"
        payload["authorization"] = authorize(payload, self.verifier)
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "verdict is not QUARANTINE"):
            self.apply_adverse(payload)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_rollback_quarantine_commit_survives_failed_observation_and_restart(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        adverse = rollback_payload(self.registry, self.parent, verdict=ExperimentVerdict.QUARANTINE)
        with patch.object(self.registry, "_observe_adverse", side_effect=OSError("observation unavailable")):
            with self.assertRaises(PromotionCommittedEvidencePending) as caught:
                self.rollback(adverse)
        admission = caught.exception.admission_digest
        self.assertEqual(self.registry.champion_digest("builder"), self.parent)
        self.assertTrue(self.registry.is_quarantined(digest))
        before = self.registry.pointer_path.read_bytes()
        self.registry.close()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.registry.close)
        self.assertTrue(self.registry.is_quarantined(digest))
        self.registry.recover_promotion_observation(admission, actor="steward:test")
        self.registry.recover_promotion_observation(admission, actor="steward:test")
        self.assertEqual(before, self.registry.pointer_path.read_bytes())
        observations = [item for item in self.registry.ledger.events()
                        if item["event_type"] == "prompt.rollback" and item["payload"].get("admission_digest") == admission]
        self.assertEqual(len(observations), 1)

    def test_rollback_precommit_failure_does_not_consume_or_quarantine(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        adverse = rollback_payload(self.registry, self.parent, verdict=ExperimentVerdict.QUARANTINE)
        before = self.registry.pointer_path.read_bytes()
        with patch.object(self.registry, "_atomic_json", side_effect=OSError("replace refused")):
            with self.assertRaises(OSError):
                self.rollback(adverse)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())
        self.assertFalse(self.registry.is_quarantined(digest))
        self.assertTrue(self.rejection()["pointer_unchanged"])

    def test_rollback_replace_then_error_reports_committed_without_rejection(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        adverse = rollback_payload(self.registry, self.parent)
        original = self.registry._atomic_json
        def replace_then_error(path, document):
            original(path, document)
            raise OSError("after replace")
        with patch.object(self.registry, "_atomic_json", side_effect=replace_then_error):
            with self.assertRaises(PromotionCommittedEvidencePending) as caught:
                self.rollback(adverse)
        self.assertEqual(self.registry.champion_digest("builder"), self.parent)
        self.registry.recover_promotion_observation(caught.exception.admission_digest, actor="steward:test")
        self.assertFalse(any(item["event_type"] == "prompt.promotion_rejected" for item in self.registry.ledger.events()))

    def test_bootstrap_commit_observation_can_recover_after_restart(self):
        role = Role.CURATOR
        digest = self.registry.register(role, generation_zero_prompt(ROLE_CONTRACTS[role]),
                                        parent_digest=None, created_by="repository:generation-0")
        with patch.object(self.registry, "_observe_promotion", side_effect=OSError("bootstrap observation")):
            with self.assertRaises(PromotionCommittedEvidencePending) as caught:
                self.registry.promote(role, digest, promoted_by="repository:generation-0",
                                      experiment_id="generation-0", expected_current=None)
        before = self.registry.pointer_path.read_bytes()
        self.registry.close()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.registry.close)
        self.assertEqual(self.registry.champion_digest(role), digest)
        self.registry.recover_promotion_observation(caught.exception.admission_digest, actor="steward:test")
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_legacy_active_pointer_is_explicit_migration_obligation_without_rewrite(self):
        digest, _ = self.candidate("EXP-legacy")
        legacy = {"schema_version": 1, "champions": {"builder": digest}}
        self.registry._atomic_json(self.registry.pointer_path, legacy)
        before = self.registry.pointer_path.read_bytes()
        self.assertEqual(self.registry.migration_status()["roles"]["builder"], "migration-required")
        with self.assertRaisesRegex(PromotionAdmissionError, "explicit migration required"):
            self.registry.champion_digest("builder")
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_schema_downgrade_cannot_relabel_admission_state_as_legacy(self):
        pointers = self.registry._read_pointers()
        self.assertEqual(self.registry.migration_status()["downgrade"], "unsupported-preserve-admission-and-replay-state")
        pointers["schema_version"] = 1
        self.registry._atomic_json(self.registry.pointer_path, pointers)
        with self.assertRaisesRegex(PromotionAdmissionError, "legacy schema"):
            self.registry.champion_digest("builder")

    def test_prompt_noncanonical_bytes_fail_even_when_normalized_digest_matches(self):
        digest, payload = self.candidate()
        path = self.registry.artifact_path(digest)
        path.write_bytes(path.read_bytes() + b"\n")
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "artifact digest"):
            self.promote(digest, payload)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_relocated_record_with_fresh_nonces_remains_consumed(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        authenticated_rollback(self.registry, self.parent)
        original = Path(payload["evaluation_record"]["record_path"])
        moved = original.with_name("relocated.json")
        moved.write_bytes(original.read_bytes())
        payload["evaluation_record"]["record_path"] = str(moved)
        payload["authorization"] = authorize(payload, self.verifier)
        before = self.registry.pointer_path.read_bytes()
        with self.assertRaisesRegex(PromotionAdmissionError, "already consumed"):
            self.promote(digest, payload)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_candidate_mutation_during_preparation_fails_commit_recheck(self):
        digest, payload = self.candidate()
        before = self.registry.pointer_path.read_bytes()
        original = self.registry._persist_manifest
        def mutate_after_preparation(admission, manifest):
            original(admission, manifest)
            self.registry.artifact_path(digest).write_bytes(b"substituted prompt")
        with patch.object(self.registry, "_persist_manifest", side_effect=mutate_after_preparation):
            with self.assertRaisesRegex(PromotionAdmissionError, "registered prompt bytes"):
                self.promote(digest, payload)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_competing_writers_commit_only_one_evaluation(self):
        first, first_payload = self.candidate("EXP-race-first")
        second, second_payload = self.candidate("EXP-race-second")
        other = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(other.close)
        first_sequence = self.publish(first_payload)
        second_sequence = self.publish(second_payload)
        def attempt(registry, digest, payload, sequence):
            try:
                registry.promote("builder", digest, promoted_by="promoter:test",
                                 experiment_id=payload["registration_experiment_id"],
                                 expected_current=self.parent, decision_event_sequence=sequence)
                return "committed"
            except PromotionAdmissionError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt, self.registry, first, first_payload, first_sequence),
                       pool.submit(attempt, other, second, second_payload, second_sequence)]
            outcomes = [future.result() for future in futures]
        self.assertCountEqual(outcomes, ["committed", "parent-stale"])
        pointers = self.registry._read_pointers()
        self.assertEqual(len(pointers["consumed_evaluations"]), 1)
        self.assertEqual(len(pointers["consumed_nonces"]), 4)

    def test_non_keep_replay_is_refused_after_new_registry_instance(self):
        _, payload = self.adverse(ExperimentVerdict.RETEST)
        self.apply_adverse(payload)
        before = self.registry.pointer_path.read_bytes()
        other = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(other.close)
        with self.assertRaisesRegex(PromotionAdmissionError, "already consumed"):
            other.apply_adverse_decision("builder", actor="promoter:test",
                                         experiment_id=payload["registration_experiment_id"],
                                         decision_event_sequence=self.publish(payload))
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_old_rollback_observation_recovers_after_later_keep(self):
        first, payload = self.candidate("EXP-first")
        self.promote(first, payload)
        adverse = rollback_payload(self.registry, self.parent)
        with patch.object(self.registry, "_observe_adverse", side_effect=OSError("pending")):
            with self.assertRaises(PromotionCommittedEvidencePending) as caught:
                self.rollback(adverse)
        second, later = self.candidate("EXP-later")
        self.promote(second, later)
        before = self.registry.pointer_path.read_bytes()
        self.registry.recover_promotion_observation(caught.exception.admission_digest, actor="steward:test")
        self.assertEqual(self.registry.champion_digest("builder"), second)
        self.assertEqual(before, self.registry.pointer_path.read_bytes())

    def test_ambiguous_rollback_commit_blocks_service_after_restart(self):
        digest, payload = self.candidate()
        self.promote(digest, payload)
        adverse = rollback_payload(self.registry, self.parent)
        original = self.registry._atomic_json
        def ambiguous(path, document):
            changed = copy.deepcopy(document)
            changed["champions"]["builder"] = digest
            original(path, changed)
            raise OSError("ambiguous rollback replace")
        with patch.object(self.registry, "_atomic_json", side_effect=ambiguous):
            with self.assertRaisesRegex(PromotionAdmissionError, "unknown"):
                self.rollback(adverse)
        self.assertTrue(self.registry.unknown_commit_path.exists())
        self.registry.close()
        self.registry = PromptRegistry(self.root, principal_verifier=self.verifier)
        self.addCleanup(self.registry.close)
        with self.assertRaisesRegex(PromotionAdmissionError, "unresolved"):
            self.registry.champion_digest("builder")

    def test_adverse_admission_cannot_be_repurposed_as_champion_binding(self):
        digest, payload = self.adverse(ExperimentVerdict.RETEST)
        self.apply_adverse(payload)
        pointers = self.registry._read_pointers()
        adverse = pointers["consumed_evaluations"][payload["evaluation_record"]["record_digest"]]
        pointers["champions"]["builder"] = digest
        pointers["promotion_bindings"]["builder"] = adverse
        self.registry._atomic_json(self.registry.pointer_path, pointers)
        with self.assertRaisesRegex(PromotionAdmissionError, "resolving promotion"):
            self.registry.champion_digest("builder")
