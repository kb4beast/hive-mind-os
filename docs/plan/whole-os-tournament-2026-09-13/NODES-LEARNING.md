# Learning, tenant boundaries, and Roblox implementation nodes

This appendix specifies future implementation work only. It does not report implemented capabilities or executed tests. Nodes N18–N27 belong to the whole-OS tournament handoff. Dependencies reference the main DAG. Existing paths and symbols below were inspected in the repository; every path marked **NEW** is a proposed output, not an existing capability. EX09 (Rojo) and EX11 (Studio testing) refer to the primary-source entries in the source appendix; absent, unpinned, or inapplicable source entries remain explicit evidence obligations.

## Shared execution and data rules

Each node may be implemented locally after the future execution authority described by the main runbook is active. Ordinary target-app code stays in the target repository. The contribution from an external-app mission to Hive Mind OS is a lessons-only draft. Target code, patches, assets, transcripts, secrets, and private runtime state do not enter that contribution. One mandatory safe draft obligation exists per stable `(tenant_id, repository_id, external_mission_id)`, including a truthful withheld/no-exportable-lesson stub when necessary. Retries, DAG nodes, polls, worker attempts, and restarts do not create new obligations. Upstream publication is conditional on the configured destination and existing export authority. A retained draft is never reported as an exported PR.

All proposed structured records use strict `schema_version: 1`, reject unknown fields, reject booleans as integers, reject NaN/infinity, use full pinned Git identities where Git identities are required, and use canonical `sha256:<64 lowercase hex>` artifact digests and UTC RFC 3339 timestamps. Identity fields are nonempty strings supplied by a trusted adapter. Tenant IDs, repository IDs, evidence locators, and private digests never become public merely because a field is named provenance. Use opaque export-safe receipt tokens when public disclosure is not authorized.

Common node receipts contain `node_id`, `run_id`, `attempt_id`, `input_digest`, `candidate_digest`, `acceptance_digest`, `environment_digest`, `actor_id`, `reviewer_id`, `result`, `evidence_refs`, `resource_use`, and `recorded_at`. Record failed, blocked, omitted, and inconclusive outcomes. Evidence caches key on immutable input, acceptance, dependency, toolchain, policy, and environment versions; branch names and file timestamps are insufficient. Reuse unchanged passing evidence, run focused checks while editing, and execute the repository CI gate on the final integrated candidate. Commands below are proposed commands for the future implementer; they have not been run for this documentation task.

Roles are separately identified. The Builder may choose edit order and routine implementation details inside the node contract. Independent Curator review does not require repeated restatement of the plan. High-risk boundary changes retain T3 review. An evidence, authority, isolation, or contract change invalidates the affected receipt and triggers the specific recheck; unrelated nodes continue. Effort estimates count focused engineering sessions, not elapsed-time or cost promises. Node-local status enums are distinct from kernel mission and work-item states; expose them through adapters instead of silently widening existing enums. N03's profile-selection receipt supplies exact installed executable paths, versions, image digests, and command argv; a model must not guess these. Secret scanners cannot provide a perfect non-leakage guarantee: enforced custody, minimal disclosure, review, and withheld safe stubs remain necessary.

## N18 — Enforce the tenant and host execution boundary

**Dependencies:** N03, N04. **Owner:** Integrator with Builder implementation. **Independent reviewer:** Curator specializing in sandbox escape tests. **Risk/tier:** security boundary, high/T3; strong isolation required for untrusted code. **Effort:** 3–5 sessions.

**Read existing:** `src/hive_mind_os/sandbox.py` (`SandboxSpec`, `SandboxRunner`, `_persist`); `src/hive_mind_os/verification_adapters.py` (`SandboxRequirements`, `SandboxCapabilities`, `SandboxAdapter`, `LocalProcessSandbox`, `UnavailableSandbox`, `verify_repository`); `tests/test_sandbox.py`; `tests/test_verification_adapters.py`. The existing process sandbox honestly reports no enforced filesystem/network isolation.

**Write allowlist:** **NEW** `src/hive_mind_os/isolated_execution.py`, `src/hive_mind_os/schemas/isolation-attestation.schema.json`, `tests/test_isolated_execution.py`, and `docs/architecture/ADR-WOS-N18-isolation.md`; N18 owns the initial isolation registration seam in `verification_adapters.py`, publishes its contract, and releases that file before N14 integrates acceptance scheduling. N18 does not wait for N14. Keep the old process backend available for explicitly trusted work, with truthful capabilities.

**Inputs/outputs:** Consume N04 subject/authority binding plus N03 command profile. Produce `IsolationAttestation(backend_id, backend_version, image_digest, tenant_id, repository_id, filesystem_scope, network_policy_digest, credential_policy_digest, writable_mounts, resource_limits, probe_suite_digest, probe_result, expires_at)`. `probe_result` is `ENFORCED|FAILED|UNAVAILABLE`; only ENFORCED admits untrusted execution. Return a separate `ExecutionResult` with exit status, timeout, cleanup receipt, and sanitized artifact references.

**Implementation steps:**

