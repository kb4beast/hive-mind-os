# Hive Mind OS — Post-P13 Production and Trust Program

- **Plan version:** 2.0-proposed
- **Date established:** 2026-07-28
- **Status:** PROPOSED — preserved for independent adoption review under ADR-015
- **Predecessor:** [`00_OVERVIEW.md`](00_OVERVIEW.md), P01–P13 complete
- **Authority:** [ADR-015](../architecture/ADR-015-POST-P13-PRODUCTION-AND-TRUST-PROGRAM.md)

## 1. Outcome

Convert the completed local/scripted P01–P13 boundary into narrowly evidenced real-provider,
authenticated, externally retained, hard-isolated, operational, and benchmarked capability
without broadening authority or silently clearing source obligations.

No row below may claim more than its exit evidence demonstrates. Production readiness and
superiority remain separate final court decisions.

## 2. Phase index

| Phase | Title | Depends on | Primary blockers | Branch | Status |
|---|---|---|---|---|---|
| [P14](P14_REAL_PROVIDER_CAPABILITY_APPEAL.md) | Real-provider capability appeal | P05, P07, P08 | B-OPS-03 | `phase/P14-real-provider-capability` | pending |
| [P15](P15_AUTHENTICATED_IDENTITY_AND_RECEIPTS.md) | Authenticated identities and provider receipts | P14 | B-GOV-02, B-GOV-03 | `phase/P15-authenticated-identity-receipts` | pending |
| [P16](P16_EXTERNAL_EVIDENCE_RETENTION.md) | External append-only evidence retention | P15 | B-GOV-04 | `phase/P16-external-evidence-retention` | pending |
| [P17](P17_HARD_ISOLATION.md) | Hard isolation for hostile workloads | P03 | B-OPS-06 | `phase/P17-hard-isolation` | pending |
| [P18](P18_BOUNDED_PRODUCTION_PILOT.md) | Bounded production pilot | P14–P17; applicable source appeals | B-OPS-04 | `phase/P18-bounded-production-pilot` | pending |
| [P19](P19_MULTI_COMPARATOR_COURT.md) | Multi-comparator benchmark court | P14, P15, P17 | B-OPS-05 | `phase/P19-multi-comparator-court` | pending |
| [P20](P20_RELEASE_READINESS_COURT.md) | Release-readiness court | P18, P19; applicable source appeals | aggregate | `phase/P20-release-readiness-court` | pending |

Source completion remains a sequence of additive P12 appeals, one source or tightly coupled
source set per branch. Deferred source evidence is never reclassified by a capability phase.

## 3. Dependency graph and concurrency

```text
completed P01–P13
        │
        ├── P14 ── P15 ── P16 ─────────┐
        │      └───────────────┐        │
        ├── P17 ───────────────┼── P18 ├── P20
        │      └───────────────┴── P19 ┘
        └── source-specific P12 appeals ─┘
```

After P14, four tracks may proceed concurrently when file ownership does not overlap:

- **Trust:** P15 → P16.
- **Isolation:** P17.
- **Evidence:** source-specific P12 appeals.
- **Assurance preparation:** comparator/corpus intake for P19, without running a qualifying
  court until P15 and P17 pass.

P18 waits for P14–P17 and every source/license obligation applicable to the pilot. P20 waits
for P18, P19, and every source obligation applicable to the proposed release scope.

## 4. Claims and hard boundaries

| Claim | Minimum permitting evidence |
|---|---|
| Real-provider E2E | One real, reversible mission through all eight roles with complete correlated receipts and independent reproduction; no deterministic substitution for the capability under test. |
| Authenticated independence | Non-self-issued, revocable role identities and authenticated provider receipts; forged, unsigned, replayed, expired, and bypassed evidence fails closed. |
| Durable evidence | Complete evidence-chain recovery after total local-state loss; privileged mutation/deletion is detected. |
| Hostile isolation | Independent adversarial proof of denied filesystem/network/secret access, pinned executable identity, bounded descendants/resources, and protected receipts. |
| Production readiness | Bounded authorized operation meeting declared SLO, safety, recovery, and customer-outcome gates; separate release court. |
| Superiority | Multiple pinned comparators and task families, equal budgets and authority, repeated held-out results, uncertainty, safety floors, raw/losing evidence, and an independent verdict limited to tested scope. |
| Source/license completion | Each source is verified with custody and compatible reuse evidence, or rejected/quarantined with dependent claims excluded; deferral remains incomplete. |

## 5. External-input register

Work must stop rather than invent:

1. model-provider credential, model ID, spending limit, and real-call authority;
2. external identity issuer and non-agent-controlled signing credentials;
3. external append-only retention account and recovery authority;
4. production deployment account, pilot scope, users, and rollback authority;
5. missing source bytes, license/reuse grants, historical pins, and custodian attestations;
6. comparator access and licensing where public evidence is insufficient.

## 6. Executor protocol

The protocol and standard gates in [`00_OVERVIEW.md`](00_OVERVIEW.md) remain in force.
Additionally:

- Run deterministic local tests during development; perform one full validation cycle only
  after the complete PR candidate is ready.
- Network, credential, destructive, deployment, and spend actions require the authority
  explicitly named by the phase.
- A manual real-world run supplements deterministic CI; it never replaces it.
- Each phase uses its listed branch and one PR. Do not combine phases.
- Update [`BLOCKERS.md`](BLOCKERS.md) only when the literal exit condition is reproduced.
- Preserve adverse runs, losing results, failed receipts, rollback evidence, and dissent.
- Run independent Curator, Judge, and Orchestrator review once on the complete candidate.

## 7. Adoption and rollback

This program becomes executable only after ADR-015 and this complete plan receive an
independent permitting disposition. Until then, all rows remain pending proposals.

Rollback removes the new plan pointer while retaining ADR-015, this plan, phase documents,
review evidence, and dissent as historical records. Rollback never changes the completed
P01–P13 boundary or silently closes a blocker.

