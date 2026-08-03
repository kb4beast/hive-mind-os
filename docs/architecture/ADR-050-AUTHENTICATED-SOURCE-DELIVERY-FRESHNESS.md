# ADR-050: Authenticated Source Delivery Freshness

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-049
- **Prior decisions:** ADR-043, ADR-048, ADR-049
- **Capability maturity:** bounded delivery-export correction; no new authority

## Context

ADR-048 re-verifies a signed source lock at remote materialization and delivery
verification. ADR-049 ensures that a recovered workspace retains the evidence needed to
place that lock in its manifest. Before this tranche, a Builder could export that manifest
after the lock had expired or its signer had been revoked: export copied cached evidence
without consulting the current source-custody verifier.

An export-time recheck is deliberately narrow. It validates the authority's current
statement about the already pinned repository, commit, mission, and state; it does not
prove source safety, provider ownership, branch protection, hostile-code isolation, or
external immutable retention.

## Court record

- **Atomic claim:** an authenticated-source workspace may export a delivery manifest only
  while its exact sealed lock/evidence/verifier context still validates against the
  original repository, base commit, mission identity, and state reference.
- **Advocate / Builder:** carry the verifier and strictness flag through materialization
  and durable recovery, then re-run ADR-043 materialization binding immediately before
  artifact staging.
- **Cross-examination:** reject partial context, non-durable provenance in the strict
  lane, expired/revoked/tampered evidence, and evidence whose verified lock differs from
  the workspace's sealed lock. Never emit a fallback unauthenticated manifest.
- **Expert testimony:** the source-custody verifier remains the only authentication
  mechanism. This change introduces no signer, key, provider API, remote ref update, or
  policy/governance mutation.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. This record grants no adoption, production, or
  superiority conclusion.

## Decision candidate

1. `GitWorkspace` preserves a complete source-custody context: verified lock, signed
   evidence, verifier, and strictness setting. Any partial context is rejected during
   construction or durable recovery.
2. `export_delivery` re-verifies that context before creating a delivery artifact. The
   check binds the signed repository URL, base commit, mission identity, and state to the
   recovered workspace; strict missions also require durable keyset and source-lock
   provenance.
3. A rejected recheck publishes no directory or manifest. Local workspaces with no source
   context retain their existing, explicitly unauthenticated local behavior.

## Migration and rollback

This is additive and schema-free. Existing local workspaces do not gain an authentication
claim. An authenticated run whose evidence expires before export is blocked and must be
rematerialized or re-admitted under a valid existing source-custody process. Rollback
retains source evidence but must not permit a stale authenticated manifest to be treated
as current.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` confirms recovered source context is
  carried through the strict export path.
- The focused test advances the authority clock beyond the signed lock expiry and proves
  export fails before an artifact directory is published.

## Open court obligations

Independent Curator and Judge review remain required. Source safety, licensing, provider
authentication, credential mediation, hostile-code isolation, external retention, and
production authority remain outside this tranche.
