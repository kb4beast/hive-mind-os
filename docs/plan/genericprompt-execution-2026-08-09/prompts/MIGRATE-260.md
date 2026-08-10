# MIGRATE-260

```text
Repository: `kb4beast/hive-mind-os`
Node: **MIGRATE-260**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`MIGRATE-260` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim MIGRATE-260 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/migrate-260`
from the claim commit. Do not reuse another branch.

## Objective

Build additive compatibility adapters and parity probes for RepositoryMission, MissionLoop, AutonomousBrain, and legacy workers.

Roles: architect, integrator, curator
Dependencies: CONTRACT-110

## Read scope

- src/hive_mind_os/mission.py
- src/hive_mind_os/mission_loop.py
- src/hive_mind_os/autonomous_os.py
- src/hive_mind_os/workers.py
- src/hive_mind_os/brain_kernel/**

## Intended write scope

- src/hive_mind_os/cortex/compatibility/**
- tests/test_hive_cortex_compatibility.py
- docs/execution/RUNTIME_COMPATIBILITY.md

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Each legacy entry point has a typed adapter or explicit retirement blocker.
- Parity probes compare behavior and evidence without dual authoritative writes.
- Rollback can route back to the prior path until canonical qualification.
- No old path is declared retired before accepted parity evidence.

## Required receipt test names

- compatibility-adapter-tests
- no-dual-write-tests
- rollback-routing-tests

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
Why sufficient: Multi-runtime compatibility is broad and conflict-prone but separable from canonical implementation.

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
