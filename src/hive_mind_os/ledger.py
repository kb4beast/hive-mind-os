from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from .models import utc_now


class LedgerIntegrityError(RuntimeError):
    """The append-only event chain no longer matches its stored digests."""


class EvidenceLedger:
    """Append-only evidence and learning store backed by SQLite."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    prev_digest TEXT,
                    row_digest TEXT
                );
                CREATE TABLE IF NOT EXISTS lessons (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    lesson TEXT NOT NULL,
                    source_event_sequence INTEGER,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(source_event_sequence) REFERENCES events(sequence)
                );
                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS lessons_no_update
                BEFORE UPDATE ON lessons BEGIN SELECT RAISE(ABORT, 'lessons are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS lessons_no_delete
                BEFORE DELETE ON lessons BEGIN SELECT RAISE(ABORT, 'lessons are append-only'); END;
                """
            )
            self._migrate_event_chain()

    def _migrate_event_chain(self) -> None:
        columns = {
            str(row["name"])
            for row in self._connection.execute("PRAGMA table_info(events)")
        }
        for column in ("prev_digest", "row_digest"):
            if column not in columns:
                self._connection.execute(f"ALTER TABLE events ADD COLUMN {column} TEXT")
        rows = self._connection.execute(
            "SELECT sequence,run_id,event_type,actor,payload,created_at,prev_digest,row_digest "
            "FROM events ORDER BY sequence"
        ).fetchall()
        if not rows or all(
            isinstance(row["prev_digest"], str)
            and isinstance(row["row_digest"], str)
            for row in rows
        ):
            return
        self._connection.execute("DROP TRIGGER IF EXISTS events_no_update")
        previous = ""
        for row in rows:
            digest = _event_digest(
                int(row["sequence"]),
                str(row["run_id"]),
                str(row["event_type"]),
                str(row["actor"]),
                str(row["payload"]),
                str(row["created_at"]),
                previous,
            )
            self._connection.execute(
                "UPDATE events SET prev_digest=?,row_digest=? WHERE sequence=?",
                (previous, digest, int(row["sequence"])),
            )
            previous = digest
        self._connection.execute(
            "CREATE TRIGGER IF NOT EXISTS events_no_update "
            "BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'events are append-only'); END"
        )

    def append_event(self, run_id: str, event_type: str, actor: str, payload: dict[str, Any]) -> int:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        with self._lock, self._connection:
            prior = self._connection.execute(
                "SELECT sequence,row_digest FROM events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = "" if prior is None else prior["row_digest"]
            if not isinstance(previous, str):
                raise LedgerIntegrityError("ledger predecessor digest is missing")
            sequence = 1 if prior is None else int(prior["sequence"]) + 1
            created_at = utc_now()
            digest = _event_digest(
                sequence,
                run_id,
                event_type,
                actor,
                encoded,
                created_at,
                previous,
            )
            cursor = self._connection.execute(
                "INSERT INTO events(sequence,run_id,event_type,actor,payload,created_at,prev_digest,row_digest) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (sequence, run_id, event_type, actor, encoded, created_at, previous, digest),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return an event sequence")
            return int(cursor.lastrowid)

    def append_lessons(
        self,
        run_id: str,
        role: str,
        lessons: Iterable[str],
        source_event_sequence: int | None = None,
    ) -> None:
        rows = [
            (run_id, role, lesson.strip(), source_event_sequence, utc_now())
            for lesson in lessons
            if lesson.strip()
        ]
        if not rows:
            return
        with self._lock, self._connection:
            self._connection.executemany(
                "INSERT INTO lessons(run_id,role,lesson,source_event_sequence,created_at) VALUES(?,?,?,?,?)",
                rows,
            )

    def events(self, run_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._connection.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        self._validate_event_chain(rows)
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload"]),
            }
            for row in rows
            if run_id is None or row["run_id"] == run_id
        ]

    @staticmethod
    def _validate_event_chain(rows: Iterable[sqlite3.Row]) -> None:
        previous = ""
        for row in rows:
            stored_previous = row["prev_digest"]
            stored_digest = row["row_digest"]
            if stored_previous != previous or not isinstance(stored_digest, str):
                raise LedgerIntegrityError("ledger event chain is malformed")
            expected = _event_digest(
                int(row["sequence"]),
                str(row["run_id"]),
                str(row["event_type"]),
                str(row["actor"]),
                str(row["payload"]),
                str(row["created_at"]),
                previous,
            )
            if stored_digest != expected:
                raise LedgerIntegrityError("ledger event chain digest mismatch")
            previous = stored_digest

    def close(self) -> None:
        self._connection.close()


def _event_digest(
    sequence: int,
    run_id: str,
    event_type: str,
    actor: str,
    payload: str,
    created_at: str,
    previous: str,
) -> str:
    encoded = json.dumps(
        (sequence, run_id, event_type, actor, payload, created_at, previous),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"
