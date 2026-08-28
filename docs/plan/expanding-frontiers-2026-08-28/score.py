#!/usr/bin/env python3
"""EXF-040 scorer: recomputes every weighted score from published inputs.

Run from the repository root:
    python docs/plan/expanding-frontiers-2026-08-28/score.py
"""
from __future__ import annotations

import json
from pathlib import Path

WEIGHTS = {
    "nasa_tech_transfer_fit": 0.18,
    "space_energy_intersection": 0.16,
    "regional_economic_impact": 0.15,
    "non_dilutive_follow_on": 0.13,
    "demonstrability_at_pitch": 0.12,
    "founder_asset_advantage": 0.10,
    "capital_efficiency": 0.08,
    "regulatory_headroom": 0.08,
}
VETO_CRITERIA = ("regional_economic_impact", "regulatory_headroom")
VETO_THRESHOLD = 3

ENTRANTS = {
    "T1": ("Corrosion-evidence coating", [10, 9, 9, 8, 10, 7, 6, 7]),
    "T2": ("Cryogenic boil-off recovery", [8, 10, 9, 8, 4, 2, 2, 4]),
    "T3": ("Compliance evidence platform", [4, 8, 6, 7, 8, 9, 9, 8]),
    "T4": ("Flare-gas to propellant", [5, 10, 7, 7, 3, 1, 2, 3]),
    "T5": ("Hydrogen-sensing tape", [9, 8, 5, 6, 8, 1, 6, 6]),
    "T6": ("Cryo GSE predictive maintenance", [4, 9, 5, 6, 6, 5, 8, 8]),
    "T7": ("Composite cryogenic valve", [9, 10, 5, 7, 6, 1, 4, 5]),
    "T8": ("AI-code assurance receipts (standalone)", [2, 3, 2, 6, 7, 10, 10, 9]),
    "T9": ("Veterans credentialing platform", [1, 6, 10, 8, 5, 2, 8, 9]),
    "T10": ("Space-weather grid alerting", [7, 9, 4, 6, 7, 3, 8, 8]),
}


def evaluate() -> list[dict]:
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1.0"
    names = list(WEIGHTS)
    rows = []
    for key, (title, values) in ENTRANTS.items():
        assert len(values) == len(names), f"{key} score vector length mismatch"
        scores = dict(zip(names, values))
        weighted = round(sum(scores[n] * WEIGHTS[n] for n in names), 4)
        vetoes = [c for c in VETO_CRITERIA if scores[c] <= VETO_THRESHOLD]
        rows.append(
            {
                "id": key,
                "name": title,
                "scores": scores,
                "weighted_score": weighted,
                "vetoed": bool(vetoes),
                "veto_criteria": vetoes,
            }
        )
    rows.sort(key=lambda r: (r["vetoed"], -r["weighted_score"]))
    for rank, row in enumerate(rows, start=1):
        row["round1_rank"] = rank if not row["vetoed"] else None
    return rows


if __name__ == "__main__":
    results = evaluate()
    width = max(len(r["name"]) for r in results)
    print(f"{'ID':<4} {'ENTRANT':<{width}}  {'WEIGHTED':>8}  {'RANK':>4}  STATUS")
    for row in results:
        status = "VETOED: " + ", ".join(row["veto_criteria"]) if row["vetoed"] else "advanced"
        rank = row["round1_rank"] or "-"
        print(f"{row['id']:<4} {row['name']:<{width}}  {row['weighted_score']:>8.4f}  {rank:>4}  {status}")
    Path(__file__).with_name("round1_scores.json").write_text(
        json.dumps({"weights": WEIGHTS, "veto_threshold": VETO_THRESHOLD,
                    "veto_criteria": list(VETO_CRITERIA), "results": results},
                   indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
