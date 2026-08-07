# ADR-047: Verifiable Hive Kernel bounded objective DAG

## Status

Proposed Phase 3 candidate. It adds no model invocation, authority grant, worker,
provider, remote Git operation, or external effect.

## Decision

`brain_kernel.objectives` validates an immutable DAG of Phase 1 `WorkItem` contracts
against a mission charter's work/depth budgets. It rejects duplicate identifiers,
cross-mission work, missing dependencies, orphan parents, depth/fanout overflow,
cycles, missing charter acceptance coverage, and overlapping write scopes that are not
ordered by an explicit dependency. Ready work is a pure projection of proposed nodes
whose dependencies are declared complete.

`DeterministicFixturePlanner` creates reproducible local plans for bugfix, feature,
refactor, documentation, and integration fixtures. It takes no model output. A typed
plan is persisted only by appending existing `work.created` kernel events whose payload
contains the complete canonical work-item document and plan digest. Replanning appends
`SUPERSEDED` transitions for still-proposed prior plan nodes; it never deletes history.
Graphs rehydrate solely from verified event payloads after restart.

`kernel plan` requires a supplied canonical charter and existing local kernel database;
`kernel graph` opens the same database read-only and renders the durable graph. Neither
command creates a mission, accesses a provider, or expands authority.

## Consequences and rollback

The Phase 2 schema is unchanged. Removing this additive planner leaves kernel missions
at `CREATED` and preserves every event. Actual model-planner proposals and authority
envelope issuance remain deferred to later governed phases; no opaque model proposal is
accepted by this slice.

## Evidence obligations

Focused tests cover all fixture kinds, deterministic digesting, restart rehydration,
replanning without deletion, malformed graphs, budget limits, acceptance coverage, and
write-race refusal. Independent courtroom dispositions remain open.
