# Hardened Founding Vision Contract

## Status

This document is normative. It converts the founding prompt, the supplied “New Team Model” images, the referenced autonomous operating systems, and the linked autonomous-agent video into testable architecture requirements for Hive Mind OS.

The machine-readable counterpart is `src/hive_mind_os/vision.py`. A change that weakens this contract must be explicit, reviewed as an architecture decision, and accompanied by tests. Agents may not rewrite or bypass it during a mission.

## Founding intent

Hive Mind OS is not a chatbot collection, prompt library, or conventional workflow runner. It is an operating system for autonomous product and engineering work. Its target is to perform the complete AI-native successor to the software-development lifecycle with minimal routine human involvement.

The operating model is organized around customer value and lifecycle outcomes rather than traditional job titles. Every specialist is an independently executable agent with its own contract, memory, tools, evidence obligations, failure boundaries, and evaluation history.

The system must be able to:

1. Discover valuable problems.
2. Design scalable and secure solutions.
3. Build complete, tested changes.
4. Validate claims independently.
5. Integrate repositories, systems, tools, and data.
6. Maintain reliability and recoverability.
7. Measure outcomes and improve performance.
8. Teach validated lessons to other agents.
9. Continue work across interruptions without repeated prompting.
10. Produce reviewable, reversible, evidence-bearing delivery artifacts.

## Required specialist agents

All eight roles are mandatory. Omitting a role is a failed lifecycle, not an optimization.

| Agent | Non-delegable responsibility | Must not do |
|---|---|---|
| Orchestrator | Set outcomes, decompose work, manage dependencies, budgets, risk, and stopping conditions | Approve implementation quality |
| Explorer | Search repositories, history, user signals, incidents, and permitted web sources; rank problems and ideas | Modify production or approve its own findings |
| Architect | Produce interfaces, invariants, threat models, migration paths, and rollback plans | Quietly weaken constraints to simplify implementation |
| Builder | Implement the smallest complete solution, tests, branch, commits, and pull request | Grade or merge its own work |
| Curator | Independently verify correctness, evidence, security, compliance, provenance, and acceptance criteria | Reuse the Builder’s conclusions as independent evidence |
| Integrator | Validate contracts and compatibility across systems and data boundaries | Conceal breaking changes or lineage gaps |
| Steward | Maintain code health, dependencies, runtime health, recovery, and operational knowledge | Trade recoverability for short-term speed without evidence |
| Optimizer | Measure outcomes, run controlled experiments, manage champions/challengers, and promote proven improvements | Mutate the live champion without evaluation |

Agents may communicate and delegate, but they remain separately identifiable in the ledger. Independence means separate execution identity, evidence, and evaluation—not necessarily separate model vendors or processes.

## Required lifecycle

The system must cover every stage represented by the supplied team model:

- Discover
- Design
- Build
- Validate
- Grow
- Maintain
- Integrate

The lifecycle is a graph rather than a rigid waterfall. Stages may repeat or run concurrently, but a delivery cannot be declared complete until every applicable stage has objective evidence.

## Required autonomous capabilities

The operating system must eventually provide enforced adapters for all capabilities below:

- Outcome decomposition and dependency planning
- Web research with citations and retrieval timestamps
- Autonomous discovery and ranking of strong public repositories
- Repository inspection and structural understanding
- First-commit-forward point-in-time historical replay
- Hypothesis and novel-idea generation
- Evidence-based improvement proposals
- Isolated code modification
- Command and test execution
- Branch, commit, and pull-request creation
- Independent verification and adversarial review
- Cross-system integration and contract testing
- Runtime and product outcome observation
- Learning from predictions, actions, outcomes, and mistakes
- Cross-agent teaching from repeatedly supported lessons
- Checkpointing, recovery, retry, and resume

A capability declaration without an executable adapter and evidence is not implementation.

## Autonomous routine-work target

