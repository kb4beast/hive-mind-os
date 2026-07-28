"""Read-only operational projection.

The JSON model contains ``schema_version``, ``generated_at``, ``missions``, ``jobs``,
and ``state_counts``. Mission rows contain identity, objective, state, lifecycle evidence,
blockers, quarantine, last checkpoint, and receipt count. Job rows contain queue state,
attempt and lease facts, and the referenced mission. Values come only from the scheduler,
mission store, and append-only ledger; a missing ledger correlation renders ``unknown``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .ledger import EvidenceLedger
from .mission_store import MissionStore
from .models import utc_now
from .scheduler import Scheduler


def build_projection(state_dir: str | Path) -> dict[str, Any]:
    root = Path(state_dir).resolve()
    scheduler = Scheduler(root)
    store = MissionStore(root)
    ledger = EvidenceLedger(root / "evidence-ledger.sqlite3")
    try:
        jobs = scheduler.jobs()
        stored = {item["mission_id"]: store.mission(item["mission_id"]) for item in store.list_missions()}
        job_by_mission = {
            job.mission_id or str(job.payload.get("mission_id")): job
            for job in jobs
            if job.mission_id or job.payload.get("mission_id")
        }
        mission_ids = sorted(set(stored) | set(job_by_mission))
        mission_rows: list[dict[str, Any]] = []
        for mission_id in mission_ids:
            mission = stored.get(mission_id)
            job = job_by_mission.get(mission_id)
            events = ledger.events(mission_id)
            event_types = [event["event_type"] for event in events]
            quarantined = any(
                "quarantin" in event["event_type"]
                or event["payload"].get("verdict") == "quarantine"
                for event in events
            )
            if job is not None and job.state == "dead-letter":
                state = "dead-letter"
            elif mission is None:
                state = "unknown"
            elif mission["status"] == "blocked":
                state = "blocked"
            elif mission["status"] == "failed":
                state = "failed"
            elif mission["status"] == "succeeded":
                state = (
                    "succeeded"
                    if "mission.completed" in event_types
                    else "unknown"
                )
            else:
                state = "running" if "mission.started" in event_types else "unknown"
            checkpoints = store.checkpoints(mission_id) if mission is not None else []
            last_checkpoint = (
                {
                    "step_index": checkpoints[-1].step_index,
                    "state": checkpoints[-1].state,
                    "intent_digest": checkpoints[-1].intent_digest,
                }
                if checkpoints
                else None
            )
            mission_rows.append(
                {
                    "mission_id": mission_id,
                    "objective": (
                        mission["config"]["objective"]
                        if mission is not None
                        else (job.payload.get("objective") if job else None)
                    ),
                    "state": state,
                    "lifecycle_stages": sorted(
                        {
                            event["actor"]
                            for event in events
                            if event["event_type"] == "role.completed"
                        }
                    ),
                    "blocked_reasons": (
                        [mission["blocker"]]
                        if mission is not None and mission["blocker"]
                        else (
                            [job.last_error]
                            if job is not None and job.state == "dead-letter"
                            and job.last_error
                            else []
                        )
                    ),
                    "quarantined": quarantined,
                    "last_checkpoint": last_checkpoint,
                    "receipt_count": sum(
                        event_type == "receipt.recorded"
                        for event_type in event_types
                    ),
                    "ledger_event_count": len(events),
                }
            )
        job_rows = [
            {
                "job_id": job.id,
                "kind": job.kind,
                "state": job.state,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "not_before": job.not_before,
                "lease_owner": job.lease_owner,
                "lease_expiry": job.lease_expiry,
                "mission_id": job.mission_id or job.payload.get("mission_id"),
                "last_error": job.last_error,
            }
            for job in jobs
        ]
        states = {
            state: sum(row["state"] == state for row in mission_rows)
            for state in (
                "running",
                "succeeded",
                "failed",
                "blocked",
                "dead-letter",
                "unknown",
            )
        }
        return {
            "schema_version": 1,
            "generated_at": utc_now(),
            "missions": mission_rows,
            "jobs": job_rows,
            "state_counts": states,
        }
    finally:
        ledger.close()
        store.close()
        scheduler.close()


def projection_json(model: dict[str, Any]) -> str:
    return json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def projection_html(model: dict[str, Any]) -> str:
    def cell(value: object) -> str:
        return html.escape("" if value is None else str(value))

    rows = []
    for mission in model["missions"]:
        flags = ["quarantined"] if mission["quarantined"] else []
        blockers = "; ".join(mission["blocked_reasons"])
        rows.append(
            "<tr>"
            f"<td>{cell(mission['mission_id'])}</td>"
            f"<td>{cell(mission['objective'])}</td>"
            f"<td><strong class=\"state-{cell(mission['state'])}\">"
            f"{cell(mission['state'])}</strong></td>"
            f"<td>{cell(', '.join(flags))}</td>"
            f"<td>{cell(blockers)}</td>"
            f"<td>{cell(mission['receipt_count'])}</td>"
            "</tr>"
        )
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        "<title>Hive Mind OS mission control</title>"
        "<style>body{font-family:system-ui;margin:2rem;color:#18202a}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;"
        "padding:.5rem;text-align:left}.state-succeeded{color:#176b35}"
        ".state-running{color:#1d4ed8}.state-failed,.state-dead-letter{color:#a00}"
        ".state-blocked,.state-unknown{color:#8a4b00}"
        ".legend{padding:.75rem;background:#f3f4f6;margin-bottom:1rem}</style>"
        "</head><body><h1>Mission control</h1>"
        '<div class="legend">States: running · succeeded · failed · blocked · '
        "dead-letter · unknown · quarantined. Missing evidence is unknown, never "
        "complete.</div>"
        "<table><thead><tr><th>Mission</th><th>Objective</th><th>State</th>"
        "<th>Flags</th><th>Blockers</th><th>Receipts</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>\n"
    )


def write_projection_html(model: dict[str, Any], path: str | Path) -> Path:
    output = Path(path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(projection_html(model), encoding="utf-8", newline="\n")
    return output
