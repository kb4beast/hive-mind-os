# Phase 3 item 1 append-only audit ledger

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
