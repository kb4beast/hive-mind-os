# ADR-057: Sealed L2 recovery bootstrap

Status: ADAPT for three named incidents only

Date: 2026-08-11

## Context and courtroom disposition

The singleton release controller correctly fails closed on an existing canonical branch,
an open or failed PR, duplicate durable receipts, and stale branch evidence. Those generic
rules exposed three distinct deadlocks that cannot be repaired by an ordinary worker:

- `OPTIMIZER-370` retained rejected receipt `926f60ec345d7bf5b5eb9229009de1f7e7888a97`
  on PR 135 after adversarial evidence invalidated its candidate.
- `ORCH-300` retained receipt `dbb8cb736eb98e77ef35eb141b2e55e492fbcf88`
  from the older `01ca563...` release before PR 131 existed; its candidate fails CI and
  requires a current-release continuation without rewriting the old history.
- `BUILDER-330` has no PR or receipt, but its stale canonical candidate branch blocks the
  normal remote claim protocol and must be archived before exact retirement.

Each incident has separate Advocate, Cross-Examiner, Expert Witness, and Judge identities,
an `ADAPT` decision, adverse findings, acceptance conditions, and rollback. The Builder
Court, Appeals, and replan documents retain the supplied canonical digests. This combined
delivery does not combine their authority or make any recovery primitive generic.

The shared baseline also had two test-isolation defects. Controller fixtures copied live
ignored `.autopilot/state/**`, and one Explorer disposable-remote test imported a live
receipt object/ref from the invoking checkout. Both could make `doctor` depend on mutable
local or origin state rather than checked-in test inputs.

## Decision

Add one exact registry containing only Optimizer and ORCH supersession authorities, plus
the separately sealed Builder record chain. Compile the first implementation commit SHA
into all three authorities in a second sealing commit. Execution is permitted only from a
current singleton target containing that exact capability commit. The incident SHAs remain
provenance and are never interpreted as permission to move the release backward.

Optimizer publishes a zero-path repair claim whose only parent is the exact old receipt,
then an immediate deterministic merge whose parents are the repair claim and captured
execution release, in that order. ORCH publishes one deterministic repair merge claim whose
parents are the exact old receipt and captured execution release, in that order. Both use
literal-origin, exact-head compare-and-swap publication; retain every old claim, candidate,
and receipt ancestor; bind a fresh snapshot, reconciliation, full doctor, dispatcher release,
owner, expiry, and plan fingerprint; and permit changes only in the named node scope.

The replacement receipt binds the exact grant, old receipt, repair-claim payload digest,
execution merge, and captured release. It is published with a second remote-head CAS while
the active repair lease and global validation lease remain live. Optimizer retains its
original `cfe17ff...` receipt base and separately proves the current-release merge. ORCH
uses the captured execution release as receipt base and has a sealed provenance validator
for its exact historical `01ca563...` claim. Only the exact old/new pair resolves. A missing
supersession, wrong PR (including any transition other than `null` to 131 for ORCH), third
receipt, mixed-case identity, non-fast-forward topology, expanded path, stale evidence, or
attempted reuse remains `REPAIR_REQUIRED`.

Builder accepts no caller-selected node, remote, branch, SHA, or ref. It requires the
controller to show exact `REPAIR_REQUIRED` and a dispatcher `STOP`, verifies the literal
origin and pinned history, then atomically creates the dedicated archive ref at candidate
`93a9c46...` and deletes only the exact canonical source under source-head and
archive-absence leases. Post-mutation verification binds tree and claim ancestry. A failure
after remote mutation is compensated atomically; an unverified compensation preserves an
ADVERSE lease/intent and append-only audit instead of claiming success. Reclaim is forbidden
until a new authenticated snapshot proves the source absent and exact archive present,
followed by reconciliation, full doctor, status, and explicit Builder `START NOW`.

Controller fixtures now copy only Git-indexed `.autopilot` files and always create an empty
runtime state directory. Generated state, ignored modules, bytecode caches, and untracked
sentinels cannot enter a fixture. The Explorer bare-remote test synthesizes its complete
candidate/receipt history inside a disposable repository and never reads or mutates a live
origin ref. Production snapshot, literal-origin, and CAS semantics are unchanged.

## Threat model and fail-closed boundary

The protected boundary includes repository/origin substitution, Git URL rewrites and
injected configuration, identity case changes, stale or raced release refs, forged snapshot
PR mappings, missing Git objects in a release-only clone, wrong parent ordering, merge-tree
conflicts, force/rebase/squash histories, scope expansion, duplicate receipts, expired or
foreign leases, crash windows, partial remote mutations, archive reuse, and evidence-write
failure after publication. Exact prefetch refs, deterministic trees, before/after release
checks, prepared state records, CAS leases, compensation, and retained adverse evidence
address those threats. Generic claims, completion, duplicate-receipt handling, Explorer
retirement, TLS, revocation, provenance, tests, courtroom rules, and protected branches are
not weakened.

## Migration, validation, and rollback

The migration order is: merge this release-only bootstrap, refresh authenticated state,
reconcile the exact current release, run full doctor and status, issue a named dispatch,
then invoke only the incident-specific transaction. No recovery runs as part of this ADR.
Focused adversarial controller tests and the canonical repository suite gate promotion;
independent Curator and Judge identities review the final candidate.

An untouched Optimizer/ORCH repair publication rolls back by CAS to its exact old receipt.
An untouched Builder retirement rolls back by atomically restoring the exact candidate from
the exact archive while deleting that archive. Once a branch advances to a correction or
replacement claim, histories are preserved and rollback requires a separately judged
appeal. The singleton release can revert the two bootstrap commits to remove all three
capabilities; generated execution evidence remains append-only. `main` is never a target.
