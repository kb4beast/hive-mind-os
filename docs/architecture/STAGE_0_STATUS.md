# Stage 0 Status: Truth and Source Hardening

This status is additive to ADR-002 through ADR-005. The authoritative exact counts and
receipts are the latest post-commit `CurrentStateAudit` artifact.

| Stage 0 deliverable | Repository status | Remaining external or later obligation |
|---|---|---|
| Reproducible current-state/history audit | Implemented and independently verified for prior slices; schema 6 derives source blockers and reconciles coverage/maturity truth sets | Re-run on the final exact commit |
| Source snapshots, pins, object types, digests, licenses, coverage | Audit and coverage are executable; sibling pack is preserved exactly | Several original bytes, external commit pins, retrieval receipts, and licenses remain unresolved |
| Seven video capture cases | All seven and their dependent claims are machine-blocked | Verified timestamped ingestion is still required |
| Sibling GPT pack and images | All 16 bytes preserved, validated, registered separately, and overlap-adjudicated; ADR-005 binds governance semantics as well as raw inventory | License/authorship and `imgo.jpg` chain of custody remain unresolved |
| Docket and stale documentation | Additively reconciled from 22/80 to 23/84; historical counts retained as history | Future sources/claims must remain additive |
| Dangling/executable receipts | Completed by ADR-003 | Provider authentication and durable retention remain later stages |
| Byte-hashed GPT manifest and formal runtime schema | ADR-005 binds clean-checkout bytes, full manifest semantics, canonical action digests, strict paths/times/numbers, and cross-record truth tests | External enforcement and signed identities remain later stages |
| Implementation-state audit | Schema 5 distinguishes structural prototype, simulation, partial in-process enforcement, and empty production proof | E2E and production maturity require future receipts |
| Protected governance and CI | CODEOWNERS, desired rules, pinned CI, scans, SBOM, and attestations declared and tested | Active remote rules and independent approvals are not yet verified |

## Current exit posture

- No broken local code/test/artifact reference may support a receipt.
- Incomplete ingestion/provenance/digest/pin evidence produces machine-blocked dependent claims.
- Mutable or ambiguous repository pins cannot support an adopted implementation claim through
  the audit gate.
- Unknown licenses and composite repository source kinds machine-block their dependent claims.
- Schema-6 verification derives blockers from source metadata and conserves source identities,
  claim/maturity partitions, blockers, release readiness, and production evidence against a
  separately reconstructed Git/docket context instead of trusting a self-digested report.
- Stage 0 is not called fully complete while remote governance, source evidence, licenses, or
  genuinely independent final verification remain unresolved.

## Exit posture (ADR-006)

Stage 0 is closed in its fail-closed form by
[ADR-006](ADR-006-STAGE-0-EXIT.md): incomplete evidence and dependent claims remain
machine-blocked, and further verifier hardening requires a reproduced fail-open
counterexample. The active obligation census, owners, review dates, phase routing, and exit
conditions are maintained in [the blocker backlog](../plan/BLOCKERS.md).

This closure is not release readiness or blocker-free status. The current audit still reports
`release_ready=false`, no evidence above structural prototype maturity, and unresolved
source, licensing, host-governance, identity, durable-operation, independent-verification,
and production obligations. Implementation sequencing is owned by
`docs/plan/00_OVERVIEW.md`; the earlier sequencing sections remain preserved as originally
recorded.
