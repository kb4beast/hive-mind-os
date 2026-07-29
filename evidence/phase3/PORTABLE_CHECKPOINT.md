# Portable checkpoint — Phase 3 item 1 open brain projection

- Branch: `codex/phase3-open-brain-obsidian-projection`
- Draft PR: #32
- Exact stack base: PR #31 head
  `94e67cde15fa8a75d92561384241f0419c9f589b`
- Accepted implementation candidate:
  `24e48933d7e4098002944b2cc5d73bfe9e3f1e3b`
- Governing ADR: ADR-022
- Court: `evidence/courts/phase3-portable-memory-pack-court.md`
- Inventory: `evidence/phase3/phase3_projection_inventory.json`
- Inventory digest:
  `sha256:5ecae209c32b6460f1e1935512c90d44fe2ab96c1de217fcc4e5857137701e74`
- Deterministic fixture tree:
  `sha256:758b20b66c095ac37bfd38e7ac4cd6d5b4dbd20ed4f9e0eed8fd210cd57dbb58`

## Adopted implementation

- Read-only, integrity-checked, tenant/repository-scoped Foundation snapshots.
- Default-denied safe-public memory projection requiring independent,
  subject-digest-bound release provenance.
- Metadata-only deterministic Markdown notes, README, manifest, eligible-set cursor,
  portable hashed paths, UTF-8/LF bytes, and seven strict projection schemas.
- Dedicated opt-in `python -m hive_mind_os.foundation.brain` project/check command;
  the 13 frozen `hive-mind` parsers remain unchanged.
- Authentic `foundation.projection.write` authority for publication.
- Private ignored process lock, journal, staged bytes, completion receipts, and
  conflict receipts.
- Manifest-last per-file atomic replacement, interruption recovery, clone-safe
  ownership rules, conflict preservation, and no automatic deletion.
- Bounded rendering, stat-first bounded private-document reads, constant-memory
  generated-file hashing, pre/open/post identity checks, and link/reparse/hardlink
  confinement.
- Typed success, drift/conflict, and failure results.

## Independent delivery receipts

- Curator `Aquinas`: `ACCEPT`; `73 passed, 27 subtests`; Ruff pass; Pyright zero
  findings; exact stack, contracts, privacy, hostile files, inventory, and CI
  reconstructed.
- Steward `Cicero`: `ACCEPT`; `73 passed, 27 subtests`; Ruff pass; Pyright zero
  findings; recovery, reliability, confinement, conflicts, compatibility, and CI
  reconstructed.
- Judge `Ohm`: `ADOPT` for Phase 3 item 1 only; `75 passed`; actual diff, court,
  artifacts, and provenance independently inspected; no item-1 remand.
- Exact implementation CI: push run `30465040651` and PR run `30465050020`, both
  successful across Python 3.11/3.12/3.14, Ruff, Pyright, CodeQL, secret scan,
  dependency/license review, SBOM, installed-wheel resource verification, and
  provenance.
- Artifact `8729181702`: wheel
  `c2db874c61be52233e1edac6dfdcbc500390cca71196c08009a0bd3952c08256`;
  SPDX SBOM
  `0014ac9cfe8155eecc52df446c99a1a9a5e94fecf4984bf037ed37f27f684872`;
  Sigstore/SLSA verification binds both to the accepted candidate.

## Compatibility and non-activation

Generation Zero remains selected. The frozen 131 root APIs, 33 package APIs, 13 CLI
contracts, and 304 definitions are unchanged. The 17 Phase 2 schemas remain
unchanged; seven separate Phase 3 projection schemas are additive. PRs #28, #29,
#31, and #32 remain unmerged. `main` is unchanged. No Obsidian runtime, account,
plugin, Sync service, watcher, importer, or external dependency is required.

## Preserved limits

All items in `PHASE3_DISSENT.md` remain binding. In particular, item 1 claims no
whole-directory CAS against a malicious writer, public-content completeness,
outbox acknowledgement, automated cleanup, richer cognitive notes, Obsidian refresh
or support, Bases/Canvas, federation, self-host recursion, Inbox intake,
production-readiness, usefulness, or superiority.

## Exact next eligible objective

Phase 3 item 2: **Separate safe public memory from private/sensitive runtime
records.**

Create `codex/phase3-public-private-memory-separation` from the final PR #32 head
after this evidence-only checkpoint is sealed and its exact-head CI is green. Keep
PR #32 draft and unmerged; do not begin HOME/domain notes, Bases/Canvas, Obsidian
refresh, federation, self-host recursion, Inbox intake, or any later item.
