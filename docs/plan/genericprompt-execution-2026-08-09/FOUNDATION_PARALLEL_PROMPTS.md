# First Major Parallel Implementation Wave — After CONTRACT-110

Start these seven chats only when BOOT-000, RECON-010, BASE-020, ARCH-100, and CONTRACT-110 are merged and validated.

## Chat 1 — ROLE-200

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

## Chat 2 — CONSULT-210

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

## Chat 3 — EFFECT-220

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

## Chat 4 — CONTEXT-230

```text
Repository: `kb4beast/hive-mind-os`
Node: **CONTEXT-230**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`CONTEXT-230` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim CONTEXT-230 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/context-230`
from the claim commit. Do not reuse another branch.

## Objective

Compile bounded, role-specific, provenance-aware memory contexts from immutable mission evidence.

Roles: explorer, architect, curator, optimizer
Dependencies: CONTRACT-110

## Read scope

- src/hive_mind_os/brain_kernel/memory.py
- src/hive_mind_os/brain_kernel/context.py
- src/hive_mind_os/repository_learning.py

## Intended write scope

- src/hive_mind_os/brain_kernel/context.py
- src/hive_mind_os/brain_kernel/memory.py
- tests/test_hive_cortex_context.py
- docs/execution/MEMORY_CONTEXT.md

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Context manifests bind source records, provenance, sensitivity, freshness, role, mission, work, and authority.
- Curator receives evaluator-isolated context and no Builder scratchpad.
- Future commits and protected holdouts remain unavailable until the appropriate seal.
- Untrusted repository text remains data rather than instruction.
- Memory expiry, correction, contradiction, and quarantine are append-only.

## Required receipt test names

- context-manifest-tests
- future-leakage-tests
- sensitivity-scope-tests
- memory-poisoning-fixtures

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
Why sufficient: Memory/context is broad and security-sensitive but isolated behind existing kernel stores.

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

## Chat 5 — ACCEPT-240

```text
Repository: `kb4beast/hive-mind-os`
Node: **ACCEPT-240**
Observed state: **READY**
Plan fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
Target SHA at dispatch: **use the exact current reconciled `main` SHA emitted by the dispatcher; `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` is the original program baseline only. Stop if the controller reports a different unreconciled target.**

Use a fresh, clean checkout with authenticated GitHub access. Read every applicable
`AGENTS.md` and `CLAUDE.md`, then read `.autopilot/README.md` and the full contract for
`ACCEPT-240` in `.autopilot/plan.json`.

Run:

```bash
python .autopilot/bin/autopilot.py --repo-root . doctor --skip-controller-tests
python .autopilot/bin/autopilot.py --repo-root . claim ACCEPT-240 \
  --owner <provider>:<unique-session> --publish-remote
```

The remote claim must succeed before product work begins. Create/switch to `autopilot/accept-240`
from the claim commit. Do not reuse another branch.

## Objective

Create the adversarial acceptance harness for all-role, humanless, no-cheating, learning, self-healing, and repository-safety proof.

Roles: curator, steward, optimizer
Dependencies: CONTRACT-110

## Read scope

- tests/**
- src/hive_mind_os/schemas/**
- docs/execution/AUTONOMY_ACCEPTANCE.md

## Intended write scope

- tests/hive_cortex/**
- tests/fixtures/hive_cortex/**
- docs/execution/AUTONOMY_ACCEPTANCE.md

## Forbidden scope

- .github/CODEOWNERS
- .github/governance/**
- evidence/courts/**
- docs/architecture/HARDENED_VISION_CONTRACT.md

## Acceptance

- Harness contains hidden-defect, misleading-README, no-test, monorepo, Python, Node, and C# fixtures.
- Tests fail against missing role wiring, fake consultation, self-approval, and future leakage.
- Humanless scenarios distinguish genuine authority blockers from software defects.
- Receipts prove exact candidate and role/effect sequence.

## Required receipt test names

- acceptance-harness-self-tests
- negative-control-tests
- cross-language-fixture-tests

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
Why sufficient: A broad adversarial harness requires substantial test design but can remain independent of runtime implementation.

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

## Chat 6 — RECONCILE-250

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

## Chat 7 — MIGRATE-260

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

