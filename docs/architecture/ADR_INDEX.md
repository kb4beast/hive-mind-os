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
| `ADR-013` | [Versioned prompt experiment loop](ADR-013-VERSIONED-PROMPT-EXPERIMENT-LOOP.md) | P10 | adapted candidate; independent-promotion appeal remains blocked |
| `ADR-014` | [Durable local operations](ADR-014-DURABLE-LOCAL-OPERATIONS.md) | P11 | adapted; local single-machine boundary permitted and merged |
| `ADR-015` | [Post-P13 production and trust program](ADR-015-POST-P13-PRODUCTION-AND-TRUST-PROGRAM.md) | P14–P20 | proposed; independent adoption review required |
| `ADR-016` | [Governed extension packages and portable host projections](ADR-016-GOVERNED-EXTENSION-PACKAGES.md) | Slice 1 | bounded structural candidate accepted/adapted; promotion deferred |
| `ADR-017` | [Inert constitutional skills, read-only tools, and host evidence](ADR-017-INERT-SKILLS-TOOLS-AND-HOST-EVIDENCE.md) | Slice 2 | adapted bounded candidate; promotion and host support blocked |
| `ADR-018` | [Runtime surface disposition](ADR-018-RUNTIME-SURFACE-DISPOSITION.md) | P2.2 | adopted |
| `ADR-041` | [Typed executable acceptance specifications](ADR-041-TYPED-EXECUTABLE-ACCEPTANCE-SPECS.md) | P3.4 | adapted |
| `ADR-042` | [Contribution governance tiers](ADR-042-CONTRIBUTION-GOVERNANCE-TIERS.md) | P4.05 | adopted |

The collisions are preserved as historical provenance. The next new numeric ADR identifier
is ADR-043; it must be unique at creation time.
