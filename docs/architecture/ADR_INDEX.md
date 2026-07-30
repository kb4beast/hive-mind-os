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
| `ADR-018` | [Canonical agent definitions and nonauthoritative projections](ADR-018-CANONICAL-AGENT-DEFINITIONS-AND-PROJECTIONS.md) | Phase 1 | adopted architecture; additive implementation begins in Phase 2 |
| `ADR-019` | [Open memory authority and Obsidian brain projection](ADR-019-OPEN-MEMORY-AND-OBSIDIAN-BRAIN.md) | Phase 1 | adopted architecture; memory foundation begins in Phase 2 and projection in Phase 3 |
| `ADR-020` | [Provider-native usage, privacy, and fair learning](ADR-020-USAGE-TELEMETRY-PRIVACY-AND-FAIR-LEARNING.md) | Phase 1 | adopted architecture; additive implementation begins in Phase 2 |
| `ADR-021` | [Additive memory and telemetry foundation](ADR-021-PHASE2-ADDITIVE-MEMORY-TELEMETRY-FOUNDATION.md) | Phase 2 | adopted implementation architecture; activation remains prohibited |
| `ADR-022` | [Portable safe-public memory pack projection](ADR-022-PORTABLE-MEMORY-PACK-PROJECTION.md) | Phase 3 item 1 | adopted at independently judged implementation candidate `24e48933`; activation remains prohibited |
| `ADR-023` | [Public/private memory release-store separation](ADR-023-PUBLIC-PRIVATE-MEMORY-SEPARATION.md) | Phase 3 item 2 | adopted architecture candidate; implementation judgment and activation pending |
| `ADR-024` | [Stable-ID cognitive note projection](ADR-024-STABLE-ID-COGNITIVE-NOTES.md) | Phase 3 item 3 | adapted for bounded draft delivery; activation and final-system promotion pending |
| `ADR-025` | [Bounded Obsidian Bases and JSON Canvas views](ADR-025-OBSIDIAN-BASES-CANVAS-VIEWS.md) | Phase 3 item 4 | adapted for bounded stacked draft delivery; activation and final-system promotion pending |
| `ADR-026` | [Pinned Obsidian vault refresh conformance](ADR-026-OBSIDIAN-VAULT-REFRESH-CONFORMANCE.md) | Phase 3 item 5 | proposed; final exact-build evidence and independent judgment pending |
| `ADR-027` | [Safe-public portfolio federation and self-host recursion guards](ADR-027-FEDERATION-AND-SELF-HOST-GUARDS.md) | Phase 3 item 6 | proposed CI-compatibility repair; renewed exact judgment pending |

The collisions are preserved as historical provenance. The next new numeric ADR identifier
is ADR-028; it must be unique at creation time.
