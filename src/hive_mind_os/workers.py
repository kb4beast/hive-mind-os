"""Retired legacy runtime surface: the legacy scheduler executor (LEGACY-620).

Canonical ownership of mission execution belongs to
``hive_mind_os.brain_kernel.mission_runtime``, reached through the
MIGRATION-460 routing installed in ``hive_mind_os.cli``.  The legacy executor
``execute_mission_job`` and its ``repository-mission`` job kind survive only as
an explicitly marked rollback/compatibility surface: rollback tag
``legacy-620-rollback``, migration receipts in
``docs/execution/LEGACY_RUNTIME_RETIREMENT.md``.

Lease-owning scheduler workers that execute durable P06 missions.  :class:`Worker`
and :func:`serve` are *not* retired: they are runtime-neutral lease holders that
dispatch through :func:`route_job_executor`, the MIGRATION-460 kind-based routing
that owns canonical execution.  Only the legacy branch of that dispatch is a
retired surface.
"""

from __future__ import annotations

import asyncio
import threading
import warnings
from pathlib import Path
from typing import Any, Callable, Mapping

from .autonomy import AutonomyBudget
from .ledger import EvidenceLedger
from .mission import (
    RepositoryMission,
    ScriptedRepositoryBackend,
    resolve_repository_pin,
)
from .mission_store import MissionStore, resume_mission
from .models import AutonomyLevel
from .policy import PolicyEngine
from .repository_compatibility import (
    CANONICAL_JOB_KIND,
    LEGACY_JOB_KIND,
    RuntimeRouteError,
    default_kernel_state_dir,
)
from .scheduler import Job, Scheduler, StaleLeaseError

LEGACY_RUNTIME_NOTICE: dict[str, str] = {
    "entry_point": "hive_mind_os.workers",
    "status": "retired-legacy-rollback-only",
    "canonical_owner": "hive_mind_os.brain_kernel.mission_runtime",
    "canonical_ingress": "hive_mind_os.cli (MIGRATION-460 routing)",
    "canonical_destination": "canonical leases and delivery workers",
    "rollback_ref": "rollback:legacy-620",
    "rollback_tag": "legacy-620-rollback",
    "retired_by_node": "LEGACY-620",
    "parity_evidence": "evidence/qualification/hive-cortex/",
    "migration_receipts": "docs/execution/LEGACY_RUNTIME_RETIREMENT.md",
}


def retirement_notice() -> dict[str, str]:
    """Machine-readable compatibility notice for this retired legacy entry point."""

    return dict(LEGACY_RUNTIME_NOTICE)


def _warn_retired(entry: str) -> None:
    warnings.warn(
        f"{entry} is a retired legacy runtime surface (LEGACY-620); the canonical "
        "owner is hive_mind_os.brain_kernel.mission_runtime; rollback tag "
        "legacy-620-rollback",
        DeprecationWarning,
        stacklevel=3,
    )


JobExecutor = Callable[[Job, Path], str]


def execute_mission_job(job: Job, state_dir: Path) -> str:
    """Execute one legacy ``repository-mission`` job (retired rollback surface).

    Retained deliberately: ``LEGACY_JOB_KIND`` dispatch is the contract-mandated
    rollback mode for MIGRATION-460, so this executor is never hard-disabled.
    """

    _warn_retired("hive_mind_os.workers.execute_mission_job")
    if job.kind != "repository-mission":
        raise ValueError(f"unsupported job kind: {job.kind}")
    payload = job.payload
    mission_id = str(payload["mission_id"])
    store = MissionStore(state_dir)
    try:
        if store.has_mission(mission_id):
            mission = store.mission(mission_id)
            if mission["status"] == "succeeded":
                return mission_id
            report = asyncio.run(resume_mission(store, mission_id))
        else:
            ledger = EvidenceLedger(state_dir / "evidence-ledger.sqlite3")
            try:
                budget = AutonomyBudget(
                    max_episodes=1000,
                    max_tool_calls=500,
                    max_compute_units=500.0,
                    max_tool_calls_per_episode=100,
                    max_compute_units_per_episode=100.0,
                )
                backend = ScriptedRepositoryBackend(str(payload["scripted_variant"]))
                output = state_dir / "d" / mission_id
                output.parent.mkdir(parents=True, exist_ok=True)
                repository = Path(str(payload["repository"])).resolve()
                raw_pin = payload.get("pin")
                if not isinstance(raw_pin, str):
                    raise ValueError(
                        "queued repository mission must include a full immutable pin"
                    )
                mission = RepositoryMission(
                    repository,
                    str(payload["objective"]),
                    acceptance_criteria=tuple(payload["acceptance_criteria"]),
                    acceptance_specifications=tuple(
                        payload.get("acceptance_specifications", ())
                    ),
                    backend=backend,
                    pin=resolve_repository_pin(repository, raw_pin),
                    output_dir=output,
                    policy=PolicyEngine(AutonomyLevel.REPOSITORY),
                    budget=budget,
                    ledger=ledger,
                    mission_store=store,
                    _run_id=mission_id,
                )
                report = asyncio.run(mission.run())
            finally:
                ledger.close()
        if report.status.value != "succeeded":
            raise RuntimeError(
                f"mission {mission_id} ended {report.status.value}: {report.failure}"
            )
        return mission_id
    finally:
        store.close()


