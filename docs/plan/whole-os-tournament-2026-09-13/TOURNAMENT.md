# Whole-OS design tournament

## What was actually run

A documentation-only, adversarial **architecture selection tournament** was performed against the pinned repository and a targeted primary-source survey. The field contains 12 materially different complete-system approaches, 60 explicit mechanism/alternative decisions and 4 coherent hybrids. The original bracket records 33 decisions; the hybrid bracket records 9; the final compares the two survivors in 5 scenarios. Each eliminated entrant has three actual recorded design losses, rather than treating three screening rounds as triple elimination.

These are analyst suitability judgments about proposed architectures, **not measured software battle results**. No comparator agents, provider benchmarks, live Roblox games, training, generated production code or PR delivery ran in this task. Ordinal scores expose the assumptions behind selection; they are not accuracy, latency, cost or production-readiness measurements. N02/N30 specify the real measured tournament before a superiority or promotion claim.

The complete record is [tournament-record.json](tournament-record.json). It is inert evidence data. Arithmetic, loss counts and dependency data are reproducible without treating the score inputs as empirical truth.

### Scouting scope and stopping reason

The survey examined actual repository primitives and primary sources for minimal coding loops, richer coding SDKs, workflow durability, graph persistence, reproducible code evaluation, execution-filtered curricula, game-agent skills and Roblox production constraints. Sources and counterclaims are in [SOURCES.md](SOURCES.md). It did not claim exhaustive Internet coverage or fifty independently benchmarked products.

Sixty mechanisms/alternatives were considered because these are genuinely distinct decisions within this OS; they are **not** sixty independently implemented competitors. Twelve complete architecture classes were retained for the bracket. Variants differing only by vendor/model were collapsed into replaceable routes. Unsafe shortcuts were rejected as mechanisms rather than allowed to offset their fatal defects with speed points.

Scouting stopped at a useful design handoff boundary: every requested lifecycle/data/runtime concern had a materially different alternative, and adding another generic graph or chat framework would not resolve the observed integration seams without implementation measurements. Global search saturation is **not established**. Open scouting obligations remain multi-host scale evidence, tenant isolation implementation, benchmark execution, and actual owner-supplied Roblox subjects/assets. New evidence can reopen the court.

## Subject-specific rubric and hard exclusions

The user wants useful autonomous work, production candidates and actual PRs on Hive and external repos, with efficient implementation and safe separate learning. Therefore the design rubric considers Q production qualification path, A autonomous lifecycle, E execution economy, R recovery, P repository portability, L learning/privacy separation, and M migration/maintenance burden.

Each value is a root Architect judgment on a 1–5 scale: 1 means weak support in the proposed design; 5 means strong structural support **if its required components are implemented and verified**. It says nothing about actual pass rates. Source maturity and unknown implementation gaps remain explicit. No numeric confidence estimate is invented.

Hard exclusions apply before scoring: unchecked authority expansion; acting builder self-approval; target secrets/code copied to Hive against the user boundary; unsealed target/future information represented as blind evaluation; suppressed failures; weakened acceptance; arbitrary hostile execution represented as safely isolated by a worktree. Complete architecture entrants are considered only with these shortcuts excluded; extra work needed to satisfy them lowers economy/migration support. None is production-qualified merely by tournament entry.

| Scenario | Q | A | E | R | P | L | M | Adversarial question |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| S1 Whole-system delivery | 30 | 25 | 10 | 10 | 10 | 10 | 5 | Can it find a useful change, implement, independently qualify and deliver after ambiguous requirements? |
| S2 Small model / low resource | 20 | 15 | 35 | 5 | 5 | 5 | 15 | Does most effort go to the actual patch or repeated council/context work? |
| S3 Failure / recovery | 20 | 15 | 10 | 35 | 5 | 5 | 10 | What happens after process death or a lost successful PR response? |
| S4 External data / learning | 20 | 15 | 10 | 10 | 15 | 25 | 5 | Can two repositories improve without exchanging their code, secrets, histories or active memory? |
| S5 Integration / maintenance | 20 | 15 | 15 | 10 | 10 | 10 | 20 | Can this be built from the current repo without a second truth store and permanent orchestration overhead? |

