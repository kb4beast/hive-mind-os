# N02 independent security rereview — round 7

Verdict: **ADAPT — the r6 C1–C6 repairs are materially closed, but qualification still accepts a registry-resolved aggregate whose family cardinality cannot satisfy the admitted 12x1 or 30x3 experiment. Do not accept N02 until R7-D1 is repaired and independently rereviewed.**

This is an append-only Curator review of exact builder commit
`5c710cf602e9afc3b25e8261490cb28dab3fc513` and tree
`b383dfcc50224493d7460c4ed3ca76796b2680ae`. The immediate parent is
`a86717340936eb99934055c8494a7f6f95a3b521`. Review work ran in the fresh
worktree `C:\h\wos-n02-rereview-r7` on branch
`codex/whole-os-n02-curator-r7`.

## Independence and scope

The Curator identity and branch are separate from the N02 builder. I read the N02
contract and required `MatchProtocol`, the accepted N00 seal, the r5 and r6 review
artifacts, the changed code/tests, protocol Markdown/JSON and ADR. I changed no
builder implementation, test, protocol, ADR or JSON. This review used the same
machine and Git object store as the builder and the repository's test-only registry,
so it is independent code review and fixture reproduction, not independent external
custody or a production-registry attestation.

No network, credential, private holdout, comparator, provider runtime, external
lease or external signing operation was used. I did not execute a comparator and
make no benchmark, promotion, readiness or superiority claim.

The accepted N00 input remained inventory `WOS-N00-20260914-01`. I recomputed all
six sealed inputs and obtained the accepted SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `source-inventory.json` | `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127` |
| `successor-node-map.json` | `aeb3d9dd35c28bf431a187b8aa60e51c9ea6531fb265b40f59056b12b0b6cc4b` |
| `symbol-classification.json` | `89f70a0b50cf84b7a2e7fa1be4e07ac58ebcc8638f8405a9658b9e3e724857b0` |
| `SOURCE_RECONCILIATION.md` | `feb58b630627d0bd56d9a4d538b530b9f9b5e4d3f9a5853805d07d6a888f3f52` |
| `verify_n00.ps1` | `7227e840296d2f61309a36b52f45eb65fdbdf0de24ad2ab7034b3e7692022a68` |
| `n00-validation.json` | `0470947dae960e5df39cf4d98cb0af3d10a5f3b8b36354c02c72f9505d5f187c` |

## Provenance and executable evidence

`git show -s --format="commit=%H%nparent=%P%ntree=%T%nsubject=%s" HEAD`
returned:

```text
commit=5c710cf602e9afc3b25e8261490cb28dab3fc513
parent=a86717340936eb99934055c8494a7f6f95a3b521
tree=b383dfcc50224493d7460c4ed3ca76796b2680ae
subject=Harden N02 bracket and qualification state
```

`git diff --check a86717340936eb99934055c8494a7f6f95a3b521..5c710cf602e9afc3b25e8261490cb28dab3fc513`
passed. The candidate was clean before this append-only review. The candidate changed
only the ADR, protocol JSON/Markdown, `campaign_metrics.py` and its focused tests.

Exact import provenance and focused test command:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -c "import hive_mind_os, hive_mind_os.campaign_metrics as m; print(hive_mind_os.__file__); print(m.__file__)"
python -m unittest tests.test_campaign_metrics -v
```

The imports resolved to this worktree's `src` directory and the suite passed
**21/21** in 0.798 seconds.

Inherited compatibility command:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
```

It passed **58/58** in 18.990 seconds. `python -m json.tool
docs/benchmarks/whole-os-match-protocol.json` passed.

Candidate artifact SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `c37e4d6db5ed93238396b3fecbe2055e4cc2d94e7af89f9c328d686bed38c890` |
| `tests/test_campaign_metrics.py` | `c53f44470157b6bd6d77c466139e17d869dc8433a56e775054739ca3a29be893` |
| `docs/benchmarks/whole-os-match-protocol.json` | `30c3d42277a5944ddbfdeeec0d00cfdba3d2e8815b6ff62e25f6d257a4f20b48` |
| `docs/benchmarks/whole-os-protocol.md` | `7eb0e7d9b7549071b3ef8a66882fad80d5f66a3447b0bdb9168e0e93c7de0a6f` |
| `docs/architecture/ADR-WOS-N02-HOST-ADMISSION-REGISTRY.md` | `531fa9f96baae5897b706cc3dddb525f41c6454ed218fccbf03eea5390dfc7da` |

## R6 correction replay

The focused suite and separate read-only fixture scripts reproduced these results:

```text
C1 arbitrary bracket handle                         REJECT CampaignMetricsError
C1 cross-registry bracket handle                    REJECT CampaignMetricsError
C1 superseded-handle schedule/apply rewind          REJECT CampaignMetricsError
second bracket CAS commit from the same state       REJECT CampaignMetricsError
receipt bracket/orientation/block/task/seed/evaluator mutations
                                                    REJECT CampaignMetricsError
bye receipt bracket-digest mutation                 REJECT CampaignMetricsError
zero/many/reused-handle receipt issuance            REJECT CampaignMetricsError
C2 final MC1/MH2, reversed MH1/MC0, cross-track MB0/MH1
                                                    REJECT CampaignMetricsError
C3 post-open backdated final seals                   REJECT CampaignMetricsError
C4 final repetition seeds (7,7,7)                   REJECT CampaignMetricsError
C5 empty builder/empty champion/colliding role sets REJECT CampaignMetricsError
C6 zero/negative/NaN/infinite cost and time ratios  REJECT CampaignMetricsError
```

