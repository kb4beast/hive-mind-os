# Phase 3 append-only audit ledger

## `P3-AUDIT-001` — exact base and eligibility

- Base/head inherited from draft PR #31:
  `94e67cde15fa8a75d92561384241f0419c9f589b`
- Branch created:
  `codex/phase3-open-brain-obsidian-projection`
- PR #31 remained open, draft, unmerged, cleanly stacked on PR #29.
- Phase 3 item 1 was the exact next eligible objective.
- No PR was merged and `main` was not modified.

## `P3-AUDIT-002` — independent architecture reconstruction

Curator/security Expert `Kuhn` and Architect/Cross-Examiner/Steward `Planck`
independently reread the handoff, ADR-019, ADR-021, Phase 1 contracts and courts,
Phase 2 store/contract/court, and exact base.

Both rejected:

- the writable Foundation constructor as a projection read boundary;
- raw record IDs as Windows paths;
- payload/storage dumps;
- modification of the frozen `hive-mind` parser;
- wall-clock/prior digest in deterministic public bytes;
- Obsidian dependency or broader Phase 3 claims; and
- self-asserted implementation sufficiency.

Their accepted narrow shape is reflected in ADR-022 and
`PHASE3_PROJECTION_CONTRACT.md`.

## `P3-AUDIT-003` — source and dependency disposition

No new source or dependency was admitted. Phase 1 Obsidian source admission remains
binding by reference only; no third-party help text or template was copied.

Phase 2 outbox consumption was explicitly deferred because accepted historical
messages use generic destination `local`. The item 1 projector neither changes nor
acknowledges them. Private Phase 3 transaction/conflict receipts make the actual
projection claim without relabeling prior evidence.

## `P3-AUDIT-004` — initial implementation characterization

The first focused candidate added:

- a read-only consistent public-memory snapshot;
- six separate strict Phase 3 projection schemas;
- safe-public metadata-only compilation;
- portable hashed note paths and eligible-set cursor;
- a dedicated module CLI with project/check modes;
- scope-bound projection authority;
- bounded safe rendering;
- same-filesystem staging, manifest-last atomic replacement, recovery, and conflict
  preservation; and
- a separately generated Phase 3 inventory.

Initial focused receipts before exact-candidate sealing:

- `12 passed` in `tests/test_phase3_open_brain.py`;
- `41 passed, 23 subtests passed` across Phase 2 plus Phase 3 focused suites;
- Ruff focused paths: pass;
- Pyright focused paths: 0 errors.

These are development receipts, not the final exact-head promotion evidence.

## `P3-AUDIT-005` — pre-commit local reconstruction

The complete current tree was reconstructed locally on both installed interpreters:

- Python 3.12.10: `469 passed, 3 skipped` in 931.36 seconds;
- Python 3.14.4: `469 passed, 3 skipped` in 909.53 seconds;
- full Ruff: pass;
- full Pyright: 0 errors and 0 warnings;
- focused Phase 3 suite after inventory regeneration: `12 passed`;
- deterministic Phase 3 inventory:
  `sha256:ea4e1323dba0ea76111f5008805d69bf08d22d5e1ae45f664a1dbc45ac4fe563`;
- deterministic fixture tree:
  `sha256:758b20b66c095ac37bfd38e7ac4cd6d5b4dbd20ed4f9e0eed8fd210cd57dbb58`;
- wheel:
  `hive_mind_os-0.6.0-py3-none-any.whl`,
  SHA-256 `83c79e1e163c66ed7cf262d612c3744efcd12eb0198ab0fc5a31bb1ab4704a41`;
- clean target install/resource verification: 20 legacy schemas, 17 Phase 2
  schemas, 6 Phase 3 schemas, 9 generated candidates, 8 canonical sources,
  48 package files, 68 legacy resources, 108 total resources, and resource-set
  digest `abdf317e8af93968be889d0247aa149cb5a9ce32d4220b3429e2c8771364afe9`;
- installed-wheel module CLI help and Phase 3 catalog validation: pass.

Python 3.11, CodeQL, secret scan, dependency/license review, SBOM, and provenance
remain pending exact-push/PR CI. No green label is substituted for those receipts.

## `P3-AUDIT-006` — first exact-push static remand

Candidate `2f8992195e5b781fd3262c772d621e47466d675c` was pushed and opened as
stacked draft PR #32. Both the push run `30459931442` and PR run `30459963393`
failed `static-and-type-checks`.

Linux Pyright 1.1.411 rejected direct access to the Windows-only
`stat_result.st_file_attributes` at `foundation/brain.py:153`:

```text
Cannot access attribute "st_file_attributes" for class "stat_result"
```

Windows local Pyright had passed because its platform model includes that field.
This is a real cross-platform typing defect, not a waived runner difference. The
candidate is remanded. Remediation uses portable `getattr` access for both the
Windows stat attribute and reparse flag while retaining runtime reparse detection.
Fresh exact-head CI and independent reconstruction remain required.

## `P3-AUDIT-007` — repaired-head CI receipt before independent runtime remand

Candidate `3aa3a8a3c7f311eadec8885e04c908f6f71ac787` repaired the portable
Windows reparse typing defect. Exact push run `30460118148` and pull-request run
`30460123065` both completed successfully:

- Python 3.11, 3.12, and 3.14 complete suites: pass;
- Ruff and Pyright: pass;
- CodeQL and secret scan: pass;
- pull-request dependency/license review: pass; the push-context copy was expected
  to skip;
- wheel build and isolated resource verification: pass;
- SPDX SBOM generation and push provenance attestation: pass.

The push artifact `8727206074` contained wheel SHA-256
`88452ab4267c73ee48a94692f6b0d05c9b510c4505f67b3234117d3dd75ccec6`
and SBOM SHA-256
`447fc9c5a0e41587608d8936c475d67187d654c49f5dd4e39cacdbb5dc9d14ea`.
This green receipt did not promote the candidate because independent runtime review
remained a separate burden.

## `P3-AUDIT-008` — independent Curator and Steward runtime remand

Curator `Kuhn` and Steward `Planck` independently reconstructed exact candidate
`3aa3a8a3c7f311eadec8885e04c908f6f71ac787` without edits. Their probes remanded:

- momentary empty-WAL inference selecting SQLite immutable mode;
- an unmanaged file created after preflight but before the process lock;
- a pack-root junction swap and nested protected-state junction redirecting writes;
- stale transaction state after an already-published completion receipt;
- a hardlink to the canonical database inside the output root;
- valid, invalid, and forged unreceipted manifest ownership;
- untyped exit-2 command output; and
- court language that overstated committed adversarial test coverage.

These were reproduced contract failures, not waived recommendations. The adverse
candidate and its otherwise-green CI remain preserved.

## `P3-AUDIT-009` — runtime remand remediation

The remediation:

- always uses normally coordinated SQLite read-only mode;
- revalidates exact generated namespace, pack/state roots, nested state paths, and
  database same-file overlap under the process lock;
- requires a private completion receipt to use a prior manifest as mutation
  authority while allowing an unreceipted exact tree to remain unchanged;
- treats manifest edits and forged ownership as conflicts;
- cleans stale transaction state after verifying a completed receipt;
- adds a seventh strict schema for exit-2 failure results; and
- adds regression tests for editor races, manifest ownership, stale-receipt cleanup,
  hardlinks, linked state, and missing/renamed managed paths.

The architecture, migration, operator documentation, dissent, and court wording were
corrected to match the narrower implementation. Fresh exact-head inventory, complete
verification, independent reconstruction, and Judge disposition remain required.

## `P3-AUDIT-010` — scoped snapshot integrity boundary

Final Builder review found that `verify_integrity(tenant_id, repository_id)` scoped
records, relations, repository identity, and opportunity keys but inspected outbox
rows from every repository. That could make one repository's projection fail with
identifiers from another repository. The outbox-message query is now joined to the
requested source-record scope, and attempt/acknowledgement checks filter their
immutable tenant/repository columns. A regression inserts a malformed message only
for a second repository and proves the first scope stays clean while the second
reports the issue.

Post-change focused receipts on Python 3.14:

- Phase 2 plus Phase 3: `51 passed, 23 subtests passed`;
- full Ruff: pass;
- full Pyright: 0 errors and 0 warnings.

The generated inventory was refreshed. Fresh exact-head CI and independent review
supersede all prior candidate-level promotion receipts.

## `P3-AUDIT-011` — first boundary-remediation CI test-portability remand

