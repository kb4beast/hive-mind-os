# ADR-010: Seal P05 Verification and Preserve Failure Evidence

- **Status:** Proposed for repaired-candidate court review
- **Date:** 2026-07-27
- **Case:** `CASE-P05-CONSOLIDATED-REVIEW-APPEAL-1`
- **Originating work order:** `docs/plan/P05_VERTICAL_SLICE.md`
- **Prior decisions:** ADR-003, ADR-007, ADR-009
- **Challenged candidate:** `f6cc1cc9947b526b1656eed7e71da321cde26c54`
- **Capability maturity:** structurally prototyped

## Context

The first consolidated P05 court withheld delivery. The Judge reproduced a model-backed
self-approval path: Explorer ran the real failing suite, while Builder and Curator
substituted passing no-op commands and published a change that did not fix the repository.
The Judge and Orchestrator also found that `model.call` events were outside the
`MissionReport` correlation. The Curator and Judge independently reproduced a Git
failure that emitted receipts which the mission neither recorded nor charged, and the
Curator and Orchestrator found that every failed-run receipt became unresolvable when its
temporary evidence directory was deleted.

These are reproduced counterexamples, not speculative hardening. The challenged candidate
and all dissent remain in Git history.

## Court record

- **Advocate:** retain the P05 local vertical-slice architecture and repair the four
  evidence and verification defects as one append-only challenger.
- **Cross-examiner:** require a regression for backend test substitution, a regression
  for post-spawn Git failure, model-call reachability assertions, and independent
  validation of failed-run receipts.
- **Expert testimony:** the Curator reproduced both Git-receipt loss and dangling
  failed-run references; the Judge reproduced model self-approval and detached model
  events; the Orchestrator confirmed the delivery boundary must remain blocked.
- **Judge disposition for the challenged candidate:** `adapt`.

The repaired candidate still requires a separate final Curator, Judge, and Orchestrator
review before this ADR may be adopted.

## Decision

1. The first Explorer test command that produces the required failing receipt becomes the
   sealed repository test command for that mission. Builder and Curator must request the
   exact same argument vector. A substituted command fails the mission before publication.
2. `Objective.id` and `MissionReport.run_id` use one mission correlation. When a
   `ModelBackend` supplies or receives a ledger, `RepositoryMission` binds it to the
   mission ledger, making every `model.call` event reachable in ledger sequence.
3. `_workspace_call` settles every receipt emitted after the call boundary even when the
   operation raises. Budget consumption and `receipt.recorded` events are attempted before
   the original exception propagates; settlement errors annotate rather than replace that
   originating exception.
4. Receipt bytes for a failed executed mission move to a unique adjacent
   `.OUTPUT-failed-evidence-RUN_ID` directory. `MissionReport.receipt_root` points there,
   the references are revalidated after the move, and the failed report is written into
   that evidence directory. The requested delivery output remains absent.

The Curator's separately requested acceptance command remains part of the P05 fixture
contract. P08 still owns structural Curator separation and sealed independent acceptance
checks; this decision does not claim to complete P08.

## Threats and controls

| Threat | Control | Residual |
|---|---|---|
| Backend substitutes a trivial passing test | Builder and Curator commands must byte-for-byte match the Explorer failure-reproducing argument vector | A Builder may edit repository tests; P05's independent scripted criterion detects its required sabotage fixture, while P08 owns stronger sealed checks |
| Model evidence is detached from the report | One run/objective correlation and one ledger binding | External durable storage and resume remain P06 |
| Git emits side effects and then raises | Exceptional settlement captures actual new receipt records and charges their count | Storage failure can still prevent preservation and therefore fails closed |
| Failed-run references dangle after cleanup | Evidence is moved outside temporary workspaces and validated before reporting | Retention policy and garbage collection belong to P06/P11 |
| Failure evidence is mistaken for delivery | `artifact_directory` stays null and the requested output path is never published | User interfaces must continue to render failed/quarantined state explicitly |

## Acceptance evidence

- An adversarial deterministic `ModelBackend` cannot replace the sealed test command with
  a passing no-op and publishes no artifact.
- All eight `model.call` events are reachable from the model-path report, share the mission
  correlation, and explain the difference between model tool calls and Git/sandbox receipts.
- A branch-creation failure retains both the successful preflight receipt and failed Git
  receipt, charges both, records both in the ledger, and preserves the original failure.
- Sabotage and Git-failure reports retain a resolvable receipt root and persisted report,
  while the requested delivery directory remains absent.
- The P05 suite, full suite, Ruff, Pyright, offline CLI repetitions, exact-head CI, audit,
  and final consolidated court all pass on one repaired candidate.

## Rollback

Revert the P05 repair commit and PR before any successor depends on it. Do not restore the
challenged candidate to delivery eligibility; its `adapt` verdict and reproduced evidence
remain preserved. Remove no failed-run evidence as part of rollback.

## Deferred limits and ownership

- P06 owns durable mission checkpoints, restart, retention, and recovery.
- P07 owns GitHub delivery, protection, credentials, and remote receipts.
- P08 owns structural Curator independence and sealed acceptance-check authority.
- P11 owns operational projection and evidence lifecycle policy.
- P12 owns unresolved source ingestion and licensing.
- B-OPS-06 owns hard hostile-code isolation.

This decision does not establish production readiness, complete source coverage, hostile
code isolation, external delivery, or superiority.
