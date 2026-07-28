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
| Builder | `/root` | bounded repair, tests, evidence, and delivery |
| Final Orchestrator | `/root/orchestrator_final` | outcome boundary, dependencies, stopping conditions, and delivery readiness |
| Explorer, Clerk, and Advocate | `/root/explorer_ci_court` | immutable baseline inspection and strongest case for repair |
| Architecture Cross-Examiner and Integrator | `/root/architect_ci_contract` | alternatives, compatibility, installed-wheel boundary, rollback |
| Curator and Expert Witness | `/root/curator_ci_repro` | clean Python 3.11/3.12/3.14 reproduction, GitHub protection inspection, operational dissent |
| Steward | `/root/steward_exact` | separate maintainability, recovery, evidence-health, and receipt-retention review |
| Optimizer | `/root/optimizer_ci_metrics` | discoverability and regression measurements |
| Exact-candidate Integrator | `/root/integrator_exact` | protection provenance, compatibility, wheel/CI contract, and rollback review |
| Judge and Appeals Judge | `/root/judge_phase0` | initial adverse disposition, remand, exact evidence-head appeal, and delivery boundary |

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

## Adverse exact-candidate reviews and repairs

Independent review rejected two intermediate candidates:

1. The Integrator rejected `1f84e5f` because a missing or null ruleset
   `bypass_actors` field was treated as proof of administrator enforcement.
   Candidate `158c556` requires that field to be explicitly list-valued and
   empty; absent or malformed authority evidence fails closed.
2. The Curator rejected `158c556` because a partial non-bypassable ruleset
   could be merged with review or signature controls from bypassable classic
   branch protection. Candidate `afb0c20` preserves enforcement provenance:
   observations are combined only when both sources are explicitly
   non-bypassable; otherwise only the non-bypassable source may satisfy the
   declared controls. A partial-status-ruleset regression proves that review
   requirements remain mismatches instead of becoming false green.

These rejected candidates and dissent are retained. The final code candidate
is `afb0c20d2a618fc33431ca78c50568831f25aa7f`.

## Exact-candidate receipts

- Clean dependency-free Linux CPython 3.14:
  image
  `sha256:5f1cdbcab9a50594a79502dd73e885456d2a2fc31f1a1fa18484815b37ee9152`,
  container
  `a61a803b8c023e79213bf9a8f754e73ff078fc95b7ec14e0004593b042ed0fd6`,
  exact no-dependency editable install, and exact unittest discovery;
  420 tests passed in 176.939 seconds with one expected skip.
- Retained split unittest logs:
  `evidence/live/phase0/unittest-afb0c20.stdout.log`
  `sha256:dbbe035998d6c5fddbd7f42b1b70ff48c4e5ac491f840500e7add7c84b5f6efd`
  (1,138 bytes) and
  `evidence/live/phase0/unittest-afb0c20.stderr.log`
  `sha256:920c7dbfa2ecbf3dd5153382d9f03e2479c2f978b11a35d7197e0f2bde2a440c`
  (76,000 bytes).
- Current-state audit:
  `evidence/audits/PR27-ci-test-contract-repair.json`, bound to `afb0c20`,
  clean before and after tests, 419 pytest cases passed and one skipped in
  178.07 seconds, no failures, canonical integrity digest
  `sha256:ca51fa285fbfbab33b137ce7209036da287a946000cd969f823925032dd60aef`.
  The first Linux materialization attempt was correctly rejected as dirty
  because a raw Windows worktree copy changed line-ending representations; the
  passing receipt came from a clean Git clone.
- Ruff `0.16.0` and Pyright `1.1.411` independently passed on the exact
  candidate with zero diagnostics.
- Exact wheel:
  `sha256:3cc9890692e705eb524559a3bdc60981ce2c7cb9f9f44c2cb59eeff1542ed3d3`
  (267,598 bytes). The wheel is an ephemeral local artifact and is rebuilt for
  the GitHub build-evidence upload; its retained verification report is
  `evidence/live/phase0/installed-wheel-afb0c20.jsonl`,
  `sha256:0a7119a937f65b381fa2280fb25f70d4b9d110468f20f9fca82aa21cd1589876`;
  it proves an isolated installed import, 20 schemas plus 48 package files,
  all 68 resource bytes equal to source, 22 components, and quarantined
  `hive-core` trust.
