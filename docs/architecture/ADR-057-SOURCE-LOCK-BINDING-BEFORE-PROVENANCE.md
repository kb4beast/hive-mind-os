# ADR-057: Source-Lock Binding Before Provenance Admission

- **Status:** Proposed implementation candidate; independent Curator and Judge review pending
- **Date:** 2026-08-03
- **Originating requirement:** P1 correctness hardening after ADR-056
- **Prior decisions:** ADR-043, ADR-048, ADR-055
- **Capability maturity:** bounded provenance-admission ordering correction; no new authority

## Context

`SourceCustodyVerifier.verify_for_materialization` authenticated and recorded a signed
source lock before checking whether it matched the caller's requested repository, commit,
mission, and state. A valid lock for another revision or mission would be rejected for
materialization but still persist in the local append-only source-lock provenance store.
That makes durable provenance contain an admission-side effect for a lock that was never
eligible for the requested operation.

This change does not challenge the signer's statement or remove retained evidence. It
prevents new, mismatched requests from being recorded before their local binding fails.

## Court record

- **Atomic claim:** a source lock must match the requested materialization coordinates
  before signature verification can record it in durable source-lock provenance.
- **Advocate / Builder:** parse the supplied typed lock and apply the exact existing
  `require_materialization` comparison before calling the verifier's record-producing
  signature path.
- **Cross-examination:** preserve signature verification and its signed-lock equality
  check for matching input; reject a forged mismatch without writing provenance, and do
  not replace the signed subject with caller-controlled fields.
- **Expert testimony:** an authentication result is only relevant to an operation after
  its subject is bound to that operation. Ordering the deterministic local check first
  prevents non-admitted assertion retention without changing the trust root.
- **Curator disposition:** pending. Focused tests are Builder evidence only.
- **Judge disposition:** pending. No adoption, production, or superiority conclusion is
  authorized.

## Decision candidate

1. `verify_for_materialization` reconstructs and binds the supplied lock to the requested
   URL, commit, mission ID, and state before signature/provenance admission.
2. The existing signature verifier then validates the same lock and records it only when
   its signed contents also match the prechecked typed lock.
3. A mismatched valid lock fails with no provenance row. Existing accepted rows are never
   deleted or reinterpreted.

## Migration and rollback

No schema changes occur. Previously retained locks remain append-only historical
provenance; they are not claimed to have matched later rejected requests. Rollback must
not remove evidence or present a rejected foreign lock as materialized source custody.

## Builder acceptance evidence

- `tests/test_authenticated_repository_source.py` submits a validly signed lock against
  a different commit request and confirms rejection occurs while source-lock provenance
  remains empty.

## Open court obligations

Independent Curator and Judge review remain required. External retention, source safety,
licensing, credential mediation, hostile-code isolation, and production authority remain
outside this tranche.
