# DURABLE-410 — Durability qualification for the canonical mission runtime

## 1. Contract summary

**Objective.** Prove restart, resume, lease, crash consistency, and event replay
for the canonical mission runtime (`MISSION-400`) and the durable substrates it
runs on: `KernelStore`, `DurableEffectOutbox`, `Scheduler`, `KernelWorker`.

**Acceptance criteria (compressed).**
1. Every injected crash resumes from append-only state.
2. No accepted effect or role result is duplicated.
3. Stale leases and corrupt snapshots are recovered or quarantined.

**Scope table.**

| Kind | Paths |
|---|---|
| write_scope (ONLY these) | `tests/test_hive_cortex_durability.py`, `docs/execution/DURABILITY_QUALIFICATION.md` |
| read_scope | `src/hive_mind_os/brain_kernel/**`, `src/hive_mind_os/scheduler.py`, `src/hive_mind_os/mission_store.py` |
| forbidden_scope | `.github/CODEOWNERS`, `.github/governance/**`, `evidence/courts/**`, `docs/architecture/HARDENED_VISION_CONTRACT.md` |

**HARD RULES (state-and-obey):**
- This is a TESTS-AND-DOCS-ONLY node. Create/modify ONLY the two write_scope
  paths. NEVER touch: any `__init__.py`, any `conftest.py`, `pyproject.toml`,
  any file under `src/`, sibling nodes' files (`DELIVERY-420`, `HUMANLESS-430`,
  `CHEAT-440`, `LEARN-500` scopes), `.autopilot/**`, or anything in
  forbidden_scope. If a fix appears to require a `src/` change, run
  `autopilot fail` with a blocker — do not "fix" the kernel from this node.
- Import every module by full path (`hive_mind_os.brain_kernel.store` etc.);
  no package re-export edits.
- Never touch the release branch; never rebase/squash/amend the node branch
  (`autopilot/durable-410`); never run repo-wide test discovery. Run ONLY the
  focused command in §5; the authenticated validation broker exclusively owns the
  repository-wide gate.
- Semantic lock: `durability-qualification`. Do not weaken acceptance to pass;
  a test that cannot be made honest is an escalation, not a skip.

**Round.** R2A, dispatched ALONE (durability must land before the level-7
parallel wave). Formerly grouped with `DELIVERY-420 HUMANLESS-430 CHEAT-440
LEARN-500` (all lock-disjoint). Depends on `MISSION-400` (R1, already
integrated into the release branch when you start). If
`src/hive_mind_os/brain_kernel/mission_runtime.py` does not exist on your base
commit, stop immediately and `autopilot fail` with blocker
"MISSION-400 not integrated".

## 2. Existing-code map (real signatures — verified on this branch)

All paths relative to repo root. Do not re-derive these; they are quoted from
source.

