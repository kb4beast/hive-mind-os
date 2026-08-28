"""Deterministic scorer for two Expanding Frontiers tournaments.

Tournament B — WHITESPACE: ideas nobody else is doing.
Tournament C — YOUTH: ideas a high school student can personally pitch and execute.

Both are re-runs of prompts/shared/ULTIMATE_SOLUTION_TOURNAMENT.md with rubrics
rebuilt for their subject (section 4), so the ranking is challenged by editing
inputs rather than by arguing with prose.

Run: python docs/plan/expanding-frontiers-whitespace-and-youth-2026-08-28/score_tournaments.py
"""

from __future__ import annotations

import json
import pathlib

# --------------------------------------------------------------------------
# Emptiness classification. Scoring "nobody is doing it" without asking WHY is
# how a tournament rewards a trap. Two classes are auto-disqualifying.
# --------------------------------------------------------------------------
EMPTINESS_CLASSES = {
    "EMPTY_BECAUSE_NEW": "A precondition became true recently. The best kind of empty.",
    "EMPTY_BECAUSE_HARD": "Genuinely difficult. Empty is a moat if you can do it.",
    "EMPTY_BECAUSE_UNGLAMOROUS": "Nobody wants the work. Durable and underrated.",
    "EMPTY_BECAUSE_GATED": "Access, permission or regulation blocks entry. Empty but you may be blocked too.",
    "EMPTY_BECAUSE_BAD": "DISQUALIFYING. Empty because it does not work or has no buyer.",
    "NOT_ACTUALLY_EMPTY": "DISQUALIFYING. Someone is already doing this.",
}
DISQUALIFYING = {"EMPTY_BECAUSE_BAD", "NOT_ACTUALLY_EMPTY"}

# --------------------------------------------------------------------------
# Tournament B — WHITESPACE
# --------------------------------------------------------------------------
B_WEIGHTS = {
    "whitespace_uncontested": 0.20,
    "emptiness_is_not_a_trap": 0.14,
    "mission_fit_space_energy": 0.11,
    "rgv_regional_anchor": 0.11,
    "customer_proximity_30km": 0.10,
    "capital_efficiency_at_32k": 0.10,
    "timing_precondition_just_became_true": 0.09,
    "stage_demonstrability": 0.06,
    "regulatory_or_mandated_pull": 0.05,
    "defensibility_once_proven": 0.04,
}
B_ORDER = list(B_WEIGHTS)

