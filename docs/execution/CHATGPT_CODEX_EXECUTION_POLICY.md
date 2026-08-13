# Host-neutral durable task execution policy

The historical ChatGPT-Classic-first policy is preserved in Git history and its sealed
amendment record. ADR-057 adapts current execution to capability-matched durable primary
tasks so the controller works consistently across ChatGPT, Codex, and future hosts.

The released node's durable primary task owns execution through its stopping condition.
Host choice does not expand authority. On Codex, the parent creates primary tasks with
`create_thread`, polls with `wait_threads`, and sends recovery with
`send_message_to_thread`. Nested multi-agent workers are sidecars only.

A missing capability becomes a typed parent recovery input. The parent must repair the
workflow or select an approved capable host and resume the same task. It may ask the user
only for genuine authority or access, with exact novice-safe instructions and rollback.

Machine-readable policy is in `.autopilot/workflow-policy.json`; orchestration behavior
is in `.autopilot/orchestration-policy.json`.
