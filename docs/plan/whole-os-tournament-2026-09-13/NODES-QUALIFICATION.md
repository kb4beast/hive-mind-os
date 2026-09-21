# Integration, measured tournament and operation nodes

These nodes qualify future implementations. No result below has been achieved by writing this document. Inherit the common worker/receipt/rollback rules in RUNBOOK. Private evidence and host configuration remain outside target repositories. `NEW` denotes proposed files.

## N28 — Compose cross-repository and cross-language operation

**Dependencies:** N13, N14, N16, N21, N25, N26. **Optional domain evidence:** N27 when available. **Owner:** Integrator; independent Curator. **Tier/risk/effort:** T3, cross-system composition, 3–4 sessions. **Locks:** release-composition and public-cli. **Read:** implemented node receipts, `cli.py`, `workers.py`, public DAG/subject adapters, `verification_adapters.py`, repository profiles, tenant/learning routes and current compatibility tests.

**Write:** NEW `tests/test_whole_os_integration.py`, `tests/fixtures/whole_os/` synthetic fixture metadata and small owned test repositories, `docs/execution/WHOLE_OS_SERVICE.md`; minimal public composition/CLI wiring in existing modules. Do not add `.autopilot` or a Hive runtime import to delivered target applications.

**Steps:**

1. Build a composition matrix with self-Python, external Python, Node/TypeScript, Go, supported Rust verification, and Roblox. Declare each adapter's actual check class; Rust metadata compilation remains compile-only until a real execution adapter is separately qualified.
   Generic service integration may finish while Studio evidence is unavailable: report Roblox runtime qualification pending N27. This does not close R14; ADR-090 keeps the optional domain outside the current N32 scope. Do not block unrelated generic service work on a missing optional domain worker.
2. Add a configured service entry that resolves the existing queue, bindings, graph, role runtime, execution backend, verification and delivery broker through one composition root. Keep old public commands' documented compatibility/retirement behavior.
3. Use trusted local fixture repositories for deterministic integration and attested strong backends for untrusted-code/tenant claims. Fixture source must not silently fetch the public final target.
4. Drive one full mission through discovery evidence, chosen goal, graph, worktree, builder, verifier, code PR intent, outcome observation and appropriate learning route. A fake forge test validates protocol; it does not prove live PR publication.
5. Run a two-repository case in parallel with colliding filenames and local work IDs. Verify code changes stay in each subject and the Hive draft export contains only permitted learning artifacts.
6. Stop the Hive service and build/run the delivered external app from its own checkout and declared normal dependencies. Assert no runtime dependency on Hive's control plane or workspace paths.
7. Compose patches in an integration worktree. Resolve shared schema/CLI changes in one serial integration commit and invalidate affected receipts. A clean merge is not sufficient acceptance.
8. Test old inert plans and documented trusted-local workflows against the new binaries. Migration must refuse ambiguous old tenant state, not assign it to an arbitrary new tenant.
9. Run cross-node focused integration checks, then the mandatory full repository gate on the final integrated candidate. Preserve failures and an exact environment/tool manifest.
10. Obtain independent Curator reproduction and a release-composition receipt mapping every requirement to one implemented boundary.

**Acceptance:** All declared supported profile contracts behave correctly; deliberately unsupported runtime classes return explicit incomplete capability. Target apps run with Hive absent. Misrouted callbacks, stale target head, schema mismatch, two tenants and missing role evidence fail correctly. Crash after integration candidate seal resumes without repeating a remote action. Commands: `python -m unittest tests.test_whole_os_integration -v`, then `python -m unittest discover -s tests -v` with `PYTHONPATH=src`.

**Output/stop:** versioned integrated candidate, compatibility matrix, real/fake evidence labels and full CI receipt. No promotion claim. **Rollback:** restore prior service/config version and replay-compatible state projection. **Escalate:** actual incompatible public contract, not routine merge conflicts.

## N29 — Attack recovery, authority, privacy and evaluation boundaries

**Dependencies:** N17, N18, N21, N23, N28. **Owner:** independent Curator/Cross-Examiner; Builders may repair in separate follow-up nodes but cannot judge their repairs. **Tier/risk/effort:** T3, high, 3–5 sessions. **Locks:** adversarial-harness and qualification-evidence.

**Read:** current isolation attestations, outbox/fencing, subject memory, export, PIT seals, delivery and self-promotion contracts. **Write:** NEW `tests/test_whole_os_adversarial.py`, `docs/execution/WHOLE_OS_FAILURE_MATRIX.md`, owned synthetic fixture manifests; minimal fixes go to separately identified repair commits and new exact-candidate verification.

**Steps:**

