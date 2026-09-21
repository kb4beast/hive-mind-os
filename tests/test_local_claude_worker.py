from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from hive_mind_os.local_claude_worker import (
    PROTOCOL,
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


def _stream(
    report: dict | None = None,
    *,
    tools: list | None = None,
    extra_tool: str | None = None,
    envelopes: int = 1,
    result_overrides: dict | None = None,
    extra_events: list | None = None,
) -> str:
    """A SYNTHETIC transcript shaped like the retained canary, not a model run."""

    report = REPORT if report is None else report
    events = [
        {"type": "system", "subtype": "init", "session_id": SESSION,
         "tools": ["StructuredOutput"] if tools is None else tools, "mcp_servers": [],
         "model": "claude-haiku-4-5-20251001", "permissionMode": "dontAsk",
         "claude_code_version": "2.1.278"},
        {"type": "system", "subtype": "status", "status": "requesting", "session_id": SESSION},
        {"type": "stream_event", "session_id": SESSION, "event": {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "tool_use", "id": "toolu_1", "name": "StructuredOutput", "input": {}}}},
    ]
    for number in range(envelopes):
        events.append({"type": "assistant", "session_id": SESSION, "message": {"content": [
            {"type": "tool_use", "id": f"toolu_{number + 1}", "name": "StructuredOutput", "input": report}]}})
    if extra_tool:
        events.append({"type": "assistant", "session_id": SESSION, "message": {"content": [
            {"type": "tool_use", "id": "toolu_x", "name": extra_tool, "input": {}}]}})
    events.append({"type": "user", "session_id": SESSION, "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "Structured output provided successfully"}]}})
    events.extend(extra_events or [])
    events.append({"type": "rate_limit_event", "session_id": SESSION, "rate_limit_info": {}})
    result = {"type": "result", "subtype": "success", "is_error": False, "session_id": SESSION,
              "terminal_reason": "completed", "permission_denials": [], "structured_output": report,
              "result": json.dumps(report), "usage": {"input_tokens": 1, "output_tokens": 2},
              "modelUsage": {}, "total_cost_usd": 0.001, "duration_ms": 5, "num_turns": 2,
              "subagent_stats": {"spawned": 0}}
    result.update(result_overrides or {})
    events.append(result)
    return "\n".join(json.dumps(event) for event in events) + "\n"


class _Directory(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def stream_file(self, text: str) -> Path:
        path = self.root / f"stream-{time.monotonic_ns()}.jsonl"
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
    def test_exact_schema_envelope_is_the_only_permitted_tool_event(self) -> None:
        parsed = parse_claude_stream(self.stream_file(_stream()))
        self.assertEqual(parsed["session_id"], SESSION)
        self.assertEqual(parsed["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(parsed["report"], REPORT)
        self.assertEqual(parsed["usage"]["total_cost_usd"], 0.001)

    def test_every_other_tool_surface_is_rejected(self) -> None:
        cases = {
            "another tool use": _stream(extra_tool="Bash"),
            "more tools exposed": _stream(tools=["StructuredOutput", "Bash"]),
            "no tools listed": _stream(tools=[]),
            "two envelopes": _stream(envelopes=2),
            "denied permission": _stream(result_overrides={"permission_denials": [{"tool": "Bash"}]}),
            "failed result": _stream(result_overrides={"is_error": True}),
            "unfinished turn": _stream(result_overrides={"terminal_reason": "max_turns"}),
            "output differs": _stream(result_overrides={"structured_output": {**REPORT, "summary": "other"}}),
            "unknown event": _stream(extra_events=[{"type": "tool_progress", "session_id": SESSION}]),
            "subagent": _stream(result_overrides={"subagent_stats": {"spawned": 1}}),
        }
        for name, text in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                parse_claude_stream(self.stream_file(text))

    def test_second_session_or_missing_result_is_rejected(self) -> None:
        foreign = {"type": "rate_limit_event", "session_id": "another-session"}
        with self.assertRaises(ValueError):
            parse_claude_stream(self.stream_file(_stream(extra_events=[foreign])))
        truncated = "\n".join(_stream().splitlines()[:-1]) + "\n"
        with self.assertRaises(ValueError):
            parse_claude_stream(self.stream_file(truncated))


class ClaudeWorkerRunTests(_ClaudeRig):
    def _scratch(self) -> Path:
        path = self.root / f"scratch-{time.monotonic_ns()}"
        path.mkdir()
        return path

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
            evidence_directory=self.root / f"evidence-{time.monotonic_ns()}",
            predecessor_reports=[], objective="propose a patch", timeout_seconds=30,
            writable=True, source_packet=packet,
        )

    def test_receipt_binds_packet_session_model_and_usage(self) -> None:
        worker = self._worker(command_runner=self._runner(_stream()))
        receipt = self._run(worker)
        self.assertEqual(receipt["protocol"], PROTOCOL)
        self.assertEqual(receipt["status"], "completed", receipt["reason"])
        self.assertEqual(receipt["session_id"], SESSION)
        self.assertEqual(receipt["model"], "claude-haiku-4-5-20251001")
        self.assertEqual(receipt["requested_model"], "haiku")
        self.assertEqual(receipt["usage"]["num_turns"], 2)
        packet_file = Path(receipt["evidence"]["source_packet"]["path"])
        self.assertEqual(
            receipt["request"]["source_packet_sha256"], hashlib.sha256(packet_file.read_bytes()).hexdigest()
        )
        on_disk = json.loads((packet_file.parent / "receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["report"], receipt["report"])

    def test_deadline_output_limit_exit_tool_and_scratch_changes_fail_closed(self) -> None:
        cases = {
            "deadline": self._runner("", timed_out=True),
            "output limit": self._runner("", limited=True),
            "exit code": self._runner(_stream(), code=3),
            "tool use": self._runner(_stream(extra_tool="Bash")),
            "scratch written": self._runner(
                _stream(), write=lambda cwd: (cwd / "leak.txt").write_text("x", encoding="utf-8")
            ),
        }
        for name, runner in cases.items():
            with self.subTest(name):
                receipt = self._run(self._worker(command_runner=runner))
                self.assertEqual(receipt["status"], "failed")
                self.assertIsNone(receipt["report"])

    def test_tool_use_failure_preserves_the_actual_session_identity(self) -> None:
        receipt = self._run(self._worker(command_runner=self._runner(_stream(extra_tool="Bash"))))
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["session_id"], SESSION)

    def test_worker_refuses_repository_access_and_unbounded_deadlines(self) -> None:
        worker = self._worker(command_runner=self._runner(_stream()))
        scratch = self._scratch()
        (scratch / "source.py").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty scratch"):
            self._run(worker, scratch=scratch)
        for bad in (float("inf"), float("nan"), 0, True):
            with self.subTest(bad), self.assertRaises(ValueError):
                worker.run(
                    node={"id": "p"}, actor_id="a", role="builder", workspace=self._scratch(),
                    evidence_directory=self.root / f"e-{time.monotonic_ns()}",
                    predecessor_reports=[], objective="o", timeout_seconds=bad,
                    writable=True, source_packet={},
                )
        with self.assertRaises(ValueError):
            worker.run(
                node={"id": "p"}, actor_id="a", role="builder", workspace=self._scratch(),
                evidence_directory=self.root / f"e-{time.monotonic_ns()}",
                predecessor_reports=[], objective="o", timeout_seconds=5, writable=True,
                source_packet=None,
            )


class ClaudeProcessRunnerTests(_Directory):
    """Real subprocesses: no model is involved, only the deadline and byte-cap machinery."""

    def _run(self, script: str, *arguments: str, timeout: float, cap: int = 1_000_000, prompt: bytes = b""):
        base = self.root / f"run-{time.monotonic_ns()}"
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


if __name__ == "__main__":
    unittest.main()
