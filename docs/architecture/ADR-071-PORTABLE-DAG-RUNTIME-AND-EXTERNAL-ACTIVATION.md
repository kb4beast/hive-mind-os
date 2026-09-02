# ADR-071: Portable DAG runtime and external one-run activation

Status: proposed `adapt`; candidate implementation and independent court pending

Date: 2026-09-02

## Context

The Generic Hive Mind Product V3 overlay defines a complete 20-node, eight-role product
program, but its frozen Standard-V2 execution mode is intentionally
`manual-parent-v1`: it contains no runnable command and the installed controller accepts
only `.autopilot/plan.json`. Pull request 154 later squash-merged the V3 tree and severed
the historical commits used by its regression suite. ADR-070 repairs that evidence
boundary without pretending that V3 became executable.

A local V4 draft introduced an inert manifest and an external-signature concept. It did
not contain a plan, accepted placeholder artifact identities, compared principals only by
labels, and let a nonce ledger key replay protection by `(nonce, payload)`. Those gaps make
the draft useful source evidence but not an activation candidate.

## Decision

Implement a subject-neutral portable runtime as a versioned product surface rather than
modifying the frozen `.autopilot` compiler. The runtime uses closed, strict JSON contracts
for subject identity, resources, adapters, capabilities, authority, budgets, recovery,
integration, evidence, and nodes. A canonical packaged compiler validates the exact plan,
builds deterministic conflict-free rounds, and leaves all host effects behind injected
adapters and explicit authority envelopes. Repository and non-repository subjects use the
same interfaces.

Complete the previously planned product modules for plan lineage and generation, runtime
contracts, adapters and indexing, durable waves and integration, task and test reuse,
context and token accounting, the generic executor, public CLI, recovery, fixtures, and
qualification. Preserve eight lifecycle dispositions even when deterministic checks avoid
model calls. Read-only commands accept explicit absolute inputs and do not create state.

Replace the V4 activation draft with an ordered external gate:

1. Strictly parse and hash the exact manifest, plan, independent-review record, and
   frozen-host record.
2. Bind request, repository, predecessor, candidate parent, candidate commit/tree/content,
   plan, manifest, evidence, five structured principals, lease, and nonce.
3. Verify the independent reviewer and frozen-host signatures through host-injected
   verifiers.
4. Verify the distinct external issuer signature over the complete bundle.
5. Atomically consume a globally unique nonce, keyed by nonce alone, in host-owned storage.
6. Return a typed one-run capability. The repository never mints a signature or nonce and
   a checked-in manifest remains `execution_authorized: false`.

The activation never authorizes a protected merge. Delivery of a review branch or draft
pull request is separately bounded; merging `main`, obtaining credentials, accepting
terms, spending, deployment, and production mutation remain external authority gates.

## Invariants and threats

- Duplicate JSON keys, non-finite numbers, excessive size/depth, unknown fields, stale
  leases, artifact substitutions, candidate/parent collapse, identity/key collisions,
  non-adopting review, dirty or writable frozen-host claims, bad signatures, and nonce
  replay fail before execution.
- Graph level is not authority. Workers are admitted only by exact dependencies, resource
  conflicts, adapter availability, live authority, budgets, and an authenticated run.
- Candidate, test, transaction, and effect identities are content-addressed. Recovery may
  adopt exact prior work but never repeats an externally observable effect.
- Repository code cannot establish that an external principal is honest, that a host is
  physically read-only, or that a host ledger is truly atomic. Those properties remain
  independently attested and operationally enforced; injected verifiers do not turn local
  strings into trust.
- A signature over a substitute but internally self-consistent candidate is valid only if
  every independent binding names that same candidate. Review and host attestations are
  therefore separately signed and included by raw digest in the issuer bundle.

## Migration

Land the squash-proof V3 baseline correction and the portable runtime together on an
ordinary `codex/` review branch based on canonical `main`. Preserve the abandoned local
V4 commits as provenance; do not cherry-pick their weak schema unchanged. Publish an exact
V3 correction candidate as a separate immutable ref for review, then bind V4 to that
commit/tree and its qualification receipt. Existing `.autopilot` state remains untouched
and quiescent.

After independent review and full supported-host CI, publish one draft pull request. A
trusted host may then create fresh signed review/frozen-host records and an issuer bundle
for a maximum 15-minute lease, consume the nonce, and run exactly the bound candidate.
No expired or partially populated template is executable.

## Rollback

Revert the portable-runtime candidate commit and close its unmerged pull request. Preserve
all source intake, losing designs, court records, benchmark lanes, failed signatures,
consumed nonces, and adverse CI. Never reuse a consumed nonce or rewrite a V3/V4 manifest
to make a later candidate appear identical. Existing Autopilot state and protected
branches are outside this rollback and must not be reset.

## Acceptance

- Focused tests cover every module and public command, plus cross-language and
  non-repository fixtures, deterministic recovery, conflict and drift failures, replay,
  duplicate effects, and a controlled token comparator.
- Full repository CI passes on Linux Python 3.11/3.12/3.14 and Windows 3.12/3.14.
- A separately identified Curator reproduces exact artifacts and a distinct Judge issues
  a courtroom disposition after the final candidate is frozen.
- The final handoff names exact commits, trees, artifact digests, CI receipts, the unmerged
  pull request, and any remaining external signature/nonce/merge gates without claiming
  A5, production readiness, release readiness, or superiority.