# name: (scores in B_ORDER, emptiness class, one line)
B_ENTRANTS = {
    "Independent launch overpressure record": ([9, 8, 7, 10, 9, 8, 10, 8, 8, 5], "EMPTY_BECAUSE_NEW", "Calibrated per-property overpressure and vibration monitoring around a launch site, the way every major airport already monitors noise"),
    "Launch site by LNG terminal co-located hazard model": ([10, 7, 10, 10, 10, 7, 9, 5, 8, 6], "EMPTY_BECAUSE_GATED", "Nobody has modelled what an anomaly at one does to the other, and this pairing did not exist anywhere until now"),
    "Sargassum to rocket-grade biomethane": ([9, 5, 10, 10, 9, 4, 7, 7, 5, 6], "EMPTY_BECAUSE_HARD", "Turn the beach plague into launch propellant, with arsenic as the unsolved problem"),
    "Boil-off gas pipeline from LNG terminal to launch site": ([9, 6, 10, 10, 10, 3, 8, 4, 6, 7], "EMPTY_BECAUSE_HARD", "The terminal vents methane; the launch site buys methane; nobody has physically connected them"),
    "Launch corridor structural design standard": ([9, 7, 6, 10, 8, 7, 9, 5, 7, 5], "EMPTY_BECAUSE_NEW", "No building code anywhere addresses repeated rocket overpressure on residential structures"),
    "Parametric insurance for launch-adjacent property": ([9, 5, 5, 10, 9, 4, 9, 5, 6, 6], "EMPTY_BECAUSE_GATED", "No insurer offers launch-overpressure cover; a startup cannot easily become an insurer"),
    "Independent launch methane venting measurement": ([8, 7, 9, 9, 9, 7, 8, 6, 7, 5], "EMPTY_BECAUSE_UNGLAMOROUS", "Methane-fuelled launch operations vent; nobody independently quantifies it"),
    "Spanish-language space technical credentialing": ([8, 8, 5, 10, 8, 8, 6, 5, 3, 4], "EMPTY_BECAUSE_UNGLAMOROUS", "A 90 percent Hispanic workforce region with no space technical training in Spanish"),
    "Gulf reentry and debris corridor awareness": ([8, 7, 8, 7, 7, 6, 9, 6, 7, 5], "EMPTY_BECAUSE_NEW", "Offshore energy crews and fishing fleets under a corridor that only recently became busy"),
    "Launch closure economic impact accounting": ([9, 6, 4, 10, 8, 9, 8, 6, 5, 3], "EMPTY_BECAUSE_UNGLAMOROUS", "Road and beach closures cost Port Isabel real money that nobody has ever measured"),
    "Launch acoustics effect on protected wildlife": ([9, 6, 5, 10, 7, 7, 8, 6, 8, 4], "EMPTY_BECAUSE_GATED", "Boca Chica is a wildlife refuge; independent acoustic ecology data barely exists"),
    "Cross-facility emergency response simulator": ([9, 7, 9, 10, 9, 6, 8, 6, 7, 5], "EMPTY_BECAUSE_UNGLAMOROUS", "One shared drill for a launch site, an LNG terminal and a port that share a peninsula"),
    "Launch proximity property valuation model": ([8, 6, 4, 10, 8, 8, 8, 6, 4, 4], "EMPTY_BECAUSE_NEW", "Nobody can price a house near a spaceport because the data does not exist"),
    "Recovery platform biofouling and marine growth": ([8, 6, 7, 6, 6, 4, 7, 5, 4, 5], "EMPTY_BECAUSE_UNGLAMOROUS", "Converted offshore platforms will foul; nobody has studied it for this use"),
    "Recovered booster corrosion forensics": ([9, 5, 8, 7, 6, 5, 7, 6, 4, 6], "EMPTY_BECAUSE_GATED", "Sea-recovered hardware degradation data that only the operator holds"),
    "School and public building vibration hardening": ([9, 7, 4, 10, 8, 6, 9, 6, 6, 4], "EMPTY_BECAUSE_UNGLAMOROUS", "Point Isabel district buildings take the same overpressure as homes, with children inside"),
    "Retired flight hardware second-life materials": ([9, 3, 7, 7, 7, 4, 6, 7, 3, 5], "EMPTY_BECAUSE_GATED", "ITAR and an operator with no incentive to sell scrap. Empty and likely to stay empty for you"),
    "Sargassum to agricultural fertiliser": ([6, 5, 3, 10, 7, 5, 6, 6, 4, 4], "NOT_ACTUALLY_EMPTY", "Caribbean and Mexican groups are already commercialising this"),
    "Launch schedule forecasting for local business": ([7, 4, 3, 9, 7, 9, 6, 5, 2, 2], "EMPTY_BECAUSE_BAD", "Cheap to build, and nobody will pay for a guess at a schedule the operator controls"),
    "Beach debris citizen mapping": ([7, 6, 4, 9, 6, 9, 7, 6, 5, 2], "EMPTY_BECAUSE_UNGLAMOROUS", "Post-launch debris surveys done publicly rather than by the operator"),
    "Launch water deluge runoff monitoring": ([8, 6, 6, 10, 8, 6, 8, 6, 8, 4], "EMPTY_BECAUSE_GATED", "Deluge discharge chemistry, measured off the operator's property line"),
    "Cryogenic road transport risk mapping": ([8, 7, 9, 9, 8, 8, 7, 6, 6, 4], "EMPTY_BECAUSE_UNGLAMOROUS", "Liquid methane trucked through a populated corridor on public roads, unmapped"),
    "Dark sky and light pollution from launch operations": ([7, 4, 3, 8, 6, 8, 5, 5, 3, 2], "EMPTY_BECAUSE_BAD", "Real but nobody funds it and there is no buyer"),
    "Space workforce housing analytics": ([6, 5, 3, 9, 7, 8, 7, 5, 3, 3], "NOT_ACTUALLY_EMPTY", "Standard real estate analytics applied to a boom town"),
}

