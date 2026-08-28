# Expanding Frontiers Award Tournament — Full Investigation Report

Run date: 2026-08-28. Base commit: `59a5364` (`main`).
Method: `prompts/shared/ULTIMATE_SOLUTION_TOURNAMENT.md` executed with the SUBJECT
"which venture idea most likely wins a grant or award from Expanding Frontiers."
Machine-readable results: `TOURNAMENT_RESULTS.json` (regenerate with
`python docs/plan/expanding-frontiers-tournament-2026-08-28/score_tournament.py`).
Evidence and its limits: `SOURCE_REGISTER.md`.

---

## 0. The answer

| Rank | Idea | Weighted | One line |
|---|---|---|---|
| **1** | **Frontier Assurance** | **8.79** | A sealed flight recorder for autonomous operations. Tamper-evident, independently re-executed proof of what an uncrewed system actually did, wedged into offshore booster recovery and cryogenic propellant transfer. |
| 2 | CryoAssay | 8.02 | Propellant-grade LNG certification and boil-off loss accounting for the Brownsville cryo corridor, with a NASA integrated-refrigeration licence as the hardware second act. |
| 3 | Saltline | 6.84 | Startup-NASA-licensed corrosion and thermal-protection coatings qualified for a decommissioned Gulf platform deck that must survive both salt spray and rocket exhaust. |

Verdict: **ADAPT**, not adopt. The winner is a hybrid that did not exist before the
tournament. Neither of the two strongest originals wins unmodified.

Confidence: **medium, and deliberately not higher.** The scoring criteria are
*derived* from what Expanding Frontiers is documentably rewarded for, not quoted
from a published rubric, and obligations O1-O7 in `SOURCE_REGISTER.md` are open.
The sensitivity analysis in section 2.1 shows the result is not robust to a rubric
change: **under a hardware-favouring rubric CryoAssay wins instead**, and with the
founder-advantage criterion removed the two are effectively tied (margin 0.078).
Read rank 1 and rank 2 as "prepare both, submit the one the real rubric rewards".
Settling which is node `EF-000`, the first thing to do.

---

## 1. Subject interpretation

The naive reading of this request is "find three good space startup ideas." That
reading loses. Expanding Frontiers is not a venture fund; it is a 501(c)(3)
ecosystem builder whose own funding — an EDA STEM Talent Challenge award, a
$50,000 DOE EPIC Prize, a 2025 SBA Growth Accelerator Fund award in the *Capital
Formation* category — is justified to its funders on Rio Grande Valley economic
development and NASA technology commercialisation (S1, S5, S6, S7).

That changes the objective function. ExF wins when its portfolio creates
high-paying RGV jobs and pulls federal non-dilutive dollars into South Texas. A
judging panel selecting on that basis will pass over a technically superior idea
that could be executed from Boulder in favour of one that must be executed within
sight of the Brownsville ship channel. The tournament is therefore scored on
**probability of winning this specific award from this specific organisation**,
not on venture quality.

Second constraint, equally load-bearing: the flagship prize is a reported $32,000
split across three business plans (S2). That is not a number that de-risks
hardware. It funds a design partner, a field trial, a licence application, or a
credible prototype. Any idea whose next honest milestone costs seven figures is
asking the wrong funder, and the scoring reflects that.

---

## 2. The evaluation system (GenericPrompt section 4)

Built for this subject, not inherited from a template. Ten criteria, weights
summing to 1.0:

| Criterion | Weight | Why it carries this weight |
|---|---|---|
| `mission_fit_space_energy` | 0.14 | ExF's signature thesis is Rockets & Rigs: problems *common to* space and energy (S4, S5). A dual-sector idea is not a bonus here, it is the house specialty. |
| `rgv_regional_anchor` | 0.13 | Every dollar ExF has raised was justified on regional development. Portability is a defect in this contest. |
| `customer_proximity_30km` | 0.13 | Starbase, Rio Grande LNG, Texas LNG, the Port of Brownsville and the reported AFRL recovery headquarters sit inside one commute. A named local buyer beats a TAM slide. |
| `capital_efficiency_at_32k` | 0.12 | The prize must actually reach the next milestone. |
| `nasa_technology_basis` | 0.10 | Entries are explicitly often NASA-technology based (S2), and Startup NASA removes the up-front licence fee (S9). A documented licence is a scoring line, not decoration. |
| `follow_on_nondilutive_ladder` | 0.10 | ExF's Capital Formation mandate means a portfolio company that goes on to win SBIR/STTR/DOE/EDA money is a reportable outcome for them. |
| `founder_unfair_advantage` | 0.10 | Panels fund people. What does *this* entrant have that a stranger does not. |
| `stage_demonstrability` | 0.08 | Five minutes in front of judges. What can be shown working, live. |
| `regulatory_or_mandated_pull` | 0.06 | A mandated buyer beats a delighted one. |
| `defensibility` | 0.04 | Real, but at pre-seed a panel discounts moat talk heavily. Deliberately the smallest weight. |

