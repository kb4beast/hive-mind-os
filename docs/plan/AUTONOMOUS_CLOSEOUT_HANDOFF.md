# Autonomous Closeout Handoff

**Status:** open; this document makes no completion or release claim.
**Snapshot:** 2026-08-05, `origin/main` at
`dfee1c24125034c750e3d6e93c5af6c9ffd06e6d`.
**Purpose:** give a fresh, autonomous executor the exact remaining work, evidence
locations, stopping conditions, and authority boundaries. It is deliberately a handoff,
not a new roadmap or an authority grant.

## Truth order

1. `AGENTS.md` and the architecture contracts are binding.
2. `docs/plan/BLOCKERS.md` is the live source of truth for unresolved, deferred, and
   blocked obligations. `docs/architecture/HUMAN_AUTHORITY_GATES.md` controls external
   authority.
3. Exact-candidate court receipts control P03--P05 closure. The broad `done` labels in
   `docs/plan/00_OVERVIEW.md` describe the historical merged P01--P13 boundary; they do
   not supersede an unresolved exact-candidate court record.
4. `EXECUTION_PLAN_v3.md` currently exists only as an owner-owned, untracked working
   copy. It is proposed, not adopted. Do not schedule its implementation tasks until the
   owner explicitly adopts it in a tracked decision. Do not recreate it from memory if
   the working copy is unavailable.
5. P14--P20 and the Obsidian redesign program are withdrawn/deferred, not an executable
   backlog. Do not revive them merely because their files remain in the tree.

## Operating rules for every action

- Start from a clean detached worktree or a new `codex/` branch based on current
  `origin/main`. Never commit to, merge into, push to, or enable auto-merge for `main` or
  a staging branch.
- Preserve all old receipts, audits, dissent, branches, and failed outcomes. Append a new
  receipt instead of replacing one.
- Keep Builder, Curator, Judge, and Orchestrator identities/worktrees separate. A role
  cannot approve its own work.
- Curator receipts may contain only a decision and a short, safe reason. Never store a
  secret, credential, token, or raw model output.
- Use saved local Codex sign-in for headless Curator work only. Do not use API keys or
  make a live provider call: G2 currently prohibits them.
- Run focused checks while repairing. Run the full GitHub CI only for a complete,
  exact candidate that is ready for a final decision. Record the run URL and conclusion.
- If a reviewer returns no parseable decision, or evidence cannot be located, write a
  new blocked receipt with that exact safe reason and stop that phase. Do not infer an
  approval.

## Immediate preflight

1. Fetch `origin`; verify the current `origin/main` SHA and a clean worktree.
2. Check the GitHub Constitutional CI run for the current `origin/main` SHA. At this
   handoff snapshot, run `31007730617` is still running; all completed jobs are green and
   the Windows unit suite is the remaining job. Do not call the trunk green until that run
   completes successfully. If it fails, fix only its demonstrated failure in a small new
   branch before any other work.
3. Confirm that `docs/plan/BLOCKERS.md` and
   `docs/architecture/HUMAN_AUTHORITY_GATES.md` are present and read them in full.
4. Confirm the historical candidates exist before reviewing them:

   | Phase | Candidate | Retained location | Current closeout state |
   |---|---|---|---|
   | P03 | `6eb469c2df5dc24810e0e63068794e9640ad7292` | `origin/codex/p03-curator-closeout-repair` | blocked at Judge |
   | P04 | `76ec259a69912a0e9a4f6324aa62353eba05feaf` | ancestor of `origin/main` | blocked at Curator |
   | P05 | `b92dc6ca7a3dcbb71c85bbe91d4f11cbacf741e9` | ancestor of `origin/main` | blocked at Orchestrator |

The first P03--P05 receipt bundle is retained on the local branch
`codex/p03-p05-curator-closeout` at
`1f2d60474ec80a2979e1e4a1c097cdc3f8c9a462`. If that branch or its evidence files are
unavailable in a later session, record an evidence-availability blocker. Do not recreate
or paraphrase a missing receipt.

