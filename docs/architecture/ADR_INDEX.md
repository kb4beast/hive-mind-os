# Architecture Decision Record Index

This registry disambiguates two historical numeric collisions without renaming or deleting
records referenced by committed audits. Use the qualified key or the full filename in new
evidence. Numeric-only references to ADR-008 or ADR-012 are ambiguous.

| Qualified key | Record | Phase | Current posture |
|---|---|---|---|
| `ADR-008-P03` | [Windows process-tree liveness](ADR-008-WINDOWS-PROCESS-TREE-LIVENESS.md) | P03 | adopted |
| `ADR-008-P07` | [External delivery boundary](ADR-008-EXTERNAL-DELIVERY-BOUNDARY.md) | P07 | adopted |
| `ADR-012-P08` | [Blind-first Curator independence](ADR-012-BLIND-FIRST-CURATOR-INDEPENDENCE.md) | P08 | adopted; authenticated identities remain deferred |
| `ADR-012-P12` | [Source ingestion and additive reconciliation](ADR-012-SOURCE-INGESTION-AND-ADDITIVE-RECONCILIATION.md) | P12 | adopted; source obligations remain deferred |
| `ADR-013` | [Versioned prompt experiment loop](ADR-013-VERSIONED-PROMPT-EXPERIMENT-LOOP.md) | P10 | proposed for consolidated review |
| `ADR-014` | [Durable local operations](ADR-014-DURABLE-LOCAL-OPERATIONS.md) | P11 | proposed for final consolidated review |

The collisions are preserved as historical provenance. The next new numeric ADR identifier
is ADR-015; it must be unique at creation time.
