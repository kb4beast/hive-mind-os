"""Portable, append-only idea history; court records confer no execution authority.

Actor names are local assertions, not authentication or independent verification.
Source strings are provenance references, not claims that a source was ingested.
Markdown is returned to callers so exporting cannot overwrite existing user notes.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from pathlib import Path
from threading import RLock

_DISPOSITIONS = frozenset({"adopt", "adapt", "defer", "reject", "quarantine"})
_KINDS = _DISPOSITIONS | {"challenged", "revised"}


class IdeaLineageError(ValueError):
    """An append violates the idea history contract or its revision precondition."""


@dataclass(frozen=True, slots=True)
class IdeaEvent:
    subject_id: str
    idea_id: str
    sequence: int
    revision: int
    event_type: str
    actor_id: str
    reason: str
    title: str
    hypothesis: str
    source: str
    parent_idea_id: str | None
    max_revisions: int
    return_to_agent: str | None
    next_action: str | None
    recorded_at: str
    previous_digest: str | None
    digest: str


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IdeaLineageError(f"{name} must be non-empty text")
    return value.strip()


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def idea_note_name(idea_id: str) -> str:
    """Portable, case-safe filename for arbitrary idea identities."""
    return "idea-" + sha256(idea_id.encode("utf-8")).hexdigest() + ".md"


class IdeaLineageStore:
    """SQLite histories partitioned by arbitrary subject identities.

    Each write checks its expected per-idea sequence inside BEGIN IMMEDIATE.
    Database triggers prevent UPDATE/DELETE, including through other connections;
    hash chains detect accidental history corruption, not a hostile database owner.
    Revision budgets include the original proposal and are fixed at creation.
    """

    def __init__(self, path: str | Path = ":memory:", *, read_only: bool = False) -> None:
        self._lock = RLock()
        connection_path = Path(path).resolve().as_uri() + "?mode=ro" if read_only else str(path)
        self._connection = sqlite3.connect(
            connection_path, uri=read_only, timeout=30, isolation_level=None, check_same_thread=False
        )
        if read_only:
            try:
                self._connection.execute(
                    "SELECT subject_id, idea_id, sequence, body_json, digest FROM idea_lineage_events LIMIT 0"
                )
            except sqlite3.Error as error:
                self._connection.close()
                raise IdeaLineageError("not an idea history database") from error
            return
        self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS idea_lineage_events (
                subject_id TEXT NOT NULL,
                idea_id TEXT NOT NULL,
                sequence INTEGER NOT NULL CHECK(sequence > 0),
                body_json TEXT NOT NULL,
                digest TEXT NOT NULL,
                PRIMARY KEY(subject_id, idea_id, sequence)
            );
            CREATE TRIGGER IF NOT EXISTS idea_lineage_no_update
            BEFORE UPDATE ON idea_lineage_events BEGIN
                SELECT RAISE(ABORT, 'idea history is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS idea_lineage_no_delete
            BEFORE DELETE ON idea_lineage_events BEGIN
                SELECT RAISE(ABORT, 'idea history is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS idea_lineage_no_replace
            BEFORE INSERT ON idea_lineage_events WHEN EXISTS (
                SELECT 1 FROM idea_lineage_events WHERE subject_id=NEW.subject_id
                AND idea_id=NEW.idea_id AND sequence=NEW.sequence
            ) BEGIN
                SELECT RAISE(ABORT, 'idea history is append-only');
            END;
        """)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> IdeaLineageStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def history(self, subject_id: str, idea_id: str) -> tuple[IdeaEvent, ...]:
        """Return immutable verified events, or an empty tuple for an unknown idea."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT sequence, body_json, digest FROM idea_lineage_events "
                "WHERE subject_id=? AND idea_id=? ORDER BY sequence",
                (subject_id, idea_id),
            ).fetchall()
            events: list[IdeaEvent] = []
            for sequence, body, digest in rows:
                try:
                    value = json.loads(body)
                    event = IdeaEvent(**value, digest=digest)
                except (TypeError, ValueError) as error:
                    raise IdeaLineageError("invalid idea history event") from error
                if (
                    sha256(_canonical(value).encode("utf-8")).hexdigest() != digest
                    or event.sequence != sequence or sequence != len(events) + 1
                    or event.subject_id != subject_id or event.idea_id != idea_id
                    or event.previous_digest != (events[-1].digest if events else None)
                ):
                    raise IdeaLineageError("idea history digest or sequence mismatch")
                events.append(event)
            return tuple(events)

    def _insert(self, value: dict) -> IdeaEvent:
        value["recorded_at"] = datetime.now(timezone.utc).isoformat()
        body = _canonical(value)
        digest = sha256(body.encode("utf-8")).hexdigest()
        self._connection.execute(
            "INSERT INTO idea_lineage_events VALUES (?, ?, ?, ?, ?)",
            (value["subject_id"], value["idea_id"], value["sequence"], body, digest),
        )
        return IdeaEvent(**value, digest=digest)

    def propose(
        self, *, subject_id: str, idea_id: str, title: str, hypothesis: str,
        source: str, actor_id: str, parent_idea_id: str | None = None,
        max_revisions: int = 8,
    ) -> IdeaEvent:
        """Capture a hypothesis and source without requiring benchmarks or proof."""
        value = {name: _text(item, name) for name, item in {
            "subject_id": subject_id, "idea_id": idea_id, "title": title,
            "hypothesis": hypothesis, "source": source, "actor_id": actor_id,
        }.items()}
        if type(max_revisions) is not int or not 1 <= max_revisions <= 100:
            raise IdeaLineageError("max_revisions must be between 1 and 100")
        if parent_idea_id is not None:
            parent_idea_id = _text(parent_idea_id, "parent_idea_id")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                if self.history(value["subject_id"], value["idea_id"]):
                    raise IdeaLineageError("idea already exists; append a revision")
                if parent_idea_id is not None and not self.history(
                    value["subject_id"], parent_idea_id
                ):
                    raise IdeaLineageError("parent must exist in the same subject")
                event = self._insert(dict(
                    value, sequence=1, revision=1, event_type="proposed",
                    reason="Initial hypothesis captured for challenge.",
                    parent_idea_id=parent_idea_id, max_revisions=max_revisions,
                    return_to_agent=None, next_action=None, previous_digest=None,
                ))
                self._connection.execute("COMMIT")
                return event
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def append(
        self, *, subject_id: str, idea_id: str, event_type: str, actor_id: str,
        reason: str, expected_sequence: int, hypothesis: str | None = None,
        source: str | None = None, return_to_agent: str | None = None,
        next_action: str | None = None,
    ) -> IdeaEvent:
        """Record challenge, revision, or disposition; never promote executable code.

        A disposition needs a challenge of the current revision and a separate
        judge. Returned work records its recipient and concrete next action.
        Even rejected ideas can be revised within their original iteration budget.
        """
        if event_type not in _KINDS:
            raise IdeaLineageError("unsupported idea event type")
        subject_id = _text(subject_id, "subject_id")
        idea_id = _text(idea_id, "idea_id")
        actor_id, reason = _text(actor_id, "actor_id"), _text(reason, "reason")
        if type(expected_sequence) is not int or expected_sequence < 1:
            raise IdeaLineageError("expected_sequence must be a positive integer")
        if (return_to_agent is None) != (next_action is None):
            raise IdeaLineageError("returned work needs both recipient and next action")
        if return_to_agent is not None:
            return_to_agent = _text(return_to_agent, "return_to_agent")
            next_action = _text(next_action, "next_action")
        if event_type in {"defer", "reject", "quarantine"} and return_to_agent is None:
            raise IdeaLineageError("non-adoption needs a recipient and recovery action")
        if hypothesis is not None and event_type != "revised":
            raise IdeaLineageError("only a revision can change the hypothesis")
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                events = self.history(subject_id, idea_id)
                if not events or events[-1].sequence != expected_sequence:
                    raise IdeaLineageError("unknown idea or stale expected_sequence")
                previous = events[-1]
                proposers = {e.actor_id for e in events if e.event_type in {"proposed", "revised"}}
                challengers = {e.actor_id for e in events if e.event_type == "challenged"}
                judges = {e.actor_id for e in events if e.event_type in _DISPOSITIONS}
                if previous.event_type in _DISPOSITIONS and event_type != "revised":
                    raise IdeaLineageError("revise the idea before reopening its court")
                if event_type == "challenged" and actor_id in proposers | judges:
                    raise IdeaLineageError("challenger must be separate from proposer and judge")
                if event_type == "revised":
                    if actor_id in challengers | judges:
                        raise IdeaLineageError("reviser must be separate from challenger and judge")
                    hypothesis = _text(hypothesis, "hypothesis")
                    if previous.revision >= previous.max_revisions:
                        raise IdeaLineageError("idea revision budget exhausted")
                if event_type in _DISPOSITIONS:
                    if actor_id in proposers | challengers:
                        raise IdeaLineageError("judge must be separate from proposer and challenger")
                    if not any(e.event_type == "challenged" and e.revision == previous.revision for e in events):
                        raise IdeaLineageError("current revision needs an independent challenge")
                value = asdict(previous)
                value.pop("digest")
                value.update(
                    sequence=previous.sequence + 1,
                    revision=previous.revision + int(event_type == "revised"),
                    event_type=event_type, actor_id=actor_id, reason=reason,
                    hypothesis=hypothesis if hypothesis is not None else previous.hypothesis,
                    source=_text(source, "source") if source is not None else previous.source,
                    return_to_agent=return_to_agent, next_action=next_action,
                    previous_digest=previous.digest,
                )
                event = self._insert(value)
                self._connection.execute("COMMIT")
                return event
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def render_markdown(self, subject_id: str, idea_id: str) -> str:
        """Deterministic complete projection; caller owns destination and export policy."""
        events = self.history(subject_id, idea_id)
        if not events:
            raise IdeaLineageError("unknown idea")
        latest = events[-1]

        def block(label: str, value: str) -> str:
            # Quote arbitrary source text so embedded headings cannot mimic metadata.
            return f"**{label}**\n\n" + "\n".join(
                f"> {escape(line, quote=False)}" for line in value.splitlines()
            ) + "\n"

        lines = ["# Idea history\n", block("Title", latest.title),
                 block("Subject", subject_id), block("Idea ID", idea_id),
                 f"Status: **{latest.event_type}** · Revision {latest.revision}/{latest.max_revisions}\n",
                 "Actor identities are local assertions, not authentication. "
                 "Court dispositions grant no execution or promotion authority.\n"]
        if latest.parent_idea_id is not None:
            lines.append(block("Parent idea", latest.parent_idea_id))
            lines.append(f"[Parent history]({idea_note_name(latest.parent_idea_id)})\n")
        for event in events:
            lines.extend([
                f"## Event {event.sequence} · Revision {event.revision} · {event.event_type}\n",
                block("Actor", event.actor_id), block("Reason", event.reason),
                block("Hypothesis", event.hypothesis), block("Source reference", event.source),
            ])
            if event.return_to_agent is not None:
                lines.extend([block("Returned to", event.return_to_agent),
                              block("Next action", _text(event.next_action, "next_action"))])
            lines.append(f"Recorded: {event.recorded_at}\n\nDigest: `{event.digest}`\n")
        return "\n".join(lines)