Points are the dot product of ordinal judgments and scenario weights. They are an auditable preference calculation, not a scientific measurement. A catastrophic safety defect disqualifies a candidate regardless of its sum. Evidence quality and untested capabilities are reported separately.

## Complete original field

The scores below follow Q/A/E/R/P/L/M order. Product names cited as components are not rated as whole products; the entrants are explicitly described deployment/architecture configurations for this task.

| ID | Complete approach | Ordinals | Evidence / source class | Strongest case, objection and preferable regime |
|---|---|---|---|---|
| A01 | Extend the existing small-experiment tournament | 3/2/2/3/3/2/5 | LOCAL-01 / ADR-078 | small migration and existing receipts; limitation: one-small-improvement execution and unwired service composition. Prefer for a single trusted local repair. |
| A02 | One durable host-driven coding brain | 3/4/4/3/3/2/4 | autonomous_os.py / EX01 | short control path and coherent session state; limitation: one session can mix target context, evaluation and long-lived learning unless separated. Prefer for one trusted repository and short tasks. |
| A03 | Minimal builder plus forge CI | 3/2/5/2/4/1/5 | EX01 / EX06 | small builder interface and low orchestration burden; limitation: discovery, recovery, tenancy and learning require additional services. Prefer for isolated issue repair with strong supplied tests. |
| A04 | Full eight-role council after every work step | 4/3/1/3/3/3/3 | local role contracts / historical full-council alternative | frequent explicitly separated review opportunities; limitation: repeated context and checks dominate small changes. Prefer for one unusually ambiguous high-risk architecture decision. |
| A05 | Durable outcome graph on the current kernel | 4/5/3/5/4/3/4 | scheduler.py / outcome graph / EX04 pattern | existing recovery plus explicit whole-mission work ownership; limitation: context/check economy and cross-tenant lessons still need integration. Prefer for long-running repository campaigns. |
| A06 | Temporal-centered service replacement | 4/4/2/5/5/3/2 | EX04 | durable distributed workflow and operational scaling; limitation: new infrastructure, migration and history ownership complexity. Prefer for already-operated multi-host Temporal estate. |
| A07 | LangGraph-centered agent service | 4/4/3/4/4/3/3 | EX05 | graph checkpoints and explicit agent transitions; limitation: replace/bridge existing event and authority contracts. Prefer for organization already standardized on LangGraph. |
| A08 | Distributed event-bus specialist services | 4/5/2/5/5/3/1 | CONGLOMERATED_SYSTEM.md / EX03 | independent service scaling and replaceable execution; limitation: distributed consistency and operating cost before workload justifies it. Prefer for many isolated repositories across multiple hosts. |
| A09 | Blackboard and task-market specialists | 3/4/3/3/4/3/2 | internal architecture alternative; no external performance evidence | opportunistic specialist assignment and broad exploration; limitation: bidding/deduplication overhead and ambiguous value attribution. Prefer for loosely coupled open-ended discovery. |
| A10 | Independent bot installed in every target repo | 3/4/4/3/3/2/3 | .autopilot installation alternative / EX03 | local repository conventions and simple per-repo triggering; limitation: configuration drift, duplicated control plane and difficult learning separation. Prefer for a small fleet with strict repo-specific automation. |
| A11 | Endpoint training first, then model-centric autonomy | 2/2/3/2/3/4/2 | EX07 / EX08 / pit_oracle.py | concentrated curriculum and reusable learned behavior experiments; limitation: training does not itself supply reliable effects, PR delivery or production oracles. Prefer for offline learning research with a fixed runtime. |
| A12 | Parallel speculative builder swarm | 4/4/2/3/4/2/2 | EX03 isolated workers / internal speculative alternative | independent implementation alternatives on uncertain problems; limitation: multiplied tokens, correlated failures and integration contention. Prefer for rare high-value hard tasks with ample budget. |

