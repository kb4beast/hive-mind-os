# N02 final defensive rereview — round 8

Verdict: **ACCEPT the N02 software contract at exact commit
`5301d71fb5bb6f81adcf0ba180a5d9d49f4c4e42`; R7-D1 is closed. External N30
evidence, authority, production-registry composition and any benchmark or promotion
claim remain blocked.**

This append-only Curator review covers builder commit
`5301d71fb5bb6f81adcf0ba180a5d9d49f4c4e42`, tree
`c2dfcc0a055b9860e1532a0e7870d500f3757619`, whose immediate parent is the r7
candidate `5c710cf602e9afc3b25e8261490cb28dab3fc513`. Review ran in the fresh worktree
`C:\h\wos-n02-rereview-r8` on branch `codex/whole-os-n02-curator-r8`.

## Scope and independence

The Curator identity, branch and worktree are separate from the builder. I read
`AGENTS.md`, the N02 contract and required `MatchProtocol`, the accepted N00 seal,
the r7 dissent, and every changed implementation, test, protocol, JSON and ADR
artifact. I did not alter candidate code, tests, protocol, JSON or ADR. The only
write is this review.

The review used the same host and Git object store as the builder and used only the
repository's deterministic unit fixtures. It did not access a network, credential,
private holdout, external source archive, comparator, provider runtime, external
lease, evaluator or signing service. Therefore this is independent software
contract verification, not external authority testimony or an N30 execution.

The six accepted N00 inputs for inventory `WOS-N00-20260914-01` were recomputed and
all matched the hashes sealed in `N00_CURATOR_REREVIEW.md`.

## Exact provenance and commands

```text
commit=5301d71fb5bb6f81adcf0ba180a5d9d49f4c4e42
parent=5c710cf602e9afc3b25e8261490cb28dab3fc513
tree=c2dfcc0a055b9860e1532a0e7870d500f3757619
subject=Bind N02 decisions to admitted observation shape
```

`git diff --check 5c710cf602e9afc3b25e8261490cb28dab3fc513..HEAD` passed,
and the worktree was clean before this review file was added. The successor changes
only these five candidate artifacts:

```text
docs/architecture/ADR-WOS-N02-HOST-ADMISSION-REGISTRY.md
docs/benchmarks/whole-os-match-protocol.json
docs/benchmarks/whole-os-protocol.md
src/hive_mind_os/campaign_metrics.py
tests/test_campaign_metrics.py
```

Exact import and focused suite:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -c "import hive_mind_os, hive_mind_os.campaign_metrics as m; print(hive_mind_os.__file__); print(m.__file__)"
python -m unittest tests.test_campaign_metrics -v
```

The imports resolved to
`C:\h\wos-n02-rereview-r8\src\hive_mind_os`. The focused suite passed
**21/21** in 1.188 seconds.

Inherited compatibility suite:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
```

It passed **58/58** in 19.701 seconds.

I also reran a proportionate seven-test security regression covering arbitrary and
cross-registry handles, bracket rewind/field forgery, exact receipt sets and replay,
lease revalidation on every effect, post-open final-seal rejection, OPEN/relabelled
JSON isolation, and odd-bye/no-schedulable terminal behavior. It passed **7/7** in
0.225 seconds.

`python -m json.tool docs/benchmarks/whole-os-match-protocol.json` passed.

Candidate artifact SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `036541377edf4cfe325857ac8a5801d7f663baf202721ddab44bdf9a4702b374` |
| `tests/test_campaign_metrics.py` | `e2b05d842087690cc8ba6006ee73018784a87acb19632156b58d4e82ef601de7` |
| `docs/benchmarks/whole-os-match-protocol.json` | `efd458d77cd0b05afe1a4308c87f69de2e1d04b2e9f1ed3ca9f003477fcebf0d` |
| `docs/benchmarks/whole-os-protocol.md` | `b35cb890db13afa30b870d7b6dd66f7fba8f326371f3c322e09c7b2ef381e493` |
| `docs/architecture/ADR-WOS-N02-HOST-ADMISSION-REGISTRY.md` | `75381a8471ff4808fd09ee33ec4109140c82e491be65d36a800ab6ede9280f76` |

## R7-D1 implementation inspection

The repair adds immutable, ordered `ObservationShapeEntry` records containing the
family ID, task ID, repetition index and declared seed. `AggregateEvidence` now:

- requires a nonempty shape made only of those records;
- rejects identical duplicates;
- requires one task identity per family;
- rejects repeated repetition indices or seeds within a family; and
- normalizes the shape by sorting it before canonical digesting.

`StageEvidence` already enforces 12 unique task/family bindings and one declared
seed for original/hybrid, or 30 unique task/family bindings and three distinct
declared seeds per task for final, with exact thirteen-stratum coverage.
`stage_paired_bootstrap` still requires the exact admitted family/task/repetition
rows and now records the complete normalized shape derived from that admitted stage.

At `decide_match`, the module re-resolves the admission, reconstructs the expected
shape from the current digest-bound `StageEvidence`, and requires every one of the
success, cost and time aggregates to equal it. It separately requires every
interval's `family_count` to equal the distinct-family count reconstructed from that
stage. These checks occur before gates, interval dominance or any verdict is
interpreted. Since `observation_shape` participates in `AggregateEvidence`'s
canonical document, mutation also changes the registry receipt digest.