1. Define an isolation backend protocol with capability discovery, materialization, execution, artifact collection, and idempotent teardown. The model cannot manufacture capabilities by filling a record.
2. Implement the first backend as an OCI Linux container runner invoked through a trusted host broker with fixed argv from N03's profile-selection receipt. Run each untrusted tenant on a tenant-dedicated worker VM with a pinned container image. A Windows Roblox Studio runner is a distinct dedicated Windows VM capability and remains unavailable until independently attested. Missing backends return UNAVAILABLE; never substitute `LocalProcessSandbox`.
3. Mount only the selected target snapshot, bounded dependency cache, writable work directory, and temporary output directory. Do not mount the host home, Hive checkout, Docker/control socket, oracle store, or another tenant's artifacts.
4. Deny network by default. Allow approved dependency retrieval only through the profile's bounded broker/cache; target tests cannot widen destinations. Start workers without provider, forge, platform, or export credentials.
5. Configure process-tree, wall-time, output, disk, CPU, and memory bounds. Host-side delivery and credential brokers remain outside the untrusted process.
6. Run real filesystem, child-process, network, and forbidden-mount probes once per backend/image/policy version; bind the attestation to the exact configuration. Cached attestations expire and invalidate when that configuration changes.
7. Copy artifacts through a host-controlled boundary after execution. Check allowed relative paths, links, sizes, and content classifications before retention.
8. Persist allocation and teardown identities before effects. Recover interrupted runs by inspecting the same allocation, terminating orphaned execution, and retaining an outcome receipt.

**Acceptance:** Positive: permitted target build reads its own inputs, writes outputs, and leaves no processes. Negative: host-home read, adjacent tenant read, network exfiltration, credential inheritance, symlink escape, and false capability declaration fail. Crash: kill the controller during execution; restart reaps or resumes the same allocation without duplicate execution. Unit command: `python -m unittest tests.test_isolated_execution tests.test_verification_adapters -v`. Real-backend probes are required separately; a skipped integration probe is UNAVAILABLE, not a pass.

**Locks/rollback/escalation:** Lock `isolation-backend:<host>` for allocation changes and the verification registration file for integration only. Roll back backend selection to the prior attested version; preserve receipts. Unsupported isolation blocks untrusted execution, not documentation or planning. Escalate only a newly required host capability or authority outside the established lease.

## N19 — Partition memory, caches, logs, and evidence by subject

**Dependencies:** N05, N18. **Owner:** Architect/Builder. **Independent reviewer:** Curator with Integrator contract testimony. **Risk/tier:** confidentiality boundary, high/T3. **Effort:** 2–4 sessions.

**Read existing:** `src/hive_mind_os/brain_kernel/memory.py` (`MemoryArtifactStore`, `MemoryAccess`, `RetrievalRequest`, `MemoryCatalog`); `src/hive_mind_os/brain_kernel/contracts.py` (`MemoryRecord`); `src/hive_mind_os/resource_adapter.py` (`ConservativeResourceAdapter`); `src/hive_mind_os/local_evidence_packet.py` (`build_source_packet`); `tests/hive_cortex/test_learning_poisoning.py`. Current record scope filtering is useful but has no tenant identity in `MemoryAccess` or `RetrievalRequest`.

**Write allowlist:** **NEW** `src/hive_mind_os/tenant_memory.py`, `src/hive_mind_os/schemas/subject-memory-boundary.schema.json`, `tests/test_tenant_memory.py`, and `docs/architecture/ADR-WOS-N19-memory-boundaries.md`. Modify N05's context integration seam only with its owner's agreement; do not duplicate its context compiler.

**Inputs/outputs:** Consume trusted subject identity, data authority, and N18 attestation. Produce `SubjectMemoryBoundary(tenant_id, repository_id, private_store_id, cache_partition_id, logging_partition_id, provider_policy_digest, encryption_profile_id, retention_policy_digest)` and `ScopedMemoryHandle(boundary_digest, role, mission_id, permitted_scopes)`. Public retrieval accepts only a handle issued by the trusted host, never raw caller-chosen scope authority. States: `BOUND|ACTIVE|REVOKED|QUARANTINED`.

**Implementation steps:**

1. Implement a namespace resolver keyed by trusted tenant plus repository identities. Keep user-facing repository names as metadata; identical names must not collide.
2. Wrap existing memory catalogs with a subject handle. Resolve reads, writes, vector retrieval, context assembly, and artifact references through that handle. Preserve existing temporal and role filters.
3. Namespace dependency caches, model caches, task reuse, output artifacts, and logs. Shared public immutable dependencies may be shared only by explicit public classification; private target-derived artifacts remain partitioned.
4. Bind model requests to the subject's configured provider-data policy. Deny requests whose context sensitivity is not allowed for that provider; do not equate a local workspace with authority to send data externally.
5. Retain sensitive material only in the configured encrypted tenant store with a managed key reference. Do not implement home-grown cryptography or write keys into Git. Missing encryption capability prevents sensitive retention and emits a typed obligation.
6. Persist sanitized metadata before storing content; use the same boundary for errors and exception traces. Do not place raw prompts, outputs, environment dumps, or private locators in global logs.
7. Make retention and revocation remove retrieval access immediately while preserving authorized audit metadata. Encrypted evidence access remains separately authorized.
8. Add migration that leaves legacy data in a `LEGACY_UNBOUND` quarantine until assigned through a trusted import; never infer tenant ownership from a filename.

**Acceptance:** Positive: same-subject scoped retrieval and cache reuse work. Negative: tenants A and B have distinct trusted tenant IDs but colliding repository names, local mission/record IDs, paths, and lesson digests; neither can retrieve the other's content. Global applicability cannot widen a tenant boundary; unauthorized provider routing fails. Crash: interruption after artifact write but before catalog registration leaves an inaccessible orphan resolved by idempotent reconciliation. Command: `python -m unittest tests.test_tenant_memory tests.hive_cortex.test_learning_poisoning -v`.

