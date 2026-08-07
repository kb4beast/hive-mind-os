"""Deterministic, bounded local primitives for governed kernel memory.

This module deliberately supplies no model, network, scheduler, or legacy-memory
adapter.  Records and lifecycle facts are append-only; larger UTF-8 bodies live in
a content-addressed artifact store and are never rewritten in place.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Iterable, Mapping

from ..contracts import ROLE_NAMES
from .canonical import canonical_digest
from .contracts import MemoryRecord, MemoryState

_TOKEN = re.compile(r"[a-z0-9][a-z0-9._/-]*")
_SECRET = re.compile(
    r"(?i)(?:\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*\S+|\b(?:sk|ghp|github_pat)_[a-z0-9_-]{8,})"
)
_TRANSCRIPT_KINDS = frozenset({"model_transcript", "raw_transcript", "tool_transcript"})
_TERMINAL_STATES = frozenset(
    {
        MemoryState.SUPERSEDED,
        MemoryState.CONTRADICTED,
        MemoryState.RETRACTED,
        MemoryState.EXPIRED,
        MemoryState.QUARANTINED,
    }
)


class MemoryDenied(ValueError):
    """A requested memory operation violates the bounded local contract."""


def estimate_tokens(text: str | bytes) -> int:
    """Return a stable conservative estimate without provider-specific tokenization."""

    size = len(text.encode("utf-8")) if isinstance(text, str) else len(text)
    return (size + 3) // 4


def normalize_terms(value: str) -> frozenset[str]:
    """Normalize lexical terms in a platform-independent, deterministic manner."""

    if not isinstance(value, str):
        raise ValueError("memory text must be a string")
    return frozenset(_TOKEN.findall(value.casefold()))


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("time must be RFC 3339") from error
    if parsed.tzinfo is None:
        raise ValueError("time must include an offset")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class MemoryArtifact:
    digest: str
    token_count: int


class MemoryArtifactStore:
    """Immutable UTF-8 content addressed bodies rooted below a supplied directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(self, body: str, *, content_kind: str = "evidence") -> MemoryArtifact:
        if not isinstance(body, str) or not body:
            raise MemoryDenied("memory body must be non-empty UTF-8 text")
        if content_kind in _TRANSCRIPT_KINDS:
            raise MemoryDenied("raw transcripts cannot enter durable memory")
        if _SECRET.search(body) is not None:
            raise MemoryDenied("secret-like data cannot enter durable memory")
        encoded = body.encode("utf-8")
        digest = f"sha256:{sha256(encoded).hexdigest()}"
        target = self._path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as artifact:
                artifact.write(encoded)
        except FileExistsError:
            if target.read_bytes() != encoded:
                raise MemoryDenied("content-addressed evidence cannot be rewritten")
        return MemoryArtifact(digest, estimate_tokens(encoded))

    def get(self, digest: str) -> str:
        target = self._path(digest)
        try:
            body = target.read_text(encoding="utf-8")
        except OSError as error:
            raise KeyError(f"unknown memory artifact: {digest}") from error
        if f"sha256:{sha256(body.encode('utf-8')).hexdigest()}" != digest:
            raise MemoryDenied("memory artifact digest mismatch")
        return body

    def _path(self, digest: str) -> Path:
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError("artifact reference must be a sha256 digest")
        value = digest.removeprefix("sha256:")
        return self.root / "memory" / "artifacts" / "sha256" / value[:2] / value


@dataclass(frozen=True, slots=True)
class MemoryAccess:
    """Explicit access labels; no caller obtains a memory view by default."""

    roles: tuple[str, ...]
    data_scopes: tuple[str, ...]
    evaluator_visible: bool = True

    def __post_init__(self) -> None:
        if not self.roles:
            raise ValueError("memory access requires at least one role")
        if any(role not in ROLE_NAMES for role in self.roles):
            raise ValueError("memory access contains an unregistered role")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("memory access roles must be unique")
        if len(set(self.data_scopes)) != len(self.data_scopes):
            raise ValueError("memory access scopes must be unique")


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    record: MemoryRecord
    access: MemoryAccess


