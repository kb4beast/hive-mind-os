# ADR-059: Durable Mission Identity Admission

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-058
- **Prior decisions:** ADR-052, ADR-053, ADR-054, ADR-058
- **Capability maturity:** bounded durable-constructor input-validation correction; no new authority

## Context

`RepositoryMission` validates a caller-facing `mission_id`, but its durable-resume `_run_id`
parameter could still supply the effective run identity without the same type and path
checks. The effective identity is used for durable state, receipt metadata, and mission
output naming. A malformed private resume input could therefore bypass the established
mission-identifier domain before source or workspace handling begins.

## Court record

- **Atomic claim:** a supplied durable run identity must satisfy the same nonempty,
  string-only, no-path-separator contract as a supplied mission ID.
- **Advocate / Builder:** reject an invalid `_run_id` during mission construction, before
  selecting durable state or output locations.
- **Cross-examination:** retain the existing exact equality check when both public and
  durable identifiers are supplied; do not synthesize or normalize a malformed resume ID.
- **Expert testimony:** resume-only inputs remain persisted control data and must preserve
  the portable identity boundary even when normal scheduling input has already been
  validated.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. `_run_id`, when supplied, is a nonempty string containing neither `/` nor `\\`.
2. It is checked before it can become `run_id`; the existing public/durable equality guard
   remains unchanged.
3. No schema, source custody, policy, credential, or governance behavior changes.

## Migration and rollback

This is additive and schema-free. Existing valid durable missions and checkpoints remain
unchanged. A caller that supplied a malformed resume identity must correct it before
resuming. Rollback must not reinterpret rejected identities as valid paths or authenticated
mission claims.

## Builder acceptance evidence

- `tests/test_mission.py` supplies a path-like private durable ID and confirms construction
  fails before a mission output location exists.

## Open court obligations

Independent Curator and Judge review remain required. Source safety, hostile-code isolation,
credential mediation, external retention, and production authority remain outside this
tranche.