**Locks/rollback/escalation:** Partition lock `memory:<tenant>:<repository>`; no global lock for ordinary reads. Roll back adapter binding and mark newly created records inactive; never re-expose quarantined legacy records. Boundary ambiguity blocks the affected retrieval/export lane. A new provider or encryption authority requires an external grant; existing grants persist across retries.

## N20 — Extract abstract lessons into a private draft pipeline

**Dependencies:** N19. **Owner:** Optimizer/Builder. **Independent reviewer:** Curator; separate Advocate and Cross-Examiner evaluate each material learning claim. **Risk/tier:** learning and data export boundary, high/T3. **Effort:** 2–3 sessions.

**Read existing:** `src/hive_mind_os/brain_kernel/learning_runtime.py` (`LearningSignal`, `LessonApplicability`, `LessonGenerator`, `lesson_memory_record`); `src/hive_mind_os/brain_kernel/challengers.py` (`lesson_from_document`); `src/hive_mind_os/repository_learning.py` (`PatternLesson`); `tests/test_hive_cortex_learning.py`. `lesson_memory_record` creates ACTIVE records; do not call it for a draft.

**Write allowlist:** **NEW** `src/hive_mind_os/lesson_drafts.py`, `src/hive_mind_os/schemas/lesson-draft.schema.json`, `tests/test_lesson_drafts.py`, and `docs/architecture/ADR-WOS-N20-draft-learning.md`. Leave kernel `MemoryState` unchanged; drafts live in a separate store until independently admitted.

**Inputs/outputs:** Input is N19-scoped outcome evidence plus an export classification policy. Output the canonical C07 `LessonDraft(draft_id, document_status, processing_state, origin_subject_token, origin_mission_token, statement, applicability, outcome_class, evidence_tokens, private_custody_token, confidence_basis, counterexamples, disposition_refs, generator_id, reviewer_id, sanitization_receipt_digest, export_policy_digest, withheld_reason_code, created_at)`. `document_status="DRAFT"` is immutable. `processing_state` is exactly `CAPTURED_PRIVATE|CANDIDATE_PRIVATE|SANITIZED_DRAFT|REVIEWED_DRAFT|COMMITTED_DRAFT|DRAFT_PR_OPEN|BLOCKED_EXPORT_DESTINATION|BLOCKED_EXPORT_AUTHORITY|QUARANTINED_EXPORT|EXPORT_FAILED_RETRYABLE`. No overloaded `status` field or free-form extensions. Optional `withheld_reason_code` and the private custody token describe withheld content without disclosing the sensitive reason. Reviewer and sanitization receipt fields are null before their stages and mandatory before REVIEWED_DRAFT.

**Implementation steps:**

1. Define strict bounds: statement at most 2,000 characters, applicability/counterexamples at most 20 entries each, no embedded binary fields, and no arbitrary record extensions. Bound model input using N05 evidence packets.
2. Derive candidates only from retained outcomes and citations. State uncertainty and contrary observations; one anecdote may create a draft but cannot claim repeated validation.
3. Generate the draft inside the tenant boundary. Keep source code, transcripts, identifiers, raw logs, and private locators out of the proposed public projection.
4. Build an allowlisted export projection using generalized claims, authorized public references, aggregate outcomes, and opaque private evidence tokens. Never export private evidence bodies or unsalted private content fingerprints by default.
5. Apply deterministic content and path checks, copied-source detection, known-secret/canary checks, and independent semantic review of the final projection. Regex scanning is defense in depth, not a proof that arbitrary secrets cannot leak.
6. If safe abstraction cannot be established, retain full evidence in the encrypted tenant store and create a safe stub with `withheld_reason_code`; review that stub through the same processing states. Keep the original content's non-exported obligation. Do not repeatedly ask a model to rephrase a secret until a scanner passes it.
7. Persist reviewer identity and disposition against the exact sanitized bytes. A content change invalidates review. Append processing transitions in the control ledger without rewriting the reviewed body merely to announce a later state. Drafts are data, never instructions to a tool, provider, memory catalog, or champion selector.
8. Expose only reviewed or withheld safe projections to N21. Reject all draft states at the accepted-lesson/challenger boundary.

**Acceptance:** Positive: generalized evidence-backed lesson becomes REVIEWED_DRAFT without source fragments. Negative: encoded secret canary, private URL, copied code, injected instructions, self-review identity, and invented evidence are rejected or withheld. Crash: restart after sanitization recovers the same content-addressed draft and does not create duplicate claims. Command: `python -m unittest tests.test_lesson_drafts tests.test_hive_cortex_learning -v`.

**Locks/rollback/escalation:** Lock `draft:<subject>:<external-mission-id>:<claim-id>`; extraction of unrelated missions is parallel. Roll back by appending quarantine/retraction facts, preserving private evidence. Sanitization failure blocks export of that content only. Never waive the boundary to meet a file-output obligation.

## N21 — Retain mandatory draft lessons and publish only configured draft contributions

**Dependencies:** N15, N20. **Owner:** Integrator/Builder. **Independent reviewer:** Curator with Steward recovery review. **Risk/tier:** repository publication, high/T3 at the external effect boundary. **Effort:** 2–3 sessions.

**Read existing:** `src/hive_mind_os/cortex/github/delivery_adapter.py` (`ControlledGitHubDelivery.draft_pr_adapter`, `branch_head`, `_own_open_draft_head`); `src/hive_mind_os/cortex/github/grants.py`; `src/hive_mind_os/cortex/github/push_executor.py`; N15 delivery contract. Reuse delivery effects and reconciliation; do not create a second forge implementation.

