# Agent readiness tournament v2

This directory versions the code-owned executable DAG implemented by
`hive_mind_os.agent_tournament_v2`. The runner grades all eight constitutional
roles separately, exercises their composition, runs a three-shape code-to-QA
fixture corpus, and preserves bounded feedback for a fresh generation. It is an
offline structural evaluation, not proof of live-provider quality, production
safety, customer value, or superiority.

## Execute

Use a new output directory outside the repository and its Git administrative
state. The directory must not already exist.

```powershell
python -B scripts/run_agent_tournament_v2.py run `
  --repository . `
  --plan docs/execution/dags/agent-readiness-tournament-v2/plan.json `
  --output-dir C:\absolute\external\run-directory
```

The default runs the canonical CI gate:

```text
python -m unittest discover -s tests -v
```

`--skip-full-suite` exists only for bounded development. Its full-suite receipt
is `deferred`, its whole-system grade is incomplete, and it can never adopt or
promote anything.

The output is create-only. It contains the canonical plan, one receipt per DAG
node, command transcripts, wave evidence, a chained event log, the retained
code-QA workspaces and losing candidates, reports, and a recursive file and
directory manifest. A failed strict gate is quarantined; passing scores cannot
average it away.

Only the code-owned `run_command_receipt` implementation can support a
non-quarantined verdict. Dependency injection remains available for bounded
tests, but the repository seal records it as untrusted and cross-examination
must quarantine the run even if the injected runner returns passing-looking
receipts.

## Parallel topology

The 30 nodes form nine dependency waves:

1. exact repository seal;
2. eight independent role grades in parallel;
3. eight parallel system lanes (static, lifecycle, resilience, evolution,
   strict control-plane, control-plane tests, the executable native-specialist
   DAG, and code-QA v2);
4. isolated control-plane doctor;
5. external-authority challenger boundary;
6. canonical full suite;
7. cross-examination;
8. eight role feedback/rethink contracts in parallel; and
9. non-compensating championship judgment.

Each declared parallel outer wave uses a bounded first-worker-cohort barrier;
the verifier reconstructs start/end intervals and requires observed peak
concurrency of at least two (and never more than `workers_used`).

The role tests, composition tests, control-plane commands, doctor isolation,
temporary-directory cleanup, and full-suite command reuse the hardened v1
execution primitives. V2 does not copy or weaken those contracts.

`SYSTEM-NATIVE-DAG` clones the exact clean sealed HEAD into a disposable source
snapshot and runs `repository_specialist_plan()` through
`ExecutableDagRuntime` with `RepositorySpecialistHandlers`. It persists all
eight native API identities, typed dependency/artifact envelopes, node
receipts, and the logical event chain. The Integrator and Steward share the
Curator dependency and are observed in the same ready set through a retained
two-party arrival/release trace. The receipt also projects composition-critical
artifact outcomes: Curator verdict, Integrator compatibility, Steward readiness
and unobserved surfaces, and Optimizer recommendation/evidence completeness.
The current bounded run honestly records Steward `repair_required` and
Optimizer `defer`; these are preserved development gaps, not hidden behind a
mechanically passing lane. The source snapshot
must remain unchanged and both it and all node workspaces must be removed. The
same gate also runs `tests.test_brain_kernel_dag_runtime` and
`tests.test_brain_kernel_specialist_handlers` plus
`tests.test_repository_specialist_handlers` through the bounded v1 command
helper. The runtime candidate uses `repository_candidate_digest()` over the
committed HEAD, tree, and native plan. The snapshot additionally copies and
rechecks every exact byte from the opening inventory; a bounded Git
line-ending mode is selected only to reproduce the already sealed clean state.
Its in-process isolation is cooperative, not an OS sandbox.
Offline verification reconstructs the native schemas, canonical ArtifactStore
bytes, dependency digests, write scopes, event chain, and semantic summary, but
does not re-execute all eight native handlers. That remaining trust/cost boundary
is explicit in the receipt and cross-examination.

## Code-to-QA qualification

`SYSTEM-CODE-QA-V2` runs every task pinned by the checked-in corpus manifest.
The required bundle pin is
`sha256:13f0d3f8a7e34ca4b16d05b774fd22cfd52f255d8a01b5e3df8e97ed380961e7`.
The three fixture shapes force the authority-bound Builder test double to make a
source change, retain a losing first attempt, reconsider the task from the
beginning, and then pass both public and sealed checks on the exact candidate.
The lane remains explicitly a same-trust deterministic test double. It is not
an adaptive model, an independent principal, a hostile-code sandbox, an
arbitrary-repository qualification, or production evidence.
Before hashing retained stdout and stderr, the evaluator replaces its disposable
workspace and runtime roots with fixed markers. This makes the complete emitted
tree replayable byte for byte; the verifier does not waive or normalize any nested
digest, JSON serialization, or record after the run.

## External challenger authority

Challenger mode requires both an absolute external authority path and its
caller-authenticated semantic digest:

```powershell
python -B scripts/run_agent_tournament_v2.py run `
  --repository . `
  --output-dir C:\absolute\external\run-directory `
  --evaluation-authority-manifest C:\separate\authority.json `
  --evaluation-authority-digest sha256:<64-lowercase-hex>
