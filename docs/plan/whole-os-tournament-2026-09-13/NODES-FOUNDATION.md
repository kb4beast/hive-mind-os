# Foundation and efficiency nodes

All steps below are future implementation instructions. Inherit RUNBOOK section 5. `NEW` means proposed, not currently implemented. Focused tests named as NEW must first be authored. Unit tests use synthetic data, fake clocks and fake effect adapters unless explicitly labelled a real integration probe. Implementation estimates are planning estimates; the execution lease supplies the actual budget. Absolute source paths are resolved under the admitted worktree, never under another worker's directory.

## N00 — Reconcile source, requirements and existing completion

**Dependencies:** none. **Owner:** Explorer; separate Curator validates the inventory. **Tier/risk/effort:** T1, read-only discovery, one session. **Lock:** successor-source-manifest. **Inputs:** original request, this handoff, current Git HEAD/tree, repository instructions, existing plan/receipts.

**Read:** `AGENTS.md`, `docs/architecture/HARDENED_VISION_CONTRACT.md`, ADR-074–078, `src/hive_mind_os/founding_docket.py`, `docs/execution/DAG_AUTHORING_STANDARD_V2.md`, `.autopilot/README.md`, and the exact seams inventoried in RUNBOOK section 2. Existing historical handoffs are evidence, not current completion proof.

**Write:** NEW successor campaign source/requirement inventory and immutable reconciliation report under the external admitted campaign root. NEW `docs/plan/whole-os-implementation/SOURCE_RECONCILIATION.md` contains safe references. Do not overwrite this handoff's baseline or `.autopilot` history.

**Steps:**

1. Observe HEAD, tree, status and configured target identity. Record dirty files and unrelated work without changing them. Materialize the inspected source separately if the target moved.
2. Preserve the owner request and each governing source as a distinct source record with original bytes or exact Git blob reference, hash, retrieval timestamp, license status and ingestion completeness.
3. Import requirements R01–R18 from `requirements.json`. Retain separately any additional adopted founding requirements; an enhancement does not erase them.
4. Check the actual source symbols named by every node. Classify each planned capability as existing-and-wired, existing-unwired, incomplete, absent, or unknown, citing its tests and callers.
5. Inspect existing completion receipts/ancestry before declaring prior work done. Map overlapping old-plan nodes to new requirements without changing old receipt bytes.
6. Emit only the affected-node changes if baseline drift is found. A capability already independently evidenced can become a reuse decision, with its dependency/authority caveats.
7. Register missing external source archives, Roblox subjects, licenses, assets and runtime access as explicit obligations. Unknown facts stay unknown; no invented trajectory or benchmark.
8. Submit the inventory for independent read-only review and seal its version. Produce N01/N02 input packets from this version.

**Acceptance:** Every requirement/source appears exactly once with a stable ID and references; no inaccessible source is marked ingested; all existing-path locators resolve; no claimed implementation is supported only by a document title. Negative cases for the future inventory checker: deleted source ID, wrong blob digest, stale receipt, dirty baseline represented as committed, duplicate requirement ID. Validation is a deterministic inventory/path/digest check and separate Curator inspection, not a product runtime test.

**Output/stop:** sealed `SourceInventory` and `ReconciliationReport`, plus a successor node map. Stop before runtime activation. **Rollback:** select the prior manifest; retain the new report as superseded evidence. **Escalation:** inaccessible evidence is a scoped obligation; only an actual new authority requirement reaches the operator.

## N01 — Record decisions and compile the successor campaign

**Dependencies:** N00. **Owner:** Architect/Advocate; separate Cross-Examiner, expert witness and Judge. **Tier/risk/effort:** T3, kernel/contract, two sessions. **Locks:** plan-schema and architecture-decision-index.

