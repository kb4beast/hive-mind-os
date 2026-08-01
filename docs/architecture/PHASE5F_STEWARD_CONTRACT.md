# Phase 5F — inert Steward deep-playbook contract

- **Status:** started; bounded stacked candidate only
- **Base:** `agent/phase5a-orchestrator-shadow` at normal Phase 5E merge commit
  `eccc8fce1bab5fb289279985198cb8753b3f171c`
- **Authority:** none
- **Activation:** inert
- **Supported API/CLI/runtime delta:** none

## Objective

Add a package-private Steward intake that records current health conservatively, plans reversible
maintenance and recovery checks, preserves evidence integrity, and carries unresolved Phase 5D and
Phase 5E obligations into a typed Optimizer handoff. The intake does not execute maintenance,
modify dependencies, repair infrastructure, approve release, activate agents, or infer health from
missing evidence.

## Normative inputs

1. The combined Phase 5A–5E integration head.
2. `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md`.
3. Existing Generation Zero, Phase 2, and built-in Steward definitions.
4. The Phase 5E Integrator envelope identity and exact repository scope.
5. Exact repository, tenant, request, commit, and tree bindings.

## Initial typed outputs

The first increment emits four separately digest-bound outputs:

1. `health_snapshot` — conservative health state and exact open/resolved debt inventories.
2. `maintenance_plan` — reliability, dependency, observability, evidence, and workflow checks,
   each truthfully marked `not-run`.
3. `recovery_plan` — ordered reversible recovery and verification steps with no execution claim.
4. `optimizer_handoff` — a blocked, authority-free handoff preserving all open obligations.

## Fixed identity and scope

- Candidate agent: `hive-agent:steward:v2-shadow-1`
- Candidate definition: `hive-agent-definition:steward:v2-shadow-1`
- Repository: `github:kb4beast/hive-mind-os`
- Tenant: `tenant:kb4beast`
- Accepted integration base: `eccc8fce1bab5fb289279985198cb8753b3f171c`
- Next role: Optimizer, advisory and blocked while any carried debt remains open

## Debt posture

The exact open set is:

- `P5D-DEBT-01`, `P5D-DEBT-02`, `P5D-DEBT-04`, `P5D-DEBT-05`;
- `P5E-DEBT-01` through `P5E-DEBT-05`.

`P5D-DEBT-03` is retained as resolved by exact-head run `30674773848`; its earlier failure remains
adverse history and cannot be erased.

## Invariants

1. Exact built-in `dict` and `list` containers are required at trust boundaries.
2. Unknown fields, duplicate identifiers, malformed digests, non-finite values, private-content
   fields, and oversized containers fail closed.
3. Missing or non-exact evidence produces `unknown`, never a passing health claim.
4. Any open carried debt fixes overall health to `degraded` and release recommendation to `defer`.
5. Every maintenance and recovery check begins `not-run`; plans are not execution receipts.
6. Recovery steps are ordered, reversible, evidence-preserving, and cannot delete dissent or failed
   receipts.
7. Request, outputs, and envelope are independently canonical-digest bound and reconstructable.
8. Implementation, maintenance execution, dependency mutation, release, promotion, and activation
   authority remain false.
9. The candidate remains package-private and outside root/package APIs, CLI, provider, scheduler,
   store, migration, lease, and runtime selection.
10. Authenticated independent Steward or Optimizer execution is not claimed.

## Initial acceptance tests

- the example request compiles deterministically and validates;
- the exact nine open debts and one resolved debt are preserved;
- open debt forces degraded health and a deferred release recommendation;
- all maintenance and recovery steps remain `not-run` and authority-free;
- repository, tenant, accepted commit, tree, Integrator envelope, debt status, and next role cannot be
  substituted even when local digests are recomputed;
- every output and envelope digest is checked directly;
- outputs are defensive against caller mutation;
- modules remain package-private and the carry-forward plan remains present.

## Rollback

Delete the two package-private Phase 5F modules, their tests, Phase 5F evidence, and this contract.
No maintenance, dependency, runtime, data, provider, scheduler, lease, API, CLI, or activation state is
introduced by this increment.
