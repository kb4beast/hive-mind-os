# Phase 2 audit ledger

This ledger is append-only. Later corrections add entries and do not rewrite adverse
evidence.

## `P2-AUDIT-001` — base and stack

- Exact base: `3298078c41ce69103eb2bdce61960a69dc6aab93`
- Base PR: #29, draft
- Phase 2 branch: `codex/phase2-additive-memory-telemetry-foundation`
- Merge/activation: prohibited

## `P2-AUDIT-002` — independent reconstruction

- Explorer `Wegener` reconstructed the Phase 2 obligations read-only.
- Architect/Cross-Examiner `Gibbs` independently selected one additive private store
  and rejected mutation of Generation Zero stores.
- Both required separate schema/resource receipts, explicit identity, encounter-first
  deduplication, unknown accounting, transactional outbox, and no Phase 3 activation.

## `P2-AUDIT-003` — implementation boundary

- Added internal `hive_mind_os.foundation`; no root/package facade or CLI export.
- Added 17 separately catalogued schemas and 9 deterministic inert artifacts.
- Added one opt-in store and provider wrapper.
- Did not change `EvidenceLedger`, `MissionStore`, scheduler, `ModelResponse`,
  `model.call`, roles, prompts, hive-core, CLI, or default runtime selection.

## `P2-AUDIT-004` — initial test

- Command: Python 3.14 unittest discovery.
- Result: 444 tests, 1 failure, 3 skips, 882.706 seconds.
- Failure: the Phase 1 live-source inventory compared the historical whole-source
  artifact to an additive Phase 2 source tree.
- Disposition: expected versioned-inventory conflict, not a runtime regression.
  The Phase 1 artifact and digest remain frozen. The test now checks frozen facades
  and safety/effect invariants while a separate Phase 2 inventory measures additive
  definitions/resources. Historical bytes were not regenerated.
- ResourceWarnings pre-existed in legacy tests and were not hidden or converted to
  success.

## `P2-AUDIT-005` — isolated foundation tests

- Initial result: 13 tests passed.
- After opt-in provider, integrity, accounting-conflict, and additive-inventory
  coverage: 16 tests passed.
- Covered strict schemas, deterministic drift, authority intersection, WAL/outbox,
  append-only mutation denial, idempotency conflict, tenant scope, privacy rejection,
  restart, concurrent exact duplicate convergence, semantic non-merge, provider
  fixtures, unknown accounting, attempt recovery, invoice residuals, bounded metrics,
  local OpenTelemetry envelope, and disabled export.

## `P2-AUDIT-006` — configured type gate

- First Pyright 1.1.411 run found two new narrowing errors in numeric schema minimum
  validation and direction-total reconciliation.
- The implementation was narrowed explicitly without ignores or configuration
  weakening.
- Re-run: 0 errors, 0 warnings, 0 information.

## Open entries

- Complete full multi-Python and security/supply-chain matrix.
- Independent Curator/Steward reconstruction.
- Independent Judge exact-candidate disposition.
- Exact commit, remote head, draft PR, and GitHub check receipts.

## `P2-AUDIT-007` — initial remote candidate and CI

- Initial candidate: `1754f568900a0e19517c0586c0406fe4164d8597`.
- Draft PR: #31, stacked on PR #29 head
  `3298078c41ce69103eb2bdce61960a69dc6aab93`.
- Push run `30423896704`: Python 3.11/3.12/3.14, Ruff/Pyright, CodeQL,
  secret scan, SBOM/build, installed-wheel/resource verification, and push
  provenance passed.
- PR run `30423909689`: CodeQL, dependency review, secret scan, static/type,
  SBOM/build, and Python 3.11/3.12 passed when first observed; this receipt is
  evidence for the remanded candidate only and is not a promotion receipt.

## `P2-AUDIT-008` — independent remand

- Curator `Kuhn` and Steward `Planck` independently reconstructed exact candidate
  `1754f568900a0e19517c0586c0406fe4164d8597`.
- Both issued `remand`. Material findings: advisory-only authority, unsafe database
  admission, cross-scope self-relation bypass, attempt-ID collision, wrapper retry
  bypass, unbounded/private observability, unbounded provider-native paths,
  incomplete canonical field families, generic schema/type bypass, payload-only
  idempotency, no separate canonical agent source, destination-unbound outbox
  receipts, incomplete integrity checks, and weakened Generation Zero inventory
  characterization.
- No finding was suppressed or reclassified as passing.

## `P2-AUDIT-009` — remand remediation

- Store entry points now enforce allowed decisions, record-type/action boundaries,
  payload scope, and explicit safe-public release authority.
- Store admission refuses every non-empty unversioned database and validates an
  ownership marker plus exact schema-object digest. Integrity verification covers
  canonical JSON, schema/type binding, commands, relations, repository identity,
  outbox projections, destinations, and successful-attempt prerequisites.
