# Hive Cortex — local governed-autonomy qualification (QUALIFY-610)

## 1. Candidate identity

| Field | Value |
|---|---|
| Candidate commit | `00fd1d80579a6bbaee35abd9288fddceb05c6ebe` |
| Candidate tree | `b383e64f9c54bd4050136488243cd6cea383a66a` |
| Branch | `release/hive-mind-os-singleton-20260812-r5` |
| Date (UTC) | 2026-08-12 |
| Host platform | `Windows-11-10.0.26200-SP0` |
| Host Python | `3.14.4 (tags/v3.14.4:23116f9, Apr  7 2026, 14:10:54) [MSC v.1944 64 bit (AMD64)]` |
| Additional interpreter | CPython `3.12.10` (via `py -3.12`) |
| Evidence root | `evidence/qualification/hive-cortex/q610-00fd1d80/` |

Every outcome below comes from a command actually executed against **this** commit,
with its real exit code and a retained log whose sha256 is recorded in
`evidence/qualification/hive-cortex/q610-00fd1d80/receipts.json`. Nothing is estimated
or inferred.

An earlier execution of this node qualified commit `a3faac5e…` and returned
`NOT QUALIFIED` on two measured gate failures. Its evidence directory was **deleted in
full**; no digest, log, exit code or count is carried forward from it. The two defects
it found were repaired by orchestrator commit `5ead055` and are independently
re-measured here rather than taken on trust.

### 1.1 Environment normalization (disclosed, not laundered)

The qualifying shell exports `GIT_EDITOR=true`. `explorer.py::_git_environment`
(`src/hive_mind_os/brain_kernel/explorer.py:224-225`) deliberately rejects **any**
inherited `GIT_*` variable as an environment-injection attempt:

```python
if any(key.upper().startswith("GIT_") for key in os.environ):
    raise ExplorerDenied("inherited Git environment injection is not allowed")
```

`env | grep '^GIT_'` on this host returns exactly one line: `GIT_EDITOR=true`.
GitHub Actions runners export no `GIT_*` variable, so the variable was stripped with
`env -u GIT_EDITOR` on every test command in order to **reproduce** CI, not to hide a
failure. The two-line proof, re-measured at this candidate, is retained in
`gate1-ci/git-env-proof.log`:

| Condition | Command | Result |
|---|---|---|
| `GIT_EDITOR` set | `PYTHONPATH=src python -m unittest tests.test_hive_cortex_explorer` | `Ran 7 tests` — `FAILED (errors=2)`, exit 1 |
| `GIT_EDITOR` stripped | `env -u GIT_EDITOR PYTHONPATH=src python -m unittest tests.test_hive_cortex_explorer` | `Ran 7 tests` — `OK`, exit 0 |

Those 2 errors are environmental and specific to this host. They are not regressions,
and they are not suppressed: the control that produces them is a security control
working as designed.

### 1.2 Evidence retention warning — the logs must be force-added

`.gitignore:127` carries a repo-wide `*.log` rule (Visual Studio boilerplate). All 11
retained logs referenced by this report are therefore ignored by default, and a plain
`git add evidence/qualification/...` would silently drop every one of them — leaving
`receipts.json` citing sha256 digests of files that are not in the repository. That is
precisely the fake-evidence failure mode this node exists to detect, so it is recorded
rather than worked around.

The committing agent must force-add them:

```
git add -f evidence/qualification/hive-cortex/q610-00fd1d80/
```

`.gitignore` was **not** edited — it is outside this node's write scope. The precedent
is established: `git ls-files evidence/local_assurance/phase12-9efe64b/logs/` returns
four committed `*.log` files despite the same rule. The exact ignored paths are listed
under `retention_requirement` in `receipts.json`.

### 1.3 Validation lease

The single repository-wide validation pass for round R17 was taken under the global
validation lease, with this node as anchor and owner.