## P03--P05 closeout sequence

Complete these phases sequentially. A defect found in an earlier phase pauses later
phases until its narrow repair is reviewed and evidenced.

### P03 -- Windows process-tree repair

Historical facts:

- `a92e677...` was not approved because of a Windows PID-reuse risk.
- Repair candidate `6eb469c...` received a Curator approval after
  `tests/test_sandbox.py` reported 21 passed, 1 skipped, and 13 subtests passed.
- Its recorded exact GitHub Constitutional CI run `30989265242` succeeded.
- The Judge then blocked because its detached workspace could not access the exact
  Curator and audit evidence. The Orchestrator review was therefore not run.

Required autonomous work:

1. Materialize a detached worktree at `6eb469c...`; verify its SHA before every review.
2. Locate and validate the preserved P03 Curator, audit, and CI receipts. If they cannot
   be validated, create a new clean closeout candidate and repeat the necessary focused
   checks, audit, Curator review, and exact-candidate CI.
3. Compare the P03 repair's relevant files with current `origin/main`. If the repair is
   not represented there, make a narrow repair PR; do not treat a historic branch review
   as proof for different mainline code.
4. Run a fresh detached Judge with the evidence paths explicitly available. If approved,
   run a fresh detached Orchestrator. Record each result in a new append-only receipt.
5. Close P03 only if the repair is represented in current mainline, the exact candidate
   has a valid audit and passing exact CI, and Curator, Judge, and Orchestrator all issue
   usable approvals.

### P04 -- evidence-confinement repair

Historical facts:

- Candidate `76ec259...` is already an ancestor of `origin/main`.
- Its first headless Curator had no parseable final decision.
- Its retry could not start in a read-only sandbox. Neither is an approval.

Required autonomous work:

1. Use a clean detached worktree at `76ec259...` and a full-access, no-edit Curator that
   can start its inspection process. Instruct it to return only `decision` and a short
   safe reason.
2. Run only the P04-focused tests needed for the Curator finding. If it reports a clear
   defect, repair only that defect on a new branch, test it, and start the P04 review
   sequence again against the new SHA.
3. Once Curator approves, obtain separate Judge and Orchestrator decisions, a clean audit,
   and exact-candidate CI. Do not reuse the historical unusable attempts as a verdict.
4. If all decisions approve and current main contains the reviewed repair, append a final
   P04 closure receipt. Otherwise preserve the new blocker and stop.

### P05 -- authority-budget repair

Historical facts:

- Candidate `b92dc6c...` received a Curator approval after 14 focused mission tests.
- Its Judge approved and recorded exact CI run `30989265377` as successful.
- Its Orchestrator blocked: no post-commit P05 audit was available and the delivery
  blocker remained open.

Required autonomous work:

1. Materialize a clean detached worktree at `b92dc6c...` and create or locate a valid,
   clean exact-candidate audit without altering historical records.
2. Re-run the final court sequentially: Curator, then Judge, then Orchestrator. Each
   reviewer receives only the candidate and permitted evidence, not another reviewer's
   conclusion as independent proof.
3. Retain the existing exact CI receipt only after confirming its SHA and workflow match.
   If any code changes, run fresh exact-candidate CI.
4. Close P05 only on three usable approvals, a valid audit, passing exact CI, and proof
   that current main still contains the reviewed repair.

## Live backlog outside P03--P05

`docs/plan/BLOCKERS.md` currently has 22 rows: 4 resolved, 11 formally deferred source
obligations, 6 open rows, and 1 open comparator row with read-only intake authorized.
The unresolved rows are not interchangeable:

- **Source custody and licensing:** B-SRC-01 through B-SRC-11 remain deferred. An agent
  may perform allowed read-only research and record an honest court disposition, but may
  not promote a dependent claim without the required source bytes, custody, and compatible
  license/reuse evidence. B-SRC-11 needs a human source custodian.