1. Create a failure matrix for every durable effect: before intent persistence, after persistence, after effect but before receipt, after receipt before next transition, lease expiry and stale worker return.
2. Inject these failures using fake adapters for deterministic coverage; repeat critical network/host cases against disposable real services inside the existing grant.
3. Prove one effective branch/PR action under response loss and retries. Do not claim exactly-once HTTP invocation; prove idempotent/reconciled resulting state and retain all attempts.
4. Exercise tenant collisions, link/mount escapes, target code reading host files, denied egress, secret inheritance, private embeddings, provider payloads and artifact extraction. Synthetic canaries include non-regex, encoded and split values.
5. Attack final staged lesson bytes, PR title/body, attachments, logs and error paths. Extra code files, source snippets, private URLs, identity fingerprints and injected instructions must be excluded/quarantined before outbound publication.
6. Attack endpoint blindness: final/intermediate Git objects, refs, LFS/submodules, source mirrors, dependency/document caches, branch/issue metadata and prior solved episodes. Preserve shared-first-snapshot blobs without false leakage claims.
7. Attack learning: draft-to-ACTIVE shortcut, automatic promotion on document merge, stale holdout, same-actor review, altered metrics, copied evaluator output and hidden failure deletion.
8. Exercise self-upgrade kill/restart, incompatible state, partial pointer switch, lost supervisor response and previous-version rollback. The running agent never acquires supervisor secrets.
9. Classify defects and remand only affected packages. New candidate bytes invalidate relevant tests and require independent verification; unchanged unrelated evidence remains usable.
10. Seal the adversarial report including attempted escapes, actual environment capabilities, known residual risks and untested obligations.

**Acceptance:** All designed negative controls fail at the intended boundary, healthy paths still succeed, and interrupted tasks retain one authoritative mission/event lineage. The report distinguishes unit simulation from demonstrated OS isolation. Command: `python -m unittest tests.test_whole_os_adversarial -v`; attested real-backend probes are a separate mandatory qualification command set from N03/N18.

**Output/stop:** independent safety/recovery disposition on the exact candidate; any critical unresolved case prevents N30's promotable claim. **Rollback:** disable affected feature/profile and select prior qualified release. **Escalate:** external missing capability or authority only; routine repair remains autonomous and visible.

## N30 — Run the measured tournament and independent promotion court

**Dependencies:** N02, N28, N29. **Owner:** Optimizer schedules; separately administered evaluator where the claimed assurance requires it, and separate Judge. **Tier/risk/effort:** T3 review; deterministic harness execution; 3–6 sessions plus configured benchmark runtime. **Locks:** frozen-benchmark and candidate-promotion.

**Read:** N02 metric and MatchProtocol artifacts, EX01/EX03/EX06 comparator sources and licenses, retained analytical tournament, N28 candidate and N29 adverse evidence. **Write:** NEW `src/hive_mind_os/whole_os_benchmark.py`, `src/hive_mind_os/benchmark_adapters.py`, `tests/test_whole_os_benchmark.py`, `tests/test_benchmark_adapters.py`, `docs/benchmarks/whole-os-results-<run-id>.md`; private/raw benchmark artifacts in the evaluator store. Reports expose only permitted data. Benchmark adapters materialize the exact MB/MC/MH recipes specified by N02; they invoke pinned external tools through the existing execution broker and do not import their control logic into the product kernel.

**Steps:**

1. Resolve the N02 candidate-selection rule to the actual N28 candidate; independently seal original variant digests before original evaluation, hybrid variants before hybrid evaluation, and the unchanged selected pair before the final. Verify model, task, tool, environment, budget, rubric and split bindings against N02. Changes within an opened stage create a declared successor experiment; no adaptive unrecorded rubric or same-bytes duplicate entrant.
2. Run the frozen current-baseline, selected design implementation, minimal-builder and SDK-builder lanes on matched compatible tasks. Use the same external effects/data policy and include adapter overhead.
3. Run ablations for cache off, capsule off, fixed role calls, no private lessons and no dynamic package revision. Keep quality gates identical. Ablation permits disabling an optimization, not removing privacy or independent qualification.
4. Apply hard safety/quality eligibility first. Record unsupported capability, failed build, timeout, budget exhaustion, no-change and successful outcomes with denominators; do not report only successful traces.
5. Retain per-task category outcomes and cost/latency vectors. Cluster repeated trials by repository family per N02. Report p50/p95 where meaningful and confidence intervals, not a single blended winner score.
6. Use triple elimination for the declared measured candidate field under the frozen matchup protocol. A loss requires a resolved outcome; inconclusive comparisons do not become invented wins/losses. Cap work by the experiment lease and report an unfinished bracket honestly.
7. Evaluate hybrids on fresh harder tasks not consumed to design them. The final championship is strongest eligible original versus strongest eligible hybrid, using untouched qualification data.
8. Have the independent evaluator reproduce selected receipts and audit failures/contamination. A public-source task with possible model-pretraining familiarity retains that caveat.
9. Judge `adopt|adapt|defer|reject|quarantine` per claim and operating regime. Require N02 noninferiority, no critical violation, regression budgets and measurable benefit before champion promotion. If statistical evidence is insufficient, retain the current champion and an INCONCLUSIVE claim.
10. Produce a candidate-bound promotion recommendation, rollback reference, dissent and learning packet. The authorized supervisor/broker performs any activation later; benchmark scoring itself has no such authority.