| Field | Value |
|---|---|
| Owner | `codex:qualify-610` |
| Lease id | `sha256:b88185d3c093adc718ed08ddfd24cbab14aec70911a96865b47ac1547bcaef47` |
| Target sha | `00fd1d80579a6bbaee35abd9288fddceb05c6ebe` |
| Acquired | `2026-08-12T18:01:02.278622Z` with `--lease-minutes 90` (exit 0) |
| Declared expiry | `2026-08-12T19:31:02.278622Z` |
| Released | `2026-08-12T18:33:47.847218Z` (exit 0, status `RELEASED`) |

Both repo-wide interpreter runs fit inside the window: the lease was held 32 m 45 s and
released 57 m 15 s before expiry, so exclusivity was lease-guaranteed for the entire
run. This corrects the previous execution's overrun, where the runbook's default
10-minute lease was exceeded by 23 m 38 s.

## 2. Gate results

| Gate | Command | Outcome | Log (under the evidence root) |
|---|---|---|---|
| `full-constitutional-ci` — compileall | `python -m compileall -q src tests` | **PASS** (exit 0) | `gate1-ci/compileall.log` |
| `full-constitutional-ci` — repo-wide unit tests (leased) | `env -u GIT_EDITOR PYTHONPATH=src python -m unittest discover -s tests -v` | **PASS** (exit 0) | `gate1-ci/unittest-full.log` |
| `full-constitutional-ci` — `quality` job, ruff | `python -m ruff check src tests` | **PASS** (exit 0) | `gate1-ci/ruff.log` |
| `full-constitutional-ci` — `quality` job, pyright | `python -m pyright` | **PASS** (exit 0) | `gate1-ci/pyright.log` |
| `full-constitutional-ci` — codeql / secret-scan / dependency-review / build-evidence | not runnable locally | **DEFERRED** | — |
| `complete-autonomy-acceptance` — focused suites | `env -u GIT_EDITOR PYTHONPATH=src python -m unittest tests.test_acceptance tests.hive_cortex.test_acceptance_harness tests.test_autonomy tests.test_policy_invariants -v` | **PASS** (exit 0) | `gate2-acceptance/focused-suite.log` |
| `complete-autonomy-acceptance` — module inventory | regex extraction over the Gate 1b log | **PASS** (exit 0) | `gate2-acceptance/module-inventory.txt` |
| `complete-autonomy-acceptance` — matrix suite coverage | node states cross-referenced against the inventory | **PASS** (6/7) + **DEFERRED** (`staged_autonomy`) | `gate2-acceptance/module-inventory.txt` |
| `clean-replay-verification` — clean worktree identity | `git -c core.longpaths=true worktree add --detach <scratch>/q610/clean2 <sha>` then `git status --porcelain` | **PASS** (exit 0) | `gate3-replay/worktree-status.txt` |
| `clean-replay-verification` — `snapshot_tree` | `PYTHONPATH=src python -c "... snapshot_tree('src') ..."` in the clean worktree | **PASS** (exit 0) | `gate3-replay/tree-snapshot.json` |
| `clean-replay-verification` — retained phase12 assurance replay | `verify_local_assurance_artifact` over every `evidence/local_assurance/phase12-*` packet | **PASS** (exit 0) | `gate3-replay/assurance-verify.log` |
| `clean-replay-verification` — focused replay suites | `env -u GIT_EDITOR PYTHONPATH=src python -m unittest tests.test_brain_kernel_verification tests.test_brain_kernel_local_assurance_artifact tests.test_brain_kernel_local_assurance_evidence tests.test_kernel -v` | **PASS** (exit 0) | `gate3-replay/replay-focused.log` |
| `cross-platform-qualification` — windows × 3.12 | `env -u GIT_EDITOR PYTHONPATH=src py -3.12 -m unittest discover -s tests -v` | **PASS** (exit 0) | `gate4-platform/py312.log` |
| `cross-platform-qualification` — windows × 3.14 (host, not a CI cell) | `env -u GIT_EDITOR PYTHONPATH=src python -m unittest discover -s tests -v` | **PASS** (exit 0) | `gate1-ci/unittest-full.log` |
| `cross-platform-qualification` — ubuntu × 3.11 / 3.12 / 3.14 | not runnable on this host | **DEFERRED** | `gate4-platform/host-platform.txt` |

