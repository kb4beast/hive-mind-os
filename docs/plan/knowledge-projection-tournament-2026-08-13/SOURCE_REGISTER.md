# Source Register

## Baseline and license

- Repository: `https://github.com/kb4beast/hive-mind-os.git`
- Baseline commit: `a93df2632f259f4b63f7a4f27eb0b163b5a47204`
- Baseline tree: `a9ba24f17974b1992298f3bc9a85e8f878b7bc5d`
- Retrieval: `git fetch origin --prune` followed by a local `main` fast-forward from
  `56cdf8b7a25294a0e1fbe73d8f732575e8c6b9a2` to the baseline on 2026-08-13.
- Repository license: MIT; `LICENSE` Git blob
  `06da1af7996f5e2b059cd52045e36f9f2cfac201`.

## User source

- `USER_OBJECTIVE.md` preserves the direct task excerpts and a separately labelled
  atomic extraction.

## Normative and planning sources on the baseline

| Source | Git blob | Use |
| --- | --- | --- |
| `AGENTS.md` | `bb5200ef404314e89ae5627d94dc98c9cad427fe` | Constitution, roles, courtroom, definition of done |
| `docs/architecture/HARDENED_VISION_CONTRACT.md` | `66a200d99fcd415bbaa2256c134b68fc0cb53aa7` | Normative product contract |
| `docs/execution/DAG_AUTHORING_STANDARD.md` | `70e43b0a8078a303d44c0109b8dd218a948258c2` | Executable DAG contract |
| `docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` | `5674febd4fdd6b9ac8a4be9bc4c003881412ba5a` | Prior proposal; not implementation evidence |

## Implemented baseline sources inspected

| Source | Git blob | Evidence boundary |
| --- | --- | --- |
| `src/hive_mind_os/brain_kernel/events.py` | `f50790ef776851f38afed8fb1bfdc1e0db9af2b5` | Hash-bound event values |
| `src/hive_mind_os/brain_kernel/store.py` | `731513e3792223213065630b0e86d6bff2f6c900` | Local append-only SQLite event spine and rebuildable projections |
| `src/hive_mind_os/brain_kernel/memory.py` | `db2994398f3b9d3489c98ffbfa831557e150d489` | Bounded memory, sensitivity, supersession, contradiction, quarantine |
| `src/hive_mind_os/brain_kernel/projection.py` | `764af4f4487ca37e2a9da2fa6394ed2d984eb92d` | Mission/work reducer only; not an Obsidian projector |
| `src/hive_mind_os/brain_kernel/court_runtime.py` | `cef6804c65ae5d2d2cd6d9e87fde41247e2c1ae6` | Court briefs, verdicts, limited appeals |
| `src/hive_mind_os/brain_kernel/learning_runtime.py` | `dcd8070e01d2b044cc77371e7716d35a498cab02` | Signals, lessons, remands, counterexamples, dissent |
| `src/hive_mind_os/brain_kernel/challengers.py` | `f1baf53b8b46b9a31b505d3114dfc8e9084d3919` | Immutable challenger generation |
| `src/hive_mind_os/brain_kernel/evaluation_runtime.py` | `a10334379f825104bbebf361282a3ee6de6e57d6` | Held-out challenger evaluation evidence |
| `src/hive_mind_os/brain_kernel/promotion.py` | `d5ba97ee98740da683f24e9351f2ba3fe96963fc` | Prompt-oriented promotion and rollback |
| `src/hive_mind_os/brain_kernel/contracts.py` | `e43fc4ddd0aceebc1e4f0b640060e5f03aa40e62` | Authority-envelope and budget contracts; narrowing gaps are adverse evidence |
| `src/hive_mind_os/brain_kernel/authority.py` | `d21eb2658de0eb4d82cc09c5e6e0e1caf36d34f3` | Authority registry; content binding and collision behavior are adverse evidence |
| `src/hive_mind_os/brain_kernel/effects.py` | `1cfb18b242f2b76395ee1efe52468110290937b3` | Actual effect-boundary checks that `AUTHORITY-020` must close |
| `src/hive_mind_os/brain_kernel/effect_outbox.py` | `99e811f72ba1d3f1f69891dcb5d3df1c4b67ec98` | Durable effect intent/outbox boundary |
| `src/hive_mind_os/projection.py` | `1f90009df27a32416ec80ec62a5552f009356688` | Direct JSON/HTML operational projection; not an Obsidian or transactional private projector |
| `.autopilot/bin/learning.py` | `b29e777064f6319889c4b33fb8971e8782547c8c` | Existing cross-repository lesson import/export path requiring quarantine controls |
| `.autopilot/lessons/README.md` | `373290ac7fc90ad2386992e2f4235c0de1b593d3` | Existing committed lesson policy and portability evidence |

Repository-wide source and test searches at the baseline found no implemented
Obsidian/vault/Wikilink projector, stable `Idea`/`IdeaPass` runtime, private/shared
knowledge registry, or publishability release gateway. This is a code finding, not a
claim that no untracked or external implementation exists.

## Prior same-repository prototype evidence

The local branch `codex/phase3-federation-recursion-guards` was inspected read-only as
prior-art evidence. It is not in the baseline ancestry and must not be reported as a
feature of `main`.

- Commit: `2cbfe1d0e4dccd6f1758e5ddba10f799834bf857`
- Tree: `31cf299fbedbb05753731ee481da84347d25c34e`
- Merge base with the planning baseline:
  `b032a9f32f48889e0889fae8d6dd04eb03f46b63`
- License lineage: same MIT-licensed repository; exact provenance and current-contract
  compatibility still require independent verification before reuse.

| Prototype source | Git blob |
| --- | --- |
| `docs/architecture/ADR-019-OPEN-MEMORY-AND-OBSIDIAN-BRAIN.md` | `530f618dab653ca6143afea094273d131933ffbe` |
| `docs/architecture/PHASE3_PUBLIC_PRIVATE_MEMORY_CONTRACT.md` | `602848215e381fc8e158a79498365539c9c3b85e` |
| `src/hive_mind_os/foundation/brain.py` | `68049354f419d33e6444df77370e896cc40ee79f` |
| `src/hive_mind_os/foundation/public_memory.py` | `dcd4ec8b46fd81b758f4321f413a67c1681c70ec` |
| `src/hive_mind_os/foundation/cognitive.py` | `01bf3611b575172f60ef88e39dba609300f081f1` |
| `src/hive_mind_os/foundation/cognitive_views.py` | `50d156f20baf7a84268d20ec821d89b796a49939` |
| `src/hive_mind_os/foundation/federation.py` | `e85adae732c6b17c0a8cd09c7b201d4f8148bb5d` |
| `src/hive_mind_os/foundation/opportunities.py` | `c8d14b7ec12fa7b8fe6483722c985f5dd73dea73` |

The prototype includes useful projection, conflict, public/private separation, and
federation patterns, plus substantial tests. It also targets a divergent `foundation`
architecture. The tournament therefore treats it as an adaptation candidate, never as
code that can be copied or activated wholesale without a current-baseline court and
tests.

## External-source obligation

No new web source was needed to establish the repository-local implementation status or
to author this plan. Obsidian product behavior mentioned by the prior handoff remains an
external-source obligation until its retained official sources, versions, licenses, and
digests are reverified. No unavailable external source content is asserted here.
