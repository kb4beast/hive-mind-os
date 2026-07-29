# Phase 1 Characterization Judge Disposition

- Judge identity: `/root/phase1_judge`
- Candidate commit:
  `cef59df84a921a3700782c96b1b5ff325e2690a7`
- Parent:
  `0948f7ec385238f5825ce7c39dd25de2e9a1035d`
- Decided: 2026-07-28

## Disposition A — delivery artifact

`adapt`

The exact candidate may be pushed and published as a stacked draft pull
request targeting `codex/repair-ci-test-contract`.

This disposition permits review of Phase 1 characterization only. It does not
authorize merge, production use, Phase 2 implementation, source admission,
host-support claims, or architecture activation.

## Disposition B — architecture, sources, and implementation

- ADR-018: `defer`
- ADR-019: `defer`
- ADR-020: `defer`
- Phase 1 source admission: `defer`
- Phase 2 implementation authorization: `defer`

None is adopted. Registration and pinning are not admission.

## Reproduced evidence

- Exact head and parent matched the values above.
- Candidate contained one commit, 14 files, and no `src/` production change.
- Worktree remained clean.
- Focused characterization: 3 of 3 passed.
- Ruff: passed.
- Pyright `src`: 0 errors and 0 warnings.
- Handoff SHA-256:
  `dbd73add9f47aa98a30d19f1538179e5e961c1452a70b9ce54b7403b4e387a46`
- Test SHA-256:
  `3ae58baf53d2c9e27ab55930ac58f5f59d32b69fe9b8a75351c4512350f13b6b`
- Fixture SHA-256:
  `7ea33827ba4180c9a86f97b8dfe8b555f0a7c6ff7202a9a7408d1fd81092642e`
- Compatibility document SHA-256:
  `1b36523a8f2cbdd7d58a6dc0c66f003a6ddb5958e80b0f0e21434bed4100f22b`

The Judge independently reproduced the Curator’s final bounded acceptance.
The two Curator remands materially strengthened SQLite DDL/index/trigger,
append-only behavior, provider-parser, and live `model.call` coverage.

## Conditions

- Keep the stacked pull request draft.
- Require clean GitHub checks on the exact Phase 1 head.
- Preserve `B-GOV-06`, `B-GOV-07`, `B-OPS-07`, and `B-OPS-08`.
- Do not use administrator bypass or weaken protection.
- Do not cite broad Windows discovery as clean while `B-OPS-08` remains open.
- Public API signatures and a machine-proven path-by-path writer/event
  inventory remain incomplete; do not claim Phase 1 or compatibility
  completeness.
- Material follow-up commits require new exact-head Curator and Judge review.

## Reasons for merits deferral

- Some source pins, versions, licenses, and admission courts remain incomplete.
- Child-claim extraction below the 31 parent claims remains incomplete.
- Capability requests and live runtime authority are not yet reconciled.
- Privacy/deletion, tenant identity, federation, and repository identity remain
  unresolved.
- Provider documentation is mutable; AgentTelemetry evidence is unavailable.
- The exact Armory source remains unidentified.
- Provider conformance fixtures and held-out behavioral evaluation designs do
  not yet exist.

## Dissent and rollback

The strongest dissent is that exported API names are frozen without public
signatures or broad behavior, and the path inventory is evidence-backed prose
rather than a completeness-enforced writer/event registry. This does not block
draft review but blocks a completion claim.

Rollback closes the stacked draft and removes its branch; generation-zero
runtime and stored state are unchanged. Preserve this record, the source
register, Curator remands, dissent, fixtures, and losing architecture
proposals.

No appeal was ripe because there was no earlier independent Judge merits
verdict. A future appeal requires a different Appeals Judge identity.
