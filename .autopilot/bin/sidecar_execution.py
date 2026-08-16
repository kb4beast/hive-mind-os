"""Token-aware planning and durable settlement for ephemeral execution sidecars.

Sidecars accelerate a durable primary task. They are not DAG nodes and never carry
claim, write, receipt, validation-lease, publication, or judgment authority.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Sequence

from controller import (
    ConfigurationError,
    assert_execution_authority_open,
    ensure_repository_runtime_identity,
    read_strict_canonical_json,
    require_execution_authority_dir,
    resolve_repository_state_dir,
    runtime_file_lock,
    runtime_file_lock_is_held,
)

SIDECAR_KINDS = frozenset(
    {"bounded_read_only_research", "independent_review", "non_blocking_validation"}
)
ACTIVE_SIDECAR_STATES = frozenset({"PREPARED", "BOUND", "ACTIVE", "ATTENTION_ACKNOWLEDGED"})
TERMINAL_SIDECAR_STATES = frozenset(
    {
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "SPAWN_FAILED",
        "SKIPPED_CAPACITY",
        "ORPHANED",
    }
)
INITIALIZATION_LOCK_NAME = "authority-ledger-initialization.lock"
DIGEST_TEXT = re.compile(r"sha256:[0-9a-f]{64}")

_SIDECAR_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "sidecar_id",
        "state",
        "previous_event_id",
        "recorded_at",
        "event_id",
    }
)
_SIDECAR_LEGACY_AUTHORITY_FIELDS = frozenset(
    {
        "parent_launch_instruction_id",
        "parent_sidecar_id",
        "parent_resource_key",
        "parent_authority_epoch",
        "parent_authority_class",
        "parent_dispatcher_release_id",
        "parent_dispatcher_admission_epoch",
        "host_reservation_id",
        "capacity_host_id",
        "capacity_generation",
        "capacity_epoch",
        "reservation_expires_at",
    }
)
_SIDECAR_ADAPTER_FIELDS = frozenset(
    {
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
    }
)
_SIDECAR_AUTHORITY_FIELDS = (
    _SIDECAR_LEGACY_AUTHORITY_FIELDS | _SIDECAR_ADAPTER_FIELDS
)
_SIDECAR_BINDING_FIELDS = frozenset(
    {
        "spec_digest",
        "token_budget_reserved",
        "host_id",
        "sidecar_task_id",
        "cursor",
        "capability_digest",
        "parent_spawn_message_id",
    }
)
_SIDECAR_PROGRESS_FIELDS = frozenset(
    {
        "host_event_id",
        "host_event_cursor",
        "message_id",
        "descendant_request",
    }
)
_SIDECAR_TERMINAL_FIELDS = frozenset(
    {
        "result",
        "parent_terminal_message_id",
        "close_reason",
        "error",
        "reason",
        "admission_code",
    }
)
_SIDECAR_ORPHAN_FIELDS = frozenset(
    {
        "recovery_actor",
        "recovery_reason",
        "orphaned_parent_event_id",
        "external_cancellation",
    }
)
_SIDECAR_ALLOWED_BY_STATE = {
    "PREPARED": _SIDECAR_ENVELOPE_FIELDS | _SIDECAR_AUTHORITY_FIELDS | {
        "spec_digest",
        "token_budget_reserved",
    },
    "BOUND": _SIDECAR_ENVELOPE_FIELDS | _SIDECAR_AUTHORITY_FIELDS | _SIDECAR_BINDING_FIELDS,
    "ACTIVE": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | _SIDECAR_BINDING_FIELDS
        | _SIDECAR_PROGRESS_FIELDS
    ),
    "ATTENTION_ACKNOWLEDGED": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | _SIDECAR_BINDING_FIELDS
        | _SIDECAR_PROGRESS_FIELDS
    ),
    "SUCCEEDED": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | _SIDECAR_BINDING_FIELDS
        | _SIDECAR_PROGRESS_FIELDS
        | _SIDECAR_TERMINAL_FIELDS
    ),
    "FAILED": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | _SIDECAR_BINDING_FIELDS
        | _SIDECAR_PROGRESS_FIELDS
        | _SIDECAR_TERMINAL_FIELDS
    ),
    "CANCELLED": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | _SIDECAR_BINDING_FIELDS
        | _SIDECAR_PROGRESS_FIELDS
        | _SIDECAR_TERMINAL_FIELDS
    ),
    "SPAWN_FAILED": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | _SIDECAR_BINDING_FIELDS
        | _SIDECAR_TERMINAL_FIELDS
    ),
    "SKIPPED_CAPACITY": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | {"spec_digest", "token_budget_reserved"}
        | _SIDECAR_TERMINAL_FIELDS
    ),
    "ORPHANED": (
        _SIDECAR_ENVELOPE_FIELDS
        | _SIDECAR_AUTHORITY_FIELDS
        | _SIDECAR_BINDING_FIELDS
        | _SIDECAR_PROGRESS_FIELDS
        | _SIDECAR_TERMINAL_FIELDS
        | _SIDECAR_ORPHAN_FIELDS
    ),
}
_LEGACY_SIDECAR_ALLOWED_BY_STATE = {
    state: (fields - _SIDECAR_AUTHORITY_FIELDS) | _SIDECAR_LEGACY_AUTHORITY_FIELDS
    for state, fields in _SIDECAR_ALLOWED_BY_STATE.items()
}


class SidecarPolicyError(ValueError):
    """A sidecar policy, specification, or durable event is unsafe."""


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _reject_duplicate_pairs(
    pairs: Sequence[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> object:
    raise ValueError(f"non-finite JSON constant {value}")


def _finite_json(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _finite_json(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_finite_json(item) for item in value)
    return value is None or type(value) in {str, int, bool}


def _strict_event(line: str, index: int) -> Mapping[str, object]:
    try:
        event = json.loads(
            line,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise SidecarPolicyError(f"sidecar ledger line {index} is invalid") from error
    if not isinstance(event, Mapping):
        raise SidecarPolicyError(f"sidecar ledger line {index} must be an object")
    if not _finite_json(event):
        raise SidecarPolicyError(f"sidecar ledger line {index} contains non-finite JSON")
    try:
        canonical_line = json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as error:
        raise SidecarPolicyError(f"sidecar ledger line {index} is not canonical JSON") from error
    if line != canonical_line:
        raise SidecarPolicyError(
            f"sidecar ledger line {index} uses a noncanonical encoding"
        )
    return event


def _validate_event_schema(event: Mapping[str, object], index: int | str) -> None:
    state = event.get("state")
    if not isinstance(state, str) or state not in _SIDECAR_ALLOWED_BY_STATE:
        raise SidecarPolicyError(f"sidecar ledger line {index} has an invalid state")
    has_adapter_identity = _SIDECAR_ADAPTER_FIELDS.issubset(event)
    has_partial_adapter_identity = bool(_SIDECAR_ADAPTER_FIELDS.intersection(event))
    if has_partial_adapter_identity and not has_adapter_identity:
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has partial adapter provenance"
        )
    allowed = (
        _SIDECAR_ALLOWED_BY_STATE[state]
        if has_adapter_identity
        else _LEGACY_SIDECAR_ALLOWED_BY_STATE[state]
    )
    unexpected = sorted(set(event) - allowed)
    if unexpected:
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has unexpected {state} fields: "
            + ", ".join(unexpected)
        )
    required = _SIDECAR_ENVELOPE_FIELDS | (
        _SIDECAR_AUTHORITY_FIELDS
        if has_adapter_identity
        else _SIDECAR_LEGACY_AUTHORITY_FIELDS
    )
    if state == "SKIPPED_CAPACITY":
        # Admission lost the aggregate host-capacity race, so no reservation
        # exists.  The denial still binds the exact capacity generation and
        # parent authority under which it was observed.
        required -= {"host_reservation_id"}
    if state == "ORPHANED":
        required |= _SIDECAR_ORPHAN_FIELDS | {"parent_launch_instruction_id"}
    missing = sorted(required - set(event))
    if missing:
        raise SidecarPolicyError(
            f"sidecar ledger line {index} lacks required {state} fields: "
            + ", ".join(missing)
        )
    if event.get("schema_version") != 1 or event.get("kind") != "hive-mind-sidecar-ledger-event-v1":
        raise SidecarPolicyError(f"sidecar ledger line {index} has an invalid schema")
    for field in ("sidecar_id", "event_id"):
        value = event.get(field)
        if not isinstance(value, str) or DIGEST_TEXT.fullmatch(value) is None:
            raise SidecarPolicyError(f"sidecar ledger line {index} has invalid {field}")
    previous = event.get("previous_event_id")
    if previous is not None and (
        not isinstance(previous, str) or DIGEST_TEXT.fullmatch(previous) is None
    ):
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has invalid previous_event_id"
        )
    if not isinstance(event.get("recorded_at"), str):
        raise SidecarPolicyError(f"sidecar ledger line {index} has invalid recorded_at")
    required_by_state = {
        "PREPARED": {"parent_launch_instruction_id"},
        "BOUND": {
            "parent_launch_instruction_id",
            "host_id",
            "sidecar_task_id",
            "cursor",
            "capability_digest",
        },
        "ACTIVE": {"parent_launch_instruction_id", "host_id", "sidecar_task_id"},
        "ATTENTION_ACKNOWLEDGED": {
            "parent_launch_instruction_id",
            "host_id",
            "sidecar_task_id",
            "host_event_id",
            "host_event_cursor",
            "message_id",
        },
        "SUCCEEDED": {"parent_launch_instruction_id"},
        "FAILED": {"parent_launch_instruction_id"},
        "CANCELLED": {"parent_launch_instruction_id"},
        "SPAWN_FAILED": {"parent_launch_instruction_id", "error"},
        "SKIPPED_CAPACITY": {
            "parent_launch_instruction_id",
            "spec_digest",
            "token_budget_reserved",
            "admission_code",
            "reason",
        },
        "ORPHANED": _SIDECAR_ORPHAN_FIELDS | {"parent_launch_instruction_id"},
    }[state]
    missing_state = sorted(required_by_state - set(event))
    if missing_state:
        raise SidecarPolicyError(
            f"sidecar ledger line {index} lacks required {state} fields: "
            + ", ".join(missing_state)
        )
    parent_id = event.get("parent_launch_instruction_id")
    if parent_id is not None and (
        not isinstance(parent_id, str) or DIGEST_TEXT.fullmatch(parent_id) is None
    ):
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has invalid parent launch identity"
        )
    epoch = event.get("parent_authority_epoch")
    if epoch is not None and (type(epoch) is not int or epoch < 1):
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has invalid parent authority epoch"
        )
    dispatch_epoch = event.get("parent_dispatcher_admission_epoch")
    if dispatch_epoch is not None and (
        type(dispatch_epoch) is not int or dispatch_epoch < 1
    ):
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has invalid dispatcher admission epoch"
        )
    authority_class = event.get("parent_authority_class")
    if authority_class not in {"PREPARATION_ONLY", "WRITE_AUTHORIZED"}:
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has invalid parent authority class"
        )
    release_id = event.get("parent_dispatcher_release_id")
    if authority_class == "WRITE_AUTHORIZED":
        if (
            not isinstance(release_id, str)
            or DIGEST_TEXT.fullmatch(release_id) is None
            or type(dispatch_epoch) is not int
            or dispatch_epoch < 1
        ):
            raise SidecarPolicyError(
                f"sidecar ledger line {index} lacks exact parent dispatcher authority"
            )
    elif release_id is not None or dispatch_epoch is not None:
        raise SidecarPolicyError(
            f"sidecar ledger line {index} gives preparation parent dispatcher authority"
        )
    for digest_field in ("host_reservation_id", "capacity_generation"):
        value = event.get(digest_field)
        if state == "SKIPPED_CAPACITY" and digest_field == "host_reservation_id":
            if value is not None:
                raise SidecarPolicyError(
                    f"sidecar ledger line {index} fabricates a denied reservation"
                )
            continue
        if not isinstance(value, str) or DIGEST_TEXT.fullmatch(value) is None:
            raise SidecarPolicyError(
                f"sidecar ledger line {index} has invalid {digest_field}"
            )
    if (
        not isinstance(event.get("capacity_host_id"), str)
        or not str(event.get("capacity_host_id")).strip()
        or type(event.get("capacity_epoch")) is not int
        or int(event["capacity_epoch"]) < 1
        or not isinstance(event.get("reservation_expires_at"), str)
        or not str(event.get("reservation_expires_at")).strip()
    ):
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has invalid host capacity fence"
        )
    if has_adapter_identity:
        for digest_field in (
            "host_kernel_generation",
            "execution_adapter_identity_record_id",
            "execution_adapter_identity_blob_digest",
        ):
            value = event.get(digest_field)
            if not isinstance(value, str) or DIGEST_TEXT.fullmatch(value) is None:
                raise SidecarPolicyError(
                    f"sidecar ledger line {index} has invalid {digest_field}"
                )
        adapter_record_id = str(event["execution_adapter_identity_record_id"])
        if event.get("execution_adapter_identity_path") != (
            "execution-adapter-bindings/"
            + adapter_record_id.removeprefix("sha256:")
            + ".json"
        ):
            raise SidecarPolicyError(
                f"sidecar ledger line {index} has invalid execution adapter evidence path"
            )
    if state == "ORPHANED":
        if event.get("external_cancellation") != "NOT_CLAIMED":
            raise SidecarPolicyError(
                f"sidecar ledger line {index} overclaims external cancellation"
            )
        for field in ("recovery_actor", "recovery_reason", "orphaned_parent_event_id"):
            value = event.get(field)
            if not isinstance(value, str) or not value.strip():
                raise SidecarPolicyError(
                    f"sidecar ledger line {index} has invalid orphan provenance"
                )
    if state == "SKIPPED_CAPACITY" and event.get("admission_code") != "ADMISSION_DENIED":
        raise SidecarPolicyError(
            f"sidecar ledger line {index} has invalid capacity-denial provenance"
        )


def _validate_sidecar_replay(events: Sequence[Mapping[str, object]]) -> None:
    latest: dict[str, Mapping[str, object]] = {}
    immutable = _SIDECAR_AUTHORITY_FIELDS | _SIDECAR_BINDING_FIELDS
    legal = {
        "PREPARED": {"BOUND", "SPAWN_FAILED", "FAILED", "CANCELLED", "ORPHANED"},
        "BOUND": {
            "ACTIVE",
            "ATTENTION_ACKNOWLEDGED",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "ORPHANED",
        },
        "ACTIVE": {
            "ACTIVE",
            "ATTENTION_ACKNOWLEDGED",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "ORPHANED",
        },
        "ATTENTION_ACKNOWLEDGED": {
            "ACTIVE",
            "ATTENTION_ACKNOWLEDGED",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "ORPHANED",
        },
        "SUCCEEDED": set(),
        "FAILED": set(),
        "CANCELLED": set(),
        "SPAWN_FAILED": set(),
        "SKIPPED_CAPACITY": set(),
        "ORPHANED": set(),
    }
    for index, event in enumerate(events, 1):
        sidecar_id = str(event["sidecar_id"])
        prior = latest.get(sidecar_id)
        if prior is None:
            if event.get("state") not in {"PREPARED", "SKIPPED_CAPACITY"}:
                raise SidecarPolicyError(
                    f"sidecar ledger line {index} has no admission ancestry"
                )
        else:
            prior_state = str(prior["state"])
            state = str(event["state"])
            if state not in legal[prior_state]:
                raise SidecarPolicyError(
                    f"sidecar ledger line {index} has impossible {prior_state} -> {state} transition"
                )
            if _SIDECAR_ADAPTER_FIELDS.issubset(prior) != _SIDECAR_ADAPTER_FIELDS.issubset(
                event
            ):
                raise SidecarPolicyError(
                    f"sidecar ledger line {index} changes adapter provenance schema"
                )
            for field in immutable:
                if prior.get(field) is not None and prior.get(field) != event.get(field):
                    raise SidecarPolicyError(
                        f"sidecar ledger line {index} mutates immutable {field}"
                    )
        latest[sidecar_id] = event


def _managed(
    repo_root: Path,
    state_dir: str | Path | None,
    *parts: str,
) -> Path:
    try:
        root = _authority_state_root(repo_root, state_dir)
    except ConfigurationError as error:
        raise SidecarPolicyError(str(error)) from error
    current = root
    for part in parts:
        current /= part
        is_junction = getattr(current, "is_junction", None)
        if current.is_symlink() or (callable(is_junction) and is_junction()):
            raise SidecarPolicyError(f"sidecar state path uses a link: {current}")
        if current.exists() and not current.resolve().is_relative_to(root):
            raise SidecarPolicyError(f"sidecar state path escapes runtime state: {current}")
    return current


def _authority_state_root(
    repo_root: Path,
    state_dir: str | Path | None,
) -> Path:
    coordination = resolve_repository_state_dir(repo_root)
    if state_dir is None:
        if (coordination / "runtime-authority-ready.json").is_file():
            raise SidecarPolicyError(
                "runtime READY requires an explicit authenticated execution directory"
            )
        return coordination
    supplied = Path(os.path.abspath(os.fspath(state_dir))).absolute()
    if supplied == coordination:
        if (coordination / "runtime-authority-ready.json").is_file():
            raise SidecarPolicyError(
                "repository-global sidecar authority is retired after runtime READY"
            )
        return coordination
    # Namespace directories intentionally use compact digest segments to keep
    # Windows authority paths bounded.  The strict identity inside the
    # canonical executions directory supplies the full digest for the
    # controller verifier; the path segment is never authority by itself.
    executions_root = (coordination / "executions").resolve()
    if supplied.parent == executions_root:
        try:
            identity = read_strict_canonical_json(
                supplied / "execution-identity.json",
                label="execution authority identity",
            )
            execution_id = (
                identity.get("execution_id") if isinstance(identity, Mapping) else None
            )
            if not isinstance(execution_id, str):
                raise ConfigurationError("execution authority identity has no execution id")
            return require_execution_authority_dir(
                repo_root,
                supplied,
                execution_id=execution_id,
            )
        except ConfigurationError as error:
            raise SidecarPolicyError(str(error)) from error
    try:
        return resolve_repository_state_dir(repo_root, supplied)
    except ConfigurationError as error:
        raise SidecarPolicyError(str(error)) from error


def _explicit_execution_dir(
    repo_root: Path,
    *,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str | None = None,
) -> Path:
    try:
        return require_execution_authority_dir(
            repo_root,
            execution_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
        )
    except ConfigurationError as error:
        raise SidecarPolicyError(str(error)) from error


@contextmanager
def _ledger_lock(
    repo_root: Path,
    state_dir: str | Path | None = None,
    *,
    for_write: bool = False,
) -> Iterator[None]:
    directory = _authority_state_root(repo_root, state_dir)
    try:
        identity = ensure_repository_runtime_identity(
            repo_root, resolve_repository_state_dir(repo_root), create=False
        )
    except ConfigurationError as error:
        raise SidecarPolicyError(str(error)) from error
    ledger_path = _managed(repo_root, directory, "sidecar-bindings.jsonl")
    lock_path = _managed(repo_root, directory, "locks", "sidecar-bindings.lock")
    initialization_path = _managed(
        repo_root,
        directory,
        "locks",
        INITIALIZATION_LOCK_NAME,
    )
    if not for_write and not lock_path.is_file():
        raise SidecarPolicyError(
            "sidecar binding lock is absent; run an explicit authority migration"
        )
    if identity is not None and (
        not lock_path.is_file() or not initialization_path.is_file()
    ):
        raise SidecarPolicyError(
            "sidecar authority is uninitialized; run runtime-authority-migrate"
        )
    is_execution = directory != resolve_repository_state_dir(repo_root)
    if for_write and is_execution:
        dispatcher_lock = directory / "locks" / "dispatcher-admission.lock"
        if not runtime_file_lock_is_held(dispatcher_lock):
            raise SidecarPolicyError(
                "sidecar mutation requires caller-held dispatcher authority"
            )
    try:
        if for_write and not ledger_path.exists() and not is_execution:
            with runtime_file_lock(initialization_path):
                with runtime_file_lock(lock_path):
                    if is_execution:
                        assert_execution_authority_open(directory)
                    yield
        else:
            with runtime_file_lock(lock_path):
                if for_write and is_execution:
                    assert_execution_authority_open(directory)
                yield
    except ConfigurationError as error:
        raise SidecarPolicyError(str(error)) from error


def _events_unlocked(
    repo_root: Path,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    path = _managed(repo_root, state_dir, "sidecar-bindings.jsonl")
    if not path.exists():
        return ()
    previous: str | None = None
    events: list[Mapping[str, object]] = []
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise SidecarPolicyError(f"cannot read sidecar ledger: {error}") from error
    if raw and not raw.endswith(b"\n"):
        raise SidecarPolicyError(
            "sidecar ledger has an unterminated final record; explicit torn-tail "
            "recovery is required"
        )
    lines = text.splitlines()
    for index, line in enumerate(lines, 1):
        event = _strict_event(line, index)
        _validate_event_schema(event, index)
        material = dict(event)
        event_id = material.pop("event_id", None)
        if material.get("previous_event_id") != previous:
            raise SidecarPolicyError(f"sidecar ledger line {index} breaks the hash chain")
        expected = "sha256:" + sha256(_canonical(material)).hexdigest()
        if event_id != expected:
            raise SidecarPolicyError(f"sidecar ledger line {index} has an invalid digest")
        previous = str(event_id)
        events.append(event)
    _validate_sidecar_replay(events)
    return tuple(events)


def sidecar_events(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    directory = _authority_state_root(repo_root, state_dir)
    path = _managed(repo_root, state_dir, "sidecar-bindings.jsonl")
    if path.exists():
        with _ledger_lock(repo_root, state_dir):
            return _events_unlocked(repo_root, state_dir)
    # Execution ledgers and their locks are installed by the explicit namespace
    # transaction.  An absent ledger is an authenticated empty store and must not
    # reacquire the lower-ranked repository initialization barrier while a caller
    # holds task-binding authority.
    if directory != resolve_repository_state_dir(repo_root):
        with _ledger_lock(repo_root, state_dir):
            return _events_unlocked(repo_root, state_dir)
    initialization_path = _managed(
        repo_root,
        state_dir,
        "locks",
        INITIALIZATION_LOCK_NAME,
    )
    if not initialization_path.is_file():
        return ()
    try:
        with runtime_file_lock(initialization_path):
            if not path.exists():
                return ()
            with _ledger_lock(repo_root, state_dir):
                return _events_unlocked(repo_root, state_dir)
    except ConfigurationError as error:
        raise SidecarPolicyError(str(error)) from error


def _append(
    repo_root: Path,
    value: Mapping[str, object],
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    with _ledger_lock(repo_root, state_dir, for_write=True):
        events = _events_unlocked(repo_root, state_dir)
        return _append_unlocked(repo_root, value, events, state_dir)


def _append_unlocked(
    repo_root: Path,
    value: Mapping[str, object],
    events: Sequence[Mapping[str, object]],
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    material = {
        "schema_version": 1,
        **dict(value),
        "previous_event_id": events[-1]["event_id"] if events else None,
        "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    event = {**material, "event_id": "sha256:" + sha256(_canonical(material)).hexdigest()}
    _validate_event_schema(event, "new")
    path = _managed(repo_root, state_dir, "sidecar-bindings.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def latest_sidecars(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> dict[str, Mapping[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for event in sidecar_events(repo_root, state_dir=state_dir):
        sidecar_id = event.get("sidecar_id")
        if isinstance(sidecar_id, str):
            latest[sidecar_id] = event
    return latest


def active_sidecars(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    latest = latest_sidecars(repo_root, state_dir=state_dir)
    return tuple(
        latest[key]
        for key in sorted(latest)
        if latest[key].get("state") in ACTIVE_SIDECAR_STATES
    )


def record_sidecar_state(
    repo_root: Path,
    sidecar_id: str,
    state: str,
    *,
    state_dir: str | Path | None = None,
    **fields: object,
) -> Mapping[str, object]:
    if state not in ACTIVE_SIDECAR_STATES | TERMINAL_SIDECAR_STATES:
        raise SidecarPolicyError("invalid sidecar state")
    with _ledger_lock(repo_root, state_dir, for_write=True):
        events = _events_unlocked(repo_root, state_dir)
        prior = next(
            (event for event in reversed(events) if event.get("sidecar_id") == sidecar_id),
            None,
        )
        if prior is None and state not in {"PREPARED", "SKIPPED_CAPACITY"}:
            raise SidecarPolicyError(
                "sidecar must begin with PREPARED or denied-admission evidence"
            )
        if prior is not None and prior.get("state") in TERMINAL_SIDECAR_STATES:
            if prior.get("state") == state and all(prior.get(key) == value for key, value in fields.items()):
                return prior
            raise SidecarPolicyError("terminal sidecar state cannot regress or change")
        inherited = (
            {
                key: value
                for key, value in prior.items()
                if key
                not in {
                    "schema_version",
                    "kind",
                    "sidecar_id",
                    "state",
                    "previous_event_id",
                    "recorded_at",
                    "event_id",
                }
            }
            if prior is not None
            else {}
        )
        return _append_unlocked(
            repo_root,
            {
                "kind": "hive-mind-sidecar-ledger-event-v1",
                "sidecar_id": sidecar_id,
                "state": state,
                **inherited,
                **fields,
            },
            events,
            state_dir,
        )


def orphan_sidecar_obligations(
    repo_root: Path,
    active_parent_launch_ids: Sequence[str],
    *,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Return active sidecars whose durable parent launch is no longer active.

    The caller owns the task-binding lock before entering this function.  This
    module never imports orchestration, preserving the single binding -> sidecar
    lock order and avoiding a circular authority dependency.
    """

    active_parents = frozenset(active_parent_launch_ids)
    return tuple(
        event
        for event in active_sidecars(repo_root, state_dir=state_dir)
        if event.get("parent_launch_instruction_id") not in active_parents
    )


