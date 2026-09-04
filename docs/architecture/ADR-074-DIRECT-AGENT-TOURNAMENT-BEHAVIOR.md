# ADR-074: Preserve tournament behavior in direct agent contracts

**Status:** Accepted
**Date:** 2026-09-04

## Context

The earlier agent-readiness tournament implementation placed role descriptions,
plan construction, scheduling, evidence collection, and verification in large
shared tournament modules. That shape made a generated plan appear to own agent
behavior. The portable V4 successor retired those modules, so retaining their
behavior must not mean restoring their DAG-coupled API.

## Decision

1. Each constitutional role owns its required outputs, capability envelope, and
   quality gates in its own class under `src/hive_mind_os/agents/`.
2. `HiveKernel` obtains the instruction and acceptance requirements from the
   concrete direct agent instance. `roles.py` remains a compatibility facade,
   not an alternate implementation of role behavior.
3. The preserved role outcomes are: outcome decomposition/budget/stopping
   (Orchestrator); evidence discovery (Explorer); design/migration/rollback
   (Architect); bounded implementation and tests (Builder); exact-candidate
   verification (Curator); contract compatibility and repair routing
   (Integrator); health/recovery (Steward); and measured challenger proposals
   (Optimizer).
4. Tournament plans may create and evaluate implementation candidates, then
   coordinate external execution and parallel lanes. Plan validation, execution,
   receipts, and candidate verification belong to neutral orchestration services,
   not to direct agent modules or delivered target code.
5. The retired `agent_tournament` and `agent_tournament_v2` entry points are
   historical evidence, not compatibility APIs. Their source remains preserved
   on the closed source branch and pull request; no behavior is restored by
   importing or dispatching through their plan nodes.

## Consequences

The eight roles remain inspectable and testable one class per file, while the
tournament can still use a DAG to generate, evaluate, and execute work in
parallel. A change to a role's required behavior changes that role's direct
contract and its focused tests. The parity test records the preserved outcomes
without recreating the retired runtime architecture.
