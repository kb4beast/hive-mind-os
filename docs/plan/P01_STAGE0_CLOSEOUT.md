# P01 — Stage 0 Closeout and Blocker Backlog

Status: tracked in `00_OVERVIEW.md` | Depends on: none | Unlocks: every other phase

## 1. Objective

Declare an explicit, evidence-backed exit for Stage 0 (truth and source hardening), convert
every remaining open obligation into a tracked blocker with an owner and a resolution path,
and make `docs/plan/` the canonical sequencing authority so all future work starts from one
roadmap instead of four.

## 2. Rationale

ADR-002 through ADR-005 progressively hardened the current-state audit; each closed real
fail-open paths, but the loop has reached diminishing returns: the remaining Stage 0 items
(video ingestion, licenses, chain of custody, GitHub rule activation, signed identities)
cannot be closed by more local schema work — they need external evidence or human action.
The repository's own recursive-improvement docket
(`docs/architecture/RECURSIVE_SELF_IMPROVEMENT_DOCKET.md`) mandates diminishing-return
stopping rules; this phase applies that rule to Stage 0 itself. Nothing is weakened:
machine-blocked claims stay machine-blocked. What changes is that blockers become tracked
decisions instead of an open-ended gate on all capability work.

## 3. Required reading

1. `docs/plan/00_OVERVIEW.md`
2. `docs/plan/BLOCKERS.md`
3. `docs/architecture/ADR-005-STAGE-0-FAIL-CLOSED-APPEAL.md` (especially "Open obligations")
4. `docs/architecture/RECURSIVE_SELF_IMPROVEMENT_DOCKET.md` (stopping rules)
5. `README.md` (sections "Courtroom-governed synthesis" and "Audit the current state")
6. `AGENTS.md`

## 4. Prerequisite verification

```bash
git status --porcelain          # expect: empty (clean worktree)
python -m pytest -q             # expect: full pass
python -m ruff check src tests  # expect: no findings
hive-mind audit --output /tmp/p01-pre.json ; echo $?   # runs; exit code may be 1 if pre-existing blockers keep it incomplete — record the output
```

If the test suite or lint fails before you change anything, STOP and report.

## 5. Scope

In scope:

- A blocker backlog file, `docs/plan/BLOCKERS.md`.
- One new ADR declaring the Stage 0 exit posture.
- A short additive pointer in each superseded sequencing section.
- A closing status record in `docs/plan/BLOCKERS.md`.

Non-goals (explicitly out):

- No code changes. No new audit schema. No docket edits. No test changes.
- No resolution of the blockers themselves (P07 and P12 do that).
- No deletion or rewording of any existing document content — pointers are additive.

## 6. Design constraints

- Append-only spirit: every edit to existing documents is an added section or added lines,
  never a removal or rewrite of existing statements.
- The ADR must state plainly that machine-blocked claims remain blocked and that this exit
  does not promote any claim's burden.
- ADR numbering: use the next unused number (ADR-006 if none has been added since this plan
  was written; verify with `ls docs/architecture/ADR-*.md`).

## 7. Deliverables

New files:

- `docs/plan/BLOCKERS.md` — the blocker backlog. One table row per open obligation. Columns:
  `ID | Obligation | Source of record | Blocked claims/effects | Resolution path | Owner (human/agent) | Target phase | Review-by date | Status`.
  ID convention (later phases grep on these prefixes): `B-SRC-NN` for source-evidence
  obligations (videos, licenses, pins, chain of custody), `B-GOV-NN` for governance/
  infrastructure obligations (GitHub rule activation, signed identities, external
  ledger), `B-OPS-NN` for operational-maturity obligations (E2E/production receipts).
  Status values: exactly one of `open`, `resolved`, `deferred (review by YYYY-MM-DD)`.
  Seed it from ADR-005 "Open obligations" and the historical Stage 0 snapshot archived
  by P5.1; at minimum it must
  contain rows for: the seven incomplete video sources (transcript/artifact ingestion);
  unresolved source licenses and external commit pins; the sibling-pack authorship and
  `imgo.jpg` chain of custody; GitHub host-side rule activation being unverified; signed
  identities / external signing authority; durable external ledger; production-operation
  and E2E maturity receipts. Each row's Target phase should reference P07 (GitHub rules),
  P12 (ingestion/licenses), or "post-P13" where genuinely later.
- `docs/architecture/ADR-006-STAGE-0-EXIT.md` — standard ADR shape (Status, Date, Context,
  Decision, Consequences, Rollback). The Decision section must contain, in substance:
  1. Stage 0 exit criteria from the master prompt are met in their fail-closed form: every
     incomplete source and dependent claim is machine-blocked; no broken reference is
     accepted as a receipt; no mutable pin supports an adopted implementation claim.
  2. Remaining obligations move to `docs/plan/BLOCKERS.md` as tracked decisions with
     review-by dates; they remain machine-blocked until resolved through the courtroom.
  3. Further audit/verifier hardening happens only in response to a demonstrated
     counterexample (a reproduced fail-open path, captured as a regression test), not
     speculatively. This is the diminishing-returns stopping rule applied to Stage 0.
  4. `docs/plan/00_OVERVIEW.md` becomes the canonical sequencing authority.

