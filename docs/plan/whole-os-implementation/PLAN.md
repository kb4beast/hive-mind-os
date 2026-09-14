# Whole-OS successor implementation plan — N01 Advocate candidate

Status: **inactive N01 implementation candidate; Cross-Examiner, Expert r1/r2, and Judge ADAPT findings repaired; final independent disposition pending**

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

Canonical successor node contracts: `docs/plan/whole-os-implementation/whole-os-node-contracts-v2.json`

Historical non-admitting compatibility evidence: `docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json`

The v2 artifact contains all N00–N33 objectives/dependencies plus exact contract-section digests, accepted source/requirement namespace bindings, routes, acceptance/output contracts, semantic locks, normalized POSIX write paths, review obligations, publication stages, completion, and rollback. The historical v1 artifact is retained only to demonstrate compatibility and must never be admitted or dispatched. Neither artifact contains a `planning_group` field.

- `whole-os-plan-v2.json` is canonical portable-plan schema v2. Digest: `sha256:a441e4906a01de776af54f0538824d18363c7403b615df67392a51df34b96005`.
- `generation-manifest.json` is the existing closed external-generation format. Generation: `sha256:fcdef7271f6f0076b305c2989b4e27179b8518888ad22ba18d40bb3fed0b69d3`. It requires a distinct host signature and contains none.
- `DISPATCHER.json` is the permanent inactive dispatcher entry. It binds the exact plan, generation, current canonical v2 node-contract, and node-prompt bytes; explicitly marks v1 historical with `admission_allowed=false`; and says `planning_group_is_lock=false`.
- `NODE_PROMPT.md` is the permanent worker-boundary specification derived from RUNBOOK section 8. It is never interpolated. `node_prompt_renderer.py` accepts only a closed canonical request, copies exact sealed node values, structurally separates fixed instructions from data, and returns a digest for the node-admission record.
- `scripts/generate_whole_os_plan_artifacts.py` deterministically reconstructs the artifacts and performs an inert compilation. Before importing compiler modules it places this checkout's `src` first and fails closed unless every compiler module resolves within that directory. It has no activation/signing/publication path.

Portable schema v1 and `TournamentPlanFactory`'s 13-stage `external-all-aspect-tournament-v2` remain supported by the original compiler package identity. Schema v2 uses a distinct lock-aware compiler identity; it serializes equal semantic locks and equal/ancestor write paths within otherwise parallel dependency levels.

## Independent N01 court requests

The N01 Architect also acted as Advocate/Builder and therefore does not approve or judge this candidate.

1. A separate Cross-Examiner produced `N01_EXAMINER_REVIEW.md` at review commit `78d0f32bfb6b47912e6d06ae33ed94d7647cf2d4` against candidate `eb506932e34ed631acb72b77872b72f7d2a0bfe9`. It returned ADAPT: CE-01 required self-verifying generator import provenance and CE-02 required a closed, injection-safe renderer. This successor repair implements both; CE-03/CE-04 controls and CE-05 deferred claims remain unchanged. The review artifact must be retained when commits are composed.
2. A separate expert witness (Integrator/Steward with portable compiler and recovery expertise) must produce `docs/plan/whole-os-implementation/N01_EXPERT_TESTIMONY.md`, reproduce all 34 mappings, v1 compatibility, deterministic generation, lock-aware rounds, source/authority closure, migration, and rollback on the exact repaired composition.
3. A Judge distinct from N00 Explorer/Curator, the Cross-Examiner, and this N01 Architect/Advocate/Builder must produce `docs/plan/whole-os-implementation/N01_JUDGE_VERDICT.md` with one disposition per material ADR and requirement family. The Judge must not infer production, efficiency, Roblox, learning, or superiority from this compilation.

Preliminary Expert review of repair `1f7557f2c91fbaadba67387275390e33dfa9d262` returned ADAPT on three technical points without issuing the requested final testimony: the schema-v2 compilation receipt named the v1 compiler, source IDs lacked runtime namespace closure, and control/Unicode path characters were admitted. This successor repair derives receipt identity from the authenticated standard binding, requires exact accepted-N00 inventory bytes for v2 compilation, closes every work-package source ID against that inventory, pins the Whole-OS factory to the accepted inventory ID/digest, and rejects non-ASCII/control path characters at the shared portable-path boundary. Existing external-defer claims remain unchanged.

Preliminary Expert r2 review of repair `97cdaf3d998ef1517592f4ceff13f14b07fe7d6d` remained ADAPT because factory sealing preceded source-ID closure and requirement closure was self-referential. This successor repair validates exact accepted source-inventory and requirements bytes before constructing or sealing a plan, pins the v2 compiler descriptor to the exact R01–R18 IDs and requirements digest, requires both byte artifacts at compilation, and delays every generated repository write until factory admission, compilation, and generation succeed. A colluding R01-to-R99 substitution and `GOV-NONEXISTENT` source now fail before the sealer is called. No external-defer claim is changed.

Independent Judge review of repair `7d89d27be127aef7320b9b2510c8525df8d9eda2` returned ADAPT because the dispatcher and PLAN selected v2 while the permanent node template still called v1 canonical. This successor repair makes v2 the one canonical admitting successor contract across dispatcher, PLAN, template, and generator; preserves v1 only as explicitly historical, non-admitting compatibility evidence; and adds an executable divergence check. No external-defer claim is changed, and this Advocate/Builder does not issue the final disposition.

Until those exact-candidate artifacts exist, N01 is an implementation candidate awaiting independent disposition and must not be represented as accepted, activated, signed, published, or complete under the repository's full-autonomy definition.

## Verification and rollback

Focused command: `python -m unittest tests.test_whole_os_plan_contract tests.test_node_prompt_renderer tests.test_tournament_plan_factory tests.test_compiled_tournament -v`, with `PYTHONPATH` bound to this worktree's absolute `src` and import provenance recorded. The mandatory repository gate remains `python -m unittest discover -s tests -v` at integration; N01 focused checks do not replace it.

Rollback selects schema-v1 compiler/profile for new admissions and reverts N01 code/docs through normal history. Preserve the v2 plan, generation, Advocate record, failures, and later court artifacts as append-only evidence. No host plan, signature, grant, external branch, PR, protected ref, or production service was touched by N01.
