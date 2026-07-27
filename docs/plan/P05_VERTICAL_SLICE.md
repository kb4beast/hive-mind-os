# P05 — End-to-End Vertical Slice: Objective → Verified Delivery Artifact

Status: tracked in `00_OVERVIEW.md` | Depends on: P02, P03, P04 | Unlocks: P06, P07, P08, P10, P13

## 1. Objective

Wire the model backend, sandbox, and Git adapter into the kernel lifecycle so that a single
command takes a repository objective ("fix the failing test") through all eight roles and
produces a reversible, fully receipted delivery artifact — with the Curator independently
re-verifying in a clean workspace — working end-to-end offline with a scripted backend (CI)
and with a real model behind a flag. This is the project's first real capability milestone:
after P05, Hive Mind OS has actually done the thing all its governance describes.

## 2. Rationale

Every architecture document defines done as: isolated implementation, executable tests,
independent verification, receipts, rollback. P02–P04 built the parts; this phase proves
the composition. It is deliberately minimal in intelligence (the fixture bug is simple; the
scripted backend applies a known-good patch) because the point is to validate the
*contracts and evidence chain* under real execution, not to demonstrate model cleverness.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/runtime.py` (kernel flow, `_validate_result`)
3. `src/hive_mind_os/model_backend.py` (P02) and `src/hive_mind_os/sandbox.py` (P03)
4. `src/hive_mind_os/git_adapter.py` and `tests/fixtures/fixture_repo.py` (P04)
5. `src/hive_mind_os/policy.py`, `src/hive_mind_os/autonomy.py` (budgets),
   `src/hive_mind_os/ledger.py`
6. `AGENTS.md` § "Full-autonomy definition of done"
7. `docs/architecture/HARDENED_VISION_CONTRACT.md` § "End-to-end definition of done"

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_model_backend.py tests/test_sandbox.py tests/test_git_adapter.py   # all pass
```

## 5. Scope

In scope:

- A `RepositoryMission` orchestration layer that gives roles real capabilities scoped to
  their contracts, over one local fixture repository.
- Builder workspace and Curator workspace as *separate* materializations.
- A `ScriptedRepositoryBackend` for deterministic offline E2E.
- CLI `hive-mind deliver`.
- A machine-readable `MissionReport` extending `RunReport` with artifact and receipt
  references.

Non-goals:

- No remote repositories, no PR (P07). No persistence/resume (P06). No parallel roles, no
  scheduler (P11). No prompt sophistication or repository intelligence — the Explorer's
  job on the fixture is only to locate the failing test via `run_tests` evidence. No
  Curator blind test authoring (P08 deepens independence; P05 establishes the workspace
  and identity separation).

## 6. Design constraints

- **Policy level.** Repository missions construct their `PolicyEngine` at
  `AutonomyLevel.REPOSITORY` — that is what A3 means, and `Action.CREATE_BRANCH`
  requires it (`policy.py` maps it to `RequiredLevel.REPOSITORY`; the default `SANDBOX`
  engine would deny the Builder's branch). Merge/deploy/secrets remain denied at every
  level (`EXTERNAL_GRANT_ACTIONS`). The mission takes the engine as a parameter so the
  policy-ceiling test can pass a lower level.
- **Role capability wiring.** Roles receive capability objects, not ambient access:
  Explorer gets read-only workspace + `run_tests`; Architect gets read-only + the
  Explorer's evidence; Builder gets a branch workspace (`create_branch`, `write_file`,
  `run_tests`, `commit`); Curator gets a *fresh* materialization of the Builder's head
  (via bundle application), `run_tests`, and `verify_delivery` — and must not receive the
  Builder's receipts or rationale as inputs (independence at the data-flow level; the
  mission code enforces what context each role's backend call sees).
- **Two backends, one shape.** `ScriptedRepositoryBackend` implements `AgentBackend`
  offline: for Builder it applies a fixture-provided patch (the known fix shipped next to
  the fixture); for other roles it emits contract-satisfying turns derived from actual
  capability outputs (e.g. Explorer's evidence embeds the real failing-test receipt
  digest). `ModelBackend` does the same via real model turns whose `proposed_actions`
  are executed through the same capability objects. Receipt *shapes* must be identical
  across backends — only content differs.
