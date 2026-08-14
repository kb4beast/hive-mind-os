# Legacy runtime retirement — LEGACY-620

Retires the four legacy runtime modules as *independent authoritative brains*.
Canonical ownership (`hive_mind_os.brain_kernel.mission_runtime` + the cortex
compatibility adapters + the MIGRATION-460 public-ingress routing) is the
declared sole default. The legacy modules are **not** deleted: they survive as
explicitly marked rollback/compatibility surfaces, because the contract-mandated
rollback modes and nine un-editable test suites still drive them.

Nothing in this node changes execution authority. MIGRATION-460 (R4) already
made canonical the default route; LEGACY-620 declares and marks the retirement
semantics on top of that routing and adds no new routing of its own.

## 1. Identity

| Field | Value |
|---|---|
| Base commit (`$BASE`) | `81b7cc65976a5ca50ff4ccef734fa138d394aa42` |
| Base tree | `75cc7e9c0f2a4055294f986c26918d41ab582324` |
| Working branch at execution | `release/hive-mind-os-singleton-20260812-r5` |
| Node branch | `autopilot/legacy-620` — created by the round integrator, not by the worker |
| Final node commit / tree | **not created by this worker** (see note) |
| Rollback tag | `legacy-620-rollback` — **not yet created** (see note) |
| Rollback ref carried in code | `rollback:legacy-620` |
| Changed paths | exactly the five write-scope paths listed in section 2 |

**Note on commits and the tag.** This worker executed under an explicit
instruction to make no state-changing Git call — no `commit`, `add`, `checkout`,
`branch`, `tag`, `stash`, `reset`, or `push`. Runbook section 3.3 places the
annotated tag `legacy-620-rollback` at `$BASE` *before* the code edits; `$BASE`
is recorded above precisely so the tag can still be created at the right commit
after the fact. The round integrator owns:

```bash
git tag -a legacy-620-rollback \
  -m "LEGACY-620 rollback point: last commit with independent legacy brain ownership" \
  81b7cc65976a5ca50ff4ccef734fa138d394aa42
git push origin refs/tags/legacy-620-rollback
```

and then the three `rollback-tag-test` receipts from runbook section 5 that
depend on the tag existing (`git tag --list`, `git rev-parse
legacy-620-rollback^{commit}`, `git merge-base --is-ancestor`). The fourth
receipt in that row — `rollback-notice-ok`, which proves every module notice
names the tag — is code-only and **was** executed here (section 4). At the time
of writing `git tag --list legacy-620-rollback` returns empty.

## 2. Disposition table

| Module | Entry point | Disposition | Canonical owner | Notice symbol | Construction warning | Pinning consumers (all outside this write scope) |
|---|---|---|---|---|---|---|
| `src/hive_mind_os/mission.py` | `hive_mind_os.mission` | `retained-as-rollback-surface` | `brain_kernel.mission_runtime` | `hive_mind_os.mission.retirement_notice` | **omitted** — see section 6, blocker 1 | `cli.py:65`, `mission_store.py:991`, `benchmark_harness.py:27`, `workers.py:12`, frozen `__init__.py`; `tests/test_mission.py`, `test_acceptance.py`, `test_curator.py`, `test_roles.py`, `test_mission_store.py`, `test_github_adapter.py`, `test_benchmark_harness.py` |
| `src/hive_mind_os/mission_loop.py` | `hive_mind_os.mission_loop` | `retained-as-rollback-surface` | `brain_kernel.mission_runtime` | `hive_mind_os.mission_loop.retirement_notice` | `MissionLoop.__init__` | frozen `__init__.py:69` only (no production consumer); `tests/test_mission_loop.py` |
| `src/hive_mind_os/autonomous_os.py` | `hive_mind_os.autonomous_os` | `retained-as-rollback-surface` | `brain_kernel.mission_runtime` | `hive_mind_os.autonomous_os.retirement_notice` | `AutonomousBrain.__init__` | `cli.py:20`, frozen `__init__.py`; `tests/test_autonomous_os.py` |
| `src/hive_mind_os/workers.py` | `hive_mind_os.workers` | `delegating-via-R4-routing` (legacy branch `retained-as-rollback-surface`) | `brain_kernel.mission_runtime` | `hive_mind_os.workers.retirement_notice` | `execute_mission_job` | `cli.py:94` (`serve`), frozen `__init__.py`; `tests/test_workers.py`, `test_brain_kernel_workers.py` |

