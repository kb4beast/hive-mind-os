# Phase 1 Generation-Zero Compatibility Boundary

Phase 1 freezes the observable generation-zero surfaces before additive
redesign. The fixture is:

`tests/fixtures/phase1/generation_zero.json`

The executable verifier is:

`tests/test_generation_zero_characterization.py`

Fixture version 2 also binds the generated surface artifact:

`evidence/phase1/generation_zero_surface_inventory.json`

The bounded generator is:

`scripts/phase1_surface_inventory.py`

The production surfaces originated at merged commit
`b032a9f32f48889e0889fae8d6dd04eb03f46b63` and were captured on verified
Phase 0 repair head `0948f7ec385238f5825ce7c39dd25de2e9a1035d`.
Phase 0 changed tests, governance, and evidence rather than these production
surfaces; both identities are retained to avoid ambiguous provenance.

## Captured surfaces

- package version and the complete exported `hive_mind_os.__all__` API,
  including canonical callable and declared public-member signatures;
- all 33 `hive_mind_os.package_system.__all__` bindings and their signatures;
- 13 CLI parser contracts and a separately classified inventory of 304
  de-facto module definitions;
- all eight runtime role contracts and default lifecycle order;
- exact generation-zero prompt digests;
- `hive-core` version, quarantine state, manifest digest, 22 component IDs,
  raw manifest digest, catalog fingerprint, loaded component-contract digest,
  and the aggregate digest of its 47 inventoried resources;
- the 20 formal schema resources and their aggregate digest;
- source-docket counts and the retained `release_ready = false` result;
- SQLite evidence-ledger, mission-store, and scheduler table/column/index/
  trigger shapes, including normalized SQL digests, foreign keys, defaults,
  primary-key positions, nullability, types, and the mission-store schema
  version; and
- the live `ModelResponse` fields, emitted `model.call`/request/context field
  sets, and provider parser observations currently retained by generation
  zero; and
- 48 direct ledger event sinks, 53 event producers, 47 literal event types,
  and 224 bounded persistence/effect sites with exact source receipts.

`package.json` plus its 47 listed files comprise the previously verified 48
`hive-core` package files. The formal schema set is separate, making 68
installed package resources in the clean-wheel boundary.

## What a fixture failure means

A failure is not automatically a defect and must not be “fixed” by refreshing
the expected JSON. It means a public API, role contract, prompt, schema, package
resource, stored-state shape, provider mapping, or truth claim changed.

The change must provide:

1. an originating court disposition;
2. an additive schema/API migration or an explicitly approved break;
3. old/new deterministic fixtures;
4. a rollback path and retained prior fixture;
5. compatibility and installed-wheel receipts; and
6. independent Curator and Judge evidence.

Phase 1 itself changes no captured production surface.
