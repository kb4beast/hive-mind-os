# ADR-076: External all-aspect tournament plan factory

**Status:** Accepted

**Date:** 2026-09-05

## Context

The portable DAG runtime can validate a pinned plan and describe independent
parallel work, but hand-authored plans made each recursive tournament a special
case. That risks topology drift, omitted specialist roles, accidental reuse of
historical authority, and a return to the rejected design where delivered code
depends on a Hive Mind workspace or DAG tree.

ADR-072 makes agent behavior direct code owned by one class per agent file.
ADR-073 confines DAGs to external orchestration. ADR-075 dispatches fresh
objectives to external plan generation. The active host also needs a reusable,
inert constructor for the standard all-aspect tournament before any separately
authenticated execution can occur.

## Decision

1. `TournamentPlanFactory` is an orchestration-host module, separate from the
   direct-agent package. It produces only portable-plan and sealed-generation
   data; it has no execution, activation, merge, or promotion method.
2. A factory request must bind one repository identity, parent commit and tree,
   target, objective, pinned DAG standard, typed evidence inventory, and a
   local-reversible authority envelope. The envelope must deny credentials,
   deployment, push, merge, payment, production mutation, and protected merge.
3. Every produced tournament uses a fixed court-backed topology: baseline;
   four parallel read-only audits (agents, orchestration, runtime, learning);
   court selection; one exclusive candidate workspace; independent
   verification; and an evidence-only integration recommendation. The topology
   covers every specialist role and lifecycle stage.
4. The plan can be sealed through the existing `PlanGenerator`, whose manifest
   still requires an authenticated external host signature. Sealing or
   validation does not activate the plan or confer authority.
5. Candidate implementation acceptance criteria require direct source and
   configuration without a Hive Mind workspace or DAG-plan dependency. A
   tournament may direct work *on* a repository, but it never becomes a runtime
   dependency *of* that repository.
6. Retained historical planning material remains evidence until separately
   authorized for removal. This decision neither deletes it nor grants a
   protected-target mutation.

## Consequences

An external host has one deterministic way to construct and inspect a fresh
full-coverage tournament, with four audit lanes eligible for parallel execution
and exclusive candidate mutation. The factory reduces manual divergence without
turning generated DAG data into application architecture.

Execution, network effects, code review, pull-request publication, promotion,
and merge remain distinct authority boundaries. The plan is deliberately useful
as a request-bound implementation recipe, not executable authority.

## Verification

`tests/test_tournament_plan_factory.py` proves deterministic construction,
parallel rounds, full role/stage coverage through the compiler, sealing without
activation, evidence and authority rejection, and source separation from
agents. Existing plan-generation, portable-DAG, delivery-boundary, and
direct-agent tests cover the contracts reused by the factory.
