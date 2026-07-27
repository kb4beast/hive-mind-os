# Stage 0 Truth Contracts and Source Governance Handoff

## Mission

- **Mission:** `MISSION-STAGE0-TRUTH-SOURCE-003-004`
- **Case:** `CASE-IMPL-003-004-STAGE0-TRUTH-SOURCE-GOVERNANCE-APPEAL`
- **Branch:** `codex/master-implementation-bootstrap`
- **Implementation candidate:** `f71e37934f86bdf45030cfa1fff4203445a1a87c`
- **Authority:** reversible local A2 work only
- **Status:** repository implementation candidate complete; final independent adjudication
  and external Stage 0 obligations remain blocked

## Delivered

1. Eleven packaged formal schemas and a strict standard-library validator.
2. Canonical action-digest, mission/state/actor/receipt/verifier truth binding.
3. Full tracked GPT manifest semantic fingerprint and clean-checkout LF byte inventory.
4. Exact preservation and governed validation of all sixteen sibling GPT/image files.
5. Additive `SRC-023` and `CLM-081`–`CLM-084`, retaining 23 sources and 84 claims.
6. Machine blocking for incomplete provenance/ingestion, licenses, digest labels, and
   repository pin/object gaps; 73 claims currently block.
7. Honest capability maturity capped at 65 specified and 19 structurally prototyped.
8. CurrentStateAudit schema 6 with metadata-derived blockers and a separately reconstructed
   Git/docket verification context.
9. CODEOWNERS, desired protected rules, pinned CI, static/type/security/license/secret
   checks, SBOM, build provenance, and attestation declarations.
10. ADR-004 plus the adverse-history-preserving ADR-005 appeal.

## Durable evidence

- [Final audit](../audits/current-state-audit-f71e379.json):
  `sha256:ea9ee7bcc78f2be6c5fff15137e1fb2f8339902696a3f5623aeaea1bf454a802`
- [Rejected first audit](../audits/current-state-audit-577cc2f.json): retained as adverse
  evidence, not a passing receipt.
- [Appeal court record](../courts/stage-0-truth-source-governance-appeal.md).
- [Remote-protection observation](../governance/repository-protection-577cc2f.json):
  required host protection absent.
- [Governed sibling manifest](../sources/SRC-023-classic-gpt-pack/manifest.json):
  `sha256:9d55be7e5d4e18fc77473e50afe8cb17dccb4e866f3c24317d300e1594455369`
  for the ordered raw inventory.

## Validation

- Clean Python 3.14: 133 passed, 1 skipped, 1,695 subtests.
- Fresh Python 3.12 installed wheel: 134 tests run, one skipped, otherwise OK.
- Ruff and Pyright pass.
- Exact wheel contains all eleven schemas.
- The final audit rejects unanchored verification and passes with the trusted context.
- The detached worktree remained clean.

## Scope and blockers

This handoff does not claim Stage 0 release readiness. The final independent reviewers could
not run because the review service reported its usage limit; the exact-candidate court
disposition remains `defer`. External source ingestion, bytes, pins, licenses, image custody,
GitHub protection/approvals, signed identities, durable evidence, production operation,
outcomes, and superiority proof remain open.

No push, PR, merge, deployment, remote policy mutation, external message, credential, secret,
financial, destructive, or authority-expanding action occurred.

## Resume instruction

When independent review capacity is available, run exactly one final wave against
`f71e37934f86bdf45030cfa1fff4203445a1a87c`: Curator reproduction, required separated
lifecycle testimony, then Judge disposition. Do not reopen implementation unless that frozen
review produces a new executable counterexample. If the candidate passes, issue an additive
evidence-only verdict commit. Backlog item 5 belongs to Stage 1 and must not be cited as Stage
0 work.
