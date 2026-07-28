# P20 — Release-Readiness Court

Status: pending in `01_POST_P13_OVERVIEW.md` | Depends on: P18, P19 and applicable source appeals | Unlocks: a narrowly scoped release decision

## 1. Objective

Issue a fail-closed release-readiness disposition for an exact product scope by integrating
capability, source/license, identity, provider, retention, isolation, operations, benchmark,
security, recovery, and customer-outcome evidence.

## 2. Required reading

1. `docs/plan/01_POST_P13_OVERVIEW.md`
2. `docs/plan/BLOCKERS.md`
3. `docs/architecture/HARDENED_VISION_CONTRACT.md`
4. P14–P19 completion records, audits, adverse evidence, and court records
5. Every source-specific P12 appeal applicable to the release scope

## 3. Prerequisites and authority

- Branch: `phase/P20-release-readiness-court`.
- P18 and P19 are complete.
- Every blocker applicable to the proposed release scope satisfies its literal exit condition.
- Release scope, exclusions, supported environments, authority, users, data classes, SLOs,
  safety floors, rollback, and claim text are frozen before judgment.
- The Judge and Appeals Judge are distinct from builders, operators, Curators, and affected
  champions and have authenticated identities.

## 4. Scope and design constraints

- Reconstruct evidence from authoritative external retention, not hand-written summaries.
- Verify exact SHAs/images, SBOM/provenance, dependencies/licenses, signed receipts, policy
  and budget envelopes, source coverage, isolation, recovery, pilot outcomes, and benchmarks.
- Treat missing, stale, conflicting, unverifiable, or out-of-scope evidence as blocking.
- Separate three decisions: release permission, production scope, and comparative claims.
- Permit only an exact version and scope with expiry/review date and emergency revocation.
- Preserve dissent and appeal paths.

## 5. Deliverables

- Machine-readable release evidence index and claim/scope manifest.
- Reproducible readiness audit and independently generated human report.
- Threat, residual-risk, operations, support, rollback, and revocation packets.
- Curator report, expert testimony, Judge verdict, Appeals disposition, and blocker updates.

## 6. Required tests

The court must reject missing source/license evidence, unsigned/replayed receipts, provider
bypass, external-ledger gaps, isolation failures, missed SLO/safety floors, failed recovery,
unresolved critical incidents, absent customer-outcome evidence, insufficient benchmark
burden, scope-broadened claims, expired authority, and Judge conflicts.

## 7. Exit criteria

- All deterministic gates and independent reconstruction pass.
- Applicable `B-SRC`, `B-GOV`, and `B-OPS` exit conditions are satisfied or the affected
  capability is explicitly excluded from the frozen release scope.
- P18 operational evidence and P19 court evidence validate from external retained records.
- Curator permits; Judge issues `adopt` or `adapt`; Appeals Judge confirms or narrows it;
  Orchestrator confirms rollback, expiry, and operational ownership.
- The release manifest states exactly what is production-ready and what remains blocked.

## 8. Evidence, rollback, and forbidden shortcuts

Retain the complete evidence index, reconstruction output, all testimony, dissent, verdicts,
authority, expiry, audit, and release artifacts. Rollback revokes the release permission,
executes the tested operational rollback, verifies state/evidence integrity, and preserves the
court record.

Do not equate green CI, a merged PR, one real-provider mission, a successful pilot, or a
benchmark win with general release readiness. Do not mark the repository blocker-free when
excluded or deferred obligations remain.

