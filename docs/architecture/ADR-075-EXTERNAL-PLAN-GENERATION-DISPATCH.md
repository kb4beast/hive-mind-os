# ADR-075: Dispatch new objectives to external plan generation

**Status:** Accepted

**Date:** 2026-09-05

## Context

`hive-mind autopilot run` correctly refused to reuse an installed controller's
historical plan for a new objective.  Its prior response had no durable task,
however, leaving the active host with a typed blocker rather than an actionable
way to create the required successor plan.

The portable DAG product already provides plan sealing, validation, deterministic
parallel-round inspection, and programmatic execution behind authenticated host
adapters.  Direct agents and target application code must remain independent of
that orchestration implementation.

## Decision

1. Every explicit `autopilot run` dispatches one fresh, deterministic external
   plan-generation task bound to the repository, request, and objective digests.
2. Presence of a target-resident controller is observed only to record the
   decision. Its plan is never inspected, invoked, or reused for the new
   objective.
3. The task requires an external HiveMind workspace to generate the plan, then
   use the public DAG build, validation, and rounds interfaces before reporting
   success.
4. The generated plan, execution receipts, and activation-preparation material
   remain outside the target delivery. A delivery must not introduce HiveMind
   imports, workspace paths, or DAG-plan references.
5. An authenticated external one-run activation remains mandatory before any
   effectful execution. This dispatch cannot mint a signature, authority,
   credential, or merge permission.

## Consequences

New objectives no longer stall at an empty plan-generation response, while old
controllers remain unable to steer them. The active host receives one
idempotent task that it can schedule and monitor. Target code still runs without
HiveMind or DAG artifacts, and the existing external runtime remains the only
place that can schedule parallel DAG work after activation.

## Verification

`tests/test_autopilot_workflow.py` proves that an installed legacy controller
produces one subject-bound external task, contains no legacy-plan content, and
requires external activation. The existing DAG product tests continue to cover
generation lineage, validation, parallel rounds, host execution, and activation
rejection paths.
