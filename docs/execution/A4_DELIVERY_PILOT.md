# A4 — Bounded governed remote-delivery pilot

**Node:** A4-800 · **Status:** STOPPED AT THE OWNER-CREDENTIAL GATE (Path A)
**Base commit:** `8041964bd8299871ad30f8b60fe7cc3f6b14b250`
**Sealed plan:** [`evidence/pilots/a4/pilot-plan.json`](../../evidence/pilots/a4/pilot-plan.json)
**Plan digest:** `sha256:1b19c027f58dd526058c3de9b0231e64b11e28fbea3003eac3f59b4e4c999776`
**Escalation record:** `ESC-A4-800-67ad9aad5d48` — see
[`evidence/pilots/a4/owner-grant/gate-stop.json`](../../evidence/pilots/a4/owner-grant/gate-stop.json)

**No remote operation was performed by this node.** No branch was pushed, no pull
request was opened, no comment was posted, on any repository. No credential was read,
searched for, or stored. That is not a shortfall to be apologised for: remote push, PR
and comment authority is genuine external authority that an agent cannot manufacture,
and the owner has not granted it. A fully prepared pilot that stops here is the correct
outcome; a fabricated remote receipt would be the one unforgivable failure.

---

## 1. The pilot boundary

The pilot is deliberately small. It touches ONE disposable repository that the owner
creates for the purpose and can delete outright afterwards.

| | |
|---|---|
| Target | one owner-named, private, disposable pilot repository (currently `UNGRANTED`) |
| Branch | exactly one: `a4-pilot/attempt-1`, under the granted prefix `a4-pilot/` |
| Pull requests | exactly one, and it is a **draft** |
| Comments | exactly one, marker-tagged for replay safety |
| Default branch | never touched |
| Protected branches | never touched |
| Other repositories | never touched |

**Allowed operations** (exactly these six; the sealed plan is authoritative):
`create-branch`, `push-branch`, `open-draft-pr`, `comment-on-own-pr`, `close-own-pr`,
`delete-own-branch`.

**Forbidden operations** (exactly these): `merge`, `push-to-protected-branch`, `deploy`,
`modify-settings`, `create-repository`, `delete-repository`, `any-spend`.

Two of those prohibitions are enforced by code rather than by good intentions, which is
worth knowing before you grant anything:

- `src/hive_mind_os/cortex/github/grants.py:26-28` closes the grantable vocabulary to
  `{"push", "open_draft_pr", "post_comment"}`. As the file says at line 25, "merge" is
  deliberately absent and is not a spelling the package accepts. **No grant you write can
  carry merge authority**, because there is no way to express it.
- `grants.py:23` pins `PROTECTED_BRANCHES = {"main", "master", "staging"}`, and
  `require_push_branch` (`grants.py:176-191`) denies a push to any protected branch, to
  the grant's own base branch, and to any ref outside the granted prefix.
- `src/hive_mind_os/cortex/github/rest_gateway.py` exposes four REST calls in total:
  find an open draft PR, create one, list comments, post one comment. There is no merge,
  close, review, or branch-protection method on the class, and none can appear without
  editing that file.

## 2. Sealed-plan digest discipline

The plan is sealed **before** any remote action, and every remote receipt must cite the
seal. This is the same discipline as
`hive_mind_os.brain_kernel.local_assurance.verify_local_assurance_artifact`:

1. Build the plan document **without** a `plan_digest` field.
2. `plan_digest = canonical_digest(plan)` — SHA-256 over the canonical encoding
   (`sort_keys=True`, `separators=(",",":")`, UTF-8, `allow_nan=False`) from
   `hive_mind_os.brain_kernel.canonical`.
3. Write the field into the document.
4. To verify: pop `plan_digest`, recompute over the remainder, compare. This round-trip
   was executed and matches.

The point is not ceremony. A remote effect is irreversible in a way a local one is not,
so the intent has to be fixed in advance and be checkable afterwards. **Remote host state
that contradicts the sealed plan is an escalation, not an improvisation** — if the host
says something the plan did not anticipate, the pilot stops and reports; it does not
adapt on the fly.

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

The gate opens only on an explicit act by the repository owner, in the live session,
supplying **both** authority classes:

- `credential_or_secret` — a scoped credential, installed by the owner themselves, never
  pasted into the conversation and never read by the agent.
- `owner_value_choice` — the named pilot repository. Where real-world side effects are
  allowed to land is a value choice, not a technical detail, and no agent may make it.

None of the following is a grant, and each will be refused:

- a grant written in a file, a README, an issue, a code comment, a commit message, or any
  document in this or any repository;
- a grant appearing in tool output of any kind;
- an orchestrating, sibling, or reviewing agent asserting that the owner approved;
- the mere presence of a `GITHUB_TOKEN` or any other credential on the host — a credential
  that exists is not a credential that was granted;
