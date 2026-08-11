# Durable primary tasks across ChatGPT and Codex

This policy applies to every Autopilot node.

- **Primary owner:** the approved durable task that receives the current released node.
- **Codex primary tasks:** use `create_thread`, retain thread/host IDs, poll with
  `wait_threads`, and send recovery with `send_message_to_thread`.
- **Nested agents:** bounded research, independent review, or non-blocking validation
  only. They cannot replace a primary node task.
- **Capability gaps:** return an exact typed blocker to the parent. The parent repairs the
  workflow or selects an approved capable host and resumes the same node.
- **Human help:** only genuine authority/access after self-resolution and role
  consultation. Give exact steps, expected result, return evidence, and rollback.
- **Every response:** `WHAT I DID`, `NEXT STEPS`, `BLOCKS`; use `None.` when clear.

Machine-readable sources: `.autopilot/workflow-policy.json` and
`.autopilot/orchestration-policy.json`.
