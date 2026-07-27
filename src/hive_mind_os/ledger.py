from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any, Iterable

from .models import utc_now


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
                    created_at TEXT NOT NULL
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

    def append_event(self, run_id: str, event_type: str, actor: str, payload: dict[str, Any]) -> int:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "INSERT INTO events(run_id,event_type,actor,payload,created_at) VALUES(?,?,?,?,?)",
                (run_id, event_type, actor, encoded, utc_now()),
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
        query = "SELECT * FROM events"
        params: tuple[str, ...] = ()
        if run_id:
            query += " WHERE run_id = ?"
            params = (run_id,)
        query += " ORDER BY sequence"
        rows = self._connection.execute(query, params).fetchall()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()
