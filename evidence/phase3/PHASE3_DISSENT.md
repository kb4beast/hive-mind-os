# Phase 3 item 1 preserved dissent

- A digest check, process lock, and immediate recheck cannot provide a cryptographic
  filesystem compare-and-swap against a malicious uncooperative writer.
- Publication is atomic per file, not for the whole directory. Readers must treat the
  valid manifest as the commit marker.
- Normal read-only SQLite coordination may create or use empty WAL/SHM sidecars. The
  projector claims no logical canonical write, not zero operating-system
  coordination.
- Private projection receipts are protected by location, exact-content validation,
  and protocol. They do not have append-only SQLite triggers.
- Safe-public release can still expose approved low-entropy identifiers or digests.
  Independent release and subject binding reduce but do not erase correlation risk.
- `memory-record-v1` provides structured metadata and protected references, not a
  released human-readable summary. The item 1 pack is deliberately less useful than
  the later item 3 cognitive notes.
- Whole-plan conflict handling preserves one coherent manifest but delays unrelated
  updates.
- Ignored private completion receipts are the ownership anchor for future mutation.
  A clone without them can recognize an exact desired tree but must conflict rather
  than update a differing generated tree until a separately adjudicated adoption or
  migration path exists.
- Item 1 does not consume or acknowledge the Phase 2 outbox because existing messages
  were not routed to a brain projection destination.
- No Obsidian refresh, query, Graph, Bases, Canvas, federation, self-host, retrieval,
  completeness, usefulness, production-readiness, or superiority claim is made.
- Item 1 provides no automated cleanup. This avoids unsafe deletion but leaves
  deliberate manual or later-version migration work.

These dissenting constraints remain part of the implementation verdict and later
appeal record.

## Final preservation receipt

Final Curator `Aquinas`, Steward `Cicero`, and Judge `Ohm` reviewed exact candidate
`24e48933d7e4098002944b2cc5d73bfe9e3f1e3b`. The Judge adopted Phase 3 item 1
only while expressly retaining every constraint above. No dissent was resolved by
deletion, and none is converted into a support, completeness, production-readiness,
or superiority claim.

## Phase 3 item 2 preserved dissent

- Physical public/private files reduce read authority but do not provide encryption,
  operating-system access control, safe backups, or resistance to an attacker who can
  rewrite both code and files.
- The authentic release capability uses a process-local integrity seal. Persisted
  decision, actor, and lease references are durable provenance, not cross-process or
  external human identity authentication.
- Public record IDs, tenant/repository identities, timestamps, release references,
  and unkeyed source digests may allow correlation or membership inference even after
  an independent release.
- A safe-public disclosure cannot be made secret again in Git history, clones,
  caches, artifacts, or recipient systems. Supersession and tombstones preserve later
  truth; they do not prove revocation, deletion, or crypto-erasure.
- The private Foundation transaction and public release-store transaction are not one
  distributed atomic commit. Protected journaling and deterministic idempotency
  recover the tested crash window but do not create exactly-once external delivery.
- The public SQLite file is deterministic in logical released content, not guaranteed
  byte-for-byte identical across SQLite versions or filesystems. The generated open
  pack remains the deterministic byte artifact.
- Existing item-1 direct projection remains compatible but still requires read access
  to the mixed Foundation store. Only the new release-store path satisfies the item-2
  separation claim.
- Item 2 forbids non-null protected content and retrieval receipts instead of
  implementing an encrypted content vault or governed retrieval.
- One public store is bound to one tenant/repository. Broader tenant-key isolation,
  federation, portfolio memory, and self-host recursion remain deferred.
- No automated move, raw SQLite copy, withdrawal, cleanup, deletion, backup, or
  erasure command is provided.
- No HOME/domain notes, richer cognitive content, Bases/Canvas, Obsidian refresh or
  support, Inbox, watcher, plugin, Sync, usefulness, production-readiness, or
  superiority claim is made.
