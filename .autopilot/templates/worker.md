Repository: `{{REPOSITORY}}`
Integration target: `{{TARGET_BRANCH}}`
Node: **{{NODE_ID}}**
Observed state: **{{NODE_STATE}}**
Plan fingerprint: `{{PLAN_FINGERPRINT}}`
Target SHA at dispatch: `{{TARGET_SHA}}`
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
use the dispatcher-injected hosted authority envelope to acquire the singleton lease
with `validation-lease-acquire`; if another owner holds it,
stop the duplicate run, preserve it as non-verdict evidence, notify the parent, and do
not retry. Retain the returned `lease_id`, keep the exact claim/launch fence alive with
the injected renewal command, and pass the same fences to `validation-lease-release`
after the one authoritative run. An owner label alone cannot renew or release a lease.

## Dispatcher release barrier

`{{NODE_STATE}}`, DAG membership, level membership, and dependency readiness are eligibility signals only. They do **not** authorize execution. This worker may claim or implement `{{NODE_ID}}` only when the latest dispatcher release is current and the rendered prompt begins with `DISPATCH VERDICT FOR {{NODE_ID}}: START NOW`. Otherwise the verdict is `WAIT` or `STOP` and this worker must not begin.

For a parallel wave, all released workers may begin claims and writes together only when the same current dispatcher release says `START TOGETHER NOW` and names the wave. Other eligible tasks may already be visible in `PREPARATION_ONLY` mode. Any target-branch advance/merge, conflicting claim, GitHub snapshot change, or reconciliation event makes the prior release stale. Re-run the dispatcher instead of reusing an old prompt. The `claim` command independently enforces this gate and fails closed on stale or absent release authority.

Use a fresh, clean checkout with authenticated GitHub access. **This rendered prompt is
the complete node contract**: the objective, scopes, acceptance, tests, escalation, and
routes below are generated from `.autopilot/plan.json` and are authoritative. Do not
re-read `plan.json`, `.autopilot/README.md`, or the policy files — every gate they
describe is enforced deterministically by the controller commands below, which fail
closed. Read only: the root `AGENTS.md`, your node runbook at
`docs/execution/runbooks/{{NODE_ID}}.md` (when present — it carries the file-by-file
implementation plan and validation commands), and files inside your read scope.

## Parallel-wave safety rules

- Work only on `{{BRANCH}}`, created from your claim commit. Never commit to, push, or
  merge `{{TARGET_BRANCH}}` — a single integrator merges finished node branches in a
  deterministic order after the wave.
- Never rebase, squash, or amend your node branch: the retained claim commit, exact
  `final_commit`, and receipt commit must stay in its ancestry.
- If `{{TARGET_BRANCH}}` advances while you work, stop new writes and all
  controller-mediated completion or publication. Preserve the node branch exactly,
  report the stale-target authority, and wait for authenticated reconciliation plus a
  fresh dispatcher release. Do not merge the new target into your branch or assume the
  old claim remains valid.
- Never wait on a sibling node's output. Waves are dependency-satisfied and
  conflict-free by construction; if you discover a real dependency on a sibling,
  stop and record a blocker with `autopilot fail` instead of polling.

Run:

```bash
{{AUTOPILOT_PREFIX}} doctor --skip-controller-tests
{{AUTOPILOT_PREFIX}} status
{{AUTOPILOT_PREFIX}} ready
```

`ready` returns only nodes with a current explicit dispatcher release, not merely static
DAG eligibility. The host must append a dispatcher-injected authority envelope containing
the exact shared `--state-dir`, launch instruction, resource key, and epoch. If that
envelope or its Claim command is absent, stop: this base template deliberately cannot
manufacture authority. The remote claim must succeed before product work begins.
Create/switch to `{{BRANCH}}` from the claim commit. Do not reuse another branch.
Preserve the returned JSON `claim_id`; every heartbeat, failure, release, and completion
must present that exact fence. Reusing only the owner label cannot mutate a replacement
claim.

## Objective

{{OBJECTIVE}}

Roles: {{ROLES}}
Dependencies: {{DEPENDENCIES}}

## Read scope

{{READ_SCOPE}}

## Intended write scope

{{WRITE_SCOPE}}

## Forbidden scope

{{FORBIDDEN_SCOPE}}

## Acceptance

{{ACCEPTANCE}}

## Required receipt test names

{{TESTS}}

Implement the smallest complete change. Current code overrides stale plans. Preserve
runtime behavior outside the node contract. Use deterministic tools for bookkeeping and
models only for semantic work. Keep all side effects within the sealed node authority.

Before asking a human any question, execute the role-first consultation protocol. Do not
ask the owner to solve a software defect, gather repository evidence, choose an obvious
reversible implementation detail, or adjudicate suspected cheating. Confirm cheating
with applicable roles and retained evidence. Same-model role passes are not independent
humans.

OpenAI minimum: **{{OPENAI_ROUTE}}**
Anthropic minimum: **{{ANTHROPIC_ROUTE}}**
Why sufficient: {{ROUTE_RATIONALE}}

Escalate and stop safely when:

{{ESCALATION}}

On escalation, preserve evidence and run `autopilot fail --kind escalation`; do not
continue with broader scope or weaker acceptance.

## Durable completion publication

Completion must survive a fresh checkout without expanding file authority. After the
implementation/evidence commit is final, record its exact base/final commits and trees
in a receipt matching `.autopilot/receipt.schema.json`, including `base_tree` and
`final_tree`, then run the dispatcher-injected Complete command from the hosted authority
envelope. It supplies the exact state directory and launch/resource/epoch tuple; substitute
only the stable owner, returned claim ID, and receipt path. If the envelope is absent or
its launch fence no longer validates, do not publish completion.

The command validates that declared changed paths equal the exact Git diff and remain
inside this node's effective write scope, validates the retained remote claim including its branch,
and appends a **zero-path durable receipt commit** whose tree equals `final_tree`. It
advances the local node branch to that receipt commit and prints its SHA. Push that branch
and open/update the draft PR. Do not put completion truth only under ignored runtime
execution state.

The node PR must later be integrated with an **ancestry-preserving merge commit**. Do not
squash or rebase: the retained claim, exact `final_commit`, and durable receipt commit
must remain ancestors of `{{TARGET_BRANCH}}` so a completely fresh dispatcher can independently
reconstruct and validate completion. A PR title, branch name, prose status, or merge
alone never proves completion.

## Stop

{{STOPPING_CONDITION}}

Do not merge or auto-merge. Publish the durable validated receipt commit and push the
claimed node branch.
