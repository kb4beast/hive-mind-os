# ADR-084: End-loaded cohort execution with synchronous hard gates

## Status

Adapted implementation candidate. Independent Curator and security review remain
required before promotion.

## Context

The existing lifecycle places review, evidence aggregation, and role hand-offs between
small implementation steps. That maximizes local scrutiny but serializes independent
work and spends coordination effort before a candidate has converged. For routine,
reversible repository changes, the same assurance can be collected more efficiently as
one cohort-end bundle without dropping any obligation.

End-loading cannot apply to authority or irreversible-effect decisions. Secrets,
destructive or irreversible operations, missing authority, spending, deployment, and
protected merges can escape the repository rollback boundary and therefore must stop
before the effect.

## Court record and disposition

- Advocate: run a complete conflict-free implementation cohort in parallel, converge
  once, then perform review, evidence aggregation, and independent verification once
  against the integrated candidate.
- Cross-Examiner: batching can conceal a dangerous effect or become a spelling of
  "skip review" unless the deferred obligations and hard gates are immutable.
- Expert: separate scheduling policy from authority policy. The cohort contract may
  move routine assurance in time, but it cannot grant an action or weaken the existing
  policy engine.
- Judge: **adapt** end-loaded cohorts with a closed configuration, a fixed convergence
  gate, explicit deferred obligations, and synchronous hard-gate classification.

## Decision

1. Add `strict` and `cohort` execution modes. Strict mode keeps routine assurance at
   each checkpoint. Cohort mode defers it only during implementation.
2. A cohort converges only when all runnable packages are terminal. At convergence and
   closeout, routine review, evidence aggregation, and independent verification are
   required as one complete bundle.
3. The maximum parallel package count is configurable, positive, and digest-bound.
4. Secrets, destructive effects, irreversible effects, missing authority, spending,
   deployment, and protected merges always return an immediate blocking decision in
   every mode and phase.
5. The scheduling contract never grants authority. Existing role capabilities,
   external grants, protected-branch rules, and effect adapters remain authoritative.
6. Unknown configuration keys, alternate convergence gates, untyped actions, and
   missing authority fail closed.

## Threats, migration, and rollback

The main threat is accumulated defects across a large cohort. Conflict-free package
leases, bounded parallelism, deterministic convergence, and one integrated assurance
bundle contain that risk. The second threat is interpreting deferred evidence as absent
evidence; typed obligations remain attached to every deferral and become mandatory at
convergence. The third threat is using cohort mode as an authority bypass; the hard-gate
set is code-defined and not configurable.

Migration makes `cohort` the default for new direct and Whole-OS runs. Existing callers
that require the former hand-off sequence can explicitly select `strict`. Rollback
selects `strict`, preserving all retained execution and evidence records.

## Acceptance evidence

Focused tests must prove closed configuration round-tripping, immutable convergence,
complete deferred obligations, strict-mode compatibility, convergence enforcement, and
fail-closed handling of every hard-gate class in every execution phase. They must also
prove mappings from the existing policy actions for secrets, spending, deployment, and
protected merges.
