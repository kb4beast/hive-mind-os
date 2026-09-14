# N01 independent Expert Witness rereview

Rereviewed: 2026-09-14
Witness: `/root/n01_expert`, acting only as an independent Integrator/Steward
Recommendation: **ADAPT**

## Exact subject and independence

I rereviewed repaired N01 commit
`97cdaf3d998ef1517592f4ceff13f14b07fe7d6d`, parent
`1f7557f2c91fbaadba67387275390e33dfa9d262`, tree
`70390666e9043558c8b676b69a2d2e78d4cbc0c1`, in fresh worktree
`C:\h\wos-n01-expert-r2` on branch
`codex/whole-os-n01-expert-r2`.

I authored the preliminary testimony for the parent repair but did not author or
edit this repaired candidate. I remain distinct from the N01
Architect/Advocate/Builder, Cross-Examiner, N00 Explorer/Curator, and future Judge.
This commit adds only this rereview. The inspection is process-independent but not
host-independent because it used a separate worktree on the same Windows host.

I read `AGENTS.md`, the exact repair diff, my prior testimony at review commit
`4f566257c1b89f770bf58f3ee7f4b94d57291ac9`, the N01 contract, accepted N00
artifacts, PLAN/ADRs, generated artifacts, compiler/factory/generator/renderer
source, and focused tests. I did not run the full repository gate; integration owns
that gate.

## Commands and positive reproduction

I bound every Python verification shell to the exact subject source tree and
asserted all imported compiler modules resolved beneath it:

```powershell
$env:PYTHONPATH='C:\h\wos-n01-expert-r2\src'
python -m unittest tests.test_whole_os_plan_contract tests.test_node_prompt_renderer tests.test_tournament_plan_factory tests.test_compiled_tournament -v
```

Result: **PASS, 23 tests, 0 failures/errors, 0.338 seconds**. Observed package
origin was
`C:\h\wos-n01-expert-r2\src\hive_mind_os\__init__.py`; `dag_standard`,
`portable_plan`, and `node_prompt_renderer` resolved under the same source root.

An independent Python audit, passed on stdin under that same environment, parsed
the handoff and candidate without using the generator's mapping constants as its
oracle. It produced these results:

- **34/34 mappings passed** across the handoff DAG, successor map, node-contract
  document, and portable plan for IDs, objectives, dependencies, owners, routes,
  review flags, completion rules, requirement mappings, exact prose-section
  digests, semantic locks, and write paths.
- The handoff, accepted inventory, and exact candidate each contain exactly
  R01--R18. The candidate's 19 referenced source IDs are members of all 32 accepted
  N00 source records; SRC-001--SRC-015 remain distinct; all eight external
  obligations remain open.
- All six N00 seal hashes reproduced exactly, including source inventory
  `39109ae21cc5d55b7fa85506ffc18920701e2e89db77949aa191021d7b85d127`.
- Canonical schema-v2 plan digest is
  `sha256:a18ac06db92edd7bedcb5e1bad5d4b359ac95615f17068fa0f98f79c2946a5bb`.
  It compiles as 34 nodes in 15 dependency/lock-safe rounds and its receipt now
  correctly names `hive-mind-portable-compiler-v2` with digest
  `sha256:ae00bc3a094608f317d10b7b1c568dc67e38bf290a33c1e33e2e92a08b1114ae`.
- The schema-v1 compatibility plan still compiles as 13 nodes and its receipt
  correctly names `hive-mind-portable-compiler-v1`.
- The 15 v2 rounds remain: `N00`; `N01,N02`; `N03,N04`;
  `N05,N06,N07,N22`; `N08,N18`; `N09,N19,N23,N26`; `N10,N12,N20`;
  `N11,N13,N14`; `N15,N24`; `N16,N21,N25,N27`; `N17,N28`; `N29`;
  `N30`; `N31,N32`; `N33`. Every dependency is earlier and no same-round
  pair shares a semantic lock or equal/ancestor write path.
- Renderer instruction/data separation reproduced with payload digest
  `sha256:dff09893b2691450507d70b321928a4bfb7b1424009e1e2bc0e84e305edde685`.
  It rejected control, non-ASCII, and traversal receipt paths.
- The dispatcher remains `INACTIVE`, grants no authority, requires host
  attestation, and binds the accepted source-inventory digest. The manifest has no
  signature, requires a distinct host signature, and forbids a repository
  signature. The plan has no external-reversible capability or external-effect
  authority.