| Path | Symbol | Signature | Role |
|---|---|---|---|
| `src/hive_mind_os/brain_kernel/store.py` | `KernelStore` | `__init__(self, path: str | Path = ":memory:", *, read_only: bool = False)` | Append-only SQLite event spine; writable ctor validates the chain and rebuilds projections; corrupt history fails closed in the constructor |
| store.py | `KernelStore.append` | `append(self, event: KernelEvent, *, expected_sequence: int | None = None, recorded_at: str = "1970-01-01T00:00:00Z", idempotency_key: str | None = None) -> int` | Atomic append; idempotency-key retry with the exact same event is read-only |
| store.py | `KernelStore.append_batch` | `append_batch(self, entries, *, expected_sequence=None, recorded_at=...) -> tuple[int, ...]` | All-or-nothing batch; rejects partial retries and competing bindings with `KernelIntegrityError` |
| store.py | `KernelStore.events` | `events(self) -> list[dict[str, Any]]` | Verified, chain-checked event records; raises `KernelIntegrityError` on a corrupt chain |
| store.py | `KernelStore.projection` / `rebuild_projections` / `status` | `projection(self) -> dict`; `rebuild_projections(self) -> dict`; `status(self, mission_id: str) -> dict` | Derived read models; rebuild replays deterministically from sequence 1 |
| store.py | `KernelStore.write_snapshot` / `load_snapshot` | `write_snapshot(self) -> int`; `load_snapshot(self) -> dict[str, Any]` | Snapshot is non-authoritative; `load_snapshot` replays events through the recorded sequence and discards any snapshot whose digest OR replay disagrees |
| store.py | `KernelStore.recover_effects` | `recover_effects(self, *, recorded_at: str) -> list[str]` | Marks all `executing` outbox rows `reconciliation_required` on restart |
| store.py | `KernelIntegrityError` | `class KernelIntegrityError(RuntimeError)` | Fail-closed durability error |
| store.py | `DATABASE_FILENAME` | `= "brain-kernel.sqlite3"` | Canonical DB filename |
| `src/hive_mind_os/brain_kernel/events.py` | `KernelEvent` | `KernelEvent(event_id, mission_id, event_type, actor_id, occurred_at, payload, work_id=None, attempt_id=None, actor_role=None, event_version=1, previous_digest=None)` (frozen dataclass) | One durable fact; `digest_for(previous_digest) -> str` binds the chain |
| `src/hive_mind_os/brain_kernel/projection.py` | `reduce_event` / `empty_state` / `state_digest` | `reduce_event(state, event) -> dict`; `empty_state() -> dict`; `state_digest(state) -> str` | Pure reducers; legal transitions include `mission.created` → `mission.transition{PLANNING}`, `work.created`, `work.transition` |
| `src/hive_mind_os/brain_kernel/effect_outbox.py` | `DurableEffectOutbox` | `__init__(self, store: KernelStore, *, adapters=None, adapter_versions=None, clock=_time)` | Durable enqueue → execute → receipt; never blind-retries |
| effect_outbox.py | `DurableEffectOutbox.execute` | `execute(self, intent: EffectIntent, token: CapabilityToken) -> EffectResult` | Duplicate delivery returns the prior receipt; interrupted delivery raises `EffectReconciliationRequired` |
| effect_outbox.py | `DurableEffectOutbox.reconcile` | `reconcile(self, intent_digest: str, receipt: EffectReceipt, *, token: CapabilityToken, evidence=None) -> EffectResult` | Adopt an explicit receipt without re-executing |
| effect_outbox.py | `DurableEffectOutbox.recover` | `recover(self) -> list[str]` | Restart hook: converts stale `executing` entries into repair obligations |
| effect_outbox.py | `EffectReconciliationRequired` | `class EffectReconciliationRequired(RuntimeError)` | Ambiguous-outcome error |
| `src/hive_mind_os/brain_kernel/effects.py` | `EffectGateway` | `__init__(self, store: KernelStore | None = None)`; `register_adapter(self, name, adapter, *, version="1")`; `execute(intent, token) -> EffectResult` | Store-backed gateway delegates to the durable outbox |
| effects.py | `build_effect_receipt` | `build_effect_receipt(intent, *, adapter_identity, adapter_version, started_at, ended_at, status="SUCCEEDED", produced_identifiers=(), observed_precondition_digest=None, postcondition_digest=None, retry_of=None, rollback_receipt=None) -> EffectReceipt` | Schema-valid reconciliation receipts |
| `src/hive_mind_os/brain_kernel/authority.py` | `AuthorityRegistry` | `register(envelope, parent=None)`; `authorize(digest, action, target, *, now: str) -> CapabilityToken` | Issues the `CapabilityToken(envelope_digest, action, target, token_digest)` the outbox validates |
| `src/hive_mind_os/brain_kernel/contracts.py` | `EffectIntent` | 16 positional fields ending `..., policy_decision_ref, intent_digest` — copy the constructor call verbatim from `tests/test_hive_cortex_effects.py::_intent` | Effect intent contract |
| contracts.py | `ConstraintEnvelope`, `Budget` | Copy verbatim from `tests/test_hive_cortex_effects.py::_envelope` | Authority envelope fixture |
| `src/hive_mind_os/brain_kernel/canonical.py` | `canonical_digest` | `canonical_digest(value: Any) -> str` (returns `"sha256:..."`) | Digest helper for distinct intent keys |
| `src/hive_mind_os/scheduler.py` | `Scheduler` | `__init__(self, state_dir, *, clock: Clock | None = None, lease_seconds: float = 30.0, backoff_seconds: float = 1.0)` | SQLite job queue with token-bound leases |
| scheduler.py | `Scheduler.claim/heartbeat/complete/fail/get/jobs` | `claim(self, owner: str) -> Job | None`; `heartbeat(self, job_id, lease_token) -> Job`; `complete(self, job_id, lease_token, *, mission_id) -> Job`; `fail(self, job_id, lease_token, error, *, mission_id=None) -> Job` | Stale-token mutation raises `StaleLeaseError`; expired leases are reclaimable; exhausted attempts dead-letter |
| scheduler.py | `ManualClock` | `ManualClock(value: float = 0.0)`; `.advance(seconds)` | Deterministic lease expiry in tests |
| scheduler.py | `Job`, `StaleLeaseError` | frozen dataclass / `RuntimeError` subclass | Lease state carriers |
| `src/hive_mind_os/brain_kernel/workers.py` | `KernelWorker` | `__init__(self, scheduler: Scheduler, scope_locks: ScopeLockStore, owner: str, executor: KernelExecutor, *, store: KernelStore | None = None)`; `enqueue(mission_id, work_id, write_scope, *, max_attempts=3) -> Job`; `run_once(self) -> bool` | Leased local worker emitting `work.transition` events |
| workers.py | `ScopeLockStore` | `__init__(self, state_dir)`; `acquire(paths, owner, now, ttl) -> bool`; `release(owner)`; `close()` | Expiring exclusive write-scope locks |
| `src/hive_mind_os/brain_kernel/mission_runtime.py` | (created by MISSION-400) | READ THIS FILE FIRST at execution time, plus `docs/execution/CANONICAL_MISSION_RUNTIME.md` | Canonical end-to-end mission runner over `KernelStore` |