```

The authority must be outside both repository and run roots, bind the exact
clean HEAD and tree, bind every generation-zero role champion, pin at least two
licensed comparators, separate proposer/builder/evaluator/judge identities, and
have a live two-generation budget. The runner authenticates it, bootstraps the
bound champion registry, and asks `V2ChallengerRuntime` to retain an owned,
falsifiable generation-one proposal.

Verification also requires the exact generation-zero prompt set, champion
artifacts and pointer, registration/promotion lineage, append-only SQLite event
chain, and sole content-addressed proposal record. Path escapes, extra files,
ledger replacement, partial proposal rewrites, and post-DEFER materialization
records are rejected.
The SQLite check covers database integrity, required schema object names, all
bootstrap rows, the digest chain, and exact lineage payloads; it does not claim
byte-identical SQLite layout or normalize and compare every trigger SQL string.
The outer bundle remains content-hashed rather than externally signed.

The manifest intentionally does not contain holdout cases or answers. Therefore
manifest-only execution stops at a typed `retest-required` / `defer` boundary
before evaluation-plan sealing or materialization. The receipt records these
blocking evidence obligations:

- an evaluator-owned `SealedHoldout` and intact pre-build prediction seal;
- ArtifactStore-backed candidate-bound evidence for held-out, PIT, adversarial,
  and pinned-comparator surfaces;
- independent qualification receipts and issuer authority; and
- a genuine retained `RETEST` outcome (or separately judged `DEFER` appeal)
  before generation-two re-entry.

The supported typed continuation is
`V2ChallengerRuntime.seal_evaluation -> materialize -> evaluate -> reenter`.
The runner never invents holdout cases or scores and has no champion promotion
path.

## Offline verification

Re-verification requires the same checkout. Authority-bound runs additionally
require the original external authority path and expected digest.

```powershell
python -B scripts/run_agent_tournament_v2.py verify `
  --repository . `
  --run-dir C:\absolute\external\run-directory
```

The verifier must be imported from the selected repository and the run directory
must remain outside the repository/Git authority roots. It refuses unknown
receipts, transcripts, files, directories, or DAG nodes; preflights manifest and
entry budgets; re-hashes the whole bundle; validates the event chain and wave topology;
re-derives role/system command receipts through the v1 validators; replays the
complete pinned code-QA corpus and compares its entire emitted tree; validates
the exact native artifact-store inventory; authenticates the external challenger authority when
present; recomputes feedback, cross-examination, and championship; and
re-inventories HEAD, tree, worktree state, and every repository file. Any source
drift or tamper fails closed. A SCAN failure occurs before the output directory
is created. A later typed node failure removes any partial lane subtree before
retaining its `contract-failed` receipt, so untyped leftovers cannot acquire
authority merely by being listed in the outer manifest.

The bundle is content hashed, not externally signed. Declared courtroom labels
are not proof of independent human or machine principals, and no comparison
winner is named without an independently measured equal-budget benchmark.