`docs/execution/LEGACY_RUNTIME_RETIREMENT.md` (this file) is the fifth
write-scope path.

Every notice is a plain `dict[str, str]` module constant, `LEGACY_RUNTIME_NOTICE`,
read through a `retirement_notice()` accessor that returns a **copy** so a caller
cannot mutate the module constant. No module imports anything from
`cortex.compatibility`: the kernel/compat layering note at the top of
`repository_compatibility.py` applies, and plain dicts add no import edge. The
only new import in any module is stdlib `warnings`.

The `canonical_destination` string in each notice mirrors the third positional
field of the corresponding `AdapterDescriptor` in
`src/hive_mind_os/cortex/compatibility/adapters.py` verbatim (lines 117, 144,
186, 219), so the notices and the compatibility registry cannot drift:

| Notice `entry_point` | `canonical_destination` | Mirrors |
|---|---|---|
| `hive_mind_os.mission` | `repository effect adapter plus Curator verifier` | `adapters.py:120` |
| `hive_mind_os.mission_loop` | `canonical role/action protocol` | `adapters.py:147` |
| `hive_mind_os.autonomous_os` | `canonical host/effect and outcome-learning adapters` | `adapters.py:189` |
| `hive_mind_os.workers` | `canonical leases and delivery workers` | `adapters.py:222` |

The cortex registry's own rollback refs (`rollback:legacy-workers`,
`rollback:repository-mission-legacy`, `rollback:mission-loop-legacy`,
`rollback:autonomous-brain-legacy`) are **unchanged**; the notices are additive
and carry their own `rollback:legacy-620`.

### 2.1 Section 3.1 decision — **row 1 (expected shape)**

The runbook's section 3.1 is a decision table, and row 1 was selected against the
real merged source, not assumed. Evidence:

| Row-1 condition | File:line | Measured |
|---|---|---|
| `route_job_executor` kind dispatch present | `src/hive_mind_os/workers.py:196-203` (pre-edit numbering) | dispatches `CANONICAL_JOB_KIND` → `execute_canonical_mission_job`, `LEGACY_JOB_KIND` → `execute_mission_job`, else `ValueError` |
| `execute_canonical_mission_job` present with `invoker=` seam | `src/hive_mind_os/workers.py:173-193` | rejects any `job.kind != CANONICAL_JOB_KIND` |
| `CanonicalMissionInvoker` alias present | `src/hive_mind_os/workers.py:90` | `Callable[[Job, Path], str]` |
| `_default_canonical_invoker` fails closed, never falls back | `src/hive_mind_os/workers.py:124-170` | every missing precondition raises `RuntimeRouteError`; the `brain_kernel` import is lazy and in-function |
| `Worker.__init__` default is `route_job_executor` | `src/hive_mind_os/workers.py:212` | confirmed by `inspect.signature` identity check (section 4, receipt E) |
| `serve` default is `route_job_executor` | `src/hive_mind_os/workers.py:290` | confirmed by `inspect.signature` identity check (section 4, receipt E) |
| `execute_mission_job` byte-identical legacy executor | `src/hive_mind_os/workers.py:31-87` | extracted from `git show bb64b95` (last pre-R4 commit) and from the working tree: both 2505 bytes, `a == b` → `True` |

Row 2 does not apply (dispatch is pure kind-based, not a selector/mode argument).
Row 3 does not apply (no dual-authority execution, no canonical→legacy fallback,
dispatch present, defaults already flipped) — so the `autopilot fail` escalation
was correctly **not** triggered.

