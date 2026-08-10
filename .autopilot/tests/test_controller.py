from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "controller.py"
SPEC = importlib.util.spec_from_file_location("autopilot_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)

BASELINE = "7e1d4d83ace334463fa8d3caa5f4c1d617bc2c23"
SECOND = "b" * 40
THIRD = "c" * 40


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2030, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, minutes: int) -> None:
        self.value += timedelta(minutes=minutes)


class AutopilotControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = Path(__file__).resolve().parents[1]
        shutil.copytree(source, self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self.clock = Clock()
        self.plane = controller.ControlPlane(self.root, clock=self.clock)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def reload(self) -> None:
        self.plane = controller.ControlPlane(self.root, clock=self.clock)

    @staticmethod
    def concrete_path(scope: str) -> str:
        path = scope.removesuffix("/**")
        path = path.replace("*", "artifact")
        if scope.endswith("/**"):
            path += "/artifact.txt"
        return path

    def consultation(self, *, decision: str = "RESOLVED", cheating: bool = False) -> dict:
        return {
            "request_id": "CONSULT-test",
            "mission_id": "MISSION-test",
            "question": "Can the roles resolve this?",
            "reason_code": "SUSPECTED_CHEATING" if cheating else "AMBIGUITY",
            "requesting_role": "builder",
            "consulted_roles": ["architect", "curator"],
            "round": 1,
            "suspected_cheating": cheating,
            "evidence_refs": ["evidence:one"],
            "decision": decision,
            "answer": "Resolved from evidence" if decision == "RESOLVED" else None,
            "dissent": [],
            "human_escalation": decision == "TRUE_AUTHORITY_REQUIRED",
            "authority_class": "credential_or_secret" if decision == "TRUE_AUTHORITY_REQUIRED" else None,
            "role_first_exhausted": True,
            "cheating_disposition": "DISPROVED" if cheating else "NOT_APPLICABLE",
            "identity_records": [
                {"role": "architect", "identity": "role:architect", "identity_kind": "model_role"},
                {"role": "curator", "identity": "role:curator", "identity_kind": "model_role"},
            ],
        }

    def receipt(self, node_id: str, *, consultations: list[dict] | None = None) -> dict:
        node = self.plane.node(node_id)
        changed = [self.concrete_path(node["write_scope"][0])]
        return {
            "schema_version": 1,
            "plan_fingerprint": self.plane.expected_plan_fingerprint,
            "node_id": node_id,
            "contract_version": 1,
            "base_commit": BASELINE,
            "final_commit": SECOND,
            "base_tree": "d" * 40,
            "final_tree": "e" * 40,
            "branch": node["branch"],
            "pr": 123,
            "changed_paths": changed,
            "tests": [
                {"name": name, "status": "passed", "command": ["python", "-m", "unittest"]}
                for name in node["required_tests"]
            ],
            "evidence_refs": ["evidence:test"],
            "model_runtime": {"provider": "fixture", "model": "fixture"},
            "role_identities": [
                {"role": role, "identity": f"role:{role}", "identity_kind": "model_role"}
                for role in node["roles"]
            ],
            "authority": {"node_id": node_id, "autonomy_level": "A3", "grants": ["repository"]},
            "consultations": consultations or [],
            "acceptance_decision": "ADOPT",
            "timestamp": "2030-01-01T00:00:00Z",
            "rollback_ref": "revert:fixture",
        }

    def mark_complete(self, node_id: str) -> None:
        path = self.plane.receipt_path(node_id)
        controller.atomic_write_json(path, self.receipt(node_id))

    def mark_dependencies_complete(self, node_id: str) -> None:
        for dependency in self.plane.node(node_id)["dependencies"]:
            self.mark_dependencies_complete(dependency)
            if not self.plane.receipt_path(dependency).exists():
                self.mark_complete(dependency)

    def install_snapshot(self, *, target: str = BASELINE, prs: list[dict] | None = None, branches: list[dict] | None = None) -> None:
        controller.atomic_write_json(
            self.plane.state_dir / "github-state.json",
            {"target_sha": target, "pull_requests": prs or [], "branches": branches or []},
        )

    def test_01_fresh_bootstrap_is_required(self) -> None:
        self.assertEqual(self.plane.node_view("BOOT-000").state, "BOOTSTRAP_REQUIRED")

    def test_02_invalid_bootstrap_missing_template(self) -> None:
        (self.root / ".autopilot" / "templates" / "worker.md").unlink()
        self.reload()
        self.assertTrue(any("worker.md" in issue for issue in self.plane.validate_configuration()))

    def test_03_first_nodes_ready_after_bootstrap(self) -> None:
        self.mark_complete("BOOT-000")
        self.assertEqual(set(self.plane.ready_nodes()), {"BASE-020", "RECON-010"})

    def test_04_parallel_foundation_wave_ready(self) -> None:
        self.mark_dependencies_complete("CONTRACT-110")
        self.mark_complete("CONTRACT-110")
        expected = {"ROLE-200", "CONSULT-210", "EFFECT-220", "CONTEXT-230", "ACCEPT-240", "RECONCILE-250", "MIGRATE-260"}
        self.assertTrue(expected.issubset(set(self.plane.ready_nodes())))

    def test_05_valid_receipt_marks_node_complete(self) -> None:
        self.mark_complete("BOOT-000")
        self.assertEqual(self.plane.node_view("BOOT-000").state, "COMPLETE")

    def test_06_deleted_branch_after_merge_does_not_erase_completion(self) -> None:
        self.mark_complete("BOOT-000")
        self.install_snapshot(branches=[])
        self.assertEqual(self.plane.node_view("BOOT-000").state, "COMPLETE")

    def test_07_open_node_pr_is_reported(self) -> None:
        self.mark_complete("BOOT-000")
        self.install_snapshot(prs=[{"node_id": "RECON-010", "number": 10, "state": "open", "merged": False, "ci": "pending"}])
        self.assertEqual(self.plane.node_view("RECON-010").state, "PR_OPEN")

    def test_08_closed_unmerged_pr_requires_repair(self) -> None:
        self.mark_complete("BOOT-000")
        self.install_snapshot(prs=[{"node_id": "RECON-010", "number": 10, "state": "closed", "merged": False, "ci": "success"}])
        self.assertEqual(self.plane.node_view("RECON-010").state, "REPAIR_REQUIRED")

    def test_09_failed_ci_is_reported(self) -> None:
        self.mark_complete("BOOT-000")
        self.install_snapshot(prs=[{"node_id": "RECON-010", "number": 10, "state": "open", "merged": False, "ci": "failure"}])
        self.assertEqual(self.plane.node_view("RECON-010").state, "CI_FAILED")

    def test_10_stale_receipt_is_not_completion(self) -> None:
        receipt = self.receipt("BOOT-000")
        receipt["plan_fingerprint"] = "sha256:" + "0" * 64
        controller.atomic_write_json(self.plane.receipt_path("BOOT-000"), receipt)
        self.assertNotEqual(self.plane.node_view("BOOT-000").state, "COMPLETE")

    def test_11_stale_branch_requires_repair(self) -> None:
        self.mark_complete("BOOT-000")
        branch = self.plane.node("RECON-010")["branch"]
        self.install_snapshot(branches=[{"name": branch, "stale": True}])
        self.assertEqual(self.plane.node_view("RECON-010").state, "REPAIR_REQUIRED")

    def test_12_duplicate_claim_is_rejected(self) -> None:
        self.mark_complete("BOOT-000")
        self.plane.claim("RECON-010", "worker:one")
        with self.assertRaises(controller.ClaimError):
            self.plane.claim("RECON-010", "worker:two")

    def test_13_file_lock_conflict_blocks_parallel_claim(self) -> None:
        self.mark_dependencies_complete("CONTRACT-110")
        self.mark_complete("CONTRACT-110")
        self.plane.claim("ROLE-200", "worker:role")
        self.plane._nodes["CONSULT-210"]["file_locks"] = list(self.plane.node("ROLE-200")["file_locks"])
        self.assertEqual(self.plane.node_view("CONSULT-210").state, "BLOCKED")

    def test_14_semantic_lock_conflict_blocks_parallel_claim(self) -> None:
        self.mark_dependencies_complete("CONTRACT-110")
        self.mark_complete("CONTRACT-110")
        self.plane.claim("ROLE-200", "worker:role")
        self.plane._nodes["CONSULT-210"]["semantic_locks"] = ["role-runtime"]
        self.assertEqual(self.plane.node_view("CONSULT-210").state, "BLOCKED")

    def test_15_merged_pr_without_receipt_waits_for_receipt(self) -> None:
        self.mark_complete("BOOT-000")
        self.install_snapshot(prs=[{"node_id": "RECON-010", "number": 10, "state": "closed", "merged": True, "ci": "success"}])
        self.assertEqual(self.plane.node_view("RECON-010").state, "WAITING_FOR_RECEIPT")

    def test_16_target_advance_requires_reconciliation(self) -> None:
        self.mark_complete("BOOT-000")
        self.install_snapshot(target=THIRD)
        self.assertEqual(self.plane.node_view("RECON-010").state, "RECONCILIATION_REQUIRED")

    def test_17_reconciliation_accepts_current_target(self) -> None:
        self.mark_complete("BOOT-000")
        self.install_snapshot(target=THIRD)
        self.plane.reconcile(THIRD, actor="dispatcher", reason="reviewed target advance")
        self.assertEqual(self.plane.node_view("RECON-010").state, "READY")

    def test_18_integration_node_becomes_integration_ready(self) -> None:
        self.mark_dependencies_complete("MISSION-400")
        self.assertEqual(self.plane.node_view("MISSION-400").state, "INTEGRATION_READY")

    def test_19_integration_pr_failure_is_ci_failed(self) -> None:
        self.mark_dependencies_complete("MISSION-400")
        self.install_snapshot(prs=[{"node_id": "MISSION-400", "number": 400, "state": "open", "merged": False, "ci": "failure"}])
        self.assertEqual(self.plane.node_view("MISSION-400").state, "CI_FAILED")

    def test_20_promotion_node_becomes_promotion_ready(self) -> None:
        self.mark_dependencies_complete("PROMOTE-530")
        self.assertEqual(self.plane.node_view("PROMOTE-530").state, "PROMOTION_READY")

    def test_21_worker_can_preserve_model_escalation(self) -> None:
        self.mark_complete("BOOT-000")
        self.plane.claim("RECON-010", "worker:one")
        self.plane.fail("RECON-010", "worker:one", error="architecture ambiguity exceeded T2", kind="escalation")
        self.assertEqual(self.plane.node_view("RECON-010").state, "ESCALATION_REQUIRED")

    def test_22_consultation_resolves_question(self) -> None:
        self.assertEqual(self.plane.validate_consultation(self.consultation()), ())

    def test_23_consultation_preserves_dissent(self) -> None:
        value = self.consultation()
        value["dissent"] = ["Curator requires one more receipt."]
        self.assertEqual(self.plane.validate_consultation(value), ())

    def test_24_consultation_loop_is_bounded(self) -> None:
        value = self.consultation()
        value["round"] = 4
        self.assertTrue(any("round" in issue for issue in self.plane.validate_consultation(value)))

    def test_25_genuine_human_authority_is_allowed(self) -> None:
        value = self.consultation(decision="TRUE_AUTHORITY_REQUIRED")
        self.assertEqual(self.plane.validate_consultation(value), ())

    def test_26_fake_human_escalation_is_rejected(self) -> None:
        value = self.consultation()
        value["human_escalation"] = True
        value["authority_class"] = "software_bug"
        self.assertTrue(self.plane.validate_consultation(value))

    def test_27_confirmed_cheating_cannot_resolve_normally(self) -> None:
        value = self.consultation(cheating=True)
        value["cheating_disposition"] = "CONFIRMED"
        self.assertTrue(self.plane.validate_consultation(value))

    def test_28_cheating_can_be_disproved_with_evidence(self) -> None:
        value = self.consultation(cheating=True)
        self.assertEqual(self.plane.validate_consultation(value), ())

    def test_29_self_healing_retry_returns_node_to_ready(self) -> None:
        self.mark_complete("BOOT-000")
        self.plane.claim("RECON-010", "worker:one")
        self.plane.fail("RECON-010", "worker:one", error="transient failure")
        self.assertEqual(self.plane.node_view("RECON-010").state, "READY")

    def test_30_repeated_failure_quarantines_node(self) -> None:
        self.mark_complete("BOOT-000")
        for index in range(3):
            self.plane.claim("RECON-010", f"worker:{index}")
            self.plane.fail("RECON-010", f"worker:{index}", error="repeated semantic failure")
        self.assertEqual(self.plane.node_view("RECON-010").state, "QUARANTINED")

    def test_31_cycle_requires_replanning(self) -> None:
        self.plane._nodes["BOOT-000"]["dependencies"] = ["RECON-010"]
        dependencies = {node_id: tuple(node["dependencies"]) for node_id, node in self.plane._nodes.items()}
        self.assertIsNotNone(self.plane._find_cycle(dependencies))

    def test_32_project_complete_when_all_nodes_have_receipts(self) -> None:
        for node_id in self.plane._nodes:
            self.mark_complete(node_id)
        self.assertTrue(self.plane.status()["complete"])

    def test_33_unknown_dependency_is_invalid(self) -> None:
        self.plane._nodes["RECON-010"]["dependencies"] = ["MISSING"]
        self.plane.plan["nodes"] = list(self.plane._nodes.values())
        self.assertTrue(any("unknown dependency" in issue for issue in self.plane.validate_configuration()))

    def test_34_duplicate_node_ids_are_invalid(self) -> None:
        self.plane.plan["nodes"].append(copy.deepcopy(self.plane.plan["nodes"][0]))
        self.assertTrue(any("not unique" in issue for issue in self.plane.validate_configuration()))

    def test_35_missing_provider_route_is_invalid(self) -> None:
        del self.plane.provider_catalog["tiers"]["T4"]["anthropic"]
        self.assertTrue(any("T4.anthropic" in issue for issue in self.plane.validate_configuration()))

    def test_36_missing_role_row_is_invalid(self) -> None:
        self.plane.role_matrix["roles"].pop()
        self.assertTrue(any("exactly all eight" in issue for issue in self.plane.validate_configuration()))

    def test_37_archive_only_installation_is_detected(self) -> None:
        (self.root / "REPO_ROOT" / ".autopilot").mkdir(parents=True)
        self.assertTrue(any("archive-only" in issue for issue in self.plane.validate_configuration()))

    def test_38_receipt_outside_write_scope_is_rejected(self) -> None:
        receipt = self.receipt("BOOT-000")
        receipt["changed_paths"] = ["src/hive_mind_os/unsafe.py"]
        self.assertTrue(any("outside" in issue for issue in self.plane.validate_receipt("BOOT-000", receipt)))

    def test_39_nonpassing_test_is_rejected(self) -> None:
        receipt = self.receipt("BOOT-000")
        receipt["tests"][0]["status"] = "failed"
        self.assertTrue(self.plane.validate_receipt("BOOT-000", receipt))

    def test_40_stale_claim_is_reaped(self) -> None:
        self.mark_complete("BOOT-000")
        self.plane.claim("RECON-010", "worker:one", lease_minutes=1)
        self.clock.advance(2)
        self.assertEqual(self.plane.clean_stale_claims(), ("RECON-010",))
        self.assertEqual(self.plane.node_view("RECON-010").state, "READY")

    def test_41_receipt_with_valid_consultation_passes(self) -> None:
        receipt = self.receipt("BOOT-000", consultations=[self.consultation()])
        self.assertEqual(self.plane.validate_receipt("BOOT-000", receipt), ())

    def test_42_doctor_passes_configuration_without_git(self) -> None:
        result = self.plane.doctor(run_controller_tests=False)
        self.assertTrue(result["passed"], result)

    def test_43_rendered_prompt_contains_node_and_routes(self) -> None:
        text = self.plane.render_worker_prompt("BOOT-000")
        self.assertIn("BOOT-000", text)
        self.assertIn("GPT-5.6 Terra", text)
        self.assertIn("Claude Sonnet 5", text)

    def test_44_filename_glob_scope_accepts_matching_receipt(self) -> None:
        self.assertTrue(
            controller.path_matches_scope(
                "src/hive_mind_os/schemas/hive-cortex-consultation.schema.json",
                "src/hive_mind_os/schemas/hive-cortex-*.schema.json",
            )
        )

    def test_45_sibling_glob_scopes_do_not_false_conflict(self) -> None:
        self.assertFalse(
            controller.scopes_overlap(
                "src/hive_mind_os/schemas/hive-cortex-*.schema.json",
                "src/hive_mind_os/schemas/other-*.schema.json",
            )
        )


if __name__ == "__main__":
    unittest.main()
