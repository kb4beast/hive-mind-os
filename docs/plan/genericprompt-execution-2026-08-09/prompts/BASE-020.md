# BASE-020

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
