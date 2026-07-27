# Stage 0 Receipt Validation and Policy Invariants Handoff

## Mission

- **Mission ID:** `MISSION-STAGE0-RECEIPTS-002`
- **Case:** `CASE-IMPL-002-RECEIPT-VALIDATION`
- **Branch:** `codex/master-implementation-bootstrap`
- **Judged implementation commit:** `e105ea49164953e97f69634dd3e03c1e71a51fea`
- **Objective:** complete `MASTER_IMPLEMENTATION_PROMPT.md` Stage 0 backlog item 2 by
  replacing nonexistent receipt-string acceptance with executable path, digest, binding,
  execution, artifact, verifier, and result validation, and add the missing policy invariant
  tests.
- **Authority/risk:** A2, reversible local code, documentation, tests, commits, and evidence.
  No push, pull request, merge, deployment, external communication, credential, secret,
  financial, destructive, or policy-expanding action was performed or inferred.
- **Resource disclosure:** no numeric compute/token lease, expiry, or detailed cost ledger was
  persisted. Local tests and audit processes were bounded by command time/output controls.
- **Stop condition:** persist the final court record and audit, validate the evidence-only
  handoff commit, then stop this mission.

## Court disposition

- **Originating claims:** `CLM-026`, `CLM-074`, `CLM-077`, and `CLM-079`.
- **ADR:** `docs/architecture/ADR-003-EXECUTABLE-RECEIPT-VALIDATION.md`.
- **Judge identity:** `judge-final-verdict-e105ea4`.
- **Disposition:** `adapt`.
- **Judgment:** Stage 0 backlog item 2 is complete at the exact judged commit. The decision
  adopts local content-addressed validation and policy invariants, while refusing claims of
  authenticated provider receipts, immutable evidence, formal cross-system schemas, signed
  identities, or a non-bypassable enforcement gateway.
- **Scope boundary:** this is not Stage 0 exit, release readiness, production enforcement,
  customer-outcome proof, or a superiority verdict.

## Independent role and lifecycle evidence

| Role / identity | Exact-commit result |
|---|---|
| Explorer/Clerk / `explorer-clerk-receipts-pass-1` | Extracted the conjunctive receipt and policy acceptance obligations |
| Architect/Advocate / `architect-advocate-receipts-pass-1` | Designed the provider-neutral, content-addressed validator and migration |
| Cross-Examiner / `cross-examiner-receipts-pass-1` | Reproduced arbitrary strings, broken references, policy bypasses, and false completion |
| Builder / primary implementation agent | Implemented and appealed the bounded change on the named branch |
| Curator / `/root/curator_final_verification` | PASS in detached read-only worktree on Python 3.14 and fresh Python 3.12 |
| Integrator / `/root/integrator_review` | PASS for schema, CLI, provider, path, docket, and migration compatibility |
| Steward / `/root/steward_review` | PASS for process containment, bounded evidence, failure visibility, and recovery behavior |
| Optimizer / `/root/optimizer_final_review` | PASS for scoped metrics; rejected customer, production, and superiority extrapolation |
| Orchestrator / `/root/orchestrator_final_review` | PASS for dependency order, A2 authority, scope, and stopping condition |
| Judge / `judge-final-verdict-e105ea4` | `adapt` at exact commit `e105ea4` |

Discover, design, build, validate, integrate, maintain, grow/measure, and orchestration stages
are represented. Acting, verifying, integrating, optimizing, orchestrating, and judging
identities were separated.

## Delivered contract

- `ReceiptReference` uses strict portable relative paths and lowercase SHA-256 digests.
- `FileReceiptValidator` hashes exact receipt and artifact bytes, requires schema/provider/
  execution/policy/lease/timestamp/result/verifier fields, and binds the exact mission,
  state, actor, action ID, action kind, and canonical action digest.
- Legacy receipt strings, missing validators, foreign/replayed/reused receipts, duplicate
  action IDs, self-verification, unexecuted work, failed completion receipts, malformed
  types, and nonportable or escaping paths fail closed.
- The classic-GPT simulation contract migrated to version 2 with typed receipt examples.
- Policy tests exhaustively cover every action mapping, autonomy level, role, and risk tier;
  Explorer effects, non-delegable effects, and grant-required merge/deploy/money/secret
  effects remain denied. Blank or mismatched charter bindings quarantine.
- CurrentStateAudit migrated through preserved historical fixtures to schema 4. It binds
  clean initial/post-test/final state, executes each unique cited test file, rejects
  fabricated or contradictory pytest results, bounds process trees and JSON-escaped output,
  validates every serialized artifact path, and fails closed on malformed envelopes.

## Preserved appeal and adverse evidence

No passing suite overrode a reproduced counterexample. The appeal chain is:

| Commit | Preserved adverse finding closed by a later appeal |
|---|---|
| `f335b19` | duplicate receipt masking, permissive schema/runtime types, dirty-input attribution, portable-contract drift |
| `742eb60` | immediate dirty state and overall test-result observation gaps |
| `6c0661f` | deep receipt contradiction, nonportable paths, schema/example drift, separate output caps, descendant pipes |
| `83f83fc` | successful parent could leave a pipe-retaining Windows descendant; failed pytest summaries could appear passing |
| `6974fdb` | unversioned command-shape change and JSON escape expansion outside the stated byte budget |
| `14aad93` | self-digested oversized command observations bypassed deep verification |
| `630a91d` | lone Unicode surrogates could raise instead of rejecting |
| `cf907a1` | noncanonical and cyclic envelope values were not comprehensively guarded |
| `561b96a` | malformed top-level/deep values and full-envelope extension fields exposed fail-closed gaps |
| `25b1920` | correctly digested excessive nesting was accepted; the first test rejected only through a bad digest |
| `e97ff25` | a shared container could bypass depth checks when first visited on a shallower path |
| `e105ea4` | every deeper serialized occurrence is now evaluated; final independent reviews passed |

Remaining operational dissent is not hidden: Windows containment uses private
`Popen._handle`/`NtResumeProcess`; raw pytest timing prevents bit-identical audit payloads;
the audit runs nine pytest processes; artifact traversal has no total node/width limit;
parent-directory fsync/power-loss durability is unproven; and direct file-symlink creation was
privilege-skipped on Windows. The Curator separately reproduced directory-junction escape
rejection.

## Durable audit receipt

- **Artifact:** `evidence/audits/current-state-audit-e105ea4.json`
- **Digest:** `sha256:c8db3cde16d909f9ba8f8a606e5200d12bd7d666a57259cccd4f0d5c2623a715`
- **Verifier:** `(True, ())`
- **Schema/type:** `4 / CurrentStateAudit`
- **Judged HEAD:** `e105ea49164953e97f69634dd3e03c1e71a51fea`
- **Repository observations:** initial, post-test, and final HEADs matched; all three worktree
  observations were clean.
- **Tests:** 104 passed, 0 failed, 0 errors.
- **Reference receipts:** 209/209 valid; zero broken references.
- **Commands:** 26 successful observations; no timeout, truncation, or incomplete drain.
- **Audit failures:** none.
- **Release boundary:** `docket.release_ready=false`.

Independent reproduction:

- Curator Python 3.14: 104 passed, 1 skipped, 1,690 policy subtests.
- Curator fresh Python 3.12: 104 passed, 1 skipped, 1,690 policy subtests.
- The skip is direct Windows symlink creation denied by privilege error 1314; an
  unprivileged directory-junction escape was independently rejected.
- Optimizer measurement: the durable audit is approximately 125 KB and ran in roughly
  10 seconds. One warm Windows sample of 10,000 successful local receipt validations averaged
  467.47 microseconds; this is not a distribution or performance guarantee.

## Compatibility, migration, and rollback

- `SimulatedAction` is keyword-only and uses a typed `ReceiptReference`; insecure string
  callers must migrate by persisting and hashing a receipt artifact.
- The classic-GPT protocol/state example is version 2.
- Current audit schema is version 4. Version-2 and version-3 fixtures are retained as
  historical evidence and intentionally rejected as current receipts.
- The legacy objective CLI and the audit CLI remain operational.
- There is no persistent database migration.
- Rollback requires additive supersession or an explicit revert of the verifier wiring,
  policy hardening, and tests while preserving this handoff, ADR, emitted artifacts, adverse
  results, and historical fixtures. Arbitrary receipt strings must not be restored as valid
  evidence. No mechanical rollback drill was performed.

## Blocking obligations

- `SRC-005`, `SRC-006`, and `SRC-016`–`SRC-020` remain incomplete.
- `SRC-022` still lacks a preserved raw-byte digest.
- The classic-GPT fingerprint does not hash the actual source-pack inventory; strict
  addition/removal/substitution/order enforcement and sibling-pack governance remain open.
- Local files do not prove provider authenticity or append-only retention.
- Formal schemas, signed identities, provider reconciliation, a non-bypassable enforcement
  gateway, and durable hash-chained evidence remain future work.
- No pinned multi-comparator or held-out evaluation supports a superiority claim.

## Eligible next transition

Stop this mission after committing and validating this evidence-only handoff. The next
dependency-ordered slice is Stage 0 backlog item 3: formal JSON Schemas and canonical
cross-system contracts. Backlog item 4's source-pack byte inventory remains independently
blocking and must not be represented as completed.