The advocate's strongest case for A05 is that the repo already has a durable queue, typed graph contracts, independent verification and controlled PR delivery; joining them avoids a second service truth. The strongest cross-examination is that those components are not currently wired into the requested complete product, and the serial fixture path is not evidence of general autonomous execution. The implementation must prove composition, not merely preserve module names.

## Sixty component/alternative decisions

Dispositions below are design recommendations subject to the independent review record. They do not confer execution rights, automatically adopt external code, or close source ingestion. Every adopted/adapted mechanism has an owner node with acceptance and rollback. Rejected/deferred alternatives remain in this record.

| ID | Mechanism or alternative | Source basis | Design disposition | Reason / required adaptation | Implementation owner |
|---|---|---|---|---|---|
| M01 | Fixed single-improvement tournament | local_dag_runtime.py | adapt | retain compatibility; make campaign size explicit | N09 |
| M02 | Unbounded idea implementation | owner scope alternative | reject | finite work-in-progress and useful outcome selection needed | N09/N11 |
| M03 | Static breadth-first waves | historical autopilot plan | adapt | true dependencies and locks determine readiness | N09/N28 |
| M04 | Dynamic outcome DAG | ObjectiveGraph / portable_plan.py | adapt | compile typed successor packages | N09 |
| M05 | Single durable queue | scheduler.py | adopt | reuse queue and fenced leases | N10 |
| M06 | Separate new queue per subsystem | alternative to M05 | reject | duplicate truth/recovery cost | N08/N10 |
| M07 | Temporal infrastructure rewrite | EX04 | defer | compare only when fleet scale justifies migration | N30 |
| M08 | Checkpoint graph framework rewrite | EX05 | defer | borrow persistence separation without new kernel dependency | N10 |
| M09 | Distributed event bus | CONGLOMERATED_SYSTEM.md | defer | current scale unmeasured | N30 |
| M10 | Claim fencing and uncertain-effect reconciliation | scheduler.py / EX04 | adapt | reconcile outcome before retry | N10/N15 |
| M11 | One builder with iterative tools | EX01 | adapt | small loop in admitted sandbox | N13 |
| M12 | Single returned patch packet | local_codex_worker.py | adapt | explicit limited-capability fallback | N05/N13 |
| M13 | Speculative builders for every task | swarm alternative | defer | select only if measured value exceeds multiplied cost | N30 |
| M14 | Eight fresh role calls per tiny edit | full council alternative | reject | use applicability without losing required evidence | N12 |
| M15 | Eight accountable mission role outcomes | agents / role_applicability.py | adopt | meaningful lifecycle evidence | N12 |
| M16 | Deterministic role checks | role_runtime.py | adapt | same scope and independently admissible outputs | N12 |
| M17 | Small model first qualified route | EX17/EX18 / model_backend.py | adapt | qualify task class and record effective model | N07 |
| M18 | Strong model for all work | routing alternative | reject | cost must buy demonstrated quality need | N07/N30 |
| M19 | Targeted model escalation | role runtime / routing policy | adapt | retain candidate and diagnostic delta | N07/N13 |
| M20 | Peer bidding market | blackboard alternative | defer | deduplication and value attribution unproven | N30 |
| M21 | Round context capsule | context_capsule.py | adapt | wire currently unused mechanism | N05 |
| M22 | Cold-reference source retrieval | local evidence / EX05 pattern | adapt | load by bounded evidence need | N05 |
| M23 | Copy full history into each prompt | current-overhead alternative | reject | redundant context does not establish better judgment | N05 |
| M24 | Exact task fingerprint reuse | task_reuse.py | adapt | bind real admission/resume call sites | N06 |
| M25 | Exact passing test cache | test_result_cache.py | adapt | bind environment and trust/purpose | N06 |
| M26 | Branch-name check cache | unsafe optimization alternative | reject | stale evidence can validate changed code | N06 |
| M27 | Impact-directed developer checks | local_evidence_packet.py | adapt | unknown dependency coverage widens checks | N06/N14 |
| M28 | Independent candidate verification | curator / verification.py | adopt | builder may not approve itself | N14 |
| M29 | Full suite after every edit | high-overhead alternative | reject | retain required full gate at integrated candidate | N06/N28 |
| M30 | Replayable append-only evidence | ledger / event spine | adopt | retain failures with compact projections | N04/N10 |
| M31 | Repository backlog signal triage | explorer.py | adapt | deduplicate and compare useful opportunities | N11 |
| M32 | Reward number of PRs | activity metric alternative | reject | customer outcomes and defects determine value | N02/N11 |
| M33 | Controlled code PR broker | ControlledGitHubDelivery | adapt | qualify exact head and distinct grant | N15 |
| M34 | Self-merging builder | unsafe authority alternative | reject | independent delivery/promotion boundaries remain | N15/N17 |
| M35 | Webhook plus periodic reconciliation | scheduler / delivery pattern | adapt | durable idempotent observation, bounded idle | N16 |
| M36 | Poll with model on every tick | overhead alternative | reject | deterministic idle/backoff first | N10/N16 |
| M37 | Versioned self challenger | challengers / promotion | adapt | canary under external supervisor | N17 |
| M38 | Edit live OS process in place | unsafe self-upgrade alternative | reject | no stable rollback/version custody | N17 |
| M39 | Tenant-bound operational memory | memory.py scope foundation | adapt | trusted partition handles and provider-data policy | N19 |
| M40 | Shared global target vector store | unsafe memory alternative | reject | namespaces alone do not enforce privacy | N19 |
| M41 | Draft-only abstract lesson export | owner requirement / EX08 limits | adapt | one external-mission obligation and safe broker | N20/N21 |
| M42 | Raw app code/skill export into Hive | EX08 transfer alternative | reject | violates requested external lessons-only boundary | N20/N25 |
| M43 | Automatically ACTIVE lesson at publication | lesson_memory_record seam | reject | separate draft lifecycle and adoption | N20/N25 |
| M44 | Private app-specific learning | learning_runtime.py | adapt | app challenger stays app-scoped | N25 |
| M45 | Weight fine-tuning immediately | EX07 alternative | defer | data rights, holdouts and useful lift first | N25/N30 |
| M46 | Endpoint-only reconstruction | owner requirement | adapt | first snapshot plus classified brief; final evaluator custody | N22/N23 |
| M47 | Strict ancestor point-in-time replay | pit_oracle.py | adopt | separate existing mode; preserve blindness | N23 |
| M48 | Changed-file overlap as sole competence score | pit_oracle.py grade | reject | retain diagnostic only, add functional outcomes | N24 |
| M49 | Family-split fresh holdouts | EX06/EX07 / evaluation runtime | adapt | fork/template grouping and reveal retirement | N02/N24 |
| M50 | Invent missing intermediate history | endpoint interpretation alternative | reject | endpoints do not establish causal trajectory | N22/N24 |
| M51 | Trusted-local process sandbox | LocalProcessSandbox | adapt | truthful trusted-only profile | N18 |
| M52 | Attested strong execution backend | EX03 / sandbox capabilities | adapt | tenant-dedicated VM plus configured worker | N18 |
| M53 | Regex-only export safety | resource/memory checks | reject | structural extraction, custody, staged-byte screening and isolation | N19/N20 |
| M54 | Rojo build adapter | EX09 | adapt | versioned external CLI; packaging is not runtime | N26 |
| M55 | Studio multiplayer/device test adapter | EX11 | adapt | capability probe and exact runtime evidence | N27 |
| M56 | Server-authoritative Roblox invariants | EX10 | adopt | abuse and context validation tests | N27 |
| M57 | Production data for Studio tests | EX12 unsafe alternative | reject | separate test universe/data | N27 |
| M58 | Third-party asset provenance/intake | EX13 | adapt | rights and malicious-script obligations | N22/N27 |
| M59 | Physical-device performance qualification | EX15 | adapt | profile-specific measured budgets | N27/N32 |
| M60 | Public game release by code success alone | EX14 unsafe alternative | reject | release eligibility and authority distinct | N32 |

