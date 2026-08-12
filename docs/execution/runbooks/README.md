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
| R2 | 7 | `DURABLE-410 DELIVERY-420 HUMANLESS-430 CHEAT-440 LEARN-500` | 5 parallel |
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

## Orchestrator procedure (one round)

Phase 0 — release the wave (~2 minutes, all deterministic):

```bash
git fetch origin <release-branch>
python .autopilot/bin/github_snapshot.py --reconcile --actor codex:<round>-orchestrator
python .autopilot/bin/autopilot.py --repo-root . dispatch --actor codex:<round>-orchestrator --node <NODE> [--node <NODE> ...]
python .autopilot/bin/autopilot.py --repo-root . render-prompt <NODE>   # per released node
```

The dispatch output must say `START NOW` (one node) or `START TOGETHER NOW`
(wave) and name every node. Open exactly the stated number of worker sessions,
pasting each rendered prompt plus the node's runbook. Do not open sessions for
`WAIT`/`STOP` verdicts.

Phase 1 — supervise with bounded waits (never block indefinitely):

- Check worker sessions on a timer, not a blocking wait. If a session shows no
  new output for 15 minutes, send one nudge ("continue; report WHAT I DID /
  NEXT STEPS / BLOCKS"). If it stays silent for another 15 minutes, treat it as
  stalled: record the blocker, leave its claim to lapse (90-minute lease), and
  plan a solo re-dispatch of that node. Never re-paste a stale prompt — a new
  dispatch is required after any target advance.
- A worker is terminal only at: draft PR opened + durable receipt commit pushed
  (success), or an `autopilot fail` blocker/escalation record (blocked). Chat
  prose alone is never completion.

Phase 2 — integrate serially, in deterministic order:

Workers never touch the release branch. The orchestrator is the single
integrator. Take finished nodes in the wave's declared `--node` order (not
finish order); for each:

```bash
git fetch origin <node-branch>
git merge --no-ff <node-branch>        # ancestry-preserving; never squash/rebase
git push origin <release-branch>
python .autopilot/bin/github_snapshot.py --reconcile --actor codex:<round>-integrator
python .autopilot/bin/autopilot.py --repo-root . status   # node must now be COMPLETE
```

A merge conflict is a stop signal, not a judgment call: scopes are disjoint, so
a conflict means a scope violation. Remand to the owning node's repair flow
(`.autopilot/templates/repair.md`); never resolve semantically in the merge.

Phase 3 — one repository-wide validation per round, then release the next round:

```bash
python .autopilot/bin/autopilot.py --repo-root . validation-lease-acquire <anchor-node> --owner codex:<round>-integrator
python -m unittest discover -s tests    # the single authoritative run for the round
python .autopilot/bin/autopilot.py --repo-root . validation-lease-release <anchor-node> --owner codex:<round>-integrator
```

Workers run only their node's focused `required_tests`; the round's repo-wide
gate runs exactly once, here. Use the round's first node as `<anchor-node>`.

**R8 exception (QUALIFY-610).** In R8 the QUALIFY-610 worker runs the round's
single leased repo-wide pass itself per its runbook (Gate 1b, anchor
`QUALIFY-610`, owner `codex:qualify-610`) — its sealed contract names
`full-constitutional-ci` and `cross-platform-qualification` among its
`required_tests`, which no focused suite can satisfy. The R8 integrator does
NOT run a second Phase 3 pass; it verifies the lease was released and consumes
the worker's retained `gate1-ci/unittest-full.log` receipts instead. The
one-leased-run-per-round invariant is preserved; only the owner changes.

## Recovery (exact commands, no diagnosis needed)

- **Fresh session shows `RECONCILIATION_REQUIRED` everywhere.** Normal: local
  reconciliation state is deliberately session-local. Run Phase 0; it clears in
  one command.
- **Validation lease held by a dead session.** The lease file names the exact
  identity. Release it verbatim:
  `cat .autopilot/state/global-validation-lease.json` →
  `python .autopilot/bin/autopilot.py --repo-root . validation-lease-release <node_id> --owner <exact-owner>`.
  An expired lease is *not* reacquirable without this exact-identity release.
- **Worker died holding a local claim.** Nothing to do: the claim lapses after
  its 90-minute lease and the next `status`/`claim` reaps it.
- **Worker died after publishing a remote claim branch.** Follow the stale-claim
  retirement in `.autopilot/README.md` (`retire-receipt-branch` /
  `STALE_TARGET_RECOVERY_SEQUENCE`); do not delete remote refs by hand.
- **Target advanced mid-wave (a sibling integrated first).** Only the
  *dispatcher release* goes stale, not running claims. Workers keep going;
  integration re-reconciles between merges. Re-run Phase 0 before any *new*
  claim or wave.

## Token discipline

- The rendered worker prompt IS the node contract. Workers must not re-read
  `.autopilot/plan.json` (~18K tokens), `.autopilot/README.md`, or policy files;
  the controller enforces every gate deterministically and fails closed.
- A worker session reads exactly: its rendered prompt, root `AGENTS.md`, its
  `docs/execution/runbooks/<NODE-ID>.md`, and files inside its read scope.
- Workers run focused tests only; one leased repo-wide run per round
  (in R8 that single leased run is executed by the QUALIFY-610 worker, not the
  integrator — see the Phase 3 R8 exception).
- Orchestrators use `github_snapshot.py --reconcile` instead of hand-building
  snapshot JSON, and `--node` lists from the table above instead of re-deriving
  eligibility from the plan.

## Portability note (running DAGs on other repositories)

When Hive Mind OS builds a DAG for another repository (`DAG-BUILD` flow in
`docs/execution/PORTABLE_AUTOPILOT.md`), regenerate this same structure there:
explicit dispatch rounds, per-node runbooks, a snapshot/reconcile helper, and
the worker read-budget above. Author node contracts so that: write scopes are
pairwise disjoint *including shared scaffold files* (package `__init__.py`,
`conftest.py`, lockfiles — name an explicit owner node or forbid touching
them); `read_scope` lists concrete paths, never `**`; and every level with a
serial node is pre-split into rounds. Those five properties are what make
one-prompt-per-level parallel execution safe and cheap on any repository.
