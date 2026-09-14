# Execution implementation nodes N08–N17

This appendix is a future implementation handoff. None of its implementations, tests, provider sessions, scheduler launches, remote effects, or upgrades were performed while authoring it. New symbols and files below are proposed interfaces, not existing repository capabilities. The program's universal contracts, court dispositions, source register, acceptance rules, and dependency table apply to every node.

All paths in this appendix are repository-relative. Read current signatures before editing; line references identify the audited baseline and may move. A listed new file must be confirmed absent before creation. Extend an existing equivalent instead of maintaining duplicate authorities; record that mapping before release. Commands below are future focused validation commands, run from the admitted repository root. In the validation shell, set `PYTHONPATH` to that worktree's absolute `src` directory (PowerShell: `$env:PYTHONPATH = (Resolve-Path -LiteralPath ./src).Path`) and confirm `hive_mind_os.__file__` resolves inside it before recording receipts. An editable installation pointing to another worktree is invalid evidence. The `tests.test_*` names resolve through this repository's namespace-package test directory when run from its root; no `tests/__init__.py` addition is needed. The full CI command remains `python -m unittest discover -s tests -v` at the applicable integration boundary. A focused pass alone never satisfies a required full gate.

The program's tier definitions apply explicitly as follows; risk descriptions in individual nodes explain their subject matter without replacing these tiers.

| Node | Execution tier |
| --- | --- |
| N08 | T2 |
| N09 | T3 |
| N10 | T3 |
| N11 | T2 |
| N12 | T2 |
| N13 | T2 |
| N14 | T3 |
| N15 | T3 |
| N16 | T2 |
| N17 | T3 |

External application artifacts must build and run without Hive Mind code, its runtime DAG, host scheduler, controller configuration, or private evidence store. These are external orchestration dependencies only. A lessons file is inert documentation. Qualification and publication must check the application's ordinary entry point from a clean distribution that excludes those orchestration artifacts; a published application's runtime must not acquire a Hive/DAG dependency as a side effect of this program.

Inside an admitted node, the Builder may reorder steps, refactor within its write scope, expand reads through recorded bounded retrieval, and run targeted tests without another court. A change to the objective, interface contract, risk, authority, mandatory acceptance, or semantic ownership requires an amended node. Never weaken checks, push protected branches, deploy production, rewrite the live controller, or infer credentials from capability. Read-only indexing may cover the repository; source bodies should follow the node's stated inputs. Every node retains a proposed/actual file manifest, candidate digest, command receipts, independent reviewer identity, unresolved obligations, and rollback record.

## N08 — Persist and restore configured canonical mission bindings

**Outcome and ownership.** A newly started worker process can reconstruct the configured canonical mission adapters from an admitted host configuration and execute the queued mission. Builder owner: Integrator implementation identity; independent reviewer: Curator with authority expertise. Risk: high, guarded integration boundary. Dependencies: N03 and N04. Inputs: their admitted authority/tenant contracts, repository descriptor, configuration digest, and adapter identities. Estimated effort: 2–3 focused implementation sessions; the estimate is planning data, not a token-spending authorization.

**Read.** `src/hive_mind_os/workers.py`, especially `set_canonical_mission_bindings_provider` at line 158 and `_default_canonical_invoker` at 177; `brain_kernel/mission_runtime.py` (`MissionConfig`, `MissionBindings`); `adapter_registry.py`; `brain_kernel/authority.py`; `tests/test_hive_cortex_cli_migration.py`. Paths prefixed with `brain_kernel/` in this appendix are under `src/hive_mind_os/`.

**Write.** Existing: `src/hive_mind_os/workers.py`, `tests/test_hive_cortex_cli_migration.py`. New: `src/hive_mind_os/cortex/repository/mission_bindings.py`, `tests/test_configured_mission_bindings.py`. Lock: `canonical-runtime-binding`; these exact files are exclusive. N09 can proceed concurrently because it owns the graph/runtime contract, provided both consume N04's frozen interface.

**Proposed contract.** `MissionBindingDescriptor` carries schema version, configuration ID/digest, tenant/repository IDs, runtime version, adapter IDs/versions, role-provider references, authority reference, verification-profile digest, and state-root reference. It contains no credentials, Python pickle, arbitrary import path, or embedded executable. `ConfiguredMissionBindingsProvider.resolve(payload, host_context)` returns the existing `MissionConfig` and `MissionBindings`. Resolution states are `UNCONFIGURED`, `VALIDATED`, `READY`, or a typed `BLOCKED`; the host configuration stays outside a writable target checkout.

1. Inventory the current registration tests and preserve the explicit dependency-injection seam for fixtures.
2. Define the descriptor's strict parsing and canonical digest. Reject duplicate, missing, unknown, cross-tenant, or mismatched identity fields before invoking adapters.
3. Resolve IDs only through the admitted adapter registry. Bind credential references in the host adapter, never into the scheduler payload or model context.
4. Add a startup factory that loads the descriptor, validates host roots and authority references, and creates the configured provider. Do not make module import perform effects.
5. Pass that provider explicitly into canonical job execution. Preserve the existing missing-configuration refusal and prohibition on legacy fallback.
6. Record configuration/version/authority digests in the mission start receipt, then verify queued subject and configuration bindings before materializing any workspace.
7. Add a subprocess test that queues a pinned fixture mission, starts a fresh process, resolves configuration, and produces its canonical receipt without relying on a process-global callback from the parent.
8. Have the independent Curator reproduce the restart case from retained fixture configuration and compare receipt bindings.

