# N01 independent Cross-Examiner rereview

Reviewed repair candidate: `1f7557f2c91fbaadba67387275390e33dfa9d262`  
Reviewed tree: `1a624333951e2abd6a5a49b26a124e5f3e55a706`  
Examiner: `/root/n02_metrics`, distinct from the N01 Architect/Builder  
Worktree: `C:\h\wos-n01-exam-r2`

This is an append-only rereview of CE-01 and CE-02 from
`N01_EXAMINER_REVIEW.md`; it neither approves the candidate nor serves as the
required N01 Judge disposition.

## Reproduction

With `PYTHONPATH=C:\h\wos-n01-exam-r2\src`, `hive_mind_os.__file__` resolved
inside this exact worktree. I ran:

```text
python -m unittest tests.test_node_prompt_renderer \
  tests.test_whole_os_plan_contract tests.test_tournament_plan_factory \
  tests.test_compiled_tournament -v
```

All 23 tests passed. I then removed `PYTHONPATH` and ran the generator directly;
it completed deterministically without a diff. `git diff --check` was clean.

## Replayed attacks

### CE-01: import provenance and write-before-provenance — closed

The generator now resolves its own `src` root, puts it first, and checks the
origin of every compiler module before importing it. The dedicated subprocess test
preloads a foreign package and verifies rejection before writes. Direct no-
`PYTHONPATH` regeneration uses the candidate's local compiler, rather than the
foreign-worktree import observed in the prior review. The compiler bundle and
dispatcher now bind generator/renderer bytes, so the generation record covers the
new boundary implementation.

### CE-02: prompt interpolation and instruction injection — closed

The Markdown is now explanatory-only. The renderer accepts a closed canonical JSON
request containing only schema version, sealed plan digest, node ID and ordered
direct prerequisite receipt references. Tests reject unknown fields, duplicate keys,
noncanonical JSON, control characters, substituted plan/node values, bad paths and
non-direct dependencies. Rendered output separates fixed instructions from data and
binds renderer, plan, request and node-contract digests; untrusted instruction-like
strings remain JSON data. The dispatcher requires this structured renderer.

## Regression checks

The 34-node contract compilation, lock-aware rounds, inactive generation/dispatcher,
N00 source custody, authority denials, deterministic regeneration, and v1 13-stage
compatibility all still pass. No generator action activates, signs, publishes, or
grants authority. No production, benchmark, delivery, Roblox, learning or
superiority conclusion is supported by this review.

## Recommendation

**ADOPT (Cross-Examiner recommendation only).** CE-01 and CE-02 reproduce as
closed on this exact candidate, with no observed regression in the focused N01
contract/compatibility boundary. An independent expert witness and Judge remain
required; this recommendation is not self-approval or an N01 completion verdict.
