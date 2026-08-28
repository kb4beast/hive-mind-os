# Expanding Frontiers award selection — governed DAG run, 2026-08-28

**Subject:** identify the top three ideas that should be entered into Expanding Frontiers
(`expandingfrontiers.org`) programs, and select the single strongest one most likely to
win a grant or award.

This directory is the complete, auditable output of one Hive Mind OS subject-DAG run.

---

## The answer

| | Idea | Weighted | Why it placed here |
|---|---|---|---|
| 🥇 | **Corrosion evidence for coastal launch and energy infrastructure** — license NASA's KSC smart corrosion-detecting and self-inhibiting coating and sell it as a *tamper-evident corrosion record* for Rio Grande Valley launch, pipeline, port and LNG assets | **8.57** | The only entrant that is simultaneously a licensable NASA technology, a genuine space × energy problem, physically anchored in the sponsor's own region, and demonstrable on a table in ten minutes |
| 🥈 | **Tamper-evident compliance evidence platform** — sealed, independently re-executed environmental and safety evidence for FAA / TCEQ / PHMSA filings | 7.03 | Highest execution readiness in the field; no NASA anchor and an uncomfortable buyer |
| 🥉 | **Cryogenic boil-off recovery** for Starbase and the Port of Brownsville | 6.59 | The purest Rockets & Rigs entry; unexecutable by this applicant at this funding scale |

**Verdict: ADAPT.** No scouted candidate wins outright. The winner is a hybrid — NASA's
coating as the sensor, the applicant's existing evidence engine as the product.

**The finding that matters most:** the applicant's own existing product, entered
standalone, was **vetoed in round one** on regional economic impact. It scores 10/10 on
founder advantage and capital efficiency and still loses, because it answers neither
*which NASA technology* nor *what happens in South Texas*. It is a component of the
winner, not an entry.

**One thing decides everything:** the verdict is conditional on NASA's KSC corrosion
coating being licensable in 2026. If it is not, the runner-up wins. That question is
answerable in one email, and it is the first action in `09_SUBMISSION_PLAN.md`.

---

## Evidence boundary

`expandingfrontiers.org` was **blocked by this session's network egress proxy**
(`EGRESS_BLOCKED`). No fact here was read from the organization's own live site; sponsor
facts come from secondary sources — NASA, NSS, DOE, EDA and Rio Grande Valley press —
and are cited in `01_SUBJECT_TRUTH.md`. Deadlines, prize amounts and eligibility rules
are **unverified** and are carried as blocking operator confirmations `C-1`…`C-5`.

---

## How this was produced

`hive-mind autopilot run` returns a host-neutral execution contract; it does not execute
target repository code itself. On this repository it correctly fails closed
(`PLAN_GENERATION_REQUIRED`) rather than reusing the installed controller's plan for a new
subject. The DAG below was therefore generated for this subject and executed by the host,
which is the contract's declared `execution_owner`.

```bash
# 1. Request the governed DAG for the subject (host-neutral contract).
#    Writes .hive-mind/autopilot-request.json as local session state. That file is
#    deliberately not committed, so the command stays runnable for the next subject.
hive-mind autopilot run "Select the single strongest idea to submit to \
  Expanding Frontiers to win a grant or award" --repository .

# 2. Validate the generated DAG against the repository's own authoring standard
python .autopilot/bin/dag_standard.py --repo-root . dag-lint \
  --plan docs/plan/expanding-frontiers-2026-08-28/plan.json --strict
# SUMMARY: 0 error, 0 warning, 0 info

# 3. Compile executable dispatch rounds
python .autopilot/bin/dag_standard.py --repo-root . dag-rounds \
  --plan docs/plan/expanding-frontiers-2026-08-28/plan.json \
  --expected-plan-digest sha256:252dcaf0b34a44107e0389286fc50427d609238fa4dff250e4af0dacdec7f71c
# DISPATCH ROUNDS: 8

# 4. Reproduce every weighted score from the published inputs
python docs/plan/expanding-frontiers-2026-08-28/score.py
```

## The DAG

| Round | Node | Output |
|---|---|---|
| R1 | `EXF-000` Subject truth | `01_SUBJECT_TRUTH.md` |
| R2 | `EXF-010` Candidate field ∥ `EXF-020` Evaluation system | `02_CANDIDATE_FIELD.md`, `03_EVALUATION_SYSTEM.md` |
| R3 | `EXF-030` Screening | `04_TOURNAMENT_FIELD.md` |
| R4 | `EXF-040` Round one — weighted scoring | `05_ROUND1_WEIGHTED.md`, `round1_scores.json` |
| R5 | `EXF-050` Round two — adversarial battles | `06_ROUND2_ADVERSARIAL.md` |
| R6 | `EXF-060` Round three — execution and funding | `07_ROUND3_EXECUTION.md` |
| R7 | `EXF-070` Championship | `08_CHAMPIONSHIP.md`, `TOURNAMENT_RESULTS.json` |
| R8 | `EXF-080` Submission plan | `09_SUBMISSION_PLAN.md` |

## Files

| File | Contents |
|---|---|
| `plan.json` | The governed DAG. Lints clean under `dag-lint --strict` |
| `score.py` | Reproduces every weighted score and veto outcome |
| `round1_scores.json` | Generated scoring output |
| `TOURNAMENT_RESULTS.json` | Machine-readable verdict, dissent and reversal conditions |
| `RECEIPT.json` | Run receipt binding plan digests, commands and outputs |

## Scope of this claim

This is a **sponsor-fit tournament**, not a market forecast. It ranks ideas by how well
they match Expanding Frontiers' observed funding and selection behaviour. It does not
claim any of these ventures will succeed commercially, and it does not claim the winner
will be awarded anything.