Two anti-gaming rules were applied (section 9): a score of 3 or below on any
criterion is recorded as a **catastrophic weakness** on the entrant's record and
is never allowed to vanish into the weighted average, and rounds 2 and 3 are kept
as separate columns rather than folded in.

### 2.1 Sensitivity — where this rubric breaks

`founder_unfair_advantage` at 0.10 is the criterion most open to the charge that
it rigs the outcome toward the entrant's existing codebase. So the rubric was
attacked directly, re-normalising the surviving weights each time. Reproduce with
`score_tournament.py`; results are stored under `sensitivity` in
`TOURNAMENT_RESULTS.json`.

| Rubric variant | Frontier Assurance | CryoAssay | Winner | Margin |
|---|---|---|---|---|
| Baseline | 8.790 | 8.020 | Frontier Assurance | 0.770 |
| Founder advantage removed | 8.656 | 8.578 | Frontier Assurance | **0.078** |
| Capital efficiency removed | 8.625 | 8.295 | Frontier Assurance | 0.330 |
| NASA basis doubled to 0.20, founder halved to 0.05 | 8.562 | 8.352 | Frontier Assurance | 0.210 |
| **Both prize-physics criteria removed** | 8.449 | **8.974** | **CryoAssay** | 0.525 |
| **Hardware-favouring rubric** (NASA 0.20, capital 0.05, founder 0.05, demo 0.04) | 8.394 | **8.628** | **CryoAssay** | 0.234 |

This is the most important table in the report, and it does not say what a
motivated author would want it to say. Removing the founder criterion alone leaves
the winner ahead by **0.078**, which is inside the noise of any judgement-based
scoring and should be read as a tie, not a win. Removing both prize-physics
criteria, or adopting a rubric that rewards hardware and NASA patent licensing,
**flips the result to CryoAssay**.

The recommendation therefore rests on a single load-bearing premise: *that a
$32,000 non-dilutive prize is scored on what the money can actually reach and on
what the founder has already built*. That premise is defensible from the prize
size alone, and it is why capital efficiency and founder advantage carry 0.22
between them. But it is a premise, not a finding — which is exactly why
obligation O2, obtaining the published rubric, is the first node in the execution
DAG rather than a footnote.

---

## 3. Scouting and saturation (sections 2, 3)

Search covered: the ExF programme surface and its funders; NASA Technology
Transfer, Startup NASA and the NASA Software Catalog; NASA cryogenic fluid
management and zero-boil-off literature; the LNG boil-off gas engineering
literature; the Brownsville industrial corridor (Rio Grande LNG, Texas LNG, Port
of Brownsville, Starbase); the reported AFRL offshore-platform rocket recovery
programme; and the NASA autonomous-systems certification literature (ATTRACTOR,
Resilient Autonomy, MM-RTA).

Saturation was reached when three consecutive searches in the cryogenics and
offshore families returned only sources already registered, and when new
candidate ideas began arriving as variants of registered entries rather than as
new mechanisms.

**Saturation was NOT reached on the ExF-specific evidence.** Four separate
primary-source fetches were blocked by this environment's egress proxy
(`expandingfrontiers.org`, `exfspacetechppitchcomp2024.org`, `airforcetimes.com`).
Per AGENTS.md courtroom rule 10 nothing was reconstructed from those pages. They
are logged as blocking obligations O1-O7 and appear as gating nodes in the DAG.

---

## 4. The field (section 6)

Thirty serious entrants across eight families: cryogenics (6), offshore and
recovery (6), sensing (4), autonomy and software (5), ecosystem and workforce (2),
materials and manufacturing (3), power (2), data and earth observation (2). Full
per-criterion matrix in `TOURNAMENT_RESULTS.json`.

**Excluded before entry**, with reasons, so the exclusions can be challenged:

- Launch vehicles, satellite buses, and constellations. Capital scale is three
  orders of magnitude past the prize; entering one signals a misread of the room.
- Space tourism, asteroid mining, orbital data centres. No local customer, no
  near-term revenue, and a panel of practitioners discounts them hard.