**Row-1 change applied:** the retirement notice plus a `DeprecationWarning` in
`execute_mission_job` only. `route_job_executor`, `execute_canonical_mission_job`,
`_default_canonical_invoker`, `set_canonical_mission_bindings_provider`, and the
flipped `Worker`/`serve` defaults were not touched. The legacy kind is **not**
hard-disabled and is not gated behind an environment variable: `LEGACY_JOB_KIND`
dispatch is the contract-mandated rollback mode, and `tests/test_workers.py`
drives `execute_mission_job` through `"repository-mission"` jobs.

## 3. Parity evidence justifying retirement

Cited read-only; nothing under `evidence/` was created, modified, or rewritten by
this node.

- **QUALIFY-610 (R8) qualification packet** —
  `evidence/qualification/hive-cortex/q610-00fd1d80/verdict.json`: maturity
  `LOCAL-QUALIFIED (pre-A3)` at candidate commit `00fd1d80…`, tree `b383e64f…`,
  `gates_failed: []`. Repo-wide discovery `Ran 985 tests, OK (skipped=7)` on
  CPython 3.14 and again on 3.12; ruff 0.16.0 clean; pyright 1.1.411 `0 errors`;
  focused acceptance 26/26; focused replay 13/13. Gate logs under
  `q610-00fd1d80/gate1-ci/`, `gate2-acceptance/`, `gate3-replay/`,
  `gate4-platform/`, with per-file sha256 in `receipts.json`.
  That packet also records `release_ready: false`, `production_ready: false`, and
  `real_provider_used: false` — this retirement is a **local** declaration of
  canonical ownership, not a production cutover.
- **MIGRATION-460 routing evidence** — `docs/execution/CLI_MIGRATION.md`: section 1
  routing table (canonical is the default mode), section 4 single-authority
  invariant (`repository-mission` → legacy only, `canonical-mission` →
  `brain_kernel` only, unknown kind refused, canonical has no legacy fallback),
  and section 3 the two explicit rollback modes (`kernel-v1`, `legacy`) that this
  node must keep working.
- **Canonical runtime definition** — `docs/execution/CANONICAL_MISSION_RUNTIME.md`:
  `MissionRuntime` as the single local composition point for a full eight-role
  kernel mission over the closed event vocabulary.
- **Typed retirement blockers** —
  `src/hive_mind_os/cortex/compatibility/models.py:138` `RetirementBlocker` and the
  four `AdapterDescriptor`s in `adapters.py`. Those blockers are the reason the
  disposition is *retained-as-rollback-surface* rather than deletion: each of the
  four adapters still declares unaccepted parity evidence
  (`candidate parity`, `action parity`, `PIT learning parity`, `lease recovery`,
  and a `rollback rehearsal` for each).

## 4. Command receipts

Environment: Windows 11 (10.0.26200), CPython 3.14.4, repo root
`C:\Repos\HiveMind\hive-mind-os`, `PYTHONPATH=src` on every Python command.
Repo-wide `unittest discover` was **never** run by this node. Current repository-wide
validation belongs exclusively to the authenticated broker, not an integrator lease.

### 4.1 `legacy-parity-tests`

The runbook's exact section 5 command **fails at `$BASE`, before any edit of this
node**, and it still fails after — for a reason unrelated to retirement. See
section 6, blocker 2.

```
$ PYTHONPATH=src python -m unittest tests.test_mission tests.test_mission_loop \
      tests.test_autonomous_os tests.test_workers -v
ERROR: test_workers (unittest.loader._FailedTest.test_workers)
ImportError: Failed to import test module: test_workers
  File "C:\Repos\HiveMind\hive-mind-os\tests\test_workers.py", line 13, in <module>
    from fixtures.fixture_repo import build_fixture_repo
ModuleNotFoundError: No module named 'fixtures'
Ran 45 tests in 100.466s
FAILED (errors=1, skipped=1)          # exit 1 — identical at $BASE and after
```

