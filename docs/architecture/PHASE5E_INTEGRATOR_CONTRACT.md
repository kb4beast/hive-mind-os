# Phase 5E — inert Integrator deep-playbook contract

- **Status:** started; bounded stacked candidate only
- **Base:** `agent/phase5a-orchestrator-shadow` at normal merge commit
  `38ecbd176f3ae5b63b116c6a182a2889cd5d16a6`
- **Authority:** none
- **Activation:** inert
- **Supported API/CLI/runtime delta:** none

## Objective

Add a package-private Integrator intake that reconstructs the exact integration scope, inventories
versioned contract and dependency boundaries, preserves data and evidence lineage, and carries all
unresolved Phase 5D debt into a typed Steward handoff. This phase does not write adapters, execute
migrations, approve release, merge branches, activate agents, or resolve inherited debt by label.

## Normative inputs

1. The combined Phase 5A–5D integration head.
2. `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md`.
3. The existing Generation Zero and Phase 2 Integrator definitions.
4. Curator output identity and evidence references supplied through a strict request envelope.
5. Exact repository, tenant, request, commit, and tree scope.

## Initial typed outputs

The first implementation increment emits four separately digest-bound outputs:

1. `integration_scope` — immutable scope and affected boundary inventory.
2. `compatibility_plan` — exact checks to be run later, each truthfully marked `not-run`.
3. `debt_register` — the five inherited Phase 5D debt items, still open and release-blocking.
4. `steward_handoff` — a blocked handoff that preserves required evidence and grants no authority.

Later Phase 5E increments may add distinct versioned outputs for full contract inventory, dependency
lineage, adapter replacement, migration, rollback, conformance, and integration receipts. They may
not collapse the four initial outputs into an untyped prose blob.

## Fixed identity and scope

- Candidate agent: `hive-agent:integrator:v2-shadow-1`
- Candidate definition: `hive-agent-definition:integrator:v2-shadow-1`
- Base definition: `hive-agent-definition:integrator:v2-candidate`
- Repository: `github:kb4beast/hive-mind-os`
- Tenant: `tenant:kb4beast`
- Accepted integration base: `38ecbd176f3ae5b63b116c6a182a2889cd5d16a6`
- Next role: Steward, advisory and blocked until evidence obligations are satisfied

Any locally resealed substitution of repository, tenant, accepted base, authority, activation,
release status, debt status, or next-role semantics must fail validation.

## Inherited debt

The exact required set is:

- `P5D-DEBT-01` — Ruff repairs demonstrated but not committed.
- `P5D-DEBT-02` — two Pyright `Mapping`/`dict` errors.
- `P5D-DEBT-03` — unresolved Python 3.11 worker-test failure.
- `P5D-DEBT-04` — retained temporary write-capable Phase 5D workflows.
- `P5D-DEBT-05` — failed exact-head Constitutional CI and cleanup runs.

The Integrator may plan resolution and define evidence gates. It may not mark an item resolved without
new exact-head receipts satisfying the exit condition in the plan record.

## Invariants

1. Exact built-in `dict` and `list` containers are required at trust boundaries.
2. Unknown fields, duplicate IDs, empty references, malformed SHA-256 values, non-finite numbers,
   private-content fields, and oversized containers fail closed.
3. Request, outputs, and envelope are independently canonical-digest bound.
4. Output semantics must reconstruct from the request and fixed Phase 5E identity; digest resealing
   alone cannot authorize semantic drift.
5. All compatibility checks begin `not-run`; no proposed plan is a test or execution receipt.
6. `release_recommendation` remains `defer`, and release, implementation, execution, promotion, and
   activation authority remain false.
7. The candidate remains package-private and is not exported from `hive_mind_os`,
   `hive_mind_os.foundation`, the CLI, package resources, provider selection, scheduler, or runtime.
8. Temporary workflow removal is an inherited integration obligation, not hidden cleanup.
9. Authenticated independent Integrator or Steward execution is not claimed.

## Initial acceptance tests

- the example request compiles deterministically and validates;
- all five inherited debt IDs are required exactly once and remain open;
- authority, activation, release recommendation, and execution statuses cannot be escalated even
  when all local digests are recomputed;
- repository, tenant, base commit, request, and Curator-envelope bindings cannot be substituted;
- every output digest and the envelope digest are checked directly;
- outputs are defensive against caller mutation;
- package/root exports and the CLI remain unchanged;
- the carried-forward debt plan remains present and machine-readable by ID.

## Rollback

Delete the two package-private Phase 5E modules, their tests, Phase 5E evidence, and this contract.
No data migration, runtime selection, API, CLI, store, provider, scheduler, lease, or activation state
is introduced by this increment.