**Read:** N00 inventory, tournament/review, `portable_plan.py`, `dag_standard.py`, `plan_generation.py`, `tournament_plan_factory.py`, existing ADRs and source docket. **Write:** five new ADRs from RUNBOOK section 2, NEW `docs/plan/whole-os-implementation/PLAN.md`, and external successor plan/generation manifest. NEW `tests/test_whole_os_plan_contract.py` covers compiled planning data when executable construction is added. No production runtime behavior is changed by ADR text.

**Steps:**

1. Assign independent court identities. Collect advocate, examiner and expert statements; disposition each R requirement and material architecture choice separately using adopt/adapt/defer/reject/quarantine.
2. Allocate next unused numeric ADR IDs after reading the current ADR index. Record exact filenames in PLAN so later nodes reference one canonical decision map. Node-specific additional ADRs may use the explicit `ADR-WOS-NNN-...` filenames in their contracts under `docs/architecture/`.
3. Preserve dissent and failed/unknown claims. Select the proposed hybrid only for design implementation; defer any speed, quality or production-superiority assertion pending N30.
4. Translate the inert 34-node index into the repository's supported versioned portable-node contracts, binding current standard/source, authority profile, dependencies, budgets, output/evidence requirements and separate publication stages.
5. Preserve the existing thirteen-stage local tournament as a compatibility profile. Do not edit its signed historical plan, manufacture a signature, or treat a local authority envelope as push permission.
6. Validate unique IDs, acyclic dependencies, no orphaned adopted requirements, complete routes and outputs, explicit semantic locks, and compatibility consumers. A graph compilation failure becomes a specific repair task.
7. Seal a new generation manifest. External host attestation/activation occurs through the already supported host boundary only when implementation execution is actually configured.
8. Emit the permanent dispatcher entry and node-prompt template from RUNBOOK section 8 with exact canonical paths. Humans must not paste the full handoff into each worker.

**Acceptance:** Positive: all 34 contracts compile, sources/requirements map and historical profile remains valid. Negative: missing role/output, cycle, lost claim, altered standard, unauthorized effect, unknown route or copied old signature rejects. Proposed command: `python -m unittest tests.test_whole_os_plan_contract tests.test_tournament_plan_factory tests.test_compiled_tournament -v`.

**Output/stop:** ADRs, court dispositions, sealed successor plan and inactive generation artifacts. **Rollback:** select prior compiler/profile for new admissions; preserve old and new evidence. **Escalate:** only unresolved contract contradictions or new scope; ordinary decomposition stays within the selected design.

## N02 — Freeze metrics, comparator manifests and experiment design

**Dependencies:** N00. **Owner:** Optimizer; separate evaluation Curator. **Tier/risk/effort:** T2, measurement integrity, two sessions. **Locks:** benchmark-rubric and holdout-manifest.

**Read:** `token_ledger.py`, `token_benchmark.py`, `benchmark.py` if confirmed by N00, `brain_kernel/evaluation_runtime.py`, existing multi-comparator court, EX01/EX03/EX06/EX07, and tournament design assumptions. **Write:** NEW `src/hive_mind_os/campaign_metrics.py`, `tests/test_campaign_metrics.py`, `docs/benchmarks/whole-os-protocol.md`; private pinned benchmark manifests outside the target.

**Contract:** `AttemptMetric` binds subject-family token, task ID, candidate/config/model/environment digests, eligibility, result, active/queue/wall time, measured/estimated/unknown usage, provider cost basis, checks, defects, recovery and disclosure events. No missing quantity is coerced to zero.

**Steps:**

