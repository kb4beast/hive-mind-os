# N01 independent Judge rereview

Rereview date: 2026-09-14

Verdict: **ADOPT exact repaired N01 candidate only**

Judge: `/root/n01_judge`, acting only as the independent N01 Judge

Candidate: `556dab17e52c1c0c41c589290d5e30546afe367e`

Candidate tree: `24af86f954c44fda94193e0ac2b771663a183764`

Parent: `7d89d27be127aef7320b9b2510c8525df8d9eda2`

Judge worktree: `C:\h\wos-n01-judge-r2`

Judge branch: `codex/whole-os-n01-judge-r2`

## Scope, independence, and holding

I am the same independent Judge identity that issued the append-only ADAPT verdict
for the parent candidate, and I remain distinct from the N00 Explorer/Curator, the
N01 Architect/Advocate/Builder, Cross-Examiner, Expert Witness, and affected
champion. I did not author or edit the repair. This commit adds only this rereview.

**ADOPT** the repaired candidate for the bounded N01 architecture and inactive
planning/compiler scope. J-01 is closed: the generator constants, PLAN,
`NODE_PROMPT.md`, and `DISPATCHER.json` now identify v2 as the sole current
admitting successor contract; v1 is separately and consistently retained as
historical, non-admitting compatibility evidence; and divergent path/status inputs
fail before sealing or before repository writes, according to their boundary.

The prior verdict remains valid append-only evidence of the rejected parent and is
not superseded as history. This rereview does not adopt an operating product,
activate a campaign, satisfy integration CI, prove runtime durability or privacy,
publish anything, qualify Roblox, demonstrate learning, run a benchmark, or support
any production or superiority claim.

## Exact binding and evidence applicability

Before this evidence file was added, the fresh worktree was clean and returned the
candidate, tree, and parent above. The repair commit changes nine N01 files only:
PLAN, prompt, dispatcher, generation manifest, v2 contracts, v2 plan, generator,
and two focused tests. It does not alter the accepted N00 inventory, requirements,
v1 historical contract, core portable compiler/factory/renderer modules, or ADR
texts.

The prior Judge verdict is commit
`640b3a1a57de61cf0649f63861c81a9431a53c53`, parent exact rejected candidate,
blob `6939b498bb720e5a8505ca33b454f6f31e604239`, file SHA-256
`c350e6146e6845bdd6d7583b3b0ef557cd3ad56f88de9a0db8cbd92325a3121a`.
It records J-01 and all earlier court history.

The final parent Cross-Examiner ADOPT evidence remains at commit
`6970b5237f4e6774a2811c7f730a7abea1d43781`, evidence SHA-256
`01c67a5bceac49b434e9731e1029e94d8c91a5c82600068bc8c31ea3247048ab`.
The final parent Expert ADOPT evidence remains at commit
`6bf9d8249e3d59086dc6e83cb12e48afdbe2c911`, evidence SHA-256
`fdc8b8541cc9020958f2c59f9e6c49654e2cc9e64541eedd7db0c396c6c10b0f`.
Their findings on source/requirement closure, compiler identity, v1 compatibility,
lock scheduling, path defenses, renderer separation, inactive authority, and open
later burdens remain applicable because their implementation bytes did not change.
Their exact parent v2-plan, contract, generation, dispatcher hashes and N01 mapping
receipt do **not** transfer to this repair; the regenerated values below supersede
those candidate-specific observations. The Judge independently reproduced the
changed mapping and canonical-selection boundary rather than relabelling the parent
receipts.

Earlier Examiner and Expert ADAPT findings, their concrete counterexamples, and
their intermediate repair reviews remain preserved through the prior verdict and
their exact commits. None is deleted or rewritten by this ADOPT decision.

## Verification

Every Python shell bound `PYTHONPATH` to
`C:\h\wos-n01-judge-r2\src`. The imported `hive_mind_os` resolved to
`C:\h\wos-n01-judge-r2\src\hive_mind_os\__init__.py`; the focused import
probe also placed `dag_standard`, `portable_plan`, and `node_prompt_renderer` under
that same source root.

The contract-focused command passed **26/26** tests in 0.401 seconds. I also replayed
the builder's exact expanded command:

```text
python -m unittest tests.test_whole_os_plan_contract \
  tests.test_node_prompt_renderer tests.test_tournament_plan_factory \
  tests.test_compiled_tournament tests.test_portable_plan \
  tests.test_dag_standard_product tests.test_plan_generation \
  tests.test_runtime_contracts tests.test_contracts -v
```

Result: **PASS, 63 tests, 0 failures/errors, 0.461 seconds**. `git diff --check`
was clean. I did not run full CI; integration retains the mandatory
`python -m unittest discover -s tests -v` burden on the exact integrated history.

With `PYTHONPATH` removed, direct regeneration completed and all four generated
artifacts remained byte-identical. The worktree remained clean.

