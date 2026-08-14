# DAG Level Runbooks — parallel wave execution protocol

This directory is the operational contract for executing the remaining
`hive-mind-os-verifiable-hive-cortex-v1` DAG levels with one orchestrator session
per dispatch round and one worker session per node. It exists to make level
execution deterministic, hang-free, and token-lean. Per-node implementation
plans live beside this file as `<NODE-ID>.md`.

The plan fingerprint is never touched by these runbooks: node contracts stay
sealed in `.autopilot/plan.json`; runbooks only add operational procedure and
implementation detail inside each node's declared scope.

## Dispatch rounds for the remaining DAG

A *round* is one dispatcher release plus its integration. Levels with a
`parallel_safe: false` member split into multiple rounds because such a node
must be released alone. Always pass the explicit `--node` list — never rely on
greedy selection, which can release a serial node first and cap the wave at 1.

| Round | Level | `--node` wave (explicit) | Sessions |
|---|---|---|---|
| R1 | 6 | `MISSION-400` | 1 |
| R2A | 7 | `DURABLE-410` (durability first — see below) | 1 |
| R2B | 7 | `DELIVERY-420 HUMANLESS-430 CHEAT-440 LEARN-500` | 4 parallel |
| R3 | 8 | `SELFHEAL-450 CHALLENGER-510 POISON-540` | 3 parallel |
| R4 | 8 | `MIGRATION-460` (serial by contract) | 1 |
| R5 | 9 | `EVAL-520` | 1 |
| R6 | 10 | `BENCH-600` | 1 |
| R7 | 10 | `PROMOTE-530` (serial by contract) | 1 |
| R8 | 11 | `QUALIFY-610` | 1 |
| R9 | 12 | `LEGACY-620` | 1 |
| R10 | 13 | `A3-700` | 1 |
| R11 | 14 | `A4-800` — stops at the genuine owner-credential gate | 1 |
| R12 | 15 | `A5-900` — stops at external security/legal/production gates | 1 |

Order of finish inside a wave never matters: waves are dependency-satisfied and
lock-disjoint by construction, and integration order is deterministic (below),
not finish order. A worker that discovers a real dependency on a sibling must
`autopilot fail` with a blocker — never poll or wait for a sibling.

**Why level 7 splits into R2A and R2B.** The sealed plan puts all five level-7
nodes at the same depth, but two of them cannot be honestly proven before
durability exists. HUMANLESS-430's own acceptance criterion is "mission resumes
after interruption without restating context" — unprovable without the crash and
replay guarantees DURABLE-410 establishes. DELIVERY-420 performs external
effects (push, draft PR, comment) where crash recovery is what prevents
duplicate deliveries. Running DURABLE-410 alone first, integrating it, and then
releasing the remaining four against that base costs one extra round and removes
both hazards. This is enforced here as round order rather than as plan
dependency edges, because adding edges would rotate the plan fingerprint and
invalidate all completed receipts; once the controller supports plan-version
lineage, these should become real dependency edges.

## Running a round as code

The procedure below is also implemented as `.autopilot/bin/round_driver.py`.
Prefer the command; the prose exists so the behaviour is auditable and so a
human can take over at any phase.

All snippets use one exact initialized execution. Populate these once and never borrow
`default` or another worktree's paths:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
STATE_DIR="<absolute repository coordination root>"
HOST_RUNTIME_DIR="<absolute canonical per-user host runtime>"
EXECUTION_NAMESPACE="<exact execution namespace>"
HOST_ID="<canonical authenticated host id>"
PYTHON="<absolute interpreter from the sealed execution identity>"
AUTOPILOT=("$PYTHON" "$REPO_ROOT/.autopilot/bin/autopilot.py" --repo-root "$REPO_ROOT" \
  --state-dir "$STATE_DIR" --host-runtime-dir "$HOST_RUNTIME_DIR" \
  --execution-namespace "$EXECUTION_NAMESPACE")