CanonicalMissionInvoker = Callable[[Job, Path], str]
CanonicalMissionBindingsProvider = Callable[[Mapping[str, Any], Path], tuple[Any, Any]]

_CANONICAL_PAYLOAD_FIELDS = (
    "mission_id",
    "repository",
    "objective",
    "acceptance_criteria",
    "acceptance_specifications",
    "pin",
)

_canonical_bindings_provider: CanonicalMissionBindingsProvider | None = None


def set_canonical_mission_bindings_provider(
    provider: CanonicalMissionBindingsProvider | None,
) -> CanonicalMissionBindingsProvider | None:
    """Register the deployment seam that builds canonical mission run inputs.

    ``MissionRuntime.run`` takes a ``MissionConfig`` and a ``MissionBindings``
    (role executor, builder effect authority, per-role verification specs, and a
    role-first consultation).  None of those can be derived from a scheduler
    payload, so a deployment must supply them explicitly.  Until one is
    registered the canonical route fails closed; it never falls back to legacy.
    Returns the previously registered provider so callers can restore it.
    """

    global _canonical_bindings_provider
    previous = _canonical_bindings_provider
    _canonical_bindings_provider = provider
    return previous


def _default_canonical_invoker(job: Job, state_dir: Path) -> str:
    """Bind lazily to :mod:`hive_mind_os.brain_kernel.mission_runtime`.

    The import stays inside the function so legacy-only deployments never load
    the canonical runtime.  Every missing precondition raises
    :class:`RuntimeRouteError`; nothing here ever reaches the legacy runtime.
    """

    payload = job.payload
    mission_id = payload.get("mission_id")
    if not isinstance(mission_id, str) or not mission_id:
        raise RuntimeRouteError("canonical mission job carries no mission id")
    missing = [name for name in _CANONICAL_PAYLOAD_FIELDS if name not in payload]
    if missing:
        raise RuntimeRouteError(
            "canonical mission job payload is incomplete: " + ", ".join(missing)
        )
    try:
        from .brain_kernel import mission_runtime as canonical_runtime
        from .brain_kernel.store import KernelStore
    except ImportError as error:
        raise RuntimeRouteError(
            f"canonical mission runtime is unavailable: {error}"
        ) from None
    runtime_class = getattr(canonical_runtime, "MissionRuntime", None)
    if runtime_class is None or not callable(getattr(runtime_class, "run", None)):
        raise RuntimeRouteError(
            "canonical mission runtime exposes no MissionRuntime.run entry point"
        )
    provider = _canonical_bindings_provider
    if provider is None:
        raise RuntimeRouteError(
            "canonical mission runtime has no registered bindings provider: "
            "MissionRuntime.run requires a MissionConfig and MissionBindings that "
            "a scheduler payload cannot supply"
        )
    kernel_root = default_kernel_state_dir(state_dir)
    kernel_root.mkdir(parents=True, exist_ok=True)
    config, bindings = provider(dict(payload), kernel_root)
    store = KernelStore(KernelStore.database_path(kernel_root))
    try:
        receipt = runtime_class(store).run(config, bindings)
    finally:
        store.close()
    if getattr(receipt, "mission_id", None) is None:
        raise RuntimeRouteError("canonical mission runtime returned no mission receipt")
    return mission_id


