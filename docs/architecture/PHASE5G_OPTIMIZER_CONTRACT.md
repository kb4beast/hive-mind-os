# Phase 5G — inert Optimizer deep-playbook contract

- **Status:** started; bounded stacked candidate only
- **Base:** `agent/phase5a-orchestrator-shadow` at normal Phase 5F merge commit
  `eebda921352271c7d534009fe5ac8ba2306a2410`
- **Authority:** none
- **Activation:** inert
- **Supported API/CLI/runtime delta:** none

## Objective

Add a package-private Optimizer intake that preserves the current champion, proposes a separately
versioned challenger, defines held-out and comparator evaluation requirements, and produces a
blocked promotion-court handoff. It carries all unresolved Phase 5D, Phase 5E, and Phase 5F debt
without treating plans, labels, or local digests as outcome evidence.

The intake does not access protected holdout data, execute evaluations, mutate the champion, edit
skills, promote a challenger, approve release, activate agents, or claim improvement or superiority.

## Normative inputs

1. The combined Phase 5A–5F integration head.
2. `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md`.
3. Existing Generation Zero, Phase 2, and built-in Optimizer definitions.
4. The Phase 5F Steward envelope identity and exact repository scope.
5. Exact repository, tenant, request, commit, tree, champion, challenger, and holdout-manifest
   bindings.

## Initial typed outputs

The first increment emits four separately digest-bound outputs:

1. `baseline_snapshot` — degraded health, incomplete evidence, current champion identity, and exact
   open/resolved debt inventories.
2. `challenger_plan` — a separately versioned proposed challenger with the champion fixed unchanged.
3. `evaluation_plan` — held-out outcome, safety, regression, cost, latency, authority, and rollback
   checks, all truthfully marked `not-run`.
4. `promotion_handoff` — a blocked independent-court handoff with no promotion or release authority.

## Fixed identity and scope

- Candidate agent: `hive-agent:optimizer:v2-shadow-1`
- Candidate definition: `hive-agent-definition:optimizer:v2-shadow-1`
- Base definition: `hive-agent-definition:optimizer:v2-candidate`
- Repository: `github:kb4beast/hive-mind-os`
- Tenant: `tenant:kb4beast`
- Accepted integration base: `eebda921352271c7d534009fe5ac8ba2306a2410`
- Champion: `champion:phase5a-5f-integration`
- Challenger: `challenger:phase5g-optimizer-shadow-1`
- Next stage: independent promotion court, blocked while any debt or evidence obligation remains open

## Debt posture

The exact open set contains fourteen items:

- `P5D-DEBT-01`, `P5D-DEBT-02`, `P5D-DEBT-04`, `P5D-DEBT-05`;
- `P5E-DEBT-01` through `P5E-DEBT-05`;
- `P5F-DEBT-01` through `P5F-DEBT-05`.

`P5D-DEBT-03` remains resolved by later exact-head cross-version evidence. Its original adverse
failure remains part of the evidence history.

## Invariants

1. Exact built-in `dict` and `list` containers are required at trust boundaries.
2. Unknown fields, duplicate identifiers, malformed digests, private-content fields, and oversized
   containers fail closed.
3. The challenger identity must differ from the champion and must never mutate the champion in place.
4. Protected holdout contents are never accepted; only a canonical manifest digest may be bound.
5. Evaluation execution remains `not-run`; plans and locally computed scores are not experiment
   receipts.
6. Open debt and degraded health prohibit improvement, superiority, promotion, release, and
   production-readiness claims.
7. Losing, null, adverse, and inconclusive results must be preserved by any future execution path.
8. Every proposed change has an explicit rollback reference and evidence-preservation requirement.
9. Request, outputs, and envelope are independently canonical-digest bound and semantically fixed.
10. Self-promotion, skill mutation, champion mutation, release, and activation authority remain false.
11. The candidate remains package-private and outside root/package APIs, CLI, provider, scheduler,
    store, migration, lease, and runtime selection.
12. Authenticated independent Optimizer, evaluator, promotion-court, or Judge execution is not
    claimed.

## Initial acceptance tests

- the example request compiles deterministically and validates;
- the exact fourteen open debts and one resolved debt are preserved;
- degraded health and incomplete evidence force `defer` and block promotion;
- champion and challenger identities are distinct and champion mutation remains prohibited;
- protected holdout access and evaluation execution remain prohibited or `not-run`;
- superiority, self-promotion, release, and skill-change authority cannot be introduced even when
  local digests are recomputed;
- repository, tenant, commit, tree, Steward envelope, debt, champion, challenger, and holdout digest
  substitutions fail closed;
- every output and envelope digest is checked directly;
- outputs are defensive against caller mutation;
- modules remain package-private and the carry-forward plan remains present.

## Rollback

Delete the two package-private Phase 5G modules, their tests, Phase 5G evidence, and this contract.
No champion, challenger registry, skill, evaluation, holdout, provider, scheduler, store, lease, API,
CLI, runtime, promotion, release, or activation state is introduced by this increment.
