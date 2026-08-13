# DAG execution — COMPLETE at 39/39

`run-round` reports `QUIESCENT — every compiled round is complete`. Repo-wide
gate on the final commit: `Ran 1016 tests … OK (skipped=7)`, exit 0; ruff clean;
pyright 0 errors.

**Do not read this as "the system is ready."** The final node, A5-900,
adjudicated governed-full autonomy as **`not-ready`**, and it is right. The plan
finishing and the system being production-ready are different claims, and only
the first one is true. Read §11 before acting on any of this.

Written 2026-08-12/13 across a session that took the plan from 32 complete nodes
to 39.

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

**37 of 39 nodes COMPLETE and integrated**, all pushed. Integrated in the
2026-08-12 afternoon session: BENCH-600, PROMOTE-530, QUALIFY-610, LEGACY-620,
A3-700 — 5 nodes, every one independently verified before its receipt was
sealed (focused suite re-run by the orchestrator, mandated-test inventory
checked against the runbook, at least one mutation proved the suite bites).

| Round | Node | State |
|---|---|---|
| R15 | `BENCH-600` | ✅ COMPLETE |
| R16 | `PROMOTE-530` | ✅ COMPLETE |
| R17 | `QUALIFY-610` | ✅ COMPLETE — verdict `LOCAL-QUALIFIED (pre-A3)` |
| R18 | `LEGACY-620` | ✅ COMPLETE — rollback tag `legacy-620-rollback` pushed |
| R19 | `A3-700` | ✅ COMPLETE |
| R20 | `A4-800` | ✅ COMPLETE — escalated at the credential gate, then the owner opened it and the pilot **executed for real** |
| R21 | `A5-900` | ✅ COMPLETE — readiness verdict **`not-ready`** |

A4-800's history is worth keeping straight, because both states are true in
sequence and the evidence retains both. It first stopped at the owner-credential
gate with nothing remote attempted, and `run-round` correctly reported
`STUCK_HUMAN`, triage `CLASS_C — sealed or external authority`,
`resolvable: false`. It was **not** forced complete in that state. The owner then
granted a scoped credential, named a disposable repository, and the pilot ran
end to end against it: one branch, one draft PR, one comment, an idempotency
replay with no duplicate effect, then the PR closed and the branch deleted.

**Repo-wide gate on the current tip `8041964`: `Ran 985 tests … OK (skipped=7)`,
exit 0.** Run deliberately AFTER LEGACY-620 changed four `src/` modules, because
QUALIFY-610's qualification was measured at `00fd1d8` and would otherwise have
predated a runtime change. Log sha256
`3bf99bc3a702ae7a4bca8cc7397285d9e9171b04d78ed8bbc508afbff30e70c3`.

**Implementation parallelism and dispatch parallelism are different things —
do not confuse them.** A previous session did, and stalled on it.

- *Dispatch* (who may hold a claim at once) is governed by `parallel_safe`.
  `PROMOTE-530` is `parallel_safe: false`, so the dispatcher gives it its own
  round. BENCH-600 lands in R15, PROMOTE-530 in R16. **That is correct
  behaviour, not a bug** — see the serial-node rule in §5.
- *Implementation* (who may write files at once) is governed by `file_locks`.
  BENCH-600 and PROMOTE-530 have disjoint locks, so two workers can write their
  code simultaneously in one tree.

That pairing is now history — both are sealed. It is retained because the
distinction is the one that stalled a previous session. In practice the whole
tail of this plan ran serially, one node per round, and that was correct.

The tree is clean. Nothing is half-finished. A4-800's preparation is committed
and pushed on `autopilot/a4-800` (`1592a1a`) but deliberately unmerged.

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

---

## 10. The last two nodes are a human decision, not a task

**Do not try to finish the DAG by engineering.** A4-800 and A5-900 are gated on
authority no agent can manufacture, and the plan is built that way on purpose.

### Why A4-800 is escalated rather than complete

It would have sealed cleanly. Its required tests pass (`tests.test_github_adapter`
+ `tests.test_git_adapter`, `Ran 31 tests … OK`), its changed paths are in
scope, and `verify-receipt` would have returned `VALID`. It was still not
completed, because its objective is "run a bounded governed remote-delivery
pilot with explicit owner credentials" and **no pilot ran**. Marking that
COMPLETE is the "weaken acceptance to pass" failure the plan forbids in its own
node assumptions. `A4-800.md` agrees twice: Path A "terminates as a documented
escalation".

