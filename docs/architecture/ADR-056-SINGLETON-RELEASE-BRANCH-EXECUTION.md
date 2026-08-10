# ADR-056: Singleton release-branch execution

Status: Accepted for the current Hive Mind OS execution program

Date: 2026-08-10

## Decision

All Autopilot nodes execute, validate, reconcile, claim, publish receipts, and open
node PRs against one configured singleton release branch:

`release/hive-mind-os-singleton-20260810-r2`

The protected `main` branch is not an execution target and must not receive node
merges. It is reserved for one final integration after L0–L15 completion has been
independently audited.

## Invariants

- The release branch is the controller's only live target during the program.
- Every durable receipt must be an ancestor of the release branch before a node is
  considered complete.
- PR target rendering is derived from the controller target, never from a stale node
  default or branch name.
- `main` remains protected until final integration; no dispatcher release may target it.
- A release-branch advance invalidates prior dispatcher releases and requires fresh
  reconciliation.
- Final integration is a separate, explicit operation after the completion audit; it
  does not authorize new node work.

## Rationale and alternatives

The previous main-target workflow made ordinary node integration indistinguishable from
production of the final repository state and caused L1 receipt ancestry to be lost in
normal PR merges. A singleton release branch keeps all work and evidence in one
reconstructable ancestry while preserving main as a final protected promotion boundary.

Per-node release branches were rejected for the execution target because they require
cross-branch reconciliation between every node and make the target ambiguous. Direct
main execution was rejected because it violates the requested final-integration boundary.

## Rollback

Revert the policy amendment and stop dispatch. The release branch and its evidence remain
recoverable; no main history is rewritten.
