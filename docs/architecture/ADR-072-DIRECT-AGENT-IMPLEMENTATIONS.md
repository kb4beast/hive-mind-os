# ADR-072: Direct Agent Implementations

**Status:** Accepted

**Date:** 2026-09-04

## Context

The eight constitutional roles were represented by shared mappings in
`roles.py` and `brain_kernel/roles.py`, while `runtime.py` constructed generic
`SpecialistAgent` wrappers. This hid a role's contract, capability envelope,
evaluator-isolation requirement, and handoff behavior across several files.

An execution runtime may invoke an agent, but it must not become the source of
the agent's implementation. In particular, agent implementations must not
depend on an execution graph in order to define or run their own bounded role
contract.

## Decision

Each constitutional role has one direct class in `src/hive_mind_os/agents/`:

- `orchestrator.py`
- `explorer.py`
- `architect.py`
- `builder.py`
- `curator.py`
- `integrator.py`
- `steward.py`
- `optimizer.py`

Every class owns its public `RoleContract`, its kernel `RoleCapabilities`, its
next-role recommendation, and its evaluator-isolation requirement. The shared
`Agent` base class only implements common, effect-free backend invocation and
result validation.

`roles.py` remains a compatibility facade for existing callers. It derives
`ROLE_CONTRACTS` and `DEFAULT_LIFECYCLE` from the direct classes rather than
duplicating role behavior. The kernel role protocol resolves a role through the
same direct implementation catalog.

The existing execution and host runtime remain separate compatibility layers.
They may invoke direct agents, but no direct agent module imports or executes
an execution graph.

## Consequences

- A reviewer can inspect one file to understand one role's direct contract and
  constraints.
- The runtime is generic: it constructs and invokes agents without defining
  their role behavior.
- Existing `ROLE_CONTRACTS` imports and lifecycle consumers remain compatible.
- Historical graph-oriented implementation code remains recoverable from Git
  history, rather than being retained as a dependency of the direct agent
  layer.

## Verification

`tests/test_agents.py` proves that all eight roles map to eight direct classes,
that direct agent modules do not import the execution graph, that every class
runs its own contract, and that `HiveKernel` constructs the direct classes.
Existing role, kernel-role, mission, model-backend, and package-facade tests
continue to validate compatibility.