At `$BASE`, before any edit, the same command produced the same single error
(`Ran 45 tests in 108.679s — FAILED (errors=1, skipped=1)`), and
`PYTHONPATH="src;tests" python -m unittest tests.test_workers -v` produced
`Ran 4 tests in 9.352s — OK`. The 45 counted "tests" are 44 real tests plus the
one loader error.

Corrected form (adds the `tests/` directory to `sys.path`, exactly what
`unittest discover -s tests` does implicitly; **no test file is modified**):

```
$ PYTHONPATH="src;tests" python -m unittest tests.test_mission tests.test_mission_loop \
      tests.test_autonomous_os tests.test_workers -v
Ran 48 tests in 114.636s
OK (skipped=1)                        # exit 0
```

`unittest` runs with `warnings="default"`, so the transcript visibly carries the
legacy `DeprecationWarning` raised through `route_job_executor` →
`execute_mission_job` while the test still reports `ok` — the warning is
informational and fails nothing.

### 4.2 `public-api-compatibility-tests`

```
$ PYTHONPATH=src python -m unittest tests.test_hive_cortex_compatibility tests.test_cli_enqueue -v
Ran 7 tests in 1.459s
OK                                    # exit 0
```

Import-surface receipt (the frozen `__init__.py` / `cli.py` names):

```
$ PYTHONPATH=src python -c "import hive_mind_os; from hive_mind_os import AutonomousBrain, \
    RepositoryMission, MissionLoop, Worker, serve; \
    from hive_mind_os.mission import resolve_repository_pin; \
    from hive_mind_os.autonomous_os import GitHubRestCommentGateway; print('public-api-ok')"
public-api-ok                         # exit 0
```

### 4.3 `rollback-tag-test`

No unittest file is inside this node's write scope, so this row is discharged by
command receipts. The code-only receipt:

```
$ PYTHONPATH=src python -c "import hive_mind_os.mission as a, hive_mind_os.mission_loop as b, \
    hive_mind_os.autonomous_os as c, hive_mind_os.workers as d; \
    ns=[m.retirement_notice() for m in (a,b,c,d)]; \
    assert all(n['rollback_tag']=='legacy-620-rollback' and n['rollback_ref']=='rollback:legacy-620' \
               for n in ns); print('rollback-notice-ok')"
rollback-notice-ok                    # exit 0
```

The three tag-dependent receipts are deferred to the integrator (section 1).

### 4.4 Edge cases required by runbook section 5

**Warnings do not leak at import** — they fire on construction, not import:

```
$ PYTHONPATH=src python -W error::DeprecationWarning -c "import hive_mind_os; print('import-clean')"
import-clean                          # exit 0
```

**`retirement_notice()` returns a copy** — for all four modules, mutating the
returned dict (overwriting `status`, injecting a new key) leaves
`LEGACY_RUNTIME_NOTICE` unchanged, and the next call returns a fresh, distinct
object: 8/8 checks PASS.

**Section 3.1 row-1 routing receipts** (`row1-receipts-ok`, all PASS):

- **A — legacy route.** One `LEGACY_JOB_KIND` (`"repository-mission"`) job through
  `route_job_executor` reaches `execute_mission_job`: exactly one
  `DeprecationWarning` is emitted, naming the executor, the canonical owner and
  the rollback tag; control then runs deep inside the legacy executor (raises
  `KeyError: 'scripted_variant'` from the real body) and the legacy stores are
  really opened (`missions.sqlite3`, `evidence-ledger.sqlite3`).
- **B — canonical route.** One `CANONICAL_JOB_KIND` job through
  `execute_canonical_mission_job(..., invoker=<test invoker>)` returns the mission
  id, runs the injected invoker, emits **zero** `DeprecationWarning`s, and creates
  **no** legacy store (state dir empty).