B_ROUND2 = {  # survives the judging room: why here, who pays, what have you built, expert attack
    "Independent launch overpressure record": 9,
    "Launch site by LNG terminal co-located hazard model": 7,
    "Sargassum to rocket-grade biomethane": 8,
    "Cross-facility emergency response simulator": 7,
    "Independent launch methane venting measurement": 7,
    "Launch corridor structural design standard": 7,
    "Cryogenic road transport risk mapping": 7,
    "School and public building vibration hardening": 6,
    "Boil-off gas pipeline from LNG terminal to launch site": 6,
    "Spanish-language space technical credentialing": 6,
    "Launch closure economic impact accounting": 6,
    "Gulf reentry and debris corridor awareness": 6,
    "Launch proximity property valuation model": 5,
    "Launch acoustics effect on protected wildlife": 5,
    "Launch water deluge runoff monitoring": 5,
    "Parametric insurance for launch-adjacent property": 4,
    "Recovered booster corrosion forensics": 4,
    "Recovery platform biofouling and marine growth": 4,
    "Beach debris citizen mapping": 4,
    "Retired flight hardware second-life materials": 3,
    "Sargassum to agricultural fertiliser": 3,
    "Launch schedule forecasting for local business": 2,
    "Dark sky and light pollution from launch operations": 2,
    "Space workforce housing analytics": 2,
}

B_ROUND3 = {  # can a solo founder actually start this without gatekeeper permission
    "Independent launch overpressure record": 9,
    "Launch closure economic impact accounting": 9,
    "Launch proximity property valuation model": 8,
    "Spanish-language space technical credentialing": 8,
    "Beach debris citizen mapping": 8,
    "Cryogenic road transport risk mapping": 7,
    "Independent launch methane venting measurement": 7,
    "School and public building vibration hardening": 6,
    "Launch corridor structural design standard": 6,
    "Gulf reentry and debris corridor awareness": 6,
    "Cross-facility emergency response simulator": 5,
    "Sargassum to rocket-grade biomethane": 5,
    "Launch schedule forecasting for local business": 5,
    "Space workforce housing analytics": 5,
    "Dark sky and light pollution from launch operations": 5,
    "Launch acoustics effect on protected wildlife": 4,
    "Sargassum to agricultural fertiliser": 4,
    "Recovery platform biofouling and marine growth": 3,
    "Launch site by LNG terminal co-located hazard model": 3,
    "Launch water deluge runoff monitoring": 3,
    "Parametric insurance for launch-adjacent property": 2,
    "Recovered booster corrosion forensics": 2,
    "Boil-off gas pipeline from LNG terminal to launch site": 2,
    "Retired flight hardware second-life materials": 1,
}

B_HYBRIDS = {
    "Boom Baseline": (
        [10, 8, 9, 10, 10, 8, 10, 8, 9, 7],
        "The independent overpressure record for launch communities, built as the sensor network first and the cross-facility hazard model second. The network is the only dataset that makes the hazard model possible, so the gated idea becomes reachable by owning the data the gatekeepers do not have.",
        ["Independent launch overpressure record", "Launch site by LNG terminal co-located hazard model", "Launch corridor structural design standard", "School and public building vibration hardening"],
    ),
    "SARGO": (
        [9, 5, 10, 10, 9, 5, 7, 8, 6, 7],
        "Sargassum to rocket-grade biomethane, with the arsenic problem treated as the actual product rather than an inconvenience: solve contaminant separation and you own both the fuel and the remediation market.",
        ["Sargassum to rocket-grade biomethane", "Independent launch methane venting measurement", "Sargassum to agricultural fertiliser"],
    ),
    "Peninsula": (
        [9, 7, 10, 10, 10, 6, 9, 6, 8, 6],
        "One shared risk picture for the launch site, the LNG terminal, the port and the highway that all occupy the same peninsula: cross-facility drills, cryogenic transport routing and joint emergency response.",
        ["Cross-facility emergency response simulator", "Cryogenic road transport risk mapping", "Launch site by LNG terminal co-located hazard model"],
    ),
    "Everything Around The Pad": (
        [9, 6, 8, 10, 9, 4, 8, 4, 7, 5],
        "Deliberate over-combination: overpressure plus venting plus deluge plus debris plus wildlife as one monitoring platform. Entered to test whether breadth beats focus when the whitespace is genuinely wide.",
        ["Independent launch overpressure record", "Independent launch methane venting measurement", "Launch water deluge runoff monitoring", "Beach debris citizen mapping"],
    ),
}
B_HYBRID_R2 = {"Boom Baseline": 10, "SARGO": 8, "Peninsula": 7, "Everything Around The Pad": 4}
B_HYBRID_R3 = {"Boom Baseline": 9, "SARGO": 5, "Peninsula": 4, "Everything Around The Pad": 6}

