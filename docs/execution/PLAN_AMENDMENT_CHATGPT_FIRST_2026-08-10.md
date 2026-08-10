# Plan Amendment — ChatGPT Classic First Workflow

Date: 2026-08-10

The original GenericPrompt tournament and its canonical 39-node dependency DAG are unchanged. This amendment adds a **mandatory execution workflow that applies across all nodes** without changing node dependencies or acceptance criteria.

The workflow is encoded in `.autopilot/workflow-policy.json`, referenced by `.autopilot/control-plane.json`, surfaced by `.autopilot/model-routing.json`, and embedded in every worker/integration/promotion/reconciliation/repair/replan prompt template.

Requirements:

1. ChatGPT Classic is the default node owner and performs as much work as its tools allow.
2. Classic exhausts repository evidence, available tools, bounded self-resolution, alternate supported paths, and role-first consultation before Codex.
3. Codex is a last-resort, smallest-possible subtask executor for a proven unavailable Classic execution capability; Classic resumes after evidence returns.
4. Human action is genuine-authority/access only, with novice-safe exact instructions.
5. Every session response contains `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`.

The original plan fingerprint remains unchanged because this is an execution-policy overlay, not a mutation of node contracts/dependencies.