Exact candidate `e2e5e8456c726fe2f1b0cc476ece1565330f1c0f` passed static/type,
CodeQL, secret, dependency/license, wheel/resource, SBOM, and provenance jobs in
push run `30461723209` and pull-request run `30461726608`, but all Python
3.11/3.12/3.14 jobs failed.

The new linked-path regressions correctly proved that no redirected write occurred.
Their cleanup used `Path.rmdir()`, which removes a Windows directory junction but
raises `NotADirectoryError` for a POSIX directory symlink. This is a portable-test
defect and remains an exact-candidate remand. Cleanup now uses `unlink()` for
symlinks and `rmdir()` for Windows junctions. Fresh exact-head matrix evidence is
required.

## `P3-AUDIT-012` — scoped integrity orphan remand

Independent Curator review of `404b0f82c91e4fe3e2609e1a7d049f7a5f567ecd`
found that the new inner join correctly isolated valid outbox rows but silently
omitted an outbox row whose source record was missing. The prior global check had
reported that corruption, so this was an evidence-control weakening and the candidate
was remanded irrespective of CI.

The repair retains scoped valid-row checks and adds a separate global orphan
existence check whose issue text contains no record or message identifier. A
regression inserts an offline foreign-key-disabled orphan and proves integrity fails
closed without exposing either identifier. Fresh inventory, exact-head CI, and
independent review remain required.

The Curator also showed that filtering attempts and acknowledgements by their own
declared scope could hide a row moved away from its immutable source scope. Delivery
rows are now selected through message-to-source joins and their declared scope is
still compared with that source. Separate generic checks retain fail-closed handling
for orphaned delivery rows without identifier disclosure. Focused Phase 2 plus Phase
3 verification after both repairs: `52 passed, 23 subtests passed`; Ruff and Pyright
pass.

## `P3-AUDIT-013` — recovery-window and generated-bound remand

Independent Steward review of `126c3e48f9374224aa8e8c8c356877fe3d385f24`
reproduced two uncovered interruption windows:

- failure immediately after manifest replacement left a valid desired manifest but
  no receipt, and restart rejected the persisted journal because it recomputed a new
  prior-manifest digest;
- failure after staging-directory creation but before journal publication left
  unrecognized staging that could not be rebuilt.

Independent Curator review also found that the 16 MiB manifest bound was checked only
when reading an existing manifest, not before first publication.

The remediation validates a recovering journal's immutable transaction identity,
authority, desired paths, and desired digests while retaining its original
expected-prior digests for replay. A safe unjournaled transaction subtree is treated
as abandoned private staging and rebuilt. Generated manifest bytes are now bounded
before entering the desired tree. Focused regressions cover all three cases; Phase 3
now has `23 passed` locally. Fresh inventory, exact-head CI, and independent
reconstruction remain required.

The Steward additionally found that a third digest appearing between the final
namespace scan and one file replacement raised a generic failure instead of the
contracted conflict. That branch now raises the internal typed conflict signal; the
caller preserves desired bytes and a conflict receipt without overwriting the late
human edit. A deterministic regression injects that exact replacement window.
Combined Phase 2 plus Phase 3 focused verification is now `56 passed, 23 subtests
passed`.

## `P3-AUDIT-014` — protected-state hardlink remand

Independent Curator review of `b2aff7361d1fd849a1f55bdfe5eec3705e7097ca`
hardlinked an external regular file to the protected projection lock. The projector
treated it as an ordinary file and changed the external bytes while acquiring the
lock. This violated repository confinement even though all symlink, junction, and
reparse probes passed.

Protected-state traversal, ownership-receipt admission, lock acquisition, and
durable writes now reject an existing regular file whose link count is not exactly
one. A regression proves a hardlinked external lock remains byte-identical and no
manifest is published. Fresh inventory, exact-head CI, and independent reconstruction
remain required.

## `P3-AUDIT-017` — bounded hostile-file inspection remand

Independent Steward review of `de36437e7a3dd1289d2227bc423ab55233a8bd26`
showed that the existing-manifest size check followed an unbounded `read_bytes()`,
and that generated-file comparisons had the same allocation weakness. A hostile or
sparse file in the public pack could therefore consume memory before the projector
classified it as a conflict.

All private state documents now use a stat-first bounded reader that verifies a
single-link regular file through the open handle. Public generated files use
constant-memory streaming SHA-256 with pre-read and post-read identity and size
checks. Manifest reads are bounded to `MAX_MANIFEST_BYTES`; every other generated
file is bounded to `MAX_NOTE_BYTES`. Regressions create sparse over-limit manifest
and note files while making every `Path.read_bytes()` call fail, proving the
projector reports typed conflicts without an unbounded read. Fresh inventory,
exact-head CI, and independent reconstruction remain required.

## `P3-AUDIT-016` — corrupt and invalid-store typed-command remand

Independent Curator review of `de36437e7a3dd1289d2227bc423ab55233a8bd26`
showed that an existing non-SQLite store raised an uncaught
`sqlite3.DatabaseError`. The module command therefore emitted no strict failure
document even though the adopted command contract assigns integrity failures typed
status `failed` and exit 2.

The CLI boundary now normalizes `sqlite3.Error` alongside the already handled
operational projection failures. The public snapshot boundary also normalizes its
expected plain `RuntimeError` shape, ownership, and schema-integrity failures into
`ProjectionError`, preserving a single library contract. Corrupt-store and
valid-SQLite/wrong-schema-digest regressions validate emitted documents against
`brain-failure-v1`, confirm exit 2, and preserve the diagnosed class or cause in the
bounded error field. Fresh exact-head evidence remains required.

## `P3-AUDIT-015` — conflict-staging recovery remand

Independent Steward review of `b2aff7361d1fd849a1f55bdfe5eec3705e7097ca`
interrupted private desired-byte preservation before the conflict receipt was
published. A truncated staged file then made every identical retry fail instead of
rebuilding the deterministic conflict evidence.

A conflict identity without its receipt is now treated as abandoned private staging:
after link/path validation, that conflict subtree is removed and rebuilt from the
already compiled desired bytes. The observed human file remains untouched. A focused
regression interrupts the staging write, retries, verifies a typed conflict receipt,
and proves the human bytes remain exact. Fresh exact-head evidence is required.

The Steward also interrupted direct `transaction.json` publication, leaving a
truncated journal that was indistinguishable from a published journal. Transaction
journals now use a durable temporary file followed by atomic replacement. A partial
temporary journal is covered by the already-adopted unjournaled-staging rebuild
rule; a regression proves retry commits and then becomes unchanged.

## `P3-AUDIT-018` — exact-candidate delivery judgment

Implementation candidate
`24e48933d7e4098002944b2cc5d73bfe9e3f1e3b` remained a clean, draft, open,
mergeable PR #32 head based exactly on PR #31 head
`94e67cde15fa8a75d92561384241f0419c9f589b`. PRs #28, #29, and #31 remained
open and unmerged.

Builder local verification:

- complete repository suite: `490 passed, 3 skipped, 1781 subtests passed`;
- focused Generation Zero plus Phase 1–3: `69 passed, 23 subtests passed`;
- Ruff: pass;
- Pyright: 0 errors and 0 warnings.

Exact push run `30465040651` and pull-request run `30465050020` both completed
successfully. Together they verified Python 3.11, 3.12, and 3.14, Ruff, Pyright,
CodeQL, secret scan, dependency/license review, wheel installation and packaged
resources, SPDX SBOM generation, and provenance. Push artifact `8729181702`
contained:

- `hive_mind_os-0.6.0-py3-none-any.whl`,
  SHA-256 `c2db874c61be52233e1edac6dfdcbc500390cca71196c08009a0bd3952c08256`;
- `hive-mind-os.spdx.json`,
  SHA-256 `0014ac9cfe8155eecc52df446c99a1a9a5e94fecf4984bf037ed37f27f684872`.

Sigstore/SLSA verification named both subjects and bound the source, workflow, and
build configuration to the exact candidate SHA.

Final Curator `Aquinas` independently reconstructed `73 passed, 27 subtests`, Ruff,
Pyright, corrupt and valid-but-invalid store failures, hostile sparse-file bounds,
determinism, inventory, stack, privacy, compatibility, and both exact CI runs, then
returned `ACCEPT`. Final Steward `Cicero` separately reconstructed `73 passed, 27
subtests`, the Phase 2–3 focused set, recovery, confinement, conflict preservation,
typed failures, stack, compatibility, and both exact CI runs, then returned `ACCEPT`.

