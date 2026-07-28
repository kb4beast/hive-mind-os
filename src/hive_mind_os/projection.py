"""Read-only operational projection.

The default schema-v1 JSON model contains ``schema_version``, ``generated_at``,
``missions``, ``jobs``, and ``state_counts``. Mission rows contain identity,
objective, state, lifecycle evidence, blockers, quarantine, last checkpoint, and
receipt count. Job rows contain queue state, attempt and lease facts, and the
referenced mission.

Schema v2 is an explicit, additive War Room view. It preserves the v1 fields and
adds evidence-indexed operational rooms. Both versions are projections only:
they cannot issue commands or grant authority. Values come only from the
scheduler, mission store, and append-only ledger; missing evidence renders
``unknown`` or ``not-recorded``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import validate_contract
from .ledger import EvidenceLedger
from .mission_store import MissionStore
from .models import utc_now
from .scheduler import Scheduler

DEFAULT_PROJECTION_SCHEMA_VERSION = 1
WAR_ROOM_PROJECTION_SCHEMA_VERSION = 2
_WAR_ROOM_LEDGER_EVENT_TYPE = "war_room.event"
_OODA_EVENT_PHASE = {
    "observation": 0,
    "hypothesis": 1,
    "dissent": 1,
    "decision": 2,
    "policy": 2,
    "action": 3,
    "receipt": 3,
}
_OODA_PHASE_NAME = ("observe", "orient", "decide", "act")


def build_projection(
    state_dir: str | Path,
    *,
    schema_version: int = DEFAULT_PROJECTION_SCHEMA_VERSION,
) -> dict[str, Any]:
    if schema_version == WAR_ROOM_PROJECTION_SCHEMA_VERSION:
        return build_war_room_projection(state_dir)
    if schema_version != DEFAULT_PROJECTION_SCHEMA_VERSION:
        raise ValueError(f"unsupported projection schema version: {schema_version}")
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
                or (
                    isinstance(event.get("payload"), Mapping)
                    and event["payload"].get("verdict") == "quarantine"
                )
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
            "schema_version": DEFAULT_PROJECTION_SCHEMA_VERSION,
            "generated_at": utc_now(),
            "missions": mission_rows,
            "jobs": job_rows,
            "state_counts": states,
        }
    finally:
        ledger.close()
        store.close()
        scheduler.close()


def _validated_war_room_events(
    events: list[dict[str, Any]],
    mission_id: str,
) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    rejected = 0
    for event in events:
        if event.get("event_type") != _WAR_ROOM_LEDGER_EVENT_TYPE:
            continue
        payload = event.get("payload")
        validation = validate_contract("war-room-event", payload)
        if not validation.valid or not isinstance(payload, Mapping):
            rejected += 1
            continue
        if payload.get("mission_id") != mission_id:
            rejected += 1
            continue
        actor_id = payload.get("actor_id")
        if not isinstance(actor_id, str) or actor_id != event.get("actor"):
            rejected += 1
            continue
        candidates.append(
            {
                "ledger_sequence": event["sequence"],
                "record": dict(payload),
            }
        )

    event_id_counts: dict[str, int] = {}
    for candidate in candidates:
        event_id = candidate["record"]["event_id"]
        event_id_counts[event_id] = event_id_counts.get(event_id, 0) + 1
    duplicated_ids = {
        event_id for event_id, count in event_id_counts.items() if count > 1
    }
    rejected += sum(event_id_counts[event_id] for event_id in duplicated_ids)
    accepted = [
        candidate
        for candidate in candidates
        if candidate["record"]["event_id"] not in duplicated_ids
    ]
    ordered: list[dict[str, Any]] = []
    cycle_phases: dict[str, int] = {}
    for candidate in accepted:
        record = candidate["record"]
        cycle_ref = record["ooda_cycle_ref"]
        phase = _OODA_EVENT_PHASE.get(record["event_type"])
        if cycle_ref is None or phase is None:
            ordered.append(candidate)
            continue
        prior = cycle_phases.get(cycle_ref)
        if (prior is None and phase != 0) or (
            prior is not None and phase not in {prior, prior + 1}
        ):
            rejected += 1
            continue
        cycle_phases[cycle_ref] = phase
        ordered.append(candidate)
    return ordered, rejected


def _ooda_phase(events: list[dict[str, Any]]) -> str:
    phase = "not-recorded"
    for event in events:
        record = event["record"]
        if record["ooda_cycle_ref"] is None:
            continue
        phase_index = _OODA_EVENT_PHASE.get(record["event_type"])
        if phase_index is not None:
            phase = _OODA_PHASE_NAME[phase_index]
    return phase


def _war_room_status(
    mission_state: str,
    events: list[dict[str, Any]],
) -> str:
    if mission_state == "unknown":
        return "unknown"
    if not events:
        return "inactive"
    if mission_state in {"succeeded", "failed", "dead-letter"}:
        return "closed"
    return "open"


def build_war_room_projection(state_dir: str | Path) -> dict[str, Any]:
    """Build the opt-in schema-v2, read-only operational projection."""

    root = Path(state_dir).resolve()
    base = build_projection(
        root,
        schema_version=DEFAULT_PROJECTION_SCHEMA_VERSION,
    )
    store = MissionStore(root)
    ledger = EvidenceLedger(root / "evidence-ledger.sqlite3")
    try:
        stored = {
            item["mission_id"]: store.mission(item["mission_id"])
            for item in store.list_missions()
        }
        rooms: list[dict[str, Any]] = []
        for mission in base["missions"]:
            mission_id = mission["mission_id"]
            events = ledger.events(mission_id)
            war_room_events, rejected_events = _validated_war_room_events(
                events,
                mission_id,
            )
            records = [event["record"] for event in war_room_events]
            record = stored.get(mission_id)
            rooms.append(
                {
                    "mission_id": mission_id,
                    "status": _war_room_status(
                        mission["state"],
                        war_room_events,
                    ),
                    "ooda_phase": _ooda_phase(war_room_events),
                    "observed_actors": sorted(
                        {
                            str(event["actor_id"])
                            for event in records
                            if event["actor_id"] is not None
                        }
                    ),
                    "budget": record.get("budget") if record is not None else None,
                    "checkpoint_count": (
                        len(store.checkpoints(mission_id))
                        if record is not None
                        else 0
                    ),
                    "evidence_refs": sorted(
                        {
                            evidence_ref
                            for event in records
                            for evidence_ref in event["evidence_refs"]
                        }
                    ),
                    "ooda_cycle_refs": sorted(
                        {
                            event["ooda_cycle_ref"]
                            for event in records
                            if event["ooda_cycle_ref"] is not None
                        }
                    ),
                    "command_intent_refs": sorted(
                        {
                            event["command_intent_ref"]
                            for event in records
                            if event["command_intent_ref"] is not None
                        }
                    ),
                    "hypotheses": [
                        event["summary"]
                        for event in records
                        if event["event_type"] == "hypothesis"
                    ],
                    "decision_event_sequences": [
                        event["ledger_sequence"]
                        for event in war_room_events
                        if event["record"]["event_type"] in {"decision", "policy"}
                    ],
                    "receipt_event_sequences": [
                        event["ledger_sequence"]
                        for event in war_room_events
                        if event["record"]["event_type"] == "receipt"
                    ],
                    "quarantine_event_sequences": [
                        event["ledger_sequence"]
                        for event in war_room_events
                        if event["record"]["event_type"] == "quarantine"
                    ],
                    "rejected_war_room_event_count": rejected_events,
                    "recent_events": war_room_events[-20:],
                }
            )
        return {
            **base,
            "schema_version": WAR_ROOM_PROJECTION_SCHEMA_VERSION,
            "projection_kind": "war-room",
            "read_only": True,
            "authority": "none",
            "commands_supported": False,
            "war_room": {
                "sources": (
                    "scheduler",
                    "mission-store",
                    "evidence-ledger",
                ),
                "mission_rooms": rooms,
            },
        }
    finally:
        ledger.close()
        store.close()


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
