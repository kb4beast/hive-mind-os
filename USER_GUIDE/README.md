# Hive Mind OS user guide

Start with [Generic DAG execution](07_GENERIC_DAG_EXECUTION.md) for the installed
`hive-mind dag` commands: validate a bound plan, inspect its graph, write an inert
canonical output, and understand the available execution and recovery profiles.
Installing the package does not select a live plan or grant release authority.

The [public runtime contract](../docs/execution/PUBLIC_DAG_RUNTIME.md) describes
the service boundary and external activation obligations. The
[DAG authoring standard](../docs/execution/DAG_AUTHORING_STANDARD_V2.md) describes
plan requirements; use the exact standard bytes bound by your plan.

## Earlier guides

[Start Here](00_START_HERE.md) preserves the original bootstrap-bundle entry point.
The following pages document that historical repository control-plane workflow
and related operator practices. Their prompts and node IDs are not a new run's
plan, authority, or completion evidence.

- [Bootstrap once](01_BOOTSTRAP_ONCE.md)
- [Permanent dispatcher prompt](02_ONE_PROMPT_FOREVER.md)
- [Parallel execution](03_PARALLEL_EXECUTION.md)
- [Starting and stopping](04_WHEN_TO_START_STOP.md)
- [Receipts, repairs, and reconciliation](05_RECEIPTS_REPAIRS_RECONCILIATION.md)
- [Human escalation](06_HUMAN_ESCALATION.md)
- [Model routing](07_MODEL_ROUTING.md)
- [ChatGPT and Codex workflow](08_CHATGPT_CODEX_WORKFLOW.md)

Current-run completion must come from the exact plan and its accepted receipts.
A green code change or an old node with the same name does not complete another
run's nodes.