| Artifact | SHA-256 |
|---|---|
| `source-inventory.json` | `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127` |
| `requirements.json` | `5c49bc3f9c818b6adfb326adb08bc103abd6f7e84feeebe74bdbe4f782d4b7d5` |
| `whole-os-node-contracts-v1.json` | `5f09d86039835bad72e75cd7179fc73c74db38b3874115a7d7f7f1e2fe776f77` |
| `whole-os-node-contracts-v2.json` | `e6266ef759c4ddfd87cdf39d0f8faee89283d967f315ae13c9a601178ea0b7cd` |
| `whole-os-plan-v2.json` | `a441e4906a01de776af54f0538824d18363c7403b615df67392a51df34b96005` |
| `generation-manifest.json` | `9cfd971bbd4403d4072196ffdbfffa174e7a14687ab84a5011d54a293b256c87` |
| `DISPATCHER.json` | `9854e52bdd8e8e48b5cb64c0c6a65eccd7c43adefb02645ed0817d5af075985a` |
| `NODE_PROMPT.md` | `dac3872048f4f2a0ea9d435c951e581b8ba195e01b2809bf758c7e5e11e3fb2a` |
| generator | `e3f85cd9c73f33a2d75ff889e357d1d4e4bb1fd0b244b07ce7c096a746f1ef61` |

## J-01 replay

The positive binding reproduced exactly:

```text
generator current = docs/plan/whole-os-implementation/whole-os-node-contracts-v2.json
generator historical = docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json
PLAN current/historical declarations = exactly one each
NODE_PROMPT current/historical declarations = exactly one each
dispatcher current = v2
dispatcher historical = v1, admission_allowed=false
current schema = whole-os-node-contracts/v2
historical schema = whole-os-node-contracts/v1
```

I mutated each material selector independently in memory. Results:

| Mutation | Observed rejection boundary |
|---|---|
| current contracts schema v2 to v1 | before sealing |
| generator current path/declaration to v1 | before factory construction/sealing |
| generator historical path/declaration to v2 | before factory construction/sealing |
| NODE_PROMPT current path to v1 | before factory construction/sealing |
| NODE_PROMPT historical path to v2 | before factory construction/sealing |
| PLAN current path to v1 | before factory construction/sealing |
| PLAN historical path to v2 | before factory construction/sealing |
| dispatcher current path to v1 | before repository writes; zero write calls |
| dispatcher historical path to v2 | before repository writes; zero write calls |
| dispatcher historical digest/purpose substitution | before repository writes |
| dispatcher historical `admission_allowed=false` to `true` | before repository writes; zero write calls |

The prose and generator-constant checks execute before `WholeOSPlanFactory` is
constructed. The derived dispatcher is necessarily assembled after the inert plan
is generated, but its complete current/historical selection is validated before
the first of the four repository artifact writes. Thus the repaired ordering meets
the appropriate pre-seal or pre-write burden without claiming that inert generation
is activation. J-01 is **closed / ADOPT**.

## Requirement dispositions

Each disposition is limited to how N01 carries or implements the requirement. Later
runtime/product acceptance remains separate.

| Requirement | Disposition | Holding and remaining burden |
|---|---|---|
| R01 | **adapt** | Adopt the durable-campaign design; N08/N10/N12/N31/N33 still owe restart and unattended-operation evidence. |
| R02 | **adapt** | Evidence-ranked discovery is mapped; value selection and autonomous operation remain N02/N11/N16/N31/N32 burdens. |
| R03 | **adapt** | Typed acceptance and exact qualification are the safe adaptation; no production profile has passed. |
| R04 | **adapt** | Separate scoped PR authority and reconciliation are accepted in design; no grant, PR, or feedback repair occurred. |
| R05 | **adapt** | Purpose/content-bound reuse preserves gates; token, cost, and elapsed-time benefit remains unmeasured. |
| R06 | **adopt** | Closed v2 work packages, successor-compatible outcomes, exact locks/routes/outputs, and local implementation freedom compile for N01. |
| R07 | **adapt** | Subject-neutral orchestration and tenant/tool boundaries are accepted; hostile external-repository operation is unproved. |
| R08 | **adapt** | Immutable challengers and supervisor-controlled promotion/rollback are the accepted safe mechanism; no promotion occurred. |
| R09 | **adapt** | App-scoped memory and challengers with no automatic Hive effect are accepted in design; enforcement remains later work. |
| R10 | **adapt** | Fail-closed custody and negative controls are required; N01 makes no universal non-leakage claim. |
| R11 | **adapt** | One stable draft-only lesson obligation with separate export authority is accepted; no draft was published or activated. |
| R12 | **adapt** | Endpoint reconstruction remains correctly distinct from strict PIT; custody and grading are not exercised here. |
| R13 | **adapt** | Versioned evidence-driven challengers are accepted; held-out learning lift remains unproved. |
| R14 | **defer** | Production Roblox qualification still lacks an admitted subject, runtime/devices, security/data, asset, and license evidence. |
| R15 | **adopt** | For N01, all 34 bounded packages and the structured worker boundary are explicit; J-01's canonical source is now closed. Route efficacy remains N07/N30 work. |
| R16 | **reject** | Reject only as a current N01 execution constraint because the later explicit implementation directive superseded the documentation-only task; preserve its original bytes/history. |
| R17 | **defer** | The analytical field and N30 obligation are preserved, but no empirical tournament or championship has run. |
| R18 | **adopt** | N00 custody, exact namespaces, roles, authority separation, anti-cheating controls, dissent, failures, and canonical-path continuity are preserved at N01. |

