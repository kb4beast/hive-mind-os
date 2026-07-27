from __future__ import annotations

from dataclasses import dataclass

from .courtroom import BurdenOfProof, Disposition, ImplementationState, SourceRecord, SourceStatus


@dataclass(frozen=True, slots=True)
class ClaimSpec:
    id: str
    sources: tuple[str, ...]
    proposition: str
    category: str
    disposition: Disposition = Disposition.ADOPT
    burden: BurdenOfProof = BurdenOfProof.DESIGN
    state: ImplementationState = ImplementationState.PLANNED
    section: str = "core"
    code_refs: tuple[str, ...] = ()
    test_refs: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    benchmark_refs: tuple[str, ...] = ()
    comparators: tuple[str, ...] = ()
    rationale: str | None = None


SOURCES: tuple[SourceRecord, ...] = (
    SourceRecord(
        id='SRC-001', title='Founding autonomous-SDLC prompt',
        uri='user-supplied:founding-prompt', kind='user_requirement',
        status=SourceStatus.VERIFIED, version_ref='conversation:2026-07-27',
        license_spdx=None, content_digest='prompt-v1',
    ),
    SourceRecord(
        id='SRC-002', title='New Team Model and Product & Engineering slides',
        uri='user-supplied:new-team-model-images', kind='image_deck',
        status=SourceStatus.VERIFIED, version_ref='files:927059b1+1f461893',
        license_spdx=None, content_digest='image-deck-v1',
    ),
    SourceRecord(
        id='SRC-003', title='Operator OS',
        uri='https://github.com/rangerrick337/operator-os', kind='repository',
        status=SourceStatus.VERIFIED, version_ref='e05d6c866181979015c82ce0163ad5383c2ca438',
        license_spdx='MIT', content_digest=None,
    ),
    SourceRecord(
        id='SRC-004', title='Hermes Agent',
        uri='https://github.com/NousResearch/hermes-agent', kind='repository',
        status=SourceStatus.VERIFIED, version_ref='d78d6d57f04563f85c4b545703317bed77b6b9b5',
        license_spdx='MIT', content_digest=None,
    ),
    SourceRecord(
        id='SRC-005', title='Autonomous operating-system reference video',
        uri='https://www.youtube.com/watch?v=mazBhCg3urw', kind='video',
        status=SourceStatus.PENDING_INGESTION, version_ref='youtube:mazBhCg3urw',
        license_spdx=None, content_digest=None,
    ),
    SourceRecord(
        id='SRC-006', title='What Happens When Millions of AIs Must Profit or Die',
        uri='https://www.youtube.com/watch?v=Gw_hnD7m00M', kind='video',
        status=SourceStatus.PARTIAL, version_ref='youtube:Gw_hnD7m00M',
        license_spdx=None, content_digest=None,
    ),
    SourceRecord(
        id='SRC-007', title='Natural Selection Favors AIs over Humans',
        uri='https://arxiv.org/abs/2303.16200', kind='research_paper',
        status=SourceStatus.VERIFIED, version_ref='arXiv:2303.16200',
        license_spdx=None, content_digest=None,
    ),
    SourceRecord(
        id='SRC-008', title='AIOS: AI Agent Operating System',
        uri='https://github.com/agiresearch/AIOS', kind='repository',
        status=SourceStatus.VERIFIED, version_ref='5354f64f7975f03a99a305285702194d6f72bfa9',
        license_spdx=None, content_digest=None,
    ),
    SourceRecord(
        id='SRC-009', title='OpenHands generalist software-agent platform',
        uri='https://arxiv.org/abs/2407.16741', kind='research_and_repository',
        status=SourceStatus.VERIFIED, version_ref='arXiv:2407.16741',
        license_spdx='MIT', content_digest=None,
    ),
    SourceRecord(
        id='SRC-010', title='Rivet Agent OS',
        uri='https://github.com/rivet-dev/agent-os', kind='repository',
        status=SourceStatus.VERIFIED, version_ref='main@retrieved-2026-07-27',
        license_spdx=None, content_digest=None,
    ),
    SourceRecord(
        id='SRC-011', title='Microsoft Agent Framework',
        uri='https://github.com/microsoft/agent-framework', kind='repository',
        status=SourceStatus.VERIFIED, version_ref='main@retrieved-2026-07-27',
        license_spdx='MIT', content_digest=None,
    ),
    SourceRecord(
        id='SRC-012', title='RepoMaster repository-understanding research',
        uri='https://arxiv.org/abs/2505.21577', kind='research_paper',
        status=SourceStatus.VERIFIED, version_ref='arXiv:2505.21577',
        license_spdx=None, content_digest=None,
    ),
    SourceRecord(
        id='SRC-013', title='User-supplied multi-agent mission-control interface video',
        uri='user-supplied:mission-control-video', kind='video',
        status=SourceStatus.VERIFIED, version_ref='project-reference:mission-control-ui',
        license_spdx=None, content_digest='mission-control-reference-v1',
    ),
    SourceRecord(
        id='SRC-014', title='OpenFang agent operating system',
        uri='https://github.com/RightNow-AI/openfang', kind='repository',
        status=SourceStatus.VERIFIED, version_ref='v0.5.10',
        license_spdx='MIT', content_digest=None,
    ),
    SourceRecord(
        id='SRC-015', title='iii AgentOS',
        uri='https://github.com/iii-hq/agentos', kind='repository',
        status=SourceStatus.VERIFIED, version_ref='main@retrieved-2026-07-27',
        license_spdx=None, content_digest=None,
    ),
)