### Component winners retained from losing designs

- A03 contributes a small iterative builder interface and a fair repair comparator, even though it lacks the full lifecycle alone.
- A06 contributes durable side-effect/idempotency reasoning. Temporal adoption remains deferred because existing queue cost/limits have not been measured.
- A07 contributes separation of resumable task state from long-term memory. Checkpoint pruning cannot erase required evidence.
- A08 contributes replaceable execution workers and dedicated isolation. A distributed event bus is not required to start.
- A11 contributes execution-filtered curricula and versioned learning experiments. It does not replace production oracles or establish causal histories from endpoints.
- A04 contributes separate challenge/judgment when material decisions need it. Repeating that entire process on every edit is rejected.
- A10 contributes target-specific profile ownership, while the execution service remains external to the shipped application.
- A12 contributes optional independent candidate exploration for unusually valuable difficult work; always-on swarming is deferred until measured.

## Triple-elimination protocol and complete matchup log

Each round sorts surviving entrants by losses then ID, rotates by round minus one, grants an entrant with the fewest prior byes a bye when necessary, then pairs adjacent entrants. Scenarios cycle by round plus pair position. Third loss eliminates. A tied point result uses the higher M support (lower proposed migration burden), then lexical ID. A bye awards no win/loss. The method is deterministic and published so the bracket cannot be quietly altered to hide a loss.

