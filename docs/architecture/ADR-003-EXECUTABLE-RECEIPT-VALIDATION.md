# ADR-003: Executable Receipt Validation and Policy Invariants

- **Status:** Accepted for Stage 0; promotion evidence pending
- **Date:** 2026-07-27
- **Originating work order:** `docs/architecture/MASTER_IMPLEMENTATION_PROMPT.md`,
  Stage 0 and first implementation backlog item 2
- **Source claims:** `CLM-026`, `CLM-074`, `CLM-077`, `CLM-079`
- **Capability maturity:** structurally prototyped

## Court record

**Case:** `CASE-IMPL-002-RECEIPT-VALIDATION`

**Question:** What is the smallest change that prevents nonexistent references, arbitrary
receipt labels, fabricated test output, and authority/type confusion from satisfying an
implementation or completion gate?

**Advocate:** `architect-advocate-receipts-pass-1` argued for a provider-neutral,
content-addressed receipt reference resolved under an injected trusted root. The verifier
binds exact bytes to mission state and the exact action without introducing the formal
cross-system schemas or single enforcement gateway assigned to later backlog items.

**Cross-Examiner:** `cross-examiner-receipts-pass-1` reproduced acceptance of blank and
fabricated receipt strings, out-of-repository docket paths, free-form `999 passed` output,
dirty-worktree completion, low-risk spending and secret access at full autonomy, malformed
role/risk bypasses, and blank charter binding.

**Expert testimony:**

- `explorer-clerk-receipts-pass-1`: the work order conjunctively requires path, digest,
  execution, and result validation; a nonempty tuple or label is not a receipt.
- `security-receipts-pass-1`: receipt bytes must be resolved beneath a trusted root, hashed
  before parsing, bound to one action/state/actor/policy/lease, and rejected on replay or
  foreign binding.
- `sre-receipts-pass-1`: each cited test file needs an exact runner observation and successful
  result; dirty working bytes cannot be attributed to `HEAD`.
- `product-receipts-pass-1`: reducing false completion is necessary infrastructure, but it
  is not yet customer-outcome or production-enforcement evidence.

**Judge:** pending a disjoint post-implementation evidence review.

**Independence disclosure:** Explorer, Architect/Advocate, and Cross-Examiner were separately
identified read-only agents. Builder changes remain unpromoted until a disjoint Curator and
Judge reproduce the committed implementation. Source-ingestion blockers remain independent
of this decision.

**Verdict:** `adapt`

Adopt exact local validation and adapt it to an injected file-backed verifier. Do not claim
authenticated provider receipts, a universal receipt schema, immutable evidence storage, or
a non-bypassable enforcement gateway in this slice.

## Considered alternatives

1. **Keep accepting provider-style strings:** rejected because syntax or truthiness cannot
   prove existence, execution, binding, or result.
2. **Check only that a path exists:** rejected because substitution, traversal, failed
   execution, and replay remain undetected.
3. **Make the source docket embed every mutable repository digest:** rejected for this slice
   because code/test edits would require a manually synchronized second source of truth.
   The audit instead records exact observed digests and explicit executions against a clean
   commit.
4. **Implement formal schemas and the single enforcement gateway now:** deferred to backlog
   items 3 and 6 to keep this change dependency-ordered.
5. **Treat a failed receipt as no evidence:** adapted. A well-bound failed receipt proves an
   attempted execution, but it can never satisfy successful completion.

## Decision

Add `FileReceiptValidator` and `ReceiptReference`:

- references use repository-independent relative paths and strict lowercase SHA-256 digests;
- receipt and artifact paths must resolve to regular files beneath an explicitly trusted root;
- the verifier reads and hashes exact bytes before accepting their JSON claims;
- version, provider, execution, policy, lease, timestamp, result, artifact, and verifier
  fields are mandatory;
- mission, state, actor, action ID, action kind, and canonical action digest must match;
- acting and verifying identities must differ;
- missing, malformed, foreign, substituted, unknown-result, or unexecuted receipts fail;
- the simulation gate rejects legacy strings and reuse across actions;
- completion requires a successfully executed receipt for every side effect.

Harden the current-state audit:

- local architecture/code/test/benchmark references must remain beneath the repository and
  have observed SHA-256 digests;
- every unique cited test file runs through the exact Python/pytest runner and retains its
  command, output, return code, and parsed result;
- arbitrary commands or free-form success text are unverified;
- a dirty worktree makes the audit incomplete because its test bytes are not attributable to
  the recorded `HEAD`;
- integrity verification rejects underspecified payloads while continuing to distinguish
  digest integrity from external authenticity.

Harden policy invariants:

