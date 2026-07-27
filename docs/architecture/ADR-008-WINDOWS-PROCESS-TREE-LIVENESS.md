# ADR-008: Bind Windows Process-Tree Liveness to Process Creation Time

- **Status:** Proposed for independent P03 appeal review
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

## Threats and residual limits

| Threat | Control | Residual |
|---|---|---|
| Stale parent PID | Root/descendant creation-time comparison | Snapshot and query are not atomic |
| Metadata access denied | Treat unknown-time candidates as descendants | May retain a false positive rather than fail open |
| Early parent exit | Root process handle retains its creation time; snapshot follows genuine descendants | Windows remains best-effort without a Job Object |
| PID reuse during traversal | Creation-time lower bound rejects pre-root processes | A later unrelated process plus matching live ancestry remains a process-tier race |

This does not add Windows CPU or memory enforcement, network isolation, filesystem ACLs,
Job Objects, containers, or externally authenticated evidence. `B-OPS-06` remains open.

## Acceptance evidence

- A deterministic table regression excludes a stale direct record and its descendants,
  while retaining a genuine child and grandchild.
- Repeated short-lived Windows sandbox commands complete without false timeout.
- Existing early-parent-exit and timeout-tree regressions still pass on Windows.
- The original P04 materialization regression completes against the repaired sandbox.
- Full tests, Ruff, Pyright, audit, exact-head GitHub checks, and independent court review
  are required before delivery.

## Rollback

Revert the implementation and tests while preserving this ADR, the reproduced P04
counterexample, audit artifacts, review dissent, and appeal history. P04 must remain paused
if rollback restores the false-timeout behavior.

## Ownership and follow-up

- Steward owns Windows process liveness and termination.
- Curator owns independent reproduction and residual-risk assessment.
- P04 owns re-running the materialization counterexample after this appeal merges.
- The hard-isolation owner of `B-OPS-06` owns Job Object/container/VM enforcement.
