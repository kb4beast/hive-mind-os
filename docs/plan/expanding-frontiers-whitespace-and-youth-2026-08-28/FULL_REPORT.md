# Whitespace and Youth Tournaments — Full Investigation Report

Run date: 2026-08-28. Base commit: `59a5364`.
Method: `prompts/shared/ULTIMATE_SOLUTION_TOURNAMENT.md`, re-run twice with rubrics
rebuilt per section 4 for two new subjects.
Machine-readable: `WHITESPACE_RESULTS.json`, `YOUTH_RESULTS.json` (regenerate with
`score_tournaments.py`). Evidence: `SOURCE_REGISTER.md`, and the first run's S1-S19.

---

## 0. The answers

**Tournament B — ideas essentially nobody is doing.**

| Rank | Idea | Weighted | Why it is empty |
|---|---|---|---|
| **1** | **Boom Baseline** — the independent launch-overpressure record. Calibrated sensors across the launch community, published as the measurement layer every major airport has and no spaceport does. | **9.12** | `EMPTY_BECAUSE_NEW` |
| 2 | **Peninsula** — one shared risk picture for the launch site, the LNG export terminal, the port and the highway that all sit on the same peninsula. | 8.39 | `EMPTY_BECAUSE_UNGLAMOROUS` |
| 3 | **SARGO** — sargassum to rocket-grade biomethane, treating the arsenic contamination as the product rather than the obstacle. | 7.79 | `EMPTY_BECAUSE_HARD` |

**Tournament C — what a high school student can personally pitch and execute.**

| Rank | Idea | Weighted |
|---|---|---|
| **1** | **The Boom Map** — a student-built network of overpressure and vibration sensors on neighbours' homes and their own school, publishing the first independent public record of what each launch does to each street. | **9.34** |
| 2 | **Beach Fuel** — jar-scale sargassum-to-methane, with the arsenic question asked honestly: measure the yield, measure the contamination, report both. | 8.58 |
| 3 | **Closure Count** — the economic ledger of launch day, collected door to door across Port Isabel and published. | 8.39 |

Both winners are **robust**, which is the meaningful difference from the first run.
Every sensitivity variant tested keeps them on top: halving the whitespace weight,
removing the trap check, removing capital efficiency, and even a novelty-maximalist
rubric at 0.35. The first tournament's winner flipped under two of six variants;
these do not flip under any.

---

## 1. What changed in the method, and why

The first run optimised for *most likely to win*. It never asked whether anyone else
was already doing the idea. That is why its winner sits next to Sigstore, in-toto and
SLSA, and why its runner-up sits next to established cryogenic engineering firms. Both
are good businesses in contested space.

So Tournament B adds two mechanisms.

**`whitespace_uncontested` at 0.20**, the heaviest single criterion in either
tournament. But scoring emptiness alone rewards traps, because most empty space is
empty for a reason. So it is paired with:

**An emptiness classification, applied as a gate before scoring.** Every entrant is
assigned why the space is empty:

| Class | Meaning | Effect |
|---|---|---|
| `EMPTY_BECAUSE_NEW` | A precondition became true recently | The best kind of empty |
| `EMPTY_BECAUSE_HARD` | Genuinely difficult | Empty is a moat if you can do it |
| `EMPTY_BECAUSE_UNGLAMOROUS` | Nobody wants the work | Durable and underrated |
| `EMPTY_BECAUSE_GATED` | Access, permission or regulation blocks entry | Empty, but you may be blocked too |
| `EMPTY_BECAUSE_BAD` | It does not work or has no buyer | **Disqualifying** |
| `NOT_ACTUALLY_EMPTY` | Someone is already doing it | **Disqualifying** |

This did real work. Eleven of the 44 entrants across both tournaments were
disqualified on emptiness before scoring: four in B, seven in C. The youth field lost
model rockets, high-altitude balloons, CubeSat design studies and space-themed
tutoring apps — the four most common high school space projects in existence, all
`NOT_ACTUALLY_EMPTY`. It also killed "launch schedule forecasting" as
`EMPTY_BECAUSE_BAD`: trivially buildable, which is exactly why its emptiness is a
warning rather than an opportunity.

