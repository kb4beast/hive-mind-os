# PR #30 supersession and atomic disposition

- Historical candidate: `39e07c9e3c3ce439911481be2d38d901d05d4824`
- Selected successor base: PR #31, `94e67cde15fa8a75d92561384241f0419c9f589b`
- Historical ADR key: `ADR-021-PR30`
- Selected ADR key: `ADR-021-PR31`
- Overall disposition: **adapt** the useful contracts into the canonical foundation;
  retain the exact losing implementation as ancestry; do not activate either design.

## Atomic claim map

| PR #30 claim or artifact | Disposition | Selected resolution |
|---|---|---|
| Separate `hive_mind_os_v2` namespace | reject as the selected runtime shape | Canonical additive implementation lives under private `hive_mind_os.foundation`; no root facade or CLI selector activates it. |
| Explicit quarantined/inactive constants | adapt | Inactivity is enforced structurally through absent root exports, absent CLI selection, scoped authority, opt-in construction, and court boundaries rather than a second product namespace. |
| Stable tenant/repository identity | adopt and expand | `repository-identity-v1`, immutable registration, controller/lineage fields, authority receipts, and scope validation are selected. |
| Immutable memory facts, relations, supersession, and tombstones | adopt and expand | `memory-record-v1`, append-only records/relations, status, contradiction and reference fields, public-release evidence, and integrity replay are selected. |
| Provider-native usage kept separate from normalized dimensions | adopt and expand | Provider-shaped fixture adapters, native provenance, versioned normalized axes, explicit unknown/conflicting accounting, reconciliation, and no manufactured aggregate are selected. |
| Cost, privacy, sensitivity, and retention fields | adapt | The selected schemas retain governed cost/provenance and private-by-default policy; complete privacy, consent, deletion, and invoice claims remain deferred. |
| Dedicated SQLite/WAL store, foreign keys, `synchronous=FULL`, bounded waits | adopt | The selected `FoundationStore` retains these local durability controls. |
| `PRAGMA application_id` plus `user_version` ownership | adapt | The selected store uses an exact metadata ownership marker, schema version, schema digest, required shape, and `user_version`; the distinct numeric application ID is not selected. |
| Same-transaction record and local outbox | adopt and expand | Records and outbox messages commit together; delivery attempts and acknowledgements are separately append-only and authority-scoped. |
| Append-only triggers | adopt and expand | Required tables have immutable update/delete triggers and shape/integrity verification. |
| Per-scope digest chains and integrity replay | adopt and expand | Canonical payload, command, stream, relation, opportunity-key, outbox, authority, and schema invariants are verified. |
| Two-connection contention behavior | adopt and expand | `BEGIN IMMEDIATE`, bounded timeout, process locking, restart recovery, and later adversarial concurrency tests are selected. |
| Wheel must contain the candidate package | reject as obsolete packaging | The wheel instead contains canonical foundation modules and 133 governed JSON resources verified from an isolated install. |
| PR #30 focused tests | adapt | Equivalent invariants are covered by `test_phase2_foundation.py` and the later Phase 3/4 regression chain; the original tests remain available at the historical commit. |
| PR #30 ADR, implementation guide, and court record | preserve as historical evidence | Exact ancestry plus `ADR-021-PR30` and this map retain their provenance without introducing duplicate active authorities. |
| No dual-write, projection, provider-conformance, learning, or production claim | adopt | Those limitations remain binding; later phases add only inert, opt-in candidates and `B-OPS-09`/P20 remain open. |

## Tree-selection invariant

The selected tree must not contain `src/hive_mind_os_v2`,
`tests/test_v2_memory_usage_foundation.py`, or the obsolete PR #30 implementation
guide. Their absence is not evidence loss because the exact historical commit is a
required ancestor and is named in the release manifest.

## Dissent and residual risk

- A tree-neutral merge preserves exact ancestry and bytes but does not make PR #30 independently
  approved.
- The accepted foundation remains a candidate, not an activated champion.
- Local hashes and SQLite guards are integrity mechanisms, not authenticated identity.
- The selected implementation may still omit useful details from the historical
  candidate; future appeals must cite the exact row above rather than silently copying
  code.