Existing durability coverage you must NOT duplicate (extend beyond it):
`tests/test_brain_kernel_store.py` (chain restart/rebuild, single corrupt
snapshot, paired snapshot tampering, batch atomicity),
`tests/test_scheduler.py` (contended claim, expired-lease reclaim, dead-letter
ladder), `tests/test_hive_cortex_effects.py` (duplicate delivery after
restart, crash-window reconciliation). Your suite composes these mechanisms
into *cross-boundary* crash/restart scenarios and mission-runtime replay.

## 3. Design

### 3.1 `tests/test_hive_cortex_durability.py` (the only new code)

Standard-library `unittest` only (no pytest). Module layout:

```python
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.authority import AuthorityRegistry
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import Budget, ConstraintEnvelope, EffectIntent
from hive_mind_os.brain_kernel.effect_outbox import (
    DurableEffectOutbox,
    EffectReconciliationRequired,
)
from hive_mind_os.brain_kernel.effects import EffectGateway, build_effect_receipt
from hive_mind_os.brain_kernel.events import KernelEvent
from hive_mind_os.brain_kernel.projection import empty_state, reduce_event, state_digest
from hive_mind_os.brain_kernel.store import (
    DATABASE_FILENAME,
    KernelIntegrityError,
    KernelStore,
)
from hive_mind_os.brain_kernel.workers import KernelWorker, ScopeLockStore
from hive_mind_os.scheduler import ManualClock, Scheduler, StaleLeaseError
# plus the mission-runtime entry point discovered in step 1 of §4, e.g.
# from hive_mind_os.brain_kernel.mission_runtime import <Runner>
```

