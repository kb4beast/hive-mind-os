# N02 independent evaluation Curator rereview

Reviewed repair commit: `b91bcd6b3195ad70901f7e3169538381b05f49b6`

Reviewed tree: `804a94be7ba35ed13b6c34efca409223d8d34371`

Review worktree: `C:\h\wos-n02-rereview`

Review branch: `codex/whole-os-n02-curator-r2`

Curator identity: `/root/n00_curator`, acting as the separate N02 evaluation Curator

Reviewed at: `2026-09-14T03:09:41Z`

Verdict: **ADAPT — N02 remains unaccepted and must not be consumed by N30.**

This review did not execute or download comparators, open a private holdout, spend provider resources, or make a championship or superiority claim.

## Independence and inspected change

I did not author the repair. I created a new worktree directly from the requested exact commit:

```powershell
git worktree add -b codex/whole-os-n02-curator-r2 C:\h\wos-n02-rereview b91bcd6b3195ad70901f7e3169538381b05f49b6
git show -s --format='%H%n%P%n%T%n%s' HEAD
git diff-tree --no-commit-id --name-status -r HEAD
git diff --stat ed2ac0a3bdbd4e5ed6b472b5518891dedab8130c..HEAD
```

The repair is the direct child of the rejected builder commit `ed2ac0a3...`. It modifies only `src/hive_mind_os/campaign_metrics.py`, `tests/test_campaign_metrics.py`, and `docs/benchmarks/whole-os-match-protocol.json`. The prose protocol is unchanged. I read the prior review from review commit `c56b28f4de2220fe79a5885248a71d62c56784c7` with `git show` because that append-only review is on its independent branch, not in the builder ancestry.

Independence is worktree/session separation, not host separation. The builder and Curator used the same machine and Git object database. No externally custodied dataset manifest, evaluator signature, comparator archive, or issued resource lease was available to inspect.

## Test and import evidence

I bound imports to this worktree and ran the complete commands from the original review:

```powershell
$env:PYTHONPATH=(Resolve-Path -LiteralPath .\src).Path
python -c "import hive_mind_os; print(hive_mind_os.__file__)"
python -m unittest tests.test_campaign_metrics -v
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
git diff --check ed2ac0a3bdbd4e5ed6b472b5518891dedab8130c..HEAD
```

Import provenance resolved to `C:\h\wos-n02-rereview\src\hive_mind_os\__init__.py`. The repaired focused suite passed 5 tests with 0 failures in 0.060 seconds. The inherited benchmark/evaluation command passed 58 tests with 0 failures in 20.562 seconds. The diff check passed.

Reviewed hashes:

| File | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `a31cad0a17f8a8ceda637fffcb6aa1652ea3381b5099c5b34a83775fa2bbf26a` |
| `tests/test_campaign_metrics.py` | `f9ef5bb8906d537f023c19a890724d5bc37d1041cca80f1aa7b17efcee6908e2` |
| `docs/benchmarks/whole-os-match-protocol.json` | `d48517458d956d62bf8fe0980331f72bbb58f8290605c439a52a7305f867d073` |
| `docs/benchmarks/whole-os-protocol.md` | `2bddd7f958548407aa9aa458223489d2cf4d924c308dbf63d876714fb91627e9` |

Passing unit tests do not close the findings below; the executable counterexamples were run separately against the exact reviewed import.

## Prior findings that are closed

- The JSON is now loadable through `load_match_protocol`, yielding six MB/MC recipes and four MH recipes.
- Protocol recipe/digest mappings are recursively read-only; top-level, nested-recipe, and digest-rule mutation attempts raise.
- Two recipe IDs resolving to the same complete eight-field behavior digest reject.
- `NaN` and infinity reject in attempts, intervals, and bootstrap observations.
- The noninferiority margin is no longer caller-overridable, and non-boolean hard-gate inputs reject.
- Left time-first/cost-within-10% and mirrored right cost-first/time-within-10% examples return the expected winner.
- The summary now exposes a complete eligibility/result matrix, including eligible `not_attempted`.
- A valid original-stage plus hybrid-stage pair can be rebound unchanged to final-stage seals; an unqualified final pair rejects.
- `BracketState` filters entrants by track in its ordinary schedule path. A resolved third loss removes the entrant from the next schedule; quarantine is kept separately; round 24 and `apply(..., lease_active=False)` produce `max_rounds` and `lease_exhausted`; the odd-field bye remains neutral and deterministic.

These are meaningful repairs, but they do not freeze a safe experiment or protect the holdout.

## Remaining material findings

### R1 — recipe and experiment digests are synthetic and the experiment manifest is outside the protocol digest

The checked-in JSON has empty `entrant_recipes` and `hybrid_recipes`. The loader manufactures every eight-field recipe digest as `sha256([recipe_seed, entrant_id, field])`. Those values are not digests of the pinned source/binary, prompt, model, command/profile, tool, context, check policy, or learning policy. The resulting `MatchProtocol` loses the fact that comparator archives/rights and future candidate bytes are unavailable and offers no per-recipe AVAILABLE/DEFERRED state. This converts missing evidence into plausible-looking immutable digests.

