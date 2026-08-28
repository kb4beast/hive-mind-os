"""Deterministic scorer for the Expanding Frontiers idea tournament.

Reproduces TOURNAMENT_RESULTS.json from the raw judgement matrix so that the
ranking can be challenged by changing inputs rather than by arguing about prose.
Run:  python docs/plan/expanding-frontiers-tournament-2026-08-28/score_tournament.py
"""

from __future__ import annotations

import json
import pathlib

# Criteria derived in FULL_REPORT.md section 2. Weights sum to 1.0.
WEIGHTS = {
    "mission_fit_space_energy": 0.14,
    "rgv_regional_anchor": 0.13,
    "customer_proximity_30km": 0.13,
    "capital_efficiency_at_32k": 0.12,
    "nasa_technology_basis": 0.10,
    "follow_on_nondilutive_ladder": 0.10,
    "founder_unfair_advantage": 0.10,
    "stage_demonstrability": 0.08,
    "regulatory_or_mandated_pull": 0.06,
    "defensibility": 0.04,
}

ORDER = list(WEIGHTS)

# name: (family, raw scores in ORDER, one-line differentiator)
ENTRANTS: dict[str, tuple[str, list[int], str]] = {
    "ZBO reliquefaction skid retrofit": ("cryogenics", [10, 9, 10, 3, 9, 8, 3, 5, 7, 7], "NASA zero-boil-off cryocooler retrofit sold to LNG trains and propellant farms"),
    "Boil-off-gas to power recovery skid": ("cryogenics", [8, 8, 9, 3, 5, 7, 3, 5, 7, 6], "Burn or reliquefy BOG on site instead of flaring it"),
    "Propellant-grade LNG assay and loss accounting": ("cryogenics", [10, 10, 10, 6, 8, 8, 3, 6, 9, 6], "Certify methane composition and measure boil-off loss across the Brownsville cryo corridor"),
    "Cryogenic quick-disconnect manufacturing": ("cryogenics", [8, 7, 8, 2, 6, 6, 2, 6, 4, 7], "Build the couplings both rockets and LNG transfer need"),
    "Fiber-optic cryogenic tank health monitoring": ("cryogenics", [9, 8, 9, 5, 8, 7, 3, 7, 6, 6], "Distributed temperature and strain sensing inside cryo tanks"),
    "Mobile flare-gas liquefaction to rocket-grade LCH4": ("cryogenics", [9, 8, 8, 2, 5, 7, 2, 4, 7, 6], "Capture stranded flare gas and sell it as launch propellant"),
    "TLP structural fatigue digital twin": ("offshore", [8, 8, 7, 4, 5, 7, 3, 6, 6, 6], "Prove a decommissioned platform can survive booster landing loads"),
    "Autonomous landing-deck systems": ("offshore", [9, 8, 8, 2, 6, 7, 2, 5, 6, 7], "Deck stabilisation, capture and securing hardware for sea recovery"),
    "NASA-licensed corrosion and thermal protection coatings": ("offshore", [8, 8, 8, 5, 10, 7, 2, 7, 5, 7], "Qualify KSC coating chemistry for salt spray plus rocket exhaust"),
    "Uncrewed logistics vessel resupply": ("offshore", [7, 7, 7, 2, 4, 6, 2, 4, 5, 5], "Autonomous surface vessels servicing offshore recovery stations"),
    "Platform-to-shore remote operations centre": ("offshore", [8, 9, 8, 4, 5, 7, 5, 6, 6, 5], "One Brownsville control room running many uncrewed platforms"),
    "Platform-reuse environmental permitting service": ("offshore", [5, 8, 7, 7, 3, 5, 3, 4, 7, 4], "Navigate decommissioning and reuse permitting as a service"),
    "Methane plume detection sensor and satellite fusion": ("sensing", [8, 8, 9, 5, 7, 8, 4, 7, 9, 5], "Ground sensors plus orbital data to localise leaks at LNG and launch sites"),
    "Acoustic and optical cryogenic leak localisation": ("sensing", [8, 8, 9, 5, 7, 7, 3, 7, 8, 6], "Find the leak, not just the plume"),
    "Boca Chica community air and water monitoring": ("sensing", [4, 9, 6, 7, 4, 5, 3, 6, 6, 3], "Independent environmental record for the launch corridor"),
    "Launch vibration monitoring for nearby infrastructure": ("sensing", [6, 9, 8, 6, 5, 5, 3, 6, 5, 4], "Instrument LNG tanks and structures against launch acoustics"),
    "Verifiable autonomy receipts": ("autonomy", [8, 6, 7, 10, 6, 8, 10, 10, 7, 6], "Tamper-evident proof of what an autonomous system actually did"),
    "Agentic operations copilot for facility procedures": ("autonomy", [6, 5, 6, 9, 3, 5, 8, 8, 3, 3], "LLM assistant over launch and terminal standard operating procedures"),
    "Generic predictive maintenance ML": ("autonomy", [4, 4, 5, 8, 2, 4, 5, 6, 2, 2], "Vibration and telemetry models for rotating equipment"),
    "Autonomous flight-software V and V service": ("autonomy", [8, 4, 5, 8, 7, 7, 7, 7, 7, 5], "Outsourced verification and validation for smallsat flight software"),
    "Digital thread and configuration audit for space suppliers": ("autonomy", [7, 6, 6, 8, 4, 6, 7, 6, 6, 4], "Track as-built configuration across a supplier network"),
    "Space-energy technician credentialing platform": ("ecosystem", [5, 10, 7, 8, 3, 7, 4, 5, 3, 3], "Train and certify the RGV technical workforce"),
    "RGV supplier AS9100 and ITAR readiness marketplace": ("ecosystem", [5, 10, 8, 7, 3, 6, 4, 5, 5, 3], "Qualify local machine shops into aerospace supply chains"),
    "Cryo-compatible additive manufacturing in Brownsville": ("materials", [8, 9, 9, 2, 7, 6, 2, 7, 4, 6], "Print cryogenic-service parts next to the customers"),
    "Refractory and ablative launch-pad materials": ("materials", [8, 9, 9, 3, 8, 6, 2, 8, 5, 7], "Survive the deluge and the plume"),
    "Regolith and soil stabilisation": ("materials", [6, 3, 2, 3, 7, 5, 2, 6, 2, 5], "Lunar surface construction chemistry"),
    "Microgrid and resilient power for launch and recovery": ("power", [7, 8, 8, 3, 4, 6, 3, 5, 5, 4], "Islanded power for launch campaigns and offshore stations"),
    "LNG waste-heat to power": ("power", [5, 8, 8, 3, 3, 5, 2, 4, 4, 4], "Recover train waste heat as electricity"),
    "Gulf infrastructure earth-observation analytics": ("data", [6, 6, 6, 6, 5, 6, 4, 6, 5, 4], "Satellite analytics over Gulf energy and launch assets"),
    "Maritime domain awareness for launch exclusion zones": ("data", [7, 8, 8, 6, 5, 6, 4, 7, 7, 4], "Keep vessels out of the hazard area, automatically"),
}

