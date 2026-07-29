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

## `P2-AUDIT-012` — third independent remand

- Exact reviewed candidate:
  `d20ee1a469b716f1a62d8d4a24c338fe66dda066`.
- Push run `30426478133` and PR run `30426479580` both passed on that exact SHA.
  Together they cover Python 3.11/3.12/3.14, Ruff, Pyright, CodeQL, secret scan,
  dependency/license review, SBOM, wheel build/install, packaged resources, and push
  provenance. These are valid receipts for the remanded SHA only.
- Curator `Kuhn` independently returned `remand`: the recorder/provider exposed no
  caller path for required mission/run/step/role/work-item/court/experiment and
  prompt/context/memory-selection attribution, and the declared billable
  reconciliation axis rejected its string-valued status vocabulary.
- Steward `Planck` independently returned `remand`: a valid 4,000-digit token integer
  bypassed the numeric ceiling; direct exported `TraceRecord` construction bypassed
  trace privacy/bounds; and integrity verification missed an opportunity key
  retargeted across repositories while the schema shape remained valid.
- Both independently reconfirmed exact 131 root APIs, 33 package APIs, 13 CLI
  contracts, 304 Generation Zero definitions, correct PR stacking, and closure of
  every earlier remand. No finding was suppressed by the green matrix.

## `P2-AUDIT-013` — third-remand remediation

- Provider normalization now applies the same `10**15` ceiling to every normalized
  integer path; valid JSON below the interpreter digit limit cannot bypass it. The
  strict schema and local validator enforce the same maximum.
- `TraceRecord` validates bounds/privacy on direct construction, and the
  OpenTelemetry boundary independently revalidates the record.
- Opportunity-key integrity compares the joined target's tenant and repository with
  the key scope, not only its type and payload digests.
- `UsageAttribution` provides a bounded caller path for mission/run/step/role/work
  item, idea/case/experiment/span, prompt/context/memory-selection, model/host, and
  access-audit lineage. Normal terminal and restart-recovery receipts preserve it
  from the durable start.
- Billable reconciliation accepts only the fixed `billable`, `non-billable`,
  `unavailable`, and `unknown` vocabulary and reports cross-source conflict.
- Direct regressions cover 4,000- and 5,000-digit integers, direct and forged traces,
  cross-repository opportunity retargeting with restored schema shape, normal and
  recovered attribution, every billable status, and billable conflict.
- Remediated implementation commit:
  `ca40eb59b2d5569e5f3dbcd05a6874cd53b3867a`.
- Focused Phase 2 plus exact Generation Zero: 33 tests passed. Deterministic
  generation verified 9 artifacts. Ruff passed. Pyright 1.1.411: 0 errors, 0
  warnings, 0 information. Inventory regeneration and patch-integrity checks passed.

## Open entries after third remand

- Seal and push the new exact candidate.
- Obtain fresh independent Curator and Steward reconstruction.
- Appoint a different Judge only after both accept.
- Repeat and record the complete exact-head matrix and final PR/checkpoint receipts.

## `P2-AUDIT-014` — fourth independent remand

- Exact reviewed candidate:
  `91fd5cff7e7b1e2d2b3203baaf67a2127e629f95`; source, tests, scripts, and project
  configuration were byte-identical to implementation commit
  `ca40eb59b2d5569e5f3dbcd05a6874cd53b3867a`.
- Curator `Kuhn` returned `remand` after forging a valid frozen
  `UsageAttribution` post-construction: a 100,000-character mission ID, invalid
  prompt digest, and `10**30` selected count were accepted because recorder admission
  did not revalidate and the schema lacked equivalent limits.
- Push run `30427534292` passed. PR run `30427537379` passed every job except Python
  3.12, where unchanged seeded worker recovery test
  `test_seeded_process_kill_sweep_reclaims_without_duplicate_effects` left a
  non-done job. The same exact-SHA Python 3.12 suite passed on the push run, so this
  is preserved as an adverse nondeterministic receipt, not silently relabeled.
