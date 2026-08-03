from __future__ import annotations

import base64
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hive_mind_os.contracts import tool_intent_digest, validate_contract
from hive_mind_os.custody import (
    CustodyProvenanceStore,
    Ed25519CustodyVerifier,
    TrustAnchor,
)
from hive_mind_os.hard_isolation import (
    CapabilityAttestationProvenance,
    CapabilityAuthorizer,
    ExternalCapabilityAuthorizer,
    HardIsolationCapability,
    HardIsolationExecutionPlan,
    HardIsolationGateway,
    HardIsolationProfile,
    HardIsolationReceipt,
    HardIsolationReceiptCollector,
    HardIsolationRejected,
    HardIsolationUnavailable,
    IsolationOutcome,
    IsolationRuntime,
    NetworkGrant,
    ResourceLimits,
    local_hard_isolation_capability,
)
from hive_mind_os.receipts import sha256_digest


def _digest(label: str) -> str:
    return sha256_digest(label.encode("utf-8"))


def _encoded(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _signed(
    document: Mapping[str, object], key: Ed25519PrivateKey, domain: bytes
) -> dict[str, object]:
    unsigned = dict(document)
    unsigned.pop("signature", None)
    payload = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {**unsigned, "signature": _encoded(key.sign(domain + payload))}


class _FakeHardAdapter:
    def __init__(self, *, mutate: str | None = None) -> None:
        self.mutate = mutate
        self.calls = 0

    def capability(self, profile: HardIsolationProfile) -> HardIsolationCapability:
        return HardIsolationCapability(
            capability_id="hard-capability-test-1",
            adapter_identity="test-hard-adapter",
            runtime=profile.runtime,
            runtime_digest=profile.runtime_digest,
            supported=True,
            conformance_status="passed",
            reason="independent conformance receipt is configured for this test adapter",
            adapter_version="test-hard-adapter-v1",
        )

    def capability_attestation(
        self, profile: HardIsolationProfile, capability: HardIsolationCapability
    ) -> Mapping[str, object]:
        return {"test_capability": capability.capability_id}

    def execute(
        self, profile: HardIsolationProfile, plan: HardIsolationExecutionPlan
    ) -> HardIsolationReceipt:
        self.calls += 1
        receipt = HardIsolationReceipt(
            receipt_id="HIRECEIPT-" + plan.execution_id.removeprefix("HIEXEC-"),
            execution_id=plan.execution_id,
            execution_plan_digest=plan.digest,
            intent_digest=plan.tool_intent_digest,
            profile_id=profile.profile_id,
            profile_digest=profile.digest(),
            runtime=profile.runtime,
            runtime_digest=profile.runtime_digest,
            image_digest=profile.image_digest,
            guest_executable_digest=profile.guest_executable_digest,
            source_snapshot_digest=profile.source_snapshot_digest,
            controller_identity=profile.controller_identity,
            actor_id=plan.actor_id,
            outcome=IsolationOutcome.SUCCEEDED,
            exit_code=0,
            output_digest=_digest("untrusted guest output"),
            output_bytes=22,
            mounts_enforced=True,
            network_enforced=True,
            resource_limits_enforced=True,
            cleanup_completed=True,
            observed_at="2026-08-03T12:00:00Z",
            adapter_version="test-hard-adapter-v1",
        )
        if self.mutate == "image":
            return replace(receipt, image_digest=_digest("substituted-image"))
        if self.mutate == "output":
            return replace(receipt, output_bytes=profile.limits.output_bytes + 1)
        return receipt


class _TestCapabilityAuthorizer(CapabilityAuthorizer):
    """A deterministic test authority, deliberately not production authentication."""

    def authorize(
        self,
        profile: HardIsolationProfile,
        capability: HardIsolationCapability,
        attestation: Mapping[str, object],
    ) -> None:
        if attestation != {"test_capability": capability.capability_id}:
            raise HardIsolationUnavailable("test capability attestation is invalid")


class HardIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def profile(self, **overrides: Any) -> HardIsolationProfile:
        values: dict[str, Any] = {
            "profile_id": "hard-profile-1",
            "runtime": IsolationRuntime.EPHEMERAL_VM,
            "runtime_digest": _digest("runtime"),
            "image_digest": _digest("image"),
            "guest_executable_digest": _digest("guest-executable"),
            "guest_executable_path": "source/bin/guest-tool",
            "source_snapshot_digest": _digest("source-snapshot"),
            "source_mount": "source",
            "writable_overlay": "overlay",
            "limits": ResourceLimits(1000, 64_000_000, 8, 64_000_000, 4096, 30),
            "controller_identity": "host-controller-1",
            "credential_broker_identity": "host-credential-broker-1",
        }
        values.update(overrides)
        return HardIsolationProfile(**values)

    def plan(
        self,
        profile: HardIsolationProfile,
        intent: Mapping[str, object],
        *,
        guest_argv: tuple[str, ...] | None = None,
    ) -> HardIsolationExecutionPlan:
        return HardIsolationExecutionPlan.create(
            profile,
            intent,
            guest_argv=guest_argv or (profile.guest_executable_path, "--check"),
        )

    def gateway(self, adapter: _FakeHardAdapter | None = None) -> HardIsolationGateway:
        return HardIsolationGateway(
            adapter,
            authorizer=_TestCapabilityAuthorizer(),
            collector=HardIsolationReceiptCollector(self.base / "host-evidence"),
        )

    def intent(self, guest_argv: list[str] | None = None) -> dict[str, Any]:
        document: dict[str, Any] = {
            "schema_version": 1,
            "action_id": "ACT-hard-1",
            "mission_id": "mission-hard",
            "state_ref": "MISSION_STATE:mission-hard:1",
            "actor_id": "builder-guest-1",
            "kind": "command",
            "description": "execute untrusted code through the hard-isolation gateway",
            "action_digest": f"sha256:{'0' * 64}",
            "policy_decision_ref": "POLICY-hard-1",
            "lease_id": "LEASE-hard-1",
            "idempotency_key": "ACT-hard-1",
            "rollback_ref": None,
            "command": {"argv": guest_argv or ["source/bin/guest-tool", "--check"], "path_args": []},
            "status": "proposed",
        }
        document["action_digest"] = tool_intent_digest(document)
        return document

    def test_profile_is_typed_credential_free_and_default_deny_network(self) -> None:
        profile = self.profile()
        document = profile.to_contract()
        self.assertEqual(document["network_grants"], [])
        self.assertEqual(document["credential_broker_identity"], "host-credential-broker-1")
        self.assertNotIn("api_key", document)
        self.assertTrue(validate_contract("hard-isolation-profile", document).valid)
        self.assertEqual(profile.digest(), profile.digest())
        with self.assertRaisesRegex(ValueError, "public DNS"):
            self.profile(network_grants=(NetworkGrant("tcp", "localhost", 443, _digest("dns")),))
        for destination in ("127.0.0.2", "::ffff:127.0.0.1", "169.254.169.254", "metadata.google.internal"):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                NetworkGrant("tcp", destination, 443, _digest(destination))
        with self.assertRaisesRegex(ValueError, "differ"):
            self.profile(credential_broker_identity="host-controller-1")

    def test_local_capability_is_explicitly_unavailable_and_never_falls_back(self) -> None:
        profile = self.profile()
        capability = local_hard_isolation_capability(profile)
        self.assertFalse(capability.supported)
        self.assertEqual(capability.conformance_status, "unverified")
        with self.assertRaises(HardIsolationUnavailable):
            HardIsolationGateway(
                collector=HardIsolationReceiptCollector(self.base / "host-evidence")
            ).execute(profile, self.intent(), self.plan(profile, self.intent()))

    def test_gateway_accepts_only_a_matching_tested_host_observation(self) -> None:
        adapter = _FakeHardAdapter()
        profile = self.profile()
        intent = self.intent()
        plan = self.plan(profile, intent)
        with self.assertRaises(HardIsolationUnavailable):
            HardIsolationGateway(
                adapter, collector=HardIsolationReceiptCollector(self.base / "self-asserted")
            ).execute(profile, intent, plan)
        receipt = self.gateway(adapter).execute(profile, intent, plan)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(receipt.outcome, IsolationOutcome.SUCCEEDED)
        self.assertTrue(validate_contract("hard-isolation-receipt", receipt.to_contract()).valid)

    def test_gateway_rejects_substituted_image_and_budget_overrun(self) -> None:
        with self.assertRaisesRegex(HardIsolationRejected, "image_digest"):
            self.gateway(_FakeHardAdapter(mutate="image")).execute(
                self.profile(), self.intent(), self.plan(self.profile(), self.intent())
            )
        with self.assertRaisesRegex(HardIsolationRejected, "output budget"):
            HardIsolationGateway(
                _FakeHardAdapter(mutate="output"),
                authorizer=_TestCapabilityAuthorizer(),
                collector=HardIsolationReceiptCollector(self.base / "output-evidence"),
            ).execute(
                self.profile(), self.intent(), self.plan(self.profile(), self.intent())
            )

    def test_collector_is_outside_guest_and_replay_is_byte_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            with self.assertRaisesRegex(ValueError, "outside guest"):
                HardIsolationReceiptCollector(base / "guest" / "evidence", guest_root=base / "guest")

            profile = self.profile()
            intent = self.intent()
            plan = self.plan(profile, intent)
            collector = HardIsolationReceiptCollector(base / "host-evidence", guest_root=base / "guest")
            receipt = HardIsolationGateway(
                _FakeHardAdapter(), authorizer=_TestCapabilityAuthorizer(), collector=collector
            ).execute(profile, intent, plan)
            path = collector.persist(plan, receipt)
            self.assertTrue(path.is_file())
            self.assertEqual(collector.persist(plan, receipt), path)
            changed = replace(receipt, output_digest=_digest("replayed"))
            with self.assertRaisesRegex(HardIsolationRejected, "replayed"):
                collector.persist(plan, changed)

    def test_receipt_id_and_collector_paths_cannot_escape_host_evidence_root(self) -> None:
        profile = self.profile()
        intent = self.intent()
        plan = self.plan(profile, intent)
        receipt = self.gateway(_FakeHardAdapter()).execute(profile, intent, plan)
        with self.assertRaisesRegex(ValueError, "single segment"):
            replace(receipt, receipt_id="../../outside")
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            collector = HardIsolationReceiptCollector(base / "host-evidence")
            collector.reserve(plan)
            directory = collector.root / "hard-isolation" / "receipts"
            directory.mkdir(parents=True)
            try:
                directory.rmdir()
                directory.symlink_to(base, target_is_directory=True)
            except OSError:
                pass
            else:
                with self.assertRaisesRegex(HardIsolationRejected, "symlink"):
                    collector.persist(plan, receipt)

    def test_execution_plan_binds_profile_intent_guest_and_reservation_before_dispatch(self) -> None:
        profile = self.profile()
        intent = self.intent()
        with self.assertRaisesRegex(HardIsolationRejected, "credentials or secrets"):
            self.plan(profile, intent, guest_argv=("source/bin/guest-tool", "--token=secret"))
        with self.assertRaisesRegex(HardIsolationRejected, "pinned guest executable"):
            self.plan(profile, intent, guest_argv=("source/bin/another", "--check"))
        plan = self.plan(profile, intent)
        adapter = _FakeHardAdapter()
        gateway = self.gateway(adapter)
        gateway.execute(profile, intent, plan)
        self.assertEqual(adapter.calls, 1)
        with self.assertRaisesRegex(HardIsolationUnavailable, "ambiguous/replayed"):
            gateway.execute(profile, intent, plan)
        self.assertEqual(adapter.calls, 1)

    def test_plan_cannot_substitute_an_unapproved_guest_argument(self) -> None:
        profile = self.profile()
        intent = self.intent()
        plan = self.plan(
            profile, intent, guest_argv=("source/bin/guest-tool", "--unapproved-side-effect")
        )
        with self.assertRaisesRegex(HardIsolationRejected, "exactly approved"):
            self.gateway(_FakeHardAdapter()).execute(profile, intent, plan)

    def test_direct_execution_plan_constructor_cannot_forge_a_fresh_logical_id(self) -> None:
        profile = self.profile()
        intent = self.intent()
        forged = replace(
            self.plan(profile, intent), execution_id="HIEXEC-" + "a" * 64
        )
        with self.assertRaisesRegex(HardIsolationRejected, "does not bind"):
            self.gateway(_FakeHardAdapter()).execute(profile, intent, forged)

    def test_writable_overlay_and_guest_path_cannot_escape_the_immutable_source_mount(self) -> None:
        with self.assertRaisesRegex(ValueError, "disjoint"):
            self.profile(writable_overlay="source/overlay")
        with self.assertRaisesRegex(ValueError, "immutable source"):
            self.profile(guest_executable_path="overlay/bin/guest-tool")

    def test_resource_profile_requires_an_inode_or_file_count_bound(self) -> None:
        with self.assertRaisesRegex(ValueError, "file_count"):
            ResourceLimits(1000, 64_000_000, 8, 64_000_000, 4096, 30, 0)
        self.assertEqual(self.profile().limits.file_count, 10_000)

    def test_nondefault_egress_requires_a_pinned_proxy_identity_and_digest(self) -> None:
        grant = NetworkGrant("tcp", "api.example", 443, _digest("api.example dns"))
        with self.assertRaisesRegex(ValueError, "egress proxy"):
            self.profile(
                network_grants=(grant,),
                egress_enforcement="pinned-egress-proxy",
            )
        profile = self.profile(
            network_grants=(grant,),
            egress_enforcement="pinned-egress-proxy",
            egress_proxy_identity="egress-proxy-1",
            egress_proxy_digest=_digest("egress-proxy-image"),
        )
        self.assertTrue(validate_contract("hard-isolation-profile", profile.to_contract()).valid)

    def test_external_capability_authorizer_checks_signature_fresh_keyset_and_nonce_replay(self) -> None:
        now = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
        root_key = Ed25519PrivateKey.generate()
        signer_key = Ed25519PrivateKey.generate()
        anchor = TrustAnchor(
            "isolation-authority.example",
            "root-1",
            "isolation-authority.example/root",
            _encoded(root_key.public_key().public_bytes_raw()),
        )
        custody_provenance = CustodyProvenanceStore(self.base / "custody.sqlite")
        try:
            verifier = Ed25519CustodyVerifier(anchor, custody_provenance, now=lambda: now)
            verifier.install_keyset(
                _signed(
                    {
                        "schema_version": 1,
                        "authority_id": anchor.authority_id,
                        "sequence": 1,
                        "issued_at": now.isoformat(),
                        "expires_at": (now + timedelta(hours=1)).isoformat(),
                        "issuer_key_id": anchor.key_id,
                        "issuer_identity": anchor.signer_identity,
                        "keys": [
                            {
                                "key_id": "adapter-attestor-1",
                                "signer_identity": "isolation-authority.example/adapter-attestor",
                                "public_key": _encoded(signer_key.public_key().public_bytes_raw()),
                                "status": "active",
                                "not_before": (now - timedelta(minutes=1)).isoformat(),
                                "not_after": None,
                                "revoked_at": None,
                            }
                        ],
                    },
                    root_key,
                    b"hive-mind-os/custody-keyset/v1\0",
                )
            )
            profile = self.profile()
            capability = _FakeHardAdapter().capability(profile)
            document = {
                "schema_version": 1,
                "attestation_id": "HICAP-1",
                "authority_id": anchor.authority_id,
                "keyset_sequence": 1,
                "signer_identity": "isolation-authority.example/adapter-attestor",
                "key_id": "adapter-attestor-1",
                "algorithm": "ed25519",
                "audience": "hive-mind-os/hard-isolation/v1",
                "issued_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
                "nonce": "capability-nonce-0001",
                "subject": capability.to_subject(profile),
            }
            authorizer = ExternalCapabilityAuthorizer(
                verifier, CapabilityAttestationProvenance(self.base / "capability-provenance")
            )
            attestation = _signed(
                document, signer_key, b"hive-mind-os/hard-isolation-capability/v1\0"
            )
            authorizer.authorize(profile, capability, attestation)
            conflicting = _signed(
                {**document, "attestation_id": "HICAP-2"},
                signer_key,
                b"hive-mind-os/hard-isolation-capability/v1\0",
            )
            with self.assertRaisesRegex(HardIsolationUnavailable, "replayed"):
                authorizer.authorize(profile, capability, conflicting)
        finally:
            custody_provenance.close()


if __name__ == "__main__":
    unittest.main()
