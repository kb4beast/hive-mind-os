# QUALIFY-610 — Complete local governed-autonomy qualification

## 1. Contract summary

**Objective.** Run the complete local governed-autonomy qualification and issue an
honest maturity verdict. This is a **docs-and-evidence-only** node: it writes a
qualification report and retained receipts. It changes **no source code and no tests**.

**Round / siblings.** Round R8, level 11, **ALONE** (`parallel_safe: false`). Node
branch `autopilot/qualify-610`, PR target `main`, draft PR only — never merge.
Dependencies already integrated when this node dispatches: MIGRATION-460,
PROMOTE-530, POISON-540, BENCH-600, DELIVERY-420.

**Special authority.** This node runs the round's ONE repo-wide validation itself,
under the global validation lease (commands in section 4, step 3). No other
repo-wide test discovery is permitted anywhere else in the node. This is the
documented R8 exception to the README's Phase 3: the R8 integrator does not run
a second Phase 3 repo-wide pass — it verifies lease release and consumes this
node's retained `gate1-ci/unittest-full.log` receipts instead.

**Compressed acceptance criteria.**
1. All required CI and adversarial suites pass on the exact candidate commit.
2. All eight roles have meaningful end-to-end receipts.
3. Humanless, no-cheating, learning, self-healing, durability, and
   repository-safety gates pass.
4. Residual blockers and maturity labels are explicit (no inflated claims).

**Scope table.**

| Kind | Paths |
|---|---|
| write (ONLY these) | `docs/execution/HIVE_CORTEX_QUALIFICATION.md`, `evidence/qualification/hive-cortex/**` |
| read | `src/**`, `tests/**`, `docs/**`, `benchmarks/**` (plus root `AGENTS.md` and this runbook) |
| forbidden | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

Additionally forbidden to create or modify: any `__init__.py`, any `conftest.py`,
`pyproject.toml`, any sibling node's files, anything under `.autopilot/**`
(controller CLI invocations are fine; hand-editing its files is not), any file
under `src/**` or `tests/**`, and `.github/**`. Semantic lock:
`local-autonomy-qualification`.

