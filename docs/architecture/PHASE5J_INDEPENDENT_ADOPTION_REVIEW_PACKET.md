# Phase 5J — Independent Adoption Review Packet

- **Status:** started; unsigned external-review packet only
- **Base:** `agent/phase5a-orchestrator-shadow` at normal Phase 5I merge commit
  `49b78e211053f8aec427351680c3fd683044420d`
- **Authority:** none
- **Activation:** inert
- **Review status:** not-run
- **Packet status:** ready-for-external-review

## Objective

Create a package-private, deterministic packet that freezes the exact proposed Post-P13 program,
all thirty open or reopened Phase 5D–5I obligations, participant requirements, unselected decision
templates, and the external action required to conduct a real adoption review.

This phase prepares materials for distinct external Curator, Judge, and Orchestrator participants. It
does not authenticate participants, create signatures, select a verdict, adopt ADR-015, unlock P14,
approve P20, or authorize release, production, deployment, promotion, superiority, or activation.

## Frozen review scope

1. Phase 5I normal merge commit and tree.
2. ADR-015 proposed bytes.
3. `docs/plan/01_POST_P13_OVERVIEW.md` proposed bytes.
4. `docs/plan/PHASE5_CARRIED_FORWARD_DEBT.md` bytes.
5. All thirty open or reopened `P5D-DEBT-01` through `P5I-DEBT-05` items.
6. Six missing external-input classes recorded by Phase 5I.
7. Existing adverse, dissenting, passing, failing, deferred, and inconclusive evidence references.

## Initial typed outputs

The first increment emits four separately digest-bound outputs:

1. `review_packet_manifest` — exact frozen documents, commit/tree, debt inventory, and packet status.
2. `participant_requirements` — Curator, Judge, and Orchestrator identity, signature, conflict,
   retention, expiry, revocation, replay, and scope-binding requirements, all unsatisfied.
3. `decision_templates` — unselected `adopt`, `adapt`, `reject`, `defer`, and `abstain` templates.
4. `external_handoff` — explicit human/external actions and `external-action-required` status.

## Invariants

1. Trust boundaries require exact built-in `dict` and `list` containers.
2. Unknown fields, duplicate IDs, malformed digests, private content, and oversized values fail closed.
3. The exact thirty debt IDs are required once in canonical order.
4. Curator, Judge, and Orchestrator are all required and remain `required-not-authenticated`.
5. No identity, signature, execution, retention, or authority evidence may be claimed present.
6. All decision templates remain unselected and unsigned.
7. Dissent, rejection, abstention, narrowing through `adapt`, and `defer` remain valid outcomes.
8. Packet readiness means only that external review materials exist; it is not a permitting decision.
9. ADR adoption, P14/P20 eligibility, release, production, deployment, promotion, superiority,
   authority, and activation remain false or none/inert.
10. Request, outputs, and envelope are independently canonical-digest bound.
11. The modules remain package-private and outside root/package APIs, CLI, provider, scheduler, store,
    migration, lease, deployment, release, and runtime selection.
12. One assistant may prepare the packet, but authenticated independent review cannot occur inside this
    procedural session.

## Initial acceptance tests

- example request compiles deterministically and validates;
- exact commit, tree, documents, external inputs, and thirty debts are preserved;
- exact Curator/Judge/Orchestrator requirements remain unsatisfied;
- every decision option exists and remains unselected and unsigned;
- semantic resealing cannot claim adoption or eligibility;
- every output and envelope digest is checked;
- caller mutation cannot alter rebuilt outputs;
- modules remain package-private and no supported surface is added; and
- the handoff explicitly requires external action.

## Completion boundary

Phase 5J completes when the unsigned packet, deterministic contracts, adversarial tests, audit ledger,
and a copyable human handoff are committed. It must stop there. External participants must review the
frozen packet outside this procedural session and return authenticated, externally retained evidence.

## Rollback

Delete the two package-private Phase 5J modules, tests, Phase 5J evidence, and this contract. No
identity, signature, review result, runtime, provider, scheduler, store, lease, API, CLI, deployment,
release, promotion, or activation state is introduced by this increment.
