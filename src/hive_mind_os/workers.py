"""Lease-owning scheduler workers that execute durable P06 missions."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Callable

from .autonomy import AutonomyBudget
from .ledger import EvidenceLedger
from .mission import RepositoryMission, ScriptedRepositoryBackend
from .mission_store import MissionStore, resume_mission
from .models import AutonomyLevel
from .policy import PolicyEngine
from .scheduler import Job, Scheduler, StaleLeaseError

JobExecutor = Callable[[Job, Path], str]


def execute_mission_job(job: Job, state_dir: Path) -> str:
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
                mission = RepositoryMission(
                    str(payload["repository"]),
                    str(payload["objective"]),
                    acceptance_criteria=tuple(payload["acceptance_criteria"]),
                    backend=backend,
                    pin=payload.get("pin"),
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


class Worker:
    def __init__(
        self,
        scheduler: Scheduler,
        owner: str,
        *,
        executor: JobExecutor = execute_mission_job,
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
    executor: JobExecutor = execute_mission_job,
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
