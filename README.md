# Hive Mind OS

Hive Mind OS is an evidence-driven agentic operating system for autonomous product and software delivery. It converts the AI-native successor to the traditional SDLC into eight independent specialist agents aligned around customer value:

| Agent | Responsibility |
|---|---|
| Orchestrator | Sets direction, decomposes outcomes, manages risk, budgets, recovery, and dependencies |
| Explorer | Finds evidence-backed problems and ideas through repository, history, user-signal, and web research |
| Architect | Designs scalable, secure, evolvable solutions with explicit threats and rollback |
| Builder | Implements complete changes with executable tests, branches, commits, and pull requests |
| Curator | Independently verifies quality, trust, security, compliance, provenance, and claims |
| Integrator | Connects systems, data, tools, repositories, and workflows through stable contracts |
| Steward | Maintains reliability, dependencies, code health, observability, and recoverability |
| Optimizer | Measures outcomes, teaches validated lessons, and promotes proven improvements |

The target is autonomous discovery through verified delivery and continuous learning—not a collection of chat personas. Routine reversible work should require no discretionary human supervision. Every agent works through typed contracts, bounded authority, isolated execution, immutable evidence, independent evaluation, and resumable workflows.

## Hardened founding vision

The original product prompt, supplied “New Team Model” images, reference repositories, and both linked videos are now preserved as a normative, machine-checkable product constitution.

- Human-readable contract: [Hardened Founding Vision Contract](docs/architecture/HARDENED_VISION_CONTRACT.md)
- Machine-readable contract and compliance gate: `src/hive_mind_os/vision.py`
- Competitive-autonomy threat model: [Bounded Evolutionary Autonomy](docs/architecture/BOUNDED_EVOLUTION.md)
- License-aware repository scouting and anti-cheat historical curriculum: `src/hive_mind_os/repository_learning.py`

A run fails full-autonomy compliance when it omits a specialist or lifecycle stage, lacks required capability evidence, uses future repository knowledge, permits self-approval, lacks provenance or rollback evidence, violates policy, or depends on discretionary human supervision for routine work.

## What is implemented

The foundation includes:

- Typed objectives, work items, evidence, results, risks, and autonomy levels.
- Contracts for all eight specialist agents.
- A runnable lifecycle kernel and provider-neutral backend interface.
- An append-only SQLite evidence and learning ledger.
- A fail-closed policy engine for side effects.
- Point-in-time commit replay that prevents future leakage.
- A first-commit-forward curriculum with explicit hidden target/future sets and access validation.
- License- and provenance-gated ranking of strong public repository learning sources.
- Abstract pattern lessons tied to repository, commit, license, source URI, and evaluations.
- A fingerprinted founding-vision contract covering every role, lifecycle stage, and autonomous capability.
- A compliance gate for role completeness, lifecycle completeness, source provenance, independent verification, rollback, anti-cheat history, and unsupervised routine work.
- Champion/challenger promotion gates for self-improvement.
- Immutable mission charters and fingerprint-based mutation detection.
- Fixed episode, tool-call, and compute budgets with per-episode allowances.
- A bounded evolution arena for competing agent strategies.
- Automatic quarantine for unsafe, deceptive, or unsupported variants.
- Evidence-supported teaching packets for cross-agent learning.
- A persistent autonomous mission loop that stops on completion, policy failure, or budget exhaustion.
- Tests and GitHub Actions CI.

## Bounded evolutionary autonomy

Hive Mind OS adopts the useful parts of competitive autonomous-agent systems—persistent operation, variation, feedback, selection, resource awareness, and learning—without giving agents survival, concealment, replication, or unrestricted profit incentives.

Fitness combines customer value, quality, trust, cooperation, efficiency, and successful delivery. Policy violations, charter mutation, concealed activity, unbounded self-replication, future-data leakage, self-approval, and missing evidence are hard disqualifiers rather than score penalties. Higher capability never grants higher authority.

## Run the bootstrap kernel

```bash
python -m pip install -e .
hive-mind "Improve repository reliability" --repository owner/repo \
  --criterion "All tests pass" \
  --criterion "The change is reversible"
```

The included deterministic backend exercises the role lifecycle offline. Real model, Git, sandbox, web-research, source-ingestion, durable scheduler, and enforced resource-lease adapters are the next implementation slices.

## Core guarantees

1. Evidence before authority.
2. No target or future knowledge in point-in-time learning.
3. Independent verification rather than self-approval.
4. Append-only provenance for sources, decisions, actions, lessons, and outcomes.
5. Self-improvement through challengers and measured promotion—not live prompt mutation.
6. Deny-by-default side effects and explicit autonomy levels.
7. Mission, policy, and founding-product boundaries cannot be rewritten by the governed agent.
8. Resource budgets are finite, explicit, and external to agent incentives.
9. Unsafe variants are quarantined even when they produce high-value results.
10. External learning is license-aware, provenance-bearing, and pattern-oriented rather than silent code copying.
11. Routine work is designed to recover and resume without repeated human prompting.
12. Models, tools, sandboxes, storage, schedulers, Git providers, and research providers remain replaceable.

See the [foundation plan](docs/architecture/FOUNDATION_PLAN.md), [hardened vision contract](docs/architecture/HARDENED_VISION_CONTRACT.md), and [agent instructions](AGENTS.md).
