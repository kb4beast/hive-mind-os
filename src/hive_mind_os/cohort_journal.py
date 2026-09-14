"""Tamper-evident, append-only persistence for cohort execution.

The journal deliberately stores lifecycle facts rather than mutable snapshots.
Every event is a canonical JSON document linked to the digest of its predecessor.
A resumed runtime must replay the complete chain before trusting any result.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from .brain_kernel.canonical import canonical_bytes, canonical_digest


class CohortJournalError(ValueError):
    """The cohort journal is corrupt or an append violates its contract."""


class CohortJournalEventKind(StrEnum):
    KICKOFF = "kickoff"
    DISPATCH = "dispatch"
    PACKAGE_RESULT = "package_result"
    CONVERGENCE = "convergence"
    VERIFICATION = "verification"
    REPAIR_ATTEMPT = "repair_attempt"
    REPAIR_RESULT = "repair_result"
    TERMINAL_EVIDENCE = "terminal_evidence"
    RUN_COMPLETED = "run_completed"


@dataclass(frozen=True, slots=True)
class CohortJournalEvent:
    sequence: int
    run_id: str
    kind: CohortJournalEventKind
    payload: Mapping[str, Any]
    recorded_at: str
    previous_digest: str | None
    event_digest: str


class CohortJournalStore(Protocol):
    """Minimal persistence interface accepted by :class:`CohortRuntime`."""

    def events(self, run_id: str) -> tuple[CohortJournalEvent, ...]: ...

    def append(
        self,
        run_id: str,
        kind: CohortJournalEventKind,
        payload: Mapping[str, Any],
    ) -> CohortJournalEvent: ...


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _canonical_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        document = json.loads(canonical_bytes(dict(value)))
    except (TypeError, ValueError) as error:
        raise CohortJournalError("journal payload must be canonical JSON") from error
    if type(document) is not dict:
        raise CohortJournalError("journal payload must be an object")
    return document


class FileCohortJournalStore:
    """Filesystem-backed cohort journal with atomic, append-only publication.

    Each run receives a content-addressed directory, so caller-provided run ids
    can never escape the configured root. Events are immutable files published
    with an atomic hard-link and verified in full on every read or append.
    """

    SCHEMA_VERSION = 1

    def __init__(
        self,
        root: str | Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.root.is_dir():
            raise CohortJournalError("cohort journal root must be a directory")
        self._clock = clock
        self._lock = threading.RLock()
        self._seen: dict[str, tuple[int, str]] = {}

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if type(run_id) is not str or not run_id.strip():
            raise CohortJournalError("cohort run id must be nonempty")

    def _run_root(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        suffix = canonical_digest({"run_id": run_id}).removeprefix("sha256:")
        return self.root / suffix

    @staticmethod
    def _body(document: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in document.items() if key != "event_digest"}

    def _read(self, run_id: str) -> list[CohortJournalEvent]:
        run_root = self._run_root(run_id)
        if not run_root.exists():
            return []
        if not run_root.is_dir():
            raise CohortJournalError("cohort journal run path is not a directory")
        records: list[CohortJournalEvent] = []
        previous: str | None = None
        paths = sorted(run_root.glob("event-*.json"))
        try:
            for sequence, path in enumerate(paths, 1):
                raw = path.read_bytes()
                document = json.loads(raw)
                expected_fields = {
                    "schema_version",
                    "sequence",
                    "run_id",
                    "kind",
                    "payload",
                    "recorded_at",
                    "previous_digest",
                    "event_digest",
                }
                if type(document) is not dict or set(document) != expected_fields:
                    raise CohortJournalError("invalid cohort journal event fields")
                if (
                    path.name != f"event-{sequence:08d}.json"
                    or document["schema_version"] != self.SCHEMA_VERSION
                    or type(document["sequence"]) is not int
                    or document["sequence"] != sequence
                    or document["run_id"] != run_id
                    or document["previous_digest"] != previous
                    or type(document["payload"]) is not dict
                    or type(document["recorded_at"]) is not str
                    or not document["recorded_at"]
                    or document["event_digest"]
                    != canonical_digest(self._body(document))
                    or raw != canonical_bytes(document) + b"\n"
                ):
                    raise CohortJournalError("cohort journal digest chain mismatch")
                kind = CohortJournalEventKind(document["kind"])
                frozen = _freeze(document["payload"])
                assert isinstance(frozen, Mapping)
                record = CohortJournalEvent(
                    sequence,
                    run_id,
                    kind,
                    frozen,
                    document["recorded_at"],
                    previous,
                    document["event_digest"],
                )
                self._validate_transition(records, kind, document["payload"])
                records.append(record)
                previous = document["event_digest"]
        except (
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            if isinstance(error, CohortJournalError):
                raise
            raise CohortJournalError(
                "cohort journal cannot be safely replayed"
            ) from error
        seen = self._seen.get(run_id)
        if seen is not None:
            count, digest = seen
            if len(records) < count or records[count - 1].event_digest != digest:
                raise CohortJournalError("previously observed cohort history changed")
        if records:
            self._seen[run_id] = (len(records), records[-1].event_digest)
        return records

    @staticmethod
    def _validate_transition(
        records: list[CohortJournalEvent],
        kind: CohortJournalEventKind,
        payload: Mapping[str, Any],
    ) -> None:
        if not records:
            if kind is not CohortJournalEventKind.KICKOFF:
                raise CohortJournalError("cohort journal must begin with kickoff")
            return
        if kind is CohortJournalEventKind.KICKOFF:
            raise CohortJournalError("cohort kickoff is immutable")
        if records[-1].kind is CohortJournalEventKind.RUN_COMPLETED:
            raise CohortJournalError("completed cohort journal is terminal")
        if kind is CohortJournalEventKind.RUN_COMPLETED and any(
            item.kind is CohortJournalEventKind.RUN_COMPLETED for item in records
        ):
            raise CohortJournalError("cohort completion may be recorded only once")
        if kind is CohortJournalEventKind.REPAIR_ATTEMPT and any(
            item.kind is CohortJournalEventKind.REPAIR_ATTEMPT for item in records
        ):
            raise CohortJournalError("cohort repair may be attempted only once")
        if kind is CohortJournalEventKind.REPAIR_RESULT:
            if not any(
                item.kind is CohortJournalEventKind.REPAIR_ATTEMPT for item in records
            ):
                raise CohortJournalError("repair result requires a repair attempt")
            if any(
                item.kind is CohortJournalEventKind.REPAIR_RESULT for item in records
            ):
                raise CohortJournalError(
                    "cohort repair result may be recorded only once"
                )
        if kind is CohortJournalEventKind.PACKAGE_RESULT:
            package_id = payload.get("package_id")
            if type(package_id) is not str or not package_id:
                raise CohortJournalError("package result requires a package id")
            if any(
                item.kind is CohortJournalEventKind.PACKAGE_RESULT
                and item.payload.get("package_id") == package_id
                for item in records
            ):
                raise CohortJournalError(
                    f"package {package_id} completion may be recorded only once"
                )

    def events(self, run_id: str) -> tuple[CohortJournalEvent, ...]:
        with self._lock:
            return tuple(self._read(run_id))

    def append(
        self,
        run_id: str,
        kind: CohortJournalEventKind,
        payload: Mapping[str, Any],
    ) -> CohortJournalEvent:
        self._validate_run_id(run_id)
        if type(kind) is not CohortJournalEventKind:
            raise CohortJournalError("cohort journal event kind must be typed")
        body_payload = _canonical_mapping(payload)
        with self._lock:
            records = self._read(run_id)
            self._validate_transition(records, kind, body_payload)
            run_root = self._run_root(run_id)
            run_root.mkdir(parents=True, exist_ok=True)
            previous = records[-1].event_digest if records else None
            body = {
                "schema_version": self.SCHEMA_VERSION,
                "sequence": len(records) + 1,
                "run_id": run_id,
                "kind": kind.value,
                "payload": body_payload,
                "recorded_at": self._clock().astimezone(timezone.utc).isoformat(),
                "previous_digest": previous,
            }
            document = {**body, "event_digest": canonical_digest(body)}
            destination = run_root / f"event-{len(records) + 1:08d}.json"
            temporary: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=run_root, prefix=".pending-", delete=False
                ) as handle:
                    temporary = Path(handle.name)
                    handle.write(canonical_bytes(document) + b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, destination)
            except OSError as error:
                raise CohortJournalError("cohort journal append failed") from error
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
            self._seen[run_id] = (len(records) + 1, document["event_digest"])
            frozen = _freeze(body_payload)
            assert isinstance(frozen, Mapping)
            return CohortJournalEvent(
                len(records) + 1,
                run_id,
                kind,
                frozen,
                body["recorded_at"],
                previous,
                document["event_digest"],
            )


__all__ = [
    "CohortJournalError",
    "CohortJournalEvent",
    "CohortJournalEventKind",
    "CohortJournalStore",
    "FileCohortJournalStore",
]
