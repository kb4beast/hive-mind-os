# N02 independent evaluation Curator rereview — round 4

Reviewed builder commit: `276bd5010524f46bf9134ee7d237a2c75909e7ee`

Reviewed tree: `c6704790396109e455b759b743e852cdbfbe8355`

Review worktree: `C:\h\wos-n02-rereview-r4`

Review branch: `codex/whole-os-n02-curator-r4`

Curator identity: `/root/n00_curator`, acting as the separate N02 evaluation Curator

Reviewed at: `2026-09-14T03:44:45Z`

Verdict: **ADAPT — inspection isolation is closed, but the fixture admission path
can confer real scheduling/sealing readiness and the evidence bindings remain
incomplete. N02 is not accepted for N30 consumption.**

No comparator was downloaded or executed. I did not reveal a private holdout,
exercise provider credentials, spend a resource lease, or establish a championship
or superiority claim.

## Independence and inspected lineage

I did not author the round-4 repair. I created a fresh worktree from the exact
requested commit and read all three prior append-only reviews from their independent
worktrees before testing:

```powershell
git worktree add -b codex/whole-os-n02-curator-r4 C:\h\wos-n02-rereview-r4 276bd5010524f46bf9134ee7d237a2c75909e7ee
Get-Content C:\h\wos-n02-review\docs\benchmarks\whole-os-protocol-curator-review.md -Raw
Get-Content C:\h\wos-n02-rereview\docs\benchmarks\whole-os-protocol-curator-rereview.md -Raw
Get-Content C:\h\wos-n02-rereview-r3\docs\benchmarks\whole-os-protocol-curator-r3.md -Raw
git show -s --format='%H%n%P%n%T%n%s' HEAD
git log --oneline 783423ef6be2420310059a7e2e2cb08f47508cb8..HEAD
git diff --stat 783423ef6be2420310059a7e2e2cb08f47508cb8..HEAD
```

The exact commit has parent `d587f9b1edcca8518f968dd2eaf2168ce3d28af2`
and is the tip of the six-commit repair chain `da12699`, `5cafd20`, `581034d`,
`06b3042`, `d587f9b`, `276bd50` descending from the round-3 target. Across that
chain only `src/hive_mind_os/campaign_metrics.py` and
`tests/test_campaign_metrics.py` changed. The final commit itself changes only the
focused test.

Independence is process/worktree separation, not host separation: the builder and
Curator used the same machine and Git object database. No authenticated external
verifier, custodian, private task manifest, holdout, comparator archive, or N30
lease was supplied.

The accepted N00 inventory `WOS-N00-20260914-01` remains byte-identical to its
accepted six-hash seal.

## Test and byte evidence

Imports were bound to this exact worktree:

```powershell
$env:PYTHONPATH=(Resolve-Path -LiteralPath .\src).Path
python -c "import hive_mind_os; print(hive_mind_os.__file__)"
python -m unittest tests.test_campaign_metrics -v
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
git diff --check 783423ef6be2420310059a7e2e2cb08f47508cb8..HEAD
```

The import resolved to
`C:\h\wos-n02-rereview-r4\src\hive_mind_os\__init__.py`. The focused suite passed
8 tests with 0 failures in 0.121 seconds. The inherited benchmark/evaluation command
passed 58 tests with 0 failures in 21.090 seconds. The diff check passed. Per the
Orchestrator's established N02 review scope, integration—not this bounded rereview—
will run the repository-wide gate.

Reviewed hashes:

| File | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `69003f9629c07ae8ffe879330622c51ab8b23f5b59a592df80451e14b6dc5acd` |
| `tests/test_campaign_metrics.py` | `0a9a473b430aeddfef0a7c2c44e3431ea07145e7cc0340b995b2f9f0ea7691a2` |
| `docs/benchmarks/whole-os-match-protocol.json` | `73b3e22cf30e4510686978f85424e5dc6fcaf99b743d2e912fa30ad801e2c8a5` |
| `docs/benchmarks/whole-os-protocol.md` | `b386fcebd5635be8d32c4b4eafe89d619bcfc3b5a2fc7cf79ebfe43eee554984` |