**Write allowlist:** **NEW** `src/hive_mind_os/lesson_delivery.py`, `src/hive_mind_os/schemas/lesson-delivery-obligation.schema.json`, `tests/test_lesson_delivery.py`, and `docs/architecture/ADR-WOS-N21-lesson-contribution.md`; register with the N15 router through its agreed seam. Future target artifact path: `.hivemind/lessons/drafts/<mission-id>.md`. Future optional upstream path: `docs/lessons/drafts/<draft-id>.md`.

**Inputs/outputs:** `LessonDeliveryObligation(external_mission_id, origin_mission_token, subject_id, safe_draft_digest, local_artifact_path, local_commit_sha, upstream_repository_id, upstream_path, export_authority_digest, delivery_idempotency_key, obligation_state, upstream_pr_url, upstream_head_sha, failure_code)`. The stable private key is `(tenant_id, repository_id, external_mission_id)`; export only the opaque mission token. Optional external fields are null until configured/observed. Obligation states are `REQUIRED|RETAINED_DRAFT|COMMITTED_DRAFT|UPSTREAM_PENDING|DRAFT_PR_OPEN|BLOCKED_EXPORT_AUTHORITY|BLOCKED_EXPORT_DESTINATION|EXPORT_FAILED_RETRYABLE|QUARANTINED_EXPORT`. Update the associated LessonDraft's C07 `processing_state` separately; its `document_status` stays DRAFT.

**Implementation steps:**

1. Create exactly one durable obligation when a stable external mission is admitted. Enforce uniqueness on its trusted tenant/repository/mission key. Retries, node execution, polling, and process restarts reuse it; a genuinely new mission receives a new ID.
2. At checkpoint/closeout, select N20's reviewed projection or safe withheld/no-exportable-lesson stub. Render explicit `document_status: DRAFT` and separate `processing_state`; never invent a learning success.
3. Write the safe draft to the target mission's isolated branch under the exact path above. Commit only with target repository write authority; read-only tenants retain the artifact and a `LOCAL_COMMIT_AUTHORITY_MISSING` obligation. Do not misreport it as checked in.
4. Keep target application code delivery in the target repository. The upstream Hive branch has only the designated lessons file and necessary machine-readable draft metadata if the main contract explicitly permits it.
5. When upstream destination/export authority is absent, record the corresponding blocked state. Continue authorized target code work; never send private content to a guessed repository.
6. For configured publication, initialize a separate upstream checkout from its permitted base. Stage exact allowed paths; inspect staged names and final bytes, file modes, symlinks, and PR title/body before passing N15 the effect request.
7. Set forge draft status true. Bind destination, draft digest, allowed paths, sanitized body, and branch identity into the effect idempotency key. Do not auto-merge, auto-adopt, or enable retrieval after publication.
8. Reconcile remote branch/PR observations after an uncertain push/create response. Update the obligation only from observed commit/PR identifiers; never create a second PR merely because the first response timed out.

**Acceptance:** Positive: target code PR and separate lessons-only upstream draft coexist; many retries/nodes/polls of one mission retain one obligation. Negative: extra source file, private body, non-draft PR, wrong destination, or missing grant stops publication. Crash: interruption after remote create yields one PR and one obligation after recovery. Commands: `python -m unittest tests.test_lesson_delivery -v` plus N15's focused delivery tests. Offline fake-forge tests are not live delivery evidence.

**Locks/rollback/escalation:** Lock `lesson-delivery:<destination>:<draft-id>` and the owned upstream branch only. Rollback uses N15's owned-draft close/branch cleanup contract; retain audit evidence. Missing export setup blocks only export. Reuse established grants without asking for repeated permission.

## N22 — Import first/final snapshots with explicit source and brief provenance

**Dependencies:** N00, N04. **Owner:** Explorer/Builder. **Independent reviewer:** Curator; source Advocate, Cross-Examiner, and Judge identities remain separate. **Risk/tier:** source and evaluation integrity, moderate until source execution. **Effort:** 2–3 sessions.

**Read existing:** `src/hive_mind_os/repository_learning.py` (`RepositoryScout`, `RepositoryLearningCurriculum`); `src/hive_mind_os/ingestion.py` (`SourceExhibit`, `LicenseRecord`); `src/hive_mind_os/source_docket.py`; `src/hive_mind_os/pit_oracle.py` (`PointInTimeOracle.build_environment`); `docs/architecture/HARDENED_VISION_CONTRACT.md`. Existing PIT exports all parent ancestors, so it cannot be reused unchanged for endpoint-only input.

**Write allowlist:** **NEW** `src/hive_mind_os/endpoint_curriculum.py`, `src/hive_mind_os/schemas/endpoint-episode.schema.json`, `tests/test_endpoint_curriculum.py`, and `docs/architecture/ADR-WOS-N22-endpoint-curriculum.md`. Preserve strict PIT as a separate mode; the ADR documents coexistence rather than replacing its no-future-evidence rule.

**Inputs/outputs:** `EndpointEpisodeManifest(episode_id, source_record_id, mode, first_commit, first_tree_digest, final_commit, final_tree_digest, readme_digest, readme_origin_commit, brief_visibility, repository_family_id, dataset_split, dependency_manifest_digest, fixture_manifest_digest, source_dispositions, obligation_refs)`. `mode` is `endpoint_reconstruction`; `brief_visibility` is `initial_readme|provided_current_readme|owner_authored_brief`. Canonical C08 `dataset_split` is exactly `training|development|promotion_holdout`. States: `REGISTERED|SOURCE_ADMITTED|BLOCKED_SOURCE|DEGENERATE_EPISODE`.

**Implementation steps:**

