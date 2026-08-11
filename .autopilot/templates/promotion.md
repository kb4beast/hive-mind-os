Repository: `{{REPOSITORY}}`
Integration target: `{{TARGET_BRANCH}}`
Promotion node: **{{NODE_ID}}**
Target SHA: `{{TARGET_SHA}}`

## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **This durable primary task owns this node** through its stopping condition. Use the approved host's available reasoning, repository/GitHub tools, files, shell, and deterministic controller directly. Host choice never expands authority.

Nested agents are bounded sidecars for research, independent review, or non-blocking validation; they do not replace this primary task. If a required capability is unavailable, return an exact typed capability blocker to the parent. The parent must repair or select an approved capable host and resume this same node rather than asking the user to perform repairable work.

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
