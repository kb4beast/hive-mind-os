Do not implement stale nodes. Reconstruct the graph from current code, receipts, PRs,
changed interfaces, and blockers. Add, split, merge, supersede, or reorder nodes only
with an append-only reason and updated plan fingerprint. Preserve completed receipt
meaning. Re-run doctor and controller tests. Stop at a draft control-plane-only PR.