- **C — fail-closed.** With no bindings provider registered, a `CANONICAL_JOB_KIND`
  job through `route_job_executor` raises `RuntimeRouteError` and emits no legacy
  warning: the canonical route never degrades to legacy.
- **D — unknown kind.** `route_job_executor` refuses an unrecognised kind with
  `ValueError`, handing it to neither authority.
- **E — R4 mechanics intact.** `Worker.__init__` and `serve` executor defaults are
  still `route_job_executor` (identity-compared via `inspect.signature`); all of
  `JobExecutor`, `execute_mission_job`, `execute_canonical_mission_job`,
  `route_job_executor`, `Worker`, `serve`, `CanonicalMissionInvoker`,
  `Worker.run_once`, `Worker.drain` are retained.

### 4.5 Mutation evidence (the notice check actually bites)

The `rollback-notice-ok` receipt was proven to actually discriminate, rather than
passing vacuously. `workers.py`'s notice was reverted to a pre-LEGACY-620
rollback identity (`rollback_ref` → `rollback:legacy-workers`, `rollback_tag` →
`""`), the receipt was re-run, and the file was restored from a byte-exact copy:

```
sha256 BEFORE mutation : 3b378499c38e94d67e1f3118fe803e58201eae80e42f90fa662e1acdfe81706c
STEP 1 control (intact tree)      -> rollback-notice-ok        exit 0
STEP 2 mutate workers.py notice   -> applied (1 occurrence)
STEP 3 rollback-notice-ok re-run  -> AssertionError            exit 1   <-- the check bites
STEP 4 restore from byte-copy     -> sha256 AFTER: 3b378499c38e94d67e1f3118fe803e58201eae80e42f90fa662e1acdfe81706c
                                     RESTORE: BYTE-IDENTICAL
STEP 5 re-verify restored tree    -> rollback-notice-ok        exit 0
```

### 4.6 Quality gates and supplementary behavior preservation

```
$ python -m ruff check src tests
All checks passed!                    # exit 0   (ruff 0.16.0, the ci.yml-pinned version)

$ python -m pyright
0 errors, 6 warnings, 0 informations  # exit 0   (pyright 1.1.411, ci.yml-pinned)
```

The 6 pyright warnings are the pre-existing `reportUnsupportedDunderAll` warnings
in `src/hive_mind_os/brain_kernel/__init__.py`, outside this write scope and
already recorded as QUALIFY-610 residual blocker 10. This node did not add or
remove any.

Beyond the two `required_tests` rows, every other suite that runbook section 3.2
names as pinning the four modules, plus their non-test consumers, was run
focused. Results in section 4.7.

### 4.7 Measured outcomes

| Command | Result | Exit |
|---|---|---|
| `legacy-parity-tests` (exact runbook form) | `Ran 45 … FAILED (errors=1, skipped=1)` — pre-existing at `$BASE`, see blocker 2 | 1 |
| `legacy-parity-tests` (corrected `PYTHONPATH="src;tests"`) | `Ran 48 … OK (skipped=1)` | 0 |
| `public-api-compatibility-tests` | `Ran 7 … OK` | 0 |
| `public-api-ok` import surface | `public-api-ok` | 0 |
| `import-clean` under `-W error::DeprecationWarning` | `import-clean` | 0 |
| `rollback-notice-ok` | `rollback-notice-ok` | 0 |
| `retirement_notice()` copy semantics | 8/8 PASS | 0 |
| section 3.1 row-1 routing receipts | `row1-receipts-ok`, all PASS | 0 |
| supplementary pinning suites (10 modules) | `Ran 135 tests in 540.870s … OK` | 0 |
| mutation probe on the `workers.py` notice | check fails on mutation, byte-identical restore | 1 then 0, as designed |
| `ruff check src tests` | `All checks passed!` | 0 |
| `pyright` | `0 errors, 6 warnings` | 0 |

