# Architecture decision: Parallel agent-readiness tournament DAG

- Status: implemented additive candidate; independent final court pending
- Date: 2026-09-03
- Scope: repository-wide role and composition assurance
- Decision: **ADAPT** the current kernel with a non-promoting shadow tournament

## Context and evidence

The repository contains eight declared roles and substantial role-specific kernel
primitives. It did not contain an executable tournament that grades all eight roles
both separately and in composition.

The installed 39-node `.autopilot/plan.json` belongs to an earlier objective. Its
current strict lint is not releaseable because its durability is legacy heuristic and
its contracts are digest-unsealed. The later Generic Hive Mind V3 overlay is an
explicitly non-authorizing artifact: its 20 rounds are serial and its commands are
null. Its current Windows/Python 3.14 verifier also treats metadata-change time as a
stable executable identity; ordinary Git execution changes that field while its byte
digest remains stable. The historical architecture tournament explicitly disclaims
an empirical product-superiority result. None of those artifacts may be relabeled as
proof for the new objective.

Current source also exposes an integration gap. `MissionRuntime` constructs a serial
all-role chain; provider-backed `RoleRuntime` is asynchronous and effect-free while
the mission protocol is synchronous; the local mission adapter remains a narrow
fixture. These facts are retained as development gaps even if every existing test
passes.

`roles.py` explicitly limits executable repository-mission delivery to Explorer,
Builder, and Curator and marks the other five roles planned. The all-eight kernel
registry routes through one generic local-only handler with effects disabled, and the
fixture experiment surface reports that evaluation is not implemented. The scorecard
therefore separates structural evidence from limited-local and production evidence;
it cannot truthfully grade all eight roles as operationally complete.

Sources used by this decision are repository-local and are rebound by content hash in
each tournament inventory:

- `prompts/shared/ULTIMATE_SOLUTION_TOURNAMENT.md`;
- `docs/plan/genericprompt-execution-2026-08-09/TOURNAMENT_RESULTS.json`;
- `.autopilot/plan.json`, `.autopilot/bin/*`, `.autopilot/tests/*`, and the
  control-room workflow;
- `docs/execution/dags/generic-hive-mind-product-v3/*`;
- `src/hive_mind_os/brain_kernel/*`, role manifests, prompts, skills, and tests.

No unavailable external source was invented for this decision.

Three adverse predecessor executions remain immutable outside the checkout:

- `C:\Users\beesp\.codex\tournament-runs\agent-readiness-20260903-run-002`
  (`manifest sha256:325e00ce4578386722e2fc1299822d2c4b031036e27e8d1d0feeca58d458a400`,
  `quarantine`) exposed product and harness failures under the original 26-node plan;
- `C:\Users\beesp\.codex\tournament-smoke\agent-readiness-control-plane-coverage-smoke`
  (`manifest sha256:6b4f3644af25ffbb49b725f77717bc89299070ef61695ea43868025a81ad1453`,
  `adapt`) proved the expanded direct suite/doctor topology while preserving the
  safe-path compatibility failure that motivated this successor;
- `C:\Users\beesp\.codex\tournament-smoke\agent-readiness-isolated-doctor-smoke`
  (`manifest sha256:271f136d36eca8e8f082a3a0d82810e4291e2a28bec884dda7c45a595cda32df`,
  `incomplete sha256:cccf655f374a8e2292237231e5fe09064b8b3832ecef79e3e86d3bb5d44a0dd8`)
  failed closed in the direct control-plane lane. Its 66-character tournament temp
  root pushed 21 sealed-arena paths to 262 characters on a host with classic long
  paths disabled. No process, reparse point, or read-only artifact explained the
  residue. The 2,664-item temporary tree was removed only after this observation was
  preserved; the immutable failed bundle itself was not changed.

They are evidence inputs, not passing receipts, and are not overwritten or relabeled.

## Decision