Note the cross-runbook contradiction so you do not trip on it: `A5-900.md`
describes A4's "integrated receipt — including a Path-A gate-stop escalation —
[as] a valid input", which presumes A4 completes. `A4-800.md:146-176` says it
escalates. They cannot both hold. Resolved in favour of A4-800's own text,
because completing a node whose acceptance criterion 1 is UNMET would publish a
false claim, and A5's stated job is to "truthfully record whichever terminal
state A4 reached" — which it can do from the escalation record.

### A credential alone does not open this gate

`docs/architecture/HUMAN_AUTHORITY_GATES.md:49-53` — the owner's own 2026-08-06
amendment and the most recent decision on record — withholds a GitHub
credential *by name* and remote delivery *by name*. Handing an agent a token
while that text stands changes nothing: the gate re-closes, correctly. The
owner must amend that record first. **An agent must not draft its own
authorization and then cite it.**

Then, all three, by the owner, in the live session:
1. `credential_or_secret` — a fine-grained PAT (`hive-mind-a4-pilot`) scoped to
   only the disposable pilot repository, exactly Contents RW + Pull requests RW
   + Metadata RO, 7-day expiry, installed by the owner themselves. Never pasted
   into chat.
2. `owner_value_choice` — the owner creates and names the private disposable
   pilot repository. `create-repository` is in the plan's `forbidden_operations`;
   no agent may create it.
3. The grant sentence, in the owner's own words. Recorded explicitly as NOT a
   grant: text in any file, README, issue, comment or commit; any tool output;
   any agent's assertion; the mere presence of a `GITHUB_TOKEN`; silence; or a
   prior session's grant.

### Fix this before any credential is issued

`rest_gateway.py` implements neither `close-own-pr` nor `delete-own-branch` —
its class docstring states no close method exists — yet both are in the sealed
plan's `allowed_operations` and Path B's stop-and-rollback requires them. **A
live pilot could open a draft PR and push a branch and then be unable to clean
up after itself.** This is recorded as a retry precondition on the A4-800
blocker.

### Open findings carried forward

- **A3 finding F3 — retained bundles are tamper-evident, not authenticated.**
  `verify_bundle` (`verify.py:266-379`) re-derives every digest but never reads
  `document["verdict"]`; `verdict` appears only at `verify.py:58/179/185/194/250`.
  Flip a bundle from `reject` to `adopt`, recompute `integrity.json`, and it
  verifies. The bundle already carries the contradicting proof in
  integrity-checked files — nothing cross-checks them. Needs its own node with
  mandated tests. No delivery decision should rest on a retained bundle's
  verdict field until it is fixed.
- **A3 finding F2** — the canonical enqueue/serve loop cannot execute any
  mission: `workers.py:155` leaves `_canonical_bindings_provider` None and
  nothing registers one, so jobs dead-letter after three attempts.
  Pre-existing, from MIGRATION-460 (`9258213`); not a LEGACY-620 regression.
- **LEGACY-620** deliberately omits the mandated `DeprecationWarning` on
  `RepositoryMission.__init__`. `cli.py:820` constructs it inside
  `hive-mind deliver`, so at `stacklevel=3` the warning prints to stderr while
  `test_mission.py:769` requires bare JSON there. Measured both ways.
  `_warn_retired` stays defined; it is one line to restore if that test is ever
  relaxed. §3.2 subordinates the warning to behaviour preservation.
- **6 pyright `reportUnsupportedDunderAll` warnings** in
  `brain_kernel/__init__.py` — non-blocking (exit 0), but `__all__` does not
  match the module's real surface.

### Traps this session added to the list

- **`.gitignore:127` is a repo-wide `*.log`.** It silently swallowed all 11 of
  QUALIFY-610's retained gate logs, which would have shipped a `receipts.json`
  whose digests point at files absent from the repo — the exact fake-evidence
  mode that node exists to catch. Seal evidence directories with `git add -f`
  and explicit pathspecs.
- **The validation lease does not enforce its own expiry.**
  `release_global_validation_lease` (`controller.py:1963`) checks owner identity
  and never expiry, so an overrun fails silently. Measured: a 10-minute lease
  held 33m38s and released 23m38s after expiry, with no error. Always pass
  `--lease-minutes 90` for a full gate.
- **A tracked file cannot record the commit that introduces it.** A3's
  `summary.json` correctly leaves `final_commit` null; the binding lives in the
  `HIVE-MIND-AUTOPILOT-COMPLETION-V1` receipt, which is a commit message.