Judge `Ohm` independently inspected the actual 27-file diff and governing evidence,
reconstructed `75 passed`, Ruff, Pyright, inventory
`sha256:5ecae209c32b6460f1e1935512c90d44fe2ab96c1de217fcc4e5857137701e74`,
fixture tree
`sha256:758b20b66c095ac37bfd38e7ac4cd6d5b4dbd20ed4f9e0eed8fd210cd57dbb58`,
frozen `131/33/13/304` compatibility, seven packaged projection schemas, exact CI,
artifact hashes, and provenance, then issued `ADOPT` for Phase 3 item 1 only with no
remand.

All dissent remains preserved. Phase 3 items 2–8 remain deferred by sequence and
scope. No PR was merged, no runtime was activated, and `main` was not modified.

## `P3-ITEM2-AUDIT-001` — exact base, stack, and pre-change reconstruction

Phase 3 item 2 began on
`codex/phase3-public-private-memory-separation` at exact PR #32 head
`7f7013c99d86bbd34f966b902bb873cf5c10d740`. PR #32 remained open, draft,
and based on exact PR #31 head
`94e67cde15fa8a75d92561384241f0419c9f589b`. PRs #28, #29, #31, and #32
remained open and unmerged; remote `main` remained
`b032a9f32f48889e0889fae8d6dd04eb03f46b63`.

The actual stacked PR metadata, ancestry, file lists, and complete item-1 code diff
were inspected. Parent push run `30466001604` and PR run `30466010066` were
independently confirmed successful at exact `7f7013c` across Python 3.11/3.12/3.14,
Ruff, Pyright, CodeQL, secret scan, dependency/license review, wheel/resource
verification, SBOM, and provenance.

Before item-2 code, 16 focused Generation Zero, Phase 1, Phase 2, and Phase 3
characterization tests passed from the exact source tree. The frozen
`131/33/13/304`, 17 Phase 2 schemas, seven item-1 schemas, item-1 fixture tree, and
committed inventories were reproduced.

## `P3-ITEM2-AUDIT-002` — separate court and independent design remand

Court `P3-MEMORY-SEPARATION-002` was opened before implementation.

- Explorer/Clerk `/root/item2_explorer` proved item 1 was a logical filter over one
  physically mixed private database and selected a separate public persistence
  artifact as the smallest missing capability.
- Architect/Cross-Examiner `/root/item2_architect` rejected path-only separation and
  selected a one-scope append-only public release store plus a projector that never
  opens Foundation.
- Privacy/security Expert `/root/item2_privacy_expert` independently remanded the
  initial path-only proposal. External placement was necessary but insufficient;
  public-only envelopes, split receipts, correlation controls, migration evidence,
  and honest deletion limits were required.

No external source or dependency was admitted. Encryption, secure deletion,
crypto-erasure, ACL, backup destruction, and malicious-writer claims remain blocked
without separately pinned sources and tests.

## `P3-ITEM2-AUDIT-003` — bounded implementation candidate

The initial item-2 slice adds:

- three separately catalogued strict item-2 schemas;
- an immutable one-scope `PublicMemoryReleaseStore` with independent ownership,
  schema digest, append-only triggers, and deterministic release identities;
- a one-way `foundation.public-memory.release` transformation from one verified
  Foundation snapshot;
- strict public envelopes with protected content and retrieval receipts denied;
- private external release journals and completion receipts with post-public-commit
  restart recovery;
- separated projection from the public store with external private projection state;
- dedicated `release`, `project-separated`, and `check-separated` module commands;
  and
- an item-2 inventory proving exact item-1 tree parity and no in-repository private
  projection state.

The Phase 2 database/schema, 17 Phase 2 schemas, seven item-1 schemas, Generation
Zero selectors/facades/prompts/stores, and 13 `hive-mind` parser contracts are
unchanged.

Development receipts before exact-candidate sealing:

- item-2 focused suite: `10 passed`;
- combined item-1/item-2 focused suite after the brain-state refactor:
  `39 tests` with only the expected stale-inventory failure;
- regenerated item-1 inventory check plus item-2 suite: `11 passed`;
- compileall and diff whitespace checks: pass.

These development receipts are not final delivery evidence. Full multi-version,
security/supply-chain, independent reconstruction, and judgment remain required.

## `P3-ITEM2-AUDIT-004` — independent remand and bounded repair

Independent pre-commit Curator and Steward reviews both returned `REMAND`. Their
reproductions found a generic envelope-append admission bypass, a changed-snapshot
recovery gap, unsupported newer-store admission, unbounded public-store enumeration,
and public/protected persistence overlap.

No finding was waived and no policy or test was weakened. The repaired candidate:

- removes the public append API and requires the verified Foundation
  materialization path;
- uses bounded self-contained journals to finish older pending releases before a
  newer snapshot;
- binds source record/digest entries and the exact allowlist policy in protected
  receipts;
- rejects unsupported store versions before read admission;
- bounds row enumeration before allocation; and
- rejects bidirectional public/protected persistence overlap.

Sixteen item-2 regressions cover the original slice plus the remands. The latest
focused item-2 run passed 15 functional tests with only the intentionally stale
inventory characterization, and the regenerated inventory characterization then
passed. Full end-to-end, multi-version, supply-chain, and final independent verdicts
are explicitly deferred to the later final-system check at user direction.

## `P3-ITEM3-AUDIT-001` — supplied base and bounded objective

Phase 3 item 3 began on `codex/phase3-stable-id-cognitive-notes` from supplied PR
#33 branch tip `40a508b6b1bfb4a8624cf1ef8169384d32a39d44`. The user-owned edit to
`docs/NEXT_SESSION_HANDOFF_PUBLIC_PRIVATE_MEMORY.md` was preserved and was not
treated as Builder work. `main` was not checked out or modified.

The eligible objective was limited to HOME, idea, evidence, court, run, agent, and
telemetry notes with stable IDs and properties. Bases/Canvas, Obsidian refresh or
support, federation, self-host recursion, Inbox/import, plugins, watchers, Sync,
retrieval, protected-content bodies, encryption/KMS, cleanup/deletion, activation,
usefulness, production readiness, and superiority remained deferred.

## `P3-ITEM3-AUDIT-002` — independent discovery, architecture, and testimony

Court `P3-COGNITIVE-NOTES-003` opened before code implementation.

- Explorer `/root/explorer` proved that the item-2 public envelope supports
  metadata navigation but no truthful rich prose, court verdict, agent scorecard, or
  raw usage accounting. The Explorer required path-independent identity, additive
  schemas, public-store-only operation, bounded total files, and installed-resource
  evidence.
- Architect `/root/architect` selected an independent
  `hive-mind/generated-cognitive` namespace, an exhaustive one-record/one-note
  mapping, eight separate contracts, external protected state, manifest-last
  recovery, and opt-in module commands.
- Integrator/Optimizer witness `/root/integrator_optimizer` confirmed the frozen
  `131/33/13/304` and 17/7/3 boundaries, required telemetry to distinguish
  unavailable from zero, and rejected usefulness or superiority claims without
  outcome evidence.

No new external source, dependency, template, or copied code was admitted. ADR-024,
the item-3 contract, migration/rollback record, preliminary court, and appended
dissent preserve the adopted and rejected alternatives before implementation.

## `P3-ITEM3-AUDIT-003` — bounded implementation candidate

The Builder candidate adds an opt-in public-store-only cognitive projector, eight
strict packaged schemas, deterministic HOME and one-record/one-note mapping across
six domain folders, domain-separated stable IDs, a separate
`hive-mind/generated-cognitive` namespace, exact manifests and ownership receipts,
typed conflicts/failures/results, external protected journals/staging, and
manifest-last restart recovery. It does not change the frozen root/package APIs,
root CLI parsers, Phase 2/item-1/item-2 schemas, item-1 output, or dependencies.

The inventory reconstructs the fixture with the private Foundation store unavailable,
records all eight installed schema digests, preserves `131/33/13/304` and 17/7/3,
reports six admitted records and seven stable notes including HOME, and explicitly
records usage accounting as unavailable.

## `P3-ITEM3-AUDIT-004` — independent cross-examination and repair

Cross-Examiner `/root/cross_examiner` issued a remand for junction write-through,
missing typed conflict evidence, absence of a total public-store bound, ambiguous
changed-snapshot recovery, lax result counts, an unvalidated HOME document, and
insufficient adversarial tests.

