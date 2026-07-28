# ADR-014: Durable Local Operations and Honest Mission Projection

- **Status:** Adapted; appeal repair pending exact-candidate consolidated review
- **Date:** 2026-07-28
- **Originating work order:** `docs/plan/P11_SCHEDULER_AND_OPERATIONS.md`
- **Prior decisions:** ADR-011, ADR-012-P08, ADR-013
- **Capability maturity:** local single-machine operation

## Context

P06 made one mission resumable but did not schedule multiple missions, detect stale
workers, or expose a truthful operating view. The control-plane contract requires leases,
heartbeats, retries, idempotency, and recovery. The experience-plane contract requires
the UI to project ledger truth and render missing evidence as unknown rather than
complete.

## Court record

- **Advocate:** add the smallest durable local queue around the existing P06 mission
  boundary so routine reversible work can continue after worker interruption.
- **Cross-examiner:** require atomic contended claims, token-bound late-completion
  rejection, real-process kill tests, bounded dead-lettering, and explicit projection
  tests for unknown, blocked, and quarantined evidence.
- **Expert testimony:** SQLite WAL plus immediate transactions provides the declared
  one-machine coordination boundary; P06 idempotency remains the effect-adoption
  authority.
- **Judge:** the first post-merge Judge issued `adapt — BLOCK`; the Curator independently
  reproduced the same expired-lease completion path. The repair is an appeal and retains
  both adverse findings.

## Decision

1. A separate SQLite scheduler stores immutable payload digests and mutable queue state.
   Enqueue deduplicates the same kind and canonical payload.
2. Claims execute in an immediate transaction and update one eligible ready or expired
   job. Every claim increments attempts and receives an opaque lease token.
3. Heartbeat, completion, and failure require the current token. Expired owners cannot
   complete late. Failures use deterministic exponential backoff and become
   `dead-letter` at the declared attempt limit.
4. Execution is at least once. Durable mission effects remain exactly-once *adopted*
   through P06 checkpoints and intent digests; the scheduler does not invent a second
   idempotency system.
5. Workers heartbeat while the mission layer executes. Graceful shutdown stops new
   claims after the in-flight job settles. A reclaimed job resumes its recorded P06
   mission.
6. `enqueue`, `serve`, and `status` are the local operating surface. No network server,
   cron, webhook, or distributed queue is introduced.
7. Status JSON and HTML are derived only from scheduler, mission-store, and ledger
   records. A store success without `mission.completed` ledger evidence is `unknown`.
   Blockers, dead letters, and quarantine are visible.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Two workers claim one ready job | Immediate transaction and conditional update | Multi-host filesystems are unsupported |
| Expired worker publishes success or failure | One atomic update requires the current token and `lease_expiry >= now` | A worker may continue an external effect; P06 adoption prevents duplicate acceptance |
| Infinite retry loop | Attempt bound, deterministic backoff, dead-letter state | Operator-triggered appeals are later work |
| Heartbeat falsely proves mission success | Heartbeat changes only lease expiry | Host clock quality remains an operating dependency |
| UI claims completion from store state alone | Requires correlated ledger completion evidence | Authenticated external ledger replication is deferred |
| Missing evidence is hidden | Explicit unknown/blocked/quarantined states in JSON and HTML | Static HTML is a snapshot, not a live server |

## Migration and rollback

P11 adds separate scheduler state under `--state-dir`; existing direct `deliver` and
`resume` paths remain available. Reverting P11 removes the queue and projection commands
without deleting user queue or mission data. Operators may still resume P06 missions
directly from retained state.

## Limits

This decision does not establish distributed operation, production readiness, hostile
code isolation, authenticated worker identity, complete source coverage, or superiority.
Triggers, retention policy, and external operational integrations remain future work.

## Consolidated-review appeal

The first all-merged review of exact `main`
`939287358679902a175d49abeea684a79b7d76ae` reproduced a fail-open interval:
after expiry but before a competing claim, the original token could still call
`complete()` or `fail()`. The original reclaim test changed the token first and therefore
did not cover this interval.

The appeal captures one clock value per operation and makes the SQLite mutation
atomically require `state='leased'`, the current token, and an unexpired lease. Failure
also rejects an expired lease before calculating retry or dead-letter state. Regressions
cover expired completion and failure before reclaim while retaining the existing
post-reclaim stale-token case. The original P11 audit remains adverse evidence; a fresh
repair audit and exact-candidate review are required.
