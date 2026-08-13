# Knowledge Projection DAG v1

This additive executable DAG implements the tournament decision recorded in
`docs/plan/knowledge-projection-tournament-2026-08-13/`.

It plans a bounded sequence:

1. close authority and learning-intake prerequisites;
2. establish stable identities, immutable idea passes, complete role/court coverage,
   classification, projection, and release contracts;
3. build one canonical protected knowledge store and a one-shot private
   Obsidian-compatible projector;
4. qualify an offline safe-learning release gate and local sanitized registry;
5. add read-only prior-art, federation guards, migration, dashboards, and exact-candidate
   qualification; and
6. end with an independent local-release court and honest handoff.

The plan does **not** authorize remote/public registry writes, a persistent watcher,
bidirectional Obsidian intake, or automatic shared-lesson-to-challenger activation.
Those remain quarantined or deferred.

## Verify, materialize, lint, and compile

```bash
python docs/execution/dags/knowledge-projection-v1/verify_plan.py --write

python .autopilot/bin/autopilot.py --repo-root . dag-lint \
  --plan .autopilot/state/knowledge-projection-v1.json --strict --json

python .autopilot/bin/autopilot.py --repo-root . dag-rounds \
  --plan .autopilot/state/knowledge-projection-v1.json \
  --max-sessions 8 --actor codex:knowledge-projection --json
```

The materialized JSON is ignored under `.autopilot/state/`. The checked-in source is
`specs.py`; `generate_plan.py` deterministically adds standard fields and digests;
`verify_plan.py` seals source blobs, the complete tournament/decision/plan bundle, node
order, plan digest, authoring-standard bytes, and the unchanged historical
`.autopilot/plan.json` bytes.

## Runtime loop versus execution DAG

An idea may return through discovery, court, design, build, verification, delivery, or
learning any number of times. Each return creates a later immutable `IdeaPass`, remand,
re-entry, or work-attempt record. It never mutates an earlier pass or creates a cycle in
this executable dependency graph.
