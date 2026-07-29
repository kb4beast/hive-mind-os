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
