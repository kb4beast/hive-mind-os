from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "bin" / "controller.py"
SPEC = importlib.util.spec_from_file_location("blocker_controller", MODULE_PATH)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = controller
SPEC.loader.exec_module(controller)


class BlockerProtocolTests(unittest.TestCase):
    def test_blocker_packet_names_cause_fix_and_retry_condition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[1]
            shutil.copytree(source, root / ".autopilot")
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
            shutil.copytree(source, root / ".autopilot")
            control = controller.read_json(root / ".autopilot" / "control-plane.json")
            control["verify_git_objects"] = False
            controller.atomic_write_json(root / ".autopilot" / "control-plane.json", control)
            plane = controller.ControlPlane(root)
            original = controller.os.environ.get("HTTPS_PROXY")
            controller.os.environ["HTTPS_PROXY"] = "https://proxy.example.test:8443"
            try:
                environment = {
                    "PATH": controller.os.environ.get("PATH", ""),
                    "GIT_CONFIG_GLOBAL": controller.os.devnull,
                    "GIT_CONFIG_NOSYSTEM": "1",
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
