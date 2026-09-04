# Agent readiness tournament v1

This package is the executable, repository-wide assurance DAG for the eight
constitutional Hive Mind roles. It is additive to the historical Autopilot plans.
It does not reinterpret a completed historical node, activate a release, move a
champion pointer, or authorize a source-repository mutation.

The canonical plan is [`plan.json`](plan.json). Its digest is
`sha256:3e04ce46f9f4b09ca8fa73d1e5ef0f890c61885f8600fc9e0eb3d1391bc3f3fc`
and is re-derived by the runner before any node executes.

## What it executes

The runner compiles 28 nodes into eight dependency-safe waves:

1. hash and classify every Git-versioned or unignored repository file;
2. grade Orchestrator, Explorer, Architect, Builder, Curator, Integrator,
   Steward, and Optimizer concurrently;
3. run seven parallel composition gates: repository-wide in-memory Python
   compilation/JSON parsing, lifecycle, scripted code-to-QA, resilience,
   evolution, legacy strict lint, and the separately governed
   `.autopilot/tests` suite;
4. after that suite completes, run the exact full bootstrap doctor alone in a
   disposable standalone clone;
5. run the canonical product unittest gate alone;
6. cross-examine apparent passes and preserve fatal findings separately from
   development gaps;
7. emit eight immutable-champion feedback/re-entry contracts in a parallel-safe
   wave; and
8. issue a non-promoting championship disposition.

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
`verify` command. The output path is rejected when it overlaps selected/shared
Git administration or ignored control-plane authority state. Test subprocesses receive a small
credential-scrubbed environment with inherited Git-control variables removed and a
fixed minimal executable search path plus a best-effort proxy deny. Each command gets
one create-only disposable temporary root; `TEMP`, `TMP`, and `TMPDIR` are rebound to
it and its removal is verified. On Windows the allocator chooses the shortest safe
parent from validated user-owned candidates (the ambient temp directory and absolute
`USERPROFILE`), excluding repository-authority overlap and link/reparse-point paths.
The generated root reserves 220 characters for descendants and must stay below the
conservative 247-character visible-directory boundary. The exact sealed control-plane
commands additionally verify their known 196-character nested-arena budget. A nested
harness receives a narrow parent hint that is accepted only when its ambient `TEMP` is
below an `htc-` child of that same revalidated parent; `USERPROFILE` itself remains scrubbed.
Cleanup
uses extended-length Windows path spelling and revalidates root identity and callback
confinement before deletion. It retries only recognized transient cleanup errors on a
bounded 0, 50, 100, 200, 400, and 800 millisecond schedule; exhaustion still fails
closed. A command that finishes but cannot clean its temp root still fails the run;
its result and lossless transcript are retained only as non-certifying diagnostics in
the incomplete bundle. That path can add
a native Node runtime only from fixed operating-system locations; its resolved path,
availability, and SHA-256 are recorded in the repository seal and re-derived during
verification. Ambient `PATH` entries are never consulted for that runtime. Inventory
uses a native Git executable from a fixed operating-system installation location and
fails if required tournament/role/control-plane files are omitted. Git observations disable hooks and
filesystem monitors, have deadlines, and fail closed when HEAD/status metadata cannot
be sealed. Command output is captured losslessly in base64 envelopes with strict
per-stream byte limits; repository files also have per-file and aggregate evidence
budgets. A bounded, non-importing probe proves that `hive_mind_os` resolves from the
checkout under test. The safe import path contains only the checkout's `src`, root,
and exact predecessor-control-plane module directory. Safe-path mode is mandatory by
default. Only the exact sealed control-plane test and doctor commands receive a
documented cwd-compatibility profile because their worktree worker replaces
`PYTHONPATH` and imports `tests.*` from a controlled checkout working directory. The
provenance probe remains in safe-path mode. The benchmark's hidden checker
replaces that parent path with the isolated candidate workspace when it intentionally
imports candidate code. This is defense in depth, not an operating-system sandbox.

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
wrong waves, and broken event history. For the doctor lane it also re-derives the
closed nested controller-test success evidence, launch working directory, interpreter,
containment, stream policy, ordered command/doctor/repair timestamps, no-hardlink clone
identity, live selected/shared authority-state manifests, and completed clone/temp
cleanup. This is schema, derivation,
content-hash, and execution-provenance verification against the caller-selected
exact checkout, using the recorded verifier runtime from that same checkout; the
bundle is not externally signed or independently portable to a
different checkout.

## Run-003 appeal evidence

`C:\Users\beesp\.codex\tournament-runs\agent-readiness-20260903-run-003` is an
immutable failed run, not a completed or passing bundle. Its product-suite command
nested another temporary directory below the 46-character tournament command root,
putting GitHub-adapter directories at 259 characters and six ordinary benchmark files
at 261 characters. The run reported two failures and three errors across four
path-sensitive tests, then failed cleanup with Windows error 145. Independent review
found no process, lock, reparse point, or read-only artifact; unnested replays passed.

