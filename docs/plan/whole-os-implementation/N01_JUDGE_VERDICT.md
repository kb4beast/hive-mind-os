# N01 independent Judge verdict

Verdict date: 2026-09-14

Verdict: **ADAPT**

Judge: `/root/n01_judge`, acting only as the independent N01 Judge

Candidate: `7d89d27be127aef7320b9b2510c8525df8d9eda2`

Candidate tree: `56d9a91b6b205b0a08ed4e3dbe544c2ef1011faa`

Judge worktree: `C:\h\wos-n01-judge`

Judge branch: `codex/whole-os-n01-judge`

## Scope, independence, and holding

I am distinct from the N00 Explorer and Curator, the N01
Architect/Advocate/Builder, the Cross-Examiner, the Expert Witness, and the
affected champion. I did not edit builder code, generated candidate artifacts,
another node, an active plan, or prior court evidence. This verdict adds only
this file.

The candidate is a strong, inactive N01 architecture/compiler implementation,
and the final Cross-Examiner and Expert recommendations correctly reproduce the
major repairs made after the earlier ADAPT findings. It is nevertheless **ADAPT,
not ADOPT**, because one material exact-candidate contradiction remains at the
permanent worker boundary: PLAN and `DISPATCHER.json` designate the namespace-
bound v2 node contracts as current, while `NODE_PROMPT.md` labels the historical
pre-namespace v1 node contracts canonical. The N01 contract expressly requires
exact canonical paths, and the stale path points to an artifact that lacks the
accepted requirement-inventory binding. J-01 below is a concrete reproducer.

This is only an N01 implementation-plan/compiler disposition. It does not accept
or establish an operating product, an activated campaign, a benchmark result,
runtime durability, publication, learning efficacy, Roblox qualification,
production readiness, or superiority.

## Exact subject and court evidence

The judge worktree was created directly from the requested commit. Before adding
this verdict, `git rev-parse HEAD` returned the candidate above,
`git rev-parse HEAD^{tree}` returned the candidate tree above, and `git status
--porcelain` was empty.

I read `AGENTS.md`; N01 in `NODES-FOUNDATION.md`; RUNBOOK sections 1--9; the
accepted N00 records and artifacts; PLAN; ADR-079--ADR-083; the dispatcher,
prompt, generation manifest, v1/v2 node contracts, portable plan; generator,
portable-plan/compiler/factory/renderer code; focused tests; and every court
artifact below. Each evidence worktree was clean, each review commit changed
only its named evidence file, and each file's worktree Git blob equalled its
committed blob.

| Evidence | Review commit / reviewed parent | Evidence blob | File SHA-256 | Recorded result |
|---|---|---|---|---|
| `N01_EXAMINER_REVIEW.md` | `78d0f32bfb6b47912e6d06ae33ed94d7647cf2d4` / `eb506932e34ed631acb72b77872b72f7d2a0bfe9` | `466d63433aa23971dbd565d5b3460bf692574b54` | `eac3384666850ff672f2ea01d0f0713d7b4baa0e64fec2203a48f528271a07e7` | ADAPT: import provenance and prompt interpolation |
| `N01_EXAMINER_REREVIEW.md` | `e638e4337d233c71b5d830059a07b7da0e4dc50d` / `1f7557f2c91fbaadba67387275390e33dfa9d262` | `311788ccdd4b5783e8ac48d136bdcd29e3058bc2` | `6723bdae972a2e26458f0fbadd000e69c000bbc876ece380b805a22e5a61ec56` | ADOPT recommendation for CE-01/CE-02 repair |
| `N01_EXAMINER_REREVIEW_R3.md` | `6970b5237f4e6774a2811c7f730a7abea1d43781` / exact candidate | `83c01358a78fab54843e79933cb3dc7d86ef4893` | `01c67a5bceac49b434e9731e1029e94d8c91a5c82600068bc8c31ea3247048ab` | ADOPT recommendation after final repair |
| `N01_EXPERT_TESTIMONY.md` | `4f566257c1b89f770bf58f3ee7f4b94d57291ac9` / `1f7557f2c91fbaadba67387275390e33dfa9d262` | `9ec4dbff3885358e3c8f93f0f0294f8c440365d9` | `a1d015bddff1f0fc64a28fdac9dece98c0dcfa7b68e2fae5ace98e6b4a29b102` | ADAPT: receipt identity, source closure, path controls |
| `N01_EXPERT_REREVIEW.md` | `9e6c09c1675fdddf1986122ff3032d4860c27c71` / `97cdaf3d998ef1517592f4ceff13f14b07fe7d6d` | `e419a3b115581c40e59754b7f24b5954cbed1aa7` | `606d424629adc679be356dc4c6709fc4ea86c46ff2af464180501114f4e72f26` | ADAPT: pre-seal source and colluding requirement substitution |
| `N01_EXPERT_REREVIEW_R3.md` | `6bf9d8249e3d59086dc6e83cb12e48afdbe2c911` / exact candidate | `30ff6515e1ef4135e3aea33dfd8e7eb111536014` | `fdc8b8541cc9020958f2c59f9e6c49654e2cc9e64541eedd7db0c396c6c10b0f` | ADOPT recommendation for bounded inactive N01 |

