from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.authority import (
    AuthorityDenied,
    AuthorityRegistry,
    CapabilityToken,
)
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
    sealed_intent,
)
from hive_mind_os.brain_kernel.store import KernelStore

DIGEST = "sha256:" + "0" * 64
TIME = "2030-01-01T00:00:00Z"
FORGED_ENVELOPE = "sha256:" + "d" * 64
REFUSED_TARGET = "secrets/keys.txt"
GRANTED_TARGET = "workspace/result.txt"
GRANTED_HOST = "api.github.com"
UNLISTED_HOST = "api.unlisted.example"


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
    ).sealed()


AUTH = _envelope().digest_value


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
        AUTH,
        ("workspace exists",),
        "remove workspace/result.txt",
        "POLICY-effects",
        digest,
    )


def _boundary_envelope(
    *,
    expires_at: str = "2030-01-02T00:00:00Z",
    network_allowlist: tuple[str, ...] = (),
) -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-boundary",
        "MISSION-effects",
        "WORK-effects",
        None,
        "builder",
        "R1",
        ("write",),
        ("push", "merge", "deploy"),
        ("workspace",),
        ("workspace",),
        network_allowlist,
        (),
        (),
        (),
        Budget(30, 0, 0, 0, 0, 0, 1, 1),
        expires_at,
        DIGEST,
        DIGEST,
    ).sealed()


def _boundary_intent(
    envelope_digest: str,
    *,
    target: str = GRANTED_TARGET,
    adapter: str = "fake",
    key: str = DIGEST,
) -> EffectIntent:
    return sealed_intent(
        EffectIntent(
            "MISSION-effects",
            "WORK-effects",
            "ATTEMPT-effects",
            "builder-1",
            "builder",
            "write",
            "R1",
            adapter,
            target,
            DIGEST,
            key,
            envelope_digest,
            ("workspace exists",),
            "remove " + target,
            "POLICY-effects",
            DIGEST,
        )
    )


def _forged_token(
    envelope_digest: str, action: str, target: str, token_digest: str
) -> CapabilityToken:
    """Write a token straight into its slots, past the constructor's issuance check.

    ``CapabilityToken.__post_init__`` now refuses a token no registry issued, so
    the probe-2 forgery cannot be built the ordinary way.  These fixtures forge
    it at the slot level anyway, which keeps every gateway-level refusal below
    under test rather than short-circuiting it at construction;
    ``IssuanceWitnessTests`` covers the constructor guard on its own.
    """

    forged = object.__new__(CapabilityToken)
    values = (envelope_digest, action, target, token_digest, "")
    for name, value in zip(CapabilityToken.__slots__, values):
        object.__setattr__(forged, name, value)
    return forged


def _hand_built_token(envelope_digest: str, action: str, target: str) -> CapabilityToken:
    """The probe-2 forgery: a token no registry ever issued, sealed as one seals."""

    return _forged_token(
        envelope_digest,
        action,
        target,
        canonical_digest(
            {"envelope": envelope_digest, "action": action, "target": target}
        ),
    )


