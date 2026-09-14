# ADR-085: Durable append-only cohort execution journal

- Status: adopted
- Date: 2026-09-14
- Owners: Orchestrator, Steward, Curator
- Affected contract: end-loaded cohort execution

## Context

Cohort execution originally retained package results only in process memory. An
interruption therefore forced already-completed packages to run again and could
repeat convergence or terminal verification after their results had been
produced. This violated the durable-continuation requirement and made
side-effecting package adapters harder to make idempotent.

## Decision

Introduce a replaceable `CohortJournalStore` interface and a default filesystem
implementation. The filesystem store writes one canonical JSON event per file,
links every event to the digest of its predecessor, publishes events atomically,
and verifies the entire retained chain before it returns any state.

The lifecycle records kickoff, dispatch batches, package results, convergence,
verification, repair attempts, and final run completion. A package result and a
run completion can each be appended only once. `CohortRuntime` accepts the store
optionally, preserving the prior in-memory API when no store is supplied.

On resume, the runtime validates the retained kickoff against the current graph,
policy, context, and effect classifications. It restores completed package
results, schedules only unfinished packages, and reuses retained convergence and
verification results. A completed run is reconstructed without invoking any
execution callback.

## Alternatives considered

- Mutable snapshots were rejected because an interrupted write or silent edit
  can replace the only account of what happened.
- Re-running the full cohort was rejected because it repeats expensive work and
  cannot provide exactly-once recorded completion.
- Embedding persistence in one host adapter was rejected because the kernel
  contract requires storage adapters to remain replaceable.

## Invariants and threat model

- Caller-controlled run ids never become filesystem paths; a canonical digest
  selects the run directory.
- Every retained event has an exact schema, contiguous sequence, previous-event
  link, canonical encoding, and content digest.
- A previously observed journal may grow but may not shrink or rewrite history.
- A mismatched kickoff, unknown package, result without dispatch evidence, or
  terminal event out of order fails closed.
- The digest chain detects corruption and unsophisticated local tampering. It is
  not a signature and does not defend against an attacker who can both rewrite
  all files and recompute all digests; authenticated remote retention remains a
  host-level option behind the store interface.
- If a process stops after an external effect succeeds but before its package
  result is journaled, the package can run again. Effect adapters must continue
  to use the stable `(run_id, package_id)` idempotency identity. The guarantee
  here is exactly-once *recorded completion*, not distributed transactionality.

## Migration and compatibility

Existing `CohortRuntime(policy)` construction and `execute(...)` calls behave as
before. Durable operation opts in with `CohortRuntime(policy, journal)`. Resume
is enabled by default when a journal exists and can be rejected explicitly with
`resume=False`.

The event schema is versioned. Future stores may implement the same protocol,
including database or authenticated remote journals, without changing runtime
callbacks.

## Verification

Focused tests demonstrate:

1. interruption after a dependency completes, process-style store reopening,
   and resume without re-executing that dependency;
2. failure on a modified retained package result; and
3. repeated execution of a completed run without repeated package,
   convergence, verification, package-completion, or run-completion records.

The existing cohort runtime suite remains the compatibility gate.

## Rollback

Stop supplying a journal store to return to the previous in-memory behavior.
Retained journals are append-only evidence and are not deleted by rollback. The
new module and optional constructor/keyword arguments can then be removed in a
later governed change if no durable consumer remains.
