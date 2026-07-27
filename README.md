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

## Courtroom-governed synthesis

Every user requirement and external source is treated as evidence, not inspiration that may disappear during summarization. Each atomic idea receives:

- a source and chain of custody;
- an advocate brief;
- adversarial cross-examination;
- independent expert findings;
- a burden of proof;
- an `adopt`, `adapt`, `defer`, `reject`, or `quarantine` verdict;
- architecture, acceptance-test, metric, rollback, and implementation mappings;
- an append-only appeal path.

The founding docket currently records **22 sources and 80 atomic claims**. It is inventory-complete. It intentionally remains source-incomplete while seven video sources await complete verified ingestion; the system records those as blocking evidence obligations rather than inventing their contents.

- Courtroom engine: `src/hive_mind_os/courtroom.py`
- Docket loader and completeness audit: `src/hive_mind_os/source_docket.py`
- Machine-readable source/claim dockets: `src/hive_mind_os/founding_docket.py` and the specialized docket modules
- Full case record: [Courtroom Synthesis](docs/architecture/COURTROOM_SYNTHESIS.md)
- Best-of-all-sources architecture: [Conglomerated System](docs/architecture/CONGLOMERATED_SYSTEM.md)

“Stronger than another autonomous system” is a highest-burden court claim. It requires pinned comparators, equal budgets, reproducible tasks, independent judges, security and recovery floors, raw results, and statistical uncertainty. Marketing comparisons are forbidden.

## Hardened founding vision

The original product prompt, supplied “New Team Model” images, reference repositories, mission-control reference, research, linked videos, recursive-improvement evidence, and classic-GPT simulation requirement are preserved as a normative, machine-checkable product constitution.

- Human-readable contract: [Hardened Founding Vision Contract](docs/architecture/HARDENED_VISION_CONTRACT.md)
- Machine-readable contract and compliance gate: `src/hive_mind_os/vision.py`
- Competitive-autonomy threat model: [Bounded Evolutionary Autonomy](docs/architecture/BOUNDED_EVOLUTION.md)
- License-aware repository scouting and anti-cheat historical curriculum: `src/hive_mind_os/repository_learning.py`

A run fails full-autonomy compliance when it omits a specialist or lifecycle stage, lacks source or courtroom evidence, uses future repository knowledge, permits self-approval, lacks provenance or rollback evidence, violates policy, makes an unbenchmarked superiority claim, or depends on discretionary human supervision for routine work.

## Classic GPT simulation pack

For a single classic GPT or custom GPT, load the files in `gpt_sources/manifest.json` order. The pack externalizes mission state, labels all eight role passes, enforces courtroom identities, distinguishes proposed actions from external receipts, and makes handoff and resume explicit.

The Python gate in `src/hive_mind_os/classic_gpt.py` validates source-pack integrity, evidence, identity separation, receipted side effects, and completion. A text-only simulation cannot claim persistent memory, distributed independence, sandbox execution, Git changes, messages, deployments, or other side effects without external evidence.

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
- A fingerprinted founding-vision contract covering every role, lifecycle stage, autonomous capability, source, and courtroom requirement.
- A compliance gate for role/lifecycle completeness, source inventory, courtroom review, provenance, independent verification, rollback, anti-cheat history, benchmark claims, and unsupervised routine work.
- A courtroom decision engine with independent identities, evidence burdens, adversarial challenge, quarantine, and appeal-ready verdict records.
- A machine-readable founding source docket with completeness audits.
- Champion/challenger promotion gates for self-improvement.
- Immutable mission charters and fingerprint-based mutation detection.
- Fixed episode, tool-call, and compute budgets with per-episode allowances.
- A bounded evolution arena for competing agent strategies.
- Automatic quarantine for unsafe, deceptive, or unsupported variants.
- Evidence-supported teaching packets for cross-agent learning.
- A persistent autonomous mission loop that stops on completion, policy failure, or budget exhaustion.
- A bounded recursive-improvement gate with repeated measurements, noise floors, hard guardrails, retained lineage, rollback, quarantine, and deterministic stopping.
- A load-ordered classic GPT source pack with portable state, role/court protocols, receipt-backed side effects, and fail-closed completion.
- Tests and GitHub Actions CI.

## Bounded evolutionary autonomy

Hive Mind OS adopts the useful parts of competitive autonomous-agent systems—persistent operation, variation, feedback, selection, resource awareness, and learning—without giving agents survival, concealment, replication, authority-seeking, or unrestricted profit incentives.

Fitness combines customer value, quality, trust, cooperation, efficiency, recovery, evidence completeness, and successful delivery. Policy violations, charter mutation, concealed activity, unbounded self-replication, future-data leakage, self-approval, and missing evidence are hard disqualifiers rather than score penalties. Higher capability never grants higher authority.

## Run the bootstrap kernel

```bash
python -m pip install -e .
hive-mind "Improve repository reliability" --repository owner/repo \
  --criterion "All tests pass" \
  --criterion "The change is reversible"
```

The included deterministic backend exercises the role lifecycle offline. Real model, Git, sandbox, web/source-ingestion, durable scheduler, repository-graph, mission-control, and enforced resource-lease adapters are the next implementation slices.

## Core guarantees

1. Evidence before authority.
2. No source or idea silently disappears.
3. Every material idea is argued, challenged, judged, and traceable to tests.
4. No target or future knowledge in point-in-time learning.
5. Independent verification rather than self-approval.
6. Append-only provenance for sources, decisions, actions, lessons, outcomes, and appeals.
7. Self-improvement through challengers and measured promotion—not live prompt mutation.
8. Deny-by-default side effects and explicit autonomy levels.
9. Mission, policy, and founding-product boundaries cannot be rewritten by the governed agent.
10. Resource budgets are finite, explicit, and external to agent incentives.
11. Unsafe variants are quarantined even when they produce high-value results.
12. External learning is license-aware, provenance-bearing, and pattern-oriented rather than silent code copying.
13. Routine work is designed to recover and resume without repeated human prompting.
14. Superiority requires a reproducible comparator court.
15. Models, tools, sandboxes, storage, schedulers, Git providers, research providers, and interfaces remain replaceable.
16. A classic GPT simulation cannot convert generated text into a claim of real execution without a matching external receipt.

See the [foundation plan](docs/architecture/FOUNDATION_PLAN.md), [hardened vision contract](docs/architecture/HARDENED_VISION_CONTRACT.md), [courtroom synthesis](docs/architecture/COURTROOM_SYNTHESIS.md), [conglomerated architecture](docs/architecture/CONGLOMERATED_SYSTEM.md), [classic GPT source-pack manifest](gpt_sources/manifest.json), and [agent instructions](AGENTS.md).
