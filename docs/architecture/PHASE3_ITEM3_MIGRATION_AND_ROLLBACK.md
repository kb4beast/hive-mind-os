# Phase 3 item 3 migration and rollback

## Additive migration

1. Keep Generation Zero, the private Foundation store, the item-2 public release
   store, and the item-1 `hive-mind/generated` projection unchanged.
2. Select an existing verified same-scope public release store.
3. Select a dedicated cognitive protected-state root outside the repository and
   disjoint from the public store and other protected persistence roots.
4. Run cognitive `check`. It reports the desired state without creating either the
   repository namespace or protected state.
5. Run cognitive `project`. It creates `hive-mind/generated-cognitive` through
   staged, manifest-last publication.
6. Re-run `project` and `check` to prove unchanged deterministic state.
7. Rebuild in a clean repository root and compare the cognitive tree digest. Confirm
   the existing item-1 tree is byte-identical before and after item 3.

Example:

```powershell
python -m hive_mind_os.foundation.cognitive check `
  --public-store C:\public-tier\released-memory.sqlite3 `
  --repo C:\Repos\example `
  --protected-state C:\protected\cognitive-state `
  --tenant tenant-id `
  --repository-id repository-id

python -m hive_mind_os.foundation.cognitive project `
  --public-store C:\public-tier\released-memory.sqlite3 `
  --repo C:\Repos\example `
  --protected-state C:\protected\cognitive-state `
  --tenant tenant-id `
  --repository-id repository-id
```

Do not supply a private Foundation database, raw-copy SQLite files, adopt an
unreceipted namespace, or treat generated notes as canonical input.

## Failure and restart

- Wrong store type/version/digest/scope or corrupt public rows fail before output.
- Unsafe repository, namespace, public-store, or protected-state overlap fails
  before a lock or directory is created.
- A public store above 512 MiB fails before SQLite decode. Oversized strings, lists,
  records, notes, manifests, file counts, or total packs fail during bounded
  compilation.
- An interruption before durable journal publication leaves no admitted journal.
- A valid pending journal resumes only when transaction identity, desired paths,
  desired digests, source cursor, prior receipt chain, expected-prior plan, scope,
  and authority match exactly.
- A sealed older transaction completes under its recorded source cursor before the
  current snapshot is projected and receipted separately.
- Manual edits, missing or unmanaged files, links/reparse points, hardlinks, and late
  replacement races preserve observed bytes and produce typed conflict evidence.
- Transaction-qualified `.cognitive-prior-*` and `.cognitive-next-*` siblings are
  reserved, same-directory atomic-install artifacts. They are never manifest files
  and may be recovered only through the exact external protected journal.
- A sibling qualified to another transaction conflicts before replay. On Windows,
  no-delete handles prevent a final-window prepared-file or junction move before the
  no-overwrite link.
- The manifest is replaced last and remains the public commit marker.

## Rollback

Disable callers of the cognitive `project` and `check` module commands. Preserve:

- the canonical private Foundation database;
- the append-only public release store;
- item-1 and cognitive generated trees and manifests;
- protected journals, staged bytes, receipts, and conflicts;
- human-authored files outside managed namespaces; and
- court, audit, inventory, dissent, test, build, and delivery evidence.

No item-3 command deletes, withdraws, relabels, moves, imports, or rewrites canonical
or human data. Cleanup, adoption, deletion, revocation, backup, encryption, or
erasure requires a separate exact-target court and migration.