1. Define the functional success/defect/privacy criteria before looking at challenger outcomes. Separate ineligible capability cases from attempted failures and retain both in totals.
2. Pin the existing baseline and external comparator sources/licenses now. Freeze the proposed candidate's build/selection rule and required adapter/configuration shape; its future bytes do not exist yet. Immediately before N30's original stage, an independent evaluator seals the actual N28 candidate and original variant digests. Seal later hybrid variants before their stage, then bind the unchanged selected pair before the final stage. No stage may change its frozen tasks, rubric, budgets or selection rules. Archive required comparator source bytes before executing them.
3. Define task strata: small bug, feature, absent tests, multi-file change, cross-language change, self-runtime change, ambiguous backlog, provider failure, restart, external tenant isolation, draft export, endpoint learning and Roblox runtime. Do not pretend all public comparators natively support every stratum.
4. For component comparisons, put builders behind identical adapters and limits. For full-system comparisons, score unsupported required capability explicitly and retain infrastructure cost; do not call that a matched builder comparison.
5. Freeze repository-family splits, task selection seed, attempts per task, retry rules, confidence calculation and thresholds. Initial qualification uses at least 30 distinct repository/task-family pairs per comparable lane, with 3 seeded repetitions where stochasticity applies; repetitions are clustered within families, not counted as independent repositories.
6. Specify paired family bootstrap, 10,000 resamples and 95% intervals for cost/time differences and paired task success difference. Noninferiority requires the lower confidence bound of success difference to exceed -0.05, plus all hard gates. If intervals are too wide, mark INCONCLUSIVE and design a new versioned experiment; do not quietly sample until significance.
7. Add counters for context retransmission, redundant checks, model calls and avoided work. Include provider billed-cache distinctions and actual availability; host token estimates remain labelled estimates.
8. Have the evaluator sign the protocol/holdout binding. Keep holdout content outside builder, prompt, memory and repository caches.

**Acceptance:** Deterministic synthetic examples validate denominators, units, unknown cost, paired differences and family grouping. Repeated seed yields identical aggregate output. Negative controls reject dropped failures, changed rubrics and treating 3 runs of one repo as 3 independent repos. Command: `python -m unittest tests.test_campaign_metrics -v`.

**Output/stop:** frozen protocol and instrumentation library; no benchmark win asserted. **Rollback:** new metric schema version with old data retained. **Escalate:** unresolvable comparator rights or missing runtime affect only that lane; do not invent a public benchmark score.

### N02 required MatchProtocol output

Produce a closed `MatchProtocol` data artifact alongside the metric protocol. It contains `protocol_id`, `version`, `track_id`, `entrant_recipes`, `variant_digest_rules`, `candidate_seal_rule`, `scenario_task_ids`, `dataset_block_ids`, `pairing_rule`, `decision_rule`, `hybrid_recipes`, `elimination_losses=3`, `resource_lease_ref`, `max_rounds=24`, and `terminal_rules`. Freeze the following rules:

- **Separate tracks.** Builder-component track uses MB0 existing packet builder, MB1 pinned EX01 minimal agent, MB2 pinned EX03 SDK, and MB3 N13's iterative builder, all behind the same admitted sandbox/verification harness. Whole-campaign track uses MC0 the pinned current campaign and MC1 the N28 implementation, with actual unsupported capabilities recorded. Builder scores are not whole-system scores. Analytical A/H IDs are not measured variant IDs.
- **Adapter ownership.** N30 authors a benchmark-only adapter module for the four builder recipes and campaign invocations. Each recipe resolves to immutable source/binary, prompt, model, command/profile, tool, context, check-policy and learning-policy digests. No extra credentials or relaxed gates for a comparator. Two recipes resolving to the same complete behavior/configuration digest are one entrant, never two competitive votes.
- **Pairing.** At each round sort eligible entrants by current losses then stable ID and rotate left by round minus one. Only when the entrant count is odd, give a bye to the entrant with the fewest prior byes (ID breaks the tie). Pair adjacent compatible entrants in that frozen order; skip pairs with two prior inconclusive meetings and choose the next compatible opponent. An unmatched entrant remains unpaired with no win/loss. Terminate INCONCLUSIVE if no pairs remain schedulable. Cycle the frozen scenario task blocks by round and pair index as in the analytical record. A bye awards no win or loss. Third resolved loss eliminates; a safety violation quarantines separately and is never hidden as an ordinary loss.
- **Match decision.** Compare paired functional success first. A candidate wins on success only when the frozen paired interval supports a positive success difference and no required safety/quality gate regresses. If both satisfy the noninferiority rule, a candidate may win on efficiency only when its paired cost-ratio upper 95% bound is below 1.0 and its elapsed-time-ratio upper bound is at most 1.10, or vice versa for time/cost. If neither dominates, record DRAW/INCONCLUSIVE with no loss. Do not break scientific ties by lexical ID or subjective model preference. Ranking retained development observations does not create new independent evidence.
- **No repeated model runs for bracket bookkeeping.** Run each frozen variant/task/seed once in its assigned evidence block. Matchups reuse those exact outcome receipts where the protocol permits; arithmetic and bracket scheduling are deterministic. Repetition happens only for predeclared seeds, invalidated executions or a new evidence block, not because an entrant appears in another matchup.
- **Measured hybrids.** After development comparisons, form up to four distinct coherent recipes: MH1 MC1 with the MB1 builder and scoped learning; MH2 MC1 with MB2 and the same privacy/learning boundaries; MH3 MC1 with MB3, capsules/cache and a frozen no-learning-activation ablation; MH4 MC1 with the Roblox-specialized N26/N27 profile and domain curriculum. Mandatory export drafts and all safety/acceptance gates remain intact. Each has a separate composition manifest and a declared operating regime. A duplicate, unavailable or immaterial recipe is explicitly DEFERRED, not assigned fabricated results. The analytical distributed H03 remains deferred unless separately implemented; do not pretend MH3 implements it.
- **Fresh data and final.** Hybrids use a disjoint harder development block after recipes are frozen. Select strongest eligible original and hybrid within the same operating regime; final qualification compares two different frozen variants on untouched family-split `promotion_holdout` data under the N02 sample/interval rules. If there is no distinct qualified pair, report no comparative championship. Public-source pretraining caveats remain. No tuning or recipe change after the final block is opened.
- **Bounds and inconclusive outcome.** Freeze development screening sizes, seeds and scenario membership in N02 before execution; the initial default is 12 distinct task families per eligible variant with one seed for screening, and the existing 30-family/3-repetition rule for final qualification. A pair with two inconclusive meetings is not scheduled again in that stage. Stop at one survivor, no unresolved schedulable pairs, 24 rounds or lease exhaustion. Preserve a partial bracket and INCONCLUSIVE verdict when applicable. Do not consume new tasks until significance appears or renew the lease automatically.

This is an implementation-ready protocol, not a command to spend resources now. Developer screening narrows expensive final evaluation. Multiple-comparison/selection uncertainty in development is not promoted into a superiority claim; the fresh final comparison carries that claim.

## N03 — Bind repository, tool and capability profiles

**Dependencies:** N01. **Owner:** Integrator; separate security Curator. **Tier/risk/effort:** T2 implementation plus T3 boundary review, two sessions. **Locks:** repository-profile and adapter-registry.

**Read:** `subject_adapter.py`, `subject_execution.py`, `adapter_registry.py`, `resource_adapter.py`, `runtime_contracts.py`, `path_boundary.py`, existing delivery grants and sandbox capabilities. **Write:** NEW `src/hive_mind_os/repository_profile.py`, `src/hive_mind_os/schemas/repository-profile.schema.json`, `tests/test_repository_profile.py`; minimal registry additions. Existing authority parsers remain authoritative.

**Steps:**

1. Implement C01 with host-issued tenant/repository identities and immutable profile digests; model-authored names never establish identity.
2. Define separate local-build, code-PR, learning-export and deployment capabilities. Represent absent external grants without preventing eligible read-only planning.
3. Resolve workspace/state/cache roots outside the target where required by existing boundaries. Check case aliases, symlinks/reparse points, parent traversal and Git common-dir/alternates.
4. Register tool adapters by ID/version and fixed argument structure. Target metadata may choose among admitted commands, not add arbitrary executable strings to a privileged host.
5. List safe environment names and secret handles. Secret values stay in narrow host brokers; target build/test children receive none unless a specific scoped integration fixture requires them.
6. Store permitted model-data routing and external export destination/policy. Default unknown sensitivity prevents external disclosure; public immutable dependencies can have an explicit shared cache.
7. Produce a capability report with supported, unavailable, denied and untested statuses. Distinguish a mock adapter from a real probe. N18 supplies strong execution attestation later.
8. Persist the profile outside model-writable target files and provide a read-only digest-bound projection to workers.