**Module fixtures** (copy the proven shapes; do not invent field orders):
- `DIGEST = "sha256:" + "0" * 64`, `TIME = "2030-01-01T00:00:00Z"`.
- `_envelope() -> ConstraintEnvelope` and
  `_intent(*, key: str = DIGEST, digest: str = DIGEST) -> EffectIntent`:
  copy verbatim from `tests/test_hive_cortex_effects.py` lines 28–69, renaming
  the identifiers to `AUTH-durable` / `MISSION-durable` / `WORK-durable` /
  `ATTEMPT-durable` / `POLICY-durable` (identifier fields must match
  `^[A-Z]+-` per `contracts._identifier` — keep the same `PREFIX-suffix`
  shape).
- `event(event_id, event_type, previous, payload=None, work_id=None) ->
  KernelEvent`: copy from `tests/test_brain_kernel_store.py` lines 23–39 with
  `mission_id="MISSION-durable"`.
- Helper `def _reopen(path: Path) -> KernelStore: return KernelStore(path)` —
  every "crash" in this suite is: stop cooperating mid-protocol, call
  `store.close()` (or simply abandon the object for scheduler DBs), and
  construct a fresh instance over the same file. Always `close()` every
  SQLite-backed object before `TemporaryDirectory` cleanup (Windows cannot
  delete open files).

**Test classes** (names are the required_tests mapping — see §5):

`class CrashMatrixTests(unittest.TestCase)` — acceptance criteria 1 and 2.
- `setUp`: `TemporaryDirectory`; `KernelStore(dir/DATABASE_FILENAME)`;
  `AuthorityRegistry` + `_envelope()` + token
  (`registry.authorize(DIGEST, "write", "workspace/result.txt", now=TIME)`).
- `test_crash_before_adapter_run_resumes_and_delivers_exactly_once`:
  `outbox.enqueue(intent, token)` (adapter NOT called), close, reopen,
  `EffectGateway(store=reopened)` with a counting adapter, `execute` →
  `SUCCEEDED`, adapter called exactly once; `execute` again after a second
  reopen → same `EffectResult`, adapter count still 1. (Crash point: after
  durable intent, before delivery.)
- `test_crash_during_execution_is_quarantined_not_retried`: drive the outbox
  to the `executing` state without a receipt by calling
  `store.begin_effect(intent_digest=..., recorded_at=TIME)` directly after
  `enqueue`, then close (the simulated process dies mid-adapter). Reopen;
  `DurableEffectOutbox(reopened).recover()` returns the intent digest; entry
  state is `reconciliation_required`;
  `execute` now raises `EffectReconciliationRequired` (no blind retry);
  `reconcile(...)` with a `build_effect_receipt(...)` receipt yields
  `SUCCEEDED`, and a further `execute` returns that same receipt.
- `test_crash_between_receipt_and_ack_is_idempotent`: complete one delivery,
  close, reopen, `execute` the same intent → identical
  `(intent_digest, receipt_digest, status)`; assert
  `store.effect_entry(...)["state"] == "receipt_recorded"` and exactly one row
  in `effect_receipts` (query `reopened.connection`).
- `test_event_append_crash_leaves_no_partial_state`: append `mission.created`;
  attempt an `append_batch` whose second event is an illegal transition
  (`{"status": "COMPLETED"}` from `CREATED`) → `KernelIntegrityError`; close,
  reopen; events list is exactly `["EVENT-1"]` and `projection()` matches the
  pre-batch value (append-only resume, criterion 1).
- `test_role_result_idempotency_key_prevents_duplicate_acceptance`:
  append an event with `idempotency_key="KEY-1"`, close, reopen, re-append the
  exact same `KernelEvent` with the same key → same sequence returned, event
  count unchanged; a *different* event with the same key raises
  `KernelIntegrityError` (criterion 2 for role results — duplication is
  rejected at the spine).

`class LeaseRecoveryTests(unittest.TestCase)` — acceptance criterion 3
(leases) and criterion 1 (resume).
- `setUp`: `TemporaryDirectory`; `ManualClock()`;
  `Scheduler(dir, clock=clock, lease_seconds=30.0, backoff_seconds=1.0)`.
  `tearDown`: `scheduler.close()`.
