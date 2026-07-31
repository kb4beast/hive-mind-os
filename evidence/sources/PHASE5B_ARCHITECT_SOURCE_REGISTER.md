# Phase 5B Architect source register

## Admission boundary

Phase 5B uses only repository-controlled sources already present at exact base
`ed1c0a76c52335e7cf92ba92b2f4d401116f85e1`. No unavailable video, external
repository, mutable web page, or unidentified Armory content is treated as evidence.

| Source | Use | Disposition |
| --- | --- | --- |
| `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` | Phase 5 requires one deep playbook per remaining role without merging authority. | `ADOPT` for design scope only. |
| `docs/architecture/ADR-018-CANONICAL-AGENT-DEFINITIONS-AND-PROJECTIONS.md` | Canonical agent identity and nonauthoritative projections. | `ADOPT`. |
| `docs/architecture/ADR-021-PHASE2-ADDITIVE-MEMORY-TELEMETRY-FOUNDATION.md` | Additive, opt-in, authority-bounded foundation. | `ADOPT`. |
| `docs/architecture/ADR-033-ORCHESTRATOR-DEEP-PLAYBOOK.md` | Phase 5A layering, typed outputs, honest independence, and inert delivery precedent. | `ADAPT` to the Architect role. |
| `src/hive_mind_os/foundation/canonical/agents/architect.json` | Exact Phase 2 Architect source identity. | `ADOPT` and digest-pin. |
| `src/hive_mind_os/foundation/generated/agents/architect.json` | Exact generated Phase 2 candidate. | `ADOPT` and byte-verify. |
| `src/hive_mind_os/builtin_packages/hive-core/agents/architect.json` | Built-in role binding. | `ADOPT` and digest-pin. |
| `src/hive_mind_os/builtin_packages/hive-core/prompts/architect.json` | Generation Zero prompt content. | `ADOPT` and digest-pin. |
| `src/hive_mind_os/builtin_packages/hive-core/skills/architect.json` | Reusable Architect skill identity. | `ADOPT` by reference. |
| `src/hive_mind_os/builtin_packages/hive-core/skills/instructions/architect.json` | Skill instructions. | `ADOPT` by reference and digest-pin. |
| `src/hive_mind_os/roles.py` | Constitutional lifecycle order. | `ADOPT`; unchanged. |

## Claims admitted

- The Architect may integrate adjudicated claims and compare bounded options.
- Architecture, interfaces, threats, migration, rollback, verification, resources,
  and handoff require separate typed records.
- The Architect may propose but not select, implement, approve, promote, or activate.
- A caller-supplied score, role label, or evidence label is not authenticated proof.
- Every adopted or adapted claim must remain traceable to evidence and acceptance.
- Each option must carry its own complete design and verification evidence.
- Migration must remain reversible and resource plans must retain recovery reserves.

## Deferred obligations

- live repository evidence acquisition;
- authenticated independent actor identities;
- actual budget leasing;
- held-out behavioral evaluation;
- design-quality or customer-value measurement;
- champion migration, promotion, or activation;
- production and release readiness.

All deferred obligations remain explicit blockers rather than inferred facts.
