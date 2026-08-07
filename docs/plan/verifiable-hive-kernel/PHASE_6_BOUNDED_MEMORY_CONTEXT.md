# Verifiable Hive Kernel: Phase 6 bounded memory and context primitives

This bounded slice supplies local, deterministic building blocks only. Memory bodies
are immutable SHA-256 artifacts; metadata and lifecycle facts remain separate so a
correction or retraction does not erase source evidence. Context assembly has no
provider dependency and is reproducible from its explicit request, catalog, and
artifact state.

The compiler accepts an explicit token budget, keeps required hot references whole,
selects warm records by the pinned Phase 6 score, and reports unselected records as
cold references. An explicit cold request produces another canonical manifest rather
than editing the prior selection. No full memory projection, CLI, worker integration,
or scheduled consolidation is part of this implementation. A deterministic local
snapshot can rebuild the active-memory view without becoming an authority.

The complete regression gate remains `python -m unittest discover -s tests -v`.
