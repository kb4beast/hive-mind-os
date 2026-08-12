# ADR-061: Token-aware, root-mediated execution sidecars

## Status

Adapted implementation candidate on the singleton release branch. Independent Curator
promotion review remains required.

## Context

Visible durable primary tasks provide ownership and recovery, but duplicating a complete
primary prompt for every research or review question wastes context. Unbounded nested
agents create the opposite failure: recursive fan-out, hidden authority, orphaned work,
unmeasured token use, unfair polling, and a parent that can incorrectly report
quiescence while descendants still run.

## Court record and disposition

- Advocate: admit execution-local sidecars when overlapping independent work saves more
  parent context than coordination costs.
- Cross-Examiner: reject self-authorized recursion, in-memory-only child tracking,
  unbounded waits, usage-free terminal prose, and any child that can complete a DAG node.
- Curator witness: require deterministic identity, lookup-before-spawn recovery, an
  append-only registry, authenticated terminal usage, parent acknowledgement, monotonic
  settlement, cancellation acknowledgement, and descendant-aware quiescence.
- Optimizer witness: cap host waits at eight targets, use stable fair rotation, charge
  coordination and result tokens, and distinguish semantic progress from heartbeats.
- Judge: **adapt** bounded depth-two sidecars whose descendants are always admitted and
  spawned by the root supervisor, never directly by a child.

## Decision

1. Sidecars are execution topology, not DAG/BFS levels. Durable primary tasks retain all
   node ownership, branch, claim, receipt, integration, and judgment authority.
2. Admission is deterministic. Estimated parent savings must exceed sidecar budget,
   result budget, coordination overhead, and the configured safety margin. Per-primary,
   cohort, depth, and aggregate token limits are hard gates.
3. A child may emit a structured descendant request with evidence. Only the root may
   validate it, reserve ancestor budget, authenticate identity, and call the host spawn
   operation. Depth greater than two is denied before a side effect.
4. `sidecar-bindings.jsonl` is an fsynced append-only hash chain protected by a checked-in
   OS lock. Deterministic idempotency and lookup-before-spawn recover a crash after host
   acceptance without duplicate work.
5. Sidecar bindings and events are capability-bound. Terminal packets require matching
   sidecar, parent, spec digest, state, compact evidence, and nonnegative usage no greater
   than the reservation. Unknown or forged data fails closed.
6. The root sends idempotent spawn and terminal messages to the primary and terminal
   results to the immediate sidecar parent. A parent terminal event first settles every
   active descendant. Spawn failure is a durable adverse terminal disposition.
7. Primary and sidecar events are collected together in stable, rotating groups of at
   most eight. The combined wait runs behind a real wall-clock deadline. Replay,
   no-progress, total-poll, and timeout bounds settle sidecars rather than looping.
8. Success requires no active sidecar registry entries. A host/protocol failure may
   return a truthful non-quiescent blocker; it may never be relabeled success or hang
   indefinitely to manufacture quiescence.

## Threats, migration, and rollback

A daemon-bounded wait can leave a defective host call alive inside its adapter after the
supervisor times out; the cancellation contract and runtime inspection must therefore
confirm external settlement. Character-based output limits are a conservative portable
fallback rather than a tokenizer claim. Root-mediated depth two adds complexity, so it
remains disabled by budget or evidence denial unless materially useful. Existing
contracts without `sidecar_cohort` retain the primary-only execution path. Rollback
disables sidecar admission while preserving the append-only registry as evidence.

## Acceptance evidence

Tests cover deterministic positive-value admission, count/depth/token gates, missing
evidence denial, hash-chain corruption, terminal monotonicity, capability-bound spawn,
crash adoption, parent notifications, terminal-before-child cancellation, over-budget
result rejection, root-mediated depth-two creation, nine-target fair batching, and
primary-only compatibility. The repository-wide gate remains the final promotion check.
