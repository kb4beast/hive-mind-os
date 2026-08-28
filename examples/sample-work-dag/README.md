# A sample Orchestrator work DAG

This example builds one nine-node work graph with the real kernel planner and prints
everything the planner derives from it: topological order, the ready waves, the canonical
digests, and the message the validator returns for each malformed variant.

Nothing here is asserted by hand. If a rule in
[`objectives.py`](../../src/hive_mind_os/brain_kernel/objectives.py) or
[`planner.py`](../../src/hive_mind_os/brain_kernel/planner.py) changes, this example's
output changes with it.

## Run it

```bash
python examples/sample-work-dag/build_sample_dag.py
```

To also write the canonical plan document:

```bash
python examples/sample-work-dag/build_sample_dag.py --json sample-work-dag.json
```

## The mission

The charter asks for a repository change that cuts p95 checkout latency below 400 ms
without altering the public API, under two acceptance specifications and one chartered
human gate for the schema migration.

Seven of the eight specialist roles appear in the graph:

| Wave | Work | Role | Risk lane |
|---|---|---|---|
| 1 | `WORK-010-profile`, `WORK-011-survey` | explorer | R0 |
| 2 | `WORK-020-design` | architect | R1 |
| 3 | `WORK-030-cache`, `WORK-031-index` | builder | R2, R3 |
| 4 | `WORK-040-contract`, `WORK-050-health` | integrator, steward | R1 |
| 5 | `WORK-060-verify` | curator | R2 |
| 6 | `WORK-000-root` | orchestrator | R0 |

Waves are not authored. They are the successive answers to
`ObjectiveGraph.ready_items(completed)` — every proposed node whose declared dependencies
have completed. The root sits in the last wave because it depends on its children: a
parent cannot report done before the work beneath it is accepted.

The two Builder nodes run in the same wave because their write scopes do not overlap.
Had both declared `src/checkout/cache.py`, the graph would have been rejected at plan
time rather than allowed to race.

## What the validator refuses

The script submits eight malformed variants and prints the validator's own message for
each, including a cycle, a self-dependency, a depth mismatch, an uncovered charter
acceptance specification, a ninth child under one parent, and two kinds of overlapping
write scope. It also shows the same overlapping pair being accepted once the dependency
edge is restored.

Schedule budgets are checked as a sum: if the per-node budgets add up past the mission
charter's budget, the plan is rejected before any node runs.

## Files

| Path | What it is |
|---|---|
| `build_sample_dag.py` | Builds, validates, and prints the graph |
| `sample-work-dag.json` | The canonical plan document the script writes |
