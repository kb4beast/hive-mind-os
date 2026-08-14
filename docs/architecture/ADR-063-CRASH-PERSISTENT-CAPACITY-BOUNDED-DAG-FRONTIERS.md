# ADR-063: Crash-persistent capacity-bounded DAG frontiers

## Status

Implemented as a bounded candidate on
`codex/hive-os-dag-runtime-recovery-v1`. The first checkpoint was independently
remanded after adversarial review; the corrective follow-up remains pending a
second Curator judgment and the repository CI gate. This ADR does not authorize
deployment, ASP resealing, or mutation of any accepted execution ledger.

## Court record

The retained primary source is the repository at
`a0d345e12c70ae15a7496057a04e254ddb222e6c` plus the failing local
reproductions made on 2026-08-13. No external source or superiority claim is
used.

Atomic claims considered:

1. The round compiler already split a level wider than host capacity, but the
   mutating dispatcher and healer bypassed that schedule.
2. A no-argument healer redispatch could release a different or over-wide wave
   after a crash.
3. A foreign-plan round command contained `dispatch --plan`, although the
   mutating dispatcher neither parsed nor safely supported that plan.
4. The attended-host ledger silently treated malformed JSON as an empty store
   and used non-atomic, unlocked replacement.
5. The kernel, mission, and scheduler stores accepted specific ambiguous or
   incoherent durable states.
6. Bare Python in this worktree imported `hive_mind_os` from another live
   worktree, contaminating test and execution truth.
7. Capacity and release state were still local to a worktree, so controllers
   using different worktrees could not share a lock or immutable active cap.
8. A completed plan with an expired validation lease could return an unwakeable
   `WAITING` result instead of repairing the lease and becoming quiescent.
9. Synthetic graphs accepted missing dependencies, frontier identities did not
   bind plan content, legacy scheduler identities could duplicate after
   migration, and receipt linkage was checked in only one direction.

The Orchestrator/Builder identity is `codex:hive-os-recovery-v1`. Independent
roles used during diagnosis were `architect:capacity-frontier`,
`cross-examiner:loop-reconstruction`, and `steward:durable-store`. The
candidate disposition is **adapt**: reuse the existing deterministic compiler
as the sole frontier selector and harden the smallest stores on the execution
path. The first independent Curator identity was
`curator:os-candidate-review`; its disposition was **defer/remand**. Final
judgment is reserved for a new review of the corrective commit.

## Context

Two controllers could observe the same eligible DAG level but use different
local capacity and recovery state. The compiler produced bounded rounds, while
`ControlPlane.dispatch()` greedily selected from the whole eligible set and
`heal_round()` redispatched without the selected round. A crash could therefore
lose the intended frontier, create more sessions, or repeat an already active
wave. Several local stores compounded the fault by accepting corruption or by
rewriting state through non-atomic paths.

The repair must preserve existing candidate and acceptance evidence. Durable
completion still comes only from the configured receipt authority; neither a
release nor a local task card can manufacture completion.

## Decision

### One capacity-bounded frontier

`dag_standard.select_frontier()` deterministically selects the first incomplete
compiled round from three inputs: the sealed plan, accepted node identities,
and active claim identities. It refuses unknown nodes, accepted/active overlap,
active work outside the current round, and active work above runtime capacity.
Its output binds the cap, round, completed members, active members, newly
releasable members, and a digest of the complete plan in a SHA-256 frontier
identity. Compilation rejects duplicate node identities, unknown dependencies,
and dependency cycles before producing any release.

The mutating dispatcher consumes that frontier directly. Each release records
the frontier identity, round identity, full round membership, and runtime cap.
An exact retry returns the existing release without appending history. The
healer may redispatch only the selected round and must carry the same cap.
Partially accepted rounds resume only their unaccepted members.

The controller holds an advisory cross-process dispatcher lock while binding
runtime state to the plan identity, plan fingerprint, repository, and target
branch. Once a frontier is released, its runtime cap is immutable until that
plan/target runtime state is retired. Every controller that may operate on the
same execution **must** use the same absolute runtime state directory, either
with `--state-dir <absolute-path>` or
`HIVE_MIND_RUNTIME_STATE_DIR=<absolute-path>`. The default remains
worktree-local for backwards compatibility and therefore does not coordinate
separate worktrees.

Plan completion and healing inactivity are distinct states:

- `NO_REPAIR` means the healer has no authorized mutation;
- `WAITING` means live runtime authority remains;
- `PLAN_QUIESCENT` requires every compiled round complete and no active claim
  or validation lease.

`WAITING` carries the earliest claim or validation-lease expiry as `wake_at`.
With healing enabled, an expired validation lease is repaired before the
quiescence decision rather than producing an unwakeable wait.

### External plans

