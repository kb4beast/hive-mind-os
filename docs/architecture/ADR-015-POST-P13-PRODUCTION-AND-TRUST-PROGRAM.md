# ADR-015 — Post-P13 Production and Trust Program

- **Status:** withdrawn as an executable program by P5.2 (2026-08-03)
- **Date:** 2026-07-28
- **Decision:** `adapt`
- **Supersedes:** no prior architecture decision
- **Depends on:** completed P01–P13 implementation boundary at
  `c8f908d4e31d7c469ed2084984cefef59100743f`

## Context

P01–P13 establish a tested local operating kernel, real-provider adapter shape, process-tier
sandbox, Git and GitHub delivery, durable local missions and scheduling, structural Curator
separation, point-in-time replay, a prompt-learning loop, governed source ingestion, and a
single-comparator benchmark court. The final merged audit reports 354 passing tests and no
failures, but it does not establish production readiness.

The source of record remains [`BLOCKERS.md`](../plan/BLOCKERS.md). In particular:

- `B-OPS-03` blocks real-provider end-to-end maturity.
- `B-GOV-02` and `B-GOV-03` block authenticated independence and provider receipts.
- `B-GOV-04` blocks durable external evidence claims.
- `B-OPS-06` blocks hostile-code isolation.
- `B-OPS-04` blocks production readiness.
- `B-OPS-05` blocks superiority claims.
- `B-SRC-01` through `B-SRC-11` preserve unresolved source and licensing obligations.

These are different evidence burdens. Combining them into one delivery would obscure
authority boundaries, make rollback unsafe, and prevent independent review from isolating
failures.

## Historical decision and withdrawal

This ADR originally adapted a second, post-P13 implementation program with separate
PR-sized phases:

1. P14 proves one real-provider, reversible objective-to-delivery mission.
2. P15 authenticates role identities and provider execution receipts.
3. P16 moves evidence to replaceable external append-only retention.
4. P17 adds a hard-isolation adapter for hostile workloads.
5. P18 conducts a bounded production pilot under explicit deployment authority.
6. P19 extends the benchmark court to multiple pinned comparators.
7. P20 adjudicates release readiness after all applicable prior gates pass.

Source and license reconciliation continues as additive, source-specific P12 appeals. It may
run independently, but unresolved sources cannot support production or superiority claims.

P5.2 withdraws that program. P14–P20 are retained as historical documents only and
must not be scheduled. Their external authority dependencies now live in
[Human Authority Gates](HUMAN_AUTHORITY_GATES.md), while the current blocker backlog
remains [`BLOCKERS.md`](../plan/BLOCKERS.md).

## Trust boundaries

- Real-provider capability does not authenticate a provider or verifier.
- Signed identities do not create authority; credentials are issued outside agent control.
- External retention does not make mutable evidence immutable without tested recovery and
  mutation detection.
- The P03 process runner remains useful but is not a hostile-code boundary.
- A successful pilot does not establish general production readiness.
- A benchmark verdict is limited to its pinned comparators, task families, budgets, safety
  floors, and execution environment.
- Source deferral is not source completion.

## Authority and human inputs

The system may implement and test replaceable adapters autonomously. It must stop for:

- provider credentials, model selection, spending limits, and real-call authority;
- identity issuer, signing, retention, and deployment accounts outside agent control;
- source bytes, licenses, reuse grants, historical pins, and custodian attestations;
- production pilot scope and deployment authority;
- comparator access or licenses that cannot be established from public evidence.

Secrets remain environment-only and must never enter code, receipts, logs, fixtures, or
committed evidence.

## Consequences

Positive:

- Capability, trust, isolation, operations, and superiority can advance without conflating
  their burdens.
- Source work can proceed independently without blocking the real-capability path.
- Every claim has a narrow exit artifact and rollback boundary.

Costs:

- Production and superiority remain intentionally unavailable until later phases.
- Some exits require external authority or evidence that agents cannot manufacture.
- Cross-platform hostile isolation and durable external retention require infrastructure
  beyond the current stdlib-only local kernel.

## Rejected alternatives

- **Declare the completed local program production-ready:** rejected; `release_ready=false`
  and the open blockers directly contradict the claim.
- **One post-P13 mega-phase:** rejected; it couples unrelated authority, evidence, and
  rollback boundaries.
- **Treat TLS or provider labels as authenticated execution:** rejected; neither proves the
  acting provider, action, result, policy, lease, or verifier.
- **Treat process-tier checks as hostile isolation:** rejected; P03 does not control network
  syscalls, filesystem mounts/ACLs, executable identity, or all resource limits.
- **Generalize P13 into superiority:** rejected; one comparator and one task family cannot
  satisfy the highest burden.

## Adoption gate

This ADR is retained as historical context. No permitting disposition can reactivate the
withdrawn P14–P20 program; any future proposal must start as a new, independently reviewed
decision without silently reusing this authority.