CLAIMS: tuple[ClaimSpec, ...] = (
    ClaimSpec('CLM-001', ('SRC-001',), 'Routine reversible work should run end-to-end without discretionary human supervision', 'autonomy', disposition=Disposition.ADAPT, section='constitutional-and-court-governance', rationale='Adopt no-supervision as the target for routine reversible work, while retaining external authorization for critical boundaries.'),
    ClaimSpec('CLM-002', ('SRC-001',), 'Agents should independently search the web and repositories, find problems, propose ideas, implement fixes, test, and deliver changes', 'end_to_end_delivery', section='role-and-workflow-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-003', ('SRC-001',), 'Repository learning must replay history from the first commit and hide the target and all future commits', 'anti_cheat_learning', burden=BurdenOfProof.IMPLEMENT, state=ImplementationState.IMPLEMENTED, section='learning-and-evolution-plane', code_refs=('src/hive_mind_os/repository_learning.py',), test_refs=('tests/test_repository_learning.py',), metrics=('leakage_rate=0',), rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-004', ('SRC-001',), 'The system should learn from outcomes and teach validated lessons to peer agents', 'learning', burden=BurdenOfProof.IMPLEMENT, state=ImplementationState.IMPLEMENTED, section='learning-and-evolution-plane', code_refs=('src/hive_mind_os/autonomy.py',), test_refs=('tests/test_autonomy.py',), metrics=('validated_lesson_reuse_rate', 'regression_rate_after_teaching'), rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-005', ('SRC-001', 'SRC-003', 'SRC-004', 'SRC-008', 'SRC-009', 'SRC-010', 'SRC-011', 'SRC-014', 'SRC-015'), 'Hive Mind OS may claim superiority only after reproducible benchmark courts beat multiple pinned comparators', 'benchmarking', disposition=Disposition.ADAPT, burden=BurdenOfProof.SUPERIORITY, section='assurance-and-benchmark-plane', metrics=('task_success_rate', 'cost_per_success', 'time_to_verified_delivery', 'security_violation_rate', 'recovery_rate'), benchmark_refs=('benchmarks/founding-comparator-suite.json',), comparators=('SRC-003', 'SRC-004', 'SRC-008', 'SRC-009', 'SRC-010', 'SRC-011', 'SRC-014', 'SRC-015'), rationale='Reject marketing-only superiority; permit the claim only after the benchmark court meets the highest burden.'),
    ClaimSpec('CLM-006', ('SRC-002',), 'The eight specialist roles are mandatory independent agents', 'team_model', burden=BurdenOfProof.IMPLEMENT, state=ImplementationState.IMPLEMENTED, section='role-and-workflow-plane', code_refs=('src/hive_mind_os/roles.py', 'src/hive_mind_os/vision.py'), test_refs=('tests/test_kernel.py', 'tests/test_vision.py'), rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-007', ('SRC-002',), 'Work is organized around customer value and lifecycle outcomes rather than legacy job titles', 'operating_model', section='constitutional-and-court-governance', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-008', ('SRC-002',), 'The Orchestrator sets vision and outcomes, allocates human and AI capacity, manages tradeoffs, risk, flow, and dependencies', 'orchestration', disposition=Disposition.ADAPT, section='control-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-009', ('SRC-002',), 'AI should multiply discovery, prototyping, coding, testing, defect detection, optimization, documentation, and integration', 'force_multiplier', section='role-and-workflow-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-010', ('SRC-002',), 'The operating system should measure faster delivery, higher quality, stronger alignment, lower coordination friction, and scalable growth', 'outcomes', section='assurance-and-benchmark-plane', metrics=('lead_time', 'change_failure_rate', 'acceptance_pass_rate', 'rework_rate', 'coordination_interventions', 'cost_per_verified_outcome'), rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-011', ('SRC-002',), 'Client value, integrity, respect, excellence, and teamwork are constitutional fitness dimensions', 'values', disposition=Disposition.ADAPT, section='constitutional-and-court-governance', rationale='Translate corporate values into provider-neutral measurable invariants: customer value, truthfulness, non-deceptive conduct, quality, and cooperation.'),
    ClaimSpec('CLM-012', ('SRC-003',), 'Separate procedures, agent identities, deterministic skills, workflows, and knowledge', 'architecture_layers', disposition=Disposition.ADAPT, section='knowledge-skill-and-workflow-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-013', ('SRC-003',), 'Use deterministic code for repeatable execution and models for judgment and orchestration', 'determinism', section='execution-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-014', ('SRC-003',), 'Load context progressively rather than placing the entire operating system into every prompt', 'context_management', section='knowledge-skill-and-workflow-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-015', ('SRC-003',), 'Errors should produce repaired skills and documentation with evidence and regression tests', 'self_annealing', disposition=Disposition.ADAPT, section='learning-and-evolution-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-016', ('SRC-003',), 'Tool permissions and MCP-style adapters should be role-scoped and provider-neutral', 'tools', section='execution-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-017', ('SRC-004',), 'Memory, skills, and lessons should form a closed outcome-learning loop across sessions', 'memory', disposition=Disposition.ADAPT, section='learning-and-evolution-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-018', ('SRC-004',), 'Natural-language scheduled automations should run unattended and deliver results across channels', 'scheduler', section='control-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-019', ('SRC-004',), 'Agents should spawn isolated subagents for parallel workstreams', 'parallelism', disposition=Disposition.ADAPT, section='role-and-workflow-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-020', ('SRC-004',), 'Models, messaging channels, and execution backends should be replaceable without rewriting role logic', 'portability', section='integration-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-021', ('SRC-004',), 'Cross-session memory should support search, summarization, durable user/project models, and explicit forgetting', 'memory', disposition=Disposition.ADAPT, section='knowledge-skill-and-workflow-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-022', ('SRC-004',), 'Execution trajectories should be retained and compressed for evaluation and future training', 'training_data', disposition=Disposition.ADAPT, section='learning-and-evolution-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-023', ('SRC-005',), 'Every atomic idea in the mazBhCg3urw video must be transcript-ingested, time-coded, cross-examined, and mapped before promotion', 'source_ingestion', disposition=Disposition.DEFER, burden=BurdenOfProof.CAPTURE, state=ImplementationState.INVENTORIED, rationale='Preserve the source and block false completeness until verified transcript/artifacts are available.'),
    ClaimSpec('CLM-024', ('SRC-006', 'SRC-007'), 'Population-based variation, environmental feedback, and selection can improve agent strategies', 'evolution', disposition=Disposition.ADAPT, burden=BurdenOfProof.IMPLEMENT, state=ImplementationState.IMPLEMENTED, section='learning-and-evolution-plane', code_refs=('src/hive_mind_os/autonomy.py',), test_refs=('tests/test_autonomy.py',), metrics=('challenger_lift', 'regression_rate'), rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-025', ('SRC-006', 'SRC-007'), 'Profit, survival, replication, and resource-acquisition pressure can select unsafe agent behavior', 'threat_model', section='constitutional-and-court-governance', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-026', ('SRC-006', 'SRC-007'), 'Hive Mind OS must reject survival incentives, concealed activity, unbounded replication, and authority-seeking', 'safety', burden=BurdenOfProof.IMPLEMENT, state=ImplementationState.IMPLEMENTED, section='constitutional-and-court-governance', code_refs=('src/hive_mind_os/autonomy.py', 'src/hive_mind_os/policy.py'), test_refs=('tests/test_autonomy.py', 'tests/test_policy_invariants.py'), rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-027', ('SRC-006', 'SRC-007'), 'Resource budgets, quarantine, and cooperation-weighted fitness must bound autonomous evolution', 'safety', burden=BurdenOfProof.IMPLEMENT, state=ImplementationState.IMPLEMENTED, section='learning-and-evolution-plane', code_refs=('src/hive_mind_os/autonomy.py',), test_refs=('tests/test_autonomy.py',), rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-028', ('SRC-008',), 'Separate an agent-facing SDK from the kernel control plane', 'kernel', disposition=Disposition.ADAPT, section='control-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-029', ('SRC-008',), 'The kernel should independently manage models, context, memory, storage, tools, scheduling, and resource allocation', 'kernel', section='control-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-030', ('SRC-008',), 'Agent operations should use typed syscalls through a sandbox and tool manager rather than direct ambient access', 'syscalls', disposition=Disposition.ADAPT, section='execution-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-031', ('SRC-008',), 'Local, remote, personal, and virtualized kernel deployment modes should share one contract', 'deployment', disposition=Disposition.ADAPT, section='integration-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-032', ('SRC-009',), 'Software agents need first-class terminal, code, browser, and file interaction', 'developer_agent', section='execution-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-033', ('SRC-009', 'SRC-010', 'SRC-014', 'SRC-015'), 'Code execution must occur in isolated, metered, deny-by-default sandboxes', 'sandbox', section='execution-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-034', ('SRC-009',), 'Agent quality must be measured on reproducible software-engineering and web task benchmarks', 'evaluation', section='assurance-and-benchmark-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-035', ('SRC-009',), 'Multiple agents should coordinate through explicit delegation and shared artifacts rather than hidden chat context', 'coordination', disposition=Disposition.ADAPT, section='role-and-workflow-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-036', ('SRC-010',), 'WASM or isolate-based lightweight sandboxes are a candidate execution tier for fast low-risk tasks', 'sandbox', disposition=Disposition.ADAPT, section='execution-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-037', ('SRC-010',), 'Filesystem, network, process, environment, CPU, and memory permissions must be deny-by-default and individually leasable', 'security', section='execution-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-038', ('SRC-010',), 'All model and tool interactions should use a universal transcript format with replayable sessions', 'observability', disposition=Disposition.ADAPT, section='evidence-and-memory-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-039', ('SRC-010', 'SRC-004'), 'Cron, webhooks, queues, retries, branching, checkpoints, and resume should be durable runtime primitives', 'durability', section='control-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-040', ('SRC-010',), 'Host tools and agent-to-agent calls must inherit the caller identity, authorization, and audit chain', 'identity', disposition=Disposition.ADAPT, section='integration-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-041', ('SRC-011',), 'Sequential, concurrent, handoff, and group-collaboration workflows should be first-class graph patterns', 'orchestration', section='role-and-workflow-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-042', ('SRC-011',), 'MCP, A2A, AG-UI, model providers, and hosting environments should connect through versioned adapters', 'interoperability', disposition=Disposition.ADAPT, section='integration-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-043', ('SRC-011',), 'The kernel should support production-grade Python and .NET clients without coupling core semantics to either language', 'sdk', disposition=Disposition.ADAPT, section='integration-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-044', ('SRC-012',), 'Repository understanding should build function-call graphs, module-dependency graphs, and hierarchical code trees', 'repository_intelligence', disposition=Disposition.ADAPT, section='repository-intelligence-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-045', ('SRC-012',), 'Agents should progressively explore relevant repository components and prune irrelevant context', 'context_management', section='repository-intelligence-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-046', ('SRC-012',), 'Repository-intelligence improvements must report task lift and token/cost reduction against a baseline', 'evaluation', disposition=Disposition.ADAPT, section='assurance-and-benchmark-plane', metrics=('valid_submission_rate', 'task_pass_rate', 'token_cost', 'retrieval_precision'), rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-047', ('SRC-013',), 'A mission-control interface should visualize each autonomous department as a live room with current state', 'experience', disposition=Disposition.ADAPT, section='experience-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-048', ('SRC-013',), 'The interface should expose tasks, confidence, evidence, cost, latency, performance, risk, and realized outcomes', 'experience', section='experience-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-049', ('SRC-013', 'SRC-002'), 'A supervisor view should show Orchestrator delegation, dependencies, disputes, courtroom cases, and blocked decisions', 'experience', disposition=Disposition.ADAPT, section='experience-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-050', ('SRC-013', 'SRC-004'), 'Persistent memory, integrations, and learning history should be inspectable from the mission-control interface', 'experience', disposition=Disposition.ADAPT, section='experience-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-051', ('SRC-014',), 'Merkle or hash-chained audit records should make evidence tampering detectable', 'audit', disposition=Disposition.ADAPT, section='evidence-and-memory-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-052', ('SRC-014',), 'Reusable autonomous hands and broad channel adapters should be packaged capabilities behind policy contracts', 'capabilities', disposition=Disposition.ADAPT, section='knowledge-skill-and-workflow-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-053', ('SRC-014',), 'Cold-start, memory, security-layer, and install-size superiority claims require independent reproduction', 'benchmarking', disposition=Disposition.DEFER, burden=BurdenOfProof.SUPERIORITY, state=ImplementationState.INVENTORIED, rationale='Capture the claim but defer any adoption or superiority inference until independently reproduced.'),
    ClaimSpec('CLM-054', ('SRC-015',), 'Workers, functions, and triggers are a useful minimal event-bus primitive set', 'runtime_primitives', disposition=Disposition.ADAPT, section='control-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-055', ('SRC-015',), 'Agents may generate candidate functions at runtime only inside a challenger lane with tests and promotion gates', 'self_modification', disposition=Disposition.ADAPT, section='learning-and-evolution-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
    ClaimSpec('CLM-056', ('SRC-015', 'SRC-004', 'SRC-010'), 'Health scanning should detect stale or dead agents and recover from durable checkpoints', 'reliability', section='control-plane', rationale='Adopt the capability behind enforceable evidence, authority, recovery, and outcome gates.'),
    ClaimSpec('CLM-057', ('SRC-015', 'SRC-014', 'SRC-010'), 'RBAC, encrypted secrets, sandboxing, signed requests, and tamper-evident audit should compose as defense in depth', 'security', disposition=Disposition.ADAPT, section='execution-plane', rationale='Adapt the useful mechanism while removing unsafe, unverifiable, or source-specific assumptions.'),
)
