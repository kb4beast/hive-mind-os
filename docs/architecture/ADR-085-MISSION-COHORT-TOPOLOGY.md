# ADR-085: Repository mission cohort topology

## Status

Adapted implementation. This decision specializes ADR-084 for the retained
`MissionLoop` compatibility surface.

## Context and source claims

ADR-084 established cohort execution as the default and strict execution as the
rollback mode. The repository mission loop still exposed only role-by-role calls,
which forced Explorer planning to finish before Architect planning could begin and
made repeated Curator exchanges the easiest orchestration pattern.

Atomic claims carried into this case are:

1. Independent proposal generation should share one sealed mission context and run
   concurrently.
2. Repository effects and append-only state transitions must remain behind the
   existing role, policy, budget, path, and receipt boundaries.
3. A cohort-oriented end-to-end entry point should converge through the Curator once.
4. Existing callers must retain their manual methods and an explicit strict mode.

## Court record and disposition

- **Advocate:** parallel Explorer and Architect proposal generation removes a role
  handoff without weakening the implementation boundary.
- **Cross-Examiner:** concurrently mutating a Git workspace or mission reducer would
  introduce races and could detach an effect from its policy receipt.
- **Expert witness:** fan out only pure proposal callbacks from an immutable kickoff;
  apply their typed outputs through the existing ordered methods.
- **Judge:** **adapt**. Make cohort mode the default, keep effectful materialization
  ordered, add a one-shot terminal Curator convergence, and retain strict mode as a
  full role-by-role rollback.

## Decision

`MissionLoop` now creates one immutable `MissionCohortKickoff` bound to the objective,
base commit, plan, roles, allowed paths, and sealed acceptance identifiers. In cohort
mode, `convene()` invokes Explorer and Architect planners concurrently with the exact
same kickoff object. It then runs `discover()` and `design()` in order so all existing
policy and evidence checks remain authoritative.

`execute()` is the end-to-end cohort ingress: one planning round, bounded Builder
actions, one `converge()` call, and atomic publication. A remand from that terminal
convergence is retained as evidence but does not start a Curator tit-for-tat loop.
Manual `discover()`, `design()`, `build()`, `curate()`, and `complete()` calls remain
available for compatibility. Selecting `execution_mode="strict"` restores sequential
Explorer-then-Architect proposal and execution order.

The scheduler grants no new authority. Planner callbacks cannot directly enter the
mission reducer, and every repository operation still passes through the existing
action allowlists, `PolicyEngine`, budget accounting, workspace confinement, sealed
test protection, and append-only receipts. Push, pull request, merge, deployment,
secret, spending, and credential capabilities remain absent.

## Migration, rollback, and evidence

New callers use `execute()` or `convene()` and receive cohort behavior by default.
Existing manual callers require no changes. Rollback is the constructor option
`execution_mode="strict"`; it changes scheduling only and preserves evidence and
effect boundaries.

Focused acceptance evidence is in `tests/test_mission_loop_cohort.py`. It proves a
shared kickoff and concurrent planning workers, strict role ordering, end-to-end
publication with exactly one convergence event, one-shot remand behavior, retained
remote-effect denial, and fail-closed mode parsing. The pre-existing mission-loop and
provider suites continue to prove path, policy, budget, candidate, and Curator
boundaries.