- `test_worker_crash_releases_lease_after_expiry_and_second_worker_resumes`:
  enqueue, `claim("worker-a")` (worker-a "crashes": never completes),
  `claim("worker-b")` before expiry → `None`; `clock.advance(31)`;
  `claim("worker-b")` → the same job id, `attempts == 2`; worker-a's late
  `complete(job.id, old_token, mission_id=...)` raises `StaleLeaseError`
  (crash consistency: the dead worker cannot corrupt state).
- `test_scheduler_restart_preserves_lease_and_job_state`: enqueue + claim,
  `scheduler.close()`, construct a new `Scheduler` over the same `state_dir`
  with the same clock; `get(job.id)` still shows `state == "leased"` with the
  same token; after `clock.advance(31)` the new process claims it (durable
  lease state survives restart).
- `test_kernel_worker_crash_mid_job_lapses_lock_and_is_reclaimable`: use
  STORE-LESS workers for the crash-and-retry path (no `store=` argument —
  the pattern of `tests/test_brain_kernel_workers.py`): `ScopeLockStore(dir)`
  and a `KernelWorker(scheduler, locks, "worker-a", executor)` whose executor
  raises `RuntimeError("injected crash")`; `run_once()` returns True and the
  job goes back to `ready` with `last_error` recording the injected crash;
  the scope lock is released (a fresh `locks.acquire` on the same
  `write_scope` paths succeeds at the current clock); `clock.advance(2)` to
  clear the retry backoff (`backoff_seconds=1.0` in `setUp`), then a second
  store-less `KernelWorker(scheduler, locks, "worker-b", succeeding_executor)`
  drains it to `done`. Do NOT pass `store=` on the crash path: after a crash
  the work projection stays `RUNNING` with no failure transition, so the
  retry's `_transition(job, "LEASED")` re-appends event id
  `worker:<job.id>:LEASED` (`KernelIntegrityError("event id is already
  bound")`) and `RUNNING → LEASED` is an illegal projection transition —
  a `src/` fix is out of scope for this node.
- `test_kernel_worker_success_records_awaiting_verification_trail`: the
  store-backed trail assertion, on a first-attempt success (mirrors
  `tests/test_brain_kernel_workers.py::test_kernel_events_precede_local_worker_completion`):
  build `KernelStore` (with `mission.created` + `work.created` events so
  `KernelWorker.enqueue` sees `PROPOSED` work) and a
  `KernelWorker(scheduler, locks, "worker-a", executor, store=store)` whose
  executor succeeds; `enqueue` + `run_once()` drains the job to `done` and
  the store shows the `work.transition` trail ending `AWAITING_VERIFICATION`.
  (Use `work_id="WORK-durable"`; the worker emits `work.transition` events
  itself via `_transition`.)
- `test_stale_scope_lock_expires_by_ttl`: `locks.acquire(("a.py",), "dead", now=0.0, ttl=10.0)`
  → True; `locks.acquire(("a.py",), "live", now=5.0, ttl=10.0)` → False;
  `now=11.0` → True (stale lock recovered, criterion 3).
- `test_dead_letter_after_exhausted_crashes`: `max_attempts=2`; two
  claim+expiry cycles without completion; next `claim` returns `None` and
  `get(job.id).state == "dead-letter"` (bounded, no infinite retry).

`class SnapshotCorruptionTests(unittest.TestCase)` — acceptance criterion 3
(snapshots) and criterion 1 (replay).
- `test_corrupt_snapshot_after_restart_is_rebuilt_from_events`: on-disk store,
  two events, `write_snapshot()`, close; open a RAW
  `sqlite3.connect(path)` and `UPDATE snapshots SET state_json='{"missions":{},"work":{}}'`,
  commit, close; reopen `KernelStore(path)`; `load_snapshot()` equals
  `projection()` and equals a manual replay
  (`reduce_event` over `store.events()` from `empty_state()`), and the
  snapshots table now holds the repaired digest
  (`state_digest(projection)`).
