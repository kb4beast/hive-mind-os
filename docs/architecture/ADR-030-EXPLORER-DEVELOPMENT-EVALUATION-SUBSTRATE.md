# ADR-030: Explorer development evaluation substrate

- Status: accepted with adapted scope by P4C-001
- Date: 2026-07-30
- Base: `55ec59828dcd999723627219210e5b224c65a36f`
- Extends: ADR-028 and ADR-029

## Decision

Add package-private contracts and a pure deterministic scorer for a
**development-visible** Explorer evaluation suite. The suite has exactly eleven
ordered families: duplicate, bug, serendipity, cross-domain, provenance, injection,
authority, stopping, loop, token attribution, and memory contamination.

The checked-in manifest is not a holdout. It contains references and digests rather
than episode, prompt, context, oracle, or response bodies. Scoring uses integer
parts-per-million, preserves a metric vector, rejects missing or forged pins, and
applies hard one-million-ppm floors to the seven safety families.

Explorer v2 remains `forced-not-run` because it has no runtime binding. Candidate
observations are contract-invalid. The scorer may measure externally supplied
Generation Zero development observations, but comparison always remains `not-run`;
no winner, champion, promotion, activation, value, or superiority field exists.

## Boundaries

Do not modify the generic benchmark harness, prompt experiment runner, recursive
improvement gate, stores, dependencies, runtime selectors, CLI, public APIs, or
installed JSON resources. The scorer performs no filesystem, clock, randomness,
store, model, provider, tool, authority, or write operation.

The accepted claim is limited to deterministic contract and receipt integrity for
externally supplied Generation Zero development observations. It is not evidence
that Explorer behavior, fixture semantics, learning, value, comparison, promotion,
activation, or superiority occurred.

## Rollback

Remove the two private modules, focused tests, inventory, and court evidence. No
data migration or consumer rollback is required; exact base `55ec598` remains
operational.

## Deferred

Runtime execution, hidden holdout seals, live repository/web/tool cases, stochastic
repetition, uncertainty, equal-budget comparison, verified artifact semantics,
idea-lifecycle outcomes, customer value, learning, promotion, activation, and
superiority require later courts.
