"""Durable execution-local supervision from one DAG frontier to fixed point.

The supervisor deliberately knows nothing about ``ControlPlane`` or any host
adapter.  Its callers authenticate the explicit execution directory and inject
one typed step function.  This keeps orchestration policy outside this module
while making the dangerous part -- repetition, crash recovery, fencing, and the
definition of success -- deterministic and fail closed.

One invocation performs only immediately available progress.  ``ROUND_COMPLETE``
advances to a new frontier; every waiting or adverse disposition returns at once.
Consequently a waiting controller cannot create a busy loop.  Only a controller
supplied, complete zero-activity ``PLAN_QUIESCENT`` observation is successful.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import stat
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any

SCHEMA_VERSION = 1
EVENT_KIND = "hive-mind-execution-supervisor-event-v1"
TRANSACTION_KIND = "hive-mind-execution-supervisor-transaction-v1"
ATTEMPT_KIND = "hive-mind-execution-supervisor-attempt-v1"
RECOVERY_KIND = "hive-mind-execution-supervisor-torn-tail-recovery-v1"
JOURNAL_NAME = "execution-supervisor.jsonl"
LOCK_NAME = "execution-supervisor.lock"
RECOVERY_DIRECTORY = "execution-supervisor-recovery"

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_NAMESPACE = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "execution_id",
        "execution_namespace",
        "plan_fingerprint",
        "state",
        "transaction_id",
        "previous_event_id",
        "recorded_at",
        "payload",
        "event_id",
    }
)


class SupervisorError(RuntimeError):
    """The supervisor cannot continue without weakening its contract."""


class SupervisorAuthenticationError(SupervisorError):
    """The explicit execution authority could not be authenticated."""


class SupervisorLeaseHeld(SupervisorError):
    """Another supervisor owns the execution-local lease."""


class SupervisorJournalError(SupervisorError):
    """The append-only supervisor journal is invalid."""


class SupervisorContractError(SupervisorError):
    """An injected step violated the typed state-machine contract."""


class SupervisorRecoveryError(SupervisorError):
    """An explicit recovery request was unsafe or inapplicable."""


class TornJournalTail(SupervisorJournalError):
    """A final unterminated journal record must be preserved before repair."""

    def __init__(
        self,
        message: str,
        *,
        valid_prefix: bytes,
        tail: bytes,
        events: tuple[dict[str, Any], ...],
    ) -> None:
        super().__init__(message)
        self.valid_prefix = valid_prefix
        self.tail = tail
        self.events = events
        self.tail_digest = _bytes_digest(tail)


class StepDisposition(str, Enum):
    WAITING = "WAITING"
    WAITING_FOR_HOST = "WAITING_FOR_HOST"
    BLOCKED = "BLOCKED"
    ROUND_COMPLETE = "ROUND_COMPLETE"
    PLAN_QUIESCENT = "PLAN_QUIESCENT"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class HostCapability(str, Enum):
    """Whether this process can actually launch work without an attended host."""

    AUTHENTICATED_LIFECYCLE = "AUTHENTICATED_LIFECYCLE"
    AUTHENTICATED_OBSERVER = "AUTHENTICATED_OBSERVER"
    ATTENDED_CARD_ONLY = "ATTENDED_CARD_ONLY"
    NO_LAUNCH = "NO_LAUNCH"


@dataclass(frozen=True, slots=True)
class WaitCondition:
    """A content-addressed wake condition, never an invitation to poll."""

    wake_at: datetime | None = None
    observation_fingerprint: str | None = None
    resume_token: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "wake_at": _format_time(self.wake_at) if self.wake_at is not None else None,
            "observation_fingerprint": self.observation_fingerprint,
            "resume_token": self.resume_token,
        }


@dataclass(frozen=True, slots=True)
class WaitObservationVerificationRequest:
    """Narrow authority for proving that a durable wait observation changed."""

    execution_dir: Path
    execution_id: str
    execution_namespace: str
    plan_fingerprint: str
    frontier_id: str
    stored_observation_fingerprint: str
    supplied_observation_fingerprint: str
    resume_token: str


@dataclass(frozen=True, slots=True)
class FixedPointVerificationRequest:
    execution_dir: Path
    execution_id: str
    execution_namespace: str
    plan_fingerprint: str
    initial_frontier_id: str
    current_frontier_id: str
    terminal_observation_id: str


@dataclass(frozen=True, slots=True)
class FixedPointEvidence:
    """The controller's complete, exact observation of fixed-point obligations."""

    evidence_id: str
    execution_id: str
    execution_namespace: str
    plan_fingerprint: str
    initial_frontier_id: str
    current_frontier_id: str
    terminal_observation_id: str
    release_authority_id: str
    controller_observation_id: str
    dag_complete: bool
    active_claims: int
    active_launches: int
    active_sidecars: int
    active_validation_leases: int
    active_publication_transactions: int
    active_global_reservations: int
    host_lifecycle_authenticated: bool
    active_host_threads: int
    active_host_turns: int
    unobserved_host_lifecycle_items: int

    @classmethod
    def create(
        cls,
        *,
        execution_id: str,
        execution_namespace: str,
        plan_fingerprint: str,
        initial_frontier_id: str,
        current_frontier_id: str,
        terminal_observation_id: str,
        release_authority_id: str,
        controller_observation_id: str,
        dag_complete: bool,
        active_claims: int,
        active_launches: int,
        active_sidecars: int,
        active_validation_leases: int,
        active_publication_transactions: int,
        active_global_reservations: int,
        host_lifecycle_authenticated: bool,
        active_host_threads: int,
        active_host_turns: int,
        unobserved_host_lifecycle_items: int,
    ) -> FixedPointEvidence:
        material: dict[str, object] = {
            "execution_id": execution_id,
            "execution_namespace": execution_namespace,
            "plan_fingerprint": plan_fingerprint,
            "initial_frontier_id": initial_frontier_id,
            "current_frontier_id": current_frontier_id,
            "terminal_observation_id": terminal_observation_id,
            "release_authority_id": release_authority_id,
            "controller_observation_id": controller_observation_id,
            "dag_complete": dag_complete,
            "active_claims": active_claims,
            "active_launches": active_launches,
            "active_sidecars": active_sidecars,
            "active_validation_leases": active_validation_leases,
            "active_publication_transactions": active_publication_transactions,
            "active_global_reservations": active_global_reservations,
            "host_lifecycle_authenticated": host_lifecycle_authenticated,
            "active_host_threads": active_host_threads,
            "active_host_turns": active_host_turns,
            "unobserved_host_lifecycle_items": unobserved_host_lifecycle_items,
        }
        return cls(evidence_id=_digest(material), **material)  # type: ignore[arg-type]

    def to_payload(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "execution_id": self.execution_id,
            "execution_namespace": self.execution_namespace,
            "plan_fingerprint": self.plan_fingerprint,
            "initial_frontier_id": self.initial_frontier_id,
            "current_frontier_id": self.current_frontier_id,
            "terminal_observation_id": self.terminal_observation_id,
            "release_authority_id": self.release_authority_id,
            "controller_observation_id": self.controller_observation_id,
            "dag_complete": self.dag_complete,
            "active_claims": self.active_claims,
            "active_launches": self.active_launches,
            "active_sidecars": self.active_sidecars,
            "active_validation_leases": self.active_validation_leases,
            "active_publication_transactions": self.active_publication_transactions,
            "active_global_reservations": self.active_global_reservations,
            "host_lifecycle_authenticated": self.host_lifecycle_authenticated,
            "active_host_threads": self.active_host_threads,
            "active_host_turns": self.active_host_turns,
            "unobserved_host_lifecycle_items": self.unobserved_host_lifecycle_items,
        }


@dataclass(frozen=True, slots=True)
class StepContext:
    execution_dir: Path
    execution_id: str
    execution_namespace: str
    plan_fingerprint: str
    initial_frontier_id: str
    epoch: int
    transaction_id: str
    attempt_id: str
    frontier_id: str
    completed_frontiers: tuple[str, ...]
    host_capability: HostCapability


@dataclass(frozen=True, slots=True)
class ObserverContext:
    """Read-only terminal-observation context with no admission transaction."""

    execution_dir: Path
    execution_id: str
    execution_namespace: str
    plan_fingerprint: str
    initial_frontier_id: str
    frontier_id: str
    completed_frontiers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StepResult:
    disposition: StepDisposition
    detail: str
    next_frontier_id: str | None = None
    fixed_point_evidence: FixedPointEvidence | None = None
    wait_condition: WaitCondition | None = None
    terminal_observation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ObserverResult:
    """A terminal observer can wait, stop, or nominate fixed-point verification."""

    disposition: StepDisposition
    detail: str
    wait_condition: WaitCondition | None = None
    terminal_observation_id: str | None = None


@dataclass(frozen=True, slots=True)
class SupervisorResult:
    disposition: StepDisposition
    successful: bool
    detail: str
    epoch: int
    transaction_id: str
    frontier_id: str
    completed_frontiers: tuple[str, ...]
    journal_event_id: str
    fixed_point_evidence: FixedPointEvidence | None = None
    wait_condition: WaitCondition | None = None
    unknown_attempt_id: str | None = None


@dataclass(frozen=True, slots=True)
class TornTailRecoveryReceipt:
    epoch: int
    transaction_id: str
    tail_digest: str
    tail_bytes: int
    evidence_path: Path
    journal_event_id: str


Authenticator = Callable[[Path, str, str, str], str | Path]
StepCallback = Callable[[StepContext], StepResult]
ObserverCallback = Callable[[ObserverContext], ObserverResult]
FixedPointVerifier = Callable[[FixedPointVerificationRequest], FixedPointEvidence]
WaitObservationVerifier = Callable[[WaitObservationVerificationRequest], str]
AfterAppend = Callable[[Mapping[str, object]], None]


@dataclass(slots=True)
class _Replay:
    events: tuple[dict[str, Any], ...]
    last_event_id: str | None
    max_epoch: int
    current_frontier: str | None
    initial_frontier: str | None
    completed_frontiers: tuple[str, ...]
    active_transaction_id: str | None
    transaction_closed: bool
    pending_attempts: tuple[tuple[str, str, str, HostCapability], ...]
    quiescent_evidence: FixedPointEvidence | None
    latest_disposition: StepDisposition | None
    durable_wait: WaitCondition | None
    durable_wait_event: dict[str, Any] | None
    durable_wait_host_capability: HostCapability | None
    unknown_recovery_event: dict[str, Any] | None


def _canonical(value: Mapping[str, object]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SupervisorJournalError(
            "journal material is not canonical JSON"
        ) from error


def _digest(value: Mapping[str, object]) -> str:
    return "sha256:" + sha256(_canonical(value)).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"non-finite JSON value {value!r}")