# --------------------------------------------------------------------------
# Tournament C — YOUTH. Different subject, therefore a different rubric.
# Founder advantage is replaced by what actually decides a high school pitch:
# can this person genuinely do it themselves, and can they show real data in
# the three weeks the ExF Space Entrepreneur Summer Academy runs.
# --------------------------------------------------------------------------
C_WEIGHTS = {
    "student_executable_solo": 0.18,
    "whitespace_uncontested": 0.14,
    "rgv_regional_anchor": 0.12,
    "real_evidence_in_three_weeks": 0.12,
    "mission_fit_space_energy": 0.11,
    "judge_legibility_in_60_seconds": 0.10,
    "personal_credibility": 0.09,
    "safety_and_permission": 0.08,
    "follow_on_path": 0.06,
}
C_ORDER = list(C_WEIGHTS)

C_ENTRANTS = {
    "Student-run launch overpressure map": ([9, 9, 10, 9, 8, 10, 10, 8, 9], "EMPTY_BECAUSE_NEW", "Cheap sensors on classmates' houses producing the first public map of how hard each launch hits each neighbourhood"),
    "Jar-scale sargassum to methane yield study": ([8, 8, 10, 8, 10, 10, 8, 6, 8], "EMPTY_BECAUSE_HARD", "Beach seaweed into rocket fuel gas, measured in a garage with a graduated cylinder"),
    "Sargassum landfall forecasting for beaches": ([7, 7, 10, 7, 4, 9, 9, 9, 6], "EMPTY_BECAUSE_UNGLAMOROUS", "Free satellite data turned into a beach-by-beach arrival forecast for South Padre"),
    "Launch day closure cost survey": ([9, 8, 10, 9, 4, 8, 9, 10, 5], "EMPTY_BECAUSE_UNGLAMOROUS", "Interview every Port Isabel business and publish what closures actually cost them"),
    "School building vibration monitoring": ([8, 9, 10, 7, 5, 9, 10, 7, 7], "EMPTY_BECAUSE_UNGLAMOROUS", "Put a sensor in your own school and find out what the building takes"),
    "Launch acoustics and shorebird response": ([5, 9, 10, 5, 5, 8, 8, 3, 7], "EMPTY_BECAUSE_GATED", "Refuge permits stand between a student and this data"),
    "Spanish-language space careers explainer": ([9, 7, 10, 8, 5, 8, 10, 10, 6], "EMPTY_BECAUSE_UNGLAMOROUS", "Space technical career content in the language half the region speaks at home"),
    "Beach debris mapping after launches": ([8, 7, 9, 7, 5, 8, 8, 6, 5], "EMPTY_BECAUSE_UNGLAMOROUS", "Walk the beach, photograph, geotag, publish"),
    "Air quality sensors near the launch corridor": ([7, 5, 9, 6, 5, 8, 8, 7, 5], "NOT_ACTUALLY_EMPTY", "Community groups and agencies already run these"),
    "Low-cost seismometer network": ([7, 6, 9, 7, 5, 7, 8, 8, 6], "EMPTY_BECAUSE_UNGLAMOROUS", "Ground motion rather than air overpressure; overlaps the overpressure map"),
    "Sargassum arsenic screening": ([3, 8, 10, 3, 6, 6, 7, 4, 6], "EMPTY_BECAUSE_HARD", "The right question, but it needs a lab a high schooler does not have"),
    "Launch photography tourism yield study": ([8, 5, 9, 7, 3, 7, 7, 10, 3], "EMPTY_BECAUSE_BAD", "Interesting, but no buyer and no space content"),
    "Water quality after deluge releases": ([4, 7, 9, 4, 6, 8, 7, 3, 5], "EMPTY_BECAUSE_GATED", "The interesting sampling points are on private property"),
    "High altitude balloon payload": ([6, 1, 3, 6, 8, 9, 4, 6, 5], "NOT_ACTUALLY_EMPTY", "Thousands of school teams do this every year"),
    "Model rocket design and launch": ([7, 1, 3, 7, 8, 9, 4, 5, 4], "NOT_ACTUALLY_EMPTY", "The single most common high school space project in existence"),
    "CubeSat design study": ([4, 1, 2, 3, 9, 7, 3, 8, 5], "NOT_ACTUALLY_EMPTY", "Heavily served by existing programmes"),
    "Space themed tutoring app": ([7, 2, 4, 6, 3, 7, 5, 9, 3], "NOT_ACTUALLY_EMPTY", "Saturated category with no regional specificity"),
    "Sargassum to fertiliser for local farms": ([7, 5, 10, 6, 3, 8, 8, 7, 5], "NOT_ACTUALLY_EMPTY", "Already commercialised elsewhere"),
    "Heat and shade mapping in colonias": ([8, 6, 10, 8, 1, 8, 9, 9, 4], "EMPTY_BECAUSE_UNGLAMOROUS", "Excellent civic project, but it is not a space or energy pitch"),
    "Rocket launch noise phone crowdsourcing app": ([8, 7, 9, 8, 6, 9, 9, 9, 5], "EMPTY_BECAUSE_NEW", "Phone microphones instead of calibrated sensors; cheaper, less defensible"),
}

