# Whole-OS N30 terminal non-promotion court — 2026-09-14

## Scope and exact candidate

This receipt closes the N30 admission attempt for commit
`8f667b6a0bbfed4e674036d0c41127b8751cf218` and tree
`6e71b4bc5cd60a084b38bc86029426be33e9a730` on
`codex/whole-os-executable-pipeline`. It is a terminal non-promotion result for
this attempt, not a completed measured tournament, an N30 acceptance, or evidence
of superiority, noninferiority, safety, cost, latency, or functional benefit.

The prior receipt in `whole-os-results-20260914-428af93.md` is retained but is
bound to another candidate. It cannot qualify this candidate.

## Frozen protocol and source status

The inspected `whole-os-match-protocol.json` has byte SHA-256
`sha256:efd458d77cd0b05afe1a4308c87f69de2e1d04b2e9f1ed3ca9f003477fcebf0d`
and canonical document digest
`sha256:7a50f32cb2f4750fb93619728fa178725a84a9569fd6a0d450bb72550b60069b`.
Its status is `OPEN_EXTERNAL_EVIDENCE_BLOCKED`.

The retained N00 records provide source metadata, not execution-ready archives or
rights:

| Source | Retained version | Retained body SHA-256 | License/reuse status |
| --- | --- | --- | --- |
| EX01 mini-swe-agent | `04d809ceab9df28f9adaed044884180159172930` | `9982d90b7566f2f3fa5e9811b475d5e8e2a84e2df80cf3f1e4be6e820b129835` | MIT metadata; raw source/license archive and admitted reuse recipe absent |
| EX03 Software Agent SDK | `15a9b8609c12635abacefa1f91beacedd7798296` | `95094c9745c7cc58136d4eaa1688fb6038aafefec2be05344293f6df7e55dbf8` | MIT metadata; raw source/license archive and admitted reuse recipe absent |
| EX06 SWE-bench | `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` | `06841624d7b5130dfe3cc6714642e9a8fd2a608c95c66ae0180e409f12b73aaa` | Harness MIT metadata; dataset/repository rights, archive, and admitted task recipe absent |
| EX07 SWE-smith | `9b74ac08118a85c39c356802f7961893af73e07f` | `058ccfb4465b3d067ac53eae9db43d55dfdaf180fcae438880901e3b192584b7` | MIT metadata; target/dataset rights and raw archive absent; N02 input only |

The older comparator intake contains limited license files for a different
comparison and expressly does not admit an N30 lane. The pinned Hive Cortex local
lanes are also a different benchmark and are not relabelled here.

## Admission, custody, lease, lanes, and execution

The live admission probe, with `PYTHONPATH` bound to this worktree's `src`, exited
23:

```text
CampaignMetricsError: OPEN or relabelled protocol is not closed
```

All MB0–MB3, MC0–MC1, and MH1–MH4 recipes remain `DEFERRED`. There are no admitted
scenario task IDs. The recipe manifest digest, all original/hybrid/final task,
family and block manifest digests, all stage signature references, evaluator
custody receipt, closure receipt, candidate seals, and authenticated N30 lease are
absent. Consequently:

- admitted lanes: 0;
- real broker operations: 0;
- scored attempts/failures: 0/0;
- task/family/repetition identities: none admitted;
- model/configuration per lane: none admitted;
- measured usage/provider cost/elapsed lane time: unavailable, not zero;
- bracket survivors/losers: none admitted and no comparative championship exists.

The trusted host-bootstrap receipt proves a local-only Codex composition at this
candidate using native Codex CLI v0.154.0, but grants no benchmark evaluator,
custodian, comparator rights, holdout, or N30 resource lease. The current stage
wrapper resolved `codex-cli 0.146.0`; because no lane was admitted, neither runtime
was invoked as a comparator.

Execution intent was durably recorded before the admission probe at
`local-custody:n30-tournament/court-8f667b6/intent.json`, with the rule that the
broker could run only after a closed host admission. One evidence-collection
failure is retained in the launcher event log: an initial PowerShell parse of
`HEAD^{tree}` produced a malformed local intent value. It was corrected to the
exact tree above before the admission probe or any broker effect. No uncertain
external outcome existed, so no retry was issued.

## Verification and independent review

The current worktree resolved `hive_mind_os` from its own `src` directory under
Python 3.14.4. This command passed 38/38 tests:

```powershell
$env:PYTHONPATH=(Resolve-Path .\src).Path
python -B -m unittest tests.test_whole_os_benchmark tests.test_benchmark_adapters tests.test_campaign_metrics tests.test_whole_os_adversarial -v
```

These are synthetic conformance tests. Their `RecordingBroker`, fixture registry,
fixture recipes, and fixture receipts are not comparator evidence.

The separate read-only Curator `/root/n30_curator` reproduced the admission facts
and recommended `DEFER`. Acting separately as the N30 admission Judge, after doing
no building or benchmark effects, that identity issued `DEFER — terminal
non-promotion for this attempt`. The review shares this host and is unauthenticated,
so it is not the independently administered evaluator/custodian receipt required
for a promotion claim. Retained N02 Curator round 8 accepts only the software
contract and expressly leaves the same external obligations open.

## Typed blockers and court disposition

The six closed-protocol blockers are:

```text
EO-EXT-SOURCE-ARCHIVES
EO-COMPARATOR-RIGHTS
EO-CONCRETE-RECIPE-MANIFEST
EO-DISJOINT-TASK-FAMILY-MANIFESTS
EO-INDEPENDENT-EVALUATOR-CUSTODY
EO-AUTHENTICATED-N30-LEASE
```

**DEFER — terminal non-promotion for this N30 attempt.** No recipe was admitted,
so executing a lane or inventing its argument vector would violate N02. The current
champion remains unchanged, with its externally bound identity unavailable here.
Rollback is therefore the no-op required by the contract: retain the prior champion
and preserve this failed admission evidence. A successor attempt must first supply
the six authenticated obligations and then generate the exact broker argument
vectors from the sealed adapter manifest.
