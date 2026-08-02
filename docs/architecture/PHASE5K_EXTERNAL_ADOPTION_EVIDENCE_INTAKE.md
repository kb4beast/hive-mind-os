# Phase 5K — External Adoption Evidence Intake

- **Status:** started; bounded stacked candidate only
- **Base:** `agent/phase5a-orchestrator-shadow` at normal Phase 5J merge commit
  `6c2e76b0e07c038724c39bebf4ab2ad8394e72a7`
- **Authority:** none
- **Activation:** inert
- **External evidence received:** false
- **ADR-015 adopted:** false
- **P14 eligibility:** false

## Objective

Create a package-private, deterministic intake boundary for future external Curator, Judge, and
Orchestrator review evidence. The first increment records the exact packet and debt scope, defines
required trust-anchor and evidence fields, enumerates rejection conditions, and emits an empty
`awaiting-external-evidence` register.

The intake does not create identities, trust anchors, signatures, external retention, decisions,
authority, adoption, P14 eligibility, release readiness, production readiness, deployment,
promotion, superiority, or activation.

## Exact scope

- Repository: `github:kb4beast/hive-mind-os`
- Tenant: `tenant:kb4beast`
- Accepted integration commit: `6c2e76b0e07c038724c39bebf4ab2ad8394e72a7`
- Phase 5J source head: `06b81ee7ae38da9c2050e92b16dfcb1fbc65a97d`
- Required roles: Curator, Judge, Orchestrator
- Permitted future Judge outcomes: `adopt`, `adapt`, `reject`, `defer`, `abstain`
- Active debt inventory: all thirty-five open or reopened Phase 5D–5J items

## Initial outputs

The intake emits four separately digest-bound outputs:

1. `evidence_requirements` — exact participant roles, required evidence fields, trust-anchor and
   external-retention requirements, all marked missing.
2. `verification_policy` — allowed decisions and fixed fail-closed rejection codes.
3. `evidence_register` — empty submissions, no verified identities, no selected decision, and
   `awaiting-external-evidence` status.
4. `intake_disposition` — all adoption, P14/P20, release, production, deployment, promotion,
   superiority, authority, and activation claims fixed false.

## Trust boundaries

1. Exact built-in `dict` and `list` containers are required.
2. Unknown fields, private-content fields, malformed digests, duplicate identifiers, and oversized
   containers fail closed.
3. The first increment accepts no evidence submission and no trust-anchor reference. Non-empty input
   is rejected rather than represented as verified.
4. Participant roles and decision options are fixed and ordered.
5. Future evidence must bind repository, tenant, Phase 5J merge, packet head/tree, role, issuer, key,
   signature, payload digest, scope, evidence index, issue/expiry times, replay nonce, retention,
   revocation, conflict disclosure, and authority reference.
6. Self-issued, unsigned, forged, replayed, expired, revoked, cross-scope, conflicted, unknown-issuer,
   incompletely retained, or incomplete evidence must fail closed.
7. `adopt` may eventually unlock only the exact next permitted phase. Other outcomes cannot be
   treated as approval.
8. All thirty-five debt items remain open or reopened and cannot be cleared by the intake.
9. The candidate remains package-private and outside supported API, CLI, provider, scheduler,
   registry, store, migration, lease, deployment, release, and runtime selection.
10. A procedural assistant cannot satisfy the external review requirement.

## Initial acceptance tests

- deterministic compilation and direct validation;
- exact Phase 5J merge and packet bindings;
- exact thirty-five-item debt inventory;
- exact roles, evidence fields, decision options, and rejection codes;
- exact empty evidence and trust-anchor inputs;
- fail-closed non-empty submission or trust-anchor attempts;
- semantic resealing cannot claim verified evidence, a selected decision, adoption, or eligibility;
- every output digest and envelope digest is checked;
- defensive copies prevent caller mutation; and
- no supported API, CLI, or runtime surface is added.

## Rollback

Delete the two package-private Phase 5K modules, focused tests, Phase 5K evidence, handoff, and this
contract. No external identity, signature, trust anchor, evidence body, decision, authority,
deployment, release, or runtime state is introduced by this increment.
