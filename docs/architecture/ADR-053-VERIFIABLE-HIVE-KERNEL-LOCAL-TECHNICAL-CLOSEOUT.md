# ADR-053: Verifiable Hive Kernel local technical closeout

## Status

Proposed Phase 9 candidate. This is a local, deterministic continuation of Phase 8.
It does not invoke providers, access a network, run remote CI, migrate or rewire a
legacy flow, or modify a historical receipt.

## Decision

Add a narrow, additive local technical-closeout path for new `brain_kernel` missions.
It derives a `TechnicalCloseoutReport` entirely from the validated append-only event
spine and self-verifying Phase 8 evidence bundles. The report names the exact event
head, projection digest, completed work, passed evaluation-result digests, evidence
bundle digests, and any unmet local obligation. It may report only:

- `TECHNICALLY_VERIFIED` when every declared local obligation is independently
  represented in the kernel event stream and every implementation work item is bound
  to its passed exact-candidate verdict;
- `PARTIAL` when recorded work is legal but declared obligations are incomplete; or
- `BLOCKED` when a required event, bundle, digest binding, identity separation, or
  local precondition cannot be verified.

The report is not a customer-outcome claim, a courtroom disposition, an external
authenticity claim, or permission to execute an effect. It cannot transform an
existing legacy mission into a kernel mission and cannot make the legacy runtime
write to the kernel store.

Phase 9 may add a `work.integrated`-equivalent kernel transition and a closeout event,
but reducer validation must reject closeout unless all declared local work is
integrated, each implementation work item names its recorded passed evaluation
result, required role results have distinct required identities, and each referenced
Phase 8 bundle re-verifies. Replaying the event stream must derive the same report
and state digest without consulting an untracked file or caller assertion.

Historical receipts remain opaque, immutable evidence. The new path may retain a
caller-supplied receipt reference plus its already-recorded digest and provenance
label in a new kernel event, but it must never copy, normalize, re-sign, delete,
rewrite, reinterpret, or use a historical receipt as proof that a new kernel effect
occurred. Missing or unverifiable historical evidence is reported as an unmet
obligation, not repaired by inference.

## Consequences and rollback

The implementation is limited to additive `brain_kernel` contracts, reducer/service
code, a read-only inspection surface, deterministic fixture support, schemas, and
focused tests. Legacy commands, stores, ledgers, receipt bodies, and compatibility
imports remain unchanged. The closeout command reads an existing kernel database and
does not create one when it is absent.

Rollback disables the new closeout entry point and stops creation of new closeout
events. It does not delete kernel events, local evidence bundles, legacy state, or
historical receipts. A later migration remains blocked on a versioned adapter,
legacy-parity fixtures, an append-only migration record, independently reproduced
rollback, and a separate courtroom disposition.

## Evidence obligations

Focused tests must cover successful local closeout, every incomplete/blocked state,
replay equivalence, forged and mismatched result/bundle/event-head bindings, a missing
role or shared required identity, unintegrated work, a changed evidence bundle, and a
historical-receipt mutation attempt. Compatibility tests must prove that every legacy
CLI route, store, receipt fixture, and prior kernel event stream keeps its existing
behavior and digest. The Advocate, Cross-Examiner, Expert Witness, Curator, and Judge
records remain separate open obligations; this ADR does not claim their dispositions.