**Windows path-length rule.** Retained evidence previously broke Windows checkouts
via long nested paths (fixed in commit `a3261ca` "fix(evidence): shorten retained
benchmark path"). All evidence for this node lives under one short run directory:
`evidence/qualification/hive-cortex/q610-<sha8>/` where `<sha8>` is the first 8 hex
chars of the candidate commit. Never copy benchmark attempt trees or other deep
directory hierarchies into evidence; retain logs and JSON summaries only.

## 2. Existing-code map (read-only; nothing here is modified)

| Path | Symbol | Real signature / shape | Role in this node |
|---|---|---|---|
| `.github/workflows/ci.yml` | workflow `Constitutional CI` | jobs: `unit-tests` (ubuntu, py 3.11/3.12/3.14: `python -m pip install --disable-pip-version-check --no-deps -e .`; `python -m compileall -q src tests`; `python -m unittest discover -s tests -v`), `unit-tests-windows` (py 3.12, same steps), `quality` (ruff `0.16.0` `check src tests`; pyright `1.1.411`), `codeql`, `secret-scan`, `dependency-review`, `build-evidence` | Defines what "full-constitutional-ci" means; Gate 1 reproduces the deterministic jobs locally and defers GitHub-hosted-only jobs honestly |
| `tests/test_ci_contract.py` | `class CIContractTests(unittest.TestCase)` | methods incl. `test_documented_gate_matches_workflow`, `test_workflow_exercises_windows_with_python_3_12`, `test_no_test_module_imports_third_party` | Proves the CI contract itself is intact (part of Gate 1) |
| `.autopilot/acceptance-matrix.json` | acceptance matrix | `{"baseline_commit": ..., "schema_version": 1, "suites": {all_role, humanless_operation, learning, no_cheating, repository_safety, self_healing, staged_autonomy}}`; each suite has `proof` and `required_nodes` | Gate 2 checklist source (read-only) |
| `docs/execution/AUTONOMY_ACCEPTANCE.md` | acceptance program | defines the seven suites, ACCEPT-240 harness fixtures, receipt-facing test identifiers | Normative definition of "complete-autonomy-acceptance" |
| `tests/hive_cortex/test_acceptance_harness.py` | `class AcceptanceHarnessTests(unittest.TestCase)` | adversarial harness self-tests + negative controls | Gate 2 focused suite |
| `tests/test_acceptance.py` | `class AcceptanceSpecificationTests(unittest.TestCase)` | e.g. `test_receipt_must_bind_the_specification_and_requested_argv` | Gate 2 focused suite |
| `src/hive_mind_os/brain_kernel/verification.py` | `def verify_bundle(bundle_directory: str \| Path) -> None` | "Re-derive the local bundle digest and embedded evaluation digest." Raises `ExactCandidateVerificationError(RuntimeError)` on mismatch | Gate 3: re-verify any retained verification bundles |
| `src/hive_mind_os/brain_kernel/verification.py` | `def snapshot_tree(root: str \| Path) -> TreeSnapshot` | hashes regular files only; symlinks/unsafe paths fail closed; `TreeSnapshot(root_digest: str, files: Mapping[str, str])` | Gate 3: candidate-tree identity in a fresh worktree |
| `src/hive_mind_os/brain_kernel/local_assurance.py` | `def verify_local_assurance_artifact(report_path: str \| Path, receipt_manifest_path: str \| Path) -> dict[str, object]` | fail-closed reconstruction of a Phase 12 assurance report + digest check of every retained receipt transcript; raises `LocalAssuranceError(ValueError)` | Gate 3: re-verify retained local assurance receipts |
| `evidence/local_assurance/phase12-9efe64b/` | retained Phase 12 packet | `assurance.json` (with `report_digest`, `candidate_commit`, `candidate_tree`, `comparative_claim_authorized: false`) + `receipts.json` manifest + `benchmark-success/<run>/summary.json` | Concrete input for Gate 3 replay verification |
| `tests/test_brain_kernel_verification.py` | `class ExactCandidateVerificationTests(unittest.TestCase)` | focused verification tests | Gate 3 focused suite |
| `tests/test_brain_kernel_local_assurance_artifact.py` | `class LocalAssuranceArtifactTests(unittest.TestCase)` | artifact round-trip tests | Gate 3 focused suite |
| `tests/test_brain_kernel_local_assurance_evidence.py` | `class LocalAssuranceEvidenceTests(unittest.TestCase)` | retained-evidence verification tests | Gate 3 focused suite |
| root `AGENTS.md` | test convention | `python -m unittest discover -s tests -v` is the documented repo-wide gate | Command style authority |
| `docs/execution/runbooks/README.md` | wave protocol | lease commands, worker read budget, "one leased repo-wide run per round" | Governs section 4 step 3 |

Modules created by earlier rounds (R2–R7: DURABLE-410, DELIVERY-420, HUMANLESS-430,
CHEAT-440, SELFHEAL-450, MIGRATION-460, LEARN-500, CHALLENGER-510, EVAL-520,
PROMOTE-530, POISON-540, BENCH-600, MISSION-400) will exist under `tests/` by the
time this node runs. Do not guess their filenames: the leased repo-wide discovery
pass executes all of them, and Gate 2 records the enumerated module list as
evidence (section 4, step 4).

## 3. Design — files this node creates

No Python. Two deliverable surfaces.

### 3.1 `docs/execution/HIVE_CORTEX_QUALIFICATION.md` (new, ~150–250 lines)

The qualification report. Required structure:

1. **Header block** — candidate identity, fill with real values:
   `Candidate commit`, `Candidate tree` (`git rev-parse HEAD` / `git rev-parse 'HEAD^{tree}'`),
   `Branch`, `Date (UTC)`, `Host platform` (`python -c "import platform,sys;print(platform.platform());print(sys.version)"`),
   `Evidence root: evidence/qualification/hive-cortex/q610-<sha8>/`.
2. **Gate results table** — one row per required test gate (section 5 names),
   columns: gate, exact command(s), outcome (`PASS` / `FAIL` / `DEFERRED`), log path
   under the evidence root.
3. **Acceptance-matrix checklist** — one row per suite key in
   `.autopilot/acceptance-matrix.json` (`all_role`, `humanless_operation`,
   `learning`, `no_cheating`, `repository_safety`, `self_healing`,
   `staged_autonomy`): suite, proof obligations (quote the matrix `proof` list),
   evidence pointer (test module names from the repo-wide run log), verdict.
4. **Eight-role receipt inventory** — for each role (orchestrator, explorer,
   architect, builder, curator, integrator, steward, optimizer): the test module(s)
   in the repo-wide log that exercised it end-to-end (the
   `tests/test_hive_cortex_<role>.py` family exists for all eight) and, where
   present, retained receipt paths under `evidence/`.
5. **Honest maturity verdict** — verbatim template, filled without softening:

   ```
   ## Maturity verdict

   Maturity level achieved: LOCAL-QUALIFIED (pre-A3). NOT release-ready.
   NOT production-ready. No comparative/superiority claim is authorized
   (retained assurance packets pin comparative_claim_authorized: false).
   Real remote providers were not exercised (real_provider_used: false).

   | # | Residual blocker | Why it blocks | Earliest resolving stage |
   |---|---|---|---|
   | 1 | <blocker> | <consequence> | A3-700 / A4-800 / A5-900 / CI |
   ```

   The residual table MUST at minimum contain honest rows for: (a) GitHub-hosted
   CI jobs not reproducible locally (codeql, secret-scan, dependency-review,
   build-evidence/attestation) — deferred to the Constitutional CI run on the
   draft PR; (b) any ubuntu / Python 3.11 / 3.14 matrix cells not executable on
   the local host; (c) no real disposable-repository pilot yet (A3-700);
   (d) no remote delivery credentials exercised (A4-800); (e) external
   security/legal/production gates unmet (A5-900). Add every gate that returned
   `DEFERRED` or `FAIL`. If any gate FAILS, the verdict is `NOT QUALIFIED` and the
   node still completes honestly with the failure receipts retained — do not
   weaken any gate to pass (node assumption: "No node may expand its own
   authority or weaken acceptance to pass").
6. **Rollback reference** — the exact candidate commit and the revert command
   (`git revert <commit>`), per the node contract.

### 3.2 `evidence/qualification/hive-cortex/q610-<sha8>/` (new)

Flat, short-pathed layout:

```
q610-<sha8>/
  gate1-ci/            compileall.log, unittest-full.log, ruff.log?, pyright.log?
  gate2-acceptance/    focused-suite.log, module-inventory.txt
  gate3-replay/        replay-focused.log, assurance-verify.log, tree-snapshot.json
  gate4-platform/      host-platform.txt, py312.log (+ pyXY.log per extra interpreter)
  receipts.json        manifest: candidate_commit, candidate_tree, per-gate entries
  verdict.json         machine-readable mirror of the maturity verdict
```

`receipts.json` shape (hand-written JSON, `schema_version: 1`): top-level
`candidate_commit`, `candidate_tree`, `generated_utc`, and `gates`: a list of
objects `{"gate": str, "command": str, "exit_code": int, "log": str (relative),
"log_sha256": str, "outcome": "PASS"|"FAIL"|"DEFERRED"}`. Compute log digests with
`python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" <log>`.
`verdict.json`: `{"schema_version": 1, "candidate_commit": ..., "maturity":
"LOCAL-QUALIFIED"|"NOT-QUALIFIED", "release_ready": false, "production_ready":
false, "comparative_claim_authorized": false, "residual_blockers": [ {"id": int,
"blocker": str, "resolving_stage": str} ]}`.

## 4. Implementation order (small commits on `autopilot/qualify-610`)

All commands run from the repo root. Use `python -m ... > <log> 2>&1` redirection
(works in PowerShell and bash) and check `$LASTEXITCODE` / `$?` after each; record
the exact exit code in `receipts.json`.

1. **Pin identity + scaffold evidence dirs.** `git rev-parse HEAD`,
   `git rev-parse 'HEAD^{tree}'`; create
   `evidence/qualification/hive-cortex/q610-<sha8>/{gate1-ci,gate2-acceptance,gate3-replay,gate4-platform}`.
   Commit: `docs(qualify): scaffold q610 evidence root` (dirs need a file — put
   `receipts.json` skeleton in now).
2. **Gate 1a — deterministic CI reproduction (non-leased parts).**
   `python -m compileall -q src tests > evidence/qualification/hive-cortex/q610-<sha8>/gate1-ci/compileall.log 2>&1`.
   If `ruff` is installed locally run `ruff check src tests` to `ruff.log`; if
   `pyright` is installed run it to `pyright.log`; if either tool is absent DO NOT
   install anything — record the gate row as `DEFERRED` to the draft PR's
   Constitutional CI `quality` job.
3. **Gate 1b — the single leased repo-wide pass.** Exactly per
   `docs/execution/runbooks/README.md` Phase 3, with this node as anchor and owner:

   ```
   python .autopilot/bin/autopilot.py --repo-root . validation-lease-acquire QUALIFY-610 --owner codex:qualify-610
   python -m unittest discover -s tests -v > evidence/qualification/hive-cortex/q610-<sha8>/gate1-ci/unittest-full.log 2>&1
   python .autopilot/bin/autopilot.py --repo-root . validation-lease-release QUALIFY-610 --owner codex:qualify-610
   ```

   Always release the lease, even on failure. This log is the authoritative input
   for Gates 1, 2, and the role inventory. Commit:
   `docs(qualify): record constitutional ci gate receipts`.
4. **Gate 2 — acceptance evidence extraction + focused confirmation.** From
   `unittest-full.log`, extract the executed module inventory into
   `gate2-acceptance/module-inventory.txt` (e.g.
   `python -c "import re,sys;t=open(sys.argv[1],encoding='utf-8',errors='replace').read();print('\n'.join(sorted(set(re.findall(r'\((tests[.][\w.]+)[.]', t)))))" <log> > module-inventory.txt`).
   Then run the focused named suites:
   `python -m unittest tests.test_acceptance tests.hive_cortex.test_acceptance_harness tests.test_autonomy tests.test_policy_invariants -v > gate2-acceptance/focused-suite.log 2>&1`.
   Map every acceptance-matrix suite to modules present in the inventory; any
   suite with no covering module is a FAIL row (not a silent omission). Commit:
   `docs(qualify): record autonomy acceptance receipts`.
5. **Gate 3 — clean replay verification.** In a scratch directory (never inside
   the repo): `git worktree add <scratch>/q610-clean <candidate-sha>` — a clean,
   uncommitted-change-free tree. Inside it, verify:
   - `git status --porcelain` output is empty (record it);
   - tree identity: run `snapshot_tree` and record the digest:
     `python -c "from hive_mind_os.brain_kernel.verification import snapshot_tree; import json; s=snapshot_tree('src'); print(json.dumps({'root_digest': s.root_digest, 'file_count': len(s.files)}))" > .../gate3-replay/tree-snapshot.json` (run from the clean worktree with the same installed package);
   - retained Phase 12 assurance replay:
     `python -c "from hive_mind_os.brain_kernel.local_assurance import verify_local_assurance_artifact as v; import json; print(json.dumps(v('evidence/local_assurance/phase12-9efe64b/assurance.json','evidence/local_assurance/phase12-9efe64b/receipts.json'), default=str)[:2000])" > .../gate3-replay/assurance-verify.log 2>&1`
     — verify every `phase12-*` packet present under `evidence/local_assurance/`;
     a raised `LocalAssuranceError` is a gate FAIL;
   - focused replay suites:
     `python -m unittest tests.test_brain_kernel_verification tests.test_brain_kernel_local_assurance_artifact tests.test_brain_kernel_local_assurance_evidence tests.test_kernel -v > .../gate3-replay/replay-focused.log 2>&1`.
   Remove the worktree afterwards (`git worktree remove <scratch>/q610-clean`).
   Commit: `docs(qualify): record clean replay receipts`.
6. **Gate 4 — cross-platform qualification.** Record host identity to
   `gate4-platform/host-platform.txt`. The host row (Windows + its Python) is
   already covered by the Gate 1b log; symlink nothing — reference the Gate 1b log
   by path. For each ADDITIONAL locally installed interpreter from the CI matrix
   (`py -3.11`, `py -3.12`, `py -3.14` on Windows; `python3.X` elsewhere), run
   `<interpreter> -m unittest discover -s tests -v > gate4-platform/pyXY.log 2>&1`
   **while still holding no new claim to repo-wide runs beyond this gate** — these
   runs are part of the same qualification and must happen inside the Gate 1b
   lease window if performed; otherwise mark the matrix cell `DEFERRED` to CI.
   Never `pip install` interpreters or packages. Every matrix cell
   (ubuntu×{3.11,3.12,3.14}, windows×3.12) gets an explicit `PASS`/`DEFERRED` row.
   Commit: `docs(qualify): record cross-platform receipts`.
7. **Write the report + verdict.** Fill `docs/execution/HIVE_CORTEX_QUALIFICATION.md`
   per section 3.1, and `receipts.json` / `verdict.json` per 3.2, with real digests
   and exit codes. Commit: `docs(qualify): issue local qualification verdict`.
8. **Close out.** Push `autopilot/qualify-610`, open a DRAFT PR to `main`, produce
   the node completion receipt per the rendered prompt (base/final commit + tree
   ids, changed-path inventory — which must show ONLY the two write-scope
   surfaces —, command receipts, role/authority identities, rollback reference:
   `git revert <final-commit>`). Stop. Do not merge; do not start LEGACY-620.

## 5. Test plan — required_tests mapping

This node's write scope contains no `tests/**`, so the four required test names map
to executed commands over EXISTING suites, not to new test files:

| required_tests name | Concrete backing | Exact command |
|---|---|---|
| `full-constitutional-ci` | local reproduction of `.github/workflows/ci.yml` deterministic jobs incl. `tests.test_ci_contract.CIContractTests`; GitHub-only jobs listed as DEFERRED residuals | `python -m compileall -q src tests` then leased `python -m unittest discover -s tests -v` (step 3); optional `ruff check src tests` |
| `complete-autonomy-acceptance` | acceptance-matrix suite checklist backed by the discovery log + focused `tests.test_acceptance.AcceptanceSpecificationTests`, `tests.hive_cortex.test_acceptance_harness.AcceptanceHarnessTests`, `tests.test_autonomy.AutonomyTests`, `tests.test_policy_invariants.PolicyInvariantTests` | `python -m unittest tests.test_acceptance tests.hive_cortex.test_acceptance_harness tests.test_autonomy tests.test_policy_invariants -v` |
| `clean-replay-verification` | fresh-worktree verification: `verify_local_assurance_artifact` over every retained `evidence/local_assurance/phase12-*` packet, `snapshot_tree` identity, plus `tests.test_brain_kernel_verification.ExactCandidateVerificationTests`, `tests.test_brain_kernel_local_assurance_artifact.LocalAssuranceArtifactTests`, `tests.test_brain_kernel_local_assurance_evidence.LocalAssuranceEvidenceTests`, `tests.test_kernel.KernelTests` | `python -m unittest tests.test_brain_kernel_verification tests.test_brain_kernel_local_assurance_artifact tests.test_brain_kernel_local_assurance_evidence tests.test_kernel -v` (in the clean worktree) |
| `cross-platform-qualification` | per-interpreter matrix runs inside the lease window; unavailable cells DEFERRED to the CI matrix on the draft PR; `tests.test_ci_contract.CIContractTests.test_workflow_exercises_windows_with_python_3_12` guards the contract | `<interpreter> -m unittest discover -s tests -v` per available interpreter |

Edge cases the procedure must handle honestly: missing ruff/pyright (DEFERRED, no
installs); a retained assurance packet raising `LocalAssuranceError` (gate FAIL +
escalate — evidence may not be rewritten); non-empty `git status` in the worktree
(abort Gate 3, investigate contamination); lease already held (follow README
recovery: read `.autopilot/state/global-validation-lease.json`, release with the
exact recorded identity — never delete the file); any FAIL → verdict
`NOT QUALIFIED`, receipts still committed.

## 6. Acceptance self-check

| Acceptance criterion | How met | Receipt evidence |
|---|---|---|
| All required CI and adversarial suites pass on exact candidate | Gate 1b leased full run + Gate 2 focused run, all executed at the pinned commit with a clean tree | `gate1-ci/unittest-full.log`, `gate2-acceptance/*.log`, exit codes + sha256 in `receipts.json`, commit/tree ids in header |
| All eight roles have meaningful end-to-end receipts | Role inventory section maps each of the eight roles to passing `tests/test_hive_cortex_<role>.py` runs in the full log + retained evidence paths | report section 4 + `module-inventory.txt` |
| Humanless / no-cheating / learning / self-healing / durability / repository-safety gates pass | Acceptance-matrix checklist row per suite, each bound to named passing modules; empty coverage = FAIL row | report section 3 + `verdict.json` |
| Residual blockers and maturity labels explicit | Mandatory verdict template with minimum residual rows (a)–(e); `release_ready`/`production_ready`/`comparative_claim_authorized` all pinned `false` | report section 5 + `verdict.json` |

## 7. Out-of-scope traps — do NOT

- Do not modify anything under `src/**`, `tests/**`, `benchmarks/**`, `.github/**`,
  `.autopilot/**` (files), `pyproject.toml`, any `__init__.py` or `conftest.py`, or
  any other `docs/**` file besides `docs/execution/HIVE_CORTEX_QUALIFICATION.md`.
- Do not touch `evidence/courts/**`, `evidence/local_assurance/**`,
  `evidence/autopilot/**`, or any evidence outside
  `evidence/qualification/hive-cortex/**`; never rewrite or "fix" retained
  receipts — a broken retained receipt is a FAIL finding, not an edit target.
- Do not fix bugs you find. A failing suite is recorded as FAIL + residual blocker;
  repairs belong to the owning node's repair flow.
- Do not run `python -m unittest discover` outside the validation-lease window, and
  never leave the lease held (release even after failure).
- Do not `pip install` tools, providers, or interpreters; do not call remote
  providers or GitHub APIs; no network effects. DEFERRED is the honest outcome for
  anything requiring them.
- Do not claim superiority, release-readiness, A3/A4/A5 maturity, or "production"
  anything — retained packets pin `comparative_claim_authorized: false`.
- Do not touch the release branch, rebase/squash/amend `autopilot/qualify-610`,
  merge the PR, or begin LEGACY-620.
- Do not copy deep benchmark attempt trees into evidence (Windows path-length
  regression, see commit `a3261ca`); logs and JSON summaries only.
- Do not re-read `.autopilot/plan.json` or policy files; the rendered prompt plus
  this runbook is the complete contract.
