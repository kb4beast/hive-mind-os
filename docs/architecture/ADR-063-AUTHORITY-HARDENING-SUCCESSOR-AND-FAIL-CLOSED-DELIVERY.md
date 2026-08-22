# ADR-063: Authority-hardening successor and fail-closed delivery

## Status

Implemented local candidate on `codex/authority-hardening-successor`; independent
Curator review and the external-root gate remain pending. This record supersedes no
historical receipt and does not seal the unsealed 2026-08-13 authority-hardening plan.

## Context

The authority-hardening v1 plan is structurally valid but `DRAFT-UNSEALED`: its
baseline and fingerprint are placeholders and it has no node runbooks or receipts.
Its retained re-audit is valuable negative evidence, not a completion certificate.
That re-audit and successor review reproduced five residual paths relevant to the
present codebase:

1. The module-level `DeliveryGrantLedger` was bare by default. A caller could record
   and spend a self-issued delivery grant before any owner anchor existed.
2. An `EffectGateway` or `DurableEffectOutbox` constructed without an
   `AuthorityRegistry` accepted a previously issued local token. It could not see
   expiry or revocation.
3. The retired `RepositoryMission` still invoked `GitHubClient.deliver` directly,
   bypassing `ControlledGitHubDelivery` and its grant boundary.
4. The retired `AutonomousBrain` accepted caller-controlled remote-push/comment
   booleans and could directly push, create a draft PR, post comments, or poll GitHub.
5. `GitHubClient` itself remained a public raw side-effect API. Its successor migration is
   now specified in ADR-064; the original audit remains retained negative evidence.

The same audit also proved a larger boundary: `AuthorityRegistry.mint_root` records
issuer and authority-reference strings but does not authenticate their holder. A
process-local agent must not manufacture a key or self-issued record and call it owner
authority.

## Decision

### Local candidate

- `DeliveryGrantLedger.record()` and `require_issued()` require a pre-existing,
  sealed owner-authority anchor. An unanchored ledger and a grant without matching
  provenance deny before delivery authorization.
- Every effect execution requires a live `AuthorityRegistry`. The compatibility
  constructors remain available for wiring, but execution, enqueue, and durable
  delivery deny without one.
- Legacy direct GitHub delivery in `RepositoryMission` is disabled. Supplying the
  legacy target causes a recorded mission failure before a push or pull-request
  request. A future migration must use an authority-bound
  `ControlledGitHubDelivery` path with a separately reviewed adapter contract.
- The retired autonomous runtime rejects its remote flags and all direct GitHub
  gateway, feedback, draft-PR, and branch-push entry points before network or Git I/O.

### Boundary deliberately retained

This decision does not claim cryptographic provenance, owner authentication, key
custody, or a production anchoring service. The final successor node requires an
externally administered verifier/signing root and a governed deployment ceremony.
No code in this ADR is a substitute for that root. ADR-064 narrows the raw write surface,
but this ADR still makes no external-authority claim.

## Alternatives rejected

- **Backdate or seal v1:** rejected because its baseline fields are placeholders and
  its historical receipts cannot be made current by declaration.
- **Keep unbound effects for compatibility:** rejected because the live registry is
  exactly where expiry and revocation are observed.
- **Silently route the legacy delivery client through the new boundary:** rejected
  until an adapter proves exact action, target, grant, receipt, and rollback bindings.
- **Generate a local signing key:** rejected because an agent-controlled key cannot
  establish non-agent owner authority.

## Threats and failure modes

- A caller holding an in-process provenance object can still imitate the process-local
  owner record. That is the external-root residual, not a closed security property.
- Legacy callers that supplied `github_delivery` now receive a failed mission report.
  This is an intentional fail-closed compatibility break.
- Autonomous remote-delivery flags and commands now refuse. Its local-only execution,
  point-in-time learning, and supervision without remote feedback remain supported.
- A gateway without a registry can still be allocated, but it cannot run an adapter.
- The grant ledger remains in-memory. Deployment persistence and recovery are outside
  this candidate and must be included in the external-root promotion review.
- ADR-064 quarantines the public raw write methods and removes `GitHubClient` from the
  production push executor. Its independent review remains a required successor gate.

## Migration and rollback

Migrate legacy delivery only by adding a dedicated, authority-bound adapter and
independent integration tests. Until then callers must use a supported controlled path
or accept refusal. Revert this candidate to restore the previous behavior only with a
new security decision; retain the adverse audit evidence and the explicit residual.

## Acceptance evidence

The successor DAG at
[`docs/plan/authority-hardening-successor-2026-08-22/PLAN.md`](../plan/authority-hardening-successor-2026-08-22/PLAN.md)
binds these changes to regression tests and an independent re-audit node. Its external
root node is intentionally `BLOCKED`, so neither this ADR nor its local test results
authorize real remote delivery or claim full authority completion.
