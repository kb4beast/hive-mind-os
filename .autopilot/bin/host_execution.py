"""Capability-bound, crash-safe host execution for Autopilot contracts."""

from __future__ import annotations

import json
import re
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

CONTRACT_KIND = "hive-mind-autopilot-orchestration-contract-v1"
CREATE_KIND = "hive-mind-host-task-binding-v1"
EVENT_KIND = "hive-mind-host-event-v1"
ACK_KIND = "hive-mind-host-message-ack-v1"
RESULT_KIND = "hive-mind-host-execution-result-v1"
BLOCKER_KIND = "hive-mind-host-execution-blocker-v1"
TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})
EVENT_STATES = TERMINAL_STATES | {"ACTIVE", "NEEDS_ATTENTION"}
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
    return tuple(tasks)


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
    while active:
        poll_cycles += 1
        waiting = tuple(active[key] for key in sorted(active))
        events_raw = adapter.wait_threads(
            [item.wait_target(event_cursors.get(item.instruction_id)) for item in waiting]
        )
        if not isinstance(events_raw, Sequence) or isinstance(events_raw, (str, bytes)):
            raise HostExecutionError("wait_threads result must be a sequence of events")
        progressed = False
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

        no_progress = 0 if progressed else no_progress + 1
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
    if claims or lease is not None or live_bindings or not controller_quiescent:
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
        "blocker": blocker,
    }
