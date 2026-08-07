# Verifiable Hive Kernel: Phase 8 exact-candidate local verification

## Candidate implementation

This phase begins from `4e82fc7`. It adds one local-only exact-candidate verification
path. A sealed evaluation plan contains the base-tree digest and is durably paired
with a complete base file manifest before the candidate is read. Verification compares
the candidate to that manifest, rejects unsafe links and path-scope escapes, invokes
only the supplied local checker, and detects checker-caused mutation by a second
snapshot.

The verifier creates a canonical result and atomically publishes a local evidence
bundle. The kernel reducer accepts a plan only for running work and a Curator verdict
only for awaiting verification. An `ACCEPTED` work transition is rejected unless it
names the same passed result digest recorded for that work.

## Completion boundary

This completes the Phase 8 exact-candidate local verification slice. It does not run
remote CI, call a provider, change legacy verification or receipt flows, or claim an
independent courtroom disposition. Environment-contamination fixtures, adapter wiring,
and broader mission-completion integration are explicitly deferred.
