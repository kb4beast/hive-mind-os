# ADR-054: Git Workspace Identity Admission

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-053
- **Prior decisions:** ADR-040, ADR-052, ADR-053
- **Capability maturity:** bounded adapter input-validation correction; no new authority

## Context

ADR-052 supplies a stable repository-mission identity to fresh Git workspaces and
ADR-053 validates it when a durable checkpoint reopens one. The lower-level
`GitWorkspace.materialize` adapter still accepted any direct caller-supplied identity,
including an empty or path-like value, before creating its workspace and receipt context.
That left the lowest admitted boundary weaker than the mission and recovery paths.

The identity remains local provenance metadata. Validating its shape does not authenticate
the caller, a source, a repository, a provider, or a receipt.

## Court record

- **Atomic claim:** Git workspace materialization rejects an empty, non-string, or
  path-like caller-supplied mission identity before creating the workspace container.
- **Advocate / Builder:** apply the same nonempty/no-path-separator contract used by the
  repository mission and recovered checkpoint before policy evaluation or filesystem work.
- **Cross-examination:** do not silently replace a supplied bad ID with a random one, and
  ensure rejection occurs before source staging, clone, or receipt creation.
- **Expert testimony:** early type/path validation keeps receipt mission/state metadata
  inside the portable identifier domain without asserting stronger authentication.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. A supplied `source_mission_id` must be a nonempty string containing neither `/` nor
   `\\`. The existing generated adapter ID remains available only when the caller omits
   this optional value.
2. Invalid input raises `PinViolation` before workspace-root creation. Local and
   authenticated remote callers use their existing valid stable IDs unchanged.
3. No schema, source custody, policy, credential, or governance behavior changes.

## Migration and rollback

This is additive and schema-free. Existing materialized workspaces and stored checkpoints
are not changed. A direct caller that previously supplied a malformed value must correct
it and restart before materialization. Rollback retains all historic evidence and cannot
upgrade a malformed identifier into an authentication claim.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` passes a path-like identity to a local
  Git workspace materialization and confirms `PinViolation` occurs with no workspace
  directory created.

## Open court obligations

Independent Curator and Judge review remain required. External custody, source safety,
hostile-code isolation, credential mediation, external retention, and production authority
remain outside this tranche.
