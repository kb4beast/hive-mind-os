# ADR-079: Host-owned N02 admission and evidence registries

- Status: ADAPT implementation candidate; independent Curator judgment required
- Date: 2026-09-14
- Scope: N02 measurement and MatchProtocol software contract
- Builder identity: `/root/n02_security`
- Judge: unassigned and explicitly not this builder

## Case and provenance

The N02 contract in
`docs/plan/whole-os-tournament-2026-09-13/NODES-FOUNDATION.md` requires frozen,
independently signed measurement custody, deterministic triple elimination and no
fabricated external evidence. Five independent Curator reviews were inspected from
their retained review worktrees, culminating in
`C:\h\wos-n02-rereview-r5\docs\benchmarks\whole-os-protocol-curator-r5.md` over
builder commit `92bf72453d80e5f98d496070bccd4f8d7d2214d4`. R5's atomic C1–C8 claims are
retained as the repair requirements: caller-minted authority; incomplete identity;
relabelled OPEN input; stale leases; noncanonical/multi-use receipts; incomplete
terminal/bye/quarantine transitions; unsatisfiable final custody; and bypassable
qualification.

No external source body was newly ingested. The existing EX01/EX03/EX06/EX07 and
N00 evidence obligations remain open; this decision does not infer their content,
license or availability.

## Advocate case

A pure metrics module should not decide whether an evaluator, custodian, manifest,
lease or signature is externally authentic. Moving authentication, opaque-handle
ownership, durable replay, seal history and aggregate issuance into a host-owned
registry creates one replaceable trust boundary. The library can still validate
canonical bindings and deterministic transitions on every use without storing a
secret or treating Python object privacy as authority.

## Cross-examination and threats

- Python protocols cannot prove that an arbitrary object is the production host.
  Therefore the module never labels a result production-ready; the composition root
  owns registry selection. A fake registry is test evidence only.
- Public dataclasses remain constructible. Construction grants nothing because every
  state transition resolves instance-bound opaque handles and every replay-sensitive
  operation is checked by that same registry.
- An in-memory implementation would not prove restart-safe replay. The production
  obligation is a transactional durable registry; the test fake only exercises the
  interface and instance binding.
- Canonical hashes prove equality, not authenticity. Authenticity remains the host
  registry's responsibility and the signed external evidence is still absent.
- Final custody can be internally consistent yet externally fictitious under a fake
  registry. Documentation and JSON therefore remain OPEN and make no N30 claim.

## Expert testimony

The r5 Curator review is treated as independent adversarial testimony for this
repair. It specifically requires a host-owned registry, opaque instance-bound
handles, per-pair/bye receipts, durable replay, repeated lease validation,
append-only seals and admission-bound aggregates. No new independent security or
evaluation witness has yet reproduced this successor candidate.

## Decision

**ADAPT**, pending independent exact-commit Curator review. Remove all verifier/HMAC/
module-token admission minting from `campaign_metrics`. Define only the registry
interface and canonical records. Re-resolve the opaque admission handle for every
schedule, apply, seal, aggregate and decision call. Bind the complete protocol,
stage, tasks/families/strata/repetitions, principals, lease and final pair. Require
one registry-issued receipt per exact pair/bye and exact-set apply through a durable
consume operation. Permit qualification decisions only from registry-resolved
aggregate receipts.

Rejected alternatives are (a) another private module token, (b) caller-supplied
verifier callbacks, (c) status-string closure, (d) self-signed fixture receipts
accepted by production-shaped paths, and (e) a replay set carried only in immutable
caller state. They do not establish host authority or restart durability.

## Acceptance, metrics and rollback

Acceptance is executable in `tests/test_campaign_metrics.py`: OPEN/relabel controls,
foreign registry handles, every bound field, issuer/scope/expiry/revocation, exact
receipt sets, field substitution, replay from a prior state, zero/odd/bye/no-pair,
third loss, dual quarantine, actual final holdout binding, seal order/time/principals,
and exact 12x1/30x3 aggregate membership. Inherited benchmark/evaluation suites must
also pass with worktree-bound imports.

Outcome metric: every r5 executable counterexample fails at its intended boundary
while the fixture-only complete path succeeds. This is software conformance, not a
benchmark outcome or superiority result.

Rollback is the parent commit
`92bf72453d80e5f98d496070bccd4f8d7d2214d4`; no external state, credential,
comparator, holdout or lease is changed by this repair. The successor schema is
intentionally incompatible with the caller-verifier API so an unsafe fallback cannot
silently survive migration.

## Open obligations and dissent

N30 must supply a durable authenticated registry implementation, host composition,
external manifests/signatures/custody, comparator rights and bytes, provider/runtime
authority, and bounded lease. A future Curator may reject this interface if the
production composition allows untrusted registry injection or if transactional
issue/consume/append behavior is not demonstrated. No N30 readiness or promotion is
claimed here.