The remediation validates a dedicated HOME contract, makes result counts exhaustive,
rejects public stores above 512 MiB before decode, validates every managed ancestor
before writes, preserves typed conflict documents externally, and specifies that a
sealed prior transaction completes and is receipted before the current snapshot.
Regressions cover control/bidirectional text, junction confinement, changed
snapshots, staged-manifest tampering, abandoned staging, completed stale state,
scope/overlap, read-only behavior, stable IDs, all memory kinds, and strict catalogs.

Steward `/root/steward` then exercised narrower publication and receipt-history
windows. The repairs:

- install desired bytes with an atomic no-overwrite hardlink after preserving the
  exact prior generated file in a transaction-qualified sibling;
- catch both recovery-time and fresh-publication late writes as typed conflicts;
- validate staged manifests and exact expected-prior plans before replay;
- validate the complete current manifest plan and historical receipt chain;
- reject extra, missing, cyclic, over-bound, corrupt, or no-op receipt operations;
- traverse up to the explicit receipt-history bound iteratively rather than through
  the Python call stack; and
- recover the manifest-last hardlink window before ordinary manifest admission.

The same-directory `.cognitive-prior-*` and `.cognitive-next-*` files are explicitly
recorded in ADR-024, the contract, migration/rollback record, and dissent as reserved
short-lived atomic-install artifacts. Durable journals, desired bytes, receipts, and
conflicts remain in the disjoint external protected-state root.

Renewed Cross-Examination then found three final-window defects: a Windows
junction/source move between validation and hardlink, an unrelated reserved sibling
detected only after partial replay, and admission of a schema-invalid existing
conflict receipt. The final repair holds Windows no-delete handles on the managed
root, destination parent, and prepared file during the final operation; revalidates
ancestry and parent identity; preflights all reserved siblings before replay; and
schema-validates existing conflict evidence before comparison. Independent reruns
confirmed typed conflict evidence, no external generated file or completion receipt,
no pre-conflict manifest mutation, preserved human bytes, and fail-closed malformed
conflict evidence. The cross-platform malicious uncooperative-writer limitation is
explicit in ADR-024, contract, migration, and dissent.

## `P3-ITEM3-AUDIT-005` — exact focused verification

On the final pre-judgment candidate:

- Phase 2 plus Phase 3 items 1–3: `101 passed, 23 subtests passed`;
- Pyright: `0 errors, 0 warnings, 0 informations`;
- Ruff: passed;
- exact inventory characterization: passed; and
- diff whitespace check: passed.

The adversarial item-3 suite includes a 1,051-receipt history above Python's ordinary
recursion limit, exact historical-plan corruption, a both-null no-op operation,
forged expected-prior journal, corrupt staged manifest, post-manifest interruption,
manifest hardlink crash window, late human write, junction recovery, public-store
byte bound, hostile rendered text, final-window junction/source movement, unrelated
transaction siblings, and malformed existing conflict evidence.

Full multi-version repository CI, CodeQL, secret/dependency/license review,
wheel/resource installation, SBOM/provenance, activation, and final-system
superiority evidence remain deferred exactly as directed by the supplied handoff.

## `P3-ITEM3-AUDIT-006` — independent final judgment

Distinct Judge `/root/judge` issued `adapt` for a stacked draft PR on the exact
implementation digest
`sha256:63e1aed35c9c403fafb488c29e098cb9178f09d9110c6098853431c19fab0b41`
and inventory digest
`sha256:2340004a3ed91df96e87826ca220c81ad6ca16aaae93f181119a225c4cdc4057`.

The Judge reproduced `101 passed, 23 subtests passed`, considered the final
current-byte Curator PASS, renewed Cross-Examiner PASS, Steward PASS, and preserved
dissent. Acceptance is limited to draft delivery of the opt-in public-store-only
metadata projection. Activation, rich content, usefulness, production readiness,
superiority, and final-system security/supply-chain evidence remain unjudged.

## `P3-ITEM4-AUDIT-001` — supplied base, source court, and bounded architecture

Phase 3 item 4 began on `codex/phase3-obsidian-bases-canvas` from the supplied PR #34
branch tip `7e26a56eab5fe79f075cccc57a6ff0a01fb9ef9a`. The user-owned edit to
`docs/NEXT_SESSION_HANDOFF_PUBLIC_PRIVATE_MEMORY.md` remains preserved and is not
treated as Builder work. `main` was not checked out or modified.

Court `P3-OBSIDIAN-VIEWS-004` and the item-4 source register opened before code.
Official Obsidian help and JSON Canvas heads matched the already pinned Phase 1
commits. Bases documentation remains `NOASSERTION` for reuse; JSON Canvas 1.0 is MIT.

Independent Explorer, Architect, and Integrator/Optimizer testimony selected a
separate `generated-cognitive-views` namespace, verified receipt-owned item-3 input,
four strict metadata Bases, one constant-size disclosure/navigation Canvas, no
loop/quarantine Base, a separate eight-schema protocol, and explicit no-runtime/
no-refresh/no-accounting/no-score limits.

## `P3-ITEM4-AUDIT-002` — bounded implementation

Builder `/root/item4_builder` added the separate eight-schema catalog and package
resources. `Codex-root` materialized and repaired the module implementation, focused
tests, deterministic inventory, and evidence. The module reads only the exact
receipt-owned item-3 tree and external item-3 protected evidence. It accepts no
private Foundation or public SQLite path.

The exact generated set is four Bases, one nine-node/zero-edge Canvas, and one
manifest under `hive-mind/generated-cognitive-views`. Base/Canvas bytes and full
domain-separated Canvas node IDs remain stable across source-cursor changes for the
same repository identity. The manifest alone records current item-3 source identity.
The output contains explicit released/static/safe-public/generated/nonauthoritative/
not-live disclosure and unavailable-not-zero statements for scores/health,
token/value accounting, loops, and quarantine.

Implementation digest:
`sha256:4b31182ced6d94b058180ae083f75c05c3afed5fdf7ba72a6117bc3b2c2d1e82`.
Inventory digest:
`sha256:61a6c27578e7cb4df97dfc9466cf39f5f485ddfa96ada0cdada25e098ce867ab`.

## `P3-ITEM4-AUDIT-003` — independent cross-examination and repairs

Distinct Cross-Examiner `/root/item4_explorer/cross_examiner` remanded the initial
runnable candidate. It reproduced an unverified reserved-sibling deletion and a
forged pending journal that could write an arbitrary file before failing ownership
verification. It also found incomplete source receipt binding, post-commit source
reporting, insufficient junction/parent defenses, weak conflict evidence,
self-denying history bounds, non-total Canvas semantics, and absent inventory
characterization.

Repairs validate the complete transaction and staged manifest before mutation;
preflight all reserved siblings; preserve mismatches; use ancestry, parent-identity,
same-file, and Windows no-delete checks; bind every current/historical receipt to
exact item-3 source evidence; check source immediately before manifest install;
validate measurable conflict evidence; separate history/transaction/conflict bounds;
make Base/Canvas semantic validation total; and check inventory equality.

The Cross-Examiner's requested raw tenant/repository expressions were rejected
because untrusted identifiers are prohibited in generated query structure. Exact
receipt-owned folder membership plus repository-identity digest binds scope. The
remaining runtime-vault spoof/property-type concern is preserved as dissent.

## `P3-ITEM4-AUDIT-004` — Curator remands and current-byte reproduction

Distinct Curator `/root/item4_architect/curator` issued three material remands:

1. a post-receipt source check could report failure after a valid commit;
2. arbitrary malformed evidence under authorized protected directories was ignored;
3. a schema-valid forged receipt side branch was not required to be reachable.

The final boundary checks source immediately before manifest install under the held
item-3 lock and makes the later uncooperative-writer window explicit dissent. Every
protected receipt/conflict is now canonical, schema-valid, identity-consistent, and
semantically valid; after recovery, every receipt must be on the single chain
reachable from the installed manifest head. Curator reproduced rejection of
malformed and schema-valid forged evidence, the adversarial repair subset, focused
suite, combined suite, inventory, lint, and type checks on current bytes.

## `P3-ITEM4-AUDIT-005` — exact verification

On the final pre-Steward candidate:

- item-4 focused suite: `24 passed`;
- Phase 2 plus Phase 3 items 1–4: `125 passed, 23 subtests passed`;
- independent Curator adversarial subset: `13 passed, 11 deselected`;
- Pyright: `0 errors, 0 warnings, 0 informations`;
- Ruff: passed;
- exact deterministic inventory: passed;
- installed-wheel eight-resource catalog: passed; and
- diff whitespace check: passed.

