# Git Commit Observation DAG

`git-commit-observation-v1` is the separate challenger authorized by the appeal in
`evidence/courts/CASE-DOCTOR-PERFORMANCE-PROMOTION.json`. It does not amend or revive the
rejected fixture candidate. It authorizes no generic Git cache, remote effect, superiority
claim, automatic promotion, or knowledge-projection `BASELINE-000` retry.

## Current truth

- Planning/sealing: complete after `GCO-SEAL-000` verifies and is committed.
- Runtime implementation: not started.
- Performance qualification: not run.
- Final promotion: blocked pending a distinct `GCO-JUDGE-090` ADOPT verdict with zero
  unresolved material findings.
- The only generated file at sealing time is ignored
  `.autopilot/state/git-commit-observation-v1.json`.

## Authorized architecture

The candidate is a controller-private immutable `GitCommitObservation`. One narrowly named
reader accepts only a finite, deduplicated, validated list of full commit OIDs. It binds the
repository root, absolute Git directory, common directory, object format, and permitted
object store; disables replacements; and uses one `git cat-file --batch` process.

Every response must preserve exact count and order and match
`<oid> commit <decimal-size>`, exact body bytes, and the protocol terminator. The reader
recomputes each OID from `commit <size>\0<body>` under the declared object format and parses
exactly one `tree` followed by zero or more `parent` headers before the first blank line.
Missing, malformed, duplicate, extra, truncated, reordered, wrong-type, or hash-mismatched
output is fatal. Shallow, graft, promisor, replace, and alternate configurations fail closed
unless separately proven safe.

The observation is used only for exercised diagnostics and explicit invocation-local pure
receipt validation. It is never serialized, retained, shared, or used as authority. It is
destroyed before claim, completion, retirement, repair, fetch, push, update-ref, CAS,
compensation, or publication decisions. Those boundaries freshly read repository, origin,
target, reconcile state, refs, objects, authority, releases, leases, claims, snapshots,
receipts, intents, and CAS state, retain existing force-with-lease/CAS, and verify fresh state
after an effect. `sealed_recovery.py` and `release_barrier.py` cannot consume it.

## Exact DAG and dispatch rounds

```text
R1  GCO-SEAL-000
        ├── R2  GCO-BASELINE-010 ──┐
        └── R2  GCO-TEST-020 ──────┼── R3 GCO-ARCH-030
                                    └──── dependencies join
R4  GCO-BUILD-040
R5  GCO-INTEGRATE-050
R6  GCO-SAFETY-060
R7  GCO-SMOKE-070
R8  GCO-QUALIFY-080
R9  GCO-JUDGE-090
```

The only parallel round is R2. `GCO-ARCH-030` depends on the seal and baseline; the Builder
depends on both the independent test contract and ADR. Every later node is serial.

| Node | Acting role/court seat | Declared output |
|---|---|---|
| `GCO-SEAL-000` | Orchestrator / Clerk | Seven DAG files plus opening court |
| `GCO-BASELINE-010` | Explorer + Optimizer | Baseline diagnostic receipt |
| `GCO-TEST-020` | Independent Curator | Adversarial test contract |
| `GCO-ARCH-030` | Architect | ADR-064 |
| `GCO-BUILD-040` | Builder | `controller.py` only |
| `GCO-INTEGRATE-050` | Integrator | `durable_controller.py` only |
| `GCO-SAFETY-060` | Steward + independent Curator | Safety qualification receipt |
| `GCO-SMOKE-070` | Optimizer | One smoke receipt per pinned runtime |
| `GCO-QUALIFY-080` | Independent qualification Curator | Conditional candidate matrix and qualification |
| `GCO-JUDGE-090` | Distinct Judge | Final qualification court |

## Sealing and execution commands

Seal verification does not run diagnostic, smoke, or qualification benchmarks:

```powershell
python docs/execution/dags/git-commit-observation-v1/benchmark.py self-test
python docs/execution/dags/git-commit-observation-v1/verify_plan.py --write
python .autopilot/bin/autopilot.py --repo-root . dag-lint --plan .autopilot/state/git-commit-observation-v1.json --strict --json
python .autopilot/bin/autopilot.py --repo-root . dag-rounds --plan .autopilot/state/git-commit-observation-v1.json --max-sessions 4 --actor codex:git-commit-observation --json
python docs/execution/dags/knowledge-projection-v1/verify_plan.py
python docs/execution/dags/doctor-performance-v1/verify_plan.py
```

Dispatch only the explicit node list printed for each compiled round. Workers use one node
branch and one retained unsquashed commit. A single Integrator merges in declared order and
runs one round-wide validation. Do not rebase, squash, amend, widen scope, or mutate main.

The benchmark harness supports:

- `run --phase baseline-diagnostic --trials 1` for the current diagnostic receipt;
- `run --phase smoke --trials 1` once on each pinned runtime;
- `qualify ...` to stop after a failed smoke or run at least six fresh cold-first alternating
  trials per runtime, followed only after performance passes by focused adversarial tests,
  full `.autopilot` discovery, and full repository CI;
- `verify` and `verify-program` for digest and gate reproduction.

The frozen burden is unchanged: exact doctor command, 180-second internal timeout, 381 total
executions = 380 pass plus the same conditional skip, complete ID digest
`sha256:7c0cf4ae7a2efca60af613b1702c97133a28b043bad09b231fe3a6c97d23eef4`,
every candidate trial below 180 seconds, and nearest-rank p95 at most 135 seconds on both
pinned runtimes.

## Author-verified standard checks

In addition to strict lint, the Clerk manually verified narrow write scopes, concrete read
scopes, runnable focused commands, meaningful node-specific stopping and rollback contracts,
honest `parallel_safe` declarations, semantic-lock vocabulary, file locks covering every
write, the safety-before-activation and benchmark-before-promotion orderings, explicit round
dispatch, all execution invariants, and all other-node write scopes in every node's
`forbidden_scope`. No universal-read warning requires justification.
