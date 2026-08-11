from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.authority import AuthorityDenied, AuthorityRegistry
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import (
    Budget,
    ConstraintEnvelope,
    EffectIntent,
)
from hive_mind_os.brain_kernel.effect_outbox import (
    DurableEffectOutbox,
    EffectReconciliationRequired,
)
from hive_mind_os.brain_kernel.effects import (
    EffectGateway,
    build_effect_receipt,
)
from hive_mind_os.brain_kernel.store import KernelStore

DIGEST = "sha256:" + "0" * 64
TIME = "2030-01-01T00:00:00Z"


def _envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-effects",
        "MISSION-effects",
        "WORK-effects",
        None,
        "builder",
        "R1",
        ("write",),
        ("push", "merge", "deploy"),
        ("workspace",),
        ("workspace",),
        (),
        (),
        (),
        (),
        Budget(30, 0, 0, 0, 0, 0, 1, 1),
        "2030-01-02T00:00:00Z",
        DIGEST,
        DIGEST,
    )


def _intent(*, key: str = DIGEST, digest: str = DIGEST) -> EffectIntent:
    return EffectIntent(
        "MISSION-effects",
        "WORK-effects",
        "ATTEMPT-effects",
        "builder-1",
        "builder",
        "write",
        "R1",
        "fake",
        "workspace/result.txt",
        DIGEST,
        key,
        DIGEST,
        ("workspace exists",),
        "remove workspace/result.txt",
        "POLICY-effects",
        digest,
    )


class EffectOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = KernelStore(Path(self.temporary.name) / "kernel.sqlite3")
        self.registry = AuthorityRegistry()
        envelope = _envelope()
        self.registry.register(envelope)
        self.token = self.registry.authorize(
            DIGEST, "write", "workspace/result.txt", now=TIME
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def test_intent_is_durable_before_adapter_runs(self) -> None:
        calls: list[str] = []
        gateway = EffectGateway(store=self.store)
        gateway.register_adapter("fake", lambda intent: calls.append(intent.target))
        intent = _intent()

        outbox = DurableEffectOutbox(
            self.store, adapters={"fake": lambda _: calls.append("delivered")}
        )
        outbox.enqueue(intent, self.token)
        self.assertEqual([], calls)
        entry = self.store.effect_entry(intent_digest=DIGEST)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual("pending", entry["state"])
        result = gateway.execute(intent, self.token)
        self.assertEqual("SUCCEEDED", result.status)
        self.assertEqual(["workspace/result.txt"], calls)
        entry = self.store.effect_entry(intent_digest=DIGEST)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual("receipt_recorded", entry["state"])

    def test_duplicate_delivery_returns_prior_receipt_after_restart(self) -> None:
        calls: list[str] = []
        intent = _intent()
        gateway = EffectGateway(store=self.store)
        gateway.register_adapter("fake", lambda _: calls.append("physical"))
        first = gateway.execute(intent, self.token)
        self.store.close()

        reopened = KernelStore(Path(self.temporary.name) / "kernel.sqlite3")
        retry = EffectGateway(store=reopened)
        retry.register_adapter("fake", lambda _: calls.append("duplicate"))
        second = retry.execute(intent, self.token)
        self.assertEqual(first, second)
        self.assertEqual(["physical"], calls)
        reopened.close()
        self.store = KernelStore(Path(self.temporary.name) / "kernel.sqlite3")

    def test_crash_window_becomes_reconciliation_and_is_repairable(self) -> None:
        calls: list[str] = []

        def ambiguous(_: EffectIntent) -> None:
            calls.append("physical-effect-happened")
            raise RuntimeError("simulated crash after physical effect")

        intent = _intent(key=canonical_digest({"key": "crash"}), digest=canonical_digest({"intent": "crash"}))
        gateway = EffectGateway(store=self.store)
        gateway.register_adapter("fake", ambiguous)
        with self.assertRaises(EffectReconciliationRequired):
            gateway.execute(intent, self.token)
        self.assertEqual(["physical-effect-happened"], calls)
        entry = self.store.effect_entry(intent_digest=intent.intent_digest)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual("reconciliation_required", entry["state"])

        receipt = build_effect_receipt(
            intent,
            adapter_identity="fake",
            adapter_version="1",
            started_at=TIME,
            ended_at="2030-01-01T00:00:01Z",
        )
        result = DurableEffectOutbox(self.store).reconcile(
            intent.intent_digest,
            receipt,
            token=self.token,
            evidence={"witness": "fixture-probe"},
        )
        self.assertEqual("SUCCEEDED", result.status)
        self.assertEqual(result, gateway.execute(intent, self.token))
        self.assertEqual(["physical-effect-happened"], calls)

    def test_authority_and_token_tampering_fail_closed(self) -> None:
        intent = _intent()
        with self.assertRaises(AuthorityDenied):
            EffectGateway().execute(
                intent,
                type(self.token)(
                    self.token.envelope_digest,
                    self.token.action,
                    self.token.target,
                    DIGEST,
                ),
            )
        with self.assertRaises(AuthorityDenied):
            self.registry.authorize(
                DIGEST, "write", "other/result.txt", now=TIME
            )


if __name__ == "__main__":
    unittest.main()
