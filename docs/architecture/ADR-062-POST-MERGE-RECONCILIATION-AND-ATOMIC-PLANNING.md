# ADR-062: Post-merge reconciliation and atomic planning

## Status

Implemented candidate on `release/hive-mind-os-singleton-20260812-r5`. Promotion to
`main` requires exact-head CI and independent review; this ADR does not authorize
merge or auto-merge.

## Context

The singleton implementation history and `main` had diverged. The singleton line held
the Autopilot, Hive Cortex role implementations, and retained node receipts, while
`main` held newer governance and CI history. A broad aggregation merge preserved both
histories but left three material problems:

1. BUILDER-330, ORCH-300, and OPTIMIZER-370 each had a historical durable receipt and a
   later bounded repair candidate. The generic controller correctly treated duplicate
   receipts as ambiguous.
2. ORCH-300 needed a public atomic event-batch primitive. Planner-private transaction
   coupling would have violated the store abstraction and could leave partial
   supersession/replacement history.
3. Builder command and commit actions needed stronger branch and effective change-set
   binding. Declared targets and paths alone were insufficient evidence of the actual
   Git branch and complete tracked/staged/untracked mutation set.

The repair must preserve every historical commit and adverse record, must not rewrite
claims or receipts, and must fail closed for any receipt topology other than the exact
three incidents.

## Decision

### Ancestry and release line

Create the r5 repair line from the merged singleton release and ancestry-preserving
merge the then-current `main`. No rebase, squash, amend, or force-push is used. The
resulting draft pull request targets `main`, but this ADR confers no promotion authority.

### Public atomic event batches

`KernelStore.append_batch()` is the public all-or-nothing event API. It:

- validates the complete event batch before mutation;
- rejects duplicate event IDs and idempotency keys;
- accepts only an exact fully persisted retry;
- rejects partial retries;
- validates chain continuity and projections in memory first;
- writes the batch and projection in one SQLite transaction;
- rolls back every write when reducer or persistence work fails.

Single-event append behavior remains compatible by delegating to the same invariants.
ORCH-300 uses the public batch API for predecessor supersession and replacement work
creation, so an injected mid-batch failure cannot publish a partial plan transition.

### Mission-scoped orchestration

ORCH-300 plan persistence and reconstruction are mission-scoped. The implementation
binds the charter into the plan digest, persists schedules, rejects cross-mission and
cross-planner lineage, enforces aggregate and remaining budgets, limits revisions,
requires two distinct non-requesting consultation roles, rejects terminal missions and
active predecessor overlap, and treats exact stale retries as idempotent. Operational
transitions use the Orchestrator actor identity.

### Builder change authority

Builder commit execution requires all of the following:

- an attached, non-protected current branch;
- exact equality between the current branch, the action target, and the workspace
  branch;
- lexical
  authority.

## Threats and failure modes

- **Broad supersession:** denied by the sealed registry digest and exact commit
  set.
- **Third receipt:** left unresolved and therefore fail closed.
- **Authority-file tampering:** detected before resolution or dispatch.
- **Partial event history:** prevented by whole-batch preflight and one database
  transaction.
- **Workspace aliasing:** `.git`, dependency, protected, case-folded, staged,
  tracked, and untracked paths are checked against the declared scope.
- **Stale target:** controller status remains reconciliation-required until the
  exact final head is reconciled.
- **False independence:** implementation evidence does not substitute for an
  independent promotion review.

## Migration

The candidate branch is based on the complete singleton release and contains
`main` as explicit ancestry. Existing historical receipts are not edited. The
three new successor receipt histories are merged into the candidate, then the
control plane deterministically selects only the exact replacement for current
state reconstruction.

## Rollback

Close the unmerged promotion PR or revert the repair commits while retaining all
old/new receipt, claim, candidate, court, and dissent objects. Never rewrite the
history to remove adverse evidence.

## Acceptance evidence

- Atomic store tests cover whole-batch success, idempotent replay, duplicate and
  partial retry denial, reducer failure rollback, and unchanged projections.
- Orchestrator tests cover mission isolation, exact lineage, stale retries,
  active predecessors, charter-bound digests, aggregate/remaining budgets,
  revision limits, canonical replan evidence, schedule round-trip, consultation
  separation, and atomic failure.
- Builder tests cover detached and mismatched branches, staged/tracked/untracked
  undeclared changes, exact declared commits, protected aliases, and `.git`.
- Optimizer tests cover strict runtime types, self-review denial, immutable
  evidence bindings, and challenger/court boundaries.
- Post-merge controller tests cover exact authority validation, exact old/new
  receipt selection, configuration tamper denial, and third-receipt failure.
