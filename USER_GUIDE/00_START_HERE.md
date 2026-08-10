# Start Here

The bundle contains two different things:

1. `REPO_ROOT/` — files to install once into the real repository root on a bootstrap branch.
2. The report and prompt files — the architecture decision and operator instructions.

Do not commit the enclosing archive directory. Copy the **contents** of `REPO_ROOT/` so the
repository receives `.autopilot/`, `.github/workflows/autopilot-control-room.yml`,
`docs/execution/`, `USER_GUIDE/`, and `ORIGINAL_PLAN.md` at their real root paths.

The first action is the one-time `BOOT-000` prompt in `BOOTSTRAP_PROMPT.md`. Do not start product
nodes before that PR is merged. After it merges, use the permanent dispatcher prompt in
`USER_GUIDE/02_ONE_PROMPT_FOREVER.md`.
