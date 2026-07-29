# Phase 3 item 4 migration and rollback

## Additive migration

1. Leave item-1 `generated`, item-3 `generated-cognitive`, and all prior protected
   state unchanged.
2. Finish or resolve any item-3 pending transaction with the item-3 projector.
3. Verify item 3 is exact, receipt-owned, and conflict-free.
4. Choose an item-4 protected-state root disjoint from the repository and every
   source/protected persistence root. On Windows its absolute path must be no more
   than 110 characters.
5. Run item-4 `check`; confirm it creates nothing.
6. Run item-4 `project`.
7. Repeat `project` and `check`; confirm unchanged deterministic state.
8. Reconstruct in a clean repository root and compare item-4 bytes.
9. Confirm item-1 and item-3 trees are byte-identical before and after.

Module command shape:

```powershell
python -m hive_mind_os.foundation.cognitive_views check `
  --repo C:\Repos\example `
  --cognitive-protected-state C:\protected\cognitive-state `
  --protected-state C:\protected\cognitive-view-state `
  --tenant tenant-id `
  --repository-id repository-id
```

Use `project` in place of `check` only with authentic scoped write authority.

## Failure and restart

- Wrong scope, source drift, pending item-3 recovery, corrupt receipts, links,
  unmanaged files, or unsafe overlap fail before item-4 mutation.
- Check mode performs no recovery and writes nothing.
- Project mode holds the item-3 lock, then the item-4 lock.
- A preparation journal is durable before desired-byte staging. Complete
  preparations are atomically sealed; incomplete preparations are preserved under
  content-addressed abandonment evidence with an exact receipt.
- Final receipts/conflicts/abandonment records are fsynced under an unsealed
  content-digest temporary and atomically renamed without replacement. Project mode
  completes a full temporary or discards a partial unsealed temporary and retries;
  check mode reports it without mutation.
- A valid sealed item-4 transaction completes under its recorded historic source
  evidence before a newer item-3 snapshot is receipted separately. The recovering
  caller supplies fresh authentic authority for the same tenant/repository; expired
  historic lease identity is evidence, not a restart requirement.
- Reserved transaction siblings are admitted only by the exact protected journal.
- A verified two-name hardlink window is completed only when next and destination
  are the same exact desired file.
- Manual edits and late destination writers are preserved as typed conflicts.
- Manifest-last remains the public commit marker.
- Source identity is revalidated immediately before manifest install while the
  item-3 lock is held. Mutation by an uncooperative writer after that validation is
  residual dissent, not a claimed rollback guarantee.
- Every protected receipt/conflict record is validated, and post-recovery receipts
  must form the single chain reachable from the installed manifest.
- The item-3 transaction root is type/link checked before enumeration, and repeated
  historic source-chain validation reuses only nodes already proven in the same
  bounded run.
- Native no-replace sealing is supported on Windows, Linux, and macOS; an unsupported
  platform fails closed before substituting a clobbering rename.

## Rollback

Stop invoking item-4 module commands. Preserve:

- item-1 and item-3 generated trees;
- the item-4 generated tree and manifest;
- all source and item-4 protected receipts, journals, staged bytes, and conflicts;
- all content-addressed incomplete-preparation receipts and preserved bytes;
- source register, court, audit, inventory, and dissent; and
- all human-authored files.

No item-4 command deletes, cleans up, adopts, moves, imports, activates, or rewrites
human or prior generated state. Opening the repository as an Obsidian vault,
launching Obsidian, runtime refresh, backup, deletion, or migration requires separate
authority.