The suite covers item-1/item-3 byte parity, no SQLite access, check-mode nonmutation,
cursor-stable Base/Canvas bytes and node IDs, exact schemas/artifacts/bounds,
unavailable-not-zero language, corrupt source evidence, pending source recovery,
manual/missing/unmanaged state, interruption recovery, sealed-old-then-current
publication, forged staged plans and arbitrary paths, reserved siblings, source
change before manifest, current/historical receipt binding, malformed conflict
evidence, schema-valid unreachable receipts, frozen public surfaces, and CLI
behavior.

## `P3-ITEM4-AUDIT-006` — Steward remand and repaired candidate

Distinct Steward `/root/item4_explorer/steward` issued a five-finding remand for the
post-hardlink two-name crash window, pre-seal interruption without a recoverable
journal, restart dependence on the historical authority identity, unsafe source
transaction-root traversal, and repeated receipt-history traversal.

The repaired candidate:

- recognizes only an exact desired-digest next/destination hardlink pair and
  completes that interrupted install;
- writes the journal before staging in a preparation directory and atomically seals
  only complete plans;
- preserves incomplete preparation bytes under a path-bounded content identity plus
  canonical receipt binding the full original transaction ID and file digests;
- uses fresh authentic same-tenant/repository authority for recovery while
  preserving the original authority tuple as historical evidence;
- checks the item-3 transaction root before enumeration; and
- caches already proven source-chain nodes within one bounded validation pass while
  revalidating every direct source receipt head.

Root reproduction after repair passed `29` focused tests and `130` Phase 2 plus
Phase 3 items 1–4 tests with `23` inherited subtests. Ruff and Pyright passed. The
superseding current implementation digest is
`sha256:edebb8053a70923264bce1d4dec8b87d48e1af2c2dd13e6000faec581f98ae40`;
the deterministic inventory body digest is
`sha256:f83985b403c835e9bacf49bc5c42e8ba072ccd482b9d533e3fdcb7a0f69a3d67`.
Independent Steward reproduction and final judgment remain required.

## `P3-ITEM4-AUDIT-007` — final Curator abandonment-evidence remand

The renewed Curator reproduced two semantic inconsistencies in the first Steward
repair. A content-addressed abandonment receipt could be recomputed and renamed with
a different transaction ID while its readable preserved journal retained the
original ID. An unexpected nested preparation path could also be quarantined on one
run even though the next admission rejected that same evidence.

The repair requires a readable preserved journal's transaction ID to match its
abandonment receipt, restricts preservable preparation shape to the journal plus the
single hashed staging directory, and fails closed in place on every unexpected path.
Targeted regressions re-address both receipt and evidence directory while preserving
file digests, and inject an unexpected nested payload. Both now fail closed before
ordinary projection can report success.

The current implementation digest is
`sha256:f2d0b8704830e22cfeb64aee97a3a163b6ce54b1602a1e440019b61174cb8c51`;
the inventory body digest is
`sha256:b4d22570079ec49db3945fc4f10f8e3e8e3c1d3caed077038192177da8b5453a`.
Root focused reproduction passed `30` tests. The final root Phase 2 plus Phase 3
items 1–4 matrix passed `131` tests with `23` inherited subtests. Independent
rereproduction remains pending.

## `P3-ITEM4-AUDIT-008` — atomic evidence and no-clobber seal repair

The Steward's renewed review confirmed its original five findings closed, then
remanded four adjacent boundaries: partial writes at final evidence names,
uncatalogued abandonment `schema_version`, directory check-then-rename clobber
semantics on POSIX, and an unenforced Windows path budget.

The second reliability repair:

- writes final completion, conflict, and abandonment evidence to fsynced
  content-digest temporaries and installs them with native atomic no-replace rename;
- finishes complete temporaries on restart and discards only incomplete unsealed
  temporaries before the originating operation is replayed;
- defines abandonment as an internal canonical `record_kind`, preserving the exact
  installed eight-schema catalog;
- uses Windows no-replace rename, Linux `renameat2`, or macOS `renamex_np` for file
  and directory seals and fails closed elsewhere; and
- rejects Windows protected-state roots above 110 characters before mutation.

Targeted tests interrupt all three final evidence kinds, inject a late seal
destination, preserve its bytes and the original preparation, and check the
Windows 110/111-character boundary. Root focused verification passed `34` tests,
Ruff passed, Pyright reported zero errors/warnings/information, inventory equality
passed, and diff whitespace passed.

The current implementation digest is
`sha256:c3554ee83627407bef457f958abdc5176ddf1e0ba76e1f0ba361dde2bb50a965`;
the inventory body digest is
`sha256:609dd6764a67b3cc0b237c5241691828236f0092139b6d0db585ea1adeebae6e`.
The final root Phase 2 plus Phase 3 items 1–4 matrix passed `135` tests with `23`
inherited subtests. Independent Steward/Curator rereproduction remains pending.

## `P3-ITEM4-AUDIT-009` — truthful complete-temporary recovery

The Curator independently interrupted after a full canonical completion-receipt
temporary was fsynced but before atomic installation. Restart installed the receipt
and removed the completed transaction correctly, but the result incorrectly said
`unchanged/not-required`.

Completed-transaction cleanup now returns the exact installed receipt reference so
the result reports `projected/recovered`. The new full-temporary regression verifies
canonical pending bytes, restart installation, transaction cleanup, no remaining
temporary, and truthful recovery status.

Root focused verification passed `35` tests, Ruff and Pyright passed, exact inventory
equality and diff whitespace passed. The superseding implementation digest is
`sha256:4469e8e1382f29d52eff197eda007cb518c1f8c183d88335685c3d75d25e143c`;
the inventory body digest is
`sha256:b4756ba77fe349e67fde2d7c8c8ccafc78c66ab186266dacc490400a25b6b7f3`.
The final root combined matrix passed `136` tests with `23` inherited subtests.
Final independent rereproduction remains pending.

## `P3-ITEM4-AUDIT-010` — final independent PASS receipts

Steward `/root/item4_explorer/steward` issued PASS on implementation
`sha256:4469e8e1382f29d52eff197eda007cb518c1f8c183d88335685c3d75d25e143c`
and inventory body
`sha256:b4756ba77fe349e67fde2d7c8c8ccafc78c66ab186266dacc490400a25b6b7f3`.
It confirmed all original and renewed recovery, no-clobber, authority, source-root,
history-cost, internal-evidence, and Windows path-budget findings closed.

Curator `/root/item4_architect/curator` issued PASS on the same bytes. Its receipts
are:

- item-4 focused suite: `35 passed`;
- selected adversarial subset: `22 passed, 13 deselected`;
- Phase 2 plus Phase 3 items 1–4: `136 passed, 23 subtests passed`;
- Ruff: passed;
- Pyright: `0 errors, 0 warnings, 0 informations`;
- exact inventory equality: passed; and
- diff whitespace: passed.

The Curator separately reproduced canonical full-temporary recovery as
`projected/recovered`, all three partial-final-evidence recoveries, journal/receipt
binding rejection, invalid-shape in-place rejection, late seal-destination
preservation, the Windows 110/111 boundary, and the exact eight-schema boundary.
Distinct final judgment remains pending.

## `P3-ITEM4-AUDIT-011` — distinct final judgment

Distinct Judge `/root/item4_architect/judge` issued `adapt` for reversible stacked
draft delivery on exact implementation
`sha256:4469e8e1382f29d52eff197eda007cb518c1f8c183d88335685c3d75d25e143c`
and inventory body
`sha256:b4756ba77fe349e67fde2d7c8c8ccafc78c66ab186266dacc490400a25b6b7f3`.

The Judge admitted only the opt-in separate view namespace, four truthful metadata
Bases, one fixed disclosure/navigation Canvas, manifest/eight schemas, exact item-3
source admission, bounded recovery/evidence, read-only check, stable identities,
frozen prior surfaces, and reversible stop-invoking rollback.

Unavailable agent score/health, token/value accounting, loop state, and quarantine
inventory remain disclosures rather than fabricated dashboards. Merge, activation,
production, Obsidian runtime/rendering/refresh, federation, plugins, retrieval,
cleanup, encryption, full CI/security/supply-chain promotion, usefulness, and
superiority remain unjudged. Any byte, schema, protocol, interface, capability, or
evidence change requires renewed review and judgment.

## `P3-ITEM5-AUDIT-001` — real-runtime remand

