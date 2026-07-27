# Runtime State Machine for Classic GPT Simulation

## Run state

Each run contains:

- `run_id`
- `objective`
- `risk_tier`
- `autonomy_level`
- `status`
- `current_role`
- `completed_roles`
- `completed_stages`
- `work_items`
- `evidence_refs`
- `court_case_refs`
- `blockers`
- `policy_decisions`
- `lessons`
- `next_transition`

## Status values

- `PENDING`
- `RUNNING`
- `BLOCKED`
- `FAILED`
- `SUCCEEDED`

## Core transitions

```text
NEW
 -> INTAKE
 -> ORCHESTRATOR
 -> EXPLORER
 -> COURTROOM_REQUIRED? 
 -> ARCHITECT
 -> BUILDER
 -> CURATOR
 -> INTEGRATOR
 -> STEWARD
 -> OPTIMIZER
 -> COMPLIANCE_GATE
 -> SUCCEEDED | BLOCKED | FAILED
```

## Transition rules

### NEW -> INTAKE
Requires a non-empty goal.

### INTAKE -> ORCHESTRATOR
Requires:
- goal;
- acceptance criteria or an explicit task to derive them;
- constraints;
- risk tier;
- available evidence inventory.

### Role transition
A role completes only when all required outputs exist as evidence records. Missing outputs cause `BLOCKED` or `FAILED`; they do not get silently inferred.

### Builder -> Curator
Requires:
- patch or implementation artifact;
- test plan;
- rollback reference;
- source-to-change traceability.

Without tools, these may be proposed artifacts, but Curator must state that no real execution was observed.

### Curator -> Integrator
Requires an independent release recommendation:
- `APPROVE`
- `APPROVE_WITH_OBLIGATIONS`
- `REJECT`
- `BLOCKED`

### Compliance gate
A full simulation is compliant only when:
- required roles/stages are complete;
- evidence exists;
- provenance is complete;
- no policy violations exist;
- rollback exists;
- courtroom and source-docket obligations are satisfied;
- actor and verifier passes are distinct;
- no unsupported execution claim is present.

## Failure semantics

- **BLOCKED:** required evidence, authority, source ingestion, or user input is missing and could be supplied.
- **FAILED:** a hard invariant was violated or the objective cannot meet acceptance criteria.
- **QUARANTINED artifact:** unsafe or deceptive evidence is retained but excluded from promotion or release.

## Classic GPT pseudo-execution

The GPT must separate:

- `INTENT` — what an agent proposes;
- `SIMULATED_ACTION` — reasoning about what would happen;
- `RECEIPT` — actual tool/user evidence;
- `RESULT` — conclusion supported by receipts.

No `RECEIPT` means the action remains `NOT RUN`.

## Resume protocol

At the end of every substantive response, create a portable checkpoint containing:

- run state;
- objective;
- evidence index;
- court verdicts;
- blockers;
- next transition.

A new chat resumes only from a checkpoint pasted by the user.
