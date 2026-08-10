# CONSULT-210

```text
Repository: `kb4beast/hive-mind-os`
Node: **CONSULT-210**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`CONSULT-210` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim CONSULT-210 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/consult-210`
from the claim commit. Do not reuse another branch.

## Objective

Implement role-first consultation and anti-cheating adjudication before any human escalation.

Roles: orchestrator, curator, architect, steward
Dependencies: CONTRACT-110

## Read scope

- src/hive_mind_os/brain_kernel/contracts.py
- src/hive_mind_os/courtroom.py
- src/hive_mind_os/roles.py

## Intended write scope

- src/hive_mind_os/brain_kernel/consultation.py
- src/hive_mind_os/schemas/hive-cortex-consultation.schema.json
- tests/test_hive_cortex_consultation.py
- docs/execution/ROLE_CONSULTATION.md

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Typed consultation requests classify ambiguity, missing evidence, authority, unsafe effect, independence, cheating, and no-progress.
- At least two applicable roles evaluate a question before human escalation.
- Consultation can resolve, remand, replan, block for evidence, quarantine, or prove genuine authority need.
- Consultation loops are bounded and preserved with dissent.
- Roles cannot fabricate credentials, consent, owner preferences, legal approval, production authority, or external facts.

## Required receipt test names

- role-first-resolution-tests
- anti-cheating-tests
- fake-human-escalation-tests
- consultation-loop-tests

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
Why sufficient: This is a core authority and anti-cheating boundary; mistakes could create fake autonomy or unsafe escalation.

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