Root opened a disposable no-hardlink clone in the installed, signed Obsidian Desktop
`1.12.7` runtime and drove the real item 1–4 projectors from externally placed
protected state. Item-1 README, item-3 HOME, and the Ideas Base refreshed inside the
predeclared 15-second observation window, and the Canvas rendered.

The post-observation integrity check failed: Obsidian removed unnecessary double
quotes from `bases/ideas.base`, changing its SHA-256 from
`53d560ba621911a994a887b3f883833bf7ccf99259e7c9f0789b5d54d2900609`
to
`db73a3e71a881baa3a00e46546f070c043b60babf72415ac9a213495206d6f99`.
Item 4 correctly reported `conflict`. The run remains a failed receipt.

## `P3-ITEM5-AUDIT-002` — Base repair and provisionally passing rerun

The Base renderer now emits plain YAML scalars only when unambiguous and keeps
unsafe or YAML-ambiguous values quoted. Focused item-4 verification passed `36`
tests; Ruff passed. Commit
`bed1c28e3b6abd1eaa72c138b99e5dc7997b229a` was cloned without hardlinks for a
fresh exact-commit rerun.

The immediate observations appeared to pass:

- item 1: `6 -> 7` records in `5.753755s`;
- item 3: `7 -> 8` total notes in `6.161164s`;
- Ideas Base: `2 -> 3` rows in `6.965943s`;
- Canvas: disclosure and embedded Bases rendered; and
- immediate item-4 check: `unchanged`, no conflicts, expected tree identity
  `sha256:3ecfe73252295079a7c5f44889208ace9a4d8d88ddc12d8fe898d702d1558fe4`.

Independent Curator and Cross-Examiner review later invalidated the run. Obsidian
rewrote `canvases/war-room.canvas` about four minutes after the immediate check,
changing SHA-256 from
`0922fb0be54882189093b12767a99fa6c2d9ca14561fe3543fb1f6608cdc7bdf`
to
`ac172a176ba5fd68412952865bb1d0d916f641c4db263df8ede7166590fb3dec`.
A reproduced item-4 check returned `conflict`. The tree digest above is expected
manifest identity, not observed-byte attestation. This run is preserved as failed.

## `P3-ITEM5-AUDIT-003` — scalar and delayed-Canvas remand

The Cross-Examiner also found YAML implicit-type gaps for date/time-like, numeric-like,
and legacy boolean values. Root repaired scalar quoting and added adversarial tests.
The Canvas renderer now matches the exact tab-indented, compact-node, no-terminal-
newline bytes written by Obsidian `1.12.7`. Focused item-4 verification passed `37`
tests with `8` subtests; Ruff and Pyright passed. Exact candidate
`fadf6e1b386eba61168c753b3cdab3d94503430f` is undergoing a fresh disposable-clone
run with a Canvas unload and a declared 300-second stability interval. No final
conformance verdict or court judgment is yet recorded.

## `P3-ITEM5-AUDIT-004` — delayed-stability run and hardened evidence boundary

The third run used exact production candidate
`fadf6e1b386eba61168c753b3cdab3d94503430f`. Same-pane observations completed in
`5.601962s`, `5.975783s`, and `5.145992s`; Canvas rendered with two embedded idea
rows. Root then switched away from Canvas and held the vault open for `329.74131s`,
exceeding the declared 300-second interval. An idempotent final projection returned
item 1, item 3, and item 4 `unchanged` with no conflicts.

All four final targets are copied under the run receipt and independently hash-bound.
The Canvas remained 2033 bytes at
`sha256:7377a6e7bce06eb7bccbcc3c27b9429bccb0af0b202954ecfa7abc371bd9c814`;
its modification time remained the projector time, before Canvas was opened.

The evidence validator now requires exact cases, timestamps, finite recalculated
latencies, runtime pins, prohibited-action keys, screenshots, delayed stability,
per-file target snapshots, and internal identity consistency. The fixture now
derives Git HEAD, checks origin/source separation, tracked cleanliness, bounded
no-hardlink identity, ignored `.obsidian/`, and persistent initialization identity.
Root verification passed `42` tests with `16` subtests, Ruff, and Pyright. Independent
current-byte review and judgment remain pending.

## `P3-ITEM5-AUDIT-005` — sealed-subject runtime evidence

Cross-examination correctly found that the preceding passing run predated final YAML
hardening. It remains a truthful pass for its own subject but is explicitly
non-promotable. Root sealed production and fixture commit
`ee09e4cb9a4bc5fd0711e738249039507a194e43` before creating the fourth clone.

The hardened fixture derived and matched Git HEAD/origin, rejected shared-object
storage, verified `1463/1463` tracked files and `3401/3401` clone Git-object files as
single-link regular files, rejected alternates, and kept protected state outside the
vault. Its committed registration is sanitized; workstation paths remain omitted.

The exact-subject run observed:

- item 1: `6 -> 7` records in `4.315128s`;
- item 3: `7 -> 8` total notes in `4.185468s`;
- Ideas Base: `1 -> 2` rows in `8.940211s`; and
- Canvas: disclosure plus two embedded idea rows rendered.

After Canvas unload, the vault remained open for `321.151072s`. The final sanitized
projector receipt records item 1, item 2, item 3, and item 4 `unchanged`; item 4 had
no conflicts. Evidence preserves and hash-binds both observed item-1/item-3 targets,
all four Bases, Canvas, the item-4 manifest, seven screenshots, the fixture
registration, and the final projector receipt.

The validator now enforces bounded single-handle reads, directory confinement,
regular single-link files, exact runtime/case/fixture schemas, visible transitions,
timestamp arithmetic, sanitized registration fields, complete target snapshots, and
cross-field final-projector identity. Root verification passed `147` tests with `57`
subtests; Ruff and Pyright passed. The original item-5 byte-freeze conflicts with
the runtime-required Base/Canvas serialization repair; only a distinct Judge may
authorize that minimal `adapt`.

## `P3-ITEM5-AUDIT-006` — exact-candidate independent review

Independent review targeted exact candidate
`8b0b0a029b8ef52b1ef75a64961234466f860dc2`; sealed runtime subject
`ee09e4cb9a4bc5fd0711e738249039507a194e43` remains its ancestor with
byte-identical production renderer and fixture files.

- Cross-Examiner/Integrator `Einstein` returned `PASS`, reproduced 115 integration
  tests with 34 subtests, and verified the surviving vault, all target hashes,
  provenance, compatibility, and prior remands.
- Curator/Expert Witness `Locke` returned `PASS`, reproduced all 147 tests with 57
  subtests plus focused checks, and independently validated subject ancestry,
  receipts, evidence privacy, and claim boundaries.
- Steward `/root/item4_explorer/steward` returned `PASS` after focused and item 2–5
  matrices, bounded-reader/fixture negatives, deterministic inventory, rollback,
  and operational-limit review.
- Optimizer `/root/item5_optimizer` returned `PASS` after independently reconciling
  latencies `4.315128s`, `4.185468s`, and `8.940211s`, the `321.151072s` stability
  interval, all comparator dispositions, and the absence of a superiority claim.

No reviewer remand remains. A separate Judge must still decide the narrow
byte-freeze conflict; reviewer approval cannot substitute for that disposition.

## `P3-ITEM5-AUDIT-007` — final narrow adaptation

Distinct Judge `/root/item5_judge` reviewed exact candidate
`b53175ffbd5d85e73ffc2ce6773560a999545170` and issued `adapt`. The Judge
independently reproduced `147` tests with `57` subtests, Ruff, and Pyright.

The judgment admits only the pinned local-runtime observations and narrowly permits
the Base scalar quoting and Canvas serialization changes required to keep generated
bytes stable under Obsidian `1.12.7`. It does not permit semantic, namespace, filter,
schema, protocol, capability, or authority redesign. Other hosts, versions,
profiles, Git remotes, Sync, multi-device behavior, production activation, merge,
usefulness, value, latency guarantees, generalization, and superiority remain
unproved or rejected.

Publication as a stacked draft PR is permitted. The PR must remain open, unmerged,
and inactive. Any relevant byte, schema, interface, capability, protocol, or
evidence change requires renewed independent review and judgment.

## `P3-ITEM5-AUDIT-008` — cross-platform CI repair review

Hosted CI exposed stale item-4 wheel totals, two platform-assumption defects in
tests, and an item-5 assertion that recognized only one of two truthful fail-closed
symlink classifications. Base repair
`19b933beb8c0008652d543567198b0e776595bfa` and item-5 repair
`0b1529a91dd86be211128375b9771a1b64caef02` correct only verification
expectations and platform setup.

