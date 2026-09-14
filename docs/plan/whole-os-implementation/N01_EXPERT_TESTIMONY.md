# N01 independent Expert Witness testimony

Testified: 2026-09-14
Witness: `/root/n01_expert`, acting only as an independent Integrator/Steward
Expertise applied: portable compilers, schema and authority boundaries, deterministic
generation, recovery, lock scheduling, and instruction/data separation
Recommendation: **ADAPT**

## Exact subject and independence

I examined repaired N01 candidate
`1f7557f2c91fbaadba67387275390e33dfa9d262`, parent
`eb506932e34ed631acb72b77872b72f7d2a0bfe9`, tree
`1a624333951e2abd6a5a49b26a124e5f3e55a706`, in the isolated worktree
`C:\h\wos-n01-expert` on witness branch `codex/whole-os-n01-expert`.
The subject is the repaired successor to the candidate reviewed in
`N01_EXAMINER_REVIEW.md` at examiner commit
`78d0f32bfb6b47912e6d06ae33ed94d7647cf2d4`.

I am distinct from the N01 Architect/Advocate/Builder, the Cross-Examiner, the N00
Explorer and Curator, and the future Judge. I did not edit builder code or generated
candidate artifacts. This commit adds only this testimony. The inspection is
process-independent but not host-independent: it used a separate worktree on the
same Windows host.

## Method and exact results

I read `AGENTS.md`, the N01 contract in `NODES-FOUNDATION.md`, both N00 Curator
records and their accepted artifacts, the five proposed ADRs (ADR-079--ADR-083),
PLAN, node contracts, portable plan, generation manifest, dispatcher, worker-prompt
specification, generator/compiler/factory/renderer source, relevant tests, and the
prior Cross-Examiner review.

All Python verification below bound `PYTHONPATH` to the subject source tree and
first asserted that `hive_mind_os`, `dag_standard`, `portable_plan`, and
`node_prompt_renderer` resolved under `C:\h\wos-n01-expert\src`. The observed
package origin was
`C:\h\wos-n01-expert\src\hive_mind_os\__init__.py`.

Focused verification:

```powershell
$env:PYTHONPATH='C:\h\wos-n01-expert\src'
python -m unittest tests.test_whole_os_plan_contract tests.test_node_prompt_renderer tests.test_tournament_plan_factory tests.test_compiled_tournament -v
```

Result: **PASS, 23 tests, 0 failures/errors, 0.270 seconds**.

I then ran an independent Python audit from stdin under the same bound environment.
It did not import the generator's mapping assertions as its oracle: it separately
parsed all four `NODES-*.md` files, recomputed each section digest, compared the
handoff DAG, successor map, generated node contracts, and parsed portable plan, and
mutated copies only in memory. Results:

- **34/34 mappings passed** for IDs, objectives, dependencies, owners, routes,
  independent-review flags, completion rules, R-requirement mappings, prose-section
  digests, semantic locks, and write paths.
- The requirement namespaces in the handoff, accepted inventory, and plan each
  equal exactly R01--R18. R16 remains historically empty in the handoff node map
  but is deliberately carried by N01 in the successor contract.
- All 19 source IDs referenced by work packages exist among the 32 accepted N00
  source records. SRC-001--SRC-015 are retained exactly once in the separate
  founding-source namespace. All eight accepted open obligations remain present.
- The six N00 input hashes exactly matched the Curator seal: source inventory
  `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127`, node map
  `aeb3d9dd35c28bf431a187b8aa60e51c9ea6531fb265b40f59056b12b0b6cc4b`, symbol
  classification `89f70a0b50cf84b7a2e7fa1be4e07ac58ebcc8638f8405a9658b9e3e724857b0`,
  reconciliation `feb58b630627d0bd56d9a4d538b530b9f9b5e4d3f9a5853805d07d6a888f3f52`,
  checker `7227e840296d2f61309a36b52f45eb65fdbdf0de24ad2ab7034b3e7692022a68`,
  and validation `0470947dae960e5df39cf4d98cb0af3d10a5f3b8b36354c02c72f9505d5f187c`.
