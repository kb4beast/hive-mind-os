"""Capability-bound, crash-safe host execution for Autopilot contracts."""

from __future__ import annotations

import json
import queue
import re
import threading
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from orchestration import (
    active_launch_bindings,
    bind_launch,
    binding_events,
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
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
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


class HostAdapter(Protocol):
    """Durable task host used by :func:`execute_contract`.

    ``lookup_thread`` and idempotent messages make adoption safe after a parent
    crash between an external side effect and its local ledger append.
    """

    def lookup_thread(self, *, idempotency_key: str) -> Mapping[str, object] | None: ...

    def trusted_singleton_target(self, *, repo_root: Path) -> str: ...

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
class _SidecarBinding:
    sidecar_id: str
    spec: Mapping[str, object]
    host_id: str
    task_id: str
    cursor: str
    capability: str

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
    claims = contract.get("active_claims", [])
    lease = contract.get("active_validation_lease")
    if not isinstance(claims, list):
        raise HostExecutionError("contract active_claims must be a list")
    if lease is not None and not isinstance(lease, Mapping):
        raise HostExecutionError("contract active_validation_lease must be an object or null")
    tasks: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_tasks):
        if not isinstance(raw, Mapping):
            raise HostExecutionError(f"task {index} must be an object")
        instruction_id = _required_text(raw.get("launch_instruction_id"), "launch_instruction_id")
        if not _DIGEST.fullmatch(instruction_id):
            raise HostExecutionError("launch_instruction_id must be a SHA-256 digest")
        if raw.get("idempotency_key") != instruction_id:
            raise HostExecutionError("task idempotency_key must equal launch_instruction_id")
        if instruction_id in seen:
            raise HostExecutionError("launch_instruction_id values must be unique")
        seen.add(instruction_id)
        _required_text(raw.get("title"), "task title")
        _required_text(raw.get("prompt"), "task prompt")
        if not isinstance(raw.get("required"), bool):
            raise HostExecutionError("task required must be boolean")
        if raw.get("transport") != "durable_user_owned_task":
            raise HostExecutionError("task transport must be durable_user_owned_task")
        if raw.get("target_branch") != target_branch:
            raise HostExecutionError("task target does not match the trusted singleton target")
        attempt = raw.get("attempt")
        retry_of = raw.get("retry_of")
        if type(attempt) is not int or attempt < 1:
            raise HostExecutionError("task attempt must be a positive integer")
        if attempt == 1 and retry_of is not None:
            raise HostExecutionError("first launch attempt cannot have retry lineage")
        if attempt > 1 and (not isinstance(retry_of, str) or not _DIGEST.fullmatch(retry_of)):
            raise HostExecutionError("retry attempt requires a released event digest")
        tasks.append(raw)
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


def _sidecar_capabilities(adapter: HostAdapter) -> None:
    missing = [
        name for name in (
            "lookup_sidecar", "spawn_sidecar", "wait_activity",
            "send_message_to_sidecar", "close_sidecar",
        ) if not callable(getattr(adapter, name, None))
    ]
    if missing:
        raise HostExecutionError("sidecar host capability missing: " + ", ".join(missing))


def _validate_sidecar_creation(value: Mapping[str, object], spec: Mapping[str, object]) -> _SidecarBinding:
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


def _validate_creation(value: Mapping[str, object], instruction_id: str) -> _Binding:
    _exact_keys(value, _CREATE_KEYS, "host task binding")
    if value.get("kind") != CREATE_KIND or value.get("idempotency_key") != instruction_id:
        raise HostExecutionError("host task does not bind the launch idempotency key")
    return _Binding(
        instruction_id=instruction_id,
        task={},
        host_id=_required_text(value.get("host_id"), "host_id"),
        task_id=_required_text(value.get("task_id"), "task_id"),
        cursor=_required_text(value.get("cursor"), "cursor"),
        capability=_required_text(value.get("capability"), "capability"),
    )


def _validate_adoption(created: _Binding, persisted: Mapping[str, object]) -> None:
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


