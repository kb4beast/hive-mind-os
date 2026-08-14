# RUNBOOK LEGACY-620 — Retire independent legacy brain ownership

Round **R9** (level 12), released **ALONE** (`parallel_safe: false`). No siblings.
Depends on QUALIFY-610 (R8). Branch: `autopilot/legacy-620`, PR target `main`,
stopping condition: **draft PR + validated node receipt; never merge**.

## 1. Contract summary

**Objective.** Retire the four legacy runtime modules as *independent
authoritative brains*. Canonical ownership (established R1–R8 by
`brain_kernel.mission_runtime` + cortex adapters + MIGRATION-460 routing) becomes
the declared sole default; the legacy modules survive only as explicitly marked
rollback/compatibility surfaces with a rollback tag and migration receipts.

**Compressed acceptance criteria.**
1. Every legacy entry point either delegates to canonical routing installed by
   MIGRATION-460 or carries a machine-readable compatibility/retirement notice.
2. **No retained public behavior or evidence path is lost** — every existing
   test that pins legacy behavior still passes unchanged (you cannot edit tests).
3. A rollback tag (`legacy-620-rollback`) and migration receipts
   (`docs/execution/LEGACY_RUNTIME_RETIREMENT.md`) exist and are verifiable.

**Scope table.**

| Kind | Paths |
|---|---|
| write | `src/hive_mind_os/mission.py`, `src/hive_mind_os/mission_loop.py`, `src/hive_mind_os/autonomous_os.py`, `src/hive_mind_os/workers.py`, `docs/execution/LEGACY_RUNTIME_RETIREMENT.md` |
| read | the four modules above, plus (read-only): `src/hive_mind_os/__init__.py`, `src/hive_mind_os/cli.py`, `src/hive_mind_os/repository_compatibility.py`, `src/hive_mind_os/cortex/compatibility/*.py`, `docs/execution/CLI_MIGRATION.md` (from MIGRATION-460), `docs/execution/CANONICAL_MISSION_RUNTIME.md` (from MISSION-400), `evidence/qualification/hive-cortex/**` (from QUALIFY-610) |
| forbidden | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` — plus the hard rules below |

**Hard scope rules (state in your receipt, obey absolutely).**
- Modify ONLY the five write-scope paths. Never touch any `__init__.py`,
  `conftest.py`, `pyproject.toml`, `tests/**`, `src/hive_mind_os/cli.py`,
  `src/hive_mind_os/repository_compatibility.py`,
  `src/hive_mind_os/cortex/**`, `.autopilot/**`, or any sibling node's files.
- New symbols live inside the four write-scope modules only; they are consumed
  by full module path (e.g. `hive_mind_os.workers.retirement_notice`). No
  package re-export edits (the package `__init__.py` is frozen).
- Never touch the release branch; never rebase/squash/amend the node branch;
  never run repo-wide test discovery (the authenticated validation broker exclusively
  owns that gate).

**Semantic locks.** `legacy-retirement`, `public-cli-routing`. You own the
retirement semantics; MIGRATION-460 (R4, already merged when you run) owns the
routing switch mechanics in `cli.py`/`repository_compatibility.py`. Do not
re-implement routing; consume what R4 installed.

## 2. Existing-code map (verified signatures on the current tree)

| Path | Symbol | Real signature | Role |
|---|---|---|---|
| `src/hive_mind_os/mission.py` | `RepositoryMission.__init__` | `(self, repository: str \| Path, objective: str, *, acceptance_criteria=(), acceptance_specifications=(), backend=None, pin=None, output_dir="hive-mind-delivery", policy=None, budget=None, ledger=None, mission_store=None, github_delivery=None, crash_hook=None, _run_id=None, _resume=False, _missing_workspaces=None) -> None` | Legacy P05/P06 delivery mission; pinned by `tests/test_mission.py`, `cli.py`, `mission_store.py:991`, `benchmark_harness.py:27` |
| `src/hive_mind_os/mission.py` | `RepositoryMission.run` | `async def run(self) -> MissionReport` | Legacy lifecycle entry |
| `src/hive_mind_os/mission.py` | `ScriptedRepositoryBackend.__init__` | `(self, variant: str = "good", *, test_argv=_DEFAULT_TEST_ARGV, criterion_argv=_DEFAULT_CRITERION_ARGV) -> None` | Deterministic offline backend used by CI + CLI fixtures |
| `src/hive_mind_os/mission.py` | `resolve_repository_pin` | `def resolve_repository_pin(repository: Path, pin: str \| None = None) -> str` | Pin resolver imported by `cli.py` and `workers.py` |
| `src/hive_mind_os/mission_loop.py` | `MissionLoop.__init__` | `(self, repository: str \| Path, objective: MissionObjective, *, output: str \| Path, base_commit: str, builder_limits=None, budget=None, policy=None) -> None` | Legacy Phase 2 role loop |
| `src/hive_mind_os/mission_loop.py` | `reduce_mission_state` | `def reduce_mission_state(state: MissionState, event: MissionEvent) -> MissionState` | Pure reducer pinned by `tests/test_mission_loop.py` |
| `src/hive_mind_os/autonomous_os.py` | `AutonomousBrain.__init__` | `(self, state_dir: str \| Path) -> None` | Legacy append-only autonomous brain (SQLite) |
| `src/hive_mind_os/autonomous_os.py` | `AUTONOMOUS_REQUIREMENTS` | `tuple[RequirementBinding, ...]` module constant | Carry-forward requirement bundle; must survive |
| `src/hive_mind_os/workers.py` | `execute_mission_job` | `def execute_mission_job(job: Job, state_dir: Path) -> str` | Scheduler job executor (see §3.1 for post-R4 shape) |
| `src/hive_mind_os/workers.py` | `Worker.__init__` | `(self, scheduler: Scheduler, owner: str, *, executor: JobExecutor = execute_mission_job, heartbeat_interval: float \| None = None) -> None` — **pre-R4 default shown**; after MIGRATION-460 (R4) the default is contractually `executor: JobExecutor = route_job_executor` (see §3.1) | Lease-owning worker; runtime-neutral |
| `src/hive_mind_os/workers.py` | `serve` | `def serve(state_dir: str \| Path, *, worker_count: int, once: bool, stop_event: threading.Event \| None = None, executor: JobExecutor = execute_mission_job) -> int` — **pre-R4 default shown**; after R4 the default is contractually `executor: JobExecutor = route_job_executor` (see §3.1) | Worker pool entry imported by `cli.py:87` |
| `src/hive_mind_os/workers.py` | `JobExecutor` | `JobExecutor = Callable[[Job, Path], str]` | Executor type alias |
| `src/hive_mind_os/repository_compatibility.py` | `record_legacy_enqueue` | `def record_legacy_enqueue(job: Job, *, kernel_state_dir: str \| Path \| None = None, legacy_state_dir: str \| Path) -> str` | Idempotent kernel-side binding of a legacy enqueue (read-only for you) |
| `src/hive_mind_os/cortex/compatibility/models.py` | `RetirementBlocker` | `@dataclass(frozen=True) RetirementBlocker(entry_point: str, reason: str, required_evidence: tuple[str, ...], rollback_ref: str)` | The typed retirement-blocker record your notices mirror |
| `src/hive_mind_os/cortex/compatibility/adapters.py` | `default_compatibility_registry` | `def default_compatibility_registry() -> CompatibilityRegistry` | Registry of the 4 legacy adapters (`RepositoryMission`, `MissionLoop`, `AutonomousBrain`, `legacy workers`) |
| `src/hive_mind_os/cortex/compatibility/routing.py` | `RollbackRouter.__init__` | `(self, legacy: Callable[..., _T], canonical: Callable[..., _T] \| None = None, *, rollback_ref: str = "route:legacy") -> None`; methods `qualify(verdict) / route(mode) / rollback() / invoke(*args, **kwargs)` | Single-authority router MIGRATION-460 uses; canonical route requires `ParityVerdict.matched` |
| `src/hive_mind_os/cortex/compatibility/parity.py` | `ParityProbe.compare` | `def compare(self, legacy, canonical) -> ParityVerdict` | Effect-free parity comparison |

**API freeze (cannot break; enforced by files outside your scope).**
`src/hive_mind_os/__init__.py` re-exports: `AutonomousBrain, AutonomousRunError,
HostKind, HostRunResult, PullRequestCommentGateway` (autonomous_os);
`MissionReport, RepositoryMission, ScriptedRepositoryBackend` (mission);
`ArchitectDesign, BuilderAction, BuilderLimits, CuratorResult, DiscoveryAction,
DiscoveryReport, MissionBudget, MissionEvent, MissionLoop, MissionLoopError,
MissionObjective, MissionState, MissionStatus, Orchestrator, StaleMissionState,
reduce_mission_state` (mission_loop); `Worker, serve` (workers).
`cli.py` additionally imports `GitHubRestCommentGateway` (autonomous_os) and
`resolve_repository_pin` (mission). Every one of these names must remain
importable with an unchanged call contract. **Freeze caveat:** the R4 flip of
the `Worker.__init__`/`serve` executor defaults from `execute_mission_job` to
`route_job_executor` is a contract-mandated MIGRATION-460 change, not a freeze
violation — the frozen contract for you is the *post-R4* signatures
(`route_job_executor` defaults), which you must not alter further.

## 3. Design

### 3.1 Post-R4 shape of `workers.py` (shared file across rounds)

`workers.py` is also in MIGRATION-460's write scope (R4). By contract
(`docs/execution/runbooks/MIGRATION-460.md` §3.2), R4 installs a **kind-based
dispatch**, not a switch inside `execute_mission_job` and not a switch in
worker-side `cli.py` ingress. The contractual post-R4 additions are:

- `CanonicalMissionInvoker` (`Callable[[Job, Path], str]` alias) and
  `_default_canonical_invoker` (lazy import of
  `hive_mind_os.brain_kernel.mission_runtime`; raises `RuntimeRouteError`
  fail-closed, never falls back to legacy);
- `execute_canonical_mission_job(job, state_dir, *, invoker=None) -> str`,
  which rejects any `job.kind != CANONICAL_JOB_KIND`;
- `route_job_executor(job, state_dir) -> str`, dispatching on `job.kind`:
  `CANONICAL_JOB_KIND` → `execute_canonical_mission_job`, `LEGACY_JOB_KIND`
  → `execute_mission_job`, anything else → `ValueError`;
- the `Worker.__init__` and `serve` executor defaults **flipped** from
  `execute_mission_job` to `route_job_executor` (only those two defaults
  change);
- `execute_mission_job(job, state_dir) -> str` itself stays **byte-identical**
  as the legacy-kind executor.

The symbols that **remain after R4 and that you must not remove or re-sign**:
`JobExecutor`, `execute_mission_job`, `execute_canonical_mission_job`,
`route_job_executor`, `Worker` (with `run_once`, `drain`, unchanged
lease/heartbeat mechanics), `serve`. Treat all R4 additions as frozen
routing mechanics owned by the `public-cli-routing` lock.

**Preflight (mandatory before editing):** read the merged `workers.py`,
`cli.py`, and `docs/execution/CLI_MIGRATION.md` to bind the actual R4 shape.
Then apply exactly one row of this decision table:

| Post-R4 finding | Your R9 change in `workers.py` |
|---|---|
| **Expected shape:** `workers.py` matches MIGRATION-460 §3.2 — `route_job_executor` kind dispatch + `execute_canonical_mission_job`/`CanonicalMissionInvoker` present, `Worker.__init__`/`serve` defaults are `route_job_executor`, `execute_mission_job` byte-identical legacy executor | Add the retirement notice + `DeprecationWarning` in `execute_mission_job` (§3.2) only. Do not touch `route_job_executor`, `execute_canonical_mission_job`, or the flipped defaults — the default flip is R4's contractual change, **not** an API-freeze violation. Do NOT hard-disable the legacy kind: `LEGACY_JOB_KIND` dispatch is the contract-mandated rollback mode, and `tests/test_workers.py` (`WorkerTests`, un-editable) drives `execute_mission_job` via `"repository-mission"` jobs and must pass byte-identically. |
| `workers.py` routes legacy vs canonical through some other contract-compliant mechanism (e.g. a selector/mode argument instead of pure kind dispatch), with legacy execution still reachable as an explicit rollback mode and no dual-authority execution | Keep both routes. Add the retirement notice + `DeprecationWarning` (§3.2). Legacy-route execution must additionally log the notice's `rollback_ref` into the job failure/receipt text it already produces — do not add new stores or side effects. Do NOT hard-disable the legacy route. |
| R4 shape contradicts the MIGRATION-460 contract (e.g. dual-authority execution, canonical falling back to legacy, `route_job_executor`/canonical dispatch absent entirely, or defaults still `execute_mission_job`) | STOP. Run the dispatcher-injected Fail command with its exact shared state, claim ID, launch instruction, resource key, and authority epoch, setting `--error "post-R4 workers.py contradicts node assumption <detail>"`. Never reconstruct an owner-only failure command. This is the "current code contradicts a node assumption" escalation condition. |

### 3.2 Retirement notice (new API, identical pattern in all four modules)

Each of the four modules gets, at module top level (no new imports beyond
`warnings` from the stdlib; **no imports from `cortex.compatibility`** — the
kernel/compat layering note in `repository_compatibility.py` applies, and plain
dicts avoid new import edges entirely):

```python
LEGACY_RUNTIME_NOTICE: dict[str, str] = {
    "entry_point": "hive_mind_os.workers",          # per module, see table
    "status": "retired-legacy-rollback-only",
    "canonical_owner": "hive_mind_os.brain_kernel.mission_runtime",
    "canonical_ingress": "hive_mind_os.cli (MIGRATION-460 routing)",
    "canonical_destination": "canonical leases and delivery workers",  # per module
    "rollback_ref": "rollback:legacy-620",
    "rollback_tag": "legacy-620-rollback",
    "retired_by_node": "LEGACY-620",
    "parity_evidence": "evidence/qualification/hive-cortex/",
    "migration_receipts": "docs/execution/LEGACY_RUNTIME_RETIREMENT.md",
}


def retirement_notice() -> dict[str, str]:
    """Machine-readable compatibility notice for this retired legacy entry point."""

    return dict(LEGACY_RUNTIME_NOTICE)


def _warn_retired(entry: str) -> None:
    warnings.warn(
        f"{entry} is a retired legacy runtime surface (LEGACY-620); the canonical "
        "owner is hive_mind_os.brain_kernel.mission_runtime; rollback tag "
        "legacy-620-rollback",
        DeprecationWarning,
        stacklevel=3,
    )
```

Per-module values of `entry_point` / `canonical_destination` (the destination
strings mirror `AdapterDescriptor.canonical_destination` in
`cortex/compatibility/adapters.py` exactly, so the doc and the registry agree):

| Module | `entry_point` | `canonical_destination` |
|---|---|---|
| `mission.py` | `hive_mind_os.mission` | `repository effect adapter plus Curator verifier` |
| `mission_loop.py` | `hive_mind_os.mission_loop` | `canonical role/action protocol` |
| `autonomous_os.py` | `hive_mind_os.autonomous_os` | `canonical host/effect and outcome-learning adapters` |
| `workers.py` | `hive_mind_os.workers` | `canonical leases and delivery workers` |

Call `_warn_retired(...)` at the top of exactly these constructors/functions:
`RepositoryMission.__init__`, `MissionLoop.__init__`,
`AutonomousBrain.__init__` (line 293), `execute_mission_job`. Never at import
time (import-time warnings would fire for every consumer of the frozen package
`__init__.py`). `DeprecationWarning` does not fail `python -m unittest`;
grep the four test modules for `assertWarns`/`simplefilter("error")` during
preflight — if any exists, drop the warning for that surface and record why in
the doc (behavior preservation outranks the warning).

Also rewrite each module's docstring first paragraph to state: retired legacy
surface, canonical owner, rollback tag, and pointer to the receipts doc.
**Delete nothing else.** All classes, functions, constants, and behavior in the
four modules are retained verbatim — the un-editable suites
`tests/test_mission.py`, `tests/test_mission_loop.py`,
`tests/test_autonomous_os.py`, `tests/test_workers.py`,
`tests/test_acceptance.py`, `tests/test_curator.py`, `tests/test_roles.py`,
`tests/test_mission_store.py`, `tests/test_github_adapter.py` pin them, as do
`mission_store.py:991` and `benchmark_harness.py:27` (both outside your scope).

### 3.3 Rollback tag

On the node branch, before any code edit:

```bash
BASE=$(git rev-parse HEAD)
git tag -a legacy-620-rollback -m "LEGACY-620 rollback point: last commit with independent legacy brain ownership" "$BASE"
git push origin refs/tags/legacy-620-rollback
```

If tag push is denied by remote policy, keep the local tag, record `$BASE` and
the tag object id in the receipts doc, and note "tag push deferred to round
integrator" — consult `orchestrator` route; do not fail the node for this alone.

### 3.4 Migration receipts doc — `docs/execution/LEGACY_RUNTIME_RETIREMENT.md`

New file (write scope). Required sections:
1. **Identity** — base commit (`$BASE`), final node commit, tree ids
   (`git rev-parse HEAD^{tree}`), branch, rollback tag name + tagged commit.
2. **Disposition table** — one row per module: entry point, disposition
   (`retained-as-rollback-surface` / `delegating-via-R4-routing`), canonical
   owner, notice symbol (`<module>.retirement_notice`), pinning consumers.
3. **Parity evidence** — cite (do not copy or rewrite) the QUALIFY-610 receipts
   under `evidence/qualification/hive-cortex/**` and the MIGRATION-460
   `docs/execution/CLI_MIGRATION.md` routing evidence that justify retirement.
4. **Command receipts** — verbatim outcomes of every §5 command.
5. **Rollback procedure** — `git checkout legacy-620-rollback` /
   revert-the-node-commit wording from the contract; adverse receipts preserved.
6. **Residual blockers** — anything retained solely because an un-editable test
   pins it (explicit, honest list; empty is acceptable only if true).

## 4. Implementation order (small commits, node branch only)

1. **Preflight (no edits).** Read merged `workers.py`, `cli.py`,
   `docs/execution/CLI_MIGRATION.md`, `docs/execution/CANONICAL_MISSION_RUNTIME.md`,
   `evidence/qualification/hive-cortex/**`; grep the four pinned test modules
   for `assertWarns`/warning filters; pick the §3.1 decision-table row. Record
   `git rev-parse HEAD` as base identity.
2. **Commit 1** — create + push rollback tag (§3.3); add
   `docs/execution/LEGACY_RUNTIME_RETIREMENT.md` with sections 1–3, 5.
3. **Commit 2** — `workers.py`: notice + `_warn_retired` in
   `execute_mission_job` + the selected decision-table change. Run
   `PYTHONPATH=src python -m unittest tests.test_workers -v`.
4. **Commit 3** — `mission.py`: notice + warning in `RepositoryMission.__init__`
   + docstring. Run `PYTHONPATH=src python -m unittest tests.test_mission -v`.
5. **Commit 4** — `mission_loop.py`: notice + warning in `MissionLoop.__init__`
   + docstring. Run `PYTHONPATH=src python -m unittest tests.test_mission_loop -v`.
6. **Commit 5** — `autonomous_os.py`: notice + warning in
   `AutonomousBrain.__init__` + docstring. Run
   `PYTHONPATH=src python -m unittest tests.test_autonomous_os -v`.
7. **Commit 6** — run the full §5 focused set; paste command receipts into the
   doc (section 4) plus section 6 residual blockers; final commit; open draft
   PR against `main`; emit the node completion receipt. STOP.

## 5. Test plan

Write scope contains **no test file**, so `required_tests` are discharged with
existing focused suites plus command receipts — never repo-wide discovery.

| required_tests name | Concrete mapping | Exact command |
|---|---|---|
| `legacy-parity-tests` | `tests.test_mission.RepositoryMissionTests`; `tests.test_mission_loop.MissionStateReducerTests` + `OrchestratorTests` + `MissionLoopAdversarialTests`; `tests.test_autonomous_os.AutonomousBrainTests`; `tests.test_workers.WorkerTests` (all pre-existing, unchanged — passing proves retained behavior is byte-compatible after retirement) | `PYTHONPATH="src;tests" python -m unittest tests.test_mission tests.test_mission_loop tests.test_autonomous_os tests.test_workers -v` (`PYTHONPATH=src:tests` on POSIX) |
| `public-api-compatibility-tests` | `tests.test_hive_cortex_compatibility.HiveCortexCompatibilityTests` (registry blockers + rollback routing) and `tests.test_cli_enqueue.EnqueueCliTests` (CLI ingress unchanged); plus import-surface receipt: `python -c "import hive_mind_os; from hive_mind_os import AutonomousBrain, RepositoryMission, MissionLoop, Worker, serve; from hive_mind_os.mission import resolve_repository_pin; from hive_mind_os.autonomous_os import GitHubRestCommentGateway; print('public-api-ok')"` | `PYTHONPATH=src python -m unittest tests.test_hive_cortex_compatibility tests.test_cli_enqueue -v` + the `python -c` receipt |
| `rollback-tag-test` | Command receipts (no unittest file is inside write scope — state this explicitly in the completion receipt): tag exists, is an ancestor, and matches every module notice | `git tag --list legacy-620-rollback` ; `git rev-parse legacy-620-rollback^{commit}` ; `git merge-base --is-ancestor legacy-620-rollback HEAD && echo ancestor-ok` ; `python -c "import hive_mind_os.mission as a, hive_mind_os.mission_loop as b, hive_mind_os.autonomous_os as c, hive_mind_os.workers as d; ns=[m.retirement_notice() for m in (a,b,c,d)]; assert all(n['rollback_tag']=='legacy-620-rollback' and n['rollback_ref']=='rollback:legacy-620' for n in ns); print('rollback-notice-ok')"` |

**Edge cases to verify by hand (receipts in the doc):**
- Warnings do not leak at import: `python -W error::DeprecationWarning -c "import hive_mind_os; print('import-clean')"` must succeed (warnings fire on construction, not import).
- `retirement_notice()` returns a *copy* (mutating the return value must not mutate `LEGACY_RUNTIME_NOTICE`).
- If §3.1 row 1 (expected kind-dispatch shape) applied: one `LEGACY_JOB_KIND` job through `route_job_executor` reaches `execute_mission_job` and emits the `DeprecationWarning`; one `CANONICAL_JOB_KIND` job (test invoker injected via `execute_canonical_mission_job`'s `invoker=` parameter) never touches legacy code. If row 2 applied: one legacy-route and one canonical-route receipt each identify their actual runtime and the legacy one carries `rollback:legacy-620`.

**`tests` must be on `PYTHONPATH` for the parity command, and this is not a
style preference.** `tests/test_workers.py:13` does
`from fixtures.fixture_repo import build_fixture_repo`; only
`discover -s tests` puts `tests/` on `sys.path`, so under a bare
`PYTHONPATH=src` that module fails to import with
`ModuleNotFoundError: No module named 'fixtures'`, 45 tests collect instead of
48, and the command exits 1 while appearing to have run the suite. The defect
is pre-existing and reproduces identically at the base commit; it is not
evidence of a regression. It cannot be fixed from inside this node — `tests/`
is read-only here and adding a `conftest.py` is forbidden — so the invocation
carries the fix.

Focused commands only. The completed R9 integrator's direct repository-wide test run is
historical evidence. Under the current publication FSM, neither worker nor integrator may
replace the validation broker with `python -m unittest discover`; without an attested
broker completion the round remains blocked.

## 6. Acceptance self-check

| Acceptance criterion | How demonstrably met | Completion-receipt evidence |
|---|---|---|
| Legacy entry points delegate to canonical runtime or are removed with compatibility notice | All four modules carry `LEGACY_RUNTIME_NOTICE` + `retirement_notice()` + constructor `DeprecationWarning`; `workers.py` honors the R4 canonical-default routing per §3.1 | Diff of the four modules; `rollback-notice-ok` receipt; §3.1 decision-table row recorded in the doc |
| No retained public behavior or evidence path is lost | Zero test files touched; full `legacy-parity-tests` + `public-api-compatibility-tests` pass on unchanged suites; frozen `__init__.py`/`cli.py` imports verified by the `public-api-ok` receipt | Focused unittest transcripts with outcomes; `public-api-ok` and `import-clean` receipts |
| Rollback tag and migration receipts exist | Annotated tag `legacy-620-rollback` at the recorded base commit; `docs/execution/LEGACY_RUNTIME_RETIREMENT.md` with all six sections | `git tag`/`rev-parse`/`merge-base` receipts; doc path + digest; base and final commit/tree identities |

Evidence requirements from the contract map directly: base/final commit + tree
ids (doc §1), changed-path inventory (exactly the five write-scope paths),
command/test receipts (doc §4), role/authority identities (your rendered-prompt
actor id), consultation records if §3.1 row 3 or tag-push denial occurred, and
rollback reference (`rollback:legacy-620` / tag).

## 7. Out-of-scope traps (do NOT do)

- Do NOT delete or rename `mission.py`, `mission_loop.py`, `autonomous_os.py`,
  `workers.py`, or any public symbol in them — the frozen package `__init__.py`,
  `cli.py`, `mission_store.py`, `benchmark_harness.py`, and nine test modules
  import them and are all outside your write scope.
- Do NOT edit `src/hive_mind_os/cli.py` or
  `src/hive_mind_os/repository_compatibility.py` (MIGRATION-460's locks) or
  anything under `src/hive_mind_os/cortex/**` (including the
  `CompatibilityRegistry` rollback refs `rollback:legacy-workers` etc. — your
  notices are additive, theirs stay as-is).
- Do NOT create tests, edit `tests/**`, `conftest.py`, `pyproject.toml`, any
  `__init__.py`, or `.autopilot/**`; do NOT touch
  `evidence/qualification/hive-cortex/**` (cite it read-only) or anything in
  `forbidden_scope`.
- Do NOT hard-disable the legacy execution branch or gate
  `execute_mission_job` behind an environment variable — explicit rollback
  modes must keep working and `WorkerTests` must pass unchanged.
- Do NOT emit warnings at module import time; do NOT convert warnings to errors.
- Do NOT run `python -m unittest discover`; do NOT merge the PR, touch the
  release branch, rebase/squash/amend, or start A3-700.
- Do NOT rewrite or "clean up" retained evidence or receipts of earlier nodes;
  reversibility is revert-the-node-commit, never history rewrite.
- If any required change exceeds this write scope (e.g. a consumer breaks
  without an edit outside scope), STOP and `autopilot fail` with the blocker —
  do not widen scope, do not weaken acceptance.