**Acceptance.** Positive: fresh-process execution and identical configuration restoration. Negative: self-issued authority, target-owned executable configuration, wrong tenant, missing adapter, changed digest, and absent descriptor all produce typed blockers without a provider call. Crash: terminate after configuration observation, restart, and obtain one mission identity rather than duplicate work. Run `python -m unittest tests.test_configured_mission_bindings tests.test_hive_cortex_cli_migration -v`.

**Evidence and recovery.** Retain redacted configuration manifest, restart transcript, route identity, and Curator reproduction. Roll back by selecting the prior immutable descriptor for new jobs; never reinterpret running jobs under a changed descriptor. Stop only the affected binding on configuration/authority ambiguity. Routine missing adapter recovery remains automatic when an already admitted replacement exists.

## N09 — Compile outcome work graphs instead of fixed tiny experiments

**Outcome and ownership.** Whole-system missions can contain several independently useful work packages while retaining bounded, reviewable changes. Builder owner: Architect implementation identity; independent reviewer: Integrator, with separate Curator confirmation of graph invariants. Risk: high, kernel/plan semantics; requires the program ADR. Dependencies: N01, N04 and N06. Effort: 3–4 sessions. Inputs: adjudicated outcomes, immutable node contract, repository binding, admitted capacity, N06's reuse contract, and acceptance inventory.

**Read.** `src/hive_mind_os/tournament_plan_factory.py` (`TournamentPlanFactory._nodes`); `local_dag_runtime.py` (`LocalTournamentService._node`, hardcoded one-improvement instruction at line 566); `brain_kernel/mission_runtime.py` (`MissionRuntime.run`, fixed role chain at 236–253 and `candidate/app.txt` at 244); `brain_kernel/objectives.py` (`ObjectiveGraph`); `compiled_tournament.py` (`compile_node_execution`); `portable_plan.py`; `docs/execution/DAG_AUTHORING_STANDARD_V2.md`.

**Write.** Existing: `src/hive_mind_os/tournament_plan_factory.py`, `src/hive_mind_os/local_dag_runtime.py`, `src/hive_mind_os/brain_kernel/mission_runtime.py`, `tests/test_tournament_plan_factory.py`, `tests/test_hive_cortex_mission_runtime.py`. New: `src/hive_mind_os/outcome_graph.py`, `tests/test_outcome_graph.py`. Locks: `outcome-graph-contract`, `tournament-dispatch-contract`. N08 is independent; N10 and N12 wait for this node.

**Proposed contract.** `OutcomeWorkPackage` binds package ID, outcome/claim IDs, dependencies, allowed paths, semantic locks, acceptance IDs, risk tier, required role evidence, implementation effort, and rollback. `OutcomeGraphSpec` contains package definitions, base snapshot, contract version, maximum concurrent packages, and selected court receipt. `compile_outcome_graph` produces existing typed work items/portable nodes. Internal build operations are not DAG nodes. Package states map to existing work states; amendments create a new graph version and preserve old dispositions.

1. Separate tournament idea selection, implementation packages, and runtime role evidence in the compiler data model.
2. Remove the universal one-small-improvement instruction in favor of explicit admitted campaign limits. Keep the existing small tournament as a valid compatibility profile.
3. Accept a validated graph as `MissionRuntime` input; replace hardcoded output paths and serial role work with package paths/dependencies. Keep the original fixture through an explicit fixture builder.
4. Reuse `ObjectiveGraph` and the portable-plan compiler for acyclicity, dependency existence, path conflicts, immutable source bindings, and capacity checks.
5. Emit eight-role obligations for the mission/cohort, referencing packages that discharge them. Leave the detailed role-resolution implementation to N12.
6. Produce dispatch rounds from dependency readiness, file/semantic conflicts, and capacity. Never infer writable concurrency from breadth-first depth alone.
7. Permit a no-change package with a reasoned disposition, while preserving unfinished value outcomes as open obligations.
8. Test graph amendments against completed-package fingerprints: reuse only what N06's dependency/identity rules permit; invalidated descendants become pending with a reason.

**Acceptance.** Positive: three packages, two safe concurrent reads/builds in distinct isolated workspaces, ordered integration, and all outcomes mapped to tests. Negative: cycle, missing dependency, overlapping writers without ordering, hidden role omission, unselected idea, or undeclared path. Crash: resume after one package completes without rebuilding it or losing its competitors. Run `python -m unittest tests.test_outcome_graph tests.test_tournament_plan_factory tests.test_hive_cortex_mission_runtime -v`.

**Evidence and recovery.** Retain graph versions, compiled rounds, changed-node invalidation report, role-coverage map and ADR. Roll back new graph admission to the previous compiler profile; preserve in-flight graph version ownership. Escalate actual contract/risk changes, not a builder's choice of local edit order.

## N10 — Run the durable campaign and recovery service

