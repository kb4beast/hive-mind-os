# Architecture Decision — Verifiable Hive Cortex

## Decision

**ADAPT the current Verifiable Hive Kernel into one canonical Verifiable Hive Cortex.**

The `brain_kernel` event spine becomes the sole authority-bearing mission truth. Existing
`HiveKernel`, `RepositoryMission`, `MissionLoop`, `AutonomousBrain`, scheduler, provider,
verification, learning, and Git/GitHub components are retained only as bounded adapters or
migrated capabilities. No new independent “brain” may own mission truth.

This is the result of the GenericPrompt architecture tournament. It is an implementation
decision for this program, not yet a repository-governance adoption. Node `ARCH-100` must
turn it into a governed repository ADR after live reconciliation and baseline evidence.

## Canonical runtime

```text
Mission Charter / Desired Outcome
            |
            v
Append-only Kernel Event Store  <---- deterministic projections / snapshots
            |
            v
Objective DAG + Desired-State Reconciler + Leases/Scope Locks
            |
            v
Provider-backed RoleRuntime for all eight roles
            |
            +--> Typed Role Consultation / Anti-Cheating Court
            |
            +--> Effect Intent -> Authority -> Durable Outbox
            |                         |
            |                         v
            |                  Idempotent Adapters
            |                         |
            |                         v
            |                    Effect Receipts
            |
            v
Fresh exact-candidate Curator verification
            |
            v
Acceptance / Remand / Quarantine / Replan
            |
            v
Outcome ledger -> lessons -> immutable challengers -> held-out court -> promotion
```

## Non-negotiable invariants

1. **One truth spine.** Every mission state is reducer-derived from append-only events.
2. **Models propose; deterministic code controls.** Models never directly transition state,
   authorize effects, mark acceptance, or promote champions.
3. **All eight roles are operationally meaningful.** Registration or a fixture does not count.
4. **Role-first resolution.** Ambiguity, missing evidence, defects, and suspected cheating are
   routed to applicable roles before a human is considered.
5. **Genuine human authority is not fabricated.** Credentials, consent, legal decisions, spend,
   production access, protected merges, owner value choices, and external commitments remain
   explicit authority boundaries.
6. **Effects are crash-safe.** Intent is durable before execution; adapters are idempotent;
   receipts bind observed effects; the reconciler repairs incomplete states.
7. **Curator independence.** Checks are sealed before candidate access; Builder context and
   hidden target data are excluded; exact commit and tree identities are verified.
8. **No self-improvement in place.** Learning creates immutable challengers. Promotion requires
   independent held-out evidence and an append-only court decision.
9. **No-cheating is executable.** Test weakening, evaluator leakage, future access, self-grading,
   fake/stale evidence, authority expansion, metric gaming, friendly consultation, and concealed
   dissent are adversarial acceptance scenarios.
10. **Recovery without restatement.** Durable state, leases, receipts, and context manifests let
    routine work resume after interruption without the owner transferring context.

## Humanless does not mean authority fabrication

The target is **zero avoidable human answers for routine reversible work**. A software bug,
missing test, design ambiguity, unavailable repository evidence, or suspected cheating is not a
human authority gate. The system must create work, consult roles, gather evidence, remand,
replan, repair, or quarantine. It may escalate only when the missing input is genuinely external
authority that the roles cannot possess.

## Migration disposition

| Current component | Disposition |
|---|---|
| `brain_kernel` contracts, event store, projections, authority, memory, verification | **Retain and make canonical** |
| `ModelBackend` and provider adapters, including Codex subscription | **Adapt behind RoleRuntime** |
| `RepositoryMission` capabilities and receipt discipline | **Extract as effect adapters; retire mission ownership after parity** |
| `MissionLoop` typed actions and iterative Builder loop | **Adapt into canonical role/action protocols** |
| `AutonomousBrain` host invocation, feedback, PIT learning patterns | **Adapt into canonical effects/outcomes; retire separate brain ownership** |
| scheduler and workers | **Adapt to kernel work items and leases** |
| exact verifier and Curator | **Retain and strengthen as acceptance authority** |
| prompt registry, experiment gate, PIT oracle | **Retain; add challenger generation and authenticated independent promotion** |
| fixture-only role handlers | **Retain as conformance fixtures, never count as operational roles** |
| public CLI routes | **Migrate behind compatibility switches, then converge** |

## Why not replace the repository with an external framework

Temporal, DBOS, Restate, LangGraph, AutoGen, and agent SDKs contain useful patterns, but no
single entrant provides Hive Mind OS’s combined truth, authority, exact-candidate evidence,
role lifecycle, anti-cheating, repository migration, and learning burden. Replacing the current
stdlib/local-first kernel would add operational dependencies before the need is proven. The
program therefore imports semantics through adapters and leaves external durable runtimes as a
later governed deployment option.
