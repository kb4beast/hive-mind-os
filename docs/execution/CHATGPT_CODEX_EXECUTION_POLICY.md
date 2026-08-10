# ChatGPT Classic First / Codex Last-Resort Workflow

This policy applies to **every node** in the Verifiable Hive Cortex plan.

- **Default owner:** ChatGPT Classic. Do all work Classic and its available tools/connectors can safely perform. Difficulty or convenience is not a reason to delegate.
- **Before Codex:** inspect current truth, try available tools, attempt bounded self-resolution, try alternate supported paths, and use role-first consultation.
- **Codex:** only the smallest remaining subtask requiring a capability unavailable in Classic, such as local shell/test/build/benchmark execution. The prompt must be short and scoped. Classic reviews the returned evidence and resumes ownership.
- **Human help:** only genuine authority/access after self-resolution. Never assume manual knowledge; provide click-by-click or copy-paste instructions, expected result, what to send back, and safety/rollback guidance.
- **Every response:** `WHAT I DID`, `NEXT STEPS`, `BLOCKS`. A BLOCKS entry must say what was tried and why it remains blocked. If none, write `None.`

Machine-readable source: `.autopilot/workflow-policy.json`.