- **Authenticated identity and evidence:** B-GOV-02, B-GOV-03, and B-GOV-04 remain open.
  They need external signing/identity and retention authority; do not simulate them.
- **Real capability:** B-OPS-03 remains open. The deterministic path is not proof of a
  real-provider end-to-end mission.
- **Production and comparison:** B-OPS-04 and B-OPS-05 remain open. No production or
  superiority claim is permitted.
- **Hard isolation:** B-OPS-06 remains open. P03's process-tier runner is not a hostile
  code isolation boundary.

There are no open GitHub issues or pull requests at this snapshot. Do not mistake the
many retained side branches for approved work: inspect and test a narrow diff before
reusing any of them.

## What can proceed autonomously after P03--P05

Only proceed after the owner explicitly adopts a tracked successor plan. The current
untracked `EXECUTION_PLAN_v3.md` proposes this strict order:

1. Re-measure the mainline baseline. If CI is not green, repair only that failure first.
2. Work one small, user-visible task at a time on a short-lived branch. Do not begin the
   next task in the same branch or session after opening its delivery PR.
3. Its P0.4 branch-fork action is already resolved by G1 and requires no merge. Do not
   reopen it.
4. Its P1.5 real-provider mission is blocked by G2. Do not use a key, spend money, or
   substitute a deterministic result while calling the real-capability blocker closed.
5. Its later production, signing, retention, comparator, source-license, and independent
   human-review tasks remain bounded by G3--G8 below.

## Non-autonomous stop conditions

An agent must write one short blocked checkpoint and stop the affected workstream when it
reaches any of these gates:

| Gate | Needed input | Current decision |
|---|---|---|
| G2 | provider credential, model ID, spend limit, and real-call permission | not authorized |
| G3 | non-agent-controlled signing/identity authority | not authorized |
| G4 | external append-only storage and recovery authority | not authorized |
| G5 | deployment account, pilot scope, users, and rollback authority | not authorized |
| G6 | comparator execution authority and qualifying court prerequisites | read-only intake only |
| G7 | founding-source bytes, license/reuse evidence, or custodian attestation | non-promoting deferrals remain |
| G8 | a second human reviewer or an explicit solo-project declaration | no decision recorded |

G1 is already resolved without a merge. Saved Codex sign-in is not authority for any of
the gates above.

## Copy-ready continuation prompt

```text
Continue Hive Mind OS autonomously from the current origin/main. Read AGENTS.md,
docs/plan/AUTONOMOUS_CLOSEOUT_HANDOFF.md, docs/plan/BLOCKERS.md, and
docs/architecture/HUMAN_AUTHORITY_GATES.md before acting.

First verify the exact main SHA and its GitHub CI. If main is not green, work only on the
demonstrated CI failure in a new codex/ branch. Never merge, push to main/staging, enable
auto-merge, delete evidence, invent a review decision, save raw model output, or use a
provider API key.

Then close P03, P04, and P05 in order using the exact candidate SHAs and receipt locations
in the handoff. Use detached, separate Curator/Judge/Orchestrator worktrees. Record every
attempt append-only with only safe reasons. A missing, unusable, or non-approval decision
is a blocker, not permission to continue. If a repair is needed, make one narrow branch,
run focused tests, obtain a fresh independent review, and use exact-candidate CI before
claiming closure.

After P03--P05, stop unless the owner has explicitly adopted a tracked successor plan.
For any external authority gate, write one concise blocked checkpoint naming the exact
needed input and stop that workstream. Do not simulate the missing authority.
```

## Completion standard for this handoff

This handoff is fulfilled only when the exact P03, P04, and P05 closure conditions above
have independently passed; the live blocker table has been updated only where a literal
exit condition was reproduced; and every remaining external gate is still shown as blocked
rather than being misrepresented as completed.
