# Phase 5D Migration and Rollback

## Migration posture

Phase 5D is additive and inactive. It adds package-private Python modules, tests, inventory and
wheel-verification scripts, documentation, and evidence. It does not select a new Curator or
modify the existing P08 runtime Curator.

There is no database, memory, schema-resource, provider, tool, host, scheduler, CLI, root API,
lease, or active-runtime migration.

## Adoption preconditions

A later runtime selection must separately prove authenticated Builder/Curator identity
separation, blind-first execution, externally protected receipts, clean-boundary reproduction,
point-in-time isolation, source/license completeness, rollback authority, and independent Judge
review. Structural tests alone are insufficient.

## Rollback procedure

1. Remove the Phase 5D source modules, focused tests, inventory script, wheel verifier,
   documentation, and evidence.
2. Restore `.github/workflows/ci.yml` and `docs/architecture/ADR_INDEX.md` to the Phase 5C
   integration versions.
3. Restore the preserved Phase 5A–5C current-tree inventories and their chained input digests.
4. Rebuild the wheel and verify the existing 133 governed resources and inherited Phase 5A–5C
   candidates.
5. Confirm the root API, package API, CLI parser set, active P08 Curator, store, and brain bytes
   match the pre-Phase 5D subject.

No data conversion or destructive cleanup is required. Source branches and adverse evidence
must remain preserved.
