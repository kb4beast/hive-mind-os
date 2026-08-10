Repository: `kb4beast/hive-mind-os`
Node: **{{NODE_ID}}**
Target SHA: `{{TARGET_SHA}}`

## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **ChatGPT Classic owns this node.** Do as much work as possible in Classic with available reasoning, GitHub/connectors, files, web, and deterministic tools. Do not use Codex because work is difficult or faster there. Exhaust Classic/tool paths and role-first consultation first.

If one remaining action truly needs a capability unavailable in Classic, emit only a **short token-aware CODEX SUBTASK** for that action (repo/node, exact base SHA if relevant, exact scope, task/commands, evidence to return, stop condition), then return the evidence to Classic and resume the node.

If genuine human action remains, never assume prior knowledge: give exact click-by-click UI steps or copy-paste commands, what should appear, what to send back, and safety/rollback guidance.

Every final response must contain `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`; use `None.` for BLOCKS when clear.

Do not implement product work. Reconstruct current branch ancestry, open/merged/closed
PRs, CI, remote branches, durable validated receipt commits, and changed planned
surfaces. Determine whether the node was completed elsewhere, partially absorbed,
invalidated, duplicated, or remains eligible. Append a reconciliation record with exact
evidence and graph-change reason. Never mark completion from prose or names alone.

## Dispatcher release barrier

While reconciliation is in progress, every worker not already validly running is `WAIT`.
Static DAG/level readiness is not execution authority. After installing the exact-current
GitHub snapshot and recording the current reconciliation event, the dispatcher must
publish an explicit release with:

```bash
python .autopilot/bin/autopilot.py --repo-root . dispatch \
  --actor <dispatcher-identity> [--node NODE ...]
```

The release assigns every candidate exactly one verdict: `START NOW`, `WAIT`, or `STOP`.
A multi-node released wave must emit `START TOGETHER NOW`. The output must also state in
plain language how many worker sessions to open, or `Do not open any worker sessions yet`.
Do not issue copy-ready worker prompts before that release exists.

A target-branch advance/merge, conflicting claim, GitHub snapshot change, or any new
reconciliation event invalidates the prior release. Re-run live reconciliation and
`dispatch`; never reuse stale release instructions.

If this reconciliation node itself reaches its completion gate, finalize its evidence
commit, create a receipt with exact base/final commit and tree identities, and run
`autopilot complete`. The command appends a zero-path durable receipt commit retaining
the exact final tree and remote-claim provenance. Push that branch. The eventual node PR
must use an ancestry-preserving merge commit; do not squash or rebase it.

Stop only after the dispatcher can safely recompute eligibility and, when releasing new
workers, can produce a current explicit release record. Completion remains durably
retained in target Git history rather than only under `.autopilot/state/`.
