# EFFECT-220

```text
Repository: `kb4beast/hive-mind-os`
Node: **EFFECT-220**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`EFFECT-220` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim EFFECT-220 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/effect-220`
from the claim commit. Do not reuse another branch.

## Objective

Make effects durable through an outbox, capability authorization, idempotent adapters, receipts, and reconciliation.

Roles: architect, builder, curator, steward
Dependencies: CONTRACT-110

## Read scope

- src/hive_mind_os/brain_kernel/effects.py
- src/hive_mind_os/brain_kernel/authority.py
- src/hive_mind_os/brain_kernel/store.py
- src/hive_mind_os/git_adapter.py
- src/hive_mind_os/github_adapter.py

## Intended write scope

- src/hive_mind_os/brain_kernel/effect_outbox.py
- src/hive_mind_os/brain_kernel/effects.py
- src/hive_mind_os/brain_kernel/store.py
- tests/test_hive_cortex_effects.py
- docs/execution/DURABLE_EFFECTS.md

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Intent is committed before execution and result receipt is append-only.
- Duplicate delivery returns the prior logical receipt or safely reconciles external state.
- Crash between external effect and receipt is detectable and repairable.
- Adapters cannot exceed the authority envelope or target scope.
- No hidden network, credential, merge, deploy, or spending authority is introduced.

## Required receipt test names

- effect-outbox-tests
- idempotency-tests
- crash-window-reconciliation-tests
- authority-denial-tests

Implement the smallest complete change. Current code overrides stale plans. Preserve
runtime behavior outside the node contract. Use deterministic tools for bookkeeping and
models only for semantic work. Keep all side effects within the sealed node authority.

Before asking a human any question, execute the role-first consultation protocol. Do not
ask the owner to solve a software defect, gather repository evidence, choose an obvious
reversible implementation detail, or adjudicate suspected cheating. Confirm cheating
with applicable roles and retained evidence. Same-model role passes are not independent
humans.

OpenAI minimum: **GPT-5.6 Sol / max**
Anthropic minimum: **Claude Fable 5 / highest available**
Why sufficient: Durable effects and authority are canonical safety-critical kernel behavior.

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