This bracket is not presented as independent empirical trials. Repeated scenario comparisons re-evaluate the same architecture priors and do not increase statistical confidence. The independent judge reviews the argument and conditions, not a supposed experimental p-value.

| Match | Scenario | Entrants and suitability points | Decision | Argument and countercase |
|---|---|---|---|---|
| O-M1 | S1 | A01 265 : 330 A02 | A02; A01 loss 1 | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for a single trusted local repair. |
| O-M2 | S2 | A03 375 : 250 A04 | A03; A04 loss 1 | Largest weighted design advantage: execution economy. Loser remains relevant for one unusually ambiguous high-risk architecture decision. |
| O-M3 | S3 | A05 435 : 395 A06 | A05; A06 loss 1 | Largest weighted design advantage: migration/maintenance burden. Loser remains relevant for already-operated multi-host Temporal estate. |
| O-M4 | S4 | A07 360 : 380 A08 | A08; A07 loss 1 | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for organization already standardized on LangGraph. |
| O-M5 | S5 | A09 305 : 320 A10 | A10; A09 loss 1 | Largest weighted design advantage: migration/maintenance burden. Loser remains relevant for loosely coupled open-ended discovery. |
| O-M6 | S1 | A11 240 : 340 A12 | A12; A11 loss 1 | Largest weighted design advantage: production qualification path. Loser remains relevant for offline learning research with a fixed runtime. |
| O-M7 | S2 | A03 375 : 380 A05 | A05; A03 loss 1 | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for isolated issue repair with strong supplied tests. |
| O-M8 | S3 | A08 400 : 320 A10 | A08; A10 loss 1 | Largest weighted design advantage: recovery. Loser remains relevant for a small fleet with strict repo-specific automation. |
| O-M9 | S4 | A12 310 : 260 A01 | A12; A01 loss 2 | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for a single trusted local repair. |
| O-M10 | S5 | A04 290 : 340 A06 | A06; A04 loss 2 | Largest weighted design advantage: recovery. Loser remains relevant for one unusually ambiguous high-risk architecture decision. |
| O-M11 | S1 | A07 375 : 330 A09 | A07; A09 loss 2 | Largest weighted design advantage: production qualification path. Loser remains relevant for loosely coupled open-ended discovery. |
| O-M12 | S2 | A11 250 : 360 A02 | A02; A11 loss 2 | Largest weighted design advantage: execution economy. Loser remains relevant for offline learning research with a fixed runtime. |
| O-M13 | S3 | A08 400 : 315 A12 | A08; A12 loss 1 | Largest weighted design advantage: recovery. Loser remains relevant for rare high-value hard tasks with ample budget. |
| O-M14 | S4 | A03 270 : 370 A06 | A06; A03 loss 2 | Largest weighted design advantage: learning/privacy separation. Loser remains relevant for isolated issue repair with strong supplied tests. |
| O-M15 | S5 | A07 355 : 320 A10 | A07; A10 loss 2 | Largest weighted design advantage: production qualification path. Loser remains relevant for a small fleet with strict repo-specific automation. |
| O-M16 | S1 | A01 265 : 310 A04 | A04; A01 loss 3 (eliminated) | Largest weighted design advantage: production qualification path. Loser remains relevant for a single trusted local repair. |
| O-M17 | S2 | A09 305 : 250 A11 | A09; A11 loss 3 (eliminated) | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for offline learning research with a fixed runtime. |
| O-M18 | S3 | A02 330 : 435 A05 | A05; A02 loss 1 | Largest weighted design advantage: recovery. Loser remains relevant for one trusted repository and short tasks. |
| O-M19 | S4 | A06 370 : 360 A07 | A06; A07 loss 2 | Largest weighted design advantage: cross-repository portability. Loser remains relevant for organization already standardized on LangGraph. |
| O-M20 | S5 | A12 300 : 335 A03 | A03; A12 loss 2 | Largest weighted design advantage: migration/maintenance burden. Loser remains relevant for rare high-value hard tasks with ample budget. |
| O-M21 | S1 | A04 310 : 330 A09 | A09; A04 loss 3 (eliminated) | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for one unusually ambiguous high-risk architecture decision. |
| O-M22 | S2 | A10 345 : 380 A05 | A05; A10 loss 3 (eliminated) | Largest weighted design advantage: production qualification path. Loser remains relevant for a small fleet with strict repo-specific automation. |
| O-M23 | S3 | A08 400 : 330 A02 | A08; A02 loss 2 | Largest weighted design advantage: recovery. Loser remains relevant for one trusted repository and short tasks. |
| O-M24 | S5 | A03 335 : 355 A07 | A07; A03 loss 3 (eliminated) | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for isolated issue repair with strong supplied tests. |
| O-M25 | S1 | A09 330 : 340 A12 | A12; A09 loss 3 (eliminated) | Largest weighted design advantage: production qualification path. Loser remains relevant for loosely coupled open-ended discovery. |
| O-M26 | S2 | A05 380 : 305 A08 | A05; A08 loss 1 | Largest weighted design advantage: migration/maintenance burden. Loser remains relevant for many isolated repositories across multiple hosts. |
| O-M27 | S3 | A06 395 : 330 A02 | A06; A02 loss 3 (eliminated) | Largest weighted design advantage: recovery. Loser remains relevant for one trusted repository and short tasks. |
| O-R6-BYE | — | A05 bye | No match/loss | — |
| O-M28 | S1 | A06 380 : 400 A08 | A08; A06 loss 2 | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for already-operated multi-host Temporal estate. |
| O-M29 | S2 | A07 345 : 285 A12 | A07; A12 loss 3 (eliminated) | Largest weighted design advantage: execution economy. Loser remains relevant for rare high-value hard tasks with ample budget. |
| O-M30 | S2 | A06 305 : 345 A07 | A07; A06 loss 3 (eliminated) | Largest weighted design advantage: execution economy. Loser remains relevant for already-operated multi-host Temporal estate. |
| O-M31 | S3 | A05 435 : 400 A08 | A05; A08 loss 2 | Largest weighted design advantage: migration/maintenance burden. Loser remains relevant for many isolated repositories across multiple hosts. |
| O-R8-BYE | — | A07 bye | No match/loss | — |
| O-M32 | S3 | A08 400 : 435 A05 | A05; A08 loss 3 (eliminated) | Largest weighted design advantage: migration/maintenance burden. Loser remains relevant for many isolated repositories across multiple hosts. |
| O-M33 | S4 | A05 390 : 360 A07 | A05; A07 loss 3 (eliminated) | Largest weighted design advantage: autonomous lifecycle coverage. Loser remains relevant for organization already standardized on LangGraph. |
| H-M1 | S1 | H01 405 : 485 H02 | H02; H01 loss 1 | Largest weighted design advantage: production qualification path. Loser remains relevant for few trusted repositories and repair-focused workloads. |
| H-M2 | S2 | H03 350 : 395 H04 | H04; H03 loss 1 | Largest weighted design advantage: execution economy. Loser remains relevant for a large existing distributed deployment. |
| H-M3 | S2 | H04 395 : 445 H01 | H01; H04 loss 1 | Largest weighted design advantage: execution economy. Loser remains relevant for a Roblox-only product with established Studio workers. |
| H-M4 | S3 | H03 440 : 480 H02 | H02; H03 loss 2 | Largest weighted design advantage: execution economy. Loser remains relevant for a large existing distributed deployment. |
| H-M5 | S3 | H04 400 : 440 H03 | H03; H04 loss 2 | Largest weighted design advantage: recovery. Loser remains relevant for a Roblox-only product with established Studio workers. |
| H-M6 | S4 | H02 485 : 390 H01 | H02; H01 loss 2 | Largest weighted design advantage: learning/privacy separation. Loser remains relevant for few trusted repositories and repair-focused workloads. |
| H-M7 | S4 | H04 385 : 485 H02 | H02; H04 loss 3 (eliminated) | Largest weighted design advantage: cross-repository portability. Loser remains relevant for a Roblox-only product with established Studio workers. |
| H-M8 | S5 | H01 425 : 395 H03 | H01; H03 loss 3 (eliminated) | Largest weighted design advantage: migration/maintenance burden. Loser remains relevant for a large existing distributed deployment. |
| H-M9 | S5 | H02 465 : 425 H01 | H02; H01 loss 3 (eliminated) | Largest weighted design advantage: production qualification path. Loser remains relevant for few trusted repositories and repair-focused workloads. |

