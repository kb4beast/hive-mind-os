# ADR-061: Non-Dot Mission Identity Admission

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-060
- **Prior decisions:** ADR-058, ADR-059, ADR-060
- **Capability maturity:** bounded identity-domain correction; no new authority

## Context

ADR-060 establishes that `.` and `..` are not safe mission-root path segments. The worker
and mission-constructor checks established by ADR-058 and ADR-059 rejected separators but
still accepted those two dot segments. That allowed an invalid effective mission identity to
advance farther than its earliest admission boundary before the store later rejected it.

## Court record

- **Atomic claim:** the worker payload identity and the mission constructor's public and
  durable identities must reject `.` and `..` as well as blank and separator-bearing values.
- **Advocate / Builder:** add the two dot values to the existing predicates, preserving all
  other accepted identifier forms and the existing exact scheduler-binding check.
- **Cross-examination:** do not normalize dot segments or wait for downstream store checks;
  fail before mission state, output paths, source handling, or workspaces are selected.
- **Expert testimony:** a filesystem-facing identifier grammar must rule out traversal
  components, not merely separators, at every early input boundary.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. `.` and `..` are invalid worker, public mission, and durable-resume mission IDs.
2. Existing no-separator and exact-binding conditions remain unchanged.
3. No schema, source custody, policy, credential, or governance behavior changes.

## Migration and rollback

This is additive and schema-free. Existing valid identities remain unchanged. A caller with a
dot-segment identity must supply a distinct portable identifier before execution or resume.
Rollback must not reinterpret dot segments as valid mission locations.

## Builder acceptance evidence

- `tests/test_workers.py` rejects a queued `..` identity before output creation.
- `tests/test_mission.py` rejects a private durable `..` identity at construction.

## Open court obligations

Independent Curator and Judge review remain required. Source safety, hostile-code isolation,
credential mediation, external retention, and production authority remain outside this
tranche.