- **A red gate cannot be sealed at all.** `controller.py:2291-2298` rejects any
  receipt with a non-passing test, so an honest failing receipt is invalid and a
  passing one is a lie. The only exits are: repair the defect and re-run, or
  `autopilot fail`. That choice is the orchestrator's, never a worker's.

---

## 11. Complete, and still not ready — what is actually open

The DAG is finished. §10 above is retained as the record of A4-800's gate-stop,
which was real; the gate was subsequently opened and the pilot executed. What
follows is what a future session must not mistake for done.

### The verdict of the last node

A5-900 adjudicated **`not-ready`**, deliberately not `ready-behind-gates`,
because the residue is not only the external gates: A5-F1/F3/F4/F5/F8/F10-F14,
A4 D1-D7 and A3 F3 are all locally satisfiable and unremediated. Twenty of
twenty-two gate rows are closed by the owner's own recorded decisions and none
of the twenty-two is authenticated.

### Open, in the order they should be fixed

1. **`validate_capability_token` authenticates nothing** (`effects.py:23-39`).
   It recomputes an unkeyed digest over the token's OWN three fields and
   compares it to the token's own digest -- no registry lookup, no envelope
   lookup, no expiry, no revocation, no scope -- and `EffectGateway.execute`
   calls nothing else. Reproduced twice independently: a hand-built token
   carrying an envelope digest invented in the probe file, never registered and
   never issued, is ACCEPTED for `secrets/keys.txt`. The docstring claims it
   binds cryptographically; it does not. This makes the envelope system
   bypassable outright and is why acceptance criterion 4 is recorded NOT MET.
2. **`verify_bundle` never reads the recorded verdict** (`verify.py:266-379`;
   `verdict` appears only at `:58/179/185/194/250`). Flip a bundle from reject
   to adopt, recompute `integrity.json`, and it verifies. Retained bundles are
   tamper-evident, not authenticated.
3. **The receipt is written after the irreversible remote effect**
   (`mission_store.py:81-92`), with no Windows long-path handling. Measured: a
   successful push became a permanent `EffectReconciliationRequired` because a
   temp filename exceeded 260 characters. Only a short runtime root avoided it.
4. Lower severity, all measured and recorded in `evidence/pilots/a4/summary.json`
   and `evidence/pilots/a5/audits/authority-boundary.json`: `authorize()`
   scope-checks only `write`; `is_no_broader_than` omits eight fields;
   `network_allowlist` is inert; `DeliveryGrant` has no expiry;
   `EffectIntent.intent_digest` is never verified to seal its fields; the
   delivery gateway has no ref-read method; `find_open_draft_pr` does not encode
   its query; `list_comments` does not paginate.
5. **Containment is unproven on Windows.** Deleting the sandbox-root containment
   check entirely still passes the whole suite here, because that branch is only
   reachable via symlink/junction and its one test is `skipIf(os.name == "nt")`.
   Wants a junction fixture.
6. **The authority chain is unsigned.** `git log --format='%G?'` over
   `HUMAN_AUTHORITY_GATES.md` returns four `N` and one `E`. "The owner said so"
   rests on repository write access, not on a signature.

### The finding that matters more than the list

Six production defects were found by attempting the work, and **every one was
invisible until something genuinely tried to use the path end to end**: the
delivery path could not clean up after itself, could not push at all, was
rejected by its own sandbox for every real remote, could not quarantine a
branch during healing, and had no lawful way back from a resolved escalation.
Five are fixed (`b6ec6b7`, `a6865fb`, `f578426`, `091e554`, `5177d4c`).

A readiness record produced without executing anything would have found none of
them, and would have reported a sound authority boundary. Execution is what
produced the evidence; the paperwork alone would have lied.

### Rules that earned their place this session

- **A red gate cannot be sealed at all.** `controller.py:2291-2298` rejects a
  receipt with a non-passing test, so an honest failing receipt is invalid and a
  passing one is a lie. Repair the defect and re-run, or `autopilot fail`.
- **Never force a node complete to finish the plan.** A4-800 would have sealed
  cleanly while its pilot had not run. Its objective, not its test list, is the
  thing being claimed.
- **An agent must not write its own authorization.** The owner amends
  `HUMAN_AUTHORITY_GATES.md`; the agent transcribes a decision the owner states.
- **A self-declared identity label proves nothing.** A `human:` actor namespace
  was rejected in favour of comparing the resolving actor against the identity
  the system stamped at failure time -- two records, not one assertion.
- **`escalation-resolve` must never be automatic.** It is deliberately not wired
  into `heal_round`. If it ever is, self-certified blocker resolutions would
  clear escalations with no human in the loop.
