# ADR-027: Safe-public portfolio federation and self-host recursion guards

- Status: proposed cross-platform inventory repair; renewed judgment pending
- Date: 2026-07-29
- Base: `376a4a6082f6bdf154ba6252ccb70062a17a549b`
- Governing claims: `MEM-024`, `MEM-025`
- Contract: `PHASE3_FEDERATION_RECURSION_CONTRACT.md`

## Context

Items 1–5 create one safe-public, deterministic cognitive vault per repository.
They intentionally do not combine repositories or decide when Hive Mind OS may
treat its own generated output as new work. The pinned internal redesign record and
adopted design claims `MEM-024`/`MEM-025` require an optional portfolio view without
tenant crossover, nested vault authority, or projection, ingestion, telemetry,
idea, and delegation feedback loops.

The source cognitive manifests identify tenant, repository, and repository-instance
digest, but do not expose enough lineage evidence to reconcile forks, mirrors, or
ordinary clones as one canonical project. Collapsing those identities would be an
unsupported inference.

## Decision

Add one opt-in local module with two independent duties:

1. Accept two to 64 already released, strict item-3 cognitive namespaces at the
   canonical `<source-vault>/hive-mind/generated-cognitive` path from exactly one
   tenant and materialize a portfolio-local namespace.
2. Evaluate an explicit self-host context before generated or self-observed material
   can become another ingestion, projection, telemetry, idea, delegation, or
   self-analysis event.

Federation is a projection, not a shared truth store:

- every source file is manifest-bound, confined, bounded, stable, and hash-checked;
- every admitted note remains `safe-public`, generated, non-authoritative,
  scope-consistent, and private-field-free;
- explicit source `tenant_id` and `repository_id` scope fields are omitted and
  replaced with deterministic digests or aliases;
- portfolio notes receive new local IDs while source IDs remain
  `provenance-only`;
- source vault roots are safely derived from the required canonical namespace;
- source namespaces are never modified;
- portfolio/source and pairwise source-vault nesting, symlinks, Windows reparse
  points/junctions, hardlinks, source drift,
  partial or unmanaged trees, duplicate identity, and cross-tenant sources fail
  closed;
- writes require additive `foundation.federation.write` authority; and
- first publication uses same-volume staging, final source revalidation, and atomic
  no-replace directory rename. Interrupted staging requires explicit operator
  recovery; exact bytes are idempotent and differing bytes are preserved.

The self-host guard records controller, subject, tenant, lineage, repository
instance, parent run, epoch, depth, origin, idempotency key, event kind, and hops.
It collapses exact repeated origins and rejects generated-memory re-ingestion,
projection-on-projection, telemetry-on-telemetry, idea feedback,
delegation-on-delegation, excessive hops/depth, missing self-analysis targets, and
changed subject commits reused inside one observation epoch.

Prior contexts are bounded and must match controller build/instance, tenant,
lineage, and repository instance. A changed subject requires an epoch strictly newer
than matching prior history.

## Alternatives

- No change was rejected for this bounded candidate because it leaves the admitted
  item-6 claims without executable evidence; it remains the rollback.
- A manifest/index-only portfolio was deferred because it does not provide the
  selected inspectable local-note surface; its cost advantage is unmeasured.
- Clearly nonauthoritative deep links were deferred because availability and mutable
  paths remain coupled to each source vault.
- Cross-vault Wikilinks were rejected because mutable vault paths are not canonical
  identity or tenant controls.
- Nested vaults were rejected because they create ambiguous ownership and refresh.
- Verbatim Markdown copies were rejected in favor of revalidation and rerendering.
- A shared writable federated database was deferred because conflict ownership,
  lineage reconciliation, access control, deletion, and distributed recovery are
  not proved.
- Automatically learning from generated portfolio output was rejected as recursion.

## Consequences and limits

This candidate supports deterministic local federation of already released public
projections. It does not implement private or cross-tenant federation, lineage
reconciliation, retrieval, network synchronization, Inbox/import, plugins, watchers,
deletion, activation, or usefulness. The guard is a deterministic admission
primitive, not a persistent scheduler or complete loop detector.

The portfolio manifest intentionally discloses the caller-supplied portfolio
repository ID, and the command result discloses the local namespace path. Other
safe-public provenance values may textually equal a repository name; the projector
does not claim whole-output identifier anonymization.

Explorer novelty-scan exclusion, persistent adapter enforcement, and the normal
challenger/evaluation/promotion path remain explicit later obligations; item 6 does
not implement or claim them.

Changes to source admission, source-vault derivation, identity, tenant policy, guard
precedence, write protocol, authority, or claimed scope require renewed independent
review.
