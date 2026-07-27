# Hive Mind OS

Hive Mind OS is an evidence-driven agentic operating system for autonomous product and software delivery. It converts the modern product lifecycle into eight independent specialist agents aligned around customer value:

| Agent | Responsibility |
|---|---|
| Orchestrator | Sets direction, decomposes outcomes, manages risk and dependencies |
| Explorer | Finds the right evidence-backed problems |
| Architect | Designs scalable, secure, evolvable solutions |
| Builder | Implements complete changes with executable tests |
| Curator | Independently verifies quality, trust, security, and compliance |
| Integrator | Connects systems, data, tools, repositories, and workflows |
| Steward | Maintains reliability, dependencies, code health, and operations |
| Optimizer | Measures outcomes and promotes proven improvements |

The target is autonomous discovery through verified delivery and continuous learning—not a collection of chat personas. Every agent works through typed contracts, bounded authority, isolated execution, immutable evidence, independent evaluation, and resumable workflows.

## What is implemented

The foundation includes:

- Typed objectives, work items, evidence, results, risks, and autonomy levels.
- Contracts for all eight specialist agents.
- A runnable lifecycle kernel and provider-neutral backend interface.
- An append-only SQLite evidence and learning ledger.
- A fail-closed policy engine for side effects.
- Point-in-time commit replay that prevents future leakage.
- A champion/challenger promotion gate for self-improvement.
- Tests and GitHub Actions CI.

## Run the bootstrap kernel

```bash
python -m pip install -e .
hive-mind "Improve repository reliability" --repository owner/repo \
  --criterion "All tests pass" \
  --criterion "The change is reversible"
```

The included deterministic backend exercises the full lifecycle offline. Real model, Git, sandbox, web, and durable scheduler adapters are the next implementation slices.

## Core guarantees

1. Evidence before authority.
2. No future knowledge in point-in-time learning.
3. Independent verification rather than self-approval.
4. Append-only provenance for decisions, actions, lessons, and outcomes.
5. Self-improvement through challengers and measured promotion—not live prompt mutation.
6. Deny-by-default side effects and explicit autonomy levels.
7. Replaceable models, tools, sandboxes, storage, and providers.

See [the foundation plan](docs/architecture/FOUNDATION_PLAN.md) and [agent instructions](AGENTS.md).
