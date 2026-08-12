"""Versioned, outer-layer compatibility records for legacy repository routes.

This module deliberately sits outside :mod:`brain_kernel`: the kernel remains
repository-neutral and never imports the legacy scheduler or mission runtime.
"""

from __future__ import annotations

from pathlib import Path

from .brain_kernel.canonical import canonical_digest
from .brain_kernel.events import KernelEvent
from .brain_kernel.store import KernelStore
from .scheduler import Job

LEGACY_ENQUEUE_ROUTE = "legacy-enqueue-v1"


def default_kernel_state_dir(legacy_state_dir: str | Path) -> Path:
    """Derive the separate kernel root associated with one legacy state root."""

    return Path(legacy_state_dir).resolve().parent / ".hive-mind-kernel-state"


def record_legacy_enqueue(
    job: Job,
    *,
    kernel_state_dir: str | Path | None = None,
    legacy_state_dir: str | Path,
) -> str:
    """Append the kernel-side binding for an already-created legacy scheduler job.

    The scheduler remains authoritative for execution.  The record is idempotent so a
    process interruption after legacy enqueue can be recovered by repeating the same
    command, without migrating or rewriting the legacy database.
    """

    legacy_mission_id = job.mission_id
    if not legacy_mission_id or not legacy_mission_id.startswith("M-"):
        raise ValueError("legacy enqueue job has no valid mission id")
    kernel_mission_id = f"MISSION-legacy-{legacy_mission_id[2:]}"
    root = (
        Path(kernel_state_dir)
        if kernel_state_dir is not None
        else default_kernel_state_dir(legacy_state_dir)
    )
    root.mkdir(parents=True, exist_ok=True)
    store = KernelStore(KernelStore.database_path(root))
    try:
        event_id = f"migration:{LEGACY_ENQUEUE_ROUTE}:{legacy_mission_id}"
        idempotency_key = canonical_digest(
            {
                "route": LEGACY_ENQUEUE_ROUTE,
                "legacy_mission_id": legacy_mission_id,
                "scheduler_payload_digest": job.payload_digest,
            }
        )
        store.append(
            KernelEvent(
                event_id=event_id,
                mission_id=kernel_mission_id,
                event_type="mission.created",
                actor_id="phase11-repository-compatibility",
                actor_role="integrator",
                occurred_at="1970-01-01T00:00:00Z",
                payload={
                    "migration_route": LEGACY_ENQUEUE_ROUTE,
                    "legacy_mission_id": legacy_mission_id,
                    "scheduler_job_id": job.id,
                    "scheduler_payload_digest": job.payload_digest,
                    "repository_pin": job.payload.get("pin"),
                },
                previous_digest=store.events()[-1]["digest"] if store.events() else None,
            ),
            idempotency_key=idempotency_key,
        )
    finally:
        store.close()
    return kernel_mission_id
