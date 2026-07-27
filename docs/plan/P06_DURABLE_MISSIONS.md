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
