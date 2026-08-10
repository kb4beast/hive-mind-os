# RECONCILE-250

```text
Repository: `kb4beast/hive-mind-os`
Node: **RECONCILE-250**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`RECONCILE-250` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim RECONCILE-250 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/reconcile-250`
from the claim commit. Do not reuse another branch.

## Objective

Implement a deterministic desired-state reconciler for mission recovery, retries, remands, rollback, and quarantine.

Roles: orchestrator, steward, curator
Dependencies: CONTRACT-110

## Read scope

- src/hive_mind_os/brain_kernel/projection.py
- src/hive_mind_os/brain_kernel/workers.py
- src/hive_mind_os/scheduler.py
- src/hive_mind_os/mission_store.py

## Intended write scope

- src/hive_mind_os/brain_kernel/reconciler.py
- src/hive_mind_os/brain_kernel/workers.py
- tests/test_hive_cortex_reconciler.py
- docs/execution/DESIRED_STATE_RECONCILIATION.md

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Mission desired state and observed state are deterministic projections.
- Stale leases, orphaned intents, missing workspaces, provider failure, and interrupted verification have bounded repairs.
- Repeated no-progress reaches quarantine rather than infinite looping.
- Recovery never rewrites history or widens authority.

## Required receipt test names

- reconciler-transition-tests
- stale-lease-tests
- crash-recovery-tests
- no-progress-quarantine-tests

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
Why sufficient: Recovery spans scheduling and event projections, but contracts isolate the work.

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