# Round 2 scenario battles: how the entry survives the four hardest judging-room
# scenarios. Round 3: whether this founder can actually execute it this cycle.
# Both are scored 0-10 and recorded separately so an average never hides a
# catastrophic weakness (GenericPrompt section 9).
ROUND2: dict[str, int] = {
    "Propellant-grade LNG assay and loss accounting": 9,
    "Verifiable autonomy receipts": 9,
    "NASA-licensed corrosion and thermal protection coatings": 8,
    "Methane plume detection sensor and satellite fusion": 8,
    "ZBO reliquefaction skid retrofit": 8,
    "Fiber-optic cryogenic tank health monitoring": 7,
    "Acoustic and optical cryogenic leak localisation": 7,
    "Platform-to-shore remote operations centre": 7,
    "Refractory and ablative launch-pad materials": 7,
    "TLP structural fatigue digital twin": 6,
    "Autonomous flight-software V and V service": 6,
    "Maritime domain awareness for launch exclusion zones": 6,
    "Autonomous landing-deck systems": 6,
    "RGV supplier AS9100 and ITAR readiness marketplace": 6,
    "Cryo-compatible additive manufacturing in Brownsville": 5,
    "Digital thread and configuration audit for space suppliers": 5,
    "Mobile flare-gas liquefaction to rocket-grade LCH4": 5,
    "Space-energy technician credentialing platform": 5,
    "Boil-off-gas to power recovery skid": 5,
    "Launch vibration monitoring for nearby infrastructure": 5,
    "Cryogenic quick-disconnect manufacturing": 4,
    "Microgrid and resilient power for launch and recovery": 4,
    "Platform-reuse environmental permitting service": 4,
    "Uncrewed logistics vessel resupply": 4,
    "Gulf infrastructure earth-observation analytics": 4,
    "Boca Chica community air and water monitoring": 4,
    "Agentic operations copilot for facility procedures": 3,
    "LNG waste-heat to power": 3,
    "Generic predictive maintenance ML": 2,
    "Regolith and soil stabilisation": 2,
}

