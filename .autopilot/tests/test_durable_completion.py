from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import durable_controller as durable  # noqa: E402

BASELINE = "7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23"
SECOND = "b" * 40
THIRD = "c" * 40
BASE_TREE = "d" * 40
FINAL_TREE = "e" * 40


class DurableCompletionTests(unittest.TestCase):
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
        self.plane = durable.ControlPlane(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def concrete_path(scope: str) -> str:
        path = scope.removesuffix("/**").replace("*", "artifact")
        if scope.endswith("/**"):
            path += "/artifact.txt"
        return path

    def receipt(self, node_id: str) -> dict:
        node = self.plane.node(node_id)
        changed = [self.concrete_path(node["write_scope"][0])]
        return {
            "schema_version": 1,
            "plan_fingerprint": self.plane.expected_plan_fingerprint,
            "node_id": node_id,
            "contract_version": node["contract_version"],
            "base_commit": BASELINE,
            "base_tree": BASE_TREE,
            "final_commit": SECOND,
            "final_tree": FINAL_TREE,
            "branch": node["branch"],
            "pr": 321,
            "changed_paths": changed,
            "tests": [
                {"name": name, "status": "passed", "command": ["python", "-m", "unittest"]}
                for name in node["required_tests"]
            ],
            "evidence_refs": ["evidence:test"],
            "model_runtime": {"provider": "fixture", "model": "fixture"},
            "role_identities": [
                {
                    "role": role,
                    "identity": f"role:{role}",
                    "identity_kind": "model_role",
                }
                for role in node["roles"]
            ],
            "authority": {
                "node_id": node_id,
                "autonomy_level": "A3",
                "grants": ["repository"],
            },
            "consultations": [],
            "acceptance_decision": "ADOPT",
            "timestamp": "2030-01-01T00:00:00Z",
            "rollback_ref": "revert:fixture",
        }

    def test_01_fresh_checkout_reconstructs_bootstrap_completion(self) -> None:
        self.assertEqual(self.plane.node_view("BOOT-000").state, "COMPLETE")
        self.assertTrue(self.plane.completed("BOOT-000"))
        self.assertEqual(self.plane.node_view("BOOT-000").branch, "agent/bootstrap-autopilot-control-plane")
        self.assertEqual(self.plane.node_view("BOOT-000").pr_number, 120)

    def test_02_ready_releases_exact_first_wave_after_bootstrap(self) -> None:
        self.assertEqual(set(self.plane.ready_nodes()), {"RECON-010", "BASE-020"})

    def test_03_missing_bootstrap_attestation_fails_closed(self) -> None:
        self.plane.bootstrap_attestation_path.unlink()
        self.assertEqual(self.plane.node_view("BOOT-000").state, "BOOTSTRAP_REQUIRED")

    def test_04_tampered_bootstrap_plan_fails_closed(self) -> None:
        value = json.loads(self.plane.bootstrap_attestation_path.read_text(encoding="utf-8"))
        value["plan_fingerprint"] = "sha256:" + "0" * 64
        self.plane.bootstrap_attestation_path.write_text(json.dumps(value), encoding="utf-8")
        view = self.plane.node_view("BOOT-000")
        self.assertEqual(view.state, "BOOTSTRAP_INVALID")
        self.assertIn("fingerprint", view.reasons[0])

    def test_05_actual_branch_provenance_cannot_be_normalized(self) -> None:
        value = json.loads(self.plane.bootstrap_attestation_path.read_text(encoding="utf-8"))
        value["actual_branch"] = value["planned_branch"]
        self.plane.bootstrap_attestation_path.write_text(json.dumps(value), encoding="utf-8")
        view = self.plane.node_view("BOOT-000")
        self.assertEqual(view.state, "BOOTSTRAP_INVALID")
        self.assertIn("actual_branch", view.reasons[0])

    def test_06_bootstrap_tree_mismatch_fails_closed(self) -> None:
        value = json.loads(self.plane.bootstrap_attestation_path.read_text(encoding="utf-8"))
        value["candidate_tree"] = "f" * 40
        self.plane.bootstrap_attestation_path.write_text(json.dumps(value), encoding="utf-8")
        view = self.plane.node_view("BOOT-000")
        self.assertEqual(view.state, "BOOTSTRAP_INVALID")
        self.assertIn("candidate_tree", view.reasons[0])

    def test_07_pr_or_status_prose_alone_never_proves_bootstrap_complete(self) -> None:
        self.plane.bootstrap_attestation_path.unlink()
        durable.atomic_write_json(
            self.plane.state_dir / "github-state.json",
            {
                "target_sha": BASELINE,
                "pull_requests": [
                    {
                        "node_id": "BOOT-000",
                        "number": 120,
                        "state": "closed",
                        "merged": True,
                        "ci": "success",
                        "title": "BOOT-000 COMPLETE everything passed",
                    }
                ],
                "branches": [
                    {"name": "autopilot/boot-000", "stale": False}
                ],
            },
        )
        self.assertEqual(self.plane.node_view("BOOT-000").state, "BOOTSTRAP_REQUIRED")

    def test_08_future_durable_receipt_survives_deleted_local_state(self) -> None:
        receipt = self.receipt("BASE-020")
        durable_path = self.plane.durable_receipt_path("BASE-020")
        durable.atomic_write_json(durable_path, receipt)
        self.assertEqual(self.plane.node_view("BASE-020").state, "COMPLETE")
        shutil.rmtree(self.plane.state_dir, ignore_errors=True)
        fresh = durable.ControlPlane(self.root)
        self.assertEqual(fresh.node_view("BOOT-000").state, "COMPLETE")
        self.assertEqual(fresh.node_view("BASE-020").state, "COMPLETE")

    def test_09_wrong_plan_future_receipt_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        receipt["plan_fingerprint"] = "sha256:" + "0" * 64
        durable.atomic_write_json(self.plane.durable_receipt_path("BASE-020"), receipt)
        self.assertEqual(self.plane.node_view("BASE-020").state, "REPAIR_REQUIRED")

    def test_10_wrong_branch_future_receipt_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        receipt["branch"] = "not/the/node/branch"
        durable.atomic_write_json(self.plane.durable_receipt_path("BASE-020"), receipt)
        view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("branch", view.reasons[0])

    def test_11_out_of_scope_future_receipt_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        receipt["changed_paths"] = ["src/unauthorized.py"]
        durable.atomic_write_json(self.plane.durable_receipt_path("BASE-020"), receipt)
        view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("outside node write scope", view.reasons[0])

    def test_12_missing_tree_binding_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        del receipt["final_tree"]
        durable.atomic_write_json(self.plane.durable_receipt_path("BASE-020"), receipt)
        view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("final_tree", view.reasons[0])

    def test_13_wrong_commit_tree_binding_is_rejected(self) -> None:
        receipt = self.receipt("BASE-020")
        self.plane.control["verify_git_objects"] = True
        with (
            mock.patch.object(self.plane, "git_object_exists", return_value=True),
            mock.patch.object(
                self.plane,
                "_commit_tree",
                side_effect=lambda commit: BASE_TREE if commit == BASELINE else "9" * 40,
            ),
            mock.patch.object(self.plane, "is_ancestor", return_value=True),
            mock.patch.object(self.plane, "current_target_sha", return_value=THIRD),
        ):
            issues = self.plane.validate_receipt("BASE-020", receipt, require_integrated=True)
        self.assertIn("receipt final_tree does not match final_commit", issues)

    def test_14_non_integrated_future_receipt_is_rejected(self) -> None:
        receipt = self.receipt("BASE-020")
        self.plane.control["verify_git_objects"] = True

        def ancestor(first: str, second: str) -> bool:
            if first == BASELINE and second == SECOND:
                return True
            if first == SECOND and second == THIRD:
                return False
            return True

        with (
            mock.patch.object(self.plane, "git_object_exists", return_value=True),
            mock.patch.object(
                self.plane,
                "_commit_tree",
                side_effect=lambda commit: BASE_TREE if commit == BASELINE else FINAL_TREE,
            ),
            mock.patch.object(self.plane, "is_ancestor", side_effect=ancestor),
            mock.patch.object(self.plane, "current_target_sha", return_value=THIRD),
        ):
            issues = self.plane.validate_receipt("BASE-020", receipt, require_integrated=True)
        self.assertIn("receipt final commit is not integrated into target history", issues)

    def test_15_tampered_local_receipt_cannot_hide_behind_durable_copy(self) -> None:
        receipt = self.receipt("BASE-020")
        durable.atomic_write_json(self.plane.durable_receipt_path("BASE-020"), receipt)
        tampered = copy.deepcopy(receipt)
        tampered["branch"] = "tampered/local"
        durable.atomic_write_json(self.plane.receipt_path("BASE-020"), tampered)
        view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("invalid local completion receipt", view.reasons[0])

    def test_16_every_future_node_has_node_owned_durable_receipt_scope(self) -> None:
        for node in self.plane.nodes():
            node_id = str(node["id"])
            if node_id == "BOOT-000":
                continue
            path = self.plane.durable_receipt_path(node_id)
            relative = path.relative_to(self.root).as_posix()
            self.assertTrue(relative.startswith("evidence/"), node_id)
            self.assertTrue(relative.endswith("/autopilot-completion-receipt.json"), node_id)


if __name__ == "__main__":
    unittest.main()
