from __future__ import annotations

import copy
import json
import shutil
import subprocess
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

    def git(self, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            text=True,
            capture_output=True,
        )
        return completed.stdout.strip()

    @staticmethod
    def concrete_path(scope: str) -> str:
        path = scope.removesuffix("/**").replace("*", "artifact")
        if scope.endswith("/**"):
            path += "/artifact.txt"
        return path

    def receipt(
        self,
        node_id: str,
        *,
        base_commit: str = BASELINE,
        base_tree: str = BASE_TREE,
        final_commit: str = SECOND,
        final_tree: str = FINAL_TREE,
        changed_paths: list[str] | None = None,
    ) -> dict:
        node = self.plane.node(node_id)
        changed = changed_paths or [self.concrete_path(node["write_scope"][0])]
        return {
            "schema_version": 1,
            "plan_fingerprint": self.plane.expected_plan_fingerprint,
            "node_id": node_id,
            "contract_version": node["contract_version"],
            "base_commit": base_commit,
            "base_tree": base_tree,
            "final_commit": final_commit,
            "final_tree": final_tree,
            "branch": node["branch"],
            "pr": 321,
            "changed_paths": changed,
            "tests": [
                {
                    "name": name,
                    "status": "passed",
                    "command": ["python", "-m", "unittest"],
                }
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

    @staticmethod
    def record(receipt: dict) -> dict:
        return {
            "commit": "a" * 40,
            "parents": (receipt["final_commit"],),
            "tree": receipt["final_tree"],
            "receipt": receipt,
        }

    def test_01_fresh_checkout_reconstructs_bootstrap_completion(self) -> None:
        view = self.plane.node_view("BOOT-000")
        self.assertEqual(view.state, "COMPLETE")
        self.assertTrue(self.plane.completed("BOOT-000"))
        self.assertEqual(view.branch, "agent/bootstrap-autopilot-control-plane")
        self.assertEqual(view.pr_number, 120)

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

    def test_07_bootstrap_outside_sealed_historical_scope_fails_closed(self) -> None:
        value = json.loads(self.plane.bootstrap_attestation_path.read_text(encoding="utf-8"))
        value["changed_paths"].append("src/unauthorized.py")
        self.plane.bootstrap_attestation_path.write_text(json.dumps(value), encoding="utf-8")
        view = self.plane.node_view("BOOT-000")
        self.assertEqual(view.state, "BOOTSTRAP_INVALID")
        self.assertIn("outside sealed historical scope", view.reasons[0])

    def test_08_pr_title_branch_or_status_alone_never_proves_bootstrap_complete(self) -> None:
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
                "branches": [{"name": "autopilot/boot-000", "stale": False}],
            },
        )
        self.assertEqual(self.plane.node_view("BOOT-000").state, "BOOTSTRAP_REQUIRED")

    def test_09_future_receipt_commit_survives_deleted_local_state(self) -> None:
        target_branch = self.plane.target_branch
        self.git("init", "-b", target_branch)
        self.git("config", "user.name", "Autopilot Test")
        self.git("config", "user.email", "autopilot-test@example.invalid")
        self.git("add", ".autopilot")
        self.git("commit", "-m", "synthetic baseline")
        base = self.git("rev-parse", "HEAD")
        base_tree = self.git("rev-parse", "HEAD^{tree}")

        branch = "autopilot/base-020"
        self.git("checkout", "-b", branch)
        claim_message = json.dumps(
            {
                "branch": branch,
                "expires_at": "2099-01-01T00:00:00Z",
                "kind": durable.REMOTE_CLAIM_KIND,
                "node_id": "BASE-020",
                "owner": "fixture:session",
                "plan_fingerprint": self.plane.expected_plan_fingerprint,
                "target_sha": base,
            },
            sort_keys=True,
        )
        self.git("commit", "--allow-empty", "-m", claim_message)

        evidence = self.root / "docs" / "execution" / "AUTONOMY_BASELINE.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("synthetic baseline evidence\n", encoding="utf-8")
        self.git("add", evidence.relative_to(self.root).as_posix())
        self.git("commit", "-m", "capture synthetic autonomy baseline")
        final = self.git("rev-parse", "HEAD")
        final_tree = self.git("rev-parse", "HEAD^{tree}")

        receipt = self.receipt(
            "BASE-020",
            base_commit=base,
            base_tree=base_tree,
            final_commit=final,
            final_tree=final_tree,
            changed_paths=["docs/execution/AUTONOMY_BASELINE.md"],
        )
        durable.atomic_write_json(
            self.plane.claim_path("BASE-020"),
            {
                "node_id": "BASE-020",
                "owner": "fixture:session",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        receipt_commit = self.plane.complete("BASE-020", "fixture:session", receipt)
        self.assertEqual(self.git("rev-parse", "HEAD"), receipt_commit)
        self.assertEqual(self.git("rev-parse", f"{receipt_commit}^{{tree}}"), final_tree)
        self.assertEqual(self.git("diff", "--name-only", f"{final}..{receipt_commit}"), "")

        self.git("checkout", target_branch)
        self.git("merge", "--no-ff", branch, "-m", "merge synthetic BASE-020")
        shutil.rmtree(self.plane.state_dir, ignore_errors=True)

        fresh = durable.ControlPlane(self.root)
        self.assertEqual(fresh.node_view("BASE-020").state, "COMPLETE")

    def test_10_wrong_plan_durable_receipt_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        receipt["plan_fingerprint"] = "sha256:" + "0" * 64
        with mock.patch.object(
            self.plane,
            "_durable_receipt_records",
            return_value={"BASE-020": [self.record(receipt)]},
        ):
            self.assertEqual(self.plane.node_view("BASE-020").state, "REPAIR_REQUIRED")

    def test_11_wrong_branch_durable_receipt_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        receipt["branch"] = "not/the/node/branch"
        with mock.patch.object(
            self.plane,
            "_durable_receipt_records",
            return_value={"BASE-020": [self.record(receipt)]},
        ):
            view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("branch", view.reasons[0])

    def test_12_out_of_scope_durable_receipt_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        receipt["changed_paths"] = ["src/unauthorized.py"]
        with mock.patch.object(
            self.plane,
            "_durable_receipt_records",
            return_value={"BASE-020": [self.record(receipt)]},
        ):
            view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("outside node write scope", view.reasons[0])

    def test_13_missing_tree_binding_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        del receipt["final_tree"]
        record = self.record({**receipt, "final_tree": FINAL_TREE})
        record["receipt"] = receipt
        with mock.patch.object(
            self.plane,
            "_durable_receipt_records",
            return_value={"BASE-020": [record]},
        ):
            view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("final_tree", view.reasons[0])

    def test_14_receipt_commit_parent_or_tree_mismatch_fails_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        bad_record = self.record(receipt)
        bad_record["parents"] = (THIRD,)
        bad_record["tree"] = "9" * 40
        with mock.patch.object(
            self.plane,
            "_durable_receipt_records",
            return_value={"BASE-020": [bad_record]},
        ):
            view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("exactly the final candidate as parent", view.reasons[0])
        self.assertIn("tree differs", view.reasons[0])

    def test_15_non_integrated_future_receipt_is_rejected(self) -> None:
        receipt = self.receipt("BASE-020")
        self.plane.control["verify_git_objects"] = True

        def ancestor(first: str, second: str) -> bool:
            if first == BASELINE and second == SECOND:
                return True
            if first == SECOND and second == THIRD:
                return False
            return True

        with (
            mock.patch.object(self.plane, "_has_git_repository", return_value=True),
            mock.patch.object(self.plane, "git_object_exists", return_value=True),
            mock.patch.object(
                self.plane,
                "_commit_tree",
                side_effect=lambda commit: BASE_TREE if commit == BASELINE else FINAL_TREE,
            ),
            mock.patch.object(self.plane, "_diff_paths", return_value=tuple(receipt["changed_paths"])),
            mock.patch.object(self.plane, "is_ancestor", side_effect=ancestor),
            mock.patch.object(self.plane, "current_target_sha", return_value=THIRD),
        ):
            issues = self.plane.validate_receipt("BASE-020", receipt, require_integrated=True)
        self.assertIn("receipt final commit is not integrated into target history", issues)

    def test_16_tampered_local_receipt_cannot_hide_behind_durable_commit(self) -> None:
        receipt = self.receipt("BASE-020")
        tampered = copy.deepcopy(receipt)
        tampered["branch"] = "tampered/local"
        durable.atomic_write_json(self.plane.receipt_path("BASE-020"), tampered)
        with mock.patch.object(
            self.plane,
            "_durable_receipt_records",
            return_value={"BASE-020": [self.record(receipt)]},
        ):
            view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("invalid local completion receipt", view.reasons[0])

    def test_17_multiple_durable_receipts_fail_closed(self) -> None:
        receipt = self.receipt("BASE-020")
        with mock.patch.object(
            self.plane,
            "_durable_receipt_records",
            return_value={"BASE-020": [self.record(receipt), self.record(receipt)]},
        ):
            view = self.plane.node_view("BASE-020")
        self.assertEqual(view.state, "REPAIR_REQUIRED")
        self.assertIn("multiple durable completion", view.reasons[0])


if __name__ == "__main__":
    unittest.main()