- Every requested third-remand path otherwise passed: 33 focused tests, normal and
  recovered attribution, all billable statuses/conflict, adapter/schema numeric
  maxima, all earlier remands, deterministic generation, Ruff, Pyright, exact
  131/33/13/304 compatibility, inventories, ancestry, and stacking.

## `P2-AUDIT-015` — fourth-remand remediation

- `UsageAttribution` validation is a reusable boundary check invoked both after
  construction and again by `UsageRecorder.start_attempt`, so post-construction
  mutation cannot bypass it.
- The local strict validator now enforces JSON Schema `maxLength` as well as
  `maximum`; `usage-event-v1` binds attribution identifiers to 256 characters,
  prompt/context/memory-selection fields to SHA-256 syntax, and selection counts to
  at most `10**9`.
- Direct tests forge the same mutated object and mutate the canonical contract;
  recorder admission and schema validation both fail closed.
- Remediated implementation commit:
  `144e943d6cf830734e40d89d4cee41e4f15de714`.
- Focused Phase 2 plus exact Generation Zero: 33 tests passed. Deterministic
  generation verified 9 artifacts. Ruff passed. Pyright 1.1.411: 0 errors, 0
  warnings, 0 information. Inventory regeneration and patch-integrity checks passed.

## Open entries after fourth remand

- Seal and push a fresh exact candidate.
- Obtain fresh Curator and Steward acceptance.
- Obtain a different Judge disposition only after both accept.
- Require a clean exact-head full matrix; preserve but do not waive the Python 3.12
  adverse receipt from run `30427537379`.

## `P2-AUDIT-016` — fifth independent remand

- Exact reviewed candidate:
  `36535f136cbebc553af7693fb6ae5f5dba75c0f2`; source, tests, scripts, and project
  configuration were byte-identical to implementation commit
  `144e943d6cf830734e40d89d4cee41e4f15de714`.
- Curator `Kuhn` and Steward `Planck` independently returned `remand`: both a
  directly fabricated allowed `AuthorityDecision` and a genuine budget-denied
  decision mutated to allowed were accepted by `FoundationStore` and produced a
  durable repository registration. The store trusted asserted dataclass fields
  without authenticating the role/policy/lease/adapter/risk/budget intersection.
- Both independently confirmed the fourth-remand attribution repair and every
  earlier adversarial path, exact 131/33/13/304 compatibility, inventories,
  deterministic generation, Ruff, Pyright, stacking, rollback, and dissent.
- PR run `30428086796` passed fully. Push run `30428084962` passed all jobs except
  Python 3.14, where the unchanged seeded worker-recovery test produced the same
  adverse state previously seen on Python 3.12. Both failures remain recorded; no
  assertion, API, or frozen Generation Zero source is weakened.

## `P2-AUDIT-017` — fifth-remand remediation

- The issuing authority module now places a process-local HMAC seal over every
  allowed or denied decision field. `FoundationStore._require_authority` verifies
  that seal before reading allowed/action/scope.
- Directly constructed decisions with fabricated seals and genuine denied decisions
  mutated after issuance fail closed before any repository row is inserted.
- The seal is deliberately scoped as in-process tamper evidence. It is not persisted,
  does not claim external identity, and does not replace the durable decision, lease,
  and release references stored with each write.
- Focused Phase 2 plus exact Generation Zero: 34 tests passed. Deterministic
  generation verified 9 artifacts. Ruff passed. Pyright 1.1.411: 0 errors, 0
  warnings, 0 information. Inventory regeneration and patch-integrity checks passed.
- Remediated implementation commit:
  `ace73253cdd61ef870ed4e2caacb2f4d91b1ef57`.

## Open entries after fifth remand

- Seal and push a fresh exact candidate.
- Obtain fresh Curator and Steward acceptance, then an independent Judge disposition.
- Require a completely green exact-head matrix. If the unchanged seeded worker test
  fails, rerun only from the same immutable SHA and retain every adverse receipt; do
  not modify frozen Generation Zero behavior or weaken the test.
