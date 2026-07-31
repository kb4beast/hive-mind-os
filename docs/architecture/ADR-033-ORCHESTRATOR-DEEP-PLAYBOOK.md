# ADR-033: Inert Orchestrator deep-playbook candidate

- Status: adapted for a bounded draft candidate; activation prohibited
- Date: 2026-07-30
- Extends: ADR-018, ADR-021-PR31, ADR-032
- Runtime selection: unchanged
- Authority: none

## Context

Phase 4 completed only the inert Explorer definition, evaluation, and reference slices that
honest evidence permitted. The next roadmap boundary is Phase 5A: deepen the Orchestrator
without treating planning as execution, procedural role labels as authenticated independence,
or a longer definition as proven behavior.

The Generation Zero and Phase 2 Orchestrator already state the constitutional purpose:
translate outcomes into bounded work, coordinate specialists, and preserve explicit
acceptance criteria and dependencies. They do not provide one strict, deterministic contract
covering request scope, decomposition, dependency closure, budget reserves, court scheduling,
recovery, stopping, and handoff.

## Decision

Add two package-private Python modules:

- `orchestrator_playbook_contracts.py` contains ten strict, fail-closed schemas and semantic
  consistency checks; and
- `orchestrator_playbook.py` composes one inert successor and generates one deterministic plan
  envelope containing seven typed outputs.

The candidate:

1. derives its fixed identity from the exact packaged Phase 2 Orchestrator, Generation Zero
   prompt, built-in `skill.orchestrator`, and constitutional lifecycle;
2. exposes no root API, CLI command, tool, host adapter, provider call, scheduler binding,
   capability, lease, or runtime selector;
3. retains every requested Generation Zero capability only as unsupported metadata and embeds
   one immutable ordered instruction for each non-Orchestrator work role in the reviewed
   successor;
4. embeds the exact validated request snapshot in the plan envelope and binds every output and
   work item to the request ID and digest, objective, tenant, and
   repository; work items also retain the objective text, constraints, acceptance criteria,
   admitted evidence, and rollback set;
5. creates seven non-Orchestrator work items in constitutional order and binds every later item
   to all earlier items;
6. treats `verification_claim_refs` only as caller-asserted labels. Even complete caller claims
   remain `claimed-unverified` because Phase 5A has no authenticated evidence verifier;
7. proposes either a wholly known budget with positive rollback and verification reserves and
   a positive allocation for every role, or a wholly unknown budget without invented values;
8. records a ten-stage procedural court schedule with unique role and actor identifiers,
   explicit procedural/unassigned actor status, and
   `authenticated_distinct_actors=false`;
9. validates each output digest directly and then validates cross-output meaning: scope,
   decomposition/graph closure, budget/stop correspondence, court predecessor closure, stop
   reasons, unknowns, recovery references, state-derived handoff, and the exact handoff
   evidence/rollback/reason union;
10. rejects resealed successor drift by requiring the exact reviewed successor digest in
    addition to layer and content-digest integrity; and
11. fails closed on private-content fields, caller-supplied authentication, mixed accounting,
    ancestry mismatch, recursion limits, repeated/partial-period progress loops, hostile
    containers, unknown fields, and semantic or digest drift.

The maximum output is a plan. It does not execute work, issue leases, approve completion,
activate a candidate, or satisfy an independent court.

## Canonical identities

- Candidate agent: `hive-agent:orchestrator:v2-shadow-1`
- Candidate definition: `hive-agent-definition:orchestrator:v2-shadow-1`
- Base/rollback: `hive-agent-definition:orchestrator:v2-candidate`
- Successor digest: `sha256:e2e6f8ee8975db17a002fafc7d78aa5e2f696540e2ce4404d4548785643528fc`

## Threats and controls

| Threat | Control |
|---|---|
| Planning silently becomes authority | Effective capabilities and tools are empty; authority and activation are fixed to none/inert. |
| Labels are presented as independent actors | Caller-supplied `authenticated=true` is rejected; role and actor IDs must be unique; outputs always state authenticated independence is unavailable. |
| Caller-asserted evidence is presented as authenticated | The field is explicitly named `verification_claim_refs`; complete claims produce `claimed-unverified`, never `verified`. |
| A plan or work item is replayed under another mission, tenant, or objective | The envelope retains the exact validated request snapshot; its digest and scope are rechecked. Each work item binds request ID/digest, objective ID/text, tenant, repository, constraints, evidence, rollback, and acceptance criteria; the stable ID binds request digest and role. |
| A later role runs without prior context | Dependencies and graph edges are the full earlier-to-later transitive closure. |
| Evidence or rollback disappears during decomposition or handoff | Every work item carries the same admitted sets; recovery must match rollback; handoff must equal the bounded union of evidence, rollback, and stop reasons. |
| Budget allocation consumes recovery capacity | Known budgets require positive reserves and a positive allocation for every role; allocations plus reserves equal one million ppm. |
| Unknown accounting is rendered as zero | All budget axes must be wholly known or wholly unknown; unknown reserves and allocations remain null. |
| Recursive self-hosting or oscillation appears as progress | Ancestry must equal recursion depth; depth is bounded; every bounded period is checked for exact or partial-period repetition. |
| Caller steers a later role around a blocker | Requested next role is advisory; the compiler derives the eligible role from fail-closed state. |
| A nested output is changed and the envelope is resealed | Every typed-output digest is checked directly and cross-output semantic relationships are re-derived. |
| A successor layer is changed and locally resealed | Layer/content hashes must be valid and the whole successor must equal the reviewed digest. |
| Mutable subclasses or post-call mutation alter sealed meaning | Exact built-in JSON containers are required and outputs are defensive copies bound by canonical digests. |
| A generated plan is treated as completion | Every output fixes completion or activation authorization to false; inert Phase 5A cannot return `continue`. |

## Migration

No stored schema, pointer, facade, CLI, package resource, or active runtime is migrated.
Adoption consists only of importing the package-private module from explicit development code.
A later runtime binding requires a new migration ADR, authenticated authority, durable storage,
real lease enforcement, behavioral evaluation, and independent promotion evidence.

## Rollback

Remove the Phase 5A modules, tests, inventory, and documents, then restore the ADR index and CI
additions. No data conversion is required. Existing Generation Zero, Phase 2–4 stores,
projectors, resources, and public surfaces remain unchanged.

## Acceptance boundary

Accepted only for an open draft delivery when:

- all ten schema contracts fail closed structurally and semantically;
- deterministic successor and plan digests reproduce;
- adversarial request, authority, replay, budget, recursion, stall, recovery, cross-output,
  scope-binding, evidence-truth, and role-boundary tests pass;
- Phase 2–5A compatibility remains green;
- the isolated wheel imports and compiles the successor and all seven outputs;
- the 133-resource installed-wheel contract remains unchanged;
- Ruff, Pyright, CodeQL, secret scan, dependency/license review, SBOM, and provenance pass on
  the exact hosted head; and
- the procedural court record discloses that one assistant simulated the role purposes and did
  not create authenticated independent actors.

## Explicitly not established

No Orchestrator behavior quality, live coordination, provider/tool use, scheduler operation,
customer value, learning, champion/challenger comparison, promotion, activation, production
readiness, release readiness, or superiority is established. `B-OPS-09` and P20 remain open.
