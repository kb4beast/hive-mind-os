from __future__ import annotations

import unittest
from dataclasses import replace

from hive_mind_os.brain_kernel.authority import (
    AuthorityDenied,
    AuthorityRegistry,
    RootProvenance,
)
from hive_mind_os.brain_kernel.contracts import Budget, ConstraintEnvelope, EffectIntent
from hive_mind_os.brain_kernel.effects import EffectGateway

DIGEST = "sha256:" + "0" * 64
ISSUER = "owner:fixture"
AUTHORITY_REF = "AUTHORITY-RECORD-one"
MINTED_AT = "2026-01-01T00:00:00Z"


def envelope(
    *,
    envelope_id: str = "AUTH-one",
    parent: str | None = None,
    allowed: tuple[str, ...] = ("write",),
    denied: tuple[str, ...] = ("push", "merge", "deploy"),
    read_scope: tuple[str, ...] = ("src",),
    write_scope: tuple[str, ...] = ("src",),
    budgets: Budget = Budget(1, 0, 0, 0, 0, 0, 1, 1),
    expires_at: str = "2030-01-01T00:00:00Z",
    seal: bool = True,
) -> ConstraintEnvelope:
    unsealed = ConstraintEnvelope(
        envelope_id,
        "MISSION-one",
        "WORK-one",
        parent,
        "builder",
        "R1",
        allowed,
        denied,
        read_scope,
        write_scope,
        (),
        (),
        (),
        (),
        budgets,
        expires_at,
        DIGEST,
        DIGEST,
    )
    return unsealed.sealed() if seal else unsealed


def mint(registry: AuthorityRegistry, granted: ConstraintEnvelope) -> RootProvenance:
    return registry.mint_root(
        granted, issuer=ISSUER, authority_ref=AUTHORITY_REF, recorded_at=MINTED_AT
    )


AUTH = envelope().digest_value


class AuthorityTests(unittest.TestCase):
    def test_scope_expiry_revocation_and_action_denials_fail_closed(self) -> None:
        registry = AuthorityRegistry()
        granted = envelope()
        mint(registry, granted)
        token = registry.authorize(
            AUTH, "write", "src/one.py", now="2029-01-01T00:00:00Z"
        )
        self.assertEqual("src/one.py", token.target)
        with self.assertRaises(AuthorityDenied):
            registry.authorize(AUTH, "write", "other.py", now="2029-01-01T00:00:00Z")
        with self.assertRaises(AuthorityDenied):
            registry.authorize(AUTH, "push", "src/one.py", now="2029-01-01T00:00:00Z")
        registry.revoke(AUTH)
        with self.assertRaises(AuthorityDenied):
            registry.authorize(
                AUTH, "write", "src/one.py", now="2029-01-01T00:00:00Z"
            )

    def test_gateway_requires_matching_token_and_deduplicates(self) -> None:
        registry = AuthorityRegistry()
        mint(registry, envelope())
        token = registry.authorize(
            AUTH, "write", "src/one.py", now="2029-01-01T00:00:00Z"
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
            AUTH,
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
                intent, type(token)(AUTH, "write", "src/other.py", DIGEST)
            )


class EnvelopeSealTests(unittest.TestCase):
    """A5-F3: the registry admits only an envelope whose digest seals its contents."""

    def test_registry_refuses_an_envelope_whose_digest_is_not_its_content_digest(
        self,
    ) -> None:
        registry = AuthorityRegistry()
        claimed = envelope(seal=False)
        self.assertEqual(DIGEST, claimed.digest_value)
        with self.assertRaisesRegex(AuthorityDenied, "does not seal its contents"):
            mint(registry, claimed)
        self.assertIsNone(registry.root_provenance(DIGEST))

    def test_two_authorities_cannot_share_one_digest(self) -> None:
        registry = AuthorityRegistry()
        narrow = envelope()
        broad = envelope(allowed=("write", "push", "deploy"), denied=(), write_scope=("src", "docs"))
        mint(registry, narrow)
        self.assertNotEqual(narrow.digest_value, broad.digest_value)
        # Cheat: claim the admitted narrow envelope's digest while carrying broader authority.
        forged = replace(broad, digest_value=narrow.digest_value)
        with self.assertRaisesRegex(AuthorityDenied, "does not seal its contents"):
            mint(registry, forged)
        with self.assertRaisesRegex(AuthorityDenied, "action is not granted"):
            registry.authorize(
                narrow.digest_value, "push", "src/one.py", now="2029-01-01T00:00:00Z"
            )


