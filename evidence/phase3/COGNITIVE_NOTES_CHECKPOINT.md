# Portable checkpoint — Phase 3 item 3 stable-ID cognitive notes

- Branch: `codex/phase3-stable-id-cognitive-notes`
- Exact base: draft PR #33 supplied tip
  `40a508b6b1bfb4a8624cf1ef8169384d32a39d44`
- Parent branch: `codex/phase3-public-private-memory-separation`
- Court: `evidence/courts/phase3-stable-id-cognitive-notes-court.md`
- Governing ADR: ADR-024
- Contract: `docs/architecture/PHASE3_COGNITIVE_NOTES_CONTRACT.md`
- Migration/rollback:
  `docs/architecture/PHASE3_ITEM3_MIGRATION_AND_ROLLBACK.md`
- Inventory: `evidence/phase3/phase3_cognitive_notes_inventory.json`
- Draft delivery: pending

## Adapted capability

- Opt-in public-store-only cognitive projection; the private Foundation database is
  unavailable during the deterministic inventory reconstruction.
- Separate `hive-mind/generated-cognitive` namespace with HOME plus idea, evidence,
  court, run, agent, and metadata-only telemetry notes.
- One note per released memory record through an exhaustive fail-closed mapping.
- Domain-separated stable note IDs and full-digest paths independent of mutable
  titles, timestamps, status, content digests, and input order.
- Eight strict packaged contracts for HOME, note, manifest, transaction, receipt,
  conflict, result, and failure.
- External protected journals, desired-byte staging, ownership receipts, and typed
  conflict evidence; manifest-last restart recovery and atomic destination
  no-overwrite.

## Exact evidence

- Implementation:
  `sha256:63e1aed35c9c403fafb488c29e098cb9178f09d9110c6098853431c19fab0b41`
- Inventory:
  `sha256:2340004a3ed91df96e87826ca220c81ad6ca16aaae93f181119a225c4cdc4057`
- Judge disposition: `adapt`
- Judge reproduction: `101 passed, 23 subtests passed`
- Curator final current-byte reproduction: 69 Phase 3 tests and exact inventory
  equality
- Renewed Cross-Examiner: PASS on final junction/source race, unrelated sibling, and
  malformed conflict evidence remands
- Steward: PASS
- Pyright: zero errors and warnings
- Ruff, exact inventory characterization, and diff whitespace: PASS
- Frozen surfaces: `131/33/13/304`; prior schemas: `17/7/3`

## Preserved limits

This is not activation, public prose, a canonical verdict, agent health, canonical
usage/cost accounting, a malicious-writer filesystem transaction, encryption,
cleanup, deletion, usefulness, production readiness, or superiority.

Bases/Canvas, Obsidian integration, federation, self-host recursion, Inbox/import,
plugins, watchers, Sync, retrieval, protected-content bodies, encryption/KMS,
cleanup/deletion, and final-system multi-version/security/supply-chain verification
remain deferred.
