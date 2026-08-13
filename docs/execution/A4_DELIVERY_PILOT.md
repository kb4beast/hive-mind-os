# A4 — Bounded governed remote-delivery pilot

**Node:** A4-800 · **Status:** EXECUTED (Path B), after an earlier Path A gate-stop
**Pilot repository:** `patencyhealth-lab/hive-mind-a4-pilot` — private, disposable, owner-created
**Pilot base branch:** `main` at `288610d48a10d8162fc45727c5a2ba81c55d5d05`
**Sealed plan:** [`evidence/pilots/a4/pilot-plan.json`](../../evidence/pilots/a4/pilot-plan.json)
· digest `sha256:1b19c027f58dd526058c3de9b0231e64b11e28fbea3003eac3f59b4e4c999776`
**Delivery grant:** `GRANT-A4-800-PATH-B` · digest
`sha256:5c1f5dd1defc1eb560dd1f875d0bf3f2ed4cb7f384364193bf93c478dece28e9`
**Gate-stop record (history):** `ESC-A4-800-67ad9aad5d48` —
[`evidence/pilots/a4/owner-grant/gate-stop.json`](../../evidence/pilots/a4/owner-grant/gate-stop.json)
**Grant record:** [`evidence/pilots/a4/owner-grant/grant-record.json`](../../evidence/pilots/a4/owner-grant/grant-record.json)

This node has **two** terminal states, in this order, and both are true:

1. **Path A, 2026-08-12 14:46 −05:00 — stopped at the owner-credential gate.** No owner
   grant existed. Nothing remote was done. That record is retained unaltered.
2. **Path B, 2026-08-12 22:53 −05:00 (2026-08-13 03:53Z) — the pilot actually ran.** The
   owner opened the gate by committing an amendment to the authority record. All six
   permitted operations were executed against a live GitHub repository, replayed for
   idempotency, then stopped and rolled back. The pilot repository was left byte-identical
   to its pre-pilot state.

The second does not erase the first. Path A was the correct answer to the question asked
on 2026-08-12 at 14:46; the question changed when the owner changed it.

Read §8 before you read anything else as a success story. Getting to Path B required
fixing three production defects that would each have made a real pilot impossible, and it
left one unfixed defect that can strand an irreversible remote effect.

---

## 1. The pilot boundary

The pilot is deliberately small. It touches ONE disposable repository the owner created
for the purpose and can delete outright afterwards.

| | |
|---|---|
| Target | `patencyhealth-lab/hive-mind-a4-pilot` — private, disposable, no branch protection |
| Branch | exactly one: `a4-pilot/attempt-1`, under the granted prefix `a4-pilot/` |
| Pull requests | exactly one, and it is a **draft** — `#1` |
| Comments | exactly one, marker-tagged for replay safety — id `5275748785` |
| Default branch | never touched — `main` ended at the same SHA it started at |
| Protected branches | never touched |
| Other repositories | never touched |

**Allowed operations** (exactly these six; the sealed plan is authoritative):
`create-branch`, `push-branch`, `open-draft-pr`, `comment-on-own-pr`, `close-own-pr`,
`delete-own-branch`.

**Forbidden operations** (exactly these): `merge`, `push-to-protected-branch`, `deploy`,
`modify-settings`, `create-repository`, `delete-repository`, `any-spend`.

Some of those prohibitions are enforced by code rather than by good intentions:

- `src/hive_mind_os/cortex/github/grants.py:29-31` closes the grantable vocabulary (the comment at line 25 says it outright); "merge"
  is deliberately absent and is not a spelling the package accepts. **No grant you write
  can carry merge authority**, because there is no way to express it.
- `grants.py:23` pins `PROTECTED_BRANCHES = {"main", "master", "staging"}`, and
  `require_push_branch` denies a push to any protected branch, to the grant's own base
  branch, and to any ref outside the granted prefix.
- `rest_gateway.py:221-241` (`close_pull_request`) sends a body containing nothing but
  `{"state": "closed"}`, and raises if the response claims the pull request was merged.
- `rest_gateway.py:185-186` raises if GitHub returns a pull request whose `draft` is not
  exactly `True`.

