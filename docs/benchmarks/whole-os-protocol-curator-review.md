# N02 independent evaluation Curator review

Reviewed builder commit: `ed2ac0a3bdbd4e5ed6b472b5518891dedab8130c`

Reviewed tree: `776df43fd5a463d8c9c73f75f86533fcd157d364`

Review worktree: `C:\h\wos-n02-review`

Review branch: `codex/whole-os-n02-curator`

Curator identity: `/root/n00_curator`, acting as the separate N02 evaluation Curator

Reviewed at: `2026-09-14T02:58:27Z`
Verdict: **ADAPT — N02 is not accepted or frozen for N30 consumption.**

This review did not execute or download a comparator, open a holdout, spend provider resources, or make a superiority claim.

## Independence and provenance

I did not participate in the N02 build and created an isolated worktree directly from the exact builder commit:

```powershell
git worktree add -b codex/whole-os-n02-curator C:\h\wos-n02-review ed2ac0a3bdbd4e5ed6b472b5518891dedab8130c
git show -s --format='%H%n%P%n%T%n%s' HEAD
git diff-tree --no-commit-id --name-status -r HEAD
```

The reviewed commit has parent `7dff0a807936b5be33099bdaa5c242674c624776`, tree `776df43fd5a463d8c9c73f75f86533fcd157d364`, and exactly four changed files: `campaign_metrics.py`, `test_campaign_metrics.py`, `whole-os-match-protocol.json`, and `whole-os-protocol.md`. The six accepted N00 artifact hashes in `N00_CURATOR_REREVIEW.md` all reproduce at this commit.

Independence is session/worktree separation, not host separation: builder and Curator used the same machine and Git object database. No private evaluator store, signed holdout binding, comparator archive, or N30 resource lease was supplied for inspection.

## Commands and passing evidence

Import provenance was explicitly bound to this review worktree:

```powershell
$env:PYTHONPATH=(Resolve-Path -LiteralPath .\src).Path
python -c "import hive_mind_os; print(hive_mind_os.__file__)"
```

It resolved to `C:\h\wos-n02-review\src\hive_mind_os\__init__.py`.

I ran the required focused suite:

```powershell
python -m unittest tests.test_campaign_metrics -v
```

Result: 6 tests passed, 0 failed, in 0.087 seconds.

I also ran the relevant inherited benchmark/evaluation suites:

```powershell
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
```

Result: 58 tests passed, 0 failed, in 20.542 seconds. `git diff --check HEAD^ HEAD` also passed.

The reviewed file hashes are:

| File | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `c0f306b675a2075608a7a9553eb3403c7109317e58901f856c8bcc4096df3e92` |
| `tests/test_campaign_metrics.py` | `739f0197804eca1555f00f7e160c3aa42cac10d27ac918e82fb25b905807bd9d` |
| `docs/benchmarks/whole-os-match-protocol.json` | `355fd120e6bf6a4a362fd00ca8a58fdb476257e1465bb5f286d198e03c962d8a` |
| `docs/benchmarks/whole-os-protocol.md` | `2bddd7f958548407aa9aa458223489d2cf4d924c308dbf63d876714fb91627e9` |

The implementation has useful foundations: it preserves `None` for ordinary unknown usage/cost, retains all raw attempt rows, averages repetitions within family before the seeded 10,000-resample bootstrap, implements the strict default `>-0.05` lower-bound check with a hard-gate input, gives a bye only for odd fields, chooses the fewest-bye entrant, rotates deterministically, skips a pairing after two recorded inconclusives, rejects round 25, and never lexically breaks a draw. The protocol text correctly disclaims execution and superiority.

Those positives are not sufficient to meet the frozen N02 contract because the executable counterexamples below pass through the implementation.

## Material findings

### F1 — the checked-in closed protocol is not loadable or immutable

`MatchProtocol` requires every entrant recipe to contain `recipe_digest`, but none of the six recipes in `whole-os-match-protocol.json` has that field. Filtering the JSON to the dataclass fields and attempting construction fails with `CampaignMetricsError: each entrant requires a frozen recipe digest`. There is no closed-schema loader or canonical protocol digest binding the JSON artifact to the Python contract.

