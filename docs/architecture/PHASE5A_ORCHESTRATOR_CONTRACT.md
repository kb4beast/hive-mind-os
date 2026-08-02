# Phase 5A Orchestrator contract

## Purpose

Phase 5A provides a deterministic, package-private planning candidate. It translates one strict
request into one inert successor definition and seven typed outputs. It does not perform the
planned work.

## Input contract

`orchestrator-plan-request-v1` requires:

- stable request, objective, tenant, and repository identifiers;
- non-empty objective and acceptance criteria;
- bounded constraints, evidence references, caller-asserted evidence labels, and rollback
  references;
- four orthogonal budget ceilings that are either all known or all unknown;
- positive rollback and verification reserves only when ceilings are known, leaving at least
  one ppm for each work role;
- procedural role labels with caller authentication fixed to false, unique roles, and unique
  actor identifiers;
- bounded ancestry with recursion depth equal to retained ancestry length;
- bounded progress fingerprints;
- explicit proposed, blocked, or recovering objective state; and
- an optional requested next role that is advisory only.

The request field is named `verification_claim_refs` because its values are only caller
assertions. The compiler has no authenticated verifier and therefore never converts those labels
into a `verified` evidence status. This pre-activation contract replaces the misleading draft
field name before any runtime or stored-data compatibility promise exists.

Private bodies, prompts, responses, secrets, hidden reasoning, hostile container subclasses,
unknown properties, mixed accounting, fabricated authentication, duplicate procedural roles or
actors, and evidence labels outside the admitted set fail closed.

## Successor definition

The successor has eight ordered layers:

1. exact Phase 2 Orchestrator base;
2. Generation Zero and built-in prompt binding;
3. bounded deep-playbook responsibilities;
4. built-in `skill.orchestrator` by reference;
5. strict request contract;
6. strict typed-output catalog;
7. Phase 5A governance and court boundary; and
8. unchanged constitutional lifecycle.

Requested capabilities remain unsupported. Effective capabilities and tools are empty. The
reviewed successor carries one ordered immutable instruction for each work role. Each layer
digest and the complete content digest must be internally valid, and the final content digest
must equal the reviewed candidate digest.

## Request snapshot and common output scope

The plan envelope retains the exact validated request as `request_snapshot`. Validation reruns
the request's semantic checks, recomputes its canonical digest, and confirms the request,
objective, tenant, and repository identifiers match the envelope.

Every typed output carries the same:

- request ID;
- canonical request digest;
- objective ID;
- tenant ID; and
- repository ID.

Envelope validation rechecks all five values. A valid nested object cannot be detached from one
request and relabeled as part of another plan.

## Typed outputs

### Objective decomposition

Creates exactly seven work items: Explorer, Architect, Builder, Curator, Integrator, Steward,
and Optimizer. Each work item binds:

- request ID and digest;
- objective ID and text;
- tenant and repository;
- constraints and acceptance criteria;
- all admitted evidence;
- every rollback reference; and
- every earlier work item as a dependency.

Each stable work-item ID derives from the request digest and role. The decomposition repeats the
request scope and cannot change one item independently while remaining valid.

### Dependency graph

Contains seven nodes and the 21-edge transitive closure. Edges may only point from earlier to
later constitutional roles. The graph cannot omit a predecessor, reverse an edge, reference an
unknown node, contain a duplicate edge, or disagree with the decomposition work-item IDs.

### Budget plan

Known ceilings produce a one-million-ppm plan containing positive rollback and verification
reserves plus a positive deterministic allocation for every role. Unknown ceilings keep
reserves and allocations null. Zero on any known axis is exhausted. The candidate never issues
a lease. The stop output must agree with the budget accounting status.

### Court schedule

Contains ten procedural purposes: Orchestrator, Explorer/Advocate, Architect, Builder,
Cross-Examiner, Curator, Integrator, Steward, Optimizer, and Judge. Each stage depends on every
prior purpose. Assigned actor IDs must be unique and remain `procedural-unverified`; missing
actors remain `unassigned`. Authenticated distinct actors are always false.

### Recovery plan

Requires checkpoints, preserves evidence, retains all rollback references, and requires an
external authority to resume. Its rollback set must equal every decomposed work item's rollback
set. It never authorizes activation.

### Stop decision

Evaluates objective state, budget, evidence, recursion, progress, and procedural independence.
It returns defer, stop, or recover; inert Phase 5A cannot return `continue` and completion
remains false.

Evidence status is one of:

- `unknown`: no evidence was admitted;
- `claims-incomplete`: caller assertions do not cover all admitted evidence; or
- `claimed-unverified`: caller assertions cover the admitted set, but no authenticated verifier
  exists.

The reason list is deterministically derived from the status fields. It cannot be replaced with
a more favorable explanation and locally resealed.

### Handoff

Derives the next role from the controlling state:

- recovery, stop, recursion, or stall -> Steward;
- missing or incomplete evidence claims -> Explorer;
- unknown/exhausted budget -> Steward;
- complete-but-unauthenticated evidence claims or procedural/unknown independence -> Curator;
  otherwise
- the next lifecycle stage -> Explorer.

The caller's requested role is retained only as an advisory field and is marked eligible only
when it matches the derived role. `required_refs` is the exact sorted union of admitted evidence,
rollback references, and stop reasons, bounded to 128 entries.

## Integrity and semantic replay

Each of the seven typed outputs has its own canonical digest. The plan envelope has a separate
digest over the entire output set. Validation does not stop at those hashes: it re-derives the
reviewed successor identity, the canonical request snapshot, shared scope, objective text,
constraints, acceptance criteria, evidence and rollback sets, stable work IDs, full dependency
closure, budget ceilings/reserves/allocations, court actor coverage, stop status/reasons,
decomposition unknowns, recovery set, handoff role/reason/eligibility, and required-reference
union.

A caller who alters nested data and recomputes local hashes therefore does not bypass semantic
validation.

## Determinism

All IDs and digests derive from canonical request bytes and fixed contracts. No timestamps,
random identifiers, environment state, chat memory, or filesystem order enter the plan.
Equivalent requests produce byte-identical outputs. Mutation after return cannot change a fresh
compilation.

## Limits

The contracts do not authenticate actors or evidence, execute roles, enforce physical budgets,
persist a mission, schedule processes, invoke tools, compare models, measure customer outcomes,
or prove that the plan is useful. Those obligations remain separate.
