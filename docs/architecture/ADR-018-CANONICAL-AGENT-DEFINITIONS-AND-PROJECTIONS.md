# ADR-018: Canonical Agent Definitions and Nonauthoritative Projections

- Status: Phase 1 candidate; implementation deferred pending independent judgment
- Date: 2026-07-28
- Constitutional impact: yes
- Extends: ADR-016 and ADR-017

## Context

Generation zero uses `models.Role`, `roles.ROLE_CONTRACTS`, and
`roles.DEFAULT_LIFECYCLE` as its live runtime facade. It manually repeats those
values across vision checks, schemas, package manifests, prompts, skills, and
workflows. The redundancy audit proves that parity is only partially enforced.

## Decision candidate

Phase 2 should introduce an additive, versioned canonical agent definition
whose records own role identity, mission, typed inputs/outputs, requested
capabilities, quality gates, prompt-layer references, skill/tool bindings,
memory boundaries, usage compatibility, evaluation contract, and deferred
obligations.

Python facades, JSON schemas, package records, prompts, workflows, and host
artifacts become deterministic projections. A projection:

- carries the canonical definition digest and generator version;
- is reproducible byte-for-byte;
- cannot grant authority or claim host conformance;
- fails the build when stale or hand-edited; and
- preserves generation-zero behavior until an independently promoted pointer
  selects a v2 champion.

Skills remain independently versioned and reusable. Reuse does not merge
acting, verification, approval, or judgment identities.

## Threats and cross-examination

- A single definition can become a high-impact compromise target.
- Generated artifacts can disguise a harmful source change as mechanical
  churn.
- Host projections can lose semantics or overstate unsupported features.
- Combining role, prompt, skill, and permission records can accidentally turn
  requested capability into granted authority.
- Regeneration can erase deliberate compatibility shims or local annotations.

Controls are content addressing, code review of canonical inputs and generated
diffs, external policy/lease enforcement, host degradation reports, generated
namespaces, golden fixtures, and independent promotion.

## Migration

1. Retain every v1 facade and fixture.
2. Add canonical v2 records without connecting runtime selection.
3. Generate candidate projections and compare them to generation zero.
4. Run shadow role behavior and equal-budget evaluations.
5. Promote one reversible role pointer at a time after independent judgment.
6. Remove a duplicate literal only after every consumer has migrated and its
   compatibility fixture remains available.

## Rollback

Move the independently controlled champion pointer back to the prior v1
definition and regenerate its projections atomically. Preserve the v2
challenger, tests, results, dissent, and receipts. Rollback cannot delete or
rewrite the canonical history.

## Acceptance and outcome metrics

- zero unexplained generated drift;
- all eight generation-zero role/prompt/API fixtures remain valid;
- every projection resolves to one canonical digest;
- no requested capability becomes an authorization;
- host projections emit explicit unsupported/degraded fields;
- shadow behavior meets absolute trust and customer-value gates; and
- activation and rollback are reproduced by a separate Curator.
