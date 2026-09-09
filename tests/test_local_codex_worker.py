from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from hive_mind_os.local_codex_worker import (
    CodexLocalWorker,
    _run_codex_process,
    resolve_codex_executable,
)


def report_document() -> dict:
    return {
        "status": "completed", "summary": "Inspected the selected implementation and tests.",
        "findings": ["The existing behavior is reproducible in tests/test_example.py."],
        "acceptance_evidence": ["Read tests/test_example.py:42 and src/example.py:12."],
        "ideas": [{
            "idea_id": "idea-1", "title": "Retain reproducible evidence",
            "hypothesis": "Recording a real command makes the outcome independently checkable.",
            "source": "src/example.py:12", "disposition": "adapt",
            "reason": "The source supports a bounded improvement with a measurable outcome.",
            "next_action": "Add an independent reproduction.",
            "return_to_agent": "curator-1", "parent_idea_id": None,
        }],
        "selected_idea_ids": ["idea-1"], "changed_paths": [], "tests": [],
    }


class FakeRunner:
    def __init__(self) -> None:
        self.report = report_document()
        self.events = [
            {"type": "thread.started", "thread_id": "fresh-codex-thread-123"},
            {"type": "turn.started"}, {"type": "turn.completed", "usage": {}},
        ]
        self.calls: list[tuple[list[str], dict]] = []
        self.exit_code = 0
        self.raw_response: str | None = None
        self.raw_transcript: str | None = None

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        kwargs["stdout_path"].write_text(
            self.raw_transcript if self.raw_transcript is not None else
            "\n".join(json.dumps(event) for event in self.events), encoding="utf-8",
        )
        kwargs["stderr_path"].write_text("", encoding="utf-8")
        response = Path(command[command.index("--output-last-message") + 1])
        response.write_text(
            self.raw_response if self.raw_response is not None else json.dumps(self.report),
            encoding="utf-8",
        )
        return self.exit_code


class CodexLocalWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "isolated subject with spaces"
        self.workspace.mkdir()
        self.runner = FakeRunner()
        self.worker = CodexLocalWorker(executable=sys.executable, command_runner=self.runner)
        self.args = {
            "node": {"node_id": "discover-1", "purpose": "Inspect a bounded improvement"},
            "actor_id": "explorer-1", "role": "Explorer", "workspace": self.workspace,
            "evidence_directory": self.root / "evidence", "predecessor_reports": [],
            "objective": "Improve the subject using evidence", "timeout_seconds": 20,
        }

    def run_worker(self, **updates):
        return self.worker.run(**(self.args | updates))

    def test_real_transport_arguments_stdin_identity_and_receipt_hashes(self) -> None:
        outcome = self.run_worker(objective="A large objective " + "x" * 40_000)
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["session_id"], "fresh-codex-thread-123")
        self.assertEqual(outcome["node_id"], "discover-1")
        self.assertEqual(outcome["report"], self.runner.report)
        command, options = self.runner.calls[0]
        self.assertEqual(command[-1], "-")
        self.assertEqual(command[1:3], ["exec", "--json"])
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertEqual(command[command.index("--config") + 1], 'approval_policy="never"')
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertNotIn("--model", command)
        self.assertNotIn("--skip-git-repo-check", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertLess(len(" ".join(command)), 4000)
        self.assertGreater(len(options["prompt"]), 40_000)
        self.assertEqual(options["cwd"], self.workspace.resolve())
        self.assertEqual(options["timeout_seconds"], 20)
        for name in ("prompt", "schema", "stdout", "stderr", "response"):
            evidence = outcome["evidence"][name]
            self.assertEqual(evidence["sha256"], hashlib.sha256(Path(evidence["path"]).read_bytes()).hexdigest())
        self.assertEqual(json.loads((self.root / "evidence" / "receipt.json").read_text()), outcome)

    def test_subscription_environment_removes_inherited_api_tokens(self) -> None:
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "test-only-api-key", "GITHUB_TOKEN": "test-only-token",
            "OTHER_ACCESS_KEY": "test-only-key", "CODEX_HOME": "subscription-profile",
        }):
            self.run_worker()
        environment = self.runner.calls[0][1]["environment"]
        for key in ("OPENAI_API_KEY", "GITHUB_TOKEN", "OTHER_ACCESS_KEY"):
            self.assertNotIn(key, environment)
        self.assertEqual(environment["CODEX_HOME"], "subscription-profile")

    def test_explicit_builder_can_write_but_other_roles_cannot(self) -> None:
        with self.assertRaisesRegex(ValueError, "Only.*Builder"):
            self.run_worker(writable=True)
        self.runner.report["changed_paths"] = ["src/example.py"]
        outcome = self.run_worker(role="Builder", writable=True)
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["sandbox"], "workspace-write")

    def test_fresh_worker_omits_app_pipe_but_preserves_security_review_context(self) -> None:
        context = {
            "CODEX_APP_TOOLS_PIPE_PATH": "test-only-parent-pipe",
            "CODEX_SESSION_ID": "parent-session", "CODEX_THREAD_ID": "parent-thread",
            "CODEX_PERMISSION_PROFILE": "preserve-parent-profile",
            "CODEX_SANDBOX_NETWORK_DISABLED": "1", "APPROVAL_POLICY": "never",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "preserve-originator",
        }
        with patch.dict(os.environ, context):
            outcome = self.run_worker()
        environment = self.runner.calls[0][1]["environment"]
        for key in ("CODEX_APP_TOOLS_PIPE_PATH",):
            self.assertNotIn(key, environment)
            self.assertIn(key, outcome["excluded_parent_context_variables"])
        for key in ("CODEX_PERMISSION_PROFILE", "CODEX_SANDBOX_NETWORK_DISABLED",
                    "APPROVAL_POLICY", "CODEX_INTERNAL_ORIGINATOR_OVERRIDE",
                    "CODEX_SESSION_ID", "CODEX_THREAD_ID"):
            self.assertEqual(environment[key], context[key])

    def test_read_only_worker_cannot_claim_edits(self) -> None:
        self.runner.report["changed_paths"] = ["src/example.py"]
        outcome = self.run_worker()
        self.assertEqual(outcome["status"], "failed")
        self.assertIn("read-only", outcome["reason"])

    def test_builder_paths_cannot_escape_workspace(self) -> None:
        for index, path in enumerate(("../outside", r"C:\outside.py", "/outside.py", r"..\outside.py", "C:outside.py")):
            with self.subTest(path=path):
                self.runner.report["changed_paths"] = [path]
                outcome = self.run_worker(
                    role="Builder", writable=True, evidence_directory=self.root / f"case-{index}",
                )
                self.assertEqual(outcome["status"], "failed")

    def test_explicit_blocker_is_preserved(self) -> None:
        self.runner.report["status"] = "blocked"
        self.runner.report["summary"] = "The sandbox does not allow the required test command."
        self.runner.report["acceptance_evidence"] = []
        outcome = self.run_worker()
        self.assertEqual(outcome["status"], "blocked")
        self.assertEqual(outcome["reason"], self.runner.report["summary"])
        self.assertEqual(len(self.runner.calls), 1)

    def test_nonzero_exit_cannot_become_success_from_report(self) -> None:
        self.runner.exit_code = 17
        outcome = self.run_worker()
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(outcome["exit_code"], 17)
        self.assertEqual(outcome["session_id"], "fresh-codex-thread-123")
        self.assertIsNone(outcome["report"])

    def test_recovered_stream_error_does_not_invalidate_a_completed_turn(self) -> None:
        self.runner.events.insert(1, {"type": "error", "message": "Reconnecting 1/5"})
        self.assertEqual(self.run_worker()["status"], "completed")

    def test_actual_provider_usage_is_preserved_and_missing_usage_is_null(self) -> None:
        usage = {"input_tokens": 120, "output_tokens": 18, "cached_input_tokens": 40}
        self.runner.events[-1]["usage"] = usage
        self.assertEqual(self.run_worker()["usage"], usage)
        self.runner.events[-1].pop("usage")
        outcome = self.run_worker(evidence_directory=self.root / "missing-usage")
        self.assertIsNone(outcome["usage"])

    def test_missing_cli_is_typed_blocker_with_evidence(self) -> None:
        self.worker.executable = self.root / "unavailable.exe"
        outcome = self.run_worker()
        self.assertEqual(outcome["status"], "blocked")
        self.assertIn("unavailable", outcome["reason"])
        self.assertTrue((self.root / "evidence" / "receipt.json").is_file())
        self.assertEqual(self.runner.calls, [])

    def test_missing_or_conflicting_session_or_completion_fails(self) -> None:
        cases = [
            [{"type": "turn.completed"}],
            [{"type": "thread.started", "thread_id": "one"}],
            [{"type": "thread.started", "thread_id": "one"},
             {"type": "thread.started", "thread_id": "two"}, {"type": "turn.completed"}],
            [{"type": "thread.started", "thread_id": "one"}, {"type": "turn.failed"}],
        ]
        for index, events in enumerate(cases):
            with self.subTest(events=events):
                self.runner.events = events
                outcome = self.run_worker(evidence_directory=self.root / f"case-{index}")
                self.assertEqual(outcome["status"], "failed")
                self.assertIsNone(outcome["report"])

    def test_malformed_and_duplicate_json_are_rejected(self) -> None:
        for index, raw in enumerate(("not-json", '{"status":"completed","status":"blocked"}')):
            with self.subTest(raw=raw):
                self.runner.raw_response = raw
                outcome = self.run_worker(evidence_directory=self.root / f"case-{index}")
                self.assertEqual(outcome["status"], "failed")
        self.runner.raw_response = None
        self.runner.raw_transcript = "not-json"
        self.assertEqual(self.run_worker()["status"], "failed")

    def test_report_requires_substantive_fields_and_evidence(self) -> None:
        mutations = [
            lambda report: report.update(summary=" "),
            lambda report: report.update(acceptance_evidence=[]),
            lambda report: report.update(invented_field=True),
            lambda report: report["ideas"][0].update(reason=""),
            lambda report: report["ideas"].append(copy.deepcopy(report["ideas"][0])),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.runner.report = report_document()
                mutate(self.runner.report)
                outcome = self.run_worker(evidence_directory=self.root / f"case-{index}")
                self.assertEqual(outcome["status"], "failed")

    def test_timeout_is_failure_with_no_sandbox_retry(self) -> None:
        calls = []
        def timeout(command, **kwargs):
            calls.append(command)
            raise subprocess.TimeoutExpired(command, kwargs["timeout_seconds"])
        self.worker.command_runner = timeout
        outcome = self.run_worker()
        self.assertEqual(outcome["status"], "failed")
        self.assertIn("deadline", outcome["reason"])
        self.assertEqual(len(calls), 1)

    def test_previous_attempt_evidence_is_never_overwritten(self) -> None:
        self.run_worker()
        before = (self.root / "evidence" / "receipt.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_worker()
        self.assertEqual((self.root / "evidence" / "receipt.json").read_bytes(), before)

    def test_source_packet_is_preserved_and_tools_are_prohibited_in_prompt(self) -> None:
        packet = {"commit": "pinned-commit", "sources": [{"path": "src/example.py", "text": "pass\n"}]}
        self.runner.report["proposed_patch"] = None
        outcome = self.run_worker(source_packet=packet)
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["execution_mode"], "source-packet")
        evidence = outcome["evidence"]["source_packet"]
        self.assertEqual(json.loads(Path(evidence["path"]).read_text()), packet)
        self.assertEqual(evidence["sha256"], hashlib.sha256(Path(evidence["path"]).read_bytes()).hexdigest())
        prompt = self.runner.calls[0][1]["prompt"].decode()
        self.assertIn("Do not invoke any tools, commands", prompt)
        self.assertIn("You did not run those commands yourself", prompt)
        self.assertNotIn("Use actual repository reads", prompt)

    def test_packet_builder_proposes_patch_while_cli_remains_read_only(self) -> None:
        self.runner.report["proposed_patch"] = "diff --git a/src/example.py b/src/example.py\n"
        self.runner.report["changed_paths"] = ["src/example.py"]
        outcome = self.run_worker(role="Builder", writable=True, source_packet={"sources": []})
        self.assertEqual(outcome["status"], "completed")
        self.assertEqual(outcome["sandbox"], "read-only")
        command, options = self.runner.calls[0]
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("PROPOSED paths", options["prompt"].decode())
        self.assertIn("you cannot apply it", options["prompt"].decode())

    def test_packet_patch_requires_builder_authority_and_nonempty_patch(self) -> None:
        for index, patch_text in enumerate(("some patch", "")):
            with self.subTest(patch_text=patch_text):
                self.runner.report["proposed_patch"] = patch_text
                outcome = self.run_worker(source_packet={}, evidence_directory=self.root / f"case-{index}")
                self.assertEqual(outcome["status"], "failed")
        self.runner.report["proposed_patch"] = None
        self.runner.report["changed_paths"] = ["src/example.py"]
        outcome = self.run_worker(role="Builder", writable=True, source_packet={})
        self.assertEqual(outcome["status"], "failed")

    def test_packet_model_tool_events_are_rejected(self) -> None:
        self.runner.report["proposed_patch"] = None
        self.runner.events.insert(1, {
            "type": "item.started", "item": {"type": "command_execution", "command": "git status"},
        })
        outcome = self.run_worker(source_packet={})
        self.assertEqual(outcome["status"], "failed")
        self.assertIn("tool operation", outcome["reason"])
        self.assertEqual(outcome["session_id"], "fresh-codex-thread-123")

    def test_timeout_must_be_bounded(self) -> None:
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                self.run_worker(timeout_seconds=timeout)

    def test_native_process_records_pid_and_kills_tree_on_timeout(self) -> None:
        process = MagicMock()
        process.pid = 123
        process.communicate.side_effect = subprocess.TimeoutExpired([sys.executable], 1)
        with patch("hive_mind_os.local_codex_worker.subprocess.Popen", return_value=process) as popen:
            with patch("hive_mind_os.local_codex_worker._kill_process_tree") as kill_tree:
                with self.assertRaises(subprocess.TimeoutExpired):
                    _run_codex_process(
                        [sys.executable], cwd=self.workspace, environment={}, prompt=b"task",
                        stdout_path=self.root / "stdout.jsonl", stderr_path=self.root / "stderr.txt",
                        timeout_seconds=1,
                    )
        kill_tree.assert_called_once_with(process)
        self.assertFalse(popen.call_args.kwargs["shell"])
        if os.name != "nt":
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
        record = json.loads((self.root / "process.json").read_text())
        self.assertEqual(record["pid"], 123)
        self.assertEqual(len(record["command_digest"]), 64)
        self.assertTrue(record["started_at"])

    @unittest.skipUnless(os.name == "nt", "Windows wrappers need native resolution")
    def test_windows_explicit_shell_wrapper_is_rejected(self) -> None:
        wrapper = self.root / "codex.cmd"
        wrapper.write_text("@echo off")
        with self.assertRaisesRegex(ValueError, "native"):
            resolve_codex_executable(wrapper)

    @unittest.skipUnless(os.name == "nt", "Windows npm layout")
    def test_windows_npm_wrapper_resolves_adjacent_native_installation(self) -> None:
        wrapper = self.root / "codex.cmd"
        wrapper.write_text("do not execute this wrapper")
        native = self.root / "node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/codex/codex.exe"
        native.parent.mkdir(parents=True)
        native.write_bytes(b"fake test executable")
        with patch("hive_mind_os.local_codex_worker.shutil.which", return_value=str(wrapper)):
            self.assertEqual(resolve_codex_executable(), native.resolve())


if __name__ == "__main__":
    unittest.main()