### 2.1 Repo-wide result, verbatim

```
Ran 985 tests in 1006.990s

OK (skipped=7)
```

0 failures, 0 errors, 7 skipped, exit code 0. The 3.12 interpreter produced the same
census: `Ran 985 tests in 956.960s` — `OK (skipped=7)`. Per-module test counts
extracted from the log sum to exactly 985, cross-checking the inventory against the
summary line. The census is unchanged from the previous candidate, as expected:
commit `5ead055` changed only import ordering, one type annotation, one name binding
and statement layout, and `00fd1d8` touched only this runbook.

### 2.2 The `quality` job, re-measured

Both tools were already present at exactly the versions `.github/workflows/ci.yml`
pins — ruff `0.16.0` and pyright `1.1.411` — so nothing was installed and neither row
is DEFERRED. Both were invoked the way CI invokes them, from the repository root,
honouring the repository's own configuration (`pyproject.toml`
`[tool.ruff.lint] select = ["E4", "E7", "E9", "F", "I"]`, and `pyrightconfig.json`
`include: ["src"]`, `pythonVersion: "3.11"`, `typeCheckingMode: "basic"`).

- **ruff — `All checks passed!`**, exit 0. The 15 errors this node measured at
  `a3faac5e` (6× I001, 4× E701, 3× E702, 2× F401) are gone.
- **pyright — `0 errors, 6 warnings, 0 informations`**, exit 0. The 4 errors measured
  at `a3faac5e` are gone.

The 6 surviving pyright warnings are all `reportUnsupportedDunderAll` in
`src/hive_mind_os/brain_kernel/__init__.py` — names exported in `__all__` that are not
present in the module. They do not fail the gate (pyright exits 0; the CI `quality`
job gates on errors), but the package's declared public surface does not match its
actual one, so they are carried as residual blocker 10 rather than dropped.

## 3. Acceptance-matrix checklist

One row per suite key in `.autopilot/acceptance-matrix.json`. Evidence pointers are
test modules present in the Gate 1b execution log; counts are as executed. Suite
classification follows runbook step 4 as amended by `00fd1d8`: an uncovered suite is
**FAIL** when its `required_nodes` are all COMPLETE, and **DEFERRED** with the blocking
nodes named when they are not. Node states were read from
`python .autopilot/bin/autopilot.py --repo-root . status --json`: 34 COMPLETE, and the
only non-COMPLETE nodes appearing in any suite's `required_nodes` are A3-700, A4-800
and A5-900 (all `RECONCILIATION_REQUIRED`).