The regenerated item-5 inventory digest is
`sha256:a19b0f105a6109afb8ecedf43ed7de879238962d5a071475d40b488b0d60592f`.
The sealed runtime subject
`ee09e4cb9a4bc5fd0711e738249039507a194e43` remains an ancestor with
unchanged production and runtime-evidence bytes.

Local verification passed `566` deterministic tests with `3` documented skips on
the base, the `147`-test Phase 2+3 matrix with `57` subtests on the child, Ruff,
Pyright, deterministic inventories, and isolated-wheel installation with exact
resource totals of `17` foundation-generated and `120` overall. Hosted push and
pull-request Constitutional CI passed for both exact repair candidates.

Cross-Examiner/Integrator `Einstein`, Curator/Expert Witness `Locke`, and Steward
`/root/item4_explorer/steward` independently returned `PASS`. They found no
production, schema, interface, protocol, capability, persistence, authority, or
claim expansion.

Distinct Judge `/root/item5_judge` reviewed exact base record
`fdefc1b5b6146b4fdf4e8a9317ebd23801e089a3` and exact item-5 record
`ac0d55a7d4ce9eea45e47efe822f3375d8532824`, independently reproduced
the four affected regressions, inventory generation, Ruff, Pyright, and exact
resource totals, and issued `adapt` with no remand.

The verdict admits only truthful verification/platform corrections and inventory
test-hash bookkeeping. The prior narrow runtime judgment, fail-closed symlink
handling, platform limitations, dissent, and protected bytes remain unchanged.
Both draft PRs may remain published, open, unmerged, and inactive; protected-surface
or claim changes require renewed review and judgment.

## `P3-ITEM6-AUDIT-001` — bounded candidate opened

Phase 3 item 6 began from exact item-5 head
`376a4a6082f6bdf154ba6252ccb70062a17a549b` on
`codex/phase3-federation-recursion-guards`.

Eligible scope is same-tenant safe-public portfolio federation and deterministic
self-host admission decisions. The candidate adds five strict schemas, an exact-scope
federation authority action, portfolio-local projection, and explicit
feedback/depth/hop/epoch guards.

Builder receipts are `15` item-6 tests and `162` Phase 2 plus Phase 3 items 1–6
tests with `57` subtests; Ruff and Pyright pass. Inventory
`sha256:50c0f08eb12c5b8c3055d0a6ae0e53ccef6f5585492271eea33b3031d7daa9e9`,
architecture, contract, migration/rollback, source register, court, and dissent are
present. The item-1 through item-5 inventories were deterministically rebound for
the additive package-data and authority hashes; item-5 runtime/production evidence
bytes are unchanged. Isolated-wheel verification passes with `133` governed
resources and explicit counts for eight cognitive plus five federation schemas.
Independent exact-candidate review and judgment remain pending. No
activation, merge, private/cross-tenant federation, lineage reconciliation, Inbox,
Sync, plugin, retrieval, usefulness, or superiority claim is admitted.

## `P3-ITEM6-AUDIT-002` — first-candidate independent remand

Cross-Examiner, Curator, and Steward independently remanded exact candidate
`34938782c750ea9d2080dcf2d25207dc13264be8`. Their adversarial fixtures proved
Windows junction source mutation, broken-link redirection, incomplete payload
validation, cross-tenant prior suppression, stale-epoch regression, late global
bounds, unmanaged target-directory admission, missing final source revalidation,
unclassified interrupted staging, and a POSIX destination replacement race.

The repair changes only item-6 code, tests, inventory, and its governing records.
It adds strict reparse/component checks, exact bounded trees, full memory/telemetry
payload validation, bounded scope-matched history, monotonic changed-subject epochs,
final source revalidation, interrupted-staging refusal, and native no-replace
publication. The failed candidate remains preserved; repaired receipts and renewed
independent review are pending.

## `P3-ITEM6-AUDIT-003` — Builder remand repair

The repaired item-6 suite passes `24` tests with one ordinary-symlink environment
skip; its Windows junction regression ran and passed. The combined Phase 2 plus
Phase 3 items 1–6 matrix passes `171` tests, one skip, and `57` subtests. Ruff and
Pyright pass. Repaired inventory is
`sha256:5dd1e6b1b68e5020c7b0bf936f93530ca71976a346d708d1dec4f0c68e693956`.

An exact repair commit and renewed independent review remain required. These Builder
receipts do not close the prior remands or authorize publication.

Renewed Cross-Examiner review of intermediate repair `616f59d` found one residual:
an orphan staging directory was not consulted on an `unchanged` rerun. The staging
check now precedes both unchanged and publication paths; a regression preserves the
orphan and refuses the rerun.

Renewed Steward review of `616f59d` separately found eager directory materialization
before the entry bound. Both managed-tree and staging-parent scans now iterate and
stop at the first over-bound entry. An instrumented regression proves early stop.

## `P3-ITEM6-AUDIT-004` — architecture and provenance remand

Architect `Heisenberg` and Explorer/Advocate `Helmholtz` independently remanded exact
candidate `0b45fc4f01400e1c9d3ec310e5a4fe593194ac32`.

The architecture remand reproduced a portfolio beside `hive-mind` but still inside
the source vault passing check mode because the projector knew only the namespace
root. The implementation now requires the canonical
`<vault>/hive-mind/generated-cognitive` suffix, derives the enclosing source-vault
root after fail-closed component checks, and rejects mutual ancestry for every
source/target and source/source pair. Parameterized check/project regressions and a
nested-source regression prove zero target creation and unchanged source bytes.

The provenance remand found an unsupported founding-docket attribution, omitted
`P1SRC-OBSIDIAN-HELP/SRC-OB-05` provenance and unresolved license, ambiguous prior
artifact references, collapsed obligations, and incomplete alternatives. The source
register now pins exact base blobs and the external commit/page digest, preserves
the unresolved documentation license, explicitly disposes lineage/link/novelty-scan/
challenger/adapter claims, assigns later owners and rollback, and compares
no-change, index-only, nonauthoritative deep-link, materialized, and shared-store
alternatives.

Builder repair receipts are `27 passed, 1 skipped` for item 6 and `174 passed,
1 skipped, 57 subtests passed` for the combined Phase 2/3 matrix. Ruff, Pyright,
inventory equality, and diff checks pass. Inventory is
`sha256:89b7625dbc4070ddf364e900de7a465005ce852d14a58d4133eb15341a072371`.
Renewed exact-candidate review and independent judgment remain pending.

Renewed Explorer/Advocate review passed the implementation and original provenance
repair but remanded one remaining evidence-only collapse: local identity,
ordinary-clone reconciliation, fork/mirror non-collapse, and complete
lineage/repository-instance/tenant/commit record binding were not atomic. The source
register now separates those propositions, assigns `adapt` or `defer`, owners,
acceptance mappings, and rollback, retains distinct repository instances until
lineage evidence exists, and removes an unproved comparative-narrowness phrase.

## `P3-ITEM6-AUDIT-005` — renewed specialist review passes

Exact implementation `0fe89d3382c624cbf4e3fb4da8a9a681306fc2a9` and exact
evidence record `494a7175d62e988ba9a071b726e023487333e042` now have renewed
independent `PASS` verdicts from Explorer/Advocate `Helmholtz`, Architect
`Heisenberg`, Cross-Examiner/Integrator `item6_cross_examiner`, Curator/Expert
Witness `Locke`, Steward `/root/item4_explorer/steward`, and Optimizer `Tesla`.

Their independent receipts preserve:

- `27 passed, 1 skipped` for item 6;
- `174 passed, 1 skipped, 57 subtests passed` for the combined matrix;
- Ruff and Pyright success;
- inventory
  `sha256:89b7625dbc4070ddf364e900de7a465005ce852d14a58d4133eb15341a072371`;
- isolated-wheel equality across all `133` governed resources, including eight
  cognitive and five federation schemas;
- zero mutation for noncanonical, nested, linked/reparse, authority, drift, race,
  and interrupted-stage failures;
- unchanged item-1 through item-5 protected/runtime evidence; and
- explicit deferral of fsync/concurrency, adapter enforcement, ordinary-clone
  reconciliation, complete lineage/commit binding, activation, performance, scale,
  value, learning, privacy/security, and superiority claims.

Optimizer recommends only narrow `adapt`. A distinct Judge verdict remains required
before draft publication; activation and merge remain prohibited.

