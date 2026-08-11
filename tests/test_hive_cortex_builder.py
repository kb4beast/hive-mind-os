from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.authority import AuthorityDenied, AuthorityRegistry
from hive_mind_os.brain_kernel.builder import (
    BuilderAction,
    BuilderActionDenied,
    BuilderActionKind,
    BuilderCoordinator,
    BuilderIterationExhausted,
)
from hive_mind_os.brain_kernel.contracts import Budget, ConstraintEnvelope
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
        self.gateway.register_adapter(self.adapter.adapter_name, self.adapter.apply)
        self.builder = BuilderCoordinator(
            self.gateway, self.registry, self.adapter, mission_id="MISSION-builder", work_id="WORK-builder",
            actor_id="builder:fixture", authority_envelope_digest=DIGEST, policy_decision_ref="POLICY-builder", now=NOW,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_builder_action_tests_use_typed_effects_and_receipts(self) -> None:
        write = BuilderAction("write-1", BuilderActionKind.WRITE, "src/result.txt", {"content": "fixed\n"}, "remove src/result.txt")
        command = BuilderAction("test-1", BuilderActionKind.COMMAND, "isolated-workspace", {"argv": ["python", "-c", "from pathlib import Path; assert Path('src/result.txt').read_text() == 'fixed\\n'"]}, "no rollback")
        executions = self.builder.repair(((write, command),), max_retries=2)
        self.assertEqual(["SUCCEEDED", "SUCCEEDED"], [item.outcome.status for item in executions])
        self.assertEqual("fixed\n", (self.root / "src" / "result.txt").read_text(encoding="utf-8"))
        self.assertTrue(all(item.effect.receipt_digest.startswith("sha256:") for item in executions))

    def test_iterative_repair_tests_keep_failed_test_evidence_then_repair(self) -> None:
        failing = BuilderAction("test-fail", BuilderActionKind.COMMAND, "isolated-workspace", {"argv": ["python", "-c", "raise SystemExit(1)"]}, "no rollback")
        write = BuilderAction("write-fix", BuilderActionKind.WRITE, "src/fixed.txt", {"content": "ok"}, "remove src/fixed.txt")
        passing = BuilderAction("test-pass", BuilderActionKind.COMMAND, "isolated-workspace", {"argv": ["python", "-c", "from pathlib import Path; assert Path('src/fixed.txt').exists()"]}, "no rollback")
        executions = self.builder.repair(((failing,), (write, passing)), max_retries=2)
        self.assertEqual("FAILED", executions[0].outcome.status)
        self.assertEqual("SUCCEEDED", executions[-1].outcome.status)
        with self.assertRaises(BuilderIterationExhausted):
            self.builder.repair(((failing,),), max_retries=0)

    def test_command_output_is_digest_only_evidence(self) -> None:
        command = BuilderAction(
            "test-output", BuilderActionKind.COMMAND, "isolated-workspace",
            {"argv": ["python", "-c", "import sys; print('sensitive-output'); print('secret-error', file=sys.stderr)"]}, "none",
        )
        execution = self.builder.execute_round("ATTEMPT-output", (command,))[0]
        self.assertEqual("SUCCEEDED", execution.outcome.status)
        self.assertTrue(execution.outcome.detail.startswith("sha256:"))
        self.assertNotIn("sensitive-output", execution.outcome.detail)

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
