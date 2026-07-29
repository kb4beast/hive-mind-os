# P2-MEMORY-USAGE-FOUNDATION — Quarantined Additive Implementation

- Case: `P2-MEMORY-USAGE-FOUNDATION`
- Source: `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md`, Phase 2
- Source lineage: PR #28 handoff at blob `5674febd4fdd6b9ac8a4be9bc4c003881412ba5a`
- Characterization base: PR #29 exact head `ee00967610df9e7d0ec4a5150bac751cc6880105`
- Burden attempted: implementation candidate only
- Promotion burden: not met
- Independence note: the authoring model performed separated review passes, not
  independently authenticated actors. Independent Curator, Steward, Integrator, and
  Judge receipts remain required.

## Atomic claims

1. Phase 2 needs an additive repository identity and append-only memory contract.
2. Provider-native usage must remain distinct from normalized dimensions.
3. Unknown usage must not be converted to zero or a fabricated total.
4. Memory/usage writes need a same-transaction local outbox before runtime dual-write.
5. Generation-zero runtime and public behavior must remain available and unselected.
6. Supersession, tombstones, delivery, and rollback must preserve prior evidence.
7. Sensitive projection, semantic deduplication, invoices, federation, and learning
   activation are separate obligations and cannot be inferred from this store.
8. Local integrity replay must bind secondary relation/outbox rows back to canonical
   records; checking isolated payload hashes alone is insufficient.
9. Shared SQLite connections must serialize reads as well as writes, while independent
   file connections must establish one valid write order under contention.

## Advocate brief

A real quarantined implementation is more informative than another schema-only record.
SQLite/WAL, append-only triggers, scoped digest chains, restart recovery, native usage
fields, normalized axes, and an outbox can be tested without modifying generation-zero
runtime selection. A sibling package makes the quarantine boundary visible in imports,
wheel installation, and code review.

## Cross-examiner brief

A sibling package can become architectural debt or evade the Phase 1 inventory. Hashes
are not signatures. A local outbox does not prove external delivery or exactly-once
execution. Two local SQLite connections do not prove distributed concurrency.
Sensitivity labels without projection/redaction enforcement do not make records safe.
Provider-native fields are generic contracts, not proven adapter capture. Raw database
access can still bypass the public append API; replay detects drift but does not provide
non-bypassable authenticated mediation. The candidate therefore must not be called
integrated, private, federated, authenticated, distributed, or active.

## Expert findings

### Storage and recovery

`BEGIN IMMEDIATE` serializes each candidate write before reading the previous stream
digest. The repository/memory/usage append and outbox insert share one transaction.
SQLite triggers reject update/delete. File-backed stores use WAL, full synchronization,
foreign keys, an application marker, an exact schema version, and bounded lock waiting.
Reopening the database exercises durable pending-work recovery. Injecting a failure after
the primary record and relation inserts proves those changes roll back when the outbox
append fails. This establishes local single-database properties only.

### Integrity replay

Replay validates database identity/version, foreign keys, SQLite integrity, mandatory
triggers, canonical row fields, repository and payload digests, per-scope chain links,
relation indexes, outbox IDs/digests/types/aggregate linkage, missing expected messages,
and delivery receipt digest shape. It detects drift; it cannot authenticate an actor or
stop a privileged attacker from rewriting every record, digest, and guard consistently.

### Usage semantics

Native fields retain provider paths and nullable observations. Normalized dimensions
use explicit axes, derivations, and a required normalization version. The contract
contains no aggregate token total, preventing the store from silently summing
inclusive/overlapping dimensions. Actual provider adapter conformance is not present.

### Compatibility

The candidate is installed as `hive_mind_os_v2`; no `hive_mind_os.__all__`, CLI,
ledger, mission store, schema resource, runtime pointer, or built-in package manifest is
changed. This preserves the Phase 1 generation-zero fixture while creating a separate
surface that must be inventoried before promotion.

## Disposition

`ADAPT` for quarantined draft implementation and exact-head CI evaluation only.

The implementation may be published as a stacked draft because it is additive,
reversible, explicitly inactive, and executable. It is not adopted as the active
memory or telemetry authority. Promotion remains blocked on:

- independently authenticated review identities and exact-head receipts;
- provider-native adapter fixtures and dual-write reconciliation;
- privacy/redaction and public/private storage enforcement;
- broader crash-window, process-kill, and multi-process stress evidence;
- a current-surface inventory covering the v2 package;
- semantic/exact idea-dedup encounter semantics;
- Obsidian projection conflict handling;
- invoice/cost reconciliation and exporter controls; and
- migration/rollback rehearsal against real generation-zero records.

## Builder evidence before publication

Local isolated draft receipts:

- `python -m unittest discover -s tests -v`: 22/22 focused tests passed;
- two-connection chain test repeated 25 additional times: passed;
- `python -m compileall -q src tests`: passed;
- no external dependencies added;
- Ruff, Pyright, full repository tests, wheel verification, security analysis, and
  exact-head GitHub checks: pending publication.

## Rollback

Delete or abandon the stacked candidate branch/PR. No generation-zero pointer selects
this package. Preserve any produced database and failed CI/review evidence; do not
rewrite it as though the attempt never occurred.
