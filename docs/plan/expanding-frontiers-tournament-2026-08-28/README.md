# Expanding Frontiers award tournament — 2026-08-28

GenericPrompt (`prompts/shared/ULTIMATE_SOLUTION_TOURNAMENT.md`) executed against
the SUBJECT: **which venture idea most likely wins a grant or award from
[Expanding Frontiers](https://www.expandingfrontiers.org), the Brownsville, Texas
space-and-energy innovation nonprofit.**

## Read in this order

| File | What it is |
|---|---|
| `FULL_REPORT.md` | The investigation. Start at section 0 for the answer, section 2.1 for where the answer breaks. |
| `DO_THIS_NEXT.md` | The handoff. Exact sessions, models and prompts. |
| `SOURCE_REGISTER.md` | Every source with a confidence level, and the seven obligations that are still open. |
| `EXECUTION_DAG.json` | 15-node execution graph for the winner, with full section-17 node contracts. |
| `TOURNAMENT_RESULTS.json` | Machine-readable scoring: 30 entrants, 4 hybrids, 6 rubric-sensitivity variants. |
| `score_tournament.py` | Regenerates the results. Change the inputs to challenge the ranking. |
| `validate_dag.py` | Checks the DAG for dependency, cycle, level-ordering and contract-completeness defects. |

## Result

| Rank | Idea | Weighted |
|---|---|---|
| 1 | **Frontier Assurance** — a sealed flight recorder for autonomous operations, wedged into offshore booster recovery and cryogenic propellant transfer | 8.79 |
| 2 | **CryoAssay** — propellant-grade LNG certification and boil-off loss accounting for the Brownsville cryo corridor | 8.02 |
| 3 | **Saltline** — Startup-NASA-licensed corrosion and thermal-protection coatings for converted Gulf recovery platforms | 6.84 |

Verdict **ADAPT**: the winner is a hybrid that did not exist before the tournament.
Confidence **medium** and conditional — the sensitivity analysis in section 2.1 flips
the winner to CryoAssay under a hardware-favouring rubric, and obtaining the real
rubric is node `EF-000`, the first thing to do.

## Level graph

```mermaid
graph TD
  subgraph L0["Level 0 — evidence gates, parallel"]
    EF000["EF-000 rules, rubric, deadline, eligibility"]
    EF001["EF-001 prior winners"]
    EF002["EF-002 verify AFRL programme claims"]
    EF003["EF-003 licensable NASA technology"]
  end
  subgraph L1["Level 1 — decision"]
    EF010["EF-010 lock the entry, may overturn the winner"]
  end
  subgraph L2["Level 2 — parallel"]
    EF020["EF-020 eligibility compliance"]
    EF040["EF-040 design partner, highest variance"]
    EF080["EF-080 use of funds and follow-on ladder"]
  end
  subgraph L3["Level 3 — parallel"]
    EF030["EF-030 NASA technology binding"]
    EF050["EF-050 live demonstration"]
  end
  EF060["Level 4 — EF-060 business plan"]
  EF070["Level 5 — EF-070 pitch deck and script"]
  EF090["Level 6 — EF-090 independent adversarial review"]
  EF100["Level 7 — EF-100 submit, irreversible"]
  EF110["Level 8 — EF-110 follow-on non-dilutive applications"]

  EF000 --> EF010
  EF001 --> EF010
  EF003 --> EF010
  EF002 -.-> EF060
  EF010 --> EF020
  EF010 --> EF040
  EF010 --> EF050
  EF000 --> EF080
  EF020 --> EF030
  EF003 --> EF030
  EF040 --> EF050
  EF040 --> EF060
  EF030 --> EF060
  EF020 --> EF060
  EF050 --> EF070
  EF060 --> EF070
  EF060 --> EF090
  EF070 --> EF090
  EF080 --> EF090
  EF090 --> EF100
  EF020 --> EF100
  EF080 --> EF110
  EF100 --> EF110
```

Critical path: `EF-000 -> EF-010 -> EF-040 -> EF-060 -> EF-090 -> EF-100`.

## Reproduce

```bash
python docs/plan/expanding-frontiers-tournament-2026-08-28/score_tournament.py
python docs/plan/expanding-frontiers-tournament-2026-08-28/validate_dag.py
```
