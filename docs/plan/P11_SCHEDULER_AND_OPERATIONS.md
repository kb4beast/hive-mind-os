# P11 — Durable Scheduler, Role Workers, and Mission-Control Projection

Status: tracked in `00_OVERVIEW.md` | Depends on: P06 | Unlocks: continuous unattended operation

## 1. Objective

Give Hive Mind OS continuous operation: a durable SQLite-backed job queue with leases,
heartbeats, retries, and dead-lettering; worker processes that claim role work and drive
missions through the P06 store; stale-worker detection and exactly-once effect adoption
under worker crash; and a read-only mission-control projection (`hive-mind status`, JSON
and static HTML) that renders ledger truth — including explicit `unknown`, `blocked`, and
`quarantined` states — without ever implying completion where evidence is missing.

## 2. Rationale

The control plane requires durable scheduling, leases, and recovery; the experience plane
requires a mission-control view that is "the operational projection of the ledger". P06
made a single mission resumable; this phase makes *operation* resumable: many missions,
crash-tolerant workers, no duplicated side effects, and a truthful window into what is
actually happening. This is the last piece of the "routine work continues without repeated
human prompting" guarantee at local scale.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `src/hive_mind_os/mission_store.py` (P06 — checkpoints, idempotency)
3. `src/hive_mind_os/mission.py`, `src/hive_mind_os/ledger.py`
4. `docs/architecture/CONGLOMERATED_SYSTEM.md` § "Control plane" and § "Experience
   plane" (the UI honesty requirement)
5. `docs/architecture/BOUNDED_EVOLUTION.md` § "Required next slices" items 1–2 (the
   durable-scheduler obligations this phase discharges)

## 4. Prerequisite verification

```bash
python -m pytest -q tests/test_mission_store.py    # P06 green
```

## 5. Scope

In scope:

- `scheduler.py`: jobs table (id, kind, payload, state, attempts, not_before), leases
  (owner, expiry), heartbeats, bounded retries with deterministic backoff, dead-letter
  state, enqueue/claim/complete/fail API — single SQLite file, multi-process safe.
- `workers.py`: a worker loop (claim → heartbeat thread/timer → execute via mission
  layer → complete/fail), worker identity, graceful shutdown, crash tolerance.
- CLI: `hive-mind serve --workers N --once|--forever`, `hive-mind enqueue …`,
  `hive-mind status [--json|--html <path>]`.
- Projection: per-mission and per-job state assembled *only* from ledger + stores.

Non-goals:

- No cron/webhook triggers (enqueue is manual/CLI for now). No distributed operation
  beyond one machine/one SQLite file. No event bus abstraction — the ledger remains the
  record; workers poll. No web server — the HTML is a static file written on demand. No
  parallel roles within one mission (missions stay sequential; parallelism is across
  missions).

## 6. Design constraints

- **Lease correctness over SQLite.** Claims use a single `UPDATE … WHERE state='ready'
  AND (lease_expiry IS NULL OR lease_expiry < :now) …` with `RETURNING` (or an
  IMMEDIATE transaction) so two workers cannot claim one job. `busy_timeout` set;
  WAL mode enabled for multi-process access. Times are injected via a `Clock` interface
  so tests control expiry deterministically (no sleeps in tests beyond minimal
  integration checks).
- **Heartbeats extend leases;** a worker that misses its heartbeat loses the lease at
  expiry and any competing claimer takes over. The old worker's late completion is
  rejected (lease token mismatch — completion requires the current token).
- **Exactly-once effects, at-least-once execution.** Reclaimed jobs re-enter the mission
  layer, where P06 idempotency adopts already-performed effects. A job is `done` only
  when its mission reports terminal success; `failed` missions retry up to
  `max_attempts` then dead-letter with the mission's recorded state referenced.
- **Crash tolerance is tested with real processes.** Integration tests spawn actual
  worker subprocesses against a tmp queue and kill them (`terminate`/`kill`) at
  randomized-but-seeded points; the suite remains deterministic via seeded choice of
  kill step and injected clock for lease expiry.
- **Projection honesty.** The status model derives, per mission: lifecycle stage evidence
  present/absent, blocked reasons, quarantine flags, last checkpoint, receipt counts.
  States rendered: `running`, `succeeded`, `failed`, `blocked`, `dead-letter`,
  `unknown` (ledger gap — e.g. store references a mission the ledger lacks). The HTML
  must render `unknown`/`blocked`/`quarantined` visibly; a missing-evidence mission must
  never display as complete. No JavaScript required; inline CSS; single self-contained
  file.
- **No new dependencies.** `sqlite3`, `subprocess`, `html` from stdlib.

## 7. Deliverables

New files:

- `src/hive_mind_os/scheduler.py` — queue, leases, retries, dead-letter, `Clock`.
- `src/hive_mind_os/workers.py` — worker loop and identity.
- `src/hive_mind_os/projection.py` — status model + JSON + static HTML renderer.
- `tests/test_scheduler.py`, `tests/test_workers.py`, `tests/test_projection.py`.

Modified files:

- `src/hive_mind_os/cli.py` — `serve`, `enqueue`, `status` subcommands.

## 8. Implementation steps

1. Verify prerequisites; branch `phase/P11-scheduler-operations`.
2. Implement the queue with injected clock; unit-test claim contention (two threads/
   processes racing on one ready job — exactly one wins) and lease expiry reclaim.
3. Implement retries/backoff/dead-letter; unit-test the attempt ladder.
4. Implement the worker loop with heartbeats and lease-token completion; wire to the
   scripted mission via `MissionStore`.
