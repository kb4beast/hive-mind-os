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
