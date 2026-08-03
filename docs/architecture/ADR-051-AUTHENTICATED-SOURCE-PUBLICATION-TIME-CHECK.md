# ADR-051: Authenticated Source Publication-Time Check

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-050
- **Prior decisions:** ADR-043, ADR-048, ADR-050
- **Capability maturity:** bounded publication-time correction; no new authority

## Context

ADR-050 validates authenticated source evidence before delivery export begins. Export then
generates a bundle and patch, copies receipt evidence, validates the staged index, and
atomically publishes the directory. A short-lived signed lock can expire after the first
check and before publication. Publishing a manifest with evidence that is stale at the
actual publication boundary would weaken ADR-050's freshness claim.

This correction does not extend the signed validity window, fetch new source, approve
code safety, change repository governance, or add a privileged delivery channel.

## Court record

- **Atomic claim:** an authenticated delivery is published only if its sealed source
  custody context remains valid immediately before its manifest is staged for atomic
  publication.
- **Advocate / Builder:** retain the early check for fail-fast behavior and add an exact
  second check after bundle/evidence staging but before `delivery.json` is written.
- **Cross-examination:** require cleanup with no output directory when the second check
  detects expiry, revocation, tampering, missing provenance, or source-binding mismatch;
  do not turn an earlier successful check into a grace period.
- **Expert testimony:** the existing external source-custody verifier decides validity.
  This change only closes a local time-of-check-to-publication gap.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No production or superiority conclusion is authorized.

## Decision candidate

1. `export_delivery` validates source custody before work and again after all staged
   bytes and receipt-index checks, immediately before writing the manifest that triggers
   artifact publication.
2. A failed final check aborts the staging context. Its temporary data is removed and no
   artifact root, bundle, patch, evidence directory, or manifest is published.
3. Local workspaces without source custody retain their local delivery behavior. The
   second call neither creates credentials nor changes source, provider, or governance
   authority.

## Migration and rollback

This schema-free correction is additive. Authenticated delivery attempts may now fail when
evidence expires during staging; they must be retried only after the existing external
source-custody process supplies valid evidence. Rollback retains source evidence and must
not recast a stale manifest as current authentication.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` advances the trusted verifier clock
  only after the initial export check, then confirms the final check rejects publication
  and leaves no delivery directory.

## Open court obligations

Independent Curator and Judge review remain required. Source safety, licensing, provider
authentication, credential mediation, hostile-code isolation, external retention, and
production authority remain outside this tranche.
