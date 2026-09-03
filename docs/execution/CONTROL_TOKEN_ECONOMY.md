# Control-plane token economy

`CONTROL-TOKEN-410` reduces coordination context only when the same acceptance,
authority, subject snapshot, route, and budget remain in force.

## Capsules and deltas

One sealed `RoundCapsule` binds the plan, generation, wave manifest, subject,
authority, model route, budget, common body, direct bodies, cold references, and
an explicit route for every node. Every context item is classified for each node
as direct, content-addressed cold, or omitted. `NodeDelta` includes only that
node's direct bodies and cold references; unrelated bodies are absent. The byte
comparison helper accepts actual immutable envelopes, not estimates, and calls a
reduction material only at twenty percent or better.

## Exact test cache

`TestCacheKey` binds an exact subject/commit/tree candidate, full command
descriptor, test set, semantic locks, configuration, toolchain, operating-system
identity, and safe-environment digest. Records are immutable content-addressed
files. The lookup verifies filename, key, canonical bytes, and record seal.
Corruption raises a blocker. Only a zero-exit `PASSED` record is reusable; failure
evidence remains recorded but never skips a later test.

The local filesystem boundary rejects a linked or reparse-point ancestor at
construction, retains the root device/inode identity, rechecks it before access,
and keeps failure records flat beneath that root. These checks detect a
pre-existing unsafe path and a root replacement visible at an observation point;
they do not hold an operating-system directory handle across each lookup or
publication. The cache root therefore requires trusted ACL/custody against a
concurrent adversarial directory swap. Under hostile concurrent filesystem
mutation, cache reuse is not authorized and the cache must be disabled or placed
behind a host adapter with handle-relative operations.

## Evidence compaction

All raw bytes receive a SHA-256 digest, exact exit code, and byte/line counts. Passing logs retain
summaries and a bounded tail. Failure logs retain the first causal line and every
distinct material error. Unrecognized failures retain their first non-empty line
instead of becoming an empty success-looking summary. Oversized logs fail closed
against the declared parsing bound, and compact records can verify later raw
bytes by digest.

## Sidecar calibration

Calibration subtracts measured sidecar input, output, and coordination tokens
from measured avoided parent work. Estimated and unavailable values stay labeled
and cannot enable a sidecar. Comparisons with different acceptance, authority,
subject snapshot, model route, or budget are rejected. One negative measured
trial stops that workload class; otherwise the configured count of controlled
measured trials must clear the positive savings threshold.

This maps `V1-CONTROL-TOKEN-410-OBJ`/`AC-01` to capsules, `AC-02` to the exact
cache, `AC-03` and `AC-04` to compaction and corruption refusal, `AC-05` to
measured-only calibration, and `AC-06` to the controlled byte comparison. A
rollback invalidates affected cache and calibration entries while retaining raw
evidence digests.
