# Whole-OS successor implementation plan — N01 Advocate candidate

Status: **inactive N01 implementation candidate; independent N01 court pending**  
Base commit: `7dff0a807936b5be33099bdaa5c242674c624776`  
Base tree: `682619e74077e9d0bbc4486dd7e219a8d282d347`  
Branch: `codex/whole-os-n01-plan`

This record compiles the accepted N00 inventory into versioned portable contracts. It does not activate a host plan, sign an artifact, publish a branch/PR, merge, deploy, or establish a product/superiority claim.

## Accepted N00 input

Only N00 inventory `WOS-N00-20260914-01` and the exact hashes accepted in `N00_CURATOR_REREVIEW.md` are inputs: source inventory `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127`, successor node map `aeb3d9dd35c28bf431a187b8aa60e51c9ea6531fb265b40f59056b12b0b6cc4b`, symbol classification `89f70a0b50cf84b7a2e7fa1be4e07ac58ebcc8638f8405a9658b9e3e724857b0`, reconciliation `feb58b630627d0bd56d9a4d538b530b9f9b5e4d3f9a5853805d07d6a888f3f52`, checker `7227e840296d2f61309a36b52f45eb65fdbdf0de24ad2ab7034b3e7692022a68`, and validation `0470947dae960e5df39cf4d98cb0af3d10a5f3b8b36354c02c72f9505d5f187c`.

N00's eight external obligations remain open: `EO-EXT-SOURCE-ARCHIVES`, `EO-OPENAI-FETCH-RECEIPTS`, `EO-COMPARATOR-RIGHTS`, `EO-EXTERNAL-CAMPAIGN-ROOT`, `EO-ROBLOX-SUBJECT`, `EO-ROBLOX-RUNTIME`, `EO-DELIVERY-GRANT`, and `EO-LEGACY-DISPATCH`.

## Canonical decision map

| ADR | Decision surface | Requirements | Test owner | Migration / rollback |
|---|---|---|---|---|
| [ADR-079](../../architecture/ADR-079-WHOLE-OS-CAMPAIGN-TOPOLOGY.md) | Flexible 34-node topology; v1 compatibility | R01/R02/R03/R05/R06/R15/R17/R18 | N01/N09/N28 | v2 new admissions; select v1 profile on rollback |
| [ADR-080](../../architecture/ADR-080-WHOLE-OS-DURABLE-COMPOSITION.md) | One durable service; delivery authority separate | R01/R02/R04/R07/R10/R15/R18 | N01/N08/N10/N15/N16 | immutable config generation; prior service/config rollback |
| [ADR-081](../../architecture/ADR-081-WHOLE-OS-TENANT-LEARNING-BOUNDARIES.md) | Tenant/private learning and draft export | R07/R08/R09/R10/R11/R13/R18 | N19–N21/N25/N29 | quarantine legacy unbound data; revoke routes/restore champion |
| [ADR-082](../../architecture/ADR-082-WHOLE-OS-ENDPOINT-RECONSTRUCTION.md) | Endpoint mode alongside strict PIT | R09/R12/R13/R14/R18 | N22–N24/N29 | new mode only; revoke/quarantine endpoint episodes |
| [ADR-083](../../architecture/ADR-083-WHOLE-OS-RISK-BASED-QUALIFICATION.md) | Purpose/content-bound checks and reuse | R03/R05/R06/R10/R14/R15/R18 | N01/N06/N14/N27/N29 | old receipts retain version; disable cache reads |

The ADR index was read before allocation. ADR-079 through ADR-083 are the next unused numeric identifiers; ADR-074 through ADR-078 remain unchanged.

## Advocate requirement recommendations

These are N01 Advocate recommendations, not independent judgments.