Supplementary suites run (single focused invocation,
`PYTHONPATH="src;tests"`): `tests.test_acceptance`, `tests.test_curator`,
`tests.test_roles`, `tests.test_mission_store`, `tests.test_github_adapter`,
`tests.test_benchmark_harness`, `tests.test_hive_cortex_cli_migration`,
`tests.test_brain_kernel_workers`, `tests.test_cli_demo`,
`tests.test_continuation` — `Ran 135 tests in 540.870s`, `OK`, exit 0.
`tests.test_roles::test_public_mission_entrypoint_remains_small` is included:
it asserts `len(inspect.getsource(RepositoryMission.run).splitlines()) < 200`,
and this node added nothing to `RepositoryMission.run` (it remains 4 lines).

**Zero files under `tests/` were modified.** `git status --short tests/` and
`git diff --stat -- tests/` are both empty; the only changed paths in the working
tree are the five write-scope paths.

## 5. Rollback procedure

Reversibility is **revert the node commit**, never a history rewrite. Retained
evidence and adverse receipts of earlier nodes are preserved untouched.

1. **Inspect the pre-retirement state.** Once the integrator has created the tag:
   `git checkout legacy-620-rollback` — the last commit with independent legacy
   brain ownership (`81b7cc65976a5ca50ff4ccef734fa138d394aa42`).
2. **Undo the retirement.** Revert the LEGACY-620 node commit
   (`git revert --no-commit <node-commit>`). This restores the four module
   docstrings and removes the notices; it changes **no** execution behavior,
   because this node changed none — see step 4.
3. **Roll a request back to legacy execution.** This is independent of steps 1-2
   and needs no revert. Per `docs/execution/CLI_MIGRATION.md` section 3, re-run the
   same `hive-mind enqueue` with an explicit mode:
   `--compatibility-mode kernel-v1` (legacy execution plus the `legacy-enqueue-v1`
   kernel ingress record) or `--compatibility-mode legacy` (legacy execution, no
   kernel write). Both produce a `repository-mission` job that the unchanged
   `execute_mission_job` runs. Enqueue is deduplicated on the payload digest, so
   repeating a command is a read-only retry.
4. **What a revert does and does not restore.** LEGACY-620 is additive and
   behavior-preserving: it adds `LEGACY_RUNTIME_NOTICE`, `retirement_notice()`,
   `_warn_retired()`, three construction `DeprecationWarning`s, and docstrings. It
   deletes no class, function, constant, or behavior, and it does not change the
   routing MIGRATION-460 installed. Reverting therefore only removes the
   *declaration* of retirement. Rolling the canonical **default** back to legacy is
   MIGRATION-460's rollback (`rollback:cli-compatibility-mode-kernel-v1`), not
   this node's.
5. **Rollback identity carried in code.** Every module notice carries
   `rollback_ref: "rollback:legacy-620"` and `rollback_tag: "legacy-620-rollback"`,
   verifiable at runtime with the `rollback-notice-ok` receipt in section 4.3.

## 6. Residual blockers

Honest and complete. Each item is retained or deviated *because* an un-editable
test or an out-of-scope file pins it.