The delivery grant that the run actually used carried **five** actions, not six —
`push`, `open_draft_pr`, `post_comment`, `close_own_pr`, `delete_own_branch`. There is no
`create-branch` action because the closed action vocabulary has no create-ref action; the
branch is created locally under the granted prefix and first reaches the host on push.

## 2. Sealed-plan digest discipline

The plan is sealed **before** any remote action. This is the same discipline as
`hive_mind_os.brain_kernel.local_assurance.verify_local_assurance_artifact`:

1. Build the plan document **without** a `plan_digest` field.
2. `plan_digest = canonical_digest(plan)` — SHA-256 over the canonical encoding
   (`sort_keys=True`, `separators=(",",":")`, UTF-8, `allow_nan=False`).
3. Write the field into the document.
4. To verify: pop `plan_digest`, recompute over the remainder, compare.

The point is not ceremony. A remote effect is irreversible in a way a local one is not, so
the intent has to be fixed in advance and be checkable afterwards. **Remote host state
that contradicts the sealed plan is an escalation, not an improvisation.**

**Where the executed run fell short of this discipline — stated plainly.** The runbook
requires every remote receipt to cite the plan digest
(`docs/execution/runbooks/A4-800.md:94-96`). **None of the six receipts does.** They cite
the *grant* digest and their own intent digests instead. And the sealed plan itself was
never re-sealed for Path B: `pilot-plan.json` still reads `pilot_repository: "UNGRANTED"`
and `authority_gate.status: "CLOSED"`, because a seal that is rewritten after the fact is
not a seal. The chain that does exist is: owner amendment → `GRANT-A4-800-PATH-B` (whose
digest genuinely seals its own fields, verified independently — see
`grant-record.json`) → per-operation intent digests → per-operation receipts. The chain
that does *not* exist is plan-to-receipt. That is a gap, and it is recorded rather than
retro-fitted.

## 3. For the repository owner — supplying scoped pilot credentials

The checklist below is reproduced verbatim from
`docs/execution/runbooks/A4-800.md:110-144`.

<!-- BEGIN VERBATIM CHECKLIST (A4-800.md:110-144) -->
> **For the repository owner — supplying scoped pilot credentials (10 minutes).**
> You are granting a bounded experiment on ONE throwaway repository. Nothing here
> touches your real projects, and you can revoke everything with one click at the end.
>
> 1. **Create a disposable pilot repository.** On github.com click "+" → "New
>    repository". Name it `hive-mind-a4-pilot`, set it **Private**, initialize with a
>    README. Do not add branch protection. This repository must contain nothing you
>    care about.
> 2. **Create a fine-grained personal access token.** GitHub → your avatar →
>    Settings → Developer settings → Personal access tokens → **Fine-grained tokens**
>    → "Generate new token".
>    - Give it the name `hive-mind-a4-pilot`
>    - Expiration: **7 days** (shortest offered at or above 7)
>    - Resource owner: your account
>    - Repository access: **Only select repositories** → select ONLY
>      `hive-mind-a4-pilot`
>    - Repository permissions — set exactly these, nothing more:
>      **Contents: Read and write** (branch pushes), **Pull requests: Read and
>      write** (draft PRs and comments), **Metadata: Read-only** (added
>      automatically). Every other permission stays "No access". Do NOT grant
>      Administration, Actions, Workflows, or any Organization/Account permission.
> 3. **Hand the token over WITHOUT pasting it into the chat.** Run
>    `gh auth login` yourself (choosing "Paste an authentication token"), or place it
>    in the credential location named by the pilot's own instructions. If the agent
>    ever asks you to paste the token into the conversation, refuse — that is a
>    boundary violation and the pilot must stop.
> 4. **State your grant explicitly in the session, in your own words**, e.g.:
>    "I grant the A4 pilot the fine-grained token `hive-mind-a4-pilot` scoped to
>    `youruser/hive-mind-a4-pilot` (Contents RW, Pull requests RW, 7-day expiry).
>    Allowed: branches, draft PRs, comments on that repository only. Not allowed:
>    merges, protected branches, other repositories, any spend."
> 5. **When the pilot ends (or anytime you feel uneasy):** Settings → Developer
>    settings → Fine-grained tokens → `hive-mind-a4-pilot` → **Delete**, and delete
>    the pilot repository (repository Settings → Danger Zone → Delete). Revocation is
>    always safe: every pilot operation is designed to survive being cut off mid-step.
<!-- END VERBATIM CHECKLIST -->