- `test_paired_snapshot_tamper_survives_restart`: like the existing in-memory
  test but across a close/reopen: tamper both `state_json` and
  `state_digest` consistently via a raw connection; reopened
  `load_snapshot()` still returns the event-derived truth (replay beats
  digest-consistent lies).
- `test_corrupt_event_chain_is_quarantined_at_open`: build a valid on-disk
  store, close; raw connection: `DROP TRIGGER kernel_events_no_update`, then
  `UPDATE events SET payload_json='{"status":"HACKED"}' WHERE event_id='EVENT-2'`,
  commit, close; `KernelStore(path)` now raises `KernelIntegrityError` from
  the constructor (writable open validates the chain) AND
  `KernelStore(path, read_only=True).events()` raises too — the corrupt
  history is quarantined, never silently served.
- `test_read_only_open_never_mutates`: reopen a healthy DB with
  `read_only=True`; `projection()` works; `write_snapshot()` /
  `rebuild_projections()` / `append(...)` raise `KernelIntegrityError`
  ("read-only kernel store cannot be mutated").

`class MissionRuntimeReplayTests(unittest.TestCase)` — binds the matrix to the
canonical runtime (criterion 1 end-to-end).
- Discovery step (§4 step 1) fixes the exact entry point; the invariants to
  assert are runtime-independent:
  1. Run one mission to completion through the mission-runtime entry point
     against an on-disk `KernelStore`; capture `store.events()` and
     `store.status(mission_id)`.
  2. Close everything; reopen the same database file; assert the two
     *event-derived* views agree — `rebuild_projections()` equals
     `load_snapshot()` — and that the materialized read model `projection()`
     agrees with them on every mission and work **status**, and that
     `status(mission_id)` equals the pre-crash value (restart/resume from
     append-only state alone).
  3. Deterministic replay: fold `reduce_event` from `empty_state()` over the
     reopened `events()`; the fold equals `rebuild_projections()`, and
     `canonical_digest(projection())` equals its pre-crash value.

     **Do not assert `projection() == rebuild_projections()`, and do not
     compare `state_digest(fold)` with `status(...)["state_digest"]`.**
     `rebuild_projections()` / `load_snapshot()` return the full reduced
     state, whose work entries accumulate `evaluation_plan_digest`,
     `passed_evaluation_digest`, and `evaluation_bundle_digest`
     (`projection.py` `reduce_event`), while `projection()` rehydrates only
     `mission_id`/`status` from the flat `work_projection` table
     (`store.py:604-668`). Any mission that seals an evaluation plan and
     records a passed evaluation — which the canonical run requires before
     ACCEPTED — makes those unequal by construction, and nothing inside this
     node's write scope can reconcile them. MISSION-400 records the same
     boundary at `mission_runtime.py:367-370`.

     Measured on the level-7 target after a canonical mission run:
     `projection() == rebuild_projections()` → False;
     `rebuild_projections() == load_snapshot()` → True; rebuilt work keys
     `{evaluation_bundle_digest, evaluation_plan_digest, mission_id,
     passed_evaluation_digest, status}` vs projection work keys
     `{mission_id, status}`. The invariants above are satisfiable and are the
     stronger claim: they prove the read model survives a full replay on the
     fields it actually materializes, rather than asserting an equality
     between two deliberately different shapes.
  4. No duplication on resume: re-invoking the runtime's resume/replay path
     (or re-appending its recorded events with their idempotency keys, if the
     runtime exposes them) leaves `len(store.events())` unchanged.
- If `mission_runtime.py` exposes no way to run against a caller-supplied
  `KernelStore` path, that contradicts the MISSION-400 acceptance criterion
  "Effects, verification, remand, integration, operations, and optimization
  are event-derived" — escalate with `autopilot fail` (assumption
  contradiction). Do NOT `skipTest` and do not weaken the assertion set.

### 3.2 `docs/execution/DURABILITY_QUALIFICATION.md`

A qualification record (not marketing). Required sections:
1. **Scope & claims** — the three acceptance criteria, verbatim, each mapped
   to test class names.