SNAPSHOT=("$PYTHON" "$REPO_ROOT/.autopilot/bin/github_snapshot.py" --repo-root "$REPO_ROOT" \
  --state-dir "$STATE_DIR" --host-runtime-dir "$HOST_RUNTIME_DIR" \
  --execution-namespace "$EXECUTION_NAMESPACE")
```

```bash
"${SNAPSHOT[@]}" --reconcile --actor codex:orchestrator
DISPATCH_JSON=$("${AUTOPILOT[@]}" dispatch --host-id "$HOST_ID" --actor codex:orchestrator --node <NODE> [--node <NODE> ...])
RELEASE_ID=$(printf '%s' "$DISPATCH_JSON" | jq -r .release_id)
# After every worker has sealed its branch and settled its claim:
"${AUTOPILOT[@]}" run-round --actor codex:round-driver --release-id "$RELEASE_ID"
```

`dispatch` publishes one repository-shared, generation-fenced release and returns its
exact `release_id`. Before its remote reads, `github_snapshot.py` reserves a monotonic
repository-shared observation ID and installs only through that exact reservation; a
slower observation that began before a newer one is fenced. `run-round` must present the
release ID. It locks and revalidates the shared release, requires all worker claims to be
settled, requires the released wave to equal the first incomplete compiled round, and
preflights the exact receipt head for every released node before triage or Git effects. A
partial wave returns `PENDING` without healing, reconciliation, merge, push, or validation.
After separately fenced recovery, run a fresh snapshot/reconciliation and dispatch before
retrying. A whole wave integrates every sealed node branch in the release's declared
order and obtains the single authenticated validation-broker completion as one
transaction. A stale,
invalidated, wrong-plan, wrong-target, wrong-wave, or noncanonical-cap release fails
before mutation. The public command has no skip-validation or in-lock healing mode.

The publication broker also requires independently attested network and credential
isolation for untrusted candidate tests. The current Windows environment cannot prove
that sandbox boundary, so the broker deliberately fails closed before validation and no
ordinary round can be published there. Do not replace it with the legacy in-process
runner.

`autopilot execute-wave` covers the worker half: it renders the released wave
into session cards under the authenticated execution directory's `host/cards/` and supervises them by
polling repository evidence, never by waiting on a chat session.

Primary, sidecar, and validation reservations consume one authenticated per-user host
budget across every registered repository. The current App Server ceiling is
conservatively one unless a stronger expiring provider capability is sealed; the
controller cannot claim eight slots from source-code parallelism alone. Optional work is
omitted when no capacity remains, while mandatory work fails closed before a host effect.
The host kernel arbitrates admission across repositories, but it does not claim OS-level
CPU, memory, disk, network, CI, or process cancellation control. A fence cannot forcibly
cancel an external chat.

The pinned Codex App Server protocol has no crash-exact thread-create idempotency token,
so its adapter is observer-only (`autonomous_launch=false`). `execute-wave` can adopt or
observe existing work, but fresh unfinished work returns `WAITING_FOR_HOST`; operators
must not describe this build as autonomous fresh-task launch.

## Orchestrator procedure (one round)

Phase 0 — release the wave (~2 minutes, all deterministic):

```bash
git fetch origin <release-branch>
"${SNAPSHOT[@]}" --reconcile --actor codex:<round>-orchestrator
DISPATCH_JSON=$("${AUTOPILOT[@]}" dispatch --host-id "$HOST_ID" --actor codex:<round>-orchestrator --node <NODE> [--node <NODE> ...])
RELEASE_ID=$(printf '%s' "$DISPATCH_JSON" | jq -r .release_id)
"${AUTOPILOT[@]}" render-prompt --host-id "$HOST_ID" <NODE>   # per released node
```

The dispatch output must say `START NOW` (one node) or `START TOGETHER NOW`
(wave) and name every node. Open exactly the stated number of worker sessions,
pasting each rendered prompt plus the node's runbook. Do not open sessions for
`WAIT`/`STOP` verdicts.

Phase 1 — supervise with bounded waits (never block indefinitely):

- Check worker sessions on a timer, not a blocking wait. If a session shows no
  new output for 15 minutes, send one nudge ("continue; report WHAT I DID /
  NEXT STEPS / BLOCKS"). If it stays silent for another 15 minutes, treat it as
  stalled and **settle its claim explicitly — never let a claim lapse silently**
  (procedure below). Never re-paste a stale prompt; a new dispatch is required
  after any target advance.
- A worker is terminal only at: draft PR opened + durable receipt commit pushed
  (success), or an `autopilot fail` blocker/escalation record (blocked). Chat
  prose alone is never completion.

### Settling a stalled worker (never let a mutated claim expire)

A claim may lapse on its own **only if the worker published nothing**. Once a
worker has pushed anything, an expiring claim is a trap: `clean_stale_claims`
reaps on expiry without checking the branch, but `publish_remote_claim` then
refuses the re-claim with `remote branch <branch> already exists; reconcile it
before claiming`, and `release_remote_claim` can only delete the ref while it
still points at the exact claim commit. A silently expired claim on an advanced
branch therefore needs sealed recovery authority to undo — this is precisely how
the historical OPTIMIZER-370 recovery became necessary.

First determine what the worker actually published:

```bash
git ls-remote origin <node-branch>
```

**No remote branch** — nothing was published. The local claim may lapse; a solo
re-dispatch of the node works normally.

**Remote branch exists, with a durable receipt commit at its head** — the
candidate is already immutable. Treat it as sealed: do NOT re-claim and do NOT
re-run the node. Validation and integration need no live claim, so integrate the
receipt branch in the normal Phase 2 order. The stall was cosmetic.

**Remote branch exists without a receipt** — settle it before the lease expires:

```bash
"${AUTOPILOT[@]}" fail <NODE> --owner <exact-owner> \
  --claim-id <exact-claim-id> \
  --launch-instruction-id <exact-launch-instruction-id> \
  --resource-key <exact-resource-key> --authority-epoch <exact-authority-epoch> \
  --kind failure --error "worker stalled; settled by <round> orchestrator" \
  --blocker-cause "no terminal evidence within supervision window" \
  --blocker-fix "resume or repair the node from its retained branch" \
  --retry-when "after the branch is reconciled"
