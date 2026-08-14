"""Capability-bound, crash-safe host execution for Autopilot contracts."""

from __future__ import annotations

import json
import queue
import re
import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence, TypeVar

from controller import (
    _host_provider_binding,
    CapacityAdmissionDenied,
    ConfigurationError,
    ControlPlane,
    active_global_host_reservations,
    append_jsonl,
    assert_execution_authority_open,
    digest_json,
    fence_expired_global_host_session,
    format_time,
    global_host_reservation_record,
    host_repository_registry_bindings,
    parse_time,
    read_host_capacity,
    release_global_host_session,
    renew_global_host_session,
    read_strict_canonical_json,
    require_execution_authority_dir,
    require_host_runtime,
    reserve_global_host_session,
    resolve_repository_state_dir,
    runtime_file_lock,
    strict_jsonl_records,
    utc_now,
    validate_host_lifecycle_observation,
    validate_host_effect_ledger_records,
)

from orchestration import (
    MAX_PRIMARY_TASKS,
    OrchestrationError,
    active_host_reservations,
    active_launch_bindings,
    active_repository_host_state,
    assert_launch_authority,
    bind_launch,
    binding_events,
    derive_launch_identity,
    fence_launch,
    launch_authority_guard,
    launch_fence_command_prefix,
    prepare_launch,
    record_host_progress,
    release_terminal_launch,
    singleton_target_branch,
)
from sidecar_execution import (
    SIDECAR_KINDS,
    TERMINAL_SIDECAR_STATES,
    active_sidecars,
    latest_sidecars,
    make_descendant_spec,
    record_sidecar_state,
    sidecar_spec_digest,
    validate_sidecar_policy,
)

CONTRACT_KIND = "hive-mind-autopilot-orchestration-contract-v1"
CREATE_KIND = "hive-mind-host-task-binding-v1"
EVENT_KIND = "hive-mind-host-event-v1"
ACK_KIND = "hive-mind-host-message-ack-v1"
RESULT_KIND = "hive-mind-host-execution-result-v1"
BLOCKER_KIND = "hive-mind-host-execution-blocker-v1"
TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})
EVENT_STATES = TERMINAL_STATES | {"ACTIVE", "NEEDS_ATTENTION"}
SIDECAR_CREATE_KIND = "hive-mind-host-sidecar-binding-v1"
SIDECAR_EVENT_KIND = "hive-mind-host-sidecar-event-v1"
SIDECAR_RESULT_KIND = "hive-mind-sidecar-result-v1"
SIDECAR_ACK_KIND = "hive-mind-host-sidecar-message-ack-v1"
SIDECAR_EVENT_STATES = TERMINAL_STATES | {"ACTIVE", "NEEDS_ATTENTION", "SPAWN_REQUEST"}
HOST_EFFECT_EVENT_KIND = "hive-mind-host-effect-event-v1"
HOST_EFFECT_EVENT_STATES = frozenset(
    {"PREPARED", "COMPLETED", "RECONCILIATION_REQUIRED"}
)
HOST_EFFECT_LEASE_SECONDS = 300
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_EffectResult = TypeVar("_EffectResult")
_CREATE_KEYS = frozenset(
    {"kind", "host_id", "task_id", "cursor", "capability", "idempotency_key"}
)
_EVENT_BASE_KEYS = frozenset(
    {
        "kind",
        "host_id",
        "task_id",
        "cursor",
        "capability",
        "state",
        "event_id",
        "event_cursor",
    }
)
_ACK_KEYS = frozenset(
    {
        "kind",
        "host_id",
        "task_id",
        "cursor",
        "capability",
        "accepted",
        "message_id",
        "idempotency_key",
    }
)
_SIDECAR_CREATE_KEYS = frozenset(
    {"kind", "host_id", "sidecar_task_id", "cursor", "capability", "idempotency_key", "parent_launch_instruction_id"}
)
_SIDECAR_EVENT_BASE_KEYS = frozenset(
    {"kind", "host_id", "sidecar_task_id", "cursor", "capability", "sidecar_id", "state", "event_id", "event_cursor"}
)
_SIDECAR_RESULT_KEYS = frozenset(
    {"kind", "sidecar_id", "parent_launch_instruction_id", "spec_digest", "status", "summary", "findings", "evidence_refs", "blocker", "token_usage"}
)
_SIDECAR_ACK_KEYS = frozenset(
    {"kind", "host_id", "sidecar_task_id", "cursor", "capability", "accepted", "message_id", "idempotency_key"}
)
_SIDECAR_SPEC_KEYS = frozenset(
    {
        "schema_version", "kind", "parent_launch_instruction_id", "parent_sidecar_id",
        "node_id", "depth", "purpose", "prompt", "read_only", "token_budget",
        "max_result_tokens", "estimated_parent_tokens_saved",
        "estimated_coordination_tokens", "estimated_net_savings_tokens", "sidecar_id",
        "idempotency_key",
    }
)


class HostExecutionError(RuntimeError):
    """A contract or host event failed closed validation."""


class LiveEffectContention(HostExecutionError):
    """Another coordinator owns a still-live external-effect operation lease."""

    def __init__(self, message: str, effect: Mapping[str, object]) -> None:
        super().__init__(message)
        self.effect = dict(effect)


class HostEffectRecoveryRequired(HostExecutionError):
    """An external effect is ambiguous and must not be retried or fenced."""


class EffectAuthorityRejected(HostExecutionError):
    """Dispatcher or launch authority explicitly rejected an effect."""


class _DispatcherEffectRejected(RuntimeError):
    """The shared dispatcher refused an effect before its body began."""


class HostAdapter(Protocol):
    """Durable task host used by :func:`execute_contract`.

    Read-side lifecycle inspection permits explicit adoption.  Merely passing a
    local idempotency key to an external host is not proof that the host enforces
    deduplication, so an ambiguous write is never retried automatically.
    """

    def lookup_thread(self, *, idempotency_key: str) -> Mapping[str, object] | None: ...

    def trusted_singleton_target(self, *, repo_root: Path) -> str: ...

    def dispatcher_effect_guard(
        self,
        *,
        node_id: str,
        release_id: str,
    ) -> AbstractContextManager[object]: ...

    def host_capacity_authority(
        self, *, repo_root: Path
    ) -> Mapping[str, object]: ...

    def host_lifecycle_authority(
        self, *, repo_root: Path
    ) -> Mapping[str, object]: ...

    def observe_task_lifecycle(
        self,
        *,
        reservation: Mapping[str, object],
        local_binding: Mapping[str, object],
        idempotency_key: str,
    ) -> Mapping[str, object] | None: ...

    def read_effect_reconciliation(
        self,
        *,
        effect_kind: str,
        idempotency_key: str,
    ) -> Mapping[str, object]: ...

    def create_thread(
        self, *, title: str, prompt: str, idempotency_key: str
    ) -> Mapping[str, object]: ...

    def wait_threads(
        self, targets: Sequence[Mapping[str, object]]
    ) -> Sequence[Mapping[str, object]]: ...

    def send_message_to_thread(
        self,
        *,
        host_id: str,
        task_id: str,
        cursor: str,
        capability: str,
        message: str,
        idempotency_key: str,
    ) -> Mapping[str, object]: ...

    def inspect_runtime_authority(self, *, repo_root: Path) -> Mapping[str, object]: ...

    # Required only when an authenticated contract contains admitted sidecars.
    def lookup_sidecar(self, *, idempotency_key: str) -> Mapping[str, object] | None: ...

    def spawn_sidecar(
        self, *, prompt: str, token_budget: int, idempotency_key: str,
        parent_launch_instruction_id: str,
    ) -> Mapping[str, object]: ...

    def wait_activity(
        self, primary_targets: Sequence[Mapping[str, object]],
        sidecar_targets: Sequence[Mapping[str, object]],
    ) -> Mapping[str, object]: ...

    def send_message_to_sidecar(
        self, *, host_id: str, sidecar_task_id: str, cursor: str, capability: str,
        message: str, idempotency_key: str,
    ) -> Mapping[str, object]: ...

    def close_sidecar(
        self, *, host_id: str, sidecar_task_id: str, cursor: str, capability: str,
        reason: str, idempotency_key: str,
    ) -> Mapping[str, object]: ...


