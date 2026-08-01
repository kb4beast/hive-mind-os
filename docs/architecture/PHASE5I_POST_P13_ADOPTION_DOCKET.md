# Phase 5I — Post-P13 Adoption Docket

- **Status:** started; bounded stacked candidate only
- **Base:** `agent/phase5a-orchestrator-shadow` at normal Phase 5H merge commit
  `522d04fe76b53574a4f93256466df69de42f747a`
- **Authority:** none
- **Activation:** inert
- **ADR-015 status:** proposed
- **P14 eligibility:** false
- **P20 eligibility:** false

## Objective

Create a package-private, deterministic adoption docket for ADR-015 and the complete post-P13
P14–P20 program. The docket binds the proposed documents, all open or reopened Phase 5D–5H debt,
required independent adoption roles, external-input obligations, and a machine-readable
`awaiting-independent-adoption` disposition.

The docket may prepare evidence for independent review. It cannot authenticate participants, issue
signatures, create external retention, provide credentials, adopt ADR-015, permit P14, clear blockers,
release software, deploy, promote, establish superiority, or activate runtime behavior.

## Normative documents

1. `docs/architecture/ADR-015-POST-P13-PRODUCTION-AND-TRUST-PROGRAM.md`
2. `docs/plan/01_POST_P13_OVERVIEW.md`
3. `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md`
4. `docs/plan/BLOCKERS.md`
5. The normal Phase 5H merge commit and retained Phase 5H court record

## Initial typed outputs

The first increment emits four separately digest-bound outputs:

1. `document_manifest` — exact proposed-document bindings and status.
2. `adoption_requirements` — required Curator, Judge, and Orchestrator roles, all marked
   `required-not-authenticated`.
3. `external_input_register` — the six external-input classes required by the post-P13 roadmap, all
   marked `missing`.
4. `adoption_disposition` — `awaiting-independent-adoption`, with ADR adoption, P14, P20, release,
   production, deployment, promotion, superiority, and activation fixed false.

## Fixed debt posture

The docket admits exactly twenty-five active items:

- `P5D-DEBT-01` through `P5D-DEBT-05`, with `P5D-DEBT-03` reopened;
- `P5E-DEBT-01` through `P5E-DEBT-05`;
- `P5F-DEBT-01` through `P5F-DEBT-05`;
- `P5G-DEBT-01` through `P5G-DEBT-05`; and
- `P5H-DEBT-01` through `P5H-DEBT-05`.

No item is resolved by inclusion in the docket.

## Independent adoption boundary

ADR-015 requires a permitting disposition from distinct independent Curator, Judge, and
Orchestrator participants. Phase 5I records that requirement but does not claim those identities or
executions exist. A procedural pass by one assistant is not authenticated independence.

## External-input boundary

The docket records these missing external inputs without storing secrets or inventing authority:

1. provider credential, model ID, spending limit, and real-call authority;
2. external identity issuer and non-agent-controlled signing credentials;
3. external append-only retention account and recovery authority;
4. production deployment account, pilot scope, users, and rollback authority;
5. source bytes, licenses, reuse grants, historical pins, and custodian attestations; and
6. comparator access and licensing.

## Invariants

1. Exact built-in `dict` and `list` containers are required at trust boundaries.
2. Unknown fields, malformed digests, private-content fields, duplicates, and oversized values fail
   closed.
3. The three proposed document bindings cannot be omitted, reordered, or relabeled adopted.
4. All twenty-five active debt items are required exactly once and retain open/reopened status.
5. Curator, Judge, and Orchestrator requirements remain unauthenticated and unexecuted.
6. Every external-input class remains `missing` until externally supplied and independently verified.
7. The only admitted disposition is `awaiting-independent-adoption`.
8. ADR adoption, P14 eligibility, P20 eligibility, release readiness, production readiness,
   deployment, promotion, superiority, and activation remain false.
9. Request, outputs, and envelope are independently canonical-digest bound.
10. The candidate remains package-private and outside root/package APIs, CLI, provider, scheduler,
    store, migration, lease, deployment, release, and runtime selection.

## Initial acceptance tests

- the example request compiles deterministically and validates;
- all three proposed documents remain exact and proposed;
- all twenty-five active debts remain exact and unresolved;
- all three independent adoption roles remain required but unauthenticated;
- all six external-input classes remain missing;
- semantic resealing cannot claim adoption or P14/P20 eligibility;
- every output and envelope digest is checked;
- caller mutation cannot alter rebuilt outputs;
- modules remain package-private; and
- the carry-forward plan remains present.

## Rollback

Delete the two package-private Phase 5I modules, their focused tests, Phase 5I evidence, and this
contract. No identity, signature, external retention, credential, provider call, deployment,
release, registry, data, scheduler, lease, API, CLI, or activation state is introduced.
