# N02 independent evaluation Curator rereview — round 3

Reviewed repair commit: `783423ef6be2420310059a7e2e2cb08f47508cb8`

Reviewed tree: `0081cddf148e374ca4adb97e643273eeffe9ca06`

Review worktree: `C:\h\wos-n02-rereview-r3`

Review branch: `codex/whole-os-n02-curator-r3`

Curator identity: `/root/n00_curator`, acting as the separate N02 evaluation Curator

Reviewed at: `2026-09-14T03:33:16Z`

Verdict: **ADAPT — the external obligations are now labelled honestly, but the
software admission boundary is not closed and N02 is not accepted for N30
consumption.**

This review did not execute or download a comparator, reveal a private holdout,
spend provider resources, or establish a championship or superiority claim.

## Independence and exact scope

I did not author the repair. I created a fresh worktree directly from the requested
exact commit and read both earlier Curator artifacts before testing:

```powershell
git worktree add -b codex/whole-os-n02-curator-r3 C:\h\wos-n02-rereview-r3 783423ef6be2420310059a7e2e2cb08f47508cb8
Get-Content C:\h\wos-n02-review\docs\benchmarks\whole-os-protocol-curator-review.md -Raw
Get-Content C:\h\wos-n02-rereview\docs\benchmarks\whole-os-protocol-curator-rereview.md -Raw
git show -s --format='%H%n%P%n%T%n%s' HEAD
git diff-tree --no-commit-id --name-status -r HEAD
git diff --stat b91bcd6b3195ad70901f7e3169538381b05f49b6..HEAD
```

The reviewed commit is a child of `f80ba5da6b6dcac790b65ee33adf903e76308c3c`
and changes exactly `campaign_metrics.py`, its focused test, the protocol JSON, and
the protocol Markdown. Independence is session/worktree separation, not host
separation: the builder and Curator used the same machine and Git object database.
No externally custodied task manifest, private holdout, evaluator signature,
comparator archive, or issued N30 lease was available to inspect.

The accepted N00 inventory `WOS-N00-20260914-01` still reproduces exactly:

| Artifact | SHA-256 |
|---|---|
| `source-inventory.json` | `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127` |
| `successor-node-map.json` | `aeb3d9dd35c28bf431a187b8aa60e51c9ea6531fb265b40f59056b12b0b6cc4b` |
| `symbol-classification.json` | `89f70a0b50cf84b7a2e7fa1be4e07ac58ebcc8638f8405a9658b9e3e724857b0` |
| `SOURCE_RECONCILIATION.md` | `feb58b630627d0bd56d9a4d538b530b9f9b5e4d3f9a5853805d07d6a888f3f52` |
| `verify_n00.ps1` | `7227e840296d2f61309a36b52f45eb65fdbdf0de24ad2ab7034b3e7692022a68` |
| `n00-validation.json` | `0470947dae960e5df39cf4d98cb0af3d10a5f3b8b36354c02c72f9505d5f187c` |

## Test and import evidence

I bound Python imports to the exact review worktree:

```powershell
$env:PYTHONPATH=(Resolve-Path -LiteralPath .\src).Path
python -c "import hive_mind_os; print(hive_mind_os.__file__)"
python -m unittest tests.test_campaign_metrics -v
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
git diff --check b91bcd6b3195ad70901f7e3169538381b05f49b6..HEAD
```

The import resolved to
`C:\h\wos-n02-rereview-r3\src\hive_mind_os\__init__.py`. The focused suite passed
6 tests with 0 failures in 0.128 seconds. The complete inherited command passed 58
tests with 0 failures in 21.836 seconds. The diff check passed. I began the repository
wide gate but cancelled that extra run at the Orchestrator's direction because the
focused, inherited, and adversarial evidence is sufficient for this bounded review;
the interrupted run is not claimed as a passing receipt.

Reviewed hashes:

| File | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `bbf0b53266ef71f8c926217a8af364d86a29ccdad0534bf8a52ab5a36eac3e1a` |
| `tests/test_campaign_metrics.py` | `e4b88fb365c8f9c7ccb132a303498d9a3abf62a2e4e4d7e260cf9c85fb4036b8` |
| `docs/benchmarks/whole-os-match-protocol.json` | `73b3e22cf30e4510686978f85424e5dc6fcaf99b743d2e912fa30ad801e2c8a5` |
| `docs/benchmarks/whole-os-protocol.md` | `b386fcebd5635be8d32c4b4eafe89d619bcfc3b5a2fc7cf79ebfe43eee554984` |

