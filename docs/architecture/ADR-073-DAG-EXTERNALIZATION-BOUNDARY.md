# ADR-073: Keep DAG orchestration outside delivered application code

**Status:** Accepted
**Date:** 2026-09-04

## Context

HiveMind uses executable DAGs to schedule implementation work, run independent
or parallel lanes, and retain orchestration evidence.  A target repository must
not need that plan, HiveMind's runtime, or HiveMind workspace state in order to
run its delivered code.

The prior architecture permitted implementation concepts to be represented in
shared graph registries.  Direct agent classes now own their behavior, but a
delivery boundary is also required so a future implementation cannot introduce
an application dependency on the orchestration layer.

## Decision

1. DAG construction, execution, tournament use, and receipts remain HiveMind
   orchestration concerns.
2. A repository delivery may not introduce HiveMind imports, HiveMind workspace
   paths, or DAG-plan-directory paths into target source/configuration files.
3. A delivery may not contain a DAG plan artifact under `plans/dags`.
4. The Git delivery exporter and immutable candidate verifier enforce the same
   fail-closed check before producing a delivery or executing acceptance tests.
5. The guard is deliberately specific to HiveMind orchestration identifiers.
   It does not prohibit a target's independent use of graph algorithms.
6. Direct agent modules may not import or reference DAGs.  Their orchestrator
   output is an `objective_plan`, not an `objective_dag`.

## Consequences

Target code is runnable from a clean checkout without HiveMind plan files or
workspace state.  A delivery that embeds an orchestration dependency is
rejected and must be redesigned around normal source inputs and neutral evidence
artifacts.  HiveMind's own executor continues to use DAGs externally.
