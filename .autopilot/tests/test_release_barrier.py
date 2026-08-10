from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

from autopilot import RECON_PREMATURE_RECEIPT, ControlPlane as CliControlPlane  # noqa: E402
from durable_controller import ClaimError  # noqa: E402
from release_barrier import ControlPlane  # noqa: E402

BASELINE = "7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23"
SECOND = "b" * 40
PLAN_FINGERPRINT = "sha256:9769f9796efb351da9b764fd49983b1130adccc0b8592e42581714d3727f8b39"


class DispatcherReleaseBarrierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source, self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(
            json.dumps(control, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.plane = ControlPlane(self.root)
        self.plane.reconcile(
            BASELINE,
            actor="test:dispatcher",
            reason="initial live reconciliation",
        )
        self._install_snapshot(BASELINE)
        self.real_base_status = self.plane._base_status
        self.plane._base_status = self._bounded_base_status  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _install_snapshot(self, target: str) -> None:
        source = self.root / "github-state-input.json"
        source.write_text(
            json.dumps(
                {
                    "target_sha": target,
                    "pull_requests": [],
                    "branches": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.plane.install_github_snapshot(source)

    def _bounded_base_status(self) -> dict[str, object]:
        nodes: list[dict[str, object]] = []
        for node_id in sorted(self.plane._nodes):
            if node_id == "BOOT-000":
                state = "COMPLETE"
            elif node_id in {"RECON-010", "BASE-020"}:
                state = "READY"
            else:
                state = "BLOCKED"
            nodes.append({"node_id": node_id, "state": state})
        return {
            "schema_version": 1,
            "plan_id": self.plane.plan.get("plan_id"),
            "plan_fingerprint": self.plane.expected_plan_fingerprint,
            "target_branch": "main",
            "target_sha": self.plane.current_target_sha(),
            "last_reconciled_sha": self.plane.reconciled_target_sha(),
            "reconciliation_required": self.plane.target_requires_reconciliation(),
            "changed_paths_since_reconciliation": [],
            "counts": {"COMPLETE": 1, "READY": 2, "BLOCKED": len(nodes) - 3},
            "ready": ["RECON-010", "BASE-020"],
            "nodes": nodes,
            "complete": False,
            "generated_at": "2030-01-01T00:00:00Z",
        }

    def _receipt_record(
        self,
        commit: str,
        *,
        supersedes: str | None = None,
    ) -> dict[str, object]:
        authority: dict[str, object] = {
            "autonomy_level": "A3",
            "node_id": "RECON-010",
        }
        if supersedes is not None:
            authority["supersedes_receipt_commit"] = supersedes
        return {
            "commit": commit,
            "receipt": {
                "schema_version": 1,
                "plan_fingerprint": PLAN_FINGERPRINT,
                "node_id": "RECON-010",
                "contract_version": 1,
                "base_commit": BASELINE,
                "base_tree": "a" * 40,
                "branch": "autopilot/recon-010",
                "pr": 122,
                "final_commit": "c" * 40,
                "authority": authority,
            },
        }

    def test_01_real_static_graph_reports_first_wave_but_release_layer_keeps_wait(self) -> None:
        base = self.real_base_status()
        self.assertEqual(set(base["ready"]), {"RECON-010", "BASE-020"})
        status = self.plane.status()
        self.assertEqual(status["ready"], [])
        self.assertEqual(status["dispatch_release"]["verdicts"]["RECON-010"], "WAIT")
        self.assertEqual(status["dispatch_release"]["verdicts"]["BASE-020"], "WAIT")
        self.assertEqual(
            status["dispatch_release"]["action"],
            "Do not open any worker sessions yet",
        )
        with self.assertRaises(ClaimError):
            self.plane.claim("RECON-010", "openai:test")

    def test_02_single_release_emits_exact_start_now(self) -> None:
        release = self.plane.dispatch(
            actor="test:dispatcher",
            requested_nodes=["RECON-010"],
        )
        self.assertEqual(release["directive"], "START NOW")
        self.assertEqual(release["released_wave"], ["RECON-010"])
        self.assertEqual(release["verdicts"]["RECON-010"], "START NOW")
        self.assertEqual(release["verdicts"]["BASE-020"], "WAIT")
        self.assertEqual(release["action"], "Open this 1 session now: RECON-010")
        self.assertEqual(self.plane.ready_nodes(), ("RECON-010",))

    def test_03_parallel_wave_requires_start_together_now(self) -> None:
        release = self.plane.dispatch(
            actor="test:dispatcher",
            requested_nodes=["RECON-010", "BASE-020"],
        )
        self.assertEqual(release["directive"], "START TOGETHER NOW")
        self.assertEqual(release["released_wave"], ["RECON-010", "BASE-020"])
        self.assertEqual(release["verdicts"]["RECON-010"], "START NOW")
        self.assertEqual(release["verdicts"]["BASE-020"], "START NOW")
        self.assertEqual(
            release["action"],
            "Open these 2 sessions now: RECON-010, BASE-020",
        )
        self.assertEqual(self.plane.ready_nodes(), ("RECON-010", "BASE-020"))

    def test_04_every_candidate_has_exactly_one_valid_verdict(self) -> None:
        release = self.plane.dispatch(actor="test:dispatcher")
        verdicts = release["verdicts"]
        self.assertEqual(set(verdicts), set(self.plane._nodes))
        self.assertTrue(
            set(verdicts.values()).issubset({"START NOW", "WAIT", "STOP"})
        )
        self.assertEqual(verdicts["BOOT-000"], "STOP")

    def test_05_target_advance_invalidates_release(self) -> None:
        self.plane.dispatch(
            actor="test:dispatcher",
            requested_nodes=["RECON-010"],
        )
        self._install_snapshot(SECOND)
        status = self.plane.status()
        self.assertFalse(status["dispatch_release"]["valid"])
        self.assertEqual(status["ready"], [])
        with self.assertRaises(ClaimError):
            self.plane.assert_start_now("RECON-010")

    def test_06_new_reconciliation_event_invalidates_release(self) -> None:
        self.plane.dispatch(
            actor="test:dispatcher",
            requested_nodes=["RECON-010"],
        )
        self.plane.reconcile(
            BASELINE,
            actor="test:dispatcher",
            reason="second reconciliation event invalidates prior release",
        )
        status = self.plane.status()
        self.assertFalse(status["dispatch_release"]["valid"])
        self.assertTrue(
            any(
                "reconciliation" in issue
                for issue in status["dispatch_release"]["issues"]
            )
        )

    def test_07_snapshot_change_invalidates_release(self) -> None:
        self.plane.dispatch(
            actor="test:dispatcher",
            requested_nodes=["RECON-010"],
        )
        source = self.root / "github-state-input-2.json"
        source.write_text(
            json.dumps(
                {
                    "target_sha": BASELINE,
                    "pull_requests": [{"number": 999, "state": "open"}],
                    "branches": [],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.plane.install_github_snapshot(source)
        status = self.plane.status()
        self.assertFalse(status["dispatch_release"]["valid"])
        self.assertTrue(
            any(
                "snapshot" in issue.lower()
                for issue in status["dispatch_release"]["issues"]
            )
        )

    def test_08_new_conflicting_claim_invalidates_release(self) -> None:
        self.plane.dispatch(
            actor="test:dispatcher",
            requested_nodes=["RECON-010"],
        )
        claim_path = self.plane.claim_path("BOOT-000")
        claim_path.parent.mkdir(parents=True, exist_ok=True)
        claim_path.write_text(
            json.dumps(
                {
                    "node_id": "BOOT-000",
                    "owner": "fixture:conflict",
                    "status": "RUNNING",
                    "expires_at": "2030-01-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        status = self.plane.status()
        self.assertFalse(status["dispatch_release"]["valid"])
        self.assertTrue(
            any(
                "conflicting claim" in issue
                for issue in status["dispatch_release"]["issues"]
            )
        )

    def test_09_nonconflicting_released_wave_claim_does_not_stale_sibling(self) -> None:
        self.plane.dispatch(
            actor="test:dispatcher",
            requested_nodes=["RECON-010", "BASE-020"],
        )
        claim = self.plane.claim("RECON-010", "openai:recon")
        self.assertEqual(claim["node_id"], "RECON-010")
        self.assertEqual(
            self.plane.assert_start_now("BASE-020")["directive"],
            "START TOGETHER NOW",
        )

    def test_10_authority_amendment_is_exact_and_plan_fingerprint_is_preserved(self) -> None:
        recon = self.plane.node("RECON-010")
        base = self.plane.node("BASE-020")
        self.assertIn(".autopilot/bin/release_barrier.py", recon["write_scope"])
        self.assertIn("dispatcher-release-barrier-tests", recon["required_tests"])
        self.assertNotIn(".autopilot/bin/release_barrier.py", base["write_scope"])
        self.assertEqual(self.plane.expected_plan_fingerprint, PLAN_FINGERPRINT)
        self.assertEqual(self.plane.authority_issues(), ())

    def test_11_authority_amendment_rejects_product_runtime_expansion(self) -> None:
        path = self.root / ".autopilot" / "authority-amendments.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["amendments"][0]["additional_write_scope"].append(
            "src/forbidden.py"
        )
        value["amendments"][0]["additional_file_locks"].append(
            "src/forbidden.py"
        )
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        plane = ControlPlane(self.root)
        self.assertTrue(
            any("product runtime" in issue for issue in plane.authority_issues())
        )
        self.assertNotIn("src/forbidden.py", plane.node("RECON-010")["write_scope"])

    def test_12_exact_premature_receipt_can_be_superseded_without_history_rewrite(self) -> None:
        plane = CliControlPlane(self.root)
        historical = self._receipt_record(RECON_PREMATURE_RECEIPT)
        replacement = self._receipt_record(
            "d" * 40,
            supersedes=RECON_PREMATURE_RECEIPT,
        )
        records = [historical, replacement]
        resolved = plane._resolve_recon_receipt_records(records)
        self.assertEqual(resolved, [replacement])
        self.assertEqual(records, [historical, replacement])

    def test_13_unbound_duplicate_receipts_remain_fail_closed(self) -> None:
        plane = CliControlPlane(self.root)
        historical = self._receipt_record(RECON_PREMATURE_RECEIPT)
        duplicate = self._receipt_record("d" * 40)
        records = [historical, duplicate]
        self.assertIs(plane._resolve_recon_receipt_records(records), records)


if __name__ == "__main__":
    unittest.main()