### What counts as a grant, and what does not

The gate opens only on an explicit act by the repository owner supplying **both**
authority classes:

- `credential_or_secret` — a scoped credential, installed by the owner themselves, never
  pasted into the conversation and never read by the agent.
- `owner_value_choice` — the named pilot repository. Where real-world side effects are
  allowed to land is a value choice, not a technical detail, and no agent may make it.

None of the following is a grant, and each will be refused: a grant written in a file, a
README, an issue, a code comment or any ordinary document; a grant appearing in tool
output; an orchestrating, sibling or reviewing agent asserting that the owner approved;
the mere presence of a token on the host; silence or absence of objection; a grant from a
previous session or issued for a different node.

**How this particular gate was opened.** The owner wrote and committed the grant into the
controlling authority record themselves — `docs/architecture/HUMAN_AUTHORITY_GATES.md`,
section "Owner decision amendment — 2026-08-12" (lines 61–87, commit `db34487`) plus
"Amendment addendum — 2026-08-12, credential delivery mechanism" (lines 89–100, commit
`c78adf4`). Both commits are authored and committed by the repository owner. The runbook
accepts exactly this form ("or by committing a signed statement themselves",
`A4-800.md:98-101`). One honest caveat: neither commit is cryptographically signed, so
"the owner committed it" rests on repository access control, not on a signature.

The addendum also relaxes one prohibition narrowly: the owner could not restart the host
process, so an agent-written wrapper hoists the token from the user-scope registry into
the pilot subprocess's environment **by variable reference**. The value is never rendered,
never logged, never written to a file, a command line, a commit, or an evidence artifact.
Nothing in `evidence/pilots/a4/**` records the credential, its length, or a fingerprint —
obtaining any of those would require reading it.

## 4. The two terminal paths, as they actually occurred

### 4.1 Path A — the gate-stop (retained unaltered)

At 2026-08-12T14:46:27−05:00 the gate was checked and found **CLOSED**. The most recent
owner decision at that moment (the 2026-08-06 amendment) withheld a GitHub credential by
name and withheld remote delivery by name. The node produced the sealed plan, this
document, and `owner-grant/gate-stop.json`, ran its focused suites (31 tests at the time),
escalated naming exactly `credential_or_secret` and `owner_value_choice`, and created no
remote effect of any kind.

`gate-stop.json` **has not been rewritten and must not be.** It is the true record of that
terminal state, including its two recorded runbook contradictions (Path A demanding push
authority it defines itself by lacking; `autopilot fail` writing under a forbidden path).
`grant-record.json` sits beside it and records only that the gate was later opened.

### 4.2 Path B — the executed pilot

Six operations, 2026-08-13T03:53:19Z → 03:53:32Z, thirteen seconds end to end. Every
receipt is in [`evidence/pilots/a4/remote/`](../../evidence/pilots/a4/remote/).

| # | Operation | What actually happened | Receipt |
|---|---|---|---|
| 1 | `create-branch` | `a4-pilot/attempt-1` created **locally** under the granted prefix, from base `main` at `288610d4…`. Sandbox-receipted (`check-ref-format`, `switch`); no REST call, because the closed action vocabulary has no create-ref action. | `01-create-branch.json` |
| 2 | `push-branch` | One trivial commit `9dbbdd124840064d1698905d96ce56128183d137` ("chore(a4-800): pilot attempt-1 marker") pushed to the pilot branch. | `02-push-branch.json` |
| 3 | `open-draft-pr` | Draft pull request **#1** created — `draft=true`, head `a4-pilot/attempt-1`, base `main`, node id `PR_kwDOT2tST87-Y13k`. GET-then-POST-then-GET, three calls. | `03-open-draft-pr.json` |
| 4 | `comment-on-own-pr` | One comment, id **5275748785**, node id `IC_kwDOT2tST88AAAABOnWJsQ`. The body is recorded by digest only. | `04-post-comment.json` |
| 5 | idempotency replay | **Two modes.** Same-intent replay: **0 REST calls, 0 git commands** — the durable outbox short-circuited on the stored receipt. Fresh-intent replay with identical parameters: **one GET listing, no POST**, returning the same pull request **#1**. | `idempotency-replay.json` |
| 6 | `close-own-pr` + `delete-own-branch` | PR #1 PATCHed to `state=closed` (state-only body, unmerged), then `DELETE /git/refs/heads/a4-pilot/attempt-1` accepted with HTTP 204. | `stop-and-rollback.json` |