class EffectBoundaryTests(unittest.TestCase):
    """A5-F10, A5-F14 and A4-D5: the boundary consults live authority state."""

    def setUp(self) -> None:
        self.calls: list[str] = []
        self.registry = AuthorityRegistry()
        self.envelope = _boundary_envelope()
        self.mint(self.envelope)

    def mint(self, envelope: ConstraintEnvelope) -> None:
        self.registry.mint_root(
            envelope,
            issuer="owner:boundary-fixture",
            authority_ref="AUTHORITY-RECORD-boundary",
            recorded_at="2026-01-01T00:00:00Z",
        )

    def record(self, intent: EffectIntent) -> None:
        self.calls.append(intent.target)

    def bound_gateway(self, **overrides) -> EffectGateway:
        gateway = EffectGateway(
            authority=overrides.pop("authority", self.registry),
            clock=overrides.pop("clock", lambda: TIME),
        )
        gateway.register_adapter("fake", self.record, **overrides)
        return gateway

    def issued(self, envelope: ConstraintEnvelope | None = None) -> CapabilityToken:
        return self.registry.authorize(
            (envelope or self.envelope).digest_value, "write", GRANTED_TARGET, now=TIME
        )

    def test_hand_built_token_for_an_unissued_envelope_is_refused(self) -> None:
        with self.assertRaises(AuthorityDenied):
            self.registry.authorize(
                self.envelope.digest_value, "write", REFUSED_TARGET, now=TIME
            )
        forged = _hand_built_token(FORGED_ENVELOPE, "write", REFUSED_TARGET)
        intent = _boundary_intent(FORGED_ENVELOPE, target=REFUSED_TARGET)
        with self.assertRaises(AuthorityDenied):
            self.bound_gateway().execute(intent, forged)
        self.assertEqual([], self.calls)

    def test_token_outside_the_envelope_scope_is_refused(self) -> None:
        forged = _hand_built_token(self.envelope.digest_value, "write", REFUSED_TARGET)
        intent = _boundary_intent(self.envelope.digest_value, target=REFUSED_TARGET)
        with self.assertRaises(AuthorityDenied):
            self.bound_gateway().execute(intent, forged)
        self.assertEqual([], self.calls)

    def test_expired_envelope_is_refused_after_a_legitimate_issue(self) -> None:
        token = self.issued()
        intent = _boundary_intent(self.envelope.digest_value)
        self.assertEqual("SUCCEEDED", self.bound_gateway().execute(intent, token).status)
        expired = self.bound_gateway(clock=lambda: "2030-01-03T00:00:00Z")
        with self.assertRaises(AuthorityDenied):
            expired.execute(intent, token)
        self.assertEqual([GRANTED_TARGET], self.calls)

    def test_revoked_envelope_is_refused_after_a_legitimate_issue(self) -> None:
        token = self.issued()
        intent = _boundary_intent(self.envelope.digest_value)
        gateway = self.bound_gateway()
        self.assertEqual("SUCCEEDED", gateway.execute(intent, token).status)
        self.registry.revoke(self.envelope.digest_value)
        with self.assertRaises(AuthorityDenied):
            gateway.execute(intent, token)
        self.assertEqual([GRANTED_TARGET], self.calls)

    def test_intent_digest_that_does_not_seal_its_fields_is_refused(self) -> None:
        token = self.issued()
        intent = _boundary_intent(self.envelope.digest_value)
        gateway = self.bound_gateway()
        with self.assertRaisesRegex(AuthorityDenied, "does not seal"):
            gateway.execute(replace(intent, intent_digest=DIGEST), token)
        with self.assertRaisesRegex(AuthorityDenied, "does not seal"):
            gateway.execute(replace(intent, rollback_description="keep it"), token)
        self.assertEqual([], self.calls)
        self.assertEqual("SUCCEEDED", gateway.execute(intent, token).status)
        self.assertEqual([GRANTED_TARGET], self.calls)

    def test_effect_reaching_a_host_outside_the_allowlist_is_refused(self) -> None:
        envelope = _boundary_envelope(network_allowlist=(GRANTED_HOST,))
        self.mint(envelope)
        token = self.issued(envelope)
        gateway = EffectGateway(authority=self.registry, clock=lambda: TIME)
        gateway.register_adapter("listed", self.record, network_hosts=(GRANTED_HOST,))
        gateway.register_adapter("unlisted", self.record, network_hosts=(UNLISTED_HOST,))
        unlisted = _boundary_intent(envelope.digest_value, adapter="unlisted")
        with self.assertRaisesRegex(AuthorityDenied, "network allowlist"):
            gateway.execute(unlisted, token)
        self.assertEqual([], self.calls)
        listed = _boundary_intent(
            envelope.digest_value,
            adapter="listed",
            key=canonical_digest({"key": "listed"}),
        )
        self.assertEqual("SUCCEEDED", gateway.execute(listed, token).status)
        self.assertEqual([GRANTED_TARGET], self.calls)

    def test_network_effect_requires_an_authority_bound_gateway(self) -> None:
        token = self.issued()
        gateway = EffectGateway()
        gateway.register_adapter("fake", self.record, network_hosts=(GRANTED_HOST,))
        with self.assertRaisesRegex(AuthorityDenied, "authority-bound"):
            gateway.execute(_boundary_intent(self.envelope.digest_value), token)
        self.assertEqual([], self.calls)

    def test_durable_gateway_refuses_a_forged_token_before_it_is_recorded(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        store = KernelStore(Path(temporary.name) / "kernel.sqlite3")
        self.addCleanup(store.close)
        forged = _hand_built_token(FORGED_ENVELOPE, "write", REFUSED_TARGET)
        intent = _boundary_intent(FORGED_ENVELOPE, target=REFUSED_TARGET)
        gateway = EffectGateway(store, authority=self.registry, clock=lambda: TIME)
        gateway.register_adapter("fake", self.record)
        with self.assertRaises(AuthorityDenied):
            gateway.execute(intent, forged)
        self.assertIsNone(store.effect_entry(intent_digest=intent.intent_digest))
        self.assertEqual([], self.calls)

    def test_gateway_without_an_authority_still_serves_existing_callers(self) -> None:
        """The compatibility path kernel callers still take; it verifies no issuance."""

        token = self.issued()
        gateway = EffectGateway()
        gateway.register_adapter("fake", self.record)
        unsealed = replace(
            _boundary_intent(self.envelope.digest_value), intent_digest=DIGEST
        )
        self.assertEqual("SUCCEEDED", gateway.execute(unsealed, token).status)
        self.assertEqual([GRANTED_TARGET], self.calls)


class IssuanceWitnessTests(unittest.TestCase):
    """BIND-1030: a capability nobody issued cannot be constructed at all."""

    def setUp(self) -> None:
        self.registry = AuthorityRegistry()
        self.envelope = _boundary_envelope()
        self.registry.mint_root(
            self.envelope,
            issuer="owner:witness-fixture",
            authority_ref="AUTHORITY-RECORD-witness",
            recorded_at="2026-01-01T00:00:00Z",
        )

    def test_a_token_no_registry_issued_cannot_be_constructed(self) -> None:
        for envelope_digest, target in (
            (FORGED_ENVELOPE, REFUSED_TARGET),
            (self.envelope.digest_value, REFUSED_TARGET),
            (self.envelope.digest_value, GRANTED_TARGET),
        ):
            with self.subTest(envelope=envelope_digest, target=target):
                with self.assertRaisesRegex(AuthorityDenied, "was not issued"):
                    CapabilityToken(
                        envelope_digest,
                        "write",
                        target,
                        canonical_digest(
                            {
                                "envelope": envelope_digest,
                                "action": "write",
                                "target": target,
                            }
                        ),
                    )

    def test_an_issued_token_carries_a_witness_bound_to_its_own_fields(self) -> None:
        issued = self.registry.authorize(
            self.envelope.digest_value, "write", GRANTED_TARGET, now=TIME
        )
        self.assertTrue(issued.issuance_witness)
        # Positive control: the same issuance reproduces exactly, so the witness
        # is a function of the token, not a nonce that breaks re-issue equality.
        self.assertEqual(
            issued,
            self.registry.authorize(
                self.envelope.digest_value, "write", GRANTED_TARGET, now=TIME
            ),
        )
        # Cheat: keep the witness while pointing the token at another target.
        with self.assertRaisesRegex(AuthorityDenied, "was not issued"):
            CapabilityToken(
                issued.envelope_digest,
                issued.action,
                REFUSED_TARGET,
                issued.token_digest,
                issued.issuance_witness,
            )

    def test_the_registry_publishes_the_envelope_behind_a_digest(self) -> None:
        self.assertIs(
            self.envelope, self.registry.envelope(self.envelope.digest_value)
        )
        with self.assertRaisesRegex(AuthorityDenied, "unavailable"):
            self.registry.envelope(FORGED_ENVELOPE)
        self.registry.revoke(self.envelope.digest_value)
        with self.assertRaisesRegex(AuthorityDenied, "unavailable"):
            self.registry.envelope(self.envelope.digest_value)


class EffectOutboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = KernelStore(Path(self.temporary.name) / "kernel.sqlite3")
        self.registry = AuthorityRegistry()
        self.registry.mint_root(
            _envelope(),
            issuer="owner:effects-fixture",
            authority_ref="AUTHORITY-RECORD-effects",
            recorded_at="2026-01-01T00:00:00Z",
        )
        self.token = self.registry.authorize(
            AUTH, "write", "workspace/result.txt", now=TIME
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
                _forged_token(
                    self.token.envelope_digest,
                    self.token.action,
                    self.token.target,
                    DIGEST,
                ),
            )
        with self.assertRaises(AuthorityDenied):
            self.registry.authorize(
                AUTH, "write", "other/result.txt", now=TIME
            )


if __name__ == "__main__":
    unittest.main()
