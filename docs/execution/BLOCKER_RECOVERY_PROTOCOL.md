# Blocker recovery protocol

Every failed attempt is an operating-system learning event.  The controller
must preserve an actionable blocker packet containing:

- the exact cause and category;
- the concrete fix required;
- the safe condition that permits retry;
- the attempted command and evidence references;
- a content-addressed blocker ID and timestamp.

Workers must report the packet to the operator and stop when the fix requires
credentials, protected-branch authority, legal consent, spending, production
access, or another authority outside the lease.  They may retry automatically
only after the packet's retry condition is verifiably true.  A security
control may not be disabled merely to make the retry pass.

Owner permission changes who may authorize an action; it does not change the
security meaning of that action. Disabling TLS verification, certificate
revocation, provenance checks, protected-branch rules, or evidence validation
is an unsafe remediation and remains ineligible for automatic retry. The
controller may pursue safe alternatives, but must stop and report the exact
repair when no safe alternative is available.

Known orchestration blockers are actionable: a missing or stale dispatcher
release produces a `SPAWN_SUBTASK` recovery action for an orchestrator child
task. That child refreshes the current singleton snapshot, reconciles the
target, emits a new explicit release, and retries the blocked claim. It must
stop again if the target changes or if the only workaround weakens a security
or provenance control.

Every child task follows this exact order:

1. fetch the current singleton release;
2. install the current GitHub snapshot;
3. reconcile the target;
4. run doctor and status;
5. dispatch an explicit `START NOW` release;
6. claim the remote node branch.

A child must never attempt step 6 before step 5 has produced a valid release.

Runtime packets are append-only under `.autopilot/state/blockers/`.  The
protocol, tests, and failed-attempt evidence are repository artifacts, so a
fresh session learns the recovery rule rather than repeating an opaque failure.

Generic in-authority software blockers select `SPAWN_SUBTASK`: a Steward child
inspects the exact evidence, applies a bounded safe fix, reruns the failed
operation, records `blocker-resolve`, and resumes the same primary task. Runtime
details remain local; the generalized sequence and regression tests are
checked-in policy, so clean checkouts and other repositories inherit the lesson.

## Human-question learning rule

If a human question is unavoidable, record it under
`.autopilot/state/questions/<node>.jsonl` with `record_human_question`. When the
human and system establish the result, immediately call
`resolve_human_question`. That appends the fix and an explicit `RETRY_NOW`
action, allowing the controller to resume the failed operation in the same
turn. The answer is stored only as a digest; credentials, proxy secrets, and
other sensitive values must never be copied into repository files or evidence.
An unresolved question remains a blocker, not a reason to repeat the same
question on the next run.

## Parent supervision and quiescence

Creating children transfers work, not responsibility. The parent registers the
released wave with `subtask-wave-start` and continues polling with
`subtask-wave-poll`. A UI state of `idle` is `IDLE_UNCOLLECTED`, never success;
the parent must read and classify the child result. `BLOCKED_RECOVERABLE`
requires the parent to apply the safe fix and retry immediately.

The parent may end its turn, or mutate the singleton release target, only when
every child is settled as `SUCCEEDED` or `BLOCKED_EXTERNAL_AUTHORITY`. Pending,
active, idle-uncollected, and recoverably blocked children emit explicit
continue/collect/retry actions. If an urgent target mutation invalidates a wave,
the parent must refresh the validated snapshot, retire only the stale claim
refs with their SHAs preserved, issue a fresh release, and resume every child
before considering the wave quiescent.

Git stashes are repository-wide across worktrees. Recovery must name every
stash with its node ID, locate it by that exact message, and verify the restored
paths against the node's write scope. Positional selectors such as `stash@{0}`
must not be used for cross-worktree orchestration. Stale generated runtime state
is archived under a named recovery directory before the current validated
snapshot and release projections are installed; evidence ledgers are retained.

Parallel nodes may run focused tests concurrently, but the repository-wide CI
gate requires the dispatcher-injected validation authority envelope. Acquire,
renew, and release must carry the exact claim ID, launch instruction, resource
key, authority epoch, and lease ID required by the command. Only one valid
generation may own that lease at a time; every other child remains active and
ready for the global gate. This prevents parallel full suites from exhausting
process, clone, or filesystem resources and turning contention into false
failures.

## Sealed rejected-receipt retirement

`EXPLORER-310` has one court-quarantined rejected receipt branch. Its recovery is not a
generic branch-delete facility. `retire-receipt-branch` accepts only the sealed record in
`.autopilot/receipt-branch-retirements.json`, verifies the separate canonical court record,
and contacts only configured `origin` for the configured repository. It archives the exact
receipt under its sealed quarantine ref and deletes the active branch in one leased atomic
transaction. No source ref is deleted if the archive is missing, forged, moved, colliding,
or unable to be verified. The archive retains the receipt as its parent and exactly the same
tree. After success, install a fresh validated snapshot, reconcile, dispatch, and only then
claim the replacement Explorer branch.

The sealed incident target is evidence of the rejected branch, not a requirement to move the
singleton release backward. The sealed Appeals `ADAPT` ordering disposition requires the
current reconciled singleton target to contain the integrated retirement capability before
the one-time operation can run, while preserving the Court `QUARANTINE` disposition.
