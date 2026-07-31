# Phase 5C Migration and Rollback

## Migration posture

Phase 5C is additive and inert. It changes no active pointer, selector, public facade, CLI,
provider, host, tool, scheduler, store, schema migration, package JSON resource, or execution
path. There is no data migration.

The only integration changes are:

- package-private Builder modules;
- focused tests and deterministic inventory tooling;
- an isolated-wheel verifier in Constitutional CI;
- architecture and evidence records; and
- reconciliation of the Phase 5A and Phase 5B current-tree inventories affected by the shared
  CI and ADR-index changes.

## Forward procedure

1. Materialize the exact Phase 5A-5B head in an isolated branch/worktree.
2. Add the Builder contracts and compiler without facade or runtime registration.
3. Run focused contract, hostile, traceability, recovery, resource, resealing, and compatibility
   tests.
4. Regenerate inventories and verify byte-for-byte equality.
5. Build and install the wheel in a clean target and run all inherited verifiers plus the new
   Phase 5C verifier.
6. Run the complete hosted CI matrix on the exact candidate head.
7. Keep the PR draft and candidate inert. Do not merge into the release branch without an
   explicit user instruction and the applicable evidence.

## Rollback procedure

1. Revert the Phase 5C normal commit(s); do not rewrite or squash history.
2. Remove the Phase 5C source, tests, scripts, documents, and evidence.
3. Restore the prior `.github/workflows/ci.yml` and ADR index.
4. Restore the prior Phase 5A and Phase 5B inventory JSON and Phase 5B input-digest constant.
5. Re-run the complete test suite and inherited installed-wheel verifiers.
6. Verify root/package APIs, CLI parsers, 133 package resources, stores, runtime selectors, and
   the release integration audit match the pre-Phase-5C baseline.

No source branch is deleted. Existing Phase 5A, Phase 5B, Generation Zero, Foundation, memory,
projection, federation, and runtime data remain usable because Phase 5C writes none of them.

## Automatic rollback triggers

Rollback or quarantine the candidate if any exact-head evidence shows:

- root API, package API, CLI, resource, store, provider/tool/host/scheduler, or runtime drift;
- authority, capability, tool, execution, result, completion, promotion, or activation
  escalation;
- semantic resealing acceptance;
- incomplete requirement/change/test/evidence/artifact/rollback coverage;
- unknown or incompatible dependency/license use;
- non-reproducible inventories or installed-wheel behavior;
- a failing required hosted job; or
- a false claim of authenticated independence, production readiness, release readiness, value,
  or superiority.
