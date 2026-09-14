# N02 independent evaluation Curator rereview — round 5

Reviewed builder commit: `92bf72453d80e5f98d496070bccd4f8d7d2214d4`

Reviewed tree: `b26d91c2de6ed44520d6d3bc299beaa52ff5f92b`

Review worktree: `C:\h\wos-n02-rereview-r5`

Review branch: `codex/whole-os-n02-curator-r5`

Curator identity: `/root/n00_curator`, acting as the separate N02 evaluation Curator

Reviewed at: `2026-09-14T04:00:52Z`

Verdict: **ADAPT — round 5 adds useful host/admission, lease, receipt, final-pair,
and aggregation structure, but a fixture or caller-supplied verifier still creates
real readiness and several execution paths are internally inconsistent. N02 is not
accepted for N30 consumption.**

The user-supplied abbreviated object name
`92bf72453d80e5f98d496070bccd4f8d7d2214d` resolves to the full reviewed object
above. This review did not execute or download a comparator, reveal a private
holdout, use provider credentials, spend an external lease, or establish a
championship or superiority claim.

## Independence and scope

I did not author the repair. I created a fresh exact-commit worktree, read the round-4
review in full, inspected the entire descendant repair chain, and replayed the
round-4 B1–B7 and earlier S1–S6/R1–R7 counterexamples:

```powershell
git worktree add -b codex/whole-os-n02-curator-r5 C:\h\wos-n02-rereview-r5 92bf72453d80e5f98d496070bccd4f8d7d2214d
Get-Content C:\h\wos-n02-rereview-r4\docs\benchmarks\whole-os-protocol-curator-r4.md -Raw
git show -s --format='%H%n%P%n%T%n%s' HEAD
git log --oneline 276bd5010524f46bf9134ee7d237a2c75909e7ee..HEAD
git diff --stat 276bd5010524f46bf9134ee7d237a2c75909e7ee..HEAD
```

The reviewed commit has parent `f26ea379c8459c3ee7487927c55274aa17e6d936`
and is the tip of a nine-commit repair chain after round 4. The final commit changes
only `whole-os-protocol.md` and `test_campaign_metrics.py`; the implementation was
last changed by its parent.

Independence is worktree/session separation, not host separation. The builder and
Curator used the same machine and Git object store. No authenticated external
verifier, private manifests, comparator archive, issued external lease, or holdout
custodian was available. The accepted N00 inventory `WOS-N00-20260914-01` and all
six accepted hashes reproduce unchanged.

## Tests, provenance and reviewed bytes

I bound imports to this worktree and ran the focused and inherited commands:

```powershell
$env:PYTHONPATH=(Resolve-Path -LiteralPath .\src).Path
python -c "import hive_mind_os; print(hive_mind_os.__file__)"
python -m unittest tests.test_campaign_metrics -v
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
git diff --check 276bd5010524f46bf9134ee7d237a2c75909e7ee..HEAD
```

The import resolved to
`C:\h\wos-n02-rereview-r5\src\hive_mind_os\__init__.py`. The focused suite passed
8 tests with 0 failures in 0.107 seconds. The inherited command passed 58 tests with
0 failures in 18.744 seconds. The diff check passed. Integration retains ownership
of the repository-wide gate for this campaign.

| File | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `9deb9e030b72913fe2ae49e9288f11a295b0ec0dfcc9b5fe8dfa107fde86895c` |
| `tests/test_campaign_metrics.py` | `7b2aabbd517c1659148450f7125b05753eff793ce904104413cc421e26579778` |
| `docs/benchmarks/whole-os-match-protocol.json` | `73b3e22cf30e4510686978f85424e5dc6fcaf99b743d2e912fa30ad801e2c8a5` |
| `docs/benchmarks/whole-os-protocol.md` | `80bd06a5f366269dc4fe8371612dcdb6c1234a32fff698ff6f05b16f21b2b1b3` |

The checked-in protocol JSON remains unchanged and explicitly OPEN/external-evidence
blocked. The Markdown now describes the new execution boundary.

## Prior findings closed or materially improved

- The checked-in OPEN JSON rejects normal loading. Inspection returns only
  `MatchProtocolInspection`; it has no recipes or scheduling API and rejects at
  admission and bracket use. Inspection isolation remains closed.