- **Evidence chain.** The mission appends ledger events for: mission start, each role's
  policy decisions, every sandbox/git receipt reference, Curator verdict, artifact
  export, mission end. `MissionReport` carries: objective, base SHA, branch, head SHA,
  tree digest, artifact directory, the list of receipt references, Curator verdict, and
  budget consumption. Everything a later auditor needs to replay the story is reachable
  from the report.
- **Fail-closed paths are first-class.** Curator re-run failure → mission status
  `FAILED`, no delivery artifact exported (or the exported artifact is marked
  quarantined — choose: do not export; record why in the ledger). Policy denial and
  budget exhaustion likewise end the mission with recorded state and no artifact.
- **Determinism in CI.** The scripted E2E must produce byte-identical tree digests and a
  stable set of ledger event types across runs (timestamps/uuids vary; assert on
  structure, not volatile values).
- **CLI.** `hive-mind deliver --repository <local-path> --objective "…" --criterion "…"
  [--backend scripted|model] [--pin <sha>] [--output-dir <dir>]`. Note: `cli.py`
  dispatches on `arguments[0]`; add `deliver` to the same dispatch table as `audit`
  (before the legacy goal-positional parse) without breaking existing invocations.

## 7. Deliverables

New files:

- `src/hive_mind_os/mission.py` — `RepositoryMission`, `MissionReport`, role capability
  objects (`ExplorerCapabilities`, `BuilderCapabilities`, `CuratorCapabilities`, …),
  `ScriptedRepositoryBackend`.
- `tests/fixtures/fixture_fix.patch` (or a function in `fixture_repo.py` returning the
  fix) — the known-good patch for the fixture bug.
- `tests/test_mission.py`.

Modified files:

