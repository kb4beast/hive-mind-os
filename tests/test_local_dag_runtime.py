from __future__ import annotations

import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.local_dag_runtime import (
    LocalExecutionError,
    LocalTournamentService,
    _clone,
)
from hive_mind_os.local_run_authority import LocalAuthorityError, LocalAuthorityStore
from hive_mind_os.runtime_contracts import raw_sha256
from hive_mind_os.tournament_cli import prepare_tournament


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class SimulatedWorkerCrash(BaseException):
    """Bypass an ordinary worker-error result, like a terminated controller."""


class RecordingWorker:
    """A deterministic test double; its receipts are never live host evidence."""

    def __init__(self, *, failed_node=None, duplicate_session=False, changed_path_mismatch=False):
        self.failed_node = failed_node
        self.duplicate_session = duplicate_session
        self.changed_path_mismatch = changed_path_mismatch
        self.calls: list[dict] = []
        self.lock = threading.Lock()
        self.after_call = None
        self.crash_node = None
        self.omit_ideas_node = None
        self.invalid_selection_node = None
        self.empty_selection_node = None
        self.run_fixture_verifier_tests = True
        self.executable = Path(sys.executable)

    def run(self, **arguments):
        node = arguments["node"]
        node_id = node["node_id"]
        workspace = arguments["workspace"]
        evidence = arguments["evidence_directory"]
        evidence.mkdir(parents=True, exist_ok=False)
        with self.lock:
            self.calls.append({
                **arguments,
                "commit_before": git(workspace, "rev-parse", "HEAD"),
                "source_before": (workspace / "counter.py").read_text(encoding="utf-8"),
            })
        if node_id == self.crash_node:
            raise SimulatedWorkerCrash()
        changed_paths = []
        if arguments["writable"]:
            (workspace / "counter.py").write_text(
                "def increment(value):\n    return value + 1\n", encoding="utf-8",
            )
            changed_paths = [] if self.changed_path_mismatch else ["counter.py"]
        tests = []
        command_log = b"Deterministic runtime test double; no model was called.\n"
        if node_id == "VERIFY-070" and self.run_fixture_verifier_tests:
            completed = subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "test_counter", "-v"],
                cwd=workspace, capture_output=True, check=False,
            )
            command_log += completed.stdout + completed.stderr
            tests = [f"Real isolated unittest process exit: {completed.returncode}"]
            if completed.returncode:
                raise AssertionError(command_log.decode("utf-8", "replace"))
        failed = node_id == self.failed_node
        report = {
            "status": "blocked" if failed else "completed",
            "summary": "Deterministic runtime test double",
            "findings": ["counter.py contains the fixture's selected experiment."],
            "acceptance_evidence": ["Test harness source inspection and recorded command output."],
            "ideas": [{
                "idea_id": "increment-result", "title": "Correct the increment result",
                "hypothesis": "Returning value + 1 satisfies the public function contract.",
                "source": "counter.py and test_counter.py", "disposition": "adapt",
                "reason": "The executable example expects increment(2) == 3.",
                "next_action": "Reproduce acceptance in the independent verification clone.",
                "return_to_agent": "curator", "parent_idea_id": None,
            }],
            "selected_idea_ids": ["increment-result"],
            "changed_paths": changed_paths, "tests": tests,
        }
        if node_id == self.omit_ideas_node:
            report["ideas"] = []
            report["selected_idea_ids"] = []
        if node_id == self.invalid_selection_node:
            report["selected_idea_ids"] = ["unadjudicated-other-experiment"]
        if node_id == self.empty_selection_node:
            report["selected_idea_ids"] = []
            report["ideas"][0]["disposition"] = "defer"
            report["ideas"][0]["reason"] = "Experiment deferred; no candidate edit selected."
        report_path = evidence / "report.json"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        command_path = evidence / "commands.txt"
        command_path.write_bytes(command_log)
        result = {
            "node_id": node_id,
            "actor_id": arguments["actor_id"],
            "role": arguments["role"],
            "workspace": str(workspace),
            "status": "failed" if failed else "completed",
            "reason": "Injected host failure" if failed else None,
            "session_id": "fixture:BASELINE-001" if self.duplicate_session else f"fixture:{node_id}",
            "exit_code": 7 if failed else 0,
            "report": report,
            "evidence": {name: {
                "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            } for name, path in (("report", report_path), ("commands", command_path))},
        }
        if self.after_call:
            self.after_call(arguments, result)
        return result


class PacketRecordingWorker(RecordingWorker):
    """Model-output fixture: source packets in, an inert patch proposal out."""

    def __init__(self):
        super().__init__()
        self.run_fixture_verifier_tests = False

    def run(self, **arguments):
        if "source_packet" not in arguments:
            raise AssertionError("Packet mode must provide captured source evidence")
        # Even the Builder fixture performs no workspace writes or test process.
        result = super().run(**{**arguments, "writable": False})
        report = result["report"]
        report["proposed_patch"] = None
        if arguments["node"]["node_id"] == "CHALLENGER-060":
            selected = {item["path"]: item["content"] for item in arguments["source_packet"]["selected_files"]}
            before = selected["counter.py"]
            after = before.replace("return value\n", "return value + 1\n")
            source_patch = "".join(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True),
                fromfile="a/counter.py", tofile="b/counter.py",
            ))
            regression = (
                "import unittest\nfrom counter import increment\n\n"
                "class PacketCounterTests(unittest.TestCase):\n"
                "    def test_increment(self):\n"
                "        self.assertEqual(3, increment(2))\n"
            )
            test_patch = "".join(difflib.unified_diff(
                [], regression.splitlines(True), fromfile="/dev/null",
                tofile="b/tests/test_counter_packet.py",
            ))
            report["proposed_patch"] = source_patch + test_patch
            report["changed_paths"] = ["counter.py", "tests/test_counter_packet.py"]
        if arguments["node"]["node_id"] == "VERIFY-070":
            checks = arguments["source_packet"]["independent_host_checks"]
            report["acceptance_evidence"] = [f"Independent host checks status: {checks['status']}"]
        report_path = arguments["evidence_directory"] / "report.json"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        result["evidence"]["report"]["sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
        return result


class LocalDagRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repository = self.root / "FOO BAR"
        self.repository.mkdir()
        git(self.repository, "init", "-b", "main")
        git(self.repository, "config", "user.name", "Runtime fixture")
        git(self.repository, "config", "user.email", "fixture@example.invalid")
        git(self.repository, "config", "commit.gpgsign", "false")
        (self.repository / "counter.py").write_text(
            "def increment(value):\n    return value\n", encoding="utf-8",
        )
        (self.repository / "test_counter.py").write_text(
            "import unittest\nfrom counter import increment\n\n"
            "class CounterTests(unittest.TestCase):\n"
            "    def test_increment(self):\n"
            "        self.assertEqual(3, increment(2))\n", encoding="utf-8",
        )
        git(self.repository, "add", ".")
        git(self.repository, "commit", "-m", "Small unrelated fixture repository")
        self.base = git(self.repository, "rev-parse", "HEAD")
        self.request = self.root / "request.txt"
        self.request.write_text(
            "Execute a local tournament on FOO BAR and retain actual outcomes.\n",
            encoding="utf-8",
        )
        self.standard = Path(__file__).resolve().parents[1] / "docs/execution/DAG_AUTHORING_STANDARD_V2.md"
        self.bundle = self.root / "prepared"
        self.manifest = prepare_tournament(
            repository=self.repository, request_file=self.request,
            standard_file=self.standard, output=self.bundle,
        )
        self.state = self.root / "private state"
        self.host = self.root / "operator host"
        self.brain = self.root / "brain run"
        self.worker = RecordingWorker()
        self.service = LocalTournamentService(self.worker, worker_mode="direct")
        # Concurrent implementation edits elsewhere must not change this test's
        # deliberately injected installed-host identity halfway through a run.
        host_pin = patch(
            "hive_mind_os.local_dag_runtime.host_digest",
            return_value=raw_sha256(b"fixed runtime test host identity"),
        )
        host_pin.start()
        self.addCleanup(host_pin.stop)

    def execute(self, **overrides):
        arguments = {
            "plan_path": self.bundle / "plan.json", "standard_path": self.standard,
            "expected_plan_digest": self.manifest["plan_digest"],
            "repository": self.repository, "state_directory": self.state,
            "host_directory": self.host, "operator_request_file": self.request,
            "brain_directory": self.brain, "workers": 4, "node_timeout": 60,
        }
        arguments.update(overrides)
        return self.service.execute(**arguments)

    def events(self):
        return self.service._events(self.state, LocalAuthorityStore(self.host))

    def test_real_clones_dispatch_dependencies_and_verify_candidate_then_resume(self) -> None:
        result = self.execute()
        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(13, result["completed_nodes"])
        self.assertEqual(14, result["session_count"])
        by_node = {call["node"]["node_id"]: call for call in self.worker.calls}
        self.assertEqual(14, len(by_node))
        for node_id, call in by_node.items():
            with self.subTest(node_id=node_id):
                context_nodes = {report["node_id"] for report in call["predecessor_reports"]}
                self.assertTrue(set(call["node"]["dependencies"]).issubset(context_nodes))
                self.assertNotEqual(self.repository, call["workspace"])
                self.assertEqual("", git(call["workspace"], "remote"))
        self.assertEqual({
            "orchestrator", "explorer", "architect", "steward", "optimizer",
            "curator", "builder", "integrator", "expert-witness",
        }, {call["role"] for call in self.worker.calls})
        builder = by_node["CHALLENGER-060"]
        verifier = by_node["VERIFY-070"]
        self.assertTrue(builder["writable"])
        self.assertFalse(verifier["writable"])
        self.assertNotEqual(builder["workspace"], verifier["workspace"])
        self.assertNotEqual(builder["actor_id"], verifier["actor_id"])
        self.assertIn("value + 1", verifier["source_before"])
        self.assertEqual(result["candidate_commit"], verifier["commit_before"])
        self.assertNotEqual(self.base, result["candidate_commit"])
        self.assertEqual(self.base, git(self.repository, "rev-parse", "HEAD"))
        self.assertEqual("", git(self.repository, "status", "--porcelain"))
        self.assertIn("return value\n", (self.repository / "counter.py").read_text())
        verification = next(event for event in self.events() if event.get("node_id") == "VERIFY-070" and event["kind"] == "node_completed")
        self.assertEqual(["Real isolated unittest process exit: 0"], verification["workers"][0]["report"]["tests"])
        notes = list(self.brain.glob("idea-*.md"))
        self.assertEqual(1, len(notes))
        history = notes[0].read_text(encoding="utf-8")
        for fragment in ("CROSS-045", "COURT-050", "JUDGE-075", "Reason:", "Return to:", "Next action:"):
            self.assertIn(fragment, history)
        before = len(self.worker.calls)
        self.assertEqual(result, self.execute(resume=True))
        self.assertEqual(before, len(self.worker.calls))

    def test_failed_worker_stops_dependent_nodes_and_does_not_retry_on_resume(self) -> None:
        self.worker.failed_node = "AGENTS-010"
        result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        nodes = {call["node"]["node_id"] for call in self.worker.calls}
        self.assertNotIn("PROPOSE-042", nodes)
        self.assertNotIn("CHALLENGER-060", nodes)
        failures = [event for event in self.events() if event["kind"] == "node_failed"]
        self.assertEqual(["AGENTS-010"], [event["node_id"] for event in failures])
        self.assertEqual(7, failures[0]["workers"][0]["exit_code"])
        before = len(self.worker.calls)
        self.assertEqual("BLOCKED", self.execute(resume=True)["status"])
        self.assertEqual(before, len(self.worker.calls))

    def test_default_packet_mode_applies_proposal_and_runs_independent_host_checks(self) -> None:
        self.worker = PacketRecordingWorker()
        self.service = LocalTournamentService(self.worker)
        result = self.execute()
        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(13, result["completed_nodes"])
        self.assertTrue(all("source_packet" in call for call in self.worker.calls))
        self.assertTrue(all(not call["writable"] for call in self.worker.calls))
        witness_index = next(i for i, call in enumerate(self.worker.calls) if call["node"]["node_id"] == "CROSS-045-WITNESS")
        examiner_index = next(i for i, call in enumerate(self.worker.calls) if call["node"]["node_id"] == "CROSS-045")
        self.assertLess(witness_index, examiner_index)
        examiner = self.worker.calls[examiner_index]
        self.assertIn("CROSS-045-WITNESS", {item["node_id"] for item in examiner["predecessor_reports"]})
        self.assertLessEqual(examiner["source_packet"]["selected_content_bytes"], 60_000)
        completed = {event["node_id"]: event for event in self.events() if event["kind"] == "node_completed"}
        runtime_call = next(call for call in self.worker.calls if call["node"]["node_id"] == "RUNTIME-030")
        runtime_checks = runtime_call["source_packet"]["independent_host_checks"]
        self.assertGreater(runtime_checks["total_tests"], 0)
        self.assertEqual(runtime_checks, completed["RUNTIME-030"]["workers"][0]["host_checks"])
        self.assertTrue(Path(runtime_checks["checks"][0]["stderr_path"]).is_file())
        builder = completed["CHALLENGER-060"]["workers"][0]
        verifier = completed["VERIFY-070"]["workers"][0]
        self.assertEqual(["counter.py", "tests/test_counter_packet.py"], builder["host_patch"]["changed_paths"])
        for receipt in (builder, verifier):
            checks = receipt["host_checks"]
            self.assertTrue(checks["all_passed"])
            self.assertEqual(1, checks["total_tests"])
            self.assertEqual(0, checks["checks"][0]["exit_code"])
        self.assertNotEqual(builder["workspace"], verifier["workspace"])
        self.assertEqual(self.base, git(self.repository, "rev-parse", "HEAD"))
        self.assertEqual("", git(self.repository, "status", "--porcelain"))
        before = len(self.worker.calls)
        self.assertEqual("COMPLETED", self.execute(resume=True)["status"])
        self.assertEqual(before, len(self.worker.calls))
        test_output = Path(verifier["host_checks"]["checks"][0]["stderr_path"])
        test_output.write_bytes(b"tampered fixed-test evidence")
        with self.assertRaisesRegex(LocalAuthorityError, "deterministic test evidence changed"):
            self.execute(resume=True)
        self.assertEqual(before, len(self.worker.calls))

    def test_baseline_packet_contains_exact_host_verified_run_metadata(self) -> None:
        self.worker = PacketRecordingWorker()
        self.worker.failed_node = "BASELINE-001"
        self.service = LocalTournamentService(self.worker)
        self.execute()
        self.assertEqual(1, len(self.worker.calls))
        packet = self.worker.calls[0]["source_packet"]
        binding = packet["run_binding"]
        plan = json.loads((self.bundle / "plan.json").read_bytes())
        request = self.request.read_bytes()
        self.assertEqual(self.manifest["plan_digest"], binding["plan_digest"])
        self.assertEqual(plan["subject"], binding["subject"])
        self.assertEqual(plan["integration"], binding["integration"])
        self.assertEqual(request.decode("utf-8"), binding["original_request"]["text"])
        self.assertEqual(raw_sha256(request), binding["original_request"]["sha256"])
        self.assertEqual(request, Path(binding["original_request"]["path"]).read_bytes())
        self.assertEqual(raw_sha256(request), binding["operator_request_digest"])
        grant = LocalAuthorityStore(self.host).unseal(json.loads((self.state / "grant.json").read_bytes()))
        self.assertEqual(grant, binding["local_grant_verified_by_host"])
        self.assertEqual(str(self.brain.resolve()), binding["brain_directory"])
        self.assertEqual(self.base, binding["candidate_commit"])
        self.assertEqual(git(self.repository, "rev-parse", "HEAD^{tree}"), binding["candidate_tree"])
        self.assertTrue(self.brain.is_dir())

    def test_integrator_receives_actual_brain_publication_and_compact_court_context(self) -> None:
        self.worker = PacketRecordingWorker()
        self.service = LocalTournamentService(self.worker)
        captured = {}

        def inspect_at_dispatch(arguments, receipt):
            if arguments["node"]["node_id"] == "INTEGRATE-080":
                captured["arguments"] = arguments
                captured["files"] = {path.name: path.read_bytes() for path in self.brain.glob("*.md")}

        self.worker.after_call = inspect_at_dispatch
        result = self.execute()
        self.assertEqual("COMPLETED", result["status"])
        arguments, actual_files = captured["arguments"], captured["files"]
        self.assertEqual({"COURT-050", "JUDGE-075"}, {item["node_id"] for item in arguments["predecessor_reports"]})
        packet = arguments["source_packet"]
        self.assertLessEqual(packet["selected_content_bytes"], 60_000)
        delivery = packet["delivery_manifest"]
        self.assertTrue(Path(delivery["candidate_directory"]).samefile(self.state / "candidate"))
        self.assertEqual(self.base, delivery["base_commit"])
        self.assertEqual(result["candidate_commit"], delivery["candidate_commit"])
        self.assertEqual(git(arguments["workspace"], "rev-parse", "HEAD^{tree}"), delivery["candidate_tree"])
        self.assertEqual(packet["run_binding"]["candidate_tree"], delivery["candidate_tree"])
        actual_diff = git(arguments["workspace"], "diff", "--no-ext-diff", "--no-textconv", self.base, result["candidate_commit"], "--")
        self.assertTrue(actual_diff)
        self.assertEqual(actual_diff, delivery["diff_text"])
        self.assertEqual(raw_sha256(actual_diff.encode("utf-8")), delivery["diff_text_sha256"])
        verifier = next(event["workers"][0] for event in self.events() if event["kind"] == "node_completed" and event["node_id"] == "VERIFY-070")
        self.assertEqual(verifier["actor_id"], delivery["verifier_actor_id"])
        self.assertEqual(verifier["session_id"], delivery["verifier_session_id"])
        self.assertEqual(verifier["host_checks"], delivery["verification"])
        self.assertTrue(delivery["verification"]["all_passed"])
        self.assertFalse(delivery["promotion_authorized"])
        self.assertFalse(delivery["protected_merge_authorized"])
        self.assertTrue(delivery["rollback"])
        publication = packet["brain_publication"]
        self.assertEqual(str(self.brain.resolve()), publication["brain_directory"])
        self.assertEqual(publication["brain_directory"], packet["run_binding"]["brain_directory"])
        self.assertEqual(self.manifest["plan_digest"], packet["run_binding"]["plan_digest"])
        self.assertEqual(raw_sha256(self.request.read_bytes()), packet["run_binding"]["operator_request_digest"])
        self.assertIsNotNone(datetime.fromisoformat(publication["captured_at"]).tzinfo)
        self.assertTrue(publication["snapshot_consistent"])
        self.assertRegex(publication["snapshot_sha256"], r"^(?:sha256:)?[a-f0-9]{64}$")
        self.assertTrue(publication["index_and_idea_links_valid"])
        self.assertEqual([], publication["invalid_links"])
        self.assertEqual(["increment-result"], publication["canonical_idea_ids"])
        selected = {Path(item["path"]).name: item for item in publication["selected_files"]}
        idea_names = [name for name in selected if name.startswith("idea-")]
        self.assertEqual(1, len(idea_names))
        self.assertEqual({"INDEX.md", *idea_names}, set(selected))
        for name, entry in selected.items():
            with self.subTest(file=name):
                self.assertEqual(actual_files[name], entry["content"].encode("utf-8"))
                self.assertEqual(len(actual_files[name]), entry["size_bytes"])
                self.assertEqual(hashlib.sha256(actual_files[name]).hexdigest(), entry["sha256"])
        self.assertEqual(1, len(publication["indexed_ideas"]))
        indexed = publication["indexed_ideas"][0]
        self.assertEqual("increment-result", indexed["idea_id"])
        self.assertEqual(selected[idea_names[0]]["sha256"], indexed["sha256"])
        history = selected[idea_names[0]]["content"]
        for marker in ("CROSS-045", "COURT-050", "JUDGE-075", "Reason:", "Return to:", "Next action:"):
            self.assertIn(marker, history)
        trace_links = [link for link in publication["links"] if link["label"] == "Node evidence and result"]
        self.assertTrue(trace_links)
        for link in trace_links:
            target = (self.brain / link["resolved_path"]).resolve()
            self.assertTrue(target.is_relative_to(self.brain.resolve()))
            self.assertIn(target.name, actual_files)
            self.assertEqual(actual_files[target.name], target.read_bytes())
        self.assertIn("12/13", selected["INDEX.md"]["content"])
        self.assertIn("13/13", (self.brain / "INDEX.md").read_text(encoding="utf-8"))
        self.assertNotEqual(actual_files["INDEX.md"], (self.brain / "INDEX.md").read_bytes())

    def test_reused_worker_session_cannot_satisfy_independent_nodes(self) -> None:
        self.worker.duplicate_session = True
        result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual(1, result["completed_nodes"])
        reasons = [event.get("reason", "") for event in self.events() if event["kind"] == "node_failed"]
        self.assertTrue(reasons)
        self.assertTrue(all("session was reused" in reason for reason in reasons))

    def test_changed_raw_worker_evidence_prevents_resume(self) -> None:
        self.worker.failed_node = "BASELINE-001"
        self.execute()
        report = self.state / "workers" / "BASELINE-001" / "report.json"
        report.write_text('{"status":"completed"}', encoding="utf-8")
        with self.assertRaisesRegex(LocalAuthorityError, "worker evidence changed"):
            self.execute(resume=True)
        self.assertEqual(1, len(self.worker.calls))

    def test_tampered_signed_event_prevents_resume(self) -> None:
        self.worker.failed_node = "BASELINE-001"
        self.execute()
        path = self.state / "events" / "0002.json"
        event = json.loads(path.read_bytes())
        event["document"]["kind"] = "node_completed"
        path.write_text(json.dumps(event), encoding="utf-8")
        with self.assertRaisesRegex(LocalAuthorityError, "authentication failed"):
            self.execute(resume=True)
        self.assertEqual(1, len(self.worker.calls))

    def test_removed_event_tail_is_detected_by_external_custody_checkpoint(self) -> None:
        self.worker.failed_node = "BASELINE-001"
        self.execute()
        (self.state / "events" / "0002.json").unlink()
        with self.assertRaisesRegex(LocalAuthorityError, "event tail differs"):
            self.execute(resume=True)
        self.assertEqual(1, len(self.worker.calls))

    def test_started_intent_without_terminal_receipt_requires_recovery(self) -> None:
        self.worker.crash_node = "BASELINE-001"
        with self.assertRaises(SimulatedWorkerCrash):
            self.execute()
        self.assertEqual(["node_started"], [event["kind"] for event in self.events()])
        with self.assertRaisesRegex(LocalExecutionError, "RECOVERY_REQUIRED"):
            self.execute(resume=True)
        self.assertEqual(1, len(self.worker.calls))

    def test_rejected_in_repository_host_never_creates_a_secret_in_target(self) -> None:
        inside_host = self.repository / "host"
        with self.assertRaisesRegex((LocalAuthorityError, LocalExecutionError), "outside"):
            self.execute(host_directory=inside_host)
        self.assertFalse((inside_host / "local-host.key").exists())
        self.assertEqual("", git(self.repository, "status", "--porcelain"))
        self.assertEqual([], self.worker.calls)

    def test_deep_clone_enables_long_paths_and_retains_every_tracked_file(self) -> None:
        relative = Path("tracked-" + "x" * 120) / "evidence.txt"
        original = self.repository / relative
        original.parent.mkdir()
        original.write_bytes(b"Retain this file in a deep worker clone.\n")
        git(self.repository, "add", ".")
        git(self.repository, "commit", "-m", "Add long-path clone regression")
        commit = git(self.repository, "rev-parse", "HEAD")
        destination = self.root / ("nested-" + "a" * 60) / ("nested-" + "b" * 60) / "clone"
        destination.parent.mkdir(parents=True)
        self.assertGreater(len(str(destination / relative)), 260)
        _clone(self.repository, destination, commit)
        long_file = destination / relative
        if os.name == "nt":
            # Git's long-path opt-in is independent from Python's process manifest.
            long_file = Path("\\\\?\\" + str(long_file))
        try:
            self.assertEqual("true", git(destination, "config", "--get", "core.longpaths"))
            self.assertEqual(original.read_bytes(), long_file.read_bytes())
            self.assertEqual("", git(destination, "status", "--porcelain"))
        finally:
            # Keep TemporaryDirectory's ordinary Windows cleanup below MAX_PATH.
            long_file.unlink(missing_ok=True)
            long_file.parent.rmdir()

    def test_clone_enables_long_paths_before_git_creates_pack_files(self) -> None:
        calls: list[tuple[Path, tuple[str, ...]]] = []

        def record_call(directory: Path, *arguments: str) -> str:
            calls.append((directory, arguments))
            return ""

        destination = self.root / "mock-clone"
        with patch("hive_mind_os.local_dag_runtime._git", side_effect=record_call):
            _clone(self.repository, destination, "a" * 40)

        self.assertEqual(self.repository, calls[0][0])
        self.assertEqual(
            ("-c", "core.longpaths=true", "clone"),
            calls[0][1][:3],
        )

    def test_candidate_drift_blocks_resume_of_completed_run(self) -> None:
        self.execute()
        (self.state / "candidate" / "counter.py").write_text("unexpected change\n", encoding="utf-8")
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalExecutionError, "candidate drifted"):
            self.execute(resume=True)
        self.assertEqual(before, len(self.worker.calls))

    def test_builder_unreported_change_never_reaches_verifier(self) -> None:
        self.worker.changed_path_mismatch = True
        result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        self.assertNotIn("VERIFY-070", {call["node"]["node_id"] for call in self.worker.calls})
        failures = [event for event in self.events() if event["kind"] == "node_failed"]
        self.assertIn("changed-path receipt mismatch", failures[0]["reason"])
        self.assertEqual(self.base, git(self.state / "candidate", "rev-parse", "HEAD"))
        self.assertEqual("", git(self.repository, "status", "--porcelain"))

    def test_court_cannot_complete_while_omitting_a_proposed_idea(self) -> None:
        self.worker.omit_ideas_node = "COURT-050"
        result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        failed = [event for event in self.events() if event["kind"] == "node_failed"]
        self.assertEqual(["COURT-050"], [event["node_id"] for event in failed])
        self.assertIn("court omitted a proposed idea", failed[0]["reason"])
        self.assertNotIn("CHALLENGER-060", {call["node"]["node_id"] for call in self.worker.calls})
        self.assertEqual(self.base, git(self.state / "candidate", "rev-parse", "HEAD"))

    def test_court_cannot_select_an_idea_without_an_adopting_disposition(self) -> None:
        self.worker.invalid_selection_node = "COURT-050"
        result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        failed = [event for event in self.events() if event["kind"] == "node_failed"]
        self.assertEqual(["COURT-050"], [event["node_id"] for event in failed])
        self.assertIn("selected an idea without an adopt/adapt disposition", failed[0]["reason"])
        self.assertNotIn("CHALLENGER-060", {call["node"]["node_id"] for call in self.worker.calls})

    def test_result_judge_must_retain_the_proposed_idea_disposition(self) -> None:
        self.worker.omit_ideas_node = "JUDGE-075"
        result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        failed = [event for event in self.events() if event["kind"] == "node_failed"]
        self.assertEqual(["JUDGE-075"], [event["node_id"] for event in failed])
        self.assertNotIn("INTEGRATE-080", {call["node"]["node_id"] for call in self.worker.calls})

    def test_builder_cannot_edit_when_court_selected_no_experiment(self) -> None:
        self.worker.empty_selection_node = "COURT-050"
        result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        failed = [event for event in self.events() if event["kind"] == "node_failed"]
        self.assertEqual(["CHALLENGER-060"], [event["node_id"] for event in failed])
        self.assertIn("builder changed files without a selected experiment", failed[0]["reason"])
        self.assertNotIn("VERIFY-070", {call["node"]["node_id"] for call in self.worker.calls})
        self.assertEqual(self.base, git(self.state / "candidate", "rev-parse", "HEAD"))

    def test_changed_resume_configuration_and_plan_are_rejected_before_dispatch(self) -> None:
        self.worker.failed_node = "BASELINE-001"
        self.execute()
        with self.assertRaisesRegex(LocalAuthorityError, "configuration differs"):
            self.execute(resume=True, node_timeout=90)
        (self.state / "plan.json").write_bytes(b"changed plan bytes")
        with self.assertRaisesRegex(LocalAuthorityError, "stored plan inputs were changed"):
            self.execute(resume=True)
        self.assertEqual(1, len(self.worker.calls))

    def test_worker_timeout_cannot_exceed_remaining_operator_grant(self) -> None:
        self.worker.failed_node = "BASELINE-001"
        issue = LocalAuthorityStore.issue

        def short_grant(store, **arguments):
            arguments["duration_seconds"] = 60
            return issue(store, **arguments)

        with patch.object(LocalAuthorityStore, "issue", short_grant):
            self.execute(node_timeout=900)
        self.assertEqual(1, len(self.worker.calls))
        self.assertLessEqual(self.worker.calls[0]["timeout_seconds"], 60)

    def test_result_after_grant_expiry_is_never_recorded_completed(self) -> None:
        observed_now = [datetime.now(UTC)]

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return observed_now[0] if tz is not None else observed_now[0].replace(tzinfo=None)

        issue = LocalAuthorityStore.issue

        def short_grant(store, **arguments):
            arguments["duration_seconds"] = 60
            return issue(store, **arguments)

        def expire_after_execution(arguments, receipt):
            observed_now[0] += timedelta(seconds=61)

        self.worker.after_call = expire_after_execution
        with patch("hive_mind_os.local_dag_runtime.datetime", Clock), patch(
            "hive_mind_os.local_run_authority.datetime", Clock,
        ), patch.object(LocalAuthorityStore, "issue", short_grant):
            try:
                result = self.execute()
            except (LocalAuthorityError, LocalExecutionError):
                result = {"status": "BLOCKED"}
        self.assertEqual("BLOCKED", result["status"])
        self.assertFalse(any(event["kind"] == "node_completed" for event in self.events()))


if __name__ == "__main__":
    unittest.main()
