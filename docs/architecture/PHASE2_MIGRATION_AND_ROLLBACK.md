# Phase 2 migration and rollback

## Migration

1. Leave `EvidenceLedger`, `MissionStore`, scheduler, v1 schemas, roles, prompts,
   packages, selectors, and CLI unchanged.
2. Create a new foundation database at schema version 1 only when an internal caller
   explicitly opts in. Refuse non-empty unversioned databases and same-version files
   without the exact foundation ownership/schema digest.
3. Register opaque repository identity before any scoped record.
4. Write records and local outbox atomically. Do not enable a consumer or network
   exporter by default.
5. Require a matching allowed authority decision at every write boundary. Require a
   separate public-release decision for safe-public sensitivity.
6. For model shadowing, wrap a provider explicitly. Record the start before I/O and
   terminal usage before returning.
7. Reconcile legacy events read-only. Any missing tenant, repository, attempt,
   provider, or usage value remains an explicit unmappable gap. Phase 2 performs no
   automatic backfill.
8. Review reconciliation, privacy, and independent court receipts before any future
   activation pointer.

Unknown future schema versions fail closed. Migration never edits a legacy database.

## Rollback

Remove the explicit foundation store/provider wrapper from the caller. The legacy
runtime resumes with identical selection and behavior because it was never replaced.
Retain:

- the foundation database and WAL;
- pending outbox messages and delivery receipts;
- interrupted/unknown attempts;
- reconciliation residuals;
- semantic candidates, dissent, and appeals;
- generated candidate and source digests.

Rollback never deletes records, rewrites usage, marks unknown as zero, or claims that
an external destination acknowledged a message.

## Recovery checks

- Reopen after a committed record and verify its outbox remains pending.
- Replay an identical idempotency key and obtain the same record.
- Reject a conflicting idempotency replay.
- Reject a legacy or malformed same-version database without changing its schema.
- Reject a mismatched authority action, cross-scope relation, or unapproved
  safe-public write.
- Convert started/nonterminal attempts to interrupted/unknown exactly once.
- Replay delivery to its immutable destination until an append-only acknowledgement
  follows a successful attempt.
- Run deterministic generation check and the complete Generation Zero regression
  suite.
