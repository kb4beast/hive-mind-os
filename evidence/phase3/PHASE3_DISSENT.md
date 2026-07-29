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

## Phase 3 item 3 preserved dissent

- Cognitive notes organize already released metadata; they do not add a public prose
  body or prove that the pack is complete, useful, understandable, or sufficient for
  retrieval.
- Idea, evidence, court, run, and agent labels are deterministic views of
  `memory_kind`; they do not prove a canonical opportunity, evidence body, verdict,
  complete run timeline, activated agent, agent health, or scorecard.
- Telemetry notes contain released `resource` or `evaluation` memory metadata only.
  They are not canonical usage accounting and contain no token, cost, provider,
  invoice, trace, or effectiveness measurements. Unavailable is not zero.
- One-note-per-record avoids cross-release aggregation but may produce multiple notes
  about the same human concept. Entity aggregation and duplicate resolution remain
  deferred.
- Full SHA-256 filenames prevent path injection; hashing released low-entropy IDs is
  not anonymization and does not remove correlation or membership-inference risk.
- The cognitive namespace has its own file-at-a-time publication and externally
  placed recovery evidence. These controls do not provide a malicious-writer
  filesystem transaction, encryption, ACLs, safe backups, or secure deletion.
- Atomic no-overwrite installation requires short-lived, transaction-qualified
  sibling files in the generated namespace. A process or machine failure can expose
  those reserved dotfiles until exact-journal recovery; they are not manifest-owned
  output and should not be treated as human content.
- Windows no-delete handles close the tested prepared-file/junction race. Platforms
  without that lease retain atomic destination no-overwrite but do not claim safety
  against an uncooperative writer deliberately moving reserved transaction
  artifacts outside the namespace.
- No generated note is authoritative or a write-back/intake channel. Human edits are
  preserved as conflicts rather than silently adopted.
- No Bases/Canvas, Obsidian refresh or support, federation, self-host recursion,
  Inbox, watcher, plugin, Sync, retrieval, encryption/KMS, cleanup, deletion,
  activation, usefulness, production readiness, or superiority claim is made.

## Phase 3 item 4 — Obsidian view projection

- Bases implement a repository-owned subset of mutable, unversioned official
  documentation. No runtime Obsidian compatibility or refresh claim is made.
- The official Obsidian help repository has no detected reuse license. Only abstract
  format facts are used; no expressive example or template is copied.
- A Base can expose editable generated note properties. It is not a read-only or
  authoritative UI, and human edits correctly create item-3 drift/conflict.
- The released source supports agent-related and telemetry metadata, not agent
  scores/health or token/cost/value accounting. Unknown is not zero.
- Loop signals and quarantine inventory are absent from the admitted source.
  Item 4 emits no empty Base, count, or all-clear claim for either.
- The Canvas is fixed navigation and disclosure, not a causal graph, live War Room,
  playback, command surface, or completeness proof.
- File nodes targeting `.base` files are structurally valid JSON Canvas; how a
  pinned Obsidian build renders them remains an open evidence obligation.
- File-at-a-time publication and the malicious uncooperative-writer limitation
  remain the same dissent as item 3.
- The held item-3 lock excludes cooperating writers, and source identity is checked
  immediately before the item-4 manifest commit marker. An uncooperative writer can
  still mutate source after that final check; item 4 does not claim detection,
  rollback, or a cross-process filesystem transaction for that window.
- Base folder plus provenance filters rely on the receipt-owned item-3 namespace.
  Raw tenant/repository strings are intentionally excluded from expressions; the
  validated repository-identity digest is the scope binding. A separately spoofed
  vault file cannot enter that exact owned tree without item-3 drift, but runtime
  vault property-type behavior remains untested.
- Protected history has explicit finite bounds. At the 200,100-path ceiling the
  projector fails closed; no cleanup or compaction policy is authorized in item 4.
- Interrupted incomplete preparations are retained as content-addressed evidence.
  This avoids silent evidence loss but can consume protected-state capacity until a
  separately authorized retention/cleanup policy exists.
- Recovery with a fresh authentic same-scope authority preserves the original
  decision/actor/lease only as historical journal evidence. This proves restart
  liveness inside the current scope; it does not renew an expired lease or authorize
  a different tenant or repository.
- Partial content-digest evidence temporaries are explicitly unsealed bytes, not
  append-only evidence. Project recovery may discard them after proving their digest
  does not match their reserved name; check mode never does. The originating sealed
  transaction, preparation, or observed conflict remains the retry authority.
- Atomic directory no-replace support is limited to the tested Windows primitive and
  native Linux/macOS no-replace syscalls. Other operating systems fail closed.
- The Windows protected-state root limit is a conservative classic-path boundary,
  not a general long-path capability claim.

## Phase 3 item 5 — pinned Obsidian refresh

- The first runtime run refreshed correctly but Obsidian rewrote quoted Base YAML.
  That failed receipt is preserved; semantic equivalence does not satisfy managed
  byte ownership.
- The second run's immediate integrity check was false reassurance: Obsidian rewrote
  the Canvas about four minutes later. It is preserved as a second failed receipt,
  and future evidence must unload Canvas and survive a 300-second stability interval.
- The third run survived that interval but became non-promotable when subsequent
  YAML hardening changed production bytes. It remains a truthful passing receipt for
  its own subject, not evidence for the sealed final subject.
- Any repaired passing run covers only Obsidian Desktop `1.12.7` on Windows build
  `26200`.
- The run reused an existing Obsidian process and user profile. It does not prove
  clean-profile isolation or absence of every global preference interaction.
- The 15-second bound is a test observation deadline, not an Obsidian service-level
  guarantee.
- Automatic local refresh does not imply Git fetch integration, remote
  synchronization, Sync correctness, multi-device convergence, or conflict
  resolution.
- Base and Canvas panes expose interactive UI. Item 5 does not authorize editing,
  write-back, command execution, plugins, or Obsidian as an execution host.
- Fixture authority and `curator:item5-runtime` labels are synthetic test inputs.
  They do not prove independent Curator approval or grant production release
  authority.
- `.obsidian` and vault registration are local side effects. They remain outside
  product ownership and are not evidence of secure cleanup or deletion.
- No production-readiness, usefulness, user-value, cost, or superiority claim is
  made.
- The Judge's `adapt` permits only the two runtime-required interoperability-byte
  repairs. It does not relax item-4 semantics, namespace, filters, schemas,
  protocols, capabilities, authority, or future evidence burdens.
- Any relevant byte or evidence change invalidates the current review boundary and
  requires renewed independent verification and judgment.
