# ADR-058: Queued Repository-Mission Identity Binding

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-057
- **Prior decisions:** ADR-052, ADR-053, ADR-054
- **Capability maturity:** bounded worker-entry input-validation correction; no new authority

## Context

The repository-mission worker converted the queued payload's `mission_id` to a string and
used it to find durable state and construct the per-mission output directory. The scheduler
also stores a mission binding on each job, but the worker did not require the payload value
to be a safe identifier or to equal that binding. A malformed or mismatched durable job
could therefore choose a different path or state identity at execution time.

## Court record

- **Atomic claim:** a queued repository mission may use its payload identity only when it
  is a nonempty, non-path-like string and exactly matches the scheduler's mission binding.
- **Advocate / Builder:** validate both facts before opening the mission store or deriving
  an output path.
- **Cross-examination:** retain the queue's existing payload digest and lease semantics;
  reject malformed or unbound jobs rather than normalizing them into a different identity.
- **Expert testimony:** a durable queue identifier crosses from persisted input into both
  provenance selection and filesystem addressing, so exact early binding is required even
  when queue integrity protects the payload bytes.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. `execute_mission_job` requires a nonempty string payload ID containing neither `/` nor
   `\\`.
2. It requires exact equality with `Job.mission_id` before any durable state or output path
   is accessed.
3. The change adds no queue schema, policy, custody, credential, or governance behavior.

## Migration and rollback

This is additive and schema-free. Existing valid queued jobs continue unchanged. A malformed
or mismatched queued job is rejected and remains auditable through the scheduler's existing
retry/dead-letter mechanics. Rollback must not reinterpret rejected jobs as correctly bound
missions.

## Builder acceptance evidence

- `tests/test_workers.py` submits a path-like identity and a payload/scheduler mismatch;
  both are rejected before the worker creates a mission-output directory.

## Open court obligations

Independent Curator and Judge review remain required. Source safety, hostile-code isolation,
credential mediation, external retention, and production authority remain outside this
tranche.
