# Agent readiness tournament v1

This package is the executable, repository-wide assurance DAG for the eight
constitutional Hive Mind roles. It is additive to the historical Autopilot plans.
It does not reinterpret a completed historical node, activate a release, move a
champion pointer, or authorize a repository mutation.

The canonical plan is [`plan.json`](plan.json). Its digest is
`sha256:5a6dadbdf39482bd32afdf3e3f1f87d64143aebed83be845e364151988ab3270`
and is re-derived by the runner before any node executes.

## What it executes

The runner compiles 26 nodes into seven dependency-safe waves:

1. hash and classify every Git-versioned or unignored repository file;
2. grade Orchestrator, Explorer, Architect, Builder, Curator, Integrator,
   Steward, and Optimizer concurrently;
3. run repository-wide static parsing plus lifecycle, scripted code-to-QA,
   resilience, evolution, and legacy-control-plane lanes concurrently;
4. run the complete repository unittest gate alone;
5. cross-examine apparent passes and preserve fatal findings separately from
   development gaps;
6. emit eight immutable-champion feedback/re-entry contracts in a parallel-safe
   wave; and
7. issue a non-promoting championship disposition.

Every role grade includes artifact validation, a static module-scope implementation
declaration, isolated focused tests, declared authority boundaries, limitations, and
non-overlapping Advocate, Cross-Examiner, Expert Witness, Curator, Judge, and
affected-champion labels.
Those labels do not prove separately authenticated principals. Explorer, Builder, and
Curator receive limited-local delivery credit; the repository itself marks the other
five delivery roles as planned.
An ordinary defect produces `adapt`; missing evidence produces `defer`; only an
identity, evidence-integrity, authority, leakage, or safety violation is eligible
for `quarantine`. A score cannot compensate for a fatal gate.

## Run it

Use a new output directory on every run. The runner refuses to overwrite prior
evidence, executes infrastructure retries at their sealed bounds, and records every
parallel-wave result before a clean abort. An interrupted run leaves self-hashed
diagnostic remnants; only a completed bundle is accepted by the independent
`verify` command. Test subprocesses receive a small
credential-scrubbed environment with inherited Git-control variables removed and a
fixed minimal executable search path plus a best-effort proxy deny. Inventory uses a
native Git executable from a fixed operating-system installation location and fails
if required tournament/role files are omitted. Git observations disable hooks and
filesystem monitors, have deadlines, and fail closed when HEAD/status metadata cannot
be sealed. Command output is captured losslessly in base64 envelopes with strict
per-stream byte limits; repository files also have per-file and aggregate evidence
budgets. A bounded, non-importing probe proves that `hive_mind_os` resolves from the
checkout under test. The safe import path contains only the checkout's `src`, root,
and exact predecessor-control-plane module directory. This is defense in depth, not
an operating-system sandbox.

```powershell
python -B scripts/run_agent_tournament.py run `
  --repository . `
  --plan docs/execution/dags/agent-readiness-tournament-v1/plan.json `
  --output-dir evidence/tournaments/<new-run-id> `
  --max-workers 8
```

Verify a completed bundle without executing tests again:

```powershell
python -B scripts/run_agent_tournament.py verify `
  --run-dir evidence/tournaments/<run-id> `
  --repository .
```

The verifier rejects missing or additional artifacts, altered plan/report/receipt
digests, rubric scores, test totals, transcript verdicts, or lane passes that cannot
be derived from their command evidence, a championship report that cannot be
rederived from source receipts, non-derivable feedback, transcript or Markdown-report
substitution, false parallel
provenance (including merely adjacent execution intervals or outer attempts that do
not enclose their command receipts), invalid retry histories,
wrong waves, and broken event history. This is schema, derivation,
content-hash, and execution-provenance verification against the caller-selected
exact checkout, using the recorded verifier runtime from that same checkout; the
bundle is not externally signed or independently portable to a
different checkout.

`--skip-full-suite` is available for development only. It records an explicit
`defer` and makes an `adopt` championship impossible.

## Interpretation boundary

A passing run proves the checked-out contracts and local deterministic behavior it
actually exercised. It does not by itself prove live-provider semantic quality,
production authority, arbitrary-repository delivery, customer value, or superiority.
The current scripted code-to-QA lane exercises an existing isolated committed-change
fixture and fresh Curator verification; this tournament does not ask Builder to author
a novel change. It is a bridge acceptance test, not the final general coding runtime.

“Repository-wide” means all Git-versioned files plus unignored working-tree files.
Ignored files are outside this v1 evidence set. Symlinks, junctions, gitlinks/submodules that
cannot be read as ordinary in-root files, tracked deletions, and evidence-budget
overruns fail closed rather than being silently skipped.

Each feedback node executes three deterministic challenge stages: reconsider the
source evidence, seek falsifying counterexamples, and seal acceptance/rollback/re-entry
requirements. It then emits a create-only re-entry contract beginning at
`SCAN-REPOSITORY`. This v1 runner does not mutate an agent or automatically execute a
successor generation; a scheduler must materialize the changed challenger in a new
run. Promotion remains exclusively behind the existing promotion authority and a
separate independent court.