**Concrete first profile selection:** N18 starts with an OCI Linux container runner invoked by a fixed-argument host broker on a tenant-dedicated worker VM. N26 starts with Rojo at the EX09 pinned source version through an external CLI adapter. N27 uses a separately attested dedicated Windows VM with installed Studio and EX11 capability probes; it has no assumed portable headless command. Emit `HostToolBinding` records with adapter ID, absolute installed executable path, observed version, binary/image digest, supported platform, fixed argv template and permitted placeholders, safe environment names, timeout/resource policy, probe command/result and receipt digest. Resolve actual versions/paths from the host; absent tools are UNAVAILABLE. Do not ask a small worker to choose a different isolation framework or invent Studio flags.

**Acceptance:** Valid self and external profiles resolve to different subjects; collisions, target-owned authority, root escapes, unrecognized commands and unauthorized destinations reject. Revocation prevents the next effect even if an older profile was valid. Crash during profile write leaves the old version valid or the new complete version; partial writes never activate. Command: `python -m unittest tests.test_repository_profile tests.test_delivery_grants -v`.

**Output/stop:** validated profiles and capability report; no credential creation, live installation or publication. **Rollback:** switch trusted config pointer, retain prior profile. **Escalate:** a required host/runtime/grant absent after discovery, not an ordinary software defect.

## N04 — Add typed mission outcomes and acceptance bindings

**Dependencies:** N01. **Owner:** Architect; separate Integrator/Curator. **Tier/risk/effort:** T2 with T3 schema review, two sessions. **Locks:** mission-contract and acceptance-contract.

**Read:** `brain_kernel/mission_runtime.py`, `brain_kernel/contracts.py`, `brain_kernel/objectives.py`, `portable_plan.py`, `runtime_contracts.py`, `schemas/acceptance-specification.schema.json`. **Write:** NEW `src/hive_mind_os/campaign_contracts.py`, `schemas/campaign-mission.schema.json`, `schemas/work-package.schema.json` under the package schema directory, `tests/test_campaign_contracts.py`; narrow adapters into existing types.

**Steps:**

1. Implement C02/C03/C09 as explicit validated immutable records. Reuse existing digest, timestamp and identifier validators.
2. Require an objective, target boundary, requirement IDs, acceptance IDs, risk, resource allocation, outputs and rollback for each package. Reject missing outcomes rather than filling them with generic prose.
3. Model acceptance as typed checks with required capability, artifact, result and owner; distinguish static, runtime, production-candidate and deployed-observed claims.
4. Map new mission/package states to existing event types through adapters. Document any unavoidable enum/schema extension in the ADR and migration tests.
5. Bind candidate completion to exact commit/tree and required output receipts. An empty/no-change result has its own truthful disposition; it does not count as customer-value implementation.
6. Implement successor graph/contract records retaining parent digests and every requirement. Changed acceptance requires a new version and independent disposition, never edit-in-place.
7. Add compatibility parsing for historical inert plans and explicit fixture mode; do not make historical `candidate/app.txt` behavior the production default.
8. Publish small contract examples and error codes for N08–N27. Use closed schemas so a smaller model can follow exact fields instead of inventing new payloads.

**Acceptance:** Round-trip valid records without digest drift; booleans in integer fields, NaN, missing requirement, orphaned dependency, changed authority, unknown state and inconsistent candidate receipt reject. Old fixtures still parse under their declared version. Command: `python -m unittest tests.test_campaign_contracts tests.test_hive_cortex_contracts -v`.

