# ADR-055: Strict Authenticated-Source Delivery Admission

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-054
- **Prior decisions:** ADR-043, ADR-048, ADR-050
- **Capability maturity:** bounded delivery-claim correction; no new authority

## Context

`GitWorkspace.materialize` supports a lower-level signed source-lock check for bounded
adapter use, while ADR-048 requires durable source and keyset provenance for an
authenticated remote repository mission. Before this tranche, either context could export
a `source_custody` delivery manifest. A non-strict lane can lack the durable provenance
required for resumed and independently verifiable authenticated-source delivery, so that
manifest would overstate its custody posture.

This correction does not change local delivery, turn a local source into an authenticated
one, add a signer or credentials, or change source/provider/governance authority.

## Court record

- **Atomic claim:** a delivery manifest may contain authenticated source custody evidence
  only when the workspace was admitted through strict source custody with durable source
  and keyset provenance.
- **Advocate / Builder:** require `require_source_custody=True` whenever a complete
  source-lock/evidence/verifier context reaches export; otherwise abort before staging.
- **Cross-examination:** do not silently omit the manifest field, downgrade the remote
  result to local, or accept an in-memory/provenance-optional lane merely because a
  signature verifies at one moment.
- **Expert testimony:** strictness is already the ADR-048 durability boundary. The new
  check makes it a precondition for the public delivery claim rather than a metadata hint.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. Any complete source-custody context at `export_delivery` must have the strict flag.
   A non-strict context raises before directory creation, bundle/patch generation, or
   manifest staging.
2. The existing strict recheck continues to require durable keyset and source-lock
   provenance, current signature validity, and exact repository/base/mission/state
   bindings.
3. Workspaces with no source context keep the existing explicitly local delivery lane.

## Migration and rollback

This is additive and schema-free. A lower-level remote workspace that needs a delivery
artifact must restart through the existing strict ADR-048 admission path. Historic
artifacts are retained and not retroactively relabeled. Rollback must not describe a
non-strict source manifest as durable authenticated custody.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` gives a complete source context a
  non-strict flag and confirms export rejects it without creating a delivery directory.

## Open court obligations

Independent Curator and Judge review remain required. External retention, source safety,
licensing, credential mediation, hostile-code isolation, and production authority remain
outside this tranche.