The repair makes public `BracketState` carry only an opaque handle. The fixture
registry resolves a digest-bound `BracketSnapshot`, supersedes the prior handle on
CAS transition, binds every pair and bye receipt to that snapshot, enforces an exact
unique receipt set and rejects replay. Admission mutation of task/family/block,
seed, evaluator and lease state remains digest-bound. Lease issuer, scope, expiry,
revocation and operation checks execute on each effect surface.

Independent terminal probes produced `no_schedulable_pairs` for zero entrants and
for every pair at two inconclusive meetings, `one_survivor` for one remaining
entrant, `max_rounds` at round 24, exactly one bye in an odd field and durable bye
and dual-quarantine state after apply. The focused tests also retain third-loss,
lease-exhaustion and replay behavior.

Forged registry-resolved final aggregates with a wrong pair, reversed pair, wrong
stage, track, regime, holdout block digest, task manifest or family manifest all
rejected. Seal sequence, stage, block, evaluator, custodian and time controls, the
post-open seal check and the append-time CAS race all rejected in the focused suite.
Success remains bounded to `[-1,1]`; cost/time ratios are finite and strictly
positive; seeded 10,000-resample 95% interval parameters are frozen. Raw descriptive
intervals remain unable to enter `decide_match` directly.

These results close the exact r6 C1–C6 counterexamples and materially preserve the
earlier closed controls. They do not close the additional decision-boundary defect
below.

## R7-D1 — decision does not enforce admitted aggregate cardinality

`stage_paired_bootstrap` checks the supplied rows against the stage's admitted
task/family/repetition keys before asking the registry to record an aggregate.
However, `decide_match` accepts three registry-resolved `AggregateEvidence` records
without checking each interval's `family_count` against the admitted stage. The
record also carries no independently checkable observation count or repetition
shape. Consequently the defensive decision boundary checks pair, track, regime and
manifest mutations but not the contract's sample shape.

Using only the existing `_FixtureRegistry.fixture_aggregate` adversarial hook, I
installed three otherwise perfectly co-bound records with valid intervals and
`family_count=1`. Exact output was:

```text
original_declared_tasks 12 repetitions 1
original_forged_family_count_1_decision LEFT
final_declared_tasks 30 repetitions 3
final_forged_family_count_1_decision LEFT
```

The final fixture had the exact admitted ordered `MC0`/`MH1` pair, valid prior and
final seals, the final track/regime, actual admitted holdout block digest and matching
task/family manifests. Only aggregate cardinality was false. Returning `LEFT` allows
one family to qualify where N02 requires 12x1 screening or 30x3 final evidence.
This is a software contract failure, not an absent external-evidence result.

The trusted production registry is an external boundary, but the module already
defensively rejects malicious or buggy registry-returned pair, stage, track, regime,
manifest and metric-domain values. Omitting sample-shape validation from that same
boundary makes the documented “registry-bound exact 12x1/30x3” guarantee incomplete.

Required repair:

1. Bind an independently checkable aggregate shape to `AggregateEvidence`—at
   minimum distinct-family count, observation count and repetitions, or an exact
   admitted row-shape digest—not only an opaque observation digest.
2. In `decide_match`, require every resolved aggregate to match the admitted stage's
   exact family and repetition shape: original/hybrid 12x1 and final 30x3. A
   `family_count=1` aggregate must reject even when all other bindings are correct.
3. Add adversarial decision tests for wrong family count and wrong final observation
   or repetition count. Retain the existing correct 12x1 and 30x3 positive paths.
4. Update the protocol Markdown and ADR acceptance wording so it claims closure only
   after that boundary is executable.

## Checked-in protocol and external obligations

The JSON is honest and synchronized about unavailable evidence. It remains
`OPEN_EXTERNAL_EVIDENCE_BLOCKED`, has no `protocol_digest`, has zero scenario task
IDs, labels every MB/MC/MH recipe `DEFERRED`, supplies no recipe provenance digest
and retains exactly six blockers:

```text
EO-EXT-SOURCE-ARCHIVES
EO-COMPARATOR-RIGHTS
EO-CONCRETE-RECIPE-MANIFEST
EO-DISJOINT-TASK-FAMILY-MANIFESTS
EO-INDEPENDENT-EVALUATOR-CUSTODY
EO-AUTHENTICATED-N30-LEASE
```

Inspection-only loading returned those six blockers. Normal loading rejected with
`OPEN or relabelled protocol is not closed`; the focused relabel control also
rejected. The fixture-only complete document and fake registry are explicitly test
mechanisms and cannot confer production readiness.

These external N30 obligations remain separate from R7-D1: pinned archive bytes,
licenses and comparator execution rights; concrete immutable eight-dimension
recipes and N28 candidate bytes; disjoint externally custodied task/family/block
manifests and private holdout; authenticated evaluator/custodian/builders/champion
roles and signatures; production durable registry composition; provider/runtime
availability; and an authenticated bounded, non-renewing lease. None was available,
invented or treated as complete.

## Disposition

**ADAPT.** Exact commit `5c710cf602e9afc3b25e8261490cb28dab3fc513`
closes the six r6 findings and passes the requested 21 focused plus 58 inherited
tests. It does not yet enforce the admitted family/repetition sample shape at the
qualification decision boundary. Repair R7-D1 on a successor commit and obtain a
fresh independent exact-candidate rereview. Even after software acceptance, N30
execution and any comparative or promotion claim remain blocked on the six external
evidence and authority obligations above.
