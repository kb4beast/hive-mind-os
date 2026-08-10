# Executable Implementation Program

## Program identity

- Plan: `hive-mind-os-verifiable-hive-cortex-v1`
- Fingerprint: `sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39`
- Baseline: `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23` / `ac76686aa004cf8188f0281b1ec9ac1f5c666929`
- Nodes: 39
- Dependency levels: 16
- Longest dependency chain: 16 nodes

## Dependency waves

| Level | Mode | Nodes | Route tiers |
|---:|---|---|---|
| 0 | serial/gated | BOOT-000 | T2 |
| 1 | parallel | RECON-010, BASE-020 | T2 |
| 2 | serial/gated | ARCH-100 | T4 |
| 3 | serial/gated | CONTRACT-110 | T4 |
| 4 | parallel | ROLE-200, CONSULT-210, EFFECT-220, CONTEXT-230, ACCEPT-240, RECONCILE-250, MIGRATE-260 | T3, T4 |
| 5 | parallel | ORCH-300, EXPLORER-310, ARCHITECT-320, BUILDER-330, CURATOR-340, INTEGRATOR-350, STEWARD-360, OPTIMIZER-370, COURT-380 | T2, T3, T4 |
| 6 | serial/gated | MISSION-400 | T4 |
| 7 | parallel | DURABLE-410, DELIVERY-420, HUMANLESS-430, CHEAT-440, LEARN-500 | T3, T4 |
| 8 | serial/gated | SELFHEAL-450, MIGRATION-460, CHALLENGER-510, POISON-540 | T3, T4 |
| 9 | serial/gated | EVAL-520 | T4 |
| 10 | serial/gated | PROMOTE-530, BENCH-600 | T3, T4 |
| 11 | serial/gated | QUALIFY-610 | T4 |
| 12 | serial/gated | LEGACY-620 | T4 |
| 13 | serial/gated | A3-700 | T4 |
| 14 | serial/gated | A4-800 | T4 |
| 15 | serial/gated | A5-900 | T4 |

## Complete node contract index

