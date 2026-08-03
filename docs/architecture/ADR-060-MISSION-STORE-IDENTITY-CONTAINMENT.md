# ADR-060: Mission-Store Identity Containment

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-059
- **Prior decisions:** ADR-052, ADR-053, ADR-054, ADR-058, ADR-059
- **Capability maturity:** bounded durable-storage input-validation correction; no new authority

## Context

`MissionStore` persists durable mission state and derives a mission-root directory by
appending a caller-supplied `mission_id` to its state directory. Its public registration and
root lookup surfaces did not validate that path segment. A direct caller, or a malformed
persisted identifier during recovery, could use `.` or `..` (or a separator-bearing value)
to select outside the intended per-mission root.

## Court record

- **Atomic claim:** every mission-root lookup and new mission registration requires a
  nonempty string that is exactly one non-dot path segment.
- **Advocate / Builder:** centralize the check at `MissionStore.mission_root` and execute it
  at the start of `register_mission`, before configuration verification, database insertion,
  or directory creation.
- **Cross-examination:** preserve normal broad identifier compatibility; reject only
  non-strings, blank values, dot segments, and path separators. Do not normalize a rejected
  value into a different mission.
- **Expert testimony:** durable identifiers become filesystem addressing coordinates at the
  store boundary, so containment must be enforced there even when upstream scheduler and
  mission constructors impose their own checks.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. `mission_root` accepts only a nonempty, non-dot string containing neither `/` nor `\\`.
2. `register_mission` applies the same validation before any persistent or filesystem side
   effect.
3. Existing root consumers inherit the fail-closed check for malformed recovered data.
4. No schema, source custody, policy, credential, or governance behavior changes.

## Migration and rollback

This is additive and schema-free. Existing valid mission directories and records remain
unchanged. Malformed historic rows cannot be resumed into an unintended filesystem root.
Rollback must not reinterpret rejected path-like identifiers as valid mission locations.

## Builder acceptance evidence

- `tests/test_mission_store.py` rejects `..` during registration before a database row or
  mission directory exists, and verifies direct root lookup rejects the same value.

## Open court obligations

Independent Curator and Judge review remain required. Source safety, hostile-code isolation,
credential mediation, external retention, and production authority remain outside this
tranche.
