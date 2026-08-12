# Generic Hive Mind Product-Completion DAG

This directory contains an additive executable DAG for completing the generic
open-source Hive Mind product. It does **not** replace or edit the sealed
`.autopilot/plan.json`, and worker nodes are forbidden from modifying this DAG.

## Materialize and validate

```bash
python docs/execution/dags/generic-hive-mind-product-v1/generate_plan.py \
  --output /tmp/generic-hive-mind-product-v1.json

python .autopilot/bin/autopilot.py --repo-root . dag-lint \
  --plan /tmp/generic-hive-mind-product-v1.json --strict --json

python .autopilot/bin/autopilot.py --repo-root . dag-rounds \
  --plan /tmp/generic-hive-mind-product-v1.json \
  --max-sessions 8 --actor codex:generic-product --json
```

`generate_plan.py` is the deterministic materializer. `specs_a.py` and
`specs_b.py` are the checked-in node contracts. The materialized JSON is written
to temporary state so executing the DAG never dirties the source branch.

## Current execution boundary

The current `dispatch` command does not yet execute an external plan path.
Until `PUBLIC-RUNTIME-500` lands, the Codex parent consumes the
`dag-rounds --json` result directly, opens one worker session for each emitted
node, and integrates sealed candidates in the compiler's declared order.
After `PUBLIC-RUNTIME-500` passes its acceptance tests, the parent must switch to
the product-native public DAG commands and qualify that path instead of
continuing to emulate it in prose.

## What the overlay completes

1. accepted PR #144, `MISSION-400`, and `DURABLE-410` gates;
2. authenticated plan generations and the typed `PortablePlanBundle`;
3. standard-bound GenericPrompt DAG generation and one canonical packaged
   compiler;
4. generic subject/resource adapters and exact-tree indexing;
5. durable wave/host execution, task reuse, and token-efficient roles/context;
6. public build, validate, rounds, execute, resume, status, cancel, graph, and
   reconcile commands;
7. cross-language and non-repository fixtures;
8. failure-recovery and token-efficiency qualification; and
9. a final open-source handoff and draft PR into `main` without auto-merge.

## Non-negotiable execution rules

- PR #144 must already have been authorized, independently reviewed, and merged
  before `BASELINE-000` can pass. This overlay never merges it.
- Never edit `.autopilot/plan.json` or reinterpret its historical receipts.
- Never undo code already implemented in PR #144.
- Use one branch, worktree, claim, and immutable candidate per node.
- Workers never mutate the integration target or wait on siblings.
- Create every permitted worker in a round before polling any worker.
- Settle a mutated claim before expiry. A sealed candidate can continue through
  verification without mutable-work authority.
- Integrate in compiled node order, validate the combined candidate once, and
  advance the target once with compare-and-swap.
- No rebase, squash, amend, force-push, hidden scope widening, or auto-merge.
- Focused tests belong to workers; one complete validation belongs to the round
  integrator.
- A discovered dependency, resource conflict, missing adapter, or authority gap
  produces a retained blocker or versioned replan, never an improvised edit.
