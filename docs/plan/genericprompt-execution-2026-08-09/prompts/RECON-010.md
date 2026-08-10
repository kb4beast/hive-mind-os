# RECON-010

```text
Repository: `kb4beast/hive-mind-os`
Node: **RECON-010**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`RECON-010` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim RECON-010 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/recon-010`
from the claim commit. Do not reuse another branch.

## Objective

Reconstruct and reconcile current main, open/closed PRs, remote branches, CI, and plan-impacting unplanned work.

Roles: orchestrator, explorer, curator
Dependencies: BOOT-000

## Read scope

- **

## Intended write scope

- docs/execution/LIVE_REPOSITORY_RECONCILIATION.md
- evidence/autopilot/recon-010/**

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Exact target SHA and ancestry are recorded.
- Open PR #114 and stale codex branches receive explicit dispositions.
- No node is marked complete from names or prose alone.
- Changed planned surfaces and absorbed work are mapped to nodes.

## Required receipt test names

- live-state-reconciliation-test

Implement the smallest complete change. Current code overrides stale plans. Preserve
runtime behavior outside the node contract. Use deterministic tools for bookkeeping and
models only for semantic work. Keep all side effects within the sealed node authority.

Before asking a human any question, execute the role-first consultation protocol. Do not
ask the owner to solve a software defect, gather repository evidence, choose an obvious
reversible implementation detail, or adjudicate suspected cheating. Confirm cheating
with applicable roles and retained evidence. Same-model role passes are not independent
humans.

OpenAI minimum: **GPT-5.6 Terra / medium**
Anthropic minimum: **Claude Sonnet 5 / medium**
Why sufficient: Requires repository/GitHub synthesis but no product design.

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