def _notify_primary(adapter: HostAdapter, binding: _Binding, message: str, subject: Mapping[str, object]) -> str:
    key = "sha256:" + sha256(_canonical({"instruction_id": binding.instruction_id, "subject": dict(subject), "message": message})).hexdigest()
    ack = adapter.send_message_to_thread(
        host_id=binding.host_id, task_id=binding.task_id, cursor=binding.cursor,
        capability=binding.capability, message=message, idempotency_key=key,
    )
    if not isinstance(ack, Mapping):
        raise HostExecutionError("primary sidecar notification acknowledgement must be an object")
    _validate_ack(ack, binding, key)
    return str(ack["message_id"])


def _notify_sidecar(adapter: HostAdapter, binding: _SidecarBinding, message: str, subject: Mapping[str, object]) -> str:
    key = "sha256:" + sha256(_canonical({"sidecar_id": binding.sidecar_id, "subject": dict(subject), "message": message})).hexdigest()
    ack = adapter.send_message_to_sidecar(
        host_id=binding.host_id, sidecar_task_id=binding.task_id, cursor=binding.cursor,
        capability=binding.capability, message=message, idempotency_key=key,
    )
    if not isinstance(ack, Mapping):
        raise HostExecutionError("sidecar notification acknowledgement must be an object")
    _validate_sidecar_ack(ack, binding, key)
    return str(ack["message_id"])