- No/default and explicitly rejecting verifier inputs fail. No signing key or
  production verifier is stored in the protocol JSON or module. A plain public
  `AdmittedProtocol(...)` constructor call without the module token rejects.
- Missing, inactive, wrong-scope, and wrong-digest leases reject at admission.
  Stage evidence requires exact 13-stratum coverage, 12x1 development or 30x3 final
  declaration, and a distinct two-label final pair.
- Pair block/orientation and cross-track mutation plus duplicate pairs in one apply
  reject. Wrong receipt seed, evaluator, block, and unknown task reject in the
  exercised first-pair path. A returned state's retained receipt digest rejects the
  old receipt on a later round.
- A correctly shaped MC0/MH1 final pair now schedules on the actual admitted holdout
  digest. Same-label and no-hybrid final-pair controls reject.
- `stage_paired_bootstrap` accepts 12x1 development and 30x3 final data and rejects
  12x3 development or 30x1 final data. Numeric, interval, recipe immutability,
  duplicate behavior, noninferiority, symmetric efficiency, and unknown-retention
  repairs from earlier rounds remain intact.
- `decide_match` continues to preserve simultaneous gate failures as
  `QUARANTINE_BOTH`; typed inconclusive keys remain intact; one-survivor, third-loss,
  round and explicit lease stops remain present.
- Core protocol digests still bind manifest/recipe content and foreign protocol
  admission objects reject.

These advances are real, but they do not close the end-to-end controls below.

## Remaining software blockers

### C1 — caller and fixture verifiers still mint the real execution capability

`admit_protocol` accepts any caller-supplied object with a truthy `verify` method.
An always-true verifier admitted an envelope whose literal signature was `"bad"`.
The test `_FixtureVerifier`, which checks only a caller-selected HMAC key and ignores
the supplied canonical payload, produced the exact `AdmittedProtocol` consumed by
real `BracketState.schedule`, `apply`, `validate_seals`, and stage aggregation.
There is no fixture-only maturity/type on that result and no execution check that
rejects fixture verification.

The `_ADMISSION_TOKEN` constructor guard is also not a trust root. Any importer can
access `campaign_metrics._ADMISSION_TOKEN` and construct a capability directly; an
exact probe did so successfully. Python naming privacy cannot establish host-issued
authority.

Thus the documented phrase “host-injected” is a convention, not an enforced
boundary. Require a host-owned authenticated verifier/registry capability whose
provenance the execution layer validates, and return a distinct non-production
fixture receipt that production-shaped scheduling, sealing, and aggregation reject.

### C2 — identity, payload and admission digests remain incomplete

`builder_ids` is still supplied by the caller. An evaluator named `builder` admitted
when the caller omitted it and rejected only when voluntarily listed. An envelope
with role `custodian` admitted as the evaluator. Arbitrary signed payload digests
admitted; `admit_protocol` never requires `envelope.payload_digest` to equal the
canonical payload it passes to the verifier.

The verifier payload now contains several stage fields, which is progress, but it
omits `strata`, `final_pair`, evaluator identity/role/time, lease scope/expiry/issuer,
and manifest signature reference. The persisted `admission_digest` still binds only
protocol digest, block digest, and envelope payload digest. Changing task manifest,
family manifest, lease, or seed produced one identical admission digest. Three
different final pairs—including cross-track MB0/MH1—also produced one identical
admission digest.

Bind the complete stage document, final pair/regime, authenticated principals,
signed canonical payload, and complete lease record in the verifier decision and
admission identity; revalidate that authenticated identity at use.

### C3 — locally relabelled status and recipe claims can still cross admission

A temporary copy of the checked-in OPEN JSON was locally changed by removing
`recipe_seed`, inserting syntactically valid available recipes/provenance hashes,
relabeling the OPEN fields CLOSED/ATTESTED/SIGNED, and supplying an arbitrary holdout
digest while leaving `evaluator_signature` null. It loaded, an always-true verifier
admitted it with an already-expired locally issued lease, and the bracket scheduled
two MB matches.

