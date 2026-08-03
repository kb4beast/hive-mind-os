# B-GOV-06 administrator-enforcement reconciliation court

## Clerk and source record

- Clerk: `BGOV06-Reconciliation-Clerk`
- Subject base: `a9bf98f01dddd51356b26897c997966f347670cd`
- External source: GitHub REST branch-protection and repository-ruleset responses for
  `kb4beast/hive-mind-os`, branch `main`, captured at the receipt timestamp.
- Provenance: one capture through the repository's GitHub adapter and one separately invoked GitHub
  CLI REST capture. Raw response bytes are represented by SHA-256; the normalized adapter report is
  retained verbatim. GitHub's API content is factual host-state evidence, not copied source code.
- Prior adverse evidence: PR #27, runs `30394284964` and `30394298035`, and the 2026-07-28 live
  response reporting `enforce_admins=false` remain preserved.

## Atomic claims

1. Current live protection reports `enforce_admins=true`.
2. The eight declared checks, two approvals, code-owner review, stale-review dismissal,
   last-push approval, conversation resolution, signed commits, linear history, force-push block,
   and deletion block remain configured.
3. Configuration evidence alone does not prove a protected delivery completed without bypass.
4. Configuration does not authenticate reviewer independence; that remains `B-GOV-07`.

## Advocate, cross-examination, and witnesses

- Advocate `BGOV06-Enforcement-Advocate` argues that the external administrator action required by
  the first half of `B-GOV-06` is now observable and should be recorded.
- Cross-Examiner `BGOV06-Delivery-CrossExaminer` rejects full closure because PR #48 has no reviews
  and has not delivered to `main`. It also rejects inferring human independence from account names.
- Adapter Witness `BGOV06-Adapter-Witness` reproduces the declared rules through the replaceable
  GitHub adapter.
- CLI Witness `BGOV06-CLI-Witness` independently normalizes a separate REST response. These are
  procedural methods under one assistant; authenticated actor independence is not claimed.

## Judgment

Judge `BGOV06-Reconciliation-Judge`, distinct from the named procedural participants, issues
`adapt`: accept the live administrator-enforcement evidence, update the declared verification
status, and narrow `B-GOV-06` to the remaining no-bypass delivery receipt. `Defer` full resolution
until PR #48 completes required checks and reviews, including two non-author approvals and required
code-owner approval, without administrator bypass. Reject any release-readiness or independent-human
claim from configuration alone.

## Acceptance, rollback, ownership, and appeal

- Acceptance: two capture methods agree on every declared rule; retained reports and receipts are
  digest-bound; tests reject claim escalation; exact-head CI passes.
- Rollback: revert the metadata and new receipt files while retaining this court and the captured
  external evidence as historical records.
- Owners: Integrator maintains the adapter record; Curator reproduces; repository administrator
  maintains host settings; external reviewers own the later protected-delivery evidence.
- Appeal: a later exact PR #48 merge receipt may close `B-GOV-06`; it may not close `B-GOV-07`,
  ADR-015 adoption, or release readiness automatically.
