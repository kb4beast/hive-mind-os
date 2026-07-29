# Phase 1 Rollback Plan

- Scope: PR #29 Phase 1 architecture/evidence completion
- Runtime migration: none
- Stored-state migration: none
- Active champion change: none

## Rollback unit

Phase 1 adds or updates architecture, source/court evidence, generated
inventories, tests, `.obsidian/` ignore policy, audit records, and a portable
checkpoint. It does not change `src/hive_mind_os`, package resources, schemas,
prompts, the 131 root APIs, 33 package APIs, 13 CLI contracts, databases,
provider parsing, host adapters, or runtime selection.

Rollback is therefore a Git revert of the Phase 1 completion commits on
`codex/phase1-redesign-characterization`. PR #29 remains stacked on PR #28.
Neither PR is merged by this plan.

## Preconditions

1. Resolve the exact PR #29 head and verify the PR still targets
   `codex/repair-ci-test-contract`.
2. Preserve the previous characterization head
   `ee00967610df9e7d0ec4a5150bac751cc6880105`.
3. Preserve all court records, dissent, adverse Python-version evidence, test
   receipts, and source obligations in Git history.
4. Verify the revert target is the PR branch, never `main`.

## Procedure

1. Revert only the Phase 1 completion commits in reverse order.
2. Regenerate the Generation Zero inventories from the reverted tree.
3. Verify their inventory and file digests match the retained Generation Zero
   receipts.
4. Run Python 3.11, 3.12, and 3.14 characterization/regression tests plus
   Ruff, Pyright, wheel/resource, security, dependency, SBOM, and provenance
   gates.
5. Push the revert to the same draft PR and append a rollback court record.

## Expected result

- ADR-018 through ADR-020 return to candidate/deferred status.
- `.obsidian/` is no longer repository policy; any local directory remains
  untracked user state and must not be deleted.
- Generation Zero runtime and stored state are unchanged before, during, and
  after rollback.
- The source/claim/court history remains recoverable from Git and is not
  rewritten.

Rollback fails closed if the prior head, generated fixture, exact PR base,
required receipts, or independent review is unavailable.