def fence_orphaned_sidecars(
    repo_root: Path,
    active_parent_launch_ids: Sequence[str],
    *,
    actor: str,
    reason: str,
    orphaned_parent_events: Mapping[str, str] | None = None,
    limit: int | None = None,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Append terminal ORPHANED evidence without claiming host cancellation.

    This is an administrative repository-state transition.  It deliberately
    does not call a host adapter: a stale external process may still exist, but
    its parent launch fence prevents it from performing repository effects.
    """

    if not actor.strip() or not reason.strip():
        raise SidecarPolicyError("orphan recovery requires actor and reason")
    if limit is not None and (type(limit) is not int or limit < 0):
        raise SidecarPolicyError("orphan recovery limit must be a nonnegative integer")
    active_parents = frozenset(active_parent_launch_ids)
    parent_events = dict(orphaned_parent_events or {})
    recovered: list[Mapping[str, object]] = []
    with _ledger_lock(repo_root, state_dir, for_write=True):
        events = list(_events_unlocked(repo_root, state_dir))
        latest: dict[str, Mapping[str, object]] = {}
        history: dict[str, list[Mapping[str, object]]] = {}
        for event in events:
            sidecar_id = str(event["sidecar_id"])
            latest[sidecar_id] = event
            history.setdefault(sidecar_id, []).append(event)
        candidates = [
            latest[key]
            for key in sorted(latest)
            if latest[key].get("state") in ACTIVE_SIDECAR_STATES
            and latest[key].get("parent_launch_instruction_id") not in active_parents
        ]
        if limit is not None:
            candidates = candidates[:limit]
        preserve_fields = (
            _SIDECAR_AUTHORITY_FIELDS
            | _SIDECAR_BINDING_FIELDS
            | _SIDECAR_PROGRESS_FIELDS
            | _SIDECAR_TERMINAL_FIELDS
        )
        for prior in candidates:
            sidecar_id = str(prior["sidecar_id"])
            aggregate: dict[str, object] = {}
            for historical in history[sidecar_id]:
                for field in preserve_fields:
                    if field in historical and historical[field] is not None:
                        aggregate[field] = historical[field]
            parent_id = aggregate.get("parent_launch_instruction_id")
            if not isinstance(parent_id, str) or DIGEST_TEXT.fullmatch(parent_id) is None:
                raise SidecarPolicyError(
                    f"active sidecar {sidecar_id} has no exact parent launch identity"
                )
            parent_event_id = parent_events.get(parent_id)
            if not isinstance(parent_event_id, str) or DIGEST_TEXT.fullmatch(parent_event_id) is None:
                raise SidecarPolicyError(
                    f"orphan sidecar {sidecar_id} lacks the exact terminal parent event"
                )
            event = _append_unlocked(
                repo_root,
                {
                    "kind": "hive-mind-sidecar-ledger-event-v1",
                    "sidecar_id": sidecar_id,
                    "state": "ORPHANED",
                    **aggregate,
                    "recovery_actor": actor,
                    "recovery_reason": reason,
                    "orphaned_parent_event_id": parent_event_id,
                    "external_cancellation": "NOT_CLAIMED",
                },
                events,
                state_dir,
            )
            events.append(event)
            recovered.append(event)
    return tuple(recovered)


def validate_sidecar_policy(value: object) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ("sidecars must be an object",)
    issues: list[str] = []
    flags = {
        "enabled": True,
        "root_mediates_descendants": True,
        "primary_authority_inheritance": False,
        "require_parent_ack": True,
        "close_descendants_before_parent_terminal": True,
    }
    for field, expected in flags.items():
        if value.get(field) is not expected:
            issues.append(f"sidecars.{field} must be {str(expected).lower()}")
    allowed = value.get("allowed_purposes")
    if not isinstance(allowed, list) or set(allowed) != set(SIDECAR_KINDS):
        issues.append("sidecar allowed_purposes must contain the three bounded purposes")
    minima = {
        "max_depth": 1, "max_sidecars_per_primary": 1, "max_total_sidecars": 1,
        "total_token_budget": 1, "per_sidecar_token_budget": 1, "max_result_tokens": 1,
        "coordination_overhead_tokens": 0, "min_net_savings_tokens": 1,
        "max_no_progress_cycles": 1, "max_poll_cycles": 1, "max_replay_events": 1,
        "wait_timeout_seconds": 1, "max_targets_per_wait": 1,
    }
    for field, minimum in minima.items():
        item = value.get(field)
        if type(item) is not int or item < minimum:
            issues.append(f"sidecars.{field} must be an integer >= {minimum}")
    if type(value.get("max_depth")) is int and int(value["max_depth"]) > 2:
        issues.append("sidecars.max_depth must be <= 2")
    if type(value.get("max_targets_per_wait")) is int and int(value["max_targets_per_wait"]) > 8:
        issues.append("sidecars.max_targets_per_wait must be <= 8")
    if type(value.get("per_sidecar_token_budget")) is int and type(value.get("total_token_budget")) is int:
        if int(value["per_sidecar_token_budget"]) > int(value["total_token_budget"]):
            issues.append("per-sidecar budget cannot exceed total budget")
    if type(value.get("max_sidecars_per_primary")) is int and type(value.get("max_total_sidecars")) is int:
        if int(value["max_sidecars_per_primary"]) > int(value["max_total_sidecars"]):
            issues.append("per-primary sidecar count cannot exceed cohort count")
    return tuple(issues)


def _candidate(parent_id: str, node_id: str, purpose: str, prompt: str, saved: int, policy: Mapping[str, object]) -> dict[str, object]:
    budget = int(policy["per_sidecar_token_budget"])
    result = int(policy["max_result_tokens"])
    overhead = int(policy["coordination_overhead_tokens"])
    material: dict[str, object] = {
        "schema_version": 1, "kind": "hive-mind-sidecar-spec-v1",
        "parent_launch_instruction_id": parent_id, "parent_sidecar_id": None,
        "node_id": node_id, "depth": 1, "purpose": purpose, "prompt": prompt,
        "read_only": True, "token_budget": budget, "max_result_tokens": result,
        "estimated_parent_tokens_saved": saved, "estimated_coordination_tokens": overhead,
        "estimated_net_savings_tokens": saved - budget - result - overhead,
    }
    material["sidecar_id"] = "sha256:" + sha256(_canonical(material)).hexdigest()
    material["idempotency_key"] = material["sidecar_id"]
    return material


def make_descendant_spec(parent: Mapping[str, object], request: Mapping[str, object], policy: Mapping[str, object]) -> dict[str, object]:
    """Root-validate and authenticate a requested descendant; never let a child spawn."""
    if set(request) != {"purpose", "prompt", "evidence_refs"}:
        raise SidecarPolicyError("descendant request fields are invalid")
    purpose = request.get("purpose")
    prompt = request.get("prompt")
    evidence_refs = request.get("evidence_refs")
    if purpose not in SIDECAR_KINDS:
        raise SidecarPolicyError("descendant purpose is not allowed")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise SidecarPolicyError("descendant prompt is empty or oversized")
    if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(item, str) and item.strip() for item in evidence_refs):
        raise SidecarPolicyError("descendant request requires independently resolvable evidence")
    depth = int(parent["depth"]) + 1
    if depth > int(policy["max_depth"]):
        raise SidecarPolicyError("descendant depth exceeds policy")
    saved = {
        "bounded_read_only_research": 4_800,
        "independent_review": 5_200,
        "non_blocking_validation": 4_600,
    }[str(purpose)]
    spec = _candidate(
        str(parent["parent_launch_instruction_id"]), str(parent["node_id"]),
        str(purpose), prompt, saved, policy,
    )
    spec["parent_sidecar_id"] = parent["sidecar_id"]
    spec["depth"] = depth
    spec["request_evidence_refs"] = list(evidence_refs)
    # Re-authenticate after parent/depth/evidence are bound.
    material = dict(spec)
    material.pop("sidecar_id", None)
    material.pop("idempotency_key", None)
    spec["sidecar_id"] = "sha256:" + sha256(_canonical(material)).hexdigest()
    spec["idempotency_key"] = spec["sidecar_id"]
    return spec


def plan_sidecars(tasks: Sequence[Mapping[str, object]], nodes: Mapping[str, Mapping[str, object]], policy: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    issues = validate_sidecar_policy(policy)
    if issues:
        raise SidecarPolicyError("; ".join(issues))
    candidates: list[dict[str, object]] = []
    for task in tasks:
        parent_id = str(task.get("launch_instruction_id", ""))
        node_id = str(task.get("node_id") or task.get("task_key") or "UNKNOWN")
        node = nodes.get(node_id, {})
        read_scope = node.get("read_scope", [])
        evidence = node.get("evidence_requirements", [])
        scope_count = len(read_scope) if isinstance(read_scope, list) else 0
        evidence_count = len(evidence) if isinstance(evidence, list) else 0
        risk = str(node.get("risk", "moderate")).lower()
        if task.get("authority_mode") == "PREPARATION_ONLY" or scope_count >= 3:
            candidates.append(_candidate(parent_id, node_id, "bounded_read_only_research", f"Read-only sidecar for {node_id}. Inspect declared read scope; return compact findings, exact evidence, contradictions, and blockers. Never claim, write, commit, push, publish, run a global gate, or spawn directly.", 4_800 + 250 * min(scope_count, 8), policy))
        if risk in {"moderate", "high", "critical"} or evidence_count >= 3:
            saved = {"moderate": 5_200, "high": 6_600, "critical": 7_800}.get(risk, 5_400) + 150 * min(evidence_count, 8)
            candidates.append(_candidate(parent_id, node_id, "independent_review", f"Independent read-only review for {node_id}. Threat-model the work and return compact ranked findings with exact evidence. Never claim, write, approve or judge the parent, run a global gate, or spawn directly.", saved, policy))
    candidates.sort(key=lambda item: (-int(item["estimated_net_savings_tokens"]), str(item["sidecar_id"])))
    admitted: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    consumed = 0
    for item in candidates:
        parent = str(item["parent_launch_instruction_id"])
        budget = int(item["token_budget"])
        if int(item["estimated_net_savings_tokens"]) < int(policy["min_net_savings_tokens"]):
            continue
        if counts.get(parent, 0) >= int(policy["max_sidecars_per_primary"]):
            continue
        if len(admitted) >= int(policy["max_total_sidecars"]) or consumed + budget > int(policy["total_token_budget"]):
            continue
        admitted.append(item)
        counts[parent] = counts.get(parent, 0) + 1
        consumed += budget
    return tuple(sorted(admitted, key=lambda item: str(item["sidecar_id"])))


def sidecar_spec_digest(spec: Mapping[str, object]) -> str:
    material = dict(spec)
    material.pop("sidecar_id", None)
    material.pop("idempotency_key", None)
    return "sha256:" + sha256(_canonical(material)).hexdigest()
