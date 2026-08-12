# DAG execution handoff — resume from 32/39

Written 2026-08-12 at the end of a session that took the plan from 21 complete
nodes to 32. This is everything the next session needs to finish the remaining
seven without rediscovering what this one learned the hard way.

Branch: `release/hive-mind-os-singleton-20260812-r5` (PR #144). Never touch
`main`.

---

## 0. Start here — the prompt that actually works

Pointing an agent at this file with "complete this handoff" **does not work**.
It was tried; the session oriented itself and stopped after three minutes
without writing a line, because subagents need explicit authorization and the
ask reads as "read this doc" rather than "execute seven engineering nodes."

Paste this instead:

> Finish the Hive Mind OS DAG on branch `release/hive-mind-os-singleton-20260812-r5`.
> Never touch `main`. Read `docs/execution/DAG_EXECUTION_HANDOFF.md` first — it
> has the state, the ceremony, and the traps.
>
> **You have my explicit authorization to spawn parallel subagents** (the Agent
> tool), one per DAG node, for every node whose `file_locks` are disjoint. That
> is the only way this finishes; do not implement seven nodes serially yourself.
>
> Work autonomously to quiescence. Do not stop to ask whether to proceed. For
> each node: spawn a worker with its runbook and write scope → verify its output
> yourself (focused suite green, no tautologies, mandated test count matches the
> runbook, changed paths inside the write scope) → claim → branch from the claim
> commit → commit → seal the receipt → push → integrate with `run-round`.
>
> If a runbook mandates something provably unsatisfiable, do not fake it and do
> not weaken the test: report the `file:line` contradiction, repair the runbook
> in a separate orchestrator commit, and continue. Four runbooks in this plan
> already needed exactly that.
>
> Remaining: BENCH-600, PROMOTE-530, QUALIFY-610, LEGACY-620, A3-700, A4-800,
> A5-900.

Expect this to take hours and many worker sessions. That is the size of the
work, not a symptom of something wrong.

---

## 1. Where the DAG actually is

**32 of 39 nodes COMPLETE and integrated**, all pushed. Integrated this
session: MISSION-400, DURABLE-410, DELIVERY-420, HUMANLESS-430, CHEAT-440,
LEARN-500, SELFHEAL-450, CHALLENGER-510, POISON-540, MIGRATION-460, EVAL-520 —
11 nodes, ~199 new tests, every one verified before its receipt was sealed.

**Seven remain**, and only one pair can run concurrently:

| Round | Node | Depends on | parallel_safe | Notes |
|---|---|---|---|---|
| R15 | `BENCH-600` | EVAL-520 ✅ | true | startable now |
| R16 | `PROMOTE-530` | EVAL-520 ✅ | false | startable now; lock-disjoint from BENCH-600 |
| R17 | `QUALIFY-610` | MIGRATION-460 ✅, PROMOTE-530, BENCH-600 | false | |
| R18 | `LEGACY-620` | QUALIFY-610 | false | touches `workers.py`, which MIGRATION-460 also changed |
| R19 | `A3-700` | QUALIFY-610, LEGACY-620 | false | |
| R20 | `A4-800` | A3-700 | false | |
| R21 | `A5-900` | A4-800 | false | |

**Implementation parallelism and dispatch parallelism are different things —
do not confuse them.** A previous session did, and stalled on it.

- *Dispatch* (who may hold a claim at once) is governed by `parallel_safe`.
  `PROMOTE-530` is `parallel_safe: false`, so the dispatcher gives it its own
  round. BENCH-600 lands in R15, PROMOTE-530 in R16. **That is correct
  behaviour, not a bug** — see the serial-node rule in §5.
- *Implementation* (who may write files at once) is governed by `file_locks`.
  BENCH-600 and PROMOTE-530 have disjoint locks, so two workers can write their
  code simultaneously in one tree.

So: implement BENCH-600 and PROMOTE-530 concurrently, then seal and integrate
them one at a time in separate rounds. Everything after them is sequential in
both senses — no fan-out changes that.

Two workers for BENCH-600 and PROMOTE-530 were launched and deliberately
stopped before they wrote any file, so the tree is clean. Nothing is
half-finished.

---

## 2. The loop

```bash
git fetch origin && git merge --ff-only origin/release/hive-mind-os-singleton-20260812-r5
python .autopilot/bin/github_snapshot.py --reconcile --actor codex:orchestrator
python .autopilot/bin/autopilot.py --repo-root . run-round --actor codex:orchestrator
python .autopilot/bin/autopilot.py --repo-root . execute-wave --apply --actor codex:orchestrator
```

`run-round` heals by default and returns a machine `disposition`:

- `HEALED` — state changed; run it again immediately.
- `ROUND_INTEGRATED` / `ROUND_COMPLETE` — a wave merged.
- `OPEN_SESSIONS` — a released node has no branch; it needs a worker. **This is
  the normal terminal state, not a failure.**
- `WAITING` — carries `wake_at`; polling before then cannot help.
- `RESOLVE_BLOCKERS` / `STUCK_HUMAN` — carries the exact commands.

Use `--skip-validation` while integrating several nodes, then run the gate once
at the end (see §6).

---

## 3. The worker → seal ceremony (proven on 11 nodes)

Implementation and the git ceremony are separate. Workers write code; the
orchestrator does all git.

**Implementation.** Nodes in a wave have disjoint `file_locks` by contract, so
several subagents can work in ONE tree at once. Tell every worker:

- write ONLY its declared `file_locks`;
- no state-changing git (no commit/push/checkout/branch/add);
- never `unittest discover` — it picks up siblings' in-progress files;
- implement every mandated test with the exact mandated names, no tautologies;
- mutate the implementation to prove the suite bites, then revert;
- if the runbook contradicts real source, **report it, never fake it**.

**Sealing (orchestrator, serial).** Use `.autopilot/bin/` verbs:

```bash
python .autopilot/bin/autopilot.py --repo-root . dispatch --actor codex:orchestrator --node <NODE>
CLAIM=$(... claim <NODE> --owner claude:<node>-worker --publish-remote --remote origin | jq -r .remote_claim_commit)
git checkout -B autopilot/<node-lower> "$CLAIM"
git add <exact scope paths>
git commit -F - <<'MSG' ... MSG
python <scratch>/mkreceipt.py <NODE> <owner> <TARGET_SHA> <out.json> "group=cmd=Ran N OK" ...
python .autopilot/bin/autopilot.py --repo-root . verify-receipt <NODE> <out.json>
python .autopilot/bin/autopilot.py --repo-root . complete <NODE> --owner <owner> --receipt <out.json>
git push origin HEAD:refs/heads/autopilot/<node-lower>
git checkout release/hive-mind-os-singleton-20260812-r5
```

Then `run-round` merges it.

### Receipt rules that cost real time to discover

- `base_commit` is the **release target**, NOT the claim commit. The claim
  commit is retained as its direct child inside `base..final`
  (`durable_controller.py:470-511` requires exactly one retained claim,
  parented by base, carrying base's tree).
- `role_identities` must cover **all eight** kernel roles, not just the ones
  that did work.
- `authority` needs `node_id`, `autonomy_level`, and a `grants` **list**.
- `changed_paths` must equal the node's write scope exactly.

A receipt generator lives in the session scratchpad as `mkreceipt.py`; it is
~90 lines and worth recreating (it derives every identity from git rather than
being told).

### The seal-script trap that bit once

`set -e` does **not** catch a failure inside `$(...)`. A refused claim produced
an empty `CLAIM`, `git checkout -B <branch> ""` failed, and the node's work was
committed onto the **release branch** and pushed to the node ref. Always:

```bash
test ${#CLAIM} -eq 40 || { echo "REFUSING: bad claim"; exit 1; }
git checkout -q -B autopilot/<node> "$CLAIM"
test "$(git rev-parse --abbrev-ref HEAD)" = "autopilot/<node>" || exit 1
```

Recovery, if it happens again: archive the mispushed ref under
`refs/hive-mind-autopilot/quarantine/operator-error/`, delete the branch ref,
then `git reset --mixed` (**never `--hard`** — concurrent workers' files live
in the working tree).

---

## 4. Verify before you seal — every time

A receipt is a claim about evidence. Check it yourself; do not trust the
worker's summary. On MISSION-400 the delivered suite asserted 2 of 7 mandated
authority cases and one was `assertTrue(True)`; sealing it would have published
a false claim.

```bash
PYTHONPATH=src python -m unittest tests.<module>          # green?
grep -nE "assertTrue\(True\)|assertFalse\(False\)|unittest.skip|expectedFailure" <test file>
grep -cE "def test_" <test file>                          # matches the runbook's mandated count?
git status --short                                        # only the declared scope?
```

For evidence files, prove they are machine-produced: hash, regenerate, hash
again, and require byte-equality. Both HUMANLESS-430 and EVAL-520 passed this;
it is cheap and it is the difference between evidence and decoration.

---

## 5. Traps already fixed — do not re-introduce

- **`PYTHONPATH=src` is mandatory.** Without it `hive_mind_os` resolves to an
  editable install at `~/.codex/worktrees/1a44/hive-mind-os/src` — a different
  checkout. Three workers hit this independently. All 55 runbook commands are
  now pinned (`db9ca20`), and the round's leased gate pins it too (`7ec26c5`).
- **CLI dispatcher ignored `parallel_safe`** (`a0a84c8`). It seated a serial
  node beside parallel siblings, producing a release its own validator rejected
  — `ready` empty forever while the healer rewrote the same invalid wave every
  pass. Regression test: `.autopilot/tests/test_dispatch_wave_selection.py`.
- **Windows long paths.** `git clone` of this repo fails on Windows with
  "Filename too long" on some `evidence/` paths. Use
  `git -c core.longpaths=true clone`, or validate in the existing working tree.
- **Windows SQLite teardown.** Close every `KernelStore` BEFORE its
  `TemporaryDirectory` is removed or teardown dies with `WinError 32`.

---

## 6. The repo-wide gate

Workers run focused tests only. The repository-wide pass is the integrator's
single leased run per round:

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

Run it only when no worker is writing — discovery otherwise picks up
in-progress files and the verdict is meaningless. `run-round` runs it
automatically unless `--skip-validation` is passed.

**Last full run on this branch: `Ran 958 tests`, 2 errors, 7 skipped — and both
errors were environmental, not regressions.** `tests/test_hive_cortex_explorer`
fails whenever ANY `GIT_*` variable is exported, because `explorer.py`
`_git_environment` rejects inherited Git environment outright. Agent harnesses
commonly export `GIT_EDITOR`. Proof:

```
PYTHONPATH=src python -m unittest tests.test_hive_cortex_explorer          # FAILED (errors=2)
env -u GIT_EDITOR PYTHONPATH=src python -m unittest tests.test_hive_cortex_explorer   # OK
```

`default_validation_runner` now strips `GIT_*` from the environment it hands
the gate, so the automated round validation no longer reports these. If you run
the suite by hand from a shell that exports `GIT_EDITOR`, unset it first or you
will chase a phantom failure.

**Do not run the gate through `| tail`** — the pipe buffers everything until
exit, so a 21-minute run is indistinguishable from a hang. Redirect to a file
and inspect it instead.

---

## 7. Expect runbook defects, and repair them as the orchestrator

Four runbooks mandated assertions that were provably unsatisfiable. This is the
most common blocker in this plan, and the correct response is never to weaken
the test:

1. **MISSION-400** — `projection()` vs `rebuild_projections()`; the rebuild
   carries evaluation digests the materialized read model never rehydrates.
2. **DURABLE-410** — the same comparison, plus `state_digest` vs
   `status()["state_digest"]` (fixed in `db9ca20`).
3. **SELFHEAL-450** — required appending a `self_healing.pass` event. The
   reducer is CLOSED, `projection.py` is under the sealed `event-schema` lock,
   and CHEAT-440's evidence asserts the spine refuses invented event types.
   **No node may fix this**; admitting a type would be the very cheat CHEAT-440
   detects. Now asserts fail-closed (`b17a7fb`).
4. **MISSION-400 / "no ACCEPTED transition"** — unsatisfiable because roles
   before the builder pass honestly and are accepted (fixed in `2eecea5`).

The pattern: find the satisfiable invariant that **preserves the sealed
criterion's intent**, correct the runbook in a **separate orchestrator commit**
(so the node's `changed_paths` stays inside its write scope), and cite the
`file:line` contradiction plus a measurement in the commit message.

Known open discrepancies for whoever does the remaining nodes:

- `EVAL-520.md:301` says `__all__` lists twelve symbols; the section defines
  thirteen. All thirteen are exported.
- EVAL-520 emits the holdout key `prediction_digest`
  (`evaluation_runtime.py:532`, field declared at `:141`); its runbook prose
  said `prediction_digest_or_null` (`EVAL-520.md:290`). Bind to what the source
  emits. This entry previously named PROMOTE-530 as the consumer; that was
  wrong. `PROMOTE-530.md:382` forbids importing `evaluation_runtime`, and the
  sealed `promotion.py` imports no evaluation symbol, so the mismatch has no
  surface in that node. It stays open for whichever node actually reads holdout
  records.
- MIGRATION-460 enqueue payloads now carry a `runtime` key, changing the
  payload digest, so a job pending from an older binary will not dedupe against
  a re-enqueue.
- `SELF_HEALING.md` records an open obligation: a node owning `projection.py`
  must admit `self_healing.pass` before the durable pass append can succeed.

---

## 8. Two cautions for BENCH-600 specifically

It is the easiest node in the plan to fabricate. Require that every published
number in `docs/benchmarks/HIVE_CORTEX_RESULTS.md` comes from a real run with a
reproducible command, and that anything unmeasurable in this environment is
stated as such rather than estimated. A plausible-looking benchmark nobody ran
is worse than a missing one.

`QUALIFY-610` aggregates the qualification evidence of everything before it —
it should be given the receipts and evidence paths of the completed nodes
rather than being asked to re-derive them.

---

## 9. Housekeeping

- `identtest/` sits untracked at the repo root (a nested git repo with a
  stray `.autopilot/lessons/x.jsonl`). It is untracked and every seal uses
  explicit pathspecs, so it has never entered a commit. Left in place because
  its provenance is unconfirmed; safe to delete if you know it is scrap.
- `.autopilot/lessons/` is the committed healing memory — inspect with
  `autopilot lessons`. It is keyed by mechanism, not by incident, so it stays
  true in any repository this control plane drives.
