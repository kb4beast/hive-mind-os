# DO THIS NEXT

The tournament is finished. This is the handoff. Nothing below is optional
reading — it says exactly what to open, what to run, and where to stop.

---

## Right now, before any session: one phone call

**Contact Expanding Frontiers and ask five questions.** This is node `EF-000`,
it is the first node on the critical path, and it can invalidate the
recommendation — which is the point of doing it first.

1. When is the next Space Tech Pitch Competition, and what is the application deadline?
2. Is there a published judging rubric, and how is it weighted?
3. What is the prize amount and how does it split across the three winners?
4. What are the eligibility requirements: incorporation, Texas or RGV residency, stage limits?
5. Who won the last two cycles, and in what sectors?

Contact route: the ExF site (`expandingfrontiers.org/current-programs` and
`/techexpoinfopage`) or ExF staff directly. Those pages were blocked by this
environment's network proxy, so nothing from them was reconstructed or guessed.

**Why this gates everything.** `FULL_REPORT.md` section 2.1 shows the ranking is
not robust to a rubric change. Under a hardware-favouring rubric the winner flips
from Frontier Assurance (8.394) to CryoAssay (8.628). With the founder-advantage
criterion removed the two are 0.078 apart, which is a tie. Building a deck before
this answer arrives risks building the wrong one.

---

## Session 1 — Rules of record (nodes EF-000 to EF-003)

**Open:** a new session in this repository, on branch
`claude/expanding-frontiers-ideas-okkz31` or a branch cut from it.
**Model:** Sonnet-class, low to medium effort. This is evidence collection, not judgement.
**Files to load:** `SOURCE_REGISTER.md`, `EXECUTION_DAG.json`.

**Paste exactly this:**

> Read `docs/plan/expanding-frontiers-tournament-2026-08-28/SOURCE_REGISTER.md` and
> `EXECUTION_DAG.json`. Execute nodes EF-000, EF-001, EF-002 and EF-003 in parallel.
> They are the four evidence gates that discharge obligations O1 through O7. Produce
> `RULES_OF_RECORD.md` in the same directory. For every claim record the source URI,
> retrieval date and confidence level A, B or C using the key in SOURCE_REGISTER.md.
> Anything you cannot source, record as still-open — do not fill a gap with a plausible
> answer. Stop when RULES_OF_RECORD.md exists and each of O1 to O7 is marked discharged
> or unanswerable. Do not write a pitch, a deck, or a business plan.

**Produces:** `RULES_OF_RECORD.md`.
**Stops when:** every obligation is discharged or explicitly recorded as unanswerable.
**Must NOT start yet:** any deliverable. No plan, no deck, no financial model.

---

## Session 2 — Lock the entry (node EF-010)

Only after Session 1 merges.

**Model:** Opus-class, high effort. This is the judgement node, and it is allowed
to overturn the recommendation.

**Paste exactly this:**

> Read `RULES_OF_RECORD.md`, `FULL_REPORT.md` and `score_tournament.py` in
> `docs/plan/expanding-frontiers-tournament-2026-08-28/`. Execute node EF-010. Replace
> the derived criteria weights in `score_tournament.py` with the real ones from
> RULES_OF_RECORD.md, re-score the entire 30-entrant field, not only the finalists, and
> regenerate `TOURNAMENT_RESULTS.json`. Write `DECISION.md` naming exactly one entry to
> submit and the margin over the runner-up. If the winner changes from Frontier Assurance,
> say so plainly; do not defend the prior recommendation. If the margin is under 0.20,
> declare a tie and defer the choice to EF-040's design-partner outcome.

**Produces:** updated weights, regenerated results, `DECISION.md`.
**Stops when:** `DECISION.md` names one entry.
**Must be merged before proceeding:** `DECISION.md`. Everything downstream branches on it.

---

## Session 3 onward — Build (nodes EF-020 to EF-080)

Follow `EXECUTION_DAG.json` levels 2 through 5. Level 2 (`EF-020` eligibility,
`EF-040` design partner, `EF-080` funding ladder) runs in parallel. Level 3
(`EF-030` NASA binding, `EF-050` live demo) follows. Each node's prompt is its own
contract in the DAG: objective, acceptance criteria, scope, stopping condition. Do
not paste this whole report into a worker session — hand it the node.

**`EF-040` is the one to start first and watch hardest.** It is the highest-variance
node in the plan: securing one named Brownsville-area design partner. If nothing
signs in 30 days, the winner has lost its regional anchor and the correct move is
to re-run EF-010 with CryoAssay, not to pitch an unanchored entry.

---

## Hard stops

- **Do not submit anything before `EF-090`**, the independent adversarial review by
  someone who did not write the submission. `EF-100` is the only irreversible node in
  the plan and is gated on it. A submission cannot be recalled.
- **Do not put any confidence-C claim in a deck.** Specifically, the Project Able
  Baker figures (S17: $480M, 38 platforms, 4 pilots by 2027, Brownsville headquarters)
  come from a single aggregator. Verify them in `EF-002` or say "reported" out loud.
- **Do not claim a NASA licence until one is signed**, or production readiness, or
  user validation. This repository's own README says prototype, no production use, no
  user validation. A judge who clones it will read that, and being caught overstating
  is worse than the gap being overstated about.
- **Do not claim the evidence-bundle format is novel** against Sigstore, in-toto or
  SLSA. The defensible claim is the independent re-execution of a check sealed before
  the change. That is the part those systems do not do.

---

## The permanent loop after bootstrap

Each subsequent session: read `EXECUTION_DAG.json`, take the highest
`critical_path_importance` node whose dependencies are complete, execute its
contract, satisfy its acceptance criteria, open a PR, stop. The DAG is the state;
this document is only the entry point.

Validate the graph at any time with:

```bash
python docs/plan/expanding-frontiers-tournament-2026-08-28/validate_dag.py
python docs/plan/expanding-frontiers-tournament-2026-08-28/score_tournament.py
```