Original survivor: **A05**, zero design losses; every other original has three. Hybrid survivor: **H02**, zero design losses; every other hybrid has three. These are conditional design selections. No actual execution success is inferred from an undefeated preference record.

## Four coherent hybrids and integration costs

| ID | Hybrid | Borrowed components | Q/A/E/R/P/L/M | Coherence and new weakness |
|---|---|---|---|---|
| H01 | Minimal loop plus durable kernel | A03+A05 | 4/4/5/4/4/3/5 | small builder and existing recovery; less complete learning/domain separation. |
| H02 | Flexible packages plus tenant-scoped learning and domain adapters | A05+A03; EX04/05/08/09 patterns; local caches and draft broker | 5/5/4/5/5/5/4 | whole-lifecycle coverage with selective execution and explicit data boundaries; more boundary integration than H01; gains unmeasured. |
| H03 | Distributed durable workers plus shared control service | A06+A08+EX03 | 5/5/2/5/5/5/2 | multi-host scaling and isolation; infrastructure and migration expense at current scale. |
| H04 | Roblox-specialized autonomous studio | A05+A11+EX09-15 | 5/4/4/4/2/4/3 | deep domain runtime acceptance and focused curriculum; general repository portability and whole-OS breadth. |

**H01: minimal durable worker.** The kernel owns mission/effect state, the builder sees a compact bounded packet and executes a simple tool loop, and Curator qualifies one candidate. It resolves A03's restart/publication gap and A05's unnecessary role/context overhead. It is the strongest simpler fallback. It does not independently solve endpoint custody or external draft lifecycle; adding those later converges toward H02.