class RootMintTests(unittest.TestCase):
    """A5-F4: a root authority exists only through a recorded ceremony."""

    def test_bare_root_registration_is_refused_and_the_ceremony_records_provenance(
        self,
    ) -> None:
        registry = AuthorityRegistry()
        root = envelope()
        # Cheat: mint a fresh root in-process through the ordinary path.
        with self.assertRaisesRegex(AuthorityDenied, "explicit mint ceremony"):
            registry.register(root)
        with self.assertRaises(AuthorityDenied):
            registry.authorize(AUTH, "write", "src/one.py", now="2029-01-01T00:00:00Z")
        # Positive control: the ceremony admits the same root and records who minted it.
        record = mint(registry, root)
        self.assertEqual(
            (root.digest_value, ISSUER, AUTHORITY_REF, MINTED_AT),
            (record.envelope_digest, record.issuer, record.authority_ref, record.recorded_at),
        )
        self.assertEqual(record, registry.root_provenance(root.digest_value))
        self.assertEqual(
            "src/one.py",
            registry.authorize(AUTH, "write", "src/one.py", now="2029-01-01T00:00:00Z").target,
        )

    def test_ceremony_refuses_an_unattributed_or_undated_mint(self) -> None:
        registry = AuthorityRegistry()
        with self.assertRaisesRegex(AuthorityDenied, "recorded issuer"):
            registry.mint_root(
                envelope(), issuer="  ", authority_ref=AUTHORITY_REF, recorded_at=MINTED_AT
            )
        with self.assertRaisesRegex(AuthorityDenied, "authority reference"):
            registry.mint_root(
                envelope(), issuer=ISSUER, authority_ref="", recorded_at=MINTED_AT
            )
        with self.assertRaisesRegex(AuthorityDenied, "RFC 3339"):
            registry.mint_root(
                envelope(), issuer=ISSUER, authority_ref=AUTHORITY_REF, recorded_at="whenever"
            )
        self.assertIsNone(registry.root_provenance(AUTH))


class RevocationTests(unittest.TestCase):
    """A5-F5: revocation binds the authority, not the digest string."""

    def test_revoked_authority_cannot_be_reminted_under_a_new_digest(self) -> None:
        registry = AuthorityRegistry()
        root = envelope()
        mint(registry, root)
        registry.revoke(root.digest_value)
        # Cheat: re-mint the identical authority under a different envelope identity.
        remint = envelope(envelope_id="AUTH-one-again")
        self.assertNotEqual(root.digest_value, remint.digest_value)
        self.assertEqual(root.authority_key(), remint.authority_key())
        with self.assertRaisesRegex(AuthorityDenied, "authority is revoked"):
            mint(registry, remint)
        with self.assertRaises(AuthorityDenied):
            registry.authorize(
                remint.digest_value, "write", "src/one.py", now="2029-01-01T00:00:00Z"
            )
        # Positive control: a genuinely different authority still mints.
        narrower = envelope(envelope_id="AUTH-two", write_scope=())
        mint(registry, narrower)
        self.assertIsNotNone(registry.root_provenance(narrower.digest_value))

    def test_revoking_a_parent_refuses_its_already_admitted_descendant(self) -> None:
        registry = AuthorityRegistry()
        root = envelope()
        mint(registry, root)
        child = envelope(
            envelope_id="AUTH-child",
            parent=root.digest_value,
            denied=("push", "merge", "deploy", "network"),
        )
        self.assertNotEqual(root.authority_key(), child.authority_key())
        registry.register(child)
        self.assertEqual(
            "src/one.py",
            registry.authorize(
                child.digest_value, "write", "src/one.py", now="2029-01-01T00:00:00Z"
            ).target,
        )
        registry.revoke(root.digest_value)
        with self.assertRaisesRegex(AuthorityDenied, "unavailable"):
            registry.authorize(
                child.digest_value, "write", "src/one.py", now="2029-01-01T00:00:00Z"
            )