def _parse_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value!r}")
    return parsed


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
            parse_float=_parse_float,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise SupervisorJournalError(f"{label} is malformed") from error
    if not isinstance(value, dict):
        raise SupervisorJournalError(f"{label} must be a JSON object")
    return value


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _reject_link_chain(path: Path, label: str) -> None:
    for component in reversed((path, *path.parents)):
        if _is_link_like(component):
            raise SupervisorAuthenticationError(f"{label} contains a link component")


def _fsync_directory(directory: Path) -> None:
    """Durably order a directory entry without following a replaced link.

    POSIX exposes directories through ordinary file descriptors.  Windows needs
    a backup-semantics handle with write authority before ``FlushFileBuffers``
    will flush directory metadata.  In both cases the opened object itself is
    checked after open, closing the usual check-then-open reparse-point race.
    """

    if any(_is_link_like(component) for component in (directory, *directory.parents)):
        raise OSError(f"directory sync target contains a link: {directory}")
    if not directory.is_dir():
        raise OSError(f"directory sync target is not a regular directory: {directory}")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class _FileAttributeTagInfo(ctypes.Structure):
            _fields_ = [
                ("FileAttributes", wintypes.DWORD),
                ("ReparseTag", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE
        get_information = kernel32.GetFileInformationByHandleEx
        get_information.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            wintypes.LPVOID,
            wintypes.DWORD,
        ]
        get_information.restype = wintypes.BOOL
        flush = kernel32.FlushFileBuffers
        flush.argtypes = [wintypes.HANDLE]
        flush.restype = wintypes.BOOL
        close = kernel32.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        close.restype = wintypes.BOOL

        generic_write = 0x40000000
        share_read_write_delete = 0x00000001 | 0x00000002 | 0x00000004
        open_existing = 3
        backup_semantics = 0x02000000
        open_reparse_point = 0x00200000
        file_attribute_directory = 0x00000010
        file_attribute_reparse_point = 0x00000400
        file_attribute_tag_info = 9
        invalid_handle = ctypes.c_void_p(-1).value
        handle = create_file(
            str(directory),
            generic_write,
            share_read_write_delete,
            None,
            open_existing,
            backup_semantics | open_reparse_point,
            None,
        )
        if handle == invalid_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            information = _FileAttributeTagInfo()
            if not get_information(
                handle,
                file_attribute_tag_info,
                ctypes.byref(information),
                ctypes.sizeof(information),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if (
                not information.FileAttributes & file_attribute_directory
                or information.FileAttributes & file_attribute_reparse_point
            ):
                raise OSError("directory sync handle is not a non-link directory")
            if not flush(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            close(handle)
        return

    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(directory, flags)
    try:
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("directory sync handle is not a directory")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_text(value: object, label: str, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise SupervisorContractError(f"{label} is invalid")
    return value


def _require_frontier(value: object, label: str = "frontier id") -> str:
    return _require_text(value, label, maximum=256)


def _format_time(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise SupervisorContractError("supervisor clock must return an aware datetime")
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _validate_time(value: object) -> str:
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise SupervisorJournalError("journal timestamp is not canonical UTC")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise SupervisorJournalError("journal timestamp is invalid") from error
    if _format_time(parsed) != value:
        raise SupervisorJournalError("journal timestamp is not canonical UTC")
    return value


def _parse_time(value: str) -> datetime:
    _validate_time(value)
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def _validate_count(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise SupervisorContractError(f"{label} must be a non-negative integer")
    return value


def _validate_wait_condition(value: object) -> WaitCondition:
    if type(value) is not WaitCondition:
        raise SupervisorContractError("waiting requires a typed wake condition")
    if value.wake_at is not None:
        _format_time(value.wake_at)
    pair = (value.observation_fingerprint, value.resume_token)
    if (pair[0] is None) != (pair[1] is None):
        raise SupervisorContractError(
            "wait observation fingerprint and resume token must be supplied together"
        )
    for item, label in zip(pair, ("wait observation fingerprint", "wait resume token")):
        if item is not None and (
            type(item) is not str or _DIGEST.fullmatch(item) is None
        ):
            raise SupervisorContractError(f"{label} is invalid")
    if value.wake_at is None and pair[0] is None:
        raise SupervisorContractError(
            "waiting requires wake_at or an observation fingerprint and resume token"
        )
    return value


def _wait_from_payload(value: object) -> WaitCondition:
    if not isinstance(value, dict) or set(value) != {
        "wake_at",
        "observation_fingerprint",
        "resume_token",
    }:
        raise SupervisorJournalError("wait condition schema is not exact")
    raw_wake = value.get("wake_at")
    if raw_wake is not None and type(raw_wake) is not str:
        raise SupervisorJournalError("wait wake_at is invalid")
    condition = WaitCondition(
        wake_at=_parse_time(raw_wake) if isinstance(raw_wake, str) else None,
        observation_fingerprint=value.get("observation_fingerprint"),
        resume_token=value.get("resume_token"),
    )
    try:
        return _validate_wait_condition(condition)
    except SupervisorContractError as error:
        raise SupervisorJournalError(str(error)) from error


def _validate_evidence(
    evidence: object,
    *,
    require_quiescent: bool,
    request: FixedPointVerificationRequest | None = None,
) -> FixedPointEvidence:
    if type(evidence) is not FixedPointEvidence:
        raise SupervisorContractError(
            "PLAN_QUIESCENT requires typed complete fixed-point evidence"
        )
    payload = evidence.to_payload()
    evidence_id = payload.pop("evidence_id")
    if evidence_id != _digest(payload):
        raise SupervisorContractError("fixed-point evidence digest is invalid")
    for field in (
        "execution_id",
        "plan_fingerprint",
        "terminal_observation_id",
        "release_authority_id",
        "controller_observation_id",
    ):
        field_value = getattr(evidence, field, None)
        if type(field_value) is not str or _DIGEST.fullmatch(field_value) is None:
            raise SupervisorContractError(f"fixed-point {field} is invalid")
    if (
        type(evidence.execution_namespace) is not str
        or _NAMESPACE.fullmatch(evidence.execution_namespace) is None
    ):
        raise SupervisorContractError("fixed-point execution namespace is invalid")
    _require_frontier(evidence.initial_frontier_id, "fixed-point initial frontier")
    _require_frontier(evidence.current_frontier_id, "fixed-point current frontier")
    if request is not None and (
        evidence.execution_id != request.execution_id
        or evidence.execution_namespace != request.execution_namespace
        or evidence.plan_fingerprint != request.plan_fingerprint
        or evidence.initial_frontier_id != request.initial_frontier_id
        or evidence.current_frontier_id != request.current_frontier_id
        or evidence.terminal_observation_id != request.terminal_observation_id
    ):
        raise SupervisorContractError(
            "fixed-point evidence is not bound to this execution and frontier"
        )
    if type(evidence.dag_complete) is not bool:
        raise SupervisorContractError("DAG completion evidence must be boolean")
    counts = (
        _validate_count(evidence.active_claims, "active claims"),
        _validate_count(evidence.active_launches, "active launches"),
        _validate_count(evidence.active_sidecars, "active sidecars"),
        _validate_count(evidence.active_validation_leases, "active validation leases"),
        _validate_count(
            evidence.active_publication_transactions,
            "active publication transactions",
        ),
        _validate_count(
            evidence.active_global_reservations, "active global reservations"
        ),
        _validate_count(evidence.active_host_threads, "active host threads"),
        _validate_count(evidence.active_host_turns, "active host turns"),
        _validate_count(
            evidence.unobserved_host_lifecycle_items,
            "unobserved host lifecycle items",
        ),
    )
    if type(evidence.host_lifecycle_authenticated) is not bool:
        raise SupervisorContractError(
            "host lifecycle authentication evidence must be boolean"
        )
    if require_quiescent and (
        evidence.dag_complete is not True
        or evidence.host_lifecycle_authenticated is not True
        or any(counts)
    ):
        raise SupervisorContractError(
            "false quiescence: DAG and authenticated host lifecycle must be complete "
            "and every activity count must be zero"
        )
    return evidence


def _evidence_from_payload(value: object) -> FixedPointEvidence:
    fields = {
        "evidence_id",
        "execution_id",
        "execution_namespace",
        "plan_fingerprint",
        "initial_frontier_id",
        "current_frontier_id",
        "terminal_observation_id",
        "release_authority_id",
        "controller_observation_id",
        "dag_complete",
        "active_claims",
        "active_launches",
        "active_sidecars",
        "active_validation_leases",
        "active_publication_transactions",
        "active_global_reservations",
        "host_lifecycle_authenticated",
        "active_host_threads",
        "active_host_turns",
        "unobserved_host_lifecycle_items",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise SupervisorJournalError("fixed-point evidence schema is not exact")
    try:
        evidence = FixedPointEvidence(**value)
        return _validate_evidence(evidence, require_quiescent=True)
    except SupervisorContractError as error:
        raise SupervisorJournalError(str(error)) from error


def _payload_fields(state: str) -> frozenset[str]:
    if state == "LEASE_ACQUIRED":
        return frozenset(
            {"epoch", "frontier_id", "resumed", "previous_transaction_closed"}
        )
    if state == "STEP_STARTED":
        return frozenset({"epoch", "frontier_id", "attempt_id", "host_capability"})
    if state in {
        StepDisposition.WAITING.value,
        StepDisposition.WAITING_FOR_HOST.value,
    }:
        return frozenset(
            {"epoch", "frontier_id", "attempt_id", "detail", "wait_condition"}
        )
    if state in {
        StepDisposition.BLOCKED.value,
        StepDisposition.RECOVERY_REQUIRED.value,
    }:
        return frozenset({"epoch", "frontier_id", "attempt_id", "detail"})
    if state == StepDisposition.ROUND_COMPLETE.value:
        return frozenset(
            {"epoch", "frontier_id", "attempt_id", "detail", "next_frontier_id"}
        )
    if state == StepDisposition.PLAN_QUIESCENT.value:
        return frozenset(
            {"epoch", "frontier_id", "attempt_id", "detail", "fixed_point_evidence"}
        )
    if state == "TORN_TAIL_RECOVERED":
        return frozenset(
            {
                "epoch",
                "actor",
                "reason",
                "tail_digest",
                "tail_bytes",
                "evidence_file",
            }
        )
    if state == "UNKNOWN_ATTEMPT_RECOVERY_REQUIRED":
        return frozenset({"epoch", "frontier_id", "attempt_id", "detail"})
    if state == "UNKNOWN_ATTEMPT_RECONCILED":
        return frozenset(
            {
                "epoch",
                "frontier_id",
                "attempt_id",
                "observation_id",
                "disposition",
                "detail",
                "next_frontier_id",
                "fixed_point_evidence",
                "wait_condition",
            }
        )
    if state == "LEASE_RELEASED":
        return frozenset({"epoch", "disposition"})
    raise SupervisorJournalError(f"unknown supervisor journal state {state!r}")


def _transaction_id(
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    epoch: int,
    previous_event_id: str | None,
) -> str:
    return _digest(
        {
            "kind": TRANSACTION_KIND,
            "execution_id": execution_id,
            "execution_namespace": execution_namespace,
            "plan_fingerprint": plan_fingerprint,
            "epoch": epoch,
            "previous_event_id": previous_event_id,
        }
    )


def _attempt_id(transaction_id: str, plan_fingerprint: str, frontier_id: str) -> str:
    return _digest(
        {
            "kind": ATTEMPT_KIND,
            "transaction_id": transaction_id,
            "plan_fingerprint": plan_fingerprint,
            "frontier_id": frontier_id,
        }
    )


def _validate_event_envelope(
    event: dict[str, Any],
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    previous_event_id: str | None,
) -> None:
    if set(event) != _EVENT_FIELDS:
        raise SupervisorJournalError("journal event does not match the exact schema")
    material = dict(event)
    event_id = material.pop("event_id", None)
    if (
        event.get("schema_version") != SCHEMA_VERSION
        or event.get("kind") != EVENT_KIND
        or event.get("execution_id") != execution_id
        or event.get("execution_namespace") != execution_namespace
        or event.get("plan_fingerprint") != plan_fingerprint
        or event.get("previous_event_id") != previous_event_id
        or not isinstance(event_id, str)
        or event_id != _digest(material)
    ):
        raise SupervisorJournalError("journal event identity or hash chain is invalid")
    if _DIGEST.fullmatch(str(event.get("transaction_id", ""))) is None:
        raise SupervisorJournalError("journal transaction id is invalid")
    _validate_time(event.get("recorded_at"))
    state = event.get("state")
    if type(state) is not str:
        raise SupervisorJournalError("journal state is invalid")
    payload = event.get("payload")
    if not isinstance(payload, dict) or set(payload) != _payload_fields(state):
        raise SupervisorJournalError(
            f"journal payload schema for {state!r} is not exact"
        )


def _replay_events(
    events: tuple[dict[str, Any], ...],
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
) -> _Replay:
    if type(plan_fingerprint) is not str or _DIGEST.fullmatch(plan_fingerprint) is None:
        raise SupervisorJournalError("journal plan fingerprint is invalid")
    previous: str | None = None
    max_epoch = 0
    current_frontier: str | None = None
    initial_frontier: str | None = None
    completed: list[str] = []
    active_transaction: str | None = None
    transaction_closed = True
    transaction_disposition: StepDisposition | None = None
    current_attempt: tuple[str, str, str, HostCapability] | None = None
    current_capability: HostCapability | None = None
    pending: list[tuple[str, str, str, HostCapability]] = []
    evidence: FixedPointEvidence | None = None
    latest: StepDisposition | None = None
    durable_wait: WaitCondition | None = None
    durable_wait_event: dict[str, Any] | None = None
    durable_wait_capability: HostCapability | None = None
    unknown_recovery_event: dict[str, Any] | None = None

    for event in events:
        _validate_event_envelope(
            event,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            previous_event_id=previous,
        )
        state = str(event["state"])
        payload = event["payload"]
        assert isinstance(payload, dict)
        epoch = payload.get("epoch")
        if type(epoch) is not int or epoch < 1:
            raise SupervisorJournalError("journal epoch must be a positive integer")
        transaction_id = str(event["transaction_id"])

        if state == "LEASE_ACQUIRED":
            if epoch != max_epoch + 1:
                raise SupervisorJournalError(
                    "supervisor epochs are not strictly monotonic"
                )
            expected_transaction = _transaction_id(
                execution_id,
                execution_namespace,
                plan_fingerprint,
                epoch,
                previous,
            )
            if transaction_id != expected_transaction:
                raise SupervisorJournalError(
                    "supervisor transaction id is noncanonical"
                )
            frontier = _require_frontier_from_journal(payload.get("frontier_id"))
            if initial_frontier is None:
                initial_frontier = frontier
                current_frontier = frontier
            elif current_frontier != frontier:
                raise SupervisorJournalError(
                    "lease acquired for the wrong DAG frontier"
                )
            expected_closed = active_transaction is None or transaction_closed
            if type(payload.get("resumed")) is not bool or payload["resumed"] != bool(
                previous is not None
            ):
                raise SupervisorJournalError("lease resume marker is invalid")
            if (
                type(payload.get("previous_transaction_closed")) is not bool
                or payload["previous_transaction_closed"] != expected_closed
            ):
                raise SupervisorJournalError("lease predecessor marker is invalid")
            max_epoch = epoch
            active_transaction = transaction_id
            transaction_closed = False
            transaction_disposition = None
            current_attempt = None
            current_capability = None
            durable_wait = None
            durable_wait_event = None
            durable_wait_capability = None
        elif active_transaction is None or transaction_id != active_transaction:
            raise SupervisorJournalError("journal event is outside its active lease")
        elif transaction_closed:
            raise SupervisorJournalError("journal event follows a released lease")
        elif epoch != max_epoch:
            raise SupervisorJournalError("journal event epoch is stale or ambiguous")
        elif state == "STEP_STARTED":
            if current_attempt is not None:
                raise SupervisorJournalError(
                    "a lease started more than one concurrent step"
                )
            frontier = _require_frontier_from_journal(payload.get("frontier_id"))
            attempt = payload.get("attempt_id")
            capability = payload.get("host_capability")
            if (
                frontier != current_frontier
                or attempt != _attempt_id(transaction_id, plan_fingerprint, frontier)
                or capability not in {item.value for item in HostCapability}
            ):
                raise SupervisorJournalError("journal step identity is invalid")
            current_capability = HostCapability(str(capability))
            current_attempt = (
                transaction_id,
                str(attempt),
                frontier,
                current_capability,
            )
            pending.append(current_attempt)
        elif state in {item.value for item in StepDisposition}:
            if current_attempt is None:
                raise SupervisorJournalError("journal disposition has no matching step")
            tx, attempt, frontier, attempt_capability = current_attempt
            if (
                payload.get("attempt_id") != attempt
                or payload.get("frontier_id") != frontier
                or tx != transaction_id
            ):
                raise SupervisorJournalError("journal disposition mismatches its step")
            _require_detail_from_journal(payload.get("detail"))
            pending.remove(current_attempt)
            current_attempt = None
            disposition = StepDisposition(state)
            transaction_disposition = disposition
            latest = disposition
            durable_wait = None
            durable_wait_event = None
            durable_wait_capability = None
            unknown_recovery_event = None
            if disposition is StepDisposition.ROUND_COMPLETE:
                next_frontier = _require_frontier_from_journal(
                    payload.get("next_frontier_id")
                )
                if next_frontier == frontier or next_frontier in completed:
                    raise SupervisorJournalError(
                        "completed frontier forms a replay cycle"
                    )
                completed.append(frontier)
                current_frontier = next_frontier
            elif disposition is StepDisposition.PLAN_QUIESCENT:
                evidence = _evidence_from_payload(payload.get("fixed_point_evidence"))
                if (
                    evidence.execution_id != execution_id
                    or evidence.execution_namespace != execution_namespace
                    or evidence.plan_fingerprint != plan_fingerprint
                    or evidence.current_frontier_id != frontier
                ):
                    raise SupervisorJournalError(
                        "fixed-point evidence is bound to another execution frontier"
                    )
            elif disposition in {
                StepDisposition.WAITING,
                StepDisposition.WAITING_FOR_HOST,
            }:
                durable_wait = _wait_from_payload(payload.get("wait_condition"))
                durable_wait_event = event
                durable_wait_capability = attempt_capability
        elif state == "UNKNOWN_ATTEMPT_RECOVERY_REQUIRED":
            if current_attempt is not None:
                raise SupervisorJournalError(
                    "unknown-attempt recovery obligation overlapped a new step"
                )
            frontier = _require_frontier_from_journal(payload.get("frontier_id"))
            attempt = payload.get("attempt_id")
            if (
                frontier != current_frontier
                or not isinstance(attempt, str)
                or not any(
                    item[1] == attempt and item[2] == frontier for item in pending
                )
            ):
                raise SupervisorJournalError(
                    "unknown-attempt recovery obligation has no exact pending attempt"
                )
            _require_detail_from_journal(payload.get("detail"))
            transaction_disposition = StepDisposition.RECOVERY_REQUIRED
            latest = StepDisposition.RECOVERY_REQUIRED
            unknown_recovery_event = event
            durable_wait = None
            durable_wait_event = None
            durable_wait_capability = None
        elif state == "UNKNOWN_ATTEMPT_RECONCILED":
            if current_attempt is not None:
                raise SupervisorJournalError(
                    "attempt reconciliation overlapped a new step"
                )
            frontier = _require_frontier_from_journal(payload.get("frontier_id"))
            attempt = payload.get("attempt_id")
            matches = [
                item for item in pending if item[1] == attempt and item[2] == frontier
            ]
            if frontier != current_frontier or len(matches) != 1:
                raise SupervisorJournalError(
                    "attempt reconciliation does not name one exact pending attempt"
                )
            observation_id = payload.get("observation_id")
            if (
                not isinstance(observation_id, str)
                or _DIGEST.fullmatch(observation_id) is None
            ):
                raise SupervisorJournalError(
                    "attempt reconciliation observation is invalid"
                )
            raw_disposition = payload.get("disposition")
            allowed = {
                StepDisposition.WAITING,
                StepDisposition.WAITING_FOR_HOST,
                StepDisposition.BLOCKED,
                StepDisposition.ROUND_COMPLETE,
                StepDisposition.PLAN_QUIESCENT,
            }
            if matches[0][3] is HostCapability.AUTHENTICATED_OBSERVER:
                allowed.remove(StepDisposition.ROUND_COMPLETE)
            try:
                disposition = StepDisposition(str(raw_disposition))
            except ValueError as error:
                raise SupervisorJournalError(
                    "attempt reconciliation disposition is invalid"
                ) from error
            if disposition not in allowed:
                raise SupervisorJournalError(
                    "attempt reconciliation cannot preserve an unknown outcome"
                )
            _require_detail_from_journal(payload.get("detail"))
            next_frontier = payload.get("next_frontier_id")
            raw_evidence = payload.get("fixed_point_evidence")
            raw_wait = payload.get("wait_condition")
            durable_wait = None
            durable_wait_event = None
            durable_wait_capability = None
            if disposition is StepDisposition.ROUND_COMPLETE:
                next_value = _require_frontier_from_journal(next_frontier)
                if raw_evidence is not None or raw_wait is not None:
                    raise SupervisorJournalError(
                        "reconciled round carries incompatible evidence"
                    )
                if next_value == frontier or next_value in completed:
                    raise SupervisorJournalError(
                        "reconciled frontier forms a replay cycle"
                    )
                completed.append(frontier)
                current_frontier = next_value
            elif disposition is StepDisposition.PLAN_QUIESCENT:
                if next_frontier is not None or raw_wait is not None:
                    raise SupervisorJournalError(
                        "reconciled fixed point carries incompatible fields"
                    )
                evidence = _evidence_from_payload(raw_evidence)
                if (
                    evidence.execution_id != execution_id
                    or evidence.execution_namespace != execution_namespace
                    or evidence.current_frontier_id != frontier
                    or evidence.terminal_observation_id != observation_id
                ):
                    raise SupervisorJournalError(
                        "reconciled fixed-point evidence binding is invalid"
                    )
            elif disposition in {
                StepDisposition.WAITING,
                StepDisposition.WAITING_FOR_HOST,
            }:
                if next_frontier is not None or raw_evidence is not None:
                    raise SupervisorJournalError(
                        "reconciled wait carries incompatible evidence"
                    )
                durable_wait = _wait_from_payload(raw_wait)
                durable_wait_event = event
                durable_wait_capability = matches[0][3]
            elif any(
                item is not None for item in (next_frontier, raw_evidence, raw_wait)
            ):
                raise SupervisorJournalError(
                    "reconciled blocker carries incompatible evidence"
                )
            pending.remove(matches[0])
            unknown_recovery_event = None
            transaction_disposition = disposition
            latest = disposition
        elif state == "TORN_TAIL_RECOVERED":
            if current_attempt is not None:
                raise SupervisorJournalError("torn-tail recovery overlapped a new step")
            _require_text_from_journal(payload.get("actor"), "recovery actor")
            _require_text_from_journal(payload.get("reason"), "recovery reason")
            if _DIGEST.fullmatch(str(payload.get("tail_digest", ""))) is None:
                raise SupervisorJournalError("recovered tail digest is invalid")
            if type(payload.get("tail_bytes")) is not int or payload["tail_bytes"] < 1:
                raise SupervisorJournalError("recovered tail byte count is invalid")
            evidence_file = payload.get("evidence_file")
            if (
                type(evidence_file) is not str
                or Path(evidence_file).is_absolute()
                or Path(evidence_file).parts[:1] != (RECOVERY_DIRECTORY,)
                or ".." in Path(evidence_file).parts
            ):
                raise SupervisorJournalError("recovery evidence path is invalid")
            transaction_disposition = StepDisposition.RECOVERY_REQUIRED
            latest = StepDisposition.RECOVERY_REQUIRED
        elif state == "LEASE_RELEASED":
            raw_disposition = payload.get("disposition")
            if raw_disposition not in {item.value for item in StepDisposition}:
                raise SupervisorJournalError("lease release disposition is invalid")
            disposition = StepDisposition(str(raw_disposition))
            if current_attempt is not None:
                raise SupervisorJournalError("lease released with a step still active")
            if transaction_disposition is None:
                if (
                    evidence is None
                    or disposition is not StepDisposition.PLAN_QUIESCENT
                ):
                    raise SupervisorJournalError("lease released without a disposition")
            elif transaction_disposition is not disposition:
                raise SupervisorJournalError(
                    "lease release contradicts its disposition"
                )
            transaction_closed = True
        else:  # pragma: no cover - exact payload routing already rejects this
            raise SupervisorJournalError(f"unsupported journal state {state!r}")
        previous = str(event["event_id"])

    return _Replay(
        events=events,
        last_event_id=previous,
        max_epoch=max_epoch,
        current_frontier=current_frontier,
        initial_frontier=initial_frontier,
        completed_frontiers=tuple(completed),
        active_transaction_id=active_transaction,
        transaction_closed=transaction_closed,
        pending_attempts=tuple(pending),
        quiescent_evidence=evidence,
        latest_disposition=latest,
        durable_wait=durable_wait,
        durable_wait_event=durable_wait_event,
        durable_wait_host_capability=durable_wait_capability,
        unknown_recovery_event=unknown_recovery_event,
    )


def _require_frontier_from_journal(value: object) -> str:
    try:
        return _require_frontier(value)
    except SupervisorContractError as error:
        raise SupervisorJournalError(str(error)) from error


def _require_detail_from_journal(value: object) -> str:
    return _require_text_from_journal(value, "journal disposition detail")


def _require_text_from_journal(value: object, label: str) -> str:
    try:
        return _require_text(value, label)
    except SupervisorContractError as error:
        raise SupervisorJournalError(str(error)) from error


def _parse_complete_lines(
    raw: bytes,
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
) -> tuple[dict[str, Any], ...]:
    events: list[dict[str, Any]] = []
    for index, line in enumerate(raw.splitlines(keepends=True), start=1):
        if not line.endswith(b"\n") or not line[:-1]:
            raise SupervisorJournalError(f"journal line {index} is not complete")
        encoded = line[:-1]
        event = _strict_json(encoded, f"journal line {index}")
        if _canonical(event) != encoded:
            raise SupervisorJournalError(f"journal line {index} is not canonical JSON")
        events.append(event)
    _replay_events(
        tuple(events),
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
    )
    return tuple(events)


def _load_journal(
    path: Path,
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
) -> _Replay:
    if not path.exists():
        return _replay_events(
            (),
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
    if _is_link_like(path) or not path.is_file():
        raise SupervisorJournalError("supervisor journal is not a regular file")
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SupervisorJournalError(
            f"supervisor journal is unreadable: {error}"
        ) from error
    if raw and not raw.endswith(b"\n"):
        split = raw.rfind(b"\n") + 1
        prefix, tail = raw[:split], raw[split:]
        events = _parse_complete_lines(
            prefix,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
        raise TornJournalTail(
            "supervisor journal has an unterminated final record; explicit recovery is required",
            valid_prefix=prefix,
            tail=tail,
            events=events,
        )
    events = _parse_complete_lines(
        raw,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
    )
    replay = _replay_events(
        events,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
    )
    _validate_recovery_receipts(path.parent, replay, plan_fingerprint=plan_fingerprint)
    return replay


def _validate_recovery_receipts(
    execution_dir: Path, replay: _Replay, *, plan_fingerprint: str
) -> None:
    expected_fields = {
        "schema_version",
        "kind",
        "execution_id",
        "execution_namespace",
        "plan_fingerprint",
        "actor",
        "reason",
        "recovered_at",
        "prior_event_id",
        "valid_prefix_bytes",
        "tail_digest",
        "tail_bytes",
        "tail_base64",
        "record_id",
    }
    for index, event in enumerate(replay.events):
        if event["state"] != "TORN_TAIL_RECOVERED":
            continue
        payload = event["payload"]
        assert isinstance(payload, dict)
        relative = Path(str(payload["evidence_file"]))
        path = execution_dir / relative
        if _is_link_like(path.parent) or _is_link_like(path) or not path.is_file():
            raise SupervisorJournalError("torn-tail recovery evidence is unavailable")
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise SupervisorJournalError(
                f"torn-tail recovery evidence is unreadable: {error}"
            ) from error
        value = _strict_json(raw, "torn-tail recovery evidence")
        canonical = (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        material = dict(value)
        record_id = material.pop("record_id", None)
        lease_event = replay.events[index - 1] if index else None
        expected_prior = (
            lease_event.get("previous_event_id")
            if isinstance(lease_event, dict)
            and lease_event.get("state") == "LEASE_ACQUIRED"
            else object()
        )
        expected_prefix_bytes = sum(
            len(_canonical(prior_event)) + 1
            for prior_event in replay.events[: max(0, index - 1)]
        )
        try:
            tail = base64.b64decode(str(value.get("tail_base64", "")), validate=True)
        except (ValueError, TypeError) as error:
            raise SupervisorJournalError(
                "torn-tail recovery evidence encoding is invalid"
            ) from error
        if (
            set(value) != expected_fields
            or raw != canonical
            or value.get("schema_version") != SCHEMA_VERSION
            or value.get("kind") != RECOVERY_KIND
            or value.get("execution_id") != event.get("execution_id")
            or value.get("execution_namespace") != event.get("execution_namespace")
            or value.get("plan_fingerprint") != plan_fingerprint
            or value.get("actor") != payload.get("actor")
            or value.get("reason") != payload.get("reason")
            or value.get("prior_event_id") != expected_prior
            or type(value.get("valid_prefix_bytes")) is not int
            or value["valid_prefix_bytes"] != expected_prefix_bytes
            or value.get("tail_digest") != payload.get("tail_digest")
            or value.get("tail_bytes") != payload.get("tail_bytes")
            or type(value.get("tail_bytes")) is not int
            or value["tail_bytes"] < 1
            or len(tail) != value["tail_bytes"]
            or _bytes_digest(tail) != value["tail_digest"]
            or not isinstance(record_id, str)
            or record_id != _digest(material)
            or relative
            != Path(RECOVERY_DIRECTORY) / (record_id.removeprefix("sha256:") + ".json")
        ):
            raise SupervisorJournalError("torn-tail recovery evidence is invalid")
        _validate_time(value.get("recovered_at"))


def _authenticate(
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    authenticate: Authenticator,
) -> Path:
    if type(execution_id) is not str or _DIGEST.fullmatch(execution_id) is None:
        raise SupervisorAuthenticationError(
            "execution id must be an exact SHA-256 digest"
        )
    if (
        type(execution_namespace) is not str
        or _NAMESPACE.fullmatch(execution_namespace) is None
    ):
        raise SupervisorAuthenticationError("execution namespace is invalid")
    if type(plan_fingerprint) is not str or _DIGEST.fullmatch(plan_fingerprint) is None:
        raise SupervisorAuthenticationError(
            "plan fingerprint must be an exact SHA-256 digest"
        )
    if not callable(authenticate):
        raise SupervisorAuthenticationError("an execution authenticator is required")
    supplied = Path(execution_dir)
    if not supplied.is_absolute():
        raise SupervisorAuthenticationError(
            "execution directory must be explicit and absolute"
        )
    _reject_link_chain(supplied, "execution directory")
    try:
        canonical = supplied.resolve(strict=True)
    except OSError as error:
        raise SupervisorAuthenticationError(
            "execution directory does not exist"
        ) from error
    if not canonical.is_dir():
        raise SupervisorAuthenticationError("execution directory is not a directory")
    try:
        authenticated_raw = authenticate(
            canonical,
            execution_id,
            execution_namespace,
            plan_fingerprint,
        )
        authenticated = Path(authenticated_raw)
    except Exception as error:
        raise SupervisorAuthenticationError(
            f"execution authority authentication failed: {type(error).__name__}"
        ) from error
    if not authenticated.is_absolute():
        raise SupervisorAuthenticationError(
            "authenticator returned a relative authority path"
        )
    _reject_link_chain(authenticated, "authenticated execution directory")
    try:
        authenticated = authenticated.resolve(strict=True)
    except OSError as error:
        raise SupervisorAuthenticationError(
            "authenticated execution directory does not exist"
        ) from error
    if authenticated != canonical:
        raise SupervisorAuthenticationError(
            "authenticated execution directory differs from the explicit directory"
        )
    return canonical


_LOCAL_LOCKS_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.Lock] = {}


class _SupervisorLease:
    """A process-local plus OS-enforced, non-waiting execution lease."""

    def __init__(self, execution_dir: Path) -> None:
        self.path = execution_dir / "locks" / LOCK_NAME
        self.fd: int | None = None
        self.local: threading.Lock | None = None

    def __enter__(self) -> _SupervisorLease:
        lock_dir = self.path.parent
        if not lock_dir.is_dir() or _is_link_like(lock_dir):
            raise SupervisorAuthenticationError(
                "authenticated execution directory has no regular locks directory"
            )
        if self.path.exists() and _is_link_like(self.path):
            raise SupervisorAuthenticationError("supervisor lock path is a link")
        lock_existed = self.path.exists()
        lock_was_empty = lock_existed and self.path.stat().st_size == 0
        key = os.path.normcase(str(self.path.resolve(strict=False)))
        with _LOCAL_LOCKS_GUARD:
            self.local = _LOCAL_LOCKS.setdefault(key, threading.Lock())
        if not self.local.acquire(blocking=False):
            raise SupervisorLeaseHeld("another supervisor owns this execution lease")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            self.fd = os.open(self.path, flags, 0o600)
            if os.fstat(self.fd).st_size == 0:
                os.write(self.fd, b"\0")
                os.fsync(self.fd)
            if not lock_existed or lock_was_empty:
                _fsync_directory(lock_dir)
            os.lseek(self.fd, 0, os.SEEK_SET)
            self._lock_os()
        except BlockingIOError as error:
            self._close()
            raise SupervisorLeaseHeld(
                "another supervisor owns this execution lease"
            ) from error
        except OSError as error:
            self._close()
            raise SupervisorJournalError(
                f"cannot establish durable supervisor lease: {error}"
            ) from error
        return self

    def _lock_os(self) -> None:
        assert self.fd is not None
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise BlockingIOError from error
        else:
            import fcntl

            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _close(self) -> None:
        if self.fd is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(self.fd, 0, os.SEEK_SET)
                    try:
                        msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    import fcntl

                    try:
                        fcntl.flock(self.fd, fcntl.LOCK_UN)
                    except OSError:
                        pass
            finally:
                os.close(self.fd)
                self.fd = None
        if self.local is not None:
            self.local.release()
            self.local = None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        self._close()
        return False


def _make_event(
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    state: str,
    transaction_id: str,
    previous_event_id: str | None,
    recorded_at: datetime,
    payload: Mapping[str, object],
) -> dict[str, Any]:
    material: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "kind": EVENT_KIND,
        "execution_id": execution_id,
        "execution_namespace": execution_namespace,
        "plan_fingerprint": plan_fingerprint,
        "state": state,
        "transaction_id": transaction_id,
        "previous_event_id": previous_event_id,
        "recorded_at": _format_time(recorded_at),
        "payload": dict(payload),
    }
    return {**material, "event_id": _digest(material)}


def _append_bytes(path: Path, encoded: bytes) -> None:
    if path.exists() and (_is_link_like(path) or not path.is_file()):
        raise SupervisorJournalError("supervisor journal is not a regular file")
    existed = path.exists()
    was_empty = existed and path.stat().st_size == 0
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(fd, view)
                if written < 1:
                    raise OSError("zero-byte journal write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        if not existed or was_empty:
            _fsync_directory(path.parent)
    except OSError as error:
        raise SupervisorJournalError(
            f"cannot append supervisor journal: {error}"
        ) from error


def _append_event(
    journal_path: Path,
    replay: _Replay,
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    state: str,
    transaction_id: str,
    payload: Mapping[str, object],
    clock: Callable[[], datetime],
    after_append: AfterAppend | None,
) -> tuple[_Replay, dict[str, Any]]:
    event = _make_event(
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
        state=state,
        transaction_id=transaction_id,
        previous_event_id=replay.last_event_id,
        recorded_at=clock(),
        payload=payload,
    )
    candidate = (*replay.events, event)
    checked = _replay_events(
        candidate,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
    )
    _append_bytes(journal_path, _canonical(event) + b"\n")
    if after_append is not None:
        observer_copy = _strict_json(_canonical(event), "appended event")
        after_append(MappingProxyType(observer_copy))
    return checked, event


def _safe_detail(prefix: str, error: BaseException) -> str:
    detail = f"{prefix}: {type(error).__name__}"
    message = " ".join(str(error).split())
    if message:
        detail += f": {message}"
    return detail[:4096].rstrip()


def _same_callable(left: object, right: object) -> bool:
    if left is right:
        return True
    return (
        getattr(left, "__self__", None) is not None
        and getattr(left, "__self__", None) is getattr(right, "__self__", None)
        and getattr(left, "__func__", None) is getattr(right, "__func__", None)
    )


def _validate_step_result(result: object, context: StepContext) -> StepResult:
    if (
        type(result) is not StepResult
        or type(result.disposition) is not StepDisposition
    ):
        raise SupervisorContractError(
            "step callback returned an unknown or untyped disposition"
        )
    _require_text(result.detail, "step detail")
    if result.disposition is StepDisposition.ROUND_COMPLETE:
        next_frontier = _require_frontier(result.next_frontier_id, "next frontier id")
        if (
            next_frontier == context.frontier_id
            or next_frontier in context.completed_frontiers
        ):
            raise SupervisorContractError(
                "ROUND_COMPLETE must advance to a new frontier"
            )
        if result.fixed_point_evidence is not None:
            raise SupervisorContractError(
                "ROUND_COMPLETE cannot carry quiescence evidence"
            )
        if (
            result.wait_condition is not None
            or result.terminal_observation_id is not None
        ):
            raise SupervisorContractError(
                "ROUND_COMPLETE carries incompatible wake evidence"
            )
    elif result.disposition is StepDisposition.PLAN_QUIESCENT:
        if result.next_frontier_id is not None:
            raise SupervisorContractError("PLAN_QUIESCENT cannot name another frontier")
        if result.fixed_point_evidence is not None or result.wait_condition is not None:
            raise SupervisorContractError(
                "host step cannot supply controller fixed-point or wait evidence"
            )
        if (
            type(result.terminal_observation_id) is not str
            or _DIGEST.fullmatch(result.terminal_observation_id) is None
        ):
            raise SupervisorContractError(
                "PLAN_QUIESCENT requires an authenticated terminal lifecycle observation"
            )
    elif result.disposition in {
        StepDisposition.WAITING,
        StepDisposition.WAITING_FOR_HOST,
    }:
        if (
            result.next_frontier_id is not None
            or result.fixed_point_evidence is not None
            or result.terminal_observation_id is not None
        ):
            raise SupervisorContractError(
                f"{result.disposition.value} carries incompatible terminal evidence"
            )
        _validate_wait_condition(result.wait_condition)
    elif (
        result.next_frontier_id is not None
        or result.fixed_point_evidence is not None
        or result.wait_condition is not None
        or result.terminal_observation_id is not None
    ):
        raise SupervisorContractError(
            f"{result.disposition.value} cannot carry frontier or quiescence evidence"
        )
    return result


def _validate_observer_result(result: object) -> StepResult:
    """Validate a read-only observer result before translating it internally."""

    if (
        type(result) is not ObserverResult
        or type(result.disposition) is not StepDisposition
    ):
        raise SupervisorContractError(
            "terminal observer returned an unknown or untyped disposition"
        )
    _require_text(result.detail, "observer detail")
    allowed = {
        StepDisposition.PLAN_QUIESCENT,
        StepDisposition.WAITING_FOR_HOST,
        StepDisposition.BLOCKED,
        StepDisposition.RECOVERY_REQUIRED,
    }
    if result.disposition not in allowed:
        raise SupervisorContractError(
            "terminal observer cannot admit work or advance a round"
        )
    if result.disposition is StepDisposition.PLAN_QUIESCENT:
        if result.wait_condition is not None:
            raise SupervisorContractError(
                "terminal observer fixed-point nomination cannot carry a wait"
            )
        if (
            type(result.terminal_observation_id) is not str
            or _DIGEST.fullmatch(result.terminal_observation_id) is None
        ):
            raise SupervisorContractError(
                "terminal observer requires an authenticated lifecycle observation"
            )
    elif result.disposition is StepDisposition.WAITING_FOR_HOST:
        if result.terminal_observation_id is not None:
            raise SupervisorContractError(
                "terminal observer wait cannot carry terminal evidence"
            )
        _validate_wait_condition(result.wait_condition)
    elif (
        result.wait_condition is not None or result.terminal_observation_id is not None
    ):
        raise SupervisorContractError(
            f"{result.disposition.value} observer result carries incompatible evidence"
        )
    return StepResult(
        disposition=result.disposition,
        detail=result.detail,
        wait_condition=result.wait_condition,
        terminal_observation_id=result.terminal_observation_id,
    )


def _verify_terminal_fixed_point(
    *,
    verifier: FixedPointVerifier,
    directory: Path,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    initial_frontier_id: str,
    frontier_id: str,
    terminal_observation_id: str,
) -> FixedPointEvidence:
    request = FixedPointVerificationRequest(
        execution_dir=directory,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
        initial_frontier_id=initial_frontier_id,
        current_frontier_id=frontier_id,
        terminal_observation_id=terminal_observation_id,
    )
    try:
        evidence = verifier(request)
    except Exception as error:
        raise SupervisorContractError(
            _safe_detail("fixed-point verifier rejected terminal observation", error)
        ) from error
    return _validate_evidence(
        evidence,
        require_quiescent=True,
        request=request,
    )


def _result_from_event(
    *,
    disposition: StepDisposition,
    detail: str,
    epoch: int,
    transaction_id: str,
    frontier_id: str,
    completed_frontiers: tuple[str, ...],
    event: Mapping[str, object],
    evidence: FixedPointEvidence | None = None,
    wait_condition: WaitCondition | None = None,
    unknown_attempt_id: str | None = None,
) -> SupervisorResult:
    return SupervisorResult(
        disposition=disposition,
        successful=disposition is StepDisposition.PLAN_QUIESCENT,
        detail=detail,
        epoch=epoch,
        transaction_id=transaction_id,
        frontier_id=frontier_id,
        completed_frontiers=completed_frontiers,
        journal_event_id=str(event["event_id"]),
        fixed_point_evidence=evidence,
        wait_condition=wait_condition,
        unknown_attempt_id=unknown_attempt_id,
    )


def _validate_resume_observation(
    observation_fingerprint: str | None, resume_token: str | None
) -> None:
    if (observation_fingerprint is None) != (resume_token is None):
        raise SupervisorContractError(
            "resume observation fingerprint and token must be supplied together"
        )
    for value, label in (
        (observation_fingerprint, "resume observation fingerprint"),
        (resume_token, "resume token"),
    ):
        if value is not None and (
            type(value) is not str or _DIGEST.fullmatch(value) is None
        ):
            raise SupervisorContractError(f"{label} is invalid")


def _wait_is_ready(
    condition: WaitCondition,
    *,
    execution_dir: Path,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    frontier_id: str,
    stored_capability: HostCapability | None,
    current_capability: HostCapability,
    now: datetime,
    observation_fingerprint: str | None,
    resume_token: str | None,
    verify_wait_observation: WaitObservationVerifier | None,
) -> bool:
    if observation_fingerprint is not None:
        if condition.resume_token is None or condition.observation_fingerprint is None:
            raise SupervisorContractError(
                "durable wait does not grant observation-resume authority"
            )
        if resume_token != condition.resume_token:
            raise SupervisorContractError(
                "resume token does not match the durable wait capability"
            )
        if not callable(verify_wait_observation):
            raise SupervisorContractError(
                "observation resume requires an authenticated wait verifier"
            )
        request = WaitObservationVerificationRequest(
            execution_dir=execution_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            frontier_id=frontier_id,
            stored_observation_fingerprint=condition.observation_fingerprint,
            supplied_observation_fingerprint=observation_fingerprint,
            resume_token=resume_token,
        )
        authenticated = verify_wait_observation(request)
        if type(authenticated) is not str or _DIGEST.fullmatch(authenticated) is None:
            raise SupervisorContractError(
                "wait verifier returned an invalid observation fingerprint"
            )
        if authenticated != observation_fingerprint:
            raise SupervisorContractError(
                "supplied wait observation is not authenticated current state"
            )
    if stored_capability is not None and stored_capability is not current_capability:
        return True
    if condition.wake_at is not None and now.astimezone(
        UTC
    ) >= condition.wake_at.astimezone(UTC):
        return True
    if observation_fingerprint is None:
        return False
    return condition.observation_fingerprint != observation_fingerprint


def _replayed_wait_result(replay: _Replay) -> SupervisorResult:
    event = replay.durable_wait_event
    condition = replay.durable_wait
    if event is None or condition is None:
        raise SupervisorJournalError("durable wait replay is incomplete")
    payload = event["payload"]
    assert isinstance(payload, dict)
    state = str(event["state"])
    disposition = (
        StepDisposition(str(payload["disposition"]))
        if state == "UNKNOWN_ATTEMPT_RECONCILED"
        else StepDisposition(state)
    )
    return _result_from_event(
        disposition=disposition,
        detail=str(payload["detail"]),
        epoch=int(payload["epoch"]),
        transaction_id=str(event["transaction_id"]),
        frontier_id=str(payload["frontier_id"]),
        completed_frontiers=replay.completed_frontiers,
        event=event,
        wait_condition=condition,
    )


def _replayed_unknown_result(replay: _Replay) -> SupervisorResult:
    event = replay.unknown_recovery_event
    if event is None:
        raise SupervisorJournalError("unknown-attempt recovery replay is incomplete")
    payload = event["payload"]
    assert isinstance(payload, dict)
    return _result_from_event(
        disposition=StepDisposition.RECOVERY_REQUIRED,
        detail=str(payload["detail"]),
        epoch=int(payload["epoch"]),
        transaction_id=str(event["transaction_id"]),
        frontier_id=str(payload["frontier_id"]),
        completed_frontiers=replay.completed_frontiers,
        event=event,
        unknown_attempt_id=str(payload["attempt_id"]),
    )


def _begin_journal_lease(
    journal_path: Path,
    replay: _Replay,
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    frontier_id: str,
    clock: Callable[[], datetime],
    after_append: AfterAppend | None,
) -> tuple[_Replay, int, str]:
    epoch = replay.max_epoch + 1
    transaction_id = _transaction_id(
        execution_id,
        execution_namespace,
        plan_fingerprint,
        epoch,
        replay.last_event_id,
    )
    replay, _ = _append_event(
        journal_path,
        replay,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
        state="LEASE_ACQUIRED",
        transaction_id=transaction_id,
        payload={
            "epoch": epoch,
            "frontier_id": frontier_id,
            "resumed": replay.last_event_id is not None,
            "previous_transaction_closed": (
                replay.active_transaction_id is None or replay.transaction_closed
            ),
        },
        clock=clock,
        after_append=after_append,
    )
    return replay, epoch, transaction_id


def _release_journal_lease(
    journal_path: Path,
    replay: _Replay,
    *,
    execution_id: str,
    execution_namespace: str,
    plan_fingerprint: str,
    epoch: int,
    transaction_id: str,
    disposition: StepDisposition,
    clock: Callable[[], datetime],
    after_append: AfterAppend | None,
) -> _Replay:
    replay, _ = _append_event(
        journal_path,
        replay,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        plan_fingerprint=plan_fingerprint,
        state="LEASE_RELEASED",
        transaction_id=transaction_id,
        payload={"epoch": epoch, "disposition": disposition.value},
        clock=clock,
        after_append=after_append,
    )
    return replay


def run_to_fixed_point(
    *,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    authenticate: Authenticator,
    plan_fingerprint: str,
    initial_frontier_id: str,
    host_capability: HostCapability,
    step: StepCallback,
    verify_fixed_point: FixedPointVerifier,
    observe_terminal: ObserverCallback | None = None,
    verify_wait_observation: WaitObservationVerifier | None = None,
    observation_fingerprint: str | None = None,
    resume_token: str | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    after_append: AfterAppend | None = None,
    max_round_transitions: int = 1024,
) -> SupervisorResult:
    """Run deterministic immediate progress and stop at wait, adversity, or proof.

    ``authenticate`` must return the same canonical directory after verifying the
    execution id and namespace against controller authority.  It is intentionally
    mandatory: possession of a writable path is not execution authority.
    """

    if type(plan_fingerprint) is not str or _DIGEST.fullmatch(plan_fingerprint) is None:
        raise SupervisorContractError(
            "plan fingerprint must be an exact SHA-256 digest"
        )
    directory = _authenticate(
        execution_dir,
        execution_id,
        execution_namespace,
        plan_fingerprint,
        authenticate,
    )
    initial = _require_frontier(initial_frontier_id, "initial frontier id")
    if type(host_capability) is not HostCapability:
        raise SupervisorContractError("host capability must be typed")
    if not callable(step):
        raise SupervisorContractError("step callback is required")
    if host_capability is HostCapability.AUTHENTICATED_OBSERVER and not callable(
        observe_terminal
    ):
        raise SupervisorContractError(
            "authenticated observer capability requires a terminal observer callback"
        )
    if observe_terminal is not None and (
        not callable(observe_terminal) or _same_callable(observe_terminal, step)
    ):
        raise SupervisorContractError(
            "terminal observer must be a distinct callable boundary"
        )
    if verify_wait_observation is not None and (
        not callable(verify_wait_observation)
        or _same_callable(verify_wait_observation, step)
        or _same_callable(verify_wait_observation, observe_terminal)
    ):
        raise SupervisorContractError(
            "wait observation verifier must be a distinct callable boundary"
        )
    if (
        not callable(verify_fixed_point)
        or _same_callable(verify_fixed_point, step)
        or (
            observe_terminal is not None
            and _same_callable(verify_fixed_point, observe_terminal)
        )
    ):
        raise SupervisorContractError(
            "fixed-point verifier must be a distinct callable authority"
        )
    _validate_resume_observation(observation_fingerprint, resume_token)
    if type(max_round_transitions) is not int or max_round_transitions < 1:
        raise SupervisorContractError("round transition bound must be positive")

    journal_path = directory / JOURNAL_NAME
    with _SupervisorLease(directory):
        replay = _load_journal(
            journal_path,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
        if replay.initial_frontier is not None and replay.initial_frontier != initial:
            raise SupervisorContractError(
                "initial frontier conflicts with the durable execution journal"
            )
        frontier = replay.current_frontier or initial
        if replay.quiescent_evidence is not None:
            sealed_evidence = replay.quiescent_evidence
            request = FixedPointVerificationRequest(
                execution_dir=directory,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                initial_frontier_id=initial,
                current_frontier_id=sealed_evidence.current_frontier_id,
                terminal_observation_id=sealed_evidence.terminal_observation_id,
            )
            _validate_evidence(sealed_evidence, require_quiescent=True, request=request)
            _authenticate(
                directory,
                execution_id,
                execution_namespace,
                plan_fingerprint,
                authenticate,
            )
            evidence = _verify_terminal_fixed_point(
                verifier=verify_fixed_point,
                directory=directory,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                initial_frontier_id=initial,
                frontier_id=sealed_evidence.current_frontier_id,
                terminal_observation_id=sealed_evidence.terminal_observation_id,
            )
            if evidence.to_payload() != sealed_evidence.to_payload():
                raise SupervisorRecoveryError(
                    "durable fixed-point evidence no longer matches live controller "
                    "authority; the execution must be reconciled before success can "
                    "be replayed"
                )
            event = next(
                item
                for item in reversed(replay.events)
                if item["state"] == StepDisposition.PLAN_QUIESCENT.value
                or (
                    item["state"] == "UNKNOWN_ATTEMPT_RECONCILED"
                    and item["payload"].get("disposition")
                    == StepDisposition.PLAN_QUIESCENT.value
                )
            )
            payload = event["payload"]
            assert isinstance(payload, dict)
            return _result_from_event(
                disposition=StepDisposition.PLAN_QUIESCENT,
                detail=str(payload["detail"]),
                epoch=int(payload["epoch"]),
                transaction_id=str(event["transaction_id"]),
                frontier_id=evidence.current_frontier_id,
                completed_frontiers=replay.completed_frontiers,
                event=event,
                evidence=evidence,
            )

        if replay.pending_attempts:
            if replay.unknown_recovery_event is not None:
                return _replayed_unknown_result(replay)
            unknown = replay.pending_attempts[0]
            replay, epoch, transaction_id = _begin_journal_lease(
                journal_path,
                replay,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                frontier_id=frontier,
                clock=clock,
                after_append=after_append,
            )
            detail = (
                "a prior supervisor crashed with an unknown step outcome; reconcile "
                "the exact attempt from authenticated host/controller observation"
            )
            replay, event = _append_event(
                journal_path,
                replay,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                state="UNKNOWN_ATTEMPT_RECOVERY_REQUIRED",
                transaction_id=transaction_id,
                payload={
                    "epoch": epoch,
                    "frontier_id": unknown[2],
                    "attempt_id": unknown[1],
                    "detail": detail,
                },
                clock=clock,
                after_append=after_append,
            )
            result = _result_from_event(
                disposition=StepDisposition.RECOVERY_REQUIRED,
                detail=detail,
                epoch=epoch,
                transaction_id=transaction_id,
                frontier_id=unknown[2],
                completed_frontiers=replay.completed_frontiers,
                event=event,
                unknown_attempt_id=unknown[1],
            )
            _release_journal_lease(
                journal_path,
                replay,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                epoch=epoch,
                transaction_id=transaction_id,
                disposition=result.disposition,
                clock=clock,
                after_append=after_append,
            )
            return result

        if replay.durable_wait is not None:
            now = clock()
            _format_time(now)
            if not _wait_is_ready(
                replay.durable_wait,
                execution_dir=directory,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                frontier_id=frontier,
                stored_capability=replay.durable_wait_host_capability,
                current_capability=host_capability,
                now=now,
                observation_fingerprint=observation_fingerprint,
                resume_token=resume_token,
                verify_wait_observation=verify_wait_observation,
            ):
                return _replayed_wait_result(replay)

        replay, epoch, transaction_id = _begin_journal_lease(
            journal_path,
            replay,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            frontier_id=frontier,
            clock=clock,
            after_append=after_append,
        )
        transitions = 0
        while True:
            attempt_id = _attempt_id(transaction_id, plan_fingerprint, frontier)
            context = StepContext(
                execution_dir=directory,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                initial_frontier_id=initial,
                epoch=epoch,
                transaction_id=transaction_id,
                attempt_id=attempt_id,
                frontier_id=frontier,
                completed_frontiers=replay.completed_frontiers,
                host_capability=host_capability,
            )
            replay, _ = _append_event(
                journal_path,
                replay,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                state="STEP_STARTED",
                transaction_id=transaction_id,
                payload={
                    "epoch": epoch,
                    "frontier_id": frontier,
                    "attempt_id": attempt_id,
                    "host_capability": host_capability.value,
                },
                clock=clock,
                after_append=after_append,
            )
            if host_capability in {
                HostCapability.ATTENDED_CARD_ONLY,
                HostCapability.NO_LAUNCH,
            }:
                host_observation = _digest(
                    {
                        "kind": "hive-mind-unlaunchable-host-observation-v1",
                        "execution_id": execution_id,
                        "frontier_id": frontier,
                        "host_capability": host_capability.value,
                    }
                )
                host_resume = _digest(
                    {
                        "kind": "hive-mind-host-lifecycle-resume-token-v1",
                        "execution_id": execution_id,
                        "frontier_id": frontier,
                    }
                )
                raw_result = StepResult(
                    StepDisposition.WAITING_FOR_HOST,
                    f"host capability {host_capability.value} cannot autonomously launch "
                    "this frontier; an attended session card is preparation, not a launch",
                    wait_condition=WaitCondition(
                        observation_fingerprint=host_observation,
                        resume_token=host_resume,
                    ),
                )
            elif host_capability is HostCapability.AUTHENTICATED_OBSERVER:
                assert observe_terminal is not None
                observer_context = ObserverContext(
                    execution_dir=directory,
                    execution_id=execution_id,
                    execution_namespace=execution_namespace,
                    plan_fingerprint=plan_fingerprint,
                    initial_frontier_id=initial,
                    frontier_id=frontier,
                    completed_frontiers=replay.completed_frontiers,
                )
                try:
                    raw_result = _validate_observer_result(
                        observe_terminal(observer_context)
                    )
                except Exception as error:
                    raw_result = StepResult(
                        StepDisposition.RECOVERY_REQUIRED,
                        _safe_detail("terminal observer failed", error),
                    )
            else:
                try:
                    raw_result = step(context)
                except Exception as error:
                    raw_result = StepResult(
                        StepDisposition.RECOVERY_REQUIRED,
                        _safe_detail("step callback failed", error),
                    )
            verified_evidence: FixedPointEvidence | None = None
            try:
                result = _validate_step_result(raw_result, context)
                if result.disposition is StepDisposition.PLAN_QUIESCENT:
                    assert result.terminal_observation_id is not None
                    _authenticate(
                        directory,
                        execution_id,
                        execution_namespace,
                        plan_fingerprint,
                        authenticate,
                    )
                    verified_evidence = _verify_terminal_fixed_point(
                        verifier=verify_fixed_point,
                        directory=directory,
                        execution_id=execution_id,
                        execution_namespace=execution_namespace,
                        plan_fingerprint=plan_fingerprint,
                        initial_frontier_id=initial,
                        frontier_id=frontier,
                        terminal_observation_id=result.terminal_observation_id,
                    )
            except SupervisorContractError as error:
                result = StepResult(
                    StepDisposition.RECOVERY_REQUIRED,
                    _safe_detail("invalid step disposition or evidence", error),
                )
                verified_evidence = None

            payload: dict[str, object] = {
                "epoch": epoch,
                "frontier_id": frontier,
                "attempt_id": attempt_id,
                "detail": result.detail,
            }
            if result.disposition is StepDisposition.ROUND_COMPLETE:
                assert result.next_frontier_id is not None
                payload["next_frontier_id"] = result.next_frontier_id
            elif result.disposition is StepDisposition.PLAN_QUIESCENT:
                assert verified_evidence is not None
                payload["fixed_point_evidence"] = verified_evidence.to_payload()
            elif result.disposition in {
                StepDisposition.WAITING,
                StepDisposition.WAITING_FOR_HOST,
            }:
                assert result.wait_condition is not None
                payload["wait_condition"] = result.wait_condition.to_payload()
            replay, outcome_event = _append_event(
                journal_path,
                replay,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                state=result.disposition.value,
                transaction_id=transaction_id,
                payload=payload,
                clock=clock,
                after_append=after_append,
            )
            if result.disposition is StepDisposition.ROUND_COMPLETE:
                transitions += 1
                frontier = str(result.next_frontier_id)
                if transitions < max_round_transitions:
                    continue
                follow_attempt = _attempt_id(transaction_id, plan_fingerprint, frontier)
                replay, _ = _append_event(
                    journal_path,
                    replay,
                    execution_id=execution_id,
                    execution_namespace=execution_namespace,
                    plan_fingerprint=plan_fingerprint,
                    state="STEP_STARTED",
                    transaction_id=transaction_id,
                    payload={
                        "epoch": epoch,
                        "frontier_id": frontier,
                        "attempt_id": follow_attempt,
                        "host_capability": host_capability.value,
                    },
                    clock=clock,
                    after_append=after_append,
                )
                result = StepResult(
                    StepDisposition.RECOVERY_REQUIRED,
                    "round transition safety bound reached; resume in a new lease",
                )
                replay, outcome_event = _append_event(
                    journal_path,
                    replay,
                    execution_id=execution_id,
                    execution_namespace=execution_namespace,
                    plan_fingerprint=plan_fingerprint,
                    state=result.disposition.value,
                    transaction_id=transaction_id,
                    payload={
                        "epoch": epoch,
                        "frontier_id": frontier,
                        "attempt_id": follow_attempt,
                        "detail": result.detail,
                    },
                    clock=clock,
                    after_append=after_append,
                )
            normal_result = _result_from_event(
                disposition=result.disposition,
                detail=result.detail,
                epoch=epoch,
                transaction_id=transaction_id,
                frontier_id=frontier,
                completed_frontiers=replay.completed_frontiers,
                event=outcome_event,
                evidence=verified_evidence,
                wait_condition=result.wait_condition,
            )
            _release_journal_lease(
                journal_path,
                replay,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                epoch=epoch,
                transaction_id=transaction_id,
                disposition=normal_result.disposition,
                clock=clock,
                after_append=after_append,
            )
            return normal_result


def reconcile_unknown_attempt(
    *,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    authenticate: Authenticator,
    plan_fingerprint: str,
    initial_frontier_id: str,
    attempt_id: str,
    observation_id: str,
    result: StepResult,
    verify_fixed_point: FixedPointVerifier,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    after_append: AfterAppend | None = None,
) -> SupervisorResult:
    """Resolve one crash-unknown attempt from an authenticated exact observation."""

    if type(plan_fingerprint) is not str or _DIGEST.fullmatch(plan_fingerprint) is None:
        raise SupervisorContractError(
            "plan fingerprint must be an exact SHA-256 digest"
        )
    directory = _authenticate(
        execution_dir,
        execution_id,
        execution_namespace,
        plan_fingerprint,
        authenticate,
    )
    initial = _require_frontier(initial_frontier_id, "initial frontier id")
    if type(attempt_id) is not str or _DIGEST.fullmatch(attempt_id) is None:
        raise SupervisorRecoveryError("reconciliation attempt id is invalid")
    if type(observation_id) is not str or _DIGEST.fullmatch(observation_id) is None:
        raise SupervisorRecoveryError("reconciliation observation id is invalid")
    if not callable(verify_fixed_point):
        raise SupervisorContractError("fixed-point verifier is required")

    journal_path = directory / JOURNAL_NAME
    with _SupervisorLease(directory):
        replay = _load_journal(
            journal_path,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
        if replay.initial_frontier is not None and replay.initial_frontier != initial:
            raise SupervisorRecoveryError(
                "initial frontier conflicts with the durable execution journal"
            )
        matches = [item for item in replay.pending_attempts if item[1] == attempt_id]
        if len(matches) != 1:
            raise SupervisorRecoveryError(
                "reconciliation must name exactly one durable unknown attempt"
            )
        frontier = matches[0][2]
        next_epoch = replay.max_epoch + 1
        next_transaction = _transaction_id(
            execution_id,
            execution_namespace,
            plan_fingerprint,
            next_epoch,
            replay.last_event_id,
        )
        context = StepContext(
            execution_dir=directory,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            initial_frontier_id=initial,
            epoch=next_epoch,
            transaction_id=next_transaction,
            attempt_id=attempt_id,
            frontier_id=frontier,
            completed_frontiers=replay.completed_frontiers,
            host_capability=matches[0][3],
        )
        checked = _validate_step_result(result, context)
        allowed = {
            StepDisposition.WAITING,
            StepDisposition.WAITING_FOR_HOST,
            StepDisposition.BLOCKED,
            StepDisposition.ROUND_COMPLETE,
            StepDisposition.PLAN_QUIESCENT,
        }
        if context.host_capability is HostCapability.AUTHENTICATED_OBSERVER:
            allowed.remove(StepDisposition.ROUND_COMPLETE)
        if checked.disposition not in allowed:
            raise SupervisorRecoveryError(
                "reconciliation observation must resolve, not preserve, uncertainty"
            )
        verified_evidence: FixedPointEvidence | None = None
        if checked.disposition is StepDisposition.PLAN_QUIESCENT:
            if checked.terminal_observation_id != observation_id:
                raise SupervisorRecoveryError(
                    "terminal reconciliation observation id is inconsistent"
                )
            assert checked.terminal_observation_id is not None
            _authenticate(
                directory,
                execution_id,
                execution_namespace,
                plan_fingerprint,
                authenticate,
            )
            verified_evidence = _verify_terminal_fixed_point(
                verifier=verify_fixed_point,
                directory=directory,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
                initial_frontier_id=initial,
                frontier_id=frontier,
                terminal_observation_id=checked.terminal_observation_id,
            )

        replay, epoch, transaction_id = _begin_journal_lease(
            journal_path,
            replay,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            frontier_id=frontier,
            clock=clock,
            after_append=after_append,
        )
        payload: dict[str, object] = {
            "epoch": epoch,
            "frontier_id": frontier,
            "attempt_id": attempt_id,
            "observation_id": observation_id,
            "disposition": checked.disposition.value,
            "detail": checked.detail,
            "next_frontier_id": checked.next_frontier_id,
            "fixed_point_evidence": (
                verified_evidence.to_payload()
                if verified_evidence is not None
                else None
            ),
            "wait_condition": (
                checked.wait_condition.to_payload()
                if checked.wait_condition is not None
                else None
            ),
        }
        replay, event = _append_event(
            journal_path,
            replay,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            state="UNKNOWN_ATTEMPT_RECONCILED",
            transaction_id=transaction_id,
            payload=payload,
            clock=clock,
            after_append=after_append,
        )
        reconciled = _result_from_event(
            disposition=checked.disposition,
            detail=checked.detail,
            epoch=epoch,
            transaction_id=transaction_id,
            frontier_id=(
                str(checked.next_frontier_id)
                if checked.disposition is StepDisposition.ROUND_COMPLETE
                else frontier
            ),
            completed_frontiers=replay.completed_frontiers,
            event=event,
            evidence=verified_evidence,
            wait_condition=checked.wait_condition,
        )
        _release_journal_lease(
            journal_path,
            replay,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            epoch=epoch,
            transaction_id=transaction_id,
            disposition=checked.disposition,
            clock=clock,
            after_append=after_append,
        )
        return reconciled


def _exclusive_canonical_write(path: Path, value: Mapping[str, object]) -> None:
    encoded = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(fd, view)
                if written < 1:
                    raise OSError("zero-byte recovery evidence write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_directory(path.parent)
    except FileExistsError as error:
        if _is_link_like(path) or not path.is_file():
            raise SupervisorRecoveryError(
                "existing torn-tail evidence receipt is not a regular file"
            ) from error
        try:
            existing = path.read_bytes()
        except OSError as read_error:
            raise SupervisorRecoveryError(
                "existing torn-tail evidence receipt is unreadable"
            ) from read_error
        if existing != encoded:
            raise SupervisorRecoveryError(
                "torn-tail evidence receipt already exists with different content"
            ) from error
        flags = os.O_RDWR
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(path.parent)
    except OSError as error:
        raise SupervisorRecoveryError(
            f"cannot preserve torn-tail evidence: {error}"
        ) from error


def _replace_with_prefix(path: Path, prefix: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(
        prefix=".execution-supervisor-recovery-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        view = memoryview(prefix)
        while view:
            written = os.write(fd, view)
            if written < 1:
                raise OSError("zero-byte recovered journal write")
            view = view[written:]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError as error:
        raise SupervisorRecoveryError(
            f"cannot install recovered journal: {error}"
        ) from error
    finally:
        if fd >= 0:
            os.close(fd)
        removed = False
        try:
            temporary.unlink()
            removed = True
        except FileNotFoundError:
            pass
        finally:
            if removed:
                _fsync_directory(path.parent)


def recover_torn_tail(
    *,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    authenticate: Authenticator,
    plan_fingerprint: str,
    initial_frontier_id: str,
    actor: str,
    reason: str,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> TornTailRecoveryReceipt:
    """Preserve an exact torn tail, truncate only it, and journal the recovery."""

    if type(plan_fingerprint) is not str or _DIGEST.fullmatch(plan_fingerprint) is None:
        raise SupervisorContractError(
            "plan fingerprint must be an exact SHA-256 digest"
        )
    directory = _authenticate(
        execution_dir,
        execution_id,
        execution_namespace,
        plan_fingerprint,
        authenticate,
    )
    initial = _require_frontier(initial_frontier_id, "initial frontier id")
    actor = _require_text(actor, "recovery actor", maximum=256)
    reason = _require_text(reason, "recovery reason")
    journal_path = directory / JOURNAL_NAME
    with _SupervisorLease(directory):
        torn: TornJournalTail | None = None
        try:
            _load_journal(
                journal_path,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                plan_fingerprint=plan_fingerprint,
            )
        except TornJournalTail as error:
            torn = error
        else:
            raise SupervisorRecoveryError("supervisor journal has no torn tail")
        assert torn is not None

        replay = _replay_events(
            torn.events,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
        if replay.initial_frontier is not None and replay.initial_frontier != initial:
            raise SupervisorRecoveryError(
                "initial frontier conflicts with the durable execution journal"
            )
        recovered_at = _format_time(clock())
        receipt_material: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "kind": RECOVERY_KIND,
            "execution_id": execution_id,
            "execution_namespace": execution_namespace,
            "plan_fingerprint": plan_fingerprint,
            "actor": actor,
            "reason": reason,
            "recovered_at": recovered_at,
            "prior_event_id": replay.last_event_id,
            "valid_prefix_bytes": len(torn.valid_prefix),
            "tail_digest": torn.tail_digest,
            "tail_bytes": len(torn.tail),
            "tail_base64": base64.b64encode(torn.tail).decode("ascii"),
        }
        receipt = {**receipt_material, "record_id": _digest(receipt_material)}
        recovery_dir = directory / RECOVERY_DIRECTORY
        if recovery_dir.exists() and (
            _is_link_like(recovery_dir) or not recovery_dir.is_dir()
        ):
            raise SupervisorRecoveryError("torn-tail evidence directory is invalid")
        recovery_dir.mkdir(mode=0o700, exist_ok=True)
        try:
            _fsync_directory(directory)
            _fsync_directory(recovery_dir)
        except OSError as error:
            raise SupervisorRecoveryError(
                f"cannot persist torn-tail evidence directory: {error}"
            ) from error
        evidence_path = recovery_dir / (
            str(receipt["record_id"]).removeprefix("sha256:") + ".json"
        )
        _exclusive_canonical_write(evidence_path, receipt)
        # Build the complete replacement before the source journal loses a byte.
        # A crash therefore leaves either the original torn journal or a complete
        # recovery transaction, never a deceptively clean unjournaled truncation.
        frontier = replay.current_frontier or initial
        epoch = replay.max_epoch + 1
        transaction_id = _transaction_id(
            execution_id,
            execution_namespace,
            plan_fingerprint,
            epoch,
            replay.last_event_id,
        )
        lease_event = _make_event(
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            state="LEASE_ACQUIRED",
            transaction_id=transaction_id,
            previous_event_id=replay.last_event_id,
            recorded_at=clock(),
            payload={
                "epoch": epoch,
                "frontier_id": frontier,
                "resumed": replay.last_event_id is not None,
                "previous_transaction_closed": (
                    replay.active_transaction_id is None or replay.transaction_closed
                ),
            },
        )
        replay = _replay_events(
            (*replay.events, lease_event),
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
        relative_evidence = evidence_path.relative_to(directory).as_posix()
        recovery_event = _make_event(
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            state="TORN_TAIL_RECOVERED",
            transaction_id=transaction_id,
            previous_event_id=replay.last_event_id,
            recorded_at=clock(),
            payload={
                "epoch": epoch,
                "actor": actor,
                "reason": reason,
                "tail_digest": torn.tail_digest,
                "tail_bytes": len(torn.tail),
                "evidence_file": relative_evidence,
            },
        )
        replay = _replay_events(
            (*replay.events, recovery_event),
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
        release_event = _make_event(
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
            state="LEASE_RELEASED",
            transaction_id=transaction_id,
            previous_event_id=replay.last_event_id,
            recorded_at=clock(),
            payload={
                "epoch": epoch,
                "disposition": StepDisposition.RECOVERY_REQUIRED.value,
            },
        )
        replay = _replay_events(
            (*replay.events, release_event),
            execution_id=execution_id,
            execution_namespace=execution_namespace,
            plan_fingerprint=plan_fingerprint,
        )
        replacement = torn.valid_prefix + b"".join(
            _canonical(event) + b"\n"
            for event in (lease_event, recovery_event, release_event)
        )
        # Evidence is durable before this one atomic journal installation.
        _replace_with_prefix(journal_path, replacement)
        _validate_recovery_receipts(
            directory, replay, plan_fingerprint=plan_fingerprint
        )
        return TornTailRecoveryReceipt(
            epoch=epoch,
            transaction_id=transaction_id,
            tail_digest=torn.tail_digest,
            tail_bytes=len(torn.tail),
            evidence_path=evidence_path,
            journal_event_id=str(recovery_event["event_id"]),
        )


__all__ = [
    "FixedPointEvidence",
    "FixedPointVerificationRequest",
    "FixedPointVerifier",
    "HostCapability",
    "ObserverCallback",
    "ObserverContext",
    "ObserverResult",
    "StepContext",
    "StepDisposition",
    "StepResult",
    "SupervisorAuthenticationError",
    "SupervisorContractError",
    "SupervisorError",
    "SupervisorJournalError",
    "SupervisorLeaseHeld",
    "SupervisorRecoveryError",
    "SupervisorResult",
    "TornJournalTail",
    "TornTailRecoveryReceipt",
    "WaitCondition",
    "WaitObservationVerificationRequest",
    "WaitObservationVerifier",
    "reconcile_unknown_attempt",
    "recover_torn_tail",
    "run_to_fixed_point",
]