- all action enum values have an explicit authority mapping;
- non-delegable actions remain denied across every role, risk, and autonomy level;
- merge, deploy, money, and secret actions remain denied until a real external-grant model
  exists;
- malformed autonomy, role, action, and risk inputs fail closed;
- Explorer remains read-only;
- blank or mismatched charter binding quarantines an otherwise high-value outcome.

## Invariants

1. A reference label is never execution evidence.
2. Receipt validation is conjunctive: path, digest, structure, binding, execution, artifacts,
   and result all matter.
3. One receipt proves at most one exact action in one mission-state version.
4. Validation observes evidence; it does not execute or repeat the side effect.
5. A failure receipt may prove an attempt but never successful completion.
6. Capability and higher autonomy never expand constitutional authority.
7. Test results bind only to clean repository inputs and recognized runner observations.
8. Unknown versions, values, paths, and runtime identities fail closed.

## Threats and controls

| Threat | Control |
|---|---|
| Fabricated or whitespace receipt label | Reject strings; require a typed content-addressed reference |
| Receipt or artifact substitution | Recompute SHA-256 over exact bytes |
| Absolute path, traversal, or symlink escape | Resolve and require containment under the trusted root/repository |
| Foreign or replayed receipt | Bind mission, state, actor, action fields, action digest, and receipt uniqueness |
| Self-verification | Require receipt verifier identity to differ from action actor |
| Unexecuted or failed work called complete | Require `executed=true`; completion additionally requires `result=succeeded` |
| Fabricated test summary | Accept only the exact Python/pytest command and observed successful return/result |
| Dirty implementation attributed to a commit | Mark a dirty-worktree audit incomplete |
| New policy action silently bypasses checks | Exhaustively assert `set(ACTION_LEVEL) == set(Action)` |
| String/int role or risk bypass | Runtime type checks produce explicit denial |
| Full autonomy grants A4/A5 effects | Deny grant-required effects until a separate verified grant model exists |
| Local JSON mistaken for provider authenticity | Keep maturity at structural prototype and preserve the authenticity obligation |

## Acceptance tests

- A correctly bound, digested success receipt passes.
- Missing, malformed, out-of-root, substituted, foreign, self-verified, unexecuted, unknown,
  or reused receipts fail.
- A valid failed receipt cannot support a complete mission.
- Legacy `receipt_ref="provider:anything"` is rejected.
- All docket-local references resolve and carry observed digests.
- Each cited test file has an explicit passing execution receipt when tests are enabled.
- A made-up command printing `999 passed` is unverified.
- A dirty worktree cannot produce a complete audit.
- Policy matrices cover every action, role, risk, and autonomy level, including A4/A5
  defaults and malformed runtime inputs.
- Blank charter binding quarantines.
- The legacy objective CLI and audit CLI remain compatible apart from intentional rejection
  of insecure receipt-string callers.

## Migration and compatibility

`SimulatedAction.receipt_ref` intentionally changes from `str | None` to
`ReceiptReference | None`, and the action now carries its actor identity. Callers must persist
a receipt JSON artifact and referenced artifact bytes under their configured trusted root,
then supply their SHA-256 digest. Reasoning-only and read-only actions are unchanged.

The audit artifact remains schema version 1 because this is stricter validation and additive
fields rather than the formal schema set scheduled for backlog item 3. Consumers that assumed
any schema-1 mapping was a valid `CurrentStateAudit` must migrate to the stricter verifier.

There is no persistent database migration.

## Rollback

Revert the verifier wiring, policy hardening, and tests only through an additive superseding
ADR. Preserve emitted receipt/audit artifacts and this adverse evidence. Do not restore
arbitrary strings or non-existent paths as accepted receipts. Existing receipt JSON is
read-only evidence and requires no destructive rollback.

## Metrics and ownership

- fabricated-receipt acceptance rate (target zero);
- foreign/replayed receipt acceptance rate (target zero);
- broken-reference acceptance rate (target zero);
- cited-test execution coverage;
- false-complete audit rate (target zero);
- policy-invariant bypass rate (target zero);
- receipt verification latency and failure reasons.

The Integrator owns reference and compatibility behavior. The Steward owns deterministic
verification and failure visibility. The Curator owns disjoint reproduction. The Optimizer
may propose measurement changes but cannot promote its own verifier.

## Open obligations

- `SRC-005`, `SRC-006`, and `SRC-016`–`SRC-020` remain incomplete source blockers.
- `SRC-022` has a label-like content digest rather than a preserved raw-byte digest.
- Local receipt files do not prove provider authenticity or append-only retention.
- Formal schemas, signed identities, provider reconciliation, the non-bypassable enforcement
  gateway, and durable hash-chained evidence remain later work.
- Promotion requires a disjoint Curator and Judge verdict over the committed implementation.
