#!/usr/bin/env python3
"""Pure deterministic host-capacity scheduling policy.

Persistence and locking belong to the canonical host controller.  This module is
the sealed, side-effect-free reducer used by admission, replay, and tests so the
three paths cannot disagree about fairness.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

AUTHORITY_ID = re.compile(r"sha256:[0-9a-f]{64}")
DEMAND_KIND = "hive-mind-host-dispatch-demand-v1"
SCHEDULE_KIND = "hive-mind-host-capacity-schedule-v1"
DEMAND_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "host_id",
        "repository_transport_digest",
        "execution_namespace",
        "execution_id",
        "plan_fingerprint",
        "capacity_generation",
        "requested_slots",
        "weight",
        "enqueued_epoch",
        "demand_id",
    }
)


class HostSchedulerError(ValueError):
    """Raised when the host scheduling projection is not canonical."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def make_demand(
    *,
    host_id: str,
    repository_transport_digest: str,
    execution_namespace: str,
    execution_id: str,
    plan_fingerprint: str,
    capacity_generation: str,
    requested_slots: int,
    weight: int,
    enqueued_epoch: int,
) -> dict[str, Any]:
    material: dict[str, Any] = {
        "schema_version": 1,
        "kind": DEMAND_KIND,
        "host_id": host_id,
        "repository_transport_digest": repository_transport_digest,
        "execution_namespace": execution_namespace,
        "execution_id": execution_id,
        "plan_fingerprint": plan_fingerprint,
        "capacity_generation": capacity_generation,
        "requested_slots": requested_slots,
        "weight": weight,
        "enqueued_epoch": enqueued_epoch,
    }
    demand = {**material, "demand_id": digest(material)}
    return validate_demand(demand)


def validate_demand(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != DEMAND_FIELDS:
        raise HostSchedulerError("host scheduling demand schema is ambiguous")
    material = dict(value)
    demand_id = material.pop("demand_id", None)
    if value.get("schema_version") != 1 or value.get("kind") != DEMAND_KIND:
        raise HostSchedulerError("host scheduling demand kind is invalid")
    for field in (
        "repository_transport_digest",
        "execution_id",
        "plan_fingerprint",
        "capacity_generation",
    ):
        if not isinstance(value.get(field), str) or AUTHORITY_ID.fullmatch(
            str(value[field])
        ) is None:
            raise HostSchedulerError(f"host scheduling demand {field} is invalid")
    for field in ("host_id", "execution_namespace"):
        text = value.get(field)
        if not isinstance(text, str) or not text.strip() or any(
            character in text for character in "\r\n\0"
        ):
            raise HostSchedulerError(f"host scheduling demand {field} is invalid")
    requested = value.get("requested_slots")
    weight = value.get("weight")
    epoch = value.get("enqueued_epoch")
    if type(requested) is not int or requested < 1:
        raise HostSchedulerError("host scheduling requested slots are invalid")
    if type(weight) is not int or not 1 <= weight <= 16:
        raise HostSchedulerError("host scheduling weight is invalid")
    if type(epoch) is not int or epoch < 1:
        raise HostSchedulerError("host scheduling enqueue epoch is invalid")
    if demand_id != digest(material):
        raise HostSchedulerError("host scheduling demand digest is invalid")
    return dict(value)


def weighted_round_robin(
    demands: Sequence[Mapping[str, Any]],
    *,
    available_slots: int,
    cursor_execution_id: str | None,
) -> dict[str, Any]:
    """Allocate every available slot with deterministic weighted round-robin.

    The cursor is the last execution served by the preceding schedule.  Starting
    strictly after it guarantees a continuously queued small execution receives a
    slot when capacity next returns, even when another execution has a wide DAG.
    """

    if type(available_slots) is not int or available_slots < 0:
        raise HostSchedulerError("available host capacity is invalid")
    validated = [validate_demand(item) for item in demands]
    execution_ids = [str(item["execution_id"]) for item in validated]
    if len(execution_ids) != len(set(execution_ids)):
        raise HostSchedulerError("host scheduling demand execution is duplicated")
    ordered = sorted(
        validated,
        key=lambda item: (
            int(item["enqueued_epoch"]),
            str(item["repository_transport_digest"]),
            str(item["execution_id"]),
        ),
    )
    if not ordered:
        if available_slots:
            raise HostSchedulerError("available capacity has no authenticated demand")
        material: dict[str, Any] = {
            "schema_version": 1,
            "kind": SCHEDULE_KIND,
            "available_slots": 0,
            "cursor_execution_id": None,
            "grants": [],
            "ungranted": [],
            "demand_ids": [],
        }
        return {**material, "schedule_id": digest(material)}

    by_execution = {str(item["execution_id"]): item for item in ordered}
    sequence = [str(item["execution_id"]) for item in ordered]
    if cursor_execution_id is not None and cursor_execution_id in sequence:
        start = (sequence.index(cursor_execution_id) + 1) % len(sequence)
    else:
        start = 0
    remaining = {
        execution_id: int(by_execution[execution_id]["requested_slots"])
        for execution_id in sequence
    }
    grants = {execution_id: 0 for execution_id in sequence}
    cursor = cursor_execution_id if cursor_execution_id in sequence else None
    slots = available_slots
    index = start
    idle_visits = 0
    while slots > 0 and any(value > 0 for value in remaining.values()):
        execution_id = sequence[index]
        demand = by_execution[execution_id]
        grant = min(int(demand["weight"]), remaining[execution_id], slots)
        if grant:
            grants[execution_id] += grant
            remaining[execution_id] -= grant
            slots -= grant
            cursor = execution_id
            idle_visits = 0
        else:
            idle_visits += 1
        index = (index + 1) % len(sequence)
        if idle_visits >= len(sequence):
            break
    grant_rows = [
        {
            "execution_id": execution_id,
            "demand_id": by_execution[execution_id]["demand_id"],
            "slots": grants[execution_id],
        }
        for execution_id in sequence
        if grants[execution_id]
    ]
    ungranted = [
        {
            "execution_id": execution_id,
            "demand_id": by_execution[execution_id]["demand_id"],
            "remaining_slots": remaining[execution_id],
        }
        for execution_id in sequence
        if remaining[execution_id]
    ]
    if sum(item["slots"] for item in grant_rows) != min(
        available_slots,
        sum(int(item["requested_slots"]) for item in ordered),
    ):
        raise HostSchedulerError("host scheduler was not work conserving")
    material = {
        "schema_version": 1,
        "kind": SCHEDULE_KIND,
        "available_slots": available_slots,
        "cursor_execution_id": cursor,
        "grants": grant_rows,
        "ungranted": ungranted,
        "demand_ids": [str(item["demand_id"]) for item in ordered],
    }
    return {**material, "schedule_id": digest(material)}

