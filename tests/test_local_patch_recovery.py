"""Recover an inert recorded patch with fake models and real isolated Git."""

from __future__ import annotations

import io
import json
import unittest
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from unittest.mock import patch

from hive_mind_os.dag_cli import build_dag_parser, run_dag_command
from hive_mind_os.local_dag_runtime import LocalExecutionError, LocalTournamentService
from hive_mind_os.local_evidence_packet import LocalEvidenceError
from hive_mind_os.local_run_authority import LocalAuthorityError
from hive_mind_os.runtime_contracts import raw_sha256
from tests import test_local_dag_runtime as fixtures
from tests.test_local_host_refresh import RecoverablePacketWorker


class RecordedPatchWorker(RecoverablePacketWorker):
    """Persist an explicitly fake model-only terminal receipt for recovery."""

    def run(self, **arguments):
        receipt = super().run(**arguments)
        receipt["execution_mode"] = "source-packet"
        if arguments["node"]["node_id"] == "CHALLENGER-060" and hasattr(self, "builder_usage"):
            receipt["usage"] = self.builder_usage
        (arguments["evidence_directory"] / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True), encoding="utf-8",
        )
        return receipt


class LocalPatchRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.LocalDagRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.worker = RecordedPatchWorker()
        self.fixture.worker = self.worker
        self.fixture.service = LocalTournamentService(self.worker, worker_mode="evidence-packet")
        self.current_host = raw_sha256(b"fake-host-before-patch-recovery")
        host_pin = patch(
            "hive_mind_os.local_dag_runtime.host_digest", side_effect=lambda: self.current_host,
        )
        host_pin.start()
        self.addCleanup(host_pin.stop)

    def execute(self, **arguments):
        return self.fixture.execute(**arguments)

    def change_host(self) -> None:
        self.current_host = raw_sha256(b"fake-host-with-corrected-patch-parser")

    def fail_host_patch(self, reason="git apply failed: error: corrupt patch at line 9"):
        with patch("hive_mind_os.local_evidence_packet.apply_proposed_patch", side_effect=LocalEvidenceError(reason)):
            result = self.execute()
        self.assertEqual("BLOCKED", result["status"])
        failures = [event for event in self.fixture.events() if event["kind"] == "node_failed"]
        self.assertEqual(["CHALLENGER-060"], [event["node_id"] for event in failures])
        self.assertEqual("completed", failures[0]["workers"][0]["status"])
        self.assertEqual("", fixtures.git(self.fixture.state / "candidate", "status", "--porcelain"))
        return failures[0]

    def test_recorded_patch_recovers_without_replaying_builder_or_prior_nodes(self) -> None:
        failure = self.fail_host_patch()
        original_grant_bytes = (self.fixture.state / "grant.json").read_bytes()
        original_grant = json.loads(original_grant_bytes)["document"]
        worker_dir = self.fixture.state / "workers/CHALLENGER-060"
        original_receipt_bytes = (worker_dir / "receipt.json").read_bytes()
        original_report_bytes = (worker_dir / "report.json").read_bytes()
        original_events = {path.name: path.read_bytes() for path in (self.fixture.state / "events").glob("*.json")}
        calls_before = Counter(call["node"]["node_id"] for call in self.worker.calls)
        self.change_host()
        result = self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual("COMPLETED", result["status"], [
            event.get("reason") for event in self.fixture.events() if event["kind"] == "node_failed"
        ])
        self.assertEqual(13, result["completed_nodes"])
        calls_after = Counter(call["node"]["node_id"] for call in self.worker.calls)
        for node, count in calls_before.items():
            with self.subTest(node=node):
                self.assertEqual(count, calls_after[node])
        self.assertEqual(1, calls_after["CHALLENGER-060"])
        events = self.fixture.events()
        intents = [event for event in events if event["kind"] == "host_patch_started"]
        self.assertEqual(1, len(intents))
        self.assertFalse(intents[0]["model_replayed"])
        self.assertEqual(
            raw_sha256(failure["workers"][0]["report"]["proposed_patch"].encode()),
            intents[0]["patch_digest"],
        )
        recovered = next(event for event in events if event["kind"] == "node_completed" and event["node_id"] == "CHALLENGER-060")
        self.assertFalse(recovered["model_replayed"])
        self.assertEqual(failure["sequence"], recovered["recovered_from_sequence"])
        self.assertEqual(failure["workers"][0]["session_id"], recovered["workers"][0]["session_id"])
        self.assertEqual(failure["workers"][0]["report"], recovered["workers"][0]["report"])
        self.assertEqual("applied", recovered["workers"][0]["host_patch"]["status"])
        self.assertTrue(recovered["workers"][0]["host_checks"]["all_passed"])
        self.assertEqual(original_grant_bytes, (self.fixture.state / "grant.json").read_bytes())
        self.assertEqual(original_receipt_bytes, (worker_dir / "receipt.json").read_bytes())
        self.assertEqual(original_report_bytes, (worker_dir / "report.json").read_bytes())
        for name, content in original_events.items():
            self.assertEqual(content, (self.fixture.state / "events" / name).read_bytes())
        update = next(event for event in events if event["kind"] == "host_updated")
        new_bytes = (self.fixture.state / update["grant_file"]).read_bytes()
        new_grant = json.loads(new_bytes)["document"]
        self.assertNotEqual(original_grant["nonce"], new_grant["nonce"])
        self.assertEqual(raw_sha256(original_grant_bytes), update["previous_grant_digest"])
        self.assertEqual(raw_sha256(new_bytes), update["grant_digest"])
        self.assertLessEqual(datetime.fromisoformat(new_grant["expires_at"]), datetime.fromisoformat(original_grant["expires_at"]))
        before = len(self.worker.calls)
        self.assertEqual(result, self.execute(resume=True))
        with self.assertRaises(LocalExecutionError):
            self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual("", fixtures.git(self.fixture.repository, "status", "--porcelain"))
        self.assertEqual(self.fixture.base, fixtures.git(self.fixture.repository, "rev-parse", "HEAD"))

    def test_dirty_candidate_refuses_patch_recovery(self) -> None:
        self.fail_host_patch()
        (self.fixture.state / "candidate/counter.py").write_text("unexpected change\n", encoding="utf-8")
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalExecutionError, "candidate drifted"):
            self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_tampered_recorded_patch_refuses_recovery(self) -> None:
        self.fail_host_patch()
        (self.fixture.state / "workers/CHALLENGER-060/report.json").write_text("changed patch", encoding="utf-8")
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalAuthorityError, "worker evidence changed"):
            self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_nonparse_builder_failure_is_not_admitted(self) -> None:
        self.fail_host_patch("git apply failed: error: patch failed: counter.py:2")
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaises(LocalExecutionError):
            self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_interrupted_host_patch_intent_cannot_be_replayed(self) -> None:
        self.fail_host_patch()
        self.change_host()
        before = len(self.worker.calls)
        with patch("hive_mind_os.local_evidence_packet.apply_proposed_patch", side_effect=fixtures.SimulatedWorkerCrash()):
            with self.assertRaises(fixtures.SimulatedWorkerCrash):
                self.execute(resume=True, recover_recorded_patch=True)
        events = self.fixture.events()
        self.assertEqual("host_patch_started", events[-1]["kind"])
        self.assertEqual("", fixtures.git(self.fixture.state / "candidate", "status", "--porcelain"))
        with self.assertRaisesRegex(LocalExecutionError, "RECOVERY_REQUIRED"):
            self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual(before, len(self.worker.calls))

    def test_expired_grant_refuses_recorded_patch_effects(self) -> None:
        self.fail_host_patch()
        grant = json.loads((self.fixture.state / "grant.json").read_bytes())["document"]
        expired = datetime.fromisoformat(grant["expires_at"]) + timedelta(seconds=1)
        self.change_host()
        before = len(self.worker.calls)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return expired if tz is not None else expired.replace(tzinfo=None)

        with patch("hive_mind_os.local_dag_runtime.datetime", Clock), patch("hive_mind_os.local_run_authority.datetime", Clock):
            with self.assertRaisesRegex(LocalAuthorityError, "not currently valid"):
                self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))
        self.assertEqual("", fixtures.git(self.fixture.state / "candidate", "status", "--porcelain"))

    def test_recovery_flags_cannot_be_combined(self) -> None:
        with self.assertRaises(LocalExecutionError):
            self.execute(resume=True, refresh_local_host=True, recover_recorded_patch=True)
        self.assertEqual([], self.worker.calls)

    def test_original_builder_usage_is_checked_before_patch_recovery(self) -> None:
        self.worker.builder_usage = {"input_tokens": 1_000_000, "output_tokens": 5}
        self.fail_host_patch()
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalExecutionError, "cumulative measured input_tokens"):
            self.execute(resume=True, recover_recorded_patch=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))
        self.assertEqual("", fixtures.git(self.fixture.state / "candidate", "status", "--porcelain"))

    def test_cli_forwards_only_explicit_recorded_patch_recovery(self) -> None:
        args = build_dag_parser().parse_args([
            "resume", "--runtime", "local", "--recover-recorded-patch",
            "--plan", str(self.fixture.bundle / "plan.json"), "--standard", str(self.fixture.standard),
            "--expected-plan-digest", self.fixture.manifest["plan_digest"],
            "--state-directory", str(self.fixture.state), "--repository", str(self.fixture.repository),
            "--host-directory", str(self.fixture.host), "--operator-request-file", str(self.fixture.request),
            "--brain-directory", str(self.fixture.brain),
        ])
        with patch.object(LocalTournamentService, "execute", return_value={"status": "BLOCKED"}) as execute:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(2, run_dag_command(args))
        self.assertIs(True, execute.call_args.kwargs["recover_recorded_patch"])
        self.assertIs(True, execute.call_args.kwargs["resume"])
        self.assertIs(False, execute.call_args.kwargs["refresh_local_host"])
        self.assertFalse(self.fixture.host.exists())


if __name__ == "__main__":
    unittest.main()
