Repository: `{{REPOSITORY}}`
Integration target: `{{TARGET_BRANCH}}`
Integration node: **{{NODE_ID}}**
Target SHA: `{{TARGET_SHA}}`
Execution namespace: `{{EXECUTION_NAMESPACE}}`
Repository root: `{{REPO_ROOT}}`
Execution authority: `{{EXECUTION_DIR}}`
Host runtime: `{{HOST_RUNTIME_DIR}}`
Authenticated host: `{{HOST_ID}}`
Controller prefix: `{{AUTOPILOT_PREFIX}}`

## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **This durable primary task owns this node** through its stopping condition. Use the approved host's available reasoning, repository/GitHub tools, files, shell, and deterministic controller directly. Host choice never expands authority.

The parent creates the complete visible task cohort before its first wait. Task creation
is not claim or write authority: the title and prompt state either `EXECUTION_AUTHORIZED`,
`RECOVERY_AUTHORIZED`, or `PREPARATION_ONLY`. A preparation-only task may inspect,
diagnose, and prepare a handoff but must not mutate repository or remote state.

Nested agents are bounded sidecars for research, independent review, or non-blocking validation; they do not replace this primary task. If a required capability is unavailable, return an exact typed capability blocker to the parent. The parent must repair or select an approved capable host and resume this same node rather than asking the user to perform repairable work.

If genuine human action remains, never assume prior knowledge: give exact click-by-click UI steps or copy-paste commands, what should appear, what to send back, and safety/rollback guidance.

Every final response must contain `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`; use `None.` for BLOCKS when clear.

Parallel tasks may run focused checks only. Before any repository-wide validation,
acquire the singleton lease with `validation-lease-acquire`; if another owner holds it,
stop the duplicate run, preserve it as non-verdict evidence, notify the parent, and do
not retry. Retain the returned `lease_id` and pass that exact value to
`validation-lease-release` after the one authoritative run; an owner label alone cannot
release a successor lease.

**This rendered prompt is the complete node contract.** Confirm every dependency is
COMPLETE with `{{AUTOPILOT_PREFIX}} status` — the controller
has already cryptographically validated each retained receipt, so do not re-read
`.autopilot/plan.json`, `.autopilot/README.md`, or hunt receipt commits through Git log
archaeology. Read your node runbook at `docs/execution/runbooks/{{NODE_ID}}.md` when
present. Claim the integration node remotely. Integrate only accepted immutable
candidates in the declared order. Re-run contract, compatibility, security, and
exact-candidate verification. Preserve dissent and failed integration attempts. Do not
resolve semantic conflicts by silently choosing a winner; remand or replan.

Before opening the draft PR, finalize the implementation/evidence commit, create a
receipt with exact base/final commit and tree identities, and run `autopilot complete`.
Pass the exact `claim_id` returned by this task's claim; an owner label is not a claim
fence.
The command appends a zero-path durable receipt commit with the exact final tree and
retained claim provenance; push that node branch. Completion retained only under runtime
execution state is not durable. The eventual node PR must use an ancestry-preserving
merge commit; do not squash or rebase it, because the claim, exact candidate, and receipt
commits must remain in target ancestry.

Stop at a green draft integration PR with the durable receipt commit pushed. Do not
merge.