The exact-candidate reviews are process-independent but not host-independent.
Their positive findings are retained. Their ADOPT recommendations do not erase
the earlier counterexamples, and they do not control this separate judgment.

## Judge reproduction

I bound `PYTHONPATH` to `C:\h\wos-n01-judge\src` and verified that
`hive_mind_os`, `dag_standard`, `portable_plan`, and `node_prompt_renderer` all
resolved beneath that exact directory. I then ran the proportionate N01 smoke:

```text
python -m unittest tests.test_whole_os_plan_contract \
  tests.test_node_prompt_renderer tests.test_tournament_plan_factory \
  tests.test_compiled_tournament -v
```

Result: **PASS, 25 tests, 0 failures/errors, 0.397 seconds**. No full repository
CI was run; integration still owns `python -m unittest discover -s tests -v` on
its exact integrated candidate. `git diff --check` was clean.

The principal artifact hashes reproduced as:

| Artifact | SHA-256 |
|---|---|
| `source-inventory.json` | `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127` |
| `requirements.json` | `5c49bc3f9c818b6adfb326adb08bc103abd6f7e84feeebe74bdbe4f782d4b7d5` |
| `whole-os-node-contracts-v1.json` | `5f09d86039835bad72e75cd7179fc73c74db38b3874115a7d7f7f1e2fe776f77` |
| `whole-os-node-contracts-v2.json` | `35a5f41a99c05794509a475e2651e141bc285825dd97a8192e14e1619b49d1ca` |
| `whole-os-plan-v2.json` | `4e94938d1762336ba34f064e58550d92ff3a2d6147486cb9fa851d2c53f40980` |
| `generation-manifest.json` | `182296c71fdcaec7bb3e6bf1f2bf092253680b647efa5249106a3b181c6241de` |
| `DISPATCHER.json` | `6951534fb41e2225e5e7613b4a74337e97925c8280e50a7384b408777a92c214` |
| `NODE_PROMPT.md` | `8eb9adb92f04029e73b76d3a568a8ee8317b84bec175d5d15035650326abab88` |

### J-01 — permanent prompt names the wrong canonical node contracts (ADAPT, material)

PLAN says `whole-os-node-contracts-v1.json` is the historical pre-namespace
contract and `whole-os-node-contracts-v2.json` is current. The dispatcher binds:

```text
dispatcher.node_contracts_path=docs/plan/whole-os-implementation/whole-os-node-contracts-v2.json
```

The permanent prompt boundary instead states:

```text
node_prompt.declared_canonical_path=docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json
```

An independent exact-byte probe parsed both referenced JSON documents and
returned:

```text
paths_equal=False
declared_schema=whole-os-node-contracts/v1
dispatcher_schema=whole-os-node-contracts/v2
declared_has_requirement_inventory=False
dispatcher_has_requirement_inventory=True
COUNTEREXAMPLE_REPRODUCED
```

