from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
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
    SIDECAR_ACK_KIND,
    SIDECAR_CREATE_KIND,
    SIDECAR_EVENT_KIND,
    SIDECAR_RESULT_KIND,
    HostExecutionError,
    execute_contract,
)
from orchestration import (  # noqa: E402
    bind_launch,
    binding_events,
    prepare_launch,
    release_terminal_launch,
)
from sidecar_execution import (  # noqa: E402
    active_sidecars,
    make_descendant_spec,
    plan_sidecars,
    sidecar_events,
    sidecar_spec_digest,
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


def _sidecar_contract() -> dict[str, Any]:
    contract = _contract(tasks=1)
    policy = json.loads((Path(__file__).resolve().parents[1] / "orchestration-policy.json").read_text(encoding="utf-8"))["sidecars"]
    node = {"risk": "high", "read_scope": ["a", "b", "c"], "evidence_requirements": ["x"]}
    sidecars = list(plan_sidecars(contract["tasks"], {"NODE-0": node}, policy))
    contract["tasks"][0]["sidecars"] = sidecars
    contract["sidecar_cohort"] = {
        "size": len(sidecars),
        "sidecar_ids": [item["sidecar_id"] for item in sidecars],
        "planned_token_budget": sum(item["token_budget"] for item in sidecars),
        "estimated_net_savings_tokens": sum(item["estimated_net_savings_tokens"] for item in sidecars),
        "root_mediated": True,
        "all_parents_require_terminal_ack": True,
        "policy": policy,
    }
    return _rehash(contract)


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
        self.wait_target_counts: list[int] = []
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
        self.wait_target_counts.append(len(targets))
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


class SidecarAdapter(Adapter):
    def __init__(self, script: Sequence[Mapping[str, object]]) -> None:
        super().__init__([])
        self.activity_script = list(script)
        self.sidecar_bindings: dict[str, dict[str, str]] = {}
        self.sidecar_spawned: list[str] = []
        self.sidecar_messages: list[str] = []
        self.sidecar_closed: list[str] = []

    def lookup_sidecar(self, *, idempotency_key: str) -> Mapping[str, object] | None:
        binding = self.sidecar_bindings.get(idempotency_key)
        if binding is None:
            return None
        parent = next(task for task in self.contract["tasks"] if any(item["sidecar_id"] == idempotency_key for item in task.get("sidecars", [])))
        return {"kind": SIDECAR_CREATE_KIND, **binding, "idempotency_key": idempotency_key, "parent_launch_instruction_id": parent["launch_instruction_id"]}

    def spawn_sidecar(self, *, prompt: str, token_budget: int, idempotency_key: str, parent_launch_instruction_id: str) -> Mapping[str, object]:
        del prompt, token_budget
        existing = self.sidecar_bindings.get(idempotency_key)
        if existing is None:
            index = len(self.sidecar_bindings)
            existing = {"host_id": "host-1", "sidecar_task_id": f"sidecar-{index}", "cursor": f"sidecar-cursor-{index}", "capability": f"sidecar-capability-{index}"}
            self.sidecar_bindings[idempotency_key] = existing
            self.sidecar_spawned.append(idempotency_key)
        return {"kind": SIDECAR_CREATE_KIND, **existing, "idempotency_key": idempotency_key, "parent_launch_instruction_id": parent_launch_instruction_id}

    def wait_activity(self, primary_targets: Sequence[Mapping[str, object]], sidecar_targets: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
        del primary_targets, sidecar_targets
        if not self.activity_script:
            return {"primary_events": [], "sidecar_events": []}
        batch = dict(self.activity_script.pop(0))
        primary = []
        for event in batch.get("primary_events", []):
            material = dict(event)
            instruction_id = str(material.pop("instruction_id"))
            material.update(self.bindings[instruction_id])
            primary.append(material)
        sidecars = []
        for event in batch.get("sidecar_events", []):
            material = dict(event)
            sidecar_id = str(material["sidecar_id"])
            material.update(self.sidecar_bindings[sidecar_id])
            sidecars.append(material)
        return {"primary_events": primary, "sidecar_events": sidecars}

    def send_message_to_sidecar(self, *, host_id: str, sidecar_task_id: str, cursor: str, capability: str, message: str, idempotency_key: str) -> Mapping[str, object]:
        self.sidecar_messages.append(message)
        return {"kind": SIDECAR_ACK_KIND, "host_id": host_id, "sidecar_task_id": sidecar_task_id, "cursor": cursor, "capability": capability, "accepted": True, "message_id": f"sidecar-message-{len(self.sidecar_messages)}", "idempotency_key": idempotency_key}

    def close_sidecar(self, *, host_id: str, sidecar_task_id: str, cursor: str, capability: str, reason: str, idempotency_key: str) -> Mapping[str, object]:
        del reason, idempotency_key
        sidecar_id = next(key for key, value in self.sidecar_bindings.items() if value["sidecar_task_id"] == sidecar_task_id)
        self.sidecar_closed.append(sidecar_id)
        spec = next(item for task in self.contract["tasks"] for item in task.get("sidecars", []) if item["sidecar_id"] == sidecar_id)
        return {"kind": SIDECAR_EVENT_KIND, "host_id": host_id, "sidecar_task_id": sidecar_task_id, "cursor": cursor, "capability": capability, "sidecar_id": sidecar_id, "state": "CANCELLED", "event_id": f"close-{sidecar_id[-8:]}", "event_cursor": "closed", "result": _sidecar_result(spec, "CANCELLED")}


def _event(instruction_id: str, state: str, cursor: str, **extra: object) -> dict[str, object]:
    return {
        "kind": EVENT_KIND,
        "instruction_id": instruction_id,
        "state": state,
        "event_id": f"event-{instruction_id[-8:]}-{cursor}",
        "event_cursor": cursor,
        **extra,
    }


def _sidecar_result(spec: Mapping[str, object], status: str = "SUCCEEDED", usage: int = 100) -> dict[str, object]:
    return {"kind": SIDECAR_RESULT_KIND, "sidecar_id": spec["sidecar_id"], "parent_launch_instruction_id": spec["parent_launch_instruction_id"], "spec_digest": sidecar_spec_digest(spec), "status": status, "summary": "bounded result", "findings": [], "evidence_refs": ["tests"], "blocker": None, "token_usage": usage}


def _sidecar_event(spec: Mapping[str, object], state: str, cursor: str, **extra: object) -> dict[str, object]:
    return {"kind": SIDECAR_EVENT_KIND, "sidecar_id": spec["sidecar_id"], "state": state, "event_id": f"sidecar-event-{spec['sidecar_id'][-8:]}-{cursor}", "event_cursor": cursor, **extra}


class HostExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".autopilot").mkdir()
        source = Path(__file__).resolve().parents[1]
        shutil.copy2(source / "task-bindings.lock", self.root / ".autopilot" / "task-bindings.lock")
        shutil.copy2(source / "sidecar-bindings.lock", self.root / ".autopilot" / "sidecar-bindings.lock")
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

    def test_nine_primary_targets_are_fairly_split_at_host_limit(self) -> None:
        contract = _contract(tasks=9)
        ids = [str(task["launch_instruction_id"]) for task in contract["tasks"]]
        adapter = Adapter([
            [_event(item, "SUCCEEDED", "1") for item in ids[:8]],
            [_event(ids[8], "SUCCEEDED", "1")],
        ])
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(adapter.wait_target_counts, [8, 1])

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

    def test_sidecars_are_spawned_once_settle_and_notify_primary_before_success(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        specs = contract["tasks"][0]["sidecars"]
        adapter = SidecarAdapter([
            {
                "primary_events": [_event(instruction_id, "SUCCEEDED", "1")],
                "sidecar_events": [
                    _sidecar_event(spec, "SUCCEEDED", "1", result=_sidecar_result(spec))
                    for spec in specs
                ],
            }
        ])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertTrue(result["quiescent"])
        self.assertEqual(set(adapter.sidecar_spawned), {item["sidecar_id"] for item in specs})
        self.assertEqual(set(result["sidecar_terminal"].values()), {"SUCCEEDED"})
        self.assertGreaterEqual(len(adapter.messages), len(specs) * 2)
        self.assertEqual(active_sidecars(self.root), ())

    def test_primary_terminal_closes_unfinished_sidecars_and_parent_is_notified(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        adapter = SidecarAdapter([{"primary_events": [_event(instruction_id, "SUCCEEDED", "1")], "sidecar_events": []}])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(set(adapter.sidecar_closed), {item["sidecar_id"] for item in contract["tasks"][0]["sidecars"]})
        self.assertEqual(set(result["sidecar_terminal"].values()), {"CANCELLED"})
        self.assertEqual(active_sidecars(self.root), ())

    def test_sidecar_binding_is_adopted_after_parent_restart(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        specs = contract["tasks"][0]["sidecars"]
        adapter = SidecarAdapter([])
        adapter.contract = contract
        for spec in specs:
            adapter.spawn_sidecar(prompt=str(spec["prompt"]), token_budget=int(spec["token_budget"]), idempotency_key=str(spec["sidecar_id"]), parent_launch_instruction_id=instruction_id)
        adapter.sidecar_spawned.clear()
        adapter.activity_script = [{"primary_events": [_event(instruction_id, "SUCCEEDED", "1")], "sidecar_events": []}]
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(adapter.sidecar_spawned, [])

    def test_over_budget_sidecar_terminal_is_rejected(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        spec = contract["tasks"][0]["sidecars"][0]
        contract["tasks"][0]["sidecars"] = [spec]
        contract["sidecar_cohort"].update({"size": 1, "sidecar_ids": [spec["sidecar_id"]], "planned_token_budget": spec["token_budget"], "estimated_net_savings_tokens": spec["estimated_net_savings_tokens"]})
        _rehash(contract)
        adapter = SidecarAdapter([{"primary_events": [_event(instruction_id, "SUCCEEDED", "1")], "sidecar_events": [_sidecar_event(spec, "SUCCEEDED", "1", result=_sidecar_result(spec, usage=int(spec["token_budget"]) + 1))]}])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(result["sidecar_terminal"][spec["sidecar_id"]], "FAILED")
        self.assertEqual(active_sidecars(self.root), ())

    def test_sidecar_may_request_but_only_root_spawns_a_budgeted_descendant(self) -> None:
        contract = _sidecar_contract()
        instruction_id = str(contract["tasks"][0]["launch_instruction_id"])
        parent = contract["tasks"][0]["sidecars"][0]
        request = {"purpose": "independent_review", "prompt": "Inspect receipt:child independently", "evidence_refs": ["receipt:child"]}
        child = make_descendant_spec(parent, request, contract["sidecar_cohort"]["policy"])
        other = contract["tasks"][0]["sidecars"][1:]
        adapter = SidecarAdapter([
            {"primary_events": [_event(instruction_id, "ACTIVE", "1")], "sidecar_events": [_sidecar_event(parent, "SPAWN_REQUEST", "1", request=request)]},
            {
                "primary_events": [_event(instruction_id, "SUCCEEDED", "2")],
                "sidecar_events": [
                    _sidecar_event(child, "SUCCEEDED", "1", result=_sidecar_result(child)),
                    _sidecar_event(parent, "SUCCEEDED", "2", result=_sidecar_result(parent)),
                    *[_sidecar_event(spec, "SUCCEEDED", "1", result=_sidecar_result(spec)) for spec in other],
                ],
            },
        ])
        adapter.contract = contract
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertTrue(result["successful"])
        self.assertEqual(result["sidecar_terminal"][child["sidecar_id"]], "SUCCEEDED")
        self.assertIn(child["sidecar_id"], adapter.sidecar_spawned)
        self.assertTrue(any("ADMITTED" in message for message in adapter.sidecar_messages))

    def test_sidecar_ledger_corruption_fails_closed(self) -> None:
        path = self.root / ".autopilot" / "state" / "sidecar-bindings.jsonl"
        path.parent.mkdir()
        path.write_text('{"broken":', encoding="utf-8")
        with self.assertRaisesRegex(Exception, "sidecar ledger line 1 is invalid"):
            sidecar_events(self.root)

    def test_blocking_combined_wait_times_out_and_settles_every_sidecar(self) -> None:
        contract = _sidecar_contract()
        contract["sidecar_cohort"]["policy"]["wait_timeout_seconds"] = 1
        _rehash(contract)
        adapter = SidecarAdapter([])
        adapter.contract = contract

        def blocked_wait(primary_targets, sidecar_targets):
            del primary_targets, sidecar_targets
            time.sleep(2)
            return {"primary_events": [], "sidecar_events": []}

        adapter.wait_activity = blocked_wait  # type: ignore[method-assign]
        started = time.monotonic()
        result = execute_contract(self.root, contract, adapter, Resolver())
        self.assertLess(time.monotonic() - started, 1.8)
        self.assertEqual(result["blocker"]["code"], "SIDECAR_WAIT_TIMEOUT")
        self.assertEqual(active_sidecars(self.root), ())


if __name__ == "__main__":
    unittest.main()