def execute_canonical_mission_job(
    job: Job,
    state_dir: Path,
    *,
    invoker: CanonicalMissionInvoker | None = None,
) -> str:
    """Execute one canonical request through the kernel runtime only.

    This path never opens the legacy :class:`MissionStore`: a canonical request
    has exactly one authoritative execution owner.
    """

    if job.kind != CANONICAL_JOB_KIND:
        raise ValueError(f"unsupported job kind: {job.kind}")
    mission_id = job.payload.get("mission_id")
    if not isinstance(mission_id, str) or not mission_id:
        raise ValueError("canonical mission job must carry a mission id")
    returned = (invoker or _default_canonical_invoker)(job, Path(state_dir))
    if not isinstance(returned, str) or not returned:
        raise RuntimeRouteError("canonical mission invoker returned no mission id")
    return returned


def route_job_executor(job: Job, state_dir: Path) -> str:
    """Select the one execution authority that owns this job kind."""

    if job.kind == CANONICAL_JOB_KIND:
        return execute_canonical_mission_job(job, state_dir)
    if job.kind == LEGACY_JOB_KIND:
        return execute_mission_job(job, state_dir)
    raise ValueError(f"unsupported job kind: {job.kind}")


class Worker:
    def __init__(
        self,
        scheduler: Scheduler,
        owner: str,
        *,
        executor: JobExecutor = route_job_executor,
        heartbeat_interval: float | None = None,
    ) -> None:
        if not owner.strip():
            raise ValueError("worker identity is required")
        self.scheduler = scheduler
        self.owner = owner
        self.executor = executor
        self.heartbeat_interval = (
            heartbeat_interval
            if heartbeat_interval is not None
            else max(0.05, scheduler.lease_seconds / 3)
        )
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat interval must be positive")

    def run_once(self) -> bool:
        job = self.scheduler.claim(self.owner)
        if job is None:
            return False
        assert job.lease_token is not None
        stop = threading.Event()
        heartbeat_error: list[BaseException] = []

        def heartbeat() -> None:
            while not stop.wait(self.heartbeat_interval):
                try:
                    self.scheduler.heartbeat(job.id, job.lease_token or "")
                except BaseException as error:
                    heartbeat_error.append(error)
                    return

        thread = threading.Thread(
            target=heartbeat,
            name=f"heartbeat-{self.owner}",
            daemon=True,
        )
        thread.start()
        mission_id: str | None = None
        try:
            mission_id = self.executor(job, self.scheduler.state_dir)
            if heartbeat_error:
                raise StaleLeaseError(str(heartbeat_error[0]))
            self.scheduler.complete(
                job.id,
                job.lease_token,
                mission_id=mission_id,
            )
        except BaseException as error:
            try:
                self.scheduler.fail(
                    job.id,
                    job.lease_token,
                    f"{type(error).__name__}: {error}",
                    mission_id=mission_id or job.payload.get("mission_id"),
                )
            except StaleLeaseError:
                pass
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            stop.set()
            thread.join(timeout=max(1.0, self.heartbeat_interval * 2))
        return True

    def drain(self) -> int:
        handled = 0
        while self.run_once():
            handled += 1
        return handled


def serve(
    state_dir: str | Path,
    *,
    worker_count: int,
    once: bool,
    stop_event: threading.Event | None = None,
    executor: JobExecutor = route_job_executor,
) -> int:
    if worker_count < 1:
        raise ValueError("worker count must be positive")
    stopping = stop_event or threading.Event()
    errors: list[BaseException] = []

    def run(index: int) -> None:
        scheduler = Scheduler(state_dir)
        worker = Worker(scheduler, f"worker:{index}", executor=executor)
        try:
            if once:
                while True:
                    if worker.run_once():
                        continue
                    pending = [
                        job
                        for job in scheduler.jobs()
                        if job.state not in {"done", "dead-letter"}
                    ]
                    if not pending:
                        break
                    future = [
                        job.not_before - scheduler.clock.now()
                        for job in pending
                        if job.state == "ready"
                    ]
                    delay = max(0.01, min(future)) if future else 0.05
                    stopping.wait(min(delay, 0.25))
            else:
                while not stopping.wait(0.25):
                    worker.run_once()
        except BaseException as error:
            errors.append(error)
            stopping.set()
        finally:
            scheduler.close()

    threads = [
        threading.Thread(target=run, args=(index,), name=f"worker-{index}")
        for index in range(worker_count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise RuntimeError(f"worker failed: {errors[0]}")
    queue = Scheduler(state_dir)
    try:
        unfinished = [job for job in queue.jobs() if job.state not in {"done", "dead-letter"}]
        return 0 if not unfinished else 1
    finally:
        queue.close()
