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

from host_execution import (  # noqa: E402
    ACK_KIND,
    CONTRACT_KIND,
    CREATE_KIND,
    EVENT_KIND,
    HostExecutionError,
    execute_contract,
)
from orchestration import (  # noqa: E402
    bind_launch,
    binding_events,
    prepare_launch,
    release_terminal_launch,
)

TARGET = "release/test"


def _rehash(value: dict[str, Any]) -> dict[str, Any]:
    material = dict(value)
    material.pop("contract_id", None)
    value["contract_id"] = "sha256:" + sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return value


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
                "attempt": 1,
                "retry_of": None,
                "title": f"Node {index}",
                "prompt": f"Execute node {index}",
                "required": True,
                "target_branch": TARGET,
                "transport": "durable_user_owned_task",
            }
        )
    return _rehash(
        {
            "schema_version": 1,
            "kind": CONTRACT_KIND,
            "target_branch": TARGET,
            "tasks": rows,
            "active_claims": [],
            "active_validation_lease": None,
            "execution": {
                "create_all_parallel_safe_primary_tasks": True,
                "poll_until_terminal": True,
                "answer_and_resume_blocked_tasks": True,
                "parent_final_while_required_tasks_active": False,
            },
        }
    )


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
        self.lookup_count = 0
        self.wait_create_counts: list[int] = []
        self.messages: dict[str, str] = {}
        self.bindings: dict[str, dict[str, str]] = {}
        self.trusted_target = TARGET
        self.runtime: dict[str, object] = {
            "target_branch": TARGET,
            "active_claims": [],
            "active_validation_lease": None,
            "quiescent": True,
        }
        self.fail_after_first_message = False

    def trusted_singleton_target(self, *, repo_root: Path) -> str:
        del repo_root
        return self.trusted_target

    def seed(self, instruction_id: str, index: int = 0) -> dict[str, object]:
        binding = {
            "host_id": "host-1",
            "task_id": f"task-{index}",
            "cursor": f"binding-cursor-{index}",
            "capability": f"capability-{index}",
        }
        self.bindings[instruction_id] = binding
        return {"kind": CREATE_KIND, **binding, "idempotency_key": instruction_id}

    def lookup_thread(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        self.lookup_count += 1
        binding = self.bindings.get(idempotency_key)
        return None if binding is None else {
            "kind": CREATE_KIND,
            **binding,
            "idempotency_key": idempotency_key,
        }

    def create_thread(
        self, *, title: str, prompt: str, idempotency_key: str
    ) -> Mapping[str, object]:
        del title, prompt
        existing = self.lookup_thread(idempotency_key=idempotency_key)
        if existing is not None:
            return existing
        index = len(self.bindings)
        self.created.append(idempotency_key)
        return self.seed(idempotency_key, index)

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
        idempotency_key: str,
    ) -> Mapping[str, object]:
        self.messages.setdefault(idempotency_key, message)
        if self.fail_after_first_message:
            self.fail_after_first_message = False
            raise RuntimeError("simulated parent crash after accepted message")
        return {
            "kind": ACK_KIND,
            "host_id": host_id,
            "task_id": task_id,
            "cursor": cursor,
            "capability": capability,
            "accepted": True,
            "message_id": f"message-{idempotency_key[-8:]}",
            "idempotency_key": idempotency_key,
        }

    def inspect_runtime_authority(self, *, repo_root: Path) -> Mapping[str, object]:
        del repo_root
        return self.runtime


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
        source = Path(__file__).resolve().parents[1]
        shutil.copy2(source / "task-bindings.lock", self.root / ".autopilot" / "task-bindings.lock")
        control = json.loads((source / "control-plane.json").read_text(encoding="utf-8"))
        control["target"]["branch"] = TARGET
        (self.root / ".autopilot" / "control-plane.json").write_text(
            json.dumps(control), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_creates_entire_parallel_wave_before_first_wait(self) -> None:
        contract = _contract()
        ids = [str(task["launch_instruction_id"]) for task in contract["tasks"]]
        adapter = Adapter([[_event(ids[0], "SUCCEEDED", "1"), _event(ids[1], "SUCCEEDED", "1")]])
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertEqual(adapter.wait_create_counts, [2])
        self.assertTrue(result["successful"])
        self.assertTrue(result["quiescent"])

    def test_attention_self_heals_sends_answer_and_resumes(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter(
            [[_event(instruction_id, "NEEDS_ATTENTION", "1", attention="need a safe fix")],
             [_event(instruction_id, "SUCCEEDED", "2")]]
        )
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertEqual(list(adapter.messages.values()), ["resolved for NODE-0"])
        self.assertEqual(adapter.wait_create_counts, [1, 1])
        self.assertTrue(result["successful"])

    def test_attention_message_is_idempotent_across_parent_crash(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        attention = _event(instruction_id, "NEEDS_ATTENTION", "1", attention="recover")
        adapter = Adapter([[attention]])
        adapter.fail_after_first_message = True
        with self.assertRaisesRegex(RuntimeError, "simulated parent crash"):
            execute_contract(self.root, contract, adapter, Resolver())
        adapter.script = [[attention], [_event(instruction_id, "SUCCEEDED", "2")]]
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(len(adapter.messages), 1)
        self.assertEqual(adapter.created, [instruction_id])

    def test_prepared_launch_adopts_lookup_without_duplicate_create(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        prepare_launch(self.root, instruction_id, "codex")
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        adapter.seed(instruction_id)
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(adapter.created, [])

    def test_bound_launch_requires_lookup_and_adopts_exact_capability(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        adapter.seed(instruction_id)
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "task-0",
            host_id="host-1", cursor="binding-cursor-0", capability="capability-0"
        )
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(adapter.created, [])

    def test_forged_capability_event_is_rejected_without_terminal_release(self) -> None:
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
        self.assertEqual(binding_events(self.root)[-1]["state"], "BOUND")

    def test_required_active_task_prevents_success_and_quiescence(self) -> None:
        contract = _contract(tasks=1)
        adapter = Adapter([[], []])
        result = execute_contract(
            self.root, contract, adapter, Resolver(), max_no_progress_cycles=2
        )
        self.assertEqual(result["blocker"]["code"], "HOST_NO_PROGRESS_LIMIT")
        self.assertFalse(result["quiescent"])

    def test_total_poll_bound_stops_endless_unique_progress(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "ACTIVE", str(index))] for index in range(1, 5)])
        result = execute_contract(
            self.root, contract, adapter, Resolver(), max_poll_cycles=3
        )
        self.assertEqual(result["blocker"]["code"], "HOST_TOTAL_POLL_LIMIT")
        self.assertFalse(result["quiescent"])

    def test_persisted_event_replay_is_bounded(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        event = _event(instruction_id, "ACTIVE", "1")
        adapter = Adapter([[event], [event], [event]])
        result = execute_contract(
            self.root, contract, adapter, Resolver(), max_replay_events=2
        )
        self.assertEqual(result["blocker"]["code"], "HOST_REPLAY_LIMIT")

    def test_main_target_is_rejected_even_with_valid_contract_digest(self) -> None:
        contract = _contract(tasks=1)
        contract["target_branch"] = "main"
        contract["tasks"][0]["target_branch"] = "main"
        _rehash(contract)
        with self.assertRaisesRegex(HostExecutionError, "trusted singleton target"):
            execute_contract(self.root, contract, Adapter([]), Resolver())

    def test_external_host_target_must_match_control_plane(self) -> None:
        adapter = Adapter([])
        adapter.trusted_target = "release/other"
        with self.assertRaisesRegex(HostExecutionError, "host trust"):
            execute_contract(self.root, _contract(tasks=1), adapter, Resolver())

    def test_live_claim_and_lease_prevent_false_quiescence(self) -> None:
        contract = _contract(tasks=1)
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        adapter.runtime = {
            "target_branch": TARGET,
            "active_claims": ["OTHER-999"],
            "active_validation_lease": {"owner": "validator"},
            "quiescent": False,
        }
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertEqual(result["outcome"], "ACTIVE")
        self.assertFalse(result["successful"])
        self.assertFalse(result["quiescent"])
        self.assertEqual(result["blocker"]["code"], "RUNTIME_AUTHORITY_ACTIVE")

    def test_retry_attempt_and_lineage_reach_durable_binding(self) -> None:
        first_id = "sha256:" + "a" * 64
        prepare_launch(self.root, first_id, "codex")
        bind_launch(
            self.root, first_id, "codex", "prior-task",
            host_id="host-1", cursor="prior-cursor", capability="prior-capability"
        )
        released = release_terminal_launch(
            self.root, first_id, host="codex", host_id="host-1", task_id="prior-task",
            cursor="prior-cursor", capability="prior-capability", terminal_state="FAILED",
            host_event_id="prior-terminal", host_event_cursor="prior-terminal-cursor"
        )
        contract = _contract(tasks=1)
        task = contract["tasks"][0]
        task["attempt"] = 2
        task["retry_of"] = released["event_id"]
        _rehash(contract)
        instruction_id = str(task["launch_instruction_id"])
        adapter = Adapter([[_event(instruction_id, "SUCCEEDED", "1")]])
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        prepared = next(
            event for event in binding_events(self.root)
            if event["launch_instruction_id"] == instruction_id and event["state"] == "PREPARED"
        )
        self.assertEqual(prepared["attempt"], 2)
        self.assertEqual(prepared["retry_of"], released["event_id"])


if __name__ == "__main__":
    unittest.main()
