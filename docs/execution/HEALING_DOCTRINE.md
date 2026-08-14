# Self-Healing Doctrine

The control plane's verbs are individually fail-closed. That is correct for a
worker and fatal for the loop that supervises workers: a dead session's live
claim, a superseded dispatch release, and an expired validation lease each
refuse every polite verb while never resolving on their own. Before this
doctrine, each of those wedges waited for a human to run commands the protocol
already permitted. The healer (`.autopilot/bin/healing.py`) is that human
judgement as code.

## The three laws

1. **Proof, never impatience.** Every action requires a proof read from
   durable evidence (git objects, claim records, lease bounds, blocker
   packets). A diagnosis is never authority: the controller verb that executes
   an action re-verifies its proof and refuses if the evidence moved.
2. **Preserve, never destroy.** Healing archives, retires, and re-issues.
   Published work is never deleted — an unsealed dead branch is archived
   verbatim under `refs/hive-mind-autopilot/quarantine/<node>/<sha>` in the
   same atomic push that retires its branch ref. Every deletion is guarded by
   `--force-with-lease`, so a worker pushing at the same moment wins the race.
3. **Sealed stays sealed.** Anything whose repair needs sealed or external
   authority (plan fingerprint, acceptance criteria, credentials, consent,
   protected branches, spending, production, legal) is reported with its
   evidence and exact instructions — never attempted.

## What the healer may do, and its proof obligations

| Wedge | Proof required | Action | Audit trail |
| --- | --- | --- | --- |
| Missing/stale reconciliation or snapshot | `status.reconciliation_required`, or a release invalidated by digest drift | Run the canonical namespace-aware `SNAPSHOT` command from the operator runbook with `--reconcile --actor <authenticated-actor>`; it reserves a monotonic shared observation before remote reads and installs only through that exact ID | snapshot observation and reconciliation records |
| Expired remote claim | `expires_at` in the claim record has lapsed | Retire the claim ref | `state/releases.jsonl` with proof |
| Claim bound to a retired plan | `plan_fingerprint` in the record differs from the sealed plan | Retire the claim ref | `state/releases.jsonl` with proof |
| Dead worker's live claim | Bare claim commit (tree == parent tree) with **zero work commits** for `claim_stall_minutes` | Retire the claim ref (`--force-with-lease` on the observed head) | `state/releases.jsonl` with `stalled-bare-claim` proof |
| Dead worker's unsealed work | Head idle ≥ `branch_stall_minutes` **and** governing claim expired/plan-superseded/absent | Archive head under the quarantine ref, retire the branch ref, atomically | `state/quarantines.jsonl` |
| Expired global validation lease | `expires_at` in the lease file has lapsed (or is unreadable, which no identity could ever release) | Archive as `EXPIRED_BROKEN`, remove the file | `state/validation-leases/` |
| Invalidated dispatcher release | Any successful healing action (each one changes the pinned evidence by design) | Re-snapshot, re-reconcile, `dispatch` a fresh release | `state/dispatcher-releases.jsonl` |

## What is deliberately NOT proof

- **A stale `target_sha` in a claim record.** The round driver integrates
  sealed heads rooted at a round's original target after siblings advance it,
  so a claim bound to an older target may still complete. Dead claims are
  caught by the stall bound instead.
- **An out-of-scope diff on a live branch.** A worker can revert out-of-scope
  paths before sealing; scope is enforced at receipt validation, not by the
  healer.
- **Silence alone, inside the stall bound.** A worker that has not pushed yet
  is indistinguishable from a slow worker; the stall bounds in
  `.autopilot/healing-policy.json` are the point where the distinction stops
  mattering, and they are the operator's to tune.

## Why a retired false positive is safe

If the healer ever retires the claim or branch of a worker that is actually
alive, git's own concurrency control bounds the damage: the worker's next push
recreates the branch with its full history (claim provenance included), a
competing claim makes that push non-fast-forward so provenance can never be
corrupted, and the worst case is bounded duplicate work — while the old worst
case was an unbounded hang. `--force-with-lease` closes the race at the moment
of deletion itself.

## Dispositions

Every heal pass ends in exactly one disposition, so a caller can act
mechanically instead of guessing:

- `HEALED` — state changed; re-observe immediately.
- `WAITING` — nothing is provably defunct yet; `wake_at` names the earliest
  time at which that can change (a stall bound maturing or a lease expiring).
  Polling before `wake_at` is pointless unless a worker pushes.  A refused
  action (the evidence moved mid-repair) also reports WAITING — the world is
  live.
