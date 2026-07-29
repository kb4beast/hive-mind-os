# Phase 3 item 1 migration and rollback

## Additive migration

1. Keep Generation Zero and the Phase 2 foundation selected and unchanged.
2. Create or use an existing Phase 2 Foundation database outside the public pack.
3. Record memory normally; default sensitivity remains private.
4. Obtain an independent, subject-digest-bound safe-public release before a record is
   eligible.
5. Run the opt-in module command against one explicit tenant/repository scope.
6. Review the typed result and the generated manifest before committing public files.
7. Use `check` in automation to detect drift without writing.

No backfill, dual write, outbox acknowledgement, watcher, or automatic activation is
performed by this item.

## Failure and recovery

- Missing, wrong-owner, newer, malformed, or corrupted stores fail before public
  filesystem mutation.
- An interruption leaves a private journal and staged desired bytes. The next exact
  projection resumes only when every observed digest is either the expected prior or
  exact desired digest.
- Manual edit, delete, rename, unmanaged file, link/reparse target, or stale manifest
  produces a conflict. Existing public bytes and the prior manifest remain.
- A committed manifest is the only new-tree commit marker.
- The projector never guesses that a partial tree succeeded and never acknowledges
  Phase 2 outbox delivery.

## Rollback

Disable all callers of `python -m hive_mind_os.foundation.brain`. This returns the
system to the unchanged Generation Zero plus opt-in Phase 2 foundation behavior.

Preserve:

- the canonical Foundation database and WAL history;
- the last public pack and manifest;
- private transaction, recovery, and conflict receipts;
- human files outside `hive-mind/generated`;
- court records, dissent, audit ledger, and test receipts.

Item 1 intentionally provides no recursive delete command. If removal is required,
validate the exact repository root, manifest schema/identity, every managed path, and
every current digest before a separately authorized cleanup. Never remove unknown
files, human notes, canonical state, or conflict evidence.