A foreign plan is never passed into the resident mutating control plane.
Generated external round commands invoke the pure `dag-frontier` contract with
prior completed nodes and an exact expected release. The command is executable
and fails closed if the compiled release differs. The foreign host adapter is
responsible for converting that verified contract into sessions.

### Durable store boundaries

- The attended-host ledger is size-bounded, duplicate-key rejecting, locked,
  atomically replaced, and bound to immutable node/card digests. An exact task
  retry is read-only; a competing instruction under the same key is rejected.
  Card content is revalidated on every ledger read, and the ledger and cards
  may live in shared runtime state outside either worktree.
- Kernel-store startup validates schema version, SQLite integrity, canonical
  effect intents, state-dependent fields, bidirectional receipt linkage, and
  reconciliation records before use. Read operations verify the event chain.
  Exact event retries include their durable predecessor digest, including at
  compatibility call sites that retry after the chain head advanced.
- Mission effects use compare-and-swap claim semantics. Missing write-ahead
  records, unsafe mission/receipt paths, noncanonical or tampered receipts, and
  mismatched receipt contracts fail closed before checkpoint completion.
- Scheduler identity includes mission, kind, payload, retry limit, and requested
  start time. Legacy rows are deterministically migrated to the same canonical
  enqueue specification before accepting new work. Claims may be mission/kind
  scoped; lease coherence and completion mission identity are validated.

### Source affinity

The repository-root source shim replaces its loader and module specification
with this checkout's `src/hive_mind_os` package. Bare repository test commands
therefore cannot silently import an editable installation from another
worktree, and package resources resolve from the same source tree.

## Threats and failure modes

- **Controller crash before task creation:** the exact release is replayed
  read-only from the deterministic frontier.
- **Controller crash with active workers:** active claims consume the current
  frontier; later rounds cannot be selected.
- **Competing worktree controller:** the shared lock serializes release and its
  runtime binding rejects a different plan, repository, or target; an active
  release rejects a changed cap.
- **Competing task instruction:** immutable card digest mismatch fails closed.
- **Torn or corrupt local JSON:** strict parsing and atomic replacement prevent
  an empty-store reset.
- **Stale worker completion:** lease token, expiry, and mission binding reject
  the mutation.
- **Receipt traversal or tamper:** resolved containment, expected receipt name,
  digest, canonical wrapper, schema, and intent bindings are all required.
- **Foreign editable install:** source-affinity tests require the imported
  package and resources to reside under this checkout.
- **Expired validation authority:** healing breaks only an expired lease and
  then reevaluates the strict fixed point; live authority returns a timed wait.

## Migration and compatibility

Existing scheduler databases gain the nullable enqueue-spec column. Legacy rows
are upgraded transactionally to the canonical specification before validation;
every newly enqueued row carries and validates the stronger identity. Existing
attended ledgers without card digests, or with the old repository-relative card
location, fail closed and require explicit operator migration rather than silent
rewriting. No accepted DAG receipt, remote evidence ref, or ASP ledger is
changed by this candidate.

Concurrent worktrees require one deliberately chosen shared state directory.
Using each worktree's default `.autopilot/state` preserves isolation but does
not provide cross-worktree exclusion. Separate DAGs must still use distinct
sealed execution namespaces and ledger/evidence refs; sharing controller state
does not merge their evidence authorities.

Conventional resident plans keep mutating dispatch commands, now with an
explicit session cap. External plan consumers must use the frontier JSON
contract instead of the invalid historical `dispatch --plan` command.

## Rollback

Revert this candidate commit. Preserve any release, task, failure, or adverse
test evidence created while evaluating it. Do not delete or rewrite accepted
ASP/knowledge ledgers. A rollback may require an explicit attended-ledger
migration if a newer card-digest entry has already been written.

## Acceptance evidence

Focused tests cover:

- 8-node levels split and advance as 3/3/2 frontiers;
- partial accepted/active round recovery and later-round refusal;
- capped mutating dispatch, exact read-only retry, and active-round resumption;
- shared-state cross-worktree dispatch exclusion and immutable active capacity;
- missing-dependency rejection and plan-bound frontier identities;
- runnable external frontier assertions;
- exact-wave healer behavior and distinct quiescence dispositions;
- timed waits and expired validation-lease repair at apparent completion;
- malformed, duplicate-key, conflicting, and traversing attended task state;
- wrong-predecessor retry, unknown kernel schema, and incoherent effects;
- bidirectional receipt/reconciliation linkage and canonical payload checks;
- competing mission effects, missing WAL, receipt tamper, and path traversal;
- cross-mission scheduler identity, scoped claims, incomplete leases, and
  mission-rebinding denial, including legacy identity migration;
- bare-Python source and package-resource affinity.

The repository-wide CI gate and independent promotion judgment remain required.
