# Verifiable Hive Kernel: Phase 0 Migration Map

## Phase 0 changes

| Current surface | Phase 0 action | Compatibility | Rollback |
| --- | --- | --- | --- |
| Existing CLI commands | Preserve unchanged | No argument or output changes | No action required |
| `hive-mind kernel doctor` | Add read-only diagnostic route | New command only | Remove route and package |
| Existing mission and scheduler databases | Do not read or write | No schema migration | No action required |
| Existing ledgers, receipts, and projections | Do not mutate | No receipt migration | No action required |
| `brain_kernel` imports | Add one-way boundary test | No existing import consumers | Remove additive package |

## Future migration prerequisites

No existing path may be routed through the kernel until the relevant phase supplies:

1. a versioned adapter contract;
2. replay or parity fixtures against the legacy behavior;
3. an append-only migration record where persistent data is involved;
4. an independently reproduced rollback procedure; and
5. a documented disposition for any source or ADR conflict.

The current Phase 0 doctor intentionally introduces no persistent state, so it has no
database migration or data rollback step.

## Phase 11: versioned enqueue convergence

| Legacy surface | Phase 11 action | Compatibility | Rollback |
| --- | --- | --- | --- |
| `hive-mind enqueue` | Record an idempotent `legacy-enqueue-v1` kernel mission binding after the existing scheduler job is created. | Existing parser, job payload, mission ID, deduplication, stdout JSON, and legacy scheduler remain authoritative. | `--compatibility-mode legacy` skips the additive kernel record and reuses the existing legacy job. |
| `.hive-mind-state` | Preserve `scheduler.sqlite3`, missions, receipts, and ledger in place. | Existing `serve`, `resume`, `missions`, and `status` retain their legacy reads and execution behavior. | No data restoration is needed because this route never migrates or mutates legacy state. |
| `.hive-mind-kernel-state` | Create a separate `brain-kernel.sqlite3` migration record. | The record binds legacy mission ID, scheduler job ID, payload digest, and repository pin. | Reverting the additive record leaves the legacy route executable; the separate kernel record is retained as evidence. |
