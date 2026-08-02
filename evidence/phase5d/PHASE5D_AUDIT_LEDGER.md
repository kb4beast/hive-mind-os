# Phase 5D Audit Ledger

Append-only record for the inert Curator deep-playbook candidate.

## Entry 1 — intake and branch boundary

- Base: `92a7f6ed96186a2a1c8fd1fd55147663f25588d9`.
- Branch: `agent/phase5d-curator-shadow`.
- Integration target: `agent/phase5a-orchestrator-shadow` through a stacked draft PR.
- `main` and `release/version_1.1` modification: prohibited.
- Squash, rebase, and source-branch deletion: prohibited.
- Candidate authority: none; activation: inert; capabilities/tools: zero.
- Authenticated distinct actors: false.
- Same assistant performed procedural passes: true.
- Independence claimed: false.

## Entry 2 — implementation inventory

- Contracts: 14.
- Typed outputs: 11.
- Candidate: `hive-agent:curator:v2-shadow-1` /
  `hive-agent-definition:curator:v2-shadow-1`.
- Reviewed successor digest:
  `sha256:3ca6aa8d1f32b1377490c0a87afd4aee248641fe95231705cb4963ef2e7eaa7c`.
- Dependencies, package JSON resources, root API, CLI, runtime/provider/tool/store/scheduler
  bindings added: zero.

## Entry 3 — local executable evidence

- Command: `PYTHONPATH=src:. python -m unittest discover -s tests -p 'test_phase5d_curator_playbook.py' -v`.
- Result: 41 focused tests passed.
- Systematic semantic-reseal attack: 747 scalar leaves across all eleven outputs rejected.
- Installed-source-root verifier: passed with fourteen schemas, eleven outputs, inert activation,
  zero capabilities/tools, and recommendation `defer`.
- Hosted exact-head Python, Ruff, Pyright, CodeQL, secret, dependency/license, wheel, SBOM,
  artifact, and provenance results remain pending at this entry.

## Entry 4 — unresolved evidence

- Authenticated independent Curator/Judge receipts: unavailable.
- Real clean-boundary execution receipts: unavailable and outside the inert playbook.
- External SAST and privacy proof: not established.
- `B-OPS-09`, P14–P20, applicable source/license appeals, and exact Armory semantics: open.
- Customer value, behavior quality, learning, promotion, activation, production readiness,
  release readiness, and superiority: not established.

## Entry 5 — hosted materialization checkpoint

- The candidate was materialized on the exact stacked branch through a self-removing workflow.
- Phase 5D focused suite: 41 tests passed before publication.
- Phase 5A–5C current-tree inventories were regenerated in dependency order.
- CI and ADR registry changes were included before the final Phase 5D inventory seal.
- Temporary materialization automation is deleted from the published candidate tree.
- Exact-head Constitutional CI remains required before the candidate can be called green.

## Entry 6 — release-stack stabilization candidate

- Successor base: `ca44bce4f118f62cd012693cd854b67bedef8846` (Phase 5K head).
- P5D-DEBT-01 repair: Curator and Phase 5D test imports are formatted, and the unused
  `builtin_instruction` local is removed without removing its packaged-resource digest check.
- P5D-DEBT-02 repair: Builder-envelope normalization now copies a `Mapping` into a concrete
  mutable dictionary before replacing the normalized outputs field; defensive-copy behavior and
  exact-container validation remain covered by the focused suite.
- P5D-DEBT-04 repair: the obsolete, branch-specific, `contents: write` Phase 5D materialization,
  publication-remand, and cleanup workflows are removed. Their committed evidence and historical
  GitHub run receipts remain retained.
- Local evidence: Ruff `0.16.0` passed `src`, `tests`, and `scripts`; Pyright `1.1.411` completed
  with zero errors; the Phase 5D focused suite passed 42 tests; the Phase 5K focused suite passed
  12 tests; and the previously intermittent worker recovery test passed 40 consecutive local
  repetitions.
- The full local unittest discovery run exceeded the practical validation window and was stopped
  without a result. It is not a passing receipt. Exact-head Constitutional CI remains the required
  full-suite, cross-version, build, security, and provenance verdict.
- This entry does not resolve P5D-DEBT-03, authenticated independence, external adoption evidence,
  release readiness, production readiness, deployment authority, or any P5E–P5K completeness debt.

## Entry 7 — worker recovery timing root cause and repair candidate

- Historical hosted failures: Constitutional CI runs `30679862330` (Python 3.12) and
  `30681039055` (Python 3.11) both reached the final assertion in
  `test_seeded_process_kill_sweep_reclaims_without_duplicate_effects` with at least one queue job
  still not `done`. The logs did not identify which claim/reclaim transition was skipped.
- Root cause: the test used a fixed `time.monotonic()` sleep to predict expiry of leases whose
  durable eligibility is evaluated by `Scheduler.clock.now()` (`time.time()` for the system
  scheduler). A wall-clock correction can therefore leave the lease unexpired after the fixed
  sleep. The test also accepted a crash-worker marker containing `none` and ignored the Boolean
  result of the recovery worker, allowing a missed claim to surface only as the final ambiguous
  queue-state failure.
- Repair: wait until the claimed lease is observed expired through the scheduler clock, require a
  nonempty and non-`none` crash claim, require the recovery worker to claim work, verify the exact
  claimed job reaches `done`, and fail each iteration if any prior lease remains. Duplicate-effect,
  final-state, and cleared-lease assertions remain unchanged.
- Runtime scheduler semantics, lease duration, retry limits, and authority are unchanged. The test
  now checks the durable state boundary directly instead of inferring it from another clock.
- Local evidence on CPython 3.14: the repaired process-kill test passed 100 consecutive runs in
  123.718 seconds; the complete three-test worker module passed; Ruff 0.16.0 passed the changed
  file; and Pyright 1.1.411 completed with zero findings.
- `P5D-DEBT-03` remains open at this entry until the exact candidate head passes repeated hosted
  Python 3.11, 3.12, and 3.14 runs. No authenticated-independence, adoption, release-readiness,
  production-readiness, deployment, promotion, or superiority claim is created.
