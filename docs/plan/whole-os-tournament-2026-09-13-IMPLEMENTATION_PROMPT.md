# End-to-end implementation prompt

This is a prompt for a future implementation task. Saving or committing it does not start that task. The documentation-only design is preserved in `docs/plan/whole-os-tournament-2026-09-13/`; its committed text uses repository-normalized line endings and a matching manifest. The original pre-commit ZIP is retained separately.

## Model recommendation

For one model owning the entire campaign, **GPT-5.6 Sol with high reasoning** is the lowest route recommended here. This is an engineering judgment for the breadth of kernel, isolation, concurrency and learning changes, not a benchmark-proven minimum or a guarantee of completion.

For lower total cost, use that route as the Orchestrator and critical reviewer while dispatching bounded T1 implementation to **GPT-5.6 Luna / medium**, T2 implementation/integration to **GPT-5.6 Terra / medium**, and T3 work/judgment to **GPT-5.6 Sol / high**. No model is needed for deterministic checks. A smaller builder does not independently approve its own work. Qualify routes through N07, subdivide difficult work, and escalate on evidence rather than repeating unsuccessful attempts with the same context.

Official OpenAI documentation describes Sol as a model for complex professional work, Terra as balancing intelligence/cost, and Luna as optimized for cost-sensitive workloads. It does not certify a minimum model for this repository. Account/tool availability and data policy must be resolved at execution time. [Official model catalog](https://developers.openai.com/api/docs/models), [model-selection guidance](https://developers.openai.com/api/docs/guides/model-selection).

## Copy the prompt below into the implementation task

You are the continuing Orchestrator and implementation owner for Hive Mind OS. Implement the entire whole-OS enhancement described in `docs/plan/whole-os-tournament-2026-09-13/`, covering N00 through N33. Start from the local branch `codex/whole-os-tournament-handoff` or a verified descendant containing that exact handoff. If the current checkout has unrelated work, create an isolated worktree from that branch; do not discard or overwrite the existing work.

This is an explicit instruction to IMPLEMENT, TEST, INTEGRATE, DELIVER AND VERIFY the enhancement end to end. It supersedes the earlier instruction to produce documentation only for this execution task. The historical handoff, source manifests, scores and review findings remain preserved evidence; create successor implementation/decision records instead of rewriting history. The handoff's analytical tournament is not a measured implementation result.

I authorize routine reversible implementation within this campaign: inspect the repository and relevant public sources, create isolated worktrees and `codex/` branches, implement and repair code/tests/docs, run builds and checks, use available qualified models and tools within existing resource allocations, commit work, and open/update scoped draft PRs using existing permitted credentials and delivery grants. Continue after interruption without asking me to repeat this authorization. This does not manufacture credentials, host signatures, new spending, protected merge authority or production deployment authority.

Do not ask me questions, request plan confirmation, ask which node comes next, ask whether to continue, or stop to offer future work. Make reasonable implementation and scheduling decisions from the accepted contracts and repository evidence. Resolve routine ambiguity through the relevant specialists. Keep working on all dependency-ready, authorized work until the complete campaign is actually finished or all remaining actions depend on unavailable external prerequisites.

### Start and reconstruct state

1. Read `AGENTS.md` and establish the actual repository/worktree/branch identity without modifying unrelated files. As the first continuation execution action, invoke the canonical launcher from this repository:

   `powershell -NoProfile -File scripts/Invoke-PreauthorizedContinuation.ps1 -Apply`

   Preserve its observed result and typed blockers. Recover eligible local defects within the campaign. Do not bypass a withheld release, treat an old release as authority for the new graph, or start unrelated historical work because it appears in launcher output. A blocker in an older control-plane lane does not prevent independently authorized source reconciliation or preparation for this enhancement.

2. Read the handoff README, RUNBOOK, REVIEW, requirements and DAG index. Reconstruct existing progress from exact commits, durable receipts, open PRs, CI and recorded claims; do not depend on chat memory or hand-edited status. Validate the original package manifest before using its evidence.

3. Complete N00 reconciliation and N01 successor decisions/compilation before executing the new graph. The JSON index is inert planning data, not a portable executable plan or authority grant. Preserve compatible prior work and already completed requirements instead of rebuilding them.

4. Own durable campaign state and continuation. A worker's instruction to stop at its node ends that assignment only; it never means the Orchestrator should stop the campaign. Claim and dispatch ready dependents, handle repairs and integration, and continue automatically.

### Execute efficiently

- Use the accepted node outcomes, interfaces, source/authority boundaries, required checks and rollback as the contract. Builders may choose local edit order, helpers, refactoring, algorithms and targeted repair without another planning debate. Replan only when material requirements, interfaces, dependencies, risk, authority or evidence change.
- Dispatch independent work concurrently in isolated worktrees. Compile and acquire exact semantic and write-path locks; index navigation labels are not locks. Serialize conflicting integrations. Do not create thousands of micro-nodes or add ceremony to routine edits.
- Give each worker only its node, direct prerequisite receipts, relevant contracts and source sections. Use the existing capsule, task-reuse, test-cache, applicability and token-accounting primitives when wired. Preserve cold evidence references and explicit omissions instead of retransmitting the entire handoff.
- Route bounded T1 builders to `gpt-5.6-luna` with medium reasoning, T2 to `gpt-5.6-terra` with medium reasoning, and T3/critical judgment to `gpt-5.6-sol` with high reasoning when available and qualified. I explicitly permit those model routes and escalation within existing allocations. If the host cannot route models, retain the configured capable model and record that limitation; do not invent a model switch or stop to ask me to select one.
- Use actual separate agents/sessions for building, independent Curator verification and judgment. Record the real independence level. Satisfy all eight specialist roles and lifecycle stages with meaningful evidence at appropriate mission/cohort boundaries, using legitimate deterministic/prior-evidence dispositions instead of eight fresh model calls after every edit.
- Run relevant focused checks during implementation. Reuse results only with matching input, candidate, check, toolchain, environment, authority and trust-purpose bindings. Independently qualify exact candidate bytes and run required composition/full CI checks at integration. Do not rerun unchanged checks without a reason, and do not weaken them to get a passing result.
- In every test shell, bind `PYTHONPATH` to this admitted worktree's absolute `src` directory and verify `hive_mind_os.__file__` resolves there. The default installed package was observed to point at another worktree. The mandatory full repository gate remains `python -m unittest discover -s tests -v`.

### Preserve the product requirements

Deliver a persistent service that discovers valuable work, executes the accepted graph, implements useful code, independently verifies it, opens scoped PRs, responds to CI/feedback, recovers after interruption and measures outcomes on Hive Mind OS and external repositories. Shipped applications must run without Hive's DAG/control-plane/workspace dependency.

Keep target application code PRs in the target repository. Keep raw app data, code, assets, secrets, logs, embeddings and app-specific learning within its own boundary. For each stable external mission, retain its mandatory lessons draft obligation and publish only sanitized lessons-only drafts to a configured authorized destination. Retries and polls update one obligation rather than creating duplicate PRs. Draft publication or document merge cannot activate Hive memory or promote a challenger.

Keep endpoint reconstruction separate from strict PIT. Learners receive only admitted initial snapshots and explicitly classified briefs; final targets/evaluator data remain outside their custody until sealing. Never invent intermediate history or claim changed-file similarity establishes functional skill. Improve app and Hive strategies through separate versioned challengers, independent evaluations and rollback.

Implement and qualify the Roblox build/runtime adapters and agreed game production profiles. Static checks, mocked Studio tests or package generation cannot satisfy engine, multiplayer, exploit-resistance, persistence, asset or real-device requirements. Preserve source licenses, raw-source obligations and public-pretraining contamination caveats.

### Handle blockers without questions or idle loops

Classify failures, retain evidence, repair the smallest affected package, reuse valid completed work, and continue independent lanes. Retry only recoverable failures under the lease; reconcile uncertain external effects before retrying. Change hypothesis or route when repeated failure shows no progress.

If essential credentials, external host grants, repositories, rights, assets, Roblox runtime access, devices or resources are unavailable, record the exact typed obligation and the dependent claims it prevents. Discover existing admissible alternatives without widening authority. Complete every other unblocked implementation, test and delivery step. Do not fabricate prerequisites, mislabel mocks, quietly shrink the accepted objective, ask me a question, or repeatedly restate an unchanged blocker.

If every remaining action is blocked by external prerequisites or an actual hard account/resource limit, checkpoint all progress and issue one precise, non-question blocker report with candidate/PR references, completed nodes, remaining obligations and the deterministic resume action. State that the campaign is incomplete. Do not claim it will resume in the background unless an actual configured runner/scheduler exists. When execution resumes, reconstruct durable state and continue without asking for repeated authorization.

### Complete and report

Continue through integration, actual benchmark execution, self/external pilots, learning/export verification and N33 closeout. Do not finish after producing a plan, one successful node, unit-test-only scaffolding or a draft PR. A deployment without granted access is not required to be fabricated, and a missing production proof is not allowed to be reported as passed.

Report completion only when the requirement-to-integrated-receipt map, independent qualification, applicable full CI, measured tournament, real profile-specific pilot evidence, rollback and outcome windows justify it. Keep inconclusive/failed comparisons and all unresolved obligations visible. Return the final branches/commits/PRs, measured validation and outcomes, operational start/resume instructions and any precise remaining external obligations.

Begin execution now. Do not respond with only an acknowledgment or another implementation plan.
