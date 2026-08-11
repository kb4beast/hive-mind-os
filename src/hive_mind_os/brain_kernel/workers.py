"""Bounded local kernel-work scheduling over the existing durable scheduler."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from ..scheduler import Job, Scheduler, StaleLeaseError
from .canonical import canonical_digest
from .events import KernelEvent
from .store import KernelStore


class ScopeLockStore:
    """Expiring exclusive write-scope locks; a failed acquisition executes nothing."""

    def __init__(self, state_dir: str | Path) -> None:
        self.path = Path(state_dir) / "kernel-scope-locks.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS scope_locks (path TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL)"
        )

    def acquire(self, paths: Iterable[str], owner: str, now: float, ttl: float) -> bool:
        paths = tuple(sorted(set(paths)))
        with self.connection:
            self.connection.execute("DELETE FROM scope_locks WHERE expires_at<?", (now,))
            held = self.connection.execute(
                "SELECT path FROM scope_locks WHERE path IN (%s)" % ",".join("?" * len(paths),),
                paths,
            ).fetchall() if paths else ()
            if held:
                return False
            self.connection.executemany(
                "INSERT INTO scope_locks VALUES(?,?,?)", ((path, owner, now + ttl) for path in paths)
            )
            return True

    def release(self, owner: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM scope_locks WHERE owner=?", (owner,))

    def close(self) -> None:
        self.connection.close()


KernelExecutor = Callable[[Job], None]


class KernelWorker:
    """One finite-poll local worker; it never invokes providers or external effects."""

    def __init__(self, scheduler: Scheduler, scope_locks: ScopeLockStore, owner: str, executor: KernelExecutor, *, store: KernelStore | None = None) -> None:
        self.scheduler, self.scope_locks, self.owner, self.executor, self.store = scheduler, scope_locks, owner, executor, store

    def _transition(self, job: Job, status: str) -> None:
        if self.store is None:
            return
        events = self.store.events()
        self.store.append(KernelEvent(f"worker:{job.id}:{status}", str(job.payload["mission_id"]), "work.transition", self.owner, "1970-01-01T00:00:00Z", {"status": status}, work_id=str(job.payload["work_id"]), actor_role="builder", previous_digest=events[-1]["digest"] if events else None))

    def enqueue(self, mission_id: str, work_id: str, write_scope: Iterable[str], *, max_attempts: int = 3) -> Job:
        payload = {"mission_id": mission_id, "work_id": work_id, "write_scope": tuple(sorted(write_scope))}
        payload["binding_digest"] = canonical_digest(payload)
        job = self.scheduler.enqueue("kernel-work", payload, max_attempts=max_attempts, mission_id=mission_id)
        if self.store is not None and self.store.projection()["work"][work_id]["status"] == "PROPOSED":
            self._transition(job, "READY")
        return job

    def cancel(self, job: Job) -> None:
        self._transition(job, "CANCELLED")

    def reconcile(
        self,
        observed: Mapping[str, Any],
        *,
        now: float | None = None,
        policy: Any | None = None,
    ) -> Any:
        """Derive a bounded recovery plan without executing any repair.

        The worker is an adapter only.  Explicit repair handlers remain the
        caller's responsibility, which keeps leases, effects, and event history
        under their existing authorities.
        """

        from .reconciler import DesiredStateReconciler

        clock_now = self.scheduler.clock.now() if now is None else now
        return DesiredStateReconciler(policy).reconcile(observed, now=clock_now)

    def run_once(self) -> bool:
        job = self.scheduler.claim(self.owner)
        if job is None:
            return False
        if job.kind != "kernel-work" or job.lease_token is None:
            self.scheduler.fail(job.id, job.lease_token or "", "unsupported kernel job")
            return True
        self._transition(job, "LEASED")
        lock_owner = f"{self.owner}:{job.id}:{job.lease_token}"
        paths = tuple(job.payload.get("write_scope", ()))
        if not self.scope_locks.acquire(paths, lock_owner, self.scheduler.clock.now(), self.scheduler.lease_seconds):
            self.scheduler.fail(job.id, job.lease_token, "write scope is locked")
            return True
        try:
            self._transition(job, "RUNNING")
            self.executor(job)
            self._transition(job, "AWAITING_VERIFICATION")
            self.scheduler.complete(job.id, job.lease_token, mission_id=str(job.payload["mission_id"]))
        except (StaleLeaseError, Exception) as error:
            try:
                self.scheduler.fail(job.id, job.lease_token, f"{type(error).__name__}: {error}")
            except StaleLeaseError:
                pass
        finally:
            self.scope_locks.release(lock_owner)
        return True