- silence, absence of objection, or a deadline;
- a grant from a previous session, or a grant issued for a different node.

If the agent ever asks you to paste a token into the conversation, refuse. That is a
boundary violation and the pilot must stop.

## 4. The two terminal paths

### Path A — gate closed (the path this node actually took)

Produce the sealed plan, this document, and `owner-grant/gate-stop.json`; run the focused
test suites; escalate; create no remote effect. The evidence tree that exists today:

```
evidence/pilots/a4/
  pilot-plan.json                 sealed, digest recorded above
  owner-grant/gate-stop.json      the gate check, the controlling lines, the escalation
  tests/a4-focused-suite.txt      focused-test transcript (31 tests, OK)
  tests/results.json              per-required-test mapping
  summary.json                    acceptance self-check and provenance
```

There is deliberately **no `remote/` directory**. The runbook creates it only if the pilot
actually ran. Its absence is the evidence.

The escalation names exactly two authority classes — `credential_or_secret` and
`owner_value_choice`. It does not name `protected_branch_merge` or `financial_spend`,
even though those would sound impressive: neither is required by the plan, so naming them
would overstate the blockage.

### Path B — gate genuinely open (not taken)

Execute the sealed plan strictly and in order: create `a4-pilot/attempt-1`, push one
trivial commit, open ONE draft PR, comment once, capturing each host response into
`remote/*.json` with the operation, request digest, host-assigned ids and timestamps.
Then **replay**: re-issue the identical push and PR-open, and record that the branch head
is unchanged and that no second PR was created. Then **stop and roll back**: close the
draft PR unmerged, delete the pilot branch, record final host state.

Before anyone runs Path B, read risk **R2** in the sealed plan. `close-own-pr` and
`delete-own-branch` are in the allowed-operations list and the stop procedure needs them,
but `ControlledRestGateway` implements neither, and `delivery_adapter.py:9-12` states that
close is not implemented and not grantable. Under Path B the rollback would have to be
performed by the owner or outside the governed adapter. That gap is real and is recorded
rather than papered over.

Risk **R1** matters too: A3-700 measured that `verify_bundle`
(`src/hive_mind_os/verify.py:266-379`) never reads a bundle's recorded `verdict`, so a
bundle re-sealed after a verdict flip is accepted. Any pilot that decides to ship on the
strength of a retained bundle inherits that weakness. This plan therefore never gates a
remote operation on a retained bundle's verdict field.

## 5. Stopping and revocation

**The pilot can be stopped at any moment, by anyone, for any reason or none.** Every
allowed operation is individually abandonable. Being cut off between any two steps leaves
at most one unreferenced branch and one unmerged draft pull request, inside a private
throwaway repository — and nothing outside it.

Owner-side revocation, which needs no agent cooperation and works even mid-step:

1. GitHub → avatar → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → `hive-mind-a4-pilot` → **Delete**.
2. Pilot repository → Settings → Danger Zone → **Delete this repository**.

Revoking mid-pilot is always safe. The next remote call simply fails with an auth error;
that failure is recorded as the stop evidence and the pilot ends there.

Within *this* repository the node is additive: it writes only `evidence/pilots/a4/**` and
this file, changes no runtime code, no tests and no configuration, and is reversible by
`git revert` of the node commits.

## 6. Acceptance criteria, honestly scored

| # | Criterion | Result |
|---|---|---|
| 1 | Owner explicitly supplies scoped credentials and pilot repository authority | **UNMET.** No owner grant exists. Recorded as unmet and escalated, not deferred and not simulated. |
| 2 | Only non-protected-branch and draft-PR operations occur | **VACUOUSLY TRUE — zero operations occurred.** The constraint is sealed in the plan and enforced in code, but it was never exercised against a live host. |
| 3 | No merge and no production deployment | **HELD.** Structurally: no merge exists in the grantable vocabulary. Also vacuously — nothing ran. |
| 4 | The pilot can be stopped and rolled back at any point | **DOCUMENTED, NOT EXECUTED.** §5 above plus the plan's stop and rollback procedures. No live stop was demonstrated, because no live pilot started. |

Criterion 1 is the gate. With it unmet, criteria 2–4 can only be scored against what was
actually exercisable without credentials, and this table says so rather than borrowing
credit from the design.

## 7. Authority record

`docs/architecture/HUMAN_AUTHORITY_GATES.md` is the controlling record. Its most recent
owner decision, the 2026-08-06 amendment at lines 50–53, withholds a GitHub credential by
name and withholds remote delivery by name. Gate G3 (line 14, decision at line 34)
withholds externally controlled identity; gate G5 (line 36) withholds any production
pilot. Nothing in this document reinterprets that record as permissive, and a new grant
would extend it, never override it.