## Closed findings reproduced

The checked-in artifact now truthfully says external evidence is blocked, and the
normal `load_match_protocol` rejects it. The experiment manifest is retained in the
constructed protocol and affects `protocol_digest`. Negative time, usage, and cost;
unknown total usage with detailed usage; partial intervals; zero-family known
intervals; non-finite inputs; and caller mutation of the principal mappings now
reject or remain isolated. The default bootstrap requires 12 families and remains
seed-deterministic at 10,000 resamples/95% confidence. Margin override still rejects;
the tested cost/time winner rules remain symmetric.

Original scheduling now uses only `development-screening`, hybrid scheduling uses
only `harder-hybrid-development`, and the original whole-campaign stage excludes
MH variants. Arbitrary cross-track pairs and unknown outcomes reject through
`BracketState.apply`. One-survivor, round-24, and lease stops reproduce; odd-only
byes remain neutral; a third loss eliminates; and quarantine excludes the affected
entrant. These are material improvements over round 2.

## Remaining software blockers

### S1 — inspection parsing confers execution and sealing capability

`load_match_protocol_for_inspection` returns the same ordinary `MatchProtocol` type
used by scheduling and sealing. It synthesizes all eight apparent recipe digests for
MB0–MB3, MC0–MC1, and MH1–MH4 from the public `recipe_seed`. A protocol obtained
from the checked-in OPEN artifact immediately produced builder-component scheduled
pairs. The same inspection object accepted an original seal, a hybrid seal, and two
final seals over those synthetic recipes. There is no admitted/readiness state that
`BracketState.schedule` or `validate_seals` can require.

Therefore the checked-in OPEN artifact is rejected by one loader entry point but is
not non-schedulable. Inspection must return a distinct non-executable document type,
or carry a non-forgeable admission state checked by every scheduling, sealing, and
execution-facing operation. Inspection must never manufacture evidence digests.

### S2 — the normal loader's admission predicate is only a status-string check

An adversarial temporary copy removed `recipe_seed`, inserted arbitrary well-formed
recipe digests, and changed only `custody_status` to `ATTESTED` and
`holdout_signature_status` to `SIGNED`. `load_match_protocol` admitted it while
`task_manifest_status` and `family_split_status` remained
`OPEN_EXTERNAL_N30_BLOCKER`, `holdout_manifest_digest` remained null, and
`evaluator_signature` remained null.

Admission must validate concrete recipe provenance/availability, task and family
manifest closure, disjoint block digests, the actual holdout-manifest digest,
authenticated evaluator signature and independence, issued lease, exact frozen
seeds/repetitions/rules, and canonical-document integrity. User-controlled status
strings are not an attestation.

### S3 — inconclusive matchup keys are corrupted, so the stop rule never activates

`BracketState.__post_init__` calls `_freeze`, whose mapping branch converts every key
to `str`. The required `frozenset({left,right})` inconclusive keys therefore become
strings. `schedule_round` looks them up as `frozenset` values and always sees zero.
Even a state initialized with every possible MB pairing at count two rescheduled
`MB0`–`MB1` and `MB2`–`MB3`, with no `no_schedulable_pairs` terminal. Applied
inconclusives accumulate stringified keys rather than reusable matchup identities.

Preserve typed canonical matchup keys, validate counts and entrants, and add an
executable two-inconclusive/no-pair terminal control.

### S4 — issued schedule identity and replay protection remain incomplete

`apply` reduces an issued pair to an unordered entrant set. It ignores direction,
bye flag, dataset block, round, task, seed, and evidence-receipt identity. Exact
probes accepted (a) an issued original-stage pair relabelled with
`promotion_holdout`, (b) the same pair with left/right reversed, which changed which
entrant received the loss, and (c) the same issued pair twice in one call, producing
two losses. There is no append-only execution/receipt ledger or replay guard.

