# ADR-053: Recovered Workspace Identity Validation

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-052
- **Prior decisions:** ADR-040, ADR-047, ADR-052
- **Capability maturity:** bounded recovery input-validation correction; no new authority

## Context

ADR-052 binds new workspace receipts to the durable repository mission. On resume, the
completed materialization checkpoint carries the historical `git_mission_id` used to
recreate the adapter. The recovery path converted that value with `str(...)`, allowing a
malformed checkpoint value such as a mapping to become an arbitrary receipt/state
identifier rather than failing at the durable boundary.

This correction does not repair a corrupted checkpoint, authenticate its local store,
alter historic workspace identities, or provide external custody. It rejects malformed
recovery metadata before filesystem adapter reconstruction.

## Court record

- **Atomic claim:** a completed materialization checkpoint may reopen a workspace only
  when its Git mission identity is a nonempty string without path separators.
- **Advocate / Builder:** validate the checkpoint value before passing it into
  `reopen_workspace`; preserve valid historical IDs exactly instead of replacing them.
- **Cross-examination:** reject missing, non-string, empty, and path-like identities
  before reopening; do not coerce untrusted structured data with `str()`.
- **Expert testimony:** type and path validation at the checkpoint adoption boundary
  prevents malformed state from influencing adapter identity or receipt state references.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. A completed workspace-materialization outcome must be a mapping containing a valid
   `git_mission_id` string. Otherwise recovery fails with `MissionFailed` before calling
   `reopen_workspace`.
2. Valid legacy IDs remain supported for exact recovery. This is validation, not a
   migration or new identity authority.
3. The normal local and authenticated source paths continue to pass a stable mission ID
   established by ADR-052 and ADR-048 respectively.

## Migration and rollback

No schema changes or backfills occur. An active mission whose retained materialization
checkpoint has malformed identity metadata is blocked from recovery and requires the
existing reconciliation/rematerialization path. Rollback retains all checkpoint evidence
and does not claim that the malformed value was valid.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` injects a structured forged workspace
  identity into an otherwise completed checkpoint and proves recovery rejects it before
  the reopening adapter is called.

## Open court obligations

Independent Curator and Judge review remain required. External custody, source safety,
hostile-code isolation, credential mediation, external retention, and production authority
remain outside this tranche.
