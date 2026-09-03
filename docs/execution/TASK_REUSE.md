# Exact task reuse

`TASK-REUSE-310` runs before model launch. `TaskFingerprint` binds the plan and
node, subject identity and snapshot, relevant content surface, ordered direct
dependency receipts, authority, compiler, policy, environment, and task
contract. Equality means equality of every field and its canonical digest.

`TaskReuseIndex` stores append-only, chained receipts and validates the full
history before making a decision. The possible dispositions are:

- `exact-reuse`: one exact receipt is both independently validated and integrated
  into an exact target identity;
- `verify-existing`: an exact sealed candidate exists but target integration is
  not proven;
- `resume-active`: exactly one matching active attempt exists;
- `repair-existing`: matching checkpointed, failed, or cancelled work exists;
- `execute-new`: there is no prior work for this plan and node;
- `stale`: prior work differs in any fingerprint field;
- `conflict`: multiple active attempts or competing exact candidate/target
  identities exist; and
- `blocked`: a blocker or corrupt evidence prevents safe classification.

An unaccepted branch is never completion. Changed content, dependency receipts,
authority, policy, environment, compiler, contract, or cross-subject identity
changes the fingerprint and invalidates reuse. Receipt corruption blocks reuse
rather than falling back to a cache miss.

Traceability is explicit: `V1-TASK-REUSE-310-OBJ` and `AC-01` map to the complete
fingerprint; `AC-02` maps to the eight dispositions; `AC-03` retains the
validated-integrated-only completion rule; and `AC-04` retains fail-closed
invalidation. Rollback invalidates new reuse decisions but preserves historical
candidate and receipt evidence.