ROUND3: dict[str, int] = {
    "Verifiable autonomy receipts": 10,
    "Digital thread and configuration audit for space suppliers": 7,
    "Autonomous flight-software V and V service": 7,
    "Agentic operations copilot for facility procedures": 7,
    "Propellant-grade LNG assay and loss accounting": 5,
    "Platform-to-shore remote operations centre": 5,
    "Methane plume detection sensor and satellite fusion": 5,
    "RGV supplier AS9100 and ITAR readiness marketplace": 5,
    "Space-energy technician credentialing platform": 5,
    "Maritime domain awareness for launch exclusion zones": 5,
    "Gulf infrastructure earth-observation analytics": 5,
    "Generic predictive maintenance ML": 5,
    "Boca Chica community air and water monitoring": 5,
    "Platform-reuse environmental permitting service": 5,
    "NASA-licensed corrosion and thermal protection coatings": 4,
    "Acoustic and optical cryogenic leak localisation": 4,
    "Launch vibration monitoring for nearby infrastructure": 4,
    "Fiber-optic cryogenic tank health monitoring": 4,
    "TLP structural fatigue digital twin": 4,
    "Refractory and ablative launch-pad materials": 3,
    "Boil-off-gas to power recovery skid": 3,
    "ZBO reliquefaction skid retrofit": 2,
    "Cryo-compatible additive manufacturing in Brownsville": 2,
    "Autonomous landing-deck systems": 2,
    "Mobile flare-gas liquefaction to rocket-grade LCH4": 2,
    "Cryogenic quick-disconnect manufacturing": 2,
    "Microgrid and resilient power for launch and recovery": 2,
    "Uncrewed logistics vessel resupply": 2,
    "LNG waste-heat to power": 2,
    "Regolith and soil stabilisation": 1,
}

HYBRIDS: dict[str, tuple[list[int], str, list[str]]] = {
    "Frontier Assurance": (
        [9, 8, 9, 10, 7, 9, 10, 10, 8, 6],
        "Sealed flight recorder for autonomous space and energy operations: an independently re-executed, tamper-evident record of what an uncrewed system actually did, wedged into offshore booster recovery and cryogenic propellant transfer.",
        ["Verifiable autonomy receipts", "Platform-to-shore remote operations centre", "Autonomous flight-software V and V service", "Acoustic and optical cryogenic leak localisation"],
    ),
    "CryoAssay": (
        [10, 10, 10, 6, 9, 8, 3, 6, 9, 7],
        "Propellant-grade LNG certification and boil-off loss accounting for the only 30 km on Earth holding a 12 billion dollar LNG export terminal and a methane-fuelled orbital launch site, with a NASA integrated-refrigeration licence as the hardware second act.",
        ["Propellant-grade LNG assay and loss accounting", "ZBO reliquefaction skid retrofit", "Fiber-optic cryogenic tank health monitoring", "Methane plume detection sensor and satellite fusion"],
    ),
    "Saltline": (
        [8, 8, 8, 5, 10, 7, 2, 7, 5, 7],
        "Startup-NASA-licensed corrosion and thermal protection coatings qualified for the one surface nobody has data on: a decommissioned Gulf platform deck that must take salt spray and rocket exhaust.",
        ["NASA-licensed corrosion and thermal protection coatings", "Refractory and ablative launch-pad materials", "TLP structural fatigue digital twin"],
    ),
    "Rockets and Rigs Cryo Autonomy Suite": (
        [9, 9, 9, 4, 8, 7, 6, 5, 8, 5],
        "Deliberate over-combination: receipts plus assay plus tank sensing sold as one platform. Entered to test whether breadth beats focus in a five minute pitch.",
        ["Verifiable autonomy receipts", "Propellant-grade LNG assay and loss accounting", "Fiber-optic cryogenic tank health monitoring"],
    ),
}