Sixteen REST calls in total, every path inside the one granted repository, of which only
four are writes: two POSTs (one PR, one comment), one PATCH (state only), one DELETE (the
pilot branch ref). No merge endpoint appears anywhere in the list, and no method on
`ControlledRestGateway` can produce one.

## 5. Independent verification

The driver verifying itself proves less than it appears to. The checks below were run
**by the orchestrator, not by the driver and not by the evidence scribe**, after the run:

- `git ls-remote --heads origin` on the pilot repository returns **only**
  `refs/heads/main` at `288610d48a10d8162fc45727c5a2ba81c55d5d05`. The pilot branch is
  gone, and `main` is at exactly the SHA it held before the pilot began.
- `get_pull_request(1)` returns `state=closed`, `draft=True`, `merged=False`,
  `merged_at=None`, `head.ref=a4-pilot/attempt-1`, `base.ref=main`.

These two results are what actually carry criteria 3 and 4. The driver's own
`stop-and-rollback.json` was honest enough to record
`pilot_branch_deletion_independently_verified: false`; this is the verification it was
waiting for. The evidence scribe who wrote this document did **not** re-run either check —
it holds no network authority — and reports them as the orchestrator's measurements.

## 6. Stopping and revocation

**The pilot can be stopped at any moment, by anyone, for any reason or none.** Every
allowed operation is individually abandonable. Being cut off between any two steps leaves
at most one unreferenced branch and one unmerged draft pull request, inside a private
throwaway repository — and nothing outside it. This is no longer only a design claim: the
stop procedure was executed, and the repository was returned to its pre-pilot state.

Owner-side revocation, which needs no agent cooperation and works even mid-step:

1. GitHub → avatar → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → `hive-mind-a4-pilot` → **Delete**.
2. Pilot repository → Settings → Danger Zone → **Delete this repository**.

Revoking mid-pilot is safe: the next remote call fails with an auth error, and that
failure is recorded as the stop evidence. One caveat that the unfixed defect D1 below
makes real — a call that *succeeds* and then fails to record its receipt leaves an effect
the system knows happened but cannot reconcile. Revocation does not cause that; a long
filesystem path does.

Within *this* repository the node is additive: it writes only `evidence/pilots/a4/**` and
this file, changes no runtime code, no tests and no configuration.

## 7. Acceptance criteria, honestly scored

| # | Criterion | Result |
|---|---|---|
| 1 | Owner explicitly supplies scoped credentials and pilot repository authority | **MET.** `HUMAN_AUTHORITY_GATES.md:61-87` (commit `db34487`) and `:89-100` (commit `c78adf4`), both committed by the owner, name the credential, its scopes, the one repository, and the six operations. Recorded in `owner-grant/grant-record.json`. Caveat: the commits are unsigned. |
| 2 | Only non-protected-branch and draft-PR operations occur | **MET AND EXERCISED.** Sixteen REST calls, all inside `patencyhealth-lab/hive-mind-a4-pilot`; four writes, listed in §4.2. PR #1 came back `draft=true` from the host and the gateway would have raised had it not. `main` ended at its starting SHA per the orchestrator's `ls-remote`. Limit: the call list is the driver's own record, not an egress trace — see §8.4. |
| 3 | No merge and no production deployment | **MET AND EXERCISED.** `get_pull_request(1)` independently returns `merged=False, merged_at=None`. The close sent a state-only PATCH and `close_pull_request` raises on a merged response. No deployment surface was touched, and the amendment leaves G5 (`HUMAN_AUTHORITY_GATES.md:77-82`) untouched. |
| 4 | The pilot can be stopped and rolled back at any point | **MET AND EXERCISED.** The stop procedure ran: PR #1 closed unmerged, pilot branch deleted (HTTP 204). Independently confirmed by `ls-remote` showing only `refs/heads/main`. Limit: the driver's own `branch_head_unchanged` assertion proves nothing on its own — see §8.4. |