1. Capture source URI, retrieval time, selected immutable endpoints, captured artifact digests, license exhibit, and supplied README provenance. Never call a moving branch name a pinned final commit.
2. Admit each required source through N00's court/disposition registry. Distinguish scouting eligibility, ingestion permission, and reuse/export permission; do not assume their current license allowlists are equivalent.
3. Define first as the explicitly selected root/baseline snapshot and final as the pinned reference endpoint. Multiple roots require a recorded choice; the importer may not silently guess a lineage.
4. Export endpoint snapshots without intermediate history, hooks, remotes, alternates, reflogs, or a source mirror in the learner package. Preserve original identities in the custodian manifest.
5. Inventory submodules, LFS pointers, assets, generated inputs, dependencies, and external configuration. Resolve immutable artifacts or emit itemized obligations; do not mark partially imported source complete.
6. Classify README visibility. A current README supplied as the target brief is legitimate endpoint-task input but is not historical evidence available at the first commit.
7. Group forks, templates, and close derivatives into repository families before training/development/promotion_holdout assignment. Record assignment once and preserve rejected or unusable examples.
8. If endpoints are identical, mark DEGENERATE_EPISODE and exclude the episode from improvement claims. Publish learner-visible and evaluator-private package manifests separately for N23.

**Acceptance:** Positive: learner package contains only baseline plus declared brief. Negative: intermediate `.git` objects, unknown license, unresolved required assets, unpinned refs, and hidden final source in README packaging fail admission. Crash: import resumes from verified exhibit digests without duplicate source claims or changing dataset split. Command: `python -m unittest tests.test_endpoint_curriculum tests.test_repository_learning -v`.

**Locks/rollback/escalation:** Lock `source:<repository-family>:<endpoint-pair>` during capture and split assignment. Source material is never executed here. Rollback revokes package admission while retaining docket entries. Missing source/license evidence blocks that example, not the entire corpus.

## N23 — Keep final targets and held-out evaluators outside learner custody

**Dependencies:** N18, N22. **Owner:** Curator/Builder with an independently identified evaluator operator. **Independent reviewer:** security Curator and separate Judge. **Risk/tier:** evaluation trust boundary, high/T3. **Effort:** 3–4 sessions.

**Read existing:** `src/hive_mind_os/pit_oracle.py` (`PITEnvironment`, `SealedPrediction`, `seal_prediction`, `recover_sealed_prediction`, `verify_environment`, `reveal`); `src/hive_mind_os/brain_kernel/evaluation_runtime.py` (`EvaluationIdentities`, `HoldoutSeal`, `SealedHoldout`); `tests/test_pit_oracle.py`. Existing Git-object checks are narrow local evidence, not proof that the learner cannot read the oracle directory or internet.

**Write allowlist:** **NEW** `src/hive_mind_os/endpoint_oracle.py`, `src/hive_mind_os/schemas/endpoint-seal.schema.json`, `tests/test_endpoint_oracle.py`, and `docs/architecture/ADR-WOS-N23-evaluator-custody.md`. Changes to legacy PIT, including shared-tree fixes, require separate focused tests in `tests/test_pit_oracle.py` and coordination with its owner.

**Inputs/outputs:** Consume N22 package manifests and N18 enforced isolation. Produce `EndpointSeal(episode_id, input_manifest_digest, candidate_tree_digest, learner_variant_digest, prompt_memory_digest, tool_profile_digest, rubric_digest, budget_digest, learner_id, evaluator_id, sealed_at, seal_digest)` and `CustodyReceipt(store_id, access_policy_digest, object_inventory_digest, contamination_probes, status)`. States: `INPUT_SEALED|LEARNER_RUNNING|CANDIDATE_SEALED|EVALUATOR_RUNNING|CONTAMINATED|BLOCKED_ENVIRONMENT`.

**Implementation steps:**

1. Put final source, final-derived fixtures, rubric internals, private reference identities, and source mirrors in an evaluator-owned store outside all learner mounts, credentials, caches, and model context.
2. Give the learner a synthetic baseline repository or plain snapshot, declared brief, pinned permitted dependencies, and public acceptance instructions. Do not provide the original final tree or intermediate objects.
3. Disable learner access to external forge metadata, solution search, previous episode answers, and unapproved documentation. Dependency retrieval uses the predeclared broker manifest, not arbitrary outbound network.
4. Attest physical/OS boundary checks and enumerate learner-visible Git objects in one deterministic batch. Shared content already present in the permitted baseline is allowed; forbid hidden commit identities and final-exclusive objects rather than every matching target tree hash.
5. Bind the immutable candidate tree and all context/tool/rubric versions into one durable seal. Validate identities differ and atomically append the seal before any evaluator access can reveal target-derived outcomes.
6. Evaluate through a separate process/identity. Send the learner only permitted aggregate outcomes; holdout internals and reference patches stay private. Detailed repair feedback converts the exposed episode into development data for subsequent runs.
7. On any leakage, mark CONTAMINATED and exclude the score from promotion. Public-repository model-pretraining contamination remains an explicit caveat; absence cannot be inferred from successful filesystem probes.
8. Recover an interrupted run from durable package, seal, and access receipts. Reject a second different seal or a changed candidate after seal; create a new development attempt instead.

**Acceptance:** Positive: sealed candidate can be graded; baseline-shared tree remains legal. Negative: final-only blob, oracle mount, model-memory answer, target-before-seal access, changed candidate, and impersonated evaluator fail. Crash: restart before/after seal produces exactly one intact seal and no early reveal. Commands: `python -m unittest tests.test_endpoint_oracle tests.test_pit_oracle -v`; run N18 real-boundary probes for integration evidence.