**Outcome and ownership.** A configured host continues admitted missions, sleeps when no work is actionable, and recovers after interruption without conversational context. Builder owner: Steward implementation identity; independent reviewer: Curator for durability and Integrator for runtime ownership. Risk: high, persistent operation. Dependencies: N08 and N09. Effort: 3–4 sessions. Inputs: configured canonical binding, graph compiler, finite campaign/resource leases, clock, and target registry.

**Read.** `src/hive_mind_os/scheduler.py` (`Scheduler.enqueue`, `claim`, `heartbeat`, `complete`, `fail`); `workers.py` (`Worker.run_once`, `serve`); `campaign_continuity.py` (`CampaignContinuityController.step`, `recover`); `brain_kernel/reconciler.py` (`DesiredStateReconciler`); `brain_kernel/effect_outbox.py`; `tests/test_scheduler.py`, `tests/test_workers.py`, `tests/test_campaign_continuity.py`.

**Write.** Existing: `src/hive_mind_os/workers.py`, `src/hive_mind_os/scheduler.py`, `tests/test_scheduler.py`, `tests/test_workers.py`. New: `src/hive_mind_os/campaign_service.py`, `tests/test_campaign_service.py`. Locks: `scheduler-lifecycle`, `campaign-controller`; one service lease per campaign. Different repositories may run concurrently only within N03's admitted resource and tenant boundaries.

**Proposed contract.** `CampaignServiceConfig` binds campaign/config IDs, repository IDs, runtime-binding digest, concurrency, daily resource allowance, idle/backoff policy, and stop conditions. `CampaignService.run_once(now)` returns `IDLE`, `PROGRESSED`, `WAITING_EXTERNAL`, `BLOCKED`, or `STOPPED` with an earliest wake time and durable checkpoint reference. This projection does not add unreviewed kernel event types. Jobs retain the existing scheduler state machine and fenced leases.

1. Construct the service by injecting Scheduler, canonical executor, continuity adapter, clock, and wake mechanism. Reuse the existing queue instead of creating a parallel task database.
2. On startup, observe configuration once, recover pending outbox/launch outcomes, and reconcile expired leases before admitting fresh work.
3. Persist a campaign checkpoint containing current graph/package IDs, consumed budgets, pending effects, backoff state and last meaningful observation digest.
4. Dispatch only ready, authorized packages. Persist effect intent before execution and use existing idempotency/lease mechanisms; never retry an uncertain remote effect before observation.
5. Calculate next wake time from queued work, lease expiry, pending external checks and configured discovery cadence. Avoid repeated provider calls or full repository scans while the observed state is unchanged.
6. Implement graceful draining: stop admission, finish or checkpoint admitted local work, release leases, and retain all evidence. A kill signal must not erase journal state.
7. Classify failures as retryable infrastructure, candidate repair, required authority, evidence quarantine, or budget exhaustion. Bound backoff and attempts; a permission denial is not a retryable provider error.
8. Add an injectable service runner suitable for a later host supervisor; tests must not install startup tasks or launch a background service on the author's machine.

**Acceptance.** Positive: two admitted repository campaigns make progress fairly, idle causes no model call, shutdown resumes. Negative: expired/revoked lease, exhausted budget, duplicate owner, and stale completion cannot dispatch or advance. Crash: kill before/after claim, effect intent, effect response and checkpoint write; one adopted effect and one terminal package result remain. Run `python -m unittest tests.test_campaign_service tests.test_scheduler tests.test_workers tests.test_campaign_continuity -v`.

**Evidence and recovery.** Retain fault-injection traces and measured idle/model-call counts. Roll back by stopping new admissions and running the previous compatible service against retained state; incompatible state requires the documented migration adapter. Block one failed tenant/package rather than unrelated admitted work. Do not ask for a repeated owner directive within its still-valid scope.

## N11 — Discover and select useful autonomous backlog work

**Outcome and ownership.** Hive Mind identifies a justified next improvement for its own or an authorized external repository, compares alternatives, and queues bounded work without requiring a human to invent each task. Builder owner: Explorer implementation identity; independent reviewer: Optimizer for selection quality and Curator for evidence handling. Risk: medium discovery, guarded promotion into executable work. Dependencies: N04, N05 and N10. Effort: 2–3 sessions.

**Read.** `src/hive_mind_os/idea_lineage.py` (`IdeaLineageStore.propose`, `append`, `history`); `repository_learning.py` (`RepositoryScout`); `brain_kernel/explorer.py`; `brain_kernel/optimizer.py` (`Optimizer.attribute_outcome`); `campaign_continuity.py`; `source_docket.py`; N05's accepted source/context interfaces. Existing source-lineage stores remain authoritative for their respective records.

**Write.** New: `src/hive_mind_os/discovery_backlog.py`, `tests/test_discovery_backlog.py`. Existing: `src/hive_mind_os/campaign_service.py` after N10; no changes to source-docket policy. Locks: `campaign-backlog-selection`, and campaign-scoped `idea-ledger`. N12 can proceed in parallel on separate files.