| Suite | Proof obligations (quoted from the matrix) | `required_nodes` state | Evidence (modules executed in `gate1-ci/unittest-full.log`) | Verdict |
|---|---|---|---|---|
| `all_role` | "all eight roles invoked where applicable"; "typed outputs and receipts"; "no fixture-only role counted as operational" | all 10 COMPLETE | `test_hive_cortex_orchestrator` (17), `_explorer` (7), `_architect` (5), `_builder` (13), `_curator` (8), `_integrator` (5), `_steward` (12), `_optimizer` (20), `test_hive_cortex_mission_runtime` (20), `test_hive_cortex_role_runtime` (3), `test_brain_kernel_roles`, `test_roles`, `test_mission` | **PASS** |
| `humanless_operation` | "role-first resolution"; "software defects become repair work"; "only genuine authority escalates" | all 3 COMPLETE | `hive_cortex.test_humanless_operation` (18), `test_hive_cortex_consultation` (6), `test_hive_cortex_mission_runtime` (20), `test_mission_loop`, `test_mission_loop_provider` | **PASS** |
| `learning` | "outcome-bound lessons"; "immutable challengers"; "held-out independent evaluation"; "atomic promotion/rollback" | all 6 COMPLETE | `test_hive_cortex_learning` (21), `test_hive_cortex_challengers` (19), `test_hive_cortex_evaluation` (17), `test_hive_cortex_promotion` (4), `hive_cortex.test_learning_poisoning` (22), `test_hive_cortex_optimizer` (20), `test_repository_learning`, `test_recursive_improvement` | **PASS** |
| `no_cheating` | "test weakening"; "future leakage"; "self-grading"; "fake evidence"; "authority expansion"; "friendly consultation" | all 4 COMPLETE | `hive_cortex.test_no_cheating` (20), `hive_cortex.test_acceptance_harness` (4), `test_hive_cortex_court` (3), `test_courtroom`, `test_hive_cortex_curator` (8), `test_curator`, `test_pit_oracle` (14), `test_hive_cortex_consultation` (6) | **PASS** |
| `repository_safety` | "isolated workspaces"; "declared paths"; "protected branch denial"; "idempotent remote effects" | all 4 COMPLETE | `test_hive_cortex_effects` (4), `test_hive_cortex_builder` (13), `test_hive_cortex_curator` (8), `test_hive_cortex_delivery` (19), `test_sandbox` (31), `test_git_adapter`, `test_github_adapter` | **PASS** |
| `self_healing` | "crash resume"; "stale lease repair"; "provider failover"; "rollback"; "no-progress quarantine" | all 4 COMPLETE | `test_hive_cortex_self_healing` (10), `test_hive_cortex_reconciler` (5), `test_hive_cortex_durability` (19), `test_hive_cortex_steward` (12), `test_scheduler` | **PASS** |
| `staged_autonomy` | "A3 no avoidable human answer"; "A4 explicit remote grant"; "A5 external governance and production authority" | **A3-700, A4-800, A5-900 all `RECONCILIATION_REQUIRED`, all downstream of this node** | none — a repository-wide search of `tests/` for `staged_autonomy`, `A3-700`, `A4-800`, `A5-900` returns no match | **DEFERRED** (blocked on A3-700, A4-800, A5-900) |

`staged_autonomy` is recorded as DEFERRED with its blocking nodes named, plus residual
blocker 3 — it does not disappear quietly, and it is not claimed as proven. Its three
required nodes are R18/R19/R20 while this node is R17, so its evidence cannot exist at
the only time this node ever runs.

## 4. Eight-role receipt inventory

Every one of the eight roles has an end-to-end module that executed and passed in the
leased repo-wide run. All eight also participate in the single canonical mission run
exercised by `test_hive_cortex_mission_runtime` (20 tests), whose originating commit
`f99d668` is titled "wire the canonical end-to-end mission runner through all eight
roles" — so these are not fixture-only role appearances.

| Role | Primary module (tests executed) | Cross-cutting end-to-end evidence | Retained evidence under `evidence/` |
|---|---|---|---|
| orchestrator | `tests/test_hive_cortex_orchestrator.py` (17) | `test_hive_cortex_mission_runtime`, `test_brain_kernel_planner` | `evidence/autopilot/`, `evidence/live/` |
| explorer | `tests/test_hive_cortex_explorer.py` (7) | `test_current_state_audit`, `test_pit_oracle` | `evidence/sources/`, `evidence/audits/` |
| architect | `tests/test_hive_cortex_architect.py` (5) | `test_hive_cortex_mission_runtime`, `test_hive_cortex_context` | `evidence/autopilot/arch-100/` |
| builder | `tests/test_hive_cortex_builder.py` (13) | `test_sandbox` (31), `test_hive_cortex_effects` | `evidence/autopilot/` |
| curator | `tests/test_hive_cortex_curator.py` (8) | `test_curator`, `test_brain_kernel_verification`, `test_hive_cortex_court` | `evidence/courts/` (read-only), `evidence/local_assurance/` |
| integrator | `tests/test_hive_cortex_integrator.py` (5) | `test_hive_cortex_delivery` (19), `test_github_adapter` | `evidence/autopilot/` |
| steward | `tests/test_hive_cortex_steward.py` (12) | `test_hive_cortex_self_healing` (10), `test_hive_cortex_durability` (19), `test_scheduler` | `evidence/governance/` |
| optimizer | `tests/test_hive_cortex_optimizer.py` (20) | `test_hive_cortex_learning` (21), `test_hive_cortex_challengers` (19), `test_hive_cortex_evaluation` (17) | `evidence/experiments/hive-cortex/` |