`founder_unfair_advantage` was **dropped entirely** from both rubrics. In the first
run it was the criterion most open to the charge of rigging the result toward the
entrant's existing codebase. Removing it means neither of these winners depends on
who is pitching, which is also why neither is the software company the first
tournament chose.

---

## 2. Tournament B — the whitespace field

24 entrants, 4 disqualified on emptiness, 15 survivors after triple elimination.
Full matrix in `WHITESPACE_RESULTS.json`.

### The decisive battle: highest whitespace lost

The single most uncontested idea in the field was **not** the winner. The
launch-site-by-LNG-terminal co-located hazard model scored **8.630**, the top original,
with a whitespace score of 10 — a genuinely unprecedented industrial adjacency where a
methane-fuelled orbital launch site and a $12 billion LNG export terminal share a
peninsula (S12), and where nobody has modelled what an anomaly at one does to the
other. It beat the overpressure record (8.470) on the pure rubric.

Then it took a round-3 score of **3**. It is `EMPTY_BECAUSE_GATED`: modelling that
interaction requires facility data from SpaceX and NextDecade, and neither hands a
solo founder their hazard analysis. The space is empty partly because the door is
locked.

**The hybrid is the resolution, and it is not a bundle.** Boom Baseline deploys the
sensor network first, because sensors on private homes and public land need nobody's
permission but the homeowner's. That network then generates *the only independent
dataset of what actually propagates across that peninsula* — which is precisely the
input the gated hazard model needs. Owning the measurement is how you get through a
door you cannot knock on. That is why the hybrid gains 0.49 over the best original
and 0.65 over its own core, rather than merely averaging them.

### Why the winner's emptiness is credible

The strongest evidence that this space is real and empty is the airport comparison.
Permanent community noise monitoring is unremarkable at airports: Toronto Pearson runs
25 IEC 61672 Class 1 terminals streaming continuously (S23). Meanwhile the National
Academies and the UK CAA have both published on commercial spaceflight noise
measurement (S25), so the problem is institutionally recognised. Searches for a
commercial provider doing this at spaceports returned test laboratories and academic
campaigns, not a service (S24).

Spaceports are roughly where airports were before noise monitoring became standard.
That is `EMPTY_BECAUSE_NEW` in its clearest form: launch cadence at a site inside a
populated area is the precondition, and it only recently became true.

The timing evidence is specific. Around 80 plaintiffs across roughly 60-70 households
in Port Isabel and South Padre Island sued in federal court in May 2026 over eleven
tests between April 2023 and October 2025 (S21). Researchers measuring an October 2024
launch recorded above 110 dB at 35 km and above 5 psf within 15 km, and found sonic
boom overpressures **exceeding FAA predictions by one to four psf** (S22).

That last fact is the business. When the predictive model is wrong by that margin and
the only measurements are academic one-offs, every party is arguing from anecdote:
residents, the operator, the insurers, the FAA, and the county. A calibrated
continuous record is what converts that into a process.

### Attacks on the winner

1. ***"This is a lawsuit support business."*** The most dangerous attack, and it is
   addressed in section 4 rather than dismissed here.
2. ***"The operator will simply publish their own data."*** Possible, and it would be
   a strong competitive response. The counter is the same reason airports do not
   self-certify community noise: the value of the record is its independence, and an
   operator-published number does not settle a dispute the operator is party to.
3. ***"Sensors are commodity hardware."*** True. The product is not the sensor, it is
   the calibrated, chain-of-custody, IEC-traceable record and the longitudinal dataset.
   That distinction has to survive a sharp judge or the idea is a hardware reseller.
4. ***"Who pays?"*** The honest answer is that this is unproven and it is the weakest
   part. Airports fund their own monitoring; the analogous payer is the operator,
   the spaceport authority, or the county. Insurers and the FAA are plausible. None
   is confirmed. Node `WS-020` exists to find one payer before anything else is built.

