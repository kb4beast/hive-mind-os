# N02 independent security Curator rereview — round 6

Reviewed builder commit: `a86717340936eb99934055c8494a7f6f95a3b521`

Reviewed tree: `d650b5647a8f9fa8886ce5b14cdf7be2eb1f21b6`

Review worktree: `C:\h\wos-n02-rereview-r6`

Review branch: `codex/whole-os-n02-curator-r6`

Curator identity: `/root/n00_curator`, acting as the separate N02 evaluation Curator

Reviewed at: `2026-09-14T04:47:40Z`

Verdict: **ADAPT — the host-registry redesign honestly separates fixture software
from unavailable external authority and closes many r5 defects, but bracket state,
final aggregation, final seal timing, principal completeness, repetition seeds and
ratio domains remain bypassable. N02 is not accepted for N30 consumption.**

No comparator was executed or downloaded. This review did not reveal a private
holdout, use credentials, spend a lease, establish real registry authority, or make
a championship or superiority claim.

## Independence, point-in-time identity and scope

I did not author the candidate. I created the requested fresh exact-commit worktree,
read the N02 contract, the round-5 review, the new ADR, the entire implementation and
focused tests, the protocol Markdown and the JSON artifact. The reviewed commit has
parent `92bf72453d80e5f98d496070bccd4f8d7d2214d4`; its declared tree reproduced
exactly. The one-commit diff contains only:

- `docs/architecture/ADR-WOS-N02-HOST-ADMISSION-REGISTRY.md`;
- `docs/benchmarks/whole-os-match-protocol.json`;
- `docs/benchmarks/whole-os-protocol.md`;
- `src/hive_mind_os/campaign_metrics.py`; and
- `tests/test_campaign_metrics.py`.

`git diff --check 92bf72453d80e5f98d496070bccd4f8d7d2214d4..HEAD`
exited 0. Independence is worktree/session separation, not machine or object-store
separation. The accepted N00 input remains inventory `WOS-N00-20260914-01`; its
sealed source-inventory hash
`39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127`
reproduced.

## Import provenance, tests and reviewed bytes

I bound Python imports to this worktree and ran:

```powershell
$env:PYTHONPATH=(Resolve-Path -LiteralPath .\src).Path
python -c "import hive_mind_os, hive_mind_os.campaign_metrics as m; print(hive_mind_os.__file__); print(m.__file__)"
python -m unittest tests.test_campaign_metrics -v
python -m unittest tests.test_benchmark_harness tests.test_generic_dag_token_benchmark tests.test_hive_cortex_evaluation tests.test_evaluation_admission -v
python -m json.tool docs/benchmarks/whole-os-match-protocol.json
```

Imports resolved to
`C:\h\wos-n02-rereview-r6\src\hive_mind_os\__init__.py` and
`C:\h\wos-n02-rereview-r6\src\hive_mind_os\campaign_metrics.py`. The focused
suite passed **19/19** in 0.737 seconds. The inherited command passed **58/58** in
20.807 seconds. The protocol JSON parsed successfully. Integration retains
ownership of the repository-wide CI gate.

| Reviewed file | SHA-256 |
|---|---|
| `src/hive_mind_os/campaign_metrics.py` | `752f6ba0bb4a3d1fb27fb27a9f63e44589c0df644a1b7b841309243db85c2135` |
| `tests/test_campaign_metrics.py` | `d8b6c9f68e983b52b014eb4e1c0da819276f9a8584272f3b1b954b6d00246a3b` |
| `docs/benchmarks/whole-os-match-protocol.json` | `9988239a0735343116cd8fe43d0b55d9681e117e3dbf80345fa80c05c2705f7e` |
| `docs/benchmarks/whole-os-protocol.md` | `24e0ba911d8a52289a59171acc7aafa1048d0af1d259da395b9571e499d06607` |
| `docs/architecture/ADR-WOS-N02-HOST-ADMISSION-REGISTRY.md` | `b07af7839c9a7034f9472fe4aab4c24961a65967f4a56043c69b47a9aff59e19` |

## R5 controls that now close or materially improve

- Production `campaign_metrics` has no `admit_protocol`, `AdmittedProtocol`,
  `EvidenceVerifier`, `SignedCustodyEnvelope`, `_ADMISSION_TOKEN`, secret key,
  default registry or concrete registry. Public data constructors and predictable
  hashes do not execute without a registry-resolved opaque handle.
- The only N02 fixture registry is `_FixtureRegistry` in
  `tests/test_campaign_metrics.py`. Cross-instance and arbitrary handles reject in
  that registry. A deliberately always-accepting Curator registry can execute, as
  any implementation of the trust-boundary interface can; this is not represented
  as real authority. Production composition and a durable authenticated registry
  remain explicit external N30 obligations.
