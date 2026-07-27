# P06 — Durable Mission State, Checkpoints, and Resume

Status: tracked in `00_OVERVIEW.md` | Depends on: P05 | Unlocks: P07 (recommended), P11

## 1. Objective

Make missions survive interruption: persist mission state and per-step checkpoints to
SQLite, give every side-effecting step an idempotency key derived from its canonical intent
digest, and implement `hive-mind resume <mission-id>` so a mission killed at any point
completes without a human restating anything and without duplicating any side effect.

## 2. Rationale

"Routine work is designed to recover and resume without repeated human prompting" is core
guarantee 13 in the README, and the vision contract's autonomous-work target forbids
restating objectives after a restart. P05 produced missions that fail closed but lose their
progress. This phase adds the durable spine that P11's scheduler and workers will later
build on. Reusing `contracts.tool_intent_digest` as the idempotency key means the dedup
mechanism is exactly the digest the receipts already bind — one identity for "what was
about to happen" across enforcement, evidence, and recovery.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/mission.py` (P05 — the step structure you will checkpoint)
3. `src/hive_mind_os/ledger.py` (SQLite conventions already in use)
4. `src/hive_mind_os/contracts.py` (`tool_intent_digest`)
5. `src/hive_mind_os/schemas/mission-state.schema.json` and
   `src/hive_mind_os/schemas/handoff.schema.json` (existing durable-state contracts —
   the store's serialized state must validate against `mission-state` where the fields
   correspond; if a needed field is missing, STOP and handle per the constitutional-change
   rule)
6. `docs/architecture/CONGLOMERATED_SYSTEM.md` § "Control plane" (idempotency, recovery)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_mission.py    # P05 green
python - <<'EOF'
import sys; sys.path.insert(0, "src")
from hive_mind_os.contracts import load_schema
load_schema("mission-state"); load_schema("handoff"); print("ok")
EOF
```

## 5. Scope

In scope:

- `MissionStore` (SQLite) with mission records, step checkpoints, and an idempotency
  table.
- Checkpoint/restore integration in `RepositoryMission`.
- Workspace reconciliation on resume (recorded digests vs. disk reality).
- CLI `resume` and `missions` (list) subcommands.

Non-goals:

- No scheduler, queue, leases, or heartbeats (P11). No multi-process concurrency — P06
  guarantees single-writer correctness and leaves contention to P11's leases. No remote
  side effects (P07 will extend idempotency to push/PR using this same table).

## 6. Design constraints

- **Same SQLite discipline as the ledger.** WAL not required; follow `ledger.py`'s
  connection and schema-creation style. Store file lives next to the ledger file, path
  supplied by the caller/CLI (`--state-dir`).
- **Checkpoint before and after side effects.** A step is recorded `intent` (with its
  canonical digest) before execution and `completed` (with receipt reference) after. On
  resume, a step found in `intent` state is re-examined: if a matching receipt exists in
  the receipt store for that digest, adopt it and mark completed (the effect happened);
  if not, the step re-executes. This is exactly-once *effect adoption*, not exactly-once
  execution — state the distinction in the module docstring.
- **Idempotency keys.** Key = `tool_intent_digest` of the full intent. The store's
  idempotency table maps digest → receipt reference, unique-constrained. A second
  execution attempt for an already-satisfied digest is a no-op returning the recorded
  receipt.
- **Workspace reconciliation.** Resume verifies: base SHA of the materialized workspace,
  current branch head tree digest vs. the last checkpoint's recorded digest. Mismatch →
  fail closed with status `BLOCKED` and a reconciliation report (never silently rebuild;
  a later human or agent decision handles divergence). Exception: a missing workspace
  directory is rebuildable deterministically (re-materialize + re-apply adopted
  receipts' committed state via the recorded branch), because nothing external depended
  on the lost sandbox.
- **Serialization contract.** Persisted mission state serializes losslessly and, where the
  schema's fields apply, validates against `mission-state`. Store schema version is
  recorded in the DB; an unknown version fails closed.
- **No clock/uuid coupling.** Resume must not depend on wall-clock ordering; step
  identity is (mission_id, step_index, intent digest).

## 7. Deliverables

New files:

- `src/hive_mind_os/mission_store.py` — `MissionStore`, `StepCheckpoint`,
  `ReconciliationError`, `resume_mission()` entry point.
- `tests/test_mission_store.py`.

Modified files:

- `src/hive_mind_os/mission.py` — accept an optional `MissionStore`; emit checkpoints at
  every step boundary; route side-effecting capability calls through the idempotency
  check.
- `src/hive_mind_os/cli.py` — `resume <mission-id> [--state-dir …]` and
  `missions [--state-dir …]` subcommands.

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P06-durable-missions`.
2. Implement `MissionStore` with its three tables and version stamp; unit-test CRUD and
   the idempotency unique constraint in isolation.
