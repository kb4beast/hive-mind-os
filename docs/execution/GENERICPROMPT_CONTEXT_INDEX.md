# GenericPrompt Execution Context Index

The full architecture/tournament/context bundle is retained under:

`docs/plan/genericprompt-execution-2026-08-09/`

Canonical operating artifacts:

- `.autopilot/plan.json` — 39-node dependency DAG.
- `.autopilot/README.md` — controller and dispatcher contract.
- `docs/execution/VERIFIABLE_HIVE_CORTEX_DECISION.md` — adopted architecture decision.
- `docs/execution/IMPLEMENTATION_LEVELS.md` — Mermaid level graph and release gates.
- `docs/execution/NEXT_SESSION_PROMPTS.md` — exact Level 1 session prompts.
- `USER_GUIDE/02_ONE_PROMPT_FOREVER.md` — permanent dispatcher prompt.

Canonical current plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`.

The earlier `sha256:5a7cb3177a11dec9d73fd531c1549388b1f82d65f8ff71e72866a61c11fdf913`
value was a stale pre-bootstrap context-index value and is not the fingerprint enforced
by the installed `.autopilot/plan.json` and `.autopilot/control-plane.json`.

Execution workflow policy: `.autopilot/workflow-policy.json` and `docs/execution/CHATGPT_CODEX_EXECUTION_POLICY.md`. The original GenericPrompt run remains preserved unchanged in the archive directory.
Original baseline: `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23`.

The user objective, exact source prompt, reports, tournament evidence, validation logs,
and run checkpoint are preserved in the archive directory so later sessions do not have
to reconstruct intent from abbreviated handoffs.
