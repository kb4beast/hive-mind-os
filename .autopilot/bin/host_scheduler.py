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
GRANT_KIND = "hive-mind-host-capacity-grant-v1"
DEMAND_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "host_id",
        "repository",
        "repository_transport_digest",
        "execution_namespace",
        "execution_id",
        "plan_fingerprint",
        "host_kernel_generation",
        "capacity_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
        "candidate_reservation_ids",
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
    repository: str | None = None,
    repository_transport_digest: str,
    execution_namespace: str,
    execution_id: str,
    plan_fingerprint: str,
    host_kernel_generation: str,
    capacity_generation: str,
    execution_adapter_identity_record_id: str,
    execution_adapter_identity_path: str | None = None,
    execution_adapter_identity_blob_digest: str | None = None,
    candidate_reservation_ids: Sequence[str] | None = None,
    requested_slots: int,
    weight: int,
    enqueued_epoch: int,
) -> dict[str, Any]:
    adapter_path = execution_adapter_identity_path or (
        "execution-adapter-bindings/"
        + execution_adapter_identity_record_id.removeprefix("sha256:")
        + ".json"
    )
    adapter_blob = (
        execution_adapter_identity_blob_digest
        or execution_adapter_identity_record_id
    )
    candidates = list(candidate_reservation_ids or ())
    if not candidates:
        candidates = [
            digest(
                {
                    "kind": "hive-mind-host-scheduler-test-candidate-v1",
                    "execution_id": execution_id,
                    "slot": index,
                }
            )
            for index in range(requested_slots)
        ]
    material: dict[str, Any] = {
        "schema_version": 1,
        "kind": DEMAND_KIND,
        "host_id": host_id,
        "repository": repository or repository_transport_digest,
        "repository_transport_digest": repository_transport_digest,
        "execution_namespace": execution_namespace,
        "execution_id": execution_id,
        "plan_fingerprint": plan_fingerprint,
        "host_kernel_generation": host_kernel_generation,
        "capacity_generation": capacity_generation,
        "execution_adapter_identity_record_id": execution_adapter_identity_record_id,
        "execution_adapter_identity_path": adapter_path,
        "execution_adapter_identity_blob_digest": adapter_blob,
        "candidate_reservation_ids": candidates,
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
        "host_kernel_generation",
        "capacity_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_blob_digest",
    ):
        if not isinstance(value.get(field), str) or AUTHORITY_ID.fullmatch(
            str(value[field])
        ) is None:
            raise HostSchedulerError(f"host scheduling demand {field} is invalid")
    for field in ("host_id", "repository", "execution_namespace"):
        text = value.get(field)
        if not isinstance(text, str) or not text.strip() or any(
            character in text for character in "\r\n\0"
        ):
            raise HostSchedulerError(f"host scheduling demand {field} is invalid")
    requested = value.get("requested_slots")
    weight = value.get("weight")
    epoch = value.get("enqueued_epoch")
    if demand_id != digest(material):
        raise HostSchedulerError("host scheduling demand digest is invalid")
    if type(requested) is not int or requested < 1:
        raise HostSchedulerError("host scheduling requested slots are invalid")
    adapter_path = value.get("execution_adapter_identity_path")
    expected_path = (
        "execution-adapter-bindings/"
        + str(value["execution_adapter_identity_record_id"]).removeprefix("sha256:")
        + ".json"
    )
    candidates = value.get("candidate_reservation_ids")
    if (
        adapter_path != expected_path
        or not isinstance(candidates, list)
        or len(candidates) != requested
        or len(candidates) != len(set(candidates))
        or any(
            not isinstance(candidate, str)
            or AUTHORITY_ID.fullmatch(candidate) is None
            for candidate in candidates
        )
    ):
        raise HostSchedulerError("host scheduling candidate authority is invalid")
    if type(weight) is not int or not 1 <= weight <= 16:
        raise HostSchedulerError("host scheduling weight is invalid")
    if type(epoch) is not int or epoch < 1:
        raise HostSchedulerError("host scheduling enqueue epoch is invalid")
    return dict(value)