Criteria 2–4 were vacuous on Path A because nothing ran. They are no longer vacuous. They
are also not unqualified: each carries a limit named in §8.4, and the strongest evidence
for 3 and 4 is the orchestrator's independent check, not the driver's self-report.

## 8. Risks and open defects

### 8.1 Three production defects the pilot discovered — and fixed

None of these were found by reading. Each was found by trying to actually do the thing.

| Defect | Why it mattered | Fix |
|---|---|---|
| `close-own-pr` and `delete-own-branch` were mandated allowed operations with **no implementation anywhere in the governed surface**. | Path B's stop-and-rollback — acceptance criterion 4 — literally could not have run. The pilot could have created an irreversible remote effect it had no code path to undo. This was recorded on Path A as plan risk R2 and contradiction C3, before it could bite. | `b6ec6b7` — adds the retraction path plus `ControlledRetractionTests` (16 tests) |
| `PushExecutor` had **no production implementation at all**. | The delivery path could not push. The seam existed; nothing filled it. | `a6865fb` — adds `push_executor.py` plus `WorkspacePushExecutorTests` (7 tests) |
| `sandbox.py::_validate_paths` auto-detected an HTTPS remote URL as a filesystem path and rejected it, so `GitWorkspace.push_branch` could never push to a real remote. | This blocked the first real attempt outright. The same defect also broke `materialize(allow_remote=True)`. | `f578426` — plus tests in `tests/test_sandbox.py` |

The honest reading: a delivery surface that had never been pointed at a real host was
missing two of its six mandated operations and its only production push implementation.
Local tests were green throughout. That is the value of the pilot, and it is a more
useful result than a clean run would have been.

### 8.2 Open defects — NOT fixed

**D1 — a completed remote effect can be permanently stranded by a long filename.
(Highest severity. Unfixed.)**
`src/hive_mind_os/mission_store.py:81-92` writes the effect receipt **after** the
irreversible remote effect, and writes it through a temporary file named
`.<name>.tmp-<pid>` — *longer* than the final name — with no Windows long-path handling.
If that path exceeds 260 characters the write fails; `effect_outbox.py:150-168` then marks
the effect `reconciliation_required`, and `effect_outbox.py:91-93` makes that state
terminal on every subsequent attempt. **During the local rehearsal a successful push
became a permanent `EffectReconciliationRequired` purely because a temp filename was too
long.** The push had happened. The system could not record that it had. The only
mitigation in this run was choosing a short runtime root, `C:\Repos\trash\a4rt`. That is
a workaround, not a fix, and it depends on an operator remembering to apply it.

**D2 — `find_open_draft_pr` builds its query by string interpolation.**
`rest_gateway.py:152-165` builds its path at lines 157-158, interpolating the branch and base names straight into
`?state=open&head={owner}:{branch}&base={base}` with no percent-encoding. A branch name
containing `&`, `#`, `?` or a space produces a malformed or differently-scoped query. The
delete path is guarded (`_branch_ref`, and there is a test that a branch name cannot
smuggle a path into the ref delete); the read path is not.

**D3 — `list_comments` never follows `Link`.**
`rest_gateway.py:189-197` requests `?per_page=100` and reads page one only. The comment
idempotency marker is found by scanning that page. Past 100 comments the marker falls off
page one and the adapter **double-posts**. The comment idempotency proven by this pilot
holds for a pull request with one comment on it.

**D4 — `DeliveryGrant` has `issued_at` but no expiry.**
`grants.py:91-101`. A grant never goes stale on its own; only the token's own expiry ends
it. The credential expiring is the real backstop, which means grant lifetime is governed
outside the governance object.