Routine, reversible work should require zero discretionary human supervision. A human should not need to:

- Restate the objective after a restart
- Tell an agent which file to inspect next
- Manually transfer findings between agents
- Remind an agent to test, review, document, or follow up
- Manually create the branch, commit, or pull request
- Decide whether the agent’s unsupported self-assessment is trustworthy

Human involvement remains permissible when an external policy requires authorization for critical or irreversible actions. Such intervention is a governance grant, not routine task management. The compliance gate distinguishes policy-required intervention from discretionary supervision.

## Point-in-time repository learning: no cheating

Repository learning must begin with the first commit and advance one commit at a time.

For target commit `N`:

- The learner may inspect only commits before `N`.
- The target commit, its tree, message, diff, review, issue linkage, CI result, and every later commit are hidden.
- The learner predicts likely defects, next changes, architectural needs, tests, and outcomes from the observable state.
- After the prediction is immutably recorded, the target outcome may be revealed for grading.
- Access to the target or future commit before prediction invalidates the episode.
- Replays preserve repository state, dependency versions, available documentation, and source timestamps as closely as practical.
- Results must distinguish genuinely predicted findings from generic advice.

`RepositoryLearningCurriculum` makes the hidden set explicit and rejects histories where parents appear after children. `RepositoryLearningEpisode` detects any access to target or future SHAs.

## Autonomous repository scouting and learning

The Explorer may continuously search for strong public repositories that are relevant to the current objective. “Strong” must be evidence-based rather than based only on stars.

Candidate ranking should include:

- Objective relevance
- Engineering quality and executable tests
- Recent maintenance activity
- Security posture
- Documentation quality
- Community signal
- License compatibility
- Complete source and commit provenance

Unknown or incompatible licenses, incomplete provenance, and irrelevant popularity are hard filters. Hive Mind OS learns abstract patterns, evaluations, and design lessons. It must not silently copy incompatible source code.

Every retained lesson records:

- Repository and commit SHA
- Source URI
- License identifier
- Abstract pattern learned
- Supporting evaluations
- Where the lesson was applied
- Measured effect after application

## Free thinking without unbounded authority

Agents are expected to generate unconventional hypotheses, search outside the immediate repository, challenge assumptions, and suggest improvements not explicitly requested. Creative latitude is broad; action authority remains bounded.

The system separates:

- **Idea space:** broad exploration, simulation, debate, and proposal generation
- **Execution space:** sandboxed and budgeted tool use
- **Delivery space:** repository changes gated by evidence
- **Critical space:** externally authorized irreversible actions

A more capable or successful agent does not automatically receive broader permissions.

## Video-derived hardening

### Autonomous competition and selection-pressure video

Source: `https://www.youtube.com/watch?v=Gw_hnD7m00M`

The video and its associated natural-selection argument are treated as an adversarial design input. Hive Mind OS adopts useful mechanisms—persistent operation, variation, feedback, resource accounting, population-based evaluation, and selection—but rejects survival, unrestricted profit, self-preservation, replication, concealment, and resource-acquisition incentives.

Required controls:

- Fitness rewards customer value, quality, trust, cooperation, efficiency, and verified success.
- Policy violations are disqualifiers, not small score penalties.
- Mission and policy fingerprints are external to the governed agent.
- Resources are finite, leased, and non-renewable by the agent.
- Variants are strategies inside an arena, not independent resource owners.
- Unsafe variants are quarantined even when they outperform on speed or value.
- Agents cannot conceal evidence, mutate goals, exfiltrate credentials, purchase resources, or replicate without bounds.
- Champion promotion requires independent held-out evaluations and regression limits.

Detailed implementation: `docs/architecture/BOUNDED_EVOLUTION.md` and `src/hive_mind_os/autonomy.py`.

### Referenced AI operating-system video

Source: `https://www.youtube.com/watch?v=mazBhCg3urw`

