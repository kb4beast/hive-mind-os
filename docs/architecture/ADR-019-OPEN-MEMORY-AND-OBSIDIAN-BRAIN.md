# ADR-019: Open Memory Authority and Obsidian Brain Projection

- Status: Phase 1 candidate; implementation deferred pending independent judgment
- Date: 2026-07-28
- Constitutional impact: yes

## Context

Generation zero has append-only evidence and lesson tables, mission
checkpoints, prompt lineage, receipts, source exhibits, and read-only
projections. It has no unified memory record, complete replay, federated
repository identity, or Obsidian projection.

Opening the repository root as an Obsidian vault already provides a useful
read-only Markdown workbench. Obsidian is not required as a Python execution
host and its presence does not close the durable-memory gap.

At Phase 1 capture, the clean repository has no `.obsidian/` directory and does
not ignore it. The candidate initial policy is local-only configuration with
the whole directory ignored. Any later curated team settings require a
separate source/security/update review and must exclude workspace layouts,
machine paths, plugin state, caches, and secrets.

## Decision candidate

Adopt an open, local-first append-only memory authority with explicit
repository/tenant scope, stable record IDs, type/schema version, provenance,
digests, timestamps, sensitivity, retention, confidence, status, relations,
and supersession/tombstone semantics.

Build a deterministic Markdown brain projection over that authority. Generated
notes are nonauthoritative, labeled, safe to regenerate, and isolated from a
separate governed human-intake namespace. The OS remains usable without
Obsidian.

## Threat and privacy model

- Prompt injection or executable content inside notes;
- secrets or private memory exposed through search, Git, Sync, graph, Canvas,
  or plugins;
- generated notes re-ingested as original ideas;
- concurrent human edits silently overwritten;
- stale projections misrepresented as current truth;
- repository/tenant crossover during federation;
- deletion demands falsifying append-only provenance; and
- a community plugin or sync client becoming an unreviewed writer.

Projection must default-deny sensitive records, sanitize unsafe content,
record redactions, stage output, compare the expected prior digest, atomically
replace, preserve conflicts, and stop the conflicted record. Deletion uses a
policy-governed tombstone and crypto/deletion procedure while retaining the
minimum non-sensitive audit fact allowed by policy.

## Migration

1. Define additive v2 memory records and repository identity.
2. Dual-write through a local transactional outbox while retaining existing
   ledger and mission stores.
3. Backfill deterministic records with original source references; do not
   invent missing lineage.
4. Verify old-store versus new-record reconciliation.
5. Add CLI/editor-readable Markdown projection before any watcher or intake.
6. Add federation and governed Inbox only under separate courts.

## Rollback

Disable the v2 writer/projector pointer and continue the unchanged
generation-zero stores. Do not delete v2 records or conflicts. Regenerate the
last independently verified projection or remove only its generated namespace
after exact-path validation; human-authored notes remain untouched.

## Observability and evaluation

Required signals include outbox lag, projection age, conflict count,
redaction/rejection count, orphan/duplicate/tombstone count, replay
completeness, retrieval precision/recall, stale-memory rate, contamination
rate, cross-tenant escape rate, and memory-attributed outcome lift. High-cardinality
record identifiers belong in traces/records, not metric labels.

Acceptance requires deterministic regeneration, crash/restart recovery,
conflict preservation, no export re-ingestion, privacy tests, complete
generation-zero reconciliation, and useful retrieval under sealed
contamination-resistant evaluation.
