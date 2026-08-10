# Role Wiring Audit — Current `main`

Baseline commit: `7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23`  
Baseline tree: `ac76686aa004cf8188f0281b1ec9ac1f5c666929`

## Verdict

The user’s concern is correct with one qualification: all eight role names and contracts exist,
and the generic `HiveKernel` can call a model for all eight serial passes. However, **no single
current product runtime gives all eight roles meaningful provider-backed cognition, bounded
tools/effects, role consultation, durable recovery, independent acceptance, and learning**.

The repository currently has overlapping execution paths:

- `runtime.py`: generic serial eight-role pass; deterministic default can manufacture contract
  outputs without repository work.
- `mission.py`: real local repository execution, but only Explorer, Builder, and Curator.
- `mission_loop.py`: richer local state/actions, but still a partial lifecycle and separate truth.
- `autonomous_os.py`: durable host-driven work and feedback/PIT learning, but bypasses the
  eight-role runtime and owns another SQLite brain.
- `brain_kernel/*`: strongest event/authority/verification foundation and all eight local role
  contracts, but current role handlers are deliberately provider-free, effect-free fixtures.
- `workers.py` and `scheduler.py`: durable queueing exists, but workers execute the scripted
  legacy repository mission rather than a canonical eight-role mission.

## Matrix

| Role | Current runtime truth | Current effect truth | Role-first consultation | Target node |
|---|---|---|---|---|
| Orchestrator | generic serial model/deterministic pass; kernel deterministic fixture | no canonical repository effects | not implemented | ORCH-300 |
| Explorer | generic model pass; real RepositoryMission read/test role; kernel fixture | real local repository reads/tests in legacy path | not implemented | EXPLORER-310 |
| Architect | generic model pass; partial MissionLoop design input; kernel fixture | no canonical tool/effect path | not implemented | ARCHITECT-320 |
| Builder | generic model pass; real RepositoryMission branch/write/test/commit; kernel fixture | real local repository effects in legacy path | not implemented | BUILDER-330 |
| Curator | generic model pass; real independent legacy verification; kernel fixture | exact-candidate verification exists but is not wired through all roles | not implemented | CURATOR-340 |
| Integrator | generic model pass; kernel fixture only | no canonical integration effect path | not implemented | INTEGRATOR-350 |
| Steward | generic model pass; high-risk MissionLoop label; kernel fixture | no canonical operations controller | not implemented | STEWARD-360 |
| Optimizer | generic model pass; experiment components exist; kernel fixture | no canonical challenger-generation/promotion runtime | not implemented | OPTIMIZER-370 |

## What counts as “wired”

A role is operational only when one real canonical mission proves all of the following:

1. the planner can select it from mission evidence;
2. it receives a typed, bounded, provenance-aware context;
3. a model or deterministic implementation performs its semantic responsibility;
4. it can request only role-authorized tools/effects;
5. every proposal and observation is receipted;
6. its result is validated against a role-specific contract;
7. downstream roles can consume the result through typed references;
8. it can consult applicable roles and preserve dissent;
9. it cannot approve itself or expand authority;
10. its contribution is included in exact-candidate acceptance and later outcome learning.

A registered prompt, fixture handler, enum member, planned role, or synthetic contract output is
not sufficient.
