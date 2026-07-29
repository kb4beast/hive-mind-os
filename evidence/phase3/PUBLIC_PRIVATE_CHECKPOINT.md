# Portable checkpoint — Phase 3 item 2 public/private memory separation

- Branch: `codex/phase3-public-private-memory-separation`
- Exact base: draft PR #32 head
  `7f7013c99d86bbd34f966b902bb873cf5c10d740`
- Parent stack base: PR #31 head
  `94e67cde15fa8a75d92561384241f0419c9f589b`
- Court: `evidence/courts/phase3-public-private-memory-separation-court.md`
- Governing ADR: ADR-023
- Contract: `docs/architecture/PHASE3_PUBLIC_PRIVATE_MEMORY_CONTRACT.md`
- Migration/rollback:
  `docs/architecture/PHASE3_ITEM2_MIGRATION_AND_ROLLBACK.md`
- Inventory: `evidence/phase3/phase3_memory_separation_inventory.json`

## Candidate capability

- Separate, self-identifying, append-only safe-public release persistence bound to
  one tenant/repository.
- One-way release from an integrity-checked Foundation snapshot under authentic
  `foundation.public-memory.release` authority.
- Strict public-only envelopes; private/internal/quarantined/unsupported records,
  protected references, retrieval receipts, runtime rows, authority/lease fields,
  private counts, outbox, and delivery state are excluded.
- Protected external release journals/receipts, including changed-source restart
  that completes older pending receipts first.
- Separated projection that reads only the public store and keeps projection recovery
  state outside the repository.
- Existing item-1 public-tree parity for the admitted fixture.
- No external dependency or new semantic source.

## Current evidence

The pre-change stack, parent CI, frozen contracts, and actual PR diffs were
reconstructed. Independent Explorer, Architect/Cross-Examiner, and privacy/security
Expert testimony selected and bounded the release-store design.

The current development inventory records:

- exact frozen `131/33/13/304`;
- 17 unchanged Phase 2 schemas;
- seven unchanged item-1 schemas;
- three additive item-2 schemas;
- one public and one private fixture input, with exactly one released record;
- equal direct and separated item-1 public trees; and
- no private projection state in the repository.

Current inventory digest:
`sha256:36ba3ba7d08ea7a9438b6ec794d2f03796bad894bce71c7ddefd095d2f8a3b59`.

Final exact commit, complete local and GitHub CI, wheel/SBOM/
provenance hashes, independent Curator/Steward reconstruction, Judge verdict, draft
PR number, blockers, and next eligible objective remain pending.

## Preserved limits

All item-1 and item-2 dissent in `PHASE3_DISSENT.md` remains binding. In particular,
this is not encryption, authenticated external identity, revocable disclosure,
physical deletion, crypto-erasure, backup control, federation, tenant-key isolation,
protected-content storage, rich notes, Obsidian support, production readiness, or
superiority.

No PR is merged, no runtime is activated, and `main` is not modified.