Modified files (additive pointer only — one short paragraph each, at the end of the named
section, reading in substance "Sequencing for this work is now owned by
`docs/plan/00_OVERVIEW.md` (see ADR-006); this section remains as originally recorded"):

- `docs/architecture/FOUNDATION_PLAN.md` — after "Immediate next slices".
- `docs/architecture/CONGLOMERATED_SYSTEM.md` — after "Delivery sequence".
- `docs/architecture/BOUNDED_EVOLUTION.md` — after "Required next slices".
- `docs/architecture/HARDENED_VISION_CONTRACT.md` — after "Implementation sequence".
- `docs/architecture/MASTER_IMPLEMENTATION_PROMPT.md` — in the "Maintainer note" section
  only (do not edit inside the BEGIN/END MASTER PROMPT block).
- `docs/plan/BLOCKERS.md` — current exit posture and links to ADR-006.
- `README.md` — one sentence in the audit section pointing to `docs/plan/00_OVERVIEW.md`
  as the active roadmap.

## 8. Implementation steps

1. Verify prerequisites (section 4). Create branch `phase/P01-stage0-closeout`.
2. Enumerate open obligations: extract every unresolved item from ADR-005 "Open
   obligations", the archived Stage 0 snapshot, and README's courtroom section.
   Cross-check against the latest audit artifact under `evidence/audits/` if present.
3. Write `docs/plan/BLOCKERS.md` with one row per obligation. Do not invent resolution
   evidence; `Status` starts as `open` for every row.
4. Write `ADR-006-STAGE-0-EXIT.md`.
5. Add the additive pointers to the six architecture documents and README.
6. Run the standard gates; commit; run `hive-mind audit --output evidence/audits/P01-post.json`
   and commit the artifact.
7. Update the phase table in `00_OVERVIEW.md` and append your completion record below.

## 9. Required tests

No new code, therefore no new tests — but the full existing suite must pass unchanged, and
`python -m pytest -q` output must show the same test count as the pre-check (no tests
lost). Record both counts in the completion record.

## 10. Exit criteria

```bash
test -f docs/plan/BLOCKERS.md                                  # exists
test -f docs/architecture/ADR-006-STAGE-0-EXIT.md              # exists
grep -c '| open |' docs/plan/BLOCKERS.md                       # >= 7 (at least the seeded obligations)
grep -l '00_OVERVIEW.md' docs/architecture/FOUNDATION_PLAN.md docs/architecture/CONGLOMERATED_SYSTEM.md docs/architecture/BOUNDED_EVOLUTION.md docs/architecture/HARDENED_VISION_CONTRACT.md docs/architecture/MASTER_IMPLEMENTATION_PROMPT.md README.md   # lists the historical plan pointers
git diff main --numstat -- docs/architecture/ | awk '{if ($2>5) print}'   # empty: no architecture doc lost more than 5 lines (additive edits only; small whitespace shifts tolerated)
python -m pytest -q && python -m ruff check src tests          # pass
hive-mind audit --output evidence/audits/P01-post.json         # runs; incompleteness only from pre-existing blockers
```

## 11. Evidence

- `evidence/audits/P01-post.json` committed on the branch.
- The pre-change audit from section 4 attached to the PR description (or committed as
  `evidence/audits/P01-pre.json`) so before/after are comparable.

## 12. Rollback

Revert the branch's commits. Nothing depends on this phase's files yet. Do not delete
ADR-006 after the branch merges — supersede it with a later ADR if the decision changes.

## 13. Handoff

Later phases may assume: `docs/plan/00_OVERVIEW.md` is canonical; every known external
obligation has a row in `BLOCKERS.md`; new blockers discovered in any phase are appended
there; Stage 0 hardening is closed to speculative expansion.

## 14. Forbidden shortcuts

- Do not mark any blocker resolved, deferred, or waived — that is courtroom work for P12.
- Do not edit inside the master prompt's BEGIN/END block.
- Do not "clean up" or reflow existing documents while adding pointers.

---
## Completion record
- Date (UTC): 2026-07-27T16:31:01Z
- Executor (model/agent identity): Codex primary Builder/Integrator; independent Curator,
  Judge, and Orchestrator identities are separate from this executor.
- Branch and final commit SHA: `phase/P01-stage0-closeout`; audited implementation commit
  `b29deaec9757df922160ab49ec259a5507211131`. The pull-request head records the final metadata
  commit because a commit cannot contain its own SHA.
- Gates: pre-change and implementation gates each ran 134 tests (133 passed, 1 skipped;
  1,695 subtests passed); Ruff 0.16.0 passed; Pyright 1.1.411 passed with zero errors.
- Audit artifact: `evidence/audits/P01-post.json` (digest:
  `sha256:e818c833a751f00b`)
- Deviations from the phase spec: Target-phase routing includes P05, P06, P08, and P11 where
  the operator instruction and canonical phase exit criteria identify the actual owner,
  while P07, P12, and post-P13 retain their specified obligations. This changes no code,
  policy, audit schema, or source docket.
- New blockers discovered (mirrored into docs/plan/BLOCKERS.md): 21 open rows preserve the
  current evidence census: 20 blocked sources, 73 machine-blocked claims, 17 license/reuse
  obligations, five exact-pin obligations, four raw-digest obligations, seven incomplete
  YouTube ingestions, and governance/independence/durability/E2E/production/benchmark gaps.
