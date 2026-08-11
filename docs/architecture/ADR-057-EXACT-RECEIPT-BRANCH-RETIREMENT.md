# ADR-057: Exact receipt-branch retirement for rejected Explorer receipt

## Status

Adopted for one sealed recovery only.

## Decision

The unintegrated `EXPLORER-310` candidate
`3d305e63391094846e8d8ebacad2fa73dbb2db8b` and its durable receipt/head
`2304036fe92e7fe499785a500c173300943a55fb` remain preserved evidence, but
cannot occupy `autopilot/explorer-310` after the candidate was shown to allow
`git diff --output=...` writes. `.autopilot/receipt-branch-retirements.json`
is a separate, exact-only record; it does not alter the sealed plan fingerprint
or the existing RECON-010 amendment.

The recovery creates a zero-path retirement commit whose only parent is the bad
receipt and whose tree is identical. One `git push --atomic` then creates the
configured quarantine ref at that retirement commit and deletes the active
branch only with an expected-SHA force-with-lease. The controller verifies both
postconditions before recording success. A fresh GitHub snapshot, target
reconciliation, and dispatch are required before a replacement Explorer claim.

## Threats and rollback

An altered record, a changed active branch tip, a pre-existing quarantine ref,
or a failed atomic push fails closed before a successful retirement is recorded.
The quarantine ref retains the bad candidate, receipt, and retirement rationale.
Rollback is a separately authorized recreation of `autopilot/explorer-310` from
the quarantine ref; this capability never force-updates an existing ref and
does not perform that rollback automatically.
