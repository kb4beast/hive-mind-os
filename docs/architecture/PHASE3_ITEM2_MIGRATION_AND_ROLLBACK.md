# Phase 3 item 2 migration and rollback

## Additive migration

1. Keep Generation Zero, the Phase 2 Foundation store, and item-1 direct projection
   unchanged.
2. Place the existing private Foundation database outside the repository/vault and
   quiesce any manual relocation before item 2. This implementation does not move it.
3. Select a new or existing same-scope public release-store path that does not share
   the private or protected root.
4. Select a protected release-state root and separated projection-state root outside
   the repository.
5. Run the explicit `release` command. It validates the complete source snapshot and
   appends only eligible strict public envelopes.
6. Run `project-separated` and compare its manifest/tree digest with the still
   supported item-1 direct projection before switching a caller.
7. Use `check-separated` for read-only drift checks.

Example:

```powershell
python -m hive_mind_os.foundation.brain release `
  --store C:\protected\foundation.sqlite3 `
  --public-store C:\public-tier\released-memory.sqlite3 `
  --repo C:\Repos\example `
  --protected-state C:\protected\release-state `
  --tenant tenant-id `
  --repository-id repository-id

python -m hive_mind_os.foundation.brain project-separated `
  --public-store C:\public-tier\released-memory.sqlite3 `
  --repo C:\Repos\example `
  --protected-state C:\protected\projection-state `
  --tenant tenant-id `
  --repository-id repository-id
```

The public store is a release projection, not canonical memory. Do not raw-copy an
open SQLite main file, WAL, or SHM sidecar. Do not relabel legacy records, acknowledge
the Phase 2 `local` outbox, or treat old generated files as authenticated release
receipts.

## Failure and restart

- Source ownership, shape, scope, integrity, release provenance, quarantine, or
  protected-field failure stops before a public envelope is appended.
- A crash before the public transaction leaves a protected journal and no public
  batch.
- A crash after the public commit leaves the same journal. Retry verifies exact
  deterministic rows, writes the protected completion receipt, and removes the
  journal. Pending older journals are completed before a changed current Foundation
  snapshot is released.
- A reused source record with different public bytes fails closed.
- Wrong/newer/corrupt public stores, wrong scopes, links/reparse/hardlinks, unsafe
  roots, or source/public overlap fail closed.
- Separated projection retains item 1's manifest-last recovery and conflict
  preservation while keeping all recovery evidence outside the repository.

## Rollback

Disable callers of `release`, `project-separated`, and `check-separated`. Continue
the unchanged item-1 direct command if required.

Preserve:

- the canonical Foundation database and its WAL/outbox history;
- the append-only public release store;
- the last generated public pack and manifest;
- protected release/projection journals, receipts, conflicts, and staged evidence;
- human-authored files outside the generated namespace; and
- court, audit, inventory, dissent, test, build, and delivery receipts.

No item-2 command deletes, withdraws, rewrites, relabels, moves, or raw-copies data.
A later cleanup, revocation, erasure, backup, or encrypted-content migration requires
its own adjudicated exact-target procedure. Public disclosure cannot be made secret
again by a tombstone.
