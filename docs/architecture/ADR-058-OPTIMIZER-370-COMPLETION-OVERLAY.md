# ADR-058: Exact OPTIMIZER-370 completion overlay

## Status

ADAPT, under the separate Court and Appeals records dated 2026-08-11.

## Context

The sealed OPTIMIZER-370 receipt truthfully preserves incident base `cfe17ff7`, while its
repair execution merged the zero-path claim with singleton release `G=9ea57b8e`. The generic
durable receipt validator therefore sees the broad `cfe..final` release diff, although the
actual `G..final` implementation diff is exactly the two authorized Optimizer paths. A release
advance during completion can also make the captured G lease look stale, and two completion
write orderings were not restart-safe.

## Decision

Add an incident-only overlay that evaluates every generic receipt rule and discards only the
single incompatible generic base-to-final changed-path diagnostic after exact immutable receipt
and Git topology checks pass. It independently requires both authorized paths in the exact
`G..final` diff.

The controller may pin one exact successor H only while the original claim is `CLAIMED` and
unexpired. H must be the direct reseal child of the compiled capability, the capability must be
a direct child of G, the complete G-to-H path set must equal this ADR's overlay, remote main must
remain unchanged, and PR 135 must still point to candidate 948. A durable state machine records
`ACTIVE`, `CONSUMING`, and `CONSUMED`; no sibling or later descendant is accepted.

Git-backed repositories must use Git object verification. Git execution isolates global/system
configuration, rejects repository-local includes, URL rewrites, protocol/HTTP overrides, and
remote-helper substitutions before transport, and does not disable TLS or certificate revocation.

## Rollback

Before receipt publication, restore an exact `CONSUMING` continuation to `ACTIVE` only after the
remote and local candidate state are restored. After exact receipt publication, retain the
`CONSUMED` marker and append-only old/new receipts. Any ambiguous rollback becomes `ADVERSE`.

## Consequences

This overlay cannot claim new work, integrate H, merge PR 135, repair another node, accept a third
receipt, or renew the immutable claim message. Those remain outside this capability.