- Pure consulting and pure services with no technology asset. ExF's mandate is
  technology commercialisation.
- Anything requiring an ITAR-controlled facility on day one. The prize cannot
  reach that milestone.
- Regolith and soil stabilisation was *kept* in the field despite being an
  obvious loser, as a calibration control. It finished last (5.02) and was
  eliminated, which is the behaviour a working rubric should produce.

---

## 5. Triple elimination (sections 7, 8)

Three rounds, each a distinct question, a loss being a below-median finish:

- **Round 1 — the rubric.** Weighted criteria score.
- **Round 2 — the judging room.** How the entry survives four adversarial
  scenarios: (a) a judge asks "why does this have to be in Brownsville";
  (b) a judge asks "who writes you a cheque in the next twelve months";
  (c) a judge asks "what have you actually built"; (d) a judge with deep domain
  expertise attacks the technical premise.
- **Round 3 — execution reality.** Can *this* entrant credibly stand behind it
  this cycle, without a co-founder who does not yet exist.

Twenty-five of thirty survived; five were eliminated on three losses. Triple
elimination did real work: **ZBO reliquefaction skid retrofit** scored third on
the pure rubric (7.33) and would have been a finalist under single elimination,
but took a fatal round-3 loss (score 2) because it requires cryogenic hardware
engineering the entrant does not have. Single elimination would have hidden that.

### The decisive battles

**Propellant-grade LNG assay (7.880) versus Verifiable autonomy receipts (7.870).**
The closest matchup in the tournament, one hundredth of a point apart, and the
two entries are near-perfect complements. The assay idea wins regional anchor
(10 vs 6), customer proximity (10 vs 7), mission fit (10 vs 8) and regulatory
pull (9 vs 7). The receipts idea wins capital efficiency (10 vs 6), founder
advantage (10 vs 3) and demonstrability (10 vs 6). Neither loss is superficial:
the assay's founder-advantage 3 is a real catastrophic weakness (no cryogenic
credential, needs a technical co-founder before the pitch), and the receipts'
regional-anchor 6 is a real one too (a judge can legitimately ask why this is not
a San Francisco company). **The tournament's central finding is that each idea's
fatal flaw is the other's strength**, which is precisely the condition that makes
hybridisation worth attempting rather than a gimmick.

**Verifiable autonomy receipts versus Autonomous flight-software V&V service.**
Both are software-assurance plays by the same founder. V&V loses on regional
anchor (4 vs 6) and customer proximity (5 vs 7) because its customers are
smallsat primes in Colorado and California, not Gulf operators. Its component
value was preserved: its NASA formal-methods lineage is the winner's route to a
documented NASA technology basis.

**Attacks on the leader, run honestly:**

1. *"This is an IT product wearing a space costume."* Real risk, and the most
   likely way this entry loses in the room. Mitigation is structural, not
   cosmetic: the wedge must be a named uncrewed operation with a named local
   operator, and the demo must show a sealed check catching a false success
   claim, live. If the founder cannot name the operator by pitch day, this
   attack lands and the entry should be swapped for CryoAssay.
2. *"Your own README says prototype, no production use, no user validation"* (S19).
   Correct, and it must be said out loud on stage. For a $32,000 non-dilutive
   prize aimed at pre-seed founders this is not a weakness, it is the reason to
   award the money. It would be fatal in a Series A room; this is not one.
3. *"There is no NASA technology here."* The weakest point of the winner, scored
   honestly at 7. There is no patent licence. The mitigation is real but must be
   executed, not asserted: the NASA Software Catalog distributes formal-methods
   and runtime-assurance tooling (PVS-based simplex runtime assurance, DAIDALUS)
   free to US entities (S10), and NASA's own literature documents autonomy
   certification as an open barrier (S11). Node `EF-030` exists to convert that
   from a claim into a signed software usage agreement before submission.
4. *"Evidence bundles are a solved problem — Sigstore, in-toto, SLSA."* Partly
   true and the strongest technical attack. The differentiator is not the bundle
   format, it is the **independent re-execution of a check sealed before the
   change**, which supply-chain attestation does not do: those systems attest
   that an artefact came from a pipeline, not that an independent party re-ran
   the acceptance test and it passed. That distinction must survive contact with
   a sharp judge or the entry is commodity.

---

## 6. Component winners and preserved ideas (section 10)

