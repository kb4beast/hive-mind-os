# N01 independent Cross-Examination

Reviewed candidate: `eb506932e34ed631acb72b77872b72f7d2a0bfe9`
Examiner: `/root/n02_metrics`, acting only as N01 Cross-Examiner
Scope: independent worktree `C:\h\wos-n01-exam`; no builder artifact was edited.

## Method and reproduced evidence

I read the N01 contract, N00 reconciliation and Curator rereview, the five new
ADRs, PLAN, node contracts, portable plan, generation/dispatcher records, prompt,
compiler source, and focused tests. With `PYTHONPATH=C:\h\wos-n01-exam\src`,
`hive_mind_os.__file__` resolved inside this worktree and:

```text
python -m unittest tests.test_whole_os_plan_contract \
  tests.test_tournament_plan_factory tests.test_compiled_tournament -v
```

passed 19 tests. The generator was byte-stable when run with that same bound
environment; `git diff --check` was clean afterwards.

## Atomic findings

### CE-01 — generator provenance is caller-dependent (ADAPT)

`scripts/generate_whole_os_plan_artifacts.py` imports package modules before it
establishes that they resolve under its own repository root. Invoked without a
worktree-bound `PYTHONPATH`, the independent probe imported
`tournament_plan_factory` from another worktree and failed because that installed
version lacked `WholeOSPlanFactory`. The N01 documentation tells test shells to bind
`PYTHONPATH`, but the permanent regeneration command is itself a supply-chain and
reproducibility boundary and must reject foreign import provenance before reading or
writing artifacts. Repair: put this repository's `src` first in `sys.path`, then
assert every N01 compiler module resolves under `ROOT / "src"`; add a subprocess
negative test with a foreign package path. This is a local software repair, not an
authority grant.

### CE-02 — worker prompt interpolation needs a typed renderer (ADAPT)

`NODE_PROMPT.md` is correctly inert and states that it grants no authority, but it
asks a dispatcher to substitute untyped values into prose placeholders, including
receipt references, paths, locks and source IDs. No escaping, identifier validation,
path normalization, length cap, or renderer receipt is specified at this boundary.
An untrusted receipt title/path can therefore alter worker-visible instructions even
though the canonical JSON contract remains sound. Repair: N08/N09's dispatcher
should render a structured, canonical payload (or validate/quote each field), bind
its digest to the node admission record, and reject text that is not an exact
compiled contract value. Do not make the Markdown template executable.

### CE-03 — accepted N00 custody is correctly preserved (ADOPT)

The checked source-inventory SHA-256 reproduces the N00 Curator's sealed
`39109a…d127`. The generator's different generation-manifest field is a digest of
the pinned artifact representation, not evidence of a modified inventory. No source
is newly described as archived/ingested and open obligations remain visible.

### CE-04 — compilation/authority and compatibility controls reproduce (ADOPT)

The focused suite rejects missing role/output, cycles, lost requirements, standard
mutation, unknown routes, copied signatures and unauthorized effects. It confirms
all 34 N00–N33 contracts, semantic/write-lock rounds, v1 13-stage profile survival,
inert dispatcher/generation properties, and deterministic regeneration under the
admitted import environment. The plan's authority profile explicitly denies push,
merge, deployment, credential, payment and signing; no activation path was found in
the generator.

### CE-05 — no measured or production claim is supported (DEFER)

The ADRs and PLAN accurately retain source archives, comparator rights, external
campaign root, Roblox subject/runtime, delivery grant and legacy dispatch as open
obligations. They propose architecture only and preserve failure/dissent. N01 cannot
close runtime, delivery, learning, Roblox, benchmark or superiority claims; later
nodes need independent evidence and a Judge distinct from this Examiner.

## Recommendation

**ADAPT.** The candidate is a credible inactive, lock-aware compilation with
preserved N00 custody and compatibility, but CE-01 is a material reproducibility
failure and CE-02 leaves an instruction-injection/boundary gap. Repair both before a
Judge considers N01 adoption. This document is cross-examination evidence only; it
does not approve the candidate, activate a plan, or authorize any effect.