- Canonical schema-v2 parsing and compilation passed for all 34 nodes. Plan digest
  was `sha256:7a52c0a98a8b9b20f5f63191c2b02ac2d9ea2fba90ff19f69ef5939e272583a9`.
  The compiler produced 15 rounds:
  `N00`; `N01,N02`; `N03,N04`; `N05,N06,N07,N22`; `N08,N18`;
  `N09,N19,N23,N26`; `N10,N12,N20`; `N11,N13,N14`; `N15,N24`;
  `N16,N21,N25,N27`; `N17,N28`; `N29`; `N30`; `N31,N32`; `N33`.
  Every dependency is in an earlier round, and no same-round pair has an equal
  semantic lock or equal/ancestor write path.
- The existing schema-v1 `external-all-aspect-tournament-v2` profile still parsed
  and compiled as 13 nodes, digest
  `sha256:e450fffc2077d7b87dc2dabf4461689116e6670654f7cd5818a05419fe63c9b9`.
- Mutations for a cycle, unknown dependency, missing R16, unknown route, unknown
  effect, unknown authority, extra top-level field, absolute write path, parent
  traversal, and backslash path all failed closed.

Deterministic regeneration was tested without `PYTHONPATH`:

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
python scripts/generate_whole_os_plan_artifacts.py
git diff --exit-code -- docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json docs/plan/whole-os-implementation/whole-os-plan-v2.json docs/plan/whole-os-implementation/generation-manifest.json docs/plan/whole-os-implementation/DISPATCHER.json
```

Result: exit 0 and byte-identical artifacts. Before/after SHA-256 values were
`5f09d86039835bad72e75cd7179fc73c74db38b3874115a7d7f7f1e2fe776f77`
(node contracts),
`7a52c0a98a8b9b20f5f63191c2b02ac2d9ea2fba90ff19f69ef5939e272583a9`
(plan), `070fbbde160dba3fa0a69afe941db66e742bf14428d6ed20e428cad460777b73`
(manifest), and
`885704cbc20ba9e8b55c2fbbbfdda1b41b7bef5e1f0b88473a01618511a0a31c`
(dispatcher). Generation ID remained
`sha256:ef684707714f91faf6002055494865a5e8b455183fccaba7a160016841553648`.

I also preloaded a synthetic foreign `hive_mind_os` package and ran the generator
through `runpy`. It exited 1 with `N01 generator import provenance mismatch`, naming
the foreign temporary `__init__.py`; all four generated artifact hashes remained
unchanged. This independently reproduces the CE-01 repair's fail-before-write
behavior.

The renderer emitted a canonical payload with five fixed instruction strings,
sealed node data, exact prerequisite order, request/node/plan bindings, and payload
digest
`sha256:589feffd326265caf3a4f28e811e0012d7fe84cf4ec426524eded1490f9205a4`.
It rejected control-character, traversal, and absolute receipt paths, as well as a
duplicate JSON key. Hostile objective prose remained JSON data and did not replace
the fixed instruction array.

The repository-wide command `python -m unittest discover -s tests -v` was started
with the same import binding, but was intentionally interrupted at the campaign
orchestrator's direction after this candidate had a material ADAPT result. It is not
represented as a completed gate. The 23-test focused result above is the complete
N01 verification result; integration still owns the mandatory full gate.

## Atomic testimony

### EW-01 — exact candidate mappings and accepted N00 custody reproduce (ADOPT)

The checked candidate has exactly N00--N33 once across the four relevant
representations, and their contract-bearing fields reproduce. R01--R18 and the
accepted N00 hashes are intact. The candidate does not close or hide any of N00's
eight external obligations.

### EW-02 — canonical v2 parsing, lock-aware scheduling, and v1 migration coexist (ADOPT)

The exact v2 bytes parse canonically, compile into dependency-safe and
lock/write-path-conflict-free rounds, and do not use `planning_group` as a lock.
The v1 profile still compiles unchanged. This is evidence for format coexistence and
an available selection-based rollback, not evidence that a live service migration
or rollback has occurred.

### EW-03 — regeneration provenance and instruction/data separation are repaired (ADOPT)

Both earlier Cross-Examiner defects reproduce as repaired on this exact candidate:
ordinary no-`PYTHONPATH` regeneration selects the checkout source and is byte-stable;
a preloaded foreign package fails before writes; and the worker renderer accepts a
closed canonical request, rejects receipt-path injection, preserves exact direct
dependencies, and separates fixed instructions from sealed JSON data.

### EW-04 — external authority and activation remain absent (ADOPT)

The plan's authority envelope has `external_effects=false`, allows only inspect,
local edit/test, and evidence preparation, and denies credential, deployment,
merge, payment, production mutation, protected merge, and push. No capability is
`external-reversible`. The dispatcher is `INACTIVE`, grants no authority, and
requires host attestation. The manifest contains no signature, requires a distinct
host signature, and forbids a repository signature. No host activation, external
write, publication, deployment, or signature was performed or found.

### EW-05 — schema-v2 compilation receipt names the v1 compiler (ADAPT, material)

`load_bound_plan` correctly requires the v2 package identity
`hive-mind-portable-compiler-v2` with digest
`sha256:4fa18b35bf7312e73ae09904113f7d9d248bfa848b0d731c8a9438c7dcb7f025`.
However, `compile_plan` unconditionally emits
`hive-mind-portable-compiler-v1` with digest
`sha256:0fcd6b6882e29759fd32502e13619f4b0b0adc48ad307b20dc5defe138c08d0c`
in the resulting `CompilationReceipt`, including for this v2 plan. That makes the
receipt's compiler provenance false even though admission selected the correct
implementation path. Repair `compile_plan` to emit the package ID/digest selected
for the parsed schema and add exact v1/v2 receipt assertions.

### EW-06 — source IDs are checked only in generation-time tests, not by the portable compiler (ADAPT, material)

The exact candidate's 19 work-package source IDs are valid, but an in-memory v2
mutation replacing N00's sources with `GOV-NONEXISTENT` parsed and compiled in 15
rounds (mutant plan digest
`sha256:00a4c8fd7b14f79e8660bf2a1a4afc9084099c2e59cf2f4794fe3f83e4b7c0b5`).
`PortablePlanBundle` has no authenticated source-ID namespace, and compilation
derives expected R requirements from evidence but has no equivalent source-closure
check. The builder test confirms the checked JSON against today's inventory, but a
portable compiler receiving substituted yet self-consistent plan bytes cannot
repeat that proof. Bind a closed source namespace (or an authenticated source-index
artifact with resolvable bytes) into schema v2 and reject every work-package source
outside it. Preserve the exact accepted N00 inventory digest in that binding.

### EW-07 — work-package paths accept control characters (ADAPT, material)

Absolute, traversal, and backslash write paths reject, and receipt paths have an
explicit control-character guard. The shared `portable_path` validator does not
apply that guard. A write path `docs/x\ninjected` therefore parsed and compiled in
15 rounds (mutant plan digest
`sha256:e47e6c25f64a906493aff0fe627d0565a95fad3b4e45fbf01c35c17a786d7093`).
This is unsafe for logs, prompts, receipts, lock keys, and any later path consumer,
even while the current compiler remains inert. Reject C0 and DEL characters in
portable paths (and test contract path, write path, and other path-bearing fields)
before a host dispatcher consumes v2 data.

### EW-08 — later operational and product claims remain deferred (DEFER)

Migration execution, crash recovery, durable effect reconciliation, tenant/privacy
enforcement, endpoint custody, Roblox runtime, real publication, benchmark outcomes,
and production behavior belong to later nodes. The present evidence proves an inert
planning/compiler candidate only. It does not establish speed, efficiency, quality,
learning lift, production readiness, Roblox readiness, or campaign/product
superiority.

## Recommendation

**ADAPT** the exact candidate. Retain EW-01 through EW-04 as positive evidence and
EW-08 as an explicit limitation. Before N01 judgment, repair EW-05 through EW-07,
add negative tests that reproduce each mutant, regenerate and reseal every derived
digest, and obtain a fresh exact-candidate independent rereview. These are bounded
local contract/compiler repairs; they grant no new authority and do not require
activation. This testimony is not a judgment, approval, activation, signature,
publication, or superiority finding.