| Component | Winner |
|---|---|
| Regional lock-in | Propellant-grade LNG assay |
| NASA technology basis | NASA-licensed corrosion and TPS coatings |
| Capital efficiency | Verifiable autonomy receipts |
| Live stage demo | Verifiable autonomy receipts |
| Regulatory pull | Methane plume detection |
| Dual-use space-energy thesis | Propellant-grade LNG assay |
| Follow-on funding ladder | Verifiable autonomy receipts |
| Physical credibility on stage | Refractory and ablative pad materials |
| Workforce and ecosystem alignment | RGV supplier readiness marketplace |

Preserved from losers: the Boca Chica community-monitoring entry has the
strongest community-benefit framing in the field and is borrowed as a slide, not
a business. The technician-credentialing entry scores a perfect 10 on regional
anchor and is folded into the winner as an explicit RGV hiring commitment. The
pad-materials entry proves that physical props beat slides, so the winner brings
a tangible artefact to the stage.

---

## 7. Hybrids (sections 11, 12)

Four hybrids were built. They did not all win, which is the point.

| Hybrid | Weighted | Outcome |
|---|---|---|
| **Frontier Assurance** | **8.79** | Champion. |
| CryoAssay | 8.02 | Runner-up. |
| Rockets and Rigs Cryo Autonomy Suite | 7.26 | **Lost.** Deliberate over-combination — receipts plus assay plus tank sensing sold as one platform. It scores well on mission fit and region and still loses, because bundling destroyed capital efficiency (4) and demonstrability (5). Breadth does not survive a five-minute pitch. |
| Saltline | 6.84 | Third overall, but note it scores **exactly** its own core component. Adding a structural digital twin to a coatings business produced zero lift. An honest hybrid that failed to be a hybrid. |

**Why Frontier Assurance gains 0.92 over its core.** The hybrid is not "receipts
plus more features." It changes what the company is *for*: from a developer tool
that verifies coding agents, to an assurance layer for uncrewed physical
operations. That single reframing moves mission fit 8→9, regional anchor 6→8,
customer proximity 7→9 and regulatory pull 7→8, while capital efficiency,
founder advantage and demonstrability all stay at their maxima because the
underlying machinery — sealed checks, independent re-execution, tamper-evident
bundles — is unchanged and already built. It borrows the remote-operations-centre
entry's Brownsville anchoring, the V&V entry's NASA formal-methods lineage, and
the leak-localisation entry's cryogenic use case. Nothing in the borrowed set
requires new core technology, which is why the hybrid is cheap and why the
combination is coherent rather than decorative.

**New weaknesses the hybrid introduces**, stated because hybrids usually hide
them: it takes on a domain the founder does not have (offshore and cryogenic
operations), so every technical claim about those environments must come from a
design partner rather than from the founder; and it inherits a dependency on the
reported AFRL programme (S17), which is C-confidence evidence from a single
aggregator. If O6 fails, the offshore wedge is removed and the cryogenic-transfer
wedge at Rio Grande LNG carries the pitch alone. The entry survives that, at a
lower score.

---

## 8. Final championship (section 13)

Best original: Propellant-grade LNG assay and loss accounting, 7.880.
Best hybrid: Frontier Assurance, 8.790.

Hardest scenario applied to both — *a judge who has personally run a cryogenic
facility, plus a judge who has personally raised venture capital, attacking
simultaneously*:

The assay entry survives the operator but loses the investor: the operator asks
who calibrates the assay and against which standard, and there is no answer
without a co-founder; the investor asks what has been built and the answer is a
plan. The receipts entry survives the investor easily — working code, a live
offline demo, a deterministic re-execution — and takes damage from the operator
on domain naivety, which is repairable inside the competition timeline by
recruiting one design partner and quoting them.

**Winner: Frontier Assurance.** The decisive factor is not technology quality; it
is that its remaining weakness is fixable with a phone call and thirty days,
while the runner-up's remaining weakness requires recruiting a co-founder with a
cryogenics credential.

**When the runner-up is preferable, stated plainly:**

- If ExF publishes a rubric weighting NASA patent licensing or hardware above
  founder traction (obligation O2). Not hypothetical: section 2.1 shows such a
  rubric produces CryoAssay 8.628 against Frontier Assurance 8.394.
- If a co-founder with genuine cryogenic or LNG operations credentials joins
  before the deadline. That single change moves CryoAssay's founder-advantage
  score from 3 to 8 and its total to roughly 8.5, past the winner.
- If the AFRL programme evidence (O6) collapses *and* no cryogenic-transfer
  design partner can be secured, removing both of the winner's physical wedges.

---

## 9. Final architecture of the winner