C_ROUND2 = {  # survives a high school judging panel: is this really yours, is it real, so what
    "Student-run launch overpressure map": 10,
    "Jar-scale sargassum to methane yield study": 9,
    "School building vibration monitoring": 8,
    "Launch day closure cost survey": 7,
    "Rocket launch noise phone crowdsourcing app": 7,
    "Spanish-language space careers explainer": 7,
    "Sargassum landfall forecasting for beaches": 6,
    "Beach debris mapping after launches": 6,
    "Low-cost seismometer network": 6,
    "Launch acoustics and shorebird response": 6,
    "Sargassum arsenic screening": 5,
    "Heat and shade mapping in colonias": 5,
    "Water quality after deluge releases": 4,
    "Air quality sensors near the launch corridor": 4,
    "Sargassum to fertiliser for local farms": 3,
    "Launch photography tourism yield study": 3,
    "High altitude balloon payload": 2,
    "Model rocket design and launch": 2,
    "CubeSat design study": 2,
    "Space themed tutoring app": 1,
}

C_ROUND3 = {  # three weeks, under 500 dollars, no adult doing the work
    "Launch day closure cost survey": 10,
    "Student-run launch overpressure map": 9,
    "Spanish-language space careers explainer": 9,
    "Rocket launch noise phone crowdsourcing app": 9,
    "Heat and shade mapping in colonias": 9,
    "Beach debris mapping after launches": 8,
    "Jar-scale sargassum to methane yield study": 8,
    "School building vibration monitoring": 8,
    "Sargassum landfall forecasting for beaches": 7,
    "Low-cost seismometer network": 7,
    "Model rocket design and launch": 7,
    "Sargassum to fertiliser for local farms": 6,
    "High altitude balloon payload": 6,
    "Space themed tutoring app": 6,
    "Air quality sensors near the launch corridor": 6,
    "Launch photography tourism yield study": 6,
    "Launch acoustics and shorebird response": 4,
    "Water quality after deluge releases": 3,
    "CubeSat design study": 3,
    "Sargassum arsenic screening": 2,
}

