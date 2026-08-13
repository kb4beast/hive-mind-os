"""Versioned, outer-layer compatibility records for legacy repository routes.

This module deliberately sits outside :mod:`brain_kernel`: the kernel remains
repository-neutral and never imports the legacy scheduler or mission runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .brain_kernel.canonical import canonical_digest
from .brain_kernel.events import KernelEvent
from .brain_kernel.store import KernelStore
from .scheduler import Job

LEGACY_ENQUEUE_ROUTE = "legacy-enqueue-v1"
CANONICAL_ENQUEUE_ROUTE = "canonical-enqueue-v1"
CANONICAL_JOB_KIND = "canonical-mission"
LEGACY_JOB_KIND = "repository-mission"
RUNTIME_CANONICAL = "canonical"
RUNTIME_LEGACY = "legacy"
RUNTIME_UNKNOWN = "unknown"
COMPATIBILITY_MODES = ("canonical", "kernel-v1", "legacy")
CANONICAL_ROLLBACK_REF = "rollback:cli-compatibility-mode-kernel-v1"


class RuntimeRouteError(RuntimeError):
    """A public ingress request cannot be routed without weakening a gate."""


@dataclass(frozen=True, slots=True)
class RuntimeRoute:
    """One resolved public-ingress route; exactly one runtime owns the request."""

    mode: str
    runtime: str
    job_kind: str
    records_kernel_ingress: bool
    rollback_ref: str


_ROUTES: dict[str, RuntimeRoute] = {
    "canonical": RuntimeRoute(
        "canonical",
        RUNTIME_CANONICAL,
        CANONICAL_JOB_KIND,
        True,
        CANONICAL_ROLLBACK_REF,
    ),
    "kernel-v1": RuntimeRoute(
        "kernel-v1",
        RUNTIME_LEGACY,
        LEGACY_JOB_KIND,
        True,
        f"rollback:{LEGACY_ENQUEUE_ROUTE}",
    ),
    "legacy": RuntimeRoute(
        "legacy",
        RUNTIME_LEGACY,
        LEGACY_JOB_KIND,
        False,
        "rollback:legacy-only",
    ),
}


def resolve_runtime_route(compatibility_mode: str) -> RuntimeRoute:
    """Select the single authoritative runtime for one public ingress request."""

    route = _ROUTES.get(compatibility_mode)
    if route is None:
        raise RuntimeRouteError(
            "unsupported compatibility mode: "
            f"{compatibility_mode!r}; expected one of {', '.join(COMPATIBILITY_MODES)}"
        )
    return route


def runtime_identity(job_kind: str) -> str:
    """Name the runtime that owns one queued job kind, without failing closed.

    Status is a read-only projection: an unrecognised kind is reported as
    ``"unknown"`` rather than raising.  Executors fail closed separately.
    """

    if job_kind == CANONICAL_JOB_KIND:
        return RUNTIME_CANONICAL
    if job_kind == LEGACY_JOB_KIND:
        return RUNTIME_LEGACY
    return RUNTIME_UNKNOWN


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


def record_canonical_enqueue(
    job: Job,
    *,
    kernel_state_dir: str | Path | None = None,
    legacy_state_dir: str | Path,
) -> str:
    """Append the kernel-side ingress record for one canonical scheduler job.

    This mirrors :func:`record_legacy_enqueue`.  It is a migration *record*, not a
    second execution authority: the scheduler still carries the request exactly
    once and the canonical runtime alone executes it.  The record is idempotent so
    repeating the same enqueue is a read-only retry.
    """

    legacy_mission_id = job.mission_id
    if not legacy_mission_id or not legacy_mission_id.startswith("M-"):
        raise ValueError("canonical enqueue job has no valid mission id")
    kernel_mission_id = f"MISSION-canonical-{legacy_mission_id[2:]}"
    root = (
        Path(kernel_state_dir)
        if kernel_state_dir is not None
        else default_kernel_state_dir(legacy_state_dir)
    )
    root.mkdir(parents=True, exist_ok=True)
    store = KernelStore(KernelStore.database_path(root))
    try:
        event_id = f"migration:{CANONICAL_ENQUEUE_ROUTE}:{legacy_mission_id}"
        idempotency_key = canonical_digest(
            {
                "route": CANONICAL_ENQUEUE_ROUTE,
                "legacy_mission_id": legacy_mission_id,
                "scheduler_payload_digest": job.payload_digest,
            }
        )
        store.append(
            KernelEvent(
                event_id=event_id,
                mission_id=kernel_mission_id,
                event_type="mission.created",
                actor_id="migration-460-cli-ingress",
                actor_role="integrator",
                occurred_at="1970-01-01T00:00:00Z",
                payload={
                    "migration_route": CANONICAL_ENQUEUE_ROUTE,
                    "runtime": RUNTIME_CANONICAL,
                    "legacy_mission_id": legacy_mission_id,
                    "scheduler_job_id": job.id,
                    "scheduler_payload_digest": job.payload_digest,
                    "repository_pin": job.payload.get("pin"),
                    "rollback_ref": CANONICAL_ROLLBACK_REF,
                },
                previous_digest=store.events()[-1]["digest"] if store.events() else None,
            ),
            idempotency_key=idempotency_key,
        )
    finally:
        store.close()
    return kernel_mission_id
