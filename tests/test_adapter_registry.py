from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

from hive_mind_os.adapter_registry import (
    AdapterRegistration,
    AdapterRegistry,
    AdapterRegistryError,
    AdapterSelection,
    CapabilityAuthority,
)
from hive_mind_os.subject_adapter import SubjectKind

DIGEST = "sha256:" + "b" * 64


def _registration(
    adapter_id: str,
    capabilities: tuple[str, ...],
    *,
    privilege_rank: int = 0,
    vendor: str | None = None,
    validated: bool = False,
) -> AdapterRegistration:
    return AdapterRegistration(
        adapter_id,
        (SubjectKind.REPOSITORY,),
        capabilities,
        ("read",),
        DIGEST,
        (f"review:{adapter_id}",),
        privilege_rank,
        vendor,
        validated,
    )


def _authority(*allowed: str) -> CapabilityAuthority:
    return CapabilityAuthority(tuple(sorted(allowed)), (), ("authority:one",))


class AdapterRegistryTests(unittest.TestCase):
    def test_selection_is_deterministic_and_lowest_sufficient(self) -> None:
        registry = AdapterRegistry()
        registry.register(_registration("builtin.wide", ("analyze", "read", "write")))
        registry.register(_registration("builtin.exact", ("analyze", "read")))
        registry.register(
            _registration(
                "vendor.exact", ("analyze", "read"), vendor="Vendor", validated=True
            )
        )
        selection = registry.select(
            SubjectKind.REPOSITORY,
            ("analyze",),
            _authority("analyze", "read"),
            evidence_refs=("request:one",),
        )
        self.assertEqual("builtin.exact", selection.registration.adapter_id)
        self.assertEqual(selection.selection_digest, selection.selection_digest)

    def test_missing_or_conflicting_authority_is_denied(self) -> None:
        registry = AdapterRegistry()
        registry.register(_registration("builtin.exact", ("analyze", "read")))
        with self.assertRaises(AdapterRegistryError):
            registry.select(
                SubjectKind.REPOSITORY,
                ("analyze",),
                _authority("read"),
                evidence_refs=("request:one",),
            )
        with self.assertRaises(AdapterRegistryError):
            CapabilityAuthority(("read",), ("read",), ("authority:one",))

    def test_unvalidated_third_party_adapter_remains_inert(self) -> None:
        registry = AdapterRegistry()
        with self.assertRaises(AdapterRegistryError):
            registry.register(
                _registration("vendor.one", ("read",), vendor="Vendor", validated=False)
            )
        self.assertEqual({}, dict(registry.registrations))

        with self.assertRaisesRegex(AdapterRegistryError, "strict boolean"):
            _registration(
                "vendor.integer-bypass",
                ("read",),
                vendor="Vendor",
                validated=1,  # type: ignore[arg-type]
            )

    def test_authority_and_selection_digests_bind_the_complete_grant(self) -> None:
        registry = AdapterRegistry()
        registry.register(_registration("builtin.exact", ("analyze", "read")))
        first = CapabilityAuthority(("analyze", "read"), (), ("authority:one",))
        changed_evidence = CapabilityAuthority(
            ("analyze", "read"), (), ("authority:two",)
        )
        narrowed = CapabilityAuthority(("analyze",), (), ("authority:one",))
        self.assertNotEqual(first.authority_digest, changed_evidence.authority_digest)
        self.assertNotEqual(first.authority_digest, narrowed.authority_digest)

        first_selection = registry.select(
            SubjectKind.REPOSITORY,
            ("analyze",),
            first,
            evidence_refs=("request:one",),
        )
        changed_selection = registry.select(
            SubjectKind.REPOSITORY,
            ("analyze",),
            changed_evidence,
            evidence_refs=("request:one",),
        )
        self.assertEqual(first, first_selection.authority)
        self.assertEqual(first.authority_digest, first_selection.authority_digest)
        self.assertNotEqual(
            first_selection.selection_digest, changed_selection.selection_digest
        )

    def test_digest_inputs_require_canonical_immutable_reference_tuples(self) -> None:
        with self.assertRaisesRegex(AdapterRegistryError, "immutable tuple"):
            CapabilityAuthority(
                ["read"],  # type: ignore[arg-type]
                (),
                ("authority:one",),
            )
        with self.assertRaisesRegex(AdapterRegistryError, "immutable tuple"):
            CapabilityAuthority(
                ("read",),
                (),
                ["authority:one"],  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(AdapterRegistryError, "sorted and unique"):
            CapabilityAuthority(("read",), (), ("authority:two", "authority:one"))
        with self.assertRaisesRegex(AdapterRegistryError, "immutable tuple"):
            AdapterRegistration(
                "builtin.mutable",
                (SubjectKind.REPOSITORY,),
                ("read",),
                ("read",),
                DIGEST,
                ["review:mutable"],  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(AdapterRegistryError, "sorted and unique"):
            AdapterRegistration(
                "builtin.unordered",
                (SubjectKind.REPOSITORY,),
                ("read",),
                ("read",),
                DIGEST,
                ("review:two", "review:one"),
            )
        authority = _authority("read")
        registration = _registration("builtin.immutable", ("read",))
        with self.assertRaises(FrozenInstanceError):
            setattr(authority, "evidence_refs", ("authority:changed",))
        with self.assertRaises(FrozenInstanceError):
            setattr(registration, "provenance_refs", ("review:changed",))

    def test_direct_selection_receipts_validate_every_digest_input(self) -> None:
        registration = _registration("builtin.direct", ("analyze", "read"))
        authority = _authority("analyze", "read")
        with self.assertRaisesRegex(AdapterRegistryError, "immutable tuple"):
            AdapterSelection(
                registration,
                SubjectKind.REPOSITORY,
                ("analyze",),
                authority,
                ["request:one"],  # type: ignore[arg-type]
                DIGEST,
            )
        with self.assertRaisesRegex(AdapterRegistryError, "registry_digest"):
            AdapterSelection(
                registration,
                SubjectKind.REPOSITORY,
                ("analyze",),
                authority,
                ("request:one",),
                "not-a-digest",
            )
        with self.assertRaisesRegex(AdapterRegistryError, "sorted and unique"):
            AdapterSelection(
                registration,
                SubjectKind.REPOSITORY,
                ("analyze",),
                authority,
                ("request:two", "request:one"),
                DIGEST,
            )
        with self.assertRaisesRegex(AdapterRegistryError, "contradicts"):
            AdapterSelection(
                registration,
                SubjectKind.REPOSITORY,
                ("analyze",),
                _authority("read"),
                ("request:one",),
                DIGEST,
            )

    def test_registration_is_idempotent_but_substitution_is_rejected(self) -> None:
        registry = AdapterRegistry()
        registration = _registration("builtin.one", ("read",))
        self.assertIs(registration, registry.register(registration))
        self.assertIs(registration, registry.register(registration))
        substituted = AdapterRegistration(
            registration.adapter_id,
            registration.subject_kinds,
            ("analyze", "read"),
            registration.required_authorities,
            registration.implementation_digest,
            registration.provenance_refs,
        )
        with self.assertRaises(AdapterRegistryError):
            registry.register(substituted)


if __name__ == "__main__":
    unittest.main()
