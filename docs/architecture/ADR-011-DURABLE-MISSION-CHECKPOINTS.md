# ADR-011: Durable Mission Checkpoints and Exactly-Once Effect Adoption

- **Status:** Proposed for independent P06 court review
- **Date:** 2026-07-27
- **Case:** `CASE-P06-DURABLE-MISSION-RECOVERY`
- **Originating work order:** `docs/plan/P06_DURABLE_MISSIONS.md`
- **Prior decisions:** ADR-003, ADR-007, ADR-010
- **Capability maturity:** locally implemented; external scheduling and delivery deferred

## Context

P05 missions kept their state in one process. A process exit therefore discarded progress
and required the objective to be restated. P06 requires a single-writer durable spine:
mission state, step intents, workspace snapshots, receipt references, budget consumption,
and completion must survive interruption without silently duplicating an already evidenced
effect.

The phase contract distinguishes exactly-once effect adoption from exactly-once execution.
A process can stop after an effect but before the completion transaction. Recovery must
first look for a receipt bound to the canonical intent digest. A matching receipt is
adopted; absence permits re-execution. The implementation must not infer completion from
time, directory presence, or an unverified outcome.

A real Windows process-tree termination exposed an additional counterexample beyond the
in-process boundary sweep: termination during Git materialization left a partial,
uncheckpointed directory. Resume initially failed because the Git adapter correctly
refused to overwrite it. The repaired rule removes only a local workspace whose intent
has no completed checkpoint or matching receipt, then rematerializes it. A recorded
workspace with digest drift remains blocked and is never silently rebuilt.

The first post-commit audit preserved in `evidence/audits/P06-post-timeout.json` exposed a
second concrete boundary: the audit runner's 300-second command ceiling terminated the
now-mandatory full suite, whose durable Windows recovery sweep takes about nine minutes.
The audit remained fail-closed and marked itself incomplete. The repaired ceiling is 1,200
seconds; timeout, output, process-tree termination, and result-recognition controls remain
unchanged.

## Court record

- **Advocate:** add a versioned SQLite `MissionStore`, canonical intent checkpoints, a
  unique digest-to-receipt idempotency index, and explicit workspace reconciliation.
- **Cross-examiner:** kill before intent, after intent, and after effect for every durable
  step; mutate and delete workspaces; tamper with the recorded digest; change the store
  version; and terminate the real CLI process during materialization.
- **Expert evidence:** deterministic tests cover 54 injected crash boundaries, while the
  external process termination reproduced and then verified the partial-materialization
  repair.
- **Judge:** a separately identified Judge must issue the final disposition on the exact
  complete candidate. This proposal cannot approve itself.

No external source is introduced by this decision. Source-ingestion and licensing
obligations remain assigned to P12.

## Decision

1. Persist missions, checkpoints, workspace snapshots, budgets, reports, and an immutable
   idempotency index in a caller-selected SQLite state directory.
2. Identify a durable step by `(mission_id, step_index, tool_intent_digest)`. Record the
   canonical intent before execution and the outcome plus receipt reference after it.
3. On resume, adopt a receipt matching an incomplete intent before considering
   re-execution. A completed checkpoint without its exact receipt reference fails closed.
4. Treat exactly-once effect adoption as the guarantee. Do not claim that an operating
   system process can provide exactly-once physical execution across an arbitrary crash.
5. Reconcile every recorded workspace against its Git head, tree, status, and content
   digests. Any mismatch blocks with a reconciliation report.
6. Rebuild a missing recorded workspace deterministically. Also discard and rebuild a
   partial local materialization only when no completed checkpoint or matching receipt
   establishes that materialization as adopted state.
7. Validate persisted mission-state projections against the existing schema and reject an
   unknown store schema version.
8. Expose offline `missions` and `resume` CLI operations. P06 durable resume is limited to
   the deterministic scripted repository backend; durable provider-call replay belongs to
   later provider and scheduler work.
9. Permit the deterministic post-commit audit command up to 1,200 seconds so the required
   recovery suite can complete. A timeout still terminates the process tree, returns 124,
   and makes the audit incomplete.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Effect executes before the completion transaction | Receipt lookup by canonical intent digest adopts the observed outcome | Physical execution itself is not exactly once |
| Resume repeats an adopted effect | Unique digest-to-receipt index and completed-checkpoint adoption | P07 must extend the same discipline to remote GitHub effects |
| Workspace changed while the process was down | Recorded Git and content digests; mismatch blocks with a report | Resolution requires a later explicit decision |
| Workspace vanished | Deterministic rematerialization and replay inside the disposable sandbox | Large workspaces may make recovery expensive |
| Process dies during materialization | An uncheckpointed, unreceipted partial directory is removed before retry | The interrupted local bytes are intentionally not evidence |
| Persisted intent is edited | Canonical digest is recomputed on read; mismatch fails closed | State-directory access control remains an operational concern |
| Unknown database format is opened | Version stamp mismatch closes the connection and fails closed | Schema migration is deferred until a second version exists |
| Durable state is mistaken for distributed scheduling | P06 is explicitly single writer | Leases, queues, heartbeats, and contention belong to P11 |
| Required audit suite exceeds its collector budget | 1,200-second ceiling covers the measured nine-minute Windows run | A genuine hang still consumes up to the declared ceiling before failing closed |

## Acceptance evidence

- Store CRUD, unique idempotency, version rejection, state round-trip, and CLI tests pass.
- All 18 durable steps pass interruption at three boundaries: 54/54 resume cases.
- Every sweep case has 18 completed checkpoints, 18 unique idempotency records, one
  checkpoint receipt per intent, and an execution count of one.
- Workspace drift blocks; a missing workspace and an uncheckpointed partial workspace
  rebuild and complete.
- The unchanged P05 mission suite passes without a store attached.
- A real Windows process-tree termination during Explorer materialization resumes to a
  successful delivery with 18 completed checkpoints, 18 idempotency records, and zero
  duplicate intent digests.
- The original 300-second audit timeout remains preserved as incomplete evidence; the
  repaired audit completes under the 1,200-second ceiling.
- Full tests, Ruff, Pyright, the P06 audit, and one consolidated independent review must
  pass on the final exact candidate before adoption.

## Rollback

Revert the P06 branch before P07 or P11 depends on it. The no-store P05 path remains the
compatibility seam. Preserve interrupted state directories, failed candidates, audit
artifacts, the hard-kill counterexample, and independent dissent as evidence; do not
misrepresent them as delivered artifacts.

## Deferred limits and ownership

- P07 owns remote GitHub effects, credentials, push/PR idempotency, and protection checks.
- P08 owns structural Curator independence and authenticated identities.
- P11 owns leases, queues, heartbeats, retention, garbage collection, and operational
  mission projection.
- P12 owns unresolved source ingestion and licensing.
- B-OPS-06 owns hard hostile-code filesystem and network isolation.

This decision does not establish production readiness, distributed correctness, hostile
code isolation, external delivery, complete source coverage, or superiority.
