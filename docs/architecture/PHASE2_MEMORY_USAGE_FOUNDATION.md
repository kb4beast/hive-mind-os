# Phase 2 Memory and Usage Foundation

## Delivered boundary

This slice introduces a real but quarantined `hive_mind_os_v2` package. It does not
change the active `hive_mind_os` runtime.

The candidate includes:

- stable repository/tenant identity;
- append-only memory records with relations, supersession, and tombstones;
- provider-native terminal attempt receipts;
- versioned normalized usage axes without synthetic totals;
- cost provenance, privacy sensitivity, and retention fields;
- per-repository memory and usage digest chains;
- a dedicated SQLite database identity and exact schema version;
- file-backed WAL, full synchronization, foreign keys, bounded lock waiting, and
  append-only mutation guards;
- a same-transaction local outbox and append-only delivery receipts;
- serialized same-connection reads/writes and tested two-connection append ordering;
- deterministic integrity replay across row columns, relations, chains, guards, and
  outbox-to-record linkage; and
- restart recovery plus injected post-insert rollback coverage.

## Deliberately not delivered

- no generation-zero dual-write or backfill;
- no active runtime or CLI pointer;
- no Obsidian/Markdown projection;
- no watcher, exporter, remote telemetry, or network service;
- no semantic index or duplicate-classification workflow;
- no provider adapter capture/conformance fixture;
- no field-level redaction or public/private database split;
- no invoice importer or price-card reconciliation service;
- no federated repository memory; and
- no learning, budget, quarantine, or champion/challenger activation.

## API sketch

```python
from hive_mind_os_v2 import FoundationStore, RepositoryIdentity

store = FoundationStore(".hive/state/foundation-v2.sqlite3")
store.register_repository(
    RepositoryIdentity(
        tenant_id="tenant:local",
        repository_id="repo:example",
        canonical_uri="https://example.invalid/repository",
    )
)
```

Memory and usage records must use the same registered tenant/repository scope. Each
successful append creates one durable outbox message in the same SQLite transaction.
Consumers call `pending_outbox(consumer_id)` and append a content-addressed delivery
receipt through `record_delivery(...)`.

## Truth boundary

`FoundationStore.verify_integrity()` detects canonical JSON, row/index, digest-chain,
mandatory-guard, and outbox-link drift in its own database. It is not a signature
verifier, identity provider, privacy certification, external delivery proof, provider
invoice proof, distributed database guarantee, or production-readiness verdict.