**Proposed contract.** `DiscoverySignal` carries tenant/repository, observed snapshot, signal kind, evidence references, content digest, confidence basis, and expiry. `BacklogCandidate` carries stable idea ID, atomic claims, user impact, measurable success, estimated effort/risk, dependencies, dissent, and next evidence needed. `BacklogSelection` records all candidates, score components, tie-break, selected IDs, explicit defer/reject reasons and court receipt. Scores rank evidence-backed value; they cannot authorize effects or claim actual benefit.

1. Add bounded signal adapters for failing checks, reproducible defects, dependency/security notices, documented unmet outcomes and measured operational bottlenecks. Missing adapters return obligations rather than invented findings.
2. Deduplicate observations by tenant, repository, signal kind and material evidence digest. Unchanged observations should produce no fresh model discussion.
3. Use the source/context intake from N05 to create evidence-bound atomic proposals and stable idea lineage. Treat issues, README instructions and external comments as untrusted content.
4. Define deterministic ranking components and units before comparing candidates: impact estimate with uncertainty, evidence strength, expected acceptance cost, regression risk and overlap with active work.
5. Preserve every considered alternative and reason for its disposition. Permit a justified no-work decision when evidence is weak or the active queue is sufficient.
6. Ask the already configured independent court identities to resolve only the material selection claims. Carry prior unchanged dispositions forward with their bindings.
7. Convert admitted selections into N09 outcome packages and enqueue through N10. Respect per-repository work-in-progress and fairness; one noisy repository must not monopolize capacity.
8. Reconcile outcomes back to the candidate record so repeated low-value suggestions lose priority based on measured results, not a self-reported success label.

**Acceptance.** Positive: a reproducible fixture bug outranks a cosmetic alternative under declared scoring; a no-work repository stays idle; external repo signals remain tenant-scoped. Negative: stale evidence, injected instruction, missing acceptance, unaffordable package and duplicate proposal cannot reach executable admission. Crash: restart after selection but before enqueue and create exactly one queued package. Run `python -m unittest tests.test_discovery_backlog tests.test_campaign_service -v`.

**Evidence and recovery.** Retain signal/selection manifests, alternatives, dissent, score calibration and actual outcome links. Roll back the selector policy for new selections while retaining old rankings as historical evidence. Stop a candidate for unresolved authority, licensing or secret evidence; continue unrelated candidates. Do not reopen completed findings simply because a timer fired.

## N12 — Discharge all eight roles at mission and cohort boundaries

**Outcome and ownership.** Every mission contains meaningful evidence for all eight specialist roles and lifecycle stages while ordinary internal edits avoid eight repeated model reviews. Builder owner: Orchestrator implementation identity; independent reviewer: Curator, with a separate Judge for the changed burden interpretation. Risk: high role/closeout semantics; requires the program ADR. Dependencies: N06, N08 and N09. Effort: 2–3 sessions. N06 supplies the reuse/invalidation contract consumed by role evidence aggregation.

**Read.** `src/hive_mind_os/brain_kernel/role_applicability.py` (`RoleDisposition`, `resolve_dispositions`, `route_prior_results`); `brain_kernel/role_runtime.py` (`RoleRuntime.deterministic_result`); `brain_kernel/roles.py`; `brain_kernel/closeout.py`; `brain_kernel/mission_runtime.py`; `tests/test_hive_cortex_role_applicability.py`. Existing tests already establish eight accountable records with fewer than eight model calls.

**Write.** Existing: `src/hive_mind_os/brain_kernel/role_applicability.py`, `src/hive_mind_os/brain_kernel/role_runtime.py`, `src/hive_mind_os/brain_kernel/mission_runtime.py`, `tests/test_hive_cortex_role_applicability.py`. New: `src/hive_mind_os/role_coverage.py`, `tests/test_role_coverage.py`. Locks: `role-applicability-policy`, `mission-closeout-contract`. N11 is independent. N13 and N14 consume the frozen output contract.

**Proposed contract.** `RoleCoveragePlan` binds mission/cohort, graph and policy digests plus exactly eight role rows. Each row names identity, responsibility, applicable packages, evidence requirements, execution mode and revisit triggers. `RoleCoverageReceipt` references actual role results and accepted deterministic checks. A role marked not applicable on one package is not removed from mission accountability. `coverage_complete` requires substantive evidence for every role and every lifecycle stage, including explicit proportional findings where no change is needed.

1. Map mission responsibilities: orchestration/selection, exploration, architecture, implementation, independent verification, integration, operation/recovery, and measured outcome learning.
2. Resolve existing applicability policies at package level, then aggregate obligations into one mission/cohort coverage plan. Keep critical independence rules structural.
3. Define deterministic role checks for straightforward contract, receipt, compatibility and operational invariants. Their result must cite executed checks, never generic boilerplate asserting a role occurred.
4. Reuse prior role evidence only when responsibility inputs, candidate-relevant surfaces, policy and acceptance bindings remain valid under N06.
5. Record revisit triggers such as public API change, migration, new external effect, security boundary change, operational regression, or newly contradicted evidence. Routine code reorder is not a trigger.
6. Route full direct-dependency results and compact indirect evidence through existing context tiers. Preserve cold references and dissent outside the transmitted prompt.
7. Integrate the coverage receipt into mission completion. A package can finish before all mission roles close, but the mission cannot claim full lifecycle completion with missing accountability.
8. Obtain independent review of representative small and large package plans before enabling the policy.

