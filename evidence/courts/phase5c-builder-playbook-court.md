# Phase 5C Builder Deep-Playbook Court

## Clerk record

- Case: `court:phase5c-builder-playbook`
- Subject base: `43db53de7a41d9bc02e987776edc260594def4c8`
- Delivery branch: `agent/phase5c-builder-shadow`
- Integration branch: `agent/phase5a-orchestrator-shadow`
- Burden: implementation structure for a bounded draft delivery only
- Authenticated distinct actors: false
- Same assistant performed procedural passes: true
- Independence claimed: false

The governing source register is
`evidence/sources/PHASE5C_BUILDER_SOURCE_REGISTER.md`. No unavailable source content or Armory
semantics were invented.

## Atomic claims and dispositions

| Claim | Advocate | Cross-examination | Disposition |
| --- | --- | --- | --- |
| Builder responsibilities require separate typed outputs rather than one prose answer. | Separate contracts permit traceability, independent mutation testing, and bounded handoff. | More contracts increase maintenance and schema skew risk. | `adapt`: ten outputs under one canonical envelope. |
| The playbook may describe implementation but must not imply execution. | Planning is useful before tool authority exists. | Names such as Builder and execution evidence may be misread as performed work. | `adapt`: all observed-effect and authority flags are fixed false; evidence is explicitly a plan. |
| Requirements must trace through acceptance, changes, tests, evidence, rollback, and artifacts. | This blocks unowned work and false completion. | Excessive completeness rules can reject small valid changes. | `adapt`: bounded nonempty catalogs with explicit ceilings and deterministic semantics. |
| Filesystem and dependency scope must fail closed. | Prevents unrelated changes, constitutional mutation, and supply-chain ambiguity. | Prefix rules can classify a denied exact path as merely outside an allowlist. | `adapt`: denied paths are tested before allowlist membership; unknown/quarantined dependencies are inadmissible. |
| Tests require failure-before and pass-after evidence. | Prevents false-green and test weakening. | Some additive/integration tests have no meaningful failure-before state. | `adapt`: at least one failure-before case is required; individual tests may declare `not-applicable`; every test still requires pass-after evidence. |
| Resources must preserve recovery and evidence capacity. | Prevents exhausting the budget before verification/rollback. | The playbook cannot issue or enforce real leases. | `adapt`: deterministic planning reserves only; `lease_status=not-issued` and `budget_authorized=false`. |
| Same-assistant lifecycle passes can support a draft. | Procedural separation surfaces threats and dissent. | It is correlated self-review, not authenticated independence. | `adapt` for draft delivery only; independent verification, merge, promotion, and activation remain deferred. |

## Procedural role passes

### Orchestrator

Objective: add only the inert Phase 5C Builder slice. Dependencies: exact Phase 5A-5B head,
accepted role boundaries, inherited wheel/resource contracts. Stop on base drift, unrelated user
work, authority expansion, source/license ambiguity, irreversible migration, or nonterminal CI.

### Explorer / Advocate

Reconciled the mission brief with `AGENTS.md`, the hardened vision, conglomerated architecture,
ADR-033, ADR-034, the ADR index, and blocker backlog. No external implementation source or new
dependency was needed. B-OPS-09, P14-P20, source/license appeals, and Armory remain outside this
slice.

### Architect

Kept the candidate package-private, deterministic, no-dependency, no-store, no-runtime, and
request-bound. The design separates ten outputs and binds all through canonical reconstruction.

### Builder

Produced contracts, compiler, focused tests, inventory, installed-wheel verifier, migration and
rollback records, source register, CI integration, and append-only evidence. Builder outputs
remain proposal-only; actual repository operations and tests require external receipts.

### Cross-Examiner

