Repository: `kb4beast/hive-mind-os`
Integration node: **{{NODE_ID}}**
Target SHA: `{{TARGET_SHA}}`

## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **ChatGPT Classic owns this node.** Do as much work as possible in Classic with available reasoning, GitHub/connectors, files, web, and deterministic tools. Do not use Codex because work is difficult or faster there. Exhaust Classic/tool paths and role-first consultation first.

If one remaining action truly needs a capability unavailable in Classic, emit only a **short token-aware CODEX SUBTASK** for that action (repo/node, exact base SHA if relevant, exact scope, task/commands, evidence to return, stop condition), then return the evidence to Classic and resume the node.

If genuine human action remains, never assume prior knowledge: give exact click-by-click UI steps or copy-paste commands, what should appear, what to send back, and safety/rollback guidance.

Every final response must contain `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`; use `None.` for BLOCKS when clear.

Read `.autopilot/README.md` and every dependency receipt. Claim the integration node
remotely. Integrate only accepted immutable candidates in the declared order. Re-run
contract, compatibility, security, and exact-candidate verification. Preserve dissent
and failed integration attempts. Do not resolve semantic conflicts by silently choosing
a winner; remand or replan. Stop at a green draft integration PR. Do not merge.
