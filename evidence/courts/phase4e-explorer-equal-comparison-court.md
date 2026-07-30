# P4E-001 — Explorer equal-evidence comparison readiness court

## Proposition

Can exact Explorer v2 be compared now with Generation Zero under equal evidence and
budgets, or must Phase 4 item 6 remain blocked?

## Source register

All sources are repository-internal at exact commit
`11e4a7b16b00e11caf59c231b5b718f14ed65195`, licensed under the repository license:

- Phase 4 roadmap:
  `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md`, item 6;
- Generation Zero provider path: `src/hive_mind_os/model_backend.py`;
- Phase 4A runner: `src/hive_mind_os/foundation/explorer_shadow.py`;
- Phase 4B candidate: `src/hive_mind_os/foundation/explorer_successor.py`;
- Phase 4C suite, subjects, scorer, and validator:
  `src/hive_mind_os/foundation/explorer_behavior.py` and
  `explorer_behavior_contracts.py`;
- Phase 4D reference bridge:
  `src/hive_mind_os/foundation/explorer_idea_lifecycle.py`;
- existing experiment and benchmark families:
  `src/hive_mind_os/experiment_runner.py` and
  `src/hive_mind_os/benchmark_harness.py`.

No external source is required to establish the current repository's missing
contracts. No unavailable source content is inferred.

## Atomic findings

1. The roadmap requires an actual equal-evidence, equal-budget comparison.
2. Explorer v2 is an inert definition with no runtime renderer or provider binding.
3. Phase 4A accepts an arbitrary injected engine and cannot prove v2 subject identity.
4. Phase 4C deliberately fixes v2 to `forced-not-run`, the suite to
   development-visible/non-holdout/non-comparison, candidate observations to invalid,
   and comparison status to `not-run`.
5. Phase 4C case and oracle digests do not resolve to executable hidden case bodies,
   custody records, or graders.
6. P10 and P13 execute different subjects and task families.
7. Existing budget labels and model-call metadata do not establish equal enforced
   token/cost/time/tool/network/provider envelopes or replayable raw results.
8. Therefore any current comparison would measure a substitute or caller-authored
   observation, not the two named subjects.

## Testimony

- Explorer/Clerk/Advocate `/root/phase4e_explorer` recommended `defer` and rejected
  new readiness code as duplication of Phase 4C.
- Architect/Cross-Examiner `/root/phase4e_architect` recommended `defer`. It found
  that a direct adapter would silently cross prior runtime, holdout, budget, and
  result-truth deferrals.
- Builder/Orchestrator `/root` made no product-code change, retained Phase 4C's
  existing fail-closed behavior, and drafted only ADR, court, index, and blocker
  records.
- Curator `/root/phase4e_curator` reproduced `defer`. Exact probes confirmed the v2
  subject and a resealed candidate observation are rejected, the suite is visible
  and non-comparative, empty scoring stays incomplete/not-run, and P10/P13 never
  execute the candidate. Its decisive Phase 4B/4C plus complete P10/P13 tests passed
  26 tests.
- Integrator `/root/phase4e_integrator` recommended `defer`. Existing components
  provide future seams but cannot bind exact subjects, shared evidence, enforced
  resource envelopes, raw results, or blind scoring without new versioned contracts.
- Optimizer `/root/phase4e_optimizer` recommended `defer`. It required
  preregistered paired statistics, task/repository-level independence, authenticated
  evaluator custody, intention-to-treat retention, anti-gaming gates, and scoped
  claims. Equal enforced ceilings are required; unequal actual consumption inside
  those ceilings is a measured outcome, not pair-invalidating drift.
- Steward `/root/phase4e_steward` recommended `defer`. It required durable private
  raw artifacts, provider usage reconciliation, retry/rate-limit/drift receipts,
  fresh isolated trials, immutable identities, idempotent crash recovery, incomplete-
  pair quarantine, and symmetric retention of wins, losses, errors, timeouts, and
  budget failures. It remanded draft rollback language that allowed evidence removal;
  ADR-032 now requires append-only supersession.

## Verdict

Fresh Judge `/root/phase4e_judge` issued `defer` at exact evidence head
`c4cad6fa8de52475c01fd8a86fc5ca680ebe05e5`. Independent reproduction passed
41 tests and 23 subtests across the decisive Phase 4B, Phase 4C, P10, and P13
surfaces.

The Judge admitted only that the existing repository correctly fails closed, the
four-file governance/evidence delta is nonduplicative, all eight specialist
functions are sufficiently represented for a defer-level decision, and
`B-OPS-09` must remain open. Local role labels are procedural evidence, not
externally authenticated identities.

The bounded Phase 4E readiness adjudication is complete with `defer`; roadmap item
6 is not complete. Phase 5 may proceed only when no work relies on a comparison,
behavior, value, learning, promotion, or activation claim. All ADR-032 reopening
gates remain binding and require a fresh court.

## Proposed disposition

`defer`. Make no product-code change. Preserve blocker `B-OPS-09` and reopen only
after ADR-032's test-only runtime, holdout custody, equality, raw-evidence, scoring,
and independent-court gates exist.

This disposition does not complete roadmap item 6 and authorizes no runtime use,
champion change, learning, promotion, activation, value, or superiority claim.
