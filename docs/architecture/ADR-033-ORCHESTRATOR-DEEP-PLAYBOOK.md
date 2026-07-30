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
covering decomposition, dependency closure, budget reserves, court scheduling, recovery,
stopping, and handoff.

## Decision

Add two package-private Python modules:

- `orchestrator_playbook_contracts.py` contains ten strict, fail-closed schemas; and
- `orchestrator_playbook.py` composes one inert successor and generates one deterministic
  plan envelope containing seven typed outputs.

The candidate:

1. derives its fixed identity from the exact packaged Phase 2 Orchestrator, Generation Zero
   prompt, built-in `skill.orchestrator`, and constitutional lifecycle;
2. exposes no root API, CLI command, tool, host adapter, provider call, scheduler binding,
   capability, lease, or runtime selector;
3. retains every requested Generation Zero capability only as unsupported metadata;
4. creates seven non-Orchestrator work items in constitutional order and binds every later
   item to all earlier items;
5. binds admitted evidence and rollback references into every work item;
6. proposes either a wholly known budget with positive rollback and verification reserves,
   or a wholly unknown budget without invented allocations;
7. records a ten-stage procedural court schedule while fixing
   `authenticated_distinct_actors=false`;
8. fails closed on private-content fields, caller-supplied authentication, mixed accounting,
   ancestry mismatch, recursion limits, repeated/partial-period progress loops, unbounded
   containers, unknown fields, and output-digest drift; and
9. derives stopping and handoff from evidence, budget, recovery, recursion, stall, and
   independence state rather than caller preference.

The maximum output is a plan. It does not execute work, issue leases, approve completion,
activate a candidate, or satisfy an independent court.

## Canonical identities

- Candidate agent: `hive-agent:orchestrator:v2-shadow-1`
- Candidate definition: `hive-agent-definition:orchestrator:v2-shadow-1`
- Base/rollback: `hive-agent-definition:orchestrator:v2-candidate`
- Successor digest: `sha256:27ee0dd40c63e1fcae04425552d8e3e3c124a807bb9f4cea4b06cca2809b9574`

## Threats and controls

| Threat | Control |
|---|---|
| Planning silently becomes authority | Effective capabilities and tools are empty; authority and activation are fixed to none/inert. |
| Labels are presented as independent actors | Caller-supplied `authenticated=true` is rejected; outputs always state authenticated independence is unavailable. |
| A later role runs without prior context | Dependency graph is the full earlier-to-later transitive closure. |
| Evidence or rollback disappears during decomposition | Every work item binds the complete admitted evidence and rollback sets. |
| Budget allocation consumes recovery capacity | Known budgets require positive rollback and verification reserves; allocations plus reserves equal one million ppm. |
| Unknown accounting is rendered as zero | All budget axes must be wholly known or wholly unknown; unknown allocations remain null. |
| Recursive self-hosting or oscillation appears as progress | Ancestry must equal recursion depth; depth is bounded; exact and partial-period loops stop. |
| Caller steers a later role around a blocker | Requested next role is advisory; the compiler derives the eligible role from fail-closed state. |
| Mutable subclasses or post-call mutation alter sealed meaning | Exact built-in JSON containers are required and outputs are defensive copies bound by canonical digests. |
| A generated plan is treated as completion | Every output fixes completion or activation authorization to false. |

## Migration

No stored schema, pointer, facade, CLI, package resource, or active runtime is migrated.
Adoption consists only of importing the package-private module from explicit development code.
A later runtime binding requires a new migration ADR, authenticated authority, durable storage,
real lease enforcement, behavioral evaluation, and independent promotion evidence.

## Rollback

Remove the Phase 5A modules, tests, inventory, and documents, then restore the ADR index and
CI additions. No data conversion is required. Existing Generation Zero, Phase 2–4 stores,
projectors, resources, and public surfaces remain unchanged.

## Acceptance boundary

Accepted only for an open draft delivery when:

- all ten schema contracts fail closed;
- deterministic successor and plan digests reproduce;
- adversarial request, authority, replay, budget, recursion, stall, recovery, and role-boundary
  tests pass;
- Phase 2–5A compatibility remains green;
- the isolated wheel imports and compiles the successor and all seven outputs;
- the 133-resource installed-wheel contract remains unchanged;
- Ruff, Pyright, CodeQL, secret scan, dependency/license review, SBOM, and provenance pass on
  the exact hosted head; and
- the procedural court record discloses that one assistant simulated the role purposes and
  did not create authenticated independent actors.

## Explicitly not established

No Orchestrator behavior quality, live coordination, provider/tool use, scheduler operation,
customer value, learning, champion/challenger comparison, promotion, activation, production
readiness, release readiness, or superiority is established. `B-OPS-09` and P20 remain open.
