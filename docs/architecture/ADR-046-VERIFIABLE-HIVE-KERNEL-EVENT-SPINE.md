# ADR-046: Verifiable Hive Kernel append-only event spine

## Status

Proposed. This is a bounded Phase 2 candidate, not a claim that the full Verifiable
Hive Kernel, all eight roles, a scheduler, an effect gateway, or an independent court
disposition exists.

## Context

Phase 1 supplied immutable, repository-neutral contracts but intentionally persisted
nothing. The preserved Verifiable Hive Kernel handoff requires a single durable source
of truth for *new* kernel missions before later planning, authority, memory, effect,
and worker phases can be connected. Existing mission stores, ledgers, receipts, and
projections remain authoritative for their established commands and histories.

## Decision

Add `brain_kernel.events`, `brain_kernel.store`, and `brain_kernel.projection` as an
additive SQLite-backed kernel event spine. Events are canonical UTF-8 JSON facts,
linked by a digest over their canonical fields and their predecessor digest. The store
requires the supplied predecessor to match the chain head, supports an optimistic
expected sequence, and rejects event-id or idempotency-key rebinding.

The `events` table has database-enforced no-update/no-delete triggers. Appending an
event, binding its idempotency key, and rebuilding the derived mission/work views occur
in one SQLite transaction. Reducers accept only the Phase 2 mission/work creation and
legal transition events; unknown, out-of-order, cross-mission, or illegal events fail
closed. Mutable views are rebuilt from sequence one whenever the store opens and by the
explicit rebuild helper; they are never an authority.

Snapshots are non-authoritative caches. Their digest and recorded sequence are checked
against a replay of the event spine; any malformed or mismatched snapshot is discarded
and replaced from canonical events. The migration/bootstrap path records schema version
one and replaces only the rebuildable Phase 2 work projection if an early local preview
lacks its mission ownership column.

`hive-mind kernel status MISSION_ID --state-dir STATE_DIR [--json]` reads an existing
`brain-kernel.sqlite3` and reports an event-derived mission status, work list, last
sequence, and state digest. It does not create missing state, execute effects, or
mutate a legacy mission path.

Existing evidence-ledger and receipt artifacts are not copied or reinterpreted in this
phase. Later adapters may reference their immutable identifiers from event payloads;
the body and lifecycle of those artifacts remain with their existing stores.

## Consequences and rollback

Phase 2 introduces one additive local database format, `kernel_metadata` schema
version `1`, and no migration of an existing mission database. Rollback consists of
removing the additive `brain_kernel` database and Phase 2 package/CLI files; it does
not modify legacy stores, receipt bodies, or external systems. Existing commands retain
their behavior.

## Evidence obligations

The deterministic tests cover restart/replay, wrong chain heads, trigger-enforced
immutability, illegal transitions, transaction rollback, idempotency, concurrent
unique ordering, corrupt snapshots, portable state paths, and status over a fixture
database. An Advocate, Cross-Examiner, Expert Witness, independently identified
Curator, and Judge must still make the required courtroom dispositions before any
promotion claim.