The prompt is explanatory and non-executable, and the structured renderer copies
the sealed portable-plan node rather than trusting prompt interpolation. Those
controls limit exploitation but do not cure the contradiction. The file is
explicitly the permanent worker-boundary specification, and N01 step 8 requires
exact canonical paths. A worker following its declared references can therefore
load the historical contract that lacks the accepted R01--R18 namespace binding,
while the dispatcher claims a different current source. The existing focused
test binds the prompt's bytes and separately checks the dispatcher's path digest;
it does not require the prompt's declared canonical path to equal the dispatcher
path.

Required repair: retain v1 as historical compatibility evidence, but make the
permanent prompt's canonical node-contract reference agree exactly with the
dispatcher/current v2 artifact (or remove the duplicated locator and make the
dispatcher the sole typed source). Add a semantic cross-artifact test that parses
the declared locator and checks exact path/schema/digest agreement. Because the
prompt is included in generation provenance, regenerate and reseal every affected
generation/dispatcher digest, then obtain fresh exact-candidate examination,
expert testimony, and judgment. Do not rewrite or delete this verdict or the
earlier review history.

## Requirement dispositions

Each disposition concerns the requirement's treatment in N01. A design/compiler
disposition is not proof of the later runtime or product acceptance statement.

| Requirement | Disposition | N01 holding and remaining burden |
|---|---|---|
| R01 | **adapt** | The durable-campaign design is suitable; restart and unattended-operation proof remains N08/N10/N12/N31/N33. |
| R02 | **adapt** | Evidence-ranked discovery is mapped; N02/N11/N16/N31/N32 must prove selection quality and autonomous operation. |
| R03 | **adapt** | Typed acceptance and exact qualification are the right adaptation; no production candidate or operational profile has passed. |
| R04 | **adapt** | Separate scoped PR authority and reconciliation are adopted in design; no delivery grant, PR, or feedback repair occurred. |
| R05 | **adapt** | Content/purpose-bound reuse and routing preserve gates; cost, token, and elapsed-time improvement remains unmeasured. |
| R06 | **adopt** | For N01 only, closed v2 work packages, successor-compatible outcomes, locks, routes, outputs, and local implementation freedom compile. Runtime consumption remains later work. |
| R07 | **adapt** | Subject-neutral orchestration plus tenant/tool boundaries is the accepted direction; hostile external-repository operation remains unproved. |
| R08 | **adapt** | Immutable challengers and supervisor-controlled promotion/rollback are the safe interpretation; no self-improvement promotion occurred. |
| R09 | **adapt** | App-scoped memories/challengers with no automatic Hive effect are accepted in design; enforcement and improvement evidence remain later burdens. |
| R10 | **adapt** | Fail-closed custody and negative controls are required; N01 cannot establish universal non-leakage or later runtime enforcement. |
| R11 | **adapt** | One stable draft-only lesson obligation with separate export authority is accepted; no draft was published or activated. |
| R12 | **adapt** | Endpoint reconstruction is correctly separated from strict PIT; custody, contamination, and functional evaluation remain unexercised. |
| R13 | **adapt** | Versioned evidence-driven challengers are the accepted mechanism; learning lift and held-out superiority remain unproved. |
| R14 | **defer** | A fully production-qualified Roblox game cannot be dispositioned as achieved without an admitted subject, Studio/device/runtime, security, data, asset, and license evidence. |
| R15 | **adapt** | Closed, bounded worker packets and the structured renderer are sound, but J-01 leaves their permanent canonical reference inconsistent. |
| R16 | **reject** | Reject it only as a current N01 execution constraint because the later explicit implementation directive superseded the documentation-only task. Preserve the original bytes and historical disposition; this does not erase the requirement. |
| R17 | **defer** | Preserve the analytical tournament and compiled N30 obligation, but no whole-repository empirical tournament or championship has run. |
| R18 | **adapt** | N00 custody, role/authority separation, anti-cheating controls, failures, and dissent are retained, but J-01 must be repaired before N01 can claim complete contract continuity. |

No requirement is quarantined. R06 is adopted only at the bounded N01
plan/compiler layer; R14 and R17 claims remain deferred rather than being treated
as implementation failures.

## ADR and material compiler-choice dispositions

