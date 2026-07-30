# Phase 4D Explorer idea lifecycle source register

## Exact internal sources

| Source | Exact identity | License/provenance | Atomic use |
|---|---|---|---|
| Phase 4C stack | Git commit `59df5f5f2d0af45f403f74dac9781d2664f227cd` | Repository MIT license; local Git object | Frozen implementation base and final Phase 4C inventory |
| Redesign roadmap | `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` at the base commit | Repository-authored governing design record | Phase 4 item 5 and required encounter/opportunity lifecycle |
| Foundation opportunity ledger | `src/hive_mind_os/foundation/opportunities.py` at the base commit | Repository MIT license | Encounter-first registration and semantic relationship vocabulary |
| Foundation store and memory schema | `src/hive_mind_os/foundation/store.py` and `schemas/memory-record-v1.schema.json` at the base commit | Repository MIT license | Append-only persistence, scoped authority, stable memory references |
| Cognitive projection | `src/hive_mind_os/foundation/cognitive.py` at the base commit | Repository MIT license | Existing independently released opportunity-note path |
| Cognitive views | `src/hive_mind_os/foundation/cognitive_views.py` at the base commit | Repository MIT license | Existing four-Base v1 contract and migration constraint |

## Atomic claims and dispositions requested

1. Every encountered idea needs durable reference evidence, including duplicates and
   explicit early dispositions: `adapt` through existing memory records.
2. Relationship identity must be content-addressed, not tied to duplicate-capable
   database row identity: `adapt`.
3. Court, experiment, and outcome locators may be retained without being represented
   as verified truth: `adapt` with `pinned-unverified`.
4. Direct private-ledger projection or automatic public release would violate the
   existing separation boundary: `reject`.
5. Mutating the v1 Obsidian view file set without a v2 migration would create silent
   mapping drift: `defer`.

No external source was needed for this additive integration slice. No unavailable
source content, artifact body, or license term is invented.
