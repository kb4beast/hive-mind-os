# Phase 1 Completion Portable Checkpoint

- Checkpoint status: independently accepted by Curator; Judge and exact-head
  delivery gates pending
- Date: 2026-07-28
- Draft PR: `kb4beast/hive-mind-os#29`
- Branch: `codex/phase1-redesign-characterization`
- Required base: `codex/repair-ci-test-contract`
- Required base SHA: `0948f7ec385238f5825ce7c39dd25de2e9a1035d`
- Starting head: `ee00967610df9e7d0ec4a5150bac751cc6880105`
- Phase 1 completion commit:
  `0d44b1665d9775b5b889e99c2d56e63db9a010b9`
- Exact published verification head: pending

## Objective and completed candidate state

Finish every Phase 1 obligation in
`docs/NEXT_SESSION_HANDOFF_OBSIDIAN_AGENT_REDESIGN.md` without starting Phase 2.
The candidate:

- preserves 131 root APIs, 33 package APIs, and 13 CLI contracts;
- adopts ADR-018, ADR-019, and ADR-020 as architecture contracts without
  activating a runtime challenger;
- defines `hive-agent-definition/v2`, `hive-memory/v1`,
  `hive-obsidian-projection/v1`, and `hive-usage-event/v1`;
- decides every registered Phase 1 source group and quarantines the
  unidentified Armory and unavailable AgentTelemetry content;
- preserves 100 atomic request claims with individual dispositions;
- closes authority, threat, privacy, isolation, migration, rollback,
  observability, and evaluation design boundaries; and
- changes only the repository-local `.obsidian/` ignore policy outside
  evidence, documentation, generated inventory, and tests.

No file under `src/hive_mind_os`, schema, package resource, prompt, stored-state
shape, provider behavior, runtime selector, public facade, or CLI parser is
changed by the completion candidate.

## Recovery and continuation

1. Verify the worktree branch and merge base exactly match the values above.
2. Read the handoff, PR #29 diff, ADR-018 through ADR-020, canonical contracts,
   completion inventory, merits court, source court, and append-only ledger.
3. Re-run the focused Generation Zero and Phase 1 tests on Python 3.11, 3.12,
   and 3.14.
4. Preserve the accepted independent Curator receipt at
   `evidence/courts/P1-COMPLETION-CURATOR.md` and obtain a separately
   identified Judge disposition. A Builder statement cannot satisfy either.
5. Repair any remand without weakening the frozen surfaces or evidence gates.
6. Push only to PR #29's branch and require its exact-head Python matrix,
   Ruff, Pyright, CodeQL, secret scan, dependency review, SBOM, wheel,
   provenance, and resource checks to pass.
7. Keep the PR draft, stacked on PR #28, and do not merge either PR or modify
   `main`.

The rollback procedure is
`docs/architecture/PHASE1_ROLLBACK_PLAN.md`. Historical source dispositions,
dissent, failures, and court records remain append-only.

## Adverse evidence and open gates

The full test suite was attempted in stock Linux Python 3.11, 3.12, and 3.14
containers. Each image collected 430 tests and reported the same two failures,
five errors, and one skip because the linked worktree's `.git` file contains a
Windows absolute gitdir unavailable inside the container. Those runs are
nonqualifying and are retained in
`evidence/audits/P1-completion-ledger.jsonl`; they are not represented as
passing. Focused Phase 1 tests pass in all three versions. The published
exact-head GitHub matrix must supply the qualifying complete-suite receipt.

Independent Curator, Judge, and exact-published-head security/provenance gates
were required at the initial checkpoint. The Curator subsequently accepted
the exact candidate `0d44b1665d9775b5b889e99c2d56e63db9a010b9`;
Judge and exact-published-head security/provenance gates remain pending.

## Deferred work and next eligible objective

Runtime implementation is deliberately outside Phase 1. After PR #29 is
independently adopted and its exact head is green, the next eligible objective
is:

`Phase 2 — Additive memory and telemetry foundation`

Recommended branch:
`codex/phase2-additive-memory-telemetry-foundation`

Required base: the final verified head of PR #29, while PR #29 remains stacked
on PR #28. Phase 2 must add versioned schemas and inert implementation
additively; it may not silently replace Generation Zero.
