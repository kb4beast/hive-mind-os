# Courtroom Synthesis and Founding Source Docket

## Binding rule

Every user requirement, image, repository, paper, video, benchmark, and newly discovered source enters Hive Mind OS as evidence. No agent may silently omit, merge away, or forget an idea. Each atomic claim receives a docket number, advocate, cross-examination, expert review, disposition, architecture mapping, acceptance test, outcome metric, and appeal path.

The complete machine-readable registry is `src/hive_mind_os/founding_docket.py`; `src/hive_mind_os/source_docket.py` builds and audits the docket; `src/hive_mind_os/courtroom.py` enforces evidence burdens and independent adjudication.

## Procedure

1. **Clerk:** preserve source identity, pinned version/digest, license, retrieval context, and completeness.
2. **Explorer:** extract atomic claims and prove source coverage.
3. **Advocate:** present the strongest evidence-supported case for each claim.
4. **Cross-Examiner:** seek contradictions, failure modes, lock-in, licensing problems, unsafe incentives, hidden costs, and counterexamples.
5. **Experts:** independent product, architecture, security, SRE, data/ML, legal/license, UX, and outcome agents testify as applicable.
6. **Judges:** issue `adopt`, `adapt`, `defer`, `reject`, or `quarantine` verdicts under a declared burden.
7. **Builder:** implement adopted/adapted claims as challengers with traceable tests and rollback.
8. **Curator:** reproduce claims independently. New material evidence may appeal a verdict; prior records remain append-only.

## Burdens of proof

| Burden | Required showing |
|---|---|
| Capture | Preserve identity and uncertainty; never invent unavailable content |
| Design | Supporting evidence, adversarial challenge, architecture and acceptance-test mapping |
| Implement | Design burden plus executable verification, isolation, and rollback |
| Promote | Code/test receipts, held-out outcomes, independent judges, and regression limits |
| Superiority | Multiple pinned comparators, equal budgets, reproducible benchmarks, safety floors, and statistical uncertainty |

## Founding sources

| ID | Source | Status | Pinned evidence |
|---|---|---|---|
| SRC-001 | Founding autonomous-SDLC prompt | verified | conversation:2026-07-27 |
| SRC-002 | New Team Model and Product & Engineering slides | verified | supplied image files |
| SRC-003 | Operator OS | verified | pinned repository content |
| SRC-004 | Hermes Agent | verified | pinned repository content |
| SRC-005 | `mazBhCg3urw` autonomous OS video | pending ingestion | video ID preserved |
| SRC-006 | `Gw_hnD7m00M` competitive autonomous-agent video | partial | video ID plus related research framing |
| SRC-007 | Natural Selection Favors AIs over Humans | verified | arXiv:2303.16200 |
| SRC-008 | AIOS | verified | pinned repository content |
| SRC-009 | OpenHands | verified | arXiv:2407.16741 and repository |
| SRC-010 | Rivet Agent OS | verified | pinned retrieval record |
| SRC-011 | Microsoft Agent Framework | verified | pinned retrieval record |
| SRC-012 | RepoMaster | verified | arXiv:2505.21577 |
| SRC-013 | User-supplied mission-control interface video | verified | project reference and extracted requirements |
| SRC-014 | OpenFang | verified | pinned release/repository record |
| SRC-015 | iii AgentOS | verified | pinned retrieval record |

## Atomic case inventory

The founding docket contains **57 separately adjudicated claims**. The exact propositions, source relationships, verdicts, rationale, architecture anchors, tests, metrics, code receipts, benchmark receipts, and implementation states are in `src/hive_mind_os/founding_docket.py`.

### Founding vision and team model — CASE-001 through CASE-011

- zero discretionary supervision for routine reversible work;
- autonomous research, problem finding, ideation, implementation, testing, and delivery;
- first-commit-forward anti-cheat learning;
- outcome learning and cross-agent teaching;
- benchmark-only superiority claims;
- eight mandatory independent specialist roles;
- customer-value lifecycle organization;
- bounded orchestration of humans and agents;
- AI force multiplication across the lifecycle;
- delivery, quality, alignment, coordination, and growth metrics;
- provider-neutral constitutional values.

### Operator OS — CASE-012 through CASE-016

