# Whole-OS N30 admission outcome — 2026-09-14

## Scope and candidate binding

This is an admission outcome, not a completed measured tournament. The inspected
candidate was `428af931342820d8f7350bf0f7664115b6257302` (tree
`8a3c9f7e08fb182de3eb61451157df6a264de0ef`), the exact `origin/main` baseline
at measurement start. No files in that checkout were changed by the measurement.

The N02 record at `docs/benchmarks/whole-os-match-protocol.json` had document
digest `sha256:7a50f32cb2f4750fb93619728fa178725a84a9569fd6a0d450bb72550b60069b`
and status `OPEN_EXTERNAL_EVIDENCE_BLOCKED`.

## Admission and lanes

The exact environment binding was:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location).Path 'src')
python -B -c "import hive_mind_os; print(hive_mind_os.__file__)"
```

It resolved `hive_mind_os` from this candidate's `src` directory. The N02
admission probe was:

```powershell
python -B -c "from hive_mind_os.campaign_metrics import load_match_protocol, load_match_protocol_for_inspection, CampaignMetricsError; from pathlib import Path; path=Path('docs/benchmarks/whole-os-match-protocol.json'); print(load_match_protocol_for_inspection(path));`ntry:`n load_match_protocol(path)`nexcept CampaignMetricsError as exc:`n print(type(exc).__name__ + ': ' + str(exc)); raise SystemExit(23)"
```

PowerShell expands the backtick-newline escapes before passing the Python source.
It exited 23 with the typed outcome:

```
CampaignMetricsError: OPEN or relabelled protocol is not closed
```

Inspection retained the following blockers: `EO-AUTHENTICATED-N30-LEASE`,
`EO-COMPARATOR-RIGHTS`, `EO-CONCRETE-RECIPE-MANIFEST`,
`EO-DISJOINT-TASK-FAMILY-MANIFESTS`, `EO-EXT-SOURCE-ARCHIVES`, and
`EO-INDEPENDENT-EVALUATOR-CUSTODY`. All MB0–MB3, MC0–MC1, and MH1–MH4 recipe
entries remained `DEFERRED`; task IDs and the required recipe/task/family/block
manifest digests were absent. Therefore there were zero admitted real or local
matched lanes, zero scored attempts, and no bracket result.

The package contains no N30 tournament invocation surface. Its `whole-os` CLI
only exposes configured service `inspect`, `status`, `run-once`, and `resume`
operations; none can materialize the missing sealed adapter manifest or host-owned
admission registry.

## Local contract checks

With the same `PYTHONPATH` binding:

```powershell
python -B -m unittest tests.test_whole_os_benchmark -v
python -B -m unittest tests.test_campaign_metrics -v
```

Both passed: 2/2 N30 harness checks and 21/21 frozen-protocol/registry checks,
for 23 passing focused tests. These are local software-contract checks only; they
do not substitute for a benchmark lane, independent evaluator, or external
comparator.

## Raw custody

Raw stdout/stderr, exit statuses, binding output, and a checksum manifest are held
under local custody reference `local-custody:n30-admission-20260914-428af93`.
The custody location is intentionally not published because it is host-local.
The manifest records SHA-256 values for:

| Receipt | SHA-256 |
| --- | --- |
| `pythonpath-binding.txt` | `38509BB71F42CD5AFE95118CC6987B75CB5DA0480360674EB542265BE7F56A73` |
| `protocol-admission.txt` | `7C0007741198173CCCA9380A71D530CF93491DD3AACBC9402132E125A9BEDA30` |
| `test_whole_os_benchmark.txt` | `D8D63F9EEAB723415D7AD75437207532A98DF88BF684EBAD5754C82105461363` |
| `test_campaign_metrics.txt` | `4784F680C810FEFCC5118B3DC40BF08562F9F422897389190CF7278F0D37A715` |
| `exit-status.txt` | `E510D7A07C40D7E5736D146DAE650B718E09EAC4232EB953DDDBB14E17658712` |
| `campaign-metrics-exit-status.txt` | `EF87674C99240CC5D7C2FC7F66ED8C56DA47C09840F17A3512D66510A20AD787` |
| `canonical-cli-help.txt` | `0BB88B29BC9EDADD5840A1E435A6C010C664C352A53D4FCF605CBED46A410747` |

## Court disposition

**DEFER — no promotion.** The current champion remains unchanged. This result
makes no superiority, noninferiority, safety, cost, latency, or functional-win
claim. Resume only after an independently administered host supplies the six
listed obligations, concrete pinned recipes and disjoint manifests, then issue and
revalidate a bounded N30 lease before generating the exact adapter invocation.
