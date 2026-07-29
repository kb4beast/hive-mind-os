# Phase 3 item 5 migration and rollback

## Migration

1. Keep item 5 opt-in and evidence-only.
2. Generate fixture records with the real item 1–4 APIs.
3. Open only the disposable clone in Obsidian `1.12.7`.
4. Capture the required same-pane refresh, Base recomputation, Canvas render, and
   post-unload 300-second integrity receipts.
5. Retain `.obsidian/` only in the disposable clone.

The only production-code changes are item-4 Base scalar quoting and Canvas byte
serialization. Contracts, schema catalogs, paths, filters, view names, and semantic
content are unchanged.

## Rollback

Revert ADR-026, item-5 evidence/scripts/tests, the Base scalar quoting change, and
the Canvas serialization change. Restore the preceding item-4 inventory. Stop
running the conformance fixture.

Rollback does not delete user vaults, local Obsidian state, failed-run evidence, or
projector protected state. Those require separate, explicitly scoped cleanup.

## Failure recovery

- Preserve a failed run unchanged.
- Diagnose without refresh gestures or cache rebuilding.
- Repair only the producing code or test harness.
- Run a new disposable exact-commit test; never relabel the failed receipt.

## Residual operations

The disposable vault registration remains in the local Obsidian profile until
removed through normal UI. Cleanup is not part of the product change and is not
claimed as secure deletion.
