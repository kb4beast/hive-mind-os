Repository: `kb4beast/hive-mind-os`
Promotion node: **{{NODE_ID}}**
Target SHA: `{{TARGET_SHA}}`

## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **ChatGPT Classic owns this node.** Do as much work as possible in Classic with available reasoning, GitHub/connectors, files, web, and deterministic tools. Do not use Codex because work is difficult or faster there. Exhaust Classic/tool paths and role-first consultation first.

If one remaining action truly needs a capability unavailable in Classic, emit only a **short token-aware CODEX SUBTASK** for that action (repo/node, exact base SHA if relevant, exact scope, task/commands, evidence to return, stop condition), then return the evidence to Classic and resume the node.

If genuine human action remains, never assume prior knowledge: give exact click-by-click UI steps or copy-paste commands, what should appear, what to send back, and safety/rollback guidance.

Every final response must contain `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`; use `None.` for BLOCKS when clear.

Promotion changes future behavior. Require immutable challenger identity, retained
baseline/candidate observations, repeated measurements, noise and regression guardrails,
proposer/builder/evaluator/judge separation, and an append-only court decision. Only a
KEEP verdict may atomically move the champion pointer. Preserve every losing result.
Never promote because a worker, Optimizer, or same-run evaluator recommends itself.

Before opening the draft PR, finalize the promotion/evidence commit, create a receipt
with exact base/final commit and tree identities, and run `autopilot complete`. The
command appends a zero-path durable receipt commit with the exact final tree and retained
claim provenance; push that node branch. Completion retained only under
`.autopilot/state/` is not durable. The eventual node PR must use an ancestry-preserving
merge commit; do not squash or rebase it, because the claim, exact candidate, and receipt
commits must remain in target ancestry.

Stop at the node's defined draft PR or genuine authority gate. Do not merge.