- The checked-in JSON is loadable only for inspection, remains
  `OPEN_EXTERNAL_EVIDENCE_BLOCKED`, has all ten MB/MC/MH labels DEFERRED with null
  provenance, zero scenario tasks, and retains six external obligations. A
  status-only CLOSED relabel rejects. A fully shaped fixture document may pass pure
  parsing but cannot execute without a registry handle.
- The admission identity canonically binds protocol digest, complete
  `StageEvidence` and complete `LeaseRecord`. A mutation matrix changed the identity
  for 20 stage/task/strata/principal/seed fields and all nine lease fields. Duplicate
  task IDs, duplicate family IDs, missing thirteen-stratum coverage and a wrong
  repetition count reject.
- `_resolve` rechecks protocol, stage, manifests, task membership, admission identity,
  trusted lease issuer, issue/expiry/revocation time and permitted operation. The
  focused suite observed schedule, apply, seal, aggregate and decide revalidation;
  expired execution becomes an explicit bracket stop and other effects fail closed.
- Registry issuance of zero receipts, an extra receipt, or one reused opaque handle
  for several plans rejected with `registry did not issue one exact unique receipt
  per pair/bye`. Empty, partial, duplicate and mutated result sets reject. Plan
  equality binds orientation, round/index, track/regime, block ID/digest,
  task/family/repetition/seed, evaluator/custodian and issue time. The test registry's
  durable consumed-handle ledger rejects replay from the same prior state.
- Odd-only byes are represented by exact BYE receipts and apply; zero/one-survivor,
  two-inconclusive/no-schedulable, max-round, lease stop, third loss and
  `QUARANTINE_BOTH` transitions execute in the focused tests.
- Final scheduling requires one whole-campaign original and one hybrid with distinct
  variants, immutable recipe/candidate bindings, the same regime, prior qualification
  seals, two pre-open final seals and the actual admitted holdout digest.
- `stage_paired_bootstrap` enforces exact admitted family/task/repetition keys and
  unique receipt-digest rows. Raw `DescriptiveInterval` output from 12x1 or 30x1
  calculation is inert and cannot enter `decide_match`. Seeded 10,000-resample 95%
  bootstrap, strict -0.05 noninferiority, hard gates, symmetric time/cost rules and
  dual quarantine remain present.

These improvements are real. The following counterexamples are independent software
contract defects, not missing external evidence.

## Remaining software blockers

### R6-C1 — public bracket state is not registry-authenticated

`BracketState` binds only the admission digest. Its round, losses, byes,
inconclusive meetings, quarantines and terminal are caller-supplied and never sent to
`registry.resolve`. With one valid fixture admission handle, exact probes constructed
new public states and observed:

```text
losses={"MB0":3}                 -> scheduled MB1/MB2; MB0 silently absent
quarantined=all original entrants -> no_schedulable_pairs
round_number=24                   -> max_rounds
terminal="one_survivor"           -> one_survivor
```

All four were accepted. Resolving a valid admission handle does not authenticate the
scientific bracket history. A holder can therefore skip rounds, eliminate or
quarantine entrants, fabricate an inconclusive history, choose byes indirectly, or
force a terminal without consuming receipts.

Move bracket state/version under the durable registry, or bind a registry-issued
state handle/digest and have scheduling/consumption atomically validate the exact
round, losses, byes, inconclusive counts, quarantines and terminal. Add rewind,
field-mutation and skipped-round controls.

### R6-C2 — qualification aggregation is not bound to the admitted stage pair

`stage_paired_bootstrap` checks that both labels name some recipe, but it does not
require stage eligibility, a common track/regime, or equality with the final
`StageEvidence.final_pair`. Under a valid final admission whose sealed pair was
MC0/MH1, 30x3 registry-backed observations were accepted for both:

```text
MC1 versus MH2  -> decide_match returned LEFT
MB0 versus MH1  -> decide_match returned LEFT
```

The second case crosses builder-component and whole-campaign tracks. Thus correct
final scheduling does not protect final qualification. Require the aggregate pair to
equal the exact final bindings during final, and require both labels to be active in
the current stage with identical track/regime in all stages. The registry should
also attest that its aggregate receipt was issued for that exact admitted pair.

### R6-C3 — final seals can be backdated after holdout opening

A final admission had `stage_opened_at=10`, `holdout_opened_at=20` and trusted
registry `observed_at=21`. The Curator submitted two seals carrying `sealed_at=11`
and `12`; `validate_and_append_seals` accepted and appended both. Field chronology is
checked, but the trusted current observation is not required to precede holdout open
when `operation="seal"`.

