"""Authentication contract tests using public TEST-ONLY HMAC fixture keys.

These tests do not establish real independently administered principals. Durable
nonce consumption and rejection persistence belong to registry integration.
"""

from __future__ import annotations

import base64
import copy
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.promotion_auth import (
    PromotionAuthenticationError,
    PromotionAuthorization,
    PromotionPrincipalVerifier,
)
from tests.promotion_auth_fixtures import authorize, verifier_for


class PromotionAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
        self.verifier = verifier_for()
        self.payload = {
            "evaluation_subject": {
                "schema_version": 1,
                "candidate_id": "candidate:test",
                "artifact_digest": canonical_digest("candidate bytes"),
                "parent_champion_digest": canonical_digest("parent bytes"),
            },
            "evaluation_record": {
                "schema_version": 1,
                "evaluation_id": "EVAL-test-reference",
                "record_path": "C:/test-only/record.json",
                "record_digest": canonical_digest("retained evaluation"),
            },
            "builder_id": "builder:test",
            "evaluator_id": "evaluator:test",
            "judge_id": "judge:test",
            "promoter_id": "promoter:test",
            "decision_id": "decision:test",
            "verdict": "keep",
        }
        self.authorization = authorize(self.payload, self.verifier, now=self.now)

    def verify(self, authorization=None, *, payload=None, verifier=None, now=None):
        given = self.payload if payload is None else payload
        return (self.verifier if verifier is None else verifier).verify_authorization(
            self.authorization if authorization is None else authorization,
            subject_digest=canonical_digest(given["evaluation_subject"]),
            record_digest=given["evaluation_record"]["record_digest"],
            builder_id=given["builder_id"], evaluator_id=given["evaluator_id"],
            judge_id=given["judge_id"], promoter_id=given["promoter_id"],
            decision_digest=canonical_digest({
                key: value for key, value in given.items() if key != "authorization"
            }),
            now=self.now if now is None else now,
        )

    def assert_code(self, code, function):
        with self.assertRaises(PromotionAuthenticationError) as caught:
            function()
        self.assertEqual(code, caught.exception.code)

    def resign(self, document, index):
        attestation = document["attestations"][index]
        unsigned = {key: value for key, value in attestation.items() if key != "signature"}
        signature = self.verifier.test_only_backend.sign(
            attestation["principal_id"], canonical_bytes(unsigned)
        )
        attestation["signature"] = base64.b64encode(signature).decode("ascii")

    def test_exact_stage_bindings_round_trip_and_nonce_identifiers(self):
        parsed = PromotionAuthorization.from_document(self.authorization)
        self.assertEqual(self.authorization, parsed.document())
        verified = self.verify(parsed)
        self.assertEqual(canonical_digest(self.authorization), verified.authorization_digest)
        self.assertEqual(self.verifier.policy_digest, verified.policy_digest)
        self.assertEqual(tuple(self.payload[key] for key in (
            "builder_id", "evaluator_id", "judge_id", "promoter_id"
        )), verified.principals)
        self.assertEqual(4, len(set(verified.nonce_ids)))
        self.assertEqual(tuple(canonical_digest({
            "policy": self.verifier.policy_digest,
            "principal": item["principal_id"], "nonce": item["nonce"],
        }) for item in self.authorization["attestations"]), verified.nonce_ids)
        builder, evaluator, judge, promoter = parsed.attestations
        self.assertIsNone(builder.record_digest)
        self.assertIsNone(builder.decision_digest)
        self.assertIsNone(evaluator.decision_digest)
        self.assertEqual(judge.decision_digest, promoter.decision_digest)

    def test_subject_record_and_full_decision_substitution_rejected(self):
        for field, code in (
            ("subject", "authentication-subject-mismatch"),
            ("record", "authentication-record-mismatch"),
            ("decision", "authentication-decision-mismatch"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.payload)
                if field == "subject":
                    changed["evaluation_subject"]["parent_champion_digest"] = canonical_digest("other parent")
                elif field == "record":
                    changed["evaluation_record"]["record_digest"] = canonical_digest("other record")
                else:
                    changed["decision_id"] = "decision:substituted"
                self.assert_code(code, lambda: self.verify(payload=changed))

    def test_signature_tamper_and_unsigned_payload_change_rejected(self):
        for index in range(4):
            with self.subTest(stage=index):
                changed = copy.deepcopy(self.authorization)
                changed["attestations"][index]["signature"] = base64.b64encode(b"wrong-signature").decode("ascii")
                self.assert_code("authentication-signature-invalid", lambda: self.verify(changed))
                changed = copy.deepcopy(self.authorization)
                changed["attestations"][index]["nonce"] += ":tampered"
                self.assert_code("authentication-signature-invalid", lambda: self.verify(changed))

    def test_principal_stage_key_and_policy_binding(self):
        for field, value, code in (
            ("principal_id", "other:builder", "authentication-principal-mismatch"),
            ("key_id", "other:key", "authentication-principal-mismatch"),
            ("policy_digest", canonical_digest("other policy"), "authentication-policy-mismatch"),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.authorization)
                changed["attestations"][0][field] = value
                self.assert_code(code, lambda: self.verify(changed))
        changed = dict(self.payload, builder_id="unknown:builder")
        self.assert_code("authentication-principal-unknown", lambda: self.verify(payload=changed))
        bindings = list(self.verifier.test_only_bindings)
        bindings[0] = replace(bindings[0], stage="verifier")
        wrong_stage = PromotionPrincipalVerifier(bindings, self.verifier.test_only_backend,
                                               self.verifier.test_only_receipt_signer)
        self.assert_code("authentication-principal-unknown", lambda: self.verify(verifier=wrong_stage))

    def test_shared_principal_administrator_or_key_fails_independence(self):
        changed = dict(self.payload, promoter_id=self.payload["judge_id"])
        self.assert_code("authentication-independence", lambda: self.verify(payload=changed))
        for field in ("administration_id", "public_key_digest"):
            with self.subTest(field=field):
                bindings = list(self.verifier.test_only_bindings)
                bindings[1] = replace(bindings[1], **{field: getattr(bindings[0], field)})
                verifier = PromotionPrincipalVerifier(bindings, self.verifier.test_only_backend,
                                                      self.verifier.test_only_receipt_signer)
                changed = copy.deepcopy(self.authorization)
                for index, item in enumerate(changed["attestations"]):
                    item["policy_digest"] = verifier.policy_digest
                    self.resign(changed, index)
                self.assert_code("authentication-independence", lambda: self.verify(changed, verifier=verifier))

    def test_future_expired_overlong_and_out_of_order_attestations(self):
        future = authorize(self.payload, self.verifier, now=self.now + timedelta(seconds=1))
        self.assert_code("authentication-stale", lambda: self.verify(future))
        self.assert_code("authentication-stale", lambda: self.verify(now=self.now + timedelta(seconds=300)))
        changed = copy.deepcopy(self.authorization)
        changed["attestations"][0]["expires_at"] = (self.now + timedelta(seconds=3601)).isoformat().replace("+00:00", "Z")
        self.resign(changed, 0)
        self.assert_code("authentication-stale", lambda: self.verify(changed))
        changed = copy.deepcopy(self.authorization)
        changed["attestations"][1]["issued_at"] = (self.now - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        self.resign(changed, 1)
        self.assert_code("authentication-ordering", lambda: self.verify(changed))

    def test_nonce_duplicates_fail_and_verification_does_not_consume(self):
        changed = copy.deepcopy(self.authorization)
        changed["attestations"][1]["nonce"] = changed["attestations"][0]["nonce"]
        self.resign(changed, 1)
        self.assert_code("authentication-replayed", lambda: self.verify(changed))
        # Durable replay rejection is a registry responsibility, not this API.
        self.assertEqual(self.verify(), self.verify())
        fresh = authorize(self.payload, self.verifier, now=self.now)
        self.assertTrue(set(self.verify().nonce_ids).isdisjoint(self.verify(fresh).nonce_ids))

    def test_malformed_stage_schema_signature_and_time_rejected(self):
        mutations = (
            lambda d: d.update(schema_version=True),
            lambda d: d["attestations"].pop(),
            lambda d: d["attestations"].reverse(),
            lambda d: d["attestations"][0].update(signature="not base64!"),
            lambda d: d["attestations"][0].update(record_digest=canonical_digest("illegal record")),
            lambda d: d["attestations"][1].update(decision_digest=canonical_digest("early decision")),
            lambda d: d["attestations"][2].update(decision_digest=None),
            lambda d: d["attestations"][0].update(issued_at="2026-09-12T12:00:00"),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                changed = copy.deepcopy(self.authorization)
                mutate(changed)
                self.assert_code("authentication-malformed", lambda: self.verify(changed))
        self.assert_code("authentication-malformed", lambda: self.verify(now=self.now.replace(tzinfo=None)))

    def test_signature_provider_failure_and_truthy_non_boolean_fail_closed(self):
        backend = self.verifier.test_only_backend
        with patch.object(backend, "verify", side_effect=OSError("test provider unavailable")):
            self.assert_code("authentication-unavailable", self.verify)
        with patch.object(backend, "verify", return_value=1):
            self.assert_code("authentication-signature-invalid", self.verify)

    def test_rejection_receipt_round_trip_is_detached_and_tamper_evident(self):
        payload = {"code": "parent-stale", "candidate_digest": canonical_digest("candidate"),
                   "pointer_unchanged": True, "details": {"attempt": "test-only"}}
        original = copy.deepcopy(payload)
        receipt = self.verifier.sign_rejection(payload)
        payload["details"]["attempt"] = "changed after signing"
        self.assertEqual(original, self.verifier.verify_rejection_receipt(receipt))
        result = self.verifier.verify_rejection_receipt(receipt)
        result["details"]["attempt"] = "changed after verification"
        self.assertEqual(original, self.verifier.verify_rejection_receipt(receipt))
        changed = copy.deepcopy(receipt)
        changed["payload"]["pointer_unchanged"] = False
        self.assert_code("authentication-signature-invalid", lambda: self.verifier.verify_rejection_receipt(changed))
        changed = dict(receipt, policy_digest=canonical_digest("other trust"))
        self.assert_code("authentication-policy-mismatch", lambda: self.verifier.verify_rejection_receipt(changed))

    def test_rejection_signer_failure_empty_or_invalid_signature_fails_closed(self):
        signer = self.verifier.test_only_receipt_signer
        with patch.object(signer, "sign", side_effect=OSError("test custody unavailable")):
            self.assert_code("rejection-signing-unavailable", lambda: self.verifier.sign_rejection({"code": "test"}))
        for result in (b"", "wrong-type"):
            with self.subTest(result=result), patch.object(signer, "sign", return_value=result):
                self.assert_code("rejection-signing-unavailable", lambda: self.verifier.sign_rejection({"code": "test"}))
        with patch.object(signer, "sign", return_value=b"invalid-signature"):
            self.assert_code("authentication-signature-invalid", lambda: self.verifier.sign_rejection({"code": "test"}))

    def test_helper_supports_explicit_identities_and_excludes_existing_authorization(self):
        verifier = verifier_for("build:custom", "eval:custom", "judge:custom", "promote:custom")
        payload = dict(self.payload, builder_id="build:custom", evaluator_id="eval:custom",
                       judge_id="judge:custom", promoter_id="promote:custom",
                       authorization={"old": "not part of signed decision"})
        before = copy.deepcopy(payload)
        authorization = authorize(payload, verifier, now=self.now)
        self.verify(authorization, payload=payload, verifier=verifier)
        self.assertEqual(before, payload)


if __name__ == "__main__":
    unittest.main()
