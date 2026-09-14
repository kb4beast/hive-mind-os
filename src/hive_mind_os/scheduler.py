"""SQLite job queue with token-bound leases, retries, and dead-lettering."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4


class Clock(Protocol):
    def now(self) -> float: ...


class SystemClock:
    def now(self) -> float:
        return time.time()


@dataclass(slots=True)
class ManualClock:
    value: float = 0.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("clock cannot move backwards")
        self.value += seconds


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    kind: str
    payload: dict[str, Any]
    payload_digest: str
    state: str
    attempts: int
    max_attempts: int
    not_before: float
    lease_owner: str | None
    lease_token: str | None
    lease_expiry: float | None
    mission_id: str | None
    last_error: str | None


class StaleLeaseError(RuntimeError):
    """A worker attempted to mutate a job after losing its lease."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class Scheduler:
    def __init__(
        self,
        state_dir: str | Path,
        *,
        clock: Clock | None = None,
        lease_seconds: float = 30.0,
        backoff_seconds: float = 1.0,
    ) -> None:
        if lease_seconds <= 0 or backoff_seconds < 0:
            raise ValueError("lease must be positive and backoff cannot be negative")
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "scheduler.sqlite3"
        self.clock = clock or SystemClock()
        self.lease_seconds = lease_seconds
        self.backoff_seconds = backoff_seconds
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            PRAGMA busy_timeout=30000;
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_digest TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL CHECK(
                    state IN ('ready','leased','done','dead-letter')
                ),
                attempts INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL,
                not_before REAL NOT NULL,
                lease_owner TEXT,
                lease_token TEXT,
                lease_expiry REAL,
                mission_id TEXT,
                last_error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS jobs_claimable
            ON jobs(state,not_before,lease_expiry,created_at);
            CREATE TABLE IF NOT EXISTS resource_leases (
                resource_id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                lease_owner TEXT NOT NULL,
                lease_token TEXT NOT NULL,
                lease_expiry REAL NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS resource_leases_expiry
            ON resource_leases(lease_expiry);
            CREATE INDEX IF NOT EXISTS resource_leases_job
            ON resource_leases(job_id,lease_token);
            """
        )

    def close(self) -> None:
        self._connection.close()

    def enqueue(
        self,
        kind: str,
        payload: Mapping[str, Any],
        *,
        max_attempts: int = 3,
        not_before: float | None = None,
        mission_id: str | None = None,
    ) -> Job:
        if not kind.strip() or max_attempts < 1:
            raise ValueError("job kind and positive max_attempts are required")
        encoded = _canonical_json(payload)
        digest_value = sha256((kind + "\0" + encoded).encode()).hexdigest()
        digest = f"sha256:{digest_value}"
        now = self.clock.now()
        job_id = f"JOB-{uuid4()}"
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO jobs(
                    id,kind,payload_json,payload_digest,state,attempts,max_attempts,
                    not_before,mission_id,created_at,updated_at
                ) VALUES(?,?,?,?, 'ready',0,?,?,?,?,?)
                """,
                (
                    job_id,
                    kind,
                    encoded,
                    digest,
                    max_attempts,
                    now if not_before is None else not_before,
                    mission_id,
                    now,
                    now,
                ),
            )
            row = self._connection.execute(
                "SELECT * FROM jobs WHERE payload_digest=?",
                (digest,),
            ).fetchone()
        assert row is not None
        return self._job(row)

    def claim(
        self,
        owner: str,
        *,
        kind: str | None = None,
        mission_id: str | None = None,
        job_id: str | None = None,
        resource_ids: Iterable[str] = (),
    ) -> Job | None:
        """Claim one eligible job, optionally within a sealed service scope.

        The optional selectors let multiple durable services safely share one
        scheduler without one service consuming another service's work. Resource
        identities are acquired atomically with the job lease and retained through
        heartbeats. Existing callers retain queue-wide behavior by omitting them.
        """
        if not owner.strip():
            raise ValueError("worker owner is required")
        supplied_resources = tuple(resource_ids)
        if any(
            not isinstance(item, str) or not item.strip() for item in supplied_resources
        ):
            raise ValueError("resource identities must be non-empty strings")
        resources = tuple(sorted(set(supplied_resources)))
        now = self.clock.now()
        token = str(uuid4())
        expiry = now + self.lease_seconds
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                # A resource row is authoritative only while its exact job lease is
                # live. Cleaning stale rows inside the same write transaction makes
                # reclamation atomic across independent Scheduler connections.
                self._connection.execute(
                    """
                    DELETE FROM resource_leases
                    WHERE lease_expiry<? OR NOT EXISTS (
                        SELECT 1 FROM jobs
                        WHERE jobs.id=resource_leases.job_id
                          AND jobs.state='leased'
                          AND jobs.lease_token=resource_leases.lease_token
                          AND jobs.lease_expiry>=?
                    )
                    """,
                    (now, now),
                )
                self._connection.execute(
                    """
                    UPDATE jobs
                    SET state='dead-letter',
                        last_error=COALESCE(
                            last_error,
                            'lease expired after final attempt'
                        ),
                        lease_owner=NULL,lease_token=NULL,lease_expiry=NULL,
                        updated_at=?
                    WHERE state='leased' AND lease_expiry<?
                      AND attempts>=max_attempts
                      AND (? IS NULL OR kind=?)
                      AND (? IS NULL OR mission_id=?)
                      AND (? IS NULL OR id=?)
                    """,
                    (
                        now,
                        now,
                        kind,
                        kind,
                        mission_id,
                        mission_id,
                        job_id,
                        job_id,
                    ),
                )
                row = self._connection.execute(
                    """
                    SELECT id FROM jobs
                    WHERE attempts < max_attempts
                      AND (
                        (state='ready' AND not_before<=?)
                        OR (state='leased' AND lease_expiry<?)
                      )
                      AND (? IS NULL OR kind=?)
                      AND (? IS NULL OR mission_id=?)
                      AND (? IS NULL OR id=?)
                    ORDER BY created_at,id
                    LIMIT 1
                    """,
                    (
                        now,
                        now,
                        kind,
                        kind,
                        mission_id,
                        mission_id,
                        job_id,
                        job_id,
                    ),
                ).fetchone()
                if row is None:
                    self._connection.execute("COMMIT")
                    return None
                if resources:
                    placeholders = ",".join("?" for _ in resources)
                    conflict = self._connection.execute(
                        f"""
                        SELECT 1 FROM resource_leases
                        WHERE resource_id IN ({placeholders})
                          AND lease_expiry>=?
                        LIMIT 1
                        """,  # noqa: S608 - placeholders are generated, not supplied
                        (*resources, now),
                    ).fetchone()
                    if conflict is not None:
                        self._connection.execute("COMMIT")
                        return None
                claimed = self._connection.execute(
                    """
                    UPDATE jobs
                    SET state='leased', attempts=attempts+1, lease_owner=?,
                        lease_token=?, lease_expiry=?, updated_at=?
                    WHERE id=? AND attempts < max_attempts
                      AND (
                        (state='ready' AND not_before<=?)
                        OR (state='leased' AND lease_expiry<?)
                      )
                    RETURNING *
                    """,
                    (owner, token, expiry, now, row["id"], now, now),
                ).fetchone()
                if claimed is not None:
                    self._connection.executemany(
                        """
                        INSERT INTO resource_leases(
                            resource_id,job_id,lease_owner,lease_token,
                            lease_expiry,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (
                            (resource, row["id"], owner, token, expiry, now, now)
                            for resource in resources
                        ),
                    )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        return None if claimed is None else self._job(claimed)

    def dead_letter(
        self,
        job_id: str,
        lease_token: str,
        error: str,
        *,
        mission_id: str | None = None,
    ) -> Job:
        """Persist a non-retryable typed blocker while retaining lease safety."""
        now = self.clock.now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    UPDATE jobs
                    SET state='dead-letter',mission_id=COALESCE(?,mission_id),
                        last_error=?,lease_owner=NULL,lease_token=NULL,
                        lease_expiry=NULL,updated_at=?
                    WHERE id=? AND state='leased' AND lease_token=? AND lease_expiry>=?
                    RETURNING *
                    """,
                    (mission_id, error, now, job_id, lease_token, now),
                ).fetchone()
                if row is not None:
                    self._connection.execute(
                        "DELETE FROM resource_leases WHERE job_id=? AND lease_token=?",
                        (job_id, lease_token),
                    )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        if row is None:
            raise StaleLeaseError("dead-letter rejected for stale lease")
        return self._job(row)

    def heartbeat(self, job_id: str, lease_token: str) -> Job:
        now = self.clock.now()
        expiry = now + self.lease_seconds
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    UPDATE jobs SET lease_expiry=?,updated_at=?
                    WHERE id=? AND state='leased' AND lease_token=? AND lease_expiry>=?
                    RETURNING *
                    """,
                    (expiry, now, job_id, lease_token, now),
                ).fetchone()
                if row is not None:
                    self._connection.execute(
                        """
                        UPDATE resource_leases SET lease_expiry=?,updated_at=?
                        WHERE job_id=? AND lease_token=?
                        """,
                        (expiry, now, job_id, lease_token),
                    )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        if row is None:
            raise StaleLeaseError("heartbeat rejected for stale lease")
        return self._job(row)

    def complete(
        self,
        job_id: str,
        lease_token: str,
        *,
        mission_id: str,
    ) -> Job:
        now = self.clock.now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    """
                    UPDATE jobs
                    SET state='done',mission_id=?,lease_owner=NULL,lease_token=NULL,
                        lease_expiry=NULL,updated_at=?
                    WHERE id=? AND state='leased' AND lease_token=? AND lease_expiry>=?
                    RETURNING *
                    """,
                    (mission_id, now, job_id, lease_token, now),
                ).fetchone()
                if row is not None:
                    self._connection.execute(
                        "DELETE FROM resource_leases WHERE job_id=? AND lease_token=?",
                        (job_id, lease_token),
                    )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        if row is None:
            raise StaleLeaseError("completion rejected for stale lease")
        return self._job(row)

    def fail(
        self,
        job_id: str,
        lease_token: str,
        error: str,
        *,
        mission_id: str | None = None,
    ) -> Job:
        now = self.clock.now()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                current_row = self._connection.execute(
                    "SELECT * FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
                if current_row is None:
                    raise KeyError(job_id)
                current = self._job(current_row)
                if (
                    current.state != "leased"
                    or current.lease_token != lease_token
                    or current.lease_expiry is None
                    or current.lease_expiry < now
                ):
                    raise StaleLeaseError("failure rejected for stale lease")
                dead = current.attempts >= current.max_attempts
                not_before = now + self.backoff_seconds * (2 ** (current.attempts - 1))
                row = self._connection.execute(
                    """
                    UPDATE jobs
                    SET state=?,not_before=?,mission_id=COALESCE(?,mission_id),
                        last_error=?,lease_owner=NULL,lease_token=NULL,
                        lease_expiry=NULL,updated_at=?
                    WHERE id=? AND state='leased' AND lease_token=? AND lease_expiry>=?
                    RETURNING *
                    """,
                    (
                        "dead-letter" if dead else "ready",
                        not_before,
                        mission_id,
                        error,
                        now,
                        job_id,
                        lease_token,
                        now,
                    ),
                ).fetchone()
                if row is not None:
                    self._connection.execute(
                        "DELETE FROM resource_leases WHERE job_id=? AND lease_token=?",
                        (job_id, lease_token),
                    )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        if row is None:
            raise StaleLeaseError("failure rejected for stale lease")
        return self._job(row)

    def get(self, job_id: str) -> Job:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._job(row)

    def jobs(self) -> tuple[Job, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM jobs ORDER BY created_at,id"
            ).fetchall()
        return tuple(self._job(row) for row in rows)

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        return Job(
            id=str(row["id"]),
            kind=str(row["kind"]),
            payload=json.loads(row["payload_json"]),
            payload_digest=str(row["payload_digest"]),
            state=str(row["state"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            not_before=float(row["not_before"]),
            lease_owner=row["lease_owner"],
            lease_token=row["lease_token"],
            lease_expiry=(
                None if row["lease_expiry"] is None else float(row["lease_expiry"])
            ),
            mission_id=row["mission_id"],
            last_error=row["last_error"],
        )