**Acceptance.** Positive: several trivial internal edits use one ongoing Builder session and bounded role invocations, yet all eight mission responsibilities are evidenced. Negative: forged deterministic pass, missing Optimizer/Steward evidence, self-verification, reused judge identity, stale architecture result or authority-change suppression blocks closeout. Crash: restart after six role receipts and execute only the remaining valid obligations. Run `python -m unittest tests.test_role_coverage tests.test_hive_cortex_role_applicability tests.test_hive_cortex_role_runtime -v`.

**Evidence and recovery.** Retain coverage tables, role-call counts, unchanged-input reuse decisions and independent interpretation verdict. Roll back the new aggregation policy for newly admitted cohorts; retain complete old receipts. If uncertainty concerns actual authority or proof burden, amend the contract; implementation inconvenience alone does not justify another court.

## N13 — Give the Builder a bounded autonomous implementation loop

**Outcome and ownership.** A Builder can inspect, implement, refactor, test and repair a coherent package inside an isolated candidate until acceptance is ready, without requesting approval for each command or patch. Builder owner: Builder implementation identity; independent reviewer: Curator with sandbox expertise. Risk: high executable tooling, bounded local effects. Dependencies: N05, N06, N07, N12 and N18. Effort: 4–6 sessions; split by adapter seam if the admitted session allowance is smaller.

**Read.** `src/hive_mind_os/local_codex_worker.py` (`CodexLocalWorker.run`); `local_dag_runtime.py` (`LocalTournamentService._node`, `_recover_patch`); `model_action_adapter.py`; `model_backend.py`; `git_adapter.py` (`GitWorkspace`); N18 sandbox contract; N05–N07 context/cache/model-routing contracts. Existing packet mode remains a valid fallback.

**Write.** Existing: `src/hive_mind_os/local_codex_worker.py`, `src/hive_mind_os/local_dag_runtime.py`, `tests/test_local_codex_worker.py`, `tests/test_local_dag_runtime.py`. New: `src/hive_mind_os/builder_session.py`, `tests/test_builder_session.py`. Locks: `builder-session`, `local-tournament-worker`. N14 may run in parallel because it owns the independent verification adapter, not these files.

**Proposed contract.** `BuilderSessionSpec` binds package/attempt/tenant IDs, starting candidate, allowed paths and operations, acceptance references, sandbox and model profiles, checkpoint policy, and finite token/tool/time/repair allowances. `BuilderSessionResult` is `READY_FOR_VERIFICATION`, `NO_CHANGE`, `NEEDS_CONTRACT_AMENDMENT`, `BUDGET_EXHAUSTED`, or `BLOCKED`, with candidate/patch, changed paths, checks, remaining failures and evidence references. Internal states are `READY → WORKING ↔ CHECKPOINTED → terminal`; only the host may commit candidate state.

1. Separate the worker's model exchange from host tool execution so configured providers and Codex local execution share the same session contract.
2. Materialize the pinned candidate under N18's admitted sandbox. Bind writable paths and deny protected references, host configuration, credentials and other tenant roots.
3. Supply the bounded source context, current failures and direct dependency receipts; fetch additional relevant context through N05 instead of sending the full repository repeatedly.
4. Permit in-scope reads, edits, local refactors and chosen targeted checks. Validate tool intent deterministically, then record receipts without launching a new court for each reversible operation.
5. Checkpoint after coherent edits and before expensive/external boundaries; preserve model/tool usage and the last clean candidate digest. A checkpoint is not a production-readiness claim.
6. Detect unchanged failure fingerprints and lack of material progress. Use N07's admitted escalation policy or return a typed blocked result; never loop indefinitely or repeat identical checks without new inputs.
7. Produce one candidate seal with exact changed paths and explicit unexecuted acceptance obligations. The independent verifier receives candidate evidence, not an instruction to trust Builder claims.
8. Keep recorded-patch recovery deterministic: an already captured patch can be applied or observed once without rerunning the model merely to regenerate identical bytes.

**Acceptance.** Positive: a fixture requires two edits and a failed-then-passing targeted test, completed within one session. Negative: out-of-scope file, secret/host access, changed acceptance, tool-capability escalation and forged test output are refused. Crash: kill after patch persistence, tool execution and checkpoint; recover without duplicate effects or lost budget. Run `python -m unittest tests.test_builder_session tests.test_local_codex_worker tests.test_local_dag_runtime -v`.

**Evidence and recovery.** Retain candidate manifests, session checkpoints, actual usage, failure fingerprints and independent sandbox review. Roll back by discarding only the isolated candidate or resuming its last retained checkpoint; source and evidence remain. Escalate only missing authority, genuine contract change, unavailable required capability or exhausted admitted recovery.

## N14 — Qualify the exact candidate independently and proportionately

**Outcome and ownership.** The Curator independently qualifies a sealed candidate using appropriate executed checks, with exact reuse and truthful distinctions among tests, compilation, static checks and unexecuted runtime obligations. Builder owner: Curator tooling implementation identity; independent reviewer: a different Curator identity plus Integrator. Risk: high acceptance boundary. Dependencies: N06, N12 and N18. Effort: 3–4 sessions.

