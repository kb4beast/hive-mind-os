# ADR-021-PR30: Historical quarantined v2 foundation namespace

- Status: superseded implementation candidate; exact history retained; runtime activation prohibited
- Date: 2026-07-29
- Historical pull request: `#30`
- Exact historical head: `39e07c9e3c3ce439911481be2d38d901d05d4824`
- Superseded by: `ADR-021-PR31` and the accepted `hive_mind_os.foundation` implementation

## Context

PR #30 created a separately importable `hive_mind_os_v2` candidate containing
repository identity, immutable memory and usage contracts, a dedicated SQLite/WAL
store, append-only mutation guards, digest chains, a transactional outbox, delivery
receipts, integrity replay, tests, and a quarantine boundary. It was closed unmerged
after the accepted Phase 2 design moved the same problem into the canonical
`hive_mind_os.foundation` namespace and expanded its authority, schema, telemetry,
reconciliation, migration, packaging, and evidence contracts.

This record does not revive the sibling package. It preserves the losing candidate
and its design claims so they cannot disappear merely because a later candidate won.
The exact source commit is retained as Git ancestry of the hardening branch through a
tree-neutral merge. Its files remain available from that historical commit without
becoming active files in the selected release tree.

## Decision

1. Preserve exact PR #30 history and its court/test evidence.
2. Do not copy `hive_mind_os_v2` into the active release tree.
3. Treat the accepted PR #31 foundation as the selected adaptation.
4. Use `PR30_SUPERSESSION_AND_DISPOSITION.md` as the atomic claim map.
5. Keep runtime activation, dual-write, migration, provider conformance, public
   projection, learning, and production claims prohibited unless separately judged.

## Why exact ancestry instead of duplicate files

Duplicating both foundation implementations in the selected tree would create two
competing authorities, two storage identities, and ambiguous migration ownership.
Exact ancestry preserves every original byte and commit while one selected tree keeps
one canonical authority. A tree-neutral merge must be verified to change history only,
not the release file tree.

## Rollback and appeal

Rollback removes only later selected consumers or the hardening branch; it never
rewrites the PR #30 commit. An appeal may reconsider a particular rejected or adapted
claim, but it must compare exact implementations and cannot silently reactivate the
sibling package.

## Not admitted

This historical preservation is not approval of PR #30, runtime activation, package
promotion, production readiness, or a claim that the accepted implementation is
superior. It is provenance and loss-prevention only.