- `evidence/live/phase0/receipt-manifest.json` binds the commands, environment,
  candidate, paths, digests, byte counts, and retention boundary.
- Post-test Windows worktree remained clean. The Windows full run's separately
  blocked process-survivor failure is preserved under `B-OPS-08` and is not
  counted as a passing Windows receipt.

## Independent Curator verdict

`/root/curator_ci_repro` independently reproduced the exact `afb0c20` changed
suite, Ruff, Pyright, installed-wheel bytes and catalog truth, split full-suite
logs, audit integrity, clean-clone/head guards, and unchanged sandbox blobs.
The Curator's disposition is `adapt`/accept for this bounded Phase 0 repair,
contingent on an independent Judge and green GitHub checks. `B-GOV-06`,
`B-OPS-07`, and `B-OPS-08` remain open; the verdict supports no broader host,
release, production, source-completeness, autonomy, or superiority claim.

## Final Orchestrator readiness finding

`/root/orchestrator_final` confirmed the clean evidence commit was technically
ready for a draft push but not promotion-ready. Live `enforce_admins=false`
remains `B-GOV-06`. The active PR author would be `kb4beast`, while current
write-capable identities are `kb4beast` and `beespinosa04`, protection requires
two approvals, and CODEOWNERS names only `kb4beast` for the affected paths.
The author cannot self-approve; current topology therefore cannot supply two
non-author approvals and a non-author code-owner review. `B-GOV-07` preserves
the required administrator/reviewer action without weakening review counts or
assuming that two account names prove genuine independence.

## Separate Steward verdict

`/root/steward_exact` initially rejected the evidence package because the
unittest logs and installed-wheel report had hashes but no durable repository
paths. That defect is closed by `evidence/live/phase0/receipt-manifest.json`
and its three bound artifacts. The Steward independently verified every byte
count and digest, the audit hashes, manifest bindings, court references, and
the `.gitattributes` binary-preservation rule for cross-platform checkout.

The amended Steward recommendation conditionally accepts the bounded repair.
Wheel bytes remain honestly ephemeral and are rebuilt/uploaded by CI; the
installed-wheel report is durable. Negative unit tests for verifier failure
branches are a non-blocking Steward + Builder follow-up before expanding the
resource catalog. `B-GOV-06`, `B-GOV-07`, `B-OPS-07`, and `B-OPS-08` remain
open.

## Initial judicial disposition and appeal

The first independent Judge review of evidence head `0f8113b` issued `defer`
because the receipt bytes, separate Steward testimony, and reviewer-topology
blocker were not yet bound. That losing disposition is preserved. The
retention artifacts, Steward verdict, and `B-GOV-07` now answer its remand; an
independent appeal/recheck of evidence head `3e41cb9` answered the remand.
Phase 1 remains prohibited until all required GitHub checks are green on the
exact final pull-request head.

## Appeal judicial disposition

`/root/judge_phase0` issued `adapt` on appeal for evidence head `3e41cb9`. The
Judge independently verified every manifest-bound byte count and digest, the
420-test receipt, installed-wheel report, audit integrity, unchanged
`afb0c20` code trees, separate Orchestrator and Steward findings, clean
worktree, and `B-GOV-07`.

The draft push is authorized solely to open the repair pull request and obtain
exact-head GitHub checks. Merge or promotion is not authorized while
`B-GOV-06` and `B-GOV-07` remain open; administrator bypass and weakened
review rules are prohibited. Phase 1 may not begin until every required check
is green on the exact final pull-request head, and any new commit resets that
gate. `B-OPS-07` and `B-OPS-08` remain deferred blockers. No broader host,
release, production, source-completeness, autonomy, or superiority claim is
adopted.

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

- Green exact-head GitHub checks.
- Administrator enforcement receipt for `B-GOV-06`.
