# Phase 5D Curator Contract

## Scope

Phase 5D adds one package-private, opt-in, inert Curator candidate. It compiles a strict
verification request into eleven separately digest-bound outputs and one final envelope. It
does not execute checks, create receipts, approve a release, or replace the active P08 Curator.

## Input contract

`curator-verification-request-v1` requires:

- a valid Phase 5C Builder envelope and independent-reconstruction handoff;
- exact repository, tenant, base, subject commit, and subject tree bindings;
- distinct Builder and Curator procedural identities;
- blind checks sealed before candidate access;
- complete acceptance, claim, check, evidence, source, regression, rollback, and point-in-time
  records;
- digest-verified, fresh evidence with exact subject and required receipt fields;
- complete admitted sources for every material claim;
- no test weakening, future-commit references, or caller-supplied success claims;
- wholly known or wholly unknown resource ceilings and reserves; and
- the complete procedural role catalog with no manufactured authentication.

Only exact built-in JSON containers are admitted. Unknown fields, private content, duplicate
identifiers, non-finite values, hostile subclasses, ambiguous references, and semantic repeat
fingerprints fail closed.

## Output contracts

| Output | Required meaning |
| --- | --- |
| `verification_scope` | Exact request, Builder, repository/tenant, subject, blind-seal, authority, evidence, rollback, and clean-boundary scope. |
| `claim_reconstruction` | Every material claim reconstructed from acceptance, evidence, and source references; no self-verification. |
| `clean_boundary_reproduction` | Sealed checks and fresh-workspace requirements without claiming that the playbook executed them. |
| `counterexample_search` | Versioned hostile attacks covering false-green, identity, receipt, freshness, leakage, weakening, source, and substitution risks. |
| `security_privacy_review` | Explicit findings and honest `not-evaluated` status where external scanners or privacy proofs are unavailable. |
| `provenance_license_review` | Complete source disposition and visible license/provenance gaps. |
| `regression_analysis` | Assertion/test-function preservation and exact regression targets. |
| `artifact_receipt_verification` | Digest and receipt-field reconstruction without artifact-creation or verification authority. |
| `rollback_verification` | Required rollback references and tests without execution or rollback authority. |
| `release_recommendation` | Structural status plus a bounded recommendation; procedural unauthenticated review cannot exceed `defer`. |
| `dissent_unresolved_evidence` | Append-only dissent, blockers, required evidence, and the rule that missing evidence is not permission. |

Every output binds request and Builder digests, identities, repository/tenant, base/subject,
authority state, budget state, complete claim/acceptance/evidence/rollback sets, its own digest,
and the final verification digest.

## Authority contract

The successor and every relevant output fix:

- `authority: none`
- `activation: inert`
- effective capabilities and tools: zero
- implementation, execution, test-result, completion, release, approval, promotion, and
  activation authority: false
- authenticated distinct actors: false
- same assistant procedural passes: true
- independence claimed: false

## Fail-closed cases

Reject or defer false-green Builder evidence, same-identity verification, forged or stale
receipts, missing receipt fields, future knowledge, foreign repository/tenant/subject data,
test weakening, partial or unlicensed sources, unsupported completion/release claims, malformed
containers, duplicate IDs, incoherent references, semantic repeats, and coherently resealed but
noncanonical outputs.