- `src/hive_mind_os/cli.py` — `deliver` subcommand.
- `README.md` — replace the aspirational "Run the bootstrap kernel" example with the real
  `deliver` example against the fixture (additive: keep the old example, add the new).

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P05-vertical-slice`.
2. Implement capability objects wrapping P03/P04 with per-role policy checks and a shared
   `EpisodeAllowance` budget stream.
3. Implement `RepositoryMission.run()` walking `DEFAULT_LIFECYCLE`, constructing each
   role's context per the independence rules, and threading receipts into the ledger.
4. Implement `ScriptedRepositoryBackend` and get the offline E2E green: mission on the
   fixture at HEAD (failing test) → Builder branch applies fix → Curator fresh workspace
   re-runs tests green → `verify_delivery` passes → artifact exported → report complete.
5. Add failure-path tests (sabotaged patch, policy denial, budget exhaustion).
6. Wire `ModelBackend` through the same path; verify manually with
   `scripts/smoke_model.py`-style run if credentials exist (record outcome; not CI).
7. Add the `deliver` CLI; test the CLI offline path.
8. Gates, audit `evidence/audits/P05-post.json`, status updates, completion record.

## 9. Required tests

`tests/test_mission.py`:

1. **Golden path (scripted):** mission succeeds; artifact directory contains
   `changes.bundle`, `changes.patch`, `delivery.json`; Curator verdict is positive;
   `MissionReport.receipts` all resolve through `FileReceiptValidator`.
2. **Independence:** Curator's workspace path ≠ Builder's; ledger shows a fresh
   materialization; the context passed to the Curator's backend call contains no Builder
   receipt digests or rationale strings (assert on the recorded context manifest).
3. **Curator catches a bad fix:** replace the fixture fix with a patch that makes the
   Builder's own test run pass but leaves the real bug (fixture provides this sabotage
   variant — e.g. it edits the test instead of the code); Curator re-run fails → mission
   `FAILED`, no artifact exported, ledger records the divergence. (This is the
   test-weakening detection scenario from the vision contract's hard failure list.)
4. **Policy ceiling:** engine at `AutonomyLevel.ADVISE` → Builder's first workspace write
   is denied; mission fails closed with the denial recorded.
5. **Budget exhaustion:** a tight budget stops the mission mid-lifecycle; recorded state
   names the exhausted allowance; no artifact.
6. **Determinism:** two scripted runs → identical head tree digests and identical ordered
   list of ledger event types.
7. **Kernel invariants intact:** every role's `AgentResult` still satisfies
   `HiveKernel._validate_result`-equivalent checks (mission reuses or mirrors the same
   validation — do not fork looser rules).
8. **CLI:** `hive-mind deliver --repository <fixture> --backend scripted …` exits 0 on
   the golden path and non-zero on the sabotage path.

## 10. Exit criteria

```bash
python -m pytest -q tests/test_mission.py     # all pass
python -m pytest -q                           # full suite passes
python -m ruff check src tests && pyright     # clean
# CLI golden path, run twice, offline:
python - <<'EOF'
import subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, "src"); sys.path.insert(0, "tests")
from fixtures.fixture_repo import build_fixture_repo
for _ in range(2):
    with tempfile.TemporaryDirectory() as td:
        repo = build_fixture_repo(Path(td) / "repo")
        out = subprocess.run([sys.executable, "-m", "hive_mind_os.cli", "deliver",
                              "--repository", str(repo.path), "--backend", "scripted",
                              "--objective", "Fix the failing test",
                              "--output-dir", str(Path(td) / "artifact")],
                             capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
print("deliver golden path: ok twice")
EOF
```

(Adjust the snippet to the fixture module's real API when implementing; the committed
version of this check lives in the test suite — the inline form here is the manual
confirmation.)

## 11. Evidence

- `evidence/audits/P05-post.json` committed.
- One full `MissionReport` JSON (volatile fields normalized) committed under
  `tests/fixtures/mission/golden_report.json` and asserted against in tests
  (structure, not volatile values).
- Completion record states whether the real-model path was exercised and with what
  provider/model.

## 12. Rollback

Revert the branch. The kernel, backends, sandbox, and git adapter remain independently
usable; nothing outside this phase imports `mission.py` yet.

## 13. Handoff

Later phases may assume: a working `deliver` pipeline over local repositories; separate
Builder/Curator workspaces with data-flow independence; `MissionReport` as the complete
evidence index; scripted and model backends interchangeable behind one flag; failure
paths (bad fix, policy, budget) fail closed with recorded state.

## 14. Forbidden shortcuts

- Do not let the Curator "verify" by reading Builder outputs instead of re-executing.
- Do not export artifacts on any failed path.
- Do not special-case the fixture inside mission code (fixture knowledge lives only in
  the scripted backend and test fixtures; `RepositoryMission` must be repository-agnostic).
- Do not weaken kernel result validation to fit mission wiring.

---
## Completion record
- Date (UTC): 2026-07-27
- Executor (model/agent identity): Codex (GPT-5)
- Branch and implementation commit SHA: `phase/P05-vertical-slice` at
  `dc41483384b7654f450fbc413aa17f51ef31a4fa`
- Gates: P05 tests 10 passed; full pytest 196 passed, 2 skipped, 1,718 subtests;
  Ruff passed; Pyright passed with 0 errors; offline CLI golden path passed twice
- Audit artifact: `evidence/audits/P05-post.json`
  (digest: `sha256:96bf4b4fac5b3c56af53abda62851fca53a0f72dfa1bb5f7e95bc6dde4c1a8b4`;
  complete: true; failures: none)
- Real-model path: not exercised against a network provider because neither a model ID nor
  provider credential was configured. The actual `ModelBackend` path was exercised offline
  with a deterministic fake provider through the same capability executor.
- Deviations from the phase spec:
  - Added ADR-009 and the narrow policy change permitting sandbox-level Explorer command
    execution while retaining every Explorer mutation denial. This was required to make
    the specified read-only failing-test reproduction reachable.
  - Extended `verify_delivery` with optional Curator identity, allowance, evidence-root,
    and receipt-sink parameters so all internal verification commands remain reachable
    from `MissionReport`; existing P04 callers retain their prior defaults.
  - Used `fixture_repo.fixture_fix()` and scripted-backend fixture bytes instead of a
    standalone patch file.
- New blockers discovered (mirrored into `docs/plan/BLOCKERS.md`): none. Existing P07,
  P08, P09, P12, and B-OPS-06 obligations remain open and are not reclassified here.
- Capability boundary: this closes the P05 local/offline vertical-slice exit criteria only.
  It does not establish production readiness, hostile-code isolation, external delivery,
  authenticated identity, resolved source licensing, or superiority.

---
## Consolidated-review appeal record

- Date (UTC): 2026-07-27
- Challenged candidate:
  `f6cc1cc9947b526b1656eed7e71da321cde26c54`
- Independent challenged-candidate dispositions:
  - Curator: `block`
  - Judge: `adapt`
  - Orchestrator: `block`
- Preserved dissent and reproduced counterexamples:
  - A deterministic model provider substituted passing no-op commands after Explorer
    reproduced the real failure, causing the challenged candidate to publish an unfixed
    repository.
  - Eight `model.call` events were outside the report correlation.
  - A Git operation emitted successful and failed receipts before raising, but the
    challenged report omitted both receipts and their budget usage.
  - Failed reports returned receipt references after their temporary backing bytes had
    been deleted.
- Repair implementation: `a5bdb333cbcd04df106e39fcee66c9ea9d5c25f1`
  (`docs/architecture/ADR-010-P05-VERIFICATION-AND-FAILURE-EVIDENCE.md`).
- Repair evidence:
  - Builder and Curator test execution is sealed to the exact Explorer
    failure-reproducing argument vector; adversarial substitution fails closed.
  - The mission objective, report, model backend, and ledger share one correlation.
  - Exceptional Git calls settle actual receipts and budget usage before propagating the
    original failure.
  - Failed-run receipt bytes and the failed report are retained in a separate evidence
    directory; the requested delivery output remains absent.
- Gates on the repair implementation: P05 tests 12 passed; full pytest 198 passed,
  2 skipped, 1,718 subtests; Ruff passed; Pyright passed with 0 errors; offline CLI
  golden and sabotage paths passed twice.
- Additive audit artifact: `evidence/audits/P05-repair-post.json`
  (canonical digest:
  `sha256:c70f34b01c4b5213b996045bb750156dbec966e0adf2edf34ac38e925b988d16`;
  complete: true; failures: none; audited implementation commit:
  `a5bdb333cbcd04df106e39fcee66c9ea9d5c25f1`).
- Final delivery eligibility remains pending one consolidated independent review of the
  complete repaired candidate and exact-head GitHub checks.
- The original completion record is retained as point-in-time evidence; this appeal
  record supersedes its delivery-eligibility implication, not its historical receipts.
- Existing P06, P07, P08, P09, P12, and B-OPS-06 obligations remain open. This appeal
  makes no production-readiness, source-completeness, hostile-isolation, external-delivery,
  or superiority claim.

---
## Consolidated-review appeal record 2

- Date (UTC): 2026-07-27
- Challenged repaired candidate:
  `b8a1d418664fd7226e29ca76cb4e592f388ba66b`
- Independent dispositions:
  - Curator: `permit`
  - Judge: `adapt`
  - Orchestrator: `permit`
- Preserved dissent: the Curator and Orchestrator found the four first-appeal blockers
  closed and would have delivered. The Judge additionally exercised a split-budget API
  construction that they did not reproduce, and the fail-closed rule controlled.
- Reproduced counterexample: a `ModelBackend` with its own budget and a
  `RepositoryMission` limited to 45 calls completed 53 actual calls—45 Git/sandbox calls
  plus eight model calls—while the report claimed only the mission's 45. A zero-call
  mission could likewise allow a model request before workspace enforcement.
- Repair implementation: `94a7e5ecc9b79ba6efe956deb34da7d67a741498`.
  `RepositoryMission` now binds a model backend to the same autonomy budget just as it
  binds the ledger. The regression constructs distinct budgets and proves that the
  45-call envelope fails closed, all observed model calls remain correlated, reported
  consumption never exceeds the limit, and total reported calls equal model events plus
  capability receipts.
- Gates on the budget repair implementation: P05 tests 13 passed; full pytest 199 passed,
  2 skipped, 1,718 subtests; Ruff passed; Pyright passed with 0 errors.
- Additive audit artifact: `evidence/audits/P05-budget-repair-post.json`
  (canonical digest:
  `sha256:bed4356708a1a3727603eedeeae1e55058d836dc24db95a92ca78b198566609e`;
  complete: true; failures: none; audited implementation commit:
  `94a7e5ecc9b79ba6efe956deb34da7d67a741498`).
- Delivery remains pending exact-head CI and one final consolidated independent review of
  this complete challenger. No earlier permit is carried forward.
- Existing P06, P07, P08, P09, P11, P12, and B-OPS-06 obligations remain open. This
  appeal makes no production-readiness, source-completeness, hostile-isolation,
  external-delivery, or superiority claim.
