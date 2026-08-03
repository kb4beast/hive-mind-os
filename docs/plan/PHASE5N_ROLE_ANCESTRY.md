# Phase 5N — role ancestry and package reconstruction

- **Subject release:** `ebe5884e30f62834ca649b72495e0178280ec3b3`
- **Subject tree:** reconstructed by `scripts/phase5h_role_ancestry_index.py`
- **Originating debt:** `P5H-DEBT-01`
- **Index digest:**
  `sha256:2b029c1f7c39b3b248b5b9e3e6a6a91ca46b93be01583e6a4c3760f427df2f9f`
- **Status:** exact implementation head validated; closure recorded additively
- **Authority:** none

## Evidence reconstruction

The machine-readable index covers all eight specialist roles from Orchestrator through the Phase 5H
consolidation court. For every role it records and independently verifies:

1. the exact introduction commit and its ancestry to the subject release;
2. the originating pull request, merge commit, and merge-tree object;
3. current subject-tree Git blobs and SHA-256 digests for implementation and contract modules;
4. the inventory artifact's Git blob, file digest, and internally validated inventory digest;
5. retained audit and court receipts, with missing dedicated E–H courts explicit;
6. package-relative implementation and contract paths; and
7. byte equality between those Git-subject files and a fresh isolated wheel installation.

GitHub pull-request metadata was retrieved from `kb4beast/hive-mind-os` at
`2026-08-03T00:34:00Z`. The repository license is MIT. No external code or unpinned source content
was copied.

## Acceptance and local receipts

- six deterministic/adversarial Phase 5N tests passed;
- the Phase 5M point-in-time reconciliation and current Phase 5 inventory tests remained green;
- Ruff and Pyright 1.1.411 passed;
- a fresh wheel was built locally with digest
  `sha256:c780fd01c5b2c3d67b8148000006f38de88cdbb693ae697b18856a22c8724f41`;
- all 16 role implementation/contract files in that wheel matched the Git-subject SHA-256 values;
- the permanent build-evidence workflow now retains and attests the ancestry verification receipt.

Hosted push and pull-request receipts are still required before closing `P5H-DEBT-01`.

Exact implementation head `a78fcdd3418565565aa82ae127957632e5ac08d8` passed push run
`30775103987` and pull-request run `30775114316`. The additive successor reconciliation is
`docs/plan/PHASE5N_DEBT_RECONCILIATION.md`.

## Threats and rollback

- Missing or shallow Git history fails closed.
- Introduction or merge ancestry substitution fails closed.
- Git tree, blob, inventory, index, or installed-package byte drift fails closed.
- Historical subjects are reconstructed with `git show`; later working-tree changes cannot rewrite
  point-in-time evidence.
- Missing E–H dedicated courts are retained as gaps and do not become inferred evidence.
- Rollback is a revert of the Phase 5N merge commit; `P5H-DEBT-01` then returns to active.

`B-OPS-08`, the missing governance and full-output debts, ADR-015, authenticated independence,
P14/P20, release/production readiness, deployment, promotion, and superiority remain unchanged.
