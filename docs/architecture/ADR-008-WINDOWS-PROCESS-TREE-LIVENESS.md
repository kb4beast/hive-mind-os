# ADR-008: Bind Windows Process-Tree Liveness to Process Creation Time

- **Status:** Implemented locally; independent P03 appeal review remains pending
- **Date:** 2026-07-27
- **Case:** `CASE-P03-WINDOWS-PROCESS-TREE-LIVENESS-APPEAL`
- **Originating decision:** `docs/architecture/ADR-007-PROCESS-SANDBOX-GATEWAY.md`
- **Reproduced by:** P04 Git adapter materialization
- **Capability maturity:** process-tier correction

## Context

ADR-007 uses a Windows Toolhelp process snapshot to keep an early-exiting command's
descendants inside the command deadline. Toolhelp exposes process IDs and parent process
IDs, but process IDs are reusable. P04 reproduced a completed `git checkout --detach`
being held until its 60-second sandbox deadline because an unrelated older process had a
recorded parent PID equal to the Git process PID.

That false-positive timeout is a blocking correctness defect in the P03 gateway. It does
not justify adding broader verifier hardening or claiming hard sandbox isolation.

## Court record

The Steward/Builder advocate binds each Windows descendant decision to the root process's
creation timestamp, preserving the early-parent-exit behavior while excluding processes
that predate the command. Cross-examination must test PID-reuse ambiguity, inaccessible
process metadata, termination races, handle lifetime, and portability. A separate Curator,
Judge, and Orchestrator must review the complete exact-SHA appeal candidate.

The repository's existing Windows integration run is the expert evidence: the P04
materialization command first completed normally and later reproduced the false timeout
under the same candidate. No external-source content or superiority claim is introduced.

## Decision

Record the root process creation time immediately after `Popen` returns, using the process
handle retained by `Popen`. For each structurally possible Toolhelp descendant:

1. query its creation time with a least-privilege
   `PROCESS_QUERY_LIMITED_INFORMATION` handle;
2. exclude it when it was created before the root process;
3. include it when it was created at or after the root process; and
4. include it fail-closed when either creation timestamp is unavailable.

Use the filtered set for both post-parent liveness and timeout termination. Preserve the
existing parent-PID traversal so genuine descendants of an early-exiting parent remain
bounded.

The P10.G local repair creates a Windows Job Object with `KILL_ON_JOB_CLOSE` before
spawning the root. It starts that root suspended, assigns it to the job, then resumes it.
Creation, assignment, or resume failure denies the command before the root can execute.
After the parent exits, an active-process query failure remains liveness-unknown until the
deadline closes the job; it does not fall back to a racy Toolhelp success decision.

## Threats and residual limits

| Threat | Control | Residual |
|---|---|---|
| Stale parent PID | Root/descendant creation-time comparison | Snapshot and query are not atomic |
| Metadata access denied | Treat unknown-time candidates as descendants | May retain a false positive rather than fail open |
| Early parent exit | Suspended root is assigned before execution; job close tears down descendants | Command is denied when the Job Object is unavailable |
| PID reuse during traversal | Creation-time lower bound rejects pre-root processes | A later unrelated process plus matching live ancestry remains a process-tier race |
| Job creation/assignment/resume unavailable | Deny before root execution | Availability reduces capability but not liveness soundness |
| Job active-process query unavailable | Treat tree liveness as unknown until timeout closes the job | May time out conservatively |

This does not add Windows CPU or memory enforcement, network isolation, filesystem ACLs,
containers, or externally authenticated evidence. `B-OPS-06` remains open.

The Job Object is only descendant-liveness and teardown plumbing. It does not impose the
filesystem, network, executable-identity, secret, or resource controls required for hard
isolation; `B-OPS-06` remains open.

## Acceptance evidence

- A deterministic table regression excludes a stale direct record and its descendants,
  while retaining a genuine child and grandchild.
- Repeated short-lived Windows sandbox commands complete without false timeout.
- Existing early-parent-exit and timeout-tree regressions still pass on Windows.
- The original P04 materialization regression completes against the repaired sandbox.
- Full tests, Ruff, Pyright, audit, exact-head GitHub checks, and independent court review
  are required before delivery.

## P10.G local implementation evidence

On 2026-08-08, the Windows early-parent-exit/background-child regression passed after the
Job Object repair, and `python -m unittest tests.test_sandbox -v` passed 23 tests with one
expected POSIX-only skip. The required full local gate was also run with `TEMP` and `TMP`
set to `C:\t`: 524 tests ran in 926.435 seconds with five expected skips and one failure.
The former sandbox failure passed; the remaining failure was
`test_long_windows_path_receipt_validates`, whose generated root length was 259 rather than
the test's required greater-than-260 length under the short temporary root. This is local
Builder evidence only and does not establish a clean full gate or independent disposition.

After cross-examination exposed the Toolhelp fallback race, the suspended-root, fail-closed
adaptation ran 25 sandbox tests with one expected POSIX-only skip. The final
short-root full gate passed 526 tests in 1043.431 seconds with five expected skips. The Judge
deferred Phase 10 pending separate Windows and Curator reproduction; this ADR does not
authorize Phase 11 or alter `B-OPS-06`.

## Rollback

Revert the implementation and tests while preserving this ADR, the reproduced P04
counterexample, audit artifacts, review dissent, and appeal history. P04 must remain paused
if rollback restores the false-timeout behavior.

## Ownership and follow-up

- Steward owns Windows process liveness and termination.
- Curator owns independent reproduction and residual-risk assessment.
- P04 owns re-running the materialization counterexample after this appeal merges.
- The hard-isolation owner of `B-OPS-06` owns Job Object/container/VM enforcement.
