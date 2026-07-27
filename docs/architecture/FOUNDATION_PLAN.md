# Hive Mind OS Foundation Plan

## Product thesis
The traditional SDLC grouped people by job title and moved work through handoffs. Hive Mind OS models the lifecycle as eight independent, continuously running specialist agents aligned around customer value. The kernel supplies scheduling, context, memory, tools, policy, evidence, evaluation, and recovery so the specialists can operate without routine supervision.

## Clean-room synthesis of useful patterns
The initial architecture builds on broad public patterns without copying implementation code:

- Operator OS: separate procedures, agents, deterministic skills, workflows, and knowledge.
- Hermes Agent: persistent memory, skills, scheduled work, subagents, provider portability, and sandboxed tools.
- AIOS-style systems: kernel-level scheduling and resource management for models, memory, storage, and tools.
- Modern agent runtimes: deny-by-default capabilities, isolated execution, observability, resumability, and event-driven work.

Hive Mind OS adds a software-delivery-specific evidence model, point-in-time repository learning, role separation, adversarial verification, and statistically gated self-improvement.

## Target architecture

```text
Outcomes / Signals
       |
       v
+------------------------- Control Plane --------------------------+
| Objective graph | Scheduler | Policy | Budget | Recovery        |
+-------------------------------+----------------------------------+
                                |
               +----------------+----------------+
               |                                 |
        Specialist agents                 Independent judges
  Orchestrator Explorer Architect      Curator Security Evaluator
  Builder Integrator Steward Optimizer  Regression / Outcome graders
               |                                 |
               +----------------+----------------+
                                |
+-------------------------- Agent Kernel ---------------------------+
| Model router | Tool router | Sandboxes | Context | Secrets       |
| Event bus    | Checkpoints | Identity  | Leases  | Rate limits   |
+-------------------------------+----------------------------------+
                                |
+------------------------ Evidence & Learning ----------------------+
| Immutable event ledger | Artifacts | Decisions | Repo snapshots |
| Skills | Episodic memory | Evals | Champion/challenger registry  |
+------------------------------------------------------------------+
```

## Autonomous lifecycle
1. **Orchestrator** turns an outcome into a dependency graph, risk register, and measurable acceptance criteria.
2. **Explorer** searches the target repository, its point-in-time history, user signals, incidents, and permitted external sources. It ranks problems by expected value and confidence.
3. **Architect** produces interfaces, invariants, threat models, migration and rollback plans, and architecture decisions.
4. **Builder** works in an isolated branch or workspace, implements the smallest complete change, and adds tests.
5. **Curator** independently verifies claims, tests, security, policy, provenance, and acceptance criteria. It cannot reuse the Builder's conclusions as evidence.
6. **Integrator** validates contracts and compatibility across systems and prepares a reversible integration path.
7. **Steward** observes runtime and repository health, repairs drift, maintains dependencies, and preserves runbooks.
8. **Optimizer** measures realized outcomes, extracts lessons, creates challenger skills/prompts/policies, and promotes only statistically supported improvements.

## Learning without cheating
For every repository, learning is replayed from the first commit forward. At commit N, an agent sees only the repository and external evidence available before N. Commit N becomes the outcome to predict, explain, reproduce, or improve. Future commits, later issue comments, and post-event documentation are inaccessible. Every replay records the visible cutoff, inputs, model, tools, output, score, and evaluator.

Learning layers:
- **Working memory:** bounded context for the active objective.
- **Episodic memory:** immutable run events and outcomes.
- **Semantic memory:** deduplicated facts with provenance and expiration.
- **Procedural memory:** versioned skills and workflows.
- **Evaluation memory:** failures, counterexamples, regressions, and regime labels.

Self-modification never edits the active champion in place. It creates a challenger, runs point-in-time and held-out evaluations, checks cost/latency/security regressions, then atomically promotes or rejects it.

## Autonomy model
- A0 Observe: read and report.
- A1 Advise: propose plans and patches.
- A2 Sandbox: edit and execute only in isolation.
- A3 Repository: create branches, commits, and pull requests.
- A4 Delivery: merge and deploy when objective evidence and policy gates pass.
- A5 Governed full autonomy: broader operations through scoped credentials, budgets, reversible actions, independent judges, and kill switches.

The goal is A5 for routine, reversible work—not unrestricted authority. Critical or irreversible actions remain bounded by external policy even when no person is in the loop.

## Build phases

### Phase 0 — kernel foundation (started)
- Typed objective, work, result, evidence, role, risk, and autonomy contracts.
- Eight role contracts and lifecycle routing.
- Append-only SQLite evidence ledger.
- Fail-closed policy engine.
- Point-in-time replay primitive and champion/challenger promotion gate.
- Offline deterministic backend, CLI, tests, and CI.

### Phase 1 — real repository worker
- Git adapter: clone, inspect, branch, diff, commit, PR, checks, rollback.
- Container sandbox with filesystem, network, CPU, time, and credential boundaries.
- Model-provider interface with structured outputs, retries, budgets, and model routing.
- Durable objective graph, leases, checkpoints, retries, cancellation, and resumability.

### Phase 2 — independent autonomous specialists
- Persistent event bus and one worker process per role.
- Role-specific prompts, tools, memory views, and conflict-of-interest controls.
- Curator adversarial review and reproducible acceptance-test generation.
- Integrator contract tests and multi-repository dependency graph.

### Phase 3 — repository time machine
- Full commit/branch/tag/issue/PR timeline ingestion.
- Point-in-time source and metadata cutoffs enforced in isolated snapshots.
- Defect-introduction, repair, architecture-evolution, and opportunity benchmarks.
- Leakage detectors and replay manifests.

### Phase 4 — self-teaching system
- Skill extraction from successful trajectories and root-cause analyses.
- Automatic curriculum generation from failures and repository history.
- Champion/challenger registry with held-out, cross-repository, and regime evaluations.
- Dynamic model/tool selection based on measured quality, cost, latency, and risk.

### Phase 5 — governed end-to-end delivery
- Autonomous issue discovery through production verification and rollback.
- Observability, SLOs, incident response, dependency maintenance, and outcome learning.
- Multi-tenant identity, secrets, policy-as-code, budgets, audit export, and kill switches.

## Immediate next slices
1. Add a Git sandbox adapter and a local repository benchmark fixture.
2. Replace the bootstrap backend with a provider-neutral structured-agent interface.
3. Persist objective graphs and resume interrupted runs.
4. Implement Curator separation: independent context, tests, and model selection.
5. Build the first point-in-time benchmark from Hive Mind OS's own commit history.

Sequencing for this work is now owned by `docs/plan/00_OVERVIEW.md` (see ADR-006);
this section remains as originally recorded.
