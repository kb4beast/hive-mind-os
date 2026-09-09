from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from hive_mind_os.evidence_court import (
    ComparatorReceipt,
    ComparatorRegistry,
    ContentAddressedExhibit,
    EvidenceCourtError,
    EvidenceSet,
    PinnedPromotionGrantVerifier,
    PromotionAdapter,
    PromotionGrant,
    evaluate_held_out,
)
from hive_mind_os.identity_attestation import (
    IdentityError,
    PinnedAttestationVerifier,
    PrincipalAttestation,
    principal_attestation_digest,
    verify_role_assignments,
)
from hive_mind_os.runtime_contracts import canonical_json_bytes, raw_sha256

DIGEST = "sha256:" + "a" * 64


def attestation(principal: str, role: str, administrator: str, domain: str) -> PrincipalAttestation:
    credential = raw_sha256((principal + "-credential").encode())
    expires = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    digest = principal_attestation_digest(
        principal_id=principal, administrator_id=administrator,
        trust_domain=domain, credential_digest=credential,
        roles=(role,), expires_at=expires,
    )
    return PrincipalAttestation(
        principal, administrator, domain, credential, (role,), expires, digest,
    )


class EvidenceCourtTests(unittest.TestCase):
    def test_repeated_exhibit_bytes_count_once(self) -> None:
        exhibit = ContentAddressedExhibit.capture(b"same evidence", media_type="text/plain", provenance="fixture")
        evidence = EvidenceSet()
        self.assertTrue(evidence.add(exhibit))
        self.assertFalse(evidence.add(exhibit))
        self.assertEqual(1, evidence.scoreable_count)

    def test_comparator_resolves_only_pinned_licensed_receipt(self) -> None:
        receipt = ComparatorReceipt(
            "tool-a", "v1", DIGEST, "https://example.invalid/tool-a",
            datetime.now(UTC).isoformat(), "Apache-2.0", DIGEST, DIGEST,
        )
        registry = ComparatorRegistry()
        identity = registry.register(receipt)
        self.assertEqual(receipt, registry.resolve(identity))
        with self.assertRaisesRegex(EvidenceCourtError, "license"):
            ComparatorReceipt("tool-b", "v1", DIGEST, "https://example.invalid/b",
                              datetime.now(UTC).isoformat(), "unknown", DIGEST, DIGEST)

    def test_held_out_receipt_evaluates_actual_outcomes(self) -> None:
        receipt = evaluate_held_out(
            sealed_case_digest=DIGEST,
            prediction={"a": "pass", "b": "fail"},
            outcomes={"a": "pass", "b": "pass"},
        )
        self.assertEqual((1, 2), (receipt.passed, receipt.total))
        self.assertTrue(receipt.receipt_digest.startswith("sha256:"))

    def test_actor_strings_cannot_fake_independent_principals(self) -> None:
        proposer = attestation("p1", "proposer", "same-admin", "same-domain")
        judge = attestation("p2", "judge", "same-admin", "same-domain")
        verifier = PinnedAttestationVerifier({
            proposer.principal_id: proposer.attestation_digest,
            judge.principal_id: judge.attestation_digest,
        })
        with self.assertRaisesRegex(IdentityError, "share administrator_id"):
            verify_role_assignments(
                {"proposer": proposer, "judge": judge}, verifier=verifier,
                independently_administered=(("proposer", "judge"),),
            )

    def test_pinned_attestation_fields_cannot_be_substituted(self) -> None:
        original = attestation("p1", "proposer", "admin-a", "domain-a")
        with self.assertRaisesRegex(IdentityError, "does not bind"):
            PrincipalAttestation(
                original.principal_id, "substituted-admin", original.trust_domain,
                original.credential_digest, original.roles, original.expires_at,
                original.attestation_digest,
            )

    def test_promotion_is_disabled_without_separate_authenticated_authority(self) -> None:
        promoted: list[str] = []
        with self.assertRaisesRegex(EvidenceCourtError, "disabled"):
            PromotionAdapter(sink=promoted.append).promote(DIGEST)

        verifier_att = attestation("verifier-principal", "verifier", "verifier-admin", "verifier-domain")
        promoter_att = attestation("promoter-principal", "promoter", "promoter-admin", "promoter-domain")
        verifier = PinnedAttestationVerifier({
            verifier_att.principal_id: verifier_att.attestation_digest,
            promoter_att.principal_id: promoter_att.attestation_digest,
        })
        expires = (datetime.now(UTC) + timedelta(minutes=5)).isoformat()
        fields = {"grant_id": "grant-1", "candidate_digest": DIGEST,
                  "action": "promote-candidate", "authority_principal_id": promoter_att.principal_id,
                  "expires_at": expires}
        grant = PromotionGrant(**fields, grant_digest=raw_sha256(canonical_json_bytes(fields)))
        with self.assertRaisesRegex(EvidenceCourtError, "authenticated authority"):
            PromotionAdapter(enabled=True, verifier=verifier, sink=promoted.append).promote(
                DIGEST, grant=grant,
                role_attestations={"verifier": verifier_att, "promoter": promoter_att},
            )
        receipt = PromotionAdapter(
            enabled=True, verifier=verifier,
            grant_verifier=PinnedPromotionGrantVerifier({grant.grant_id: grant.grant_digest}),
            sink=promoted.append,
        ).promote(
            DIGEST, grant=grant,
            role_attestations={"verifier": verifier_att, "promoter": promoter_att},
        )
        self.assertEqual([DIGEST], promoted)
        self.assertEqual("PROMOTED", receipt["status"])


if __name__ == "__main__":
    unittest.main()
