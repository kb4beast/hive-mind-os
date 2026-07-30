# Phase 4A Explorer shadow contract

## Required invariants

- Generation Zero and every Phase 2/3 contract remain byte-compatible and active
  behavior remains unchanged.
- Skill records are strict, content-addressed, inert, nonauthoritative, and cannot
  grant capabilities.
- Context selection is independent of input order and selects only complete records.
- The nine critical classes are mandatory. Missing, quarantined, future, recursive,
  cross-scope, or over-budget critical context fails closed.
- The receipt binds inventory, policy, ordered selected IDs, omitted IDs and reasons,
  byte counts, purpose, cutoff, and critical coverage.
- Untrusted record content is data. The injected engine receives no execution
  interface.
- Exactly one bounded engine call is permitted per invocation.
- Findings use a closed typed shape, cite only selected evidence, and cannot request
  actions, tools, permissions, code changes, approval, or activation.
- The runner derives the structured collision key and registers through the existing
  encounter-first `OpportunityLedger`.
- Exact duplicates converge; semantic similarity never auto-merges.

## Acceptance tests

Test order-independent replay, whole-record budgets, every critical failure mode,
quarantine and same-run exclusion, prompt-injection text, invented evidence,
unexpected output fields, engine failure, bounded findings, exact duplicate
convergence, wrong authority scope/actor, deterministic skill compilation, drift,
and installed-wheel resources.

## Deferred

Live Git/web/repository tools, model-provider calls, protected-content dereferencing,
semantic retrieval, public brain release, multi-turn autonomy, cross-repository
search, hard hierarchical token/cost leases, persistent circuit breakers,
champion comparison, activation, promotion, and superiority.