def _close_sidecar(repo_root: Path, adapter: HostAdapter, binding: _SidecarBinding, reason: str) -> Mapping[str, object]:
    key = "sha256:" + sha256(_canonical({"sidecar_id": binding.sidecar_id, "reason": reason})).hexdigest()
    raw = adapter.close_sidecar(
        host_id=binding.host_id, sidecar_task_id=binding.task_id, cursor=binding.cursor,
        capability=binding.capability, reason=reason, idempotency_key=key,
    )
    if not isinstance(raw, Mapping):
        raise HostExecutionError("close_sidecar must return a terminal sidecar event")
    _validate_sidecar_event(raw, binding)
    if raw.get("state") not in {"CANCELLED", "FAILED"}:
        raise HostExecutionError("close_sidecar did not settle the sidecar")
    state, result = _terminal_sidecar_result(raw.get("result"), binding, str(raw["state"]))
    record_sidecar_state(
        repo_root, binding.sidecar_id, state,
        parent_launch_instruction_id=binding.spec["parent_launch_instruction_id"],
        parent_sidecar_id=binding.spec.get("parent_sidecar_id"),
        host_id=binding.host_id, sidecar_task_id=binding.task_id,
        host_event_id=raw["event_id"], host_event_cursor=raw["event_cursor"],
        result=dict(result), close_reason=reason,
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
    return {
        "schema_version": 1,
        "kind": RESULT_KIND,
        "outcome": "BLOCKED",
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
) -> dict[str, object]:
    """Create or adopt a complete wave, supervise it, and close only on live truth."""

    if min(max_no_progress_cycles, max_poll_cycles, max_replay_events) < 1:
        raise HostExecutionError("host polling bounds must be positive")
    trusted_target_branch = adapter.trusted_singleton_target(repo_root=repo_root)
    tasks = validate_contract(repo_root, contract, trusted_target_branch)
    sidecar_specs = _sidecar_specs(contract, tasks)
    if sidecar_specs:
        _sidecar_capabilities(adapter)
    active: dict[str, _Binding] = {}
    terminal: dict[str, str] = {}

    # Every task is created or crash-safely adopted before the first wait.
    for task in tasks:
        instruction_id = str(task["launch_instruction_id"])
        attempt = task.get("attempt")
        if type(attempt) is not int:
            raise HostExecutionError("validated task attempt changed before launch")
        prepared = prepare_launch(
            repo_root,
            instruction_id,
            host,
            attempt=attempt,
            retry_of=str(task["retry_of"]) if task.get("retry_of") is not None else None,
        )
        if prepared.get("state") == "RELEASED" and prepared.get("terminal_state") == "SUCCEEDED":
            terminal[instruction_id] = "SUCCEEDED"
            continue
        looked_up = adapter.lookup_thread(idempotency_key=instruction_id)
        if looked_up is None:
            if prepared.get("state") not in {"PREPARED"}:
                raise HostExecutionError("persisted host binding cannot be recovered by idempotency key")
            looked_up = adapter.create_thread(
                title=str(task["title"]),
                prompt=str(task["prompt"]),
                idempotency_key=instruction_id,
            )
        if not isinstance(looked_up, Mapping):
            raise HostExecutionError("host task lookup or creation must return an object")
        created = _validate_creation(looked_up, instruction_id)
        _validate_adoption(created, prepared)
        binding = _Binding(
            instruction_id=instruction_id,
            task=task,
            host_id=created.host_id,
            task_id=created.task_id,
            cursor=created.cursor,
            capability=created.capability,
        )
        bind_launch(
            repo_root,
            instruction_id,
            host,
            binding.task_id,
            host_id=binding.host_id,
            cursor=binding.cursor,
            capability=binding.capability,
        )
        active[instruction_id] = binding

    primary_bindings = dict(active)
    sidecar_active: dict[str, _SidecarBinding] = {}
    sidecar_terminal: dict[str, str] = {}
    persisted_sidecars = latest_sidecars(repo_root) if sidecar_specs else {}
    for spec in sidecar_specs:
        sidecar_id = str(spec["sidecar_id"])
        parent_id = str(spec["parent_launch_instruction_id"])
        prior = persisted_sidecars.get(sidecar_id)
        if prior is not None and prior.get("state") in TERMINAL_SIDECAR_STATES:
            sidecar_terminal[sidecar_id] = str(prior["state"])
            continue
        if prior is None:
            record_sidecar_state(
                repo_root, sidecar_id, "PREPARED",
                parent_launch_instruction_id=parent_id,
                parent_sidecar_id=spec.get("parent_sidecar_id"),
                spec_digest=sidecar_spec_digest(spec),
                token_budget_reserved=spec["token_budget"],
            )
        looked_up = adapter.lookup_sidecar(idempotency_key=sidecar_id)
        if looked_up is None:
            try:
                looked_up = adapter.spawn_sidecar(
                    prompt=str(spec["prompt"]), token_budget=int(spec["token_budget"]),
                    idempotency_key=sidecar_id, parent_launch_instruction_id=parent_id,
                )
            except Exception as error:
                record_sidecar_state(
                    repo_root, sidecar_id, "SPAWN_FAILED",
                    parent_launch_instruction_id=parent_id,
                    parent_sidecar_id=spec.get("parent_sidecar_id"),
                    spec_digest=sidecar_spec_digest(spec), error=type(error).__name__,
                )
                sidecar_terminal[sidecar_id] = "SPAWN_FAILED"
                parent = primary_bindings.get(parent_id)
                if parent is not None:
                    _notify_primary(
                        adapter, parent,
                        f"Sidecar {sidecar_id} could not start ({type(error).__name__}); continue without its advisory evidence.",
                        {"sidecar_id": sidecar_id, "state": "SPAWN_FAILED"},
                    )
                continue
        if not isinstance(looked_up, Mapping):
            return _blocked(
                "SIDECAR_BINDING_INVALID",
                "sidecar lookup or spawn returned no recoverable binding",
                tuple(active.values()), terminal, sidecar_id=sidecar_id,
            )
        binding = _validate_sidecar_creation(looked_up, spec)
        if prior is not None:
            for field, actual in {"host_id": binding.host_id, "sidecar_task_id": binding.task_id}.items():
                if prior.get(field) is not None and prior.get(field) != actual:
                    raise HostExecutionError(f"looked-up sidecar conflicts with persisted {field}")
        record_sidecar_state(
            repo_root, sidecar_id, "BOUND",
            parent_launch_instruction_id=parent_id,
            parent_sidecar_id=spec.get("parent_sidecar_id"),
            spec_digest=sidecar_spec_digest(spec), host_id=binding.host_id,
            sidecar_task_id=binding.task_id, cursor=binding.cursor,
            capability_digest="sha256:" + sha256(binding.capability.encode()).hexdigest(),
            token_budget_reserved=spec["token_budget"],
        )
        sidecar_active[sidecar_id] = binding
        parent = primary_bindings.get(parent_id)
        if parent is not None:
            message_id = _notify_primary(
                adapter, parent,
                f"Advisory read-only sidecar {sidecar_id} ({spec['purpose']}) is active. Do not finish until its root-delivered terminal packet arrives.",
                {"sidecar_id": sidecar_id, "state": "BOUND"},
            )
            record_sidecar_state(
                repo_root, sidecar_id, "ACTIVE",
                parent_launch_instruction_id=parent_id,
                parent_sidecar_id=spec.get("parent_sidecar_id"),
                host_id=binding.host_id, sidecar_task_id=binding.task_id,
                parent_spawn_message_id=message_id,
            )

    event_cursors: dict[str, str] = {}
    seen_event_ids: dict[str, tuple[str, str]] = {}
    for event in binding_events(repo_root):
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
    sidecar_count = len(sidecar_specs)
    sidecar_budget_reserved = sum(int(spec["token_budget"]) for spec in sidecar_specs)
    wait_rotation = 0
    while active or sidecar_active:
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
                    result = _close_sidecar(repo_root, adapter, sidecar, "wall-clock wait timeout")
                    parent = primary_bindings.get(str(sidecar.spec["parent_launch_instruction_id"]))
                    if parent is not None and parent.instruction_id in active:
                        _notify_primary(adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": key, "state": "CANCELLED"})
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
                result = _close_sidecar(repo_root, adapter, sidecar, f"invalid host event: {error}")
                parent_id = str(sidecar.spec["parent_launch_instruction_id"])
                parent = primary_bindings.get(parent_id)
                if parent is not None and parent_id in active:
                    _notify_primary(adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": sidecar.sidecar_id, "state": "FAILED"})
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
                message_id = _notify_sidecar(adapter, sidecar, answer, {"host_event_id": event_id})
                record_sidecar_state(repo_root, sidecar.sidecar_id, "ATTENTION_ACKNOWLEDGED", parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_event_id=event_id, host_event_cursor=event_cursor, message_id=message_id)
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
                    if sidecar_count >= int(sidecar_policy["max_total_sidecars"]):
                        raise HostExecutionError("sidecar count budget exhausted")
                    if sidecar_budget_reserved + descendant_budget > int(sidecar_policy["total_token_budget"]):
                        raise HostExecutionError("sidecar token budget exhausted")
                    if descendant_id in sidecar_active or descendant_id in sidecar_terminal:
                        raise HostExecutionError("duplicate descendant is already known")
                    record_sidecar_state(repo_root, descendant_id, "PREPARED", parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.sidecar_id, spec_digest=sidecar_spec_digest(descendant_spec), token_budget_reserved=descendant_budget)
                    created_raw = adapter.lookup_sidecar(idempotency_key=descendant_id)
                    if created_raw is None:
                        created_raw = adapter.spawn_sidecar(
                            prompt=str(descendant_spec["prompt"]), token_budget=descendant_budget,
                            idempotency_key=descendant_id, parent_launch_instruction_id=parent_id,
                        )
                    if not isinstance(created_raw, Mapping):
                        raise HostExecutionError("descendant spawn returned no binding")
                    descendant = _validate_sidecar_creation(created_raw, descendant_spec)
                    record_sidecar_state(repo_root, descendant_id, "BOUND", parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.sidecar_id, spec_digest=sidecar_spec_digest(descendant_spec), host_id=descendant.host_id, sidecar_task_id=descendant.task_id, cursor=descendant.cursor, capability_digest="sha256:" + sha256(descendant.capability.encode()).hexdigest(), token_budget_reserved=descendant_budget)
                    sidecar_active[descendant_id] = descendant
                    sidecar_count += 1
                    sidecar_budget_reserved += descendant_budget
                    decision = "ADMITTED"
                    denial = ""
                    if parent is not None and parent_id in active:
                        _notify_primary(adapter, parent, f"Root admitted descendant sidecar {descendant_id} under {sidecar.sidecar_id}; wait for its terminal packet.", {"sidecar_id": descendant_id, "parent_sidecar_id": sidecar.sidecar_id, "state": "BOUND"})
                except Exception as error:
                    denial = str(error)
                response = f"{decision}: {denial}" if denial else f"{decision}: descendant {descendant_id} is root-managed and budget-reserved."
                _notify_sidecar(adapter, sidecar, response, {"host_event_id": event_id, "decision": decision})
                record_sidecar_state(repo_root, sidecar.sidecar_id, "ACTIVE", parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_event_id=event_id, host_event_cursor=event_cursor, descendant_request=decision)
            elif state == "ACTIVE":
                record_sidecar_state(repo_root, sidecar.sidecar_id, "ACTIVE", parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_event_id=event_id, host_event_cursor=event_cursor)
            else:
                descendants = [
                    child for child in sidecar_active.values()
                    if child.spec.get("parent_sidecar_id") == sidecar.sidecar_id
                ]
                for child in descendants:
                    child_result = _close_sidecar(
                        repo_root, adapter, child,
                        "sidecar parent attempted terminal transition before descendant settlement",
                    )
                    _notify_sidecar(adapter, sidecar, json.dumps(dict(child_result), sort_keys=True), {"sidecar_id": child.sidecar_id, "state": "CANCELLED"})
                    if parent is not None and parent_id in active:
                        _notify_primary(adapter, parent, json.dumps(dict(child_result), sort_keys=True), {"sidecar_id": child.sidecar_id, "state": "CANCELLED"})
                    sidecar_terminal[child.sidecar_id] = "CANCELLED"
                    del sidecar_active[child.sidecar_id]
                state, result = _terminal_sidecar_result(raw.get("result"), sidecar, state)
                message_id = None
                immediate_parent_id = sidecar.spec.get("parent_sidecar_id")
                immediate_parent = sidecar_active.get(str(immediate_parent_id)) if immediate_parent_id else None
                if immediate_parent is not None:
                    _notify_sidecar(adapter, immediate_parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": sidecar.sidecar_id, "state": state})
                if parent is not None and parent_id in active:
                    message_id = _notify_primary(adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": sidecar.sidecar_id, "state": state})
                # The terminal record plus an acknowledged parent message is the settlement barrier.
                record_sidecar_state(repo_root, sidecar.sidecar_id, state, parent_launch_instruction_id=parent_id, parent_sidecar_id=sidecar.spec.get("parent_sidecar_id"), host_id=sidecar.host_id, sidecar_task_id=sidecar.task_id, host_event_id=event_id, host_event_cursor=event_cursor, result=dict(result), parent_terminal_message_id=message_id)
                sidecar_terminal[sidecar.sidecar_id] = state
                del sidecar_active[sidecar.sidecar_id]
            sidecar_cursors[sidecar.sidecar_id] = event_cursor
            sidecar_seen_events[event_id] = (sidecar.sidecar_id, event_cursor)
            sidecar_progressed = True
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
                    message_id=str(ack_raw["message_id"]),
                )
            elif state == "ACTIVE":
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
                    )
                    _notify_primary(
                        adapter, binding, json.dumps(dict(result), sort_keys=True),
                        {"sidecar_id": child.sidecar_id, "state": "CANCELLED"},
                    )
                    sidecar_terminal[child.sidecar_id] = "CANCELLED"
                    del sidecar_active[child.sidecar_id]
                release_terminal_launch(
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
                result = _close_sidecar(repo_root, adapter, child, disposition)
                parent = primary_bindings.get(str(child.spec["parent_launch_instruction_id"]))
                if parent is not None and parent.instruction_id in active:
                    _notify_primary(adapter, parent, json.dumps(dict(result), sort_keys=True), {"sidecar_id": key, "state": "CANCELLED"})
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

    failed_required = sorted(
        str(task["launch_instruction_id"])
        for task in tasks
        if task.get("required") is True
        and terminal.get(str(task["launch_instruction_id"])) != "SUCCEEDED"
    )
    claims, lease, controller_quiescent = _runtime_authority(
        repo_root, contract, adapter, trusted_target_branch
    )
    live_bindings = active_launch_bindings(repo_root)
    live_sidecars = active_sidecars(repo_root) if sidecar_specs else ()
    if claims or lease is not None or live_bindings or live_sidecars or not controller_quiescent:
        return {
            "schema_version": 1,
            "kind": RESULT_KIND,
            "outcome": "BLOCKED" if failed_required else "ACTIVE",
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
        "successful": not failed_required,
        "quiescent": True,
        "required_active": [],
        "terminal": dict(sorted(terminal.items())),
        "sidecar_terminal": dict(sorted(sidecar_terminal.items())),
        "blocker": blocker,
    }
