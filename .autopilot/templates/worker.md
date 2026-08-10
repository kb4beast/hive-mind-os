Repository: `kb4beast/hive-mind-os`
Node: **{{NODE_ID}}**
Observed state: **{{NODE_STATE}}**
Plan fingerprint: `{{PLAN_FINGERPRINT}}`
Target SHA at dispatch: `{{TARGET_SHA}}`

## Mandatory execution-surface policy

Read `.autopilot/workflow-policy.json`. **ChatGPT Classic owns this node.** Do as much work as possible in Classic with available reasoning, GitHub/connectors, files, web, and deterministic tools. Do not use Codex because work is difficult or faster there. Exhaust Classic/tool paths and role-first consultation first.

If one remaining action truly needs a capability unavailable in Classic, emit only a **short token-aware CODEX SUBTASK** for that action (repo/node, exact base SHA if relevant, exact scope, task/commands, evidence to return, stop condition), then return the evidence to Classic and resume the node.

If genuine human action remains, never assume prior knowledge: give exact click-by-click UI steps or copy-paste commands, what should appear, what to send back, and safety/rollback guidance.

Every final response must contain `WHAT I DID`, `NEXT STEPS`, and `BLOCKS`; use `None.` for BLOCKS when clear.

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`{{NODE_ID}}` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim {{NODE_ID}} \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `{{BRANCH}}`
from the claim commit. Do not reuse another branch.

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
`final_tree`, then run:

```bash
python .autopilot/bin/autopilot.py --repo-root . complete {{NODE_ID}} \
  --owner <provider>:<unique-session> --receipt <receipt.json>
```

The command validates that declared changed paths equal the exact Git diff and remain
inside this node's write scope, validates the retained remote claim including its branch,
and appends a **zero-path durable receipt commit** whose tree equals `final_tree`. It
advances the local node branch to that receipt commit and prints its SHA. Push that branch
and open/update the draft PR. Do not put completion truth only under ignored
`.autopilot/state/`.

The node PR must later be integrated with an **ancestry-preserving merge commit**. Do not
squash or rebase: the retained claim, exact `final_commit`, and durable receipt commit
must remain ancestors of `main` so a completely fresh dispatcher can independently
reconstruct and validate completion. A PR title, branch name, prose status, or merge
alone never proves completion.

## Stop

{{STOPPING_CONDITION}}

Do not merge or auto-merge. Publish the durable validated receipt commit and push the
claimed node branch.
