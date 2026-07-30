# Phase 3 item 6 federation and recursion contract

## Scope

This contract governs an optional portfolio vault generated from two to 64 item-3
safe-public cognitive namespaces owned by one tenant, plus deterministic admission
decisions for bounded self-host events.

Generation Zero remains active. Items 1–5 remain unchanged. Private federation,
cross-tenant sharing, network transport, retrieval, Inbox/import, plugins, Sync,
watchers, activation, and merge are excluded.

## Federation invariants

1. A source is a real directory at the exact
   `<source-vault>/hive-mind/generated-cognitive` suffix with a strict
   `hive-cognitive-manifest/v1`; the enclosing source-vault root is derived before
   admission.
2. Every listed file is bounded, stable, single-link, regular, and confined.
3. Every note is strict, `safe-public`, generated, non-authoritative,
   manifest-bound, and scope-consistent.
4. Every source tenant equals the requested portfolio tenant.
5. Repository-instance digests are unique; clones/forks/mirrors are not collapsed.
6. Portfolio bytes omit explicit source `tenant_id`/`repository_id` scope fields and
   use digests or opaque aliases. The portfolio ID, result path, and other upstream
   safe-public provenance are not anonymized.
7. Portfolio notes receive new IDs; source IDs remain provenance only.
8. Payloads are re-parsed, private-field checked, scope-stripped, and rerendered.
9. Sources are read-only. Every source-vault/target pair and every source-vault pair
   must be distinct and mutually non-ancestral.
10. Check mode writes nothing. Projection needs authentic exact-scope authority.
11. First write stages, revalidates exact source trees, and atomically installs with
    no replacement. Exact reruns are `unchanged`; source/target drift, interrupted
    staging, or unmanaged content fails closed without overwrite.
12. Sources, notes, files, paths, bytes, depth, and hops are bounded.

## Self-host decision matrix

| Current event | Origin or state | Result |
| --- | --- | --- |
| evidence ingestion | generated memory | reject |
| projection | generated memory or projection event | reject |
| telemetry | telemetry event | reject |
| idea | generated memory, projection event, or idea event | reject |
| delegation | delegation event | reject |
| any | repeated key or identical origin ID/digest | collapse |
| delegation | excessive hops | reject |
| any | excessive self-host depth | reject |
| self-analysis | missing explicit target | reject |
| changed subject | epoch not strictly newer than matching history | reject |
| otherwise | valid bounded context | accept |

Decision order is normative: repeats collapse first, then kind feedback, hop/depth
limits, target presence, and epoch freshness. Decisions have stable IDs over the
exact context and result. Prior history is bounded and must match controller
build/instance, tenant, lineage, and repository-instance scope.

## Acceptance

- source ordering does not change manifest/tree digests;
- same-tenant sources create only portfolio-local authority;
- explicit source tenant/repository scope fields are absent from output;
- noncanonical source paths; cross-tenant, duplicate, linked, nested, drift, and
  forged-authority cases reject;
- a portfolio beside `hive-mind` but inside a source vault rejects in check and
  project modes with zero source/output mutation; nested source vaults reject;
- Windows junction/reparse redirection, unmanaged directories, interrupted staging,
  source mutation after admission, and destination-creation races reject;
- exact rerun is idempotent;
- every recursion class has a negative test;
- repeats collapse and changed commits require a new epoch;
- five additive schemas are strict and packaged;
- prior Phase 2/3 tests remain green; and
- rollback mutates no source or canonical state.

Zero escape in bounded fixtures is not a general security, privacy, scale,
cross-platform, usefulness, learning, or superiority guarantee.