| Requirement | Recommendation | Reason and deferred burden |
|---|---|---|
| R01 | adapt | Compose existing durability into a persistent campaign; operational proof remains N31/N33. |
| R02 | adapt | Evidence-ranked autonomous discovery; measured value remains N02/N11/N31/N32. |
| R03 | adapt | Typed production profiles and exact qualification; production readiness remains profile-specific and deferred. |
| R04 | adapt | Separate qualified code-PR broker and feedback loop; real granted effects remain pending. |
| R05 | adapt | Capsules/reuse/routing with intact gates; cost/time superiority is deferred to N30. |
| R06 | adopt/adapt | Adopt flexible work outcomes; adapt them to closed portable v2 packages and successor revisions. |
| R07 | adapt | External orchestration and tenant isolation; hostile-code/real-target evidence remains pending. |
| R08 | adapt | Immutable self challengers and supervisor rollback; promotion remains separately judged. |
| R09 | adapt | App-scoped memory/challengers; no automatic Hive effect. |
| R10 | adapt | Enforced custody plus negative controls; no universal non-leakage claim. |
| R11 | adapt | One stable draft obligation per mission with separate export grant and no activation. |
| R12 | adapt | Explicit endpoint reconstruction while retaining strict PIT. |
| R13 | adapt | Versioned evidence-driven challengers; learning superiority remains deferred. |
| R14 | adapt/defer claim | Implement adapters/profiles; production Roblox status deferred until real Studio/device/asset evidence. |
| R15 | adopt/adapt | Adopt explicit small packets; adapt route names as unqualified hypotheses until N07. |
| R16 | reject as current execution constraint; preserve historically | `OWNER-IMPLEMENTATION-01` supersedes the documentation-only restriction for this campaign; the original bytes/disposition remain evidence. N01 carries R16 so it cannot silently disappear. |
| R17 | adapt/defer claim | Preserve the analytical tournament; measured championship remains N30. |
| R18 | adopt | Preserve sources, roles, authority separation, PIT, dissent, failures, and anti-cheating gates. |

## Compiled artifacts and compatibility

- `whole-os-node-contracts-v1.json` contains all N00–N33 objectives/dependencies plus exact contract-section digests, requirement/source bindings, routes, acceptance/output contracts, semantic locks, normalized POSIX write paths, review obligations, publication stages, completion, and rollback. It contains no `planning_group` field.
- `whole-os-plan-v2.json` is canonical portable-plan schema v2. Digest: `sha256:2152dd3637d1a7dfd69ad1a121de198b6588a3310fa02ea98483edd4125897b1`.
- `generation-manifest.json` is the existing closed external-generation format. Generation: `sha256:3e0a738c8ca110181c85c29022f233f5dab0df058755c1883a9d7d20721dce5d`. It requires a distinct host signature and contains none.
- `DISPATCHER.json` is the permanent inactive dispatcher entry. It binds the exact plan, generation, node-contract, and node-prompt bytes and says `planning_group_is_lock=false`.
- `NODE_PROMPT.md` is the permanent compact worker template derived from RUNBOOK section 8. Workers receive only their node, direct prerequisite receipts, named contracts/sources, and compiled locks/outputs.
- `scripts/generate_whole_os_plan_artifacts.py` deterministically reconstructs the artifacts and performs an inert compilation. It has no activation/signing/publication path.

Portable schema v1 and `TournamentPlanFactory`'s 13-stage `external-all-aspect-tournament-v2` remain supported by the original compiler package identity. Schema v2 uses a distinct lock-aware compiler identity; it serializes equal semantic locks and equal/ancestor write paths within otherwise parallel dependency levels.

## Independent N01 court requests

The N01 Architect also acted as Advocate/Builder and therefore does not approve or judge this candidate.

1. A separate Cross-Examiner must produce `docs/plan/whole-os-implementation/N01_EXAMINER_REVIEW.md`, challenge each ADR and R01–R18 recommendation, inspect lock/path completeness and aliases, attempt every negative case, and preserve dissent.
2. A separate expert witness (Integrator/Steward with portable compiler and recovery expertise) must produce `docs/plan/whole-os-implementation/N01_EXPERT_TESTIMONY.md`, reproduce all 34 mappings, v1 compatibility, deterministic generation, lock-aware rounds, source/authority closure, migration, and rollback on the exact commit.
3. A Judge distinct from N00 Explorer/Curator and this N01 Architect/Advocate/Builder must produce `docs/plan/whole-os-implementation/N01_JUDGE_VERDICT.md` with one disposition per material ADR and requirement family. The Judge must not infer production, efficiency, Roblox, learning, or superiority from this compilation.

Until those exact-candidate artifacts exist, N01 is an implementation candidate awaiting independent disposition and must not be represented as accepted, activated, signed, published, or complete under the repository's full-autonomy definition.

## Verification and rollback

Focused command: `python -m unittest tests.test_whole_os_plan_contract tests.test_tournament_plan_factory tests.test_compiled_tournament -v`, with `PYTHONPATH` bound to this worktree's absolute `src` and import provenance recorded. The mandatory repository gate remains `python -m unittest discover -s tests -v` at integration; N01 focused checks do not replace it.

Rollback selects schema-v1 compiler/profile for new admissions and reverts N01 code/docs through normal history. Preserve the v2 plan, generation, Advocate record, failures, and later court artifacts as append-only evidence. No host plan, signature, grant, external branch, PR, protected ref, or production service was touched by N01.
