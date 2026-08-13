# Durability qualification — canonical mission runtime (DURABLE-410)

This is a qualification record, not a summary. Every claim below is bound to an
executable assertion in `tests/test_hive_cortex_durability.py`. Where the
kernel's real behaviour differs from what a claim would like to be true, the
limit is recorded here rather than asserted away.

## 1. Scope & claims

Substrates under qualification: `KernelStore`
(`src/hive_mind_os/brain_kernel/store.py`), `DurableEffectOutbox`
(`brain_kernel/effect_outbox.py`), `Scheduler` (`src/hive_mind_os/scheduler.py`),
`KernelWorker`/`ScopeLockStore` (`brain_kernel/workers.py`), and the canonical
`MissionRuntime` (`brain_kernel/mission_runtime.py`, MISSION-400).

| # | Acceptance criterion (verbatim) | Demonstrated by |
|---|---|---|
| 1 | Every injected crash resumes from append-only state. | `CrashMatrixTests`, `LeaseRecoveryTests`, `SnapshotCorruptionTests`, `MissionRuntimeReplayTests` |
| 2 | No accepted effect or role result is duplicated. | `CrashMatrixTests`, `MissionRuntimeReplayTests` |
| 3 | Stale leases and corrupt snapshots are recovered or quarantined. | `LeaseRecoveryTests`, `SnapshotCorruptionTests` |

A "crash" in this suite is always a real process boundary: stop cooperating
mid-protocol, close the SQLite-backed object, and construct a fresh instance
over the same file. No sleeps, no wall clocks (`ManualClock` only), no mocks
standing in for a durable substrate.

## 2. Failure-injection matrix