@dataclass(frozen=True, slots=True)
class MemoryLifecycleEvent:
    sequence: int
    event_id: str
    record_id: str
    previous_state: MemoryState
    state: MemoryState
    occurred_at: str
    reason: str
    successor_id: str | None = None

    def digest(self) -> str:
        return canonical_digest(
            {
                "sequence": self.sequence,
                "event_id": self.event_id,
                "record_id": self.record_id,
                "previous_state": self.previous_state.value,
                "state": self.state.value,
                "occurred_at": self.occurred_at,
                "reason": self.reason,
                "successor_id": self.successor_id,
            }
        )


@dataclass(frozen=True, slots=True)
class MemoryConflict:
    conflict_id: str
    record_ids: tuple[str, ...]
    reason: str
    recorded_at: str

    def __post_init__(self) -> None:
        if len(self.record_ids) < 2 or len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("a conflict requires at least two distinct records")
        if tuple(sorted(self.record_ids)) != self.record_ids:
            raise ValueError("conflict record ids must be sorted")
        if not self.reason:
            raise ValueError("conflict reason is required")
        _instant(self.recorded_at)


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    """A deterministic, non-authoritative reconstruction input for local memory."""

    entries: tuple[MemoryEntry, ...]
    lifecycle_events: tuple[MemoryLifecycleEvent, ...]
    conflicts: tuple[MemoryConflict, ...]

    def digest(self) -> str:
        return canonical_digest(
            {
                "entries": [
                    {
                        "record": entry.record.to_document(),
                        "access": {
                            "roles": entry.access.roles,
                            "data_scopes": entry.access.data_scopes,
                            "evaluator_visible": entry.access.evaluator_visible,
                        },
                    }
                    for entry in self.entries
                ],
                "lifecycle_events": [
                    {
                        "sequence": event.sequence,
                        "event_id": event.event_id,
                        "record_id": event.record_id,
                        "previous_state": event.previous_state.value,
                        "state": event.state.value,
                        "occurred_at": event.occurred_at,
                        "reason": event.reason,
                        "successor_id": event.successor_id,
                    }
                    for event in self.lifecycle_events
                ],
                "conflicts": [
                    {
                        "conflict_id": conflict.conflict_id,
                        "record_ids": conflict.record_ids,
                        "reason": conflict.reason,
                        "recorded_at": conflict.recorded_at,
                    }
                    for conflict in self.conflicts
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class ConsolidationPolicy:
    """The minimum evidence burden for a deterministic lesson promotion."""

    minimum_independent_episodes: int = 2
    minimum_distinct_contexts: int = 2

    def __post_init__(self) -> None:
        if (
            type(self.minimum_independent_episodes) is not int
            or type(self.minimum_distinct_contexts) is not int
            or self.minimum_independent_episodes < 2
            or self.minimum_distinct_contexts < 2
        ):
            raise ValueError("consolidation minimums must be integers of at least two")


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    mission_id: str
    work_id: str
    role: str
    query: str
    now: str
    data_scopes: tuple[str, ...]
    repository_key: str | None = None
    explicit_pins: tuple[str, ...] = ()
    graph_proximity: Mapping[str, float] | None = None
    prior_usefulness: Mapping[str, float] | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLE_NAMES:
            raise ValueError("retrieval role is not registered")
        if not self.mission_id or not self.work_id:
            raise ValueError("retrieval mission and work are required")
        _instant(self.now)
        if len(set(self.data_scopes)) != len(self.data_scopes):
            raise ValueError("retrieval data scopes must be unique")


@dataclass(frozen=True, slots=True)
class ScoreTerms:
    lexical_overlap: float
    authority_score: float
    evidence_strength: float
    repository_graph_proximity: float
    freshness_score: float
    role_scope_match: float
    prior_usefulness: float
    explicit_pin: float
    unresolved_conflict_penalty: float
    sensitivity_penalty: float
    token_cost_penalty: float

    def __post_init__(self) -> None:
        for value in self.__dataclass_fields__:
            number = getattr(self, value)
            if not isinstance(number, float) or not 0.0 <= number <= 1.0:
                raise ValueError("score terms must be floats in [0, 1]")

    @property
    def score(self) -> float:
        return (
            0.28 * self.lexical_overlap
            + 0.18 * self.authority_score
            + 0.14 * self.evidence_strength
            + 0.12 * self.repository_graph_proximity
            + 0.10 * self.freshness_score
            + 0.08 * self.role_scope_match
            + 0.06 * self.prior_usefulness
            + 0.04 * self.explicit_pin
            - 0.18 * self.unresolved_conflict_penalty
            - 0.10 * self.sensitivity_penalty
            - 0.08 * self.token_cost_penalty
        )


@dataclass(frozen=True, slots=True)
class RankedMemory:
    entry: MemoryEntry
    token_count: int
    terms: ScoreTerms

    @property
    def score(self) -> float:
        return self.terms.score


class MemoryCatalog:
    """An append-only catalog that derives active, accessible facts deterministically."""

    def __init__(self, artifacts: MemoryArtifactStore) -> None:
        self.artifacts = artifacts
        self._entries: dict[str, MemoryEntry] = {}
        self._states: dict[str, MemoryState] = {}
        self._events: list[MemoryLifecycleEvent] = []
        self._conflicts: dict[str, MemoryConflict] = {}
        self._lock = RLock()

    def register(self, record: MemoryRecord, access: MemoryAccess) -> None:
        """Register immutable metadata only after its immutable body is verified."""

        if record.content_ref != self._verified_artifact(record.content_ref):
            raise MemoryDenied("memory record content_ref must name its stored artifact")
        with self._lock:
            existing = self._entries.get(record.record_id)
            entry = MemoryEntry(record, access)
            if existing is not None:
                if existing != entry:
                    raise MemoryDenied("memory record cannot be rewritten")
                return
            self._entries[record.record_id] = entry
            self._states[record.record_id] = record.state

    def transition(
        self,
        record_id: str,
        state: MemoryState,
        *,
        event_id: str,
        occurred_at: str,
        reason: str,
        successor_id: str | None = None,
    ) -> MemoryLifecycleEvent:
        """Append one legal lifecycle fact; the underlying record is never mutated."""

        _instant(occurred_at)
        if not event_id or not reason:
            raise ValueError("lifecycle event id and reason are required")
        with self._lock:
            if record_id not in self._entries:
                raise KeyError(f"unknown memory record: {record_id}")
            previous = self._states[record_id]
            if previous is not MemoryState.ACTIVE or state not in _TERMINAL_STATES:
                raise MemoryDenied("memory lifecycle transition is not legal")
            if state is MemoryState.SUPERSEDED and successor_id not in self._entries:
                raise MemoryDenied("supersession requires a registered successor")
            if any(item.event_id == event_id for item in self._events):
                raise MemoryDenied("memory lifecycle event id is already bound")
            event = MemoryLifecycleEvent(
                len(self._events) + 1,
                event_id,
                record_id,
                previous,
                state,
                occurred_at,
                reason,
                successor_id,
            )
            self._events.append(event)
            self._states[record_id] = state
            return event

    def supersede(
        self, successor: MemoryRecord, access: MemoryAccess, *, now: str, reason: str
    ) -> tuple[MemoryLifecycleEvent, ...]:
        """Add a successor then append facts retiring every declared predecessor."""

        if successor.state is not MemoryState.ACTIVE or not successor.supersedes:
            raise MemoryDenied("an active successor must name prior records")
        with self._lock:
            predecessor_ids = tuple(sorted(successor.supersedes))
            if successor.record_id in predecessor_ids or any(
                record_id not in self._entries
                or self._states[record_id] is not MemoryState.ACTIVE
                for record_id in predecessor_ids
            ):
                raise MemoryDenied("supersession requires active registered predecessors")
            self.register(successor, access)
            events = []
            for record_id in predecessor_ids:
                events.append(
                    self.transition(
                        record_id,
                        MemoryState.SUPERSEDED,
                        event_id=f"memory.superseded:{record_id}:{successor.record_id}",
                        occurred_at=now,
                        reason=reason,
                        successor_id=successor.record_id,
                    )
                )
            return tuple(events)

    def consolidate(
        self,
        lesson: MemoryRecord,
        access: MemoryAccess,
        *,
        supporting_record_ids: Iterable[str],
        independence_keys: Mapping[str, str],
        now: str,
        reason: str,
        policy: ConsolidationPolicy = ConsolidationPolicy(),
    ) -> tuple[MemoryLifecycleEvent, ...]:
        """Promote a lesson only from independently evidenced active episodes."""

        support = tuple(sorted(set(supporting_record_ids)))
        if (
            lesson.memory_class != "lesson"
            or lesson.evaluator_id is None
            or not lesson.outcome_refs
            or lesson.supersedes != support
        ):
            raise MemoryDenied("lesson consolidation lacks a complete independent approval")
        if len(support) < policy.minimum_independent_episodes:
            raise MemoryDenied("lesson consolidation has too few episodes")
        with self._lock:
            if any(
                record_id not in self._entries
                or self._states[record_id] is not MemoryState.ACTIVE
                or self._entries[record_id].record.memory_class != "episode"
                or not self._entries[record_id].record.source_refs
                or not self._entries[record_id].record.outcome_refs
                for record_id in support
            ):
                raise MemoryDenied("lesson consolidation requires active evidenced episodes")
            contexts = {independence_keys.get(record_id, "") for record_id in support}
            if "" in contexts or len(contexts) < policy.minimum_distinct_contexts:
                raise MemoryDenied("lesson consolidation lacks independent contexts")
            return self.supersede(lesson, access, now=now, reason=reason)

    def record_conflict(
        self, record_ids: Iterable[str], *, reason: str, recorded_at: str
    ) -> MemoryConflict:
        """Preserve competing facts instead of silently selecting or overwriting one."""

        identities = tuple(sorted(set(record_ids)))
        with self._lock:
            if any(record_id not in self._entries for record_id in identities):
                raise KeyError("conflict references an unknown memory record")
            conflict_id = "CONFLICT-" + canonical_digest(
                {"records": identities, "reason": reason, "recorded_at": recorded_at}
            ).removeprefix("sha256:")[:20]
            conflict = MemoryConflict(conflict_id, identities, reason, recorded_at)
            existing = self._conflicts.get(conflict_id)
            if existing is not None and existing != conflict:
                raise MemoryDenied("conflict cannot be rewritten")
            self._conflicts[conflict_id] = conflict
            return conflict

    def expire(self, *, now: str) -> tuple[MemoryLifecycleEvent, ...]:
        """Append deterministic expiration facts for active records past valid_to."""

        current = _instant(now)
        events = []
        for record_id in sorted(self._entries):
            record = self._entries[record_id].record
            if (
                self._states[record_id] is MemoryState.ACTIVE
                and record.valid_to is not None
                and _instant(record.valid_to) < current
            ):
                events.append(
                    self.transition(
                        record_id,
                        MemoryState.EXPIRED,
                        event_id=f"memory.expired:{record_id}:{now}",
                        occurred_at=now,
                        reason="validity window elapsed",
                    )
                )
        return tuple(events)

    def lifecycle_events(self) -> tuple[MemoryLifecycleEvent, ...]:
        with self._lock:
            return tuple(self._events)

    def snapshot(self) -> MemorySnapshot:
        """Return a stable rebuild input; it is never a replacement for artifacts."""

        with self._lock:
            return MemorySnapshot(
                tuple(self._entries[record_id] for record_id in sorted(self._entries)),
                tuple(self._events),
                tuple(self._conflicts[conflict_id] for conflict_id in sorted(self._conflicts)),
            )

    @classmethod
    def rebuild(cls, artifacts: MemoryArtifactStore, snapshot: MemorySnapshot) -> MemoryCatalog:
        """Fail closed while replaying immutable local lifecycle and conflict facts."""

        catalog = cls(artifacts)
        for entry in snapshot.entries:
            catalog.register(entry.record, entry.access)
        for event in snapshot.lifecycle_events:
            rebuilt = catalog.transition(
                event.record_id,
                event.state,
                event_id=event.event_id,
                occurred_at=event.occurred_at,
                reason=event.reason,
                successor_id=event.successor_id,
            )
            if rebuilt != event:
                raise MemoryDenied("memory lifecycle reconstruction diverged")
        for conflict in snapshot.conflicts:
            rebuilt = catalog.record_conflict(
                conflict.record_ids,
                reason=conflict.reason,
                recorded_at=conflict.recorded_at,
            )
            if rebuilt != conflict:
                raise MemoryDenied("memory conflict reconstruction diverged")
        return catalog

    def active_records(self, request: RetrievalRequest) -> tuple[MemoryEntry, ...]:
        """Return active authorized records only, in stable record-id order."""

        now = _instant(request.now)
        with self._lock:
            return tuple(
                entry
                for record_id, entry in sorted(self._entries.items())
                if self._eligible(entry, request, now)
            )

    def rank(self, request: RetrievalRequest) -> tuple[RankedMemory, ...]:
        """Score eligible memory with the handoff's deterministic bounded formula."""

        query = normalize_terms(request.query)
        conflicts = self._unresolved_conflict_ids()
        ranked = []
        for entry in self.active_records(request):
            record = entry.record
            text = self.artifacts.get(record.content_ref)
            terms = normalize_terms(" ".join((*record.subject_keys, text)))
            overlap = len(query & terms) / len(query) if query else 0.0
            ranked.append(
                RankedMemory(
                    entry,
                    estimate_tokens(text),
                    ScoreTerms(
                        float(overlap),
                        _authority_score(record.authority_level),
                        min(1.0, len(record.source_refs) / 3.0),
                        _bounded_lookup(request.graph_proximity, record.record_id),
                        1.0,
                        1.0,
                        _bounded_lookup(request.prior_usefulness, record.record_id),
                        1.0 if record.record_id in request.explicit_pins else 0.0,
                        1.0 if record.record_id in conflicts else 0.0,
                        0.0,
                        min(1.0, estimate_tokens(text) / 4096.0),
                    ),
                )
            )
        return tuple(sorted(ranked, key=lambda item: (-item.score, item.entry.record.record_id)))

    def conflicts_for(self, record_ids: Iterable[str]) -> tuple[str, ...]:
        wanted = set(record_ids)
        with self._lock:
            return tuple(
                conflict.conflict_id
                for _, conflict in sorted(self._conflicts.items())
                if wanted.intersection(conflict.record_ids)
            )

    def _verified_artifact(self, digest: str) -> str:
        self.artifacts.get(digest)
        return digest

    def _eligible(self, entry: MemoryEntry, request: RetrievalRequest, now: datetime) -> bool:
        record = entry.record
        if self._states[record.record_id] is not MemoryState.ACTIVE:
            return False
        if _instant(record.available_at) > now or _instant(record.valid_from) > now:
            return False
        if record.valid_to is not None and _instant(record.valid_to) < now:
            return False
        if request.role not in entry.access.roles:
            return False
        if not set(entry.access.data_scopes).issubset(request.data_scopes):
            return False
        if record.scope == "mission" and request.mission_id not in record.subject_keys:
            return False
        if record.scope == "work_item" and request.work_id not in record.subject_keys:
            return False
        if record.scope == "role" and request.role not in record.subject_keys:
            return False
        if record.scope == "repository" and request.repository_key not in record.subject_keys:
            return False
        return True

    def _unresolved_conflict_ids(self) -> frozenset[str]:
        return frozenset(record_id for conflict in self._conflicts.values() for record_id in conflict.record_ids)


def _authority_score(level: str) -> float:
    return {"unverified": 0.0, "reported": 0.25, "internal": 0.5, "verified": 0.75, "constitutional": 1.0}.get(level, 0.0)


def _bounded_lookup(values: Mapping[str, float] | None, key: str) -> float:
    value = 0.0 if values is None else values.get(key, 0.0)
    if not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
        raise ValueError("retrieval component values must be in [0, 1]")
    return float(value)