- `OPEN_SESSIONS` — a valid release authorizes nodes whose branches do not
  exist; the operator cards under `.autopilot/state/host/cards/` are the one
  thing code cannot open on an attended host.
- `RESOLVE_BLOCKERS` — recorded causes lack verified resolutions; each stuck
  entry names the blocker ids and the exact `blocker-resolve` command.  This
  is the orchestrator's judgement work, not a human gate.
- `STUCK_HUMAN` — only sealed/external-authority blockers remain; each entry
  carries the evidence and exact instructions.
- `ACTIONABLE` — dry-run only: actions exist and were withheld.
- `BLOCKED` — healing itself failed (the reconcile subprocess errored); the
  action detail carries the reason.
- `DISABLED` — the policy master switch is off.
- `QUIESCENT` — no candidate needs anything.

`run-round` adds its own integration dispositions on top of these:
`RECONCILE_REQUIRED`, `PENDING` (the public wave is not whole and no recovery mutation ran),
`ROUND_INTEGRATED` (controller-internal validation-disabled calls only), `ROUND_COMPLETE`, and
`VALIDATION_FAILED`.  Repeated stall retirements for the same node double the
stall bound each time and suspend it after three — lease expiry then bounds
the wait — so a slow-but-alive worker cannot be reaped in a loop.

The public loop contract: `run-round --release-id <exact-shared-release>` revalidates the
release and preflights every exact receipt head before triage or Git effects. A partial
wave returns `PENDING` without healing, reconciliation, merge, push, or validation.
Run the canonical host- and namespace-aware `AUTOPILOT` heal command separately, then run
the canonical `SNAPSHOT` command with `--reconcile --actor <authenticated-actor>`, obtain
a fresh dispatcher release, and retry with its new ID. Snapshot acquisition reserves its
monotonic shared observation before `git fetch`
or `gh`, so a slower older observation cannot overwrite the newer one. A whole public
wave always validates after integration; the existing `--no-heal` parser option does not
grant an in-lock recovery path. `execute-wave --apply` may still heal a withheld wave
once before conceding.

## Learning at runtime

Every action and refusal is appended to its ledger with the proof or the
refusal reason, and every heal pass fingerprints the observed evidence into
`state/heal/observations.jsonl`. `evidence_frozen_minutes` in the report says
how long the world has been byte-identical — the difference between "workers
are running" and "polling for no reason" is that number against `wake_at`.

Those healing-observation ledgers remain worktree-local by design even though execution
authority under `.autopilot/state/` is repository-shared, so on their own they teach
nobody. The durable memory is
**`.autopilot/lessons/`, which is committed** — see its README for the format.

**The feedback loop.** An applied repair is not a successful repair. After
every action the healer *re-observes* the node: if the diagnosed wedge is gone
the outcome is recorded `UNBLOCKED`, and if it survived its own repair,
`NO_EFFECT`. Refusals record `REFUSED` and count toward neither, because losing
a `--force-with-lease` race proves nothing about whether the repair works.

**Withdrawal.** Lessons are keyed by mechanism — `<verdict>|<proof kind>|
<action>`, containing no node id, branch, or SHA — so what is learned here
transfers to any repository this control plane drives. Before acting, the
healer consults that record. A mechanism tried at least three times that has
**never once** worked is `DISPROVEN` and withdrawn: the healer stops attempting
it and reports the recorded evidence under `RESOLVE_BLOCKERS` instead. That is
the guarantee that an automatic repair can never become the loop it was written
to end.

**Checking in.** With `commit_lessons` (default on) each heal pass commits new
lessons to the current branch — pathspec-limited to `.autopilot/lessons`, so it
can never sweep in unrelated work, refused on `main`, and authored as
`autopilot-lessons@hive-mind.invalid` so a lesson commit is never mistaken for
a sealed receipt. `push_lessons` (default off) publishes them. Inspect the
record with `autopilot lessons`; commit or publish by hand with
`autopilot lessons --commit [--push]`.

**What healing does not do.** It repairs control-plane *state*, not source
code. A blocker whose repair is a semantic change to a runbook or to product
code is reported, with its evidence and the exact `blocker-resolve` command —
authoring that fix is worker and orchestrator judgement, and receipt validation
is the boundary that keeps it honest. Blocker packets remain the record of
those causes; healing never rewrites them, it only acts on what they prove.