The protocol JSON and Markdown are unchanged from round 3.

## Prior findings now closed

- The checked-in OPEN JSON still rejects through `load_match_protocol`.
  `load_match_protocol_for_inspection` now returns an opaque
  `MatchProtocolInspection`, exposes neither recipes nor scheduling, and rejects at
  both `admit_protocol` and `BracketState.schedule`. Round-3 S1 is closed for the
  inspection API itself.
- Recursive freezing preserves `frozenset` matchup keys. Recipe and manifest maps
  are read-only, and duplicate complete behavior recipes reject.
- In one `apply` call, altered pair orientation/block, cross-track pairs, unknown
  outcomes, and duplicate `ScheduledPair` values reject. Original and hybrid stages
  remain isolated to their respective development block labels.
- Negative/non-finite measurements, unknown-total/detailed usage conflicts, partial
  intervals, known zero-family intervals, and unknown positive-family intervals
  reject. The default bootstrap rejects fewer than 12 families, remains seeded,
  and uses 10,000 resamples/95% intervals. The noninferiority margin cannot be
  overridden; the tested left/right efficiency decisions remain symmetric.
- `StageEvidence` requires the exact 13 declared strata, rejects duplicates or
  omissions, requires 12x1 for original/hybrid and 30x3 for final, and validates
  digest shapes. `decide_match` now preserves simultaneous hard-gate failures as
  `QUARANTINE_BOTH`.
- One-survivor, third-loss, quarantine, round-24, lease-false and odd-only-bye
  behavior previously reproduced remain intact. Exact duplicate `IssuedReceipt`
  identities reject.
- Core `MatchProtocol.protocol_digest` changes when frozen manifest fields such as
  selection seed or retry rule change, and a receipt for a different protocol
  object rejects.

These are substantial repairs. They do not close the execution-facing trust and
custody problems below.

## Remaining software blockers

### B1 — the “fixture-only” admission is a production-shaped public capability

`admit_protocol` accepts a caller-supplied `fixture_hmac_key` and returns the same
public `AdmittedProtocol` required by scheduling, application, and sealing. The
module docstring says fixture HMAC is not a production key store, but no type,
field, verifier interface, or execution check marks the result fixture-only. An
adversarial caller constructed a production-shaped `MatchProtocol`, signed an
arbitrary payload with its own key, received an `AdmittedProtocol`, and scheduled
MB matches.

More directly, `AdmittedProtocol` is a public dataclass with no construction guard.
A caller constructed one around an envelope containing the literal signature
`"bad"`, recomputed the simple public admission digest, and scheduled matches
without calling `admit_protocol`. `_require_admission` checks object identity and
that recomputable digest, but never re-verifies authenticity.

The fully admitted fixture therefore is not confined to tests and can confer real
readiness. A production execution path must require an authenticated external
verifier/custody receipt that callers cannot self-issue; fixture authority must have
a distinct type or maturity that every execution-facing method rejects outside an
explicit test-only harness. `AdmittedProtocol` must not be forgeable by public
constructor plus public hash formula.

### B2 — evaluator independence and signatures are caller-declared

The caller supplies both the HMAC key and `builder_ids`. A seal signed by an actor
named `builder` admitted when the caller passed an empty builder list and rejected
only when the caller voluntarily listed `builder`. A `SignedCustodyEnvelope` with
role `custodian` also admitted as the evaluator. The signed payload is an arbitrary
digest: changing it and signing with the caller key still admitted, with no binding
to the protocol, stage, task/family manifests, lease, recipes, or candidate seals.
The manifest may omit `evaluator_signature` entirely; its textual `SIGNED` status is
not tied to the envelope.

Require authenticated principal/role resolution from a trusted registry or injected
verifier, bind proposer/builder/affected champion identities independently of caller
arguments, require the evaluator role, and verify a canonical payload containing
the complete protocol and stage-evidence document.

### B3 — the admission digest omits most stage evidence