| Crash point | Injection mechanism | Durable invariant | Recovery behaviour | Verifying test |
|---|---|---|---|---|
| After durable intent, before the adapter runs | `enqueue` then `close`/reopen | The intent is `pending` and no physical effect happened | Resume: the reopened process delivers exactly once (adapter call count 1) | `CrashMatrixTests.test_crash_before_adapter_run_resumes_and_delivers_exactly_once` |
| After the receipt, before the caller's ack | `close`/reopen after a completed delivery | One `effect_receipts` row per intent, entry `receipt_recorded` | Exactly-once: the retry returns the identical `(intent_digest, receipt_digest, status)`, adapter never re-invoked | `CrashMatrixTests.test_crash_between_receipt_and_ack_is_idempotent` |
| Inside the adapter, outcome unknown | `store.begin_effect(...)` then abandon the process (`close`) | The entry is stuck `executing`; the physical outcome is not knowable | Quarantine: `DurableEffectOutbox.recover()` marks it `reconciliation_required`; `execute` raises `EffectReconciliationRequired` instead of blind retry; only an explicit `reconcile` receipt resolves it | `CrashMatrixTests.test_crash_during_execution_is_quarantined_not_retried` |
| Mid-batch event append | `append_batch` whose second event is an illegal `PLANNING → COMPLETED` transition | All-or-nothing: a rejected batch persists no event | Resume: after reopen the spine is exactly `["EVENT-1"]` and `projection()`, `rebuild_projections()`, and a cold reducer fold all equal the pre-batch value | `CrashMatrixTests.test_event_append_crash_leaves_no_partial_state` |
| Role result replayed by a resuming caller | `close`/reopen, then re-`append` under the same idempotency key | A key binds 1:1 to one exact event | Idempotent: the original sequence is returned and the event count is unchanged; a *different* event under that key raises `KernelIntegrityError` | `CrashMatrixTests.test_role_result_idempotency_key_prevents_duplicate_acceptance` |
| Worker dies holding a live lease | `claim` then never complete; `ManualClock.advance(31)` | A lease is time-bound, and lease tokens are single-valued | Recovery: a second worker reclaims the same job at `attempts == 2`; the dead worker's late `complete` raises `StaleLeaseError` | `LeaseRecoveryTests.test_worker_crash_releases_lease_after_expiry_and_second_worker_resumes` |
| Scheduler process dies with a lease outstanding | `scheduler.close()`, new `Scheduler` over the same `state_dir` | Lease owner, token, expiry, and attempt count are durable, not in-memory | Resume: the restarted process sees `state == "leased"` with the same token, refuses an early claim, and reclaims only after expiry | `LeaseRecoveryTests.test_scheduler_restart_preserves_lease_and_job_state` |
| `KernelWorker` executor raises mid-job | Executor raising `RuntimeError("injected crash")` | A crash must not strand the write-scope lock or the job | Recovery: job returns to `ready` with `last_error` recording the crash, the scope lock is re-acquirable immediately, and a second worker drains it to `done` at `attempts == 2` | `LeaseRecoveryTests.test_kernel_worker_crash_mid_job_lapses_lock_and_is_reclaimable` |
| (Control) first-attempt success | Store-backed worker over a seeded spine | Kernel events precede completion | The `work.transition` trail is exactly `READY → LEASED → RUNNING → AWAITING_VERIFICATION` | `LeaseRecoveryTests.test_kernel_worker_success_records_awaiting_verification_trail` |
| Lock holder dies without releasing | `ScopeLockStore.acquire` with an elapsed TTL | Write-scope exclusivity is expiring, never permanent | Recovery: contention is refused inside the TTL and granted after it | `LeaseRecoveryTests.test_stale_scope_lock_expires_by_ttl` |
| Repeated crashes exhaust the budget | `max_attempts=2`, two claim/expiry cycles | Retry is bounded | Quarantine: the next `claim` returns `None` and the job is `dead-letter` | `LeaseRecoveryTests.test_dead_letter_after_exhausted_crashes` |
| Snapshot corrupted at rest | Raw `sqlite3` `UPDATE snapshots SET state_json=...` on a closed DB | A snapshot is acceleration, never authority | Recovery: `load_snapshot()` discards it, returns the event-derived truth (equal to `projection()` and to a cold reducer fold) and rewrites the repaired digest | `SnapshotCorruptionTests.test_corrupt_snapshot_after_restart_is_rebuilt_from_events` |
| Snapshot data *and* digest tampered consistently | Raw `UPDATE snapshots SET state_json=?, state_digest=?` with a self-consistent lie | Digest self-consistency is not sufficient evidence | Recovery: replay through the recorded sequence beats the digest-consistent lie | `SnapshotCorruptionTests.test_paired_snapshot_tamper_survives_restart` |
| Event history tampered at rest | Raw `DROP TRIGGER kernel_events_no_update` then `UPDATE events SET payload_json=...` | The hash chain is the authority | Quarantine: the writable constructor raises `KernelIntegrityError`, and `KernelStore(path, read_only=True).events()` raises too — corrupt history is never silently served | `SnapshotCorruptionTests.test_corrupt_event_chain_is_quarantined_at_open` |
| Forensic read of a live database | `KernelStore(path, read_only=True)` | Inspection cannot mutate | `projection()` works; `write_snapshot`, `rebuild_projections`, and `append` all raise `KernelIntegrityError("read-only kernel store cannot be mutated")` | `SnapshotCorruptionTests.test_read_only_open_never_mutates` |
| Mission process dies with the mission complete | Run `MissionRuntime.run` against a caller-owned on-disk store, `close`, reopen | The mission's whole outcome is derivable from events alone | Resume: `status()`, `projection()`, the event head digest, and `canonical_digest(projection())` all equal their pre-crash values and the run receipt | `MissionRuntimeReplayTests.test_completed_mission_reopens_from_append_only_state` |
| Cold replay after that crash | Fold `reduce_event` from `empty_state()` over the reopened spine | Replay is deterministic and total | `rebuild_projections()`, `load_snapshot()`, and the cold fold are all equal; the materialized read model agrees on every mission and work status | `MissionRuntimeReplayTests.test_reopened_replay_is_deterministic` |
| Resume path re-invoked | `MissionRuntime(reopened).replay(...)`, twice | Resume is side-effect free | No duplication: the event count is unchanged, and the event head and closeout report digests still equal the original receipt's | `MissionRuntimeReplayTests.test_resume_replay_appends_no_duplicate_events` |
| Builder effect re-executed after restart | Fresh `EffectGateway(store=reopened)` over the same intent | An accepted effect is accepted once | Exactly-once end-to-end: the prior receipt is returned, the adapter is never invoked, and `effect_receipts` still holds one row | `MissionRuntimeReplayTests.test_builder_effect_is_not_redelivered_after_restart` |

Each row was mutation-probed: removing the injection (or the recovery call)
makes the corresponding test fail. Spot checks performed — omitting the payload
tamper (chain quarantine no longer raises), omitting `ManualClock.advance`
(lease is not reclaimable), omitting `DurableEffectOutbox.recover()` (entry
stays `executing`), and resuming with a genuinely different intent (receipt
digests diverge).

## 3. Recovery protocols

Restart order for an operator or process supervisor:

1. **Reopen `KernelStore`.** The writable constructor validates the full hash
   chain and rebuilds every mutable projection before returning. A corrupt
   history therefore fails closed *at open*, not at first read.
2. **Run `DurableEffectOutbox.recover()`.** Every entry left `executing` by the
   dead process becomes `reconciliation_required` with an append-only
   reconciliation record. Nothing is retried.
3. **Resolve each reconciliation obligation explicitly.** Establish the real
   external outcome, then call `reconcile(intent_digest, receipt, token=...)`
   with a `build_effect_receipt` witness. `execute` on such an entry raises
   `EffectReconciliationRequired` until this is done.
