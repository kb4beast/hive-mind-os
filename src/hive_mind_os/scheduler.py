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
    """The durable queue or immutable job identity is inconsistent."""


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
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            raise

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
                enqueue_spec_json TEXT,
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
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(jobs)")
        }
        if "enqueue_spec_json" not in columns:
            self._connection.execute("ALTER TABLE jobs ADD COLUMN enqueue_spec_json TEXT")
        self._validate_open()

    def _validate_open(self) -> None:
        quick = [str(row[0]) for row in self._connection.execute("PRAGMA quick_check")]
        if quick != ["ok"]:
            raise SchedulerIntegrityError("scheduler failed SQLite integrity check")
        if self._connection.execute("PRAGMA foreign_key_check").fetchall():
            raise SchedulerIntegrityError("scheduler failed foreign-key validation")
        for row in self._connection.execute("SELECT * FROM jobs"):
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, json.JSONDecodeError) as error:
                raise SchedulerIntegrityError("scheduler payload JSON is corrupt") from error
            if not isinstance(payload, dict) or _canonical_json(payload) != row["payload_json"]:
                raise SchedulerIntegrityError("scheduler payload JSON is not canonical")
            spec_json = row["enqueue_spec_json"]
            if spec_json is not None:
                try:
                    spec = json.loads(str(spec_json))
                except (TypeError, json.JSONDecodeError) as error:
                    raise SchedulerIntegrityError("scheduler enqueue identity is corrupt") from error
                if not isinstance(spec, dict) or _canonical_json(spec) != spec_json:
                    raise SchedulerIntegrityError("scheduler enqueue identity is not canonical")
                expected_digest = "sha256:" + sha256(str(spec_json).encode("utf-8")).hexdigest()
                if row["payload_digest"] != expected_digest:
                    raise SchedulerIntegrityError("scheduler enqueue identity digest is corrupt")
                if (
                    spec.get("kind") != row["kind"]
                    or spec.get("payload") != payload
                    or spec.get("max_attempts") != row["max_attempts"]
                    or (
                        spec.get("mission_id") is not None
                        and spec.get("mission_id") != row["mission_id"]
                    )
                ):
                    raise SchedulerIntegrityError("scheduler row differs from its enqueue identity")
                requested = spec.get("not_before")
                if requested is not None and float(requested) != float(row["not_before"]):
                    raise SchedulerIntegrityError("scheduler start time differs from enqueue identity")
            state = str(row["state"])
            lease = (row["lease_owner"], row["lease_token"], row["lease_expiry"])
            attempts = int(row["attempts"])
            maximum = int(row["max_attempts"])
            if attempts < 0 or maximum < 1 or attempts > maximum:
                raise SchedulerIntegrityError("scheduler attempt counters are incoherent")
            if state == "leased":
                if (
                    attempts < 1
                    or not all(value is not None for value in lease)
                    or not str(row["lease_owner"]).strip()
                    or not str(row["lease_token"]).strip()
                ):
                    raise SchedulerIntegrityError("leased job has incomplete lease authority")
            elif any(value is not None for value in lease):
                raise SchedulerIntegrityError("unleased job retains lease authority")

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
        enqueue_spec = _canonical_json(
            {
                "kind": kind,
                "payload": dict(payload),
                "max_attempts": max_attempts,
                "not_before": not_before,
                "mission_id": mission_id,
            }
        )
        digest_value = sha256(enqueue_spec.encode("utf-8")).hexdigest()
        digest = f"sha256:{digest_value}"
        now = self.clock.now()
        job_id = f"JOB-{uuid4()}"
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO jobs(
                    id,kind,payload_json,payload_digest,enqueue_spec_json,
                    state,attempts,max_attempts,
                    not_before,mission_id,created_at,updated_at
                ) VALUES(?,?,?,?,?, 'ready',0,?,?,?,?,?)
                """,
                (
                    job_id,
                    kind,
                    encoded,
                    digest,
                    enqueue_spec,
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
        if row["enqueue_spec_json"] != enqueue_spec:
            raise SchedulerIntegrityError("scheduler digest collision binds another job spec")
        return self._job(row)

    def claim(
        self,
        owner: str,
        *,
        mission_id: str | None = None,
        kind: str | None = None,
    ) -> Job | None:
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
                    SELECT id FROM jobs
                    WHERE attempts < max_attempts
                      AND (? IS NULL OR mission_id=?)
                      AND (? IS NULL OR kind=?)
                      AND (
                        (state='ready' AND not_before<=?)
                        OR (state='leased' AND lease_expiry<?)
                      )
                    ORDER BY created_at,id
                    LIMIT 1
                    """,
                    (mission_id, mission_id, kind, kind, now, now),
                ).fetchone()
                if row is None:
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
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        return None if claimed is None else self._job(claimed)

    def heartbeat(self, job_id: str, lease_token: str) -> Job:
        now = self.clock.now()
        with self._lock:
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
            current = self.get(job_id)
            if (
                current.state != "leased"
                or current.lease_token != lease_token
                or current.lease_expiry is None
                or current.lease_expiry < now
            ):
                raise StaleLeaseError("completion rejected for stale lease")
            if current.mission_id is not None and current.mission_id != mission_id:
                raise SchedulerIntegrityError("completion mission differs from queued mission")
            row = self._connection.execute(
                """
                UPDATE jobs
                SET state='done',mission_id=COALESCE(mission_id,?),
                    lease_owner=NULL,lease_token=NULL,
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
            if (
                mission_id is not None
                and current.mission_id is not None
                and current.mission_id != mission_id
            ):
                raise SchedulerIntegrityError("failure mission differs from queued mission")
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
