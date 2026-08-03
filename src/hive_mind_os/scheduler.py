"""SQLite job queue with token-bound leases, retries, and dead-lettering."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol
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


class SchedulerIntegrityError(RuntimeError):
    """A persisted job no longer binds to the payload it was approved with."""


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _payload_digest(kind: str, payload: Mapping[str, Any]) -> str:
    encoded = _canonical_json(payload)
    return "sha256:" + sha256((kind + "\0" + encoded).encode()).hexdigest()


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
        digest = _payload_digest(kind, payload)
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

    def claim(self, owner: str) -> Job | None:
        if not owner.strip():
            raise ValueError("worker owner is required")
        now = self.clock.now()
        token = str(uuid4())
        expiry = now + self.lease_seconds
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
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
                    """,
                    (now, now),
                )
                row = self._connection.execute(
                    """
                    SELECT * FROM jobs
                    WHERE attempts < max_attempts
                      AND (
                        (state='ready' AND not_before<=?)
                        OR (state='leased' AND lease_expiry<?)
                      )
                    ORDER BY created_at,id
                    LIMIT 1
                    """,
                    (now, now),
                ).fetchone()
                if row is None:
                    self._connection.execute("COMMIT")
                    return None
                self._job(row)
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
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        return None if claimed is None else self._job(claimed)

    def heartbeat(self, job_id: str, lease_token: str) -> Job:
        now = self.clock.now()
        with self._lock:
            current = self._connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if current is not None:
                self._job(current)
            row = self._connection.execute(
                """
                UPDATE jobs SET lease_expiry=?,updated_at=?
                WHERE id=? AND state='leased' AND lease_token=? AND lease_expiry>=?
                RETURNING *
                """,
                (now + self.lease_seconds, now, job_id, lease_token, now),
            ).fetchone()
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
            current = self._connection.execute(
                "SELECT * FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if current is not None:
                self._job(current)
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
            current = self.get(job_id)
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
                SET state=?,not_before=?,mission_id=COALESCE(?,mission_id),last_error=?,
                    lease_owner=NULL,lease_token=NULL,lease_expiry=NULL,updated_at=?
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
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError as error:
            raise SchedulerIntegrityError("job payload is not valid JSON") from error
        if not isinstance(payload, dict):
            raise SchedulerIntegrityError("job payload is not an object")
        observed = _payload_digest(str(row["kind"]), payload)
        if row["payload_digest"] != observed:
            raise SchedulerIntegrityError(
                "job payload no longer binds its canonical digest"
            )
        return Job(
            id=str(row["id"]),
            kind=str(row["kind"]),
            payload=payload,
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