Attacked hostile dict/list subclasses, unknown/private fields, non-finite and oversized data,
duplicate IDs, request/repository/tenant/design substitution, denied paths, dependency/license
scope, test weakening, false-green evidence, checkpoint/restart gaps, rollback coverage,
resource reserves, authority escalation, and coherent resealing. The first pass found denied
root API/CLI paths were checked after allowlist membership; the implementation was remanded and
changed to evaluate denied paths first.

### Curator

Procedural-only reconstruction verified the example compiler from a fresh process and checked
all thirteen schemas, ten outputs, deterministic digests, inherited Phase 5A/5B imports, 133
package resources, and package-private facade/CLI behavior. This is not authenticated or
disjoint independent verification.

### Integrator

No root/package facade export, CLI command, JSON package resource, migration, provider, tool,
host, scheduler, store, or active runtime binding is introduced. CI adds only the isolated
Phase 5C wheel verifier and evidence paths. Earlier current-tree inventories are reconciled.

### Steward

Restart procedures, checkpoints, inverse rollback, verification tests, evidence references,
resource reserves, and no-data rollback are explicit. Long-term external evidence retention
remains blocked by B-GOV-04/P16.

### Optimizer

No value, behavior-quality, learning, or superiority metric is claimed. A future evaluation
must use customer-linked held-out outcomes, equal budgets, pinned identities, safety floors,
and independent grading.

### Judge

Procedural disposition: `adapt` for a bounded draft stacked delivery only, contingent on
terminal exact-head hosted CI. The Judge does not establish independence, merge permission,
activation, production readiness, release readiness, value, learning, or superiority.

## Preserved remands and dissent

1. Denied-path classification order was repaired; the original finding remains recorded.
2. Same-assistant procedural review is correlated and cannot satisfy authenticated independence.
3. The playbook plans execution evidence but cannot prove execution.
4. Hosted exact-head security, wheel, SBOM, dependency, and provenance results are external
   receipts and must be checked before calling the final head green.
5. B-OPS-09, P14-P20, source/license appeals, and Armory semantics remain open.

## Local command-target and automation-scaffolding remand

A resumed review found that the sample execution-evidence plan named
`BuilderAdversarialTests`, while the actual focused class is
`BuilderOutputAndAdversarialTests`. The stale target could make a future executor fail before
running the intended hostile and resealing cases even though the direct focused suite was green.
The target was corrected and a compatibility regression now resolves every sample unittest class.

Temporary write-capable repair workflow scaffolding added only to transfer the prior Ruff remand
was not part of the Builder candidate and would contradict the no-runtime/no-authority delivery
boundary if retained. It is removed from the final candidate tree. These repairs do not authorize
execution, weaken tests, or establish authenticated independence.

## Hosted type and inherited-inventory remand

Constitutional CI run `30654019571` on exact head
`6d07f9acb63f86d27fe68e5e3ff66621bea09a2f` produced a bounded remand.
Python 3.11, 3.12, and 3.14 each reached the same inherited Phase 5B
inventory failure: Phase 5C had redirected `selection_authorized` and
`implementation_authorized` to the Architect handoff output even though those
facts remain owned by `option_analysis` and `architecture`. Pyright 1.1.411
also rejected four optional-integer arithmetic sites after runtime validation.

The repair restores the exact Phase 5B authority-field sources, regenerates the
Phase 5B to Phase 5C inventory chain, and adds static casts only after existing
fail-closed exact-integer validation. It does not change accepted values, resource
arithmetic, schemas, authority, activation, APIs, CLI, runtime bindings, or package
resources. Self-removing repair run `30654662336` passed the focused Phase 5B
and 67-test Phase 5C suites, Ruff 0.16.0, and Pyright 1.1.411 before publication.

The prior failing run remains adverse evidence. Its CodeQL, secret scan,
dependency/license review, wheel build, installed Phase 5A/5B/5C verification,
SPDX SBOM, and immutable artifact upload passed; PR-event provenance attestation
was skipped and is not claimed. The procedural Judge remains `adapt` for a draft
stacked delivery only, contingent on terminal Constitutional CI for the repaired head.