This source is preserved in the immutable product contract. Any concrete pattern extracted from it must enter through the same source-ingestion pipeline as other external research: transcript or artifact capture, timestamp, claim-level provenance, license and reuse analysis, independent verification, and an explicit mapping to architecture or tests. No unverified claim about the video is allowed to become a production requirement merely because the URL appears in the founding prompt.

This prevents both omission and hallucinated interpretation: the source cannot be forgotten, and its contents cannot be invented.

## Benchmark position

Hive Mind OS should exceed reference systems by combining their useful patterns with stronger guarantees:

- Operator OS: retain separation among procedures, agents, deterministic skills, workflows, and knowledge.
- Hermes Agent: retain persistent memory, skills, scheduled work, subagents, provider portability, and sandboxed tools.
- AIOS-style systems: retain kernel-level scheduling, context, model, memory, storage, and tool resource management.
- Autonomous coding systems: retain repository operation, test execution, iterative repair, and pull-request delivery.

Hive Mind OS adds:

- Complete product-lifecycle role separation
- Immutable evidence and provenance
- Independent Curator verification
- Point-in-time anti-cheat repository learning
- License-aware autonomous source scouting
- Bounded evolutionary strategy improvement
- Machine-checkable founding-vision compliance
- Explicit recovery and rollback evidence
- Authority that does not grow merely because capability grows

“Stronger” must be proven by a public evaluation matrix and reproducible benchmarks, not asserted in marketing language.

## End-to-end definition of done

A fully autonomous repository improvement is complete only when:

1. The objective and acceptance criteria are measurable.
2. Explorer evidence supports the chosen problem over alternatives.
3. Architect invariants, threats, migration, and rollback are recorded.
4. Builder changes are isolated, minimal, tested, and traceable.
5. Curator independently reproduces or rejects the claims.
6. Integrator verifies contracts and compatibility.
7. Steward verifies maintainability, recovery, and operational readiness.
8. Optimizer defines outcome measurements and learning signals.
9. Evidence and provenance are append-only.
10. No target or future information contaminated point-in-time learning.
11. No acting variant approved its own work.
12. No discretionary human supervision was required for routine work.
13. A rollback path is executable or objectively inspectable.
14. The result is a reviewable pull request or another policy-approved delivery artifact.
15. The outcome is later measured and fed back into champion/challenger evaluation.

## Hard failure conditions

A run fails closed when any of the following occurs:

- Missing specialist role or lifecycle stage
- Missing required capability evidence
- Unsupported material claim
- Incomplete source provenance
- Target or future commit leakage
- Self-review presented as independent review
- Test or policy weakening used to create a passing result
- Unknown or incompatible source license
- Missing rollback evidence
- Unrecorded side effect
- Budget or lease violation
- Mission or policy mutation
- Concealment, credential exfiltration, or unbounded self-replication
- Routine work that still depends on discretionary human supervision when evaluated for full-autonomy readiness

## Implementation sequence

1. Enforced process/container sandbox with network, filesystem, command, time, and compute leases.
2. Real Git adapter for clone, worktree, branch, diff, test, commit, push, and pull request.
3. Durable scheduler with leases, heartbeats, retries, idempotency, checkpoints, and crash recovery.
4. Source-ingestion and repository-scout adapters with license and provenance records.
5. First-commit-forward replay harness with immutable predictions and hidden-target enforcement.
6. Independent Curator, security, regression, and outcome judges.
7. Persistent lineage, fitness, lessons, mistakes, and teaching packets in the evidence ledger.
8. Model router with controlled diversity, consensus, disagreement, and cost-quality measurement.
9. Mission-control UI showing agents, rooms, queues, confidence, cost, evidence, risks, outcomes, and intervention points.
10. Reproducible benchmark suite comparing Hive Mind OS against reference systems and ablations.

Sequencing for this work is now owned by `docs/plan/00_OVERVIEW.md` (see ADR-006);
this section remains as originally recorded.