**Read.** `src/hive_mind_os/brain_kernel/verification.py` (`verify_exact_candidate`); `brain_kernel/curator_runtime.py`; `local_evidence_packet.py` (`run_focused_checks`); `verification_adapters.py` (`VerificationRegistry`, `verify_repository`); `test_result_cache.py` (`TestCacheKey`, `TestResultCache`); `tests/test_control_token_economy.py`. The current local tournament checks the patch and later verifies in another clone; the two evidence origins must remain distinguishable.

**Write.** Existing: `src/hive_mind_os/local_evidence_packet.py`, `src/hive_mind_os/verification_adapters.py`, `tests/test_verification_adapters.py`. New: `src/hive_mind_os/candidate_qualification.py`, `tests/test_candidate_qualification.py`. Locks: `candidate-qualification`, `verification-adapter-contract`; independent workspaces per candidate. N18 owns the initial isolation-backend registration and completes it first; N14 consumes and extends that registered seam after N18 releases the file lock. N18 never waits for N14, so this ownership transfer adds no circular dependency. N13 is parallel-safe; N15 waits for this node's contract.

**Proposed contract.** `QualificationRequest` binds candidate/base identities, sealed acceptance manifest, changed surfaces, risk tier, sandbox/toolchain/environment digests, evaluator identity and allowed cache provenance. `QualificationReceipt` carries each check's kind, command/input digests, execution/cache origin, status, actual count, artifacts, omissions and invalidation rules. Terminal dispositions are `PASSED`, `FAILED`, `INCOMPLETE` or `QUARANTINED`; missing required tests/runtime evidence cannot become `PASSED`.

1. Replace filename-only test guessing with an explicit acceptance manifest plus deterministic impact mapping. Keep safe heuristic suggestions as proposals, never sole proof of full coverage.
2. Materialize the exact candidate in an independently controlled N18 workspace. Validate evaluator independence and candidate content before executing any qualification command.
3. Form N06 cache keys from all relevant execution inputs and provenance domain. Reuse independently authenticated exact results where allowed; do not relabel Builder checks as Curator execution.
4. Run the required focused/static/integration checks in the sealed manifest. Report absent toolchains, unexecuted tests and unsupported runtime adapters as incomplete obligations.
5. Compare observed files before/after verification and reject candidate or acceptance drift. Retain actual process outcomes and full logs by digest; transmit concise successful summaries and distinct failures.
6. Have the Curator review coverage, threats and material failure evidence once per qualified candidate, not after each implementation edit.
7. At the integration boundary require the repository's full CI gate for the final integrated candidate, reusing only an independently valid exact receipt if governing policy allows it. Never skip a mandated round/integration gate to save tokens.
8. Emit invalidation reasons for candidate, acceptance, dependency, environment or material evidence changes so downstream delivery can determine whether qualification remains usable.

**Acceptance.** Positive: unchanged independently verified candidate reuses one receipt; changed relevant input executes again. Negative: Builder-origin cache, zero tests, compile-only output labeled tests, stale candidate, altered manifest or missing required runtime cannot pass. Crash: terminate after command exit before receipt publication; observe retained results or rerun safely in a clean verifier workspace without granting success from uncertainty. Run `python -m unittest tests.test_candidate_qualification tests.test_verification_adapters tests.test_control_token_economy -v`.

**Evidence and recovery.** Retain qualification/coverage manifests, check origins, drift observations and independent reproduction. Roll back the qualification adapter version for new requests; prior receipts keep their version binding. Fail the affected candidate, not all discovery work. Changed code repairs return to N13 with concise failure evidence.

## N15 — Publish reviewable PRs through a separate delivery broker

**Outcome and ownership.** A qualified candidate can become a draft PR on its authorized repository and run branch without granting remote permissions to local tournament workers. Builder owner: Integrator implementation identity; independent reviewer: Curator for authority and privacy. Risk: high external effects. Dependencies: N03, N10 and N14. Effort: 3–4 sessions. Inputs: exact qualified candidate, admitted delivery grant, owner/repository/base binding, sanitized PR content, and durable effect store.

**Read.** `src/hive_mind_os/cortex/github/delivery_adapter.py` (`ControlledGitHubDelivery.register_with`, `push_adapter`, `draft_pr_adapter`); `cortex/github/grants.py` (`DeliveryGrant`, `DeliveryGrantLedger`); `cortex/github/push_executor.py`; `brain_kernel/effects.py`; `brain_kernel/effect_outbox.py`; `delivery_boundary.py`; `tests/test_hive_cortex_delivery.py`. `github_adapter.py` raw write methods remain quarantined.

**Write.** New: `src/hive_mind_os/delivery_broker.py`, `tests/test_delivery_broker.py`. Existing: `src/hive_mind_os/campaign_service.py`, `tests/test_hive_cortex_delivery.py`. Locks: `remote-delivery`, repository/run-branch scoped effect lock, and `campaign-controller` during integration. This node is independent of N13 implementation work after its dependencies pass.

