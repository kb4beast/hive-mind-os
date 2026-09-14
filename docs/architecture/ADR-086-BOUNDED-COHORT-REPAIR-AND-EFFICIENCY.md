# ADR-086: Bounded cohort repair, terminal evidence, and efficiency receipts

## Status

Adapted implementation candidate. Production superiority remains unclaimed until
measured production receipts and independent qualification exist.

## Context

End-loaded execution removes repeated implementation-time hand-offs, but convergence
can still expose failures. Repairing one finding at a time would recreate the serial
coordination pattern at the end of the run. A cohort also needs objective evidence that
its scheduling topology reduces elapsed time and coordination boundaries without
turning a deterministic model into an unsupported production-performance claim.

## Court record and disposition

- Advocate: aggregate terminal findings into one shared repair directive, run its
  conflict-free targets concurrently, then converge and verify exactly once more.
- Cross-Examiner: an unlimited repair loop could conceal a permanently failing cohort;
  an untyped evidence bundle could make "verified" a bare assertion; and modeled speed
  must not be described as measured production speed.
- Expert: cap recovery at one wave, retain synchronous hard-effect gates, require
  digest-bound typed receipts, and label deterministic scheduler estimates explicitly.
- Judge: **adapt** one consolidated repair wave and deterministic topology receipts.
  Fail closed after the wave and preserve external qualification as a separate gate.

## Decision

1. A failed cohort may receive zero or one `RepairDirective`. The directive carries one
   shared instruction and a unique target set.
2. Repair targets must exist, be conflict-free, and remain outside the immutable
   secret, destructive, irreversible, missing-authority, spending, deployment, and
   protected-merge gates.
3. All repair callbacks receive the same immutable kickoff and directive. Results are
   converged once and assessed once after the wave. A remaining failure is terminal;
   the runtime does not begin a package-by-package exchange.
4. Success requires a `TerminalEvidence` bundle whose SHA-256 digest exactly matches
   the canonical convergence output, whose review, aggregate, and verification
   references each bind that digest, and whose producer and terminal reviewer are
   distinct. Untyped, incomplete, self-reviewed, or mismatched evidence fails closed.
5. Deterministic benchmark receipts bind the outcome-graph and duration-manifest
   digests. They compare strict serialization with dependency-, capacity-, path-, and
   semantic-lock-aware cohort scheduling.
6. Benchmark receipts identify their claim scope as
   `deterministic-scheduler-model-only`. Production superiority requires separately
   captured wall-clock measurements and the repository's qualification process.
7. When a journal is configured, the initial pass, repair directive, repair results,
   both terminal assessments, and final completion share one hash-chained lifecycle.
   The repair-attempt event is written before execution. An interruption therefore
   consumes the single repair allowance and fails closed instead of repeating an
   ambiguous effect.

## Threats, migration, and rollback

The primary threat is a repair target set that has overlapping write paths or semantic
locks; such a directive is rejected rather than silently serialized. The second threat
is using repair to retry a hard-gated effect; effect classification is checked again at
the repair boundary. The third threat is evidence fabrication; the local type contract
can prove completeness and binding shape, not external truth, so referenced receipts
remain subject to provenance and qualification checks.

Migration is additive. Callers that need recovery select `CohortAssuranceRuntime`;
plain `CohortRuntime` retains its existing single-pass interface. Rollback removes the
assurance wrapper and retains the initial cohort result, journal, and all referenced
evidence.

## Acceptance evidence

Focused tests prove one repair wave and one reverification, no iterative retry after a
failed repair, fail-closed untyped/incomplete evidence, hard-gate preservation,
conflict-aware deterministic scheduling, dynamic worker refill, exact duration binding,
and explicit model-only claim scope.
