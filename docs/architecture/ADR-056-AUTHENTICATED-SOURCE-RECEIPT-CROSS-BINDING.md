# ADR-056: Authenticated-Source Receipt Cross-Binding

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-055
- **Prior decisions:** ADR-042, ADR-048, ADR-055
- **Capability maturity:** bounded delivery-integrity correction; no new authority

## Context

ADR-055 allows a source-custody manifest only from the strict authenticated-source lane.
The delivery verifier already rejects such a manifest when any indexed receipt has a
different mission or state from the signed source lock. The exporter, however, could
still publish that inherently unverifiable artifact if a foreign receipt entered its local
receipt collection. Receiver-side rejection is necessary but does not justify creating a
delivery that violates its own manifest contract.

This correction validates existing local receipt metadata. It does not authenticate a
receipt, assert provider execution, or make an untrusted local receipt externally trusted.

## Court record

- **Atomic claim:** every receipt in an authenticated-source delivery must bind the exact
  mission ID and state reference asserted by the signed source lock before export starts.
- **Advocate / Builder:** validate the in-memory receipt collection immediately after the
  strict source-custody recheck and before status, bundle, patch, evidence-copy, or
  manifest work.
- **Cross-examination:** reject a non-mapping record, foreign mission, or foreign state;
  do not strip it, relabel it, or rely on later verification to detect the mistake.
- **Expert testimony:** exact mission/state cross-binding is already the verifier's
  receipt condition. Enforcing it at producer and verifier makes the reversible artifact
  self-consistent without adding a new trust root.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. An exporting workspace with a source lock checks every receipt record against the
   lock's mission ID and state reference. Any mismatch raises before artifact staging.
2. Strict source-custody revalidation remains the preceding gate; local deliveries with
   no source lock retain their existing receipt behavior.
3. The delivery verifier keeps its independent matching check. Producer-side validation
   is an additional fail-closed boundary, not a substitute for verification.

## Migration and rollback

No schema or provenance backfill occurs. A newly found foreign receipt blocks the affected
authenticated export and requires the existing mission reconciliation path. Historic
artifacts remain retained, with no retroactive claim that their receipt set was valid.
Rollback must not claim an artifact with cross-mission receipts is authenticated.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` adds a copied receipt with a foreign
  mission/state to an otherwise strict authenticated workspace and confirms export fails
  without creating a delivery directory.

## Open court obligations

Independent Curator and Judge review remain required. External custody, source safety,
licensing, credential mediation, hostile-code isolation, external retention, and
production authority remain outside this tranche.
