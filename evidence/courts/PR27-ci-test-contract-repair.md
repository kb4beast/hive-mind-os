# PR #27 CI Test-Contract Repair Court

## Boundary and provenance

- Case ID: `CASE-PR27-CI-TEST-CONTRACT`
- Captured user mission:
  `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md`
- Captured mission SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`
- Baseline repository:
  `https://github.com/kb4beast/hive-mind-os.git`
- Baseline commit:
  `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- Baseline subject:
  `Harden extensible agent architecture (#27)`
- Retrieval date: 2026-07-28
- Implementation branch: `codex/repair-ci-test-contract`
- Risk class: reversible isolated repository repair (`A2`), followed by a
  reversible draft pull request (`A3`) only after independent verification.

The handoff is a user requirement and mission brief, not proof that any
requested feature is already implemented. This court is limited to Phase 0:
restore an honest test boundary and preserve the remote-governance obligation
before beginning the Obsidian or agent-system redesign.

## Participants and separation

| Function | Identity | Scope |
| --- | --- | --- |
| Orchestrator and Builder | `/root` | bounded repair, tests, evidence, and delivery |
| Explorer, Clerk, and Advocate | `/root/explorer_ci_court` | immutable baseline inspection and strongest case for repair |
| Architecture Cross-Examiner and Integrator | `/root/architect_ci_contract` | alternatives, compatibility, installed-wheel boundary, rollback |
| Curator, Steward, and Expert Witness | `/root/curator_ci_repro` | clean Python 3.11/3.12/3.14 reproduction, GitHub protection inspection, operational dissent |
| Optimizer | `/root/optimizer_ci_metrics` | discoverability and regression measurements |
| Judge | pending independent identity | final disposition only after exact-candidate evidence |

The Builder may not use its own results as independent verification. The Judge
receipt remains pending until it reviews the exact committed candidate and the
independent Curator evidence.

## Frozen atomic claims

### `CI-001` — declared runner and dependency contract disagree

At baseline, `.github/workflows/ci.yml` installs the editable package with
`--no-deps` and runs:

```text
python -m unittest discover -s tests -v
```

`pyproject.toml` declares no runtime dependencies. Four merged test modules
import the undeclared `pytest` package. This is an implementation-burden claim.

### `CI-002` — the failure is independently reproducible

GitHub push run `30394284964` and pull-request run `30394298035` each failed
the Python 3.11, 3.12, and 3.14 unit-test jobs. The independent Curator
reproduced the same result in disposable clean Linux containers using CPython
3.11.15, 3.12.13, and 3.14.6:

- package install exit `0`;
- byte compilation exit `0`;
- exact unittest command exit `1`;
- 386 tests, four import errors, one skip;
- every error was `ModuleNotFoundError: No module named 'pytest'`.

### `CI-003` — import repair alone would create false green coverage

The four pytest-importing files held 31 top-level functions representing 38
parameterized pytest cases. A fifth merged module,
`tests/test_builtin_role_facade.py`, imported no pytest but also exposed only
top-level test functions. Focused `unittest` discovery ran zero tests from each
of the five modules. Therefore removing imports or installing pytest while
retaining the unittest runner would silently omit material ADR-017 coverage.

### `CI-004` — the remote process has an unresolved bypass

PR #27 was merged by repository administrator `kb4beast` at
`2026-07-28T20:00:36Z`, with zero reviews, while the unit jobs were still
running; all six push/PR unit jobs later failed. The live branch-protection API
currently reports the intended eight checks, two approvals, code-owner review,
last-push approval, signed commits, linear history, and conversation
resolution, but `enforce_admins=false`.

The current administrator bypass is proven. Because the API does not expose
the historical protection state, the claim that this exact setting caused the
PR #27 merge is a supported inference, not an observed historical fact.

### `CI-005` — clean Windows materialization has a path-length obligation

The independent Steward attempted a clean clone beneath a validated
77-character temporary root. Checkout failed and repeatedly reported
`Filename too long`. The longest tracked relative path is 192 characters and
`core.longpaths` was unset. This does not block the current short-path repair
workspace, but it blocks a general claim that arbitrary Windows clean
workspaces and recovery are reliable.

### `CI-006` — the Windows process tier has an independently exposed survivor

After the pytest import failures were removed, the exact full command on
Windows CPython 3.14 executed 420 tests in 975.986 seconds and exposed one
pre-existing platform failure:
`test_timeout_covers_early_parent_exit_and_background_child`. The parent exits
before the polling boundary retains its descendant; the background child
survives, no `SandboxTimeout` is raised, and temporary-workspace cleanup fails
with a sharing violation. The focused test reproduces the same failure.

This finding is outside the Linux GitHub CI-contract repair and does not justify
weakening the sandbox test or broadening the Phase 0 patch into an unreviewed
Windows security-boundary redesign. It is retained as `B-OPS-08` for the
already-planned P17 hard-isolation court. The exact Linux matrix remains the
promotion boundary for this repair; Windows sandbox or host support remains
explicitly unclaimed.

The independent Curator confirmed that both files are byte-identical to
baseline (`sandbox.py` blob `0fa7b6b...`, `test_sandbox.py` blob `b9cfed6...`)
and traced the current creation-time filter to baseline ancestor `a92e677`.
The fail-open mechanism is a single non-atomic Toolhelp parent-PID snapshot:
after the leader exits, a transiently missed child lets the runner persist
`succeeded` without durable ownership of the process tree. Twenty focused
repetitions also produced timing instability. The credible repair is a
suspended Windows root assigned to a kill-on-close Job Object before resume,
with job liveness governed by the same deadline and fail-closed create,
assignment, and resume paths. Toolhelp snapshots may remain diagnostic but
cannot be authoritative containment.

## Alternatives

### Alternative A — preserve dependency-free unittest CI

Convert every affected test to `unittest.TestCase`; replace `tmp_path` with
fresh `TemporaryDirectory` instances, `pytest.raises` with
`assertRaises`/`assertRaisesRegex`, parametrization with `subTest`, monkeypatch
with `unittest.mock.patch`, and the conditional symlink skip with
`unittest.SkipTest`. Retain pytest as an optional development runner.

Add a repository governance regression that rejects both pytest imports and
top-level `test_*` functions while the constitutional workflow uses
dependency-free unittest discovery.

### Alternative B — make pytest the constitutional runner

Declare and pin pytest, install it explicitly in every matrix job, change the
workflow runner, update audit and documentation contracts, and adjudicate the
new dependency and supply-chain surface.

### Alternative C — remove imports or add a local pytest shim

This would either silently leave top-level functions undiscovered or create an
incomplete imitation of pytest. It does not provide honest coverage.

## Advocate case

Alternative A is the smallest coherent repair. It matches the repository's
zero-runtime-dependency policy, 33 pre-existing unittest modules, and the
recorded P06, P12, and P13 CI repairs. It changes no runtime API, schema,
package manifest, role authority, source disposition, or production behavior.
Both runners can still execute the same behavioral assertions.

## Cross-examination and dissent

- Conversion can lose parameter cases, change exception scope, share temporary
  state, or turn a conditional skip into a pass. The focused dual-runner
  inventory and subtests must reproduce each case.
- A unittest headline count does not separately enumerate subtests. Receipts
  must state methods and logical parameter cases honestly.
- Alternative B is a defensible project-wide tooling choice because local
  plans use pytest. It is rejected only as the larger, unnecessary emergency
  repair; the dissent remains eligible for a later tooling court.
- A source-tree resource check is not installed-wheel proof. The clean wheel
  must preserve all 68 expected resources byte-for-byte, 22 components, and
  quarantined `hive-core` truth.
- Repository configuration can declare `enforce_admins=true`, observe the live
  mismatch, and fail closed. Only a repository administrator can close the
  host-side setting.
- The Windows path-length finding is separately tracked as `B-OPS-07`; it must
  not be hidden by using only the existing short workspace.
- The early-parent-exit survivor is separately tracked as `B-OPS-08`. Cleanup
  retries, timing inflation, or test weakening would conceal a real descendant
  containment gap and are prohibited.

## Optimizer measurements

The independent Optimizer compared the immutable baseline and candidate:

- baseline unittest discovery exposed zero tests in all five affected modules;
- candidate focused unittest exposed 36 methods, with 35 passing and one
  platform skip;
- candidate pytest preserved all 43 logical cases, including all ten
  parameter values, with 42 passing and one skip;
- each converted module exposes the expected nonzero method count
  (`5, 8, 6, 10, 7`);
- candidate-wide static discovery found 419 methods across 37 modules, with
  zero loader errors and zero zero-discovery modules;
- focused pytest runtime remained effectively unchanged (`0.84s` baseline,
  `0.86s` candidate).

The first governance regression could still miss deletion of a `TestCase`
wrapper. The Builder accepted that dissent and strengthened the gate: it now
recursively inventories test modules, loads each with `unittest`, rejects
loader errors, and requires every module to expose at least one case. The
textual workflow-command assertion remains defense in depth rather than a YAML
semantic proof; the exact clean-environment run and GitHub jobs are the
authoritative execution receipts.

## Proposed disposition

`adapt` Alternative A, with these conditions:

1. Convert all five silent or import-failing modules, not only the four named
   in the handoff.
2. Preserve all assertions, parameters, skips, temporary-state isolation, and
   pytest compatibility.
3. Add a repository-wide test-contract regression.
4. Make administrator enforcement part of the desired protection contract and
   preserve the live mismatch as `B-GOV-06`; do not claim repository code
   closes the external setting.
5. Run exact full unittest, pytest, Ruff, Pyright, clean wheel install/resource
   verification, and post-test worktree reconciliation.
6. Obtain a disjoint Curator and Judge receipt on the exact committed
   candidate.
7. Do not begin the larger redesign until the repair pull request is green.

Alternative C is `reject`. Alternative B is `defer` for a separate test-tooling
court. No source-completeness, release-readiness, production, host-support,
autonomy, or superiority claim is made.

## Acceptance, outcome, ownership, and rollback

- Failure-before receipt: clean 3.11/3.12/3.14 environments reproduce the exact
  import failure and silent fifth-module omission.
- Pass-after receipt: the exact CI command imports and executes the complete
  suite without pytest installed.
- Compatibility: focused and full pytest runs pass with no new skip.
- Governance: a regression detects undeclared pytest imports and top-level
  test functions; protection verification detects `enforce_admins=false`.
- Artifact: a clean installed wheel contains the exact 68 expected resources
  and loads the 22-component quarantined catalog.
- Integrity: tests do not modify the Git worktree.
- Outcome metric: required unit jobs pass on Python 3.11, 3.12, and 3.14 on the
  exact pull-request head.
- Owners: Builder `/root`; independent verification and maintenance evidence
  `/root/curator_ci_repro`; integration contract
  `/root/architect_ci_contract`; remote setting repository administrator.
- Rollback: revert the bounded test conversion and governance-contract changes
  only in favor of an equal-or-stronger discoverable runner contract. Never
  restore the known import-red or silent-zero-discovery state as an accepted
  baseline. Preserve this court, failures, dissent, and blockers.

## Pending receipts

- Exact candidate commit and diff digest.
- Full deterministic gates and clean wheel/resource receipt.
- Independent post-build Curator verdict.
- Independent Judge disposition.
- Green exact-head GitHub checks.
- Administrator enforcement receipt for `B-GOV-06`.
