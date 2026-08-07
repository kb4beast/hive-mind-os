# Verifiable Hive Kernel: Phase 6 bounded memory and context primitives

This bounded slice supplies local, deterministic building blocks only. Memory bodies
are immutable SHA-256 artifacts; metadata and lifecycle facts remain separate so a
correction or retraction does not erase source evidence. Context assembly has no
provider dependency and is reproducible from its explicit request, catalog, and
artifact state.

Memory classes are closed and policy is not admitted to this plane. Working memory is
bounded to one work item with an explicit expiry.

The compiler accepts an explicit token budget, keeps required hot references whole,
selects warm records by the pinned Phase 6 score, and reports unselected records as
cold references. An explicit cold request produces another canonical manifest rather
than editing the prior selection. Explicit sensitivity scope filters records and
penalizes non-required sensitivity. No full memory projection, CLI, worker integration,
or scheduled consolidation is part of this implementation. A deterministic local
snapshot can rebuild the active-memory view without becoming an authority.

Canonical manifests can optionally persist beneath a caller-selected local root and
are restored only after contract/digest verification. Consolidation remains an explicit
bounded operation: independently evidenced episodes and an evaluator-approved outcome
are required before it may emit supersession facts for a validated lesson.

The complete regression gate remains `python -m unittest discover -s tests -v`.
