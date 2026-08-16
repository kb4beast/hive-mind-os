"""Intent-aware, host-neutral orchestration contracts for Autopilot DAGs.

The deterministic controller owns repository truth.  This module translates that
truth into an executable host contract without pretending that a repository process
can directly control every supported chat/task host.  Host adapters consume the
contract and persist their task identifiers outside repository source files.
"""

from __future__ import annotations

import hmac
import json
import math
import os
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from controller import (
    ConfigurationError,
    assert_execution_authority_open,
    atomic_write_json,
    digest_json,
    ensure_repository_runtime_identity,
    exclusive_write_bytes_or_identical,
    read_strict_canonical_json,
    require_execution_authority_dir,
    resolve_host_runtime_dir,
    resolve_repository_state_dir,
    runtime_file_lock,
    runtime_file_lock_is_held,
)
from sidecar_execution import (
    active_sidecars,
    fence_orphaned_sidecars,
    plan_sidecars,
    validate_sidecar_policy,
)
from sidecar_execution import (
    orphan_sidecar_obligations as _sidecar_orphan_obligations,
)

INTENTS = ("BUILD_DAG", "START", "CONTINUE", "CHECK", "FINISH")
ACTIVE_STATES = {"CLAIMED", "RUNNING", "WAITING_FOR_RECEIPT", "PR_OPEN"}
RECOVERY_STATES = {
    "CI_FAILED",
    "REPAIR_REQUIRED",
    "RECONCILIATION_REQUIRED",
    "REPLAN_REQUIRED",
}
TERMINAL_STATES = {"COMPLETE", "SUPERSEDED", "CANCELLED", "QUARANTINED"}
SUCCESS_STATES = {"COMPLETE", "SUPERSEDED"}
BLOCKING_STATES = {
    "BLOCKED",
    "BOOTSTRAP_INVALID",
    "CANCELLED",
    "ESCALATION_REQUIRED",
    "QUARANTINED",
}
ACTIVE_BINDING_STATES = {
    "PREPARED",
    "CREATED",
    "BOUND",
    "HOST_EVENT_OBSERVED",
    "ATTENTION_ACKNOWLEDGED",
}
READY_STATES = {"READY", "INTEGRATION_READY", "PROMOTION_READY"}
SECRET_TEXT = re.compile(
    r"(?i)(?:\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|password)\b\s*[:=]\s*\S+|"
    r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}|\b(?:gh[oprsu]_|sk-)[A-Za-z0-9_-]{12,})"
)
DIGEST_TEXT = re.compile(r"sha256:[0-9a-f]{64}")
_CONTROL_PLANE_FIELDS = frozenset(
    {
        "bootstrap_completion",
        "default_claim_lease_minutes",
        "max_consultation_rounds",
        "plan_fingerprint",
        "plan_id",
        "prohibitions",
        "schema_version",
        "orchestration_policy_file",
        "source_of_truth",
        "target",
        "verify_git_objects",
        "workflow_policy_file",
    }
)
_PLAN_FIELDS = frozenset(
    {
        "baseline",
        "created_at",
        "nodes",
        "plan_fingerprint",
        "plan_id",
        "schema_version",
        "state_machine",
        "subject",
        "title",
    }
)
_ORCHESTRATION_POLICY_FIELDS = frozenset(
    {
        "closure_first",
        "host_adapters",
        "host_executor",
        "intent",
        "kind",
        "polling",
        "parallel_task_cohort",
        "recovery",
        "schema_version",
        "sidecars",
        "task_transport",
        "wave",
    }
)
AUTHORITY_CLASSES = frozenset({"PREPARATION_ONLY", "WRITE_AUTHORIZED"})
# One attended repository runtime may own at most eight host sessions in total.
# Keep the older name as a compatibility alias for callers that still describe
# the primary-only portion of the cohort.
MAX_HOST_TASKS = 8
MAX_PRIMARY_TASKS = MAX_HOST_TASKS
AUTHORITY_METADATA_FIELDS = (
    "target_sha",
    "plan_fingerprint",
    "target_branch",
    "authority_class",
)
LAUNCH_IDENTITY_FIELDS = (
    "execution_id",
    "execution_namespace",
    "repository",
    "node_id",
    "lifecycle",
    "branch",
    *AUTHORITY_METADATA_FIELDS,
)
FULL_GIT_SHA = re.compile(r"[0-9a-f]{40}")

_BINDING_ENVELOPE_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "launch_instruction_id",
        "previous_event_id",
        "recorded_at",
        "event_id",
        "state",
    }
)
_BINDING_IDENTITY_FIELDS = frozenset(
    {
        "resource_key",
        "authority_epoch",
        "execution_id",
        "execution_namespace",
        "repository",
        "node_id",
        "lifecycle",
        "branch",
        "target_sha",
        "plan_fingerprint",
        "target_branch",
        "authority_class",
        "dispatcher_release_id",
        "dispatcher_admission_epoch",
        "host_reservation_id",
        "capacity_host_id",
        "capacity_generation",
        "capacity_epoch",
        "reservation_expires_at",
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
    }
)
_BINDING_RETRY_FIELDS = frozenset({"host", "attempt", "retry_of"})
_BINDING_HOST_FIELDS = frozenset(
    {"host_id", "task_id", "cursor", "capability_digest"}
)
_BINDING_PROGRESS_FIELDS = frozenset(
    {"host_state", "host_event_id", "host_event_cursor", "message_id"}
)
_BINDING_TERMINAL_FIELDS = frozenset(
    {"terminal_state", "observed_by", "reason"}
)
_BINDING_FENCE_FIELDS = frozenset(
    {"superseded_by", "superseded_by_actor", "reason"}
)
_BINDING_CAPACITY_FIELDS = frozenset(
    {
        "host_reservation_id",
        "capacity_host_id",
        "capacity_generation",
        "capacity_epoch",
        "reservation_expires_at",
    }
)
_BINDING_ADAPTER_FIELDS = frozenset(
    {
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_path",
        "execution_adapter_identity_blob_digest",
    }
)
_BINDING_EXECUTION_FIELDS = frozenset(
    {"execution_id", "execution_namespace"}
)
_PRE_ADAPTER_BINDING_IDENTITY_FIELDS = (
    _BINDING_IDENTITY_FIELDS - _BINDING_ADAPTER_FIELDS
)
_LEGACY_BINDING_IDENTITY_VARIANTS = (
    _PRE_ADAPTER_BINDING_IDENTITY_FIELDS,
    _PRE_ADAPTER_BINDING_IDENTITY_FIELDS - _BINDING_CAPACITY_FIELDS,
    _PRE_ADAPTER_BINDING_IDENTITY_FIELDS - _BINDING_EXECUTION_FIELDS,
    _PRE_ADAPTER_BINDING_IDENTITY_FIELDS
    - _BINDING_EXECUTION_FIELDS
    - _BINDING_CAPACITY_FIELDS,
)
_BINDING_ALLOWED_BY_STATE = {
    "PREPARED": _BINDING_ENVELOPE_FIELDS | _BINDING_IDENTITY_FIELDS | _BINDING_RETRY_FIELDS,
    "CREATED": (
        _BINDING_ENVELOPE_FIELDS
        | _BINDING_IDENTITY_FIELDS
        | _BINDING_RETRY_FIELDS
        | _BINDING_HOST_FIELDS
    ),
    "BOUND": (
        _BINDING_ENVELOPE_FIELDS
        | _BINDING_IDENTITY_FIELDS
        | _BINDING_RETRY_FIELDS
        | _BINDING_HOST_FIELDS
    ),
    "HOST_EVENT_OBSERVED": (
        _BINDING_ENVELOPE_FIELDS
        | _BINDING_IDENTITY_FIELDS
        | _BINDING_RETRY_FIELDS
        | _BINDING_HOST_FIELDS
        | _BINDING_PROGRESS_FIELDS
    ),
    "ATTENTION_ACKNOWLEDGED": (
        _BINDING_ENVELOPE_FIELDS
        | _BINDING_IDENTITY_FIELDS
        | _BINDING_RETRY_FIELDS
        | _BINDING_HOST_FIELDS
        | _BINDING_PROGRESS_FIELDS
    ),
    "RELEASED": (
        _BINDING_ENVELOPE_FIELDS
        | _BINDING_IDENTITY_FIELDS
        | _BINDING_RETRY_FIELDS
        | _BINDING_HOST_FIELDS
        | _BINDING_PROGRESS_FIELDS
        | _BINDING_TERMINAL_FIELDS
    ),
    "SUPERSEDED": (
        _BINDING_ENVELOPE_FIELDS
        | _BINDING_IDENTITY_FIELDS
        | _BINDING_RETRY_FIELDS
        | _BINDING_HOST_FIELDS
        | _BINDING_PROGRESS_FIELDS
        | _BINDING_FENCE_FIELDS
    ),
}

# These four state-specific key sets are the only historical task-binding
# representation admitted without the post-fencing identity fields.  They are
# enumerated rather than inferred so a novel/ambiguous mapping cannot become
# authority merely because its hash happens to verify.
_LEGACY_BINDING_SCHEMAS = frozenset(
    {
        frozenset(_BINDING_ENVELOPE_FIELDS | _BINDING_RETRY_FIELDS),
        frozenset(
            _BINDING_ENVELOPE_FIELDS | _BINDING_RETRY_FIELDS | _BINDING_HOST_FIELDS
        ),
        frozenset(
            _BINDING_ENVELOPE_FIELDS
            | _BINDING_RETRY_FIELDS
            | _BINDING_HOST_FIELDS
            | _BINDING_PROGRESS_FIELDS
        ),
        frozenset(
            _BINDING_ENVELOPE_FIELDS
            | _BINDING_RETRY_FIELDS
            | _BINDING_HOST_FIELDS
            | _BINDING_TERMINAL_FIELDS
        ),
        frozenset(
            _BINDING_ENVELOPE_FIELDS
            | _BINDING_RETRY_FIELDS
            | _BINDING_HOST_FIELDS
            | _BINDING_PROGRESS_FIELDS
            | _BINDING_TERMINAL_FIELDS
        ),
        *(
            frozenset((allowed - _BINDING_IDENTITY_FIELDS) | legacy_identity)
            for allowed in _BINDING_ALLOWED_BY_STATE.values()
            for legacy_identity in _LEGACY_BINDING_IDENTITY_VARIANTS
        ),
    }
)


class OrchestrationError(RuntimeError):
    """The orchestration contract cannot be produced safely."""


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


