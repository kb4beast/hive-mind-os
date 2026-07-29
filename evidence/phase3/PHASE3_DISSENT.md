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