`admission_digest` binds only protocol digest, stage block digest, and evaluator
payload digest. Independent probes changed each of task-manifest digest,
family-manifest digest, lease digest, and stage seed while retaining the same
admission digest; all variants admitted. The observed set contained exactly one
digest for five materially different evidence packets. For non-final stages even
the block digest is arbitrary because it is not checked against a manifest.

Bind stage, task/family/block manifests, exact task membership, strata mapping,
families, repetitions, seed, retry policy, lease terms/status/expiry, evaluator
identity/role/signature/time, and protocol digest in one canonical signed payload
and admission identity. Recompute it at every use.

### B4 — status flips plus self-created evidence still turn OPEN bytes executable

The checked-in file itself remains closed, which is a positive control. However, a
temporary copy with `recipe_seed` removed, arbitrary syntactically valid
available/provenance recipes inserted, four OPEN strings relabelled CLOSED/ATTESTED/
SIGNED, and an arbitrary holdout digest passed `load_match_protocol`. A caller-made
HMAC envelope then passed `admit_protocol` and scheduled matches even though no
external archive, manifest content, evaluator signature, or lease existed. The
null `evaluator_signature` was accepted.

Status strings and well-shaped hashes are claims, not proof. Admission must resolve
the referenced immutable bytes/receipts through the trusted external boundary and
must not accept a locally rewritten OPEN document as evidence closure.

### B5 — receipts are not integrated with bracket application or replay custody

`IssuedReceipt` and `reject_receipt_replay` are standalone. `BracketState.schedule`
does not issue task, seed, evaluator, or receipt identities, and `apply` accepts no
receipts. Changing receipt digest, task, seed, or evaluator makes a second receipt
different, so the replay helper accepts both; `receipt_digest` is not recomputed
from the fields or checked against an issued schedule. Applying the same issued pair
twice to the same prior immutable state also succeeds twice in separate calls.

The repaired exact in-call pair validation is useful, but it does not prove the
one-variant/task/seed execution rule. Bind each scheduled pair to a canonical issued
receipt and retained applied-receipt ledger; reject altered task/seed/evaluator/
block/orientation/digest and replay across calls or restarts.

### B6 — stage, terminal, lease and final-seal custody remain inconsistent

- When every possible pairing already has two inconclusive meetings, scheduling
  returns four `right=None, bye=False` placeholder rows and leaves `terminal=None`.
  Applying them advances the round and still leaves no `no_schedulable_pairs`
  terminal or partial-bracket verdict.
- Negative loss counts still construct. `lease_active=1` is accepted as true, and
  `lease_digest` has no issued/active/expiry/budget binding to `resource_lease_ref`.
- A final `StageEvidence` correctly requires its block digest to equal the manifest
  holdout digest, but `validate_seals(final=True)` instead requires
  `canonical_digest("promotion_holdout")`. A realistic distinct holdout-manifest
  digest is rejected; the public label hash passes.
- Final seals listed before their original/hybrid qualification seals pass because
  input order is not enforced. Seal evaluator defaults are not bound to the admitted
  evaluator: seals naming `builder` passed under an admission by `eval`. A non-final
  seal with arbitrary block digest, evaluator, and non-time `sealed_at` also passed.
- `BracketState` has no final entrants or final schedule path; a fully admitted final
  state returns an empty schedule without a terminal reason.

Implement explicit `no_schedulable_pairs`/partial state, validate state counters and
lease type/receipt, bind every stage to its actual manifest digest and evaluator,
validate append-only seal order/timestamps and unchanged pair, and make the final
stage executable only after those conditions are satisfied.

### B7 — 12x1/30x3 controls are recorded but not bound to calculations

`StageEvidence` validates the declared threshold, but `paired_family_bootstrap` has
no stage/admission input. It accepted 12 families with one observation, 30x1, and
30x2. Thus a final caller can compute a qualification-looking 30-family interval
without the required three repetitions, and a 12-family interval can flow to
`decide_match` without any final-stage rejection. There is no binding between the
13 strata labels, the protocol's 12 generic scenario IDs, the task/family manifest
digests, and actual paired observations. Currency, usage unit, provider billing
basis, and concrete stratum membership also remain incompletely validated.