Well-shaped hashes and status strings remain unauthenticated claims. Recipe archive,
manifest, signature, evaluator, and lease receipts must resolve through the trusted
host boundary rather than become true because local fields and an injected callback
say so.

### C4 — leases have no time, issuer, revocation, or continued-use enforcement

`LeaseRecord(expires_at=0, issued_by="builder")` admitted and then scheduled. The
code validates only active flag, digest equality, and scope string at admission; it
does not compare expiry to a trusted clock, authenticate the issuer, retain the
lease record in the admission capability, or recheck expiry/revocation on schedule,
apply, seal, or aggregation. The separate caller boolean `lease_active` remains the
only later-use signal.

Bind an authenticated issued lease with budget/scope/expiry to the admission, use a
trusted time/revocation source, and fail closed at every use without caller-supplied
truth flags.

### C5 — one receipt can cover zero, one, or many matches and replay identity is mutable

`apply` validates its single receipt against only the first scheduled pair, then
accepts any subset of the scheduled pairs. Exact probes showed:

- both scheduled pairs applied under one first-pair receipt;
- the second pair alone applied under the first pair's receipt;
- an empty pair list consumed the receipt and advanced the round;
- another in-protocol task ID and an arbitrary new receipt digest were accepted;
- the same prior state accepted the same receipt in two separate calls;
- `reject_receipt_replay` accepted an otherwise identical receipt after only its
  caller-provided `receipt_digest` changed.

`receipt_digest` is not recomputed or authenticated. Development scheduled pairs
carry a public block label while the receipt carries the independent admitted block
digest, and those are not compared. Task/seed/evaluator are not assigned by the
scheduler per pair. No durable ledger prevents replay after restoring an earlier
state or restart.

Require one canonical, authenticated issued receipt per applied pair/bye, bind it to
the exact scheduled block/task/seed/evaluator/orientation/round, require exact set
equality between scheduled work and submitted results, and retain applied identities
in append-only durable evidence rather than caller-reconstructible state.

### C6 — bracket terminal, bye and quarantine transitions are not composable

When every possible pair has two inconclusive meetings, `schedule` returns four
`right=None, bye=False` placeholders with `terminal=None`; `apply` cannot accept
them, so `no_schedulable_pairs` and its partial INCONCLUSIVE result are still absent.
Negative loss counts still construct.

In any odd field the neutral bye is emitted first, but `apply` requires the first
issued row to have a right entrant and `IssuedReceipt` cannot represent a bye. A
three-entrant round therefore cannot be applied. Conversely, an empty pair list can
advance a normal round as described above. `decide_match` emits
`QUARANTINE_BOTH`, but `apply` does not recognize that outcome and raises
`unknown outcome`, so the repaired safety verdict cannot transition bracket state.

Implement explicit terminal/partial states, valid counter invariants, bye receipts,
exact scheduled-result completeness, and a two-entrant quarantine transition.

### C7 — final seal/custody validation is unsatisfiable and final eligibility is weak

Final scheduling works for MC0/MH1, but final sealing cannot validate a legitimate
history. Under final admission every submitted seal must have `stage="final"`, so
including the required prior original/hybrid seals rejects with stage mismatch. If
only the two final seals are submitted, validation cannot find the prior seals and
rejects as unqualified.

Additionally, the final custody check still requires
`canonical_digest("promotion_holdout")`, not the admitted external holdout-manifest
digest. A real distinct digest rejects. A label-hash manifest gets past that check
but still fails for missing prior seals. There is no authenticated append-only seal
registry across stage admissions. `sealed_at="not-a-time"` remains valid.

`StageEvidence.final_pair` enforces only distinct labels. MB0/MH1 admits as an
original/hybrid pair; whole-campaign scheduling then filters away MB0 and silently
reports one survivor instead of rejecting the cross-track pair. Operating regime is
not bound at final admission or scheduling. Bind the selected pair to qualified
stage seals, same whole-campaign track and regime, actual holdout digest, evaluator
signature, chronological RFC3339 order, and unchanged candidate/recipe bytes.

### C8 — calculation binding is optional and output loses its admission identity