**H02: flexible packages with scoped learning and domain adapters.** One durable composition root connects the existing queue, campaign continuity, graph compiler, role applicability and exact-candidate delivery. Existing capsules/reuse/cache utilities reduce duplicate work. Tenant/private-app learning and export drafts are separate typed paths. Endpoint evaluator custody and Roblox runtime profiles plug into generic acceptance adapters. New costs are boundary integration, schema migrations, profile qualification and keeping evidence trustworthy under caching. It resolves those costs through N03/N04 stable contracts, N18/N19 isolation, N28 composition and N29 negative controls.

**H03: distributed durable fleet.** A workflow service coordinates ephemeral SDK/VM workers and tenant stores across hosts. It borrows strong recovery and scale components, but introduces multi-store consistency, fleet credentials and operations before scale needs are evidenced. It can win later if queue/fleet measurements demonstrate a bottleneck that the simpler service cannot meet. Keep adapters replaceable so that later migration remains possible.

**H04: specialized Roblox studio.** A domain curriculum, Rojo build adapter and Studio/game oracle drive a focused builder on explicit gameplay acceptance. It can outperform a generic stack on domain-specific acceptance completeness after qualification. It loses whole-repository portability if domain logic enters the kernel. Preserve it as a domain profile under H02, with target-specific code and learning staying private.