Reject final seal operations when trusted `observed_at >= holdout_opened_at`, and
require the registry's append operation to enforce this atomically so a caller cannot
create an apparently pre-open seal after seeing holdout data.

### R6-C4 — three final repetitions need not use three distinct seeds

Replacing one final task's declared seeds with `(7, 7, 7)` produced valid
`StageEvidence` and a new evidence digest. Length is enforced but uniqueness is not.
This permits one stochastic execution to masquerade as three seeded repetitions.
Require exactly three distinct seeds per final task (and distinct declared
repetition identities wherever stochastic repetition is claimed).

### R6-C5 — principal omission still bypasses collision detection

This public record constructed successfully:

```python
AuthorityBinding("builder:a", "custodian:x", (), (), "sig:e", "sig:c")
```

An evaluator who is actually a builder is rejected only if the authenticated stage
record lists that builder; empty `builder_ids` and `affected_champion_ids` are
allowed. This retains the r5 omission path in a new shape. Require nonempty complete
builder and affected-champion sets for N02 stages and require the host registry to
attest the complete role roster rather than accepting a caller-selected subset.

The separate probe in which a registry explicitly trusted `builder:a` as the lease
issuer also scheduled. That part is necessarily a host-registry authentication
decision, but it reinforces that fixture assertions cannot stand in for the missing
production role/issuer registry.

### R6-C6 — impossible negative efficiency ratios can qualify

Registry-backed final aggregates with cost ratio `-2.0` and time ratio `-3.0` were
accepted; with a noninferior success interval, `decide_match` returned LEFT. The raw
bootstrap correctly permits negative paired differences, but cost/time ratios have
a different domain. Enforce metric-specific ranges before aggregate issuance:
cost/time ratios must be finite and nonnegative (prefer strictly positive where a
zero denominator is invalid), and paired success differences must remain within
their valid probability range.

## Other replay observations

Read-only adversarial scripts also reproduced these exact results:

```text
arbitrary handle against instance-bound fixture registry -> CampaignMetricsError
cross-instance handle                                -> CampaignMetricsError
always-accepting Curator registry + arbitrary handle -> two fixture receipts
public minter/token/verifier symbol count             -> zero
zero/many/reused-handle registry issuance             -> CampaignMetricsError
wrong receipt orientation/block/task/seed/evaluator   -> CampaignMetricsError
empty/partial result set                              -> CampaignMetricsError
same-prior-state receipt replay                       -> CampaignMetricsError
checked-in OPEN normal load and status-only relabel   -> CampaignMetricsError
duplicate task/family, missing stratum, wrong count   -> CampaignMetricsError
```

The always-accepting registry result is not treated as an external-authentication
failure inside this interface-only module: it confirms that the registry is the
trust boundary. It also means no code in this commit can establish that a registry
is the production host. N30 must provide and independently verify that composition.

## External N30 evidence and authority obligations

These remain unavailable and are judged separately from R6-C1 through R6-C6:

- pinned archive bytes, licenses and execution rights for EX01, EX03, EX06, EX07,
  datasets and every comparator lane;
- concrete immutable eight-dimension MB/MC/MH recipes and actual N28 candidate
  bytes, with unavailable, duplicate or immaterial variants kept DEFERRED;
- externally custodied, disjoint original, harder-hybrid and promotion-holdout
  task/family/block manifests with the declared thirteen strata;
- authenticated independent evaluator, custodian, builders, affected champion,
  qualification seals and unchanged final-pair signature;
- an actual durable transactional host registry with instance-bound handles,
  monotonic trusted time, append-only seal and receipt ledgers, atomic lease
  revalidation, restart-safe replay rejection and host-controlled composition;
- actual provider/runtime availability and a bounded, active, non-renewing N30
  resource lease from an authenticated issuer.

The new ADR, Markdown and JSON state these limitations honestly. The checked-in OPEN
artifact cannot schedule anything by itself, and the test fake is not represented as
external evidence. Those absences do not excuse the six internal validation gaps,
and fixing those gaps will not satisfy the external obligations.

## Disposition

Round 6 is a substantial architectural improvement and remains repairable, so ADAPT
is appropriate rather than REJECT. Preserve the passing 19/19 focused and 58/58
inherited receipts and this dissent. Repair R6-C1 through R6-C6 on a successor
commit, add direct negative tests for each, and obtain another independent
exact-commit Curator review. N02 is not frozen or N30-ready, and no comparator,
championship or superiority result exists.
