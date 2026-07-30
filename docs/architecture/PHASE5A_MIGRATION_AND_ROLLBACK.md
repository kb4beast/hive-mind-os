# Phase 5A migration and rollback

## Migration posture

Phase 5A is additive and inactive. It adds ordinary Python modules, tests, evidence, and CI
verification. It does not alter:

- root or package exports;
- CLI parsers;
- Generation Zero role behavior;
- Foundation database schema or authority mapping;
- public/private memory stores;
- projectors, Obsidian views, or federation;
- Explorer v2 runtime state;
- package JSON resources; or
- provider, tool, host, scheduler, or deployment configuration.

No automatic backfill, dual write, pointer switch, or data migration occurs.

## Development use

An explicit caller may import the package-private compiler and supply a strict request. The
result is development metadata only. It must not be used as proof that work ran, roles were
independent, budgets were enforced, or completion was authorized.

## Future binding prerequisites

Before any active binding, a later court must provide:

1. authenticated actor and authority receipts;
2. durable mission, plan, checkpoint, and handoff storage;
3. real hierarchical budget leases with rollback reserve enforcement;
4. scheduler interruption, concurrency, replay, and compensation tests;
5. held-out Orchestrator behavioral evaluation;
6. host/provider/tool conformance;
7. privacy, retention, and tenant-isolation review;
8. reversible pointer migration; and
9. independent Curator and Judge authorization.

## Rollback procedure

1. Stop any explicit development imports of the candidate.
2. Remove the Phase 5A modules and tests.
3. Remove the Phase 5A inventory and evidence documents only through a new reviewed change;
   retain published Git history as evidence.
4. Revert the ADR index and CI wheel-verification additions.
5. Re-run the complete Generation Zero and Phase 2–4 compatibility suite.

No database deletion or history rewrite is required. The active champion remains the existing
Generation Zero path throughout.