**Locks/rollback/escalation:** Lock `episode:<id>:seal` and evaluator custody grants. Revoke learner/evaluator allocations on contamination, retain encrypted evidence, and invalidate derived scores. Do not rerun a contaminated holdout as though fresh.

## N24 — Grade working behavior rather than copying the reference tree

**Dependencies:** N14, N23. **Owner:** Optimizer/Builder. **Independent reviewer:** Curator with domain expert testimony. **Risk/tier:** evaluation and promotion evidence, high/T3. **Effort:** 2–4 sessions.

**Read existing:** `src/hive_mind_os/pit_oracle.py` (`EpisodeGrade`, `grade`, `run_scripted_episode`); `src/hive_mind_os/brain_kernel/evaluation_runtime.py` (`SurfaceKind`, `SurfaceResult`, evaluation verdict logic); `src/hive_mind_os/verification_adapters.py` (`VerificationRegistry`, `SealedCommand`, `verify_repository`). Existing changed-path Jaccard is only a diagnostic metric and cannot establish functional or production equivalence.

**Write allowlist:** **NEW** `src/hive_mind_os/functional_evaluation.py`, `src/hive_mind_os/schemas/functional-evaluation.schema.json`, `tests/test_functional_evaluation.py`, and `docs/architecture/ADR-WOS-N24-functional-evaluation.md`. Register domain acceptance through N14 rather than duplicating its validation scheduler.

**Inputs/outputs:** Consume candidate seal, immutable reference endpoint, N14 acceptance specification, domain/environment profile, and comparator pins. Emit `FunctionalEvaluation(episode_id, candidate_digest, rubric_digest, environment_digest, reference_health, required_checks, capability_results, quality_metrics, security_results, resource_use, contamination_status, evaluator_id, verdict, evidence_refs)`. Check outcomes are `PASS|FAIL|UNAVAILABLE|INCONCLUSIVE`; verdict is `PASS|FAIL|BLOCKED_ENVIRONMENT|CONTAMINATED|INCONCLUSIVE`.

**Implementation steps:**

1. Freeze an externally observable rubric before execution: required behavior, tolerances, inputs, expected outcomes, performance budget, and mandatory security checks. The Builder cannot edit that rubric or its evaluator fixtures.
2. Derive reference behavior in evaluator custody and test the reference itself. Record baseline failures and ambiguous README claims; final commit does not automatically mean correct or production ready.
3. Implement a domain adapter protocol that runs the same observable checks against reference and candidate with equivalent dependencies, workloads, and environmental limits.
4. Grade required behavior and regression/security budgets first. Treat implementation structure, filename overlap, textual similarity, and patch size as optional diagnostics, never the primary success criterion.
5. Record build, runtime, performance, reliability, and resource evidence separately. Missing runtime capability yields UNAVAILABLE/BLOCKED_ENVIRONMENT, not a zero or a passing static substitute.
6. Measure successful accepted outcomes per cost and elapsed time only among candidates satisfying admission gates. Retain unsuccessful comparators and their pinned versions; use multiple comparators before a superiority claim.
7. Cache invariant checks for exact immutable input/environment/rubric digests. During repair run affected tests, then one independent final evaluation on the sealed candidate. Do not repeat all checks merely because another role reads the same result.
8. Bind the final report to seal and artifacts. Invalidate only affected evidence when candidate, dependency, toolchain, rubric, or isolation changes; deny post-hoc threshold changes intended to make a candidate pass.

**Acceptance:** Positive: a differently organized implementation satisfying the observable contract passes. Negative: exact clone with broken runtime fails; changed evaluator, unavailable runtime disguised as success, leaked target, fabricated score, and failed security invariant fail. Crash: restart recovers finished check receipts and executes only missing valid checks without changing sealed inputs. Command: `python -m unittest tests.test_functional_evaluation -v` plus N14's selected acceptance tests.

**Locks/rollback/escalation:** Lock `evaluation:<seal>:<rubric>` for report publication; checks can run concurrently under the profile budget. Rollback quarantines the report and dependent promotion eligibility. Ambiguous expected behavior requests a rubric disposition; it does not justify guessing a favorable score.

## N25 — Separate app learning from Hive learning and champion promotion

**Dependencies:** N02, N19, N24. **Owner:** Optimizer/Builder. **Independent reviewer:** Curator; distinct promotion Judge. **Risk/tier:** self-improvement and authority, high/T3. **Effort:** 2–4 sessions.

**Read existing:** `src/hive_mind_os/brain_kernel/challengers.py` (`AcceptedLesson`, `lesson_from_document`, `ChallengerGenerator`, `classify_forbidden`); `src/hive_mind_os/brain_kernel/evaluation_runtime.py`; `src/hive_mind_os/brain_kernel/promotion.py` (`PromotionAuthority`, `PromotionDecision`); `src/hive_mind_os/brain_kernel/learning_runtime.py`; `src/hive_mind_os/learning.py` (`LearningPromotionGate`). Do not use the simple success-rate gate alone as proof of scoped independent promotion.

**Write allowlist:** **NEW** `src/hive_mind_os/scoped_learning.py`, `src/hive_mind_os/schemas/learning-route.schema.json`, `tests/test_scoped_learning.py`, and `docs/architecture/ADR-WOS-N25-scoped-promotion.md`. Integrate at existing accepted-lesson and registry boundaries under their file-owner locks; do not replace the promotion kernel.

