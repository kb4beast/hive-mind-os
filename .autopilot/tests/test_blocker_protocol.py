from __future__ import annotations

import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture, ready_runtime

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "controller.py"
SPEC = importlib.util.spec_from_file_location("blocker_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


class BlockerProtocolTests(unittest.TestCase):
    def test_atomic_json_write_retries_transient_windows_file_lock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "state.json"
            real_replace = controller.os.replace
            attempts = 0

            def transient_replace(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    raise PermissionError("transient scanner lock")
                return real_replace(source, destination)

            with (
                mock.patch.object(
                    controller, "windows_replace_retry_enabled", return_value=True
                ),
                mock.patch.object(controller.os, "replace", side_effect=transient_replace),
                mock.patch.object(controller.time, "sleep") as pause,
            ):
                controller.atomic_write_json(target, {"status": "durable"})

            self.assertEqual(controller.read_json(target), {"status": "durable"})
            self.assertEqual(attempts, 2)
            pause.assert_called_once_with(0.01)

    def test_blocker_packet_names_cause_fix_and_retry_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            packet = plane.record_blocker(
                "ARCH-100",
                category="remote-authority",
                cause="remote TLS revocation validation failed",
                fix="restore certificate revocation validation or provide a trusted network path",
                retry_when="remote inspection succeeds without disabling TLS controls",
                attempted_command=["git", "ls-remote", "origin"],
                evidence_refs=["test:evidence"],
            )
            self.assertTrue(packet["blocker_id"])
            self.assertEqual(packet["status"], "OPEN")
            self.assertTrue(plane.safe_retry_allowed(packet))
            self.assertEqual(packet["recovery_action"]["action"], "REPORT_BLOCKER")
            stored = root / ".autopilot" / "state" / "blockers" / "ARCH-100.jsonl"
            self.assertIn("retry_when", stored.read_text(encoding="utf-8"))

    def test_generic_software_blocker_spawns_repair_and_can_be_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            packet = plane.record_blocker(
                "ARCH-100",
                cause="controller subprocess could not inspect the remote",
                fix="repair the bounded subprocess environment",
                retry_when="normal verified remote inspection succeeds",
                category="software",
            )
            self.assertEqual(packet["recovery_action"]["action"], "SPAWN_SUBTASK")
            resolution = plane.resolve_blocker(
                "ARCH-100",
                packet["blocker_id"],
                actor="steward:fixture",
                fix="passed validated proxy variables through the safe allowlist",
                retry_command=["git", "ls-remote", "origin"],
                evidence_refs=["test:remote-inspection"],
            )
            self.assertEqual(resolution["status"], "RESOLVED")
            self.assertEqual(resolution["recovery_action"]["action"], "RETRY_NOW")

    def test_blocker_resolution_rejects_security_bypassing_retry_argv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            packet = plane.record_blocker(
                "ARCH-100",
                cause="remote inspection failed",
                fix="repair the bounded subprocess environment",
                retry_when="verified remote inspection succeeds",
                category="software",
            )
            for command in (
                ["git", "-c", "http.sslVerify=false", "ls-remote", "origin"],
                ["env", "GIT_SSL_NO_VERIFY=1", "git", "ls-remote", "origin"],
                ["curl", "--insecure", "https://example.test"],
            ):
                with self.subTest(command=command), self.assertRaises(controller.AutopilotError):
                    plane.resolve_blocker(
                        "ARCH-100",
                        packet["blocker_id"],
                        actor="steward:fixture",
                        fix="use the normal verified transport path",
                        retry_command=command,
                    )

    def test_permission_does_not_authorize_security_bypass(self) -> None:
        self.assertFalse(
            controller.ControlPlane.safe_retry_allowed(
                {"fix": "disable TLS certificate revocation", "retry_when": "retry"}
            )
        )

    def test_stale_dispatcher_release_requests_orchestrator_subtask(self) -> None:
        action = controller.ControlPlane.recovery_action(
            {"category": "dispatcher", "cause": "dispatcher release is stale", "fix": "rerun dispatch"}
        )
        self.assertEqual(action["action"], "SPAWN_SUBTASK")
        self.assertEqual(action["role"], "orchestrator")
        self.assertEqual(
            action["required_sequence"],
            list(controller.SUBTASK_EXECUTION_SEQUENCE),
        )
        self.assertLess(
            action["required_sequence"].index("dispatch_explicit_start_now"),
            action["required_sequence"].index("claim_remote_node_branch"),
        )

    def test_git_transport_allowlist_accepts_proxy_only_in_child_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            original = controller.os.environ.get("HTTPS_PROXY")
            controller.os.environ["HTTPS_PROXY"] = "https://proxy.example.test:8443"
            try:
                environment = {
                    "PATH": controller.os.environ.get("PATH", ""),
                    "GIT_TERMINAL_PROMPT": "0",
                }
                for key in controller.SAFE_GIT_TRANSPORT_ENVIRONMENT_KEYS:
                    value = controller.os.environ.get(key)
                    if value and not any(character in value for character in "\r\n"):
                        if key.lower() in {"http_proxy", "https_proxy"}:
                            parsed = controller.urlparse(value)
                            if parsed.scheme in {"http", "https", "socks5", "socks5h"} and parsed.hostname:
                                environment[key] = value
                        else:
                            environment[key] = value
                self.assertEqual(environment["HTTPS_PROXY"], "https://proxy.example.test:8443")
                self.assertNotIn("GITHUB_TOKEN", environment)
            finally:
                if original is None:
                    controller.os.environ.pop("HTTPS_PROXY", None)
                else:
                    controller.os.environ["HTTPS_PROXY"] = original

    def test_human_question_is_resolved_into_immediate_safe_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            opened = plane.record_human_question(
                "ARCH-100",
                question="Which trusted proxy environment is available?",
                cause="Git remote inspection cannot start without the runtime transport path",
                attempted_command=["git", "ls-remote", "origin"],
            )
            resolved = plane.resolve_human_question(
                "ARCH-100",
                opened["question_id"],
                answer="Use the existing trusted HTTPS proxy environment.",
                fix="Pass validated HTTP_PROXY, HTTPS_PROXY, and NO_PROXY to the Git subprocess.",
                retry_command=["git", "ls-remote", "origin"],
            )
            self.assertEqual(resolved["recovery_action"]["action"], "RETRY_NOW")
            self.assertNotIn("trusted HTTPS proxy", resolved["answer_digest"])
            text = (root / ".autopilot" / "state" / "questions" / "ARCH-100.jsonl").read_text()
            self.assertIn("QUESTION_OPENED", text)
            self.assertIn("QUESTION_RESOLVED", text)

    def test_subtask_wave_cannot_end_on_idle_or_recoverable_children(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            plane.start_subtask_wave(
                "wave-l1",
                ("ACCEPT-240", "CONSULT-210"),
                target_sha="0" * 40,
            )
            active = plane.poll_subtask_wave(
                "wave-l1",
                {"ACCEPT-240": "IDLE_UNCOLLECTED", "CONSULT-210": "BLOCKED_RECOVERABLE"},
            )
            self.assertFalse(active["may_end_turn"])
            self.assertFalse(active["target_mutation_allowed"])
            self.assertEqual(active["recovery_actions"]["ACCEPT-240"], "COLLECT_RESULT_NOW")
            self.assertEqual(active["recovery_actions"]["CONSULT-210"], "APPLY_FIX_AND_RETRY_NOW")
            settled = plane.poll_subtask_wave(
                "wave-l1",
                {"ACCEPT-240": "SUCCEEDED", "CONSULT-210": "BLOCKED_EXTERNAL_AUTHORITY"},
            )
            self.assertTrue(settled["may_end_turn"])
            self.assertTrue(settled["target_mutation_allowed"])

    def test_stale_snapshot_recovery_is_ordered_and_stash_safe(self) -> None:
        action = controller.ControlPlane.recovery_action(
            {
                "category": "snapshot",
                "cause": "validated snapshot target mismatch after release advance",
                "fix": "refresh stale snapshot and recover child work",
            }
        )
        self.assertEqual(action["action"], "SPAWN_SUBTASK")
        sequence = action["required_sequence"]
        self.assertEqual(sequence, list(controller.STALE_TARGET_RECOVERY_SEQUENCE))
        self.assertLess(sequence.index("refresh_validated_github_snapshot"), sequence.index("install_snapshot_and_reconcile"))
        self.assertLess(sequence.index("doctor_status_dispatch_and_reclaim"), sequence.index("apply_exact_node_named_stash"))
        self.assertTrue(all("stash@" not in step for step in sequence))

    def test_repository_wide_validation_has_singleton_lease(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            copy_autopilot_fixture(source, root / ".autopilot")
            (root / ".autopilot" / "state" / "global-validation-lease.json").unlink(
                missing_ok=True
            )
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            ready_runtime(controller, root)
            lease = plane.acquire_global_validation_lease_internal("ACCEPT-240", "worker:accept")
            self.assertEqual(lease["status"], "ACTIVE")
            with self.assertRaises(controller.AutopilotError):
                plane.acquire_global_validation_lease_internal("CONSULT-210", "worker:consult")
            plane.release_global_validation_lease_internal(
                "ACCEPT-240",
                "worker:accept",
                lease_id=str(lease["lease_id"]),
            )
            second = plane.acquire_global_validation_lease_internal("CONSULT-210", "worker:consult")
            self.assertEqual(second["node_id"], "CONSULT-210")

    def test_validation_lease_concurrent_acquisition_has_exactly_one_winner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_autopilot_fixture(Path(__file__).resolve().parents[1], root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            ready_runtime(controller, root)
            barrier = threading.Barrier(2)
            outcomes: list[str] = []

            def acquire(node_id: str, owner: str) -> None:
                barrier.wait()
                try:
                    plane.acquire_global_validation_lease_internal(node_id, owner)
                    outcomes.append("won")
                except controller.AutopilotError:
                    outcomes.append("lost")

            threads = [
                threading.Thread(target=acquire, args=("ACCEPT-240", "worker:accept")),
                threading.Thread(target=acquire, args=("CONSULT-210", "worker:consult")),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(sorted(outcomes), ["lost", "won"])
