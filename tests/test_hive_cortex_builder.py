from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Callable, cast
from unittest.mock import patch

from hive_mind_os.brain_kernel.authority import AuthorityDenied, AuthorityRegistry
from hive_mind_os.brain_kernel.builder import (
    BuilderAction,
    BuilderActionDenied,
    BuilderActionKind,
    BuilderCoordinator,
    BuilderIterationExhausted,
)
from hive_mind_os.brain_kernel.contracts import Budget, ConstraintEnvelope, EffectIntent
from hive_mind_os.brain_kernel.effects import EffectGateway
from hive_mind_os.cortex.repository.builder_adapter import IsolatedBuilderAdapter

DIGEST = "sha256:" + "b" * 64
NOW = "2030-01-01T00:00:00Z"


def _envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-builder", "MISSION-builder", "WORK-builder", None, "builder", "R1",
        ("write", "command", "branch", "commit"), ("push", "merge", "deploy"),
        ("isolated-workspace",), ("src", "tests"), (), (), (), (),
        Budget(20, 0, 0, 0, 0, 0, 4, 4), "2030-01-02T00:00:00Z", DIGEST, DIGEST,
    )


class HiveCortexBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = AuthorityRegistry()
        self.registry.register(_envelope())
        self.adapter = IsolatedBuilderAdapter(self.root)
        self.gateway = EffectGateway()
        self.gateway.register_adapter(
            self.adapter.adapter_name,
            cast(Callable[[EffectIntent], None], self.adapter.apply),
        )
        self.builder = BuilderCoordinator(
            self.gateway, self.registry, self.adapter, mission_id="MISSION-builder", work_id="WORK-builder",
            actor_id="builder:fixture", authority_envelope_digest=DIGEST, policy_decision_ref="POLICY-builder", now=NOW,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_builder_action_tests_use_typed_effects_and_receipts(self) -> None:
        write = BuilderAction("write-1", BuilderActionKind.WRITE, "src/result.txt", {"content": "fixed\n"}, "remove src/result.txt")
        command = BuilderAction(
            "test-1", BuilderActionKind.COMMAND, "isolated-workspace",
            {"profile": "file-exists", "paths": ["src/result.txt"]}, "no rollback",
        )
        executions = self.builder.repair(((write, command),), max_retries=2)
        self.assertEqual(["SUCCEEDED", "SUCCEEDED"], [item.outcome.status for item in executions])
        self.assertEqual("fixed\n", (self.root / "src" / "result.txt").read_text(encoding="utf-8"))
        self.assertTrue(all(item.effect.receipt_digest.startswith("sha256:") for item in executions))

    def test_iterative_repair_tests_keep_failed_test_evidence_then_repair(self) -> None:
        failing = BuilderAction(
            "test-fail", BuilderActionKind.COMMAND, "isolated-workspace",
            {"profile": "file-exists", "paths": ["src/fixed.txt"]}, "no rollback",
        )
        write = BuilderAction("write-fix", BuilderActionKind.WRITE, "src/fixed.txt", {"content": "ok"}, "remove src/fixed.txt")
        passing = BuilderAction(
            "test-pass", BuilderActionKind.COMMAND, "isolated-workspace",
            {"profile": "file-exists", "paths": ["src/fixed.txt"]}, "no rollback",
        )
        executions = self.builder.repair(((failing,), (write, passing)), max_retries=2)
        self.assertEqual("FAILED", executions[0].outcome.status)
        self.assertEqual("SUCCEEDED", executions[-1].outcome.status)
        with self.assertRaises(BuilderIterationExhausted):
            self.builder.repair(((failing,),), max_retries=0)

    def test_command_result_is_digest_only_evidence(self) -> None:
        (self.root / "src").mkdir()
        (self.root / "src" / "result.txt").write_text("sensitive-output", encoding="utf-8")
        command = BuilderAction(
            "test-output", BuilderActionKind.COMMAND, "isolated-workspace",
            {"profile": "file-exists", "paths": ["src/result.txt"]}, "none",
        )
        execution = self.builder.execute_round("ATTEMPT-output", (command,))[0]
        self.assertEqual("SUCCEEDED", execution.outcome.status)
        self.assertTrue(execution.outcome.detail.startswith("sha256:"))
        self.assertNotIn("sensitive-output", execution.outcome.detail)

    def test_python_powershell_and_shell_escape_profiles_fail_before_execution(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.txt"
        self.addCleanup(outside.unlink, missing_ok=True)
        escape_commands = (
            [sys.executable, "-c", f"from pathlib import Path; Path({str(outside)!r}).write_text('x')"],
            ["powershell", "-NoProfile", "-Command", f"Set-Content '{outside}' x"],
            ["pwsh", "-NoProfile", "-Command", f"Set-Content '{outside}' x"],
            ["cmd", "/c", f"echo x>{outside}"],
            ["sh", "-c", f"printf x > '{outside}'"],
            ["bash", "-c", f"printf x > '{outside}'"],
        )
        for argv in escape_commands:
            with self.subTest(executable=argv[0]), self.assertRaises(BuilderActionDenied):
                BuilderAction(
                    f"escape-{argv[0]}", BuilderActionKind.COMMAND, "isolated-workspace",
                    {"argv": argv}, "remove outside file",
                )
            self.assertFalse(outside.exists())

    def test_command_profiles_reject_path_escape(self) -> None:
        with self.assertRaises(ValueError):
            BuilderAction(
                "escape-path", BuilderActionKind.COMMAND, "isolated-workspace",
                {"profile": "file-exists", "paths": ["../outside.txt"]}, "none",
            )
        with self.assertRaises(ValueError):
            BuilderAction(
                "absolute-path", BuilderActionKind.COMMAND, "isolated-workspace",
                {"profile": "git-diff-check", "paths": [str(self.root.parent / "outside.txt")]}, "none",
            )

    def test_external_profile_receives_only_narrow_workspace_local_environment(self) -> None:
        (self.root / "src").mkdir()
        command = BuilderAction(
            "git-diff", BuilderActionKind.COMMAND, "isolated-workspace",
            {"profile": "git-diff-check", "paths": ["src"]}, "none",
        )
        completed = subprocess.CompletedProcess([], 0, stdout=b"", stderr=b"")
        with (
            patch.dict(os.environ, {"HIVE_SECRET_TOKEN": "must-not-leak"}),
            patch(
                "hive_mind_os.cortex.repository.builder_adapter.shutil.which",
                return_value=sys.executable,
            ),
            patch(
                "hive_mind_os.cortex.repository.builder_adapter.subprocess.run",
                return_value=completed,
            ) as run,
        ):
            execution = self.builder.execute_round("ATTEMPT-git-diff", (command,))[0]
        self.assertEqual("SUCCEEDED", execution.outcome.status)
        environment = run.call_args.kwargs["env"]
        self.assertNotIn("HIVE_SECRET_TOKEN", environment)
        self.assertEqual("1", environment["GIT_CONFIG_NOSYSTEM"])
        self.assertEqual(os.devnull, environment["GIT_CONFIG_GLOBAL"])
        self.assertTrue(Path(environment["HOME"]).is_relative_to(self.root))
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_git_diff_check_profile_runs_only_the_fixed_validation_command(self) -> None:
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "fixture@example.invalid"],
            cwd=self.root,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Builder fixture"],
            cwd=self.root,
            check=True,
        )
        source = self.root / "src" / "checked.py"
        source.parent.mkdir()
        source.write_bytes(b"value = 1\n")
        subprocess.run(
            ["git", "add", "src/checked.py"],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        source.write_bytes(b"value = 1 \n")
        failing = BuilderAction(
            "git-diff-fail", BuilderActionKind.COMMAND, "isolated-workspace",
            {"profile": "git-diff-check", "paths": ["src"]}, "none",
        )
        self.assertEqual(
            "FAILED",
            self.builder.execute_round("ATTEMPT-git-diff-fail", (failing,))[0].outcome.status,
        )
        source.write_bytes(b"value = 2\n")
        passing = BuilderAction(
            "git-diff-pass", BuilderActionKind.COMMAND, "isolated-workspace",
            {"profile": "git-diff-check", "paths": ["src"]}, "none",
        )
        self.assertEqual(
            "SUCCEEDED",
            self.builder.execute_round("ATTEMPT-git-diff-pass", (passing,))[0].outcome.status,
        )

    def test_branch_and_commit_actions_stay_in_the_isolated_workspace(self) -> None:
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Builder fixture"], cwd=self.root, check=True)
        branch = BuilderAction("branch-1", BuilderActionKind.BRANCH, "autopilot/fixture", {}, "switch back")
        write = BuilderAction("write-commit", BuilderActionKind.WRITE, "src/commit.txt", {"content": "committed"}, "remove src/commit.txt")
        commit = BuilderAction("commit-1", BuilderActionKind.COMMIT, "autopilot/fixture", {"paths": ["src/commit.txt"], "message": "fixture commit"}, "revert fixture commit")
        outcomes = self.builder.execute_round("ATTEMPT-commit", (branch, write, commit))
        self.assertTrue(all(item.outcome.status == "SUCCEEDED" for item in outcomes))
        head = subprocess.run(["git", "branch", "--show-current"], cwd=self.root, check=True, capture_output=True, text=True)
        self.assertEqual("autopilot/fixture", head.stdout.strip())

    def test_sealed_acceptance_denial_tests_fail_before_effect_execution(self) -> None:
        with self.assertRaises(BuilderActionDenied):
            BuilderAction("sealed", BuilderActionKind.WRITE, "tests/sealed/answer.py", {"content": "cheat"}, "revert")
        with self.assertRaises(BuilderActionDenied):
            BuilderAction("dependencies", BuilderActionKind.WRITE, "pyproject.toml", {"content": "cheat"}, "revert")
        with self.assertRaises(BuilderActionDenied):
            BuilderAction("push", BuilderActionKind.COMMAND, "isolated-workspace", {"argv": ["git", "push"]}, "none")
        with self.assertRaises(BuilderActionDenied):
            BuilderAction(
                "unknown-profile", BuilderActionKind.COMMAND, "isolated-workspace",
                {"profile": "python-unittest", "paths": ["tests"]}, "none",
            )
        with self.assertRaises(BuilderActionDenied):
            BuilderAction("protected", BuilderActionKind.BRANCH, "main", {}, "delete branch")

    def test_isolation_tests_reject_path_and_token_escape(self) -> None:
        with self.assertRaises(ValueError):
            BuilderAction("escape", BuilderActionKind.WRITE, "../outside.txt", {"content": "x"}, "remove")
        action = BuilderAction("write-2", BuilderActionKind.WRITE, "src/only.txt", {"content": "x"}, "remove")
        self.registry.revoke(DIGEST)
        with self.assertRaises(AuthorityDenied):
            self.builder.execute_round("ATTEMPT-revoked", (action,))


if __name__ == "__main__":
    unittest.main()
