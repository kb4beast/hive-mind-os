"""Bounded host execution for v1 Autopilot orchestration contracts.

The repository controller emits host-neutral work.  This module is the reusable
host-side loop that turns that work into durable tasks while keeping host events
strictly bound to the task capability returned at creation time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from orchestration import (
    bind_launch,
    observe_terminal_launch,
    prepare_launch,
    release_launch,
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
    }
)


class HostExecutionError(RuntimeError):
    """A contract or host event failed closed validation."""


class HostAdapter(Protocol):
    """Durable task host used by :func:`execute_contract`."""

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
    ) -> Mapping[str, object]: ...


class SafeResolver(Protocol):
    """Produces an in-authority answer for a task attention request."""

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
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise HostExecutionError(
            f"{subject} has invalid fields; missing={missing}, unknown={unknown}"
        )


def validate_contract(contract: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    """Validate the executable subset of a v1 orchestration contract."""

    if contract.get("schema_version") != 1 or contract.get("kind") != CONTRACT_KIND:
        raise HostExecutionError("expected a v1 Autopilot orchestration contract")
    contract_id = contract.get("contract_id")
    if not isinstance(contract_id, str) or not _DIGEST.fullmatch(contract_id):
        raise HostExecutionError("contract_id must be a SHA-256 digest")
    material = dict(contract)
    material.pop("contract_id", None)
    expected_id = "sha256:" + sha256(_canonical(material)).hexdigest()
    if contract_id != expected_id:
        raise HostExecutionError("contract_id does not authenticate the contract body")
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
        tasks.append(raw)
    return tuple(tasks)


def _validate_creation(value: Mapping[str, object], instruction_id: str) -> _Binding:
    _exact_keys(value, _CREATE_KEYS, "create_thread result")
    if value.get("kind") != CREATE_KIND:
        raise HostExecutionError("create_thread returned an unknown result kind")
    if value.get("idempotency_key") != instruction_id:
        raise HostExecutionError("create_thread did not bind the launch idempotency key")
    return _Binding(
        instruction_id=instruction_id,
        task={},
        host_id=_required_text(value.get("host_id"), "host_id"),
        task_id=_required_text(value.get("task_id"), "task_id"),
        cursor=_required_text(value.get("cursor"), "cursor"),
        capability=_required_text(value.get("capability"), "capability"),
    )


def _validate_event(value: Mapping[str, object], binding: _Binding) -> None:
    state = value.get("state")
    expected_keys = _EVENT_BASE_KEYS | ({"attention"} if state == "NEEDS_ATTENTION" else set())
    _exact_keys(value, frozenset(expected_keys), "host event")
    if value.get("kind") != EVENT_KIND or state not in EVENT_STATES:
        raise HostExecutionError("host returned an unknown event kind or state")
    expected_binding = {
        "host_id": binding.host_id,
        "task_id": binding.task_id,
        "cursor": binding.cursor,
        "capability": binding.capability,
    }
    for field, expected in expected_binding.items():
        if value.get(field) != expected:
            raise HostExecutionError(f"host event has forged or mismatched {field}")
    _required_text(value.get("event_id"), "event_id")
    _required_text(value.get("event_cursor"), "event_cursor")
    if state == "NEEDS_ATTENTION":
        _required_text(value.get("attention"), "attention")


def _validate_ack(value: Mapping[str, object], binding: _Binding) -> None:
    _exact_keys(value, _ACK_KEYS, "send_message_to_thread result")
    if value.get("kind") != ACK_KIND or value.get("accepted") is not True:
        raise HostExecutionError("host did not accept the recovery message")
    for field, expected in {
        "host_id": binding.host_id,
        "task_id": binding.task_id,
        "cursor": binding.cursor,
        "capability": binding.capability,
    }.items():
        if value.get(field) != expected:
            raise HostExecutionError(f"message acknowledgement has mismatched {field}")
    _required_text(value.get("message_id"), "message_id")


def _blocker(code: str, message: str, active: Sequence[_Binding], limit: int) -> dict[str, object]:
    return {
        "kind": BLOCKER_KIND,
        "code": code,
        "message": message,
        "max_no_progress_cycles": limit,
        "active_launch_instruction_ids": sorted(item.instruction_id for item in active),
    }


def execute_contract(
    repo_root: Path,
    contract: Mapping[str, object],
    adapter: HostAdapter,
    resolver: SafeResolver,
    *,
    host: str = "codex",
    max_no_progress_cycles: int = 3,
) -> dict[str, object]:
    """Create, supervise, recover, and close every task in a v1 contract."""

    if max_no_progress_cycles < 1:
        raise HostExecutionError("max_no_progress_cycles must be at least one")
    tasks = validate_contract(contract)
    active: dict[str, _Binding] = {}
    terminal: dict[str, str] = {}
    event_cursors: dict[str, str] = {}

    # This phase intentionally completes for every task before the first wait.
    for task in tasks:
        instruction_id = str(task["launch_instruction_id"])
        prepare_launch(repo_root, instruction_id, host)
        created_raw = adapter.create_thread(
            title=str(task["title"]),
            prompt=str(task["prompt"]),
            idempotency_key=instruction_id,
        )
        if not isinstance(created_raw, Mapping):
            raise HostExecutionError("create_thread result must be an object")
        created = _validate_creation(created_raw, instruction_id)
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
        )
        active[instruction_id] = binding

    no_progress = 0
    while active:
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
            task_id = raw.get("task_id")
            matches = [item for item in active.values() if item.task_id == task_id]
            if len(matches) != 1:
                raise HostExecutionError("host event references an unknown or ambiguous task_id")
            binding = matches[0]
            _validate_event(raw, binding)
            event_id = str(raw["event_id"])
            event_cursor = str(raw["event_cursor"])
            if event_id in seen_in_batch:
                raise HostExecutionError("wait_threads returned a duplicate event_id")
            seen_in_batch.add(event_id)
            if event_cursors.get(binding.instruction_id) == event_cursor:
                continue
            event_cursors[binding.instruction_id] = event_cursor
            progressed = True
            state = str(raw["state"])
            if state == "NEEDS_ATTENTION":
                answer = resolver.resolve_attention(binding.task, raw)
                if not isinstance(answer, str) or not answer.strip():
                    raise HostExecutionError("safe resolver must return a non-empty answer")
                ack_raw = adapter.send_message_to_thread(
                    host_id=binding.host_id,
                    task_id=binding.task_id,
                    cursor=binding.cursor,
                    capability=binding.capability,
                    message=answer,
                )
                if not isinstance(ack_raw, Mapping):
                    raise HostExecutionError("send_message_to_thread result must be an object")
                _validate_ack(ack_raw, binding)
            elif state in TERMINAL_STATES:
                observed = observe_terminal_launch(
                    repo_root,
                    binding.instruction_id,
                    terminal_state=state,
                    host_event_ref=(
                        f"{host}:{binding.host_id}:{binding.task_id}:{event_id}:{event_cursor}"
                    ),
                    observed_by=f"host-execution:{host}",
                )
                release_launch(
                    repo_root,
                    binding.instruction_id,
                    terminal_event_id=str(observed["event_id"]),
                    reason="capability-bound host task reached a terminal state",
                )
                terminal[binding.instruction_id] = state
                del active[binding.instruction_id]

        no_progress = 0 if progressed else no_progress + 1
        if active and no_progress >= max_no_progress_cycles:
            required_active = [item for item in active.values() if item.task.get("required") is True]
            blocker = _blocker(
                "HOST_NO_PROGRESS_LIMIT",
                "host tasks made no progress before the bounded polling limit",
                tuple(active.values()),
                max_no_progress_cycles,
            )
            return {
                "schema_version": 1,
                "kind": RESULT_KIND,
                "outcome": "BLOCKED",
                "successful": False,
                "quiescent": False,
                "required_active": sorted(item.instruction_id for item in required_active),
                "terminal": dict(sorted(terminal.items())),
                "blocker": blocker,
            }

    failed_required = sorted(
        str(task["launch_instruction_id"])
        for task in tasks
        if task.get("required") is True
        and terminal.get(str(task["launch_instruction_id"])) != "SUCCEEDED"
    )
    successful = not failed_required
    blocker = None
    if failed_required:
        blocker = _blocker(
            "REQUIRED_TASK_TERMINAL_FAILURE",
            "one or more required host tasks ended without success",
            (),
            max_no_progress_cycles,
        )
        blocker["failed_launch_instruction_ids"] = failed_required
    return {
        "schema_version": 1,
        "kind": RESULT_KIND,
        "outcome": "SUCCESS" if successful else "BLOCKED",
        "successful": successful,
        "quiescent": True,
        "required_active": [],
        "terminal": dict(sorted(terminal.items())),
        "blocker": blocker,
    }