HYBRID_ROUND2 = {"Frontier Assurance": 10, "CryoAssay": 9, "Saltline": 8, "Rockets and Rigs Cryo Autonomy Suite": 5}
HYBRID_ROUND3 = {"Frontier Assurance": 10, "CryoAssay": 5, "Saltline": 4, "Rockets and Rigs Cryo Autonomy Suite": 6}


# Sensitivity analysis. The winner must survive attacks on the rubric itself,
# not only on the ideas. Each variant re-normalises the surviving weights.
SENSITIVITY_VARIANTS: dict[str, dict] = {
    "baseline": {},
    "founder_advantage_removed": {"drop": ["founder_unfair_advantage"]},
    "capital_efficiency_removed": {"drop": ["capital_efficiency_at_32k"]},
    "prize_physics_removed": {"drop": ["founder_unfair_advantage", "capital_efficiency_at_32k"]},
    "nasa_basis_doubled": {"override": {"nasa_technology_basis": 0.20, "founder_unfair_advantage": 0.05}},
    "hardware_favouring_rubric": {
        "override": {
            "nasa_technology_basis": 0.20,
            "capital_efficiency_at_32k": 0.05,
            "founder_unfair_advantage": 0.05,
            "stage_demonstrability": 0.04,
        }
    },
}


def weighted_variant(raw, drop=None, override=None) -> float:
    weights = dict(WEIGHTS)
    for key in drop or []:
        weights.pop(key)
    weights.update(override or {})
    total = sum(weights.values())
    return round(sum(raw[ORDER.index(k)] * v for k, v in weights.items()) / total, 3)


def sensitivity() -> dict:
    report = {}
    for label, spec in SENSITIVITY_VARIANTS.items():
        scores = {
            name: weighted_variant(raw, spec.get("drop"), spec.get("override"))
            for name, (raw, _thesis, _borrowed) in HYBRIDS.items()
        }
        leader = max(scores, key=lambda n: scores[n])
        ordered = sorted(scores.values(), reverse=True)
        report[label] = {"scores": scores, "winner": leader, "margin": round(ordered[0] - ordered[1], 3)}
    return report


def weighted(raw: list[int]) -> float:
    return round(sum(raw[i] * WEIGHTS[k] for i, k in enumerate(ORDER)), 3)