**Inputs/outputs:** `LearningRoute(origin_subject_id, learning_scope, destination_subject_id, source_evidence_refs, candidate_kind, authorization_digest, accepted_lesson_digest)` where scope is `target_app|hive_os|export_draft`. `ScopedChallenger(subject_boundary_digest, champion_id, parent_digest, candidate_digest, evaluation_plan_digest, evaluator_id, verdict_ref, promotion_state)`. States: `PROPOSED|EVALUATING|RETAIN_CHAMPION|ELIGIBLE|PROMOTED|ROLLED_BACK|QUARANTINED`.

**Implementation steps:**

1. Bind every learning signal to N19's subject handle. Route product-specific improvements to that app's registry and memory; do not infer Hive scope from generic wording.
2. Reserve Hive champion proposals for Hive-authorized work or an independently adopted abstract lesson. An external draft cannot be converted to AcceptedLesson by changing a status string.
3. Maintain separate champion registries and content stores per subject. Resolve parent and challenger identifiers within the subject boundary; reject cross-subject references even when IDs or digests match.
4. Generate immutable challengers using existing machinery. Keep proposal, builder, evaluator, and promotion identities distinct. Governance/policy mutation is not granted by a successful learning episode.
5. Evaluate on N24's held-out functional/adversarial surfaces using N02's predeclared budgets and comparator rules. Training wins, leaked holdouts, and repeated attempts on exposed answers cannot count as fresh improvement.
6. Promote only when the independently authenticated verdict and current parent digest match. Use the existing authority and compare-and-swap transaction; a stale champion triggers reevaluation or a new proposal, not forced overwrite.
7. After promotion, observe the predeclared regression window and retain the prior champion. Record outcome attribution, contrary evidence, and failure receipts in the same subject partition.
8. Roll back through the existing versioned path on a supported regression verdict. Never copy target source into Hive as a rollback shortcut or grant new authority because a challenger performed well.

**Acceptance:** Positive: an app challenger improves that app while Hive memory/registry digests remain unchanged; a separately adopted Hive lesson can seed a Hive challenger. Negative: draft ingestion, cross-tenant parent, self-grading, stale parent, leaked holdout, and altered thresholds are denied. Crash: interruption after promotion transaction recovers the same champion and receipt, with no second promotion. Command: `python -m unittest tests.test_scoped_learning -v` plus existing promotion and challenger suites selected by changed integration paths.

**Locks/rollback/escalation:** Lock `champion:<subject>:<surface>` only during compare-and-swap. App experiments run in parallel with Hive experiments under independent budgets. Rollback restores the previous subject champion and retains dissent. New policy/spending/credential authority is an external obligation, never learned behavior.

## N26 — Add the Roblox build and static profile adapter

**Dependencies:** N03, N18, N22. **Owner:** Integrator/Builder. **Independent reviewer:** Curator with Roblox build-tool expert testimony. **Risk/tier:** untrusted build tooling, moderate; isolation capability changes retain high/T3 review. **Effort:** 2–4 sessions.

**Read existing:** `src/hive_mind_os/verification_adapters.py` (`VerificationAdapter`, `SealedCommand`, `VerificationRegistry`); `src/hive_mind_os/resource_adapter.py`; N03 profile-selection receipt and N22 source manifests. No Roblox adapter was identified in the inspected repository. EX09 supplies the Rojo primary-source baseline; verify its pinned version, formats, and platform constraints before integration is declared complete.

**Write allowlist:** **NEW** `src/hive_mind_os/roblox_profile.py`, `src/hive_mind_os/schemas/roblox-profile.schema.json`, `tests/test_roblox_profile.py`, `tests/fixtures/roblox_profile/README.md`, and `docs/architecture/ADR-WOS-N26-roblox-profile.md`. Fixture implementation files are future node outputs only. Registry edits occur through N03/N14 ownership seams; do not globally override language detection.

**Inputs/outputs:** `RobloxProfile(profile_id, profile_selection_receipt_digest, source_refs, toolchain_versions, executable_paths, executable_digests, image_digest, project_manifest_paths, source_roots, package_lock_digests, build_commands, static_check_commands, artifact_paths, asset_manifest_digest, runtime_requirements, capability_status)`. Exact installed paths, versions, image digest, and sealed command argv come from N03's verified host receipt, not guessed shell strings. Status is `PROFILE_VALID|BLOCKED_TOOLCHAIN|BLOCKED_SOURCE|STATIC_VALIDATED`; STATIC_VALIDATED does not mean playable or production ready.

**Implementation steps:**

1. Implement the first build adapter as an external CLI adapter for the pinned Rojo version admitted by EX09. Read its captured primary docs and N03's installed-host receipt; record licenses, executable/image digests, command argv, and supported host platform. Missing sources/tooling block that adapter.
2. Implement deterministic Rojo project discovery from the admitted manifests and source roots. Support a user-configured profile override with trusted validation; ambiguous detection emits a typed decision instead of guessing commands.
3. Resolve dependencies and asset references through N22's immutable source inventory. Record asset rights/availability separately from code licensing. Do not treat an asset ID or public repository as a reuse grant.
4. Seal build, format, lint/type, and unit-check commands actually supported by the chosen versioned tools. Permit checks to be declared unsupported; never invent a CLI capability.
5. Materialize build work in N18's isolated runner before executing downloaded tools or repository scripts. Install from the pinned cache/broker; no worker inherits platform or forge credentials.
6. Verify output artifact identity, expected paths, source mapping, file bounds, and manifest consistency. Preserve static diagnostics and output digests without raw private source in global evidence.
7. Produce a runtime requirement record for N27: required host/runtime, entrypoint/artifact, fixtures, test accounts or credential capabilities, asset dependencies, and explicitly unverified behaviors.
8. Cache repeatable static checks by input/toolchain/profile digest. Rebuild changed components and run one final static profile check after integration; do not rerun all tooling after each edit.

