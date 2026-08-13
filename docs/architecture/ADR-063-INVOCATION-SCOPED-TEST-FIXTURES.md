# ADR-063: Invocation-scoped content-addressed test fixtures

- Status: proposed by an independent Judge; implementation remains blocked
- Disposition: `ADAPT`
- Program: `doctor-performance-v1`
- Source evidence: commit `6bc343f079be6f2d5fd6953d92099a8d5de872b1`
- Scope: test fixtures and qualification evidence only

## Context

The unchanged doctor gate launches the complete `.autopilot/tests` discovery command with
an internal 180-second subprocess timeout. The retained baseline evidence reports 381
total executions in 259.640 seconds on Python 3.14.4: 380 passes, the same one conditional
skip, and zero failures or errors. The same doctor command timed out on both Python 3.14.4
and the bundled Python 3.12.13 runtime. The knowledge
projection `BASELINE-000` contract cannot change controller code or weaken its required
doctor gate, so it remains blocked.

Inspection identifies repeated repository construction in `HealingFixture` as a bounded
test-only candidate. That is a hypothesis, not a proven cause or superiority claim. It
must beat the pinned behavior and timing comparator under independent qualification.

## Decision

Adopt a separately governed predecessor program with this exact order:

```text
DP-CONTRACT-000
  +--> DP-TESTS-010 ---+
  +--> DP-BENCH-020 ---+--> DP-FIXTURE-030
                              --> DP-QUALIFY-040
                              --> DP-JUDGE-050
                              --> retry knowledge BASELINE-000 only after ADOPT
```

The fixture candidate may create one content-addressed seed from a pinned, tracked
`.autopilot` snapshot. Before every derivation it must revalidate the seed digest and
repository identity. Each individual test invocation then receives a fresh writable
repository, object database, index, worktree, refs, branches, receipts, and state.

The seed contains only pinned tracked files and their recorded index modes and blob IDs.
It excludes untracked and ignored files, `.autopilot/state`, bytecode, credential-shaped
content, and anything outside the declared snapshot. Mutation fails closed; an explicit
rebuild produces a new validated content address.

## Immutable behavioral contract

The doctor command, its internal 180-second timeout, and unittest discovery do not
change. Frozen and candidate suites must have an identical complete unittest ID set with
SHA-256 `7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4`.
On the cited host the frozen suite has 381 total executions: 380 passes, zero failures,
zero errors, and the same one conditional skip. That skip is
`test_orchestration.IntentOrchestrationTests.test_binding_state_symlink_escape_is_rejected`
and occurs only when directory symlink creation raises `OSError`. Test IDs, discovery
order, test methods, assertion bodies, subtests, behavior constants, and skip decorators
remain identical.

Within `.autopilot/tests/test_healing.py`, the only allowed edits are fixture imports and
`HealingFixture.setUp`/`tearDown`. The only new fixture implementation file is
`.autopilot/tests/fixture_support.py`.

## Isolation and threat model

The test contract must demonstrate source tree, commit, index-mode, and blob identity;
mutation rejection and rebuild; ref, branch, receipt, index, worktree, and concurrent
invocation isolation; and cleanup after success, failure, and interruption. Network use
is forbidden.

Derivations may not use `--shared`, Git alternates, a shared object database, hardlinks,
symlinks, persistent caches, cached verdicts, or prior test results. These shortcuts make
the candidate fast by coupling tests or reusing conclusions, which would invalidate the
comparison.

## Benchmark and promotion burden

Baseline and candidate receipts are retained separately. For each of Python 3.14 and the
bundled Python 3.12 runtime, qualification requires at least six fresh exact doctor
trials, alternating declared cold and warm modes with at least three cold trials. Every
candidate trial must complete below 180 seconds and nearest-rank p95 must be at most 135
seconds. Receipts bind source, tree, commit, index, runtime, platform, command, order,
timings, and output digests without retaining potentially secret environment values.

The independent qualification Curator must differ from the test Curator and Builder.
A separate Integrator validates the candidate. A Judge distinct from all affected roles
may issue `ADOPT`, `ADAPT`, `DEFER`, `REJECT`, or `QUARANTINE`. Only `ADOPT`, with no
material unresolved findings, authorizes retrying knowledge `BASELINE-000`.

## Forbidden changes

This program cannot edit `.autopilot/bin/controller.py`, any other controller file,
`.autopilot/plan.json`, `.autopilot/control-plane.json`, production `src`, `.github`,
protected branches or remotes, the sealed knowledge DAG, or its tournament bundle. All
`.autopilot/tests/test_*.py` files are forbidden except the narrow `test_healing.py`
lifecycle edit. Production/controller Git caching is deferred to another court.

## Rollback

Each node is one retained unsquashed integration commit. Revert only the failing node,
restore the frozen suite, and retain its benchmark and court evidence marked superseded.
No rollback may rewrite adverse evidence or unwind an independent sibling.

## Adopted factual erratum

The Judge issued a narrow `ADOPT` erratum after comparing the contract wording with the
retained unittest receipt. It corrects the unsupported claim of 382 executions / 381
passes plus one skip. The authoritative frozen evidence is the complete ID-set digest
above and the cited-host result of 381 total executions: 380 passes, the same conditional
skip, zero failures, and zero errors. This erratum changes no scope, command, performance
threshold, role, gate, or rollback requirement.