2. **Failure-injection matrix** — one table row per test: crash point,
   injection mechanism (close/reopen, `begin_effect` abandonment,
   `ManualClock` expiry, raw-SQL tamper, trigger drop), durable invariant,
   recovery behavior (resume / exactly-once / quarantine), verifying test
   method.
3. **Recovery protocols** — restart order for an operator/process supervisor:
   reopen `KernelStore` (constructor self-validates) →
   `DurableEffectOutbox.recover()` → `Scheduler` claims resume naturally after
   lease expiry; corrupt event chains fail closed and require restoring from
   the last good copy (quarantine, never repair-in-place).
4. **Known limits** — local guarantees only (single-host SQLite); external
   adapter outcomes resolve via explicit `reconcile` witnesses, never blind
   retry; snapshots are acceleration, never authority.
5. **Evidence** — the exact focused command, base/final commit SHAs, and the
   pass output summary (filled in at completion time).

## 4. Implementation order (small commits on `autopilot/durable-410`)

1. Read `src/hive_mind_os/brain_kernel/mission_runtime.py` and
   `docs/execution/CANONICAL_MISSION_RUNTIME.md` (both in read_scope, created
   by MISSION-400). Note the exact public entry point and how it binds to
   `KernelStore` before writing any code.
2. Commit 1: `tests/test_hive_cortex_durability.py` with module fixtures +
   `CrashMatrixTests`. Run the focused command; green.
3. Commit 2: add `LeaseRecoveryTests`. Focused run; green.
4. Commit 3: add `SnapshotCorruptionTests`. Focused run; green.
5. Commit 4: add `MissionRuntimeReplayTests` bound to the discovered entry
   point. Focused run; green.
6. Commit 5: `docs/execution/DURABILITY_QUALIFICATION.md` with the completed
   matrix and evidence section.
7. Open the draft PR against `main` per the rendered prompt; push the receipt;
   stop (stopping_condition: do not merge, do not start downstream nodes).

## 5. Test plan

**required_tests mapping.**

| required_tests name | unittest class | Methods |
|---|---|---|
| `crash-matrix-tests` | `tests.test_hive_cortex_durability.CrashMatrixTests` | `test_crash_before_adapter_run_resumes_and_delivers_exactly_once`, `test_crash_during_execution_is_quarantined_not_retried`, `test_crash_between_receipt_and_ack_is_idempotent`, `test_event_append_crash_leaves_no_partial_state`, `test_role_result_idempotency_key_prevents_duplicate_acceptance` |
| `lease-recovery-tests` | `tests.test_hive_cortex_durability.LeaseRecoveryTests` | `test_worker_crash_releases_lease_after_expiry_and_second_worker_resumes`, `test_scheduler_restart_preserves_lease_and_job_state`, `test_kernel_worker_crash_mid_job_lapses_lock_and_is_reclaimable`, `test_kernel_worker_success_records_awaiting_verification_trail`, `test_stale_scope_lock_expires_by_ttl`, `test_dead_letter_after_exhausted_crashes` |
| `snapshot-corruption-tests` | `tests.test_hive_cortex_durability.SnapshotCorruptionTests` | `test_corrupt_snapshot_after_restart_is_rebuilt_from_events`, `test_paired_snapshot_tamper_survives_restart`, `test_corrupt_event_chain_is_quarantined_at_open`, `test_read_only_open_never_mutates` |
| (binds the matrix to MISSION-400) | `tests.test_hive_cortex_durability.MissionRuntimeReplayTests` | replay/resume/no-duplication methods per §3.1 |

**Exact focused commands (the ONLY test commands this node runs):**

```bash
PYTHONPATH=src python -m unittest tests.test_hive_cortex_durability -v
```

Optionally per-class while iterating:

```bash
PYTHONPATH=src python -m unittest tests.test_hive_cortex_durability.CrashMatrixTests -v
PYTHONPATH=src python -m unittest tests.test_hive_cortex_durability.LeaseRecoveryTests -v
PYTHONPATH=src python -m unittest tests.test_hive_cortex_durability.SnapshotCorruptionTests -v
PYTHONPATH=src python -m unittest tests.test_hive_cortex_durability.MissionRuntimeReplayTests -v
```

