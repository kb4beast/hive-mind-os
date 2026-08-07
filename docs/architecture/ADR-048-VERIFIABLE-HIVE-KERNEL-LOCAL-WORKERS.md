# ADR-048: Verifiable Hive Kernel bounded local workers

## Status

Proposed Phase 4 candidate. It is local-only and grants no provider, network, Git,
credential, or external-effect authority.

## Decision

Phase 4 reuses the existing durable local `Scheduler` rather than adding another queue.
`KernelWorker` binds each local `kernel-work` job to mission/work identifiers and a
canonical binding digest. It appends kernel work transitions before scheduler completion
and uses expiring exclusive write-scope locks. A held scope causes a scheduler retry;
no executor runs. Existing scheduler leases provide finite claims, heartbeats, expiry
reclaim, exponential retry/backoff, stale-token rejection, and dead-lettering.

Cancellation is represented by an append-only `CANCELLED` work transition. This slice
does not execute role code or external effects; `AWAITING_VERIFICATION` is its terminal
worker handoff. The scheduler and scope-lock stores are separate local SQLite files, so
the lock is acquired only after a lease claim and failure releases it; this is a bounded
fail-closed local boundary, not a distributed atomicity claim.

## Rollback

Stop local kernel workers and remove the additive worker/lock files. Existing scheduler
jobs and kernel events remain intact. Independent courtroom disposition remains open.