The dataclass is frozen only at its top level. It retains caller-owned mutable dictionaries. After successful construction, this mutation succeeds without validation:

```python
recipes["MB0"]["recipe_digest"] = "not-a-digest"
```

Two different entrant IDs with the same complete recipe digest are also accepted, contrary to the one-entrant/no-two-votes rule. The implementation does not validate the required MB0–MB3 and MC0–MC1 sets, separate tracks, exact digest dimensions, MH1–MH4 recipes, operating regimes, scenario/block sets, or terminal-rule contents.

Required repair: define one canonical closed schema and parser; recursively freeze/copy mappings; bind the checked-in JSON bytes/canonical digest; enforce the exact IDs, tracks, recipe-shape/digest rules, duplicate-complete-behavior collapse/rejection, hybrid states/regimes, and terminal rules. Add round-trip and mutation negative tests.

### F2 — the experiment is described but not actually frozen

The JSON contains stratum labels such as `small-bug`, not concrete scenario task IDs or membership manifests. Neither artifact supplies the published selection/bootstrap seeds, family split/hash, attempts per task, retry/invalid-run rules, development-screening membership, harder hybrid block membership, or untouched promotion-holdout manifest/binding. `resource_lease_ref` is a future placeholder. No independent evaluator signature or digest-bound private manifest receipt is present.

The external archive and comparator-rights obligations may legitimately block comparator execution, but they do not permit calling an unbound experiment frozen. Required repair: emit digest-bound public metadata plus externally custodied manifests/attestations for the three disjoint blocks, fixed seeds, family assignments, attempts/repetitions, invalidation/retry rules, sample thresholds, rubric/check-set, selection rule, and bounded lease reference. Preserve holdout contents outside builder custody and retain an evaluator identity/signature receipt. Mark unavailable comparator recipes/lanes DEFERRED rather than assigning fabricated bytes or outcomes.

### F3 — final seals do not establish staged custody or an untouched holdout

`validate_seals(final=True)` checks only that two distinct dictionary keys were seen. It accepts unknown variants `X`/`Y`, identical recipe and candidate digests, the same evaluator, and `stage="development"` as a final pair. It does not bind protocol ID/digest, dataset block, task-family split, operating regime, source/config/model/environment/check/learning digests, evaluator independence, seal time, prior selected-original/hybrid decision, or no-change-after-open invariant.

Conversely, it rejects the same variant sealed in two different stages because it keys only by variant ID, even though the protocol requires an original-stage seal and a later unchanged final binding.

Required repair: make seals stage-specific and append-only, bind them to the complete recipe/candidate/protocol/block/regime digests and independent evaluator, validate admissible entrants/hybrids, require one qualified original and one distinct qualified hybrid in the same regime, and prove the final pair is unchanged before `promotion_holdout` opens. Duplicate behavior digests must not become two finalists.

### F4 — match-decision logic violates the frozen decision rule

The efficiency branch checks noninferiority only in the left-minus-right direction. For success interval `[-0.04, 0.20]`, where the left is noninferior but the right is not, favorable cost/time intervals return `LEFT`; the contract requires both candidates to satisfy noninferiority before efficiency decides.

The `or vice versa for time/cost` branch is absent. A time-dominant candidate with cost within 10% returns `DRAW`. Opponent symmetry is also wrong: the right candidate can be conclusively cheaper with time within 10% and still return `DRAW`, because the code requires both left/right ratio lower bounds to exceed 1.10. Inverting a ratio interval requires reciprocal bounds, not that condition.

`noninferior` also exposes an arbitrary `margin` parameter; passing `margin=-1.0` makes a `-0.50` lower bound pass despite the frozen `-0.05` margin. A one-sided hard-gate failure returns an ordinary `LEFT`/`RIGHT` result, with no typed safety quarantine path.

Required repair: freeze the margin in the admitted protocol, validate both directional noninferiority conditions, implement both cost-first/time-within-budget and time-first/cost-within-budget branches symmetrically using correct ratio inversion, and return a typed decision that separates safety quarantine from a resolved competitive loss. Add mirrored and boundary tests.

### F5 — the bracket implementation does not implement tournament state

