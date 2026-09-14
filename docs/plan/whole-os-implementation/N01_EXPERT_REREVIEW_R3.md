# N01 independent Expert Witness rereview r3

Rereviewed: 2026-09-14
Witness: `/root/n01_expert`, acting only as an independent Integrator/Steward
Recommendation: **ADOPT** for the bounded, inactive N01 planning/compiler candidate

## Exact subject and independence

I rereviewed exact candidate
`7d89d27be127aef7320b9b2510c8525df8d9eda2`, parent
`97cdaf3d998ef1517592f4ceff13f14b07fe7d6d`, tree
`56d9a91b6b205b0a08ed4e3dbe544c2ef1011faa`, in fresh worktree
`C:\h\wos-n01-expert-r3` on branch
`codex/whole-os-n01-expert-r3`.

I authored the prior Expert testimony and rereview, but did not author or edit this
repair. I remain distinct from the N01 Architect/Advocate/Builder,
Cross-Examiner, N00 Explorer/Curator, and future Judge. This commit adds only this
r3 rereview. The inspection is process-independent but not host-independent because
it used another worktree on the same Windows host.

I read `AGENTS.md`, the N01 contract, accepted N00 records and artifacts, PLAN and
ADRs, generated artifacts, compiler/factory/generator/renderer code and focused
tests, my initial testimony at
`4f566257c1b89f770bf58f3ee7f4b94d57291ac9`, and r2 rereview at
`9e6c09c1675fdddf1986122ff3032d4860c27c71`. I ran no full repository CI gate;
integration retains that obligation.

## Commands and observed results

Every Python verification shell bound `PYTHONPATH` to the exact subject source and
asserted import provenance beneath that root:

```powershell
$env:PYTHONPATH='C:\h\wos-n01-expert-r3\src'
python -m unittest tests.test_whole_os_plan_contract tests.test_node_prompt_renderer tests.test_tournament_plan_factory tests.test_compiled_tournament -v
```

Result: **PASS, 25 tests, 0 failures/errors, 0.398 seconds**. Observed origins for
`hive_mind_os`, `dag_standard`, `portable_plan`, and `node_prompt_renderer` were all
under `C:\h\wos-n01-expert-r3\src`.

I separately parsed the handoff DAG, all four `NODES-*.md` files, accepted N00
inventory, successor map, current `whole-os-node-contracts-v2.json`, and canonical
portable plan. I recomputed prose-section and artifact hashes rather than trusting
the generator's constants. Results:

- **34/34 mappings passed** for IDs, objectives, dependencies, owners, routes,
  review flags, completion rules, R mappings, exact prose-section digests,
  semantic locks, and write paths.
- Handoff requirements, accepted N00 requirements, v2 contract namespace, and
  exact plan each contain exactly R01--R18. Requirements bytes digest is
  `sha256:5c49bc3f9c818b6adfb326adb08bc103abd6f7e84feeebe74bdbe4f782d4b7d5`.
- All 19 work-package source references are members of the 32 accepted N00 source
  records; SRC-001--SRC-015 remain separately retained and all eight external
  obligations remain open.
- The six Curator-sealed N00 hashes reproduced exactly. Source inventory remained
  `sha256:39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127`.
- Canonical v2 plan digest is
  `sha256:4e94938d1762336ba34f064e58550d92ff3a2d6147486cb9fa851d2c53f40980`.
  It compiled as 34 nodes in 15 rounds. Its receipt names
  `hive-mind-portable-compiler-v2` and digest
  `sha256:191895692b8429ccd84ef66a03692ab5ab87fe96a0ca76162a32957be2df883c`.
- The v1 compatibility plan still compiles as 13 nodes and its receipt names
  `hive-mind-portable-compiler-v1`.
- The 15 v2 rounds remain: `N00`; `N01,N02`; `N03,N04`;
  `N05,N06,N07,N22`; `N08,N18`; `N09,N19,N23,N26`; `N10,N12,N20`;
  `N11,N13,N14`; `N15,N24`; `N16,N21,N25,N27`; `N17,N28`; `N29`;
  `N30`; `N31,N32`; `N33`. Every dependency is earlier and no same-round
  pair shares a semantic lock or an equal/ancestor write path.

I replayed all prior negative probes against copies held only in memory:

- missing source-inventory bytes and missing requirements bytes reject;
- `GOV-NONEXISTENT` rejects at compiler and factory/generate boundaries;
- substituted source-evidence claims reject;
- altered, missing, or reordered requirements bytes reject against the exact
  accepted digest;
- colluding R01-to-R99 changes in evidence plus every affected work-package mapping
  reject at compiler admission;
- colluding R01-to-R99 changes in the factory contract and its declared requirement
  namespace reject before sealing;
- control, DEL, non-ASCII, absolute, traversal, and backslash path attacks reject at
  their applicable parser/renderer boundaries;
- control/non-ASCII source identifiers and semantic locks reject as non-portable
  identifiers.

For pre-seal ordering I supplied a spy generator whose `generate` method would fail
the probe if called. Both `GOV-NONEXISTENT` and colluding R01-to-R99 factory
requests rejected with `spy.calls == 0`. Hashes of the contracts, plan, manifest,
and dispatcher were identical before and after. I also replaced the script's
factory with an independently refusing factory: `main()` propagated the admission
failure and changed **0 of 4 artifacts**.

