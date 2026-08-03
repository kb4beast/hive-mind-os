# ADR-052: Durable Workspace Mission-Identity Binding

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-051
- **Prior decisions:** ADR-040, ADR-047, ADR-049
- **Capability maturity:** bounded local/durable identity correction; no new authority

## Context

`GitWorkspace.materialize` accepts an optional caller identity for its receipts and state
reference. Authenticated remote missions supplied that identity through their source lock,
but local `RepositoryMission` materializations did not. The Git adapter then generated a
random `git-workspace-*` identity, which durable checkpoints carried forward on recovery.
The workspace's receipts were reproducible but not directly bound to the repository
mission that scheduled and adopted them.

This is an identity/provenance correction only. It does not authenticate local work,
convert a local digest into external custody, change source admission, or widen any
repository, provider, worker, or governance authority.

## Court record

- **Atomic claim:** every workspace created by a `RepositoryMission`, including a local
  one, uses that mission's stable identity and its default state reference from its first
  receipt; a durable recovery continues to use the same recorded identity.
- **Advocate / Builder:** always pass `RepositoryMission.run_id` into the existing
  materialization adapter. Authenticated remote options already carry the same value and
  therefore remain unchanged.
- **Cross-examination:** reject a patch that creates a new ID on resume, changes a stored
  historic workspace ID, or treats a local mission ID as external authentication.
- **Expert testimony:** the Git adapter's receipt binding is the existing evidence
  mechanism. Stable local identity improves causal traceability but remains local
  integrity evidence.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. `_materialize_once` begins with `source_mission_id=run_id` for every repository
   mission. Source-custody options may add strict remote fields but cannot substitute a
   different identity.
2. New local workspace receipts and their default `MISSION_STATE:<run-id>:1` reference
   are directly attributable to the durable mission. Existing completed checkpoints keep
   their retained historical workspace identity for exact recovery compatibility.
3. No schema migration, backfill, reclassification, credential, source, or policy change
   occurs.

## Migration and rollback

The change is schema-free and applies to future materializations. Existing checkpointed
workspaces reopen using their retained `git_mission_id`; they are neither rewritten nor
claimed to have been externally authenticated. Rollback restores the prior identity
generation for future local work only and preserves all evidence already recorded.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` constructs a local durable
  `RepositoryMission`, intercepts its fresh materialization, and confirms the Git adapter
  receives the stable mission identity rather than generating its own.

## Open court obligations

Independent Curator and Judge review remain required. External custody, source safety,
hostile-code isolation, credential mediation, external retention, and production authority
remain outside this tranche.