## Independent shape counterexamples

I used the existing test-only registry's adversarial `fixture_aggregate` hook to
install otherwise correctly bound aggregates. This exercises the defensive decision
boundary without pretending the fixture is a production authority.

Positive controls:

```text
original_shape 12 entries, 12 families
original_12x1_positive: ACCEPT LEFT
final_shape 90 entries, 30 families, 90 distinct fixture seeds
final_30x3_positive: ACCEPT LEFT
```

Negative controls:

```text
original_family_count_1             REJECT CampaignMetricsError
original_missing_shape_entry        REJECT CampaignMetricsError
original_extra_shape_entry          REJECT CampaignMetricsError
original_changed_family             REJECT CampaignMetricsError
original_changed_task               REJECT CampaignMetricsError
original_changed_repetition         REJECT CampaignMetricsError
original_changed_seed               REJECT CampaignMetricsError
original_identical_duplicate        REJECT CampaignMetricsError

final_family_count_1                REJECT CampaignMetricsError
final_89_of_90                      REJECT CampaignMetricsError
final_extra_91                      REJECT CampaignMetricsError
final_changed_family                REJECT CampaignMetricsError
final_changed_task                  REJECT CampaignMetricsError
final_changed_repetition            REJECT CampaignMetricsError
final_changed_seed                  REJECT CampaignMetricsError
final_identical_duplicate           REJECT CampaignMetricsError
final_duplicate_repetition          REJECT CampaignMetricsError
final_duplicate_seed                REJECT CampaignMetricsError
declared final seeds (7,7,7)        REJECT CampaignMetricsError
```

The missing, extra and changed cases remained structurally valid
`AggregateEvidence` where possible and were rejected specifically by `decide_match`'s
equality with the newly resolved admitted shape. Identical entries, repeated
repetitions and repeated per-family seeds reject even earlier at record construction.
This closes the exact r7 exploit in which `family_count=1` returned `LEFT` for both
stages and establishes the required 89/90 final negative.

## Earlier controls and trust boundary

The focused and seven-test regression preserve the earlier accepted controls:
opaque registry-owned bracket state; stale/foreign handle and CAS rejection;
bracket-bound exact pair/bye receipts and durable replay rejection; deterministic
odd-only byes, two-inconclusive stop, third loss, dual quarantine, one survivor,
max-round and lease terminal behavior; complete admission and principal bindings;
issuer/scope/expiry/revocation checks at every effect; exact ordered final pair and
regime; chronological pre-open seals and append CAS; metric domains; hard gates;
seeded 10,000-resample 95% bootstrap; noninferiority and symmetric cost/time rules;
and raw-descriptive-output isolation.

The repository fixture registry checks only enough durable receipt state for unit
conformance. A production host must additionally demonstrate that each observation's
receipt digest resolves to the exact admitted family/task/repetition/seed and that
the three metrics derive from the authorized frozen executions. The interface
provides those fields to `record_aggregate`; this review does not supply or attest
the production implementation.

## Documentation, JSON and external obligations

The Markdown and ADR accurately describe the normalized shape, decision-time
reconstruction, 12x1/30x3 counts, one-family/missing/repeated/changed-seed negatives,
fixture-only status, rollback to the immediate parent and absence of an N30 or
superiority claim. The JSON parses and synchronizes its `decision_rule` to
`registry-bound-exact-observation-shape-stage-pair-positive-ratio-bootstrap-hard-gates`.

The checked-in protocol remains `OPEN_EXTERNAL_EVIDENCE_BLOCKED`, has zero scenario
tasks, labels every MB/MC/MH recipe `DEFERRED`, supplies no recipe provenance and
retains exactly six external obligations:

```text
EO-EXT-SOURCE-ARCHIVES
EO-COMPARATOR-RIGHTS
EO-CONCRETE-RECIPE-MANIFEST
EO-DISJOINT-TASK-FAMILY-MANIFESTS
EO-INDEPENDENT-EVALUATOR-CUSTODY
EO-AUTHENTICATED-N30-LEASE
```

Inspection-only loading returns these six blockers. Normal loading rejects OPEN
JSON; changing only its status to `CLOSED_ADMISSION_CANDIDATE` also rejects because
the obligations remain. No checked-in document, fixture handle or local relabel can
confer execution readiness.

N30 must still provide pinned external source/comparator bytes and rights; concrete
immutable recipe and candidate manifests; disjoint externally custodied task,
family, block and private holdout manifests; authenticated independent principals,
signatures and custody; a durable production registry and transaction behavior;
provider/runtime availability; and an authenticated bounded, non-renewing lease.
Those obligations are separate from the accepted software contract and were not
fabricated or discharged here.

## Disposition

**ACCEPT** N02 software contract commit
`5301d71fb5bb6f81adcf0ba180a5d9d49f4c4e42` at tree
`c2dfcc0a055b9860e1532a0e7870d500f3757619`. R7-D1 is closed, no software
blocker remains from the reviewed counterexamples, and the focused plus inherited
suites pass from exact worktree provenance. This acceptance does not authorize N30
execution, reveal a holdout, satisfy external custody, spend a lease, promote a
candidate or support a comparator/superiority claim.