Make aggregation stage/admission aware, require exact family/task membership and
the predeclared repetition count before an interval can be used, and bind its output
to the protocol/stage evidence identity.

## Adversarial replay excerpt

Two read-only Python probes, run with the exact `PYTHONPATH` above, replayed the
prior S1–S6/R1–R7 matrix and new admission mutations. Selected results:

```text
checked_open_normal_load CampaignMetricsError
inspection_type MatchProtocolInspection; no recipes/schedule
inspection_admit CampaignMetricsError
inspection_bracket_schedule CampaignMetricsError
caller_minted_admission ACCEPTED; caller_minted_schedule two MB pairs
direct_forged_admission_schedule ACCEPTED with signature "bad"
builder_omitted_from_builder_ids ACCEPTED
builder_named_in_builder_ids CampaignMetricsError
custodian_as_evaluator ACCEPTED
wrong_signature_key CampaignMetricsError
arbitrary_payload_signed ACCEPTED
task/family/lease/original-block/selection-seed mutations ACCEPTED
admission_digest_count for original plus task/family/lease/seed mutations 1
relabelled_open_to_execution ACCEPTED and scheduled two MB pairs
protocol_digest_selection_seed_changes True
protocol_digest_retry_changes True
duplicate_complete_behavior CampaignMetricsError
negative/nonfinite/unknown-detail/partial-interval controls CampaignMetricsError
bootstrap_1_family CampaignMetricsError
bootstrap_12x1 ACCEPTED
bootstrap_30x1_final_like ACCEPTED
bootstrap_30x2_final_like ACCEPTED
missing/duplicate stratum CampaignMetricsError
original_30x3 and final_12x1 StageEvidence CampaignMetricsError
both_quarantines QUARANTINE_BOTH
forged_block/reversed_orientation/cross_track CampaignMetricsError
duplicate_application_same_call CampaignMetricsError
repeat_apply_same_prior_state ACCEPTED twice
exact_receipt_replay CampaignMetricsError
receipt digest/task/seed/evaluator mutation pairs ACCEPTED
inconclusive_key_types ['frozenset']
all_pairs_twice_schedule four unmatched rows; terminal None
negative_losses ACCEPTED
one_survivor/max_rounds/lease_exhausted terminals reproduced
lease_truthy_int ACCEPTED
actual_holdout_digest_final_seals CampaignMetricsError
label_hash_final_seals ACCEPTED
final_first_seal_order ACCEPTED
seal_evaluator_not_bound ACCEPTED
wrong_original_block_evaluator_time ACCEPTED
final_bracket_schedule (); terminal None
```

These are contract counterexamples, not comparator outcomes.

## External N30 obligations, judged separately

The software findings above do not manufacture or resolve the legitimately
unavailable external evidence. N30 still requires:

- archived, pinned source bytes and license/right-to-execute receipts for EX01,
  EX03, EX06, EX07, datasets, and each comparator lane;
- concrete immutable eight-dimension MB/MC/MH recipes and actual candidate bytes,
  with unavailable, duplicate, or immaterial variants explicitly DEFERRED;
- externally custodied, disjoint development, harder-hybrid, and promotion-holdout
  task/family manifests covering the declared strata, with published digests;
- an authenticated independent evaluator signature and custody attestation binding
  the unchanged selected pair before holdout reveal;
- actual comparator/runtime/provider availability and authority, plus an issued,
  bounded, non-renewing N30 resource lease.

Those missing artifacts need not block acceptance of an inert software contract if
the implementation fails closed until a trusted external verifier supplies them.
They remain relevant here only because B1–B4 allow local fixtures, constructors, and
status strings to impersonate that external closure.

## Disposition

Round 4 closes meaningful defects and retains honest OPEN metadata, so the design is
repairable and ADAPT is more appropriate than REJECT. B1–B7 still block software
acceptance. Preserve this review and the 8/8 focused plus 58/58 inherited passing
receipts, repair on a successor commit, and obtain another independent exact-commit
Curator review. Until then N02 is not frozen or N30-ready, and no comparator,
championship, or superiority result exists.