- Idempotency binds the full semantic write command. Relations bind canonical
  evidence. Delivery rejects wrong destinations, empty receipts, acknowledgement
  before success, and conflicting receipts.
- Physical attempt IDs are unique across wrappers/restarts; opt-in completion now
  preserves configured transport retries and receipts each physical attempt.
- Provider-native capture is path-allowlisted and bounded. Metric names, labels,
  values, and trace privacy/reserved keys fail closed.
- Canonical memory, usage, and agent contracts now carry the Phase 1 field families.
  Eight separately versioned canonical agent sources compile to the nine inert
  generated resources.
- The Phase 1 inventory builder excludes the additive foundation by default and its
  characterization again requires exact whole-receipt equality and exactly 304
  frozen definitions.
- Adversarial foundation suite: 22 tests passed. Exact Generation Zero
  characterization: 4 tests passed. Ruff passed. Pyright 1.1.411: 0 errors,
  0 warnings, 0 information.
- Two full-suite processes begun while the remand was being edited later completed
  against mixed, pre-remediation source states (Python 3.14: 446 tests; Python 3.12:
  446 tests). They failed on transient missing canonical fields and are explicitly
  stale/non-candidate evidence, not final-matrix receipts.

## Open entries after remand

- Commit the remediated exact candidate and obtain fresh independent Curator and
  Steward reconstruction.
- Obtain a different Judge disposition on the accepted exact candidate.
- Run the complete exact-head local/remote matrix and record final PR/head receipts.

## `P2-AUDIT-010` — second independent remand

- Exact reviewed candidate:
  `b881f75dbc4a23062511fed8c90a2e107ddda8f8`.
- Curator `Kuhn` and Steward `Planck` independently returned `remand` despite 26
  focused/Generation Zero tests, Ruff, Pyright, deterministic generation, exact
  131/33/13/304 compatibility, and a fully green push run `30425316778` plus PR
  run `30425319854`.
- Curator blockers: incomplete canonical memory kinds; unscoped outbox reads and
  delivery; unenforced agent content digests; missing generator version on agent
  projections; unconstrained nested agent contracts; missing committed per-axis
  double-count/conflict evidence.
- Steward blockers: uncaught oversized JSON integers; unbounded provider IDs and
  traces; top-level accounting not propagating axis conflicts; nonrecoverable
  interrupted initialization; untyped/unstaged semantic classification; explicit
  observed time absent from idempotency; non-attributable/unscoped public release;
  incomplete opportunity-key integrity.
- The green CI receipts remain valid evidence for the remanded SHA only. They do not
  override either independent remand.

## `P2-AUDIT-011` — second-remand remediation

- Memory records cover working, episodic, semantic, procedural, prospective,
  decision, opportunity, counterfactual, social, evaluation, resource, governance,
  and not-applicable classes, plus a strict nullable retrieval receipt for selected,
  omitted, ordering, purpose, policy, and critical-context coverage.
- Every authority decision is scoped to tenant/repository/actor and carries decision
  and lease identity. Safe-public additionally requires an independent decider and
  decision bound to the exact subject digest; all provenance is stored.
- Explicit observed time joins full-command idempotency. Outbox reads, attempts, and
  acknowledgements require tenant/repository scope and store actor/decision/lease
  provenance.
- Initial schema creation, triggers, ownership marker, schema digest, and user version
  now commit or roll back together. An injected interruption leaves no user table and
  reinitializes successfully.
- Opportunity semantic candidates must be typed opportunity records; classification
  requires the staged relation. Integrity binds opportunity keys to scoped type and
  normalization/exact/structured payload digests.
- Canonical agent self-digests are checked before generation. Generated agents carry
  generator version. Memory, usage, portability, and governance nested agent
  contracts are strict and complete.
- Provider parsing converts oversized integer JSON to explicit unknown, bounds
  provider identities, preserves strict native paths/provenance, and propagates
  direction/cache/reasoning conflicts. Traces and OpenTelemetry provider/outcome
  vocabulary are bounded.
- Per-axis reconciliation compares like dimensions only and returns the explicit
  `orthogonal-axes-never-summed` guard. Direction, cache, reasoning, and deliberate
  cross-axis regressions are committed.
- Focused Phase 2: 28 tests passed. Phase 2 plus exact Generation Zero: 32 tests
  passed. Ruff passed. Pyright 1.1.411: 0 errors, 0 warnings, 0 information.

## Open entries after second remand

- Commit and independently reconstruct the new exact candidate through Curator and
  Steward.
- Obtain a separate Judge verdict only after both accept.
- Repeat the exact-head full Python/security/supply-chain/wheel/provenance matrix and
  update the PR/evidence-only checkpoint.
