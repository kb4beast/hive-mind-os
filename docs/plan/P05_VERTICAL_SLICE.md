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
