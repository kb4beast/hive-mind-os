# ADR-006: Stage 0 Exit with Fail-Closed Blocker Backlog

- **Status:** Adopted
- **Date:** 2026-07-27
- **Case:** `CASE-P01-STAGE0-CLOSEOUT`

## Context

ADR-002 through ADR-005 closed reproduced fail-open paths in the current-state audit,
executable receipt verification, source governance, and trusted-context reconstruction.
PR #3 delivered those controls at
`f17e95c00b90434d0610f8d4de2c261a74201b8f`; a separate Curator, Judge, and Orchestrator
reviewed that exact candidate, reproduced no blocking defect, and preserved every external
obligation. GitHub merged it into `main` at
`19ca4ab2a52d042570c7d48cd90f3d9406b6d73e`.

The P01 pre-change audit is complete for that exact `main` commit. It conserves 23 sources
and 84 claims, records 20 blocked sources and 73 machine-blocked claims, leaves
`release_ready=false`, and places all 84 claims at either `specified` (65) or
`structurally_prototyped` (19). It contains no executed-in-isolation, independently verified
end-to-end, or production-proven claim.

The remaining work is not another locally reproduced audit-verifier defect. It consists of
missing or externally controlled evidence, host configuration, identity/signing, durable
operation, structural independence, and maturity receipts. Continuing speculative verifier
expansion without a counterexample would violate the recursive-improvement docket's
diminishing-return stopping rule and delay the real-capability path that can produce new
evidence.

## Decision

1. **Stage 0 closes in its fail-closed form.** The master prompt's Stage 0 truth and source
   exit criteria are met because every incomplete source and dependent claim is
   machine-blocked; no broken reference is accepted as a receipt; and no mutable or
   ambiguous repository pin can support an adopted implementation claim.
2. **Closure is not promotion.** Machine-blocked claims remain blocked. This decision does
   not raise any claim's burden, mark a source complete, establish release readiness, prove
   production operation, or support a superiority claim.
3. **Every remaining obligation is tracked.** `docs/plan/BLOCKERS.md` records current
   evidence, owner, target phase, review date, resolution path, and an objective exit
   condition. Source ingestion, licenses, pins, and custody move to P12; GitHub delivery and
   host protection to P07; structural Curator independence to P08; mission durability and
   operations to P06/P11; and later identity, external-ledger, production, and benchmark
   burdens remain explicit post-P13 obligations.
4. **Further Stage 0 verifier hardening requires evidence.** A new audit or verifier change
   must begin with a demonstrated fail-open counterexample, captured by a regression test
   and adjudicated through a new court record. Speculative hardening is outside the closed
   Stage 0 scope.
5. **The canonical sequence is singular.** `docs/plan/00_OVERVIEW.md` owns implementation
   order. Earlier architecture and master-prompt sequencing sections remain preserved as
   historical and normative design context, with additive pointers to the canonical plan.
6. **Dissent and adverse evidence remain preserved.** Rejected intermediate appeals,
   earlier audits, residual risks, unresolved source evidence, and the Windows
   privilege-limited symlink-test skip remain part of the record. Nothing in this decision
   rewrites ADR-005 or converts its open obligations into completion claims.

## Consequences

- P02 through P05 may pursue the real model, sandbox, Git, and vertical-slice capability
  path without waiting for P12 source ingestion, because affected source-derived claims
  remain machine-blocked rather than silently adopted.
- A phase may resolve only blockers within its authority and exit criteria. Missing
  external authority, evidence, licensing, or host state continues to fail closed.
- Stage 0 is described as **closed with tracked blockers**, never “blocker-free,”
  “release-ready,” “production-ready,” or “superior.”
- The blocker census is evidence-derived and may change only through later append-only audit
  and courtroom receipts; the counts in this ADR remain a point-in-time record.

## Rollback

Rollback is additive supersession. If a reproduced counterexample shows that this stopping
decision reopened a fail-open path, quarantine the affected claim, add the regression test
and evidence, and issue a later ADR that reopens the minimum necessary Stage 0 scope.
Do not delete ADR-006, `BLOCKERS.md`, earlier ADRs, audits, court records, source exhibits,
dissent, or rejected candidates.