def weighted_round_robin(
    demands: Sequence[Mapping[str, Any]],
    *,
    available_slots: int,
    cursor_execution_id: str | None,
    remaining_slots_by_demand_id: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Allocate every available slot with deterministic weighted round-robin.

    The cursor is the last execution served by the preceding schedule.  Starting
    strictly after it guarantees a continuously queued small execution receives a
    slot when capacity next returns, even when another execution has a wide DAG.
    """

    if type(available_slots) is not int or available_slots < 0:
        raise HostSchedulerError("available host capacity is invalid")
    validated = [validate_demand(item) for item in demands]
    demand_ids = [str(item["demand_id"]) for item in validated]
    if len(demand_ids) != len(set(demand_ids)):
        raise HostSchedulerError("host scheduling demand is duplicated")
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

    by_demand = {str(item["demand_id"]): item for item in ordered}
    sequence = [str(item["demand_id"]) for item in ordered]
    cursor_positions = [
        index
        for index, demand_id in enumerate(sequence)
        if by_demand[demand_id]["execution_id"] == cursor_execution_id
    ]
    if cursor_positions:
        start = (cursor_positions[-1] + 1) % len(sequence)
    else:
        start = 0
    overrides = dict(remaining_slots_by_demand_id or {})
    if set(overrides) - {
        str(item["demand_id"]) for item in validated
    }:
        raise HostSchedulerError("host scheduling remaining demand is unknown")
    remaining: dict[str, int] = {}
    for demand_id in sequence:
        demand = by_demand[demand_id]
        value = overrides.get(
            str(demand["demand_id"]), int(demand["requested_slots"])
        )
        if type(value) is not int or not 0 <= value <= int(demand["requested_slots"]):
            raise HostSchedulerError("host scheduling remaining slots are invalid")
        remaining[demand_id] = value
    initially_remaining = sum(remaining.values())
    grants = {demand_id: 0 for demand_id in sequence}
    cursor = cursor_execution_id if cursor_positions else None
    slots = available_slots
    index = start
    idle_visits = 0
    while slots > 0 and any(value > 0 for value in remaining.values()):
        demand_id = sequence[index]
        demand = by_demand[demand_id]
        grant = min(int(demand["weight"]), remaining[demand_id], slots)
        if grant:
            grants[demand_id] += grant
            remaining[demand_id] -= grant
            slots -= grant
            cursor = str(demand["execution_id"])
            idle_visits = 0
        else:
            idle_visits += 1
        index = (index + 1) % len(sequence)
        if idle_visits >= len(sequence):
            break
    grant_rows = [
        {
            "execution_id": by_demand[demand_id]["execution_id"],
            "demand_id": demand_id,
            "slots": grants[demand_id],
        }
        for demand_id in sequence
        if grants[demand_id]
    ]
    ungranted = [
        {
            "execution_id": by_demand[demand_id]["execution_id"],
            "demand_id": demand_id,
            "remaining_slots": remaining[demand_id],
        }
        for demand_id in sequence
        if remaining[demand_id]
    ]
    if sum(item["slots"] for item in grant_rows) != min(
        available_slots,
        initially_remaining,
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


def make_grant_tokens(
    schedule: Mapping[str, Any],
    demands: Sequence[Mapping[str, Any]],
    *,
    remaining_candidates_by_demand_id: Mapping[str, Sequence[str]],
    issued_at: str,
    expires_at: str,
) -> list[dict[str, Any]]:
    """Expand one deterministic allocation into exact per-slot capabilities."""

    if (
        schedule.get("kind") != SCHEDULE_KIND
        or not isinstance(schedule.get("schedule_id"), str)
        or AUTHORITY_ID.fullmatch(str(schedule["schedule_id"])) is None
        or not isinstance(issued_at, str)
        or not issued_at.strip()
        or not isinstance(expires_at, str)
        or not expires_at.strip()
    ):
        raise HostSchedulerError("host scheduling grant envelope is invalid")
    validated = {str(item["demand_id"]): validate_demand(item) for item in demands}
    tokens: list[dict[str, Any]] = []
    grant_rows = schedule.get("grants")
    if not isinstance(grant_rows, list):
        raise HostSchedulerError("host scheduling grants are malformed")
    for row in grant_rows:
        if not isinstance(row, Mapping):
            raise HostSchedulerError("host scheduling grant row is malformed")
        demand_id = str(row.get("demand_id"))
        demand = validated.get(demand_id)
        candidates = list(remaining_candidates_by_demand_id.get(demand_id, ()))
        slots = row.get("slots")
        if (
            demand is None
            or row.get("execution_id") != demand.get("execution_id")
            or type(slots) is not int
            or slots < 1
            or len(candidates) < slots
        ):
            raise HostSchedulerError("host scheduling grant row conflicts with demand")
        for slot_index, local_reservation_id in enumerate(candidates[:slots], 1):
            material: dict[str, Any] = {
                "schema_version": 1,
                "kind": GRANT_KIND,
                "host_id": demand["host_id"],
                "host_kernel_generation": demand["host_kernel_generation"],
                "capacity_generation": demand["capacity_generation"],
                "execution_id": demand["execution_id"],
                "demand_id": demand_id,
                "schedule_id": schedule["schedule_id"],
                "local_reservation_id": local_reservation_id,
                "slot_index": slot_index,
                "issued_at": issued_at,
                "expires_at": expires_at,
            }
            tokens.append({**material, "grant_id": digest(material)})
    return tokens


def validate_schedule(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema_version",
        "kind",
        "available_slots",
        "cursor_execution_id",
        "grants",
        "ungranted",
        "demand_ids",
        "schedule_id",
    }
    if set(value) != fields:
        raise HostSchedulerError("host scheduling schedule schema is ambiguous")
    material = dict(value)
    schedule_id = material.pop("schedule_id", None)
    if (
        value.get("schema_version") != 1
        or value.get("kind") != SCHEDULE_KIND
        or type(value.get("available_slots")) is not int
        or int(value["available_slots"]) < 0
        or (
            value.get("cursor_execution_id") is not None
            and AUTHORITY_ID.fullmatch(str(value.get("cursor_execution_id"))) is None
        )
        or not isinstance(value.get("grants"), list)
        or not isinstance(value.get("ungranted"), list)
        or not isinstance(value.get("demand_ids"), list)
        or any(
            AUTHORITY_ID.fullmatch(str(item)) is None
            for item in value.get("demand_ids", [])
        )
        or schedule_id != digest(material)
    ):
        raise HostSchedulerError("host scheduling schedule is invalid")
    granted = 0
    seen: set[str] = set()
    for row in value["grants"]:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"execution_id", "demand_id", "slots"}
            or AUTHORITY_ID.fullmatch(str(row.get("execution_id"))) is None
            or AUTHORITY_ID.fullmatch(str(row.get("demand_id"))) is None
            or type(row.get("slots")) is not int
            or int(row["slots"]) < 1
            or str(row["demand_id"]) in seen
        ):
            raise HostSchedulerError("host scheduling grant allocation is invalid")
        seen.add(str(row["demand_id"]))
        granted += int(row["slots"])
    for row in value["ungranted"]:
        if (
            not isinstance(row, Mapping)
            or set(row) != {"execution_id", "demand_id", "remaining_slots"}
            or AUTHORITY_ID.fullmatch(str(row.get("execution_id"))) is None
            or AUTHORITY_ID.fullmatch(str(row.get("demand_id"))) is None
            or type(row.get("remaining_slots")) is not int
            or int(row["remaining_slots"]) < 1
        ):
            raise HostSchedulerError("host scheduling remainder is invalid")
    if granted > int(value["available_slots"]):
        raise HostSchedulerError("host scheduling grants exceed available capacity")
    return dict(value)


def validate_grant(value: Mapping[str, Any]) -> dict[str, Any]:
    fields = {
        "schema_version",
        "kind",
        "host_id",
        "host_kernel_generation",
        "capacity_generation",
        "execution_id",
        "demand_id",
        "schedule_id",
        "local_reservation_id",
        "slot_index",
        "issued_at",
        "expires_at",
        "grant_id",
    }
    if set(value) != fields:
        raise HostSchedulerError("host scheduling grant schema is ambiguous")
    material = dict(value)
    grant_id = material.pop("grant_id", None)
    if value.get("schema_version") != 1 or value.get("kind") != GRANT_KIND:
        raise HostSchedulerError("host scheduling grant kind is invalid")
    for field in (
        "host_kernel_generation",
        "capacity_generation",
        "execution_id",
        "demand_id",
        "schedule_id",
        "local_reservation_id",
    ):
        if AUTHORITY_ID.fullmatch(str(value.get(field))) is None:
            raise HostSchedulerError(f"host scheduling grant {field} is invalid")
    if (
        not isinstance(value.get("host_id"), str)
        or not str(value["host_id"]).strip()
        or type(value.get("slot_index")) is not int
        or int(value["slot_index"]) < 1
        or not isinstance(value.get("issued_at"), str)
        or not str(value["issued_at"]).strip()
        or not isinstance(value.get("expires_at"), str)
        or not str(value["expires_at"]).strip()
        or grant_id != digest(material)
    ):
        raise HostSchedulerError("host scheduling grant is invalid")
    return dict(value)
