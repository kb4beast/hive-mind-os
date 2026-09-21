from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from itertools import count
from pathlib import Path
from typing import Any
from unittest import mock

from hive_mind_os.local_claude_worker import (
    PROTOCOL,
    STRUCTURED_OUTPUT_ACK,
    ClaudeInterfaceUnavailable,
    ClaudeLocalWorker,
    _run_claude_process,
    parse_claude_stream,
    supported_options,
)
from hive_mind_os.whole_os_repository_host import process_is_alive

# SYNTHETIC replica of the retained ``claude --help`` option layout (two-space
# indented option heads, wrapped descriptions). It is not the real help text.
SYNTHETIC_HELP = """\
Usage: claude [options] [command] [prompt]

Options:
  --json-schema <schema>                JSON Schema for structured output
                                        validation. Mentions --print in prose.
  --model <model>                       Model for the current session.
  --no-chrome                           Disable Claude in Chrome integration
  --no-session-persistence              Disable session persistence
  --output-format <format>              Output format: "text" (default), "json"
                                        (single result), or "stream-json"
                                        (realtime streaming) (choices: "text")
  --permission-mode <mode>              Permission mode (choices: "acceptEdits",
                                        "dontAsk", "plan")
  --permission-prompts <target>         Who answers prompts: "host" or "none"
                                        (nobody)
  -p, --print                           Print response and exit
  --safe-mode                           Start with customizations disabled
  --setting-sources <sources>           Comma-separated list of setting sources
  --strict-mcp-config                   Only use MCP servers from --mcp-config
  --system-prompt <prompt>              System prompt to use for the session
  --tools <tools...>                    Specify the list of available tools from
                                        the built-in set. Use "" to disable all
                                        tools, "default" to use all tools.
  --verbose                             Override verbose mode setting
  --restricted                          Restricted mode
  --disable-slash-commands              Disable all skills
  --include-hook-events                 Include all hook lifecycle events
  --include-partial-messages            Include partial message chunks

Commands:
  agents [options]                      Manage background agents
"""

REPORT = {
    "status": "completed",
    "summary": "synthetic proposal",
    "findings": ["synthetic finding"],
    "acceptance_evidence": ["synthetic evidence"],
    "ideas": [],
    "selected_idea_ids": [],
    "changed_paths": ["src/calc.py"],
    "tests": ["not run by the worker"],
    "proposed_patch": "diff --git a/src/calc.py b/src/calc.py\n",
}
SESSION = "11111111-2222-3333-4444-555555555555"
MODEL = "claude-haiku-4-5-20251001"
TOOL_ID = "toolu_synthetic_0001"
TOOL = "StructuredOutput"


def _events(report: dict | None = None, *, tool_name: str = TOOL, with_text: bool = False):
    """A SYNTHETIC transcript with the exact event sequence of the retained canary.

    Sequence: init, status, message_start, tool block start/deltas, assistant
    envelope, block stop, tool_result, message_delta, message_stop, rate limit,
    result. It is not a model run and carries no real identifiers.
    """

    report = REPORT if report is None else report
    rendered = json.dumps(report)
    cut = len(rendered) // 2
    index = 1 if with_text else 0

    def streamed(inner: dict) -> dict:
        return {
            "type": "stream_event",
            "event": inner,
            "session_id": SESSION,
            "parent_tool_use_id": None,
        }

    events = [
        {
            "type": "system", "subtype": "init", "session_id": SESSION, "tools": [TOOL],
            "mcp_servers": [], "model": MODEL, "permissionMode": "dontAsk",
            "slash_commands": [], "skills": [], "plugins": [],
            "claude_code_version": "2.1.278",
        },
        {"type": "system", "subtype": "status", "status": "requesting", "session_id": SESSION},
        streamed({
            "type": "message_start",
            "message": {"model": MODEL, "role": "assistant", "content": []},
        }),
    ]
    content = []
    if with_text:
        events += [
            streamed({"type": "content_block_start", "index": 0,
                      "content_block": {"type": "text", "text": ""}}),
            streamed({"type": "content_block_delta", "index": 0,
                      "delta": {"type": "text_delta", "text": "inert preface"}}),
            streamed({"type": "content_block_stop", "index": 0}),
        ]
        content.append({"type": "text", "text": "inert preface"})
    events.append(streamed({
        "type": "content_block_start", "index": index,
        "content_block": {"type": "tool_use", "id": TOOL_ID, "name": tool_name, "input": {}},
    }))
    for piece in ("", rendered[:cut], rendered[cut:]):
        events.append(streamed({
            "type": "content_block_delta", "index": index,
            "delta": {"type": "input_json_delta", "partial_json": piece},
        }))
    content.append({"type": "tool_use", "id": TOOL_ID, "name": tool_name, "input": report})
    events += [
        {
            "type": "assistant", "session_id": SESSION, "parent_tool_use_id": None,
            "message": {"model": MODEL, "role": "assistant", "content": content},
        },
        streamed({"type": "content_block_stop", "index": index}),
        {
            "type": "user", "session_id": SESSION, "parent_tool_use_id": None,
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": TOOL_ID, "content": STRUCTURED_OUTPUT_ACK},
            ]},
            "tool_use_result": STRUCTURED_OUTPUT_ACK,
        },
        streamed({"type": "message_delta", "delta": {"stop_reason": "tool_use"}}),
        streamed({"type": "message_stop"}),
        {"type": "rate_limit_event", "session_id": SESSION, "rate_limit_info": {}},
        {
            "type": "result", "subtype": "success", "is_error": False, "session_id": SESSION,
            "terminal_reason": "completed", "permission_denials": [],
            "structured_output": report, "result": rendered,
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "modelUsage": {MODEL: {}}, "total_cost_usd": 0.001, "duration_ms": 5,
            "duration_api_ms": 4, "num_turns": 2, "subagent_stats": {"spawned": 0},
        },
    ]
    return events


