# ADR-021: Quarantined Additive Phase 2 Foundation Namespace

- Status: implementation candidate; quarantined; independent promotion review pending
- Date: 2026-07-28
- Extends: ADR-018, ADR-019, and ADR-020
- Runtime activation: prohibited by this record

## Context

Phase 1 characterized the generation-zero `hive_mind_os` facade, CLI, stored state,
writers, and event producers. Phase 2 must add real memory and provider-native usage
contracts without silently changing those captured behaviors or treating an additive
candidate as the active runtime.

Adding the first v2 implementation directly to the generation-zero package would make
it easy to couple new authority to existing facades before migration, reconciliation,
privacy, and independent promotion evidence exists. Leaving the work as prose would
not exercise SQLite, crash recovery, hash-chain integrity, or transactional-outbox
invariants.

## Decision candidate

Create a separately importable `hive_mind_os_v2` package in the same distribution.
It is a quarantined candidate namespace, not a second product and not a permanent
fork. Its root contract must expose:

- `CANDIDATE_STATUS = "quarantined"`;
- `RUNTIME_ACTIVATED = False`;
- additive v2 repository, memory, usage, cost, privacy, and retention contracts; and
- an append-only SQLite/WAL authority with a same-transaction local outbox.

The generation-zero `hive_mind_os` facade, runtime selection, ledger, mission store,
model backend, CLI, schemas, and package resources remain unchanged in this slice.
No adapter dual-writes to the new store yet. No Obsidian projection, exporter,
watcher, network service, invoice importer, semantic index, or learning policy is
activated.

The sibling namespace is a compatibility and quarantine boundary only. A later,
independently approved migration may move stable contracts behind the canonical
facade, but it must preserve import compatibility or provide an explicit migration.

## Contract and storage invariants

1. Repository identity uses stable tenant/repository scope and a content digest that
   excludes observation time.
2. Memory records are immutable append-only facts. Supersession and tombstones append
   new records rather than updating old ones.
3. Usage events represent one terminal model, tool, or host attempt and retain native
   provider fields separately from versioned normalized axes.
4. Unknown usage remains unknown. The contract exposes no synthetic `total_tokens`
   field and does not sum overlapping cache, reasoning, modality, or billable axes.
5. Prompt and response bodies are not contract fields; only governed digests are
   available in this slice.
6. Repository registration, each memory/usage append, and its outbox message commit in
   one `BEGIN IMMEDIATE` transaction.
7. The dedicated database carries an application marker and exact schema version,
   enables foreign keys, uses `synchronous=FULL`, waits for bounded lock contention,
   and uses WAL for file-backed stores.
8. Repository, memory, relation, usage, outbox, delivery, and schema metadata rows are
   protected from update and deletion by SQLite triggers.
9. Memory and usage streams maintain per-repository digest chains. Integrity replay
   recomputes repository, payload, stream, relation-index, and outbox linkages.
10. Outbox delivery receipts append independently and are idempotent per
    message/consumer. A consumer cannot replace a prior receipt.
11. Cross-repository supersession and writes to unregistered scope fail closed.
12. Every public read and write serializes access to its connection. Two independent
    connections rely on `BEGIN IMMEDIATE`, SQLite locking, and bounded busy timeout to
    preserve one chain order.

## Alternatives considered

### Modify `EvidenceLedger` in place

Rejected for this slice. It would change the frozen generation-zero database shape and
make rollback dependent on a schema migration before dual-write reconciliation exists.

### Add v2 code directly under `hive_mind_os`

Deferred. That would expand the Phase 1 de-facto module surface and effect inventory
before the repository has a versioned current-surface inventory distinct from the
frozen generation-zero fixture.

### Add only JSON schemas or architecture prose

Rejected as insufficient. It would not prove transaction rollback, restart recovery,
append-only enforcement, provider-native/normalized separation, or outbox behavior.

### Activate dual-write from `ModelBackend` immediately

Rejected. Provider adapters still discard native dimensions, and no independent
privacy, reconciliation, migration, or rollback judgment permits runtime activation.

## Threats and controls

- **Namespace becomes a hidden permanent fork:** retain one distribution, document the
  temporary boundary, and require a migration ADR before champion selection.
- **Candidate is mistaken for active capability:** explicit quarantine constants,
  no root-facade export, no CLI entry point, no runtime pointer, and draft-PR wording.
- **Digest chain races:** serialize same-connection work with a process lock and use
  SQLite `BEGIN IMMEDIATE` plus bounded busy timeout across connections.
- **Outbox falsely implies external delivery:** outbox means durable local availability
  only. Delivery requires a separate consumer receipt.
- **Sensitive content enters open memory:** projection is absent and sensitivity is
  explicit, but field-level redaction policy and private/public store separation remain
  blockers before any Obsidian or exporter work.
- **Integrity verification is treated as authenticity:** hashes and database guards
  detect accidental or unsophisticated mutation; they do not establish authenticated
  actor identity or resist an attacker able to rewrite all records and digests.
- **Provider normalization becomes gameable:** native observations are immutable and
  normalized axes retain derivation/version; fair-learning activation remains blocked.
- **Raw SQL bypasses public append methods:** integrity replay compares relation indexes,
  row columns, digest chains, mandatory guards, and outbox rows to canonical records;
  authenticated write mediation remains a later requirement.

## Migration

1. Keep generation zero active and unchanged.
2. Land this package as a quarantined candidate with isolated contract/store tests.
3. Inventory the new candidate namespace and pin deterministic v2 contract fixtures.
4. Add provider fixtures and a governed generation-zero-to-v2 dual-write adapter in a
   separate change.
5. Reconcile counts, outcomes, retries, digests, privacy decisions, and crash windows.
6. Add public/private memory separation and deterministic read-only projection.
7. Promote one reversible consumer pointer only after independent Curator, Steward,
   Integrator, and Judge receipts.
8. Retire the sibling namespace only through an explicit compatibility migration.

## Rollback

No generation-zero path selects this candidate. Rollback therefore removes or disables
only the candidate consumer/branch while preserving any created v2 database as evidence.
Do not rewrite or delete v2 records to simulate rollback. Existing
`hive_mind_os` imports and stores remain the active champion.

## Acceptance for this slice

- Python 3.11, 3.12, and 3.14 execute the deterministic suite;
- the candidate package installs in the wheel and is imported from the isolated wheel;
- generation-zero characterization remains byte-for-byte unchanged;
- repository registration is idempotent but conflicting identity is rejected;
- incompatible database markers, versions, and unmarked non-empty databases fail before the candidate schema is used;
- memory and usage records are append-only, scoped, chained, and replay-verifiable;
- failure after a primary insert but before outbox completion rolls back records,
  relation indexes, and outbox state together;
- native unknown usage remains `null`, normalized axes are unique and versioned, and
  no combined total is manufactured;
- restart recovery retains records and pending outbox work;
- delivery receipts are idempotent, strictly content-addressed, and cannot be replaced;
- two file-backed connections serialize concurrent appends into one valid digest chain;
- integrity replay detects missing guards, relation-index drift, and outbox drift; and
- independent promotion, runtime dual-write, Obsidian projection, semantic dedup,
  provider conformance, privacy completeness, invoice reconciliation, federation, and
  production readiness remain explicitly deferred.
