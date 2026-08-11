from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from host_execution import (  # pyright: ignore[reportMissingImports]  # noqa: E402
    ACK_KIND,
    CONTRACT_KIND,
    CREATE_KIND,
    EVENT_KIND,
    HostExecutionError,
    execute_contract,
)


def _contract(*, tasks: int = 2) -> dict[str, Any]:
    rows = []
    for index in range(tasks):
        instruction_id = "sha256:" + f"{index + 1:064x}"
        rows.append(
            {
                "task_key": f"NODE-{index}",
                "node_id": f"NODE-{index}",
                "launch_instruction_id": instruction_id,
                "idempotency_key": instruction_id,
                "title": f"Node {index}",
                "prompt": f"Execute node {index}",
                "required": True,
                "transport": "durable_user_owned_task",
            }
        )
    value: dict[str, Any] = {
        "schema_version": 1,
        "kind": CONTRACT_KIND,
        "tasks": rows,
        "execution": {
            "create_all_parallel_safe_primary_tasks": True,
            "poll_until_terminal": True,
            "answer_and_resume_blocked_tasks": True,
            "parent_final_while_required_tasks_active": False,
        },
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    value["contract_id"] = "sha256:" + sha256(encoded).hexdigest()
    return value


class Resolver:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def resolve_attention(
        self, task: Mapping[str, object], event: Mapping[str, object]
    ) -> str:
        self.questions.append(str(event["attention"]))
        return f"resolved for {task['node_id']}"


class Adapter:
    def __init__(self, script: Sequence[Sequence[Mapping[str, object]]]) -> None:
        self.script = list(script)
        self.created: list[str] = []
        self.wait_create_counts: list[int] = []
        self.messages: list[str] = []
        self.bindings: dict[str, dict[str, str]] = {}

    def create_thread(
        self, *, title: str, prompt: str, idempotency_key: str
    ) -> Mapping[str, object]:
        del title, prompt
        index = len(self.created)
        self.created.append(idempotency_key)
        binding = {
            "host_id": "host-1",
            "task_id": f"task-{index}",
            "cursor": f"binding-cursor-{index}",
            "capability": f"capability-{index}",
        }
        self.bindings[idempotency_key] = binding
        return {
            "kind": CREATE_KIND,
            **binding,
            "idempotency_key": idempotency_key,
        }

    def wait_threads(
        self, targets: Sequence[Mapping[str, object]]
    ) -> Sequence[Mapping[str, object]]:
        self.wait_create_counts.append(len(self.created))
        if not self.script:
            return []
        batch = []
        for event in self.script.pop(0):
            material = dict(event)
            instruction_id = str(material.pop("instruction_id"))
            material.update(self.bindings[instruction_id])
            batch.append(material)
        return batch

    def send_message_to_thread(
        self,
        *,
        host_id: str,
        task_id: str,
        cursor: str,
        capability: str,
        message: str,
    ) -> Mapping[str, object]:
        self.messages.append(message)
        return {
            "kind": ACK_KIND,
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
            "capability": capability,
            "accepted": True,
            "message_id": f"message-{len(self.messages)}",
        }


def _event(instruction_id: str, state: str, cursor: str, **extra: object) -> dict[str, object]:
    return {
        "kind": EVENT_KIND,
        "instruction_id": instruction_id,
        "state": state,
        "event_id": f"event-{instruction_id[-8:]}-{cursor}",
        "event_cursor": cursor,
        **extra,
    }


class HostExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".autopilot").mkdir()
        shutil.copy2(
            Path(__file__).resolve().parents[1] / "task-bindings.lock",
            self.root / ".autopilot" / "task-bindings.lock",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_creates_entire_parallel_wave_before_first_wait(self) -> None:
        contract = _contract()
        ids = [str(task["launch_instruction_id"]) for task in contract["tasks"]]
        adapter = Adapter(
            [[_event(ids[0], "SUCCEEDED", "1"), _event(ids[1], "SUCCEEDED", "1")]]
        )

        result = execute_contract(self.root, contract, adapter, Resolver())

        self.assertEqual(adapter.wait_create_counts, [2])
        self.assertTrue(result["successful"])
        self.assertTrue(result["quiescent"])

    def test_attention_self_heals_sends_answer_and_resumes(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter(
            [
                [_event(instruction_id, "NEEDS_ATTENTION", "1", attention="need a safe fix")],
                [_event(instruction_id, "SUCCEEDED", "2")],
            ]
        )
        resolver = Resolver()

        result = execute_contract(self.root, contract, adapter, resolver)

        self.assertEqual(resolver.questions, ["need a safe fix"])
        self.assertEqual(adapter.messages, ["resolved for NODE-0"])
        self.assertEqual(adapter.wait_create_counts, [1, 1])
        self.assertTrue(result["successful"])

    def test_forged_capability_event_is_rejected(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        original_wait = adapter.wait_threads

        def forged_wait(targets: Sequence[Mapping[str, object]]) -> Sequence[Mapping[str, object]]:
            events = [dict(item) for item in original_wait(targets)]
            events[0]["capability"] = "forged-capability"
            return events

        adapter.wait_threads = forged_wait  # type: ignore[method-assign]

        with self.assertRaisesRegex(HostExecutionError, "forged or mismatched capability"):
            execute_contract(self.root, contract, adapter, Resolver())

    def test_required_active_task_prevents_success_and_quiescence(self) -> None:
        contract = _contract(tasks=1)
        adapter = Adapter([[], []])

        result = execute_contract(
            self.root,
            contract,
            adapter,
            Resolver(),
            max_no_progress_cycles=2,
        )

        self.assertEqual(result["outcome"], "BLOCKED")
        self.assertFalse(result["successful"])
        self.assertFalse(result["quiescent"])
        self.assertEqual(result["blocker"]["code"], "HOST_NO_PROGRESS_LIMIT")
        self.assertEqual(len(result["required_active"]), 1)


if __name__ == "__main__":
    unittest.main()
