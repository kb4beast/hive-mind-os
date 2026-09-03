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
- `.autopilot/plan.json` and `.autopilot/bin/dag_standard.py`;
- `docs/execution/dags/generic-hive-mind-product-v3/*`;
- `src/hive_mind_os/brain_kernel/*`, role manifests, prompts, skills, and tests.

No unavailable external source was invented for this decision.

## Decision

Add `hive_mind_os.agent_tournament` and the `hive-mind tournament` CLI. The runtime
loads a digest-bound 26-node plan and executes dependency-ready nodes in real parallel
waves. Its output directory is create-only. A central recorder writes one receipt per
node, lossless base64 command-transcript envelopes, bounded infrastructure-attempt
records, exact wave records with derived positive-overlap evidence, and a chained
event history. Command-bearing waves record a separate positive-overlap peak derived
from enclosed command-receipt intervals, so outer orchestration timing cannot stand
in for parallel test execution. A final manifest binds the complete artifact set, and the
verifier rejects both omissions and additions. Exhausted retries preserve every
completed peer result plus a self-hashed incomplete-run diagnostic manifest before
failing closed. The completed-run verifier deliberately does not certify those
partial diagnostics.

The DAG has seven waves:

```text
repository seal
      |
eight parallel role grades
      |
six parallel composition gates
      |
isolated full-suite gate
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
artifacts are parsed. Role lanes execute role-specific tests. Composition lanes cover
all-role lifecycle, scripted code-to-QA delivery, resilience/no-cheating, learning and
promotion boundaries, and the predecessor control plane. The canonical CI command is
then executed in full.

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
  and a best-effort proxy deny, and record resolved import provenance using a bounded,
  non-importing probe. Their execution and captured streams have wall-time and byte
  budgets. These processes are not protected by a kernel filesystem, process, or
  network sandbox, so no hostile-code or production claim is allowed.
- Git inventory uses a native executable from a fixed operating-system installation
  location, disables hooks and filesystem monitors, has a deadline, verifies the
  requested top-level, fails on tracked deletions or omitted required role/tournament
  paths, and binds that executable by path and digest.
- The verifier binds plan, rubric-derived role scores, evidence-derived system-lane
  statuses, a rederived championship report, derived feedback, command receipts,
  transcripts, the Markdown report, execution attempts and waves, event chain, and
  exact artifact inventory. It re-derives role and static-parser claims from the
  caller-selected exact checkout without rerunning tests, and requires the loaded
  verifier to be the digest-bound runtime recorded from that checkout. This proves checkout-bound
  internal derivation and content integrity, not an external signature or portable
  standalone attestation.
- Court participants in this slice are non-overlapping declared labels, not evidence
  of separately authenticated principals. That missing independence blocks promotion.
- Development scores cannot mask a critical system lane.
- No method in this slice changes a prompt champion, production state, policy,
  protected branch, or remote repository.

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
- all six component gates appear in a second actual positive-overlap parallel wave;
- existing code-to-QA bridge fixtures, resilience, evolution, and complete unittest
  gates execute;
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