## `P3-ITEM6-AUDIT-006` — Judge provenance remand

Distinct Judge `/root/item5_judge` reviewed exact implementation `0fe89d3`, identity
record `494a717`, and specialist record `ab21442` and issued `defer`. All technical
receipts passed, but ADR-027 retained an obsolete claim that “the founding docket
requires” item-6 behavior. The source register correctly establishes that
`founding_docket.py` contains no such atomic proposition and pins the actual internal
redesign record plus `MEM-024`/`MEM-025`.

ADR-027 now attributes the requirement only to those pinned sources. Technical bytes
are unchanged, so the Judge requires renewed exact-record judgment but no production
rerun. Draft publication, activation, and merge remain prohibited pending that
renewed verdict.

## `P3-ITEM6-AUDIT-007` — final narrow `adapt`

Distinct Judge `/root/item5_judge` renewed judgment on exact evidence repair
`7e66574945b1a45a59958406494dd27ff37dafcf` and issued `adapt` with no
remand. The final judgment also binds implementation `0fe89d3`, identity evidence
`494a717`, and specialist record `ab21442`.

Only stacked draft publication may proceed, open, unmerged, and inactive. Activation
and merge are prohibited. The judgment admits only opt-in first publication of a
local same-tenant safe-public portfolio, deterministic self-host decisions as an
inactive primitive, and the tested bounded/read-only/non-nested/no-replace/rollback
behavior.

Adapter enforcement, a full-system no-loop guarantee, clone/fork/lineage
reconciliation, complete lineage/commit binding, persistent history, updates,
deletion, fsync durability, concurrent/distributed writers, private/cross-tenant
federation, authentication, and every usefulness, value, performance, scale,
privacy, security, learning, generalization, or superiority claim remain deferred.

## `P3-ITEM6-AUDIT-008` — hosted unittest compatibility remand

Draft PR `#37` at exact head `b1d2575` failed all completed hosted unit-test jobs
while static/type checks, CodeQL, dependency/license review, secret scan, and build
provenance passed. Runs `30506872482` and `30506889077` reported two exact causes:
the item-6 test module imported unavailable `pytest`, and its top-level tests were
not discoverable by the required `python -m unittest discover -s tests -v` command.
The constitutional governance test correctly failed rather than silently skipping
item 6.

The narrow repair converts all 28 item-6 cases to standard-library
`unittest.TestCase` discovery without adding dependencies or weakening tests,
policies, acceptance criteria, or governance. Runtime, schemas, authority,
architecture, source admission, identity, protocol, capability, and claimed scope
remain unchanged. Only the test module and its deterministic inventory hash change.

Builder repair receipts:

- item 6 via unittest: `27 passed, 1 privilege-dependent skip`;
- item 6 via pytest: `27 passed, 1 privilege-dependent skip`;
- combined Phase 2/3 pytest: `174 passed, 1 skipped, 57 subtests passed`;
- exact hosted-style full unittest discovery: `605 tests, 4 platform skips`;
- governance discoverability, Ruff, Pyright, inventory equality, and diff checks:
  pass; and
- inventory:
  `sha256:0cb30744190e9eb521ed99da01ddf25bdb89dc755812786b2be1dff9abd1fe87`.

The prior judgment does not authorize the changed test/evidence bytes. Renewed
independent review and judgment are required before the repair is pushed.

## `P3-ITEM6-AUDIT-009` — CI repair independently verified

Cross-Examiner `item6_cross_examiner` and Curator/Expert Witness `Locke` returned
independent `PASS` verdicts on exact repair `d2aee8a`.

They verified 28 unique unittest-discoverable cases retain all 20 prior test bodies,
both vault-sibling modes, all eight self-host parameter cases, 35 assertions, and 23
negative exception checks. Exception mismatch/absence/propagation, patch cleanup,
the Windows junction case, focused unittest/pytest, all governance tests, combined
Phase 2/3 pytest, inventory equality, Ruff, and Pyright pass. Root full discovery
ran `605 tests` with four platform skips.

Runtime, schemas, authority, contracts, source register, dissent, workflow,
governance criteria, dependencies, prior tests/inventories, and protected runtime
evidence remain unchanged. A renewed Judge verdict is the only remaining gate before
pushing the repair.

## `P3-ITEM6-AUDIT-010` — CI repair judged `adapt`

Distinct Judge `/root/item5_judge` reviewed exact repair `d2aee8a` and renewed
review record `1bce33b` and issued `adapt` with no remand. The Judge independently
reproduced all 28 item-6 unittest cases, pytest compatibility, all eight governance
tests, deterministic inventory, Ruff, and Pyright.

The prior narrow item-6 judgment remains controlling because production, schemas,
authority, workflow, contracts, source admission, identity, protocol, capability,
protected evidence, and claims are unchanged. Inventory
`sha256:0cb30744190e9eb521ed99da01ddf25bdb89dc755812786b2be1dff9abd1fe87`
truthfully rebinds only the converted test bytes.

The repair may be pushed to existing draft PR `#37`; it must remain open, unmerged,
and inactive. Activation and merge are prohibited. Hosted checks must rerun before
the PR is described as passing.

## `P3-ITEM6-AUDIT-011` — cross-platform inventory remand

Fresh push run `30508445464` and PR run `30508447831` at exact judged repair head
`8f97ebc` passed all non-test checks and ran the full hosted suite. Every completed
Python job failed only item-6 inventory equality; behavior and discovery tests
passed.

Root cause: the item-6 chain hashed raw working-tree bytes of the inherited item-5
JSON inventory. Windows CRLF and GitHub LF checkouts therefore produced different
digests for semantically identical committed JSON.

The repair hashes the parsed inherited document using canonical JSON and adds a
direct LF/CRLF equality regression. Windows and Linux Python 3.12 each run all 29
item-6 tests with `28 passed, 1 platform skip`. Combined Phase 2/3 pytest reports
`175 passed, 1 skipped, 57 subtests`; all eight governance tests, Ruff, Pyright,
inventory equality, and diff checks pass. Cross-platform inventory is
`sha256:7656c7f2fec506eecaa23b5b4a378187d246e26de92c870e5aece185c3caa9ec`.

No runtime, schema, authority, workflow, contract, source-admission, identity,
protocol, capability, or claim surface changed. Renewed independent review and
judgment remain required before pushing.

## `P3-ITEM6-AUDIT-013` — evidence-coverage remand

Curator/Expert Witness `Locke` reproduced the claimed loader behavior and all
receipts at exact commit `d5f3633`, but returned `REMAND` because the 29th test
proved only newline stability and top-level duplicate rejection. The preceding
audit entry overstated durable test coverage for nested duplicates, malformed JSON,
and non-finite values.

The same test case now explicitly rejects top-level and nested duplicate names,
malformed JSON, `NaN`, positive infinity, and negative infinity. This changes no
runtime and does not increase the 29-case count. Windows unittest and pytest report
`28 passed, 1 skipped`; the combined Phase 2/3 matrix reports
`175 passed, 1 skipped, 57 subtests passed`; Ruff, Pyright, inventory equality,
and diff checks pass. Regenerated inventory is
`sha256:788340384cc3b0489e2e909b93f8d92bf911792a3f08f64eb5231ea701e4378a`.
Renewed independent review is required.

## `P3-ITEM6-AUDIT-012` — duplicate-key fail-closed remand

Curator/Expert Witness `Locke` returned `PASS` on exact cross-platform repair
`7f0a28a`. Cross-Examiner `item6_cross_examiner` returned `REMAND` because the
default JSON decoder's last-value-wins handling allowed duplicate object names to
collapse distinct evidence bytes to the same canonical document.

The repaired canonical loader rejects duplicate names with an
`object_pairs_hook`. The 29th item-6 test now proves all three boundaries:
semantically identical LF/CRLF JSON hashes equally, duplicate-name JSON fails
closed, and malformed/non-finite JSON remains rejected.

Windows unittest and pytest, plus Linux Python 3.12 unittest, each execute all 29
item-6 cases with `28 passed, 1 platform skip`. Combined Phase 2/3 pytest reports
`175 passed, 1 skipped, 57 subtests`; all eight governance tests, Ruff, Pyright,
inventory equality, and diff checks pass. The repaired inventory is
`sha256:0d798c8caa36edf3323389be8cab4af9a59b7aba5821532f84a2eb934be3367f`.

No runtime, schema, authority, workflow, contract, source-admission, identity,
protocol, capability, or claim surface changed. Renewed independent review and
judgment remain required before pushing.