**Company:** Frontier Assurance (Brownsville, Texas).
**Product:** a sealed flight recorder for autonomous operations.
**One-line pitch:** *Autonomy is arriving on the Gulf faster than the paperwork
that proves it worked. We make an uncrewed system prove what it actually did, to
a standard an inspector can re-run.*

**What it technically is**, and this is the part that must be true: before an
autonomous operation runs, the acceptance conditions are **sealed** — fixed and
fingerprinted so they cannot be edited afterward. The operation runs. An
independent process then **re-executes those sealed checks** against the recorded
result, in a separate workspace, and publishes a tamper-evident bundle containing
the commands run, their exit codes, the resulting state change, and the
independent verdict. A failed validation publishes nothing. This is the
machinery already implemented in this repository for software delivery
(Explorer, Builder, Curator; `hive-mind verify`), pointed at physical operations.

**Why it is dual-use, which is the whole Rockets & Rigs thesis:** an uncrewed
offshore recovery platform and an automated cryogenic transfer at an LNG terminal
have the same unsolved problem — the autonomous system reports success, and the
operator, the insurer and the regulator each have to take its word for it. NASA
has documented this as a genuine barrier to certifying autonomous systems (S11).
Offshore energy already runs on a safety-case culture that expects auditable
evidence. The same evidence layer serves both, and both customers are inside a
30 km radius of Brownsville.

**Beachhead:** one design partner, one operation, one sealed check, one bundle a
regulator or insurer would accept. Not a platform. Not a suite.

**Business model:** per-operation assurance subscription plus a one-time
integration fee; expand by operation count, not by seat count.

**What the $32,000 actually buys** — this is the slide that wins non-dilutive
prizes, because it makes the money legible:

| Use | Amount |
|---|---|
| Design-partner pilot: instrument one real local operation end to end | $14,000 |
| NASA Software Catalog licence integration and formal-methods conformance work | $6,000 |
| Independent third-party review of one published bundle | $5,000 |
| Legal: entity formation, licence agreements, design-partner terms | $4,000 |
| Travel and demonstration hardware for the pitch and follow-on meetings | $3,000 |

**Follow-on ladder:** AFRL/SpaceWERX and NASA SBIR topics on trusted autonomy and
mission assurance; DOE programmes on methane and facility safety; EDA and Texas
Space Commission regional instruments. Each is a reportable Capital Formation
outcome for ExF, which is exactly what their SBA award obliges them to produce
(S6).

**RGV commitment (borrowed from the credentialing entrant):** first two technical
hires from UTRGV or Texas Southmost College, stated on the slide with numbers.

**Honesty constraints that must survive into the pitch**, because breaking them
is both wrong and, in a room of practitioners, fatal:

- Say "working prototype, deterministic offline demonstration, no production
  deployment and no user validation yet." That is what the README says (S19) and
  a judge who clones the repository will read it.
- Do not claim a NASA patent licence until one is signed. Say "NASA Software
  Catalog tooling, application in progress" if that is the true state.
- Do not present the Project Able Baker figures (S17) as fact. They are
  single-aggregator sourced. Say "reported" or verify them first via O6.
- Do not claim the evidence format is novel against Sigstore, in-toto or SLSA.
  Claim the independent re-execution of a pre-sealed check, which is the part
  that is actually different.

---

## 10. Unknowns

1. The real ExF rubric and deadline (O1, O2). Everything is scheduled off these.
2. Whether the 2026 prize is still $32,000 and how it splits (O3).
3. Eligibility mechanics: incorporation, residency, stage limits, re-entry (O4).
4. Prior winners, which reveal panel preference better than any rubric (O5).
5. Whether the AFRL offshore recovery programme carries a real autonomy-assurance
   requirement (O6).
6. Whether a specific NASA Software Catalog item or Startup NASA patent is
   licensable for this concept and on what terms (O7).
7. Whether a Brownsville design partner will sign inside the competition
   timeline. This is the single highest-variance unknown in the plan, and node
   `EF-040` is the go/no-go on it.

---

## 11. What would change this answer

State the falsifiers up front, so the recommendation can be killed cleanly:

- ExF publishes a rubric that weights hardware or a NASA patent licence above
  capital efficiency and traction → switch to CryoAssay.
- No Brownsville design partner signs within 30 days → the winner has no wedge
  and drops behind CryoAssay and Saltline.
- A cryogenics co-founder joins → CryoAssay overtakes the winner outright.
- The competition requires a formed Texas entity with revenue → re-score the
  whole field on eligibility before anything else.