**Output/stop:** schemas, adapters, positive/negative fixtures and ADR links. No workers launched. **Rollback:** keep versioned readers and select prior admission schema. **Escalate:** actual compatibility conflict, not a formatting preference.

## N05 — Wire progressive context and immutable capsules

**Dependencies:** N03, N04. **Owner:** Builder; separate Curator with Optimizer witness. **Tier/risk/effort:** T1, medium context/privacy risk, two sessions. **Locks:** context-assembly; N19 later extends subject isolation without duplicating this compiler.

**Read:** `context_capsule.py` (`RoundCapsule`, `NodeDelta`), `local_evidence_packet.py`, `brain_kernel/context.py`, `repository_index.py`, existing context/token tests. **Write:** NEW `src/hive_mind_os/campaign_context.py`, `tests/test_campaign_context.py`; narrow `local_dag_runtime.py` and worker packet integration after their owner releases the file lock.

**Steps:**

1. Define `CampaignContextRequest` from trusted subject, node contract, direct dependencies and role purpose. Input includes permitted source/memory handles, never a global unrestricted store.
2. Build one immutable capsule of relevant base facts per subject/snapshot/contract version. Construct node deltas with only the package objective, relevant source bodies, direct receipt summaries and unresolved obligations.
3. Use source symbols and dependency/test maps to select initial files. Put other material behind cold references with digest, size and retrieval reason.
4. Implement bounded retrieval expansion when a worker names a missing symbol/evidence need. Log selection and omission; do not silently truncate acceptance or threat facts.
5. Preserve original artifacts separately from compact summaries. A summary cannot claim unavailable source contents or become authority.
6. Bind provider destination and data policy before sending a packet. Keep packet-mode and native-tool-mode capabilities explicit in receipts.
7. Wire packet assembly into one execution seam used by N08/N13. Keep old fixtures stable; prevent accidental duplicate full previous-report histories.
8. Measure original versus transmitted bytes/tokens using existing ledger distinctions, and have the reviewer inspect one complete expanded packet and its cold-source mapping.

**Acceptance:** Two dependent nodes reuse identical base body digests but receive different deltas; source/contract change invalidates relevant packets. Tests reject cross-subject handles, missing acceptance, stale digests, forged cold refs and target/evaluator leaks. Check deterministic packet equality and meaningful savings on the same fixture without asserting real-model performance. Command: `python -m unittest tests.test_campaign_context tests.test_hive_cortex_context -v`.

**Output/stop:** integrated packet path, snapshots, omission ledger and accounting receipts. **Rollback:** select old packet builder for compatible trusted fixtures; private-boundary requirements still apply. **Escalate:** essential context exceeds capability after bounded expansion, requiring a different route or split, not an owner-led reread.

## N06 — Integrate task reuse, test caching and check invalidation

**Dependencies:** N02, N04. **Owner:** Builder; separate Curator; Optimizer measures overhead. **Tier/risk/effort:** T2, high evidence integrity, two sessions. **Locks:** validation-cache-contract and task-reuse-admission.

**Read:** `task_reuse.py` (`TaskFingerprint`, `TaskReuseIndex`, `classify_reuse`), `test_result_cache.py` (`TestCacheKey`, `TestResultCache`), `verification_adapters.py`, `local_evidence_packet.py`, `tests/test_control_token_economy.py`, `tests/test_task_reuse.py`.

**Write:** NEW `src/hive_mind_os/validation_policy.py`, `tests/test_validation_policy.py`; extend existing cache/reuse models only if C04 requires missing fields, with versioned compatibility. Wire final adapter calls with N14 after its file lock is released.

**Steps:**