**Acceptance:** Positive: a minimal licensed fixture builds and yields the expected artifact with a stable manifest. Negative: ambiguous manifest, changed executable, missing locked dependency, inaccessible asset, injected build command, or absent runtime capability cannot become production evidence. Crash: interrupted installation/build resumes from verified cache entries and rebuilds incomplete outputs. Command: `python -m unittest tests.test_roblox_profile -v`; actual versioned tool commands come from the admitted profile and must have receipts before STATIC_VALIDATED.

**Locks/rollback/escalation:** Lock shared tool-cache population by tool digest; each target build uses its own workspace. Roll back the adapter registration/profile version, not unrelated language adapters. New platform capabilities or asset grants block only affected checks and stay explicit.

## N27 — Collect Studio/game runtime evidence for production candidates

**Dependencies:** N15, N24, N26. **Owner:** Integrator/Builder. **Independent reviewer:** Roblox runtime Curator, with security and reliability witnesses. **Risk/tier:** externally hosted runtime and release boundary, high/T3; local fixture development remains reversible. **Effort:** 3–5 sessions plus externally dependent runtime availability.

**Read existing:** N26 profile, N03's dedicated-host receipt, and EX11 Studio-testing primary-source entry; `src/hive_mind_os/verification_adapters.py` (`SandboxRequirements`, `VerificationBudget`); `src/hive_mind_os/brain_kernel/evaluation_runtime.py`; N24 functional grading and N15 effect/authority contracts. Verify the actual Studio test adapter surface on the dedicated Windows host. A static runner or invented portable/headless command cannot substitute for game execution.

**Write allowlist:** **NEW** `src/hive_mind_os/roblox_runtime.py`, `src/hive_mind_os/schemas/roblox-runtime-evidence.schema.json`, `tests/test_roblox_runtime.py`, and `docs/architecture/ADR-WOS-N27-roblox-runtime-evidence.md`; admitted fixture/test-harness paths under `tests/fixtures/roblox_profile/` with N26 coordination.

**Inputs/outputs:** `RobloxRuntimeEvidence(candidate_digest, profile_digest, platform_tool_version, environment_id, scenario_manifest_digest, account_capability_refs, runtime_receipts, performance_samples, persistence_results, security_results, asset_results, cleanup_receipt, verdict, missing_obligations)`. Capability references are opaque; no token values. Verdict is `RUNTIME_VALIDATED|PRODUCTION_CANDIDATE|BLOCKED_RUNTIME|FAILED|INCONCLUSIVE`. `DEPLOYED_OBSERVED` requires a separate authorized release and observation receipt; it is never inferred from PRODUCTION_CANDIDATE.

**Implementation steps:**

1. Implement and probe the Studio test adapter described by EX11 through the distinct dedicated Windows VM host capability. Bind executable paths, versions, image, and supported control/command operations from N03's host receipt. Until N18 attests that capability and the probe succeeds, return BLOCKED_RUNTIME; fake clients prove only unit behavior.
2. Allocate the dedicated non-production Windows test environment through the host broker and existing N15 lease/effect path. Scope test accounts, assets, network destinations, data stores, spending, and teardown authority explicitly. Missing access returns BLOCKED_RUNTIME; never reuse the Linux container claim as Windows isolation evidence.
3. Freeze scenario inputs and pass/fail tolerances through N24 before testing. Include startup, the declared core game loop, session join/leave/reconnect, and multi-client server behavior appropriate to the game.
4. For each present feature, verify persistence retries/idempotency/failure recovery, server authority for sensitive actions, hostile client input validation/rate limits, and duplicate transaction protection. Mark absent features not applicable with an inspectable reason; never silently omit a present feature.
5. Exercise asset loading/permissions, target device/network conditions, performance budgets, and recoverable state transitions. Collect actual runtime observations and independent artifacts; README promises and successful builds are insufficient.
6. Keep credentials in the broker; sanitize logs, screenshots, player/account identifiers, and traces before retention/export. Runtime observations remain in the target tenant unless separately generalized by N20.
7. Compute verdict from mandatory scenario results and evidence completeness. Missing platform execution is BLOCKED_RUNTIME/INCONCLUSIVE even when every static check passes. PRODUCTION_CANDIDATE also requires N24 quality/security criteria and a reviewable release/rollback plan.
8. Persist environment allocation and scenario completion IDs before effects. On interruption, inspect the existing environment, recover valid observations, clean up owned test resources, and resume only unfinished scenarios within the lease.

**Acceptance:** Positive: admitted fixture receives actual runtime receipts for required scenarios and teardown. Negative: forged runtime report, stale candidate, unavailable Studio/platform, omitted security case, credential-bearing artifact, or production environment substituted for test environment fails. Crash: controller interruption leaves one discoverable allocation and recovery produces cleanup without duplicate purchases/actions. Command: `python -m unittest tests.test_roblox_runtime -v`; the admitted runtime profile supplies exact integration commands, whose receipts are mandatory before runtime validation.

**Locks/rollback/escalation:** Lock `roblox-test-environment:<id>` and bounded account capabilities; unrelated tenant games remain parallel. Rollback stops owned sessions and restores/cleans only leased test state. New credentials, platform permissions, spending, or public release require their existing external authority path. Unavailable runtime evidence blocks the production claim while other authorized implementation nodes continue.