def _text(events: list[dict]) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _find(events: list[dict], kind: str, inner: str | None = None) -> dict:
    return next(
        event for event in events
        if event["type"] == kind and (inner is None or event["event"]["type"] == inner)
    )


def _mutations() -> dict:
    """Each entry damages a valid canary-shaped transcript in one specific way."""

    def rename_assistant_tool(events):
        _find(events, "assistant")["message"]["content"][0]["name"] = "Bash"

    def rename_streamed_tool(events):
        _find(events, "stream_event", "content_block_start")["event"]["content_block"]["name"] = "PowerShell"

    def drop_tool_result(events):
        events[:] = [event for event in events if event["type"] != "user"]

    def duplicate_tool_result(events):
        events.insert(-1, copy.deepcopy(_find(events, "user")))

    def unknown_nested_execution(events):
        events.insert(-1, {
            "type": "stream_event", "session_id": SESSION, "parent_tool_use_id": None,
            "event": {"type": "command_execution", "command": "INERT NEGATIVE CONTROL"},
        })

    def assistant_without_session(events):
        _find(events, "assistant").pop("session_id")

    def assistant_other_session(events):
        _find(events, "assistant")["session_id"] = "different-synthetic-session"

    def assistant_other_model(events):
        _find(events, "assistant")["message"]["model"] = "different-synthetic-model"

    def message_start_other_model(events):
        _find(events, "stream_event", "message_start")["event"]["message"]["model"] = "other"

    def event_after_result(events):
        events.append({"type": "system", "subtype": "status", "status": "requesting", "session_id": SESSION})

    def result_disagrees(events):
        events[-1]["structured_output"] = {**REPORT, "summary": "other"}

    def streamed_json_disagrees(events):
        _find(events, "stream_event", "content_block_delta")["event"]["delta"]["partial_json"] = "{"

    def extra_capability(events):
        events[0]["tools"].append("Read")

    def mcp_server(events):
        events[0]["mcp_servers"] = [{"name": "external"}]

    def plugin_loaded(events):
        events[0]["plugins"] = ["external"]

    def error_result(events):
        events[-1]["is_error"] = True

    def denial(events):
        events[-1]["permission_denials"] = [{"tool": "Bash"}]

    def unfinished(events):
        events[-1]["terminal_reason"] = "max_turns"

    def subagent(events):
        events[-1]["subagent_stats"] = {"spawned": 1}

    def nested_agent(events):
        _find(events, "assistant")["parent_tool_use_id"] = "toolu_parent"

    def second_envelope(events):
        block = {"type": "tool_use", "id": "toolu_second", "name": TOOL, "input": REPORT}
        _find(events, "assistant")["message"]["content"].append(block)

    def second_message(events):
        events.insert(3, copy.deepcopy(events[2]))

    def result_before_message_stop(events):
        events[:] = [event for event in events if not (
            event["type"] == "stream_event" and event["event"]["type"] == "message_stop")]

    def stream_without_message(events):
        events[:] = [event for event in events if not (
            event["type"] == "stream_event" and event["event"]["type"] == "message_start")]

    def result_text_disagrees(events):
        events[-1]["result"] = json.dumps({**REPORT, "summary": "other"})

    def other_model_usage(events):
        events[-1]["modelUsage"] = {"another-model": {}}

    def tool_result_other_content(events):
        _find(events, "user")["message"]["content"][0]["content"] = "something else"

    def tool_result_other_summary(events):
        _find(events, "user")["tool_use_result"] = "something else"

    def tool_result_unknown_id(events):
        _find(events, "user")["message"]["content"][0]["tool_use_id"] = "toolu_unknown"

    def tool_result_error(events):
        _find(events, "user")["message"]["content"][0]["is_error"] = True

    def user_text_block(events):
        _find(events, "user")["message"]["content"].append({"type": "text", "text": "hi"})

    def status_before_init(events):
        events[0], events[1] = events[1], events[0]

    def delta_on_closed_block(events):
        events.insert(-4, {
            "type": "stream_event", "session_id": SESSION, "parent_tool_use_id": None,
            "event": {"type": "content_block_delta", "index": 0,
                      "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        })

    def unknown_assistant_block(events):
        _find(events, "assistant")["message"]["content"].append({"type": "command_execution"})

    def unknown_event_type(events):
        events.insert(-1, {"type": "tool_progress", "session_id": SESSION})

    def other_system_subtype(events):
        events[1]["subtype"] = "hook_started"

    def truncated(events):
        events.pop()

    return {
        "assistant tool renamed": rename_assistant_tool,
        "streamed tool renamed": rename_streamed_tool,
        "missing internal tool_result": drop_tool_result,
        "duplicate internal tool_result": duplicate_tool_result,
        "unknown nested execution event": unknown_nested_execution,
        "assistant lacks session": assistant_without_session,
        "assistant other session": assistant_other_session,
        "assistant/init model conflict": assistant_other_model,
        "message_start/init model conflict": message_start_other_model,
        "event after terminal result": event_after_result,
        "result disagrees with envelope": result_disagrees,
        "streamed JSON disagrees with envelope": streamed_json_disagrees,
        "extra executable capability": extra_capability,
        "mcp server exposed": mcp_server,
        "plugin loaded": plugin_loaded,
        "error result": error_result,
        "permission denial": denial,
        "unfinished turn": unfinished,
        "subagent spawned": subagent,
        "nested agent event": nested_agent,
        "second schema envelope": second_envelope,
        "second message": second_message,
        "result before message_stop": result_before_message_stop,
        "stream event without message": stream_without_message,
        "result text disagrees": result_text_disagrees,
        "model usage names another model": other_model_usage,
        "tool_result with other content": tool_result_other_content,
        "tool_use_result with other content": tool_result_other_summary,
        "tool_result for unknown id": tool_result_unknown_id,
        "tool_result marked error": tool_result_error,
        "extra user block": user_text_block,
        "status before init": status_before_init,
        "delta on a closed block": delta_on_closed_block,
        "unknown assistant block": unknown_assistant_block,
        "unknown event type": unknown_event_type,
        "unknown system subtype": other_system_subtype,
        "missing result": truncated,
    }


class _Directory(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self._fixture_paths = count()

    def _fixture_path(self, prefix: str, suffix: str = "") -> Path:
        # Clock resolution is not a uniqueness guarantee (Windows Python 3.12).
        return self.root / f"{prefix}-{next(self._fixture_paths)}{suffix}"

    def stream_file(self, text: str) -> Path:
        path = self._fixture_path("stream", ".jsonl")
        path.write_text(text, encoding="utf-8")
        return path


class SupportedOptionTests(unittest.TestCase):
    def test_options_come_from_declarations_not_prose(self) -> None:
        options = supported_options(SYNTHETIC_HELP)
        self.assertIn("--json-schema", options)
        self.assertIn("--print", options)
        self.assertNotIn("--mcp-config", options)  # only mentioned in another option's prose


class _ClaudeRig(_Directory):
    """Helpers only; concrete test classes below add the test methods."""

    def _executable(self) -> Path:
        path = self.root / ("claude-double.exe" if os.name == "nt" else "claude-double")
        shutil.copy2(sys.executable, path)
        return path

    def _evidence(self, help_text: str = SYNTHETIC_HELP, digest: str | None = None) -> tuple[Path, Path]:
        executable = self._executable()
        help_path = self.root / "help.txt"
        help_path.write_text(help_text, encoding="utf-8")
        receipt = self.root / "help-receipt.json"
        receipt.write_text(json.dumps({
            "command": [str(executable), "--help"],
            "executable_sha256": digest or hashlib.sha256(executable.read_bytes()).hexdigest(),
        }), encoding="utf-8")
        return help_path, receipt

    def _worker(self, **overrides) -> ClaudeLocalWorker:
        help_path, receipt = self._evidence(**{k: v for k, v in overrides.items() if k in {"help_text", "digest"}})
        runner = overrides.get("command_runner")
        return ClaudeLocalWorker(
            executable=self.root / ("claude-double.exe" if os.name == "nt" else "claude-double"),
            help_evidence=help_path, help_receipt=receipt, model="haiku", command_runner=runner,
        )


class ClaudeInterfaceBindingTests(_ClaudeRig):
    def test_invocation_is_derived_from_retained_help_and_binary(self) -> None:
        worker = self._worker()
        command = worker._command("{}")
        emitted = {item for item in command if item.startswith("--")}
        self.assertTrue(emitted <= supported_options(SYNTHETIC_HELP))
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertEqual(command[command.index("--permission-prompts") + 1], "none")
        self.assertEqual(worker.preflight(), ())

    def test_missing_control_or_foreign_binary_is_a_typed_blocker(self) -> None:
        without_schema = SYNTHETIC_HELP.replace("--json-schema", "--json-shape")
        with self.assertRaisesRegex(ClaudeInterfaceUnavailable, "json-schema"):
            self._worker(help_text=without_schema)
        with self.assertRaisesRegex(ClaudeInterfaceUnavailable, "does not describe"):
            self._worker(digest="0" * 64)

    def test_replaced_binary_is_seen_by_preflight(self) -> None:
        worker = self._worker()
        worker.executable.write_bytes(b"replaced")
        self.assertTrue(worker.preflight())


class ClaudeStreamParserTests(_Directory):
    def test_canary_shaped_envelope_is_accepted_with_exact_identities(self) -> None:
        parsed = parse_claude_stream(self.stream_file(_text(_events())))
        self.assertEqual(parsed["session_id"], SESSION)
        self.assertEqual(parsed["model"], MODEL)
        self.assertEqual(parsed["cli_version"], "2.1.278")
        self.assertEqual(parsed["report"], REPORT)
        self.assertEqual(parsed["usage"]["total_cost_usd"], 0.001)

    def test_inert_text_block_is_allowed_beside_the_envelope(self) -> None:
        parsed = parse_claude_stream(self.stream_file(_text(_events(with_text=True))))
        self.assertEqual(parsed["report"], REPORT)

    def test_every_counterexample_is_rejected(self) -> None:
        for name, mutate in _mutations().items():
            events = _events()
            mutate(events)
            with self.subTest(name), self.assertRaises(ValueError):
                parse_claude_stream(self.stream_file(_text(events)))

    def test_each_mutation_changes_a_transcript_that_is_otherwise_accepted(self) -> None:
        # Guards the mutation table itself: the untouched transcript must pass.
        parse_claude_stream(self.stream_file(_text(_events())))
        for name, mutate in _mutations().items():
            events = _events()
            mutate(events)
            self.assertNotEqual(events, _events(), name)

    def test_duplicate_json_key_and_blank_padding_are_handled_strictly(self) -> None:
        lines = [json.dumps(event) for event in _events()]
        duplicated = [*lines[:-1], lines[-1][:-1] + ', "is_error": true}']
        with self.assertRaises(ValueError):
            parse_claude_stream(self.stream_file("\n".join(duplicated) + "\n"))
        padded = "\n\n".join(lines) + "\n\n\n"
        self.assertEqual(parse_claude_stream(self.stream_file(padded))["report"], REPORT)
        with self.assertRaises(ValueError):
            parse_claude_stream(self.stream_file("\n".join(lines) + "\n{}\n"))

    def test_oversized_transcript_is_rejected_before_parsing(self) -> None:
        path = self.stream_file(_text(_events()))
        with self.assertRaises(ValueError):
            parse_claude_stream(path, max_bytes=100)


class ClaudeWorkerRunTests(_ClaudeRig):
    def _scratch(self) -> Path:
        path = self._fixture_path("scratch")
        path.mkdir()
        return path

    def test_fixture_paths_do_not_reuse_a_clock_tick_or_overwrite_streams(self) -> None:
        with mock.patch("time.monotonic_ns", return_value=2428890000000):
            scratches = [self._scratch() for _ in range(20)]
            streams = [self.stream_file(str(index)) for index in range(20)]
            evidence = [self._fixture_path("evidence") for _ in range(20)]
        self.assertEqual(60, len(set(scratches + streams + evidence)))
        self.assertTrue(all(path.is_dir() and not tuple(path.iterdir()) for path in scratches))
        self.assertEqual([str(index) for index in range(20)],
                         [path.read_text(encoding="utf-8") for path in streams])
        self.assertTrue(all(not path.exists() and path.parent == self.root for path in evidence))

    @staticmethod
    def _runner(text: str, *, code: int = 0, timed_out: bool = False, limited: bool = False, write=None):
        # SYNTHETIC command runner: writes a canned transcript instead of starting Claude.
        def run(command, *, cwd, environment, prompt, stdout_path, stderr_path, process_path,
                timeout_seconds, max_output_bytes):
            stdout_path.write_text(text, encoding="utf-8")
            stderr_path.write_bytes(b"")
            if write is not None:
                write(cwd)
            return code, timed_out, limited
        return run

    def _run(self, worker: ClaudeLocalWorker, *, scratch: Path | None = None) -> dict:
        packet = {"kind": "synthetic-packet", "head": "a" * 40}
        return worker.run(
            node={"id": "package"}, actor_id="builder-actor", role="builder",
            workspace=scratch or self._scratch(),
            evidence_directory=self._fixture_path("evidence"),
            predecessor_reports=[], objective="propose a patch", timeout_seconds=30,
            writable=True, source_packet=packet,
        )

    def test_receipt_binds_packet_session_model_and_usage(self) -> None:
        worker = self._worker(command_runner=self._runner(_text(_events())))
        receipt = self._run(worker)
        self.assertEqual(receipt["protocol"], PROTOCOL)
        self.assertEqual(receipt["status"], "completed", receipt["reason"])
        self.assertEqual(receipt["session_id"], SESSION)
        self.assertEqual(receipt["model"], MODEL)
        self.assertEqual(receipt["requested_model"], "haiku")
        self.assertEqual(receipt["usage"]["num_turns"], 2)
        packet_file = Path(receipt["evidence"]["source_packet"]["path"])
        self.assertEqual(
            receipt["request"]["source_packet_sha256"], hashlib.sha256(packet_file.read_bytes()).hexdigest()
        )
        on_disk = json.loads((packet_file.parent / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["report"], receipt["report"])

    def test_deadline_output_limit_exit_tool_and_scratch_changes_fail_closed(self) -> None:
        tool_events = _events(tool_name="Bash")
        cases = {
            "deadline": self._runner("", timed_out=True),
            "output limit": self._runner("", limited=True),
            "exit code": self._runner(_text(_events()), code=3),
            "tool use": self._runner(_text(tool_events)),
            "scratch written": self._runner(
                _text(_events()), write=lambda cwd: (cwd / "leak.txt").write_text("x", encoding="utf-8")
            ),
        }
        for name, runner in cases.items():
            with self.subTest(name):
                receipt = self._run(self._worker(command_runner=runner))
                self.assertEqual(receipt["status"], "failed")
                self.assertIsNone(receipt["report"])

    def test_unchanged_executable_is_rechecked_and_recorded_at_dispatch(self) -> None:
        calls = []
        canned = self._runner(_text(_events()))

        def runner(*args, **kwargs):
            calls.append(args[0][0])
            return canned(*args, **kwargs)

        worker = self._worker(command_runner=runner)
        receipt = self._run(worker)
        self.assertEqual(receipt["status"], "completed", receipt["reason"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            receipt["dispatch"],
            {
                "dispatched": True,
                "executable_sha256_sealed": worker.executable_sha256,
                "executable_sha256_observed": worker.executable_sha256,
                "matches_sealed": True,
            },
        )

    def test_executable_drift_after_construction_is_refused_before_dispatch(self) -> None:
        # Judge counterexample: preflight saw the drift, run() still dispatched.
        calls = []
        canned = self._runner(_text(_events()))

        def runner(*args, **kwargs):
            calls.append(args[0][0])
            return canned(*args, **kwargs)

        cases = {
            "content replaced": lambda path: path.write_bytes(b"synthetic changed executable"),
            "file removed": lambda path: path.unlink(),
        }
        for name, damage in cases.items():
            with self.subTest(name):
                calls.clear()
                worker = self._worker(command_runner=runner)
                sealed = worker.executable_sha256
                self.assertEqual(worker.preflight(), ())
                damage(worker.executable)
                self.assertTrue(worker.preflight())
                receipt = self._run(worker)
                self.assertEqual(calls, [], "the runner was never reached")
                self.assertEqual(receipt["status"], "failed")
                self.assertIsNone(receipt["report"])
                self.assertIn("dispatch refused", receipt["reason"])
                self.assertIn("no process was started", receipt["reason"])
                self.assertFalse(receipt["dispatch"]["dispatched"])
                self.assertFalse(receipt["dispatch"]["matches_sealed"])
                self.assertEqual(receipt["dispatch"]["executable_sha256_sealed"], sealed)
                if name == "content replaced":
                    self.assertNotEqual(receipt["dispatch"]["executable_sha256_observed"], sealed)
                else:
                    self.assertIsNone(receipt["dispatch"]["executable_sha256_observed"])
                evidence = Path(receipt["evidence"]["source_packet"]["path"]).parent
                self.assertFalse((evidence / "stdout.jsonl").exists(), "no transcript exists")
                self.assertFalse((evidence / "process.json").exists(), "no process was recorded")
                on_disk = json.loads((evidence / "receipt.json").read_text(encoding="utf-8"))
                self.assertEqual(on_disk["dispatch"], receipt["dispatch"])
                # Restoring the exact sealed bytes lets the same worker dispatch again.
                self._executable()
                self.assertEqual(worker.preflight(), ())
                self.assertEqual(self._run(worker)["status"], "completed")
                self.assertEqual(len(calls), 1)

    def test_a_rejected_transcript_preserves_the_actual_session_identity(self) -> None:
        events = _events()
        events.pop(-5)  # the internal tool_result, just before message_delta/stop/result
        receipt = self._run(self._worker(command_runner=self._runner(_text(events))))
        self.assertEqual(receipt["status"], "failed")
        self.assertIn("tool result", receipt["reason"])
        self.assertEqual(receipt["session_id"], SESSION)

    def test_worker_refuses_repository_access_and_unbounded_deadlines(self) -> None:
        worker = self._worker(command_runner=self._runner(_text(_events())))
        scratch = self._scratch()
        (scratch / "source.py").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty scratch"):
            self._run(worker, scratch=scratch)
        for bad in (float("inf"), float("nan"), 0, True):
            with self.subTest(bad), self.assertRaises(ValueError):
                worker.run(
                    node={"id": "p"}, actor_id="a", role="builder", workspace=self._scratch(),
                    evidence_directory=self._fixture_path("e"),
                    predecessor_reports=[], objective="o", timeout_seconds=bad,
                    writable=True, source_packet={},
                )
        with self.assertRaises(ValueError):
            worker.run(
                node={"id": "p"}, actor_id="a", role="builder", workspace=self._scratch(),
                evidence_directory=self._fixture_path("e"),
                predecessor_reports=[], objective="o", timeout_seconds=5, writable=True,
                source_packet=None,
            )


class ClaudeProcessRunnerTests(_Directory):
    """Real subprocesses: no model is involved, only the deadline and byte-cap machinery."""

    def _run(self, script: str, *arguments: str, timeout: float, cap: int = 1_000_000, prompt: bytes = b""):
        base = self._fixture_path("run")
        base.mkdir()
        result = _run_claude_process(
            [sys.executable, "-c", script, *arguments], cwd=base, environment=dict(os.environ),
            prompt=prompt, stdout_path=base / "stdout", stderr_path=base / "stderr",
            process_path=base / "process.json", timeout_seconds=timeout, max_output_bytes=cap,
        )
        return result, base

    def test_normal_run_returns_output_and_records_the_process(self) -> None:
        (code, timed_out, limited), base = self._run(
            "import sys; sys.stdout.write(sys.stdin.read().upper())", timeout=30, prompt=b"prompt text"
        )
        self.assertEqual((code, timed_out, limited), (0, False, False))
        self.assertEqual((base / "stdout").read_bytes(), b"PROMPT TEXT")
        self.assertIn("pid", json.loads((base / "process.json").read_text(encoding="utf-8")))

    def test_deadline_terminates_the_whole_process_tree(self) -> None:
        pid_file = self.root / "child.pid"
        script = (
            "import subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            "open(sys.argv[1], 'w').write(str(child.pid))\n"
            "time.sleep(120)\n"
        )
        started = time.monotonic()
        (code, timed_out, limited), _ = self._run(script, str(pid_file), timeout=6)
        self.assertLess(time.monotonic() - started, 60)
        self.assertTrue(timed_out)
        self.assertFalse(limited)
        child = int(pid_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 15
        while process_is_alive(child) and time.monotonic() < deadline:
            time.sleep(0.25)
        self.assertFalse(process_is_alive(child), "grandchild survived the process-tree kill")

    def test_output_is_bounded_and_the_process_is_stopped(self) -> None:
        script = "import sys, time\nwhile True:\n    sys.stdout.write('x' * 65536); sys.stdout.flush()\n"
        (code, timed_out, limited), base = self._run(script, timeout=60, cap=5_000)
        self.assertTrue(limited)
        self.assertFalse(timed_out)
        self.assertLessEqual((base / "stdout").stat().st_size, 5_000)

    def _assert_child_reaped_and_pipes_closed(self, proc: subprocess.Popen[Any]) -> None:
        # Observation only: poll()/wait() here would repair an unreaped child.
        self.assertIsNotNone(proc.returncode, f"process {proc.pid} was not reaped by the runner")
        for name in ("stdin", "stdout", "stderr"):
            pipe = getattr(proc, name)
            self.assertIsNotNone(pipe, f"runner child has no {name} pipe")
            self.assertTrue(pipe.closed, f"process {proc.pid} {name} not closed")

    def test_no_pipe_is_left_open_after_a_deadline_an_output_cap_or_a_normal_exit(self) -> None:
        # Retain the real runner child and inspect it before any test cleanup.
        # Process-global GC is not an ownership-bound leak oracle.
        flood = "import sys\nwhile True:\n    sys.stdout.write('x' * 65536); sys.stdout.flush()\n"
        cases = (
            ("deadline", "import time; time.sleep(120)", 1, 1_000_000),
            ("output_cap", flood, 60, 2_000),
            ("normal", "print('done')", 30, 1_000_000),
        )
        original_popen = subprocess.Popen
        for name, script, timeout, cap in cases:
            with self.subTest(name=name):
                owned: list[subprocess.Popen[Any]] = []

                def capture_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[Any]:
                    proc = original_popen(*args, **kwargs)
                    owned.append(proc)
                    return proc

                try:
                    with mock.patch("hive_mind_os.local_claude_worker.subprocess.Popen", side_effect=capture_popen):
                        (code, timed_out, limited), _ = self._run(script, timeout=timeout, cap=cap)
                    # Windows tree termination may spawn its own helper. Match the
                    # exact Python child instead of treating that helper as the worker.
                    children = [p for p in owned if p.args == [sys.executable, "-c", script]]
                    self.assertEqual(len(children), 1)
                    self._assert_child_reaped_and_pipes_closed(children[0])
                    self.assertEqual(timed_out, name == "deadline")
                    self.assertEqual(limited, name == "output_cap")
                    if name == "normal":
                        self.assertEqual(code, 0)
                finally:
                    # This runs after the observations, including when they fail.
                    for proc in owned:
                        try:
                            if proc.poll() is None:
                                proc.kill()
                            proc.wait(timeout=5)
                        finally:
                            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                                if pipe is not None and not pipe.closed:
                                    pipe.close()


if __name__ == "__main__":
    unittest.main()