Never run `python -m unittest discover` or `pytest`.

**Edge cases to keep honest.**
- Windows file locking: `close()` every `KernelStore`, `Scheduler`,
  `ScopeLockStore`, and raw `sqlite3` connection before
  `TemporaryDirectory.cleanup()`; prefer `addCleanup`.
- Distinct intents need distinct digests: use
  `canonical_digest({"key": <name>})` for `idempotency_key`/`intent_digest`
  pairs (the store binds keys to digests 1:1).
- `_identifier` validation requires `PREFIX-suffix` uppercase-prefix ids;
  `_time` requires `...T...Z`-style ISO timestamps; reuse the fixture
  constants.
- `Scheduler` uses WAL mode; a second `Scheduler` over the same dir is the
  legitimate "restarted process" — do not copy files around.
- Do not assert on wall-clock values; drive everything through `ManualClock`.

## 6. Acceptance self-check

| Criterion | Demonstrated by | Receipt evidence |
|---|---|---|
| Every injected crash resumes from append-only state | Every test reopens the same on-disk DB after the injected failure and asserts equality of `projection()`, `rebuild_projections()`, `load_snapshot()`, and replayed `reduce_event` state (`CrashMatrixTests`, `SnapshotCorruptionTests`, `MissionRuntimeReplayTests`) | Focused command output showing all methods PASS; changed-path inventory = exactly the two write_scope files |
| No accepted effect or role result is duplicated | Adapter call-count assertions across restart (`test_crash_before_adapter_run...`, `test_crash_between_receipt_and_ack...`); single `effect_receipts` row; idempotency-key re-append returns the original sequence (`test_role_result_idempotency_key...`); runtime resume leaves event count unchanged | Same test receipts; quote the exactly-once assertions in the completion receipt |
| Stale leases and corrupt snapshots are recovered or quarantined | Lease expiry reclaim + `StaleLeaseError` on the dead worker (`LeaseRecoveryTests`); corrupt/tampered snapshots rebuilt from the spine, corrupt event chain refuses to open (`SnapshotCorruptionTests`); `DurableEffectOutbox.recover()` converts stale executions to reconciliation obligations | Same receipts + the failure-injection matrix table in `DURABILITY_QUALIFICATION.md` |

Also record in the receipt: base and final commit SHAs, the focused command
with outcome, role identities from the rendered prompt, and the rollback
reference (revert of the node commit).

## 7. Out-of-scope traps (do NOT do these)

- Do NOT modify anything under `src/` — not even a "one-line fix" to
  `mission_runtime.py`, `store.py`, or `scheduler.py`. A real kernel bug found
  by these tests is an `autopilot fail` escalation with the failing test as
  evidence.
- Do NOT create or edit `__init__.py`, `conftest.py`, `pyproject.toml`, or any
  other test file (`tests/test_brain_kernel_store.py`,
  `tests/test_scheduler.py`, `tests/test_hive_cortex_effects.py`,
  `tests/test_hive_cortex_mission_runtime.py` are read-only references).
- Do NOT touch the level-7 (R2B) sibling scopes: delivery/packaging files (DELIVERY-420),
  humanless-operation files (HUMANLESS-430), anti-cheat files (CHEAT-440),
  learning files (LEARN-500).
- Do NOT touch `.autopilot/**`, `.github/CODEOWNERS`, `.github/governance/**`,
  `evidence/courts/**`, or `docs/architecture/HARDENED_VISION_CONTRACT.md`.
- Do NOT run repo-wide discovery, `pytest`, coverage tools, or linters that
  rewrite files.
- Do NOT use `unittest.skip*` to route around a failing durability invariant,
  loosen an assertion to equality-of-something-weaker, sleep-based timing, or
  real wall clocks.
- Do NOT add third-party test dependencies; standard library only.
- Do NOT merge the PR, rebase/squash/amend the node branch, or push to the
  release branch; open a draft PR and stop.
