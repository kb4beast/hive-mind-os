# Verifiable Hive Kernel: Phase 2 event spine and projections

## Delivered boundary

Phase 2 establishes the durable authority for new kernel missions only:

- `KernelEvent` immutable values and canonical predecessor-bound digests;
- a portable local SQLite database named `brain-kernel.sqlite3`;
- append-only `events`, projection, snapshot, and idempotency tables;
- reducer-controlled mission/work projections rebuilt from sequence one;
- snapshot verification against replay, with corrupt snapshots replaced;
- read-only `hive-mind kernel status MISSION_ID --state-dir STATE_DIR [--json]`.

The event spine does not execute a role, grant authority, call a model, access a
provider, broker an external effect, change an old mission store, or claim that Phase 3
planning has begun. Existing ledger and receipt data are referenced only by future
event payload identifiers; Phase 2 neither copies nor migrates their bodies.

## Data and migration record

`kernel_metadata.schema_version` is `1`. The bootstrap is deliberately idempotent. If
an early, uncommitted Phase 2 preview created `work_projection` without `mission_id`,
bootstrap drops only that derived table and recreates it from authoritative events. No
event, snapshot, idempotency, legacy mission, ledger, or receipt record is migrated.

The database location is `STATE_DIR/brain-kernel.sqlite3`; state-dir spelling is left
to `pathlib`, making the same relative directory usable on Windows and Linux. The
database never stores a source artifact or receipt body.

## Operator procedure

Create or append a kernel fixture through the Python API, then inspect it without
creating state:

```text
hive-mind kernel status MISSION-one --state-dir .hive-mind-kernel-state --json
```

The JSON report contains `mission_id`, mission `status`, sorted mission work entries,
the authoritative `last_sequence`, and a canonical full-state digest. If the database
does not exist, the command returns failure and does not create a directory or database.
If the event chain cannot be verified or reduced, it returns failure rather than a
potentially stale view.

## Invariants and adversarial coverage

| Invariant | Executable coverage |
| --- | --- |
| Only events are authoritative | Projections rebuild on startup and explicit replay; normal and rebuilt state match after restart. |
| Events cannot be silently altered | SQLite update/delete triggers reject mutation; chain verification detects direct corruption. |
| Failed writes leave no half-state | A reducer-invalid append rolls back the new event and all derived view changes. |
| Retry cannot duplicate the same fact | An idempotency retry returns its original sequence; rebinding fails. |
| Snapshot corruption cannot lie | Snapshot state and digest are compared with event replay before use; mismatch is replaced. |
| Status remains a projection | The CLI opens an existing database read-only in intent, reports only derived fields, and refuses missing state. |

## Phase completion handoff

- Phase: 2 — Append-only kernel event store and deterministic projections.
- Repository: `HiveMind/hive-mind-os`.
- Base main SHA: `cf0c3fbbb46e6fd40ea2e26af177d3ee55a97f52` (Phase 1 baseline branch head).
- Branch: `codex/verifiable-hive-kernel-phase-2`.
- Final commit SHA: recorded in this branch's Git history after this handoff is
  committed; no remote delivery is included.
- Draft PR: not created in this phase handoff.
- Files added: event, store, projection, focused tests, ADR-046, and this handoff.
- Existing paths reused: Phase 1 canonical contracts, canonical JSON utility, and the
  additive `kernel` CLI namespace.
- Existing paths superseded or deprecated: none.
- User-visible capability delivered: durable fixture status for new kernel missions.
- Invariants added or strengthened: append-only chain, atomic append/rebuild,
  idempotency, deterministic projections, and replay-verified snapshots.
- Adversarial tests added: concurrency, chain mismatch, direct mutation, illegal
  transition, transactional rollback, snapshot corruption, and missing-state CLI.
- Bug-restore proof performed: the invalid transition test proves the append transaction
  fails before any event/projection change; the snapshot test proves a corrupted cache
  is replaced from events.
- Focused test commands and results:
  `python -m unittest -v tests/test_brain_kernel_store.py
  tests/test_brain_kernel_doctor.py tests/test_brain_kernel_contracts.py` — 22 passed;
  `python -m compileall -q src tests`, `python -m ruff check src tests`, and `pyright`
  — passed (0 static-analysis errors, warnings, or informations).
- Full local gate commands and results:
  `python -m unittest discover -s tests -v` — 478 passed in 754.853 seconds on
  2026-08-07; 5 skips are expected where Windows does not grant symlink privilege.
- CI state: not invoked; no remote action is authorized by this phase.
- Evidence artifacts and digests: deterministic local test output only; no new external
  evidence artifact.
- Database/schema version introduced: `brain-kernel.sqlite3`, schema version `1`.
- Migration performed: rebuildable early-preview `work_projection` only, if present.
- Rollback command/procedure: remove the additive kernel state directory and revert this
  additive commit; legacy stores remain untouched.
- Known limitations: no DAG, roles, worker scheduler, authority issuer, effect outbox,
  memory, evaluation, or legacy-store convergence.
- New blockers: independent courtroom disposition remains required.
- Human authority still required: all external effects, promotion, and any PR action.
- Plan deviations and repository-truth reason: status is intentionally limited to an
  existing fixture DB because Phase 2 must not create a second mission flow.
- Exact next eligible phase: Phase 3 — durable objective DAG and recursive planner.
- Files the next executor must read first: `ADR-046`, this handoff, `store.py`,
  `projection.py`, `contracts.py`, and the preserved standalone handoff Phase 3 section.
- Same-session or new-session recommendation and why: new session; it needs the final
  commit SHA and local-gate receipt, and must not mix DAG work with the event-spine diff.