Bind the full issued schedule record and one-execution receipt key; reject altered
orientation/block/task/seed and duplicate or replayed applications. This is also
needed to prove that bookkeeping never triggers or double-counts model work.

### S5 — seals still do not prove stage custody or evaluator independence

The inspection protocol accepted an arbitrary original-stage block digest and an
evaluator named `builder`. Final validation still recognizes the digest of the
public string `promotion_holdout`, not an externally custodied manifest digest.
`sealed_at` is only a whitespace-free string. The code has no authenticated
signature, proposer/builder identity separation, stage-specific manifest binding,
or append-only time/order receipt. These failures are distinct from the legitimate
absence of the external signature: software must reject such unbound objects even
after evidence becomes available.

### S6 — remaining statistical and safety controls are caller-bypassable

`paired_family_bootstrap(..., minimum_families=1)` accepted one family, and twelve
families with one observation each accepted despite the final 30-family/3-repetition
rule. Stage does not determine the frozen threshold or repetition count.
`PairedInterval(None, None, None, 1)` accepted an unknown interval with a positive
family count. When both candidates fail hard gates, `decide_match` returns only
`QUARANTINE_LEFT`, losing the right-side safety violation. Currency/unit/billing
basis and the concrete thirteen-stratum membership remain unvalidated.

Derive thresholds and repetition requirements from an admitted stage, enforce
paired family/task membership, make unknown interval counts coherent, and preserve
all safety-quarantine outcomes rather than collapsing one.

## Replayed counterexample excerpt

The adversarial probes used the exact worktree import and produced:

```text
normal_open_load CampaignMetricsError
inspection_schedule (MB0-MB1 development-screening, MB2-MB3 development-screening)
inspection_final_seals ACCEPTED
forged_minimal_admission ACCEPTED task/family OPEN, holdout digest/signature null
duplicate_complete_behavior CampaignMetricsError
active_nan/active_inf/active_negative CampaignMetricsError
negative_cost/negative_usage CampaignMetricsError
unknown_total_measured_detail CampaignMetricsError
unknown_interval_positive_family ACCEPTED
one_family_default CampaignMetricsError
one_family_override ACCEPTED
one_rep_screening ACCEPTED
margin_override TypeError
time_first_left LEFT
cost_first_right RIGHT
both_gate_fail QUARANTINE_LEFT
promotion_holdout_exposed False
whole_original_entrants ['MC0', 'MC1']
one_survivor terminal one_survivor
round24 terminal max_rounds
lease terminal lease_exhausted
stored_inconclusive_key_types ['str']
two_inconclusive_schedule MB0-MB1, MB2-MB3; terminal None
cross_track_apply CampaignMetricsError
unknown_outcome CampaignMetricsError
forged_block_apply ACCEPTED
reversed_pair_apply ACCEPTED
duplicate_pair_apply ACCEPTED (two losses)
```

These are software-contract observations, not comparator results.

## External obligations, judged separately

The following were unavailable and remain explicit external N30 obligations, not
facts this review can fabricate:

- pinned source/archive bytes and license/right-to-execute receipts for EX01,
  EX03, EX06, EX07, datasets, and each comparator lane;
- concrete immutable eight-dimension MB/MC/MH recipe manifests and actual candidate
  bytes, with unavailable/duplicate/immaterial variants kept DEFERRED;
- externally custodied, disjoint development, harder-hybrid, and promotion-holdout
  task/family manifests covering the declared strata, with public digests;
- authenticated independent evaluator identity, signature, custody attestation,
  and unchanged pre-open final-pair binding;
- actual runtime/provider availability, credentials or external authority where
  required, and a bounded N30 resource lease.

Those absences need not prevent acceptance of an inert software contract if it is
impossible for OPEN/inspection data to become ready. At this commit they remain
acceptance-relevant because S1 and S2 let inspection or minimally relabelled data
cross that boundary.

## Disposition

Round 3 truthfully separates software from external custody and closes several prior
defects, so ADAPT remains appropriate rather than REJECT. However, S1–S6 prevent
acceptance of the software contract itself. Preserve this review and the passing
focused/inherited receipts, repair on a successor builder commit, and obtain another
independent exact-commit review. Until then N02 must not be frozen or consumed by
N30, and no comparator, championship, or superiority result exists.
