"""Pure reducers for the kernel's durable event spine."""

from __future__ import annotations

from typing import Any, Mapping

from .canonical import canonical_digest
from .contracts import MissionState, WorkState

_MISSION_NEXT = {
    MissionState.CREATED: {
        MissionState.PLANNING,
        MissionState.WAITING_HUMAN,
        MissionState.PAUSED,
        MissionState.CANCELLED,
        MissionState.FAILED,
    },
    MissionState.PLANNING: {
        MissionState.READY,
        MissionState.FAILED,
        MissionState.WAITING_HUMAN,
    },
    MissionState.READY: {MissionState.RUNNING, MissionState.CANCELLED},
    MissionState.RUNNING: {
        MissionState.VERIFYING,
        MissionState.PAUSED,
        MissionState.FAILED,
    },
    MissionState.VERIFYING: {MissionState.INTEGRATING, MissionState.FAILED},
    MissionState.INTEGRATING: {
        MissionState.COMPLETED,
        MissionState.ROLLING_BACK,
        MissionState.FAILED,
    },
}
_WORK_NEXT = {
    WorkState.PROPOSED: {
        WorkState.READY,
        WorkState.BLOCKED_DEPENDENCY,
        WorkState.CANCELLED,
        WorkState.SUPERSEDED,
    },
    WorkState.READY: {WorkState.LEASED, WorkState.CANCELLED},
    WorkState.LEASED: {WorkState.RUNNING, WorkState.RETRYABLE_FAILED, WorkState.CANCELLED},
    WorkState.RUNNING: {
        WorkState.AWAITING_VERIFICATION,
        WorkState.RETRYABLE_FAILED,
        WorkState.TERMINAL_FAILED,
        WorkState.CANCELLED,
    },
    WorkState.AWAITING_VERIFICATION: {
        WorkState.ACCEPTED,
        WorkState.RETRYABLE_FAILED,
        WorkState.TERMINAL_FAILED,
    },
    WorkState.ACCEPTED: {WorkState.INTEGRATED},
}


def empty_state() -> dict[str, Any]:
    """Return a fresh, canonical empty state."""

    return {"missions": {}, "work": {}}


def reduce_event(state: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    """Apply one legal event and return a new deterministic projection state."""

    result = {
        "missions": dict(state.get("missions", {})),
        "work": dict(state.get("work", {})),
    }
    payload = event["payload"]
    event_type = event["event_type"]
    mission_id = event["mission_id"]
    if event_type == "mission.created":
        if mission_id in result["missions"]:
            raise ValueError("mission already exists")
        result["missions"][mission_id] = MissionState.CREATED.value
    elif event_type == "mission.transition":
        if mission_id not in result["missions"]:
            raise ValueError("mission transition belongs to an unknown mission")
        old = MissionState(result["missions"][mission_id])
        new = MissionState(payload["status"])
        if new not in _MISSION_NEXT.get(old, set()):
            raise ValueError(f"illegal mission transition: {old} -> {new}")
        result["missions"][mission_id] = new.value
    elif event_type == "work.created":
        work_id = event["work_id"]
        if not work_id or work_id in result["work"]:
            raise ValueError("work id is missing or already exists")
        if mission_id not in result["missions"]:
            raise ValueError("work belongs to unknown mission")
        result["work"][work_id] = {
            "mission_id": mission_id,
            "status": WorkState.PROPOSED.value,
        }
    elif event_type == "work.transition":
        work_id = event["work_id"]
        if not work_id or work_id not in result["work"]:
            raise ValueError("work transition belongs to an unknown work item")
        work = dict(result["work"][work_id])
        if work["mission_id"] != mission_id:
            raise ValueError("work transition mission does not match work item")
        old = WorkState(work["status"])
        new = WorkState(payload["status"])
        if new not in _WORK_NEXT.get(old, set()):
            raise ValueError(f"illegal work transition: {old} -> {new}")
        work["status"] = new.value
        result["work"][work_id] = work
    else:
        raise ValueError(f"unknown kernel event type: {event_type}")
    return result


def state_digest(state: Mapping[str, Any]) -> str:
    """Return the canonical state digest used by snapshots and projections."""

    return canonical_digest(state)
