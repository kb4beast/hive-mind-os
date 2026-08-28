# EXF-040 — Round one: weighted scoring and vetoes

**Node:** `EXF-040` · **Round:** R4 · **Role:** Curator
**Stopping condition:** all entrants carry a reproducible weighted score and the veto outcomes are recorded.

Scores are reproducible. `score.py` in this directory recomputes every number below from
the published per-criterion scores and the weights in `03_EVALUATION_SYSTEM.md`, and
writes `round1_scores.json`:

```
python docs/plan/expanding-frontiers-2026-08-28/score.py
```

## Per-criterion scores (0–10)

| Entrant | NASA fit ×.18 | Space×Energy ×.16 | Regional ×.15 | Follow-on ×.13 | Demo ×.12 | Founder asset ×.10 | Capital eff. ×.08 | Reg. headroom ×.08 | **Weighted** |
|---|---|---|---|---|---|---|---|---|---|
| **T1** Corrosion-evidence coating | 10 | 9 | 9 | 8 | 10 | 7 | 6 | 7 | **8.57** |
| **T3** Compliance evidence platform | 4 | 8 | 6 | 7 | 8 | 9 | 9 | 8 | **7.03** |
| **T2** Cryogenic boil-off recovery | 8 | 10 | 9 | 8 | 4 | 2 | 2 | 4 | **6.59** |
| **T10** Space-weather grid alerting | 7 | 9 | 4 | 6 | 7 | 3 | 8 | 8 | **6.50** |
| **T5** Hydrogen-sensing tape | 9 | 8 | 5 | 6 | 8 | 1 | 6 | 6 | **6.45** |
| **T7** Composite cryogenic valve | 9 | 10 | 5 | 7 | 6 | 1 | 4 | 5 | **6.42** |
| **T6** Cryo GSE predictive maintenance | 4 | 9 | 5 | 6 | 6 | 5 | 8 | 8 | **6.19** |
| **T9** Veterans credentialing | 1 | 6 | 10 | 8 | 5 | 2 | 8 | 9 | **5.84** |
| ~~T4~~ Flare-gas to propellant | 5 | 10 | 7 | 7 | 3 | 1 | 2 | **3** | 5.32 |
| ~~T8~~ AI-code assurance receipts | 2 | 3 | **2** | 6 | 7 | 10 | 10 | 9 | 5.28 |

## Veto outcomes

| Entrant | Vetoing criterion | Why it is a veto and not a penalty |
|---|---|---|
| **T4** Flare-gas to propellant | `regulatory_headroom` = 3 | Gas processing and propellant-spec production sit behind TCEQ air permitting and pipeline authority. No prize shortens that. The award would fund a waiting room. |
| **T8** AI-code assurance receipts, standalone | `regional_economic_impact` = 2 | A developer-tools company can be run from anywhere. ExF's own money comes from EDA, SBA and BCIC, all of which are buying South Texas outcomes. A generic devtool gives their funders nothing to report. |

**The T8 result is the most important finding of round one, and it cuts against the
applicant's own asset.** The strongest thing in the applicant's hands — a working
tamper-evident receipt engine — loses outright when pitched as itself. It scores 10, 10
and 9 on founder advantage, capital efficiency and regulatory headroom, and still fails,
because it has no answer to the two questions this sponsor actually asks: *which NASA
technology* and *what happens in South Texas*.

That does not mean the asset is worthless here. It means the asset is a **component**,
not an entry. Round two tests whether pairing it with a physical, licensable, locally
anchored technology survives attack — which is exactly what T1 and T3 are.

## Advancing to round two

T1, T3, T2, T10, T5, T7 advance. T6 and T9 are eliminated on score: T6 is dominated by
T3 on mechanism and by T2 on domain; T9 scores 10 on regional impact but 1 on NASA
transfer fit, and a technology pitch competition is the wrong venue for a workforce
programme — it is a strong idea aimed at the wrong door.