Deterministic reconstruction was then replayed without `PYTHONPATH`:

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
python scripts/generate_whole_os_plan_artifacts.py
git diff --exit-code -- docs/plan/whole-os-implementation/whole-os-node-contracts-v2.json docs/plan/whole-os-implementation/whole-os-plan-v2.json docs/plan/whole-os-implementation/generation-manifest.json docs/plan/whole-os-implementation/DISPATCHER.json
```

It exited 0 with no diff. Before/after SHA-256 values were
`35a5f41a99c05794509a475e2651e141bc285825dd97a8192e14e1619b49d1ca`
(contracts),
`4e94938d1762336ba34f064e58550d92ff3a2d6147486cb9fa851d2c53f40980`
(plan), `182296c71fdcaec7bb3e6bf1f2bf092253680b647efa5249106a3b181c6241de`
(manifest), and
`6951534fb41e2225e5e7613b4a74337e97925c8280e50a7384b408777a92c214`
(dispatcher). Generation ID remained
`sha256:50bdd4cbc2712892713d3ef5dffccb792f0605db77ed40ca434ba594a8ee9a0c`.

A separate process preloaded a synthetic foreign `hive_mind_os`. The generator
exited 1 with `N01 generator import provenance mismatch`, named the foreign package,
and changed **0 of 4 artifacts**.

The renderer preserved five fixed instructions separate from sealed node/receipt
data and emitted payload digest
`sha256:1ea51a79eac4ea75c0ed33147fc8534873f35d0c0a69b9ef70bfd75b830ff135`.
Control, non-ASCII, traversal, duplicate/substituted, and noncanonical request forms
failed closed in the focused and independent probes.

## Atomic testimony

### R3-EW-01 — exact mappings and N00 custody reproduce (ADOPT)

The exact candidate preserves all 34 mappings, R01--R18, admitted source namespaces,
founding sources, open obligations, and sealed N00 hashes. The current v2 contract
adds authenticated source and requirement namespace bindings without rewriting the
retained historical v1 node-contract artifact.

### R3-EW-02 — v1/v2 compatibility and lock-aware compilation reproduce (ADOPT)

Both compiler profiles parse and emit truthful package identities. V2 produces the
same dependency-safe, lock-aware 15-round schedule; v1 remains a readable 13-node
compatibility profile. This supports the documented selection-based migration and
rollback design, not a claim that a live service migration was exercised.

### R3-EW-03 — EW-05 receipt provenance remains closed (ADOPT)

The v2 receipt identifies the authenticated v2 compiler package and v1 still
identifies v1. No false compiler provenance reproduced.

### R3-EW-04 — EW-06 and the r2 pre-seal source gap are closed (ADOPT)

Exact source bytes, digest, inventory identity, evidence binding, and node source IDs
are validated at compiler admission. The factory receives the exact pinned bytes,
derives admitted IDs before constructing nodes, and rejects unknown sources before
calling its sealer. The generator script performs all admission/generation work
before its first repository artifact write.

### R3-EW-05 — the r2 requirement-substitution gap is closed (ADOPT)

The v2 compiler descriptor, contract artifact, factory, plan evidence, and dispatcher
bind the exact requirements path, bytes digest, and ordered R01--R18 identifiers.
Omission, alteration, reordering, and colluding evidence/mapping substitution all
fail against an independently supplied pinned requirements artifact. No
self-referential requirement oracle remains on the exercised N01 path.

### R3-EW-06 — EW-07 injection defenses remain closed (ADOPT)

Path-bearing fields reject controls, DEL, non-ASCII text, absolute paths, traversal,
and unnormalized separators. Identifier-bearing fields reject control and Unicode
substitution. Caller prose remains inert structured data and cannot replace the
renderer instruction contract.

### R3-EW-07 — external activation and authority remain absent (ADOPT)

The dispatcher is `INACTIVE`, grants no authority, requires host attestation, and
binds both source and requirement artifacts. The generation manifest contains no
signature, requires a distinct host signature, and forbids repository signatures.
The plan has no external-reversible capability or external-effect authority. No
activation, signature, external write, publication, merge, deployment, or credential
operation occurred.

### R3-EW-08 — later operational and product claims remain deferred (DEFER)

This evidence covers an inert N01 plan/compiler candidate. Live migration, crash
recovery, durable effect reconciliation, tenant/privacy enforcement, endpoint
custody, Roblox runtime, real publication, benchmark outcomes, and production
behavior remain later-node burdens. Nothing here supports efficiency, quality,
learning, production, Roblox, campaign, or product superiority.

## Recommendation

**ADOPT** the exact candidate for the bounded N01 architecture and inactive
planning/compiler scope, subject to a separate Judge's disposition. Preserve the
prior dissent and all r1/r2 counterexamples as append-only evidence. Integration
must still compose those review artifacts, run the repository CI gate on the final
candidate, and keep every later operational/product claim deferred until its own
evidence exists.

This expert recommendation is not a judgment, activation, signature, publication,
or superiority finding.