3. Thread checkpointing through `RepositoryMission` (keep the no-store path working —
   P05 tests must pass unmodified).
4. Implement resume: load mission, reconcile workspace, adopt satisfied intents, continue
   the lifecycle from the first incomplete step.
5. Implement the crash-injection test harness: run the scripted mission in-process with a
   monkeypatched capability layer that raises `SimulatedCrash` after step N's side effect
   but before its `completed` checkpoint; then resume and assert completion.
6. CLI subcommands.
7. Gates, audit `evidence/audits/P06-post.json`, status updates, completion record.

## 9. Required tests

`tests/test_mission_store.py`:

1. **Kill-at-every-boundary sweep:** parametrize over every step boundary of the scripted
   fixture mission (before intent, after intent/before effect, after effect/before
   completed); resume completes the mission successfully in each case.
2. **No duplicate side effects:** across every sweep case, each intent digest has exactly
   one receipt (assert count in receipt store and idempotency table).
3. **Effect adoption:** the after-effect/before-completed case adopts the existing
   receipt rather than re-executing (assert the capability layer's execution count).
4. **Workspace drift:** mutate the Builder workspace between crash and resume → resume
   fails closed with `ReconciliationError`, mission status `BLOCKED`, report names the
   digest mismatch.
5. **Lost workspace rebuild:** delete the workspace directory entirely → resume
   re-materializes and completes.
6. **Tamper:** edit a checkpoint row's recorded digest directly in SQLite → resume fails
   closed (fail-closed on inconsistent store).
7. **Store versioning:** bump the stored version stamp → open fails closed with a clear
   error.
8. **State validates:** persisted mission state round-trips and, where applicable,
   passes `validate_contract("mission-state", …)`.
9. **CLI:** `hive-mind missions` lists the interrupted mission; `hive-mind resume <id>`
   exits 0 and completes it (scripted backend, offline).
10. **P05 regression:** the entire `tests/test_mission.py` suite passes unchanged with no
    store attached.

## 10. Exit criteria

```bash
python -m pytest -q tests/test_mission_store.py tests/test_mission.py   # all pass
python -m pytest -q && python -m ruff check src tests && pyright        # clean
```

Manual confirmation (record output in completion record): run the scripted `deliver` with
`--state-dir`, `kill -9` (or Windows `taskkill /F`) the process mid-run, then
`hive-mind resume <id>` and verify completion with a single receipt per intent digest.

## 11. Evidence

- `evidence/audits/P06-post.json` committed.
- The kill-sweep test's summary (boundary count × completion) quoted in the completion
  record.

## 12. Rollback

Revert the branch; `mission.py` keeps its optional-store seam so removal is a clean
subtraction. Existing mission-state schema files are untouched.

## 13. Handoff

Later phases may assume: missions are resumable at any boundary; intent digest =
idempotency key = receipt binding; workspace divergence blocks rather than guesses; P07
can register push/PR intents in the same idempotency table; P11 can drive many missions
through `MissionStore` without inventing new state.

## 14. Forbidden shortcuts

- No "resume by re-running from scratch and hoping effects are idempotent" — adoption is
  explicit, from receipts.
- No silent workspace rebuild when recorded digests mismatch disk.
- No timestamps as ordering keys.
- Do not weaken or fork P05's mission validation to accommodate persistence.

---
## Completion record

- Date (UTC): 2026-07-27T21:53:48Z
- Executor (model/agent identity): Codex primary Builder/Integrator; independent Curator,
  Judge, and Orchestrator review remains required on the complete exact-SHA pull-request
  candidate.
- Branch and audited implementation commit: `phase/P06-durable-missions`;
  `a136af13a9ed7fd595329bbeffa3ad2a9507d6a0`.
- Gates: P06 tests 62 passed, including 54/54 injected crash boundaries; audit full pytest
  263 passed, 2 skipped, 1,718 subtests; Ruff passed; Pyright passed with 0 errors.
- Audit artifact: `evidence/audits/P06-post.json`
  (canonical digest:
  `sha256:d56d0efad6e672270e8287829de4a8a9e4f6c484e4dcc33bb6ea199b2882ed1f`;
  complete: true; failures: none; audited implementation commit:
  `a136af13a9ed7fd595329bbeffa3ad2a9507d6a0`).
- Preserved challenged audit: `evidence/audits/P06-post-timeout.json`
  (complete: false; its Python 3.12 pytest command returned 124 at the former 300-second
  ceiling). ADR-011 records the reproduced counterexample and the 1,200-second repair.
- Manual hard-kill confirmation: Windows terminated the real scripted `deliver` process
  during Explorer materialization. The first resume reproduced an uncheckpointed partial
  workspace failure. After the repair, the same durable mission resumed successfully with
  18 completed checkpoints, 18 idempotency records, and zero duplicate intent digests.
- Workspace and state evidence: digest drift blocks with a reconciliation report; missing
  recorded workspaces and uncheckpointed partial materializations rebuild; checkpoint
  digest tamper and unknown store versions fail closed; serialized state validates against
  `mission-state`.
- Deviations from the phase spec:
  - Shortened private durable candidate staging and the Git adapter's private staging
    prefix after a reproduced Windows `MAX_PATH` failure while copying content-addressed
    evidence. Artifact names and delivery contracts are unchanged.
  - Increased the current-state audit command timeout from 300 to 1,200 seconds after the
    required recovery suite reproducibly exceeded the former ceiling. Timeout failure,
    process-tree termination, output caps, and result recognition remain fail closed.
  - Added an uncheckpointed-partial-workspace regression after the real process kill
    reached a boundary not represented by the deterministic post-effect hook.
- New blockers discovered (mirrored into `docs/plan/BLOCKERS.md`): none. Existing P07,
  P08, P11, P12, and B-OPS-06 obligations remain open.
- Capability boundary: P06 supplies single-writer local persistence and exactly-once
  effect adoption for the offline scripted repository mission. It does not establish
  exactly-once physical execution, durable live-provider replay, distributed scheduling,
  external GitHub delivery, authenticated identity, hostile-code isolation, production
  readiness, complete source coverage, or superiority.

### Consolidated-review appeal record

- The independent Curator blocked candidate
  `51d749f323a8bca1721c92d6a0a650afb8fa6e10` after reproducing a stop between a
  physical sandbox receipt and its synthetic checkpoint receipt. The same review found
  that GitHub's `unittest discover` jobs could not import the pytest-dependent P06 test
  module and that Gitleaks classified one synthetic idempotency fixture as a secret.
  ADR-011 preserves the findings, counterexample, repair rationale, and narrow
  operational-source receipt.
- Repaired implementation commit:
  `ca5742bbd6c842ab68db3165e7b3be3daca4272b`. It adopts or accounts validated
  unclaimed physical receipts, transactionally binds budget consumption to checkpoint
  completion, adds the missing `after_capability_effect` boundary, makes all P06 cases
  discoverable by stdlib `unittest`, and constrains the historical Gitleaks exception to
  one exact line while retaining default rules.
- Direct repaired-candidate gates: `python -m unittest discover -s tests -v` passed
  267 tests with 2 skips; `python -m pytest -q` passed 265 tests with 2 skips and 1,718
  subtests; Ruff passed; Pyright passed with 0 errors.
- Repair audit: `evidence/audits/P06-repair-post.json`
  (canonical digest:
  `sha256:8a5aa9280b8a4e0b1c9a40159139a6494eead5fd0f4f13fcb3da3a391b4ec703`;
  complete: true; failures: none; audited implementation commit:
  `ca5742bbd6c842ab68db3165e7b3be3daca4272b`; audit pytest: 265 passed).
- The challenged block remains preserved rather than overwritten. Delivery still
  requires green exact-head GitHub checks and a fresh sequential Curator, Judge, and
  Orchestrator disposition on the complete repaired candidate.
