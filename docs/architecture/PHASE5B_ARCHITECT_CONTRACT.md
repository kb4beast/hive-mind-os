# Phase 5B Architect contract

## Purpose

Phase 5B provides a deterministic, package-private Architect candidate. It converts one
strict design request into one inert successor definition and ten separately validated
outputs. It does not implement, select, approve, or activate a design.

## Input contract

`architect-design-request-v1` requires:

- stable request, objective, tenant, and repository identifiers;
- a bounded objective, constraints, acceptance criteria, evidence references, and
  rollback references;
- atomic claims with `adopt`, `adapt`, `defer`, `reject`, or `quarantine`
  dispositions;
- two to eight bounded design options;
- one option-local mapping for each adopted or adapted claim and each option;
- components, interfaces, invariants, trust boundaries, threats, migration steps,
  rollback steps, and verification steps for every option;
- orthogonal token, cost, elapsed-time, and tool ceilings that are wholly known or
  wholly unknown;
- positive rollback and verification reserve percentages only for known budgets;
- bounded prior design fingerprints;
- an advisory requested option and requested next role; and
- all ten procedural role labels with caller authentication fixed to false.

Private prompts, responses, secrets, hidden reasoning, hostile container subclasses,
unknown properties, non-finite numbers, mixed budget accounting, duplicate IDs, foreign
references, and fabricated authentication fail closed.

## Successor definition

The successor has eight ordered layers:

1. exact Phase 2 Architect base;
2. Generation Zero and built-in prompt binding;
3. bounded Architect deep-playbook responsibilities;
4. built-in `skill.architect` by reference;
5. strict request contract;
6. strict typed-output catalog;
7. Phase 5B governance and court boundary; and
8. unchanged constitutional lifecycle.

Requested capabilities remain unsupported. Effective capabilities and tools are empty.

## Typed outputs

### Claim integration

Each adopted or adapted claim maps exactly once into every admitted option. Mappings
must reference only design IDs owned by that option. Deferred, rejected, or quarantined
claims cannot be silently integrated.

### Option analysis

Each option receives a deterministic integer-ppm score and explicit viability status.
Viable options rank before blocked options. Violations, unknowns, objective state, and
blocking residual risk prevent selection regardless of score. The preferred option is
provisional and selection remains unauthorized.

### Architecture

Preserves the exact objective and constraints and emits option-local components,
invariants, trust boundaries, and the provisional option. Implementation remains false.

### Interface contract

Interfaces may connect only two distinct components owned by the same option. Contract
compatibility is proposed, not executed or proven.

### Threat model

Every threat is owned by one option, every trust boundary references only that option's
components and threats, and the union of boundary threats equals the option's threat set.
Residual risk and blocking threats are explicit; risk acceptance remains false.

### Migration plan

Migration dependencies may reference only earlier steps in the same option. Each step
binds exactly one option-local rollback step. Migration remains proposed, blocked, or
recovery-required according to objective state and is never authorized.

### Rollback plan

The rollback set exactly matches migration references. Rollback remains required and
unauthorized; it is not represented as executed.

### Verification plan

Every option independently covers all acceptance criteria, invariants, threats,
migration steps, and rollback steps. Verification is planned but not executed.

### Resource plan

Known ceilings fund positive rollback and verification reserves before nine positive
design-section allocations. Every axis reconciles exactly. Unknown ceilings retain null
reserves and allocations. No lease is issued.

### Handoff

Blocked, recovering, repeated, unviable, or resource-unknown designs route to Steward.
Otherwise the candidate routes to Curator because procedural labels do not establish
authenticated independent review. Caller-requested roles are advisory only. Builder is
never authorized by this candidate.

## Determinism and canonical validation

All identities and digests derive from canonical request bytes and fixed contracts. No
timestamp, randomness, chat memory, environment state, or filesystem ordering enters the
design. Validation reconstructs the canonical design from the retained request snapshot,
so an attacker cannot alter nested semantics and escape by recomputing output and envelope
digests.

## Limits

The contracts do not authenticate people, inspect a live repository, select an option,
accept risk, reserve physical resources, write code, run verification, persist a mission,
or measure customer outcomes. Those obligations remain separate.
