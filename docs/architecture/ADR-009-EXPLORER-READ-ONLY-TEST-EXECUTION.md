# ADR-009: Read-Only Test Execution for Repository Exploration

- **Status:** Proposed for independent P05 court review
- **Date:** 2026-07-27
- **Case:** `CASE-P05-EXPLORER-READ-ONLY-TEST-EXECUTION`
- **Originating work order:** `docs/plan/P05_VERTICAL_SLICE.md`
- **Prior decisions:** ADR-006 and ADR-007
- **Capability maturity:** structurally prototyped

## Context

P05 requires the Explorer to reproduce a repository failure through the P03 sandbox while
remaining unable to modify the repository. The role contract already grants
`run_analysis`, and the P05 work order explicitly grants a read-only workspace plus
`run_tests`. The existing policy special case nevertheless denied every Explorer action
except repository reads and web searches, including `Action.RUN_COMMANDS`. That made the
required evidence path unreachable even at repository autonomy.

This is a policy-semantics change, so AGENTS.md requires an architecture decision and
regression tests. It does not change the autonomy floor for commands.

## Court record

The P05 Builder advocates allowing the Explorer to request `RUN_COMMANDS` only after the
ordinary autonomy, risk, typed-intent, executable allowlist, path-confinement, environment,
time, output, and fixed-allowance checks have passed. Cross-examination must attempt writes,
branch creation, policy mutation, direct Git authority bypass, and execution below the
Sandbox autonomy level. The Curator, Judge, and Orchestrator must review the complete P05
candidate at one exact commit before this decision is adopted.

No external-source content is introduced. The evidence is the existing role contract,
P05 work order, ADR-007 enforcement boundary, policy regressions, mission tests, and final
independent review. Source-ingestion and licensing obligations remain assigned to P12.

## Decision

Permit `Role.EXPLORER` to request `Action.RUN_COMMANDS` in addition to
`READ_REPOSITORY` and `SEARCH_WEB`.

All other controls remain in force:

1. `RUN_COMMANDS` still requires at least `AutonomyLevel.SANDBOX`.
2. The sandbox validates the typed intent and action digest before spawn.
3. Only explicitly allowlisted executables can run.
4. The Explorer capability exposes test execution but no workspace-write, branch, commit,
   delivery, or Git-metadata method.
5. `PolicyEngine` continues to deny every Explorer action outside the three-item set.
6. P03 process-tier limitations remain unchanged; this is not hostile-code isolation.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Explorer mutates the repository | No write/branch capability; policy retains explicit denials | An allowed executable is not a hard filesystem boundary until B-OPS-06 |
| Command authority at too-low autonomy | Existing `ACTION_LEVEL` keeps `RUN_COMMANDS` at Sandbox | None inside the process-tier policy model |
| Explorer invokes Git directly | P04 `GitWorkspace.run_tests` denies the Git executable before spawn | Other allowed executables remain trusted process-tier programs |
| Receipt presented as independent approval | Runner identity differs from actor; Curator still re-executes later | Structural identity is not authenticated until P08 |
| Policy change broadens delivery authority | Branch, PR, merge, deploy, secrets, and policy actions remain denied | None |

## Acceptance evidence

- A policy regression permits Explorer `RUN_COMMANDS` at Sandbox or Repository autonomy.
- A policy regression denies the same action at Advise autonomy.
- Existing Explorer write and branch denials remain green.
- P05 Explorer reproduces the failing fixture test through a receipted sandbox call.
- The complete P05 suite, full suite, Ruff, Pyright, audit, and independent court review
  pass at one exact candidate.

## Rollback

Revert the one policy-set addition and P05 mission code together before any later phase
depends on Explorer test evidence. Preserve this ADR, receipts, audit artifacts, rejected
candidates, and dissent.

## Deferred limits and ownership

- P08 owns structural Curator independence and authenticated identity.
- B-OPS-06 owns hard filesystem/network isolation for hostile allowed programs.
- P06 owns durable mission state and resume.
- P07 owns external GitHub delivery and credentials.
- P12 owns unresolved source and licensing obligations.

This decision does not establish production readiness, complete mediation, or superiority.