**D5 — `EffectIntent.intent_digest` is format-checked but never verified to seal its
fields.** `contracts.py:527-535` runs `_digest()` over it, which checks the string looks
like a digest. Nothing recomputes it from the intent's own contents. Contrast
`DeliveryGrant.__post_init__` (`grants.py:114-129`), which *does* recompute and rejects a
digest that does not seal its fields. The intent contract should do the same.

**D6 — the gateway has no ref-read method.**
There is `default_branch()`, `get_pull_request()` and `delete_branch()`, but nothing that
reads `refs/heads/<branch>`. This is not merely missing convenience: it is why the
idempotency replay's before/after branch snapshots are `null`, and therefore why the
driver's own "branch head unchanged" verdict is worth nothing (§8.4).

**D7 — no remote receipt cites the sealed plan digest, and the plan was never re-sealed.**
See §2. The receipts bind to the grant and to their own intents; the plan sits outside the
chain, still saying `UNGRANTED` and `CLOSED`.

### 8.3 Carried forward from A3 — finding F3

`hive_mind_os.verify.verify_bundle` (`src/hive_mind_os/verify.py:266-379`) re-derives file
digests but **never reads the bundle's recorded `verdict`**. A bundle flipped from reject
to adopt is accepted, as long as `integrity.json` is recomputed — because `integrity.json`
is an unkeyed in-bundle manifest attesting self-consistency, not authenticity. Any
delivery pilot that ships on the strength of a retained bundle inherits that weakness.
This pilot gated no remote operation on a retained bundle's verdict field.

### 8.4 What this run does NOT prove

- **The driver's idempotency and rollback verdicts are weaker than they look.**
  `idempotency-replay.json` reports `branch_head_unchanged: true`, but both the before and
  after snapshots carry `branch_head_sha: null` and `host_pull_count: null`, because of
  D6. That assertion is `None == None`. It verified nothing by itself. The same file's
  `no_second_pull_request_created` is better supported — the fresh-intent replay's REST
  list genuinely contains a GET and no POST. And `stop-and-rollback.json`'s
  `no_open_draft_pr_remains` is asserted while its own `open_draft_pr_after_rollback` is
  `null`. **The real verification of both is the orchestrator's independent `ls-remote`
  and `get_pull_request` in §5**, not anything the driver said about itself.
- **No unexpected outbound connection is NOT proven.** `run-summary.json` records
  `socket_guard_installed: false`. The network guard used in the local rehearsal was
  deliberately absent here, because real network access was required and the guard would
  have blocked it. The evidence for what went out is the REST call list — the driver's own
  record of the calls it issued — and nothing observed the process's sockets. The driver
  originally emitted `outbound_connection_attempts: 0` alongside the absent guard; that
  pair reads as an affirmative claim of no network activity, which is false. The field has
  been corrected in place with the original value preserved beside it.
- **The credential's real scopes were never verified.** What is recorded is what the owner
  declared in the amendment. Verifying the token's actual permissions would require using
  or inspecting the token.
- **Every focused test still runs against fakes.** All 54 tests in the node's suite drive
  in-process fake transports, a recording push executor, or bare repositories the test
  creates with `git init --bare` in its own temp directory and reaches through
  `allow_local_test_remote=True`. The `https://github.com/...` strings in the file are
  fixture data inside fake responses, not requests. The github.com half of this node's
  evidence is the remote receipts, not the test suite.

## 9. Authority record

`docs/architecture/HUMAN_AUTHORITY_GATES.md` is the controlling record.

Its 2026-08-12 amendment (lines 61–87) authorizes one scoped GitHub credential and bounded
draft-pull-request delivery against exactly one disposable repository,
`patencyhealth-lab/hive-mind-a4-pilot`, permitting exactly six operations. Its addendum
(lines 89–100) permits the by-reference credential hoist described in §3.

The amendment **narrowly** supersedes the 2026-08-06 amendment's withholding of a GitHub
credential and of remote delivery — for this one repository and these six operations only.
Everything else in that amendment stands, including the API-key and spend prohibitions.
The amendment does not close `B-OPS-03` and does not alter G3, G4, G5, G6, G7 or G8. Gate
G5 in particular still withholds any production pilot. Nothing in this document
reinterprets that record as permissive.