4. **Let the `Scheduler` recover itself.** Leases are durable and time-bound;
   an abandoned job becomes claimable once `lease_expiry` passes, and the dead
   worker's stale token can no longer mutate it (`StaleLeaseError`). Scope locks
   lapse by TTL on the same principle. Jobs that exhaust `max_attempts`
   dead-letter instead of looping.
5. **Corrupt event chains are quarantined, never repaired in place.** The store
   refuses to open; restore from the last good copy. Snapshots need no operator
   action — `load_snapshot()` discards any snapshot whose digest *or* replay
   disagrees and rewrites a repaired one.

## 4. Known limits

- **Local guarantees only.** These are single-host SQLite guarantees. Nothing
  here qualifies multi-host consensus, replication, or fsync behaviour under
  power loss; the substrate's durability is SQLite's.
- **External outcomes need witnesses, not retries.** The outbox deliberately
  cannot decide whether an interrupted adapter changed the outside world. It
  converts ambiguity into an obligation and waits for an explicit authorized
  receipt. Availability is traded for never double-applying an effect.
- **Snapshots are acceleration, never authority.** No snapshot is trusted on
  digest self-consistency alone; it is replayed through its recorded sequence.
- **`projection()` is a strict projection of the reduced state.** The
  materialized `mission_projection`/`work_projection` tables carry mission and
  work *statuses* only. The full reduced state additionally accumulates
  `evaluation_plan_digest`, `passed_evaluation_digest`, and
  `evaluation_bundle_digest` per work item, which the materialized tables never
  rehydrate (documented at `src/hive_mind_os/brain_kernel/mission_runtime.py`
  lines 367-370). So after any mission that seals an evaluation plan,
  `projection() != rebuild_projections()` and
  `state_digest(cold_fold) != status(mission_id)["state_digest"]` — by design,
  not by defect. `MissionRuntimeReplayTests.test_reopened_replay_is_deterministic`
  therefore asserts the satisfiable form: the cold fold equals
  `rebuild_projections()` equals `load_snapshot()`, and the materialized read
  model agrees with the fold on every mission and work status. See §6.
- **The suite qualifies durability, not liveness.** It does not bound recovery
  latency or throughput.

## 5. Evidence

- Focused command (the only test command this node runs):
  `PYTHONPATH=src python -m unittest tests.test_hive_cortex_durability -v`
- Result: `Ran 19 tests in 5.809s` — `OK` (19 passed, 0 failed, 0 skipped,
  0 errors). No `unittest.skip` appears in the suite.
- Base commit: `7ec26c540e211dfe06007259df90c2091c04034d`
  (`fix(autopilot): make the round gate test the checkout it is integrating`).
- Changed-path inventory (exactly the node's write scope):
  `tests/test_hive_cortex_durability.py`,
  `docs/execution/DURABILITY_QUALIFICATION.md`.
- Rollback reference: revert of the node commit; the change is additive and
  touches no runtime code.

| required_tests name | Class | Methods |
|---|---|---|
| `crash-matrix-tests` | `CrashMatrixTests` | 5 |
| `lease-recovery-tests` | `LeaseRecoveryTests` | 6 |
| `snapshot-corruption-tests` | `SnapshotCorruptionTests` | 4 |
| (MISSION-400 binding) | `MissionRuntimeReplayTests` | 4 |

## 6. Recorded contradiction (open, for the integrator)

`docs/execution/runbooks/DURABLE-410.md` §3.1, `MissionRuntimeReplayTests`
items 2 and 3, mandates two assertions that the kernel's own design makes
unsatisfiable after a completed mission:

- item 2 — "assert `projection()`, `rebuild_projections()`, and
  `load_snapshot()` all agree";
- item 3 — "`state_digest(replayed)` equals `status(mission_id)["state_digest"]`".

`rebuild_projections()` and `load_snapshot()` return the **full reduced state**;
`projection()` and `status()` read the **materialized read model**, which stores
only `(mission_id, status)` per work item. MISSION-400 states this explicitly at
`src/hive_mind_os/brain_kernel/mission_runtime.py:367-370` ("Comparing those two
would be unsatisfiable after any accepted mission") and encodes it in
`store.py:604-668`. Measured on this base commit after a canonical mission:
`projection() == rebuild_projections()` is `False`;
`rebuild_projections() == load_snapshot()` is `True`;
`state_digest(cold_fold) == status()["state_digest"]` is `False`.

No assertion was weakened to route around this: the satisfiable invariants
asserted instead are strictly checkable and are listed in §4. Making the
runbook's literal wording true would require a `src/` change (rehydrating the
evaluation digests into the materialized projection), which is outside this
node's write scope.