`schedule_round` accepts only plain IDs and can pair `MB0` directly with `MC0`, violating separate tracks and compatibility. It has no scenario-task/block assignment, no protocol or evidence-receipt binding, and no rule preventing a repeated model execution. It emits pairs but has no append-only match/loss/inconclusive/bye/quarantine ledger, third-loss transition, partial-bracket receipt, no-schedulable-pairs verdict, one-survivor rule, or resource-lease exhaustion/checkpoint behavior. The two-inconclusive count is unscoped and could leak across stages. Max-round validation alone is not the required bounded tournament.

Required repair: implement or validate a deterministic stage state transition tied to the closed protocol. It must filter by track/regime, cycle the frozen scenario blocks by round/pair index, reuse one frozen variant/task/seed receipt, update only resolved losses, eliminate on exactly the third loss, quarantine safety violations separately, scope inconclusive history per stage, issue odd-only neutral byes, and preserve an INCONCLUSIVE partial bracket on no schedulable pair, round 24, or lease exhaustion without renewal.

### F6 — metric and interval validation is not fail-closed enough

`AttemptMetric` accepts `NaN` for time/usage/cost because `_nonnegative` checks `< 0` but not finiteness. `PairedInterval` has no validation for finite/order-consistent bounds, family count, fixed 10,000 resamples, or 95% confidence. `paired_family_bootstrap` likewise accepts non-finite observations and can return a qualification-looking interval from one or two families; there is no stage-bound 12-family/30-family minimum or paired-family completeness check. `noninferior` accepts any truthy `hard_gates_pass` value.

The attempt schema has one generic `usage_units` value and does not represent provider billed-cache distinctions, separate input/output/cache/reasoning measurements where available, units/currency/cost basis identity, or actual provider availability. `summarize_attempts` retains raw rows but omits an explicit count for eligible `not_attempted` cases and does not expose a complete eligibility/result matrix, so exclusion reasons are not auditable from the summary alone.

Required repair: reject booleans, NaN, and infinity in all numeric fields/intervals; validate interval ordering and fixed confidence/resamples; enforce screening/final family thresholds at the appropriate stage; bind paired completeness; expand usage/cost/cache/availability fields with explicit measured/estimated/unknown bases and units; and return complete eligibility/result/exclusion counts without converting unknowns to zero.

### F7 — acceptance negative controls are substantially incomplete

The six new tests prove the narrow happy paths but do not reject changed rubrics, mutable recipes, duplicate complete behavior digests, the checked-in JSON mismatch, dropped/eligible-not-attempted categories, non-finite measurements, invalid intervals, undersized final samples, unpaired families, unknown/wrong-stage/equivalent final seals, cross-track matches, incorrect reciprocal efficiency, time-first efficiency, safety quarantine loss, repeated receipt execution, third-loss elimination, no-schedule termination, partial bracket preservation, or lease exhaustion. The passing inherited suites do not exercise this new module's missing state transitions.

Required repair: add deterministic positive and negative cases for every item above, including repeated-seed byte equality and a mutation test for every frozen task/rubric/budget/selection input.

## Executed counterexample summary

With the reviewed module imported from this worktree, a single read-only Python probe observed:

```text
nan_accepted True
frozen_mapping_mutated not-a-digest
duplicate_behavior_digest_accepted 2
json_protocol_load CampaignMetricsError each entrant requires a frozen recipe digest
margin_override True
one_sided_NI_efficiency LEFT
time_first_left DRAW
symmetric_right DRAW
wrong_stage_unknown_duplicate_final_seals accepted
same_variant_stage_rebind CampaignMetricsError
cross_track_pair (ScheduledPair(left='MB0', right='MC0', bye=False),)
```

These are contract failures, not claims about comparator performance.

## Disposition

The N02 approach is suitable for repair, so the judgment is ADAPT rather than REJECT. The current commit must not be described as a frozen `MatchProtocol`, evaluator-signed holdout design, executable triple-elimination implementation, or N30-ready input. Repair F1–F7 on a successor builder commit, retain this losing review and the current passing-test receipts, then obtain a new independent exact-commit Curator review.

Open comparator archives, rights, runtime access, evaluator custody, and lease issuance remain explicit obligations. No comparator was executed and no relative quality, cost, time, championship, or superiority result was established.