No requirement is quarantined. R06, R15, and R18 are adopted only at the bounded
N01 plan/compiler layer. R14 and R17 remain explicit deferrals.

## ADR and material compiler-choice dispositions

| Decision | Disposition | Bounded holding |
|---|---|---|
| ADR-079 — 34-node topology and flexible local execution | **adopt** | Versioned topology, direct ownership, lock/write-path scheduling, and v1 compiler-profile compatibility reproduce. |
| ADR-080 — durable composition with separate delivery authority | **adopt** | Adopt the single declared state boundary and separately revocable publication authority as architecture; runtime crash/effect proof remains later. |
| ADR-081 — tenant learning and draft-only lessons | **adopt** | Adopt custody and promotion separation; privacy enforcement and learning benefit remain later claims. |
| ADR-082 — endpoint reconstruction beside strict PIT | **adopt** | Adopt distinct modes, evaluator custody, family splits, and reveal retirement; no episode result is inferred. |
| ADR-083 — risk-based qualification and content-bound reuse | **adopt** | Adopt purpose/content-bound receipts and independent qualification; efficiency remains empirical. |
| Schema-v2 work packages and 34-node mapping | **adopt** | Exact N00--N33 coverage, R01--R18 closure, routes, outputs, locks, and conflict-safe rounds reproduce. |
| V1 compiler/profile compatibility and selection rollback | **adopt** | The existing 13-stage v1 portable plan still compiles. The separate historical v1 node-contract artifact is non-admitting. No live rollback is claimed. |
| Source/requirement closure and pre-seal admission | **adopt** | Prior unknown-source and colluding R01-to-R99 attacks remain closed. |
| Compiler identity and path/identifier controls | **adopt** | V1/v2 identities remain truthful and applicable control/Unicode/escape attacks fail closed. |
| Local import provenance and deterministic regeneration | **adopt** | Checkout-local imports and byte-stable generation reproduce; foreign preloaded packages remain rejected before writes. |
| Closed structured renderer | **adopt** | Canonical request, direct dependency, instruction/data, and payload-digest controls are unchanged and pass. |
| Inert authority/signature boundary | **adopt** | Dispatcher remains inactive, grants no authority, plan external effects are false, and no repository signature is present or permitted. |
| Current/historical canonical contract composition | **adopt** | J-01 path/status mutation matrix rejects and v1 is explicitly non-admitting. |

## Open obligations and prohibited inferences

N00 remains accepted only for inventory `WOS-N00-20260914-01` and its sealed
hashes. Its eight external obligations remain open:

`EO-EXT-SOURCE-ARCHIVES`, `EO-OPENAI-FETCH-RECEIPTS`,
`EO-COMPARATOR-RIGHTS`, `EO-EXTERNAL-CAMPAIGN-ROOT`, `EO-ROBLOX-SUBJECT`,
`EO-ROBLOX-RUNTIME`, `EO-DELIVERY-GRANT`, and `EO-LEGACY-DISPATCH`.

N02 remains an independent open prerequisite. No comparator/holdout protocol,
campaign-metrics implementation, or benchmark result is supplied by N01.

The dispatcher is `INACTIVE` with `authority_granted=false`; the plan permits only
inspection, local edit/test, and evidence preparation; external effects are false;
push, merge, deployment, credential, payment, production mutation, and protected
merge are denied. The manifest contains no signature, requires a distinct host
signature, and forbids repository signatures. Neither the repair nor this Judge
session activated, signed, published, pushed, merged, deployed, opened a PR,
created credentials, mutated production, or used external effect authority.

## Final order

**ADOPT exact candidate `556dab17e52c1c0c41c589290d5e30546afe367e` for N01
only.** Preserve the parent ADAPT verdict, every earlier dissent and counterexample,
and all superseded hashes. This evidence may be composed as the independent N01
Judge receipt. Integration must still run full CI on its exact integrated history;
N02 and every external/runtime/product burden remain open until separately
evidenced. No broader completion or superiority conclusion is authorized.
