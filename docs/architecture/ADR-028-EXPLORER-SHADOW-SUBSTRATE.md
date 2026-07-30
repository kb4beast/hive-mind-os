# ADR-028: Explorer shadow substrate

- Status: adapted as bounded inert candidate; activation and value claims deferred
- Date: 2026-07-29
- Base: `2cbfe1d0e4dccd6f1758e5ddba10f799834bf857`
- Governing claims: `AG-010`, `AG-014`, `AG-018`–`AG-020`,
  `MEM-018`–`MEM-023`

## Decision

Add an inert, opt-in Explorer shadow substrate with three bounded capabilities:

1. content-addressed reusable discovery-skill definitions;
2. deterministic whole-record context selection that receipts every selected and
   omitted record and fails closed when critical context cannot fit; and
3. one injected, typed discovery call whose findings may enter only the existing
   `OpportunityLedger`.

The selector admits only one tenant/repository, rejects future and same-run records,
excludes quarantined records, never slices record content, and requires blocker,
dissent, authority, provenance, rollback, acceptance, decision, contradiction, and
court coverage. The runner derives collision keys itself, rejects invented evidence
references and action/tool fields, and has no tool, filesystem, Git, web, provider,
public-release, activation, or promotion interface.

## Alternatives

- Skill definitions alone are deferred because static prose is not behavioral
  evidence.
- A live Explorer is deferred because protected-content retrieval, enforced hard
  budgets, persistent loop controls, and real-tool conformance are incomplete.
- Replacing Generation Zero is rejected for this slice; its APIs, prompts, role
  facade, and champion remain unchanged.

## Migration and rollback

The new package-private surface is additive and inactive. Callers must construct it
explicitly with an injected discovery engine and an already authorized
`OpportunityLedger`. Rollback removes that caller; append-only encounters, receipts,
dissent, and evaluation evidence remain.

## Limits

Scripted fixtures can prove deterministic selection, authority containment, typed
admission, and collision safety. They cannot prove curiosity, defect recall,
cross-domain usefulness, customer value, token accuracy, semantic error bounds,
superiority, or readiness for activation.