**Proposed contract.** `DeliveryRequest` binds request/package/tenant, candidate commit/tree, qualification receipt, target/base, run branch, grant reference, artifact kind, content digest and idempotency key. `DeliveryResult` is `LOCAL_ARTIFACT_READY`, `PUSH_PENDING`, `PR_PENDING`, `PUBLISHED`, `RECONCILIATION_REQUIRED` or `BLOCKED`. Artifact kinds distinguish application code delivery from sanitized lessons-only export; the learning producer supplies the latter's exact file manifest. A draft PR is delivery evidence, not merge or production deployment.

1. Parse a delivery request and verify tenant, target, branch, candidate, qualification validity and grant issuance before retrieving credentials or invoking a transport.
2. Validate the artifact kind's allowed changed files. Application code belongs only in its authorized application PR; a lessons-only artifact cannot contain code, raw logs or unrelated files.
3. Prepare deterministic PR title/body with problem, behavior, validation and remaining limitations. Sanitize content before it crosses the broker boundary; retain raw sensitive evidence only in its permitted tenant custody.
4. Bind parameters to `ControlledGitHubDelivery`, register it with the existing `EffectGateway`, and obtain the existing capability token from the admitted authority registry.
5. Persist push intent, publish only the granted run branch, and verify the observed head SHA. Never force-push a protected branch or infer merge permission.
6. Persist draft-PR intent and reuse an existing matching PR before creating one. On uncertain network outcome, observe remote branch/PR identity before any retry.
7. Retain qualification and remote identifiers in the durable result. Notify the campaign of meaningful publication/failure once; do not post repetitive status comments.
8. If grant/credentials are absent, retain the prepared local delivery artifact and typed requirement. Do not discard completed implementation or repeatedly ask for previously granted authority.

**Acceptance.** Positive: exact candidate push plus one draft PR and idempotent repeat. Negative: wrong repository, stale head, invalid grant, protected/base branch, lessons containing code, or secret-bearing body produces no remote call. Crash: lost push response, lost PR response and post-effect journal interruption reconcile to one delivery. Run `python -m unittest tests.test_delivery_broker tests.test_hive_cortex_delivery tests.test_delivery_grants -v` with fake transports; a later live pilot needs its own admitted binding.

**Evidence and recovery.** Retain sanitized request, effect/qualification references and observed PR/head. Rollback normally supersedes or reverts the run branch via an authorized artifact; close/delete only own draft/branch when explicitly granted. Stop on uncertain effect identity until reconciled, while unrelated local work continues.

## N16 — Consume PR feedback and repair CI without duplicate work

**Outcome and ownership.** The campaign notices meaningful feedback or CI failures on its own draft PR, reproduces actionable problems and sends bounded repairs through the same build/verify/delivery path. Builder owner: Steward implementation identity; independent reviewer: Curator for untrusted input and Integrator for delivery continuity. Risk: high remote observations feeding local execution. Dependencies: N11, N13 and N15. Effort: 3–4 sessions; use N14 transitively through N15 for every changed candidate.

**Read.** `src/hive_mind_os/github_adapter.py` read-only `poll_checks`; `cortex/github/rest_gateway.py`; `cortex/github/delivery_adapter.py`; `campaign_service.py`; `discovery_backlog.py`; `builder_session.py`; `delivery_broker.py`. Read retired `autonomous_os.py` feedback methods only as historical references, not as an execution route to restore.

**Write.** New: `src/hive_mind_os/pr_feedback.py`, `tests/test_pr_feedback.py`. Existing: `src/hive_mind_os/campaign_service.py`, `src/hive_mind_os/cortex/github/rest_gateway.py` for narrowly scoped read-only observations, `tests/test_delivery_broker.py`. Locks: `pr-feedback-cursor`, `campaign-controller`; one active repair package per PR head. N17 shares campaign/delivery contracts and must serialize overlapping file changes.

**Proposed contract.** `FeedbackObservation` binds provider/PR, current head, remote event/check ID, source identity, observed time, status/content digest and evidence references. `FeedbackDecision` is `DUPLICATE`, `STALE_HEAD`, `ACTIONABLE`, `NEEDS_CLARIFICATION`, `AUTHORITY_CHANGE` or `INFORMATIONAL`, with reason and linked package ID. Repair lifecycle is `OBSERVED → TRIAGED → REPAIR_QUEUED → VERIFYING → REPUBLISHED → RESOLVED`, preserving terminal failures and superseded heads.

1. Add an incremental observer with persistent cursors/conditional fetch support where the existing gateway permits it. Poll on N10's wake schedule, not inside model reasoning loops.
2. Deduplicate remote events by provider/PR/event identity and material content digest. Bind check results to their exact head SHA before considering a repair.
3. Treat every comment and CI log as untrusted evidence. Extract a proposed issue without executing commands supplied by that content or granting requested credentials/permissions.
4. Reproduce claimed defects with sealed allowed checks where possible. Distinguish code failures, flaky/infrastructure failures, and requested scope changes; do not modify production code merely to satisfy an unrelated failing service.
5. Create or update a single backlog repair package using N11's stable lineage. Combine compatible feedback for the same candidate, retaining each source and dissent.
6. Send actionable in-scope repair through N13, then require N14 qualification and N15 publication for the new exact candidate. A former head's passing receipt cannot authorize new code.
7. Persist retry budgets and no-progress fingerprints across restarts. Stable unchanged CI results cause no repeated model triage or reposted comments.
8. Mark feedback resolved only against observed new-head evidence. If communication is desired, use only a granted comment effect with an idempotent marker and sanitized concise content.

