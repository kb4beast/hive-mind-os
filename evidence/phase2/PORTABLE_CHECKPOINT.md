# Portable checkpoint — Phase 2 additive foundation

- Branch: `codex/phase2-additive-memory-telemetry-foundation`
- Stack base: PR #29 exact head `3298078c41ce69103eb2bdce61960a69dc6aab93`
- Current state: implementation candidate; not activated
- Governing ADR: ADR-021
- Court: `evidence/courts/phase2-additive-foundation-court.md`
- Inventory: `evidence/phase2/phase2_foundation_inventory.json`

Implemented:

- 17 strict additive contracts and 9 deterministic inert agent/manifest artifacts;
- private scoped SQLite/WAL foundation store with record chains and transactional
  outbox;
- encounter-first concurrent exact/structured opportunity deduplication;
- semantic-candidate classification without automatic merge;
- provider-shaped native usage observations and orthogonal normalized axes;
- started/terminal attempt receipts, restart interruption recovery, and an opt-in
  provider wrapper;
- append-only delivery attempts/acks, bounded metrics, correlated local traces,
  disabled-export OpenTelemetry envelope, and invoice gap reconciliation;
- explicit authority intersection and privacy/body rejection.

Unchanged:

- Generation Zero runtime selection and stores;
- 131 root APIs, 33 package APIs, 13 CLI contracts;
- legacy schemas/resources and Phase 1 historical inventory;
- Obsidian/Phase 3 and later behavior.

Resume by running deterministic generation check, the Phase 2 tests, full regression,
Ruff, configured Pyright, wheel/resource verification, and the remaining declared
matrix. Then appoint independent Curator/Steward and Judge identities on the exact
committed candidate. Do not activate, merge, or start Phase 3.