The partial manifest file is
`sha256:8198a836430512abd6f0167a71fbaaf968375a8bb67f24df53a32f1c17fb0e65`
(canonical self-digest
`sha256:54420a29b0906835f99914165024165f63655c06cb7742b80936296ac166a904`),
and `incomplete.json` is
`sha256:2fc043f9c743ec927269fcb95e22f1670e8834b3959f9c40e5bcafc8d68d357b`
(canonical self-digest
`sha256:9ab5dadbab8c1ea8ff91ade8ac9367b3ff51e69a95dea3eca757f1d8203b20d9`).
The failed node receipt file is
`sha256:0a15e53d163340b7eadb520e0eff54a14a3c6a4c5e52bc6d3e994921380bc8df`;
its diagnostic transcript is
`sha256:2e63a2226d50a4a58ad9c180142738ab449fe205f6095231ace0d70f13d6f556`.
The official verifier exits nonzero because no completed report exists. The disposable
residue was removed only after independent inspection; the sealed run directory was
not modified.

The appeal disposition is **ADAPT**: use the short-parent path budget, extended-length
cleanup, and bounded retry policy described above, then start a fresh create-only run.
Writing at a volume root, introducing junctions, sharing a fixed command directory, or
relabeling run 003 were rejected. Retries are limited to Windows errors 5, 32, 33, and
145 and POSIX `EACCES`, `EPERM`, `EBUSY`, and `ENOTEMPTY`; they never convert a failed
test command into a pass.

## Run-004 nested-environment appeal

`C:\Users\beesp\.codex\tournament-runs\agent-readiness-20260903-run-004`
completed all 28 nodes and reverified as `quarantine`. Its full suite ran 1,250 tests
with 11 skips, one failure, and two errors, all in the newly added tournament regression
tests. The short-root cleanup succeeded and the run-003 long-path product failures did
not recur. The failing tests instead depended on `USERPROFILE` after the tournament had
correctly scrubbed it, or accidentally selected the real allowed parent for a negative
case. The sealed report digest is
`sha256:8da935e8556ca27e8aa0a654b613610d4fdc982d05369202df97d8dd235d7cbd`,
the transcript digest is
`sha256:7c02184af89e3409315174e9cd62f979fdcd6d0ccb12ffe21c0e4abd410db5b1`,
and the event-chain tail is
`sha256:5cb792ed3e769418a2d28b329fcde8ac2a0449ab22470cd32aeb9aac5a254ee4`.

The appeal disposition is **ADAPT**. Tests resolve the harness-specific parent hint
before supplying a temporary `USERPROFILE` fixture, and negative parent evidence uses
a short volume-root child. Nested selection accepts the hint only when ambient temp
descends through an `htc-` child of that parent, then re-runs the normal safety and path
checks. A fresh create-only full run is required; run 004 remains immutable adverse
evidence.

`--skip-full-suite` is available for development only. It records an explicit
`defer` and makes an `adopt` championship impossible.

## Interpretation boundary

A passing run proves the checked-out contracts and local deterministic behavior it
actually exercised. It does not by itself prove live-provider semantic quality,
production authority, arbitrary-repository delivery, customer value, or superiority.
The current scripted code-to-QA lane exercises an existing isolated committed-change
fixture and fresh Curator verification; this tournament does not ask Builder to author
a novel change. It is a bridge acceptance test, not the final general coding runtime.
The product `tests` gate, separately governed `.autopilot/tests`, and serialized full
bootstrap doctor are distinct evidence lanes, so “repository-wide” does not silently
collapse to the product suite alone. The doctor clone begins without ignored state and
therefore validates clean bootstrap behavior. Source-state before/after manifests prove
that the selected and shared-primary state was not changed through verification; they
do not certify the health or meaning of that live ignored coordination state.

“Repository-wide” means all Git-versioned files plus unignored working-tree files.
Ignored files are outside the inventory evidence set except for the narrowly protected
authority-state mutation guards just described. Symlinks, junctions, gitlinks/submodules that
cannot be read as ordinary in-root files, tracked deletions, and evidence-budget
overruns fail closed rather than being silently skipped.

Each feedback node executes three deterministic challenge stages: reconsider the
source evidence, seek falsifying counterexamples, and seal acceptance/rollback/re-entry
requirements. It then emits a create-only re-entry contract beginning at
`SCAN-REPOSITORY`; it also names the lifecycle, control-plane test/doctor, and product
suite gates that must be revisited. This v1 runner does not mutate an agent or
automatically execute a successor generation; a scheduler must materialize the changed
challenger in a new run. Promotion remains exclusively behind the existing promotion
authority and a separate independent court.