Hybrids were stressed against privacy, failure and composition scenarios, rather than credited automatically for having more features. Their favorable ratings are still untested architecture judgments. N30 uses fresh harder tasks for measured hybrid evaluation because design has consumed the earlier findings.

## Final championship: original A05 versus hybrid H02

| Scenario | A05 design points | H02 design points | Conditional selection |
|---|---:|---:|---|
| S1 | 415 | 485 | H02 |
| S2 | 380 | 450 | H02 |
| S3 | 435 | 480 | H02 |
| S4 | 390 | 485 | H02 |
| S5 | 400 | 465 | H02 |

**Design decision: ADAPT H02 for implementation, retaining H01 as the simpler fallback and H04 as a domain profile.** The reason is direct coverage of the user's requested autonomous lifecycle plus external learning isolation and concrete removal of currently unused efficiency seams. It is not a claim that a speculative combination has already outperformed working products.

### Attack the winner

1. **Integration burden can erase efficiency gains.** The minimum proof is an actual queued mission through the canonical bindings, iterative builder, independent verifier and real scoped PR broker. N08–N16 and N28 own it.
2. **Security can be claimed by names rather than enforcement.** N18 needs actual denied filesystem/network/process probes; N19 needs trusted tenant handles. Process-only compatibility cannot pass hostile-repository acceptance.
3. **Caches can create stale or self-approved evidence.** N06/N14 bind exact inputs, check purposes and reviewer trust domains. Cache misses are normal; they do not trigger repeated court debate.
4. **Draft lessons can become covert data/code transfer.** N20/N21 constrain the output grammar, staged diff and outgoing body, retain private custody and enforce no active retrieval on publication.
5. **Public endpoints can reward memorization.** N22–N25 separate training/development/holdout by family, hide final data until sealing and retain public-pretraining caveats. Better source similarity is not better production behavior.
6. **Production Roblox requires unavailable assets/runtime.** N26/N27 distinguish package builds from engine/device evidence. Missing prerequisites remain obligations; the system does not invent them.
7. **Role reuse could become role omission.** N12 must prove meaningful required outcomes and legitimate deterministic/prior dispositions. Fewer calls are useful only when evidence and independence remain adequate.
8. **Autonomous discovery can optimize easy PRs.** N11/N02 compare opportunity value and record no-change/rejected work, defects and actual outcomes rather than PR counts.

### Sensitivity and conditions that reverse the choice

The winner's high Q/A/L ratings are design assumptions that must be independently tested. If scoped learning/domain support is not required and implementation economy dominates, H01 is preferable. For example, a deliberately narrow weighting of 10/5/60/5/5/5/10 gives H01 465 versus H02 430 preference points; this is a changed objective, not a benchmark result. For a large already-operated distributed fleet, H03 may overcome its migration disadvantage. For only Roblox, H04's specialization can be preferable. If integrated measurements show no efficiency gain, keep the existing qualified champion or H01 and revise the package design. There is no immutable champion-by-document.

## Court and execution obligations

The independent review is recorded in [REVIEW.md](REVIEW.md). Root authored the architecture priors and advocated their fit; the repository auditor supplied actual seam evidence; the source researcher supplied independent technical testimony; the learning examiner challenged historical/privacy assumptions; a separately tasked judge reviewed the design without authoring it. This is agent-session independence under one host administration, not externally independent principal assurance.

The selected design maps into [dag-index.json](dag-index.json). N00/N01 reconcile and adjudicate source/contract claims; N02 freezes actual measurement; N03–N29 build and qualify the implementation; N30 runs the measured tournament; N31/N32 demonstrate self/external operation; N33 closes outcomes. No measured competitor, production game, archive-complete source intake, operational all-role lifecycle or self-improvement win is claimed by this design tournament.
