from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fixture_support import copy_autopilot_fixture, ready_runtime

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))
MODULE_PATH = BIN / "controller.py"
SPEC = importlib.util.spec_from_file_location("autopilot_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)

from orchestration import (  # noqa: E402
    OrchestrationError,
    bind_launch,
    binding_events,
    derive_launch_identity,
    fence_launch,
    prepare_launch,
)
from sidecar_execution import SidecarPolicyError, sidecar_events  # noqa: E402

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
        copy_autopilot_fixture(source, self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(
            json.dumps(control, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        self.clock = Clock()
        self.plane = controller.ControlPlane(self.root, clock=self.clock)
        ready_runtime(controller, self.root)

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

    def bind_hosted_launch(self, node_id: str) -> dict[str, object]:
        node = self.plane.node(node_id)
        target = self.plane.control["target"]
        identity = dict(
            derive_launch_identity(
                execution_id=self.plane.execution_id,
                execution_namespace=self.plane.execution_namespace,
                repository=str(target["repository"]),
                node_id=node_id,
                lifecycle="NODE_DELIVERY",
                branch=str(node["branch"]),
                target_sha=self.plane.current_target_sha(),
                plan_fingerprint=self.plane.expected_plan_fingerprint,
                target_branch=self.plane.target_branch,
                authority_class="WRITE_AUTHORIZED",
                attempt=1,
                retry_of=None,
            )
        )
        with self.plane.execution_lock("dispatcher-admission.lock"):
            prepared = prepare_launch(
                self.root,
                str(identity["launch_instruction_id"]),
                "codex",
                execution_id=self.plane.execution_id,
                execution_namespace=self.plane.execution_namespace,
                repository=str(target["repository"]),
                node_id=node_id,
                lifecycle="NODE_DELIVERY",
                branch=str(node["branch"]),
                resource_key=str(identity["resource_key"]),
                target_sha=self.plane.current_target_sha(),
                plan_fingerprint=self.plane.expected_plan_fingerprint,
                target_branch=self.plane.target_branch,
                authority_class="WRITE_AUTHORIZED",
                dispatcher_release_id="sha256:" + "1" * 64,
                dispatcher_admission_epoch=1,
                host_reservation_id="sha256:" + "2" * 64,
                capacity_host_id="test:host",
                capacity_generation="sha256:" + "3" * 64,
                capacity_epoch=1,
                reservation_expires_at="2030-01-01T02:00:00Z",
                host_kernel_generation="sha256:" + "4" * 64,
                execution_adapter_identity_record_id="sha256:" + "5" * 64,
                execution_adapter_identity_path=(
                    "execution-adapter-bindings/" + "5" * 64 + ".json"
                ),
                execution_adapter_identity_blob_digest="sha256:" + "6" * 64,
                state_dir=self.plane.execution_dir,
            )
            bind_launch(
                self.root,
                str(identity["launch_instruction_id"]),
                "codex",
                "task:test-hosted",
                capability="durable_user_owned_task",
                resource_key=str(identity["resource_key"]),
                authority_epoch=int(prepared["authority_epoch"]),
                state_dir=self.plane.execution_dir,
            )
        identity["authority_epoch"] = int(prepared["authority_epoch"])
        return identity

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
        self.plane.claim_internal("RECON-010", "worker:one")
        with self.assertRaises(controller.ClaimError):
            self.plane.claim_internal("RECON-010", "worker:two")

    def test_13_file_lock_conflict_blocks_parallel_claim(self) -> None:
        self.mark_dependencies_complete("CONTRACT-110")
        self.mark_complete("CONTRACT-110")
        self.plane.claim_internal("ROLE-200", "worker:role")
        self.plane._nodes["CONSULT-210"]["file_locks"] = list(self.plane.node("ROLE-200")["file_locks"])
        self.assertEqual(self.plane.node_view("CONSULT-210").state, "BLOCKED")

    def test_hosted_claim_is_bound_to_launch_and_fence_blocks_all_transitions(self) -> None:
        self.mark_complete("BOOT-000")
        identity = self.bind_hosted_launch("RECON-010")
        coordinates = {
            "claim_authority_class": "HOSTED_LAUNCH",
            "launch_instruction_id": str(identity["launch_instruction_id"]),
            "resource_key": str(identity["resource_key"]),
            "authority_epoch": int(identity["authority_epoch"]),
        }
        claim = self.plane.claim(
            "RECON-010",
            "worker:hosted",
            **coordinates,
        )
        claim_id = str(claim["claim_id"])
        validation_coordinates = {**coordinates, "claim_id": claim_id}
        validation = self.plane.acquire_global_validation_lease(
            "RECON-010",
            "worker:hosted",
            lease_minutes=10,
            **validation_coordinates,
        )
        with self.plane.execution_lock("dispatcher-admission.lock"):
            fence_launch(
                self.root,
                str(identity["launch_instruction_id"]),
                actor="curator:test",
                reason="session superseded",
                state_dir=self.plane.execution_dir,
            )
        transitions = (
            lambda: self.plane.heartbeat(
                "RECON-010", "worker:hosted", claim_id=claim_id, **coordinates
            ),
            lambda: self.plane.release(
                "RECON-010",
                "worker:hosted",
                claim_id=claim_id,
                reason="stale release",
                **coordinates,
            ),
            lambda: self.plane.fail(
                "RECON-010",
                "worker:hosted",
                claim_id=claim_id,
                error="stale failure",
                **coordinates,
            ),
            lambda: self.plane.complete(
                "RECON-010",
                "worker:hosted",
                self.receipt("RECON-010"),
                claim_id=claim_id,
                **coordinates,
            ),
        )
        for transition in transitions:
            with self.subTest(transition=transition):
                with self.assertRaisesRegex(controller.ClaimError, "stale or revoked"):
                    transition()
        validation_transitions = (
            lambda: self.plane.acquire_global_validation_lease(
                "RECON-010",
                "worker:hosted",
                lease_minutes=10,
                **validation_coordinates,
            ),
            lambda: self.plane.renew_global_validation_lease(
                "RECON-010",
                "worker:hosted",
                lease_id=str(validation["lease_id"]),
                lease_minutes=10,
                **validation_coordinates,
            ),
            lambda: self.plane.release_global_validation_lease(
                "RECON-010",
                "worker:hosted",
                lease_id=str(validation["lease_id"]),
                **validation_coordinates,
            ),
        )
        for transition in validation_transitions:
            with self.subTest(validation_transition=transition):
                with self.assertRaisesRegex(controller.ClaimError, "stale or revoked"):
                    transition()
        self.assertTrue(self.plane.claim_path("RECON-010").is_file())
        self.assertTrue(self.plane.validation_lease_path.is_file())

        for node_id in self.plane._nodes:
            self.mark_complete(node_id)
        status = self.plane.observe_status()
        self.assertFalse(status["complete"])
        self.assertTrue(status["claim_authority_reconciliation_required"])
        self.assertEqual(
            [item["node_id"] for item in status["stale_hosted_claims"]],
            ["RECON-010"],
        )
        self.assertEqual(
            [item["node_id"] for item in status["stale_hosted_validation_leases"]],
            ["RECON-010"],
        )
        self.assertNotIn("RECON-010", status["ready"])

    def test_caller_text_cannot_grant_privileged_internal_claim_authority(self) -> None:
        self.mark_complete("BOOT-000")
        with self.assertRaisesRegex(controller.ClaimError, "not available"):
            self.plane.claim(
                "RECON-010",
                "worker:hosted",
                claim_authority_class="PRIVILEGED_INTERNAL",
            )

    def test_hosted_heartbeat_and_completion_recheck_dispatcher_generation(self) -> None:
        self.mark_complete("BOOT-000")
        identity = self.bind_hosted_launch("RECON-010")
        coordinates = {
            "claim_authority_class": "HOSTED_LAUNCH",
            "launch_instruction_id": str(identity["launch_instruction_id"]),
            "resource_key": str(identity["resource_key"]),
            "authority_epoch": int(identity["authority_epoch"]),
        }
        claim = self.plane.claim("RECON-010", "worker:hosted", **coordinates)
        claim_id = str(claim["claim_id"])

        @contextmanager
        def invalidated_dispatcher(node_id: str, **_coordinates: object):
            self.assertEqual(node_id, "RECON-010")
            raise controller.ClaimError(
                "shared dispatcher admission invalidated by target advance"
            )
            yield None  # pragma: no cover - required by contextmanager protocol

        self.plane.dispatcher_launch_authority_guard = invalidated_dispatcher  # type: ignore[method-assign]
        transitions = (
            lambda: self.plane.heartbeat(
                "RECON-010",
                "worker:hosted",
                claim_id=claim_id,
                **coordinates,
            ),
            lambda: self.plane.complete(
                "RECON-010",
                "worker:hosted",
                self.receipt("RECON-010"),
                claim_id=claim_id,
                **coordinates,
            ),
        )
        for transition in transitions:
            with self.subTest(transition=transition):
                with self.assertRaisesRegex(controller.ClaimError, "target advance"):
                    transition()
        self.assertTrue(self.plane.claim_path("RECON-010").is_file())

    def test_expired_hosted_claim_cannot_acquire_validation_authority(self) -> None:
        self.mark_complete("BOOT-000")
        identity = self.bind_hosted_launch("RECON-010")
        coordinates = {
            "claim_authority_class": "HOSTED_LAUNCH",
            "launch_instruction_id": str(identity["launch_instruction_id"]),
            "resource_key": str(identity["resource_key"]),
            "authority_epoch": int(identity["authority_epoch"]),
        }
        claim = self.plane.claim(
            "RECON-010",
            "worker:hosted",
            lease_minutes=1,
            **coordinates,
        )
        self.clock.advance(2)
        with self.assertRaisesRegex(controller.ClaimError, "has expired"):
            self.plane.acquire_global_validation_lease(
                "RECON-010",
                "worker:hosted",
                claim_id=str(claim["claim_id"]),
                lease_minutes=10,
                **coordinates,
            )
        self.assertFalse(self.plane.validation_lease_path.exists())

    def test_expired_validation_lease_is_visible_and_prevents_quiescence(self) -> None:
        lease = self.plane.acquire_global_validation_lease_internal(
            "BOOT-000",
            "controller:test",
            lease_minutes=1,
        )
        self.clock.advance(2)
        for node_id in self.plane._nodes:
            self.mark_complete(node_id)
        status = self.plane.observe_status()
        self.assertIsNone(status["active_validation_lease"])
        self.assertEqual(
            status["expired_validation_lease"]["lease_id"],
            lease["lease_id"],
        )
        self.assertTrue(status["validation_lease_recovery_required"])
        self.assertTrue(status["reconciliation_required"])
        self.assertFalse(status["complete"])

    def test_14_semantic_lock_conflict_blocks_parallel_claim(self) -> None:
        self.mark_dependencies_complete("CONTRACT-110")
        self.mark_complete("CONTRACT-110")
        self.plane.claim_internal("ROLE-200", "worker:role")
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
        claim = self.plane.claim_internal("RECON-010", "worker:one")
        self.plane.fail_internal(
            "RECON-010",
            "worker:one",
            claim_id=str(claim["claim_id"]),
            error="architecture ambiguity exceeded T2",
            kind="escalation",
        )
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
        claim = self.plane.claim_internal("RECON-010", "worker:one")
        self.plane.fail_internal(
            "RECON-010",
            "worker:one",
            claim_id=str(claim["claim_id"]),
            error="transient failure",
        )
        self.assertEqual(self.plane.node_view("RECON-010").state, "READY")

    def test_30_repeated_failure_quarantines_node(self) -> None:
        self.mark_complete("BOOT-000")
        for index in range(3):
            claim = self.plane.claim_internal("RECON-010", f"worker:{index}")
            self.plane.fail_internal(
                "RECON-010",
                f"worker:{index}",
                claim_id=str(claim["claim_id"]),
                error="repeated semantic failure",
            )
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

    def test_receipt_rejects_out_of_scope_commit_hidden_by_revert(self) -> None:
        def git(*arguments: str) -> str:
            return subprocess.run(
                ("git", "-C", str(self.root), *arguments),
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        git("init", "--initial-branch=main")
        git("config", "user.name", "Receipt Ancestry Fixture")
        git("config", "user.email", "receipt-ancestry@hive-mind.invalid")
        git("add", "-A")
        git("commit", "-m", "baseline")
        base = git("rev-parse", "HEAD")

        allowed = self.root / ".autopilot" / "bin" / "allowed-fixture.txt"
        allowed.write_text("allowed\n", encoding="utf-8")
        git("add", str(allowed.relative_to(self.root)))
        git("commit", "-m", "allowed governed work")

        poison = self.root / "src" / "poison.txt"
        poison.parent.mkdir(parents=True, exist_ok=True)
        poison.write_text("must never enter this node ancestry\n", encoding="utf-8")
        git("add", str(poison.relative_to(self.root)))
        git("commit", "-m", "poison outside scope")
        poison_commit = git("rev-parse", "HEAD")
        git("revert", "--no-edit", poison_commit)
        final = git("rev-parse", "HEAD")

        self.plane.control["verify_git_objects"] = True
        candidate = self.receipt("BOOT-000")
        candidate["base_commit"] = base
        candidate["final_commit"] = final
        candidate["changed_paths"] = [
            str(allowed.relative_to(self.root)).replace("\\", "/")
        ]
        issues = self.plane.validate_receipt("BOOT-000", candidate)
        self.assertTrue(
            any(
                "raw ancestry" in issue
                and "outside node write scope" in issue
                and "src/poison.txt" in issue
                for issue in issues
            ),
            issues,
        )

    def test_39_nonpassing_test_is_rejected(self) -> None:
        receipt = self.receipt("BOOT-000")
        receipt["tests"][0]["status"] = "failed"
        self.assertTrue(self.plane.validate_receipt("BOOT-000", receipt))

    def test_40_stale_claim_is_reaped(self) -> None:
        self.mark_complete("BOOT-000")
        self.plane.claim_internal("RECON-010", "worker:one", lease_minutes=1)
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
        text = self.plane.render_worker_prompt(
            "BOOT-000", host_id="host:authenticated-fixture"
        )
        self.assertIn("BOOT-000", text)
        self.assertIn("GPT-5.6 Terra", text)
        self.assertIn("Claude Sonnet 5", text)
        self.assertIn("dispatcher-injected authority envelope", text)
        self.assertNotIn(" claim {{NODE_ID}}", text)

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

    def test_terminal_fixed_point_closes_later_validation_and_claim_admission(self) -> None:
        host_base = self.root / "canonical-host-base"
        host_runtime = self.root / "host-kernel"
        with mock.patch.object(
            controller, "_host_runtime_base_dir", return_value=host_base
        ):
            controller.initialize_host_runtime(host_runtime)
            self.plane.host_runtime_dir = host_runtime
            for node_id in self.plane._nodes:
                self.mark_complete(node_id)
            release_id = "sha256:" + "e" * 64
            target_watermark = self.plane.repository_target_watermark()
            release = {
                "release_id": release_id,
                "admission_epoch": 1,
                "released_wave": [],
                "target_sha": self.plane.current_target_sha(),
                "target_generation": target_watermark["target_generation"],
                "target_watermark_record_id": target_watermark["record_id"],
            }
            self.plane.current_release = lambda: release
            self.plane._release_issues = lambda _value: ()
            publication_path = self.plane.execution_dir / "publication-test.json"
            self.plane._publication_resource_path = lambda: publication_path
            publication_material = {
                "status": "PREPARED",
                "transaction": {
                    "transaction_id": "sha256:" + "a" * 64,
                    "transaction_key": "sha256:" + "b" * 64,
                    "execution_id": self.plane.execution_id,
                    "release_id": release_id,
                    "round_id": "sha256:" + "c" * 64,
                    "repository": self.plane.control["target"]["repository"],
                    "target_branch": self.plane.target_branch,
                    "expected_target_sha": self.plane.current_target_sha(),
                    "receipt_heads_digest": "sha256:" + "d" * 64,
                },
            }
            controller.atomic_write_json(
                publication_path,
                {
                    **publication_material,
                    "record_id": controller.digest_json(publication_material),
                },
            )
            blocked_snapshot = self.plane.round_authority_snapshot(release_id)
            self.assertEqual(blocked_snapshot["active_publication_count"], 1)
            with self.assertRaisesRegex(
                controller.AutopilotError, "publication"
            ):
                self.plane.seal_plan_quiescent(
                    release_id,
                    actor="test:publication-race",
                    expected_authority_digest=str(
                        blocked_snapshot["authority_digest"]
                    ),
                )
            publication_path.unlink()
            snapshot = self.plane.round_authority_snapshot(release_id)
            self.assertTrue(snapshot["status"]["complete"])
            fence = self.plane.seal_plan_quiescent(
                release_id,
                actor="test:fixed-point",
                expected_authority_digest=str(snapshot["authority_digest"]),
            )
            self.assertEqual(fence["state"], "PLAN_QUIESCENT")
            self.assertEqual(
                self.plane.seal_plan_quiescent(
                    release_id,
                    actor="test:fixed-point-retry",
                    expected_authority_digest=str(snapshot["authority_digest"]),
                ),
                fence,
            )
            with self.assertRaisesRegex(
                controller.AutopilotError, "terminal fence"
            ):
                self.plane.acquire_global_validation_lease_internal(
                    "RECON-010", "test:late-validator"
                )
            with self.assertRaisesRegex(controller.ClaimError, "terminal fence"):
                self.plane.claim_internal("RECON-010", "test:late-claim")

    def test_ready_runtime_cannot_recreate_retired_repository_global_ledgers(self) -> None:
        task_ledger = self.plane.coordination_dir / "task-bindings.jsonl"
        sidecar_ledger = self.plane.coordination_dir / "sidecar-bindings.jsonl"
        self.assertFalse(task_ledger.exists())
        self.assertFalse(sidecar_ledger.exists())
        with self.assertRaisesRegex(OrchestrationError, "explicit authenticated"):
            binding_events(self.root)
        with self.assertRaisesRegex(SidecarPolicyError, "explicit authenticated"):
            sidecar_events(self.root)
        self.assertFalse(task_ledger.exists())
        self.assertFalse(sidecar_ledger.exists())
        self.assertEqual(
            binding_events(self.root, state_dir=self.plane.execution_dir), ()
        )
        self.assertEqual(
            sidecar_events(self.root, state_dir=self.plane.execution_dir), ()
        )

    def test_malformed_target_control_never_justifies_claim_supersession(self) -> None:
        plan_text = (self.root / ".autopilot" / "plan.json").read_text(
            encoding="utf-8"
        )
        cases = (
            '{"plan_fingerprint":"sha256:' + "1" * 64 + '","plan_fingerprint":"sha256:' + "2" * 64 + '"}\n',
            '{"plan_fingerprint":NaN}\n',
            '{ "plan_fingerprint": "sha256:' + "3" * 64 + '" }\n',
        )
        self.plane.control["verify_git_objects"] = True
        self.plane.current_target_sha = lambda: "f" * 40
        record = {
            "expires_at": "2030-01-01T01:00:00Z",
            "plan_fingerprint": "sha256:" + "0" * 64,
        }
        for malformed in cases:
            with self.subTest(malformed=malformed[:24]):
                def fake_git(arguments, *, check=True):
                    del check
                    text = malformed if str(arguments[1]).endswith("control-plane.json") else plan_text
                    return SimpleNamespace(returncode=0, stdout=text, stderr="")

                with mock.patch.object(self.plane, "_git", side_effect=fake_git):
                    with self.assertRaisesRegex(
                        controller.ClaimError, "cannot justify destructive"
                    ):
                        self.plane.defunct_remote_claim_proof(record)


if __name__ == "__main__":
    unittest.main()