Retained-evidence roots are listed because they exist and belong to the named role's
work; this node did not re-verify their contents beyond the Phase 12 assurance packets
covered in Gate 3, and makes no claim about the rest.

## 5. Maturity verdict

Maturity level achieved: LOCAL-QUALIFIED (pre-A3). NOT release-ready.
NOT production-ready. No comparative/superiority claim is authorized
(retained assurance packets pin comparative_claim_authorized: false).
Real remote providers were not exercised (real_provider_used: false).

| # | Residual blocker | Why it blocks | Earliest resolving stage |
|---|---|---|---|
| 1 | GitHub-hosted-only jobs not reproducible locally: `codeql`, `secret-scan`, `dependency-review`, `build-evidence` (SBOM + provenance attestation) | Security, secret, licence and supply-chain assurance is unmeasured locally; no network or GitHub API effects were permitted | CI |
| 2 | CI matrix cells ubuntu × {3.11, 3.12, 3.14} not executed — host is Windows 11 and no CPython 3.11 is installed; provisioning is forbidden | Linux behaviour and the 3.11 floor / 3.14 ceiling are unverified on the declared platform | CI |
| 3 | Acceptance suite `staged_autonomy` DEFERRED: no covering module because A3-700, A4-800 and A5-900 are downstream and not COMPLETE | A mandatory acceptance suite is unproven, capping maturity below A3 | A3-700 / A4-800 / A5-900 |
| 4 | No real disposable-repository pilot; all repository work is against fixtures and the local checkout | Autonomy is unproven against a repository the system did not author | A3-700 |
| 5 | No remote delivery credentials exercised; no remote effect produced; `real_provider_used: false` | Remote grant, push, and draft-PR authority are unexercised end-to-end | A4-800 |
| 6 | External security, legal, operational and owner governance gates unmet; no merge or production authority | Production autonomy is ungoverned and therefore unauthorized | A5-900 |
| 7 | No comparative or superiority claim authorized; both retained phase12 packets pin `comparative_claim_authorized: false` and this node measured no comparator baseline | Any "better than" statement would be unevidenced | A5-900 |
| 8 | `evidence/local_assurance/phase12-54020b7.json` verified digest-only — no adjacent receipts manifest, so the receipt-transcript digest check could not be applied | Partial verification coverage of retained evidence; the packet's own `report_digest` re-derived correctly and nothing was rewritten | CI |
| 9 | `.gitignore:127` (`*.log`) ignores all 11 retained logs named in `receipts.json`; a plain `git add` would commit a manifest whose digests point at absent files | Receipt verifiability depends on a force-add the runbook never specifies | CI |
| 10 | pyright reports 6 non-blocking `reportUnsupportedDunderAll` warnings in `src/hive_mind_os/brain_kernel/__init__.py` | The package's declared `__all__` does not match its actual surface; does not fail CI, which gates on errors | CI |

## 6. Rollback reference

Candidate commit: `00fd1d80579a6bbaee35abd9288fddceb05c6ebe`
Candidate tree: `b383e64f9c54bd4050136488243cd6cea383a66a`

```
git revert 00fd1d80579a6bbaee35abd9288fddceb05c6ebe
```

This node writes only `docs/execution/HIVE_CORTEX_QUALIFICATION.md` and
`evidence/qualification/hive-cortex/q610-00fd1d80/**`. It changed no source, no tests,
and no retained evidence outside its own run directory. Reverting this node's own
commits removes the report and its receipts and nothing else.
