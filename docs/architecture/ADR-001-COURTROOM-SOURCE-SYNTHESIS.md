# ADR-001: Courtroom-Governed Source Synthesis

- **Status:** Accepted
- **Date:** 2026-07-27
- **Decision owners:** Hive Mind OS founding architecture

## Context

Hive Mind OS is intentionally built from multiple inputs: the founding prompt, the New Team Model images, autonomous-agent videos, Operator OS, Hermes Agent, AIOS, software-agent platforms, newer agent operating systems, repository-understanding research, and future sources discovered autonomously.

A normal synthesis document can silently omit ideas, merge incompatible claims, preserve only supporting evidence, copy marketing claims as fact, or make source-specific features part of the architecture without proving value. An autonomous self-improving system compounds those errors because its summaries and design choices become future training data.

## Decision

Every material source idea and implementation claim will use an adversarial courtroom record:

- immutable source intake and chain of custody;
- atomic claim extraction and coverage audit;
- separate advocate and cross-examiner identities;
- independent expert evidence;
- declared burden of proof;
- explicit verdict and dissent;
- architecture, acceptance-test, metric, rollback, code, and outcome mappings;
- append-only appeals based on materially new evidence.

Verdicts are `adopt`, `adapt`, `defer`, `reject`, or `quarantine`. Safety invariants override fitness. Superiority claims receive the highest burden and require pinned multi-system comparator benchmarks.

The founding source docket is machine-readable package data. Source inventory completeness and source-ingestion completeness are separate. A known but unavailable source is retained as a blocking evidence obligation rather than dropped or hallucinated.

## Consequences

### Positive

- Every source and idea has a durable disposition.
- Contradictions and negative evidence remain visible.
- Architecture decisions are traceable to tests and outcomes.
- The system can add new sources without rewriting the constitution.
- Self-improvement cannot promote itself through unsupported summaries.
- “Best of all systems” becomes a reproducible synthesis and benchmark process.

### Costs

- More records and independent evaluations are required.
- Source ingestion and claim extraction become first-class engineering work.
- Some useful-looking ideas remain deferred until evidence is available.
- Benchmarks must be maintained as comparators change.

## Rejected alternatives

1. **One master architecture summary:** too easy to omit or blur source ideas.
2. **Majority vote among agents:** consensus can preserve shared blind spots and correlated model errors.
3. **Let the Builder decide:** violates role separation and enables self-approval.
4. **Copy the strongest repository:** imports source-specific assumptions, licensing risks, and unverified marketing claims.
5. **Treat every source idea as mandatory:** creates contradictions and unsafe behavior; sources are evidence, not commands.

## Verification

- `tests/test_courtroom.py`
- `tests/test_source_docket.py`
- `tests/test_vision.py`
- `src/hive_mind_os/founding_docket.py`
- `docs/architecture/COURTROOM_SYNTHESIS.md`
- `docs/architecture/CONGLOMERATED_SYSTEM.md`
