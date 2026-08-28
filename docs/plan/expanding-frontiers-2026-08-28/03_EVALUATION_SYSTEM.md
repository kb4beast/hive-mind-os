# EXF-020 — The evaluation system, derived from sponsor behaviour

**Node:** `EXF-020` · **Round:** R2 (parallel with EXF-010) · **Roles:** Architect, Curator
**Stopping condition:** criteria, weights, and the veto rule are fixed and justified against sponsor evidence before any candidate is scored.

## Why not a generic startup rubric

A generic rubric (market size / team / traction / moat) would rank these candidates the
way a seed VC would. That is the wrong judging function. The money at the end of this
funnel is **non-dilutive**: DOE prize money, SBA capital-formation money, EDA talent
money, NASA technology-transfer access, and a non-profit's cash prizes. Non-dilutive
funders do not buy equity upside. They buy **their own mission outcomes**.

Every criterion below traces to an observed funding behaviour from `01_SUBJECT_TRUTH.md`,
not to intuition.

## Criteria and weights

| # | Criterion | Weight | Traced to |
|---|---|---|---|
| 1 | **NASA technology-transfer fit** — can this be built on an actual licensable NASA technology? | **0.18** | Space Act Agreement with NASA JSC; NASA Tech Trek; pitch-competition entrants historically pitch *licensed NASA technologies* |
| 2 | **Space × energy intersection** — does it serve both industries, not one? | **0.16** | DOE EPIC Prize was awarded *specifically* to fund Rockets & Rigs |
| 3 | **Regional economic impact** — jobs, capital and activity that land in South Texas | **0.15** | EDA STEM Talent Challenge; SBA GAFC Capital Formation; BCIC backing |
| 4 | **Non-dilutive follow-on path** — a named next cheque (SBIR/STTR/DOE/NASA/state) | **0.13** | SBA GAFC *Capital Formation* category; an accelerator is judged on where its companies go next |
| 5 | **Demonstrability at a pitch** — can a judge *see* it work in ten minutes? | **0.12** | The award mechanism is a live pitch competition before non-technical investors and industry leaders |
| 6 | **Founder asset advantage** — what already exists in the applicant's hands | **0.10** | Prizes reward credible execution, not proposals; ExF's own value proposition is speed to a real company |
| 7 | **Capital efficiency to first revenue** | **0.08** | Prize sizes are modest (ExF's own flagship win was $50k); an idea that needs $5M before it does anything cannot be started with the award |
| 8 | **Regulatory and safety headroom** — how much permitting stands between award and revenue | **0.08** | FAA/TCEQ/Army Corps scrutiny is continuous at this site; a prize cannot shorten a multi-year permit |

Weights sum to **1.00**.

## The veto rule

Weighted averages hide fatal flaws. Two criteria are therefore **vetoes**, not weights:

> An entrant scoring **≤ 3 / 10** on **regional economic impact (#3)** or on
> **regulatory and safety headroom (#8)** is eliminated regardless of its weighted score.

- **#3 is a veto** because a non-profit funded by EDA, SBA and a municipal improvement
  corporation cannot champion something with no South Texas footprint. It is not a
  scoring penalty for them; it is disqualifying.
- **#8 is a veto** because prize money cannot buy a permit. An idea whose first revenue
  sits behind an Army Corps or FAA approval converts an award into a waiting room.

## Scoring scale

0–10 per criterion. Weighted score = Σ(score × weight). Scores are evidence-anchored
where evidence exists and are labelled as judgement where it does not; where evidence is
weak the confidence is lowered rather than the number invented.

## What this rubric deliberately does *not* reward

- **Market size in the abstract.** A trillion-dollar TAM slide does not move a
  regional-impact funder.
- **Novelty for its own sake.** NASA technology transfer rewards *transfer*, not invention.
- **Pure software elegance.** Software with no physical or regional footprint scores 0.18
  and 0.16 near zero and will usually trip the #3 veto.

That third point is the rubric's sharpest edge, and it is aimed at the most tempting
candidates in the field.