The loader also removes `experiment_manifest` and `recipe_seed` before constructing the protocol. `protocol_digest` therefore does not bind the published selection seed `271828`, bootstrap seed `314159`, family thresholds, repetitions, retry rule, or open holdout-custody obligation. Mutating those JSON fields would not change the protocol digest.

Required repair: never synthesize evidence digests for unavailable recipe components. Preserve explicit unresolved component/status fields and DEFERRED entrants until actual immutable sources/configurations are sealed. Put the complete experiment manifest, recipe construction rule/version, availability states, seeds, task/family/block manifest digests, retry rules, thresholds, and custody/signature references inside the canonical protocol document and digest. Add a raw-JSON/canonical-digest mutation test for every frozen field.

### R2 — the alleged frozen datasets and evaluator signature remain absent

The JSON contains twelve generic IDs `f01`–`f12`, not the concrete family/task memberships for the thirteen required strata. It provides no mapping from those IDs to small bug, feature, absent tests, multi-file, cross-language, self-runtime, ambiguous backlog, provider failure, restart, tenant isolation, draft export, endpoint learning, and Roblox runtime. No disjoint development/harder-hybrid/promotion-holdout manifest digests or externally custodied contents were supplied. The JSON explicitly says `holdout: externally-custodied; signature obligation OPEN`; there is no evaluator signature/attestation.

This is honest as an open obligation, but N02 step 8 requires the evaluator to sign the protocol/holdout binding before N02 acceptance. Required repair: create and independently attest the private manifests outside builder custody; expose their immutable digests, family split, operating regimes, task counts, retry/invalidation rules, and evaluator identity/signature in the protocol. Missing comparator rights/runtime may defer individual lanes, but the frozen selection and custody records cannot remain placeholders.

### R3 — development scheduling opens the promotion holdout

`BracketState.schedule` passes all three dataset-stage IDs to `schedule_round`. Its block formula assigns the first development pair `promotion_holdout` and the second `development-screening`. The exact probe returned:

```text
development_blocks ['promotion_holdout', 'development-screening']
promotion_holdout_exposed True
```

This directly violates untouched final-data custody. The stage field is otherwise ignored: an `original` whole-campaign bracket immediately includes `MH1`–`MH4` alongside `MC0`/`MC1`, before the hybrids' separately frozen harder-development stage. Scenario task IDs are never assigned or cycled, and there is no variant/task/seed evidence-receipt identity preventing a repeated model run.

Required repair: make stage select exactly one permitted, digest-bound dataset block and eligible entrant set; development must never reference `promotion_holdout`, original stages must exclude unsealed hybrids, and hybrid development must use only the disjoint harder block. Assign the frozen scenario task/seed/receipt key deterministically by round and pair. Final scheduling must require the accepted final seals before revealing holdout handles.

### R4 — bracket state is mutable and its terminal/transition validation remains incomplete

`BracketState` is frozen only at the attribute level. Caller-owned `losses`, `byes`, and `inconclusive` dictionaries remain mutable after construction. `apply` accepts arbitrary pairs not issued by the state: a builder-component state accepted `ScheduledPair("MB0", "MC0")` and incremented `MC0`'s loss. An unknown outcome string such as `TYPO` is silently recorded as an inconclusive rather than rejected.

One survivor is scheduled for a bye forever instead of producing `one_survivor`. When all pairs have two prior inconclusive meetings, the scheduler returns four unmatched entries and `apply` leaves `terminal=None` rather than `no_schedulable_pairs`. `schedule(..., lease_active=False)` returns an empty tuple without checkpointing a `lease_exhausted` state; only a later `apply` call does so. Directly exported `schedule_round` still pairs `MB0` with `MC0` because it has no protocol/track input. No append-only receipt ledger binds issued pair, outcome, block, task, seed, loss, bye, quarantine, or terminal transition.

Required repair: recursively freeze/validate all state maps and IDs/counts, retain issued-schedule identity, reject outcomes and pairs outside that schedule/track/stage, and implement explicit `one_survivor`, `no_schedulable_pairs`, round/lease checkpoint, and partial-bracket states. Do not use empty return values as an ambiguous terminal signal. Preserve one-execution receipt keys and reject replay that would duplicate model work or losses.

### R5 — numeric and interval validation still permits invalid evidence

The new `_num` rejects non-finite numbers but no longer rejects negative values. The exact probe accepted negative active time, provider cost, and token usage. It also accepted detailed input usage while total usage was unknown, and a caller-owned `checks` list remained mutable after construction.