C_HYBRIDS = {
    "The Boom Map": (
        [9, 10, 10, 9, 8, 10, 10, 9, 9],
        "A student-built network of calibrated overpressure and vibration sensors on neighbours' homes and the local school, publishing the first independent public record of what each launch does to each street. The pitch is not a grievance; it is the measurement layer every airport has and no spaceport does.",
        ["Student-run launch overpressure map", "School building vibration monitoring", "Rocket launch noise phone crowdsourcing app", "Launch day closure cost survey"],
    ),
    "Beach Fuel": (
        [8, 8, 10, 8, 10, 10, 8, 7, 8],
        "Sargassum to methane at jar scale, with the arsenic question asked honestly rather than hidden: measure the yield, measure the contamination, and report both.",
        ["Jar-scale sargassum to methane yield study", "Sargassum arsenic screening", "Sargassum landfall forecasting for beaches"],
    ),
    "Closure Count": (
        [9, 8, 10, 10, 4, 9, 9, 10, 5],
        "The economic ledger of launch day: what closures cost every business in Port Isabel, collected door to door and published.",
        ["Launch day closure cost survey", "Sargassum landfall forecasting for beaches"],
    ),
    "Everything Near The Beach": (
        [7, 7, 10, 5, 7, 6, 8, 6, 5],
        "Deliberate over-combination: overpressure plus sargassum plus debris plus closures as one youth project. Entered to test whether a student pitch survives breadth.",
        ["Student-run launch overpressure map", "Jar-scale sargassum to methane yield study", "Beach debris mapping after launches", "Launch day closure cost survey"],
    ),
}
C_HYBRID_R2 = {"The Boom Map": 10, "Beach Fuel": 9, "Closure Count": 7, "Everything Near The Beach": 4}
C_HYBRID_R3 = {"The Boom Map": 9, "Beach Fuel": 8, "Closure Count": 10, "Everything Near The Beach": 4}


def weighted(raw, weights, order) -> float:
    return round(sum(raw[i] * weights[k] for i, k in enumerate(order)), 3)