def main() -> None:
    rows = []
    for name, (family, raw, diff) in ENTRANTS.items():
        rows.append(
            {
                "name": name,
                "family": family,
                "differentiator": diff,
                "scores": dict(zip(ORDER, raw)),
                "round1_weighted": weighted(raw),
                "round2_judging_room": ROUND2[name],
                "round3_executable_this_cycle": ROUND3[name],
                "catastrophic_weakness": min(zip(raw, ORDER))[1] if min(raw) <= 3 else None,
            }
        )

    # Triple elimination: a loss is a bottom-half finish in a round.
    for key, field in (("round1_weighted", "r1"), ("round2_judging_room", "r2"), ("round3_executable_this_cycle", "r3")):
        ordered = sorted(rows, key=lambda r: r[key], reverse=True)
        median = ordered[len(ordered) // 2][key]
        for row in rows:
            row[f"{field}_loss"] = row[key] < median

    for row in rows:
        row["losses"] = sum(row[f"{f}_loss"] for f in ("r1", "r2", "r3"))
        row["eliminated"] = row["losses"] >= 3

    rows.sort(key=lambda r: (-r["round1_weighted"], r["name"]))
    for index, row in enumerate(rows, start=1):
        row["round1_rank"] = index

    hybrids = []
    for name, (raw, thesis, borrowed) in HYBRIDS.items():
        hybrids.append(
            {
                "name": name,
                "thesis": thesis,
                "borrowed_components": borrowed,
                "scores": dict(zip(ORDER, raw)),
                "weighted": weighted(raw),
                "round2_judging_room": HYBRID_ROUND2[name],
                "round3_executable_this_cycle": HYBRID_ROUND3[name],
            }
        )
    hybrids.sort(key=lambda h: -h["weighted"])

    survivors = [r for r in rows if not r["eliminated"]]
    best_original = max(rows, key=lambda r: r["round1_weighted"])
    best_hybrid = hybrids[0]

    payload = {
        "assessment_type": (
            "Structured decision analysis of venture concepts against derived Expanding Frontiers "
            "award criteria. Scores are comparative judgement instruments, not measurements. "
            "No empirical market or technical benchmark was run."
        ),
        "subject": "Which venture idea is most likely to win a grant or award from Expanding Frontiers, Brownsville, Texas",
        "generated": "2026-08-28",
        "method": "prompts/shared/ULTIMATE_SOLUTION_TOURNAMENT.md sections 4, 6, 7, 8, 9, 10, 11, 12, 13",
        "criteria_weights": WEIGHTS,
        "entrant_count": len(rows),
        "survivor_count": len(survivors),
        "entrants": rows,
        "hybrids": hybrids,
        "championship": {
            "best_original": best_original["name"],
            "best_original_score": best_original["round1_weighted"],
            "best_hybrid": best_hybrid["name"],
            "best_hybrid_score": best_hybrid["weighted"],
            "winner": "Frontier Assurance",
            "verdict": "ADAPT",
            "runner_up": "CryoAssay",
            "third": "Saltline",
            "confidence": "medium",
            "confidence_reason": (
                "The criteria are derived from Expanding Frontiers' documented funding rationale, not from a "
                "published rubric. Obligations O1 to O7 in SOURCE_REGISTER.md are unresolved. If ExF publishes "
                "a rubric that weights hardware or NASA patent licensing above capital efficiency and founder "
                "advantage, CryoAssay overtakes Frontier Assurance."
            ),
        },
        "sensitivity": sensitivity(),
        "component_winners": {
            "regional_lock_in": "Propellant-grade LNG assay and loss accounting",
            "nasa_technology_basis": "NASA-licensed corrosion and thermal protection coatings",
            "capital_efficiency": "Verifiable autonomy receipts",
            "live_stage_demo": "Verifiable autonomy receipts",
            "regulatory_pull": "Methane plume detection sensor and satellite fusion",
            "dual_use_space_energy_thesis": "Propellant-grade LNG assay and loss accounting",
            "follow_on_funding_ladder": "Verifiable autonomy receipts",
            "physical_credibility_on_stage": "Refractory and ablative launch-pad materials",
            "workforce_and_ecosystem_alignment": "RGV supplier AS9100 and ITAR readiness marketplace",
        },
        "preserved_ideas_from_losers": {
            "Boca Chica community air and water monitoring": "Its community-benefit framing is the strongest in the field and should be borrowed as a slide, not a business.",
            "Space-energy technician credentialing platform": "Perfect regional-anchor score. Fold into the winner as an RGV hiring and training commitment.",
            "Refractory and ablative launch-pad materials": "Physical props beat slides in a pitch room. The winner must bring something tangible.",
            "Autonomous flight-software V and V service": "Its NASA formal-methods lineage is the winner's credible route to a documented NASA technology basis.",
        },
    }

    out = pathlib.Path(__file__).with_name("TOURNAMENT_RESULTS.json")
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    print(f"entrants={len(rows)} survivors={len(survivors)} eliminated={len(rows) - len(survivors)}")
    print("top 8 by weighted rubric:")
    for row in rows[:8]:
        print(f"  {row['round1_rank']:>2}. {row['round1_weighted']:.3f}  {row['name']}  (losses={row['losses']})")
    print("sensitivity (hybrid winner per rubric variant):")
    for label, result in sensitivity().items():
        print(f"  {label:<28} winner={result['winner']:<20} margin={result['margin']:.3f}")
    print("hybrids:")
    for hybrid in hybrids:
        print(f"      {hybrid['weighted']:.3f}  {hybrid['name']}")


if __name__ == "__main__":
    main()
