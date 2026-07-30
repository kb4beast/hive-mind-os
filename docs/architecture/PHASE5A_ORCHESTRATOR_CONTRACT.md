# Phase 5A Orchestrator contract

## Purpose

Phase 5A provides a deterministic, package-private planning candidate. It translates one
strict request into one inert successor definition and seven independently valid outputs.
It does not perform the planned work.

## Input contract

`orchestrator-plan-request-v1` requires:

- stable request, objective, tenant, and repository identifiers;
- non-empty objective and acceptance criteria;
- bounded constraints, evidence references, verified-evidence subset, and rollback references;
- four orthogonal budget ceilings that are either all known or all unknown;
- positive rollback and verification reserves only when ceilings are known;
- procedural role labels with caller authentication fixed to false;
- bounded ancestry with recursion depth equal to retained ancestry length;
- bounded progress fingerprints;
- explicit proposed, blocked, or recovering objective state; and
- an optional requested next role that is advisory only.

Private bodies, prompts, responses, secrets, hidden reasoning, hostile container subclasses,
unknown properties, mixed accounting, fabricated authentication, and unbound verified evidence
fail closed.

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

Requested capabilities remain unsupported. Effective capabilities and tools are empty.

## Typed outputs

### Objective decomposition

Creates exactly seven work items: Explorer, Architect, Builder, Curator, Integrator, Steward,
and Optimizer. Each item binds all admitted evidence, every rollback reference, the objective's
acceptance criteria, and every earlier work item as a dependency.

### Dependency graph

Contains seven nodes and the 21-edge transitive closure. Edges may only point from earlier to
later constitutional roles. The graph cannot omit a predecessor, reverse an edge, reference an
unknown node, or contain a duplicate edge.

### Budget plan

Known ceilings produce a one-million-ppm plan containing positive rollback and verification
reserves plus deterministic role allocations. Unknown ceilings keep reserves and allocations
null. Zero on any known axis is exhausted. The candidate never issues a lease.

### Court schedule

Contains ten procedural purposes: Orchestrator, Explorer/Advocate, Architect, Builder,
Cross-Examiner, Curator, Integrator, Steward, Optimizer, and Judge. Each stage depends on every
prior purpose. Status remains pending and authenticated distinct actors remain false.

### Recovery plan

Requires checkpoints, preserves evidence, retains all rollback references, and requires an
external authority to resume. It never authorizes activation.

### Stop decision

Evaluates blocked/recovering state, budget, evidence, recursion, progress, and procedural
independence. It returns continue, defer, stop, or recover, but completion remains false. In this
inert candidate, authenticated independence is unavailable, so otherwise healthy requests defer.

### Handoff

Derives the next role from the controlling state:

- recovery, stop, recursion, or stall -> Steward;
- evidence gap -> Explorer;
- budget boundary -> Steward;
- procedural or unknown independence -> Curator; otherwise
- the next lifecycle stage -> Explorer.

The caller's requested role is retained only as an advisory field and is marked eligible only
when it matches the derived role.

## Determinism and replay

All IDs and digests derive from canonical request bytes and fixed contracts. No timestamps,
random identifiers, environment state, chat memory, or filesystem order enter the plan.
Equivalent requests produce byte-identical outputs. Mutation after return cannot change a fresh
compilation.

## Limits

The contracts do not authenticate actors, execute roles, enforce physical budgets, persist a
mission, schedule processes, invoke tools, compare models, measure customer outcomes, or prove
that the plan is useful. Those obligations remain separate.