### Third place, and its honest defect

SARGO (sargassum to rocket-grade biomethane) is the most charismatic idea in the
field: a beach plague converted into launch propellant, which is the Rockets & Rigs
thesis rendered literal. It finished third because of one criterion.

It scores **5 on `emptiness_is_not_a_trap`**, and that score is the whole finding.
Sargassum bioaccumulates arsenic because its phosphate transporter confuses arsenic
for phosphate; arsenic is elevated in fresh biomass and released during decomposition;
digestate carries arsenic and zinc requiring treatment before agricultural use; and
heavy metals may cause toxicity that further reduces methanogenic performance (S27).
Methane yield is modest at roughly 92.62 mL CH4 per gram of volatile solids (S26). And
sargassum valorisation is already being commercialised in Grenada and Michoacán (S28),
so the *general* idea is not even empty — only the Texas propellant framing is.

The idea survives only in its reframed form: if arsenic is the reason the field is
empty, then contaminant separation is the actual product, and it opens both a fuel
market and a remediation market. That is a real thesis. It is also a chemistry
research programme, not something $32,000 finishes.

---

## 3. Tournament C — the youth field

The venue is concrete. ExF runs the **Space Entrepreneur Summer Academy**, a
three-week immersive programme for high school students in Brownsville, and ten SESA
students receive ExF internships through the NSS Club for the Future Scholars
programme (S20). The Conrad Challenge (ages 13-18) and the Diamond Challenge take the
same entry with no rework (S29).

