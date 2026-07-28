# ADR-012: Source Ingestion and Additive Reconciliation

- **Status:** Proposed pending independent Curator and Judge review
- **Date:** 2026-07-27
- **Scope:** P12 source-exhibit capture, court-gated source reconciliation, and dated
  evidence-obligation deferral

## Context

The immutable founding docket records 23 sources and 84 claims, but it had no executable
path for attaching newly supplied bytes to an existing source identity. The current-state
audit could derive incomplete-source blockers, yet no admitted additive record could change
the current projection after missing evidence was captured. Unavailable materials also
remained represented only by open backlog prose rather than a dated court decision.

The seven incomplete videos, historical raw bytes, source licenses, repository pins, and
the sibling pack's authorship and image custody were not available in the P12 worktree.
Inventing or remotely substituting those materials would violate the capture burden. In
particular, a current remote repository head would not prove which historical commit an
earlier mutable reference intended.

## Decision

1. Preserve the founding docket constants unchanged. New evidence attaches under
   `evidence/sources/<SRC-ID>/` as raw content-addressed bytes and immutable JSON records.
2. A source exhibit binds the raw-byte SHA-256 digest, original filename, media type, byte
   count, actual capture time, capturer identity, supply method, exact locator, license
   state, and—for an agent-derived artifact—an existing parent exhibit digest.
3. Exhibit capture alone cannot change the current source projection. A reconciliation
   requires an admitted exhibit and a promoting courtroom verdict with structurally
   distinct advocate, cross-examiner, and judge identities.
4. Reconciliations form a unique append-only chain from the prior serialized source state.
   An orphaned or branched chain, altered exhibit, non-promoting verdict, unrelated claim,
   mutated source identity, or result not bound to the exhibit digest fails closed.
5. `load_source_docket(repository)` applies admitted reconciliation chains when an explicit
   repository root is supplied. `load_default_source_docket()` remains the immutable
   founding inventory, and callers without a repository root retain its historical
   behavior.
6. The current-state audit supplies its audited repository root to the docket loader, so
   any future admitted reconciliation is reflected by the existing blocker derivation
   rather than by a new bypass or self-reported blocker field.
7. An unavailable evidence obligation receives a `defer` verdict with a future review date
   and remains machine-blocked. A deferral schedules reconsideration; it is not source
   completion, license resolution, independent verification, or promotion.
8. The CLI accepts only human-supplied or explicitly parent-bound derived files. It does not
   download videos or external transcripts.

## Advocate case

An executable capture path turns source completeness from a static audit finding into a
reversible evidence workflow. Content addressing protects exact bytes, court gating prevents
an exhibit from silently promoting a claim, and explicit repository-root reconciliation lets
the audit continue deriving its own blockers from source metadata. Dated deferrals prevent
unavailable evidence from becoming undated backlog rot without weakening any dependent-claim
block.

## Cross-examination

Local participant labels do not authenticate independent actors. SHA-256 proves integrity,
not authorship or permission to reuse. A maintainer could supply incomplete or misleading
bytes, and a captured license text still needs compatibility review. Multiple competing
reconciliations could hide a fork if accepted by ordering alone. The design therefore rejects
branches, binds every transition to the preceding source state, preserves unknown licenses
as blockers, and leaves all P12 backlog claims blocked when no actual source evidence was
available.

## Expert findings

- **Source governance:** retain original bytes and distinguish capture time from publication
  or historical retrieval time.
- **Security:** reject digest mismatch before registration, verify stored bytes on every
  admission, and prevent path data from controlling storage locations.
- **Licensing:** accept an SPDX field as structured evidence only; `unknown` and
  `unresolved-pending-review` cannot populate `SourceRecord.license_spdx`.
- **Reliability:** append-only transition records require a unique prior-state chain and
  deterministic fail-closed replay.

## Threat delta

| Threat | Control | Residual risk |
|---|---|---|
| Fabricated digest | Recompute before capture and on every read; ledger rejection when available | Capturer identity is not externally signed |
| Derived text presented as primary evidence | Require an existing parent exhibit digest | Extraction correctness still needs independent review |
| Exhibit silently unblocks a claim | Require a promoting courtroom verdict and admitted reconciliation | Local identity separation is structural, not authenticated |
| Reconciliation rewrites source identity | Immutable identity fields and prior-state digest binding | A future schema migration needs a superseding ADR |
| Competing source histories | Reject orphaned and branched chains | External append-only retention remains unresolved |
| Deferral interpreted as completion | Keep source metadata and dependent machine blockers unchanged | Review-date enforcement needs operational scheduling |

## Acceptance evidence

- `tests/test_ingestion.py` covers content addressing, tamper detection, parent binding,
  exhibit-plus-verdict gating, participant separation, dated deferral, license blocking,
  additivity, fabrication rejection, and CLI contracts.
- Existing source-docket and current-state-audit tests remain unchanged and passing.
- Every P12 source backlog row points to an immutable defer record and future review date;
  no unavailable content or license is asserted.

## Migration and rollback

The repository-aware loader is opt-in outside the audit, so existing callers of
`load_source_docket()` retain the immutable founding projection. Revert code by reverting the
P12 implementation commit. Captured exhibits, defer verdicts, and any later reconciliation
records are evidence history and must be preserved or additively superseded, never deleted.