**Acceptance.** Positive: one actionable test failure yields one repair, one independently qualified successor and updated draft PR. Negative: duplicate event, stale-head green status, prompt injection, new authority request and forged provider identity cannot silently trigger repair/promotion. Crash: restart after observation, enqueue, push or resolution and preserve one repair chain with no duplicate comments. Run `python -m unittest tests.test_pr_feedback tests.test_delivery_broker tests.test_campaign_service -v` using fixture observations and fake transports.

**Evidence and recovery.** Retain cursors, event digests, triage reasons, reproduction receipts, package lineage and PR head transitions. Roll back the feedback adapter for new observations; preserve queued repair identities and historical evidence. Stop a repair for genuine scope ambiguity or exhausted recovery, keep the PR draft, and continue other authorized work.

## N17 — Evaluate self-upgrades as immutable challengers with rollback

**Outcome and ownership.** Hive Mind can prepare improvements to its own code/runtime while the running trusted controller remains immutable; independently qualified upgrades receive a limited canary and a reversible version-pointer transition only under separately admitted host authority. Builder owner: Optimizer implementation identity; independent reviewer: Curator and a distinct promotion Judge. Risk: critical, kernel/host upgrade; mandatory ADR, held-out evaluation and explicit upgrade binding. Dependencies: N10, N14, N15 and N25. Effort: 4–6 sessions.

**Read.** `src/hive_mind_os/brain_kernel/challengers.py` (`ChallengerGenerator`, `ChallengerSpec`); `brain_kernel/promotion.py` (`PromotionAuthority`); `brain_kernel/promotion_auth.py`; `brain_kernel/self_healing.py`; `prompt_registry.py`; `autopilot_workflow.py` (`trust_controller`); N25's sealed benchmark/evaluation contracts. Existing prompt promotion is a pattern and cannot be relabeled as OS binary/version activation authority.

**Write.** New: `src/hive_mind_os/self_upgrade.py`, `tests/test_self_upgrade.py`. Existing: `src/hive_mind_os/campaign_service.py` only to pause/resume new admissions and record upgrade observations. Do not modify the active installed controller, host trust records, existing promotion policy, or a live pointer during implementation tests. Locks: `self-upgrade`, `host-runtime-version-pointer`, `campaign-controller`; one upgrade transition per host.

**Proposed contract.** `RuntimeChallenger` binds candidate artifact/version/digest, champion parent, source PR/commit, dependency and migration manifests, rollback artifact, evaluation plan/results, builder/evaluator/judge identities and requested canary scope. `UpgradeDecision` is `RETAIN`, `CANARY`, `PROMOTE`, `ROLLBACK`, `DEFER` or `QUARANTINE`. Host states are `CHAMPION_ACTIVE → CANARY_PREPARED → CANARY_RUNNING → DECISION_READY → CHAMPION_ACTIVE`; an uncertain activation enters `RECONCILIATION_REQUIRED`. A digest proves identity, not authority or superiority.

1. Package the challenger in a separate immutable directory/process environment; bind code, dependencies, configuration schema and migration compatibility to its digest.
2. Require N14 correctness/acceptance and N25's independently sealed held-out evaluations before canary admission. Compare pinned champion and other required comparators under equal declared budgets, preserving losing outcomes.
3. Validate complete identity separation and permitted upgrade authority. Keep `LOCAL_ARTIFACT_READY` or a draft PR as the successful delivery when no activation authority exists.
4. Prepare reversible state migration on copies. Reject an upgrade whose old champion cannot read required retained state or whose rollback cannot restore service safely.
5. Launch the canary through an injected host adapter with an admitted finite tenant/task/resource scope, isolated state and no production credentials by default. Shadow operations must not duplicate external side effects.
6. Measure correctness, escaped regressions, tenant isolation, throughput/cost, restart recovery and operational health against predeclared budgets. Stop and quarantine on mandatory safety regression.
7. After a valid independent verdict, drain old admissions and request an atomic compare-and-swap version-pointer update through the separate host broker. Keep the previous champion artifact and activation receipt.
8. Reconcile lost activation responses by observing the actual pointer/process state. Exercise rollback through the same authorized broker; never let a candidate rewrite the live controller or grant itself authority.

**Acceptance.** Positive: immutable challenger, isolated canary, accepted verdict and simulated atomic transition. Negative: self-judgment, changed holdout, missing rollback, incompatible migration, absent host authority, tenant leak or guardrail weakening retains/quarantines without activation. Crash: kill before/after pointer change and recover one observed active champion; rollback restores retained compatible state. Run `python -m unittest tests.test_self_upgrade tests.test_hive_cortex_promotion tests.test_campaign_service -v` with a fake host broker.

**Evidence and recovery.** Retain immutable artifacts, comparator pins, canary metrics, independent verdict, migration rehearsal and activation/rollback receipts. Missing authority is a typed activation blocker, not an excuse to abandon prepared code/PR work. Real host deployment remains a separately authorized action after the complete reversible candidate and evidence are reviewable.