**Acceptance:** Synthetic harness tests reject dropped failures, stale evidence, repeated-family inflation, changed rubrics, fake measurements and self-approval. Real benchmark receipts reproduce under the pinned configuration. Command for harness: `python -m unittest tests.test_whole_os_benchmark -v`; actual benchmark invocation and exact argument vector must be generated from the sealed N02 adapter manifest, not guessed here before implementation.

**Output/stop:** measured court disposition with explicit scope, remaining uncertainty and surviving/losing competitors. **Rollback:** keep prior champion and all failed challenger evidence. **Escalate:** new resource/authority need; insufficient evidence is a normal defer outcome, not a reason to lower thresholds.

## N31 — Operate the self-repository pilot with rollback

**Dependencies:** N17, N30. **Owner:** Steward; separate Curator and promotion Judge. **Tier/risk/effort:** T3, self-runtime risk; two setup sessions plus 72-hour pilot observation. **Locks:** self-campaign and supervisor-release-pointer.

**Read:** candidate promotion verdict, standing self-repository profile, existing protections, scheduler service and supervisor receipts. **Write:** NEW `docs/execution/SELF_PILOT_RECEIPT.md` safe report; actual code proposals use normal future node branches/PRs, private state outside the repository. No special grant is created by this document.

**Steps:**

1. Admit only the measured candidate and authorized self-repository scope. Capture previous champion, exact supervisor configuration and tested rollback artifact.
2. Start with one concurrent code package, explicit daily resource lease, PR rate cap from the configured forge profile and a 72-hour observation window. These are initial pilot limits, versionable after evidence, not permanent arbitrary constraints.
3. Let the OS discover at least three evidenced opportunities, rank them including no-change, and autonomously select authorized valuable work. Do not preselect trivial changes to make the autonomy test easy.
4. Complete at least three nontrivial accepted changes from distinct failure/feature families, or report insufficient opportunities/evidence. Exercise discovery, implementation, verification, PR opening and repair without owner prompt transfers.
5. Intentionally restart the service and interrupt one tool/effect boundary under the safe pilot fixture. Prove mission continuity, no duplicate PRs and retained budget accounting.
6. Run one qualified self-challenger canary and restoration drill through the external supervisor. Verify old jobs remain pinned and no live host binaries are edited in place.
7. Observe PR CI and outcome signals during the window. Count avoidable human questions, manual rescue, invalid PRs and idle loops explicitly.
8. Complete the required independent checks and record actual success/failure/blocked totals. A lack of authority to merge is different from a need for humans to coordinate implementation.
9. Judge the pilot for its specific scope. Promote broader operating capacity only through a successor configured lease and independently supported decision.

**Acceptance:** Zero avoidable owner coordination in the evaluated workflow; correct recovery and at least required qualifying attempts; no unauthorized effects; configured budgets enforced; actual PR receipts if granted. Capability or merge restrictions remain explicit. Validation uses N28/N29 executable checks plus the recorded real pilot, not a mocked PR test presented as live behavior.

**Output/stop:** self-pilot report with actual elapsed observation and interventions. **Rollback:** external supervisor restores previous release and pauses new self-jobs; existing evidence remains. **Escalate:** only a new external grant/resource need or critical revocation event.

## N32 — Qualify two external repositories

**Dependencies:** N21, N30. **Owner:** Integrator/Steward; independent Curator, target witness and Judge. **Tier/risk/effort:** T3, external data/runtime, 3–5 sessions plus 72-hour observation. **Locks:** per-tenant pilot; no shared writable target checkout.

**Read:** qualified target profiles, target owners' actual goals and standing grants, code/lesson delivery routes, and runtime evidence. **Write:** NEW `docs/execution/EXTERNAL_PILOT_RECEIPT.md` sanitized report; target code PRs stay in their own repositories, upstream drafts use C07. Raw target code, private data and tenant receipts remain private to their admitted subjects.

**Steps:**

