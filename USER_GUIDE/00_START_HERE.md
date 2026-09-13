# Start Here

For the current installed package, use the [user guide index](README.md) and
[Generic DAG execution](07_GENERIC_DAG_EXECUTION.md). An installed checkout does
not need the archive-copy procedure below. A new objective needs its own bound
plan and evidence; these historical prompts do not activate it.

## Historical bootstrap bundle

The original bundle instructions are retained below for interpreting that
bootstrap workflow and its receipts.

The bundle contains two different things:

1. `REPO_ROOT/` — files to install once into the real repository root on a bootstrap branch.
2. The report and prompt files — the architecture decision and operator instructions.

Do not commit the enclosing archive directory. Copy the **contents** of `REPO_ROOT/` so the
repository receives `.autopilot/`, `.github/workflows/autopilot-control-room.yml`,
`docs/execution/`, `USER_GUIDE/`, and `ORIGINAL_PLAN.md` at their real root paths.

The first action is the one-time `BOOT-000` prompt in `BOOTSTRAP_PROMPT.md`. Do not start product
nodes before that PR is merged. After it merges, use the permanent dispatcher prompt in
`USER_GUIDE/02_ONE_PROMPT_FOREVER.md`.
