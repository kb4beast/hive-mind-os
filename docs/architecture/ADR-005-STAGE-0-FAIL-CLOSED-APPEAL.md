# ADR-005: Stage 0 Fail-Closed Appeal

- **Status:** Accepted as an appeal amendment to ADR-004; Stage 0 external obligations remain open
- **Date:** 2026-07-27
- **Case:** `CASE-IMPL-003-004-STAGE0-TRUTH-SOURCE-GOVERNANCE`
- **Appealed commit:** `577cc2f3bad9c7c78dd372a8207a871b8a06eb35`

## Context

Independent Curator, Cross-Examiner, Orchestrator, and Judge review rejected completion at
the appealed commit. The review preserved the useful implementation but reproduced
fail-open counterexamples:

- the tracked GPT manifest described the author's CRLF working bytes rather than the LF Git
  blobs used by a clean checkout;
- portable-path, date-time, and numeric validation admitted nonportable paths, non-RFC 3339
  times, and non-finite resource values;
- proposed actions were not independently bound to mission, state, actor, and a recomputed
  canonical digest, and receipts could be self-verified;
- material tracked-pack and governed-source manifest semantics could be changed without
  rejection;
- unresolved licenses and composite repository sources escaped dependent-claim blocking;
- schema-5 audit verification checked counts and shapes without conserving source identities,
  claim partitions, blocker derivation, release readiness, or production evidence; and
- actual source and claim records had no demonstrated formal-contract serialization path.

The appeal treats the earlier test pass and audit as adverse historical evidence, not as a
promotion receipt.

## Decision

1. A portable artifact path uses canonical relative POSIX syntax, has no empty/current/parent
   segment, Windows drive or reserved name, alternate-data-stream colon, backslash, or
   trailing dot/space.
2. Contract date-times must be calendar-valid RFC 3339 values with an explicit `Z` or
   hour/minute offset. Numeric limits must be finite. Exact digests have fixed length as well
   as a lowercase SHA-256 pattern.
3. A tool intent's canonical digest binds every declared field except the digest field
   itself. Runtime validation independently recomputes it and binds action and receipt to the
   mission, state, role actor, policy reference, lease, and a different verifier.
4. The tracked GPT fingerprint binds the complete strict manifest, including authority,
   simulation limits, formal-schema reference, and fail-closed declarations. Unknown or
   altered semantics are rejected.
5. The governed `SRC-023` manifest has an exact shape and a governance digest over all
   source-adjudication metadata. Relationship, image-independence, chain-of-custody, and
   blocking-obligation values are semantically checked even if an attacker recomputes the
   unkeyed digest.
6. Unknown licenses and every repository-bearing source kind are source-evidence blockers.
   Their dependent claims are blocked at design, implementation, and promotion burdens.
7. Schema-5 verification reconciles unique source coverage, source-status counts, docket
   issues, source blockers, machine-blocked claims, release readiness, inventory
   completeness, the complete maturity partition, and evidence classes. A freshly
   self-digested contradiction remains invalid.
8. `SourceRecord` and `IdeaClaim` expose lossless contract serializers. Historical
   non-digests such as `prompt-v1` remain preserved as `unverified_digest_label`, never in a
   cryptographic digest field.

## Threat delta

| Threat | Appeal control | Residual risk |
|---|---|---|
| Author workstation passes while clean checkout fails | LF-normalized tracked pack plus exact byte tests and detached reproduction | Platform/filesystem behavior still requires CI coverage |
| Fabricated action and matching fabricated receipt digest | Independent canonical intent digest and cross-record binding | External provider authentication is a later-stage control |
| Authority text substituted in a valid byte inventory | Strict full-manifest fingerprint | Local SHA-256 does not authenticate the manifest author |
| Image or overlap reclassified as independent/superseding | Governance digest plus source-specific semantic constraints | Provenance and reuse rights remain unresolved |
| Licensed/pinned source gap escapes claim blocking | License and composite-repository blockers feed courtroom and audit gates | External evidence still has to be retrieved and adjudicated |
| Self-digested audit claims false production readiness | Conservation and contradiction checks across every schema-5 truth set | Signed external identity and durable storage remain later stages |

## Acceptance evidence

- Regression tests reproduce every rejected path, time, number, action, receipt, manifest,
  source-blocking, and audit-verifier counterexample.
- All live docket source and claim records validate through their formal serializers.
- The full suite, Ruff, and Pyright pass.
- A wheel built from the exact committed tree contains all eleven schemas and passes in a
  fresh environment.
- A disjoint Curator retests the exact appeal commit from a clean detached checkout.
- Separate lifecycle and court identities preserve dissent and issue a new verdict; no prior
  rejection is overwritten.

## Migration and rollback

This is a strict compatible-reader migration: documents previously accepted only through a
fail-open edge may now be rejected. The runtime-state schema version remains 3 because the
wire fields are unchanged; action-digest semantics are clarified and the example digest is
regenerated. The governed `SRC-023` manifest gains `governance_digest`; no raw exhibit changes.
Historical non-digest labels move to an explicit field without deleting their values.

Rollback is additive supersession only. Do not restore the rejected validators or delete the
appealed commit, adverse reports, manifests, source records, or audits. A future relaxation
requires a new ADR, counterexample tests, disjoint review, and evidence that it does not
reopen these fail-open paths.

## Open obligations

This appeal does not activate GitHub protection, resolve source licenses or missing bytes,
ingest the seven videos, establish signed identities, create a durable external ledger, prove
production operation, or support a superiority claim. Those obligations remain explicit and
machine-blocked.
