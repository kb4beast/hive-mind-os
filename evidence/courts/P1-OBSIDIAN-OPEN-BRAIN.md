# Phase 1 Court: Obsidian Open Brain

- Case ID: `P1-OBSIDIAN-OPEN-BRAIN`
- Status: characterization adapted for draft publication; architecture deferred
- Original request SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`
- Source register:
  `evidence/sources/PHASE1_PRIMARY_SOURCE_REGISTER.md`

## Participants

| Function | Identity |
| --- | --- |
| Explorer, Clerk, Advocate | `/root/phase1_sources` |
| Architect, Cross-Examiner | `/root/phase1_architecture` |
| Builder | `/root` |
| Curator, security/privacy Expert Witness | `/root/phase1_curator` |
| Judge | `/root/phase1_judge` |

## Frozen parent claims

- `OB-001`: Open the repository root as a local repository-as-vault workbench.
- `OB-002`: Generate deterministic Obsidian projections only when direct
  Markdown browsing is insufficient.
- `OB-003`: Keep optional Obsidian-to-OS intake separate, explicit, validated,
  untrusted, idempotent, dry-runnable, and governed.
- `OB-004`: Distinguish automatic local-file freshness from explicit remote Git,
  application, plugin, and Sync update semantics.
- `OB-005`: Make Obsidian a first-class brain, review, navigation, and
  knowledge-gardening surface without making it storage or execution authority.

Child claims include generated-note identity/provenance, staging and atomic
replace, expected-prior-digest conflicts, conflict preservation, tombstones,
no export re-ingestion, generated/human namespace separation, safe rendering,
and optional portable Bases/Canvas views.

## Advocate case

Official Obsidian sources support the smallest first step: a vault is a local
folder and existing Markdown requires no importer. A deterministic projection
is justified only for durable facts absent from repository Markdown. JSON
Canvas supplies an optional pinned MIT spatial format.

## Cross-examination and dissent

Obsidian is optional external software. Documentation reuse remains unresolved;
plugins and Sync add writers, trust, conflict, privacy, and cost surfaces.
Remote Git changes are not automatic. Generating a second knowledge tree can
create churn, stale authority, disclosure, and overwrite risk. No plugin,
watcher, Inbox, or executable Markdown path is justified in Phase 1.

## Architecture mapping

Candidate decision: `docs/architecture/ADR-019-OPEN-MEMORY-AND-OBSIDIAN-BRAIN.md`.
Generation-zero truth remains unchanged. The proposed projection is downstream
of the open memory authority and can be disabled or regenerated.

The clean clone has no `.obsidian/` directory, and `.gitignore` does not
currently exclude one. The Phase 1 candidate policy is to keep the entire
directory local and ignored at first. A curated portable team configuration is
a later, separately reviewed change; workspace layouts, paths, plugin state,
caches, and secrets must never be committed accidentally. Phase 1 records this
candidate but does not change `.gitignore` before judgment.

## Acceptance and rollback mapping

Acceptance requires deterministic bytes, stable IDs, source/run/digest/status
metadata, safe-public allowlisting, conflict preservation, interruption/restart
tests, no re-ingestion, no secret export, and operation without Obsidian.
Rollback disables only the generated namespace and preserves human notes,
canonical memory, conflicts, receipts, and dissent.

## Open obligations

`P1-SRC-B01`, privacy classification, a final repository policy for
`.obsidian`, and multi-writer conflict tests remain blocking. The independent
Curator accepted the accuracy of this characterization. The independent Judge
adapted it for stacked draft publication while deferring ADR-019, source
admission, and implementation.

## Phase 1 merits continuation

The earlier candidate correctly deferred these merits. The completion
candidate now adopts local-only `.obsidian/` policy in `.gitignore`, narrows
official-help use to factual citation without copying, and specifies
safe-public allowlisting, deterministic bytes, expected-prior-digest
conflicts, namespace separation, interruption recovery, no re-ingestion, and
operation without Obsidian in `hive-obsidian-projection/v1`.

Multi-writer behavior remains an executable Phase 3 gate rather than an
unresolved Phase 1 design choice. No plugin, watcher, Inbox, Sync dependency,
or executable host is admitted.