Add `hive_mind_os.agent_tournament` and the `hive-mind tournament` CLI. The runtime
loads a digest-bound 28-node plan and executes dependency-ready nodes in real parallel
waves. Its output directory is create-only. A central recorder writes one receipt per
node, lossless base64 command-transcript envelopes, bounded infrastructure-attempt
records, exact wave records with derived positive-overlap evidence, and a chained
event history. Command-bearing waves record a separate positive-overlap peak derived
from enclosed command-receipt intervals, so outer orchestration timing cannot stand
in for parallel test execution. A final manifest binds the complete artifact set, and the
verifier rejects both omissions and additions. Exhausted retries preserve every
completed peer result plus a self-hashed incomplete-run diagnostic manifest before
failing closed. If a command finishes but its temp cleanup fails, the incomplete
bundle also preserves the command result and lossless transcript as explicitly
non-certifying diagnostics. The completed-run verifier deliberately does not certify
those partial diagnostics.

The DAG has eight waves:

```text
repository seal
      |
eight parallel role grades
      |
seven parallel composition gates
      |
serialized full doctor in a disposable clone
      |
serial canonical product-suite gate
      |
declared-role cross-examination
      |
eight parallel feedback contracts
      |
non-promoting championship
```

The repository inventory hashes every versioned or unignored ordinary in-root file,
subject to explicit per-file and aggregate evidence budgets; ignored files are outside
v1 scope, and symlinks, junctions, tracked deletions, and gitlinks fail closed. Python and JSON
Python artifacts are parsed and compiled in memory, and JSON artifacts are parsed.
Role lanes execute role-specific tests. Seven parallel composition lanes cover
all-role lifecycle, scripted code-to-QA delivery, resilience/no-cheating, learning and
promotion boundaries, predecessor strict lint, and its separately governed 447-test
control-plane suite. The exact full bootstrap doctor then runs serially in a
hardlink-free standalone clone, after the direct control-plane suite has completed.
In-memory compilation covers the
control-room syntax objective without writing ignored bytecode into the sealed checkout.
The canonical product CI command is then executed in full.

## Grading and feedback

Safety eligibility and merit are separate. Every role receives a multidimensional
scorecard, evidence limitations, a letter grade, and a courtroom disposition. An
offline declaration or passing fixture does not earn live-provider credit. Therefore
v1 cannot mark a role operationally complete without later live semantic task evidence.

Fixable failure results in `adapt` and a new challenger contract. Uncertainty results
in `defer`/retest. Fatal authority, identity, evidence-integrity, evaluator-leakage, or
safety violations are non-compensating and may quarantine the candidate. Losing
receipts and dissent remain in the bundle.

The intended future feedback loop has bounded generations:

```text
candidate.g0 -> evaluation.g0 -> disposition.g0
                                      |
                                  challenger.g1
                                      |
                                  evaluation.g1
```

V1 stops before the second evaluation arrow. Each feedback action preserves its parent
champion and executes three bounded challenge-synthesis stages: source reconsideration,
counterexample attack, and sealed acceptance/rollback/re-entry design. It emits a
contract requiring any changed
challenger to start a create-only run from a new repository scan. V1 does not mutate a
champion, materialize a successor, or automatically run the successor generation.

## Alternatives considered

1. Reuse the installed Autopilot plan: rejected because it is stale for this objective
   and fails strict release lint.
2. Activate the Generic V3 overlay: rejected because it explicitly has no commands or
   execution authority.
3. Immediately rewrite `MissionRuntime` for parallel mutation: deferred because that
   would mix assurance with authority-bearing product changes before the baseline is
   trustworthy.
4. Add a shadow, read/test-only tournament: adopted as the reversible first slice.

## Threats and constraints

- The plan validator enforces the exact v1 action topology, complete node contracts,
  acyclicity, role/lane bindings, bounded attempts, and ordered overlapping writes.