def _strict_binding_event(line: str, index: int) -> Mapping[str, object]:
    try:
        event = json.loads(
            line,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise OrchestrationError(f"task binding ledger line {index} is invalid") from error
    if not isinstance(event, Mapping):
        raise OrchestrationError(f"task binding ledger line {index} must be an object")
    if not _finite_json(event):
        raise OrchestrationError(
            f"task binding ledger line {index} contains non-finite JSON"
        )
    try:
        canonical_line = json.dumps(
            event,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as error:
        raise OrchestrationError(
            f"task binding ledger line {index} is not canonical JSON"
        ) from error
    if line != canonical_line:
        raise OrchestrationError(
            f"task binding ledger line {index} uses a noncanonical encoding"
        )
    return event


def _validate_binding_event_schema(
    event: Mapping[str, object], index: int | str
) -> None:
    state = event.get("state")
    if not isinstance(state, str) or state not in _BINDING_ALLOWED_BY_STATE:
        raise OrchestrationError(f"task binding ledger line {index} has an invalid state")
    allowed = _BINDING_ALLOWED_BY_STATE[state]
    unexpected = sorted(set(event) - allowed)
    if unexpected:
        raise OrchestrationError(
            f"task binding ledger line {index} has unexpected {state} fields: "
            + ", ".join(unexpected)
        )
    missing_envelope = sorted(_BINDING_ENVELOPE_FIELDS - set(event))
    if missing_envelope:
        raise OrchestrationError(
            f"task binding ledger line {index} lacks required fields: "
            + ", ".join(missing_envelope)
        )
    if event.get("schema_version") != 1 or event.get("kind") != "hive-mind-task-binding-event-v1":
        raise OrchestrationError(f"task binding ledger line {index} has an invalid schema")
    for field in ("launch_instruction_id", "event_id"):
        value = event.get(field)
        if not isinstance(value, str) or DIGEST_TEXT.fullmatch(value) is None:
            raise OrchestrationError(
                f"task binding ledger line {index} has invalid {field}"
            )
    previous = event.get("previous_event_id")
    if previous is not None and (
        not isinstance(previous, str) or DIGEST_TEXT.fullmatch(previous) is None
    ):
        raise OrchestrationError(
            f"task binding ledger line {index} has invalid previous_event_id"
        )
    if not isinstance(event.get("recorded_at"), str):
        raise OrchestrationError(
            f"task binding ledger line {index} has invalid recorded_at"
        )
    state_required = {
        "PREPARED": _BINDING_RETRY_FIELDS,
        "CREATED": _BINDING_RETRY_FIELDS | _BINDING_HOST_FIELDS,
        "BOUND": _BINDING_RETRY_FIELDS | _BINDING_HOST_FIELDS,
        "HOST_EVENT_OBSERVED": (
            _BINDING_RETRY_FIELDS | _BINDING_HOST_FIELDS | _BINDING_PROGRESS_FIELDS
        ),
        "ATTENTION_ACKNOWLEDGED": (
            _BINDING_RETRY_FIELDS | _BINDING_HOST_FIELDS | _BINDING_PROGRESS_FIELDS
        ),
        "RELEASED": (
            _BINDING_RETRY_FIELDS
            | _BINDING_HOST_FIELDS
            | _BINDING_TERMINAL_FIELDS
            | {"host_event_id", "host_event_cursor"}
        ),
        "SUPERSEDED": _BINDING_RETRY_FIELDS | _BINDING_FENCE_FIELDS,
    }[state]
    missing_state = sorted(state_required - set(event))
    if missing_state:
        raise OrchestrationError(
            f"task binding ledger line {index} lacks required {state} fields: "
            + ", ".join(missing_state)
        )

    fields = frozenset(event)
    has_complete_identity = all(field in event for field in _BINDING_IDENTITY_FIELDS)
    if not has_complete_identity:
        legacy_fenced = (
            state == "SUPERSEDED"
            and set(event).issuperset(
                _BINDING_ENVELOPE_FIELDS
                | _BINDING_RETRY_FIELDS
                | {"resource_key", "authority_epoch"}
                | _BINDING_FENCE_FIELDS
            )
            and not any(
                field in event
                for field in _BINDING_IDENTITY_FIELDS
                - {"resource_key", "authority_epoch"}
            )
        )
        if fields not in _LEGACY_BINDING_SCHEMAS and not legacy_fenced:
            raise OrchestrationError(
                f"task binding ledger line {index} has an unrecognized legacy schema"
            )
    else:
        execution_id = event.get("execution_id")
        execution_namespace = event.get("execution_namespace")
        if (
            not isinstance(execution_id, str)
            or DIGEST_TEXT.fullmatch(execution_id) is None
            or not isinstance(execution_namespace, str)
            or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", execution_namespace)
            is None
        ):
            raise OrchestrationError(
                f"task binding ledger line {index} has invalid execution identity"
            )
        authority_class = event.get("authority_class")
        if authority_class not in AUTHORITY_CLASSES:
            raise OrchestrationError(
                f"task binding ledger line {index} has invalid authority class"
            )
        if authority_class == "WRITE_AUTHORIZED":
            release_id = event.get("dispatcher_release_id")
            admission_epoch = event.get("dispatcher_admission_epoch")
            if (
                not isinstance(release_id, str)
                or DIGEST_TEXT.fullmatch(release_id) is None
                or type(admission_epoch) is not int
                or admission_epoch < 1
            ):
                raise OrchestrationError(
                    f"task binding ledger line {index} lacks exact dispatcher authority"
                )
        elif (
            event.get("dispatcher_release_id") is not None
            or event.get("dispatcher_admission_epoch") is not None
        ):
            raise OrchestrationError(
                f"task binding ledger line {index} gives preparation dispatcher authority"
            )
        resource = event.get("resource_key")
        epoch = event.get("authority_epoch")
        if (
            not isinstance(resource, str)
            or DIGEST_TEXT.fullmatch(resource) is None
            or type(epoch) is not int
            or epoch < 1
        ):
            raise OrchestrationError(
                f"task binding ledger line {index} has invalid launch authority"
            )
        for digest_field in ("host_reservation_id", "capacity_generation"):
            digest_value = event.get(digest_field)
            if (
                not isinstance(digest_value, str)
                or DIGEST_TEXT.fullmatch(digest_value) is None
            ):
                raise OrchestrationError(
                    f"task binding ledger line {index} has invalid {digest_field}"
                )
        if (
            not isinstance(event.get("capacity_host_id"), str)
            or not str(event.get("capacity_host_id")).strip()
            or type(event.get("capacity_epoch")) is not int
            or int(event["capacity_epoch"]) < 1
            or not isinstance(event.get("reservation_expires_at"), str)
            or not str(event.get("reservation_expires_at")).strip()
        ):
            raise OrchestrationError(
                f"task binding ledger line {index} has invalid host capacity fence"
            )
        for digest_field in (
            "host_kernel_generation",
            "execution_adapter_identity_record_id",
            "execution_adapter_identity_blob_digest",
        ):
            digest_value = event.get(digest_field)
            if (
                not isinstance(digest_value, str)
                or DIGEST_TEXT.fullmatch(digest_value) is None
            ):
                raise OrchestrationError(
                    f"task binding ledger line {index} has invalid {digest_field}"
                )
        adapter_record_id = str(event["execution_adapter_identity_record_id"])
        if event.get("execution_adapter_identity_path") != (
            "execution-adapter-bindings/"
            + adapter_record_id.removeprefix("sha256:")
            + ".json"
        ):
            raise OrchestrationError(
                f"task binding ledger line {index} has invalid execution adapter evidence path"
            )


def _validate_binding_replay(events: Sequence[Mapping[str, object]]) -> None:
    latest: dict[str, Mapping[str, object]] = {}
    immutable_fields = (
        _BINDING_IDENTITY_FIELDS
        | _BINDING_RETRY_FIELDS
        | _BINDING_HOST_FIELDS
    ) - {"host_id", "task_id", "cursor", "capability_digest"}
    legal = {
        "PREPARED": {"CREATED", "SUPERSEDED"},
        "CREATED": {"BOUND", "SUPERSEDED"},
        "BOUND": {
            "HOST_EVENT_OBSERVED",
            "ATTENTION_ACKNOWLEDGED",
            "RELEASED",
            "SUPERSEDED",
        },
        "HOST_EVENT_OBSERVED": {
            "HOST_EVENT_OBSERVED",
            "ATTENTION_ACKNOWLEDGED",
            "RELEASED",
            "SUPERSEDED",
        },
        "ATTENTION_ACKNOWLEDGED": {
            "HOST_EVENT_OBSERVED",
            "ATTENTION_ACKNOWLEDGED",
            "RELEASED",
            "SUPERSEDED",
        },
        "RELEASED": set(),
        "SUPERSEDED": set(),
    }
    for index, event in enumerate(events, 1):
        instruction_id = str(event["launch_instruction_id"])
        prior = latest.get(instruction_id)
        if prior is None:
            if event.get("state") != "PREPARED":
                raise OrchestrationError(
                    f"task binding ledger line {index} has terminal or transition evidence without PREPARED ancestry"
                )
        else:
            prior_state = str(prior["state"])
            state = str(event["state"])
            if state not in legal[prior_state]:
                raise OrchestrationError(
                    f"task binding ledger line {index} has impossible {prior_state} -> {state} transition"
                )
            if _BINDING_ADAPTER_FIELDS.issubset(prior) != _BINDING_ADAPTER_FIELDS.issubset(
                event
            ):
                raise OrchestrationError(
                    f"task binding ledger line {index} changes adapter provenance schema"
                )
            for field in immutable_fields:
                if field in prior and prior.get(field) != event.get(field):
                    raise OrchestrationError(
                        f"task binding ledger line {index} mutates immutable {field}"
                    )
            for field in _BINDING_HOST_FIELDS:
                if prior.get(field) is not None and prior.get(field) != event.get(field):
                    raise OrchestrationError(
                        f"task binding ledger line {index} mutates bound host {field}"
                    )
        latest[instruction_id] = event

    active_resources: dict[str, str] = {}
    for instruction_id, event in latest.items():
        if event.get("state") not in ACTIVE_BINDING_STATES:
            continue
        resource = event.get("resource_key")
        if not isinstance(resource, str) or DIGEST_TEXT.fullmatch(resource) is None:
            # Enumerated legacy bindings remain readable solely so an explicit
            # coordinator fence can retire them. They cannot issue new effects.
            continue
        prior_instruction = active_resources.get(resource)
        if prior_instruction is not None and prior_instruction != instruction_id:
            raise OrchestrationError(
                "task binding ledger contains multiple active generations for one resource"
            )
        active_resources[resource] = instruction_id


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _managed_path(repo_root: Path, *parts: str) -> Path:
    root = repo_root.resolve()
    current = root
    for part in parts:
        current = current / part
        if _is_link_like(current):
            raise OrchestrationError(
                f"task binding path uses a symlink or junction: {current}"
            )
        if current.exists() and not current.resolve().is_relative_to(root):
            raise OrchestrationError(f"task binding path escapes the repository: {current}")
    return current


def _state_path(
    repo_root: Path,
    state_dir: str | Path | None,
    *parts: str,
) -> Path:
    try:
        root = _authority_state_root(repo_root, state_dir)
    except ConfigurationError as error:
        raise OrchestrationError(str(error)) from error
    current = root
    for part in parts:
        current /= part
        if _is_link_like(current):
            raise OrchestrationError(f"task binding state path uses a link: {current}")
        if current.exists() and not current.resolve().is_relative_to(root):
            raise OrchestrationError(f"task binding state path escapes runtime state: {current}")
    return current


def _authority_state_root(
    repo_root: Path,
    state_dir: str | Path | None,
) -> Path:
    """Authenticate either the repo migration root or one execution root."""

    coordination = resolve_repository_state_dir(repo_root)
    if state_dir is None:
        if (coordination / "runtime-authority-ready.json").is_file():
            raise OrchestrationError(
                "runtime READY requires an explicit authenticated execution directory"
            )
        return coordination
    supplied = Path(os.path.abspath(os.fspath(state_dir))).absolute()
    if supplied == coordination:
        if (coordination / "runtime-authority-ready.json").is_file():
            raise OrchestrationError(
                "repository-global task authority is retired after runtime READY"
            )
        return coordination
    # Execution directories deliberately use a compact digest segment on
    # Windows-safe authority paths.  Authenticate the identity stored inside
    # a candidate below the canonical executions directory, then let the
    # controller prove that its full digest resolves to this exact directory.
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
            raise OrchestrationError(str(error)) from error
    # Preserve the canonical-root diagnostic for an arbitrary path; a caller
    # cannot turn ``state_dir`` into an independent sovereignty boundary.
    try:
        return resolve_repository_state_dir(repo_root, supplied)
    except ConfigurationError as error:
        raise OrchestrationError(str(error)) from error


def _execution_state_dir(
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
        raise OrchestrationError(str(error)) from error


def _binding_path(
    repo_root: Path,
    state_dir: str | Path | None = None,
) -> Path:
    return _state_path(repo_root, state_dir, "task-bindings.jsonl")


def singleton_target_branch(repo_root: Path) -> str:
    """Return the only live execution target from the trusted control plane."""

    path = _managed_path(repo_root, ".autopilot", "control-plane.json")
    try:
        value = read_strict_canonical_json(
            path,
            label="singleton control plane",
            expected_fields=_CONTROL_PLANE_FIELDS,
        )
    except ConfigurationError as error:
        raise OrchestrationError(f"cannot read singleton control plane: {error}") from error
    if not isinstance(value, Mapping) or not isinstance(value.get("target"), Mapping):
        raise OrchestrationError("control-plane target must be an object")
    target = value["target"]
    branch = target.get("branch")
    final = target.get("final_integration_branch")
    if target.get("execution_mode") != "singleton-release-branch":
        raise OrchestrationError("control plane must use singleton-release-branch execution")
    if not isinstance(branch, str) or not branch.strip():
        raise OrchestrationError("singleton target branch is required")
    if not isinstance(final, str) or not final.strip():
        raise OrchestrationError("final integration branch is required")
    protected = target.get("protected_until_final_integration")
    if branch == final or branch == "main" or not isinstance(protected, list) or final not in protected:
        raise OrchestrationError("singleton execution target must not be main or the protected final branch")
    return branch


INITIALIZATION_LOCK_NAME = "authority-ledger-initialization.lock"


@contextmanager
def _binding_lock(
    repo_root: Path,
    state_dir: str | Path | None = None,
    *,
    for_write: bool = False,
) -> Iterator[None]:
    directory = _authority_state_root(repo_root, state_dir)
    try:
        coordination = resolve_repository_state_dir(repo_root)
        identity = ensure_repository_runtime_identity(
            repo_root, coordination, create=False
        )
    except ConfigurationError as error:
        raise OrchestrationError(str(error)) from error
    ledger_path = _binding_path(repo_root, directory)
    lock_path = _state_path(repo_root, directory, "locks", "task-bindings.lock")
    initialization_path = _state_path(
        repo_root,
        directory,
        "locks",
        INITIALIZATION_LOCK_NAME,
    )
    if not for_write and not lock_path.is_file():
        raise OrchestrationError(
            "task binding lock is absent; run an explicit authority migration"
        )
    if identity is not None and (
        not lock_path.is_file() or not initialization_path.is_file()
    ):
        raise OrchestrationError(
            "task binding authority is uninitialized; run runtime-authority-migrate"
        )
    is_execution = directory != resolve_repository_state_dir(repo_root)
    if for_write and is_execution:
        dispatcher_lock = directory / "locks" / "dispatcher-admission.lock"
        if not runtime_file_lock_is_held(dispatcher_lock):
            raise OrchestrationError(
                "task binding mutation requires caller-held dispatcher authority"
            )
    try:
        if for_write and not ledger_path.exists() and not is_execution:
            # First writers serialize identity/lock/ledger publication through one
            # repository-wide barrier. Readers that observe this persistent lock
            # recheck the ledger under the same barrier instead of racing the first
            # append. Established ledgers take only their dedicated lock.
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
        raise OrchestrationError(str(error)) from error


def _binding_events_unlocked(
    repo_root: Path,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    path = _binding_path(repo_root, state_dir)
    if not path.exists():
        return ()
    events: list[Mapping[str, object]] = []
    previous: str | None = None
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise OrchestrationError(f"cannot read task binding ledger: {error}") from error
    if raw and not raw.endswith(b"\n"):
        raise OrchestrationError(
            "task binding ledger has an unterminated final record; explicit torn-tail "
            "recovery is required"
        )
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        event = _strict_binding_event(line, index)
        _validate_binding_event_schema(event, index)
        material = dict(event)
        event_id = material.pop("event_id", None)
        if material.get("previous_event_id") != previous:
            raise OrchestrationError(f"task binding ledger line {index} breaks the hash chain")
        expected = "sha256:" + sha256(_canonical(material)).hexdigest()
        if event_id != expected:
            raise OrchestrationError(f"task binding ledger line {index} has an invalid digest")
        previous = str(event_id)
        events.append(event)
    _validate_binding_replay(events)
    return tuple(events)


def binding_events(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    directory = _authority_state_root(repo_root, state_dir)
    path = _binding_path(repo_root, state_dir)
    if path.exists():
        with _binding_lock(repo_root, state_dir):
            return _binding_events_unlocked(repo_root, state_dir)
    # Explicit execution initialization seals the empty-ledger proof.  Never
    # reacquire the lower-ranked repository initialization barrier from a
    # compound execution authority cut.
    if directory != resolve_repository_state_dir(repo_root):
        with _binding_lock(repo_root, state_dir):
            return _binding_events_unlocked(repo_root, state_dir)
    initialization_path = _state_path(
        repo_root,
        state_dir,
        "locks",
        INITIALIZATION_LOCK_NAME,
    )
    # The truly absent state remains observational: do not create runtime
    # identity, directories, or lock files merely to report an empty ledger.
    if not initialization_path.is_file():
        return ()
    try:
        with runtime_file_lock(initialization_path):
            if not path.exists():
                return ()
            with _binding_lock(repo_root, state_dir):
                return _binding_events_unlocked(repo_root, state_dir)
    except ConfigurationError as error:
            raise OrchestrationError(str(error)) from error


@contextmanager
def binding_authority_guard(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> Iterator[None]:
    """Hold the canonical task-binding authority for a compound read cut."""

    with _binding_lock(repo_root, state_dir):
        yield


def _provably_incomplete_json_tail(tail: bytes) -> bool:
    if not tail or not tail.lstrip().startswith(b"{"):
        return False
    try:
        text = tail.decode("utf-8")
    except UnicodeDecodeError as error:
        return error.reason == "unexpected end of data" and error.end == len(tail)
    try:
        json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except json.JSONDecodeError as error:
        if error.msg.startswith("Unterminated string"):
            return True
        eof_messages = {
            "Expecting value",
            "Expecting ',' delimiter",
            "Expecting ':' delimiter",
            "Expecting property name enclosed in double quotes",
        }
        return error.msg in eof_messages and error.pos >= len(text.rstrip()) - 1
    except ValueError:
        return False
    return False  # a complete JSON value without its newline is ambiguous


def recover_torn_binding_tail(
    repo_root: Path,
    *,
    actor: str,
    reason: str,
    state_dir: str | Path | None = None,
) -> Mapping[str, object] | None:
    """Quarantine only a provably incomplete final append and preserve its prefix.

    Interior corruption and complete-but-unterminated JSON are never repaired.
    The content-addressed archive and recovery manifest make crash retries
    idempotent; no valid prefix byte is rewritten semantically.
    """

    if not actor.strip() or not reason.strip():
        raise OrchestrationError("torn-tail recovery requires actor and reason")
    with _binding_lock(repo_root, state_dir, for_write=True):
        path = _binding_path(repo_root, state_dir)
        if not path.is_file():
            return None
        raw = path.read_bytes()
        if not raw or raw.endswith(b"\n"):
            return None
        split = raw.rfind(b"\n") + 1
        prefix = raw[:split]
        tail = raw[split:]
        if not _provably_incomplete_json_tail(tail):
            raise OrchestrationError(
                "task binding final bytes are not provably an incomplete JSON append"
            )
        try:
            prefix_text = prefix.decode("utf-8")
        except UnicodeError as error:
            raise OrchestrationError(
                "task binding valid prefix is not UTF-8"
            ) from error
        prefix_events: list[Mapping[str, object]] = []
        previous: str | None = None
        for index, line in enumerate(prefix_text.splitlines(), 1):
            event = _strict_binding_event(line, index)
            _validate_binding_event_schema(event, index)
            material = dict(event)
            event_id = material.pop("event_id")
            if material.get("previous_event_id") != previous:
                raise OrchestrationError(
                    "task binding valid prefix breaks its hash chain"
                )
            if event_id != "sha256:" + sha256(_canonical(material)).hexdigest():
                raise OrchestrationError(
                    "task binding valid prefix contains an invalid digest"
                )
            previous = str(event_id)
            prefix_events.append(event)
        _validate_binding_replay(prefix_events)

        tail_digest = "sha256:" + sha256(tail).hexdigest()
        prefix_digest = "sha256:" + sha256(prefix).hexdigest()
        recovery_dir = _state_path(
            repo_root, state_dir, "task-binding-tail-recoveries"
        )
        stem = tail_digest.replace(":", "-")
        archive = recovery_dir / f"{stem}.bin"
        manifest_path = recovery_dir / f"{stem}.json"
        exclusive_write_bytes_or_identical(archive, tail)
        prepared: dict[str, object] = {
            "schema_version": 1,
            "kind": "hive-mind-task-binding-tail-recovery-v1",
            "status": "PREPARED",
            "actor": actor,
            "reason": reason,
            "ledger_path": str(path),
            "prefix_digest": prefix_digest,
            "prefix_last_event_id": previous,
            "torn_tail_digest": tail_digest,
            "torn_tail_bytes": len(tail),
            "archive_path": str(archive),
        }
        prepared["recovery_id"] = digest_json(prepared)
        if manifest_path.is_file():
            try:
                installed = read_strict_canonical_json(
                    manifest_path, label="torn-tail recovery manifest"
                )
            except ConfigurationError as error:
                raise OrchestrationError(str(error)) from error
            if not isinstance(installed, Mapping) or any(
                installed.get(field) != value
                for field, value in prepared.items()
                if field != "status"
            ):
                raise OrchestrationError("torn-tail recovery manifest conflicts")
        else:
            atomic_write_json(manifest_path, prepared)
        if path.read_bytes() != raw:
            raise OrchestrationError("task binding ledger changed during torn-tail recovery")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(prefix)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        completed = {
            **prepared,
            "status": "COMPLETE",
            "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        completed_material = dict(completed)
        completed_material.pop("record_id", None)
        completed["record_id"] = digest_json(completed_material)
        atomic_write_json(manifest_path, completed)
        return completed


def _append_binding_event_unlocked(
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
    _validate_binding_event_schema(event, "new")
    path = _binding_path(repo_root, state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path = _binding_path(repo_root, state_dir)
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return event


def launch_binding(
    repo_root: Path,
    instruction_id: str,
    *,
    state_dir: str | Path | None = None,
) -> Mapping[str, object] | None:
    latest: Mapping[str, object] | None = None
    for event in binding_events(repo_root, state_dir=state_dir):
        if event.get("launch_instruction_id") == instruction_id:
            latest = event
    return latest


def active_launch_bindings(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    latest: dict[str, Mapping[str, object]] = {}
    for event in binding_events(repo_root, state_dir=state_dir):
        instruction_id = event.get("launch_instruction_id")
        if isinstance(instruction_id, str):
            latest[instruction_id] = event
    return tuple(
        latest[key]
        for key in sorted(latest)
        if latest[key].get("state") in ACTIVE_BINDING_STATES
    )


def _active_binding_events_unlocked(
    events: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    latest = _latest_binding_events(events)
    return tuple(
        latest[key]
        for key in sorted(latest)
        if latest[key].get("state") in ACTIVE_BINDING_STATES
    )


def _write_reservation(event: Mapping[str, object]) -> dict[str, object]:
    if event.get("authority_class") != "WRITE_AUTHORIZED":
        raise OrchestrationError(
            "active launch has unclassified dispatcher reservation authority"
        )
    required_digests = (
        "launch_instruction_id",
        "resource_key",
        "dispatcher_release_id",
        "event_id",
        "host_kernel_generation",
        "execution_adapter_identity_record_id",
        "execution_adapter_identity_blob_digest",
    )
    for field in required_digests:
        value = event.get(field)
        if not isinstance(value, str) or DIGEST_TEXT.fullmatch(value) is None:
            raise OrchestrationError(
                f"active write launch has invalid reservation {field}"
            )
    authority_epoch = event.get("authority_epoch")
    admission_epoch = event.get("dispatcher_admission_epoch")
    if (
        type(authority_epoch) is not int
        or authority_epoch < 1
        or type(admission_epoch) is not int
        or admission_epoch < 1
    ):
        raise OrchestrationError(
            "active write launch has invalid reservation generation epoch"
        )
    node_id = event.get("node_id")
    if not isinstance(node_id, str) or not node_id.strip():
        raise OrchestrationError("active write launch has no exact node identity")
    return {
        "reservation_kind": "WRITE_LAUNCH",
        "node_id": node_id,
        "launch_instruction_id": event["launch_instruction_id"],
        "resource_key": event["resource_key"],
        "authority_epoch": authority_epoch,
        "dispatcher_release_id": event["dispatcher_release_id"],
        "dispatcher_admission_epoch": admission_epoch,
        "host_reservation_id": event.get("host_reservation_id"),
        "capacity_host_id": event.get("capacity_host_id"),
        "capacity_generation": event.get("capacity_generation"),
        "capacity_epoch": event.get("capacity_epoch"),
        "reservation_expires_at": event.get("reservation_expires_at"),
        "host_kernel_generation": event.get("host_kernel_generation"),
        "execution_adapter_identity_record_id": event.get(
            "execution_adapter_identity_record_id"
        ),
        "execution_adapter_identity_path": event.get(
            "execution_adapter_identity_path"
        ),
        "execution_adapter_identity_blob_digest": event.get(
            "execution_adapter_identity_blob_digest"
        ),
        "binding_event_id": event["event_id"],
        "state": event["state"],
    }


def active_write_launch_reservations(
    repo_root: Path,
    *,
    execution_dir: str | Path | None = None,
    execution_id: str | None = None,
    execution_namespace: str | None = None,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Inventory the exact pre-claim WRITE reservations under the binding lock.

    Callers that also mutate dispatcher state must already hold the dispatcher
    lock.  The global order is dispatcher -> binding -> sidecar -> claim ->
    validation; this function never acquires dispatcher authority itself.
    """

    if execution_dir is not None or execution_id is not None:
        if execution_dir is None or execution_id is None:
            raise OrchestrationError(
                "execution reservation inventory requires both execution_dir and execution_id"
            )
        state_dir = _execution_state_dir(
            repo_root,
            execution_dir=execution_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
        )
    with _binding_lock(repo_root, state_dir):
        active = _active_binding_events_unlocked(
            _binding_events_unlocked(repo_root, state_dir)
        )
        reservations: list[Mapping[str, object]] = []
        for event in active:
            authority_class = event.get("authority_class")
            if authority_class == "PREPARATION_ONLY":
                continue
            reservation = _write_reservation(event)
            if execution_id is not None:
                reservation = {"execution_id": execution_id, **reservation}
            reservations.append(reservation)
        return tuple(reservations)


def active_host_reservations(
    repo_root: Path,
    *,
    execution_dir: str | Path | None = None,
    execution_id: str | None = None,
    execution_namespace: str | None = None,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Return one exact, fail-closed primary+sidecar capacity inventory."""

    if execution_dir is not None or execution_id is not None:
        if execution_dir is None or execution_id is None:
            raise OrchestrationError(
                "host reservation inventory requires both execution_dir and execution_id"
            )
        state_dir = _execution_state_dir(
            repo_root,
            execution_dir=execution_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
        )
    with _binding_lock(repo_root, state_dir):
        active = _active_binding_events_unlocked(
            _binding_events_unlocked(repo_root, state_dir)
        )
        by_parent = {
            str(event["launch_instruction_id"]): event
            for event in active
            if isinstance(event.get("launch_instruction_id"), str)
        }
        reservations: list[Mapping[str, object]] = []
        for event in active:
            authority_class = event.get("authority_class")
            if authority_class not in AUTHORITY_CLASSES:
                raise OrchestrationError(
                    "active launch has unclassified host capacity authority"
                )
            if authority_class == "WRITE_AUTHORIZED":
                reservation = _write_reservation(event)
            else:
                reservation = {
                    "reservation_kind": "PREPARATION_LAUNCH",
                    "node_id": event.get("node_id"),
                    "launch_instruction_id": event.get("launch_instruction_id"),
                    "resource_key": event.get("resource_key"),
                    "authority_epoch": event.get("authority_epoch"),
                    "host_reservation_id": event.get("host_reservation_id"),
                    "capacity_host_id": event.get("capacity_host_id"),
                    "capacity_generation": event.get("capacity_generation"),
                    "capacity_epoch": event.get("capacity_epoch"),
                    "reservation_expires_at": event.get(
                        "reservation_expires_at"
                    ),
                    "host_kernel_generation": event.get(
                        "host_kernel_generation"
                    ),
                    "execution_adapter_identity_record_id": event.get(
                        "execution_adapter_identity_record_id"
                    ),
                    "execution_adapter_identity_path": event.get(
                        "execution_adapter_identity_path"
                    ),
                    "execution_adapter_identity_blob_digest": event.get(
                        "execution_adapter_identity_blob_digest"
                    ),
                    "binding_event_id": event.get("event_id"),
                    "state": event.get("state"),
                }
            if execution_id is not None:
                reservation = {"execution_id": execution_id, **reservation}
            reservations.append(reservation)
        # Holding binding while the sidecar reader acquires its own lock is the
        # only combined-inventory order used anywhere in the runtime.
        for sidecar in active_sidecars(repo_root, state_dir=state_dir):
            parent_id = sidecar.get("parent_launch_instruction_id")
            parent = by_parent.get(str(parent_id))
            if parent is None:
                raise OrchestrationError(
                    f"active sidecar {sidecar.get('sidecar_id')} is an orphan reconciliation obligation"
                )
            for sidecar_field, parent_field in (
                ("parent_resource_key", "resource_key"),
                ("parent_authority_epoch", "authority_epoch"),
                ("parent_authority_class", "authority_class"),
                ("parent_dispatcher_release_id", "dispatcher_release_id"),
                ("parent_dispatcher_admission_epoch", "dispatcher_admission_epoch"),
                ("host_kernel_generation", "host_kernel_generation"),
                (
                    "execution_adapter_identity_record_id",
                    "execution_adapter_identity_record_id",
                ),
                (
                    "execution_adapter_identity_path",
                    "execution_adapter_identity_path",
                ),
                (
                    "execution_adapter_identity_blob_digest",
                    "execution_adapter_identity_blob_digest",
                ),
            ):
                if sidecar.get(sidecar_field) != parent.get(parent_field):
                    raise OrchestrationError(
                        f"active sidecar {sidecar.get('sidecar_id')} has stale {sidecar_field}"
                    )
            sidecar_id = sidecar.get("sidecar_id")
            if not isinstance(sidecar_id, str) or DIGEST_TEXT.fullmatch(sidecar_id) is None:
                raise OrchestrationError("active sidecar reservation identity is invalid")
            reservations.append(
                {
                    **({"execution_id": execution_id} if execution_id else {}),
                    "reservation_kind": "SIDECAR",
                    "sidecar_id": sidecar_id,
                    "parent_launch_instruction_id": parent_id,
                    "resource_key": parent.get("resource_key"),
                    "authority_epoch": parent.get("authority_epoch"),
                    "dispatcher_release_id": parent.get("dispatcher_release_id"),
                    "dispatcher_admission_epoch": parent.get(
                        "dispatcher_admission_epoch"
                    ),
                    "host_reservation_id": sidecar.get("host_reservation_id"),
                    "capacity_host_id": sidecar.get("capacity_host_id"),
                    "capacity_generation": sidecar.get("capacity_generation"),
                    "capacity_epoch": sidecar.get("capacity_epoch"),
                    "reservation_expires_at": sidecar.get(
                        "reservation_expires_at"
                    ),
                    "host_kernel_generation": sidecar.get(
                        "host_kernel_generation"
                    ),
                    "execution_adapter_identity_record_id": sidecar.get(
                        "execution_adapter_identity_record_id"
                    ),
                    "execution_adapter_identity_path": sidecar.get(
                        "execution_adapter_identity_path"
                    ),
                    "execution_adapter_identity_blob_digest": sidecar.get(
                        "execution_adapter_identity_blob_digest"
                    ),
                    "sidecar_event_id": sidecar.get("event_id"),
                    "state": sidecar.get("state"),
                }
            )
        return tuple(
            sorted(
                reservations,
                key=lambda item: (
                    str(item.get("reservation_kind")),
                    str(
                        item.get("launch_instruction_id")
                        or item.get("sidecar_id")
                    ),
                ),
            )
        )


def orphaned_sidecar_obligations(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Classify repository-global orphan sidecars under binding -> sidecar locks."""

    with _binding_lock(repo_root, state_dir):
        active = _active_binding_events_unlocked(
            _binding_events_unlocked(repo_root, state_dir)
        )
        return _sidecar_orphan_obligations(
            repo_root,
            [str(event["launch_instruction_id"]) for event in active],
            state_dir=state_dir,
        )


def active_repository_host_state(
    repo_root: Path,
    *,
    state_dir: str | Path | None = None,
) -> Mapping[str, tuple[Mapping[str, object], ...]]:
    """Observe active primaries, sidecars, and orphan obligations atomically."""

    with _binding_lock(repo_root, state_dir):
        active = _active_binding_events_unlocked(
            _binding_events_unlocked(repo_root, state_dir)
        )
        sidecars = active_sidecars(repo_root, state_dir=state_dir)
        active_ids = frozenset(str(event["launch_instruction_id"]) for event in active)
        orphans = tuple(
            event
            for event in sidecars
            if event.get("parent_launch_instruction_id") not in active_ids
        )
        return {
            "launches": active,
            "sidecars": sidecars,
            "orphan_sidecars": orphans,
        }


def reconcile_orphaned_sidecars(
    repo_root: Path,
    *,
    actor: str,
    reason: str,
    limit: int | None = None,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    """Terminally fence orphan reservations under binding -> sidecar locks."""

    with _binding_lock(repo_root, state_dir):
        events = _binding_events_unlocked(repo_root, state_dir)
        return _reconcile_orphans_for_binding_events(
            repo_root,
            events,
            actor=actor,
            reason=reason,
            limit=limit,
            state_dir=state_dir,
        )


def _reconcile_orphans_for_binding_events(
    repo_root: Path,
    events: Sequence[Mapping[str, object]],
    *,
    actor: str,
    reason: str,
    limit: int | None = None,
    state_dir: str | Path | None = None,
) -> tuple[Mapping[str, object], ...]:
    latest = _latest_binding_events(events)
    active_ids = [
        instruction_id
        for instruction_id, event in latest.items()
        if event.get("state") in ACTIVE_BINDING_STATES
    ]
    parent_events = {
        instruction_id: str(event["event_id"])
        for instruction_id, event in latest.items()
        if event.get("state") not in ACTIVE_BINDING_STATES
        and isinstance(event.get("event_id"), str)
    }
    return fence_orphaned_sidecars(
        repo_root,
        active_ids,
        actor=actor,
        reason=reason,
        orphaned_parent_events=parent_events,
        limit=limit,
        state_dir=state_dir,
    )


def _latest_binding_events(
    events: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    latest: dict[str, Mapping[str, object]] = {}
    for event in events:
        instruction_id = event.get("launch_instruction_id")
        if isinstance(instruction_id, str):
            latest[instruction_id] = event
    return latest


def _transition_payload(
    event: Mapping[str, object],
    **changes: object,
) -> dict[str, object]:
    payload = {
        key: value
        for key, value in event.items()
        if key not in {"schema_version", "event_id", "previous_event_id", "recorded_at"}
    }
    payload.update(changes)
    return payload


def _next_authority_epoch(
    events: Sequence[Mapping[str, object]],
    resource_key: str,
) -> int:
    epochs = [
        int(event["authority_epoch"])
        for event in events
        if event.get("resource_key") == resource_key
        and type(event.get("authority_epoch")) is int
    ]
    return max(epochs, default=0) + 1


def _validate_authority_fence(resource_key: str, authority_epoch: int) -> None:
    if not isinstance(resource_key, str) or DIGEST_TEXT.fullmatch(resource_key) is None:
        raise OrchestrationError("launch resource key must be a SHA-256 digest")
    if type(authority_epoch) is not int or authority_epoch < 1:
        raise OrchestrationError("launch authority epoch must be a positive integer")


def _validate_authority_metadata(
    *,
    target_sha: str,
    plan_fingerprint: str,
    target_branch: str,
    authority_class: str,
) -> dict[str, str]:
    values = {
        "target_sha": target_sha,
        "plan_fingerprint": plan_fingerprint,
        "target_branch": target_branch,
        "authority_class": authority_class,
    }
    for field in AUTHORITY_METADATA_FIELDS[:-1]:
        if not isinstance(values[field], str) or not values[field].strip():
            raise OrchestrationError(f"launch {field} is required")
    if authority_class not in AUTHORITY_CLASSES:
        raise OrchestrationError(
            "launch authority class must be PREPARATION_ONLY or WRITE_AUTHORIZED"
        )
    return values


def _canonical_mutable_branch_ref(branch: str) -> str:
    if (
        branch.startswith("refs/")
        or branch.startswith(("/", "."))
        or branch.endswith(("/", ".", ".lock"))
        or "//" in branch
        or ".." in branch
        or "@{" in branch
        or any(ord(character) < 32 or character in " ~^:?*[\\" for character in branch)
        or any(component in {"", ".", ".."} or component.endswith(".lock") for component in branch.split("/"))
    ):
        raise OrchestrationError("launch identity worker branch is not a canonical Git ref")
    return "refs/heads/" + branch


def derive_launch_identity(
    *,
    execution_id: str,
    execution_namespace: str,
    repository: str,
    node_id: str,
    lifecycle: str,
    authority_class: str,
    branch: str,
    target_branch: str,
    target_sha: str,
    plan_fingerprint: str,
    attempt: int = 1,
    retry_of: str | None = None,
) -> Mapping[str, object]:
    """Derive the only accepted resource and instruction identities."""

    texts = {
        "execution_id": execution_id,
        "execution_namespace": execution_namespace,
        "repository": repository,
        "node_id": node_id,
        "lifecycle": lifecycle,
        "branch": branch,
        "target_branch": target_branch,
        "target_sha": target_sha,
        "plan_fingerprint": plan_fingerprint,
    }
    for field, value in texts.items():
        if not isinstance(value, str) or not value.strip():
            raise OrchestrationError(f"launch identity {field} is required")
    if DIGEST_TEXT.fullmatch(execution_id) is None:
        raise OrchestrationError("launch identity execution_id must be a SHA-256 digest")
    if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", execution_namespace) is None:
        raise OrchestrationError("launch identity execution_namespace is invalid")
    if authority_class not in AUTHORITY_CLASSES:
        raise OrchestrationError("launch identity authority class is invalid")
    if type(attempt) is not int or attempt < 1:
        raise OrchestrationError("launch identity attempt must be positive")
    if retry_of is not None and DIGEST_TEXT.fullmatch(retry_of) is None:
        raise OrchestrationError("launch identity retry lineage must be a digest")
    resource_material = {
        "repository": repository,
        "target_branch": target_branch,
        "mutable_ref": _canonical_mutable_branch_ref(branch),
    }
    resource_key = "sha256:" + sha256(_canonical(resource_material)).hexdigest()
    instruction_material = {
        **resource_material,
        "execution_id": execution_id,
        "execution_namespace": execution_namespace,
        "node_id": node_id,
        "lifecycle": lifecycle,
        "authority_class": authority_class,
        "branch": branch,
        "target_sha": target_sha,
        "plan_fingerprint": plan_fingerprint,
        "attempt": attempt,
        "retry_of": retry_of,
    }
    instruction_id = "sha256:" + sha256(_canonical(instruction_material)).hexdigest()
    return {
        "resource_key": resource_key,
        "launch_instruction_id": instruction_id,
        "resource_material": resource_material,
        "instruction_material": instruction_material,
    }


def launch_fence_command_prefix(
    repo_root: Path,
    state_dir: str | Path | None,
    execution_namespace: str = "default",
    host_runtime_dir: str | Path | None = None,
) -> str:
    """Return a fail-closed CLI prefix carrying all three authority roots."""

    try:
        directory = str(resolve_repository_state_dir(repo_root, state_dir))
        host_directory = str(resolve_host_runtime_dir(host_runtime_dir))
    except ConfigurationError as error:
        raise OrchestrationError(str(error)) from error
    # The command is copied into user-owned shells on multiple platforms. Keep
    # the allowed representation deliberately narrower than filesystem syntax
    # so a configured coordination path cannot become prompt-level shell code.
    repository_root = str(repo_root.resolve())
    script = str((repo_root.resolve() / ".autopilot" / "bin" / "autopilot.py"))
    if any(
        character in candidate
        for candidate in (directory, host_directory, repository_root, script)
        for character in '\r\n"`$&|<>%!^'
    ):
        raise OrchestrationError(
            "runtime authority path contains characters unsafe for a launch fence command"
        )
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", execution_namespace):
        raise OrchestrationError("execution namespace is unsafe for a launch fence command")
    return (
        'python "'
        + script
        + '" --repo-root "'
        + repository_root
        + '" --state-dir "'
        + directory
        + '" --host-runtime-dir "'
        + host_directory
        + '" --execution-namespace '
        + execution_namespace
    )


def _live_launch_context(repo_root: Path) -> Mapping[str, object]:
    """Read the current trusted repository/plan/target authority without mutation."""

    path = _managed_path(repo_root, ".autopilot", "control-plane.json")
    try:
        control = read_strict_canonical_json(
            path,
            label="live launch control plane",
            expected_fields=_CONTROL_PLANE_FIELDS,
        )
    except ConfigurationError as error:
        raise OrchestrationError(f"cannot read live launch control plane: {error}") from error
    if not isinstance(control, Mapping) or not isinstance(control.get("target"), Mapping):
        raise OrchestrationError("live launch control target is invalid")
    target = control["target"]
    repository = target.get("repository")
    target_branch = target.get("branch")
    plan_fingerprint = control.get("plan_fingerprint")
    for field, value in {
        "repository": repository,
        "target_branch": target_branch,
        "plan_fingerprint": plan_fingerprint,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise OrchestrationError(f"live launch {field} is required")
    verify_git = control.get("verify_git_objects", True)
    if type(verify_git) is not bool:
        raise OrchestrationError("live launch verify_git_objects must be boolean")
    target_sha: str | None = None
    if verify_git:
        environment = {
            key: value
            for key in ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")
            if (value := os.environ.get(key))
            and not any(character in value for character in "\r\n")
        }
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment["GIT_OPTIONAL_LOCKS"] = "0"
        for reference in (
            f"refs/remotes/origin/{target_branch}",
            f"refs/heads/{target_branch}",
        ):
            completed = subprocess.run(
                ("git", "-C", str(repo_root), "rev-parse", "--verify", reference),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=environment,
                check=False,
            )
            candidate = completed.stdout.strip()
            if completed.returncode == 0 and FULL_GIT_SHA.fullmatch(candidate):
                target_sha = candidate
                break
    else:
        snapshot_path = repo_root / ".autopilot" / "state" / "github-state.json"
        if snapshot_path.is_file():
            try:
                snapshot = read_strict_canonical_json(
                    snapshot_path, label="live target snapshot"
                )
            except ConfigurationError as error:
                raise OrchestrationError(f"cannot read live target snapshot: {error}") from error
            candidate = snapshot.get("target_sha") if isinstance(snapshot, Mapping) else None
            if isinstance(candidate, str) and FULL_GIT_SHA.fullmatch(candidate):
                target_sha = candidate
        if target_sha is None:
            candidate = target.get("baseline_sha")
            if isinstance(candidate, str) and FULL_GIT_SHA.fullmatch(candidate):
                target_sha = candidate
    if target_sha is None:
        raise OrchestrationError(
            f"cannot resolve live target SHA for {target_branch!r}; refresh authority first"
        )
    plan_path = _managed_path(repo_root, ".autopilot", "plan.json")
    try:
        plan = read_strict_canonical_json(
            plan_path,
            label="live launch plan",
            expected_fields=_PLAN_FIELDS,
        )
    except ConfigurationError as error:
        raise OrchestrationError(f"cannot read live launch plan: {error}") from error
    if not isinstance(plan, Mapping):
        raise OrchestrationError("live launch plan must be an object")
    plan_material = dict(plan)
    embedded_fingerprint = plan_material.pop("plan_fingerprint", None)
    observed_fingerprint = "sha256:" + sha256(_canonical(plan_material)).hexdigest()
    if (
        embedded_fingerprint != observed_fingerprint
        or plan_fingerprint != observed_fingerprint
    ):
        raise OrchestrationError("live launch plan fingerprint is not authenticated")
    raw_nodes = plan.get("nodes")
    if not isinstance(raw_nodes, list):
        raise OrchestrationError("live launch plan nodes must be a list")
    node_branches: dict[str, str] = {}
    for index, raw_node in enumerate(raw_nodes):
        if not isinstance(raw_node, Mapping):
            raise OrchestrationError(f"live launch plan node {index} must be an object")
        live_node_id = raw_node.get("id")
        live_branch = raw_node.get("branch")
        if not isinstance(live_node_id, str) or not live_node_id.strip():
            raise OrchestrationError(f"live launch plan node {index} has no ID")
        if not isinstance(live_branch, str) or not live_branch.strip():
            raise OrchestrationError(f"live launch plan node {live_node_id} has no branch")
        if live_node_id in node_branches:
            raise OrchestrationError(f"live launch plan repeats node {live_node_id}")
        node_branches[live_node_id] = live_branch
    return {
        "repository": str(repository),
        "target_branch": str(target_branch),
        "target_sha": target_sha,
        "plan_fingerprint": str(plan_fingerprint),
        "node_branches": node_branches,
    }


def _assert_live_launch_identity(
    live: Mapping[str, object],
    *,
    repository: str,
    node_id: str,
    lifecycle: str,
    branch: str,
    target_branch: str,
    target_sha: str,
    plan_fingerprint: str,
) -> None:
    asserted = {
        "repository": repository,
        "target_branch": target_branch,
        "target_sha": target_sha,
        "plan_fingerprint": plan_fingerprint,
    }
    if any(live.get(field) != value for field, value in asserted.items()):
        raise OrchestrationError("launch identity does not match live repository authority")
    node_branches = live.get("node_branches")
    if not isinstance(node_branches, Mapping):
        raise OrchestrationError("live launch node authority is unavailable")
    if lifecycle == "NODE_DELIVERY":
        if node_branches.get(node_id) != branch:
            raise OrchestrationError(
                "launch node or worker branch does not match the authenticated live plan"
            )
    elif lifecycle == "RECONCILIATION":
        if node_id != "RECONCILIATION" or branch != target_branch:
            raise OrchestrationError("reconciliation launch identity is not canonical")
    else:
        raise OrchestrationError("launch lifecycle is not authorized by the live plan")


def _require_transition_authority(
    events: Sequence[Mapping[str, object]],
    instruction_id: str,
    *,
    resource_key: str,
    authority_epoch: int,
    allowed_states: set[str] | frozenset[str],
) -> Mapping[str, object]:
    """Return the exact live fence or reject an ABA/stale transition."""

    _validate_authority_fence(resource_key, authority_epoch)
    latest = _latest_binding_events(events)
    existing = latest.get(instruction_id)
    if existing is None or existing.get("state") not in allowed_states:
        raise OrchestrationError("launch instruction is not in an allowed transition state")
    if (
        existing.get("resource_key") != resource_key
        or existing.get("authority_epoch") != authority_epoch
    ):
        raise OrchestrationError("launch transition presented a stale resource fence")
    observed_epochs = [
        int(event["authority_epoch"])
        for event in events
        if event.get("resource_key") == resource_key
        and type(event.get("authority_epoch")) is int
    ]
    if not observed_epochs or max(observed_epochs) != authority_epoch:
        raise OrchestrationError("a newer authority epoch has fenced this launch")
    if any(
        other_id != instruction_id
        and other.get("resource_key") == resource_key
        and other.get("state") in ACTIVE_BINDING_STATES
        for other_id, other in latest.items()
    ):
        raise OrchestrationError("resource authority is ambiguous across active launches")
    return existing


@contextmanager
def launch_authority_guard(
    repo_root: Path,
    instruction_id: str,
    *,
    resource_key: str | None = None,
    authority_epoch: int | None = None,
    state_dir: str | Path | None = None,
) -> Iterator[Mapping[str, object]]:
    """Hold the binding lock across one short, authority-sensitive effect.

    Normal callers must present the exact resource and epoch.  The both-omitted
    form exists only for adopting a legacy attended mapping: it resolves the
    current active instruction while holding the same lock used by fencing.
    """

    if (resource_key is None) != (authority_epoch is None):
        raise OrchestrationError(
            "launch authority guard requires both resource key and epoch"
        )
    with _binding_lock(repo_root, state_dir):
        events = _binding_events_unlocked(repo_root, state_dir)
        if resource_key is not None and authority_epoch is not None:
            existing = _require_transition_authority(
                events,
                instruction_id,
                resource_key=resource_key,
                authority_epoch=authority_epoch,
                allowed_states=ACTIVE_BINDING_STATES,
            )
        else:
            existing = _latest_binding_events(events).get(instruction_id)
            if existing is None or existing.get("state") not in ACTIVE_BINDING_STATES:
                raise OrchestrationError("legacy launch authority is stale or revoked")
            stored_resource = existing.get("resource_key")
            stored_epoch = existing.get("authority_epoch")
            if isinstance(stored_resource, str) and type(stored_epoch) is int:
                existing = _require_transition_authority(
                    events,
                    instruction_id,
                    resource_key=stored_resource,
                    authority_epoch=stored_epoch,
                    allowed_states=ACTIVE_BINDING_STATES,
                )
        yield existing


def fence_launch(
    repo_root: Path,
    instruction_id: str,
    *,
    actor: str,
    reason: str,
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    """Administratively revoke one durable launch without claiming host cancellation."""

    if re.fullmatch(r"sha256:[0-9a-f]{64}", instruction_id) is None:
        raise OrchestrationError("launch instruction id must be a SHA-256 digest")
    if not actor.strip() or not reason.strip():
        raise OrchestrationError("launch fencing requires actor and reason")
    with _binding_lock(repo_root, state_dir, for_write=True):
        events = list(_binding_events_unlocked(repo_root, state_dir))
        existing = _latest_binding_events(events).get(instruction_id)
        if existing is None:
            raise OrchestrationError("launch instruction is not present in the binding ledger")
        if existing.get("state") == "SUPERSEDED":
            _reconcile_orphans_for_binding_events(
                repo_root,
                events,
                actor=actor,
                reason=reason,
                state_dir=state_dir,
            )
            return existing
        if existing.get("state") not in ACTIVE_BINDING_STATES:
            raise OrchestrationError("only an active launch can be fenced")
        fenced = _append_binding_event_unlocked(
            repo_root,
            _transition_payload(
                existing,
                resource_key=existing.get("resource_key") or f"legacy:{instruction_id}",
                authority_epoch=(
                    existing.get("authority_epoch")
                    if type(existing.get("authority_epoch")) is int
                    else 0
                ),
                state="SUPERSEDED",
                superseded_by=None,
                superseded_by_actor=actor,
                reason=reason,
            ),
            events,
            state_dir,
        )
        events.append(fenced)
        _reconcile_orphans_for_binding_events(
            repo_root,
            events,
            actor=actor,
            reason=reason,
            state_dir=state_dir,
        )
        return fenced


def assert_launch_authority(
    repo_root: Path,
    instruction_id: str,
    *,
    resource_key: str,
    authority_epoch: int,
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    """Fail closed when a stale session presents an old resource fence."""

    with launch_authority_guard(
        repo_root,
        instruction_id,
        resource_key=resource_key,
        authority_epoch=authority_epoch,
        state_dir=state_dir,
    ) as existing:
        return existing


def _capability_digest(capability: str) -> str:
    if not isinstance(capability, str) or not capability.strip():
        raise OrchestrationError("host task capability is required")
    return "sha256:" + sha256(capability.encode("utf-8")).hexdigest()


def _same_capability(event: Mapping[str, object], capability: str) -> bool:
    expected = event.get("capability_digest")
    return isinstance(expected, str) and hmac.compare_digest(expected, _capability_digest(capability))


def prepare_launch(
    repo_root: Path,
    instruction_id: str,
    host: str,
    *,
    execution_id: str,
    execution_namespace: str,
    repository: str,
    node_id: str,
    lifecycle: str,
    branch: str,
    resource_key: str,
    target_sha: str,
    plan_fingerprint: str,
    target_branch: str,
    authority_class: str,
    dispatcher_release_id: str | None = None,
    dispatcher_admission_epoch: int | None = None,
    host_reservation_id: str,
    capacity_host_id: str,
    capacity_generation: str,
    capacity_epoch: int,
    reservation_expires_at: str,
    host_kernel_generation: str,
    execution_adapter_identity_record_id: str,
    execution_adapter_identity_path: str,
    execution_adapter_identity_blob_digest: str,
    attempt: int = 1,
    retry_of: str | None = None,
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    if DIGEST_TEXT.fullmatch(instruction_id) is None:
        raise OrchestrationError("launch instruction id must be a SHA-256 digest")
    if not host.strip():
        raise OrchestrationError("launch host is required")
    if type(attempt) is not int or attempt < 1:
        raise OrchestrationError("launch attempt must be a positive integer")
    if state_dir is None:
        raise OrchestrationError(
            "launch preparation requires an explicit authenticated execution directory"
        )
    execution_directory = _execution_state_dir(
        repo_root,
        execution_dir=state_dir,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
    )
    metadata = _validate_authority_metadata(
        target_sha=target_sha,
        plan_fingerprint=plan_fingerprint,
        target_branch=target_branch,
        authority_class=authority_class,
    )
    if authority_class == "WRITE_AUTHORIZED":
        if (
            not isinstance(dispatcher_release_id, str)
            or DIGEST_TEXT.fullmatch(dispatcher_release_id) is None
            or type(dispatcher_admission_epoch) is not int
            or dispatcher_admission_epoch < 1
        ):
            raise OrchestrationError(
                "write-authorized launch requires an exact dispatcher release and admission epoch"
            )
    elif dispatcher_release_id is not None or dispatcher_admission_epoch is not None:
        raise OrchestrationError(
            "preparation-only launch cannot carry dispatcher authority"
        )
    if (
        DIGEST_TEXT.fullmatch(host_reservation_id) is None
        or not capacity_host_id.strip()
        or DIGEST_TEXT.fullmatch(capacity_generation) is None
        or type(capacity_epoch) is not int
        or capacity_epoch < 1
        or not reservation_expires_at.strip()
    ):
        raise OrchestrationError("launch requires an exact global host reservation fence")
    for label, value in (
        ("host kernel generation", host_kernel_generation),
        ("execution adapter identity", execution_adapter_identity_record_id),
        ("execution adapter identity blob", execution_adapter_identity_blob_digest),
    ):
        if not isinstance(value, str) or DIGEST_TEXT.fullmatch(value) is None:
            raise OrchestrationError(f"launch requires an exact {label}")
    if execution_adapter_identity_path != (
        "execution-adapter-bindings/"
        + execution_adapter_identity_record_id.removeprefix("sha256:")
        + ".json"
    ):
        raise OrchestrationError("launch execution adapter evidence path is invalid")
    derived = derive_launch_identity(
        execution_id=execution_id,
        execution_namespace=execution_namespace,
        repository=repository,
        node_id=node_id,
        lifecycle=lifecycle,
        authority_class=authority_class,
        branch=branch,
        target_branch=target_branch,
        target_sha=target_sha,
        plan_fingerprint=plan_fingerprint,
        attempt=attempt,
        retry_of=retry_of,
    )
    if derived["resource_key"] != resource_key:
        raise OrchestrationError("launch resource key is not canonical for its repository scope")
    if derived["launch_instruction_id"] != instruction_id:
        raise OrchestrationError("launch instruction id is not canonical for its identity")
    live = _live_launch_context(repo_root)
    _assert_live_launch_identity(
        live,
        repository=repository,
        node_id=node_id,
        lifecycle=lifecycle,
        branch=branch,
        target_branch=target_branch,
        target_sha=target_sha,
        plan_fingerprint=plan_fingerprint,
    )
    identity_metadata = {
        "execution_id": execution_id,
        "execution_namespace": execution_namespace,
        "repository": repository,
        "node_id": node_id,
        "lifecycle": lifecycle,
        "branch": branch,
        **metadata,
        "dispatcher_release_id": dispatcher_release_id,
        "dispatcher_admission_epoch": dispatcher_admission_epoch,
        "host_reservation_id": host_reservation_id,
        "capacity_host_id": capacity_host_id,
        "capacity_generation": capacity_generation,
        "capacity_epoch": capacity_epoch,
        "reservation_expires_at": reservation_expires_at,
        "host_kernel_generation": host_kernel_generation,
        "execution_adapter_identity_record_id": execution_adapter_identity_record_id,
        "execution_adapter_identity_path": execution_adapter_identity_path,
        "execution_adapter_identity_blob_digest": execution_adapter_identity_blob_digest,
    }
    with _binding_lock(repo_root, execution_directory, for_write=True):
        # Re-read trusted authority while holding the transition lock. This
        # closes the local check-to-append window for plan/target advancement;
        # external Git reference movement remains detectable at the next effect
        # boundary but cannot be made atomic with this filesystem ledger.
        _assert_live_launch_identity(
            _live_launch_context(repo_root),
            repository=repository,
            node_id=node_id,
            lifecycle=lifecycle,
            branch=branch,
            target_branch=target_branch,
            target_sha=target_sha,
            plan_fingerprint=plan_fingerprint,
        )
        events = list(_binding_events_unlocked(repo_root, execution_directory))
        existing = next(
            (event for event in reversed(events) if event.get("launch_instruction_id") == instruction_id),
            None,
        )
        if existing is not None and existing.get("state") != "RELEASED":
            if (
                existing.get("host") != host
                or existing.get("attempt") != attempt
                or existing.get("retry_of") != retry_of
                or existing.get("resource_key") not in {None, resource_key}
                or any(
                    existing.get(field) not in {None, value}
                    for field, value in identity_metadata.items()
                )
                or existing.get("dispatcher_release_id") != dispatcher_release_id
                or existing.get("dispatcher_admission_epoch")
                != dispatcher_admission_epoch
            ):
                raise OrchestrationError("prepared launch identity or retry lineage changed")
            if existing.get("state") == "SUPERSEDED":
                raise OrchestrationError("launch instruction has been superseded")
            if (
                existing.get("resource_key") is None
                or type(existing.get("authority_epoch")) is not int
                or any(existing.get(field) is None for field in LAUNCH_IDENTITY_FIELDS)
                or not _BINDING_IDENTITY_FIELDS.issubset(existing)
            ):
                raise OrchestrationError(
                    "legacy active launch has no complete authority fence; explicitly "
                    "fence or migrate it before normal launch issuance"
                )
            existing_epoch = existing.get("authority_epoch")
            if type(existing_epoch) is not int:
                raise OrchestrationError("prepared launch has no valid authority epoch")
            return _require_transition_authority(
                events,
                instruction_id,
                resource_key=resource_key,
                authority_epoch=existing_epoch,
                allowed_states=ACTIVE_BINDING_STATES,
            )
        if existing is not None:
            if (
                existing.get("terminal_state") == "SUCCEEDED"
                and existing.get("host") == host
                and existing.get("attempt") == attempt
                and existing.get("retry_of") == retry_of
                and existing.get("resource_key") == resource_key
                and all(
                    existing.get(field) == value
                    for field, value in identity_metadata.items()
                )
                and existing.get("dispatcher_release_id") == dispatcher_release_id
                and existing.get("dispatcher_admission_epoch")
                == dispatcher_admission_epoch
            ):
                return existing
            if existing.get("terminal_state") == "SUCCEEDED":
                raise OrchestrationError("successful launch tombstone identity changed")
            raise OrchestrationError(
                "an unsuccessful released launch requires a new instruction id and explicit retry lineage"
            )
        if retry_of is not None:
            if DIGEST_TEXT.fullmatch(retry_of) is None:
                raise OrchestrationError("retry lineage must name a released event digest")
            prior = next((event for event in events if event.get("event_id") == retry_of), None)
            if (
                prior is None
                or prior.get("state") != "RELEASED"
                or prior.get("terminal_state") not in {"FAILED", "CANCELLED"}
                or prior.get("launch_instruction_id") == instruction_id
                or prior.get("resource_key") != resource_key
            ):
                raise OrchestrationError(
                    "retry lineage must name a failed or cancelled release for another instruction"
                )
            prior_attempt = prior.get("attempt")
            if type(prior_attempt) is not int or prior_attempt < 1:
                raise OrchestrationError("retry lineage has an invalid prior attempt")
            expected_attempt = prior_attempt + 1
            if attempt != expected_attempt:
                raise OrchestrationError("launch attempt does not match retry lineage")
        elif attempt != 1:
            raise OrchestrationError("a retry attempt requires explicit retry lineage")
        latest = _latest_binding_events(events)
        for old_instruction in sorted(latest):
            old = latest[old_instruction]
            if (
                old_instruction != instruction_id
                and old.get("state") in ACTIVE_BINDING_STATES
                and (
                    not isinstance(old.get("resource_key"), str)
                    or type(old.get("authority_epoch")) is not int
                    or any(old.get(field) is None for field in LAUNCH_IDENTITY_FIELDS)
                )
            ):
                raise OrchestrationError(
                    "legacy active launch has no complete authority fence; explicitly reconcile it "
                    "before creating another host task"
                )
            if (
                old_instruction == instruction_id
                or old.get("state") not in ACTIVE_BINDING_STATES
                or old.get("resource_key") != resource_key
            ):
                continue
            if (
                authority_class == "WRITE_AUTHORIZED"
                and old.get("authority_class") == "PREPARATION_ONLY"
            ):
                superseded = _append_binding_event_unlocked(
                    repo_root,
                    _transition_payload(
                        old,
                        state="SUPERSEDED",
                        superseded_by=instruction_id,
                        superseded_by_actor=f"authority-transition:{host}",
                        reason=(
                            "write-authorized launch supersedes read-only preparation "
                            "for the same repository node lifecycle"
                        ),
                    ),
                    events,
                    execution_directory,
                )
                events.append(superseded)
                _reconcile_orphans_for_binding_events(
                    repo_root,
                    events,
                    actor=f"authority-transition:{host}",
                    reason=(
                        "write-authorized launch superseded read-only preparation "
                        "for the same repository node lifecycle"
                    ),
                    state_dir=execution_directory,
                )
                continue
            raise OrchestrationError(
                "resource already has an active launch; observe terminal host evidence "
                "or explicitly fence that instruction before creating a successor"
            )
        return _append_binding_event_unlocked(
            repo_root,
            {
                "kind": "hive-mind-task-binding-event-v1",
                "launch_instruction_id": instruction_id,
                "resource_key": resource_key,
                "authority_epoch": _next_authority_epoch(events, resource_key),
                **identity_metadata,
                "host": host,
                "attempt": attempt,
                "retry_of": retry_of,
                "state": "PREPARED",
            },
            events,
            execution_directory,
        )


def bind_launch(
    repo_root: Path,
    instruction_id: str,
    host: str,
    task_id: str,
    *,
    host_id: str | None = None,
    cursor: str | None = None,
    capability: str,
    resource_key: str,
    authority_epoch: int,
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    capability_digest = _capability_digest(capability)
    with _binding_lock(repo_root, state_dir, for_write=True):
        events = list(_binding_events_unlocked(repo_root, state_dir))
        existing = _require_transition_authority(
            events,
            instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            allowed_states=ACTIVE_BINDING_STATES,
        )
        if existing.get("host") != host:
            raise OrchestrationError("prepared launch host cannot be rebound by another host")
        if existing.get("state") in {"BOUND", "HOST_EVENT_OBSERVED", "ATTENTION_ACKNOWLEDGED"}:
            if (
                existing.get("task_id") != task_id
                or existing.get("host") != host
                or existing.get("host_id") != host_id
                or existing.get("cursor") != cursor
                or not _same_capability(existing, capability)
            ):
                raise OrchestrationError("launch instruction is already bound to another task")
            return existing
        if existing.get("state") == "CREATED" and (
            existing.get("task_id") != task_id
            or existing.get("host_id") != host_id
            or existing.get("cursor") != cursor
            or not _same_capability(existing, capability)
        ):
            raise OrchestrationError("created launch cannot adopt a different host task")
        if not host.strip() or not task_id.strip():
            raise OrchestrationError("host and task id are required")
        if existing.get("state") == "PREPARED":
            created = _append_binding_event_unlocked(
                repo_root,
                _transition_payload(
                    existing,
                    host=host,
                    host_id=host_id,
                    task_id=task_id,
                    cursor=cursor,
                    capability_digest=capability_digest,
                    attempt=existing.get("attempt", 1),
                    retry_of=existing.get("retry_of"),
                    state="CREATED",
                ),
                events,
                state_dir,
            )
            events.append(created)
            existing = created
        return _append_binding_event_unlocked(
            repo_root,
            _transition_payload(
                existing,
                host=host,
                host_id=host_id,
                task_id=task_id,
                cursor=cursor,
                capability_digest=capability_digest,
                attempt=existing.get("attempt", 1),
                retry_of=existing.get("retry_of"),
                state="BOUND",
            ),
            events,
            state_dir,
        )


def record_host_progress(
    repo_root: Path,
    instruction_id: str,
    *,
    host: str,
    host_id: str,
    task_id: str,
    cursor: str,
    capability: str,
    host_state: str,
    host_event_id: str,
    host_event_cursor: str,
    resource_key: str,
    authority_epoch: int,
    message_id: str | None = None,
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    if host_state not in {"ACTIVE", "NEEDS_ATTENTION"}:
        raise OrchestrationError("progress state must be ACTIVE or NEEDS_ATTENTION")
    if not host_event_id.strip() or not host_event_cursor.strip():
        raise OrchestrationError("host event id and cursor are required")
    if host_state == "NEEDS_ATTENTION" and (not isinstance(message_id, str) or not message_id.strip()):
        raise OrchestrationError("attention recovery requires an acknowledged message id")
    with _binding_lock(repo_root, state_dir, for_write=True):
        events = list(_binding_events_unlocked(repo_root, state_dir))
        existing = _require_transition_authority(
            events,
            instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            allowed_states=ACTIVE_BINDING_STATES - {"PREPARED", "CREATED"},
        )
        expected = {
            "host": host,
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
        }
        if any(existing.get(key) != value for key, value in expected.items()) or not _same_capability(existing, capability):
            raise OrchestrationError("host progress does not match the capability-bound task")
        prior = next(
            (
                event
                for event in reversed(events)
                if event.get("launch_instruction_id") == instruction_id
                and (
                    event.get("host_event_id") == host_event_id
                    or event.get("host_event_cursor") == host_event_cursor
                )
            ),
            None,
        )
        if prior is not None:
            if (
                prior.get("host_event_id") == host_event_id
                and prior.get("host_event_cursor") == host_event_cursor
                and prior.get("host_state") == host_state
                and prior.get("message_id") == message_id
            ):
                return prior
            raise OrchestrationError("host event id or cursor replayed with different evidence")
        return _append_binding_event_unlocked(
            repo_root,
            _transition_payload(
                existing,
                **expected,
                capability_digest=existing.get("capability_digest"),
                host_state=host_state,
                host_event_id=host_event_id,
                host_event_cursor=host_event_cursor,
                message_id=message_id,
                attempt=existing.get("attempt", 1),
                retry_of=existing.get("retry_of"),
                state=(
                    "ATTENTION_ACKNOWLEDGED"
                    if host_state == "NEEDS_ATTENTION"
                    else "HOST_EVENT_OBSERVED"
                ),
            ),
            events,
            state_dir,
        )


def release_terminal_launch(
    repo_root: Path,
    instruction_id: str,
    *,
    host: str,
    host_id: str,
    task_id: str,
    cursor: str,
    capability: str,
    terminal_state: str,
    host_event_id: str,
    host_event_cursor: str,
    resource_key: str,
    authority_epoch: int,
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    if terminal_state not in {"SUCCEEDED", "FAILED", "CANCELLED"}:
        raise OrchestrationError("host terminal state must be SUCCEEDED, FAILED, or CANCELLED")
    if not host_event_id.strip() or not host_event_cursor.strip():
        raise OrchestrationError("host terminal event id and cursor are required")
    with _binding_lock(repo_root, state_dir, for_write=True):
        events = _binding_events_unlocked(repo_root, state_dir)
        expected = {"host": host, "host_id": host_id, "task_id": task_id, "cursor": cursor}
        latest = _latest_binding_events(events)
        existing = latest.get(instruction_id)
        if existing is not None and existing.get("state") == "RELEASED":
            _require_transition_authority(
                events,
                instruction_id,
                resource_key=resource_key,
                authority_epoch=authority_epoch,
                allowed_states={"RELEASED"},
            )
            if (
                all(existing.get(key) == value for key, value in expected.items())
                and existing.get("terminal_state") == terminal_state
                and existing.get("host_event_id") == host_event_id
                and existing.get("host_event_cursor") == host_event_cursor
                and _same_capability(existing, capability)
            ):
                return existing
            raise OrchestrationError("released launch cannot be replaced by different terminal evidence")
        existing = _require_transition_authority(
            events,
            instruction_id,
            resource_key=resource_key,
            authority_epoch=authority_epoch,
            allowed_states=ACTIVE_BINDING_STATES - {"PREPARED", "CREATED"},
        )
        if any(existing.get(key) != value for key, value in expected.items()) or not _same_capability(existing, capability):
            raise OrchestrationError("terminal event does not match the capability-bound task")
        if any(
            event.get("host_event_id") == host_event_id
            or event.get("host_event_cursor") == host_event_cursor
            for event in events
            if event.get("launch_instruction_id") == instruction_id
        ):
            raise OrchestrationError("terminal host event replays previously observed evidence")
        return _append_binding_event_unlocked(
            repo_root,
            _transition_payload(
                existing,
                **expected,
                capability_digest=existing.get("capability_digest"),
                terminal_state=terminal_state,
                host_event_id=host_event_id,
                host_event_cursor=host_event_cursor,
                observed_by=f"host-execution:{host}",
                reason="capability-authenticated host terminal event",
                attempt=existing.get("attempt", 1),
                retry_of=existing.get("retry_of"),
                state="RELEASED",
            ),
            events,
            state_dir,
        )


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: str
    confidence: str
    explicit: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "explicit": self.explicit,
            "reasons": list(self.reasons),
        }


def _words(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _requests_read_only(value: str) -> bool:
    text = re.sub(r'"[^"]*"|“[^”]*”', " ", value).casefold()
    action = r"(?:start(?:ing)?|run(?:ning)?|execute|continue|resume|finish|complete|build|create|generate|launch|kick\s+off|modif(?:y|ies|ied|ying)|chang(?:e|es|ed|ing)|writ(?:e|es|ing)|apply|dispatch)"
    if re.search(r"\b(?:do\s+nothing|don['’]?t\s+do\s+anything|dont\s+do\s+anything|no\s+changes?)\b", text):
        return True
    if re.search(rf"\b(?:do\s+not|don['’]?t|dont|never)\s+(?:\w+\s+){{0,3}}{action}\b", text):
        return True
    if re.search(r"\b(?:only|just)\s+(?:check|inspect|report|summari[sz]e|explain|review)\b", text):
        return True
    if re.search(r"\b(?:explain|describe|summari[sz]e|tell\s+me|show\s+me)\s+(?:how|why|what|when|where|whether)\b", text):
        return True
    if re.search(r"\b(?:review|audit|analy[sz]e|discuss)\s+(?:how|why|what|when|where|whether)\b", text):
        return True
    if re.search(r"\bhow\s+(?:can|could|would|should|do|does|did)\s+(?:i|we|you|this|it|the\s+dag)\b", text):
        return True
    if re.search(r"\b(?:check|inspect|report|summari[sz]e|explain|review)\s+only\b", text):
        return True
    if re.search(r"\bshould\s+(?:i|we|you)\b", text):
        return True
    if re.search(r"\b(?:is|would)\s+it\b.*\b(?:start|finish|continue|run|execute)\b", text):
        return True
    if re.search(r"\b(?:can|could)\s+(?:this|it|the\s+dag)\b", text):
        return True
    return any(
        phrase in text
        for phrase in (
            "read only",
            "read-only",
            "explain the",
            "summarize the",
            "what would you do",
            "what should we do",
            "how would you",
            "how do i",
            "how do we",
            "why did",
            "why didn",
        )
    )


def _node_rows(status: Mapping[str, object]) -> list[Mapping[str, object]]:
    rows = status.get("nodes", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def infer_intent(request: str, status: Mapping[str, object] | None) -> IntentDecision:
    """Infer operator intent from ordinary language and current controller truth.

    Explicit action language wins.  Otherwise the current state supplies the least
    surprising safe action: resume active/recovery work, start released/eligible work,
    build when no plan is installed, and inspect a completed graph.
    """

    if SECRET_TEXT.search(request):
        raise OrchestrationError(
            "operator request appears to contain a credential; remove it and use the host secret store"
        )
    text = request.strip()
    # Quoted examples and documentation excerpts are context, not authority.
    actionable = re.sub(r'"[^"]*"|“[^”]*”', " ", text)
    if _requests_read_only(actionable):
        return IntentDecision(
            "CHECK",
            "high",
            True,
            ("explicit non-execution language overrides action words",),
        )
    text = actionable
    words = _words(text)
    normalized = " ".join(re.findall(r"[a-z0-9]+", text.casefold()))

    def explicit(intent: str, reason: str) -> IntentDecision:
        return IntentDecision(intent, "high", True, (reason,))

    if words & {"finish", "complete", "quiescence", "quiescent"} or any(
        phrase in normalized
        for phrase in ("end to end", "until done", "do not stop", "all the way")
    ):
        return explicit("FINISH", "completion language requests execution to quiescence")
    if words & {"continue", "resume", "recover"} or any(
        phrase in normalized for phrase in ("pick up", "keep going", "carry on")
    ):
        return explicit("CONTINUE", "continuation language requests recovery of existing work")
    if words & {"check", "status", "inspect", "progress", "report"} or any(
        phrase in normalized for phrase in ("where are we", "what is left", "whats left")
    ):
        return explicit("CHECK", "inspection language requests a read-only controller view")
    if words & {"start", "begin", "kickoff", "launch", "execute", "run"} or any(
        phrase in normalized for phrase in ("kick off", "start now")
    ):
        return explicit("START", "execution language requests the next released wave")
    if (
        words & {"build", "create", "generate", "design", "plan"}
        and words & {"dag", "autopilot", "plan", "graph", "hivemind", "workflow"}
    ):
        return explicit("BUILD_DAG", "planning language requests an Autopilot DAG")

    if status is None:
        return IntentDecision(
            "BUILD_DAG",
            "medium",
            False,
            ("no installed Autopilot plan exists, so the reusable workflow begins with DAG construction",),
        )

    rows = _node_rows(status)
    states = {str(row.get("state", "")) for row in rows}
    if states & (ACTIVE_STATES | RECOVERY_STATES):
        return IntentDecision(
            "CONTINUE",
            "medium",
            False,
            ("live DAG state contains active or recoverable work",),
        )
    release = status.get("dispatch_release")
    released = []
    if isinstance(release, Mapping) and release.get("valid") is True:
        raw = release.get("released_wave", [])
        if isinstance(raw, list):
            released = [str(item) for item in raw]
    eligible = status.get("eligible", status.get("ready", []))
    if released or (isinstance(eligible, list) and eligible):
        return IntentDecision(
            "START",
            "medium",
            False,
            ("live DAG state contains released or dependency-eligible work",),
        )
    if status.get("complete") is True:
        return IntentDecision(
            "CHECK",
            "medium",
            False,
            ("the installed DAG reports terminal completion, so inspection is safest",),
        )
    return IntentDecision(
        "CONTINUE",
        "low",
        False,
        ("an installed non-terminal DAG exists and no contradictory intent was expressed",),
    )


def load_policy(repo_root: Path) -> Mapping[str, Any]:
    path = repo_root / ".autopilot" / "orchestration-policy.json"
    try:
        value = read_strict_canonical_json(
            path,
            label="orchestration policy",
            expected_fields=_ORCHESTRATION_POLICY_FIELDS,
        )
    except ConfigurationError as error:
        raise OrchestrationError(f"cannot read orchestration policy: {error}") from error
    issues = validate_policy(value)
    if issues:
        raise OrchestrationError("invalid orchestration policy: " + "; ".join(issues))
    assert isinstance(value, Mapping)
    return value


def validate_policy(value: object) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ("policy must be an object",)
    issues: list[str] = []
    issues.extend(validate_sidecar_policy(value.get("sidecars")))
    if value.get("schema_version") != 1:
        issues.append("schema_version must be 1")
    if value.get("kind") != "hive-mind-autopilot-orchestration-policy-v1":
        issues.append("kind is invalid")
    transport = value.get("task_transport")
    if not isinstance(transport, Mapping):
        issues.append("task_transport must be an object")
    else:
        if transport.get("primary") != "durable_user_owned_task":
            issues.append("primary task transport must be durable_user_owned_task")
        if transport.get("nested_primary_forbidden") is not True:
            issues.append("nested primary tasks must be forbidden")
    polling = value.get("polling")
    if not isinstance(polling, Mapping):
        issues.append("polling must be an object")
    else:
        minimum = polling.get("minimum_primary_completions_before_parent_yield")
        if type(minimum) is not int or minimum < 1:
            issues.append("polling must require at least one primary completion")
        if polling.get("parent_final_while_required_tasks_active") is not False:
            issues.append("parent final must be forbidden while required tasks are active")
        for key in ("poll_until_terminal", "answer_questions_then_resume"):
            if polling.get(key) is not True:
                issues.append(f"polling.{key} must be true")
    closure = value.get("closure_first")
    if not isinstance(closure, Mapping) or closure.get("enabled") is not True:
        issues.append("closure_first.enabled must be true")
    elif type(closure.get("before_optional_audits")) is not int or closure.get("before_optional_audits", 0) < 1:
        issues.append("closure_first must require completion before optional audits")
    recovery = value.get("recovery")
    if not isinstance(recovery, Mapping):
        issues.append("recovery must be an object")
    else:
        if recovery.get("blocker_is_completion") is not False:
            issues.append("a blocker must not count as completion")
        for key in (
            "consult_roles_before_human",
            "record_resolved_questions",
            "resume_same_task_after_fix",
        ):
            if recovery.get(key) is not True:
                issues.append(f"recovery.{key} must be true")
    wave = value.get("wave")
    if not isinstance(wave, Mapping):
        issues.append("wave must be an object")
    else:
        if wave.get("mode") != "deterministic_priority_ordered_maximal_conflict_free":
            issues.append("wave mode must be deterministic priority-ordered maximal conflict-free")
        if wave.get("never_start_next_level_before_required_current_cohort_quiescence") is not True:
            issues.append("wave must wait for current cohort quiescence")
    cohort = value.get("parallel_task_cohort")
    if not isinstance(cohort, Mapping):
        issues.append("parallel_task_cohort must be an object")
    else:
        for key in (
            "create_released_tasks_even_when_recovery_tasks_exist",
            "create_eligible_preparation_tasks",
            "create_entire_cohort_before_first_wait",
            "poll_every_created_task_to_terminal",
            "closure_target_prioritizes_collection_not_creation",
        ):
            if cohort.get(key) is not True:
                issues.append(f"parallel_task_cohort.{key} must be true")
        if cohort.get("preparation_authority") != "read_only_until_start_now":
            issues.append("parallel preparation authority must be read_only_until_start_now")
        if cohort.get("title_fields") != [
            "node_id", "action", "authority_mode", "instruction_digest"
        ]:
            issues.append("parallel task titles must be unambiguous")
    if isinstance(transport, Mapping):
        for key in ("record_host_id", "record_task_id", "resume_by_node_identity"):
            if transport.get(key) is not True:
                issues.append(f"task_transport.{key} must be true")
        if transport.get("binding_ledger") != ".autopilot/state/task-bindings.jsonl":
            issues.append("task binding ledger path is invalid")
        if transport.get("binding_sequence") != [
            "PREPARED",
            "CREATED",
            "BOUND",
            "TERMINAL_OBSERVED",
            "RELEASED",
        ]:
            issues.append("task binding sequence is invalid")
    adapters = value.get("host_adapters")
    codex = adapters.get("codex") if isinstance(adapters, Mapping) else None
    if not isinstance(codex, Mapping):
        issues.append("Codex host adapter is required")
    else:
        expected = {
            "create": "create_thread",
            "wait": "wait_threads",
            "message": "send_message_to_thread",
            "nested_sidecar": "multi_agent_v1.spawn_agent",
            "sidecar_close": "multi_agent_v1.close_agent",
            "sidecar_lookup": "lookup_sidecar",
            "sidecar_message": "multi_agent_v1.send_input",
            "sidecar_wait": "wait_activity",
        }
        for key, expected_value in expected.items():
            if codex.get(key) != expected_value:
                issues.append(f"Codex adapter {key} must be {expected_value}")
    executor = value.get("host_executor")
    if not isinstance(executor, Mapping):
        issues.append("host_executor is required")
    else:
        if executor.get("module") != ".autopilot/bin/host_execution.py":
            issues.append("host executor module is invalid")
        if executor.get("entrypoint") != "execute_contract":
            issues.append("host executor entrypoint is invalid")
        for key in (
            "capability_bound_events",
            "create_entire_wave_before_wait",
            "bounded_no_progress_blocker",
        ):
            if executor.get(key) is not True:
                issues.append(f"host_executor.{key} must be true")
    return tuple(dict.fromkeys(issues))


def should_publish_release(
    decision: IntentDecision,
    status: Mapping[str, object],
) -> bool:
    if decision.intent not in {"START", "CONTINUE", "FINISH"}:
        return False
    if status.get("reconciliation_required") is True:
        return False
    states = {str(row.get("state", "")) for row in _node_rows(status)}
    if states & (ACTIVE_STATES | RECOVERY_STATES):
        return False
    release = status.get("dispatch_release")
    if isinstance(release, Mapping) and release.get("valid") is True:
        return False
    eligible = status.get("eligible", [])
    return isinstance(eligible, list) and bool(eligible)


def _node_map(plane: Any) -> dict[str, Mapping[str, Any]]:
    return {str(node.get("id")): node for node in plane.nodes()}


def _task_prompt(
    plane: Any,
    node_id: str,
    action: str,
    authority_mode: str,
    *,
    host_id: str,
) -> str:
    base = plane.render_worker_prompt(node_id, host_id=host_id)
    return (
        "Read .autopilot/orchestration-policy.json and obey its durable-task, "
        "closure-first, polling, recovery, and quiescence contract.\n"
        f"Primary task action: {action}. Authority mode: {authority_mode}. "
        "PREPARATION_ONLY may inspect, diagnose, and prepare an exact handoff but may "
        "not claim, write, commit, push, or publish completion until START NOW. "
        f"Reuse existing work for {node_id}; do not "
        "duplicate a valid claim, branch, candidate, receipt, or PR. A blocker is not "
        "completion: record it, recover within authority, and resume.\n\n"
        + base
    )


def _task(
    plane: Any,
    policy: Mapping[str, Any],
    node: Mapping[str, Any],
    row: Mapping[str, object],
    *,
    action: str,
    host_id: str,
    required: bool = True,
    authority_mode: str = "RECOVERY_AUTHORIZED",
) -> dict[str, object]:
    node_id = str(node.get("id"))
    adapters = policy.get("host_adapters", {})
    target = getattr(plane, "control", {}).get("target", {})
    repository = (
        str(target.get("repository"))
        if isinstance(target, Mapping) and target.get("repository")
        else str(Path(plane.repo_root).resolve())
    )
    target_branch = str(getattr(plane, "target_branch", "") or node.get("pr_target", ""))
    if not target_branch:
        raise OrchestrationError("the controller has no singleton target branch")
    authority_class = (
        "PREPARATION_ONLY"
        if authority_mode == "PREPARATION_ONLY"
        else "WRITE_AUTHORIZED"
    )
    lifecycle = "NODE_DELIVERY"
    branch = str(node.get("branch"))
    plan_fingerprint = str(getattr(plane, "expected_plan_fingerprint", "unknown"))
    target_sha = (
        str(plane.current_target_sha())
        if hasattr(plane, "current_target_sha")
        else "unknown"
    )
    # All actions from claim through receipt are one durable node-delivery
    # lifecycle. Preparation is intentionally a separate authority identity.
    identity_arguments: dict[str, object] = {
        "execution_id": str(getattr(plane, "execution_id", "")),
        "execution_namespace": str(
            getattr(plane, "execution_namespace", "")
        ),
        "repository": repository,
        "node_id": node_id,
        "lifecycle": lifecycle,
        "authority_class": authority_class,
        "branch": branch,
        "target_branch": target_branch,
        "target_sha": target_sha,
        "plan_fingerprint": plan_fingerprint,
        "attempt": 1,
        "retry_of": None,
    }
    identity = derive_launch_identity(**identity_arguments)  # type: ignore[arg-type]
    resource_key = str(identity["resource_key"])
    instruction_id = str(identity["launch_instruction_id"])
    binding = launch_binding(
        Path(plane.repo_root),
        instruction_id,
        state_dir=getattr(plane, "execution_dir", None),
    )
    if (
        binding is not None
        and binding.get("capacity_host_id") is not None
        and binding.get("capacity_host_id") != host_id
    ):
        raise OrchestrationError(
            "active launch is bound to a different authenticated host"
        )
    retry_of: str | None = None
    while (
        binding is not None
        and binding.get("state") == "RELEASED"
        and binding.get("terminal_state") in {"FAILED", "CANCELLED"}
    ):
        retry_of = str(binding.get("event_id"))
        prior_attempt = binding.get("attempt")
        if type(prior_attempt) is not int or prior_attempt < 1:
            raise OrchestrationError("released launch has an invalid retry attempt")
        identity_arguments["attempt"] = prior_attempt + 1
        identity_arguments["retry_of"] = retry_of
        identity = derive_launch_identity(**identity_arguments)  # type: ignore[arg-type]
        instruction_id = str(identity["launch_instruction_id"])
        binding = launch_binding(
            Path(plane.repo_root),
            instruction_id,
            state_dir=getattr(plane, "execution_dir", None),
        )
    effective_action = action
    if binding is not None and binding.get("state") in {
        "BOUND",
        "HOST_EVENT_OBSERVED",
        "ATTENTION_ACKNOWLEDGED",
    }:
        effective_action = "RESUME_BOUND"
    elif binding is not None and binding.get("state") in {"PREPARED", "CREATED"}:
        effective_action = "RECOVER_PREPARED"
    raw_reasons = row.get("reasons", [])
    reasons = list(raw_reasons) if isinstance(raw_reasons, (list, tuple)) else []
    fence_command = launch_fence_command_prefix(
        Path(plane.repo_root),
        getattr(plane, "coordination_dir", None),
        str(getattr(plane, "execution_namespace", "default")),
        getattr(plane, "host_runtime_dir", None),
    )
    return {
        "task_key": node_id,
        "resource_key": resource_key,
        "execution_id": str(getattr(plane, "execution_id", "")),
        "execution_namespace": str(
            getattr(plane, "execution_namespace", "default")
        ),
        "capacity_host_id": host_id,
        "repository": repository,
        "node_id": node_id,
        "lifecycle": lifecycle,
        "launch_instruction_id": instruction_id,
        "idempotency_key": instruction_id,
        "attempt": identity_arguments["attempt"],
        "retry_of": retry_of,
        "title": f"Hive Mind {node_id} — {action} — {authority_mode} [{instruction_id[7:19]}]",
        "action": effective_action,
        "authority_mode": authority_mode,
        "may_claim_or_write": authority_mode != "PREPARATION_ONLY",
        "start_condition": (
            "current dispatcher release says START NOW for this exact node"
            if authority_mode == "PREPARATION_ONLY"
            else "authority already established by release, claim, or checked-in repair grant"
        ),
        "required": required,
        "state": str(row.get("state", "UNKNOWN")),
        "branch": branch,
        "target_branch": target_branch,
        "target_sha": target_sha,
        "plan_fingerprint": plan_fingerprint,
        "authority_class": authority_class,
        "write_scope": list(node.get("write_scope", [])),
        "reasons": reasons,
        "expected_artifact": (
            "validated candidate, durable receipt, released claim, and draft PR "
            "targeting the configured integration branch"
        ),
        "transport": "durable_user_owned_task",
        "binding_required": True,
        "binding": dict(binding) if binding is not None else None,
        "host_adapters": adapters,
        "prompt": (
            _task_prompt(
                plane,
                node_id,
                effective_action,
                authority_mode,
                host_id=host_id,
            )
            + "\n\nRuntime fence: this session owns only launch instruction "
            + instruction_id
            + f" for resource {resource_key}. Before every claim, write, test, commit, "
            "push, validation gate, or worker launch, run `"
            + fence_command
            + " check-launch-authority "
            + instruction_id
            + f" --resource-key {resource_key} --authority-epoch "
            "<epoch returned by prepare-launch or bind-launch>`. Stop immediately if it "
            "fails; a newer "
            "session has superseded this authority."
        ),
    }


def _closure_key(task: Mapping[str, object], nodes: Mapping[str, Mapping[str, Any]]) -> tuple[int, int, int, str]:
    state_rank = {
        "WAITING_FOR_RECEIPT": 0,
        "PR_OPEN": 1,
        "CI_FAILED": 2,
        "RUNNING": 3,
        "CLAIMED": 4,
        "REPAIR_REQUIRED": 5,
        "RECONCILIATION_REQUIRED": 6,
        "INTEGRATION_READY": 7,
        "PROMOTION_READY": 7,
        "READY": 8,
    }
    node_id = str(task.get("node_id"))
    node = nodes.get(node_id, {})
    return (
        state_rank.get(str(task.get("state")), 99),
        -int(node.get("critical_path_importance", 0)),
        -int(node.get("downstream_unlock_value", 0)),
        node_id,
    )


def build_orchestration_contract(
    plane: Any,
    request: str,
    *,
    status: Mapping[str, object] | None = None,
    allow_sidecars: bool = True,
    allow_preparation_tasks: bool = True,
    host_id: str | None = None,
) -> dict[str, object]:
    """Build the content-addressed wave contract for the current live state.

    Optional transports must be omitted before the contract is authenticated.
    ``allow_sidecars=False`` removes the read-only sidecar cohort.
    ``allow_preparation_tasks=False`` removes speculative preparation primaries
    for an attended host that cannot observe their lifecycle.  Active, recovery,
    and dispatcher-released work is never optional and cannot be truncated.
    """

    policy = load_policy(Path(plane.repo_root))
    current = dict(status or plane.status())
    release_candidate = current.get("dispatch_release")
    host_candidates = {
        value
        for value in (
            host_id,
            getattr(plane, "authenticated_host_id", None),
            (
                release_candidate.get("host_id")
                if isinstance(release_candidate, Mapping)
                and release_candidate.get("valid") is True
                else None
            ),
        )
        if isinstance(value, str) and value.strip()
    }
    if len(host_candidates) > 1:
        raise OrchestrationError(
            "orchestration host identity disagrees with dispatcher authority"
        )
    authenticated_host_id = next(iter(host_candidates), None)
    decision = infer_intent(request, current)
    node_defs = _node_map(plane)
    rows = {
        str(row.get("node_id")): row
        for row in _node_rows(current)
        if isinstance(row.get("node_id"), str)
    }

    tasks: list[dict[str, object]] = []
    if decision.intent != "CHECK" and current.get("complete") is not True:
        if current.get("reconciliation_required") is True:
            repository = str(
                getattr(plane, "control", {}).get("target", {}).get(
                    "repository", Path(plane.repo_root).resolve()
                )
            )
            target_branch = str(current.get("target_branch") or "")
            target_sha = str(current.get("target_sha") or "unknown")
            plan_fingerprint = str(current.get("plan_fingerprint") or "unknown")
            reconciliation_node = "RECONCILIATION"
            reconciliation_lifecycle = "RECONCILIATION"
            reconciliation_branch = target_branch
            reconciliation_identity = derive_launch_identity(
                execution_id=str(getattr(plane, "execution_id", "")),
                execution_namespace=str(
                    getattr(plane, "execution_namespace", "")
                ),
                repository=repository,
                node_id=reconciliation_node,
                lifecycle=reconciliation_lifecycle,
                branch=reconciliation_branch,
                target_sha=target_sha,
                plan_fingerprint=plan_fingerprint,
                target_branch=target_branch,
                authority_class="WRITE_AUTHORIZED",
            )
            reconciliation_resource = str(reconciliation_identity["resource_key"])
            reconciliation_id = str(reconciliation_identity["launch_instruction_id"])
            reconciliation_binding = launch_binding(
                Path(plane.repo_root),
                reconciliation_id,
                state_dir=getattr(plane, "execution_dir", None),
            )
            fence_command = launch_fence_command_prefix(
                Path(plane.repo_root),
                getattr(plane, "coordination_dir", None),
                str(getattr(plane, "execution_namespace", "default")),
                getattr(plane, "host_runtime_dir", None),
            )
            if authenticated_host_id is None:
                raise OrchestrationError(
                    "executable reconciliation requires an authenticated host id"
                )
            tasks.append(
                {
                    "task_key": "RECONCILIATION",
                    "resource_key": reconciliation_resource,
                    "execution_id": str(getattr(plane, "execution_id", "")),
                    "execution_namespace": str(
                        getattr(plane, "execution_namespace", "default")
                    ),
                    "capacity_host_id": authenticated_host_id,
                    "repository": repository,
                    "node_id": reconciliation_node,
                    "lifecycle": reconciliation_lifecycle,
                    "branch": reconciliation_branch,
                    "launch_instruction_id": reconciliation_id,
                    "idempotency_key": reconciliation_id,
                    "attempt": 1,
                    "retry_of": None,
                    "title": f"Hive Mind Reconciliation [{reconciliation_id[7:19]}]",
                    "action": "RECONCILE",
                    "authority_mode": "RECOVERY_AUTHORIZED",
                    "authority_class": "WRITE_AUTHORIZED",
                    "may_claim_or_write": True,
                    "required": True,
                    "state": "RECONCILIATION_REQUIRED",
                    "target_branch": target_branch,
                    "target_sha": target_sha,
                    "plan_fingerprint": plan_fingerprint,
                    "transport": "durable_user_owned_task",
                    "binding_required": True,
                    "binding": (
                        dict(reconciliation_binding)
                        if reconciliation_binding is not None
                        else None
                    ),
                    "host_adapters": policy.get("host_adapters", {}),
                    "expected_artifact": "current verified snapshot and append-only reconciliation record",
                    "prompt": (
                        f"Execution namespace: `{getattr(plane, 'execution_namespace', 'default')}`\n"
                        f"Execution authority: `{getattr(plane, 'execution_dir', '')}`\n"
                        f"Authenticated host: `{authenticated_host_id}`\n"
                        f"Controller prefix: `{fence_command}`\n\n"
                        "Read .autopilot/README.md and .autopilot/orchestration-policy.json. "
                        "Refresh verified repository/GitHub truth, reconcile the exact target, "
                        "run doctor/status, and return the newly eligible wave. Do not implement "
                        "product work or mutate a protected branch. Before every side effect run "
                        "`"
                        + fence_command
                        + " "
                        f"check-launch-authority {reconciliation_id} "
                        f"--resource-key {reconciliation_resource} --authority-epoch "
                        "<epoch returned by prepare-launch or bind-launch>`; stop if it fails."
                    ),
                }
            )
        else:
            for node_id, row in sorted(rows.items()):
                state = str(row.get("state"))
                node = node_defs.get(node_id)
                if node is None:
                    continue
                if state in ACTIVE_STATES:
                    action = {
                        "WAITING_FOR_RECEIPT": "PUBLISH_RECEIPT",
                        "PR_OPEN": "VALIDATE_PR",
                    }.get(state, "RESUME")
                    if authenticated_host_id is None:
                        raise OrchestrationError(
                            "executable task requires an authenticated host id"
                        )
                    tasks.append(
                        _task(
                            plane,
                            policy,
                            node,
                            row,
                            action=action,
                            host_id=authenticated_host_id,
                        )
                    )
                elif state in RECOVERY_STATES:
                    action = {
                        "CI_FAILED": "REPAIR_CI",
                        "REPAIR_REQUIRED": "REPAIR_NODE",
                        "RECONCILIATION_REQUIRED": "RECONCILE_NODE",
                        "REPLAN_REQUIRED": "REPLAN_NODE",
                    }[state]
                    if authenticated_host_id is None:
                        raise OrchestrationError(
                            "executable recovery requires an authenticated host id"
                        )
                    tasks.append(
                        _task(
                            plane,
                            policy,
                            node,
                            row,
                            action=action,
                            host_id=authenticated_host_id,
                        )
                    )

            release = current.get("dispatch_release")
            released: list[str] = []
            if isinstance(release, Mapping) and release.get("valid") is True:
                raw = release.get("released_wave", [])
                if isinstance(raw, list):
                    released = [str(item) for item in raw]
            existing = {str(task.get("node_id")) for task in tasks}
            for node_id in released:
                if node_id in existing or node_id not in node_defs:
                    continue
                if authenticated_host_id is None:
                    raise OrchestrationError(
                        "released task requires an authenticated host id"
                    )
                row = rows.get(node_id, {"node_id": node_id, "state": "READY"})
                tasks.append(
                    _task(
                        plane, policy, node_defs[node_id], row, action="CREATE",
                        host_id=authenticated_host_id,
                        authority_mode="EXECUTION_AUTHORIZED",
                    )
                )
                existing.add(node_id)

            eligible = current.get("eligible", [])
            if allow_preparation_tasks and isinstance(eligible, list):
                for node_id in sorted(str(item) for item in eligible):
                    if node_id in existing or node_id not in node_defs:
                        continue
                    if authenticated_host_id is None:
                        raise OrchestrationError(
                            "preparation task requires an authenticated host id"
                        )
                    row = rows.get(node_id, {"node_id": node_id, "state": "READY"})
                    tasks.append(
                        _task(
                            plane, policy, node_defs[node_id], row,
                            action="PREPARE_READ_ONLY",
                            host_id=authenticated_host_id,
                            authority_mode="PREPARATION_ONLY",
                        )
                    )
                    existing.add(node_id)

    mandatory_tasks = [
        task for task in tasks if task.get("authority_mode") != "PREPARATION_ONLY"
    ]
    if len(mandatory_tasks) > MAX_PRIMARY_TASKS:
        mandatory_ids = ", ".join(
            str(task.get("node_id"))
            for task in sorted(
                mandatory_tasks,
                key=lambda item: _closure_key(item, node_defs),
            )
        )
        raise OrchestrationError(
            f"mandatory primary cohort exceeds canonical cap {MAX_PRIMARY_TASKS}: "
            + mandatory_ids
        )
    optional_tasks = [
        task for task in tasks if task.get("authority_mode") == "PREPARATION_ONLY"
    ]
    mandatory_tasks.sort(key=lambda item: _closure_key(item, node_defs))
    optional_tasks.sort(key=lambda item: _closure_key(item, node_defs))
    tasks = mandatory_tasks + optional_tasks[: MAX_PRIMARY_TASKS - len(mandatory_tasks)]

    primary_tasks = [task for task in tasks if task.get("required") is True]
    closure_target = None
    if primary_tasks:
        closure_target = min(primary_tasks, key=lambda item: _closure_key(item, node_defs)).get("task_key")

    release = current.get("dispatch_release", {})
    release_valid = isinstance(release, Mapping) and release.get("valid") is True
    eligible = current.get("eligible", [])
    dispatch_required = (
        decision.intent in {"START", "CONTINUE", "FINISH"}
        and not release_valid
        and current.get("reconciliation_required") is not True
        and isinstance(eligible, list)
        and bool(eligible)
    )
    observed_states = {str(row.get("state", "")) for row in rows.values()}
    repository_host_state = active_repository_host_state(
        Path(plane.repo_root),
        state_dir=getattr(plane, "execution_dir", None),
    )
    live_bindings = repository_host_state["launches"]
    live_sidecars = repository_host_state["sidecars"]
    orphan_sidecars = repository_host_state["orphan_sidecars"]
    active_claims = current.get("active_claims", [])
    active_validation_lease = current.get("active_validation_lease")
    runtime_authority_active = (
        isinstance(active_claims, list) and bool(active_claims)
    ) or isinstance(active_validation_lease, Mapping)
    if tasks or live_bindings or live_sidecars or runtime_authority_active:
        outcome = "ACTIVE"
        quiescent = False
    elif observed_states and observed_states.issubset(SUCCESS_STATES):
        outcome = "SUCCESS"
        quiescent = True
    elif observed_states & BLOCKING_STATES:
        outcome = "BLOCKED"
        quiescent = bool(
            current.get("complete") is True
            and observed_states
            and observed_states.issubset(TERMINAL_STATES)
        )
    else:
        outcome = "IDLE"
        quiescent = False

    authority_counts: dict[str, int] = {}
    for task in tasks:
        mode = str(task.get("authority_mode", "UNKNOWN"))
        authority_counts[mode] = authority_counts.get(mode, 0) + 1

    planned_sidecars = (
        list(plan_sidecars(tasks, node_defs, policy["sidecars"]))
        if allow_sidecars
        else []
    )
    # Sidecars are optional advisory work. Primaries retain their deterministic
    # closure order, and only the highest-value sidecars that fit the remaining
    # repository host-session capacity are authenticated into the contract.
    remaining_host_slots = MAX_HOST_TASKS - len(tasks)
    planned_sidecars.sort(
        key=lambda item: (
            -int(item["estimated_net_savings_tokens"]),
            str(item["sidecar_id"]),
        )
    )
    sidecars = sorted(
        planned_sidecars[:remaining_host_slots],
        key=lambda item: str(item["sidecar_id"]),
    )
    sidecars_by_parent: dict[str, list[dict[str, object]]] = {}
    for sidecar in sidecars:
        sidecars_by_parent.setdefault(str(sidecar["parent_launch_instruction_id"]), []).append(sidecar)
    for task in tasks:
        task["sidecars"] = sidecars_by_parent.get(str(task.get("launch_instruction_id")), [])

    material = {
        "schema_version": 1,
        "kind": "hive-mind-autopilot-orchestration-contract-v1",
        "execution_id": str(getattr(plane, "execution_id", "")),
        "execution_namespace": str(
            getattr(plane, "execution_namespace", "default")
        ),
        "capacity_host_id": authenticated_host_id,
        "request": request,
        "intent": decision.to_dict(),
        "target_branch": current.get("target_branch"),
        "target_sha": current.get("target_sha"),
        "plan_id": current.get("plan_id"),
        "plan_fingerprint": current.get("plan_fingerprint"),
        "dispatch_required": dispatch_required,
        "dispatch_release": release,
        "eligible": list(eligible) if isinstance(eligible, list) else [],
        "tasks": tasks,
        "task_cohort": {
            "size": len(tasks),
            "canonical_cap": MAX_PRIMARY_TASKS,
            "task_keys": [str(task.get("task_key")) for task in tasks],
            "authority_counts": dict(sorted(authority_counts.items())),
            "created_together_before_first_wait": True,
            "every_task_polled_to_terminal": True,
        },
        "sidecar_cohort": {
            "size": len(sidecars),
            "sidecar_ids": [str(item["sidecar_id"]) for item in sidecars],
            "canonical_host_cap": MAX_HOST_TASKS,
            "initial_host_reservations": len(tasks) + len(sidecars),
            "remaining_descendant_slots": (
                MAX_HOST_TASKS - len(tasks) - len(sidecars)
            ),
            "planned_token_budget": sum(int(item["token_budget"]) for item in sidecars),
            "estimated_net_savings_tokens": sum(
                int(item["estimated_net_savings_tokens"]) for item in sidecars
            ),
            "root_mediated": True,
            "all_parents_require_terminal_ack": True,
            "policy": dict(policy["sidecars"]),
        },
        "active_host_bindings": [dict(item) for item in live_bindings],
        "active_sidecar_bindings": [dict(item) for item in live_sidecars],
        "orphan_sidecar_reconciliation_obligations": [
            dict(item) for item in orphan_sidecars
        ],
        "active_claims": list(active_claims) if isinstance(active_claims, list) else [],
        "active_validation_lease": (
            dict(active_validation_lease)
            if isinstance(active_validation_lease, Mapping)
            else None
        ),
        "closure_target": closure_target,
        "outcome": outcome,
        "successful": outcome == "SUCCESS",
        "quiescent": quiescent,
        "execution": {
            "executor_module": policy["host_executor"]["module"],
            "executor_entrypoint": policy["host_executor"]["entrypoint"],
            "primary_transport": "durable_user_owned_task",
            "nested_agents": "bounded_sidecars_only",
            "create_all_parallel_safe_primary_tasks": True,
            "create_released_tasks_even_when_recovery_tasks_exist": True,
            "create_eligible_read_only_preparation_tasks": allow_preparation_tasks,
            "closure_target_prioritizes_collection_not_task_creation": True,
            "resume_by_node_identity_before_create": True,
            "recover_unbound_launch_by_instruction_id": True,
            "record_task_id_host_id_and_cursor": True,
            "poll_until_terminal": True,
            "answer_and_resume_blocked_tasks": True,
            "minimum_primary_completions_before_parent_yield": policy["polling"][
                "minimum_primary_completions_before_parent_yield"
            ],
            "parent_final_while_required_tasks_active": False,
        },
        "stop_condition": (
            "current DAG is quiescent: every required node is terminal, all claims and "
            "leases are released, required receipts and integration evidence are valid, "
            "and no primary or sidecar host reservation is active"
        ),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    material["contract_id"] = "sha256:" + sha256(encoded.encode("utf-8")).hexdigest()
    return material


def simple_prompt() -> str:
    return (
        "Use Hive Mind OS Autopilot on this repository. Infer whether I mean build, "
        "start, continue, check, or finish; execute its durable parallel-task contract, "
        "recover blockers, and continue until the current DAG is quiescent."
    )
