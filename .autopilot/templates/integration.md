Repository: `{{REPOSITORY}}`
Integration target: `{{TARGET_BRANCH}}`
Integration node: **{{NODE_ID}}**
Target SHA: `{{TARGET_SHA}}`

## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **This durable primary task owns this node** through its stopping condition. Use the approved host's available reasoning, repository/GitHub tools, files, shell, and deterministic controller directly. Host choice never expands authority.

Nested agents are bounded sidecars for research, independent review, or non-blocking validation; they do not replace this primary task. If a required capability is unavailable, return an exact typed capability blocker to the parent. The parent must repair or select an approved capable host and resume this same node rather than asking the user to perform repairable work.

If genuine human action remains, never assume prior knowledge: give exact click-by-click UI steps or copy-paste commands, what should appear, what to send back, and safety/rollback guidance.

Every final response must contain `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`; use `None.` for BLOCKS when clear.

Read `.autopilot/README.md` and every dependency receipt. Claim the integration node
remotely. Integrate only accepted immutable candidates in the declared order. Re-run
contract, compatibility, security, and exact-candidate verification. Preserve dissent
and failed integration attempts. Do not resolve semantic conflicts by silently choosing
a winner; remand or replan.

Before opening the draft PR, finalize the implementation/evidence commit, create a
receipt with exact base/final commit and tree identities, and run `autopilot complete`.
The command appends a zero-path durable receipt commit with the exact final tree and
retained claim provenance; push that node branch. Completion retained only under
`.autopilot/state/` is not durable. The eventual node PR must use an ancestry-preserving
merge commit; do not squash or rebase it, because the claim, exact candidate, and receipt
commits must remain in target ancestry.

Stop at a green draft integration PR with the durable receipt commit pushed. Do not
merge.
