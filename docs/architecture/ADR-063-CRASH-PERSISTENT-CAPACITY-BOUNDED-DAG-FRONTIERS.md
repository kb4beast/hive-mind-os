# ADR-063: Crash-persistent capacity-bounded DAG frontiers

## Status

Implemented as a bounded candidate on
`codex/hive-os-dag-runtime-recovery-v1`. Promotion remains pending an
independent Curator review and the repository CI gate. This ADR does not
authorize deployment, ASP resealing, or mutation of any accepted execution
ledger.

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

The Orchestrator/Builder identity is `codex:hive-os-recovery-v1`. Independent
roles used during diagnosis were `architect:capacity-frontier`,
`cross-examiner:loop-reconstruction`, and `steward:durable-store`. The
candidate disposition is **adapt**: reuse the existing deterministic compiler
as the sole frontier selector and harden the smallest stores on the execution
path. Final judgment is intentionally reserved for a separately identified
Curator after the candidate commit exists.

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
Its output binds the cap, round, completed members, active members, and newly
releasable members in a SHA-256 frontier identity.

The mutating dispatcher consumes that frontier directly. Each release records
the frontier identity, round identity, full round membership, and runtime cap.
An exact retry returns the existing release without appending history. The
healer may redispatch only the selected round and must carry the same cap.
Partially accepted rounds resume only their unaccepted members.

Plan completion and healing inactivity are distinct states:

- `NO_REPAIR` means the healer has no authorized mutation;
- `WAITING` means live runtime authority remains;
- `PLAN_QUIESCENT` requires every compiled round complete and no active claim
  or validation lease.

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
- Kernel-store startup validates schema version, SQLite integrity, canonical
  effect intents, state-dependent fields, receipt linkage, and the event chain
  before use. Exact event retries include their predecessor digest.
- Mission effects use compare-and-swap claim semantics. Missing write-ahead
  records, unsafe mission/receipt paths, noncanonical or tampered receipts, and
  mismatched receipt contracts fail closed before checkpoint completion.
- Scheduler identity includes mission, kind, payload, retry limit, and requested
  start time. Claims may be mission/kind scoped; lease coherence and completion
  mission identity are validated.

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
- **Competing task instruction:** immutable card digest mismatch fails closed.
- **Torn or corrupt local JSON:** strict parsing and atomic replacement prevent
  an empty-store reset.
- **Stale worker completion:** lease token, expiry, and mission binding reject
  the mutation.
- **Receipt traversal or tamper:** resolved containment, expected receipt name,
  digest, canonical wrapper, schema, and intent bindings are all required.
- **Foreign editable install:** source-affinity tests require the imported
  package and resources to reside under this checkout.

## Migration and compatibility

Existing scheduler databases gain the nullable enqueue-spec column. Legacy rows
remain readable; every newly enqueued row carries and validates the stronger
identity. Existing attended ledgers without card digests fail closed and require
explicit operator migration rather than silent rewriting. No accepted DAG
receipt, remote evidence ref, or ASP ledger is changed by this candidate.

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
- runnable external frontier assertions;
- exact-wave healer behavior and distinct quiescence dispositions;
- malformed, duplicate-key, conflicting, and traversing attended task state;
- wrong-predecessor retry, unknown kernel schema, and incoherent effects;
- competing mission effects, missing WAL, receipt tamper, and path traversal;
- cross-mission scheduler identity, scoped claims, incomplete leases, and
  mission-rebinding denial;
- bare-Python source and package-resource affinity.

The repository-wide CI gate and independent promotion judgment remain required.
