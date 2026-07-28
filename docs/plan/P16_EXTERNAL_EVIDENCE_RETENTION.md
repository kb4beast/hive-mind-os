# P16 — External Append-Only Evidence Retention

Status: pending in `01_POST_P13_OVERVIEW.md` | Depends on: P15 | Unlocks: P18, P20

## 1. Objective

Close `B-GOV-04` by persisting authenticated audit and operational evidence outside the
repository and local scheduler in a replaceable append-only store with independently tested
integrity and disaster recovery.

## 2. Required reading

1. `docs/plan/01_POST_P13_OVERVIEW.md`
2. `docs/plan/P06_DURABLE_MISSIONS.md`
3. `docs/plan/P11_SCHEDULER_AND_OPERATIONS.md`
4. `docs/plan/P15_AUTHENTICATED_IDENTITY_AND_RECEIPTS.md`
5. `docs/plan/BLOCKERS.md` (`B-GOV-04`)

## 3. Prerequisites and authority

- Branch: `phase/P16-external-evidence-retention`.
- P15 signed evidence envelopes are stable.
- A human provides a bounded external retention account, retention policy, access roles,
  cost limit, recovery authority, and deletion/expiry policy.

## 4. Scope and design constraints

- Add a provider-neutral retention interface with append, read, enumerate, verify, export,
  checkpoint, and recovery operations.
- Use authenticated, content-addressed records with ordered chain/checkpoint proofs.
- Acknowledge mission completion only according to an explicit local/external durability
  policy; partial writes and ambiguous acknowledgements fail closed.
- Detect gaps, reorder, rollback, mutation, deletion, duplicate/conflicting sequence, and
  stale-writer attempts.
- Keep an offline deterministic adapter for CI and at least one authorized external adapter
  for manual recovery evidence.
- Redact before persistence and minimize sensitive content.

## 5. Deliverables

- Retention ADR, interface, offline conformance adapter, and authorized external adapter.
- Export/restore and independent integrity-verification tools.
- Disaster-recovery, access-rotation, outage, and cost runbooks.
- P16 audit, external recovery receipt, adverse evidence, and court record.

## 6. Required tests

Conformance tests cover append-only behavior, idempotent retry, crash between local/external
commit, conflicting writers, mutation/deletion/gap/reorder detection, credential expiry,
provider outage, export completeness, and reconstruction after complete local-state loss.

## 7. Exit criteria

- Full deterministic gates and adapter conformance pass.
- An authorized external run retains a complete authenticated mission evidence chain.
- On a clean machine/workspace with local state removed, an independent Curator exports,
  verifies, and reconstructs the chain.
- Mutation and deletion attempts are detected and block promotion.
- A separate Judge and Orchestrator permit the exact candidate.

## 8. Evidence, rollback, and forbidden shortcuts

Preserve configuration digests, retention acknowledgements, recovery transcripts, integrity
proofs, failures, costs, audit, and dissent. Rollback stops new external writes and exports
all retained evidence; it never deletes remote evidence merely to revert code.

Do not call ordinary mutable object storage append-only without enforcement and recovery
proof, or treat repository Git history as external disaster recovery.

