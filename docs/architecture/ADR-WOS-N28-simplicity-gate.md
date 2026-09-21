# ADR-WOS-N28: Smallest sufficient plan and downward replanning

## Status

Adopted on 2026-09-21.

## Context

An operator reported that a small application request expanded into a long qualification
effort without producing the requested usable result. Existing graph validation bounded
plans, but it did not prefer the smallest sufficient candidate or provide a fail-closed
operation for an explicit scope reduction.

## Decision

The planner exposes a deterministic complexity vector covering work items, dependency
edges, depth, attempts, and all consumptive schedule budgets. `select_simplest` accepts
only plans for the same exact charter and chooses the lowest vector with the plan digest
as a stable tie-breaker. `simplify` requires every bound to stay level or fall and at
least one bound to fall.

Planner prompt version 2 starts from the smallest plan that covers acceptance criteria,
excludes optional work by default, combines lifecycle duties where identity separation
still holds, and immediately replans downward after an operator narrows scope.

## Consequences

Safety, authority, acceptance coverage, and independent judgment remain mandatory. The
change prevents a claimed simplification from hiding added work or resource budgets. It
does not guess that two different charters are equivalent.

## Verification and rollback

Unit tests cover deterministic selection, cross-charter rejection, valid downward
replanning, increased-budget rejection, prompt versioning, and required prompt language.
Rollback is one revert; persisted plan schema version 1 is unchanged.
