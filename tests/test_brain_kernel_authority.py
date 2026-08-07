from __future__ import annotations

import unittest

from hive_mind_os.brain_kernel.authority import AuthorityDenied, AuthorityRegistry
from hive_mind_os.brain_kernel.contracts import Budget, ConstraintEnvelope, EffectIntent
from hive_mind_os.brain_kernel.effects import EffectGateway

DIGEST = "sha256:" + "0" * 64


def envelope(*, expires_at: str = "2030-01-01T00:00:00Z") -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-one",
        "MISSION-one",
        "WORK-one",
        None,
        "builder",
        "R1",
        ("write",),
        ("push", "merge", "deploy"),
        ("src",),
        ("src",),
        (),
        (),
        (),
        (),
        Budget(1, 0, 0, 0, 0, 0, 1, 1),
        expires_at,
        DIGEST,
        DIGEST,
    )


class AuthorityTests(unittest.TestCase):
    def test_scope_expiry_revocation_and_action_denials_fail_closed(self) -> None:
        registry = AuthorityRegistry()
        granted = envelope()
        registry.register(granted)
        token = registry.authorize(
            DIGEST, "write", "src/one.py", now="2029-01-01T00:00:00Z"
        )
        self.assertEqual("src/one.py", token.target)
        with self.assertRaises(AuthorityDenied):
            registry.authorize(DIGEST, "write", "other.py", now="2029-01-01T00:00:00Z")
        with self.assertRaises(AuthorityDenied):
            registry.authorize(DIGEST, "push", "src/one.py", now="2029-01-01T00:00:00Z")
        registry.revoke(DIGEST)
        with self.assertRaises(AuthorityDenied):
            registry.authorize(
                DIGEST, "write", "src/one.py", now="2029-01-01T00:00:00Z"
            )

    def test_gateway_requires_matching_token_and_deduplicates(self) -> None:
        registry = AuthorityRegistry()
        registry.register(envelope())
        token = registry.authorize(
            DIGEST, "write", "src/one.py", now="2029-01-01T00:00:00Z"
        )
        intent = EffectIntent(
            "MISSION-one",
            "WORK-one",
            "ATTEMPT-one",
            "builder",
            "builder",
            "write",
            "R1",
            "local",
            "src/one.py",
            DIGEST,
            DIGEST,
            DIGEST,
            (),
            "revert",
            "policy",
            DIGEST,
        )
        calls: list[str] = []
        gateway = EffectGateway()
        gateway.register_adapter("local", lambda _: calls.append("called"))
        self.assertEqual(gateway.execute(intent, token), gateway.execute(intent, token))
        self.assertEqual(["called"], calls)
        with self.assertRaises(AuthorityDenied):
            gateway.execute(
                intent, type(token)(DIGEST, "write", "src/other.py", DIGEST)
            )
