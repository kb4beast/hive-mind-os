from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from hive_mind_os.autopilot_workflow import (
    GENERIC_PROMPT_SOURCE,
    PortableAutopilotError,
    initialize_repository,
    inspect_repository,
    simple_prompt,
)


class PortableAutopilotWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Other Repository\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.invalid/acme/widgets.git"],
            cwd=self.root,
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_initialize_and_inspect_uninstalled_repository(self) -> None:
        result = initialize_repository(
            self.root,
            objective="Build a portable widget service",
            target_branch="release/widgets",
        )
        self.assertEqual(result["status"], "initialized")
        request = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(request["target_branch"], "release/widgets")
        self.assertEqual(request["source"]["sha256"], GENERIC_PROMPT_SOURCE["sha256"])
        self.assertEqual(request["source"]["license"], "unresolved-no-repository-license-declared")
        contract = inspect_repository(self.root, request="Take it from here")
        self.assertEqual(contract["intent"]["intent"], "BUILD_DAG")
        self.assertEqual(contract["tasks"][0]["transport"], "durable_user_owned_task")
        self.assertRegex(
            contract["tasks"][0]["title"],
            r"^Hive Mind DAG-BUILD-[0-9a-f]{12} \[[0-9a-f]{12}\]$",
        )
        self.assertNotIn("kb4beast/hive-mind-os", contract["tasks"][0]["prompt"])

    def test_initialize_fails_closed_instead_of_overwriting_request(self) -> None:
        first = initialize_repository(self.root, objective="First")
        repeated = initialize_repository(self.root, objective="First")
        self.assertEqual(first["request"]["request_id"], repeated["request"]["request_id"])
        self.assertEqual(repeated["status"], "already-initialized")
        (self.root / "README.md").write_text("# Changed\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=self.root, check=True, capture_output=True)
        self.assertEqual(
            initialize_repository(self.root, objective="First")["status"],
            "already-initialized",
        )
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, objective="Second")

    def test_protected_or_invalid_target_branch_is_rejected(self) -> None:
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="main")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="Main")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="REFS/HEADS/release/test")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="bad branch")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(
                self.root,
                target_branch="production",
                protected_branches=("production",),
            )

    def test_remote_credentials_are_not_persisted(self) -> None:
        subprocess.run(["git", "remote", "remove", "origin"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://secret@example.invalid/acme/widgets.git?token=also-secret#private",
            ],
            cwd=self.root,
            check=True,
        )
        result = initialize_repository(self.root)
        request = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(
            request["repository_remote"],
            "https://example.invalid/acme/widgets.git",
        )
        self.assertNotIn("secret", json.dumps(request))

    def test_ssh_user_info_and_missing_origin_are_safe(self) -> None:
        subprocess.run(["git", "remote", "remove", "origin"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "ssh://secret@example.invalid/acme/widgets.git"],
            cwd=self.root,
            check=True,
        )
        result = initialize_repository(self.root)
        self.assertEqual(result["request"]["repository_remote"], "ssh://example.invalid/acme/widgets.git")
        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Local\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=self.root, check=True, capture_output=True)
        local = initialize_repository(self.root)
        self.assertIsNone(local["request"]["repository_remote"])

    def test_check_only_does_not_bootstrap_uninstalled_repository(self) -> None:
        initialize_repository(self.root)
        contract = inspect_repository(self.root, request="Check only; do not build or start anything")
        self.assertEqual(contract["intent"]["intent"], "CHECK")
        self.assertEqual(contract["tasks"], [])
        self.assertTrue(contract["bootstrap_required"])

    def test_explanation_language_does_not_bootstrap(self) -> None:
        initialize_repository(self.root)
        contract = inspect_repository(self.root, request="Explain how to finish the DAG")
        self.assertEqual(contract["intent"]["intent"], "CHECK")
        self.assertEqual(contract["tasks"], [])

    def test_persisted_request_cannot_redeclare_target_as_protected(self) -> None:
        result = initialize_repository(self.root, target_branch="release/widgets")
        path = Path(result["path"])
        request = json.loads(path.read_text(encoding="utf-8"))
        request["protected_branches"].append("release/*")
        material = dict(request)
        material.pop("request_id")
        request["request_id"] = "sha256:" + sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        path.write_text(json.dumps(request), encoding="utf-8")
        with self.assertRaises(PortableAutopilotError):
            inspect_repository(self.root, request="continue")

    def test_repository_state_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside_name:
            managed = self.root / ".hive-mind"
            try:
                os.symlink(outside_name, managed, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with self.assertRaises(PortableAutopilotError):
                initialize_repository(self.root)

    def test_simple_prompt_is_repository_neutral(self) -> None:
        prompt = simple_prompt()
        self.assertIn("build, start, continue, check, or finish", prompt)
        self.assertNotIn("kb4beast", prompt)

    def test_inspect_never_executes_target_repository_controller(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        escaped = self.root.parent / f"{self.root.name}-controller-escaped.txt"
        controller.write_text(
            "from pathlib import Path\n"
            f"Path({str(escaped)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        contract = inspect_repository(self.root, request="check")
        self.assertEqual(contract["kind"], "hive-mind-portable-controller-invocation-v1")
        self.assertEqual(contract["invocation"]["execution_owner"], "active_host_sandbox")
        self.assertFalse(escaped.exists())
        (self.root / "README.md").write_text("# Product-only change\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "product"], cwd=self.root, check=True, capture_output=True)
        self.assertEqual(
            inspect_repository(self.root, request="check")["outcome"],
            "HOST_EXECUTION_REQUIRED",
        )
        controller.write_text(controller.read_text(encoding="utf-8") + "# dirty\n", encoding="utf-8")
        with self.assertRaises(PortableAutopilotError):
            inspect_repository(self.root, request="check")

    def test_installed_controller_contract_requires_host_sandbox(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        controller.write_text("print('{}')\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        contract = inspect_repository(self.root, request="check")
        self.assertTrue(contract["invocation"]["deny_outside_repository_filesystem"])
        self.assertTrue(contract["invocation"]["deny_descendant_processes"])


if __name__ == "__main__":
    unittest.main()
