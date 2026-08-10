# ROLE-200

```text
Repository: `kb4beast/hive-mind-os`
Node: **ROLE-200**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`ROLE-200` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim ROLE-200 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/role-200`
from the claim commit. Do not reuse another branch.

## Objective

Implement a provider-backed RoleRuntime that executes all eight real roles through bounded prompts, tools, and typed results without direct side effects.

Roles: orchestrator, architect, builder, curator
Dependencies: CONTRACT-110

## Read scope

- src/hive_mind_os/model_backend.py
- src/hive_mind_os/model_provider.py
- src/hive_mind_os/brain_kernel/**
- src/hive_mind_os/roles.py

## Intended write scope

- src/hive_mind_os/brain_kernel/role_runtime.py
- src/hive_mind_os/brain_kernel/roles.py
- tests/test_hive_cortex_role_runtime.py
- docs/execution/ROLE_RUNTIME.md

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Every role is reachable in a real mission and invokes its configured provider when cognition is required.
- Role-specific prompts, required outputs, context, tool permissions, and identity are bound to each invocation.
- No role directly writes, pushes, merges, deploys, promotes, or approves itself.
- Same-model role passes are labeled procedural separation, not independent humans.

## Required receipt test names

- all-eight-role-runtime-tests
- role-provider-routing-tests
- role-capability-denial-tests

Implement the smallest complete change. Current code overrides stale plans. Preserve
runtime behavior outside the node contract. Use deterministic tools for bookkeeping and
models only for semantic work. Keep all side effects within the sealed node authority.

Before asking a human any question, execute the role-first consultation protocol. Do not
ask the owner to solve a software defect, gather repository evidence, choose an obvious
reversible implementation detail, or adjudicate suspected cheating. Confirm cheating
with applicable roles and retained evidence. Same-model role passes are not independent
humans.

OpenAI minimum: **GPT-5.6 Sol / high**
Anthropic minimum: **Claude Opus 4.8 / high**
Why sufficient: Cross-cutting model/runtime integration is difficult but bounded by the frozen contracts.

Escalate and stop safely when:

- Current code contradicts a node assumption.
- Required changes exceed declared write scope.
- A genuine credential, consent, protected-branch, spending, legal, or production authority is required.
- Independent verification cannot be preserved.
- Three semantic attempts fail or no-progress repeats.

On escalation, preserve evidence and run `autopilot fail --kind escalation`; do not
continue with broader scope or weaker acceptance.

## Stop

Open a draft PR with a validated node receipt; do not merge or start downstream nodes.

Do not merge or auto-merge. Publish a receipt matching `.autopilot/receipt.schema.json`.

```