`PairedInterval(None, None, 1, 0)` is accepted because the all-known/all-unknown condition is incorrect. A known interval with `family_count=0` is also accepted. `paired_family_bootstrap` defaults `minimum_families=0`, so a one-family result succeeds; callers can bypass the 12-family screening and 30-family final rules, and no three-repetition/family-pair completeness is bound to a stage. Currency, usage unit, cost currency requirement, detailed usage bases, and eligibility/exclusion reason are not validated sufficiently for reproducible billing comparisons.

Required repair: require finite nonnegative time/usage/cost/counter values; enforce coherent total/detailed measurement bases and immutable event/check sequences; require intervals to be wholly known or wholly unknown with family-count coherence; remove caller-selectable sample minima in favor of protocol/stage-derived thresholds; and validate paired family/task membership plus predeclared repetition counts. Bind currency/unit/provider availability and billed-cache bases explicitly.

### R6 — seal custody still accepts unbound evidence

An `original` seal with an arbitrary block digest is accepted. An evaluator named `builder` is accepted unless a caller happens to pass a matching expected evaluator string; no proposer/builder identities or independent evaluator signature are bound. `sealed_at` is only a whitespace-free identifier, not a validated timestamp. Final block validation compares against `canonical_digest("promotion_holdout")`, the digest of a public label, not the private holdout manifest. Because the experiment manifest is absent from `protocol_digest`, final seals do not bind the frozen seeds/tasks/rubric/custody record.

Required repair: bind every stage to its actual external block-manifest digest and admitted independent evaluator signature/identity; validate evaluator separation from proposer/builder/affected champion; validate append-only stage order and time; and bind all selection/rubric/task/seed/operating-regime data through the protocol digest. A label hash is not a holdout seal.

### R7 — prose, JSON, and tests are not synchronized

The prose says the closed JSON carries immutable recipe dimensions and the defined MB/MC/MH compositions, while JSON stores empty recipe maps and the loader generates opaque seeded placeholders without the stated composition semantics. The prose lists thirteen task strata; JSON has twelve unclassified IDs. The prose promises an untouched holdout; the implementation cycles the holdout into development. The prose says stop at one survivor/no schedulable pairs; the state machine does neither.

The repaired test file has five tests and does not exercise these contradictions, negative numbers, partial intervals, stage/block isolation, experiment-manifest digest mutation, evaluator independence/signature, arbitrary pair/outcome rejection, one-survivor/no-schedule termination, state-map immutability, receipt replay, or signed holdout binding.

Required repair: make the Markdown, closed JSON, loader, dataclasses, and tests describe and enforce one canonical contract. Add negative controls for each remaining counterexample and a synchronization test that loads the exact checked-in artifact and checks its canonical digest and public/private manifest bindings.

## Replayed counterexample evidence

The prior counterexamples now produce a mix of fixed and still-failing results:

```text
json_load WOS-N02-MATCH-01 1.1.0 6 4
top_recipe_mutation AttributeError
nested_recipe_mutation AttributeError
duplicate_complete_behavior CampaignMetricsError
active nan CampaignMetricsError
active inf CampaignMetricsError
active -1.0 ACCEPTED
negative_cost ACCEPTED
negative_usage ACCEPTED
interval (None, None, 1, 0) ACCEPTED
one_family_default ACCEPTED
margin_override TypeError
time_first_left LEFT
cost_first_right RIGHT
both_gate_fail QUARANTINE_LEFT
wrong_original_block ACCEPTED
unbound_evaluator_independence ACCEPTED
stage_final_pair ACCEPTED
unqualified_final CampaignMetricsError
direct_cross_track (ScheduledPair(left='MB0', right='MC0', bye=False, block_id=None),)
promotion_holdout_exposed True
whole_original_entrants ['MC0', 'MC1', 'MH1', 'MH2', 'MH3', 'MH4']
bracket_nested_mutation {'MB0': 3}
one_survivor_schedule (ScheduledPair(left='MB0', right=None, bye=True, block_id=None),) terminal None
no_sched_pairs (...) terminal_after None
lease_schedule_only () state_terminal None
cross_track_apply ACCEPTED {'MC0': 1}
unknown_outcome ACCEPTED
```

When both hard gates fail, `decide_match` returns only `QUARANTINE_LEFT`; a repaired typed decision should preserve both safety violations rather than hide the right-side violation.

## Disposition and obligations

The repair closes several important defects, so ADAPT remains appropriate rather than REJECT. However, R1–R7 are acceptance blockers. N02 is not a frozen, evaluator-signed, holdout-safe, N30-ready protocol at commit `b91bcd6b...`. Preserve this repair and its passing receipts as partial evidence, repair on a successor commit, and obtain another independent exact-commit review.

Remaining external obligations are explicit and unchanged: archive and license/rights custody for EX01/EX03/EX06/EX07 and benchmark datasets, actual comparator availability, externally held disjoint task/family manifests, independent evaluator signature/holdout binding, and a bounded N30 resource lease. These obligations authorize no fabricated digests or results. No comparator was run and no superiority conclusion exists.
