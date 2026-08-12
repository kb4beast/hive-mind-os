# BENCH-600 — Reproducible multi-scenario autonomy benchmark + comparator court

## 1. Contract summary

**Objective.** Create a reproducible multi-scenario autonomy benchmark and a
comparator court without unsupported superiority claims.

**Acceptance criteria (compressed).**
1. Benchmark measures ALL seven dimensions: correctness, human interventions,
   role coverage, recovery, evidence completeness, cost, latency.
2. Every comparator is pinned AND licensed, or explicitly marked unavailable
   (with reason). Machine-checked.
3. No superiority claim anywhere without reproducible receipts; the court
   disposition is capped at `measurement-recorded` and a claim guard enforces
   this on the results document.

**Scope table.**

| Kind | Paths |
|---|---|
| write (ONLY these) | `benchmarks/hive-cortex/**`, `docs/benchmarks/HIVE_CORTEX_RESULTS.md`, `tests/test_hive_cortex_benchmark.py` |
| read | `benchmarks/**`, `src/hive_mind_os/benchmark_harness.py`, `tests/fixtures/hive_cortex/**` |
| forbidden | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

HARD RULES (state-and-obey):
- Create/modify ONLY the exact write-scope paths above. Do NOT touch any
  `__init__.py` (including `benchmarks/__init__.py` or a new
  `benchmarks/hive-cortex/__init__.py` — the directory name is hyphenated and
  must NOT become a package), any `conftest.py`, `pyproject.toml`,
  `docs/benchmarks/RESULTS.md` (owned elsewhere), sibling nodes' files,
  `.autopilot/**`, or anything in forbidden scope.
- No package re-export edits anywhere. New code under `benchmarks/hive-cortex/`
  is NOT importable by module path (hyphen); load it by file path with
  `importlib.util.spec_from_file_location` (see §3.5). Imports of existing
  code use full module paths (`hive_mind_os.benchmark_harness`).
- Work only on branch `autopilot/bench-600`. Never touch the release branch;
  never rebase/squash/amend the node branch; open a draft PR + push the
  receipt commit, then STOP (do not merge, do not start downstream nodes).
- Run ONLY the focused tests in §5. Never run
  `python -m unittest discover -s tests` — the round integrator runs the single
  leased repo-wide pass.
- Semantic lock: `autonomy-benchmark`. Round R6, wave = `BENCH-600` alone (no
  siblings; no coordination needed).

## 2. Existing-code map (real symbols; do not invent others)

All in `src/hive_mind_os/benchmark_harness.py` unless noted.