def run(name, weights, order, entrants, round2, round3, hybrids, hybrid_r2, hybrid_r3, subject):
    rows = []
    for entry, (raw, emptiness, diff) in entrants.items():
        disqualified = emptiness in DISQUALIFYING
        rows.append({
            "name": entry,
            "differentiator": diff,
            "emptiness_class": emptiness,
            "emptiness_meaning": EMPTINESS_CLASSES[emptiness],
            "disqualified_on_emptiness": disqualified,
            "scores": dict(zip(order, raw)),
            "round1_weighted": weighted(raw, weights, order),
            "round2_judging_room": round2[entry],
            "round3_actually_startable": round3[entry],
            "catastrophic_weakness": min(zip(raw, order))[1] if min(raw) <= 3 else None,
        })

    live = [r for r in rows if not r["disqualified_on_emptiness"]]
    for key, field in (("round1_weighted", "r1"), ("round2_judging_room", "r2"), ("round3_actually_startable", "r3")):
        ordered = sorted(live, key=lambda r: r[key], reverse=True)
        median = ordered[len(ordered) // 2][key] if ordered else 0
        for row in rows:
            row[f"{field}_loss"] = (not row["disqualified_on_emptiness"]) and row[key] < median
    for row in rows:
        row["losses"] = sum(row[f"{f}_loss"] for f in ("r1", "r2", "r3"))
        row["eliminated"] = row["disqualified_on_emptiness"] or row["losses"] >= 3

    rows.sort(key=lambda r: (r["disqualified_on_emptiness"], -r["round1_weighted"], r["name"]))
    for index, row in enumerate(rows, start=1):
        row["round1_rank"] = index

    hybrid_rows = []
    for hname, (raw, thesis, borrowed) in hybrids.items():
        hybrid_rows.append({
            "name": hname,
            "thesis": thesis,
            "borrowed_components": borrowed,
            "scores": dict(zip(order, raw)),
            "weighted": weighted(raw, weights, order),
            "round2_judging_room": hybrid_r2[hname],
            "round3_actually_startable": hybrid_r3[hname],
        })
    hybrid_rows.sort(key=lambda h: -h["weighted"])

    best_original = max(live, key=lambda r: r["round1_weighted"])
    return {
        "tournament": name,
        "subject": subject,
        "assessment_type": (
            "Structured decision analysis under partial evidence. Scores are comparative judgement "
            "instruments, not measurements. No market survey or technical benchmark was run."
        ),
        "generated": "2026-08-28",
        "method": "prompts/shared/ULTIMATE_SOLUTION_TOURNAMENT.md sections 4, 6, 7, 8, 9, 10, 11, 12, 13",
        "emptiness_classes": EMPTINESS_CLASSES,
        "criteria_weights": weights,
        "entrant_count": len(rows),
        "disqualified_on_emptiness": [r["name"] for r in rows if r["disqualified_on_emptiness"]],
        "survivor_count": len([r for r in rows if not r["eliminated"]]),
        "entrants": rows,
        "hybrids": hybrid_rows,
        "championship": {
            "best_original": best_original["name"],
            "best_original_score": best_original["round1_weighted"],
            "best_hybrid": hybrid_rows[0]["name"],
            "best_hybrid_score": hybrid_rows[0]["weighted"],
            "winner": hybrid_rows[0]["name"],
            "runner_up": hybrid_rows[1]["name"],
            "third": hybrid_rows[2]["name"],
            "verdict": "ADAPT",
        },
    }


def sensitivity(hybrids, weights, order, variants):
    report = {}
    for label, spec in variants.items():
        active = {k: v for k, v in weights.items() if k not in spec.get("drop", [])}
        active.update(spec.get("override", {}))
        total = sum(active.values())
        scores = {
            n: round(sum(raw[order.index(k)] * v for k, v in active.items()) / total, 3)
            for n, (raw, _t, _b) in hybrids.items()
        }
        best = sorted(scores.values(), reverse=True)
        report[label] = {"scores": scores, "winner": max(scores, key=lambda n: scores[n]), "margin": round(best[0] - best[1], 3)}
    return report


def main() -> None:
    here = pathlib.Path(__file__).parent

    b = run("WHITESPACE", B_WEIGHTS, B_ORDER, B_ENTRANTS, B_ROUND2, B_ROUND3, B_HYBRIDS, B_HYBRID_R2, B_HYBRID_R3,
            "Which venture idea that essentially nobody is pursuing best wins an Expanding Frontiers grant or award")
    b["sensitivity"] = sensitivity(B_HYBRIDS, B_WEIGHTS, B_ORDER, {
        "baseline": {},
        "whitespace_halved": {"override": {"whitespace_uncontested": 0.10}},
        "trap_check_removed": {"drop": ["emptiness_is_not_a_trap"]},
        "capital_efficiency_removed": {"drop": ["capital_efficiency_at_32k"]},
        "novelty_maximalist": {"override": {"whitespace_uncontested": 0.35, "emptiness_is_not_a_trap": 0.05}},
    })
    (here / "WHITESPACE_RESULTS.json").write_text(json.dumps(b, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    c = run("YOUTH", C_WEIGHTS, C_ORDER, C_ENTRANTS, C_ROUND2, C_ROUND3, C_HYBRIDS, C_HYBRID_R2, C_HYBRID_R3,
            "Which idea can a high school student personally pitch and execute at the ExF Space Entrepreneur Summer Academy")
    c["sensitivity"] = sensitivity(C_HYBRIDS, C_WEIGHTS, C_ORDER, {
        "baseline": {},
        "executability_doubled": {"override": {"student_executable_solo": 0.30, "whitespace_uncontested": 0.07}},
        "whitespace_removed": {"drop": ["whitespace_uncontested"]},
        "mission_fit_doubled": {"override": {"mission_fit_space_energy": 0.25, "judge_legibility_in_60_seconds": 0.05}},
    })
    (here / "YOUTH_RESULTS.json").write_text(json.dumps(c, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for payload in (b, c):
        print(f"\n=== {payload['tournament']} ===")
        print(f"entrants={payload['entrant_count']} disqualified_on_emptiness={len(payload['disqualified_on_emptiness'])} survivors={payload['survivor_count']}")
        print("top 6 originals:")
        for row in [r for r in payload["entrants"] if not r["disqualified_on_emptiness"]][:6]:
            print(f"  {row['round1_weighted']:.3f}  {row['name']}  [{row['emptiness_class']}] losses={row['losses']}")
        print("hybrids:")
        for hybrid in payload["hybrids"]:
            print(f"  {hybrid['weighted']:.3f}  {hybrid['name']}  (r2={hybrid['round2_judging_room']} r3={hybrid['round3_actually_startable']})")
        print("sensitivity:")
        for label, result in payload["sensitivity"].items():
            print(f"  {label:<28} winner={result['winner']:<24} margin={result['margin']:.3f}")


if __name__ == "__main__":
    main()
