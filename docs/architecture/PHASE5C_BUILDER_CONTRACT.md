# Phase 5C Builder Contract

## Scope

Phase 5C adds one package-private, opt-in, inert Builder candidate. It compiles a validated
implementation request into ten separately digest-bound planning outputs and one final
request-bound envelope. It does not execute commands, edit files, run tests, issue resource
leases, create artifacts, or authorize completion.

## Input contract

`builder-implementation-request-v1` requires:

- a typed objective in `ready` state;
- explicit constraints and acceptance criteria;
- adopted/adapted adjudicated requirements with source, acceptance, architecture, and evidence
  references;
- one accepted architecture decision with no unresolved blocking contradiction;
- exact repository, tenant, worktree, subject commit/tree, allowed/denied path, file, and
  dependency limits;
- bounded changes, dependencies, tests, evidence items, checkpoints, rollback steps, and
  artifacts;
- evidence and rollback references;
- wholly known or wholly unknown resource ceilings and reserves;
- the ten procedural role records, all unauthenticated;
- prior progress fingerprints;
- an advisory next-role request; and
- false caller claims for code execution, passed tests, and completion.

Only exact built-in JSON containers are admitted. Unknown fields, private content, non-finite
numbers, excessive nesting/value counts, duplicate identifiers, ambiguous references, and
noncanonical paths fail closed.

## Output contracts

| Output | Required meaning |
| --- | --- |
| `requirement_trace` | Every admitted requirement maps to acceptance criteria, changes, tests, evidence, and artifacts. |
| `implementation_scope` | The exact worktree, subject, allow/deny paths, change set, and ceilings; no unrelated overwrite or implementation authority. |
| `change_plan` | Ordered bounded changes with requirement, acceptance, architecture, and dependency trace; no execution or completion claim. |
| `workspace_plan` | Isolated clean-start workspace, checkpoints, and interruption recovery; no execution authority. |
| `dependency_plan` | Admitted dependency/source/version/license/obligation impact and explicit unknown/quarantine emptiness; no dependency-change authority. |
| `test_plan` | Complete requirement/acceptance/change coverage, hostile cases, failure-before/pass-after requirements, and no test weakening or result authority. |
| `execution_evidence_plan` | Required evidence kinds and exact receipt fields; all execution, pass, completion, and sealing claims false. |
| `rollback_plan` | Checkpoints, restart procedures, one inverse step per change, verification tests, and complete coverage; no rollback execution/authority claim. |
| `artifact_manifest` | Source/test/manifest/receipt artifacts with change/test coverage and required digests/receipts; no creation claim. |
| `curator_handoff` | Clean-boundary reconstruction by Curator, required references, truthful procedural nonindependence, and all authority flags false. |

Every output binds the request ID/digest, objective, tenant, repository, Builder
identity/version, architecture decision/design digest, subject commit/tree, complete requirement
and acceptance sets, authority state, budget state, evidence references, rollback references,
its own digest, and the final implementation-envelope digest.

## Authority contract

```text
authority: none
activation: inert
effective capabilities: []
tools: []
implementation_authorized: false
execution_authorized: false
test_result_authorized: false
completion_authorized: false
promotion_authorized: false
activation_authorized: false
```

Requested capabilities remain unsupported metadata. Capability descriptions do not grant
execution authority.

## Semantic invariants

1. Architecture and implementation scope bind the same subject commit and tree.
2. Every acceptance criterion is owned by at least one adjudicated requirement.
3. Every requirement maps to at least one bounded change.
4. Change acceptance references derive only from the change's requirements.
5. Every dependency is referenced by a change and every change dependency reference is
   admitted.
6. Every test derives requirements and acceptance from its changes.
7. Tests cover every acceptance criterion and every change.
8. At least one failure-before test exists and all tests have pass-after evidence.
9. One diff evidence item covers the complete change set.
10. Every evidence item uses the exact receipt-field catalog.
11. Checkpoints cover every change and retain restart procedures.
12. Every change has exactly one rollback step with the correct inverse operation.
13. Artifacts cover every change and test; manifest and receipt artifacts exist; every artifact
    requires a digest and receipt.
14. Known budgets fund checkpoint, evidence, rollback, and every Builder section; unknown
    budgets remain null; no lease is issued.
15. A repeated semantic progress fingerprint fails closed.
16. Every typed output and the final envelope must equal canonical reconstruction from the
    validated request.

## Compatibility

The candidate adds no root or package facade export, CLI parser, JSON package resource,
storage migration, runtime registration, provider/tool/host/scheduler binding, or dependency.
The installed package resource count remains 133. Phase 5A and Phase 5B candidates continue to
compile and validate.