- Test subprocesses receive this checkout's `src`, repository root, and the exact
  predecessor-control-plane module directory on a safe `PYTHONPATH`; they disable
  user-site and bytecode behavior and use a small credential-scrubbed environment with
  inherited Git-control variables removed, a fixed minimal executable search path,
  and a best-effort proxy deny. A repository-required Node runtime is admitted only
  from fixed native operating-system locations; its availability, absolute path, and
  SHA-256 are sealed and live-rederived, never selected from ambient `PATH`. The
  default profile also enables safe-path mode. Only the exact sealed control-plane
  tests and full-doctor commands use a narrow cwd-compatibility profile because the
  sealed worktree worker replaces `PYTHONPATH` and imports `tests.*` from its controlled
  working directory; the separate provenance probe retains safe-path mode. Every
  command gets a disposable temporary root and has `TEMP`, `TMP`, and `TMPDIR` rebound
  to it. Tournament-owned temp/workspace basenames are intentionally short, and the
  exact sealed control-plane commands preflight their known 196-character descendant
  budget against the 259-character classic Windows boundary before launch. This is a
  compatibility constraint inside the same validated ambient-temp authority, not an
  authority expansion. The benchmark hidden checker replaces the parent `PYTHONPATH` with the exact isolated
  candidate workspace when candidate import is its intended check. A bounded,
  non-importing probe records resolved package provenance. Execution and captured
  streams have wall-time and byte budgets. These processes are not protected by a
  kernel filesystem, process, or network sandbox, so no hostile-code or production
  claim is allowed.
- Git inventory uses a native executable from a fixed operating-system installation
  location, disables hooks and filesystem monitors, has a deadline, verifies the
  requested top-level, fails on tracked deletions or omitted required role/tournament
  paths, and binds that executable by path and digest.
- Tournament output and ambient temporary paths are rejected when they overlap the
  selected/shared Git administrative roots or selected/shared-primary ignored
  control-plane state. The full doctor receives an empty ignored-state seed in a
  standalone no-hardlink clone. Its command temporary root is confined beside that
  clone, and both are removed fail-closed. Selected and shared-primary state manifests
  are compared before, after, and again during bundle verification. This proves the
  tournament did not mutate those authority roots through the verification observation;
  the clean-clone doctor does not certify the health of their live ignored contents.
- The verifier binds plan, rubric-derived role scores, evidence-derived system-lane
  statuses, a rederived championship report, derived feedback, command receipts,
  transcripts, the Markdown report, execution attempts and waves, event chain, and
  exact artifact inventory. The full-doctor receipt additionally binds its launch cwd,
  interpreter, exact nested controller-test success schema, containment and discarded
  stream policy, ordered command/doctor/repair timestamps, live protected-state
  manifests, and cleanup. It re-derives role and static-parser claims from the
  caller-selected exact checkout without rerunning tests, and requires the loaded
  verifier to be the digest-bound runtime recorded from that checkout. This proves checkout-bound
  internal derivation and content integrity, not an external signature or portable
  standalone attestation.
- Court participants in this slice are non-overlapping declared labels, not evidence
  of separately authenticated principals. That missing independence blocks promotion.
- Development scores cannot mask a critical system lane.
- No method in this slice changes a prompt champion, source control-plane authority,
  production state, policy, protected branch, or remote repository. It does create
  explicitly selected evidence plus bounded disposable clone/temp artifacts.

## Migration and rollback

This is a shadow-mode additive slice. The next governed generation may consume its
feedback contracts to make `MissionRuntime` async-first, schedule true objective-DAG
ready sets, bridge provider cognition to typed effect adapters, and expand the
code-to-QA corpus beyond the bundled Python fixture. Those are not claimed here.

Rollback removes the CLI route, module, tests, and plan/ADR from a successor commit.
Previously emitted evidence remains append-only and is never used to reactivate an old
Autopilot release.

## Acceptance

- all eight role lanes appear in one actual positive-overlap parallel wave and a serial
  worker setting is rejected;
- seven component gates appear in a second actual positive-overlap parallel wave, and
  the full bootstrap doctor runs serially after the direct control-plane tests;
- existing code-to-QA bridge fixtures, resilience, evolution, product unittests,
  separately governed control-plane unittests, and the bootstrap doctor execute;
- no unordered overlapping write scopes validate;
- every role and feedback receipt is digest-bound;
- report forgery, weakened plan policies, hostile ambient Git routing, extra files,
  transcript substitution, false parallel evidence, and event-chain tampering fail;
- bounded infrastructure-only retry, non-retry of contract/evidence defects, and
  terminal all-peer failure diagnostics are tested;
- a fatal finding defeats a perfect average;
- skipped full-suite evidence can only yield `adapt` or worse;
- the repository CI gate executes from the exact checkout; a nonpass quarantines the
  candidate and must pass before promotion.

The run receipt supplies the implementation court evidence. It remains a repository
readiness verdict, not a live-provider, production, customer-value, or superiority
claim.
