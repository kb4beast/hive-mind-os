# Phase 5H — Role-Deepening Consolidation Court

- **Status:** started; bounded stacked candidate only
- **Base:** `agent/phase5a-orchestrator-shadow` at normal Phase 5G merge commit
  `e65be29ae1380743dfb6804e12c83af43abd291d`
- **Authority:** none
- **Activation:** inert
- **Release authority:** none
- **P20 status:** ineligible

## Objective

Create a package-private, deterministic court intake that reconstructs the complete role-deepening
sequence, binds every open or reopened debt item, records evidence coverage and conflicts, and emits
a machine-readable non-release disposition.

This court does not execute role candidates, authenticate judges, resolve debt by declaration,
release software, promote challengers, deploy, activate runtime behavior, or substitute for P20
Release Readiness.

## Consolidated role sequence

The exact admitted sequence is:

1. Phase 4 — Explorer
2. Phase 5A — Orchestrator
3. Phase 5B — Architect
4. Phase 5C — Builder
5. Phase 5D — Curator
6. Phase 5E — Integrator
7. Phase 5F — Steward
8. Phase 5G — Optimizer

Every entry remains a bounded candidate. Integration, naming, procedural role separation, local
digests, or broad passing CI jobs do not grant authority, activation, authenticated independence,
release readiness, production readiness, or superiority.

## Initial typed outputs

The first increment emits four separately digest-bound outputs:

1. `role_inventory` — exact phase/role order and bounded authority posture.
2. `evidence_coverage` — evidence categories with `partial`, `missing`, or `blocked` status only.
3. `conflict_register` — all open/reopened debt plus structural conflicts and required exits.
4. `court_disposition` — `defer-non-release`, P20 ineligible, and no promotion/release authority.

## P20 boundary

Phase 5H is not P20. P20 requires, among other prerequisites, completed P18 and P19 evidence,
externally retained evidence, authenticated distinct judges, satisfied applicable blockers,
operational evidence, and a terminal release-readiness adjudication. None of those requirements is
established by this consolidation court.

## Invariants

1. Exact built-in `dict` and `list` containers are required at trust boundaries.
2. Unknown fields, duplicate identifiers, malformed digests, private-content fields, and oversized
   containers fail closed.
3. The exact eight-role sequence cannot be reordered, omitted, renamed, or expanded.
4. Every open or reopened Phase 5D–5G debt item is required exactly once.
5. Evidence coverage cannot be represented as complete or independently verified.
6. Conflicts cannot be marked resolved by the court intake.
7. The only admitted disposition is `defer-non-release`.
8. P20 eligibility, release readiness, production readiness, promotion eligibility, authenticated
   independence, and superiority remain false.
9. Request, outputs, and envelope are independently canonical-digest bound.
10. The candidate remains package-private and outside root/package APIs, CLI, provider, scheduler,
    store, migration, lease, deployment, release, and runtime selection.
11. One assistant may perform separate procedural role passes, but authenticated independent actors
    or judges are not claimed.

## Initial acceptance tests

- the example request compiles deterministically and validates;
- all eight roles appear once in exact lifecycle order;
- all twenty open/reopened debt items appear exactly once;
- P20 eligibility and all release/promotion/production claims remain false;
- semantic resealing cannot change role order, debt status, evidence coverage, or disposition;
- every output digest and the envelope digest are checked;
- caller mutation cannot alter rebuilt outputs;
- the modules remain package-private;
- the carry-forward plan is present; and
- no supported API, CLI, or runtime surface is added.

## Rollback

Delete the two package-private Phase 5H modules, their focused tests, Phase 5H evidence, and this
contract. No runtime, release, deployment, registry, data, provider, scheduler, lease, API, CLI, or
activation state is introduced by this increment.