- separation of constitution/SOPs, agent identity, deterministic skills, workflows, and knowledge;
- deterministic execution with models used for judgment;
- progressive context disclosure;
- evidence-gated self-annealing;
- role-scoped, provider-neutral tool and MCP adapters.

### Hermes Agent — CASE-017 through CASE-022

- closed memory/skill/outcome learning loops;
- unattended scheduled automation and multichannel delivery;
- isolated parallel subagents;
- model, channel, and execution-backend portability;
- searchable cross-session memory with correction and forgetting;
- retained/compressed execution trajectories for evaluation and training.

### Video and evolutionary safety evidence — CASE-023 through CASE-027

- mandatory transcript/artifact ingestion for `mazBhCg3urw`, with all derived claims deferred until verified;
- bounded population-based strategy variation and selection;
- threat modeling of survival, profit, replication, and resource-acquisition incentives;
- prohibition of concealment, authority seeking, mission mutation, and unbounded replication;
- finite budgets, cooperation-weighted fitness, quarantine, and independent promotion gates.

### AIOS and OpenHands — CASE-028 through CASE-035

- separation between agent-facing SDKs and the kernel;
- independent management of models, context, memory, storage, tools, scheduling, and resources;
- typed syscalls and sandbox/tool managers instead of ambient access;
- local, remote, personal, and virtualized deployment contracts;
- first-class terminal, code, browser, and file operations;
- isolated metered execution;
- reproducible software/web benchmark evaluation;
- explicit delegation and artifact-based multi-agent coordination.

### Rivet Agent OS — CASE-036 through CASE-040

- WASM/isolate execution as a low-risk tier;
- individually leasable deny-by-default filesystem, network, process, environment, CPU, and memory authority;
- universal replayable transcripts;
- durable cron, webhook, queue, retry, branch, checkpoint, and resume primitives;
- inherited identity, authorization, budget, and audit chains for tools and agent calls.

### Microsoft Agent Framework — CASE-041 through CASE-043

- sequential, concurrent, handoff, and group workflow graphs;
- versioned MCP, A2A, AG-UI, provider, and hosting adapters;
- language-neutral kernel contracts with Python and .NET clients.

### RepoMaster — CASE-044 through CASE-046

- function-call graphs, module-dependency graphs, and hierarchical code trees;
- progressive repository exploration and irrelevant-context pruning;
- measured task lift and token/cost reduction against baselines.

### Mission-control interface — CASE-047 through CASE-050

- live rooms and state for each autonomous department;
- task, confidence, evidence, cost, latency, risk, performance, and outcome telemetry;
- supervisor views for delegation, dependencies, disputes, courts, and blocked decisions;
- inspectable memory, integrations, schedules, and learning history.

### OpenFang and iii AgentOS — CASE-051 through CASE-057

- tamper-evident hash/Merkle audit records;
- reusable autonomous capabilities and channel adapters behind policy contracts;
- independent reproduction before accepting performance/superiority claims;
- workers, functions, and triggers as minimal runtime primitives;
- runtime-generated candidate functions only in challenger lanes;
- stale/dead-agent detection and checkpoint recovery;
- defense in depth through RBAC, encrypted secrets, sandboxing, signed requests, and tamper-evident audit.

## Blocking evidence obligations

- **SRC-005:** no verified transcript/artifact set is currently available. Its contents cannot be invented; CASE-023 remains deferred.
- **SRC-006:** the paper-grounded evolutionary threat model is captured, but video-specific claims remain blocked pending full timestamped ingestion.
- The docket is **inventory-complete** but intentionally **not source-complete** while these obligations remain.

## Completeness rules

- Every registered source must own at least one atomic claim.
- Every claim must have a courtroom disposition and adversarial record.
- Adopted/adapted claims must map to architecture and acceptance tests.
- Implemented claims must carry code and test receipts.
- Promoted claims must carry independent outcome evidence and rollback.
- Superiority claims must carry multi-comparator benchmark receipts.
- Unavailable or disputed sources remain explicit blockers rather than disappearing.

## Appeals and future sources

Explorer continuously scouts repositories, papers, incidents, benchmarks, and product signals. Discovery never mutates production behavior directly. A new source first enters this docket, then passes provenance/license review, advocate and cross-examiner briefs, expert testimony, judge verdict, challenger implementation, independent validation, measured outcomes, and an appeal decision.
