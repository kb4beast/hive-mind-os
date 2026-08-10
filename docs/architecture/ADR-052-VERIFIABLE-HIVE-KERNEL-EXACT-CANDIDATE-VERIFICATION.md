# ADR-052: Verifiable Hive Kernel exact-candidate local verification

## Status

Proposed Phase 8 candidate. This implementation is local and deterministic only. It
does not invoke providers, access a network, call remote CI, alter legacy flows, or
modify historical receipts.

## Decision

`brain_kernel.verification` creates an `EvaluationPlan` from a caller-selected local
base tree. Sealing records both the canonical plan and its complete file manifest in
the append-only kernel spine before candidate verification. A changed base cannot be
sealed under the old plan.

Verification binds one exact candidate snapshot to the sealed base, checks that every
changed path is inside the plan's permitted scope, runs only caller-supplied local
checks, and snapshots the candidate again afterward. Symbolic links, a post-check
mutation, a shared Builder/Curator identity, malformed plan data, or an out-of-scope
change fail the verdict closed.

Each verdict has a self-verifying local evidence bundle published by atomic directory
replacement. The reducer independently validates the plan/result digest bindings. A
work item can enter `ACCEPTED` only from a recorded passed Curator verdict whose digest
is explicitly named by the acceptance transition. Failed verification may retain its
evidence bundle but cannot create a delivery acceptance.

## Consequences and rollback

The change is additive to the kernel and its focused tests. It neither adapts legacy
verification paths nor writes outside caller-selected local candidate and bundle roots.
Rollback stops using the additive API; append-only events and already-published local
evidence remain intact.

## Evidence obligations

Focused tests cover a passing candidate, base drift before sealing, Builder/Curator
identity separation, out-of-scope changes, checker-caused candidate mutation, forged
acceptance, and evidence-bundle tampering. Independent courtroom roles and broader
fixture/environment-contamination coverage remain open.