The rubric was rebuilt around what actually decides a high school pitch:
`student_executable_solo` at 0.18 (can a sixteen-year-old genuinely do this with a
laptop, a phone and under $500, without an adult doing the work),
`real_evidence_in_three_weeks` at 0.12 (SESA's actual length),
`judge_legibility_in_60_seconds` at 0.10, `personal_credibility` at 0.09, and
`safety_and_permission` at 0.08 — because a plan that puts a minor near cryogens,
rocket hardware or a wildlife refuge permit is not a plan.

### The winner

**The Boom Map** takes the same whitespace as the adult winner and executes it at
student scale: cheap sensors on classmates' homes and the school building, one public
map of what each launch does to each street.

It wins on the criteria that are hard to fake:

- **Personal credibility 10.** The student lives in the house that shakes. No adult
  founder can buy that standing, and a judging panel feels it immediately.
- **Executability 9.** Sensor nodes are tens of dollars. Fifteen homes is a few
  hundred. This is genuinely a student's own work, not a parent's.
- **Evidence in three weeks 9.** One launch inside the window produces the headline
  chart. Zero launches still produces a deployed, calibrated, documented network.
- **Legibility 10.** "Every airport measures its noise. No spaceport does. I built
  the first one." That is the whole pitch, and it lands in one breath.

The strongest structural argument for it: **it is the same gap as the adult winner.**
The whitespace is wide enough that a venture and a high school project both fit
inside it at different scales, and the student's dataset is genuinely the seed of the
commercial one. A student who runs this for a year walks into SESA, the Conrad
Challenge and a university application with a real longitudinal dataset nobody else
on earth has.

### Runner-up and third

**Beach Fuel** is the most *fun* pitch in either tournament and scores 10 on mission
fit and legibility: seaweed into rocket fuel, demonstrated in a jar. It loses on the
same arsenic problem as SARGO, and its integrity depends on the student reporting the
contamination result honestly rather than only the yield. Framed that way it is
excellent science-fair work and a strong entry. Framed as "I solved rocket fuel" it
is a claim a knowledgeable judge will take apart in one question.

**Closure Count** scores the highest executability in the entire field (round-3 score
of 10 — it needs a notebook and a bicycle) and is the safest entry with zero
permission wall. It ranks third only because its space-and-energy mission fit is 4:
it is an economics project about a launch site rather than a space project. If the
student is more interested in business than instrumentation, this is the better fit
for them personally, and the tournament says so plainly rather than pretending the
ranking is the only input.

### What the emptiness gate removed

Model rockets, high-altitude balloons, CubeSat design studies, space-themed tutoring
apps, sargassum fertiliser and air-quality sensing near the corridor were all
disqualified as `NOT_ACTUALLY_EMPTY`. This is the most useful output of Tournament C
for a student: **the four most common high school space projects are the four worst
choices** if the goal is to be memorable to a judge who has seen forty pitches.

---

## 4. The risk both winners share, stated plainly

Expanding Frontiers is an NSS affiliate, a signatory to the Washington Compact on
commercial space norms, and an ecosystem builder embedded in the industry it serves
(S1, S8). Both winning ideas measure the impact of a launch operator on its
neighbours, in a region where roughly 80 of those neighbours are currently suing that
operator (S21).

**This can be heard two ways, and the framing decides which.**

Framed as impact documentation for litigation, it is adversarial to ExF's ecosystem,
and it should not be pitched to them. That is not a matter of tactics; it is a
mismatch of purpose.

Framed as **coexistence infrastructure**, it is pro-industry, and the argument is
strong: launch cadence in a populated region is limited by public consent, public
consent is currently being negotiated through anecdote and a courtroom, and the
FAA's own predictions were off by one to four psf (S22). Airports solved this
problem with measurement, not with argument, and they did it because operators
benefit from a trusted number. A spaceport that can point to an independent
calibrated record is in a stronger position than one that cannot, with the FAA, with
insurers, with the county, and with the residents.

Two commitments follow, and they are not optional decoration:

1. **Do not build a plaintiff-side business.** Serve every party the same data on the
   same terms, including the operator. The moment the record is for sale to one side,
   its value is gone.
2. **Ask ExF directly before submitting** (obligation O10). Do not guess how they will
   hear it. If the honest answer is that they will hear it as adversarial, pitch
   Peninsula or SARGO to ExF and take Boom Baseline elsewhere. Getting this wrong
   costs the entry and the relationship.

The youth version carries the same risk in a gentler form, plus one of its own:
publishing measurements tied to identifiable homes raises privacy and consent
questions that a high school project must answer before it collects anything
(obligation O12). Aggregate by street, get written consent, and never publish an
address.

---

## 5. Confidence, and the one claim most likely to be wrong

Confidence: **medium-high on the ranking, low-medium on the whitespace premise.**

The ranking is robust. Nine sensitivity variants were computed across the two
tournaments and **not one changes either winner**, including a novelty-maximalist
rubric that pushes whitespace to 0.35 and a variant that removes it entirely. That is
a materially stronger result than the first tournament, whose winner flipped under
two of six variants.

But the ranking rests on a premise scored from a **negative search result**. The
heaviest criterion in Tournament B is "nobody is doing this," and absence of evidence
in a search index is weak evidence of absence (S24). A stealth startup, a corporate
programme, a university spinout or an unindexed filing would not appear. Every
whitespace score here is a hypothesis, and `WS-000` exists to attack it properly:
patents, SBIR awards, trade press, FAA and county filings, and asking ExF, who would
know.

**If somebody is already doing calibrated community overpressure monitoring at a
spaceport, both winners collapse and the correct answer becomes Peninsula.** Find out
before building anything.

## 6. What would change these answers

- Someone is already doing spaceport community overpressure monitoring → both winners
  collapse; go to Peninsula (Tournament B) and Beach Fuel (Tournament C).
- ExF reads independent launch-impact measurement as adversarial (O10) → keep the
  idea, change the venue; pitch Peninsula or SARGO to ExF instead.
- The FAA overprediction finding has been superseded (O11) → the sharpest line in the
  pitch is stale; re-derive the urgency from the lawsuit and cadence alone, which is
  weaker but still holds.
- No payer can be identified in 30 days (`WS-020`) → this is a public-good project,
  not a venture; pitch it as the youth version and a nonprofit programme, which is
  honest and still wins a student competition.
- SESA turns out not to accept student-originated projects (O9) → the youth winner
  moves to the Conrad Challenge, which explicitly does (S29).
