# ADR-035: Inert Builder deep-playbook candidate

- Status: adapted for a bounded stacked draft candidate; activation prohibited
- Date: 2026-07-31
- Extends: ADR-018, ADR-021-PR31, ADR-033, ADR-034
- Runtime selection: unchanged
- Authority: none

## Context

Phase 5 deepens each constitutional role without merging authority. Phase 5A added an inert
Orchestrator planning candidate and Phase 5B added an inert Architect design candidate. Phase
5C addresses only the Builder boundary: turning an adjudicated requirement and accepted design
into a bounded implementation proposal, test/evidence plan, recovery plan, artifact manifest,
and Curator handoff.

The existing Generation Zero and Phase 2 Builder definitions describe implementation duties,
but do not provide one strict request-bound envelope that prevents a plan from being presented
as executed work. They also do not fully bind requirements, acceptance criteria, design,
repository scope, subject commit/tree, dependencies, tests, evidence, checkpoints, rollback,
artifacts, resources, and downstream verification.

## Decision

Add two package-private Python modules:

- `builder_playbook_contracts.py` owns thirteen strict contracts; and
- `builder_playbook.py` composes one deterministic inert successor and ten typed outputs.

The ten outputs are `requirement_trace`, `implementation_scope`, `change_plan`,
`workspace_plan`, `dependency_plan`, `test_plan`, `execution_evidence_plan`, `rollback_plan`,
`artifact_manifest`, and `curator_handoff`.

The candidate:

1. derives from the exact packaged Phase 2 Builder, Generation Zero prompt, built-in
   `skill.builder`, and constitutional lifecycle;
2. exposes no root API, CLI command, capability, tool, provider, host, scheduler, store,
   migration, lease, or runtime selector;
3. admits only adopted or adapted requirements with acceptance, architecture, source-claim,
   and evidence bindings;
4. requires architecture and scope to bind the same subject commit and tree and rejects any
   unresolved blocking contradiction;
5. bounds every change and artifact to admitted paths, evaluates explicit denied paths before
   generic allowlist membership, prevents duplicate paths, and enforces file and dependency
   ceilings;
6. requires every requirement to map to a change, every change to tests and artifacts, and
   every acceptance criterion to tests;
7. rejects unknown or quarantined dependencies and requires exact source, version, license,
   obligation, change, and license-evidence mappings for admitted dependencies;
8. requires failure-before evidence where applicable, pass-after evidence for every test,
   complete diff evidence, and the exact receipt-field catalog;
9. requires interruption checkpoints, restart procedures, one exact inverse rollback path per
   change, rollback verification tests, and rollback evidence;
10. requires digest- and receipt-bearing source, test, manifest, and receipt artifacts;
11. reserves positive checkpoint, evidence, and rollback capacity before distributing each
   known resource ceiling across all ten Builder sections; unknown budgets stay null;
12. binds every output to the request digest, Builder definition/version, requirement and
   acceptance sets, design digest, repository/tenant, subject commit/tree, authority state,
   budget state, evidence, rollback, output digest, and final envelope digest;
13. reconstructs the canonical request-bound envelope during validation, so an attacker cannot
   change semantic leaves and merely reseal local digests; and
14. always states that code was not executed by the playbook, tests were not run by the
   playbook, artifacts were not created by the playbook, and implementation, execution,
   test-result, completion, promotion, and activation authority are false.

The maximum output is implementation planning metadata. A future runtime may execute work only
through separately authenticated identities, policy decisions, resource leases, isolated
tools, and receipted enforcement points.

## Canonical identity

- Candidate agent: `hive-agent:builder:v2-shadow-1`
- Candidate definition: `hive-agent-definition:builder:v2-shadow-1`
- Base and rollback: `hive-agent-definition:builder:v2-candidate`
- Successor digest:
  `sha256:ac69c53464f7e24022b7c29d12889d0f80190d86e3d5650f00a15ae57ecfdccd`

## Threats and controls

| Threat | Control |
| --- | --- |
| Unadjudicated prose becomes implementation scope | Requirements must be adopted/adapted and bind admitted source claims, acceptance criteria, architecture, and evidence. |
| A change reaches outside the repository/worktree boundary | Canonical relative paths, explicit allow/deny sets, duplicate-path rejection, and file ceilings fail closed. |
| A denied constitutional path is disguised as merely out of scope | Denied prefixes are evaluated before the generic allowlist check. |
| Tests are weakened to manufacture a pass | `test_weakening=false`, `expected_after=pass`, failure-before and pass-after evidence, and complete acceptance/change coverage are mandatory. |
| Caller claims are treated as receipts | Caller execution/test/completion claims must all be false; receipt fields and evidence kinds are only plans. |
| Unknown supply-chain input is smuggled in | Only `known-admitted` dependencies with source, version, license, obligations, change links, and license evidence validate. |
| Interruption loses recoverability | Every change is checkpointed; restart procedures and one exact inverse rollback step per change are mandatory. |
| Resource planning consumes verification/recovery capacity | Positive checkpoint, evidence, and rollback reserves are funded before ten positive section allocations. |
| One request/output is replayed in another repository, tenant, design, or subject | All outputs bind the exact request digest, scope, design, subject commit/tree, and canonical envelope. |
| Semantics are changed and coherently resealed | Every scalar leaf is covered by canonical reconstruction tests across all ten outputs. |
| Same-assistant role passes are presented as independent review | The handoff fixes `authenticated_distinct_actors=false`, `same_assistant_performed_procedural_passes=true`, and `independence_claimed=false`. |
| A plan is treated as execution or completion | All authority flags and observed-effect claims remain false; the only next role is Curator. |

## Migration

No stored schema, facade, CLI, package resource, provider/tool adapter, scheduler, store,
pointer, or active runtime changes. Development use requires an explicit package-private
import. A future execution binding requires a separate ADR, authenticated authority, hard
isolation, durable receipts, real resource leases, independent verification, and reversible
champion migration.

## Rollback

Remove the Phase 5C modules, tests, scripts, inventory, documents, and evidence; restore the
prior CI and ADR index; restore the prior Phase 5A and Phase 5B inventory snapshots and Phase
5B inventory input constant. No data conversion or history rewrite is required. Existing
Generation Zero through Phase 5B behavior remains unchanged.

## Acceptance boundary

The maximum permitted result is a draft stacked pull request when:

- all thirteen contracts and ten typed outputs fail closed;
- deterministic successor, request, output, and envelope digests reproduce;
- scope, traceability, dependency/license, test/evidence, checkpoint/restart, rollback,
  resource, hostile-container, substitution, and authority regressions pass;
- a systematic semantic resealing attack fails across every scalar leaf of every output;
- no root API, CLI, package-resource, runtime, provider, tool, store, scheduler, or authority
  surface changes;
- the isolated wheel imports and verifies the candidate;
- inherited Python, Ruff, Pyright, CodeQL, secret, dependency/license, release-audit, wheel,
  package-resource, SBOM, artifact, and available provenance gates pass on the exact hosted
  head; and
- the procedural court record discloses that one assistant performed separate role passes and
  did not create authenticated independent actors.

## Not established

No code execution by the playbook, test-result truth, independent verification, implementation
completion, customer value, live Builder quality, learning, champion migration, promotion,
activation, production readiness, release readiness, or superiority is established.
`B-OPS-09`, P14-P20, source/license appeals, and the exact Armory source remain open.