class ParentResolutionTests(unittest.TestCase):
    """A5-F13: the parent comes from the registry, never from the caller."""

    def test_caller_supplied_parent_the_registry_never_admitted_is_refused(self) -> None:
        registry = AuthorityRegistry()
        root = envelope()
        mint(registry, root)
        wide = envelope(
            envelope_id="AUTH-wide",
            allowed=("write", "push", "deploy"),
            denied=(),
            write_scope=("src", "docs"),
        )
        # Cheat: hand in a wide parent object the registry has never seen.
        orphan_child = envelope(
            envelope_id="AUTH-child",
            parent=wide.digest_value,
            allowed=("write", "push"),
            denied=(),
            write_scope=("src", "docs"),
        )
        with self.assertRaisesRegex(AuthorityDenied, "parent envelope is required"):
            registry.register(orphan_child, wide)
        # Cheat: claim the admitted parent's slot while presenting a different object.
        bound_child = envelope(envelope_id="AUTH-child", parent=root.digest_value)
        with self.assertRaisesRegex(AuthorityDenied, "not the admitted authority"):
            registry.register(bound_child, wide)
        # Positive control: the registry resolves the parent itself.
        registry.register(bound_child)
        self.assertEqual(
            "src/one.py",
            registry.authorize(
                bound_child.digest_value, "write", "src/one.py", now="2029-01-01T00:00:00Z"
            ).target,
        )

    def test_registry_resolved_parent_still_refuses_a_broadening_child(self) -> None:
        registry = AuthorityRegistry()
        root = envelope()
        mint(registry, root)
        broadening = envelope(
            envelope_id="AUTH-child",
            parent=root.digest_value,
            allowed=("write", "push"),
            denied=(),
        )
        with self.assertRaisesRegex(AuthorityDenied, "broadens"):
            registry.register(broadening)


class ActionScopeTests(unittest.TestCase):
    """A5-F11: every declared action is target-scoped, reads against the read scope."""

    def granted(self) -> tuple[AuthorityRegistry, ConstraintEnvelope]:
        registry = AuthorityRegistry()
        granted = envelope(
            allowed=("write", "push", "read"),
            denied=("merge", "deploy"),
            read_scope=("docs",),
            write_scope=("src",),
        )
        mint(registry, granted)
        return registry, granted

    def test_a_non_write_action_is_refused_outside_the_write_scope(self) -> None:
        registry, granted = self.granted()
        # Cheat: spend a granted non-write action on a target no scope covers.
        with self.assertRaisesRegex(AuthorityDenied, "outside write scope"):
            registry.authorize(
                granted.digest_value, "push", "somewhere/else.txt", now="2029-01-01T00:00:00Z"
            )
        # Positive control: the same action inside the write scope is authorized.
        self.assertEqual(
            "src/one.py",
            registry.authorize(
                granted.digest_value, "push", "src/one.py", now="2029-01-01T00:00:00Z"
            ).target,
        )

    def test_a_read_action_is_bound_to_the_read_scope(self) -> None:
        registry, granted = self.granted()
        self.assertEqual(
            "docs/x.md",
            registry.authorize(
                granted.digest_value, "read", "docs/x.md", now="2029-01-01T00:00:00Z"
            ).target,
        )
        # Cheat: read a path only the write scope covers.
        with self.assertRaisesRegex(AuthorityDenied, "outside read scope"):
            registry.authorize(
                granted.digest_value, "read", "src/one.py", now="2029-01-01T00:00:00Z"
            )


if __name__ == "__main__":
    unittest.main()
