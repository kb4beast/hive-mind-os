# P04 Audit-Compatibility Continuation Handoff

**Status:** open and blocked; this document makes no P04 completion, release, or
integration claim.
**Snapshot:** 2026-08-05. `origin/main` is
`dfee1c24125034c750e3d6e93c5af6c9ffd06e6d`.
**Purpose:** allow one new session to remove the exact-audit blocker for P04 without
reopening P03, advancing P05, weakening audit controls, or using external authority.

## Binding order and authority

`AGENTS.md`, `docs/plan/BLOCKERS.md`, and
`docs/architecture/HUMAN_AUTHORITY_GATES.md` remain binding. Read all three before
acting. Do not merge, push to, or enable auto-merge for `main` or staging. Do not use
provider credentials, live provider calls, signing authority, or external retention
authority. Do not update `BLOCKERS.md` unless its literal exit condition is reproduced.

P03 has a separate draft repair PR, #110. It is not merged and remains pending
authorized integration. It is not part of this handoff.

## P04 facts that are already established

| Item | Exact value |
|---|---|
| P04 product candidate | `76ec259a69912a0e9a4f6324aa62353eba05feaf` |
| Representation in main | Candidate is an ancestor of `origin/main` |
| Exact CI result | Constitutional CI run [31018970420](https://github.com/kb4beast/hive-mind-os/actions/runs/31018970420) completed successfully for that SHA |
| Preserved evidence branch | `origin/codex/p04-evidence-confinement-closeout` at `3d2ff1a75628caf2f6af6551290f504d51e00903` |
| Current P04 court state | blocked before Curator, Judge, or Orchestrator because no clean exact-candidate audit exists |

The evidence branch is append-only. It contains:

- `evidence/audits/P04-evidence-confinement-closeout-post.json` — the candidate's
  legacy auditor attempt, `complete: false`.
- `evidence/audits/P04-evidence-confinement-closeout-current-auditor-post.json` — the
  current auditor's attempt against the exact candidate, also `complete: false`.
- `evidence/courts/p04-audit-76ec259.json` — the blocker receipt.
- `evidence/courts/p04-github-ci-76ec259.json` — the exact successful CI reference.

Retain all four files. They are failed evidence attempts, not permission to claim P04
approved.

## Demonstrated blocker

Both audit attempts passed the candidate's 186 tests and found a clean worktree, but
failed closed while loading its founding-source docket:

- At candidate line `src/hive_mind_os/source_docket.py:162`,
  `load_source_docket()` accepts no arguments.
- The current dynamic audit loader at
  `src/hive_mind_os/current_state_audit.py:484` always calls
  `load_source_docket(repository)`.
- The resulting exact safe error is:
  `load_source_docket() takes 0 positional arguments but 1 was given`.

This is an audit-loader compatibility defect, not evidence that the P04
evidence-confinement repair failed. It must still be repaired and independently
verified before P04 can proceed.

## Only permitted next implementation

Create one clean `codex/` branch from the then-current `origin/main` for an
audit-loader compatibility repair. Limit product changes to
`src/hive_mind_os/current_state_audit.py` and focused tests for that loader. Do not
alter the historical P04 candidate or change the P04 git-adapter behavior.

The repair must select invocation by the inspected callable signature, not by catching
an arbitrary `TypeError` from the loader body:

1. Invoke a loader that accepts the repository argument with that argument.
2. Invoke a legacy zero-argument loader with no argument.
3. Fail closed for an unsupported, ambiguous, or uninspectable signature.
4. Never retry a loader after it raises `TypeError` internally; that could hide a real
   docket-loading failure.

Focused tests must demonstrate all four behaviors, including preservation of an
internally raised `TypeError` as a failure. Run the focused tests before broader
validation. Do not weaken audit-completeness, provenance, or docket validation checks.

## Required P04 continuation sequence

1. Fetch `origin`, verify the current `main` SHA and successful Constitutional CI, and
   verify that `76ec259...` remains an ancestor of `origin/main`. If main is not green,
   stop P04 and address only the demonstrated mainline failure in a separate branch.
2. Verify the preserved evidence branch and files above. If any are unavailable, append
   a new P04 evidence-availability blocker and stop.
3. Implement the narrow audit-loader repair and independently review that repair. Its
   own test and CI evidence must be preserved; it must not silently change the P04
   product candidate.
4. From the repaired auditor, audit a clean detached worktree at exactly
   `76ec259a69912a0e9a4f6324aa62353eba05feaf`. The resulting artifact is usable only
   if it reports `audit.complete: true`, the repository head is exactly `76ec259...`,
   the worktree is clean, and the test result is passing. Write it under a new,
   append-only P04 evidence filename; never replace either failed attempt.
5. Materialize separate detached worktrees and run the P04 court in order: Curator,
   Judge, then Orchestrator. Curator may use saved local Codex sign-in only, may not
   edit files or use provider credentials, and must return only `decision` and a short
   safe reason. Each later role must make an independent decision rather than treating
   another role's conclusion as proof.
6. The exact CI receipt above may be retained only while the P04 product candidate stays
   exactly `76ec259...`. If any P04 product code changes, run fresh exact-candidate CI
   and record its URL and conclusion.
7. Append a P04 closure receipt only after a valid audit, usable Curator/Judge/
   Orchestrator approvals, passing exact CI, and a current-main ancestry check. Deliver
   the receipts through a reversible branch or draft PR; never merge them directly.

## Stop conditions

- If the compatibility repair cannot produce a clean exact-candidate audit, append one
  short blocked receipt with the demonstrated reason and stop P04.
- If any court role returns an unusable, blocked, or non-approval decision, preserve the
  result and stop P04 unless it identifies one narrow repair.
- P05 remains paused until P04 has met its closure conditions. Do not run P05 audits or
  court reviews during this workstream.
- After P04 and P05 are both actually closed, stop unless the owner adopts a tracked
  successor plan.

## Copy-ready continuation prompt

```text
Continue only P04 from docs/plan/P04_AUDIT_COMPATIBILITY_HANDOFF.md. Read AGENTS.md,
docs/plan/BLOCKERS.md, and docs/architecture/HUMAN_AUTHORITY_GATES.md first. Start from
current origin/main in a clean codex/ branch. Do not merge or push to main/staging, use
provider credentials, alter the historical P04 candidate, replace failed evidence, or
run P05.

Repair only the signature-aware source-docket invocation in the current audit loader,
with focused tests that preserve internal loader TypeErrors as failures. Then create a
new clean audit of exact candidate 76ec259a69912a0e9a4f6324aa62353eba05feaf and resume
the P04 Curator, Judge, and Orchestrator sequence only if that audit is complete.
```
