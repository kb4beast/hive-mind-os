# Next Sessions After BOOT-000 Is Merged

This handoff is bound to plan `hive-mind-os-verifiable-hive-cortex-v1` and fingerprint
`sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`. The original baseline SHA is provenance only. Each new
session must use the exact current `main` SHA emitted by the dispatcher after the
bootstrap PR merges.

The two nodes below are parallel-safe with respect to their declared write and semantic
locks. Open one fresh session per node. Each session stops at its own draft PR and
validated receipt.

# Exact First Parallel Prompts — After BOOT-000 Merges

> Run the permanent dispatcher first so current `main` is fetched and reconciled. These are the two first product-program nodes and may run concurrently only after BOOT-000 is integrated.

## Chat 1 — RECON-010

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

## Chat 2 — BASE-020

```text
Repository: `kb4beast/hive-mind-os`
Node: **BASE-020**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`BASE-020` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim BASE-020 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/base-020`
from the claim commit. Do not reuse another branch.

## Objective

Capture an exact clean baseline of tests, call paths, role wiring, provider availability, and current runtime claims.

Roles: explorer, curator, steward
Dependencies: BOOT-000

## Read scope

- src/**
- tests/**
- docs/**
- README.md
- AGENTS.md
- pyproject.toml

## Intended write scope

- docs/execution/AUTONOMY_BASELINE.md
- docs/execution/ROLE_WIRING_AUDIT.md
- evidence/autopilot/base-020/**

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Every public CLI route is traced to its actual runtime and side-effect path.
- All eight roles are classified as contract-only, model-backed, tool-backed, effect-backed, and/or fixture-only.
- Full deterministic baseline and focused role tests are retained without normalizing failures away.
- Codex subscription transport is tested or explicitly blocked with evidence.

## Required receipt test names

- full-unittest-baseline
- role-wiring-focused-tests
- provider-preflight

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
Why sufficient: Broad inspection and baseline characterization need moderate reasoning and careful evidence capture.

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

## Stop/merge rule

Each chat stops after its draft PR and receipt. Do not start `ARCH-100` until both are merged and a dispatcher confirms their receipts against current `main`.