`stage_paired_bootstrap` correctly enforces declared counts, but the exported
`paired_family_bootstrap` still accepts 12x1 and 30x1, and `decide_match` accepts the
resulting plain `PairedInterval`. Nothing marks an interval as stage-admitted or
prevents bypassing the new gateway. Even the stage gateway checks only mapping size
and repetition lengths; it cannot prove family/task membership against the manifest
digest, paired completeness, strata coverage, or receipt provenance. Its tautological
`set(pairs) != set(pairs)` check adds no validation.

Return an admission-bound aggregate receipt, make decision/sealing require it, and
resolve exact family/task membership and repetitions from authenticated manifests.
The raw statistical helper may remain available for inert calculation, but its
output must not be qualification-capable.

## Replayed counterexample excerpt

Read-only probes used the exact worktree import and produced:

```text
checked_open_load CampaignMetricsError
inspection MatchProtocolInspection; inspection admission/schedule CampaignMetricsError
no_verifier / rejecting_verifier CampaignMetricsError
public AdmittedProtocol constructor CampaignMetricsError
module_token_constructor ACCEPTED
always_true_bad_signature ACCEPTED
fixture_verifier_real_schedule two MB pairs
builder_omitted ACCEPTED; builder_listed CampaignMetricsError
custodian_as_evaluator ACCEPTED
missing/inactive/wrong-scope/wrong-digest lease CampaignMetricsError
expired_zero_lease ACCEPTED; arbitrary_lease_issuer ACCEPTED
payload/task/family/block/seed mutations ACCEPTED
admission_digest_count after task/family/lease/seed mutations 1
final_pair_admission_digest_count across MC0/MH1, MC1/MH2, MB0/MH1 1
status_flip_to_schedule ACCEPTED
pair orientation/seed/evaluator/block/unknown-task mutations CampaignMetricsError
apply_all_pairs_one_receipt ACCEPTED
apply_second_pair_with_first_receipt ACCEPTED
empty_pairs_advances ACCEPTED
receipt_task_other_valid / receipt_digest_mutation ACCEPTED
repeat_same_prior_state ACCEPTED
exact receipt replay helper CampaignMetricsError; changed-digest pair ACCEPTED
no_schedulable_output four unmatched rows; terminal None
odd_round_apply CampaignMetricsError
both_quarantine_decision QUARANTINE_BOTH; bracket apply CampaignMetricsError
negative_loss ACCEPTED
final MC0/MH1 schedule uses actual holdout digest
cross_track MB0/MH1 final schedule ACCEPTED as one survivor
final seals with history CampaignMetricsError stage/block mismatch
final seals only CampaignMetricsError invalid custody or unqualified
arbitrary seal time ACCEPTED
stage 12x1 and final 30x3 aggregation ACCEPTED
stage 12x3 and final 30x1 aggregation CampaignMetricsError
raw 12x1 and raw 30x1 aggregation ACCEPTED
```

These are software-contract observations, not comparator results.

## External N30 obligations, judged separately

The following evidence was unavailable and is neither invented nor treated as a
software test fixture:

- pinned source/archive bytes and license/right-to-execute receipts for EX01,
  EX03, EX06, EX07, datasets, and each comparator lane;
- concrete immutable eight-dimension MB/MC/MH recipes and actual candidate bytes,
  keeping unavailable, duplicate, or immaterial variants DEFERRED;
- externally custodied disjoint development, harder-hybrid, and promotion-holdout
  task/family manifests covering the declared strata, with published digests;
- authenticated independent evaluator/custodian identities and signatures binding
  the unchanged qualified final pair before holdout reveal;
- actual runtime/provider availability and authority, plus an authenticated,
  bounded, active, non-renewing N30 resource lease.

These absences need not prevent acceptance of an inert software contract once its
execution layer can distinguish trusted external verification from local fixtures.
At this commit they remain acceptance-relevant only because C1–C4 allow local
callbacks, tokens, status claims, and expired leases to imitate external closure.

## Disposition

Round 5 is a material improvement and remains repairable, so ADAPT is appropriate
rather than REJECT. C1–C8 block software acceptance. Preserve this review and the
8/8 focused plus 58/58 inherited receipts, repair on a successor commit, and obtain
another independent exact-commit Curator review. N02 is not frozen or N30-ready,
and no comparator, championship, or superiority result exists.
