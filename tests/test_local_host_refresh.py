"""Local recovery integration with explicitly fake model responses."""

from __future__ import annotations

import json
import unittest
from collections import Counter
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from hive_mind_os.local_dag_runtime import LocalExecutionError, LocalTournamentService
from hive_mind_os.local_run_authority import LocalAuthorityError
from hive_mind_os.runtime_contracts import raw_sha256
from tests import test_local_dag_runtime as fixtures


class RecoverablePacketWorker(fixtures.PacketRecordingWorker):
    """No model calls: simulate clean, terminal read-only model blockers."""

    def __init__(self):
        super().__init__()
        self.usage = {"input_tokens": 10, "output_tokens": 5}

    def run(self, **arguments):
        started = datetime.now(UTC)
        receipt = super().run(**arguments)
        blocked = receipt["report"]["status"] == "blocked"
        receipt.update(
            status="blocked" if blocked else "completed",
            reason="Fixture model needs the refreshed host evidence." if blocked else None,
            exit_code=0,
            sandbox="read-only",
            session_id=f"fixture:{arguments['evidence_directory'].name}",
            started_at=started.isoformat(),
            finished_at=(started + timedelta(milliseconds=10)).isoformat(),
            usage=dict(self.usage),
        )
        (arguments["evidence_directory"] / "receipt.json").write_text(
            json.dumps(receipt, sort_keys=True), encoding="utf-8",
        )
        return receipt


class LocalHostRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.LocalDagRuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.worker = RecoverablePacketWorker()
        self.fixture.worker = self.worker
        self.fixture.service = LocalTournamentService(self.worker, worker_mode="evidence-packet")
        self.current_host = raw_sha256(b"fake-host-before-refresh")
        host_pin = patch(
            "hive_mind_os.local_dag_runtime.host_digest", side_effect=lambda: self.current_host,
        )
        host_pin.start()
        self.addCleanup(host_pin.stop)

    def execute(self, **arguments):
        return self.fixture.execute(**arguments)

    def change_host(self, version: int = 1) -> None:
        self.current_host = raw_sha256(f"fake-host-refresh-{version}".encode())

    def block(self, node: str = "BASELINE-001") -> None:
        self.worker.failed_node = node
        self.assertEqual("BLOCKED", self.execute()["status"])

    def test_refresh_reuses_completed_nodes_preserves_grant_and_never_replays(self) -> None:
        self.block("CROSS-045")
        original_grant_path = self.fixture.state / "grant.json"
        original_bytes = original_grant_path.read_bytes()
        original_grant = json.loads(original_bytes)["document"]
        original_report = self.fixture.state / "workers/CROSS-045/report.json"
        original_report_bytes = original_report.read_bytes()
        completed = {
            event["node_id"] for event in self.fixture.events() if event["kind"] == "node_completed"
        }
        calls_before = Counter(call["node"]["node_id"] for call in self.worker.calls)
        self.worker.failed_node = None
        self.change_host()
        result = self.execute(resume=True, refresh_local_host=True)
        self.assertEqual("COMPLETED", result["status"])
        self.assertEqual(13, result["completed_nodes"])
        calls_after = Counter(call["node"]["node_id"] for call in self.worker.calls)
        for node in completed:
            with self.subTest(node=node):
                self.assertEqual(calls_before[node], calls_after[node])
        cross_calls = [call for call in self.worker.calls if call["node"]["node_id"] == "CROSS-045"]
        self.assertEqual(2, len(cross_calls))
        self.assertNotEqual(cross_calls[0]["workspace"], cross_calls[1]["workspace"])
        self.assertNotEqual(cross_calls[0]["evidence_directory"], cross_calls[1]["evidence_directory"])
        self.assertNotEqual(cross_calls[0]["actor_id"], cross_calls[1]["actor_id"])
        updates = [event for event in self.fixture.events() if event["kind"] == "host_updated"]
        self.assertEqual(1, len(updates))
        update = updates[0]
        new_bytes = (self.fixture.state / update["grant_file"]).read_bytes()
        refreshed = json.loads(new_bytes)["document"]
        self.assertEqual(original_bytes, original_grant_path.read_bytes())
        self.assertEqual(original_report_bytes, original_report.read_bytes())
        self.assertNotEqual(original_grant["nonce"], refreshed["nonce"])
        self.assertLessEqual(
            datetime.fromisoformat(refreshed["expires_at"]),
            datetime.fromisoformat(original_grant["expires_at"]),
        )
        self.assertEqual(raw_sha256(original_bytes), update["previous_grant_digest"])
        self.assertEqual(raw_sha256(new_bytes), update["grant_digest"])
        for field in ("plan_digest", "repository", "commit", "tree", "state_directory",
                      "operator_request_digest", "allowed_actions"):
            self.assertEqual(original_grant[field], refreshed[field])
        before = len(self.worker.calls)
        self.assertEqual(result, self.execute(resume=True))
        self.assertEqual(before, len(self.worker.calls))

    def test_plain_resume_cannot_silently_change_host(self) -> None:
        self.block()
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalAuthorityError, "binding differs"):
            self.execute(resume=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_wrong_expected_binding_prevents_host_initialization(self) -> None:
        for field in ("expected_request_id", "expected_subject_id"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.execute(**{field: "different-expected-identity"})
        self.assertFalse(self.fixture.host.exists())
        self.assertFalse(self.fixture.state.exists())
        self.assertEqual([], self.worker.calls)

    def test_tampered_prior_worker_evidence_prevents_host_refresh(self) -> None:
        self.block()
        (self.fixture.state / "workers/BASELINE-001/report.json").write_text("changed", encoding="utf-8")
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalAuthorityError, "worker evidence changed"):
            self.execute(resume=True, refresh_local_host=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_unfinished_worker_intent_cannot_be_refreshed(self) -> None:
        self.worker.crash_node = "BASELINE-001"
        with self.assertRaises(fixtures.SimulatedWorkerCrash):
            self.execute()
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalExecutionError, "RECOVERY_REQUIRED"):
            self.execute(resume=True, refresh_local_host=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_even_clean_builder_blocker_cannot_be_refreshed(self) -> None:
        self.block("CHALLENGER-060")
        self.assertEqual("", fixtures.git(self.fixture.state / "candidate", "status", "--porcelain"))
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalExecutionError, "uncertain or writing effects"):
            self.execute(resume=True, refresh_local_host=True)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_repeated_clean_blockers_exhaust_three_attempts(self) -> None:
        self.block()
        for version in (1, 2):
            self.change_host(version)
            self.assertEqual("BLOCKED", self.execute(resume=True, refresh_local_host=True)["status"])
        calls = list(self.worker.calls)
        self.assertEqual(3, len(calls))
        self.assertEqual(3, len({call["evidence_directory"] for call in calls}))
        self.change_host(3)
        with self.assertRaisesRegex(LocalExecutionError, "retry budget is exhausted"):
            self.execute(resume=True, refresh_local_host=True)
        self.assertEqual(3, len(self.worker.calls))

    def test_refresh_cannot_change_saved_execution_configuration(self) -> None:
        self.block()
        self.change_host()
        before = len(self.worker.calls)
        with self.assertRaisesRegex(LocalAuthorityError, "configuration differs"):
            self.execute(resume=True, refresh_local_host=True, node_timeout=90)
        self.assertEqual(before, len(self.worker.calls))
        self.assertEqual([], list(self.fixture.state.glob("grant-*.json")))

    def test_retry_token_usage_accumulates_instead_of_resetting(self) -> None:
        plan = json.loads((self.fixture.bundle / "plan.json").read_bytes())
        baseline = next(node for node in plan["nodes"] if node["node_id"] == "BASELINE-001")
        budget = next(item["policy"] for item in plan["budgets"] if item["budget_id"] == baseline["budget_id"])
        per_attempt = budget["input_tokens"] // 2 + 1
        self.worker.usage = {"input_tokens": per_attempt, "output_tokens": 5}
        self.block()
        self.change_host()
        result = self.execute(resume=True, refresh_local_host=True)
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual(2, len(self.worker.calls))
        failures = [event for event in self.fixture.events() if event["kind"] == "node_failed"]
        self.assertIn("cumulative measured input_tokens", failures[-1]["reason"])
        self.assertEqual(per_attempt, failures[-1]["workers"][0]["usage"]["input_tokens"])

    def test_grant_signing_delay_cannot_extend_original_expiry(self) -> None:
        self.block()
        old_grant = json.loads((self.fixture.state / "grant.json").read_bytes())["document"]
        self.change_host()

        class SigningClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz) + timedelta(seconds=5)

        with patch("hive_mind_os.local_run_authority.datetime", SigningClock):
            self.assertEqual("BLOCKED", self.execute(resume=True, refresh_local_host=True)["status"])
        update = next(event for event in self.fixture.events() if event["kind"] == "host_updated")
        refreshed = json.loads((self.fixture.state / update["grant_file"]).read_bytes())["document"]
        self.assertLessEqual(
            datetime.fromisoformat(refreshed["expires_at"]),
            datetime.fromisoformat(old_grant["expires_at"]),
        )

    def test_exhausted_cumulative_wall_budget_never_dispatches_retry(self) -> None:
        observed = [datetime.now(UTC)]

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return observed[0] if tz is not None else observed[0].replace(tzinfo=None)

        def finish_after_budget(arguments, receipt):
            observed[0] += timedelta(seconds=61)

        self.worker.after_call = finish_after_budget
        with patch("hive_mind_os.local_dag_runtime.datetime", Clock), patch(
            "hive_mind_os.local_run_authority.datetime", Clock,
        ):
            self.block()
            self.change_host()
            with self.assertRaisesRegex(LocalExecutionError, "cumulative node wall budget"):
                self.execute(resume=True, refresh_local_host=True)
        self.assertEqual(1, len(self.worker.calls))


if __name__ == "__main__":
    unittest.main()
