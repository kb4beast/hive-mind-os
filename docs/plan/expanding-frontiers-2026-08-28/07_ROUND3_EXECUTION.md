# EXF-060 — Round three: can this applicant actually execute and fund it?

**Node:** `EXF-060` · **Round:** R6 · **Roles:** Builder, Integrator
**Stopping condition:** execution readiness and a downstream funding path are recorded for every surviving entrant.

Rounds one and two asked which idea is best. Round three asks a narrower and more
decisive question: **which one can this applicant start on Monday, and what is the next
cheque after the prize?** An idea that cannot be demonstrated with assets already in
hand loses to a weaker idea that can be shown working.

## Applicant asset inventory (verified from this repository)

| Asset | State | Evidence |
|---|---|---|
| Tamper-evident receipt bundle generation | Working, offline, deterministic | `hive-mind demo` produces a receipt bundle; `hive-mind verify` validates a change against a pre-sealed specification |
| Independent re-execution of sealed checks | Working (Curator role) | Curator re-runs sealed checks in a separate workspace; a failed validation publishes nothing |
| Reversible evidence bundle: patch, manifest, validated receipt store, machine-readable report | Working | Documented and exercised by the bundled example |
| Governed DAG planning, linting and round compilation | Working | This document set was produced by it; the plan lints clean under `dag-lint --strict` |
| Materials science / coatings capability | **Absent** | — |
| Cryogenic process engineering capability | **Absent** | — |
| Field instrumentation and sensing capability | **Absent** | — |

The repository is explicit that it is an early prototype and not production-validated.
That is stated honestly here because a pitch that overclaims maturity fails the first
technical question from a judging panel, and because the receipt engine's value in these
entries is as a *credible working demonstrator*, not as a shipped product.

## T1 · Corrosion-evidence coating

| | |
|---|---|
| **Already exists** | The entire evidence layer: sealed inspection specifications, independent re-execution, tamper-evident bundles. A corrosion inspection is structurally the same object as a verified build — a declared scope, a sealed check, an independently re-run result, a signed receipt. |
| **Must be built** | NASA license (confirmation `C-1`); coating formulation transfer; coated test coupons; a phone-based indicator reader; a field pilot on one real asset. |
| **Must be partnered** | Materials/coatings capability. Candidate routes: UTRGV materials and chemistry faculty, a Port of Brownsville coatings applicator, ExF's own NASA JSC channel. |
| **Time to a pitch-grade demo** | Weeks. A salt-fog-exposed coupon that visibly indicates corrosion onset, photographed into a tamper-evident inspection receipt, is buildable before a cohort ends. |
| **Follow-on non-dilutive path** | NASA SBIR (technology infusion on a licensed NASA technology is the strongest possible framing); DOE SBIR under pipeline and storage integrity; the DoD Corrosion Prevention and Control programme, which exists specifically to fund this problem; ONR marine corrosion. |
| **Verdict** | Executable now, contingent on `C-1` and on securing one materials partner. |

## T3 · Compliance evidence platform

| | |
|---|---|
| **Already exists** | The same evidence layer — and here it is the whole product, not a component. |
| **Must be built** | Sensor ingestion; regulator-format export for FAA and TCEQ submissions; a customer willing to be measured. |
| **Time to a pitch-grade demo** | Days. This is the fastest demo in the field, because the applicant already has one. |
| **Follow-on non-dilutive path** | EPA SBIR; DOE SBIR; NASA SBIR under range and environmental operations; Texas state environmental technology programmes. |
| **Verdict** | Highest execution readiness in the entire field. Constrained by the buyer problem from round two, not by capability. |

## T2 · Cryogenic boil-off recovery

| | |
|---|---|
| **Already exists** | Nothing. |
| **Must be built** | Everything: process design, a cryogenic test rig, permits, a site partner. |
| **Time to a pitch-grade demo** | Years, and the demo is a simulation or a slide. |
| **Follow-on non-dilutive path** | Genuinely excellent — DOE SBIR, ARPA-E, and the DOE relationship ExF already holds. This is the one criterion on which T2 beats T1. |
| **Verdict** | Not executable by this applicant at this funding scale. Correct domain, wrong founder. |

## The decisive asymmetry

T2 has the best domain fit and the worst execution position. T3 has the best execution
position and the worst buyer. **T1 is the only entrant that is strong on both** — it
borrows T2's physical, regional, space-and-energy domain and T3's already-built evidence
mechanism, and it anchors the pair on an actual NASA license, which is the specific thing
this sponsor's pipeline exists to hand out.

That is not a compromise between two mediocre options. It is the hybrid the tournament
was run to find.
