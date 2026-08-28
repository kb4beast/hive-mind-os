# DO THIS NEXT

Two tracks. They are independent, so the student never waits on the venture.

---

## Before anything: the call that can kill this

**One conversation with Expanding Frontiers, three questions.** These are nodes
`WS-000`, `WS-001` and `YM-000`, and any of them can end the plan, which is why they
come first.

1. *"Is anyone already doing calibrated community overpressure or noise monitoring at
   a spaceport? Airports all do it. Do you know of a spaceport that does?"* ExF sits
   inside this ecosystem. If anyone knows, they do. **If the answer is yes, both
   winners collapse and the answer becomes Peninsula.**
2. *"Would you see an independent launch-impact measurement venture as coexistence
   infrastructure for the ecosystem, or as adversarial to it?"* Ask it in those words.
   Do not guess. If they hear it as adversarial, keep the idea and change the venue.
3. *"For the Space Entrepreneur Summer Academy: what are the 2026 dates and deadline,
   and do students bring their own project or get assigned one?"* The youth plan
   depends entirely on the last part.

The heaviest criterion in the whitespace tournament, at 0.20, is scored from failing
to find a competitor in a web search. That is the weakest evidence in this document
and the claim most likely to be wrong. `WS-000` exists to attack it properly: USPTO,
SBIR and STTR awards, Crunchbase, trade press, FAA and Cameron County filings, plus
that question to ExF.

---

## Venture track — Boom Baseline

**Session 1 (nodes WS-000, WS-001, WS-002).** Sonnet-class, medium effort.

> Read `docs/plan/expanding-frontiers-whitespace-and-youth-2026-08-28/SOURCE_REGISTER.md`
> and `EXECUTION_DAG_VENTURE.json`. Execute WS-000, WS-001 and WS-002 in parallel.
> WS-000 is the important one: your job is to DISPROVE the claim that nobody is doing
> calibrated community overpressure monitoring at a spaceport. Search USPTO, SBIR and
> STTR award databases, Crunchbase, aerospace and acoustics trade press, FAA
> environmental filings and Cameron County records. Produce
> `WHITESPACE_VERIFICATION.md`. Record negative results as "searched X, Y, Z and found
> nothing", never as "nobody is doing this". If you find a competitor, say so plainly
> and do not defend the recommendation. Stop there. Write no pitch and no plan.

**Session 2 (WS-010).** Opus-class, high effort. Lock the entry and venue, re-running
`score_tournaments.py` with any corrected inputs. This node is allowed to overturn the
winner.

**Then WS-020 first and hardest.** Find one payer who will state in writing what they
would pay. This is the weakest part of the whole idea, stated honestly: airports fund
their own monitoring, and the analogous payer here is unconfirmed. If no payer exists
after 30 days, that is a real finding — it means this is a public-good programme and a
student project rather than a venture, and saying so is better than pitching a
business with no buyer.

`WS-030` (consent and privacy) runs in parallel and is not optional. Publishing
measurements about identifiable homes without a policy is how this goes wrong.

---

## Youth track — The Boom Map

Runs independently. A student can start `YM-010` the day `YM-000` answers.

**The order matters and is deliberate: the consent protocol is written before the
first sensor is built.** Not bureaucracy. It is what makes the project defensible, and
a judging panel will notice that a sixteen-year-old thought about consent before
hardware.

1. **`YM-000`** — SESA dates, deadline, and whether students bring their own project.
   Conrad Challenge and Diamond Challenge as alternates; the same work fits all three
   with no rework.
2. **`YM-010`** — one page: homeowner consent, parental consent, school permission,
   and a publication policy that never identifies an address.
3. **`YM-020`** — build three nodes, starting on your own house, and calibrate them
   against each other. Under $500 total. Write the build guide as you go.
4. **`YM-030`** — recruit twelve to fifteen homes plus the school. Eight is the floor.
   Spread them by distance; the gradient is the science.
5. **`YM-040`** — capture a launch, publish the map, the method, the limitations and
   the raw data.
6. **`YM-050`** — submit.

**The pitch is one sentence:** *every airport measures its noise, no spaceport does,
so I built the first one.*

---

## Hard stops, both tracks

- **Never claim causation.** The data measures what arrived at a house. It does not
  measure what caused a crack. Say that out loud, in the pitch and in the writeup. It
  is both the honest position and the credible one.
- **Never build a plaintiff-side business.** Same data, same terms, to every party
  including the operator. The moment it serves one side, its value is gone.
- **Never publish an address.** Aggregate by street or larger, with written consent
  before installation.
- **Do not say "nobody is doing this"** until `WS-000` is done. Say "we searched these
  places and found nothing."
- **Do not put a minor near cryogens, rocket hardware, industrial property or a
  wildlife refuge permit.** Every node in the youth track is designed to avoid this.
- **Do not lead the sargassum idea with the yield.** Lead with the arsenic. Methane
  yield is modest and the contamination is real; a judge who knows the field will ask,
  and having asked it first is the difference between credible and not.

---

## Reproduce and validate

```bash
python docs/plan/expanding-frontiers-whitespace-and-youth-2026-08-28/score_tournaments.py
python docs/plan/expanding-frontiers-whitespace-and-youth-2026-08-28/validate_dag.py
```