class SafeResolver(Protocol):
    def resolve_attention(
        self, task: Mapping[str, object], event: Mapping[str, object]
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class _Binding:
    instruction_id: str
    resource_key: str
    authority_epoch: int
    dispatch_release_id: str | None
    dispatch_admission_epoch: int | None
    host_reservation_id: str
    capacity_host_id: str
    capacity_generation: str
    capacity_epoch: int
    reservation_expires_at: str
    task: Mapping[str, object]
    host_id: str
    task_id: str
    cursor: str
    capability: str

    def wait_target(self, after_event_cursor: str | None) -> dict[str, object]:
        return {
            "host_id": self.host_id,
            "task_id": self.task_id,
            "cursor": self.cursor,
            "capability": self.capability,
            "after_event_cursor": after_event_cursor,
        }


@dataclass(frozen=True, slots=True)
class _EffectFence:
    """The authority coordinates needed around a short host-effect transition."""

    instruction_id: str
    resource_key: str
    authority_epoch: int
    dispatch_release_id: str | None
    dispatch_admission_epoch: int | None
    task: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _SidecarBinding:
    sidecar_id: str
    spec: Mapping[str, object]
    host_id: str
    task_id: str
    cursor: str
    capability: str
    parent: _Binding

    def wait_target(self, after_event_cursor: str | None) -> dict[str, object]:
        return {
            "host_id": self.host_id,
            "sidecar_task_id": self.task_id,
            "cursor": self.cursor,
            "capability": self.capability,
            "after_event_cursor": after_event_cursor,
        }


def _canonical(value: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HostExecutionError(f"{field} must be a non-empty string")
    return value


def _exact_keys(value: Mapping[str, object], expected: frozenset[str], subject: str) -> None:
    actual = frozenset(value)
    if actual != expected:
        raise HostExecutionError(
            f"{subject} has invalid fields; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )


def validate_contract(
    repo_root: Path,
    contract: Mapping[str, object],
    trusted_target_branch: str,
) -> tuple[Mapping[str, object], ...]:
    """Validate execution policy, retry lineage, and singleton target authority."""

    if contract.get("schema_version") != 1 or contract.get("kind") != CONTRACT_KIND:
        raise HostExecutionError("expected a v1 Autopilot orchestration contract")
    contract_id = contract.get("contract_id")
    if not isinstance(contract_id, str) or not _DIGEST.fullmatch(contract_id):
        raise HostExecutionError("contract_id must be a SHA-256 digest")
    material = dict(contract)
    material.pop("contract_id", None)
    if contract_id != "sha256:" + sha256(_canonical(material)).hexdigest():
        raise HostExecutionError("contract_id does not authenticate the contract body")
    target_branch = singleton_target_branch(repo_root)
    if (
        not isinstance(trusted_target_branch, str)
        or not trusted_target_branch.strip()
        or trusted_target_branch == "main"
        or trusted_target_branch != target_branch
    ):
        raise HostExecutionError("host trust does not authorize the singleton target")
    if contract.get("target_branch") != target_branch:
        raise HostExecutionError("contract target does not match the trusted singleton target")
    execution_id = _required_text(contract.get("execution_id"), "contract execution_id")
    execution_namespace = _required_text(
        contract.get("execution_namespace"), "contract execution_namespace"
    )
    if not _DIGEST.fullmatch(execution_id) or re.fullmatch(
        r"[a-z0-9][a-z0-9._-]{0,63}", execution_namespace
    ) is None:
        raise HostExecutionError("contract execution namespace identity is invalid")
    contract_target_sha = _required_text(contract.get("target_sha"), "contract target_sha")
    contract_plan = _required_text(
        contract.get("plan_fingerprint"), "contract plan_fingerprint"
    )
    execution = contract.get("execution")
    if not isinstance(execution, Mapping):
        raise HostExecutionError("contract execution policy is required")
    required_flags = {
        "create_all_parallel_safe_primary_tasks": True,
        "poll_until_terminal": True,
        "answer_and_resume_blocked_tasks": True,
        "parent_final_while_required_tasks_active": False,
    }
    for name, expected in required_flags.items():
        if execution.get(name) is not expected:
            raise HostExecutionError(f"contract execution policy requires {name}={expected}")
    raw_tasks = contract.get("tasks")
    if not isinstance(raw_tasks, list):
        raise HostExecutionError("contract tasks must be a list")
    if len(raw_tasks) > MAX_PRIMARY_TASKS:
        raise HostExecutionError(
            f"primary task cohort exceeds canonical cap {MAX_PRIMARY_TASKS}"
        )
    claims = contract.get("active_claims", [])
    lease = contract.get("active_validation_lease")
    if not isinstance(claims, list):
        raise HostExecutionError("contract active_claims must be a list")
    if lease is not None and not isinstance(lease, Mapping):
        raise HostExecutionError("contract active_validation_lease must be an object or null")
    tasks: list[Mapping[str, object]] = []
    contract_host_id = contract.get("capacity_host_id")
    if raw_tasks and not isinstance(contract_host_id, str):
        raise HostExecutionError(
            "executable contract requires an authenticated host identity"
        )
    seen: set[str] = set()
    seen_resources: set[str] = set()
    for index, raw in enumerate(raw_tasks):
        if not isinstance(raw, Mapping):
            raise HostExecutionError(f"task {index} must be an object")
        instruction_id = _required_text(raw.get("launch_instruction_id"), "launch_instruction_id")
        if (
            raw.get("execution_id") != execution_id
            or raw.get("execution_namespace") != execution_namespace
        ):
            raise HostExecutionError("task changed its execution namespace identity")
        task_host_id = _required_text(
            raw.get("capacity_host_id"), "task capacity_host_id"
        )
        if task_host_id != contract_host_id:
            raise HostExecutionError("task changed its contract host identity")
        if not _DIGEST.fullmatch(instruction_id):
            raise HostExecutionError("launch_instruction_id must be a SHA-256 digest")
        if raw.get("idempotency_key") != instruction_id:
            raise HostExecutionError("task idempotency_key must equal launch_instruction_id")
        if instruction_id in seen:
            raise HostExecutionError("launch_instruction_id values must be unique")
        seen.add(instruction_id)
        resource_key = _required_text(raw.get("resource_key"), "resource_key")
        if not _DIGEST.fullmatch(resource_key):
            raise HostExecutionError("resource_key must be a SHA-256 digest")
        if resource_key in seen_resources:
            raise HostExecutionError("contract cannot launch the same resource twice")
        seen_resources.add(resource_key)
        _required_text(raw.get("title"), "task title")
        _required_text(raw.get("prompt"), "task prompt")
        if not isinstance(raw.get("required"), bool):
            raise HostExecutionError("task required must be boolean")
        if raw.get("transport") != "durable_user_owned_task":
            raise HostExecutionError("task transport must be durable_user_owned_task")
        if raw.get("target_branch") != target_branch:
            raise HostExecutionError("task target does not match the trusted singleton target")
        if raw.get("target_sha") != contract_target_sha:
            raise HostExecutionError("task target SHA does not match the contract snapshot")
        if raw.get("plan_fingerprint") != contract_plan:
            raise HostExecutionError("task plan fingerprint does not match the contract snapshot")
        authority_class = raw.get("authority_class")
        if authority_class not in {"PREPARATION_ONLY", "WRITE_AUTHORIZED"}:
            raise HostExecutionError("task authority class is invalid")
        if (
            raw.get("authority_mode") == "PREPARATION_ONLY"
            and authority_class != "PREPARATION_ONLY"
        ):
            raise HostExecutionError("preparation task cannot carry write authority")
        attempt = raw.get("attempt")
        retry_of = raw.get("retry_of")
        if type(attempt) is not int or attempt < 1:
            raise HostExecutionError("task attempt must be a positive integer")
        if attempt == 1 and retry_of is not None:
            raise HostExecutionError("first launch attempt cannot have retry lineage")
        if attempt > 1 and (not isinstance(retry_of, str) or not _DIGEST.fullmatch(retry_of)):
            raise HostExecutionError("retry attempt requires a released event digest")
        repository = _required_text(raw.get("repository"), "task repository")
        node_id = _required_text(raw.get("node_id"), "task node_id")
        lifecycle = _required_text(raw.get("lifecycle"), "task lifecycle")
        branch = _required_text(raw.get("branch"), "task branch")
        try:
            identity = derive_launch_identity(
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                repository=repository,
                node_id=node_id,
                lifecycle=lifecycle,
                authority_class=str(authority_class),
                branch=branch,
                target_branch=target_branch,
                target_sha=contract_target_sha,
                plan_fingerprint=contract_plan,
                attempt=attempt,
                retry_of=retry_of if isinstance(retry_of, str) else None,
            )
        except OrchestrationError as error:
            raise HostExecutionError(f"task launch identity is invalid: {error}") from error
        if identity["resource_key"] != resource_key:
            raise HostExecutionError("task resource_key is not canonical for its repository scope")
        if identity["launch_instruction_id"] != instruction_id:
            raise HostExecutionError("task launch_instruction_id is not canonical")
        tasks.append(raw)
    write_nodes = [
        str(task["node_id"])
        for task in tasks
        if task.get("authority_class") == "WRITE_AUTHORIZED"
    ]
    if write_nodes:
        dispatch_release = contract.get("dispatch_release")
        if not isinstance(dispatch_release, Mapping) or dispatch_release.get("valid") is not True:
            raise HostExecutionError(
                "write-authorized host tasks require a valid dispatcher release"
            )
        release_id = dispatch_release.get("release_id")
        if not isinstance(release_id, str) or not _DIGEST.fullmatch(release_id):
            raise HostExecutionError(
                "write-authorized host tasks require an exact dispatcher release id"
            )
        admission_epoch = dispatch_release.get("admission_epoch")
        if type(admission_epoch) is not int or admission_epoch < 1:
            raise HostExecutionError(
                "write-authorized host tasks require an exact dispatcher admission epoch"
            )
        released_wave = dispatch_release.get("released_wave")
        if (
            not isinstance(released_wave, list)
            or any(not isinstance(node_id, str) for node_id in released_wave)
            or not set(write_nodes) <= set(released_wave)
        ):
            raise HostExecutionError(
                "write-authorized host task cohort exceeds its dispatcher release"
            )
    cohort = contract.get("sidecar_cohort")
    if cohort is not None:
        if not isinstance(cohort, Mapping):
            raise HostExecutionError("sidecar_cohort must be an object")
        policy = cohort.get("policy")
        issues = validate_sidecar_policy(policy)
        if issues:
            raise HostExecutionError("invalid sidecar policy: " + "; ".join(issues))
        raw_ids = cohort.get("sidecar_ids")
        if not isinstance(raw_ids, list) or len(raw_ids) != cohort.get("size"):
            raise HostExecutionError("sidecar cohort size and IDs disagree")
        if cohort.get("root_mediated") is not True or cohort.get("all_parents_require_terminal_ack") is not True:
            raise HostExecutionError("sidecar cohort must be root-mediated with parent acknowledgements")
        discovered: list[str] = []
        total_budget = 0
        total_net = 0
        parents = {str(item["launch_instruction_id"]) for item in tasks}
        parent_counts: dict[str, int] = {}
        for task in tasks:
            raw_sidecars = task.get("sidecars", [])
            if not isinstance(raw_sidecars, list):
                raise HostExecutionError("task sidecars must be a list")
            for spec in raw_sidecars:
                if not isinstance(spec, Mapping):
                    raise HostExecutionError("sidecar specification must be an object")
                _exact_keys(spec, _SIDECAR_SPEC_KEYS, "planned sidecar specification")
                if spec.get("schema_version") != 1 or spec.get("kind") != "hive-mind-sidecar-spec-v1":
                    raise HostExecutionError("sidecar specification kind or version is invalid")
                sidecar_id = _required_text(spec.get("sidecar_id"), "sidecar_id")
                if not _DIGEST.fullmatch(sidecar_id) or sidecar_spec_digest(spec) != sidecar_id:
                    raise HostExecutionError("sidecar specification digest is invalid")
                if spec.get("idempotency_key") != sidecar_id:
                    raise HostExecutionError("sidecar idempotency key must equal sidecar_id")
                if spec.get("parent_launch_instruction_id") != task.get("launch_instruction_id"):
                    raise HostExecutionError("sidecar is attached to the wrong primary parent")
                if spec.get("parent_sidecar_id") is not None or spec.get("depth") != 1:
                    raise HostExecutionError("planned sidecars must begin at depth one")
                if spec.get("purpose") not in SIDECAR_KINDS or spec.get("read_only") is not True:
                    raise HostExecutionError("sidecar purpose or read-only authority is invalid")
                for field in (
                    "token_budget", "max_result_tokens", "estimated_parent_tokens_saved",
                    "estimated_coordination_tokens", "estimated_net_savings_tokens",
                ):
                    if type(spec.get(field)) is not int or int(spec[field]) < 0:
                        raise HostExecutionError(f"sidecar {field} must be a non-negative integer")
                expected_net = int(spec["estimated_parent_tokens_saved"]) - int(spec["token_budget"]) - int(spec["max_result_tokens"]) - int(spec["estimated_coordination_tokens"])
                if int(spec["estimated_net_savings_tokens"]) != expected_net or expected_net < int(policy["min_net_savings_tokens"]):
                    raise HostExecutionError("sidecar does not satisfy token admission policy")
                _required_text(spec.get("prompt"), "sidecar prompt")
                discovered.append(sidecar_id)
                parent_key = str(spec["parent_launch_instruction_id"])
                parent_counts[parent_key] = parent_counts.get(parent_key, 0) + 1
                total_budget += int(spec["token_budget"])
                total_net += expected_net
        if len(discovered) != len(set(discovered)) or sorted(discovered) != sorted(str(item) for item in raw_ids):
            raise HostExecutionError("sidecar cohort IDs are duplicate or incomplete")
        if not set(str(item) for item in raw_ids).issubset(set(discovered)) or not parents:
            raise HostExecutionError("sidecar cohort has no valid parents")
        if total_budget != cohort.get("planned_token_budget") or total_net != cohort.get("estimated_net_savings_tokens"):
            raise HostExecutionError("sidecar cohort accounting is inconsistent")
        if total_budget > int(policy["total_token_budget"]):
            raise HostExecutionError("sidecar cohort exceeds total token budget")
        if len(discovered) > int(policy["max_total_sidecars"]) or any(
            count > int(policy["max_sidecars_per_primary"]) for count in parent_counts.values()
        ):
            raise HostExecutionError("sidecar cohort exceeds count policy")
        initial_reservations = len(tasks) + len(discovered)
        if (
            cohort.get("initial_host_reservations") != initial_reservations
            or type(cohort.get("remaining_descendant_slots")) is not int
            or int(cohort["remaining_descendant_slots"]) < 0
        ):
            raise HostExecutionError("sidecar cohort host-capacity accounting is inconsistent")
    return tuple(tasks)


def _sidecar_specs(contract: Mapping[str, object], tasks: Sequence[Mapping[str, object]]) -> tuple[Mapping[str, object], ...]:
    if contract.get("sidecar_cohort") is None:
        return ()
    return tuple(
        spec
        for task in tasks
        for spec in task.get("sidecars", [])  # type: ignore[union-attr]
        if isinstance(spec, Mapping)
    )


def _live_host_reservation_count(
    repo_root: Path,
    state_dir: str | Path | None,
) -> int:
    """Count shared active primary and sidecar reservations for this repository."""

    return len(active_host_reservations(repo_root, state_dir=state_dir))


def _sidecar_capabilities(adapter: HostAdapter) -> None:
    missing = [
        name for name in (
            "lookup_sidecar", "spawn_sidecar", "wait_activity",
            "send_message_to_sidecar", "close_sidecar",
        ) if not callable(getattr(adapter, name, None))
    ]
    if missing:
        raise HostExecutionError("sidecar host capability missing: " + ", ".join(missing))


def _validate_sidecar_creation(
    value: Mapping[str, object],
    spec: Mapping[str, object],
    parent: _Binding,
) -> _SidecarBinding:
    _exact_keys(value, _SIDECAR_CREATE_KEYS, "host sidecar binding")
    sidecar_id = str(spec["sidecar_id"])
    if value.get("kind") != SIDECAR_CREATE_KIND or value.get("idempotency_key") != sidecar_id:
        raise HostExecutionError("host sidecar does not bind its idempotency key")
    if value.get("parent_launch_instruction_id") != spec.get("parent_launch_instruction_id"):
        raise HostExecutionError("host sidecar binding changed its primary parent")
    return _SidecarBinding(
        sidecar_id=sidecar_id, spec=spec,
        host_id=_required_text(value.get("host_id"), "sidecar host_id"),
        task_id=_required_text(value.get("sidecar_task_id"), "sidecar_task_id"),
        cursor=_required_text(value.get("cursor"), "sidecar cursor"),
        capability=_required_text(value.get("capability"), "sidecar capability"),
        parent=parent,
    )


def _validate_sidecar_event(value: Mapping[str, object], binding: _SidecarBinding) -> None:
    state = value.get("state")
    extra = {"attention"} if state == "NEEDS_ATTENTION" else ({"request"} if state == "SPAWN_REQUEST" else ({"result"} if state in TERMINAL_STATES else set()))
    _exact_keys(value, frozenset(_SIDECAR_EVENT_BASE_KEYS | extra), "host sidecar event")
    if value.get("kind") != SIDECAR_EVENT_KIND or state not in SIDECAR_EVENT_STATES:
        raise HostExecutionError("host returned an unknown sidecar event kind or state")
    for field, expected in {
        "host_id": binding.host_id, "sidecar_task_id": binding.task_id,
        "cursor": binding.cursor, "capability": binding.capability,
        "sidecar_id": binding.sidecar_id,
    }.items():
        if value.get(field) != expected:
            raise HostExecutionError(f"host sidecar event has forged or mismatched {field}")
    _required_text(value.get("event_id"), "sidecar event_id")
    _required_text(value.get("event_cursor"), "sidecar event_cursor")
    if state == "NEEDS_ATTENTION":
        _required_text(value.get("attention"), "sidecar attention")


def _validate_sidecar_result(value: object, binding: _SidecarBinding) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise HostExecutionError("terminal sidecar result must be an object")
    _exact_keys(value, _SIDECAR_RESULT_KEYS, "terminal sidecar result")
    if value.get("kind") != SIDECAR_RESULT_KIND or value.get("sidecar_id") != binding.sidecar_id:
        raise HostExecutionError("terminal sidecar result identity is invalid")
    if value.get("parent_launch_instruction_id") != binding.spec.get("parent_launch_instruction_id"):
        raise HostExecutionError("terminal sidecar result changed parent identity")
    if value.get("spec_digest") != sidecar_spec_digest(binding.spec) or value.get("status") not in TERMINAL_STATES:
        raise HostExecutionError("terminal sidecar result is stale or unauthenticated")
    _required_text(value.get("summary"), "sidecar result summary")
    if not isinstance(value.get("findings"), list) or not isinstance(value.get("evidence_refs"), list):
        raise HostExecutionError("sidecar findings and evidence_refs must be lists")
    usage = value.get("token_usage")
    if type(usage) is not int or usage < 0 or usage > int(binding.spec["token_budget"]):
        raise HostExecutionError("sidecar token usage is missing or over budget")
    if len(json.dumps(dict(value), ensure_ascii=False)) > int(binding.spec["max_result_tokens"]) * 6:
        raise HostExecutionError("sidecar result exceeds its compact result budget")
    return value


def _terminal_sidecar_result(value: object, binding: _SidecarBinding, host_state: str) -> tuple[str, Mapping[str, object]]:
    """Convert untrusted terminal output into a bounded adverse terminal packet."""
    try:
        result = _validate_sidecar_result(value, binding)
        if result.get("status") != host_state:
            raise HostExecutionError("sidecar result status does not match its event")
        return host_state, result
    except HostExecutionError as error:
        diagnostic = str(error)[:240]
        return "FAILED", {
            "kind": SIDECAR_RESULT_KIND,
            "sidecar_id": binding.sidecar_id,
            "parent_launch_instruction_id": binding.spec["parent_launch_instruction_id"],
            "spec_digest": sidecar_spec_digest(binding.spec),
            "status": "FAILED",
            "summary": "Untrusted terminal output was rejected and the reservation was charged.",
            "findings": [],
            "evidence_refs": [],
            "blocker": {"code": "INVALID_TERMINAL_SCHEMA", "diagnostic": diagnostic},
            "token_usage": int(binding.spec["token_budget"]),
        }


def _validate_sidecar_ack(value: Mapping[str, object], binding: _SidecarBinding, key: str) -> None:
    _exact_keys(value, _SIDECAR_ACK_KEYS, "send_message_to_sidecar result")
    if value.get("kind") != SIDECAR_ACK_KIND or value.get("accepted") is not True:
        raise HostExecutionError("host did not accept the sidecar message")
    for field, expected in {
        "host_id": binding.host_id, "sidecar_task_id": binding.task_id,
        "cursor": binding.cursor, "capability": binding.capability, "idempotency_key": key,
    }.items():
        if value.get(field) != expected:
            raise HostExecutionError(f"sidecar message acknowledgement has mismatched {field}")
    _required_text(value.get("message_id"), "sidecar message_id")


def _bounded_wait(adapter: HostAdapter, primary: Sequence[Mapping[str, object]], sidecars: Sequence[Mapping[str, object]], timeout: int) -> Mapping[str, object]:
    responses: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)
    def invoke() -> None:
        try:
            responses.put((True, adapter.wait_activity(primary, sidecars)), block=False)
        except BaseException as error:  # propagated on the supervising thread
            responses.put((False, error), block=False)
    thread = threading.Thread(target=invoke, name="hive-sidecar-wait", daemon=True)
    thread.start()
    try:
        ok, value = responses.get(timeout=timeout)
    except queue.Empty as error:
        raise TimeoutError("combined host activity wait exceeded its wall-clock deadline") from error
    if not ok:
        assert isinstance(value, BaseException)
        raise value
    if not isinstance(value, Mapping) or set(value) != {"primary_events", "sidecar_events"}:
        raise HostExecutionError("wait_activity must return exact primary_events and sidecar_events")
    return value


def _validate_creation(
    value: Mapping[str, object],
    instruction_id: str,
    *,
    resource_key: str,
    authority_epoch: int,
) -> _Binding:
    _exact_keys(value, _CREATE_KEYS, "host task binding")
    if value.get("kind") != CREATE_KIND or value.get("idempotency_key") != instruction_id:
        raise HostExecutionError("host task does not bind the launch idempotency key")
    return _Binding(
        instruction_id=instruction_id,
        resource_key=resource_key,
        authority_epoch=authority_epoch,
        dispatch_release_id=None,
        dispatch_admission_epoch=None,
        host_reservation_id="",
        capacity_host_id="",
        capacity_generation="",
        capacity_epoch=0,
        reservation_expires_at="",
        task={},
        host_id=_required_text(value.get("host_id"), "host_id"),
        task_id=_required_text(value.get("task_id"), "task_id"),
        cursor=_required_text(value.get("cursor"), "cursor"),
        capability=_required_text(value.get("capability"), "capability"),
    )


def _validate_adoption(created: _Binding, persisted: Mapping[str, object]) -> None:
    if (
        persisted.get("resource_key") != created.resource_key
        or persisted.get("authority_epoch") != created.authority_epoch
    ):
        raise HostExecutionError("looked-up host task conflicts with the durable authority fence")
    for field, actual in {
        "host_id": created.host_id,
        "task_id": created.task_id,
        "cursor": created.cursor,
    }.items():
        expected = persisted.get(field)
        if expected is not None and expected != actual:
            raise HostExecutionError(f"looked-up host task conflicts with persisted {field}")
    expected_digest = persisted.get("capability_digest")
    actual_digest = "sha256:" + sha256(created.capability.encode("utf-8")).hexdigest()
    if expected_digest is not None and expected_digest != actual_digest:
        raise HostExecutionError("looked-up host task has a different capability")


def _validate_event(value: Mapping[str, object], binding: _Binding) -> None:
    state = value.get("state")
    expected_keys = _EVENT_BASE_KEYS | ({"attention"} if state == "NEEDS_ATTENTION" else set())
    _exact_keys(value, frozenset(expected_keys), "host event")
    if value.get("kind") != EVENT_KIND or state not in EVENT_STATES:
        raise HostExecutionError("host returned an unknown event kind or state")
    for field, expected in {
        "host_id": binding.host_id,
        "task_id": binding.task_id,
        "cursor": binding.cursor,
        "capability": binding.capability,
    }.items():
        if value.get(field) != expected:
            raise HostExecutionError(f"host event has forged or mismatched {field}")
    _required_text(value.get("event_id"), "event_id")
    _required_text(value.get("event_cursor"), "event_cursor")
    if state == "NEEDS_ATTENTION":
        _required_text(value.get("attention"), "attention")


def _validate_ack(value: Mapping[str, object], binding: _Binding, key: str) -> None:
    _exact_keys(value, _ACK_KEYS, "send_message_to_thread result")
    if value.get("kind") != ACK_KIND or value.get("accepted") is not True:
        raise HostExecutionError("host did not accept the recovery message")
    for field, expected in {
        "host_id": binding.host_id,
        "task_id": binding.task_id,
        "cursor": binding.cursor,
        "capability": binding.capability,
        "idempotency_key": key,
    }.items():
        if value.get(field) != expected:
            raise HostExecutionError(f"message acknowledgement has mismatched {field}")
    _required_text(value.get("message_id"), "message_id")


def _notify_primary(
    repo_root: Path,
    adapter: HostAdapter,
    binding: _Binding,
    message: str,
    subject: Mapping[str, object],
    *,
    state_dir: str | Path | None = None,
) -> str:
    key = "sha256:" + sha256(_canonical({"instruction_id": binding.instruction_id, "subject": dict(subject), "message": message})).hexdigest()
    def send() -> Mapping[str, object]:
        ack = adapter.send_message_to_thread(
            host_id=binding.host_id, task_id=binding.task_id, cursor=binding.cursor,
            capability=binding.capability, message=message, idempotency_key=key,
        )
        if not isinstance(ack, Mapping):
            raise HostExecutionError("primary sidecar notification acknowledgement must be an object")
        _validate_ack(ack, binding, key)
        return ack

    ack = _perform_host_effect(
        repo_root,
        binding,
        state_dir,
        adapter=adapter,
        effect_kind="SEND_PRIMARY_MESSAGE",
        idempotency_key=key,
        request={
            "host_id": binding.host_id,
            "task_id": binding.task_id,
            "cursor": binding.cursor,
            "message_digest": digest_json({"message": message}),
            "subject": dict(subject),
        },
        operation=send,
    )
    return str(ack["message_id"])


def _assert_effect_authority(
    repo_root: Path,
    binding: _Binding,
    state_dir: str | Path | None,
) -> None:
    try:
        assert_launch_authority(
            repo_root,
            binding.instruction_id,
            resource_key=binding.resource_key,
            authority_epoch=binding.authority_epoch,
            state_dir=state_dir,
        )
    except OrchestrationError as error:
        raise HostExecutionError(
            f"launch authority was revoked before an effect boundary: {error}"
        ) from error


@contextmanager
def _effect_guard(
    repo_root: Path,
    binding: _Binding | _EffectFence,
    state_dir: str | Path | None,
    *,
    adapter: HostAdapter | None = None,
) -> Iterator[None]:
    dispatcher_entered = False
    try:
        dispatcher_guard = (
            _host_dispatcher_guard(
                adapter,
                binding.task,
                binding.dispatch_release_id,
            )
            if adapter is not None
            else nullcontext(None)
        )
        with dispatcher_guard:
            dispatcher_entered = True
            if state_dir is None:
                raise HostExecutionError(
                    "host effects require an authenticated execution directory"
                )
            execution_directory = Path(state_dir).resolve()
            with runtime_file_lock(
                execution_directory / "locks" / "dispatcher-admission.lock",
                timeout_seconds=120.0,
            ):
                try:
                    assert_execution_authority_open(execution_directory)
                except ConfigurationError as error:
                    raise HostExecutionError(str(error)) from error
                with launch_authority_guard(
                    repo_root,
                    binding.instruction_id,
                    resource_key=binding.resource_key,
                    authority_epoch=binding.authority_epoch,
                    state_dir=execution_directory,
                ):
                    yield
    except Exception as error:
        if adapter is not None and not dispatcher_entered:
            error = _DispatcherEffectRejected(str(error))
        if isinstance(error, _DispatcherEffectRejected):
            try:
                fence_launch(
                    repo_root,
                    binding.instruction_id,
                    actor="host-execution:failed-effect-guard",
                    reason="shared dispatcher rejected an external host effect",
                    state_dir=state_dir,
                )
            except OrchestrationError:
                pass
            raise EffectAuthorityRejected(
                f"dispatcher guard rejected external host effect: {error}"
            ) from error
        if isinstance(error, OrchestrationError):
            raise EffectAuthorityRejected(
                f"launch authority was revoked before an effect boundary: {error}"
            ) from error
        raise


_HOST_EFFECT_FIELDS = frozenset(
    {
        "schema_version",
        "kind",
        "state",
        "effect_id",
        "operation_lease_id",
        "attempt",
        "launch_instruction_id",
        "resource_key",
        "authority_epoch",
        "dispatcher_release_id",
        "dispatcher_admission_epoch",
        "effect_kind",
        "idempotency_key",
        "request_digest",
        "prepared_at",
        "lease_expires_at",
        "completed_at",
        "result_digest",
        "error_code",
        "reconciliation_observation_id",
        "previous_event_id",
        "event_id",
    }
)
_HOST_EFFECT_KINDS = frozenset(
    {
        "CREATE_THREAD",
        "SEND_PRIMARY_MESSAGE",
        "SPAWN_SIDECAR",
        "SEND_SIDECAR_MESSAGE",
        "CLOSE_SIDECAR",
    }
)
_HOST_EFFECT_IDENTITY_FIELDS = frozenset(
    {
        "effect_id",
        "launch_instruction_id",
        "resource_key",
        "authority_epoch",
        "dispatcher_release_id",
        "dispatcher_admission_epoch",
        "effect_kind",
        "idempotency_key",
        "request_digest",
    }
)


def _host_effect_path(
    state_dir: str | Path | None, instruction_id: str
) -> Path:
    if state_dir is None:
        raise HostExecutionError("external host effects require an execution directory")
    if _DIGEST.fullmatch(instruction_id) is None:
        raise HostExecutionError("host effect launch instruction id is invalid")
    directory = Path(state_dir).resolve()
    return directory / "host-effects" / f"{instruction_id.removeprefix('sha256:')}.jsonl"


def _host_effect_events(
    state_dir: str | Path | None, instruction_id: str
) -> tuple[Mapping[str, object], ...]:
    path = _host_effect_path(state_dir, instruction_id)
    try:
        records = strict_jsonl_records(path, label="host effect intent ledger")
        return validate_host_effect_ledger_records(
            records, launch_instruction_id=instruction_id
        )
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
def _append_host_effect_event(
    path: Path,
    events: Sequence[Mapping[str, object]],
    payload: Mapping[str, object],
) -> Mapping[str, object]:
    material = {
        "schema_version": 1,
        "kind": HOST_EFFECT_EVENT_KIND,
        **dict(payload),
        "previous_event_id": events[-1]["event_id"] if events else None,
    }
    event = {**material, "event_id": digest_json(material)}
    try:
        append_jsonl(path, event)
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
    return event


def _effect_binding_document(
    binding: _Binding | _EffectFence,
) -> Mapping[str, object]:
    return {
        "schema_version": 1,
        "kind": "hive-mind-host-effect-binding-fence-v1",
        "launch_instruction_id": binding.instruction_id,
        "resource_key": binding.resource_key,
        "authority_epoch": binding.authority_epoch,
        "dispatcher_release_id": binding.dispatch_release_id,
        "dispatcher_admission_epoch": binding.dispatch_admission_epoch,
    }


def _validate_effect_reconciliation(
    value: object,
    *,
    effect: Mapping[str, object],
    state_dir: str | Path | None,
    expected_host_id: str,
) -> Mapping[str, object]:
    fields = {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "outcome",
        "external_identity",
        "result",
        "unobserved_host_lifecycle_items",
        "observed_at",
        "record_id",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise HostExecutionError("host effect reconciliation has an invalid schema")
    material = dict(value)
    record_id = material.pop("record_id", None)
    if state_dir is None:
        raise HostExecutionError("host effect reconciliation lacks execution identity")
    try:
        identity = read_strict_canonical_json(
            Path(state_dir).resolve() / "execution-identity.json",
            label="host effect execution identity",
        )
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
    external_fields = {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "external_id",
        "record_id",
    }
    unobserved_fields = {
        "schema_version",
        "kind",
        "execution_namespace",
        "execution_id",
        "host_id",
        "effect_kind",
        "idempotency_key",
        "item_type",
        "item_identity",
        "record_id",
    }
    if (
        value.get("schema_version") != 1
        or value.get("kind")
        != "hive-mind-host-effect-reconciliation-observation-v1"
        or not isinstance(identity, Mapping)
        or value.get("execution_namespace") != identity.get("namespace")
        or value.get("execution_id") != identity.get("execution_id")
        or value.get("host_id") != expected_host_id
        or value.get("effect_kind") != effect.get("effect_kind")
        or value.get("idempotency_key") != effect.get("idempotency_key")
        or value.get("outcome") not in {"COMPLETED", "UNKNOWN"}
        or not isinstance(value.get("observed_at"), str)
        or not isinstance(value.get("external_identity"), Mapping)
        or not isinstance(value.get("unobserved_host_lifecycle_items"), list)
        or record_id != digest_json(material)
    ):
        raise HostExecutionError("host effect reconciliation is not authentic")
    try:
        parse_time(value.get("observed_at"))
    except (TypeError, ValueError) as error:
        raise HostExecutionError("host effect reconciliation time is invalid") from error
    external = value["external_identity"]
    assert isinstance(external, Mapping)
    external_material = dict(external)
    external_record_id = external_material.pop("record_id", None)
    if (
        set(external) != external_fields
        or external.get("schema_version") != 1
        or external.get("kind")
        != "hive-mind-host-effect-external-identity-v1"
        or external.get("execution_namespace") != identity.get("namespace")
        or external.get("execution_id") != identity.get("execution_id")
        or external.get("host_id") != expected_host_id
        or external.get("effect_kind") != effect.get("effect_kind")
        or external.get("idempotency_key") != effect.get("idempotency_key")
        or external_record_id != digest_json(external_material)
    ):
        raise HostExecutionError(
            "host effect reconciliation external identity is invalid"
        )
    unobserved = value["unobserved_host_lifecycle_items"]
    assert isinstance(unobserved, list)
    seen_items: set[str] = set()
    for item in unobserved:
        if not isinstance(item, Mapping) or set(item) != unobserved_fields:
            raise HostExecutionError(
                "host effect reconciliation lifecycle item schema is invalid"
            )
        item_material = dict(item)
        item_record_id = item_material.pop("record_id", None)
        if (
            item.get("schema_version") != 1
            or item.get("kind")
            != "hive-mind-unobserved-host-lifecycle-item-v1"
            or item.get("execution_namespace") != identity.get("namespace")
            or item.get("execution_id") != identity.get("execution_id")
            or item.get("host_id") != expected_host_id
            or item.get("effect_kind") != effect.get("effect_kind")
            or item.get("idempotency_key") != effect.get("idempotency_key")
            or item.get("item_type") not in {"THREAD", "TURN", "EFFECT"}
            or not isinstance(item.get("item_identity"), str)
            or not str(item["item_identity"]).strip()
            or item_record_id != digest_json(item_material)
            or item_record_id in seen_items
        ):
            raise HostExecutionError(
                "host effect reconciliation lifecycle item is invalid"
            )
        seen_items.add(str(item_record_id))
    result = value.get("result")
    external_id = external.get("external_id")
    if value.get("outcome") == "COMPLETED":
        if (
            not isinstance(external_id, str)
            or not external_id.strip()
            or not isinstance(result, Mapping)
        ):
            raise HostExecutionError("completed host reconciliation lacks its result")
        if unobserved:
            raise HostExecutionError(
                "completed host reconciliation retains unobserved lifecycle items"
            )
    elif external_id is not None or result is not None or not unobserved:
        raise HostExecutionError("unknown host reconciliation fabricates a result")
    return value


def _prepare_host_effect(
    repo_root: Path,
    binding: _Binding | _EffectFence,
    state_dir: str | Path | None,
    *,
    adapter: HostAdapter,
    effect_kind: str,
    idempotency_key: str,
    request: Mapping[str, object],
) -> tuple[str, Mapping[str, object]]:
    if effect_kind not in _HOST_EFFECT_KINDS or _DIGEST.fullmatch(idempotency_key) is None:
        raise HostExecutionError("host effect identity is invalid")
    request_digest = digest_json(
        {"kind": "hive-mind-host-effect-request-v1", **dict(request)}
    )
    effect_material = {
        "kind": "hive-mind-host-effect-key-v1",
        "launch_instruction_id": binding.instruction_id,
        "resource_key": binding.resource_key,
        "authority_epoch": binding.authority_epoch,
        "dispatcher_release_id": binding.dispatch_release_id,
        "dispatcher_admission_epoch": binding.dispatch_admission_epoch,
        "effect_kind": effect_kind,
        "idempotency_key": idempotency_key,
        "request_digest": request_digest,
    }
    effect_id = digest_json(effect_material)
    path = _host_effect_path(state_dir, binding.instruction_id)
    reconcile_event: Mapping[str, object] | None = None
    with _effect_guard(repo_root, binding, state_dir, adapter=adapter):
        events = list(_host_effect_events(state_dir, binding.instruction_id))
        same_effect = [event for event in events if event.get("effect_id") == effect_id]
        latest = same_effect[-1] if same_effect else None
        now = utc_now()
        if latest is not None and latest.get("state") == "PREPARED":
            if parse_time(latest.get("lease_expires_at")) <= now:
                latest = _append_host_effect_event(
                    path,
                    events,
                    {
                        **{
                            key: latest[key]
                            for key in _HOST_EFFECT_FIELDS
                            if key
                            not in {
                                "schema_version",
                                "kind",
                                "state",
                                "completed_at",
                                "result_digest",
                                "error_code",
                                "previous_event_id",
                                "event_id",
                            }
                        },
                        "state": "RECONCILIATION_REQUIRED",
                        "completed_at": format_time(now),
                        "result_digest": None,
                        "error_code": "OPERATION_LEASE_EXPIRED",
                    },
                )
            reconcile_event = latest
        elif latest is not None and latest.get("state") in {
            "RECONCILIATION_REQUIRED",
            "COMPLETED",
        }:
            reconcile_event = latest
        if reconcile_event is not None:
            pass
        else:
            attempt = max(
                (int(event["attempt"]) for event in same_effect), default=0
            ) + 1
            prepared_at = format_time(now)
            lease_expires_at = format_time(
                now + timedelta(seconds=HOST_EFFECT_LEASE_SECONDS)
            )
            lease_id = digest_json(
                {
                    "kind": "hive-mind-host-effect-operation-lease-v1",
                    "effect_id": effect_id,
                    "attempt": attempt,
                    "prepared_at": prepared_at,
                    "lease_expires_at": lease_expires_at,
                }
            )
            return "EXECUTE", _append_host_effect_event(
                path,
                events,
                {
                    "state": "PREPARED",
                    "effect_id": effect_id,
                    "operation_lease_id": lease_id,
                    "attempt": attempt,
                    "launch_instruction_id": binding.instruction_id,
                    "resource_key": binding.resource_key,
                    "authority_epoch": binding.authority_epoch,
                    "dispatcher_release_id": binding.dispatch_release_id,
                    "dispatcher_admission_epoch": binding.dispatch_admission_epoch,
                    "effect_kind": effect_kind,
                    "idempotency_key": idempotency_key,
                    "request_digest": request_digest,
                    "prepared_at": prepared_at,
                    "lease_expires_at": lease_expires_at,
                    "completed_at": None,
                    "result_digest": None,
                    "error_code": None,
                    "reconciliation_observation_id": None,
                },
            )
    if reconcile_event is None:
        raise HostExecutionError("host effect reconciliation state was lost")
    reader = getattr(adapter, "read_effect_reconciliation", None)
    if not callable(reader):
        raise HostEffectRecoveryRequired(
            "host effect has an ambiguous external outcome or a completed result "
            "that must be adopted; adapter "
            "cannot authenticate reconciliation"
        )
    supplied = reader(
        effect_kind=str(reconcile_event["effect_kind"]),
        idempotency_key=str(reconcile_event["idempotency_key"]),
    )
    if not isinstance(supplied, Mapping):
        raise HostEffectRecoveryRequired(
            "host effect external outcome remains unavailable; recovery is required"
        )
    observed = _validate_effect_reconciliation(
        supplied,
        effect=reconcile_event,
        state_dir=state_dir,
        expected_host_id=_required_text(
            getattr(adapter, "host_id", None), "adapter host_id"
        ),
    )
    with _effect_guard(repo_root, binding, state_dir, adapter=adapter):
        events = list(_host_effect_events(state_dir, binding.instruction_id))
        current = next(
            (
                event
                for event in reversed(events)
                if event.get("effect_id") == effect_id
            ),
            None,
        )
        if current is None or current.get("event_id") != reconcile_event.get("event_id"):
            raise HostExecutionError(
                "host effect changed during external reconciliation"
            )
        payload = {
            key: current[key]
            for key in _HOST_EFFECT_FIELDS
            if key
            not in {
                "schema_version",
                "kind",
                "state",
                "completed_at",
                "result_digest",
                "error_code",
                "reconciliation_observation_id",
                "previous_event_id",
                "event_id",
            }
        }
        if observed["outcome"] == "UNKNOWN":
            if current.get("state") == "PREPARED" and parse_time(
                current.get("lease_expires_at")
            ) > utc_now():
                raise LiveEffectContention(
                    "host effect operation lease is active and host outcome is unknown",
                    current,
                )
            _append_host_effect_event(
                path,
                events,
                {
                    **payload,
                    "state": "RECONCILIATION_REQUIRED",
                    "completed_at": format_time(utc_now()),
                    "result_digest": None,
                    "error_code": "AUTHENTICATED_HOST_OUTCOME_UNKNOWN",
                    "reconciliation_observation_id": observed["record_id"],
                },
            )
            raise HostEffectRecoveryRequired(
                "host effect external outcome is authenticated as unknown; recovery is required"
            )
        completed = _append_host_effect_event(
            path,
            events,
            {
                **payload,
                "state": "COMPLETED",
                "completed_at": format_time(utc_now()),
                "result_digest": digest_json(
                    {
                        "kind": "hive-mind-host-effect-result-v1",
                        **dict(observed["result"]),
                    }
                ),
                "error_code": None,
                "reconciliation_observation_id": observed["record_id"],
            },
        )
    return "ADOPTED", dict(observed["result"])


def _complete_host_effect(
    repo_root: Path,
    binding: _Binding | _EffectFence,
    state_dir: str | Path | None,
    *,
    adapter: HostAdapter,
    prepared: Mapping[str, object],
    state: str,
    result_digest: str | None,
    error_code: str | None,
) -> Mapping[str, object]:
    path = _host_effect_path(state_dir, binding.instruction_id)

    def append_terminal(
        terminal_state: str,
        terminal_result_digest: str | None,
        terminal_error_code: str | None,
    ) -> Mapping[str, object]:
        events = list(_host_effect_events(state_dir, binding.instruction_id))
        current = next(
            (
                event
                for event in reversed(events)
                if event.get("effect_id") == prepared.get("effect_id")
                and event.get("attempt") == prepared.get("attempt")
            ),
            None,
        )
        if current is None:
            raise HostExecutionError("host effect operation lease disappeared")
        if current.get("state") != "PREPARED":
            if current.get("state") == terminal_state:
                return current
            raise HostExecutionError(
                "host effect operation lease was terminalized by another actor"
            )
        payload = {
            key: prepared[key]
            for key in _HOST_EFFECT_FIELDS
            if key
            not in {
                "schema_version",
                "kind",
                "state",
                "completed_at",
                "result_digest",
                "error_code",
                "reconciliation_observation_id",
                "previous_event_id",
                "event_id",
            }
        }
        return _append_host_effect_event(
            path,
            events,
            {
                **payload,
                "state": terminal_state,
                "completed_at": format_time(utc_now()),
                "result_digest": terminal_result_digest,
                "error_code": terminal_error_code,
                "reconciliation_observation_id": prepared.get(
                    "reconciliation_observation_id"
                ),
            },
        )

    if state == "COMPLETED":
        try:
            with _effect_guard(repo_root, binding, state_dir, adapter=adapter):
                return append_terminal(state, result_digest, error_code)
        except Exception as error:
            # The external result exists but its old launch authority no longer
            # authorizes publication. Persist ambiguity under only the binding
            # lock; this is evidence, never renewed execution authority.
            if state_dir is None:
                raise
            with runtime_file_lock(
                Path(state_dir).resolve() / "locks" / "task-bindings.lock",
                timeout_seconds=120.0,
            ):
                append_terminal(
                    "RECONCILIATION_REQUIRED",
                    result_digest,
                    f"AUTHORITY_REVALIDATION_FAILED:{type(error).__name__}",
                )
            raise HostExecutionError(
                "host effect completed after authority revocation; reconciliation is required"
            ) from error
    # Reconciliation evidence must remain writable even after authority loss.
    if state_dir is None:
        raise HostExecutionError("host effect reconciliation requires an execution directory")
    with runtime_file_lock(
        Path(state_dir).resolve() / "locks" / "task-bindings.lock",
        timeout_seconds=120.0,
    ):
        return append_terminal(state, result_digest, error_code)


def _perform_host_effect(
    repo_root: Path,
    binding: _Binding | _EffectFence,
    state_dir: str | Path | None,
    *,
    adapter: HostAdapter,
    effect_kind: str,
    idempotency_key: str,
    request: Mapping[str, object],
    operation: Callable[[], _EffectResult],
) -> _EffectResult:
    """Persist intent, release every authority lock, perform I/O, then revalidate."""

    disposition, prepared = _prepare_host_effect(
        repo_root,
        binding,
        state_dir,
        adapter=adapter,
        effect_kind=effect_kind,
        idempotency_key=idempotency_key,
        request=request,
    )
    if disposition == "ADOPTED":
        return prepared  # type: ignore[return-value]
    try:
        result = operation()
        if not isinstance(result, Mapping):
            raise HostExecutionError("external host effect must return an object")
        result_digest = digest_json(
            {"kind": "hive-mind-host-effect-result-v1", **dict(result)}
        )
    except Exception as error:
        _complete_host_effect(
            repo_root,
            binding,
            state_dir,
            adapter=adapter,
            prepared=prepared,
            state="RECONCILIATION_REQUIRED",
            result_digest=None,
            error_code=f"EXTERNAL_EFFECT_AMBIGUOUS:{type(error).__name__}",
        )
        raise
    _complete_host_effect(
        repo_root,
        binding,
        state_dir,
        adapter=adapter,
        prepared=prepared,
        state="COMPLETED",
        result_digest=result_digest,
        error_code=None,
    )
    return result


def _host_dispatcher_guard(
    adapter: HostAdapter,
    task: Mapping[str, object],
    release_id: str | None,
) -> AbstractContextManager[object]:
    if task.get("authority_class") != "WRITE_AUTHORIZED":
        return nullcontext(None)
    if release_id is None:
        raise HostExecutionError("write-authorized task lacks dispatcher release authority")
    guard = getattr(adapter, "dispatcher_effect_guard", None)
    if not callable(guard):
        raise HostExecutionError(
            "host adapter cannot fence effects to the shared dispatcher release"
        )
    return guard(node_id=str(task["node_id"]), release_id=release_id)


def _authenticated_host_capacity(
    adapter: HostAdapter,
    repo_root: Path,
    host_runtime_dir: Path,
) -> Mapping[str, object]:
    provider = getattr(adapter, "host_capacity_authority", None)
    if not callable(provider):
        raise HostExecutionError(
            "host adapter has no authenticated launch-capacity capability"
        )
    supplied = provider(repo_root=repo_root)
    if not isinstance(supplied, Mapping):
        raise HostExecutionError("host capacity authority must be an object")
    host_id = supplied.get("host_id")
    if not isinstance(host_id, str) or not host_id.strip():
        raise HostExecutionError("host capacity authority lacks a stable host id")
    try:
        installed = read_host_capacity(
            host_runtime_dir, host_id, now=utc_now()
        )
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
    if dict(supplied) != dict(installed):
        raise HostExecutionError(
            "host adapter capacity does not match the installed generation"
        )
    return installed


def _authenticated_lifecycle_capability(
    adapter: HostAdapter,
    repo_root: Path,
) -> Mapping[str, object]:
    provider = getattr(adapter, "host_lifecycle_authority", None)
    if not callable(provider):
        raise HostExecutionError(
            "host adapter has no authenticated lifecycle capability"
        )
    supplied = provider(repo_root=repo_root)
    fields = {
        "schema_version",
        "kind",
        "host_id",
        "create",
        "query",
        "resume",
        "interrupt",
        "archive",
        "autonomous_launch",
        "source",
        "record_id",
    }
    if not isinstance(supplied, Mapping) or set(supplied) != fields:
        raise HostExecutionError("host lifecycle capability schema is invalid")
    material = dict(supplied)
    record_id = material.pop("record_id", None)
    if (
        supplied.get("schema_version") != 1
        or supplied.get("kind")
        != "hive-mind-host-lifecycle-capability-v1"
        or not isinstance(supplied.get("host_id"), str)
        or not str(supplied["host_id"]).strip()
        or not isinstance(supplied.get("source"), str)
        or not str(supplied["source"]).strip()
        or any(
            type(supplied.get(field)) is not bool
            for field in (
                "create",
                "query",
                "resume",
                "interrupt",
                "archive",
                "autonomous_launch",
            )
        )
        or record_id != "sha256:" + sha256(_canonical(material)).hexdigest()
    ):
        raise HostExecutionError("host lifecycle capability is invalid")
    return supplied


@contextmanager
def _host_repository_admission_guard(
    *,
    host_runtime_dir: Path,
    coordination_dir: Path,
    execution_dir: Path,
    adapter: HostAdapter,
    task: Mapping[str, object],
    release_id: str | None,
) -> Iterator[None]:
    """Short admission lock order: host -> repository -> dispatcher."""

    with runtime_file_lock(
        host_runtime_dir / "locks" / "host-authority.lock",
        timeout_seconds=120.0,
    ):
        with runtime_file_lock(
            coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock",
            timeout_seconds=120.0,
        ):
            with runtime_file_lock(
                execution_dir / "locks" / "dispatcher-admission.lock",
                timeout_seconds=120.0,
            ):
                with _host_dispatcher_guard(adapter, task, release_id):
                    yield


def _release_primary_capacity(
    *,
    repo_root: Path,
    host_runtime_dir: Path,
    coordination_dir: Path,
    execution_dir: Path,
    execution_id: str,
    execution_namespace: str,
    binding: _Binding,
    actor: str,
    reason: str,
    local_terminal_event: Mapping[str, object],
) -> Mapping[str, object]:
    with runtime_file_lock(
        host_runtime_dir / "locks" / "host-authority.lock",
        timeout_seconds=120.0,
    ):
        with runtime_file_lock(
            coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock",
            timeout_seconds=120.0,
        ):
            try:
                reservation = global_host_reservation_record(
                    host_runtime_dir, binding.host_reservation_id
                )
                if reservation is None:
                    raise HostExecutionError("primary host reservation is absent")
                if (
                    reservation.get("reservation_kind") != "PRIMARY"
                    or reservation.get("execution_id") != execution_id
                    or reservation.get("resource_key") != binding.resource_key
                    or reservation.get("host_id") != binding.capacity_host_id
                    or reservation.get("capacity_generation")
                    != binding.capacity_generation
                ):
                    raise HostExecutionError(
                        "primary host reservation differs from its durable launch fence"
                    )
                return release_global_host_session(
                    host_runtime_dir,
                    binding.host_reservation_id,
                    execution_id=execution_id,
                    local_reservation_id=str(reservation["local_reservation_id"]),
                    capacity_generation=binding.capacity_generation,
                    actor=actor,
                    reason=reason,
                    released_at=format_time(utc_now()),
                    local_terminal_event=local_terminal_event,
                    repo_root=repo_root,
                    coordination_dir=coordination_dir,
                    execution_dir=execution_dir,
                    execution_namespace=execution_namespace,
                )
            except ConfigurationError as error:
                raise HostExecutionError(str(error)) from error


def _renew_execution_host_reservations(
    *,
    host_runtime_dir: Path,
    execution_id: str,
    capacity: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    """Renew near-expiry permits while their authenticated generation is live."""

    now = utc_now()
    renewed: list[Mapping[str, object]] = []
    with runtime_file_lock(
        host_runtime_dir / "locks" / "host-authority.lock",
        timeout_seconds=120.0,
    ):
        reservations = active_global_host_reservations(host_runtime_dir)
        capacity_expiry = parse_time(capacity.get("expires_at"))
        for reservation in reservations:
            if (
                reservation.get("execution_id") != execution_id
                or reservation.get("reservation_kind")
                not in {"PRIMARY", "SIDECAR"}
            ):
                continue
            expiry = parse_time(reservation.get("expires_at"))
            if expiry <= now:
                # A clock can request reconciliation but can never free or
                # extend a task whose external lifecycle is unknown.
                continue
            if expiry - now > timedelta(minutes=30):
                continue
            requested = min(capacity_expiry, now + timedelta(minutes=90))
            if requested <= expiry:
                continue
            try:
                renewed.append(
                    renew_global_host_session(
                        host_runtime_dir,
                        str(reservation["reservation_id"]),
                        execution_id=execution_id,
                        local_reservation_id=str(
                            reservation["local_reservation_id"]
                        ),
                        capacity_generation=str(
                            reservation["capacity_generation"]
                        ),
                        actor="host-execution:supervisor-renewal",
                        reason="active supervised host task remains lifecycle-observable",
                        renewed_at=format_time(now),
                        expires_at=format_time(requested),
                        now=now,
                    )
                )
            except ConfigurationError as error:
                raise HostExecutionError(str(error)) from error
    return tuple(renewed)


def _release_terminal_sidecar_capacity(
    *,
    repo_root: Path,
    state_dir: str | Path,
    host_runtime_dir: Path,
    coordination_dir: Path,
    execution_id: str,
    execution_namespace: str,
) -> tuple[Mapping[str, object], ...]:
    terminal_events = [
        event
        for event in latest_sidecars(repo_root, state_dir=state_dir).values()
        if event.get("state")
        in {"SUCCEEDED", "FAILED", "CANCELLED", "SPAWN_FAILED", "SKIPPED_CAPACITY"}
        and isinstance(event.get("host_reservation_id"), str)
    ]
    released: list[Mapping[str, object]] = []
    with runtime_file_lock(
        host_runtime_dir / "locks" / "host-authority.lock",
        timeout_seconds=120.0,
    ):
        with runtime_file_lock(
            coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock",
            timeout_seconds=120.0,
        ):
            for event in terminal_events:
                try:
                    released.append(
                        release_global_host_session(
                            host_runtime_dir,
                            str(event["host_reservation_id"]),
                            execution_id=execution_id,
                            local_reservation_id=str(event["sidecar_id"]),
                            capacity_generation=str(event["capacity_generation"]),
                            actor="host-execution:terminal-sidecar",
                            reason=f"durable sidecar terminal state {event['state']}",
                            released_at=format_time(utc_now()),
                            local_terminal_event=event,
                            repo_root=repo_root,
                            coordination_dir=coordination_dir,
                            execution_dir=state_dir,
                            execution_namespace=execution_namespace,
                        )
                    )
                except ConfigurationError as error:
                    raise HostExecutionError(str(error)) from error
    return tuple(released)


def _latest_local_reservation(
    repo_root: Path,
    state_dir: str | Path,
    reservation_id: str,
) -> tuple[str, Mapping[str, object]] | None:
    primary_latest: dict[str, Mapping[str, object]] = {}
    for event in binding_events(repo_root, state_dir=state_dir):
        instruction_id = event.get("launch_instruction_id")
        if isinstance(instruction_id, str):
            primary_latest[instruction_id] = event
    primary = [
        event
        for event in primary_latest.values()
        if event.get("host_reservation_id") == reservation_id
    ]
    sidecars = [
        event
        for event in latest_sidecars(repo_root, state_dir=state_dir).values()
        if event.get("host_reservation_id") == reservation_id
    ]
    if len(primary) + len(sidecars) > 1:
        raise HostExecutionError(
            "one global host reservation maps to multiple local bindings"
        )
    if primary:
        return "PRIMARY", primary[0]
    if sidecars:
        return "SIDECAR", sidecars[0]
    return None


def _local_host_terminal_is_authoritative(
    local_kind: str, event: Mapping[str, object]
) -> bool:
    if local_kind == "PRIMARY":
        return (
            event.get("state") == "RELEASED"
            and event.get("terminal_state") in TERMINAL_STATES
            and isinstance(event.get("host_event_id"), str)
            and _DIGEST.fullmatch(str(event["host_event_id"])) is not None
        )
    if event.get("state") == "SPAWN_FAILED":
        return True
    return (
        event.get("state") in {"SUCCEEDED", "FAILED", "CANCELLED"}
        and isinstance(event.get("host_event_id"), str)
        and _DIGEST.fullmatch(str(event["host_event_id"])) is not None
    )


def recover_expired_host_reservation(
    repo_root: Path,
    reservation_id: str,
    *,
    execution_dir: str | Path,
    execution_id: str,
    execution_namespace: str,
    host_runtime_dir: str | Path,
    adapter: HostAdapter,
    actor: str,
    reason: str,
) -> Mapping[str, object]:
    """Reconcile one expired permit without freeing capacity on a clock alone.

    Host observation is deliberately performed with no authority lock held. The
    second phase reacquires host -> repository -> dispatcher -> binding, proves
    both ledgers are unchanged, durably fences local execution, and only then
    terminalizes the machine-global permit.
    """

    if _DIGEST.fullmatch(reservation_id) is None or not actor.strip() or not reason.strip():
        raise HostExecutionError("expired host reservation recovery evidence is invalid")
    try:
        directory = require_execution_authority_dir(
            repo_root,
            execution_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
        )
        host_runtime = require_host_runtime(host_runtime_dir)
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
    coordination_dir = directory.parents[1]
    now = utc_now()
    with runtime_file_lock(
        host_runtime / "locks" / "host-authority.lock", timeout_seconds=120.0
    ):
        reservation = global_host_reservation_record(host_runtime, reservation_id)
        if reservation is None:
            raise HostExecutionError("expired host reservation is absent")
        if reservation.get("execution_id") != execution_id:
            raise HostExecutionError("expired host reservation execution fence mismatch")
        if reservation.get("state") in {"RELEASED", "EXPIRED_FENCED"}:
            return {
                "schema_version": 1,
                "kind": "hive-mind-host-reservation-recovery-v1",
                "state": "ALREADY_TERMINAL",
                "reservation": dict(reservation),
            }
        if parse_time(reservation.get("expires_at")) > now:
            return {
                "schema_version": 1,
                "kind": "hive-mind-host-reservation-recovery-v1",
                "state": "LIVE",
                "reservation": dict(reservation),
            }
    local = _latest_local_reservation(repo_root, directory, reservation_id)
    if local is None:
        # The global permit is reserved before local PREPARED. A crash in that
        # narrow window has no host effect to cancel, but capacity may be freed
        # only after proving both the local ledger and every effect ledger lack
        # the exact intent. A still-current dispatcher release remains a
        # coordinator reconciliation obligation; it is never silently rewritten.
        with runtime_file_lock(
            host_runtime / "locks" / "host-authority.lock", timeout_seconds=120.0
        ):
            with runtime_file_lock(
                coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock",
                timeout_seconds=120.0,
            ):
                with runtime_file_lock(
                    directory / "locks" / "dispatcher-admission.lock",
                    timeout_seconds=120.0,
                ):
                    with runtime_file_lock(
                        directory / "locks" / "task-bindings.lock",
                        timeout_seconds=120.0,
                    ):
                        current_reservation = global_host_reservation_record(
                            host_runtime, reservation_id
                        )
                        if (
                            current_reservation is None
                            or current_reservation.get("event_id")
                            != reservation.get("event_id")
                            or current_reservation.get("state")
                            not in {"RESERVED", "RENEWED"}
                            or parse_time(current_reservation.get("expires_at")) > utc_now()
                        ):
                            raise HostExecutionError(
                                "unbound host reservation changed during recovery"
                            )
                        if _latest_local_reservation(
                            repo_root, directory, reservation_id
                        ) is not None:
                            raise HostExecutionError(
                                "local host binding appeared during unbound recovery"
                            )

                        def contains_exact(value: object, expected: str) -> bool:
                            if value == expected:
                                return True
                            if isinstance(value, Mapping):
                                return any(
                                    contains_exact(item, expected)
                                    for item in value.values()
                                )
                            if isinstance(value, list):
                                return any(contains_exact(item, expected) for item in value)
                            return False

                        effect_root = directory / "host-effects"
                        if effect_root.is_dir():
                            for effect_path in sorted(effect_root.glob("*.jsonl")):
                                for effect in strict_jsonl_records(
                                    effect_path,
                                    label="unbound host-effect recovery evidence",
                                ):
                                    if contains_exact(effect, reservation_id) or contains_exact(
                                        effect,
                                        str(current_reservation["local_reservation_id"]),
                                    ):
                                        return {
                                            "schema_version": 1,
                                            "kind": "hive-mind-host-reservation-recovery-v1",
                                            "state": "RECOVERY_REQUIRED",
                                            "reservation_id": reservation_id,
                                            "reason": (
                                                "unbound permit has host-effect evidence; "
                                                "external outcome is ambiguous"
                                            ),
                                        }
                        release_path = directory / "dispatcher-release.json"
                        if release_path.is_file():
                            release = read_strict_canonical_json(
                                release_path,
                                label="unbound reservation dispatcher release",
                            )
                            if contains_exact(release, reservation_id):
                                return {
                                    "schema_version": 1,
                                    "kind": "hive-mind-host-reservation-recovery-v1",
                                    "state": "RECOVERY_REQUIRED",
                                    "reservation_id": reservation_id,
                                    "reason": (
                                        "current dispatcher release still owns the unbound "
                                        "permit; reconcile or replace that release"
                                    ),
                                }
                        return {
                            "schema_version": 1,
                            "kind": "hive-mind-host-reservation-recovery-v1",
                            "state": "RECOVERY_REQUIRED",
                            "reservation_id": reservation_id,
                            "reason": (
                                "unbound primary permit has no authenticated durable "
                                "PRE_LAUNCH_ABORT dispatcher receipt; it remains charged"
                            ),
                        }
    local_kind, local_event = local
    if reservation.get("reservation_kind") != local_kind:
        raise HostExecutionError("global and local reservation kinds differ")

    observation: Mapping[str, object] | None = None
    if not _local_host_terminal_is_authoritative(local_kind, local_event):
        observer = getattr(adapter, "observe_task_lifecycle", None)
        if not callable(observer):
            return {
                "schema_version": 1,
                "kind": "hive-mind-host-reservation-recovery-v1",
                "state": "WAITING_FOR_HOST",
                "reservation_id": reservation_id,
                "reason": "host adapter cannot authenticate task lifecycle",
            }
        observation_key = digest_json(
            {
                "kind": "hive-mind-host-reservation-observation-request-v1",
                "reservation_id": reservation_id,
                "local_event_id": local_event.get("event_id"),
            }
        )
        supplied = observer(
            reservation=dict(reservation),
            local_binding=dict(local_event),
            idempotency_key=observation_key,
        )
        if not isinstance(supplied, Mapping):
            return {
                "schema_version": 1,
                "kind": "hive-mind-host-reservation-recovery-v1",
                "state": "WAITING_FOR_HOST",
                "reservation_id": reservation_id,
                "reason": "host lifecycle observation is unavailable",
            }
        try:
            observation = validate_host_lifecycle_observation(
                supplied, reservation=reservation, now=utc_now()
            )
        except ConfigurationError as error:
            raise HostExecutionError(str(error)) from error
        for observation_field, local_field in (
            ("host_id", "host_id"),
            (
                "host_task_id",
                "task_id" if local_kind == "PRIMARY" else "sidecar_task_id",
            ),
            ("host_cursor", "cursor"),
            ("capability_digest", "capability_digest"),
        ):
            expected = local_event.get(local_field)
            if expected is not None and observation.get(observation_field) != expected:
                raise HostExecutionError(
                    f"host lifecycle observation changed local {local_field}"
                )

    with runtime_file_lock(
        host_runtime / "locks" / "host-authority.lock", timeout_seconds=120.0
    ):
        with runtime_file_lock(
            coordination_dir / "arbiter" / "locks" / "arbiter-authority.lock",
            timeout_seconds=120.0,
        ):
            with runtime_file_lock(
                directory / "locks" / "dispatcher-admission.lock",
                timeout_seconds=120.0,
            ):
                with runtime_file_lock(
                    directory / "locks" / "task-bindings.lock",
                    timeout_seconds=120.0,
                ):
                    current_reservation = global_host_reservation_record(
                        host_runtime, reservation_id
                    )
                    if current_reservation is None:
                        raise HostExecutionError(
                            "host reservation disappeared during reconciliation"
                        )
                    current_local = _latest_local_reservation(
                        repo_root, directory, reservation_id
                    )
                    if (
                        current_local is None
                        or current_local[0] != local_kind
                        or current_local[1].get("event_id")
                        != local_event.get("event_id")
                    ):
                        raise HostExecutionError(
                            "local host binding changed during lifecycle observation"
                        )
                    terminal_event = current_local[1]
                    if not _local_host_terminal_is_authoritative(
                        local_kind, terminal_event
                    ):
                        if observation is None:
                            raise HostExecutionError(
                                "host lifecycle recovery lacks authenticated observation"
                            )
                        if local_kind == "PRIMARY":
                            terminal_event = fence_launch(
                                repo_root,
                                str(terminal_event["launch_instruction_id"]),
                                actor=actor,
                                reason=(
                                    reason
                                    + "; lifecycle_observation="
                                    + str(observation["observation_id"])
                                ),
                                state_dir=directory,
                            )
                        else:
                            parent_id = terminal_event.get(
                                "parent_launch_instruction_id"
                            )
                            if not isinstance(parent_id, str):
                                raise HostExecutionError(
                                    "expired sidecar lacks exact parent launch"
                                )
                            fence_launch(
                                repo_root,
                                parent_id,
                                actor=actor,
                                reason=(
                                    reason
                                    + "; expired sidecar lifecycle_observation="
                                    + str(observation["observation_id"])
                                ),
                                state_dir=directory,
                            )
                            refreshed = _latest_local_reservation(
                                repo_root, directory, reservation_id
                            )
                            if refreshed is None or refreshed[1].get("state") != "ORPHANED":
                                raise HostExecutionError(
                                    "parent fence did not terminalize its expired sidecar"
                                )
                            terminal_event = refreshed[1]
                    terminal_event_id = terminal_event.get("event_id")
                    if not isinstance(terminal_event_id, str):
                        raise HostExecutionError(
                            "local reservation terminal event has no digest"
                        )
                    if observation is None:
                        released = release_global_host_session(
                            host_runtime,
                            reservation_id,
                            execution_id=execution_id,
                            local_reservation_id=str(
                                current_reservation["local_reservation_id"]
                            ),
                            capacity_generation=str(
                                current_reservation["capacity_generation"]
                            ),
                            actor=actor,
                            reason=reason,
                            released_at=format_time(utc_now()),
                            local_terminal_event=terminal_event,
                            repo_root=repo_root,
                            coordination_dir=coordination_dir,
                            execution_dir=directory,
                            execution_namespace=execution_namespace,
                        )
                    else:
                        released = fence_expired_global_host_session(
                            host_runtime,
                            reservation_id,
                            execution_id=execution_id,
                            local_reservation_id=str(
                                current_reservation["local_reservation_id"]
                            ),
                            capacity_generation=str(
                                current_reservation["capacity_generation"]
                            ),
                            actor=actor,
                            reason=reason,
                            fenced_at=format_time(utc_now()),
                            now=utc_now(),
                            lifecycle_observation=observation,
                            local_terminal_event_id=terminal_event_id,
                        )
    return {
        "schema_version": 1,
        "kind": "hive-mind-host-reservation-recovery-v1",
        "state": "RECOVERED",
        "reservation": dict(released),
        "local_terminal_event": dict(terminal_event),
        "lifecycle_observation": dict(observation) if observation is not None else None,
    }


def reconcile_global_expired_host_reservations(
    host_runtime_dir: str | Path,
    *,
    adapter_resolver: Callable[..., HostAdapter | None],
    repository_root_resolver: Callable[[Mapping[str, object]], Path | None],
    actor: str,
    reason: str,
) -> tuple[Mapping[str, object], ...]:
    """Reconcile expired permits across every registered repository.

    Inventory is captured under the short host lock. Repository discovery and
    host lifecycle I/O happen after releasing it; each individual recovery then
    reacquires host -> repository -> execution locks and revalidates both ledger
    heads. A missing checkout, live task, or unreachable host remains charged.
    """

    if (
        not callable(repository_root_resolver)
        or not callable(adapter_resolver)
        or not actor.strip()
        or not reason.strip()
    ):
        raise HostExecutionError("global host reconciliation inputs are invalid")
    try:
        host_runtime = require_host_runtime(host_runtime_dir)
        now = utc_now()
        with runtime_file_lock(
            host_runtime / "locks" / "host-authority.lock",
            timeout_seconds=120.0,
        ):
            reservations = tuple(active_global_host_reservations(host_runtime))
            registry = tuple(host_repository_registry_bindings(host_runtime))
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
    bindings_by_repository: dict[str, Mapping[str, object]] = {}
    for binding in registry:
        repository = str(binding.get("repository"))
        if repository in bindings_by_repository:
            raise HostExecutionError(
                "host repository registry contains duplicate authority"
            )
        bindings_by_repository[repository] = binding
    results: list[Mapping[str, object]] = []
    for reservation in reservations:
        try:
            expires = parse_time(reservation.get("expires_at"))
        except (TypeError, ValueError) as error:
            raise HostExecutionError("global reservation expiry is malformed") from error
        if expires > now:
            continue
        reservation_id = str(reservation.get("reservation_id"))
        repository_binding = bindings_by_repository.get(
            str(reservation.get("repository"))
        )
        if repository_binding is None:
            results.append(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-global-host-reconciliation-v1",
                    "state": "RECOVERY_REQUIRED",
                    "reservation_id": reservation_id,
                    "reason": "repository has no authenticated host registry binding",
                }
            )
            continue
        try:
            repo_root = repository_root_resolver(dict(repository_binding))
        except Exception as error:
            results.append(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-global-host-reconciliation-v1",
                    "state": "WAITING_FOR_REPOSITORY",
                    "reservation_id": reservation_id,
                    "reason": f"repository resolver failed: {type(error).__name__}",
                }
            )
            continue
        if repo_root is None:
            results.append(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-global-host-reconciliation-v1",
                    "state": "WAITING_FOR_REPOSITORY",
                    "reservation_id": reservation_id,
                    "reason": "registered repository checkout is unavailable",
                }
            )
            continue
        try:
            canonical_coordination = resolve_repository_state_dir(repo_root)
            registered_coordination = Path(
                str(repository_binding["coordination_dir"])
            ).resolve()
            if canonical_coordination != registered_coordination:
                raise HostExecutionError(
                    "repository resolver points at another coordination authority"
                )
            execution_id = str(reservation.get("execution_id"))
            if _DIGEST.fullmatch(execution_id) is None:
                raise HostExecutionError("global reservation execution id is invalid")
            execution_dir = (
                registered_coordination
                / "executions"
                / execution_id.removeprefix("sha256:")
            )
            identity = read_strict_canonical_json(
                execution_dir / "execution-identity.json",
                label="global reconciliation execution identity",
            )
            if (
                not isinstance(identity, Mapping)
                or identity.get("execution_id") != execution_id
                or identity.get("repository") != repository_binding.get("repository")
                or identity.get("repository_transport_digest")
                != repository_binding.get("transport_digest")
                or not isinstance(identity.get("namespace"), str)
            ):
                raise HostExecutionError(
                    "global reconciliation execution identity is invalid"
                )
            if reservation.get("reservation_kind") == "VALIDATION":
                plane = ControlPlane(
                    Path(repo_root),
                    state_dir=registered_coordination,
                    execution_namespace=str(identity["namespace"]),
                    host_runtime_dir=host_runtime,
                )
                result = plane.recover_expired_keyed_validation_lease_internal(
                    actor=actor,
                    host_reservation_id=reservation_id,
                    reason=reason,
                )
            else:
                adapter = adapter_resolver(
                    reservation=dict(reservation),
                    repository_binding=dict(repository_binding),
                    execution_identity=dict(identity),
                    repo_root=Path(repo_root),
                    execution_dir=execution_dir,
                )
                if adapter is None:
                    raise HostExecutionError(
                        "owning execution host adapter is unavailable"
                    )
                if (
                    Path(str(getattr(adapter, "repo_root", ""))).resolve()
                    != Path(repo_root).resolve()
                    or Path(
                        str(getattr(adapter, "execution_dir", ""))
                    ).resolve()
                    != execution_dir.resolve()
                    or str(getattr(adapter, "execution_id", "")) != execution_id
                    or str(getattr(adapter, "execution_namespace", ""))
                    != str(identity["namespace"])
                    or Path(
                        str(getattr(adapter, "host_runtime_dir", ""))
                    ).resolve()
                    != host_runtime.resolve()
                ):
                    raise HostExecutionError(
                        "resolved host adapter is not bound to the owning repository execution"
                    )
                lifecycle = _authenticated_lifecycle_capability(
                    adapter, Path(repo_root)
                )
                with runtime_file_lock(
                    host_runtime / "locks" / "host-authority.lock",
                    timeout_seconds=120.0,
                ):
                    provider = _host_provider_binding(
                        host_runtime,
                        host_id=str(reservation["host_id"]),
                    )
                    current_reservation = global_host_reservation_record(
                        host_runtime, reservation_id
                    )
                if (
                    current_reservation is None
                    or current_reservation.get("state")
                    not in {"RESERVED", "RENEWED"}
                    or current_reservation.get("event_id")
                    != reservation.get("event_id")
                    or lifecycle.get("host_id") != reservation.get("host_id")
                    or provider.get("provider_generation")
                    != reservation.get("provider_generation")
                    or provider.get("provider_epoch")
                    != reservation.get("provider_epoch")
                    or getattr(adapter, "provider_identity_digest", None)
                    != provider.get("provider_identity_digest")
                ):
                    raise HostExecutionError(
                        "resolved host adapter provider generation or reservation fence changed"
                    )
                result = recover_expired_host_reservation(
                    Path(repo_root),
                    reservation_id,
                    execution_dir=execution_dir,
                    execution_id=execution_id,
                    execution_namespace=str(identity["namespace"]),
                    host_runtime_dir=host_runtime,
                    adapter=adapter,
                    actor=actor,
                    reason=reason,
                )
        except (ConfigurationError, HostExecutionError) as error:
            results.append(
                {
                    "schema_version": 1,
                    "kind": "hive-mind-global-host-reconciliation-v1",
                    "state": "RECOVERY_REQUIRED",
                    "reservation_id": reservation_id,
                    "reason": str(error),
                }
            )
            continue
        results.append(
            {
                "schema_version": 1,
                "kind": "hive-mind-global-host-reconciliation-v1",
                "state": result.get("state"),
                "reservation_id": reservation_id,
                "repository": reservation.get("repository"),
                "execution_id": reservation.get("execution_id"),
                "result": dict(result),
            }
        )
    return tuple(results)


def _record_sidecar_authorized(
    repo_root: Path,
    parent: _Binding,
    sidecar_id: str,
    state: str,
    *,
    adapter: HostAdapter,
    state_dir: str | Path | None = None,
    **fields: object,
) -> Mapping[str, object]:
    with _effect_guard(repo_root, parent, state_dir, adapter=adapter):
        return record_sidecar_state(
            repo_root,
            sidecar_id,
            state,
            state_dir=state_dir,
            parent_resource_key=parent.resource_key,
            parent_authority_epoch=parent.authority_epoch,
            parent_authority_class=parent.task.get("authority_class"),
            parent_dispatcher_release_id=parent.dispatch_release_id,
            parent_dispatcher_admission_epoch=parent.dispatch_admission_epoch,
            **fields,
        )


def _notify_sidecar(
    repo_root: Path,
    adapter: HostAdapter,
    binding: _SidecarBinding,
    message: str,
    subject: Mapping[str, object],
    *,
    state_dir: str | Path | None = None,
) -> str:
    key = "sha256:" + sha256(_canonical({"sidecar_id": binding.sidecar_id, "subject": dict(subject), "message": message})).hexdigest()
    def send() -> Mapping[str, object]:
        ack = adapter.send_message_to_sidecar(
            host_id=binding.host_id, sidecar_task_id=binding.task_id, cursor=binding.cursor,
            capability=binding.capability, message=message, idempotency_key=key,
        )
        if not isinstance(ack, Mapping):
            raise HostExecutionError("sidecar notification acknowledgement must be an object")
        _validate_sidecar_ack(ack, binding, key)
        return ack

    ack = _perform_host_effect(
        repo_root,
        binding.parent,
        state_dir,
        adapter=adapter,
        effect_kind="SEND_SIDECAR_MESSAGE",
        idempotency_key=key,
        request={
            "sidecar_id": binding.sidecar_id,
            "host_id": binding.host_id,
            "sidecar_task_id": binding.task_id,
            "cursor": binding.cursor,
            "message_digest": digest_json({"message": message}),
            "subject": dict(subject),
        },
        operation=send,
    )
    return str(ack["message_id"])


def _close_sidecar(
    repo_root: Path,
    adapter: HostAdapter,
    binding: _SidecarBinding,
    reason: str,
    *,
    state_dir: str | Path | None = None,
) -> Mapping[str, object]:
    key = "sha256:" + sha256(_canonical({"sidecar_id": binding.sidecar_id, "reason": reason})).hexdigest()
    def close() -> Mapping[str, object]:
        raw = adapter.close_sidecar(
            host_id=binding.host_id, sidecar_task_id=binding.task_id, cursor=binding.cursor,
            capability=binding.capability, reason=reason, idempotency_key=key,
        )
        if not isinstance(raw, Mapping):
            raise HostExecutionError("close_sidecar must return a terminal sidecar event")
        _validate_sidecar_event(raw, binding)
        if raw.get("state") not in {"CANCELLED", "FAILED"}:
            raise HostExecutionError("close_sidecar did not settle the sidecar")
        return raw

    raw = _perform_host_effect(
        repo_root,
        binding.parent,
        state_dir,
        adapter=adapter,
        effect_kind="CLOSE_SIDECAR",
        idempotency_key=key,
        request={
            "sidecar_id": binding.sidecar_id,
            "host_id": binding.host_id,
            "sidecar_task_id": binding.task_id,
            "cursor": binding.cursor,
            "reason": reason,
        },
        operation=close,
    )
    state, result = _terminal_sidecar_result(raw.get("result"), binding, str(raw["state"]))
    _record_sidecar_authorized(
        repo_root, binding.parent, binding.sidecar_id, state,
        adapter=adapter,
        parent_launch_instruction_id=binding.spec["parent_launch_instruction_id"],
        parent_sidecar_id=binding.spec.get("parent_sidecar_id"),
        host_id=binding.host_id, sidecar_task_id=binding.task_id,
        host_event_id=raw["event_id"], host_event_cursor=raw["event_cursor"],
        result=dict(result), close_reason=reason, state_dir=state_dir,
    )
    return result


def _blocker(code: str, message: str, active: Sequence[_Binding], **extra: object) -> dict[str, object]:
    return {
        "kind": BLOCKER_KIND,
        "code": code,
        "message": message,
        "active_launch_instruction_ids": sorted(item.instruction_id for item in active),
        **extra,
    }


def _blocked(
    code: str,
    message: str,
    active: Sequence[_Binding],
    terminal: Mapping[str, str],
    **extra: object,
) -> dict[str, object]:
    required = [item.instruction_id for item in active if item.task.get("required") is True]
    waiting_codes = {"HOST_NO_PROGRESS_LIMIT", "LIVE_EFFECT_CONTENTION"}
    supervisor_state = "WAITING" if code in waiting_codes else "RECOVERY_REQUIRED"
    return {
        "schema_version": 1,
        "kind": RESULT_KIND,
        "outcome": "WAITING" if code in waiting_codes else "BLOCKED",
        "supervisor_state": supervisor_state,
        "successful": False,
        "quiescent": False,
        "required_active": sorted(required),
        "terminal": dict(sorted(terminal.items())),
        "blocker": _blocker(code, message, active, **extra),
    }


def _runtime_authority(
    repo_root: Path,
    contract: Mapping[str, object],
    adapter: HostAdapter,
    trusted_target_branch: str,
) -> tuple[list[object], Mapping[str, object] | None, bool]:
    current = adapter.inspect_runtime_authority(repo_root=repo_root)
    if not isinstance(current, Mapping):
        raise HostExecutionError("runtime authority inspection must return an object")
    claims = current.get("active_claims")
    lease = current.get("active_validation_lease")
    quiescent = current.get("quiescent")
    if current.get("target_branch") != trusted_target_branch:
        raise HostExecutionError("runtime authority inspection changed the trusted target")
    if not isinstance(claims, list):
        raise HostExecutionError("runtime authority active_claims must be a list")
    if lease is not None and not isinstance(lease, Mapping):
        raise HostExecutionError("runtime authority validation lease must be an object or null")
    if type(quiescent) is not bool:
        raise HostExecutionError("runtime authority quiescent flag must be boolean")
    snapshot_claims = contract.get("active_claims", [])
    snapshot_lease = contract.get("active_validation_lease")
    combined_claims = list(snapshot_claims) if isinstance(snapshot_claims, list) else []
    combined_claims.extend(claims)
    return combined_claims, lease if lease is not None else (
        snapshot_lease if isinstance(snapshot_lease, Mapping) else None
    ), quiescent


def execute_contract(
    repo_root: Path,
    contract: Mapping[str, object],
    adapter: HostAdapter,
    resolver: SafeResolver,
    *,
    host: str = "codex",
    max_no_progress_cycles: int = 3,
    max_poll_cycles: int = 100,
    max_replay_events: int = 3,
    state_dir: str | Path | None = None,
    host_runtime_dir: str | Path | None = None,
) -> dict[str, object]:
    """Create or adopt a complete wave, supervise it, and close only on live truth."""

    if min(max_no_progress_cycles, max_poll_cycles, max_replay_events) < 1:
        raise HostExecutionError("host polling bounds must be positive")
    execution_id = _required_text(contract.get("execution_id"), "contract execution_id")
    execution_namespace = _required_text(
        contract.get("execution_namespace"), "contract execution_namespace"
    )
    if state_dir is None:
        raise HostExecutionError("host execution requires an explicit execution directory")
    try:
        state_dir = require_execution_authority_dir(
            repo_root,
            state_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
        )
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
    coordination_dir = Path(state_dir).parents[1]
    try:
        host_runtime = require_host_runtime(host_runtime_dir)
    except ConfigurationError as error:
        raise HostExecutionError(str(error)) from error
    trusted_target_branch = adapter.trusted_singleton_target(repo_root=repo_root)
    tasks = validate_contract(repo_root, contract, trusted_target_branch)
    lifecycle = _authenticated_lifecycle_capability(adapter, repo_root)
    required_lifecycle = ("create", "query", "resume", "interrupt", "archive")
    if lifecycle.get("autonomous_launch") is not True or any(
        lifecycle.get(field) is not True for field in required_lifecycle
    ):
        return {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "outcome": "WAITING",
            "supervisor_state": "WAITING_FOR_HOST",
            "successful": False,
            "quiescent": False,
            "required_active": [],
            "terminal": {},
            "sidecar_terminal": {},
            "blocker": {
                "kind": BLOCKER_KIND,
                "code": "HOST_LIFECYCLE_CAPABILITY_REQUIRED",
                "message": (
                    "the selected host cannot autonomously create, query, resume, "
                    "interrupt, and archive tasks"
                ),
                "active_launch_instruction_ids": [],
                "host_lifecycle_authority": dict(lifecycle),
            },
        }
    with runtime_file_lock(
        host_runtime / "locks" / "host-authority.lock", timeout_seconds=120.0
    ):
        expired_reservations = tuple(
            reservation
            for reservation in active_global_host_reservations(host_runtime)
            if reservation.get("execution_id") == execution_id
            and parse_time(reservation.get("expires_at")) <= utc_now()
        )
    recovery_results: list[Mapping[str, object]] = []
    for reservation in expired_reservations:
        recovery_results.append(
            recover_expired_host_reservation(
                repo_root,
                str(reservation["reservation_id"]),
                execution_dir=state_dir,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                host_runtime_dir=host_runtime,
                adapter=adapter,
                actor="host-execution:expired-reservation-recovery",
                reason="expired host permit requires authenticated lifecycle reconciliation",
            )
        )
    unresolved_recovery = [
        result
        for result in recovery_results
        if result.get("state") in {"WAITING_FOR_HOST", "RECOVERY_REQUIRED"}
    ]
    fenced_recovery = [
        result
        for result in recovery_results
        if result.get("state") == "RECOVERED"
        and isinstance(result.get("local_terminal_event"), Mapping)
        and result["local_terminal_event"].get("state")
        in {"SUPERSEDED", "ORPHANED"}
    ]
    if unresolved_recovery or fenced_recovery:
        waiting = any(
            result.get("state") == "WAITING_FOR_HOST"
            for result in unresolved_recovery
        )
        return {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "outcome": "WAITING" if waiting else "BLOCKED",
            "supervisor_state": (
                "WAITING_FOR_HOST" if waiting else "RECOVERY_REQUIRED"
            ),
            "successful": False,
            "quiescent": False,
            "required_active": [],
            "terminal": {},
            "sidecar_terminal": {},
            "blocker": {
                "kind": BLOCKER_KIND,
                "code": "HOST_RESERVATION_RECONCILIATION_REQUIRED",
                "message": (
                    "expired host capacity remains fenced until host lifecycle and "
                    "local launch authority reach one durable terminal state"
                ),
                "active_launch_instruction_ids": [],
                "recovery_results": [
                    dict(result)
                    for result in unresolved_recovery + fenced_recovery
                ],
            },
        }
    capacity = _authenticated_host_capacity(adapter, repo_root, host_runtime)
    if lifecycle.get("host_id") != capacity.get("host_id"):
        raise HostExecutionError(
            "host lifecycle and capacity authorities identify different hosts"
        )
    if any(task.get("capacity_host_id") != capacity.get("host_id") for task in tasks):
        raise HostExecutionError(
            "signed task cohort identifies a different authenticated host"
        )
    host_limit = int(capacity["max_total_sessions"])
    write_tasks = [
        task for task in tasks if task.get("authority_class") == "WRITE_AUTHORIZED"
    ]
    dispatch_release = contract.get("dispatch_release")
    dispatch_release_id = (
        str(dispatch_release.get("release_id"))
        if isinstance(dispatch_release, Mapping)
        and isinstance(dispatch_release.get("release_id"), str)
        else None
    )
    dispatch_admission_epoch = (
        int(dispatch_release["admission_epoch"])
        if isinstance(dispatch_release, Mapping)
        and type(dispatch_release.get("admission_epoch")) is int
        else None
    )
    if write_tasks and not callable(getattr(adapter, "dispatcher_effect_guard", None)):
        raise HostExecutionError(
            "host adapter cannot fence effects to the shared dispatcher release"
        )
    if (
        getattr(adapter, "supports_preparation_only", True) is not True
        and any(task.get("authority_class") == "PREPARATION_ONLY" for task in tasks)
    ):
        raise HostExecutionError(
            "host cannot observe preparation-only task lifecycle; rebuild the signed "
            "contract without preparation tasks"
        )
    try:
        fence_command = launch_fence_command_prefix(
            repo_root,
            coordination_dir,
            execution_namespace,
            host_runtime,
        )
    except OrchestrationError as error:
        raise HostExecutionError(f"cannot render the durable launch fence: {error}") from error
    sidecar_specs = _sidecar_specs(contract, tasks)
    if sidecar_specs:
        _sidecar_capabilities(adapter)
    latest_primary: dict[str, Mapping[str, object]] = {}
    for event in binding_events(repo_root, state_dir=state_dir):
        instruction_id = event.get("launch_instruction_id")
        if isinstance(instruction_id, str):
            latest_primary[instruction_id] = event
    latest_sidecar = latest_sidecars(repo_root, state_dir=state_dir)
    prospective_reservations = {
        ("primary", str(item["launch_instruction_id"]))
        for item in active_launch_bindings(repo_root, state_dir=state_dir)
    } | {
        ("sidecar", str(item["sidecar_id"]))
        for item in active_sidecars(repo_root, state_dir=state_dir)
    }
    prospective_reservations.update(
        ("primary", str(task["launch_instruction_id"]))
        for task in tasks
        if not (
            latest_primary.get(str(task["launch_instruction_id"]), {}).get("state")
            == "RELEASED"
            and latest_primary.get(str(task["launch_instruction_id"]), {}).get(
                "terminal_state"
            )
            == "SUCCEEDED"
        )
    )
    # Planned sidecars are optional advisory work.  They compete for a slot at
    # their own durable admission boundary and must never make the required
    # primary cohort fail preflight.
    if len(prospective_reservations) > host_limit:
        raise HostExecutionError(
            "execution reservations exceed authenticated host capacity"
        )
    active: dict[str, _Binding] = {}
    terminal: dict[str, str] = {}

    # Every task is created or crash-safely adopted before the first wait.
    for task in tasks:
        instruction_id = str(task["launch_instruction_id"])
        attempt = task.get("attempt")
        if type(attempt) is not int:
            raise HostExecutionError("validated task attempt changed before launch")
        persisted = latest_primary.get(instruction_id)
        if (
            isinstance(persisted, Mapping)
            and persisted.get("state") == "RELEASED"
            and isinstance(persisted.get("terminal_state"), str)
        ):
            terminal[instruction_id] = str(persisted["terminal_state"])
            continue
        now = utc_now()
        with _host_repository_admission_guard(
            host_runtime_dir=host_runtime,
            coordination_dir=coordination_dir,
            execution_dir=Path(state_dir),
            adapter=adapter,
            task=task,
            release_id=dispatch_release_id,
        ):
            try:
                if task.get("authority_class") == "WRITE_AUTHORIZED":
                    raw_permits = (
                        dispatch_release.get("primary_host_reservations", [])
                        if isinstance(dispatch_release, Mapping)
                        else []
                    )
                    permit = next(
                        (
                            item
                            for item in raw_permits
                            if isinstance(item, Mapping)
                            and item.get("node_id") == task.get("node_id")
                            and item.get("resource_key") == task.get("resource_key")
                        ),
                        None,
                    )
                    active_permits = {
                        str(item["reservation_id"]): item
                        for item in active_global_host_reservations(host_runtime)
                    }
                    if (
                        not isinstance(permit, Mapping)
                        or permit.get("reservation_id") not in active_permits
                    ):
                        raise HostExecutionError(
                            "dispatcher primary host reservation is missing or stale"
                        )
                    global_reservation = active_permits[str(permit["reservation_id"])]
                    if any(
                        global_reservation.get(field) != expected
                        for field, expected in {
                            "reservation_kind": "PRIMARY",
                            "repository": task["repository"],
                            "execution_id": execution_id,
                            "host_id": capacity["host_id"],
                            "capacity_generation": capacity["capacity_generation"],
                            "resource_key": task["resource_key"],
                        }.items()
                    ):
                        raise HostExecutionError(
                            "dispatcher primary host reservation fence mismatch"
                        )
                else:
                    global_reservation = reserve_global_host_session(
                        host_runtime,
                        repository=str(task["repository"]),
                        execution_id=execution_id,
                        host_id=str(capacity["host_id"]),
                        capacity_generation=str(capacity["capacity_generation"]),
                        local_reservation_id=instruction_id,
                        reservation_kind="PRIMARY",
                        resource_key=str(task["resource_key"]),
                        write_scopes=(),
                        actor_time=format_time(now),
                        expires_at=str(capacity["expires_at"]),
                        now=now,
                    )
            except ConfigurationError as error:
                raise HostExecutionError(str(error)) from error
            prepared = prepare_launch(
                repo_root,
                instruction_id,
                host,
                execution_id=execution_id,
                execution_namespace=execution_namespace,
                repository=str(task["repository"]),
                node_id=str(task["node_id"]),
                lifecycle=str(task["lifecycle"]),
                branch=str(task["branch"]),
                resource_key=str(task["resource_key"]),
                target_sha=str(task["target_sha"]),
                plan_fingerprint=str(task["plan_fingerprint"]),
                target_branch=str(task["target_branch"]),
                authority_class=str(task["authority_class"]),
                dispatcher_release_id=(
                    dispatch_release_id
                    if task.get("authority_class") == "WRITE_AUTHORIZED"
                    else None
                ),
                dispatcher_admission_epoch=(
                    dispatch_admission_epoch
                    if task.get("authority_class") == "WRITE_AUTHORIZED"
                    else None
                ),
                host_reservation_id=str(global_reservation["reservation_id"]),
                capacity_host_id=str(global_reservation["host_id"]),
                capacity_generation=str(global_reservation["capacity_generation"]),
                capacity_epoch=int(global_reservation["capacity_epoch"]),
                reservation_expires_at=str(global_reservation["expires_at"]),
                attempt=attempt,
                retry_of=str(task["retry_of"]) if task.get("retry_of") is not None else None,
                state_dir=state_dir,
            )
        if prepared.get("state") == "RELEASED" and prepared.get("terminal_state") == "SUCCEEDED":
            terminal[instruction_id] = "SUCCEEDED"
            continue
        looked_up = adapter.lookup_thread(idempotency_key=instruction_id)
        if looked_up is None:
            if prepared.get("state") not in {"PREPARED"}:
                raise HostExecutionError("persisted host binding cannot be recovered by idempotency key")
            authority_epoch = prepared.get("authority_epoch")
            if type(authority_epoch) is not int:
                raise HostExecutionError("prepared launch has no durable authority epoch")
            hosted_coordinates = (
                " --launch-instruction-id "
                + instruction_id
                + " --resource-key "
                + str(task["resource_key"])
                + " --authority-epoch "
                + str(authority_epoch)
            )
            node_id = str(task["node_id"])
            launch_prompt = (
                str(task["prompt"])
                + "\n\nExact durable fence for this host task: `"
                + fence_command
                + " check-launch-authority "
                + instruction_id
                + " --resource-key "
                + str(task["resource_key"])
                + " --authority-epoch "
                + str(authority_epoch)
                + "`. Run it immediately before every effect boundary."
                + "\n\nHosted authority command envelope (dispatcher injected; do not omit or alter "
                + "the launch/resource/epoch arguments):"
                + " Choose one stable CLAIM_OWNER; copy CLAIM_ID and VALIDATION_LEASE_ID "
                + "from the exact JSON responses before later commands."
                + "\n- Claim: `"
                + fence_command
                + " claim "
                + node_id
                + " --owner CLAIM_OWNER"
                + hosted_coordinates
                + " --publish-remote`"
                + "\n- Heartbeat: `"
                + fence_command
                + " heartbeat "
                + node_id
                + " --owner CLAIM_OWNER --claim-id CLAIM_ID"
                + hosted_coordinates
                + "`"
                + "\n- Fail: `"
                + fence_command
                + " fail "
                + node_id
                + " --owner CLAIM_OWNER --claim-id CLAIM_ID"
                + hosted_coordinates
                + " --error \"BOUNDED_ERROR\"`"
                + "\n- Release: `"
                + fence_command
                + " release "
                + node_id
                + " --owner CLAIM_OWNER --claim-id CLAIM_ID"
                + hosted_coordinates
                + " --reason \"BOUNDED_REASON\"`"
                + "\n- Complete: `"
                + fence_command
                + " complete "
                + node_id
                + " --owner CLAIM_OWNER --claim-id CLAIM_ID"
                + hosted_coordinates
                + " --receipt RECEIPT_JSON`"
                + "\n- Validation acquire: `"
                + fence_command
                + " validation-lease-acquire "
                + node_id
                + " --owner CLAIM_OWNER --claim-id CLAIM_ID"
                + hosted_coordinates
                + " --lease-minutes 10`"
                + "\n- Validation renew: `"
                + fence_command
                + " validation-lease-renew "
                + node_id
                + " --owner CLAIM_OWNER --claim-id CLAIM_ID "
                + "--lease-id VALIDATION_LEASE_ID"
                + hosted_coordinates
                + " --lease-minutes 10`"
                + "\n- Validation release: `"
                + fence_command
                + " validation-lease-release "
                + node_id
                + " --owner CLAIM_OWNER --claim-id CLAIM_ID "
                + "--lease-id VALIDATION_LEASE_ID"
                + hosted_coordinates
                + "`"
            )
            try:
                effect_fence = _EffectFence(
                    instruction_id=instruction_id,
                    resource_key=str(task["resource_key"]),
                    authority_epoch=authority_epoch,
                    dispatch_release_id=(
                        dispatch_release_id
                        if task.get("authority_class") == "WRITE_AUTHORIZED"
                        else None
                    ),
                    dispatch_admission_epoch=(
                        dispatch_admission_epoch
                        if task.get("authority_class") == "WRITE_AUTHORIZED"
                        else None
                    ),
                    task=task,
                )

                def create() -> Mapping[str, object]:
                    raw = adapter.create_thread(
                        title=str(task["title"]),
                        prompt=launch_prompt,
                        idempotency_key=instruction_id,
                    )
                    if not isinstance(raw, Mapping):
                        raise HostExecutionError(
                            "host task creation must return an object"
                        )
                    candidate = _validate_creation(
                        raw,
                        instruction_id,
                        resource_key=str(task["resource_key"]),
                        authority_epoch=authority_epoch,
                    )
                    _validate_adoption(candidate, prepared)
                    return raw

                looked_up = _perform_host_effect(
                    repo_root,
                    effect_fence,
                    state_dir,
                    adapter=adapter,
                    effect_kind="CREATE_THREAD",
                    idempotency_key=instruction_id,
                    request={
                        "title": str(task["title"]),
                        "prompt_digest": digest_json({"prompt": launch_prompt}),
                    },
                    operation=create,
                )
            except LiveEffectContention as error:
                return _blocked(
                    "LIVE_EFFECT_CONTENTION",
                    str(error),
                    list(active.values()),
                    terminal,
                    launch_instruction_id=instruction_id,
                    effect_event_id=error.effect.get("event_id"),
                    operation_lease_id=error.effect.get("operation_lease_id"),
                    lease_expires_at=error.effect.get("lease_expires_at"),
                    wake_condition=(
                        "retry only after the exact effect event changes or its "
                        "operation lease expires and authenticated reconciliation completes"
                    ),
                )
            except HostEffectRecoveryRequired as error:
                return _blocked(
                    "HOST_EFFECT_RECOVERY_REQUIRED",
                    str(error),
                    list(active.values()),
                    terminal,
                    launch_instruction_id=instruction_id,
                )
            except (EffectAuthorityRejected, OrchestrationError) as error:
                try:
                    fence_launch(
                        repo_root,
                        instruction_id,
                        actor="host-execution:failed-effect-guard",
                        reason="dispatcher or host creation effect failed before binding",
                        state_dir=state_dir,
                    )
                except OrchestrationError:
                    pass
                raise EffectAuthorityRejected(
                    f"dispatcher or launch authority rejected task creation: {error}"
                ) from error
            except Exception as error:
                # The PREPARED/RECONCILIATION_REQUIRED intent remains the
                # authority. Host I/O failure is not proof that dispatcher or
                # launch authority should be revoked.
                return _blocked(
                    "HOST_EFFECT_RECOVERY_REQUIRED",
                    f"task creation requires external reconciliation: {error}",
                    list(active.values()),
                    terminal,
                    launch_instruction_id=instruction_id,
                )
        if not isinstance(looked_up, Mapping):
            raise HostExecutionError("host task lookup or creation must return an object")
        authority_epoch = prepared.get("authority_epoch")
        if type(authority_epoch) is not int:
            raise HostExecutionError("prepared launch has no durable authority epoch")
        created = _validate_creation(
            looked_up,
            instruction_id,
            resource_key=str(task["resource_key"]),
            authority_epoch=authority_epoch,
        )
        _validate_adoption(created, prepared)
        binding = _Binding(
            instruction_id=instruction_id,
            resource_key=created.resource_key,
            authority_epoch=created.authority_epoch,
            dispatch_release_id=(
                dispatch_release_id
                if task.get("authority_class") == "WRITE_AUTHORIZED"
                else None
            ),
            dispatch_admission_epoch=(
                int(prepared["dispatcher_admission_epoch"])
                if task.get("authority_class") == "WRITE_AUTHORIZED"
                and type(prepared.get("dispatcher_admission_epoch")) is int
                else None
            ),
            host_reservation_id=str(prepared["host_reservation_id"]),
            capacity_host_id=str(prepared["capacity_host_id"]),
            capacity_generation=str(prepared["capacity_generation"]),
            capacity_epoch=int(prepared["capacity_epoch"]),
            reservation_expires_at=str(prepared["reservation_expires_at"]),
            task=task,
            host_id=created.host_id,
            task_id=created.task_id,
            cursor=created.cursor,
            capability=created.capability,
        )
        try:
            with _effect_guard(
                repo_root,
                binding,
                state_dir,
                adapter=adapter,
            ):
                if _live_host_reservation_count(repo_root, state_dir) > host_limit:
                    raise HostExecutionError(
                        "shared repository host reservations exceed canonical capacity"
                    )
                bind_launch(
                    repo_root,
                    instruction_id,
                    host,
                    binding.task_id,
                    host_id=binding.host_id,
                    cursor=binding.cursor,
                    capability=binding.capability,
                    resource_key=binding.resource_key,
                    authority_epoch=binding.authority_epoch,
                    state_dir=state_dir,
                )
        except Exception as error:
            try:
                fence_launch(
                    repo_root,
                    instruction_id,
                    actor="host-execution:failed-effect-guard",
                    reason="dispatcher or host binding effect failed",
                    state_dir=state_dir,
                )
            except OrchestrationError:
                pass
            if isinstance(error, OrchestrationError):
                raise HostExecutionError(
                    f"launch authority was revoked before task binding: {error}"
                ) from error
            raise HostExecutionError(
                f"dispatcher or host task-binding effect failed closed: {error}"
            ) from error
        active[instruction_id] = binding

    primary_bindings = dict(active)
    sidecar_active: dict[str, _SidecarBinding] = {}
    sidecar_terminal: dict[str, str] = {}
    persisted_sidecars = (
        latest_sidecars(repo_root, state_dir=state_dir) if sidecar_specs else {}
    )
    for spec in sidecar_specs:
        sidecar_id = str(spec["sidecar_id"])
        parent_id = str(spec["parent_launch_instruction_id"])
        parent = primary_bindings.get(parent_id)
        if parent is None:
            continue
        _assert_effect_authority(repo_root, parent, state_dir)
        prior = persisted_sidecars.get(sidecar_id)
        if prior is not None and prior.get("state") in TERMINAL_SIDECAR_STATES:
            sidecar_terminal[sidecar_id] = str(prior["state"])
            continue
        looked_up: Mapping[str, object] | None = None
        settled_prior: str | None = None
        try:
            if prior is None:
                admission_now = utc_now()
                with _host_repository_admission_guard(
                    host_runtime_dir=host_runtime,
                    coordination_dir=coordination_dir,
                    adapter=adapter,
                    task=parent.task,
                    release_id=parent.dispatch_release_id,
                ):
                    with launch_authority_guard(
                        repo_root,
                        parent.instruction_id,
                        resource_key=parent.resource_key,
                        authority_epoch=parent.authority_epoch,
                        state_dir=state_dir,
                    ):
                        try:
                            sidecar_reservation = reserve_global_host_session(
                                host_runtime,
                                repository=str(parent.task["repository"]),
                                execution_id=execution_id,
                                host_id=str(capacity["host_id"]),
                                capacity_generation=str(capacity["capacity_generation"]),
                                local_reservation_id=sidecar_id,
                                reservation_kind="SIDECAR",
                                resource_key=sidecar_id,
                                write_scopes=(),
                                actor_time=format_time(admission_now),
                                expires_at=str(capacity["expires_at"]),
                                now=admission_now,
                            )
                        except CapacityAdmissionDenied as error:
                            record_sidecar_state(
                                repo_root,
                                sidecar_id,
                                "SKIPPED_CAPACITY",
                                state_dir=state_dir,
                                parent_launch_instruction_id=parent_id,
                                parent_sidecar_id=spec.get("parent_sidecar_id"),
                                parent_resource_key=parent.resource_key,
                                parent_authority_epoch=parent.authority_epoch,
                                parent_authority_class=parent.task.get("authority_class"),
                                parent_dispatcher_release_id=parent.dispatch_release_id,
                                parent_dispatcher_admission_epoch=parent.dispatch_admission_epoch,
                                spec_digest=sidecar_spec_digest(spec),
                                token_budget_reserved=spec["token_budget"],
                                capacity_host_id=capacity["host_id"],
                                capacity_generation=capacity["capacity_generation"],
                                capacity_epoch=capacity["capacity_epoch"],
                                reservation_expires_at=capacity["expires_at"],
                                admission_code="ADMISSION_DENIED",
                                reason=str(error),
                            )
                            sidecar_terminal[sidecar_id] = "SKIPPED_CAPACITY"
                            continue
                        _record_sidecar_authorized(
                            repo_root, parent, sidecar_id, "PREPARED",
                            adapter=adapter,
                            parent_launch_instruction_id=parent_id,
                            parent_sidecar_id=spec.get("parent_sidecar_id"),
                            spec_digest=sidecar_spec_digest(spec),
                            token_budget_reserved=spec["token_budget"],
                            host_reservation_id=sidecar_reservation["reservation_id"],
                            capacity_host_id=sidecar_reservation["host_id"],
                            capacity_generation=sidecar_reservation["capacity_generation"],
                            capacity_epoch=sidecar_reservation["capacity_epoch"],
                            reservation_expires_at=sidecar_reservation["expires_at"],
                            state_dir=state_dir,
                        )
            prior = latest_sidecars(repo_root, state_dir=state_dir).get(sidecar_id)
            if prior is not None and prior.get("state") in TERMINAL_SIDECAR_STATES:
                settled_prior = str(prior["state"])
            else:
                def spawn() -> Mapping[str, object]:
                    raw = adapter.lookup_sidecar(idempotency_key=sidecar_id)
                    if raw is None:
                        raw = adapter.spawn_sidecar(
                            prompt=str(spec["prompt"]),
                            token_budget=int(spec["token_budget"]),
                            idempotency_key=sidecar_id,
                            parent_launch_instruction_id=parent_id,
                        )
                    if not isinstance(raw, Mapping):
                        raise HostExecutionError(
                            "sidecar lookup or spawn returned no recoverable binding"
                        )
                    _validate_sidecar_creation(raw, spec, parent)
                    return raw

                looked_up = _perform_host_effect(
                    repo_root,
                    parent,
                    state_dir,
                    adapter=adapter,
                    effect_kind="SPAWN_SIDECAR",
                    idempotency_key=sidecar_id,
                    request={
                        "sidecar_id": sidecar_id,
                        "parent_launch_instruction_id": parent_id,
                        "prompt_digest": digest_json({"prompt": str(spec["prompt"])}),
                        "token_budget": int(spec["token_budget"]),
                    },
                    operation=spawn,
                )
        except Exception as error:
            durable_prior = latest_sidecars(repo_root, state_dir=state_dir).get(sidecar_id)
            if durable_prior is None:
                raise HostExecutionError(
                    "sidecar admission failed before a durable PREPARED transition; "
                    "global reservation reconciliation is required"
                ) from error
            _record_sidecar_authorized(
                repo_root, parent, sidecar_id, "SPAWN_FAILED",
                adapter=adapter,
                parent_launch_instruction_id=parent_id,
                parent_sidecar_id=spec.get("parent_sidecar_id"),
                spec_digest=sidecar_spec_digest(spec), error=type(error).__name__,
                state_dir=state_dir,
            )
            sidecar_terminal[sidecar_id] = "SPAWN_FAILED"
            if parent is not None:
                _notify_primary(
                    repo_root, adapter, parent,
                    f"Sidecar {sidecar_id} could not start ({type(error).__name__}); continue without its advisory evidence.",
                    {"sidecar_id": sidecar_id, "state": "SPAWN_FAILED"},
                    state_dir=state_dir,
                )
            continue
        if settled_prior is not None:
            sidecar_terminal[sidecar_id] = settled_prior
            continue
        if not isinstance(looked_up, Mapping):
            return _blocked(
                "SIDECAR_BINDING_INVALID",
                "sidecar lookup or spawn returned no recoverable binding",
                tuple(active.values()), terminal, sidecar_id=sidecar_id,
            )
        binding = _validate_sidecar_creation(looked_up, spec, parent)
        if prior is not None:
            for field, actual in {"host_id": binding.host_id, "sidecar_task_id": binding.task_id}.items():
                if prior.get(field) is not None and prior.get(field) != actual:
                    raise HostExecutionError(f"looked-up sidecar conflicts with persisted {field}")
        _record_sidecar_authorized(
            repo_root, parent, sidecar_id, "BOUND",
            adapter=adapter,
            parent_launch_instruction_id=parent_id,
            parent_sidecar_id=spec.get("parent_sidecar_id"),
            spec_digest=sidecar_spec_digest(spec), host_id=binding.host_id,
            sidecar_task_id=binding.task_id, cursor=binding.cursor,
            capability_digest="sha256:" + sha256(binding.capability.encode()).hexdigest(),
            token_budget_reserved=spec["token_budget"],
            state_dir=state_dir,
        )
        sidecar_active[sidecar_id] = binding
        if parent is not None:
            message_id = _notify_primary(
                repo_root, adapter, parent,
                f"Advisory read-only sidecar {sidecar_id} ({spec['purpose']}) is active. Do not finish until its root-delivered terminal packet arrives.",
                {"sidecar_id": sidecar_id, "state": "BOUND"},
                state_dir=state_dir,
            )
            _record_sidecar_authorized(
                repo_root, parent, sidecar_id, "ACTIVE",
                adapter=adapter,
                parent_launch_instruction_id=parent_id,
                parent_sidecar_id=spec.get("parent_sidecar_id"),
                host_id=binding.host_id, sidecar_task_id=binding.task_id,
                parent_spawn_message_id=message_id,
                state_dir=state_dir,
            )

    event_cursors: dict[str, str] = {}
    seen_event_ids: dict[str, tuple[str, str]] = {}
    for event in binding_events(repo_root, state_dir=state_dir):
        instruction_id = event.get("launch_instruction_id")
        event_id = event.get("host_event_id")
        event_cursor = event.get("host_event_cursor")
        if instruction_id in active and isinstance(event_id, str) and isinstance(event_cursor, str):
            event_cursors[str(instruction_id)] = event_cursor
            seen_event_ids[event_id] = (str(instruction_id), event_cursor)

    no_progress = 0
    poll_cycles = 0
    replay_events = 0
    sidecar_cursors: dict[str, str] = {}
    sidecar_seen_events: dict[str, tuple[str, str]] = {}
    sidecar_replays = 0
    sidecar_no_progress = 0
    sidecar_polls = 0
    sidecar_policy = contract.get("sidecar_cohort", {}).get("policy", {}) if isinstance(contract.get("sidecar_cohort"), Mapping) else {}
    cohort_parent_ids = set(primary_bindings)
    issued_sidecar_ids = {
        str(spec["sidecar_id"]) for spec in sidecar_specs
    } | {
        sidecar_id
        for sidecar_id, event in persisted_sidecars.items()
        if event.get("parent_launch_instruction_id") in cohort_parent_ids
    }
    sidecar_count = len(issued_sidecar_ids)
    sidecar_budget_reserved = sum(int(spec["token_budget"]) for spec in sidecar_specs)
    wait_rotation = 0
    while active or sidecar_active:
        for binding in active.values():
            _assert_effect_authority(repo_root, binding, state_dir)
        for sidecar in sidecar_active.values():
            parent = primary_bindings.get(
                str(sidecar.spec["parent_launch_instruction_id"])
            )
            if parent is None:
                raise HostExecutionError("active sidecar has no durable primary authority")
            _assert_effect_authority(repo_root, parent, state_dir)
        _renew_execution_host_reservations(
            host_runtime_dir=host_runtime,
            execution_id=execution_id,
            capacity=capacity,
        )
        poll_cycles += 1
        closure_target = contract.get("closure_target")
        waiting = tuple(
            sorted(
                active.values(),
                key=lambda item: (
                    0 if item.task.get("task_key") == closure_target else 1,
                    item.instruction_id,
                ),
            )
        )
        if sidecar_active:
            sidecar_polls += 1
            combined: list[tuple[str, object]] = [
                ("primary", item) for item in waiting
            ] + [("sidecar", sidecar_active[key]) for key in sorted(sidecar_active)]
            limit = int(sidecar_policy["max_targets_per_wait"])
            start = wait_rotation % len(combined)
            selected = [combined[(start + offset) % len(combined)] for offset in range(min(limit, len(combined)))]
            wait_rotation = (start + len(selected)) % len(combined)
            selected_primary = [item for kind, item in selected if kind == "primary"]
            selected_sidecars = [item for kind, item in selected if kind == "sidecar"]
            try:
                activity = _bounded_wait(
                    adapter,
                    [item.wait_target(event_cursors.get(item.instruction_id)) for item in selected_primary],
                    [item.wait_target(sidecar_cursors.get(item.sidecar_id)) for item in selected_sidecars],
                    int(sidecar_policy["wait_timeout_seconds"]),
                )
            except TimeoutError:
                for key, sidecar in tuple(sidecar_active.items()):
                    result = _close_sidecar(
                        repo_root,
                        adapter,
                        sidecar,
                        "wall-clock wait timeout",
                        state_dir=state_dir,
                    )
                    parent = primary_bindings.get(str(sidecar.spec["parent_launch_instruction_id"]))
                    if parent is not None and parent.instruction_id in active:
                        _notify_primary(repo_root, adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": key, "state": "CANCELLED"}, state_dir=state_dir)
                    sidecar_terminal[key] = "CANCELLED"
                    del sidecar_active[key]
                return _blocked(
                    "SIDECAR_WAIT_TIMEOUT", "combined host wait exceeded its wall-clock deadline; all sidecars were settled",
                    tuple(active.values()), terminal, sidecar_terminal=dict(sorted(sidecar_terminal.items())),
                )
            events_raw = activity["primary_events"]
            sidecar_events_raw = activity["sidecar_events"]
        else:
            # Durable hosts such as Codex cap one wait at eight targets. Rotate stable
            # windows so a ninth task cannot starve or force an invalid host call.
            limit = 8
            if isinstance(contract.get("sidecar_cohort"), Mapping):
                limit = int(sidecar_policy.get("max_targets_per_wait", 8))
            selected_waiting = waiting
            if len(waiting) > limit:
                start = wait_rotation % len(waiting)
                selected_waiting = tuple(waiting[(start + offset) % len(waiting)] for offset in range(limit))
                wait_rotation = (start + limit) % len(waiting)
            events_raw = adapter.wait_threads(
                [item.wait_target(event_cursors.get(item.instruction_id)) for item in selected_waiting]
            )
            sidecar_events_raw = []
        if not isinstance(events_raw, Sequence) or isinstance(events_raw, (str, bytes)):
            raise HostExecutionError("wait_threads result must be a sequence of events")
        if not isinstance(sidecar_events_raw, Sequence) or isinstance(sidecar_events_raw, (str, bytes)):
            raise HostExecutionError("sidecar_events must be a sequence")
        progressed = False
        sidecar_progressed = False
        sidecar_seen_batch: set[str] = set()
        for raw in sidecar_events_raw:
            if not isinstance(raw, Mapping):
                raise HostExecutionError("host sidecar event must be an object")
            matches = [item for item in sidecar_active.values() if item.task_id == raw.get("sidecar_task_id")]
            if not matches:
                # Unbound host noise cannot be granted authority. Known sidecars remain
                # supervised and their liveness bounds will settle them if necessary.
                continue
            if len(matches) != 1:
                raise HostExecutionError("host sidecar event references an ambiguous task")
            sidecar = matches[0]
            try:
                _validate_sidecar_event(raw, sidecar)
            except HostExecutionError as error:
                result = _close_sidecar(
                    repo_root,
                    adapter,
                    sidecar,
                    f"invalid host event: {error}",
                    state_dir=state_dir,
                )
                parent_id = str(sidecar.spec["parent_launch_instruction_id"])
                parent = primary_bindings.get(parent_id)
                if parent is not None and parent_id in active:
                    _notify_primary(repo_root, adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": sidecar.sidecar_id, "state": "FAILED"}, state_dir=state_dir)
                sidecar_terminal[sidecar.sidecar_id] = "FAILED"
                del sidecar_active[sidecar.sidecar_id]
                sidecar_progressed = True
                continue
            event_id = str(raw["event_id"])
            event_cursor = str(raw["event_cursor"])
            if event_id in sidecar_seen_batch:
                raise HostExecutionError("wait_activity returned a duplicate sidecar event_id")
            sidecar_seen_batch.add(event_id)
            prior_event = sidecar_seen_events.get(event_id)
            if prior_event is not None:
                if prior_event != (sidecar.sidecar_id, event_cursor):
                    raise HostExecutionError("sidecar replay changed cursor or identity")
                sidecar_replays += 1
                continue
            if event_cursor == sidecar_cursors.get(sidecar.sidecar_id):
                raise HostExecutionError("new sidecar evidence reused an event cursor")
            state = str(raw["state"])
            parent_id = str(sidecar.spec["parent_launch_instruction_id"])
            parent = primary_bindings.get(parent_id)
            if state == "NEEDS_ATTENTION":
                answer = resolver.resolve_attention(sidecar.spec, raw)
                if not isinstance(answer, str) or not answer.strip():
                    raise HostExecutionError("safe resolver must answer sidecar attention")
                message_id = _notify_sidecar(repo_root, adapter, sidecar, answer, {"host_event_id": event_id}, state_dir=state_dir)
                _record_sidecar_authorized(repo_root, sidecar.parent, sidecar.sidecar_id, "ATTENTION_ACKNOWLEDGED", adapter=adapter, parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_event_id=event_id, host_event_cursor=event_cursor, message_id=message_id, state_dir=state_dir)
            elif state == "SPAWN_REQUEST":
                decision = "DENIED"
                denial = "request failed root admission"
                try:
                    request = raw.get("request")
                    if not isinstance(request, Mapping):
                        raise HostExecutionError("descendant spawn request must be an object")
                    descendant_spec = make_descendant_spec(sidecar.spec, request, sidecar_policy)
                    descendant_id = str(descendant_spec["sidecar_id"])
                    descendant_budget = int(descendant_spec["token_budget"])
                    if sidecar_budget_reserved + descendant_budget > int(sidecar_policy["total_token_budget"]):
                        raise HostExecutionError("sidecar token budget exhausted")
                    admission_denial = ""
                    created_raw: Mapping[str, object] | None = None
                    fresh_issued_ids: set[str] = set()
                    with _effect_guard(
                        repo_root,
                        sidecar.parent,
                        state_dir,
                        adapter=adapter,
                    ):
                        fresh_persisted = latest_sidecars(repo_root, state_dir=state_dir)
                        fresh_issued_ids = {
                            str(spec["sidecar_id"]) for spec in sidecar_specs
                        } | {
                            known_id
                            for known_id, event in fresh_persisted.items()
                            if event.get("parent_launch_instruction_id")
                            in cohort_parent_ids
                        }
                        if len(fresh_issued_ids) >= int(
                            sidecar_policy["max_total_sidecars"]
                        ):
                            admission_denial = "sidecar count budget exhausted"
                        elif (
                            _live_host_reservation_count(repo_root, state_dir)
                            >= host_limit
                        ):
                            admission_denial = (
                                "canonical attended host capacity exhausted"
                            )
                        elif (
                            descendant_id in fresh_issued_ids
                            or descendant_id in sidecar_active
                            or descendant_id in sidecar_terminal
                        ):
                            admission_denial = "duplicate descendant is already known"
                    if not admission_denial:
                        admission_now = utc_now()
                        with _host_repository_admission_guard(
                            host_runtime_dir=host_runtime,
                            coordination_dir=coordination_dir,
                            execution_dir=Path(state_dir),
                            adapter=adapter,
                            task=sidecar.parent.task,
                            release_id=sidecar.parent.dispatch_release_id,
                        ):
                            with launch_authority_guard(
                                repo_root,
                                sidecar.parent.instruction_id,
                                resource_key=sidecar.parent.resource_key,
                                authority_epoch=sidecar.parent.authority_epoch,
                                state_dir=state_dir,
                            ):
                                descendant_reservation = reserve_global_host_session(
                                    host_runtime,
                                    repository=str(sidecar.parent.task["repository"]),
                                    execution_id=execution_id,
                                    host_id=str(capacity["host_id"]),
                                    capacity_generation=str(capacity["capacity_generation"]),
                                    local_reservation_id=descendant_id,
                                    reservation_kind="SIDECAR",
                                    resource_key=descendant_id,
                                    write_scopes=(),
                                    actor_time=format_time(admission_now),
                                    expires_at=str(capacity["expires_at"]),
                                    now=admission_now,
                                )
                                _record_sidecar_authorized(
                                    repo_root,
                                    sidecar.parent,
                                    descendant_id,
                                    "PREPARED",
                                    adapter=adapter,
                                    parent_launch_instruction_id=parent_id,
                                    parent_sidecar_id=sidecar.sidecar_id,
                                    spec_digest=sidecar_spec_digest(descendant_spec),
                                    token_budget_reserved=descendant_budget,
                                    host_reservation_id=descendant_reservation["reservation_id"],
                                    capacity_host_id=descendant_reservation["host_id"],
                                    capacity_generation=descendant_reservation["capacity_generation"],
                                    capacity_epoch=descendant_reservation["capacity_epoch"],
                                    reservation_expires_at=descendant_reservation["expires_at"],
                                    state_dir=state_dir,
                                )
                        def spawn_descendant() -> Mapping[str, object]:
                            raw = adapter.lookup_sidecar(
                                idempotency_key=descendant_id
                            )
                            if raw is None:
                                raw = adapter.spawn_sidecar(
                                    prompt=str(descendant_spec["prompt"]),
                                    token_budget=descendant_budget,
                                    idempotency_key=descendant_id,
                                    parent_launch_instruction_id=parent_id,
                                )
                            if not isinstance(raw, Mapping):
                                raise HostExecutionError(
                                    "descendant spawn returned no binding"
                                )
                            _validate_sidecar_creation(
                                raw, descendant_spec, sidecar.parent
                            )
                            return raw

                        created_raw = _perform_host_effect(
                            repo_root,
                            sidecar.parent,
                            state_dir,
                            adapter=adapter,
                            effect_kind="SPAWN_SIDECAR",
                            idempotency_key=descendant_id,
                            request={
                                "sidecar_id": descendant_id,
                                "parent_launch_instruction_id": parent_id,
                                "parent_sidecar_id": sidecar.sidecar_id,
                                "prompt_digest": digest_json(
                                    {"prompt": str(descendant_spec["prompt"])}
                                ),
                                "token_budget": descendant_budget,
                            },
                            operation=spawn_descendant,
                        )
                    if admission_denial:
                        raise HostExecutionError(admission_denial)
                    if not isinstance(created_raw, Mapping):
                        raise HostExecutionError("descendant spawn returned no binding")
                    descendant = _validate_sidecar_creation(created_raw, descendant_spec, sidecar.parent)
                    _record_sidecar_authorized(repo_root, sidecar.parent, descendant_id, "BOUND", adapter=adapter, parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.sidecar_id, spec_digest=sidecar_spec_digest(descendant_spec), host_id=descendant.host_id, sidecar_task_id=descendant.task_id, cursor=descendant.cursor, capability_digest="sha256:" + sha256(descendant.capability.encode()).hexdigest(), token_budget_reserved=descendant_budget, state_dir=state_dir)
                    sidecar_active[descendant_id] = descendant
                    issued_sidecar_ids = fresh_issued_ids | {descendant_id}
                    sidecar_count = len(issued_sidecar_ids)
                    sidecar_budget_reserved += descendant_budget
                    decision = "ADMITTED"
                    denial = ""
                    if parent is not None and parent_id in active:
                        _notify_primary(repo_root, adapter, parent, f"Root admitted descendant sidecar {descendant_id} under {sidecar.sidecar_id}; wait for its terminal packet.", {"sidecar_id": descendant_id, "parent_sidecar_id": sidecar.sidecar_id, "state": "BOUND"}, state_dir=state_dir)
                except Exception as error:
                    denial = str(error)
                response = f"{decision}: {denial}" if denial else f"{decision}: descendant {descendant_id} is root-managed and budget-reserved."
                _notify_sidecar(repo_root, adapter, sidecar, response, {"host_event_id": event_id, "decision": decision}, state_dir=state_dir)
                _record_sidecar_authorized(repo_root, sidecar.parent, sidecar.sidecar_id, "ACTIVE", adapter=adapter, parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_event_id=event_id, host_event_cursor=event_cursor, descendant_request=decision, state_dir=state_dir)
            elif state == "ACTIVE":
                _record_sidecar_authorized(repo_root, sidecar.parent, sidecar.sidecar_id, "ACTIVE", adapter=adapter, parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_event_id=event_id, host_event_cursor=event_cursor, state_dir=state_dir)
            else:
                descendants = [
                    child for child in sidecar_active.values()
                    if child.spec.get("parent_sidecar_id") == sidecar.sidecar_id
                ]
                for child in descendants:
                    child_result = _close_sidecar(
                        repo_root, adapter, child,
                        "sidecar parent attempted terminal transition before descendant settlement",
                        state_dir=state_dir,
                    )
                    _notify_sidecar(repo_root, adapter, sidecar, json.dumps(dict(child_result), sort_keys=True), {"sidecar_id": child.sidecar_id, "state": "CANCELLED"}, state_dir=state_dir)
                    if parent is not None and parent_id in active:
                        _notify_primary(repo_root, adapter, parent, json.dumps(dict(child_result), sort_keys=True), {"sidecar_id": child.sidecar_id, "state": "CANCELLED"}, state_dir=state_dir)
                    sidecar_terminal[child.sidecar_id] = "CANCELLED"
                    del sidecar_active[child.sidecar_id]
                state, result = _terminal_sidecar_result(raw.get("result"), sidecar, state)
                message_id = None
                immediate_parent_id = sidecar.spec.get("parent_sidecar_id")
                immediate_parent = sidecar_active.get(str(immediate_parent_id)) if immediate_parent_id else None
                if immediate_parent is not None:
                    _notify_sidecar(repo_root, adapter, immediate_parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": sidecar.sidecar_id, "state": state}, state_dir=state_dir)
                if parent is not None and parent_id in active:
                    message_id = _notify_primary(repo_root, adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": sidecar.sidecar_id, "state": state}, state_dir=state_dir)
                # The terminal record plus an acknowledged parent message is the settlement barrier.
                _record_sidecar_authorized(repo_root, sidecar.parent, sidecar.sidecar_id, state, adapter=adapter, parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_id=sidecar.host_id, sidecar_task_id=sidecar.task_id, host_event_id=event_id, host_event_cursor=event_cursor, result=dict(result), parent_terminal_message_id=message_id, state_dir=state_dir)
                sidecar_terminal[sidecar.sidecar_id] = state
                del sidecar_active[sidecar.sidecar_id]
            sidecar_cursors[sidecar.sidecar_id] = event_cursor
            sidecar_seen_events[event_id] = (sidecar.sidecar_id, event_cursor)
            sidecar_progressed = True
        _release_terminal_sidecar_capacity(
            repo_root=repo_root,
            state_dir=state_dir,
            host_runtime_dir=host_runtime,
            coordination_dir=coordination_dir,
            execution_id=execution_id,
            execution_namespace=execution_namespace,
        )
        seen_in_batch: set[str] = set()
        for raw in events_raw:
            if not isinstance(raw, Mapping):
                raise HostExecutionError("host event must be an object")
            matches = [item for item in active.values() if item.task_id == raw.get("task_id")]
            if len(matches) != 1:
                raise HostExecutionError("host event references an unknown or ambiguous task_id")
            binding = matches[0]
            _validate_event(raw, binding)
            event_id = str(raw["event_id"])
            event_cursor = str(raw["event_cursor"])
            if event_id in seen_in_batch:
                raise HostExecutionError("wait_threads returned a duplicate event_id")
            seen_in_batch.add(event_id)
            prior = seen_event_ids.get(event_id)
            if prior is not None:
                if prior != (binding.instruction_id, event_cursor):
                    raise HostExecutionError("host replay changed an event cursor or task identity")
                replay_events += 1
                continue
            if event_cursor == event_cursors.get(binding.instruction_id):
                raise HostExecutionError("host replay reused an event cursor for new evidence")
            state = str(raw["state"])
            if state == "NEEDS_ATTENTION":
                answer = resolver.resolve_attention(binding.task, raw)
                if not isinstance(answer, str) or not answer.strip():
                    raise HostExecutionError("safe resolver must return a non-empty answer")
                message_key = "sha256:" + sha256(
                    _canonical(
                        {
                            "instruction_id": binding.instruction_id,
                            "host_event_id": event_id,
                            "answer": answer,
                        }
                    )
                ).hexdigest()
                def send_attention_answer() -> Mapping[str, object]:
                    ack_raw = adapter.send_message_to_thread(
                        host_id=binding.host_id,
                        task_id=binding.task_id,
                        cursor=binding.cursor,
                        capability=binding.capability,
                        message=answer,
                        idempotency_key=message_key,
                    )
                    if not isinstance(ack_raw, Mapping):
                        raise HostExecutionError("send_message_to_thread result must be an object")
                    _validate_ack(ack_raw, binding, message_key)
                    return ack_raw

                ack_raw = _perform_host_effect(
                    repo_root,
                    binding,
                    state_dir,
                    adapter=adapter,
                    effect_kind="SEND_PRIMARY_MESSAGE",
                    idempotency_key=message_key,
                    request={
                        "host_id": binding.host_id,
                        "task_id": binding.task_id,
                        "cursor": binding.cursor,
                        "host_event_id": event_id,
                        "message_digest": digest_json({"message": answer}),
                    },
                    operation=send_attention_answer,
                )
                _assert_effect_authority(repo_root, binding, state_dir)
                record_host_progress(
                    repo_root,
                    binding.instruction_id,
                    host=host,
                    host_id=binding.host_id,
                    task_id=binding.task_id,
                    cursor=binding.cursor,
                    capability=binding.capability,
                    host_state=state,
                    host_event_id=event_id,
                    host_event_cursor=event_cursor,
                    resource_key=binding.resource_key,
                    authority_epoch=binding.authority_epoch,
                    message_id=str(ack_raw["message_id"]),
                    state_dir=state_dir,
                )
            elif state == "ACTIVE":
                _assert_effect_authority(repo_root, binding, state_dir)
                record_host_progress(
                    repo_root,
                    binding.instruction_id,
                    host=host,
                    host_id=binding.host_id,
                    task_id=binding.task_id,
                    cursor=binding.cursor,
                    capability=binding.capability,
                    host_state=state,
                    host_event_id=event_id,
                    host_event_cursor=event_cursor,
                    resource_key=binding.resource_key,
                    authority_epoch=binding.authority_epoch,
                    state_dir=state_dir,
                )
            else:
                descendants = [
                    child for child in sidecar_active.values()
                    if child.spec.get("parent_launch_instruction_id") == binding.instruction_id
                ]
                for child in descendants:
                    result = _close_sidecar(
                        repo_root, adapter, child,
                        "primary attempted terminal transition before sidecar settlement",
                        state_dir=state_dir,
                    )
                    _notify_primary(
                        repo_root, adapter, binding, json.dumps(dict(result), sort_keys=True),
                        {"sidecar_id": child.sidecar_id, "state": "CANCELLED"},
                        state_dir=state_dir,
                    )
                    sidecar_terminal[child.sidecar_id] = "CANCELLED"
                    del sidecar_active[child.sidecar_id]
                with _effect_guard(repo_root, binding, state_dir, adapter=adapter):
                    terminal_launch_event = release_terminal_launch(
                        repo_root,
                        binding.instruction_id,
                        host=host,
                        host_id=binding.host_id,
                        task_id=binding.task_id,
                        cursor=binding.cursor,
                        capability=binding.capability,
                        terminal_state=state,
                        host_event_id=event_id,
                        host_event_cursor=event_cursor,
                        resource_key=binding.resource_key,
                        authority_epoch=binding.authority_epoch,
                        state_dir=state_dir,
                    )
                _release_primary_capacity(
                    repo_root=repo_root,
                    host_runtime_dir=host_runtime,
                    coordination_dir=coordination_dir,
                    execution_dir=Path(state_dir),
                    execution_id=execution_id,
                    execution_namespace=execution_namespace,
                    binding=binding,
                    actor="host-execution:terminal-observation",
                    reason=f"durable primary terminal state {state}",
                    local_terminal_event=terminal_launch_event,
                )
                terminal[binding.instruction_id] = state
                del active[binding.instruction_id]
            event_cursors[binding.instruction_id] = event_cursor
            seen_event_ids[event_id] = (binding.instruction_id, event_cursor)
            progressed = True

        primary_progressed = progressed
        # A sidecar cannot manufacture primary progress. While sidecars are still in
        # their bounded collection phase, defer the primary no-progress counter; the
        # independent total poll bound still prevents starvation.
        if primary_progressed:
            no_progress = 0
        elif not sidecar_active and not sidecar_progressed:
            no_progress += 1
        sidecar_no_progress = 0 if sidecar_progressed or not sidecar_active else sidecar_no_progress + 1
        sidecar_bound_hit = sidecar_active and (
            sidecar_replays >= int(sidecar_policy["max_replay_events"])
            or sidecar_polls >= int(sidecar_policy["max_poll_cycles"])
            or sidecar_no_progress >= int(sidecar_policy["max_no_progress_cycles"])
        )
        if sidecar_bound_hit:
            disposition = (
                "SIDECAR_REPLAY_LIMIT" if sidecar_replays >= int(sidecar_policy["max_replay_events"])
                else "SIDECAR_TOTAL_POLL_LIMIT" if sidecar_polls >= int(sidecar_policy["max_poll_cycles"])
                else "SIDECAR_NO_PROGRESS_LIMIT"
            )
            for key, child in tuple(sidecar_active.items()):
                result = _close_sidecar(
                    repo_root, adapter, child, disposition, state_dir=state_dir
                )
                parent = primary_bindings.get(str(child.spec["parent_launch_instruction_id"]))
                if parent is not None and parent.instruction_id in active:
                    _notify_primary(repo_root, adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": key, "state": "CANCELLED"}, state_dir=state_dir)
                sidecar_terminal[key] = "CANCELLED"
                del sidecar_active[key]
            # Sidecars are advisory and settled; primaries continue instead of hanging.
        if active and replay_events >= max_replay_events:
            return _blocked(
                "HOST_REPLAY_LIMIT",
                "host repeatedly replayed already persisted events",
                tuple(active.values()),
                terminal,
                replay_events=replay_events,
            )
        if active and poll_cycles >= max_poll_cycles:
            return _blocked(
                "HOST_TOTAL_POLL_LIMIT",
                "host tasks did not terminate before the total polling bound",
                tuple(active.values()),
                terminal,
                max_poll_cycles=max_poll_cycles,
            )
        if active and no_progress >= max_no_progress_cycles:
            return _blocked(
                "HOST_NO_PROGRESS_LIMIT",
                "host tasks made no progress before the bounded polling limit",
                tuple(active.values()),
                terminal,
                max_no_progress_cycles=max_no_progress_cycles,
            )

    _release_terminal_sidecar_capacity(
        repo_root=repo_root,
        state_dir=state_dir,
        host_runtime_dir=host_runtime,
        coordination_dir=coordination_dir,
        execution_id=execution_id,
        execution_namespace=execution_namespace,
    )
    failed_required = sorted(
        str(task["launch_instruction_id"])
        for task in tasks
        if task.get("required") is True
        and terminal.get(str(task["launch_instruction_id"])) != "SUCCEEDED"
    )
    claims, lease, controller_quiescent = _runtime_authority(
        repo_root, contract, adapter, trusted_target_branch
    )
    live_bindings = active_launch_bindings(repo_root, state_dir=state_dir)
    # Repository/execution quiescence is global to the execution namespace, not
    # conditional on whether this particular contract planned sidecars.
    live_sidecars = active_sidecars(repo_root, state_dir=state_dir)
    with runtime_file_lock(
        host_runtime / "locks" / "host-authority.lock", timeout_seconds=120.0
    ):
        try:
            live_global_reservations = tuple(
                item
                for item in active_global_host_reservations(host_runtime)
                if item.get("execution_id") == execution_id
            )
        except ConfigurationError as error:
            raise HostExecutionError(str(error)) from error
    if (
        claims
        or lease is not None
        or live_bindings
        or live_sidecars
        or live_global_reservations
        or not controller_quiescent
    ):
        return {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "outcome": "BLOCKED" if failed_required else "ACTIVE",
            "supervisor_state": (
                "RECOVERY_REQUIRED" if failed_required else "WAITING"
            ),
            "successful": False,
            "quiescent": False,
            "required_active": [],
            "terminal": dict(sorted(terminal.items())),
            "blocker": _blocker(
                "RUNTIME_AUTHORITY_ACTIVE",
                "repository claims, leases, bindings, or controller state are not quiescent",
                (),
                active_claims=claims,
                active_validation_lease=dict(lease) if lease is not None else None,
                active_host_bindings=[dict(item) for item in live_bindings],
                active_sidecar_bindings=[dict(item) for item in live_sidecars],
                active_global_host_reservations=[
                    dict(item) for item in live_global_reservations
                ],
                controller_quiescent=controller_quiescent,
            ),
        }
    blocker = None
    if failed_required:
        blocker = _blocker(
            "REQUIRED_TASK_TERMINAL_FAILURE",
            "one or more required host tasks ended without success",
            (),
            failed_launch_instruction_ids=failed_required,
        )
    return {
        "schema_version": 1,
        "kind": RESULT_KIND,
        "outcome": "SUCCESS" if not failed_required else "BLOCKED",
        "supervisor_state": "PLAN_QUIESCENT",
        "successful": not failed_required,
        "quiescent": True,
        "required_active": [],
        "terminal": dict(sorted(terminal.items())),
        "sidecar_terminal": dict(sorted(sidecar_terminal.items())),
        "blocker": blocker,
    }
