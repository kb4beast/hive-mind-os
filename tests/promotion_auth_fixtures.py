"""TEST-ONLY HMAC fixtures; these provide no production principal independence.

Keys are deterministic public test data. Never import this module from src or
use this backend to authorize a real registry or external action.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.promotion_auth import (
    PrincipalBinding,
    PromotionPrincipalVerifier,
)


class TestOnlyHmacBackend:
    """Insecure, local test double for the signature-provider protocol."""

    def __init__(self, bindings):
        self.bindings = {item.principal_id: item for item in bindings}
        self.keys = {
            item.key_id: self.key_for(item.principal_id) for item in bindings
        }

    @staticmethod
    def key_for(principal_id):
        return hashlib.sha256(
            ("PUBLIC TEST DATA ONLY:" + principal_id).encode("utf-8")
        ).digest()

    def sign(self, principal_id, message):
        binding = self.bindings[principal_id]
        return hmac.digest(self.keys[binding.key_id], message, "sha256")

    def verify(self, principal, message, signature):
        key = self.keys.get(principal.key_id)
        if key is None:
            return False
        if principal.public_key_digest != "sha256:" + hashlib.sha256(key).hexdigest():
            return False
        return hmac.compare_digest(hmac.digest(key, message, "sha256"), signature)


class TestOnlyReceiptSigner:
    def __init__(self, backend, binding):
        self.backend = backend
        self.principal_id = binding.principal_id
        self.key_id = binding.key_id

    def sign(self, message):
        return self.backend.sign(self.principal_id, message)


def verifier_for(
    builder_id="builder:test",
    evaluator_id="evaluator:test",
    judge_id="judge:test",
    promoter_id="promoter:test",
):
    """Return an explicitly TEST-ONLY verifier with distinct local fixture pins."""
    stages = ("builder", "verifier", "judge", "promoter", "receipt")
    identities = (
        builder_id, evaluator_id, judge_id, promoter_id, "receipt:test-only"
    )
    bindings = tuple(
        PrincipalBinding(
            identity,
            stage,
            "test-only-administration:" + identity,
            "test-only-key:" + identity,
            "sha256:" + hashlib.sha256(
                TestOnlyHmacBackend.key_for(identity)
            ).hexdigest(),
        )
        for stage, identity in zip(stages, identities)
    )
    backend = TestOnlyHmacBackend(bindings)
    signer = TestOnlyReceiptSigner(backend, bindings[-1])
    verifier = PromotionPrincipalVerifier(bindings, backend, signer)
    # Deliberately named testing hooks; no production policy introspection API.
    verifier.test_only_bindings = bindings
    verifier.test_only_backend = backend
    verifier.test_only_receipt_signer = signer
    return verifier


def authorize(payload, verifier, *, now=None, lifetime_seconds=300):
    """Sign a payload using ONLY verifier_for's public test-data credentials.

    Existing authorization is excluded from the decision preimage. The caller's
    payload is not mutated. A fresh nonce is used for each stage on every call.
    """
    if not 0 < lifetime_seconds <= 3600:
        raise ValueError("test authorization lifetime must be in (0, 3600]")
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() != timedelta(0):
        raise ValueError("test authorization time must be aware UTC")
    subject = canonical_digest(payload["evaluation_subject"])
    record = payload["evaluation_record"]["record_digest"]
    decision = canonical_digest({
        key: value for key, value in payload.items() if key != "authorization"
    })
    identities = (
        payload["builder_id"], payload["evaluator_id"],
        payload["judge_id"], payload["promoter_id"],
    )
    attestations = []
    for stage, identity in zip(("builder", "verifier", "judge", "promoter"), identities):
        binding = verifier.test_only_backend.bindings[identity]
        unsigned = {
            "schema_version": 1,
            "kind": "promotion-attestation",
            "stage": stage,
            "principal_id": identity,
            "key_id": binding.key_id,
            "policy_digest": verifier.policy_digest,
            "subject_digest": subject,
            "record_digest": None if stage == "builder" else record,
            "decision_digest": decision if stage in ("judge", "promoter") else None,
            "nonce": "test-only:" + uuid4().hex,
            "issued_at": current.isoformat().replace("+00:00", "Z"),
            "expires_at": (current + timedelta(seconds=lifetime_seconds)).isoformat().replace("+00:00", "Z"),
        }
        signature = verifier.test_only_backend.sign(identity, canonical_bytes(unsigned))
        attestations.append({
            **unsigned, "signature": base64.b64encode(signature).decode("ascii")
        })
    return {"schema_version": 1, "attestations": attestations}
