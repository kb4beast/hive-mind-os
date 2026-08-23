from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402
from orchestration import (  # noqa: E402
    OrchestrationError,
    bind_launch,
    binding_events,
    build_orchestration_contract,
    infer_intent,
    prepare_launch,
    release_terminal_launch,
    should_publish_release,
    simple_prompt,
    validate_policy,
)

autopilot_parser = autopilot.parser
run_orchestration = autopilot.run_orchestration
select_orchestration_status = autopilot.select_orchestration_status


class FakePlane:
    def __init__(
        self,
        root: Path,
        status: Mapping[str, object],
        nodes: list[Mapping[str, Any]],
    ) -> None:
        self.repo_root = root
        self._status = dict(status)
        self._nodes = nodes
        self.dispatched_actors: list[str] = []

    def status(self) -> Mapping[str, object]:
        return self._status

    def observe_status(self) -> Mapping[str, object]:
        return self._status

    def dispatch(self, *, actor: str) -> None:
        self.dispatched_actors.append(actor)

    def nodes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._nodes)

    def render_worker_prompt(self, node_id: str) -> str:
        return f"canonical worker prompt for {node_id}"


class IntentOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / ".autopilot").mkdir()
        source = Path(__file__).resolve().parents[1] / "orchestration-policy.json"
        shutil.copy2(source, self.root / ".autopilot" / "orchestration-policy.json")
        shutil.copy2(
            Path(__file__).resolve().parents[1] / "task-bindings.lock",
            self.root / ".autopilot" / "task-bindings.lock",
        )
        self.nodes = [
            {
                "id": "ACTIVE-100",
                "branch": "autopilot/active-100",
                "pr_target": "release/test",
                "write_scope": ["src/active/**"],
                "critical_path_importance": 50,
                "downstream_unlock_value": 40,
            },
            {
                "id": "CLOSE-200",
                "branch": "autopilot/close-200",
                "pr_target": "release/test",
                "write_scope": ["src/close/**"],
                "critical_path_importance": 90,
                "downstream_unlock_value": 80,
            },
            {
                "id": "NEW-300",
                "branch": "autopilot/new-300",
                "pr_target": "release/test",
                "write_scope": ["src/new/**"],
                "critical_path_importance": 100,
                "downstream_unlock_value": 100,
            },
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def status(self, rows: list[dict[str, object]]) -> dict[str, object]:
        return {
            "plan_id": "portable-test",
            "plan_fingerprint": "sha256:test",
            "target_branch": "release/test",
            "target_sha": "a" * 40,
            "reconciliation_required": False,
            "eligible": [
                str(row["node_id"])
                for row in rows
                if row.get("state") == "READY"
            ],
            "ready": [],
            "dispatch_release": {
                "valid": False,
                "released_wave": [],
                "issues": ["no current dispatcher release"],
            },
            "nodes": rows,
            "complete": False,
            "active_claims": [],
            "active_validation_lease": None,
        }

    def test_explicit_and_implicit_intents(self) -> None:
        self.assertEqual(infer_intent("Finish everything to quiescence", {}).intent, "FINISH")
        self.assertEqual(infer_intent("Pick up where it stopped", {}).intent, "CONTINUE")
        self.assertEqual(infer_intent("What is left?", {}).intent, "CHECK")
        self.assertEqual(infer_intent("Kick off the next wave", {}).intent, "START")
        self.assertEqual(infer_intent("Build an autopilot DAG", None).intent, "BUILD_DAG")
        inferred = infer_intent(
            "Handle the rest",
            self.status([{"node_id": "ACTIVE-100", "state": "RUNNING"}]),
        )
        self.assertEqual(inferred.intent, "CONTINUE")
        self.assertFalse(inferred.explicit)

    def test_negation_advice_and_quoted_text_do_not_authorize_execution(self) -> None:
        cases = (
            "Don't start anything; just summarize the state.",
            "Do not continue this DAG.",
            "Check only; do not build or start anything.",
            "Do nothing.",
            "Don't make any changes.",
            "What would you do next?",
            "Why didn't it start?",
            "Explain how to finish the DAG",
            "How can I finish the DAG?",
            "Review how to start the next level",
            "Should we finish the DAG?",
            "Is it safe to start now?",
            "Could this continue without review?",
            'Explain the README sentence "keep going until done".',
        )
        for request in cases:
            with self.subTest(request=request):
                self.assertEqual(infer_intent(request, {}).intent, "CHECK")

    def test_closure_first_manages_active_recovery_and_read_only_preparation_in_parallel(self) -> None:
        status = self.status(
            [
                {"node_id": "ACTIVE-100", "state": "RUNNING", "reasons": []},
                {"node_id": "CLOSE-200", "state": "CI_FAILED", "reasons": ["CI failed"]},
                {"node_id": "NEW-300", "state": "READY", "reasons": []},
            ]
        )
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "Handle the rest", status=status)
        tasks = {str(item["node_id"]): item for item in contract["tasks"]}
        self.assertEqual(set(tasks), {"ACTIVE-100", "CLOSE-200", "NEW-300"})
        self.assertEqual(tasks["ACTIVE-100"]["action"], "RESUME")
        self.assertEqual(tasks["CLOSE-200"]["action"], "REPAIR_CI")
        self.assertEqual(tasks["NEW-300"]["action"], "PREPARE_READ_ONLY")
        self.assertEqual(tasks["NEW-300"]["authority_mode"], "PREPARATION_ONLY")
        self.assertFalse(tasks["NEW-300"]["may_claim_or_write"])
        self.assertEqual(contract["closure_target"], "CLOSE-200")
        self.assertTrue(
            contract["execution"]["closure_target_prioritizes_collection_not_task_creation"]
        )
        self.assertFalse(should_publish_release(infer_intent("finish", status), status))

    def test_released_parallel_wave_emits_durable_primary_tasks(self) -> None:
        rows = [
            {"node_id": "ACTIVE-100", "state": "READY", "reasons": []},
            {"node_id": "CLOSE-200", "state": "READY", "reasons": []},
        ]
        status = self.status(rows)
        status["dispatch_release"] = {
            "valid": True,
            "released_wave": ["ACTIVE-100", "CLOSE-200"],
            "directive": "START TOGETHER NOW",
        }
        status["ready"] = ["ACTIVE-100", "CLOSE-200"]
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "start", status=status)
        self.assertEqual(len(contract["tasks"]), 2)
        for task in contract["tasks"]:
            self.assertEqual(task["transport"], "durable_user_owned_task")
            self.assertEqual(task["host_adapters"]["codex"]["create"], "create_thread")
            self.assertIn("orchestration-policy.json", task["prompt"])
            self.assertRegex(task["launch_instruction_id"], r"^sha256:[0-9a-f]{64}$")
            self.assertIn(task["launch_instruction_id"][7:19], task["title"])
            self.assertEqual(task["target_branch"], "release/test")
            self.assertEqual(task["authority_mode"], "EXECUTION_AUTHORIZED")
            self.assertTrue(task["may_claim_or_write"])
        self.assertEqual(
            contract["execution"]["executor_module"],
            ".autopilot/bin/host_execution.py",
        )
        self.assertFalse(contract["execution"]["parent_final_while_required_tasks_active"])

    def test_existing_recovery_does_not_suppress_released_or_preparation_tasks(self) -> None:
        rows = [
            {"node_id": "ACTIVE-100", "state": "RUNNING", "reasons": []},
            {"node_id": "CLOSE-200", "state": "READY", "reasons": []},
            {"node_id": "NEW-300", "state": "READY", "reasons": []},
        ]
        status = self.status(rows)
        status["dispatch_release"] = {
            "valid": True,
            "released_wave": ["CLOSE-200"],
            "directive": "START NOW",
        }
        status["ready"] = ["CLOSE-200"]
        plane = FakePlane(self.root, status, self.nodes)

        contract = build_orchestration_contract(plane, "continue", status=status)
        tasks = {str(task["node_id"]): task for task in contract["tasks"]}

        self.assertEqual(set(tasks), {"ACTIVE-100", "CLOSE-200", "NEW-300"})
        self.assertEqual(tasks["ACTIVE-100"]["authority_mode"], "RECOVERY_AUTHORIZED")
        self.assertEqual(tasks["CLOSE-200"]["authority_mode"], "EXECUTION_AUTHORIZED")
        self.assertEqual(tasks["NEW-300"]["authority_mode"], "PREPARATION_ONLY")
        self.assertTrue(tasks["CLOSE-200"]["may_claim_or_write"])
        self.assertFalse(tasks["NEW-300"]["may_claim_or_write"])
        self.assertEqual(len({task["title"] for task in tasks.values()}), 3)
        self.assertEqual(contract["task_cohort"]["size"], 3)
        self.assertEqual(
            contract["task_cohort"]["authority_counts"],
            {
                "EXECUTION_AUTHORIZED": 1,
                "PREPARATION_ONLY": 1,
                "RECOVERY_AUTHORIZED": 1,
            },
        )
        self.assertTrue(contract["task_cohort"]["created_together_before_first_wait"])
        self.assertTrue(contract["task_cohort"]["every_task_polled_to_terminal"])
        for node_id, task in tasks.items():
            self.assertIn(node_id, task["title"])
            self.assertIn(str(task["action"]), task["title"])
            self.assertIn(str(task["authority_mode"]), task["title"])

    def test_launch_binding_is_append_only_and_consumed_before_create(self) -> None:
        rows = [{"node_id": "ACTIVE-100", "state": "READY", "reasons": []}]
        status = self.status(rows)
        status["dispatch_release"] = {
            "valid": True,
            "released_wave": ["ACTIVE-100"],
            "directive": "START NOW",
        }
        plane = FakePlane(self.root, status, self.nodes)
        first = build_orchestration_contract(plane, "start", status=status)
        instruction_id = first["tasks"][0]["launch_instruction_id"]
        prepared = prepare_launch(self.root, instruction_id, "codex")
        self.assertEqual(prepared["state"], "PREPARED")
        recovering = build_orchestration_contract(plane, "continue", status=status)
        self.assertEqual(recovering["tasks"][0]["action"], "RECOVER_PREPARED")
        bound = bind_launch(
            self.root,
            instruction_id,
            "codex",
            "thread-123",
            host_id="local",
            cursor="cursor-1",
            capability="capability-1",
        )
        self.assertEqual(bound["state"], "BOUND")
        running_status = self.status(
            [{"node_id": "ACTIVE-100", "state": "RUNNING", "reasons": []}]
        )
        resumed = build_orchestration_contract(
            plane, "continue", status=running_status
        )
        self.assertEqual(
            resumed["tasks"][0]["launch_instruction_id"], instruction_id
        )
        self.assertEqual(resumed["tasks"][0]["action"], "RESUME_BOUND")
        self.assertEqual(resumed["tasks"][0]["binding"]["task_id"], "thread-123")
        self.assertEqual([event["state"] for event in binding_events(self.root)], ["PREPARED", "CREATED", "BOUND"])
        released = release_terminal_launch(
            self.root,
            instruction_id,
            host="codex",
            host_id="local",
            task_id="thread-123",
            cursor="cursor-1",
            capability="capability-1",
            terminal_state="SUCCEEDED",
            host_event_id="terminal-123",
            host_event_cursor="terminal-cursor-123",
        )
        self.assertEqual(released["state"], "RELEASED")
        self.assertEqual(
            [event["state"] for event in binding_events(self.root)],
            ["PREPARED", "CREATED", "BOUND", "RELEASED"],
        )

    def test_release_launch_requires_terminal_evidence(self) -> None:
        instruction_id = "sha256:" + "2" * 64
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "thread-live",
            host_id="host", cursor="cursor", capability="capability"
        )
        with self.assertRaises(Exception):
            release_terminal_launch(
                self.root,
                instruction_id,
                host="codex",
                host_id="host",
                task_id="thread-live",
                cursor="cursor",
                capability="forged",
                terminal_state="SUCCEEDED",
                host_event_id="forged-terminal",
                host_event_cursor="forged-cursor",
            )
        self.assertEqual(binding_events(self.root)[-1]["state"], "BOUND")

    def test_raw_cli_cannot_assert_terminal_host_evidence(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                autopilot_parser().parse_args(
                    ["--repo-root", str(self.root), "record-launch-terminal"]
                )
            with self.assertRaises(SystemExit):
                autopilot_parser().parse_args(
                    ["--repo-root", str(self.root), "release-launch"]
                )

    def test_successful_release_is_an_idempotency_tombstone(self) -> None:
        instruction_id = "sha256:" + "5" * 64
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "thread-success",
            host_id="host", cursor="cursor", capability="capability"
        )
        released = release_terminal_launch(
            self.root,
            instruction_id,
            host="codex",
            host_id="host",
            task_id="thread-success",
            cursor="cursor",
            capability="capability",
            terminal_state="SUCCEEDED",
            host_event_id="success-terminal",
            host_event_cursor="success-cursor",
        )
        replay = prepare_launch(self.root, instruction_id, "codex")
        self.assertEqual(replay["event_id"], released["event_id"])
        self.assertEqual(len(binding_events(self.root)), 4)

    def test_failed_retry_requires_new_instruction_and_explicit_lineage(self) -> None:
        first_id = "sha256:" + "6" * 64
        prepare_launch(self.root, first_id, "codex")
        bind_launch(
            self.root, first_id, "codex", "thread-failed",
            host_id="host", cursor="cursor", capability="capability"
        )
        released = release_terminal_launch(
            self.root,
            first_id,
            host="codex",
            host_id="host",
            task_id="thread-failed",
            cursor="cursor",
            capability="capability",
            terminal_state="FAILED",
            host_event_id="failed-terminal",
            host_event_cursor="failed-cursor",
        )
        with self.assertRaises(OrchestrationError):
            prepare_launch(self.root, first_id, "codex")
        second_id = "sha256:" + "7" * 64
        retry = prepare_launch(
            self.root,
            second_id,
            "codex",
            attempt=2,
            retry_of=str(released["event_id"]),
        )
        self.assertEqual(retry["attempt"], 2)
        self.assertEqual(retry["retry_of"], released["event_id"])

    def test_contract_generates_attempt_specific_retry_lineage(self) -> None:
        rows = [{"node_id": "ACTIVE-100", "state": "READY", "reasons": []}]
        status = self.status(rows)
        status["dispatch_release"] = {"valid": True, "released_wave": ["ACTIVE-100"]}
        plane = FakePlane(self.root, status, self.nodes)
        first = build_orchestration_contract(plane, "start", status=status)["tasks"][0]
        prepare_launch(self.root, first["launch_instruction_id"], "codex")
        bind_launch(
            self.root, first["launch_instruction_id"], "codex", "thread-failed-contract",
            host_id="host", cursor="cursor", capability="capability"
        )
        released = release_terminal_launch(
            self.root,
            first["launch_instruction_id"],
            host="codex",
            host_id="host",
            task_id="thread-failed-contract",
            cursor="cursor",
            capability="capability",
            terminal_state="FAILED",
            host_event_id="contract-failed-terminal",
            host_event_cursor="contract-failed-cursor",
        )
        retry = build_orchestration_contract(plane, "start", status=status)["tasks"][0]
        self.assertNotEqual(first["launch_instruction_id"], retry["launch_instruction_id"])
        self.assertEqual(retry["attempt"], 2)
        self.assertEqual(retry["retry_of"], released["event_id"])
        prepared = prepare_launch(
            self.root,
            retry["launch_instruction_id"],
            "codex",
            attempt=retry["attempt"],
            retry_of=retry["retry_of"],
        )
        self.assertEqual(prepared["attempt"], 2)

    def test_binding_state_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside_name:
            state = self.root / ".autopilot" / "state"
            try:
                os.symlink(outside_name, state, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with self.assertRaises(OrchestrationError):
                prepare_launch(self.root, "sha256:" + "8" * 64, "codex")

    def test_prepared_launch_cannot_be_taken_over_by_another_host(self) -> None:
        instruction_id = "sha256:" + "4" * 64
        prepare_launch(self.root, instruction_id, "codex")
        with self.assertRaises(Exception):
            bind_launch(
                self.root, instruction_id, "other-host", "foreign-task",
                capability="foreign-capability"
            )

    def test_concurrent_prepare_launch_is_idempotent_and_hash_chained(self) -> None:
        instruction_id = "sha256:" + "3" * 64
        with ThreadPoolExecutor(max_workers=12) as executor:
            results = list(
                executor.map(
                    lambda _: prepare_launch(self.root, instruction_id, "codex"),
                    range(12),
                )
            )
        self.assertEqual({item["event_id"] for item in results}, {results[0]["event_id"]})
        self.assertEqual(len(binding_events(self.root)), 1)

    def test_first_binding_read_requires_the_preexisting_os_lock(self) -> None:
        (self.root / ".autopilot" / "task-bindings.lock").unlink()
        with self.assertRaises(Exception):
            binding_events(self.root)

    def test_implicit_completed_check_never_calls_mutating_status(self) -> None:
        completed = self.status([{"node_id": "ACTIVE-100", "state": "COMPLETE"}])
        completed["complete"] = True

        class StatusProbe:
            def __init__(self) -> None:
                self.status_calls = 0

            def observe_status(self):
                return completed

            def status(self):
                self.status_calls += 1
                return completed

        for request in ("", "What happened?"):
            probe = StatusProbe()
            _, decision = select_orchestration_status(probe, request)
            self.assertEqual(decision.intent, "CHECK")
            self.assertEqual(probe.status_calls, 0)

    def test_bound_host_task_prevents_false_quiescence(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "COMPLETE"}])
        status["complete"] = True
        plane = FakePlane(self.root, status, self.nodes)
        instruction_id = "sha256:" + "1" * 64
        prepare_launch(self.root, instruction_id, "codex")
        bind_launch(
            self.root, instruction_id, "codex", "thread-live",
            capability="capability"
        )
        contract = build_orchestration_contract(plane, "check", status=status)
        self.assertEqual(contract["outcome"], "ACTIVE")
        self.assertFalse(contract["quiescent"])

    def test_active_validation_lease_prevents_false_quiescence(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "COMPLETE"}])
        status["complete"] = True
        status["active_validation_lease"] = {
            "node_id": "ACTIVE-100",
            "owner": "curator:fixture",
            "expires_at": "2030-01-01T00:00:00Z",
        }
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "check", status=status)
        self.assertEqual(contract["outcome"], "ACTIVE")
        self.assertFalse(contract["successful"])
        self.assertFalse(contract["quiescent"])

    def test_launch_identity_is_repository_scoped(self) -> None:
        rows = [{"node_id": "ACTIVE-100", "state": "READY", "reasons": []}]
        status = self.status(rows)
        status["dispatch_release"] = {"valid": True, "released_wave": ["ACTIVE-100"]}
        first = FakePlane(self.root, status, self.nodes)
        first.control = {"target": {"repository": "acme/one"}}
        other_root = self.root / "other"
        (other_root / ".autopilot").mkdir(parents=True)
        shutil.copy2(
            self.root / ".autopilot" / "orchestration-policy.json",
            other_root / ".autopilot" / "orchestration-policy.json",
        )
        shutil.copy2(
            self.root / ".autopilot" / "task-bindings.lock",
            other_root / ".autopilot" / "task-bindings.lock",
        )
        second = FakePlane(other_root, status, self.nodes)
        second.control = {"target": {"repository": "acme/two"}}
        first_id = build_orchestration_contract(first, "start", status=status)["tasks"][0]["launch_instruction_id"]
        second_id = build_orchestration_contract(second, "start", status=status)["tasks"][0]["launch_instruction_id"]
        self.assertNotEqual(first_id, second_id)

    def test_check_is_read_only_even_when_work_is_ready(self) -> None:
        status = self.status([{"node_id": "NEW-300", "state": "READY"}])
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "check status", status=status)
        self.assertEqual(contract["tasks"], [])
        self.assertFalse(contract["dispatch_required"])

    def test_orchestration_marks_an_ineligible_apply_request_withheld(self) -> None:
        status = self.status([{"node_id": "NEW-300", "state": "BLOCKED"}])
        status["reconciliation_required"] = True
        plane = FakePlane(self.root, status, self.nodes)

        result = run_orchestration(
            plane,
            "continue the existing work",
            actor="test:continuation",
            apply=True,
        )

        self.assertEqual(
            result["release_publication"],
            {"requested": True, "published": False, "outcome": "WITHHELD"},
        )
        self.assertEqual(plane.dispatched_actors, [])

    def test_orchestration_marks_a_dispatched_apply_request_published(self) -> None:
        status = self.status([{"node_id": "NEW-300", "state": "READY"}])
        plane = FakePlane(self.root, status, self.nodes)

        result = run_orchestration(
            plane,
            "continue the existing work",
            actor="test:continuation",
            apply=True,
        )

        self.assertEqual(
            result["release_publication"],
            {"requested": True, "published": True, "outcome": "PUBLISHED"},
        )
        self.assertEqual(plane.dispatched_actors, ["test:continuation"])

    def test_adverse_settled_state_is_quiescent_but_not_success(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "QUARANTINED"}])
        status["complete"] = True
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "finish", status=status)
        self.assertTrue(contract["quiescent"])
        self.assertEqual(contract["outcome"], "BLOCKED")
        self.assertFalse(contract["successful"])

    def test_nonterminal_blocker_is_not_quiescent(self) -> None:
        status = self.status([{"node_id": "ACTIVE-100", "state": "BLOCKED"}])
        plane = FakePlane(self.root, status, self.nodes)
        contract = build_orchestration_contract(plane, "finish", status=status)
        self.assertEqual(contract["outcome"], "BLOCKED")
        self.assertFalse(contract["quiescent"])

    def test_policy_and_simple_prompt_encode_required_behavior(self) -> None:
        policy = json.loads(
            (self.root / ".autopilot" / "orchestration-policy.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(validate_policy(policy), ())
        policy["task_transport"]["nested_primary_forbidden"] = False
        self.assertTrue(validate_policy(policy))
        prompt = simple_prompt()
        self.assertIn("Infer whether I mean", prompt)
        self.assertIn("quiescent", prompt)

    def test_policy_validation_rejects_disabled_execution_invariants(self) -> None:
        source = json.loads(
            (self.root / ".autopilot" / "orchestration-policy.json").read_text(
                encoding="utf-8"
            )
        )
        mutations = (
            ("polling", "poll_until_terminal", False),
            ("polling", "answer_questions_then_resume", False),
            ("recovery", "resume_same_task_after_fix", False),
            ("recovery", "blocker_is_completion", True),
            ("wave", "never_start_next_level_before_required_current_cohort_quiescence", False),
            ("task_transport", "record_task_id", False),
            (
                "parallel_task_cohort",
                "create_released_tasks_even_when_recovery_tasks_exist",
                False,
            ),
            ("parallel_task_cohort", "create_eligible_preparation_tasks", False),
            ("parallel_task_cohort", "create_entire_cohort_before_first_wait", False),
            ("parallel_task_cohort", "poll_every_created_task_to_terminal", False),
            (
                "parallel_task_cohort",
                "closure_target_prioritizes_collection_not_creation",
                False,
            ),
        )
        for section, key, value in mutations:
            with self.subTest(section=section, key=key):
                candidate = copy.deepcopy(source)
                candidate[section][key] = value
                self.assertTrue(validate_policy(candidate))


if __name__ == "__main__":
    unittest.main()