1. Admit at least two distinct external repository profiles. Each must be an owner-authorized non-Hive project with a pinned snapshot, reuse rights, measurable acceptance goal, and declared runtime. A missing real project is an explicit unmet pilot prerequisite.
2. Onboard each once: target identity, host capability, permitted provider data, secrets broker, build/acceptance, PR destination, lessons destination and resource lease. Retain configuration so routine runs need no repeated questions.
3. Autonomously discover and deliver at least two nontrivial accepted changes under the N31-style observation protocol, covering both targets. Prove no Hive runtime dependency in either result.
4. Execute each target's declared build, test, security and user-acceptance profile on its real runtime. Record exact tool and runtime versions with the evidence artifacts.
5. Keep test data separate from production. Staging or public publication occurs only if already authorized and eligible; absence of publishing authority can leave a qualified repository candidate without pretending it is deployed.
6. Complete a private app-learning update and a separate sanitized lessons-only draft obligation for each stable completed external mission. Verify the exported draft does not activate Hive memory or change Hive source.
7. Run a concurrent two-tenant canary case and a service interruption. Ensure raw lessons, code, caches, provider payloads and PR credentials do not cross tenants.
8. Independently judge external autonomy for the exact target profiles. Do not generalize two repositories to arbitrary production systems or claim weight training occurred.

**Acceptance:** Real target code PRs and required lesson drafts have exact safe receipts; runtime evidence meets each declared profile; all obligations are visible; both targets run with Hive offline. N28/N29 checks pass on the final pilot release; actual target observation is additionally required. Missing runtime, rights, or target evidence is BLOCKED_CAPABILITY/SOURCE for this node, not an automatically passing static substitute.

**Output/stop:** per-subject maturity verdict, sanitized artifact links, target acceptance matrix and residual limitations. **Rollback:** abandon/revert scoped candidate PRs and restore qualified test artifacts through normal target procedures; preserve learning drafts and failed evidence. **Escalate:** genuine external input/authority only.

## N33 — Close outcomes and publish the final operating handoff

**Dependencies:** N31, N32. **Owner:** Orchestrator/Steward; independent Curator and final Judge. **Tier/risk/effort:** T2 synthesis, T3 final judgment, two sessions after outcome windows. **Locks:** release-closeout; no new product changes.

**Read:** all integrated node receipts, requirement map, source obligations, benchmark court, self/external pilot and rollback/outcome evidence. **Write:** NEW `docs/execution/WHOLE_OS_ACCEPTANCE.md`, `USER_GUIDE/08_AUTONOMOUS_REPOSITORY_SERVICE.md`, `docs/execution/WHOLE_OS_RECOVERY.md`; versioned safe release manifest. Any code defect returns to a bounded repair node rather than hiding inside documentation closeout.

**Steps:**

1. Reconstruct implementation completion from exact integrated commits, verified output contracts and target ancestry. Mark deferred or blocked requirements explicitly; do not equate PR-open with merged/integrated.
2. Audit all eight specialist roles and discover/design/build/validate/grow/maintain/integrate evidence in actual missions. List deterministic applicability/prior-evidence dispositions truthfully.
3. Compare measured outcomes with N02 thresholds and actual profile-specific production requirements. Retain noninferior/inferior/inconclusive results per regime rather than universal marketing.
4. Reconcile each completed external mission's one draft obligation. Report published, private pending, withheld, quarantined and failed states without leaking private origins. Unresolved mandatory destinations remain open.
5. Verify source completeness, rights, secrets, compatibility, resource leases and rollback evidence. An open source archive or asset requirement prevents only the claims that depend on it; never misrepresent complete ingestion.
6. Write installation and one-command service startup using commands verified from the implemented CLI. Include configured host paths, profile creation, provider availability and credential-handle setup without secret values.
7. Write recovery by typed state: stale lease, uncertain effect, provider failure, invalidated candidate, blocked export, unavailable runtime and supervisor rollback. Each includes the observed evidence, deterministic next action and stopping condition.
8. Demonstrate cold restart from durable state with a fresh operator session. The owner must not transfer chat history or hand-paste node prompts for routine continuation.
9. Have the independent Judge issue the scoped final release disposition and identify remaining unsupported environments. Report actual token/cost/time and interventions from receipts.
10. Seal the release handoff and stop the enhancement campaign. Continuous operation continues only under its configured service charter; it does not create an unbounded mandate to change unrelated repositories.

**Acceptance:** A fresh qualified operator can reconstruct service state and recovery from artifacts; every R01–R18 requirement maps to evidence or explicit unresolved disposition; no production/superiority/source-completeness assertion exceeds receipts. Documentation links and installed CLI examples validate, and final integrated CI evidence is current. Re-run product checks only when new bytes or unresolved evidence invalidate the prior run.

**Output/stop:** complete operating handoff, versioned release manifest and scoped final verdict. **Rollback:** select previous documented release/configuration; leave all candidate history. **Escalation:** remaining external prerequisites are recorded as such. An incomplete pilot means the overall enhancement is not yet full-autonomy complete.
