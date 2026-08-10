# ADR-055: Verifiable Hive Cortex as the Canonical Runtime

Status: accepted for migration planning

Date: 2026-08-10

## Context

The repository contains several overlapping runtime entry points: `HiveKernel`,
`RepositoryMission`, `MissionLoop`, `AutonomousBrain`, the scheduler/worker
path, and the newer `brain_kernel` event spine.  Treating any of these as a
second authority-bearing brain would create divergent mission truth, duplicate
effects, and unverifiable promotion decisions.

The accepted direction is therefore a single Verifiable Hive Cortex.  Its
authority-bearing source of truth is `brain_kernel`: an append-only event spine
with typed mission contracts, deterministic projections, explicit authority,
bounded context, effect requests, verification, and delivery gates.  Models
propose and interpret; deterministic policy and effect adapters decide and
execute.

## Decision

`brain_kernel` is the sole authority-bearing event spine for new missions.
The canonical boundaries are:

| Boundary | Responsibility | Authority |
| --- | --- | --- |
| Cognition | provider-backed role reasoning and synthesis | proposes typed plans/results |
| Control | event ordering, DAG state, leases, retries, gates | authoritative deterministic state |
| Effects | repository, process, Git, network, and delivery adapters | executes only leased grants |
| Verification | independent tests, provenance, threat/licence checks | can reject or quarantine |
| Learning | held-out evaluation and challenger records | cannot self-promote |
| Delivery | reversible release artifacts and final integration gate | protected final branch only |

Existing runtime surfaces receive these dispositions:

| Surface | Disposition | Migration rule |
| --- | --- | --- |
| `brain_kernel` | retain and make canonical | own new mission events, authority, projections, and gates |
| `RepositoryMission` | adapt, then retire ownership | extract bounded repository effects and receipt verification behind adapters |
| `MissionLoop` | adapt | preserve typed iterative Builder actions as canonical role protocols |
| `AutonomousBrain` | adapt | preserve host invocation, feedback, and point-in-time learning as effect/outcome adapters |
| scheduler/workers | adapt | become delivery of leased canonical work, never a second mission truth |
| `HiveKernel` | adapt/compatibility facade | route new work to canonical contracts while preserving a reversible legacy command surface |

No dual-write migration is permitted.  During each cutover, one canonical
event is written and compatibility projections are derived from it.  A failed
parity check stops promotion and retains the legacy path for rollback.

## Invariants and threats

1. Only `brain_kernel` may create authority-bearing mission events.
2. Capability does not expand authority; every effect is bound to a lease,
   scope, target, actor, and rollback reference.
3. Existing commands remain reversible compatibility surfaces until parity is
   independently demonstrated.
4. No migration may weaken source provenance, acceptance tests, court records,
   or protected-branch policy.
5. A challenger, optimizer, or model may not approve or promote itself.
6. Missing evidence, ambiguous ownership, unsafe effects, and incompatible
   state fail closed.

Primary threats are split-brain mission state, duplicate effects, replay or
out-of-order events, authority confused with capability, legacy bypasses, and
learning contamination.  The event spine, idempotency keys, deterministic
projections, explicit adapters, held-out evaluation, and append-only evidence
address these threats; residual risk is handled by the migration gates.

## Consequences

This decision gives new work one source of truth and makes the competing
runtime surfaces measurable migration clients.  It requires adapter work,
parity fixtures, replay tests, and a temporary compatibility layer.  It does
not authorize runtime implementation in this architecture node; later nodes
must produce the executable contracts and adapters under their own scopes.

## Rollback and evidence

Rollback is a revert of the exact migration candidate or a stop at the last
accepted adapter boundary.  Existing legacy paths and receipts remain intact;
no history rewrite or silent deletion is allowed.  Promotion requires exact
event/projection parity, effect idempotency tests, independent Curator
verification, and a release-branch receipt.