```

`--owner` and `--claim-id` must come from the exact stalled claim (read them from
the shared authority's `claims/<NODE>.json` before it is reaped). `fail` releases an
untouched remote claim but preserves a branch that advanced past the claim commit. In
that case do not force-delete it — the node's next round is a **repair**, not a fresh claim:
re-dispatch it and use `.autopilot/templates/repair.md`, which resumes from the
retained branch instead of demanding a new claim.

Phase 2 — integrate and validate under the exact shared release:

Workers never touch the release branch. After every node has a durable receipt branch and
every worker claim is settled, the orchestrator invokes the single fenced integrator:

```bash
"${AUTOPILOT[@]}" run-round \
  --actor codex:<round>-integrator --release-id "$RELEASE_ID"
```

The command owns deterministic ancestry-preserving merges, optional push, and the one
repository-wide validation lease while holding the dispatcher-admission lock. A merge
conflict is a stop signal, not a judgment call: scopes are disjoint, so a conflict means a
scope violation. Remand to the owning node's repair flow
(`.autopilot/templates/repair.md`); never resolve semantically in the merge. Validation
failure fails the round; it cannot be bypassed by a public CLI flag. Worker-required
qualification receipts remain evidence, but they do not replace this integration-time
gate over the exact integrated tree.

## Self-healing blocker triage (repair and continue; do not halt the DAG)

A worker blocker ends that worker, not the round and not the run. The
orchestrator classifies every blocker, repairs what it owns, re-dispatches, and
keeps going. Class A and B are never escalated to the human; class C is never
self-healed.

| Class | Signature | Why it is or is not repairable |
|---|---|---|
| **A — runbook defect** | the blocker names a requirement that lives in `docs/execution/runbooks/<NODE>.md`, and real source contradicts it | runbooks are unsealed operational detail; the orchestrator owns them outright |
| **B — scope or ordering defect** | the required change is real but falls outside the node's `file_locks`, or a dependency is not materially satisfied despite a satisfied edge | node assignment and round order are operational, not sealed |
| **C — sealed or external** | the blocker is an `acceptance_criteria` entry in `plan.json`, or a genuine credential, consent, protected-branch, spending, legal, or production gate | repairing it would rotate the plan fingerprint or fabricate authority; both invalidate every receipt the DAG has earned |

**Preflight — cheapest possible fix.** Before dispatching a node, check each
concrete symbol its runbook asserts against real source
(`grep -n "def <symbol>" <path>`). A runbook assertion that no longer matches
source is a class A repair *before* a worker session is ever opened. One grep
per asserted symbol beats a 6-minute worker that fails closed.

**Class A repair (evidence-producing, never a weakening):**

1. Read the exact symbols the blocker names in real source. If source does not
   actually contradict the runbook, it is not class A — reclassify.
2. Correct the runbook to the satisfiable invariant that *preserves the sealed
   acceptance criterion's intent*. Never delete a `required_tests` entry, never
   replace a check with a tautology. If the only honest repair reduces real
   coverage, it is class C.
3. Commit to the release branch: `fix(runbooks): <NODE> <what was unsatisfiable>`,
   citing the `file:line` contradiction and naming the replacement invariant.
4. Settle the node's claim (§ Settling a stalled worker), re-dispatch, and hand
   the worker the corrected runbook.

**Class B repair:** reassign the change to the node whose `file_locks` already
own the path, or dispatch that owner first and re-order the round. Never widen a
node's `file_locks`, and never let a node write outside its declared scope —
that is a sealed boundary wearing operational clothes.

**Guards against thrash:**

- Two self-heal repairs per node per run. A third blocker on the same node is
  class C by definition: stop that node, record it, continue other rounds.
- A repair that cannot cite a `file:line` contradiction is not a repair. Stop.
- Never edit `plan.json`, `authority-amendments.json`, `.github/governance/**`,
  or any node's `forbidden_scope`, under any classification.
- A class C node blocks only its own descendants. Continue every other round,
  and report class C nodes as a batch at the end rather than one interruption
  each.
- Record every repair in the round report: node, class, `file:line` evidence,
  the replacement invariant, and the re-dispatch result.

## Recovery (heal separately; manual commands only when healing reports STUCK_HUMAN)

Every mechanical wedge below has a deterministic recovery path. Public `run-round` does
not perform it while holding a release fence: a partial wave returns `PENDING` with no
heal, reconciliation, merge, push, or validation effect. Run the standalone healer,
refresh snapshot/reconciliation evidence, and obtain a new release before retrying:

```bash
"${AUTOPILOT[@]}" heal --host-id "$HOST_ID" --actor codex:<round>-orchestrator
"${SNAPSHOT[@]}" --reconcile --actor codex:<round>-orchestrator
DISPATCH_JSON=$("${AUTOPILOT[@]}" dispatch --host-id "$HOST_ID" --actor codex:<round>-orchestrator --node <NODE> [--node <NODE> ...])
RELEASE_ID=$(printf '%s' "$DISPATCH_JSON" | jq -r .release_id)
```

`execute-wave --apply` may heal a withheld wave once before conceding, and
`"${AUTOPILOT[@]}" heal --host-id "$HOST_ID" [--dry-run]` runs the
same pass standalone. Each action is proof-carrying, audited, and guarded by
`--force-with-lease`; the laws and their limits live in
`docs/execution/HEALING_DOCTRINE.md`. The heal report ends in a machine
disposition — `HEALED` (loop again now), `WAITING` with the exact `wake_at`
past which polling can matter again, `OPEN_SESSIONS` (open the named operator
cards), or `STUCK_HUMAN` (genuine sealed/external authority, with evidence).
What follows explains what the healer does, and remains runnable by hand.

- **Fresh session shows `RECONCILIATION_REQUIRED` everywhere.** Normal: local
  reconciliation state is deliberately session-local. Healed automatically
  (the healer runs Phase 0 itself); or run Phase 0 by hand.
- **Validation lease held by a dead session.** A *live* lease is released only
  by its exact identity:
  `"${AUTOPILOT[@]}" validation-lease-release <node_id> --owner <exact-owner> --claim-id <exact-claim-id> --lease-id <exact-lease-id> --launch-instruction-id <exact-launch-instruction-id> --resource-key <exact-resource-key> --authority-epoch <exact-authority-epoch>`.
  An *expired* lease no longer wedges the round: the healer archives it as
  `EXPIRED_BROKEN` (expiry is the bound the owner itself declared). Refresh the
  snapshot/reconciliation and obtain a new release after that repair; public
  `run-round` does not break the lease inside its admission transaction.
- **Worker died holding a local claim.** Safe to let lapse **only if it pushed
  nothing** (`git ls-remote origin <node-branch>` is empty). If it published a
  branch, see the next two bullets — the healer settles both cases.
- **Worker died after publishing a remote claim branch.** The healer retires a
  bare remote claim once any proof of defunctness holds: lease expired, plan
  fingerprint superseded, or zero work commits within
  `claim_stall_minutes` (`.autopilot/healing-policy.json`) — a dead session no
  longer wedges the node until TTL. Manual equivalent:

  ```bash
  "${AUTOPILOT[@]}" reap-stale-remote-claim <NODE> --owner <exact-owner-from-the-claim-commit-message> --reason "worker session ended"
  ```

  A branch carrying real unsealed work is never deleted: once its governing
  claim is defunct and the head has been still for `branch_stall_minutes`, the
  healer archives it verbatim under
  `refs/hive-mind-autopilot/quarantine/<node>/<sha>` and retires the branch ref
  in the same atomic push. Sealed receipts are never quarantined — they
  integrate.
- **Retry budget exhausted by a dead session's failures.** Quarantine-by-budget
  lifts only on proof: record a `blocker-resolve` (verified fix + safe retry
  command) for **every** open blocker, and the healer (or
  `lift-retry-quarantine <NODE> --actor <you>`) archives the spent ledger and
  reopens the node for dispatch. Unresolved causes keep the quarantine.
- **Target advanced outside the admitted transaction.** The shared dispatcher
  generation becomes stale. Hosted claim transitions fail closed against the
  advanced target; preserve the worker branch and reconcile it explicitly. A
  fresh snapshot, reconciliation, and dispatch are required before new work.

## Token discipline

- The rendered worker prompt IS the node contract. Workers must not re-read
  `.autopilot/plan.json` (~18K tokens), `.autopilot/README.md`, or policy files;
  the controller enforces every gate deterministically and fails closed.
- A worker session reads exactly: its rendered prompt, root `AGENTS.md`, its
  `docs/execution/runbooks/<NODE-ID>.md`, and files inside its read scope.
- Workers run their node's focused `required_tests`. `run-round` accepts only the
  authenticated validation-broker completion over the exact integrated tree; when the
  broker cannot attest isolation, it fails closed.
- Orchestrators use `"${SNAPSHOT[@]}" --reconcile --actor "$ACTOR"` instead of
  hand-building snapshot JSON, and `--node` lists from the table above instead of
  re-deriving eligibility from the plan.

## Portability note (running DAGs on other repositories)

When Hive Mind OS builds a DAG for another repository (`DAG-BUILD` flow in
`docs/execution/PORTABLE_AUTOPILOT.md`), regenerate this same structure there:
explicit dispatch rounds, per-node runbooks, a snapshot/reconcile helper, and
the worker read-budget above. Author node contracts so that: write scopes are
pairwise disjoint *including shared scaffold files* (package `__init__.py`,
`conftest.py`, lockfiles — name an explicit owner node or forbid touching
them); `read_scope` starts from concrete paths plus a metadata-only repository
index (paths, blob SHAs, symbols, imports, test map) rather than a bare `**`
glob, while allowing budgeted, recorded cold expansion when a node proves its
initial scope was incomplete — repositories that genuinely need a broad
discovery pass get one, on the record, instead of every node reading the world
by default; and every level with a serial node is pre-split into rounds. Those five properties are what make
one-prompt-per-level parallel execution safe and cheap on any repository.