| Decision | Disposition | Bounded holding |
|---|---|---|
| ADR-079 — 34-node topology and flexible local execution | **adopt** | Adopt the versioned portable topology, exact lock/write-path scheduling, direct ownership, and v1 compatibility design. This is not runtime activation. |
| ADR-080 — durable composition with separate delivery authority | **adopt** | Adopt one declared durable state boundary and separately revocable publication authority as architecture. Crash/effect reconciliation remains deferred. |
| ADR-081 — tenant learning and draft-only cross-repository lessons | **adopt** | Adopt the custody and promotion separation. Privacy enforcement and learning benefit remain later claims. |
| ADR-082 — endpoint reconstruction beside strict PIT | **adopt** | Adopt distinct modes, evaluator custody, family splits, and reveal retirement. No endpoint episode or learning lift is proven. |
| ADR-083 — risk-based qualification and content-bound reuse | **adopt** | Adopt purpose/content-bound receipts and independent qualification. Efficiency and invalidation completeness remain later empirical burdens. |
| Schema-v2 work packages and 34-node mapping | **adopt** | Exact N00--N33 mappings, routes, outputs, locks, dependencies, R01--R18 coverage, and 15 conflict-safe rounds reproduce. |
| V1 compatibility profile and selection rollback | **adopt** | The 13-stage v1 plan still compiles; this proves format coexistence, not a live migration/rollback drill. |
| Authenticated source/requirement closure before sealing | **adopt** | Final controls reject unknown sources and colluding R01-to-R99 substitutions before the sealer and before artifact writes. |
| Compiler receipt identity and portable path/identifier controls | **adopt** | V1/v2 identities are distinct and truthful; applicable control, DEL, Unicode, absolute, traversal, and separator attacks fail closed. |
| Local-import provenance and deterministic reconstruction | **adopt** | The checkout-local compiler boundary and fail-before-write foreign-package control are adequately evidenced for N01. |
| Closed structured worker renderer | **adopt** | Canonical requests, direct prerequisite binding, instruction/data separation, and rendered-payload digests close the original interpolation defect. |
| Inert dispatcher, authority envelope, and signature separation | **adopt** | The dispatcher is `INACTIVE`, grants no authority, requires host attestation, and no repository signature is present or permitted. |
| Permanent canonical-path composition across PLAN/dispatcher/prompt | **adapt** | J-01 proves the prompt names v1 while PLAN/dispatcher name v2; repair and reseal are required. |

The five ADRs are adopted as bounded architecture decisions even though N01 as a
whole is ADAPT. Their runtime, product, privacy, efficiency, and superiority claims
remain outside the evidence burden satisfied here.

## N00, N02, external obligations, and effects

N00 acceptance remains bound to inventory `WOS-N00-20260914-01` and the six
Curator-sealed hashes. J-01 does not reopen N00 itself. Its eight obligations remain
open and are not converted into completed inputs:

`EO-EXT-SOURCE-ARCHIVES`, `EO-OPENAI-FETCH-RECEIPTS`,
`EO-COMPARATOR-RIGHTS`, `EO-EXTERNAL-CAMPAIGN-ROOT`, `EO-ROBLOX-SUBJECT`,
`EO-ROBLOX-RUNTIME`, `EO-DELIVERY-GRANT`, and `EO-LEGACY-DISPATCH`.

N02 remains an independent open prerequisite. Its required campaign-metrics test
and benchmark-protocol artifacts are absent on this candidate, no comparator or
holdout was frozen here, and no N30 measurement may be inferred from N01.

The plan authority allows only inspect, local edit/test, and evidence preparation;
external effects are false and push, merge, deployment, credential, payment,
production mutation, and protected merge are denied. The dispatcher is inactive,
the manifest contains no signature and requires a distinct host signature, and the
review evidence found no activation or external-effect path. Neither the candidate
reviews nor this Judge session activated, signed, published, pushed, merged,
deployed, opened a PR, created credentials, or mutated production.

## Final order

**ADAPT exact candidate `7d89d27be127aef7320b9b2510c8525df8d9eda2` only.**
Preserve its positive evidence, every prior dissent/counterexample, the losing
review stages, and this verdict. Correct J-01, add the cross-artifact semantic test,
regenerate affected provenance artifacts, and submit a new exact candidate to the
independent court. Until then N01 is not accepted or complete, and N02/dependent
execution must not treat this candidate as an approved N01 input.