1. Inventory every cache-key field and explicitly add missing tenant, evidence trust-domain, adapter/check-set and external-state freshness bindings using a new schema version.
2. Define check purposes `developer`, `independent_candidate`, `integration`, `publication_observation`; identity and purpose are part of receipt admissibility, not cosmetic labels.
3. Call TaskReuseIndex at package admission/resume. Reuse only equivalent completed work; reject branch-name-only or partial-evidence completion.
4. Resolve required checks from the product profile and impact map. Start conservatively: unknown dependency coverage is a miss and a broader check, not a guessed green result.
5. Look up only matching passing test receipts. Keep failures/tampering as evidence. Do not cache network/live-state qualification unless the profile defines valid freshness/input bounds.
6. Add an invalidation report explaining which input changed and which check must rerun. A changed candidate cannot inherit an exact-candidate receipt; component reuse requires its separately complete dependency proof.
7. Record repeated-check reasons and compute duplicate work only within the same purpose/trust boundary. Curator reproduction and CI are legitimate separate checks.
8. Connect N02 counters. Run negative controls before enabling cache hits in production mode; use a feature flag to fall back to actual checks.

**Acceptance:** Repeated identical eligible check executes once; changes to source, tests, lockfile, environment, OS, adapter, policy, tenant or reviewer scope cause correct misses. Builder receipt fails Curator admission. Corrupt entries reject; concurrent publication is atomic; crash cannot create a passing partial result. Command: `python -m unittest tests.test_validation_policy tests.test_control_token_economy tests.test_task_reuse -v`.

**Output/stop:** functioning reuse policy and invalidation receipts, not a promise that tests never repeat. **Rollback:** disable reads from the new cache; retain records and execute checks. **Escalate:** unknown validity forces a miss; it does not require a court on every edit.

## N07 — Add explicit small-model routing and leased repair budgets

**Dependencies:** N02, N03, N04. **Owner:** Optimizer/Builder; separate Curator verifies route/data boundaries. **Tier/risk/effort:** T2, medium provider integration, two sessions. **Locks:** provider-route-binding and local-worker-command.

**Read:** `model_backend.py` (`role_providers`), `brain_kernel/role_runtime.py` (`provider_for`), `local_codex_worker.py`, `token_ledger.py`, existing provider catalog and official EX16–EX18. **Write:** NEW `src/hive_mind_os/campaign_routing.py`, `tests/test_campaign_routing.py`; narrow configuration support in `local_codex_worker.py` and model adapter tests. Do not embed provider catalogs in the kernel or every node.

**Steps:**

1. Implement C05 route selection from task capability, risk and an account-validated catalog. Treat old catalog `verified-current` strings as historical assertions until revalidated.
2. Keep provider-specific model ID, effort/thinking schema and supported limits in adapters. Deterministic tasks choose no model.
3. Make the local worker accept an explicit effective model route and record the launched route; no silent default model for a node claiming small-model efficiency.
4. Reject route/data-policy mismatch before transmitting context. Do not pass provider/forge credentials into the target sandbox.
5. Define cumulative token/time/tool allowances from the admitted lease. Record unknown usage honestly. Stop/checkpoint before exceeding a known hard allocation.
6. Implement classified transient retry and focused repair limits from RUNBOOK. Route escalation carries the failure/hypothesis, delta context and retained candidate, so a bigger model does not repeat discovery.
7. Qualify candidate routes on separate development tasks from N02. Minimum safe route is measured per task class; security/promotion judgment can use a stronger independent route.
8. Add fallback behavior: another qualified available provider with allowed data policy, or a typed capability/budget block. Do not invent an unavailable provider version or increase spending authority.

**Acceptance:** Mechanical job uses no provider; bounded job passes its actual small-model flag; unsupported effort is rejected/mapped in the right adapter; route usage receipt matches observed configuration. Fake clock/usage cases cover hard exhaustion, transient retry, repeated identical failure and escalation without duplicate effects. Command: `python -m unittest tests.test_campaign_routing -v` plus existing model/worker focused suites selected from N00.

**Output/stop:** explicit routing and measured development qualification receipts; no guarantee of universal smaller-model ability. **Rollback:** select prior admitted route map for new jobs. **Escalate:** proven task-class capability gap, not routine first-test failure.