5. Process-level crash tests: seeded kill sweep over worker subprocesses; assert mission
   completion, single receipt per intent digest, no double-claims.
6. Implement the projection (JSON first, HTML from the same model); test honesty rules
   with constructed gap/blocked/quarantine cases.
7. CLI subcommands; a `--once` mode that drains the queue and exits (used by tests).
8. Gates; audit `evidence/audits/P11-post.json`; status updates; completion record.

## 9. Required tests

`tests/test_scheduler.py`:

1. Contended claim: exactly one winner; loser sees no job.
2. Lease expiry with injected clock: reclaim by a second worker; first worker's late
   completion rejected via stale token.
3. Heartbeat extends lease across the expiry boundary.
4. Retry ladder: fail → backoff schedule respected (clock-injected) → dead-letter at
   `max_attempts`, mission state referenced.
5. Enqueue idempotency: enqueueing the same mission payload digest twice is deduplicated
   (or explicitly versioned — choose and test one behavior).

`tests/test_workers.py`:

6. Seeded kill sweep (subprocess workers, ≥3 kill points): queue drains, mission
   completes, exactly one receipt per intent digest, no orphaned leases at exit.
7. Graceful shutdown finishes the in-flight step, checkpoints, and releases the lease.

`tests/test_projection.py`:

8. Ledger-gap mission renders `unknown` (never `succeeded`).
9. Blocked mission (P06 reconciliation case) renders `blocked` with reason text.
10. Dead-letter job renders with its mission's recorded failure.
11. HTML output contains all states present in the model (string-level assertions) and
    is a single self-contained file.
12. JSON projection round-trips (`status --json` parses; fields documented in the module
    docstring are all present).

## 10. Exit criteria

```bash
python -m pytest -q tests/test_scheduler.py tests/test_workers.py tests/test_projection.py   # pass
python -m pytest -q && python -m ruff check src tests && pyright                             # clean
# Offline operational check:
hive-mind enqueue --repository <fixture-path> --backend scripted --objective "Fix the failing test" --state-dir /tmp/hmq
hive-mind serve --workers 2 --once --state-dir /tmp/hmq        # exits 0 after draining
hive-mind status --state-dir /tmp/hmq --json                   # shows the mission succeeded with receipts
hive-mind status --state-dir /tmp/hmq --html /tmp/status.html  # writes the honest static page
```

## 11. Evidence

- `evidence/audits/P11-post.json` committed.
- One generated status HTML (from the fixture run, volatile fields normalized) under
  `tests/fixtures/projection/` as a golden file.

## 12. Rollback

Revert the branch. Queue/state files are user data under `--state-dir`; the mission layer
remains fully usable without the scheduler.

## 13. Handoff

Later phases may assume: multi-mission unattended operation on one machine with crash
tolerance and exactly-once effects; a truthful status projection consumable as JSON or
HTML; enqueue/serve/status as the operational surface that triggers (cron, webhooks) can
later target.

## 14. Forbidden shortcuts

- No sleep-based lease logic in tests; the clock is injected.
- No completion without a valid lease token.
- No projection state derived from anything but ledger + stores (no worker "I think it's
  fine" self-reports).
- No UI state that renders missing evidence as success — this is a constitutional UI
  requirement, test it.

---

## Completion record

- Date (UTC): 2026-07-28T12:58:16Z
- Executor (model/agent identity): Codex primary Builder/Integrator. Per the user's
  consolidated-review instruction, independent Curator, Judge, and Orchestrator review
  is reserved for the final all-merged boundary; this record is not self-approval.
- Branch and audited implementation commit: `phase/P11-scheduler-operations`;
  `d12713480840474eb6021d4a56377980e8116d11`. The audit was collected from that clean
  commit; the pull-request head contains the append-only audit/status follow-up.
- Gates: P11 exit tests passed (14); full pytest passed (348 passed, 2 pre-existing
  skips, 1,744 subtests); Ruff 0.16.0 passed; Pyright 1.1.411 passed with 0 errors.
- Offline operational check: a fixture regression was enqueued, drained by two workers,
  completed all eight roles, retained 45 receipt events, rendered `succeeded` in parsed
  JSON, and produced a self-contained static HTML status page.
- Reproduced repair: the first offline run exposed Windows path-budget exhaustion during
  durable publication. Mission identifiers and scheduler delivery paths are now bounded;
  the real durable-worker regression test reproduces successful publication and unique
  adopted effect digests.
- Audit artifact: `evidence/audits/P11-post.json`
  (digest: `sha256:f864a338d59250903ac7c1a60c5f6b401c2f22191ffcda877a702c57f13459e3`;
  complete: true; failures: none).
- Deviations from the phase spec: none.
- New blockers discovered (mirrored into `docs/plan/BLOCKERS.md`): none. P11 remains a
  local single-machine capability and does not close existing source, real-provider,
  authenticated-identity, hostile-isolation, or production-operation obligations.

## Post-merge appeal — expired lease authority

The first all-merged Curator and Judge review blocked exact candidate
`939287358679902a175d49abeea684a79b7d76ae`. Both reproduced that the original worker
could complete or fail after lease expiry when no competitor had yet reclaimed the job.
The earlier stale-token regression covered only the later post-reclaim state.

The appeal atomically requires the current token and `lease_expiry >= now` for both
completion and failure. New no-reclaim regressions preserve the job unchanged after each
rejected operation, and the existing post-reclaim test remains. A new
`P10-P11-repair-post.json` audit supersedes the original lease-authority claim while
retaining the original audit and independent dissent.