| Path | Symbol | Real signature | Role |
|---|---|---|---|
| src/hive_mind_os/benchmark_harness.py | `MEASUREMENT_DISPOSITION` | `MEASUREMENT_DISPOSITION = "measurement-recorded"` | The only allowed court disposition; reuse verbatim. |
| src/hive_mind_os/benchmark_harness.py | `bootstrap_interval` | `def bootstrap_interval(outcomes: Sequence[bool \| int], *, seed: int, samples: int = 2000) -> tuple[float, float, float]` | Seeded 95% CI for success rates; reuse for statistics. |
| src/hive_mind_os/benchmark_harness.py | `find_unauthorized_claims` | `def find_unauthorized_claims(root: str \| Path) -> tuple[str, ...]` | Scans `README.md` + `docs/**/*.md` for forbidden comparative-claim regex; reuse in the guard. |
| src/hive_mind_os/benchmark_harness.py | `MeasurementVerdict` | frozen dataclass; `__post_init__` raises `ValueError` unless `disposition == MEASUREMENT_DISPOSITION`, judge independent of lanes, lane identities distinct | Pattern to mirror for the comparator-court verdict (do NOT modify it; define your own dataclass in your own file). |
| src/hive_mind_os/benchmark_harness.py | `render_results` | `def render_results(report: Mapping[str, object]) -> str` | Markdown-rendering pattern (table + mandatory no-claim paragraph) to mirror. |
| benchmarks/founding-comparator-suite.json | (data) | JSON with `comparators: [{"source_id","name","pin_required":true}, ...]`, `required_controls`, `benchmark_families`, `minimum_safety_floors`, `"verdict": null` | Source of comparator names/`source_id`s (SRC-003/004/008/009/010/011/014/015) for the pinned registry. |
| tests/fixtures/hive_cortex/*/fixture.json | (data) | `{"schema_version":1,"fixture_id","scenario","language","languages":[...],"tests_present":bool}` | Four scenario fixtures: `hidden-defect-python`, `misleading-readme-node`, `monorepo-cross-language`, `no-test-csharp`. |
| tests/test_benchmark_harness.py | (conventions) | plain `unittest.TestCase` classes, run as `python -m unittest tests.test_x -v` | Test style to follow. |

Fixture ground truth you will encode in scenario checkers (verified content):
- `hidden-defect-python/app.py`: `discount_total(total, discount)` returns
  `total - discount - discount` (defect: subtracts twice); its test expects
  `discount_total(100, 10) == 90`.
- `misleading-readme-node/index.js`: `parsePort(value)` is `Number(value)`;
  README falsely claims privileged ports are rejected.
- `no-test-csharp/Program.cs`: `Main` returns `args.Length`; no tests exist.
- `monorepo-cross-language/`: `python/app.py` `component() -> "python"`, plus
  `node/index.js`, `csharp/Program.cs`, `tests/test_components.py`.

Do NOT import `hive_mind_os.receipts`, `benchmark_corpus`, `mission`, or any
`brain_kernel` module — they are outside read scope. Hash with
`hashlib.sha256`; canonical JSON with
`json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)`.

## 3. Design — new files (all inside write scope)

### 3.1 `benchmarks/hive-cortex/scenarios.json`
One entry per fixture directory in `tests/fixtures/hive_cortex/`:

```json
{"schema_version": 1, "scenarios": [
  {"scenario_id": "hidden-defect-python",
   "fixture": "tests/fixtures/hive_cortex/hidden-defect-python",
   "required_roles": ["explorer", "builder", "verifier"],
   "patch": {"app.py": "def discount_total(total: int, discount: int) -> int:\n    \"\"\"Apply the discount exactly once.\"\"\"\n    return total - discount\n"},
   "checker": "import sys; sys.path.insert(0, '.'); from app import discount_total; assert discount_total(100, 10) == 90; assert discount_total(50, 5) == 45"},
  ... 3 more ...
]}
```
Checkers are pure-Python assertion programs executed with
`sys.executable -B -c <program>` with `cwd=<workspace>` (mirrors the
`_CHECK_PROGRAMS` + `_run_hidden_check` pattern in `benchmark_harness.py`), so
node/csharp fixtures are checked by file-content assertions
(`pathlib.Path(...).read_text()`), never by running node/dotnet — the whole
benchmark must be offline and toolchain-free. Concrete checkers:
- misleading-readme-node: assert `index.js` contains a guard rejecting ports
  `< 1024` (the patch adds `if (port < 1024) throw new RangeError(...)`).
- no-test-csharp: assert a `tests/expected_behavior.md` file created by the
  patch exists AND `Program.cs` is unchanged byte-for-byte vs a recorded sha256.
- monorepo-cross-language: assert all three `component` sources still exist and
  the patched `python/app.py` returns `"python"` when imported.
Derive every patch/checker from the actual fixture bytes you read; do not
guess content.

### 3.2 `benchmarks/hive-cortex/runner.py` (standalone; stdlib + `hive_mind_os.benchmark_harness` only)

```python
class ScenarioError(ValueError): ...

@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    fixture: Path
    required_roles: tuple[str, ...]
    patch: Mapping[str, str]
    checker: str
    fixture_digest: str          # sha256 over sorted (relpath, bytes) pairs

def load_scenarios(repo_root: Path) -> tuple[Scenario, ...]  # parses scenarios.json, validates fixture dirs exist

@dataclass(frozen=True)
class AttemptMetrics:            # THE seven acceptance dimensions
    correctness: bool
    human_interventions: int
    role_coverage: float         # exercised/required, in [0,1]
    recovery: bool
    evidence_completeness: bool
    cost_units: int              # deterministic action counter
    latency_seconds: float       # wall clock; EXCLUDED from digests
    def to_dict(self) -> dict[str, object]

@dataclass(frozen=True)
class LaneResult:
    status: str                  # "succeeded" | "failed"
    roles_exercised: tuple[str, ...]
    human_interventions: int
    cost_units: int
    artifacts: Mapping[str, str] # relpath -> content written into attempt dir

class ScriptedHiveCortexLane:    # identity = "hive-cortex-scripted-lane-v1"
    def execute(self, scenario: Scenario, workspace: Path,
                checkpoint: Path, resume: bool) -> LaneResult
class NullBaselineLane:          # identity = "pinned-null-baseline-v1"; applies no patch
    def execute(...same signature...) -> LaneResult

class HiveCortexBenchmark:
    def __init__(self, repo_root: Path, *, seed: int, repetitions: int,
                 lanes: Mapping[str, object] | None = None) -> None
    def run(self, output_root: Path) -> dict[str, object]
    @staticmethod
    def render_results(report: Mapping[str, object]) -> str

def main(argv: Sequence[str] | None = None) -> int   # --output, --seed, --repetitions, --render <path>
if __name__ == "__main__": raise SystemExit(main())
```

Control flow of `run()`:
1. Load scenarios; compute `scenario_digest` per scenario and a corpus digest.
2. `run_key = sha256(canonical({"scenarios": digests, "lanes": lane ids,
   "seed": seed, "repetitions": repetitions, "runner": sha256(runner.py bytes)}))`;
   `run_id = f"hive-cortex-{run_key[:16]}"`. Refuse to overwrite an existing
   `output_root/run_id` (`FileExistsError`, append-only evidence — mirrors
   `BenchmarkHarness.run`).
3. For each scenario x repetition x lane: copy fixture to
   `attempts/<key>/workspace` (`shutil.copytree`), run lane. The lane writes a
   `checkpoint.json` after its first action; on repetition 2 the runner runs
   the lane TWICE — once interrupted after checkpoint (lane raises a scripted
   `_SimulatedInterruption`), then again with `resume=True` — and sets
   `recovery = (post-resume workspace digest == uninterrupted digest from
   repetition 1)`. Other repetitions record `recovery` from repetition 2's
   drill result for that lane/scenario (or `False` if drill failed).
4. Run the checker subprocess → `correctness`. `role_coverage =
   len(set(result.roles_exercised) & set(required_roles)) / len(required_roles)`.
   `evidence_completeness`: the four attempt artifacts below all exist and
   their sha256s are recorded. `cost_units` from the lane's action counter
   (files read + files written + checks run). `latency_seconds` via
   `time.monotonic()` around lane+check.
5. Per attempt write (canonical JSON, one trailing `\n`):
   `lane-report.json`, `metrics.json`, `check.json`, `checkpoint.json`.
   Delete nothing on failure — losing attempts are retained identically.
6. Append every attempt record to `raw-results.jsonl` (canonical lines).
   `results_digest = sha256(raw-results.jsonl bytes with all
   "latency_seconds" values replaced by 0 in a canonical copy)` — the digest
   file `raw-results.digest-input.jsonl` with zeroed latency is also written so
   the digest is reproducible byte-for-byte across machines.
7. Statistics per lane and per scenario via
   `hive_mind_os.benchmark_harness.bootstrap_interval(outcomes, seed=seed + lane_index)`
   over `correctness`, plus means for interventions/coverage/cost and
   recovery/evidence rates.
8. Build the comparator-court verdict (§3.3) and write `verdict.json` +
   `summary.json`; return the summary dict.

### 3.3 `benchmarks/hive-cortex/comparator_court.py`

```python
class ComparatorProvenanceError(ValueError): ...
class SuperiorityClaimError(ValueError): ...

@dataclass(frozen=True)
class ComparatorRecord:
    source_id: str; name: str
    pin: str | None              # exact commit/version, or None
    license: str | None          # SPDX id, or None
    availability: str            # "pinned" | "unavailable"
    reason: str | None
    # __post_init__: availability=="pinned" requires pin AND license non-empty;
    # availability=="unavailable" requires reason non-empty; else raise
    # ComparatorProvenanceError.

def load_comparators(path: Path) -> tuple[ComparatorRecord, ...]

@dataclass(frozen=True)
class ComparatorCourtVerdict:
    schema_version: int; disposition: str; judge_id: str
    lane_identities: tuple[str, ...]
    comparators: tuple[ComparatorRecord, ...]
    results_digest: str; obligations: tuple[str, ...]
    # __post_init__ mirrors MeasurementVerdict: disposition must equal
    # hive_mind_os.benchmark_harness.MEASUREMENT_DISPOSITION; judge_id not in
    # lane_identities; identities distinct. Any other disposition ->
    # SuperiorityClaimError("superiority dispositions require reproducible
    # receipts from multiple pinned external comparators; none exist").
    def to_dict(self) -> dict[str, object]

def guard_results_document(text: str) -> tuple[str, ...]
    # returns violation strings; flags superiority phrasing
    # (outperforms|beats|stronger than|superior to|state[- ]of[- ]the[- ]art)
    # near "hive" / "benchmark" / "comparator" / "baseline", and flags a
    # MISSING mandatory disclaimer line (see §3.6). Empty tuple == pass.
```

Judge id: `"hive-cortex-independent-benchmark-judge"` (never a lane identity).
Obligations (verbatim in verdict): no comparative claim authorized; external
comparators must be executed under equal pinned conditions before any
superiority court; all losing/failed attempts retained.

### 3.4 `benchmarks/hive-cortex/comparators.json`
Registry seeded from `benchmarks/founding-comparator-suite.json` comparator
list. Every entry in this node is honest: `"availability": "unavailable"` with
`"reason": "not executed in this repository; no pinned offline harness
integration yet"`, `pin: null`, `license: null` — EXCEPT the two in-repo lanes
which are pinned: e.g. `{"source_id": "LOCAL-000", "name": "pinned-null-baseline-v1",
"pin": "<this repo commit>", "license": "repository-internal", "availability":
"pinned", "reason": null}`. Do NOT invent pins or licenses for external
systems; that is exactly what acceptance criterion 2 forbids.

### 3.5 Loading convention (tests and cross-file use)
`benchmarks/hive-cortex/` is intentionally not a package. In
`tests/test_hive_cortex_benchmark.py`:

```python
import importlib.util
from pathlib import Path
_BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "hive-cortex"
def _load(alias: str, filename: str):
    spec = importlib.util.spec_from_file_location(alias, _BENCH / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
runner = _load("hive_cortex_runner", "runner.py")
court = _load("hive_cortex_comparator_court", "comparator_court.py")
```
`runner.py` loads `comparator_court.py` the same way relative to its own
`Path(__file__).parent`. No `sys.path` mutation, no `__init__.py`.

### 3.6 `docs/benchmarks/HIVE_CORTEX_RESULTS.md`
Generated by `HiveCortexBenchmark.render_results` from ONE real local run
(`python benchmarks/hive-cortex/runner.py --output
<scratch>/hive-cortex-bench --seed 7 --repetitions 3 --render
docs/benchmarks/HIVE_CORTEX_RESULTS.md`). Must contain: run id, corpus/runner/
results digests, seed, repetitions, the exact reproduction command, a
seven-dimension table per lane (correctness rate + seeded 95% CI,
interventions mean, role-coverage mean, recovery rate, evidence-completeness
rate, cost mean, latency mean flagged "informational, excluded from digests"),
the comparator table (name, source_id, pin, license, availability, reason),
and — verbatim, guard-checked — the disclaimer line:
`These are measurements only; they authorize no comparative quality or
superiority claim.` Note that raw artifacts are regenerable via the
reproduction command (run outputs are not committed). Never write
`docs/benchmarks/RESULTS.md`.

### 3.7 `benchmarks/hive-cortex/README.md` (short)
Layout, reproduction command, loading convention, and the no-claims rule.

## 4. Implementation order (small commits on `autopilot/bench-600`)

1. Read the four fixture directories; commit `scenarios.json` +
   `comparators.json` + `README.md`.
2. Commit `comparator_court.py` (records, verdict, guard) — pure functions
   first; they have no runner dependency.
3. Commit `runner.py` (scenarios, lanes, recovery drill, metrics, statistics,
   render, CLI).
4. Commit `tests/test_hive_cortex_benchmark.py`; iterate until §5 passes.
5. Run the real benchmark once into the scratch directory; commit the rendered
   `docs/benchmarks/HIVE_CORTEX_RESULTS.md`.
6. Push, open draft PR to `main`, attach the node receipt (base/final SHAs,
   changed-path inventory, test command receipts, rollback ref = revert of the
   node commit). STOP.

## 5. Test plan — `tests/test_hive_cortex_benchmark.py`

Focused command (the ONLY test command this node runs):

```bash
python -m unittest tests.test_hive_cortex_benchmark -v
```

| required_tests name | unittest class | key methods |
|---|---|---|
| benchmark-harness-tests | `BenchmarkHarnessTests` | `test_run_reports_all_seven_metric_dimensions` (every raw record's `metrics` has exactly the 7 keys); `test_same_seed_reproduces_results_digest` (two runs, same seed → equal `results_digest` despite differing latencies); `test_run_directory_is_append_only` (second run into same run_id raises `FileExistsError`); `test_recovery_drill_resumes_from_checkpoint`; `test_failed_attempts_are_retained_with_same_artifacts` (use a rigged always-failing lane; its attempt dir keeps all four artifacts); `test_statistics_use_seeded_bootstrap_interval` (matches direct `bootstrap_interval` call); `test_scenarios_cover_all_four_fixtures` |
| comparator-provenance-tests | `ComparatorProvenanceTests` | `test_registry_entries_are_pinned_or_marked_unavailable` (load real `comparators.json`; every record validates); `test_pinned_without_license_is_rejected` (`ComparatorProvenanceError`); `test_unavailable_without_reason_is_rejected`; `test_court_verdict_pins_lane_identities_and_judge_independence` |
| superiority-claim-guard-tests | `SuperiorityClaimGuardTests` | `test_guard_flags_superiority_phrasing` ("Hive Mind OS outperforms the baseline on this benchmark" → nonempty); `test_guard_requires_disclaimer_line`; `test_results_document_passes_guard` (real `docs/benchmarks/HIVE_CORTEX_RESULTS.md` → `()`); `test_non_measurement_disposition_raises_superiority_claim_error`; `test_repo_docs_scan_stays_clean` (`hive_mind_os.benchmark_harness.find_unauthorized_claims(repo_root)` does not flag `docs/benchmarks/HIVE_CORTEX_RESULTS.md`) |

Edge cases: empty scenario list → `ScenarioError`; `repetitions < 1` →
`ValueError`; lane returning wrong identity → attempt marked failed;
role_coverage with zero required roles forbidden at load time; checker
subprocess timeout (30s) → correctness False, attempt retained. Use
`tempfile.TemporaryDirectory` for run outputs in every test; never write test
output into the repo tree.

## 6. Acceptance self-check → receipt evidence

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Seven-dimension coverage | `AttemptMetrics` fields + `test_run_reports_all_seven_metric_dimensions` | focused-test transcript; `summary.json` excerpt from the recorded run |
| Comparators pinned+licensed or marked unavailable | `ComparatorRecord.__post_init__` + `ComparatorProvenanceTests` against the committed `comparators.json` | test transcript; `comparators.json` sha256 |
| No superiority claim without reproducible receipts | disposition hard-capped at `MEASUREMENT_DISPOSITION` (`SuperiorityClaimError` otherwise) + `guard_results_document` passing on the committed results doc + repo scan test | test transcript; guard output `()`; run id + digests in `HIVE_CORTEX_RESULTS.md` |
| Reproducibility | seeded run_key, latency-neutral `results_digest`, reproduction command in the doc, `test_same_seed_reproduces_results_digest` | two-run digest equality in test output |
| Evidence retention | append-only run dirs; failed attempts keep full artifact set | `test_failed_attempts_are_retained_with_same_artifacts` transcript |

## 7. Out-of-scope traps — do NOT

- Do NOT edit `src/hive_mind_os/benchmark_harness.py`, `benchmark_corpus.py`,
  `benchmark_baseline.py`, or `benchmarks/harness.py|corpus.py|baseline_agent.py|__init__.py|founding-comparator-suite.json` — read-only.
- Do NOT create `benchmarks/hive-cortex/__init__.py`, any `conftest.py`, or
  touch `pyproject.toml`, `tests/__init__.py`, `.autopilot/**`.
- Do NOT edit `docs/benchmarks/RESULTS.md`, `tests/test_benchmark_harness.py`,
  or anything under `tests/fixtures/hive_cortex/**` (fixtures are read-only
  inputs; copy them to temp workspaces instead).
- Do NOT write into `evidence/**` (forbidden `evidence/courts/**`; the rest is
  other nodes' surface). Run outputs go to a temp/scratch directory only.
- Do NOT import kernel modules (`hive_mind_os.brain_kernel.*`,
  `hive_mind_os.mission`, `hive_mind_os.receipts`, `hive_mind_os.autonomy`) —
  outside read scope; the runner is stdlib + `hive_mind_os.benchmark_harness`.
- Do NOT run node/npm/dotnet or any network call; checkers are Python-only.
- Do NOT invent pins/licenses for external comparators, and do NOT write any
  sentence comparing Hive Mind OS favorably to anything.
- Do NOT run repo-wide test discovery, touch the release branch, or
  rebase/squash/amend `autopilot/bench-600`.
