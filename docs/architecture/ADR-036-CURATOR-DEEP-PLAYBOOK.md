# ADR-036: Inert Curator deep-playbook candidate

- Status: adapted for a bounded stacked draft candidate; activation prohibited
- Date: 2026-07-31
- Extends: ADR-012-P08, ADR-018, ADR-021-PR31, ADR-033, ADR-034, ADR-035
- Runtime selection: unchanged
- Authority: none

## Context

Phase 5 deepens each constitutional role without merging authority. Phase 5A–5C added inert,
package-private Orchestrator, Architect, and Builder candidates. Phase 5D addresses only the
Curator boundary: reconstructing Builder claims from sealed evidence, reproducing them from a
clean boundary, searching for counterexamples, and preserving dissent and unresolved evidence.

The existing P08 runtime Curator remains the active structural verification mechanism. This ADR
does not replace, select, or modify it. The new candidate is a deterministic, package-private
verification-plan envelope that can be evaluated without treating Builder summaries, caller
claims, procedural labels, or locally resealed digests as independent proof.

## Decision

Add two package-private modules:

- `curator_playbook_contracts.py` owns fourteen strict contracts; and
- `curator_playbook.py` composes one inert successor and eleven typed outputs.

The outputs are `verification_scope`, `claim_reconstruction`,
`clean_boundary_reproduction`, `counterexample_search`, `security_privacy_review`,
`provenance_license_review`, `regression_analysis`, `artifact_receipt_verification`,
`rollback_verification`, `release_recommendation`, and `dissent_unresolved_evidence`.

The candidate:

1. derives from the exact packaged Phase 2 Curator, Generation Zero prompt, built-in Curator
   agent/skill, and P08 blind-first verification boundary;
2. exposes no root API, CLI command, capability, tool, provider, host, scheduler, store,
   migration, lease, or runtime selector;
3. accepts only a valid Builder envelope with matching repository, tenant, subject commit/tree,
   and an explicit independent-reconstruction handoff;
4. requires distinct Builder and Curator actor identifiers while truthfully retaining that the
   procedural actors are not externally authenticated;
5. requires blind checks to be sealed before candidate access and prevents late checks from
   becoming verification evidence;
6. binds claims to acceptance criteria, sealed checks, observed evidence, and complete admitted
   sources;
7. rejects Builder-produced verification-class evidence, forged or stale evidence, incomplete
   receipts, foreign trees, and future-commit leakage;
8. rejects source/license gaps for material claims and test/assertion weakening;
9. preserves wholly known or wholly unknown resource accounting, with positive verification,
   evidence, and rollback reserves before eleven section allocations;
10. binds every output to the exact request, Builder identity/digests, repository/tenant,
    subject commit/tree, authority state, budget state, evidence, rollback, output digest, and
    final verification digest;
11. canonically reconstructs the request-bound envelope so coherent local resealing cannot
    convert changed semantics into a valid result; and
12. fixes implementation, execution, test-result, completion, release, approval, promotion,
    and activation authority to false.

The strongest result available to this procedural, unauthenticated candidate is `defer`.
Structural checks may pass, but the playbook cannot execute its own verification, authenticate
its own independence, approve its own work, or establish release readiness.

## Canonical identity

- Candidate agent: `hive-agent:curator:v2-shadow-1`
- Candidate definition: `hive-agent-definition:curator:v2-shadow-1`
- Base and rollback: `hive-agent-definition:curator:v2-candidate`
- Reviewed successor digest:
  `sha256:3ca6aa8d1f32b1377490c0a87afd4aee248641fe95231705cb4963ef2e7eaa7c`

## Threats and controls

| Threat | Control |
| --- | --- |
| Builder summary is accepted as proof | Claims must be reconstructed from sealed checks, evidence, receipts, and sources; `builder_summary_is_proof=false`. |
| Curator verifies its own or Builder identity | Distinct role/actor bindings are mandatory; authenticated independence remains false. |
| Checks are written after seeing the candidate | Blind-seal sequence must precede candidate access and every check is sealed. |
| Forged, stale, or incomplete receipts produce a false green | Digest-verified integrity, freshness, exact subject bindings, and required receipt fields fail closed. |
| Future or foreign evidence leaks into point-in-time review | Evidence and point-in-time commits/trees are limited to the admitted base and subject. |
| Tests are weakened to manufacture success | Assertion and test-function counts cannot decrease. |
| Unlicensed or partial sources support material claims | Every material claim requires complete, admitted source coverage. |
| Another repository, tenant, request, or Builder envelope is substituted | Every output and the canonical envelope bind exact identities and scope. |
| Semantic leaves are changed and all local digests are recomputed | Canonical request-bound reconstruction rejects the resealed result. |
| Structural pass is presented as release approval | Recommendation remains `defer`; release, approval, and promotion authority are false. |

## Migration

No active Curator, stored schema, pointer, facade, CLI, package resource, provider/tool adapter,
scheduler, store, or runtime selector changes. Development use requires an explicit
package-private import. Any future runtime selection requires a separate ADR, authenticated
identities, externally protected receipts, clean-boundary execution, independent adjudication,
and reversible migration.

## Rollback

Remove the Phase 5D modules, tests, scripts, inventory, documents, and evidence; restore the
prior CI and ADR index; restore the prior Phase 5A–5C inventory snapshots and input constants.
The existing P08 Curator and Generation Zero through Phase 5C behavior remain unchanged.

## Acceptance boundary

The maximum permitted result is a draft stacked pull request when all fourteen contracts and
all eleven outputs fail closed, deterministic and semantic-reseal tests pass, inherited
interfaces remain unchanged, the isolated wheel verifies the candidate, and terminal hosted CI
passes on the exact head. Procedural review does not create authenticated independence.

## Not established

No independent execution, authenticated verification, release approval, customer value,
behavioral superiority, learning, promotion, production readiness, or release readiness is
established. `B-OPS-09`, P14–P20, source/license appeals, and exact Armory semantics remain open.