1. **`RepositoryMission.__init__` carries no `DeprecationWarning`** — a deliberate
   deviation from runbook section 3.2, taken under that same section's explicit
   precedence rule ("behavior preservation outranks the warning") and under
   acceptance criterion 2.

   Section 3.2 anticipated only `assertWarns` / `simplefilter("error")` in the four
   pinned suites; a preflight grep found **none** anywhere in `tests/`, in
   `conftest.py`, or in `pyproject.toml`. The real conflict is different and was
   found by measurement, not by reading:

   - `tests/test_mission.py:769` asserts
     `json.loads(sabotage.stderr)["status"] == "failed"` — it requires the
     `hive-mind deliver` subprocess's **stderr** to be a bare JSON document.
   - `cli.py:820` constructs `RepositoryMission`. Run as
     `python -m hive_mind_os.cli`, that frame's module is `__main__`, so with the
     mandated `stacklevel=3` the warning is attributed to `__main__` and Python's
     default `default::DeprecationWarning:__main__` filter **prints** it.
   - Measured stderr, first line, with the warning in place:
     `C:\…\src\hive_mind_os\cli.py:820: DeprecationWarning: hive_mind_os.mission.RepositoryMission is a retired legacy runtime surface (LEGACY-620); …`,
     followed by the JSON on line 3. `json.loads` then raises
     `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`.
   - With the warning present: `tests.test_mission` `FAILED (errors=1)`. With it
     removed: `OK`. The four suites in `legacy-parity-tests` were green at `$BASE`,
     so this was a real regression introduced by the warning, not a pre-existing one.

   The two mandates cannot both hold: the warning targets the CLI operator via
   `__main__` attribution, and the test forbids anything on that stream. Editing
   the test is forbidden, and lowering `stacklevel` to 2 would only hide the
   warning from exactly the operator it exists to inform — cosmetic compliance, so
   it was rejected. The warning is therefore omitted for this one surface. Its
   retirement contract is carried by `LEGACY_RUNTIME_NOTICE` and
   `retirement_notice()`, which acceptance criterion 1 accepts as the alternative
   ("delegates … **or** carries a machine-readable compatibility/retirement
   notice"). `mission._warn_retired` remains defined, with a docstring and an
   in-place comment at the constructor, so a future node can restore the call the
   moment `tests/test_mission.py:769` is relaxed. The other three surfaces
   (`MissionLoop.__init__`, `AutonomousBrain.__init__`, `execute_mission_job`) do
   carry the warning and are unaffected: none of them writes to a stream any test
   parses as JSON.

2. **Runbook section 5's `legacy-parity-tests` command is defective as written** —
   pre-existing, not caused by this node, and not fixable inside this write scope.
   `PYTHONPATH=src python -m unittest tests.test_workers` cannot import
   `tests/test_workers.py:13` (`from fixtures.fixture_repo import build_fixture_repo`)
   because only `unittest discover -s tests` puts `tests/` on `sys.path`. Measured
   identically at `$BASE` and after this node's edits: `ModuleNotFoundError: No
   module named 'fixtures'`, exit 1. Fixing it inside the repo would require
   editing `tests/test_workers.py` or adding a `conftest.py` — both forbidden. The
   corrected invocation `PYTHONPATH="src;tests"` runs all 48 tests green and is
   recorded alongside the literal command in section 4.1. The repo-wide
   `unittest discover -s tests` pass that CI and the round integrator run is
   unaffected.

3. **Legacy execution paths are retained, not removed.** All four modules keep
   every class, function, and constant. The `LEGACY_JOB_KIND` branch of
   `route_job_executor` still executes `RepositoryMission` through `MissionStore`.
   This is contract-mandated (runbook sections 3.1 and 7: rollback modes must keep
   working, `execute_mission_job` must not be hard-disabled or env-gated) and is
   pinned by `tests/test_workers.py::WorkerTests`, which drives
   `"repository-mission"` jobs end to end.

4. **The four cortex `RetirementBlocker` records are still unresolved**, and this
   node did not and could not resolve them (`cortex/**` is forbidden scope): each
   adapter still declares unaccepted `candidate parity` / `action parity` /
   `PIT learning parity` / `lease recovery` evidence plus a `rollback rehearsal`.
   Retirement here is a declaration of canonical *default* ownership, not proof
   that the legacy paths are removable.

5. **The rollback tag does not exist yet.** `git tag --list legacy-620-rollback`
   is empty at the time of writing; the tag and its three receipts are the round
   integrator's (section 1). Every module notice already names the tag, so the
   code-side half of the check passes today.

6. **Retirement is local-only.** Inherited from QUALIFY-610's packet:
   `release_ready: false`, `production_ready: false`, `real_provider_used: false`,
   `comparative_claim_authorized: false`. No real disposable-repository pilot, no
   remote delivery credential, and no external governance gate backs this
   retirement; those remain with A3-700 / A4-800 / A5-900.
