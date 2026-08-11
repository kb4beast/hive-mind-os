# ADR-055: Exact Explorer receipt-branch retirement

## Status

Adopted only for the sealed `EXPLORER-310` rejected receipt branch.

## Context

The Explorer L2 receipt branch contains a read-only-boundary violation. Its candidate
and receipt are evidence, not delivery, and cannot be deleted silently. The normal
claim protocol correctly refuses to reuse an existing remote node branch, but had no
bounded way to retain this rejected branch and permit a clean replacement claim.

## Decision

`.autopilot/bin/autopilot.py` exposes one command for one configured record. It accepts
only the sealed retirement ID and actor; it accepts no remote, branch, ref, SHA, or
replacement-node input. The record binds `origin`, `kb4beast/hive-mind-os`, the singleton
target, candidate, receipt, blocker, court-quarantine digest, archive ref, and expected
source SHA. The canonical court record is retained separately and its digest is checked.
The configured origin URL must be the sole fetch URL; any `remote.origin.pushurl`,
`url.*.insteadOf` / `pushInsteadOf`, or process-injected Git config causes a fail-closed
refusal, because fetch identity alone does not prove the atomic push destination.

The command requires current target reconciliation and snapshot evidence and no active
Explorer claim. It fetches and validates the candidate and completion receipt, creates a
zero-path archive commit with the receipt as its sole parent and the identical tree, then
uses one atomic origin push. The push creates the empty archive ref and deletes the source
only under exact source and archive-absence leases. It re-reads both refs and archive
contents before an append-only local execution/audit record can say `RETIRED`.

A fresh clone can recover only from a verified archive with no source. After retirement,
a controller-local recovery marker requires a new snapshot installation and reconciliation
before a new dispatcher release or claim is accepted. This does not alter generic snapshot
semantics or rewrite the sealed plan, L0/L1 receipts, or authority amendments.

## Consequences and rollback

The active rejected branch may become absent, but its exact receipt remains reachable from
the immutable quarantine ref. The operation never force-updates the singleton release or
`main`; this implementation does not execute retirement. A failed lease, archive collision,
remote movement, malformed court record, missing evidence, or failed verification leaves
the active source untouched and requires investigation. Restoration, if ever separately
authorized, must create a new named ref from the retained archive parent; it is not part of
this command.
