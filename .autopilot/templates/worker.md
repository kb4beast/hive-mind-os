Repository: `kb4beast/hive-mind-os`
Node: **{{NODE_ID}}**
Observed state: **{{NODE_STATE}}**
Plan fingerprint: `{{PLAN_FINGERPRINT}}`
Target SHA at dispatch: `{{TARGET_SHA}}`

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

## Stop

{{STOPPING_CONDITION}}

Do not merge or auto-merge. Publish a receipt matching `.autopilot/receipt.schema.json`.