| Node | Dependencies | Route | Objective |
|---|---|---|---|
| BOOT-000 | none | T2 | Install the repository-resident implementation control plane at its real root paths and prove it deterministically. |
| RECON-010 | BOOT-000 | T2 | Reconstruct and reconcile current main, open/closed PRs, remote branches, CI, and plan-impacting unplanned work. |
| BASE-020 | BOOT-000 | T2 | Capture an exact clean baseline of tests, call paths, role wiring, provider availability, and current runtime claims. |
| ARCH-100 | RECON-010, BASE-020 | T4 | Adopt one canonical Verifiable Hive Cortex architecture and a reversible migration from competing runtime brains. |
| CONTRACT-110 | ARCH-100 | T4 | Freeze the canonical mission, role invocation/result, consultation, effect intent/receipt, outcome, and promotion contracts. |
| ROLE-200 | CONTRACT-110 | T3 | Implement a provider-backed RoleRuntime that executes all eight real roles through bounded prompts, tools, and typed results without direct side effects. |
| CONSULT-210 | CONTRACT-110 | T4 | Implement role-first consultation and anti-cheating adjudication before any human escalation. |
| EFFECT-220 | CONTRACT-110 | T4 | Make effects durable through an outbox, capability authorization, idempotent adapters, receipts, and reconciliation. |
| CONTEXT-230 | CONTRACT-110 | T3 | Compile bounded, role-specific, provenance-aware memory contexts from immutable mission evidence. |
| ACCEPT-240 | CONTRACT-110 | T3 | Create the adversarial acceptance harness for all-role, humanless, no-cheating, learning, self-healing, and repository-safety proof. |
| RECONCILE-250 | CONTRACT-110 | T3 | Implement a deterministic desired-state reconciler for mission recovery, retries, remands, rollback, and quarantine. |
| MIGRATE-260 | CONTRACT-110 | T3 | Build additive compatibility adapters and parity probes for RepositoryMission, MissionLoop, AutonomousBrain, and legacy workers. |
| ORCH-300 | ROLE-200, CONSULT-210, RECONCILE-250 | T3 | Make Orchestrator build and continuously revise a dependency DAG with budgets, risk lanes, stop conditions, and consultation scheduling. |
| EXPLORER-310 | ROLE-200, CONTEXT-230, EFFECT-220 | T2 | Give Explorer real read-only repository, history, test-discovery, and governed source-intake capabilities. |
| ARCHITECT-320 | ROLE-200, CONTEXT-230 | T2 | Make Architect compare alternatives and produce threat, interface, migration, rollback, and acceptance mappings. |
| BUILDER-330 | ROLE-200, EFFECT-220, CONTEXT-230 | T3 | Make Builder iteratively request isolated writes, commands, branches, and commits through the durable effect path. |
| CURATOR-340 | ROLE-200, ACCEPT-240, CONTEXT-230 | T4 | Make Curator independently reconstruct and verify exact immutable candidates, remanding defects without Builder context leakage. |
| INTEGRATOR-350 | ROLE-200, EFFECT-220, MIGRATE-260 | T3 | Make Integrator validate versioned contracts, data lineage, adapters, and cross-runtime compatibility, requesting Builder repairs rather than patching. |
| STEWARD-360 | ROLE-200, RECONCILE-250, EFFECT-220 | T3 | Make Steward continuously assess operational health, recovery, dependencies, observability, and evidence integrity. |
| OPTIMIZER-370 | ROLE-200, CONTEXT-230, ACCEPT-240 | T3 | Make Optimizer attribute outcomes, generate scoped lessons and challengers, and recommend—but never perform—promotion. |
| COURT-380 | ROLE-200, CONSULT-210, ACCEPT-240 | T4 | Operationalize temporary Advocate, Cross-Examiner, Expert, Judge, and Appeals identities over role results and consultations. |
| MISSION-400 | ORCH-300, EXPLORER-310, ARCHITECT-320, BUILDER-330, CURATOR-340, INTEGRATOR-350, STEWARD-360, OPTIMIZER-370, COURT-380, EFFECT-220, CONTEXT-230, RECONCILE-250 | T4 | Wire one canonical end-to-end mission runner through all eight roles, consultation, durable effects, exact verification, and acceptance. |
| DURABLE-410 | MISSION-400 | T3 | Prove restart, resume, lease, crash consistency, and event replay for the canonical mission runtime. |
| DELIVERY-420 | MISSION-400, EFFECT-220 | T4 | Connect controlled non-protected push, draft PR, and comment adapters to the canonical effect path without adding merge authority. |
| HUMANLESS-430 | MISSION-400, CONSULT-210, ACCEPT-240 | T4 | Prove role-first end-to-end resolution across ambiguity, missing tests, design tradeoffs, CI repair, and recoverable failures. |
| CHEAT-440 | MISSION-400, CONSULT-210, ACCEPT-240, CURATOR-340, COURT-380 | T4 | Prove cheating detection and independent challenge against test weakening, evaluator leakage, future access, stale evidence, fake receipts, authority expansion, and friendly consultation. |
| SELFHEAL-450 | DURABLE-410, STEWARD-360, RECONCILE-250, EFFECT-220 | T4 | Integrate provider failover, bounded retry, remand, rollback, workspace rebuild, stale lease repair, and quarantine into mission reconciliation. |
| MIGRATION-460 | MISSION-400, MIGRATE-260, DURABLE-410 | T4 | Route public CLI and scheduler ingress to the canonical mission runtime behind compatibility switches. |
| LEARN-500 | MISSION-400, OPTIMIZER-370, CONTEXT-230 | T3 | Generate scoped, evidence-bound lessons from outcomes, incidents, remands, repairs, and human corrections. |
| CHALLENGER-510 | LEARN-500 | T3 | Generate immutable prompt, planner, policy-rule, retrieval, or tool-selection challengers from accepted lessons. |
| EVAL-520 | CHALLENGER-510, CURATOR-340, ACCEPT-240 | T4 | Evaluate challengers on held-out, PIT, adversarial, and comparator surfaces with independent evaluators. |
| PROMOTE-530 | EVAL-520, COURT-380, EFFECT-220 | T4 | Authorize atomic champion promotion or rollback only through an independent append-only court decision. |
| POISON-540 | LEARN-500, CHEAT-440 | T3 | Test and harden memory, lesson, and challenger paths against poisoning, stale evidence, provenance gaps, and overgeneralization. |
| BENCH-600 | HUMANLESS-430, CHEAT-440, SELFHEAL-450, EVAL-520 | T3 | Create a reproducible multi-scenario autonomy benchmark and comparator court without unsupported superiority claims. |
| QUALIFY-610 | MIGRATION-460, PROMOTE-530, POISON-540, BENCH-600, DELIVERY-420 | T4 | Run the complete local governed-autonomy qualification and issue an honest maturity verdict. |
| LEGACY-620 | QUALIFY-610 | T4 | Retire independent legacy brain ownership only after accepted parity and rollback evidence. |
| A3-700 | QUALIFY-610, LEGACY-620 | T4 | Qualify A3 repository autonomy on real disposable repositories without remote delivery authority. |
| A4-800 | A3-700, DELIVERY-420 | T4 | Run a bounded governed remote-delivery pilot with explicit owner credentials and grants. |
| A5-900 | A4-800 | T4 | Qualify governed-full production autonomy only after external security, legal, operational, and owner gates. |

## Critical path

Node-count path:

`BOOT-000 -> RECON-010 -> ARCH-100 -> CONTRACT-110 -> ROLE-200 -> ORCH-300 -> MISSION-400 -> LEARN-500 -> CHALLENGER-510 -> EVAL-520 -> PROMOTE-530 -> QUALIFY-610 -> LEGACY-620 -> A3-700 -> A4-800 -> A5-900`

Highest accumulated criticality path:

`BOOT-000 -> RECON-010 -> ARCH-100 -> CONTRACT-110 -> ROLE-200 -> CURATOR-340 -> MISSION-400 -> LEARN-500 -> CHALLENGER-510 -> EVAL-520 -> PROMOTE-530 -> QUALIFY-610 -> LEGACY-620 -> A3-700 -> A4-800 -> A5-900`

## Program gates

- **Bootstrap:** no product work before BOOT-000.
- **Truth:** architecture begins only after live reconciliation and baseline audit.
- **Contracts:** no parallel foundation implementation before canonical contracts freeze.
- **Mission:** no autonomy claim before all role cells and shared infrastructure integrate.
- **Learning:** no promotion before held-out evaluation and independent court authorization.
- **Qualification:** no legacy retirement before complete local qualification.
- **Maturity:** A3, then A4, then A5; later levels cannot be inferred from earlier success.

Full machine-readable details, locks, tests, outputs, risks, routes, and stopping conditions are in `REPO_ROOT/.autopilot/plan.json`.