Deterministic regeneration was replayed with `PYTHONPATH` removed:

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
python scripts/generate_whole_os_plan_artifacts.py
git diff --exit-code -- docs/plan/whole-os-implementation/whole-os-node-contracts-v1.json docs/plan/whole-os-implementation/whole-os-plan-v2.json docs/plan/whole-os-implementation/generation-manifest.json docs/plan/whole-os-implementation/DISPATCHER.json
```

It exited 0 with no diff. Before/after SHA-256 values were
`5f09d86039835bad72e75cd7179fc73c74db38b3874115a7d7f7f1e2fe776f77`
(contracts),
`a18ac06db92edd7bedcb5e1bad5d4b359ac95615f17068fa0f98f79c2946a5bb`
(plan), `73fe3ddd8efb6f516fb741aa42178ec52138cd6743615802b61162538998a85b`
(manifest), and
`4f3c58be9a5affac6574ff2d709be2ad69c38de777ac321563699e199d681c57`
(dispatcher). Generation ID remained
`sha256:38f4e7d416926ade40ccd30a5326d993e2dbea93c718f6421979a709073f6616`.

A separately spawned Python process preloaded a synthetic foreign
`hive_mind_os`. The generator exited 1 with `N01 generator import provenance
mismatch` naming the foreign temporary package, and all four artifact hashes stayed
unchanged.

## Replay of the original findings

### EW-05 — v2 receipt compiler identity (closed: ADOPT)

The exact v2 receipt now derives its compiler identity from the authenticated
standard binding and names compiler v2; the independently generated v1 receipt
still names v1. This closes the prior false-provenance defect without rewriting v1
history.

### EW-06 — source namespace closure (partly closed: ADAPT)

The compiler now requires the exact accepted source-inventory bytes. The following
independent mutations all failed closed:

- omitted source-inventory bytes;
- changed source ID within reserialized inventory bytes;
- changed inventory ID;
- changed plan evidence digest while supplying the exact inventory;
- unknown `GOV-NONEXISTENT` in a work package while supplying the exact inventory;
- substituted factory-level inventory ID or digest.

Thus the exact candidate and the compiler admission boundary have genuine source
closure. However, the pre-compilation factory/sealing boundary remains open. With
the correct accepted inventory ID/digest and evidence, I replaced N00's source list
with `GOV-NONEXISTENT`. `WholeOSPlanFactory.build` returned plan
`sha256:44f5181b39b722700e5dc5b16fe76464cc0147dc0b9511ae18391d118fda4c5f`.
`WholeOSPlanFactory.generate` then returned `inserted=True` and sealed inert
generation
`sha256:8428833f781d7da8fbee37cba64a31b18bd37a7c4f477041fc8fcdd9cfd5c21c`
with plan digest
`sha256:4996db18cab7c4df82c16abeb3c6b6ecfe5c87b4bf12eb29fe25e2c1a6820b25`.
Only a later explicit `compile_plan(..., source_inventory_bytes=...)` rejected it
as `node N00 cites unadmitted source id(s): GOV-NONEXISTENT`.

Generation is itself an N01 evidence/provenance boundary. It must not seal a plan
that the canonical compiler rejects. Pass the exact inventory bytes/admitted
namespace into `WholeOSPlanFactory.build/generate`, or compile and authenticate the
candidate before `PlanGenerator.generate` registers it. Add negative tests for
both `build` and `generate`, not only downstream compilation.

### EW-07 — path and identifier injection (closed: ADOPT)

At portable-plan parse time, newline and DEL write paths reject as control
characters and `docs/café` rejects as non-ASCII. Control/non-ASCII contract paths,
source IDs, and semantic locks likewise reject. Renderer receipt paths reject
control, non-ASCII, absolute, and traversal forms. Absolute, traversal, and
backslash work-package paths remain rejected. Instruction-like objective prose is
still inert JSON data, not an identifier or instruction field.

The ASCII restriction is intentionally conservative and may require a future
versioned path policy for repositories with Unicode filenames; this does not weaken
the current fail-closed boundary.

## Additional atomic finding

### EW-R2-01 — requirement closure remains self-referential (ADAPT, material)

The positive exact-candidate mapping is R01--R18, but compiler closure derives its
expected requirement set from mutable evidence metadata inside the same plan. I
replaced R01 with R99 both in `whole-os-handoff.claim_ids` and every affected work
package. The resulting canonical v2 plan
`sha256:c0f3982ca45dcdd78b3b84cb86a6aba6fae284898f26830f3da41442ba21a493`
compiled all 34 nodes. Its observed set was R02--R18 plus R99; R01 silently
disappeared.

This is a substitution rather than the already-tested orphan/removal case. The
accepted source inventory already contains the exact R01--R18 requirement
namespace, so compiler validation should derive admitted requirements from those
authenticated inventory bytes and require exact equality. The factory/generation
boundary must enforce the same rule before sealing. Add a colluding
evidence-plus-node substitution negative control.

## Migration, rollback, and limitations

The v1 and v2 compiler receipts now truthfully identify their distinct packages,
and both profiles remain readable. Deterministic reconstruction and lack of any
active dispatcher mutation support the documented selection-based rollback. This
does not prove a live service migration, crash recovery, or operational rollback.

No external host, signature, activation, publication, credential, benchmark,
Roblox runtime, tenant boundary, or production behavior was exercised. These
remain later-node obligations. Nothing in this rereview supports an efficiency,
quality, learning, production, Roblox, campaign, or product superiority claim.

## Recommendation

**ADAPT.** Retain the exact-candidate positive evidence and the closure of EW-05 and
EW-07. Retain EW-06's compiler-level repair, but close the factory/generation path
before it can return or register an invalid plan. Bind R01--R18 to the exact
accepted inventory bytes rather than plan-authored evidence metadata. Regenerate
and reseal derived artifacts, add the two counterexample families above, and obtain
a fresh exact-candidate independent rereview before judgment.

This is expert testimony, not a judgment, approval, activation, signature,
publication, or superiority finding.
