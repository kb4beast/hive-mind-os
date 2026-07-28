from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.autonomy import EpisodeAllowance
from hive_mind_os.git_adapter import (
    GitOperationFailed,
    GitPolicyDenied,
    GitWorkspace,
    PinViolation,
    WorkspaceDirty,
    verify_delivery,
)
from hive_mind_os.models import AutonomyLevel
from hive_mind_os.policy import Action, PolicyEngine
from hive_mind_os.receipts import (
    FileReceiptValidator,
    ReceiptReference,
    sha256_digest,
)
from hive_mind_os.sandbox import (
    ConfinementViolation,
    SandboxRunner,
    SandboxSpec,
)
from tests.fixtures.fixture_repo import (
    COMMIT_ONE_SHA,
    COMMIT_TWO_SHA,
    build_fixture_repo,
)

FIXED_HEAD_SHA = "6c4a1f8d7036a1520260c004170c740bf41b89a5"
FIXED_TREE_SHA = "e2fed4976f15a32feb343b06e51e634bddcae76c"


class GitAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.fixture = build_fixture_repo(self.base / "source-parent")
        self.counter = 0

    def workspace(self, pin: str = COMMIT_TWO_SHA) -> GitWorkspace:
        self.counter += 1
        return GitWorkspace.materialize(
            self.fixture.root,
            pin,
            self.base / f"workspace-{self.counter}",
            self.base / f"evidence-{self.counter}",
        )

    @staticmethod
    def declared_test_argv() -> list[str]:
        return [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ]

    def fix_and_commit(self) -> GitWorkspace:
        workspace = self.workspace()
        workspace.create_branch("phase/fix-increment")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        head = workspace.commit("fix: restore increment")
        self.assertEqual(head, FIXED_HEAD_SHA)
        return workspace

    def validate_receipts(self, workspace: GitWorkspace) -> None:
        validator = FileReceiptValidator(workspace.trusted_root)
        for record in workspace.receipt_records:
            validation = validator.validate(
                ReceiptReference(record["path"], record["digest"]),
                mission_id=record["mission_id"],
                state_ref=record["state_ref"],
                actor_id=record["actor_id"],
                action_id=record["action_id"],
                action_kind=record["action_kind"],
                action_digest=record["action_digest"],
            )
            self.assertTrue(validation.valid, validation.issues)

    def test_fixture_repository_has_stable_pinned_history(self) -> None:
        second_parent = self.base / "second-parent"
        repeated = build_fixture_repo(second_parent)
        self.assertEqual(
            (self.fixture.commit_one, self.fixture.commit_two),
            (COMMIT_ONE_SHA, COMMIT_TWO_SHA),
        )
        self.assertEqual(
            (repeated.commit_one, repeated.commit_two),
            (COMMIT_ONE_SHA, COMMIT_TWO_SHA),
        )

    def test_materialize_exact_detached_pin_and_inert_hooks(self) -> None:
        workspace = self.workspace(COMMIT_ONE_SHA)
        head = workspace._git_text(
            ["rev-parse", "HEAD"],
            Action.READ_REPOSITORY,
            "test exact materialized head",
        )
        symbolic = workspace._run_git(
            ["symbolic-ref", "-q", "HEAD"],
            Action.READ_REPOSITORY,
            "test detached head",
            allow_failure=True,
        )[0]
        self.assertEqual(head, COMMIT_ONE_SHA)
        self.assertEqual(symbolic["result"], "failed")
        self.assertFalse((self.fixture.root.parent / "fixture-hook-ran.txt").exists())

    def test_materialize_excludes_local_codex_bookkeeping_refs(self) -> None:
        bookkeeping = (
            self.fixture.root
            / ".git"
            / "refs"
            / "codex"
            / "turn-diffs"
            / "checkpoints"
            / ("a" * 16)
            / ("b" * 16)
        )
        bookkeeping.mkdir(parents=True)
        (bookkeeping / "1785167248210").write_text(
            COMMIT_TWO_SHA + "\n",
            encoding="ascii",
        )
        workspace = self.workspace()
        self.assertFalse(
            (
                workspace.container_root
                / "source"
                / ".git"
                / "refs"
                / "codex"
            ).exists()
        )
        self.assertEqual(
            workspace._git_text(
                ["rev-parse", "HEAD"],
                Action.READ_REPOSITORY,
                "test materialized head without app refs",
            ),
            COMMIT_TWO_SHA,
        )
        if os.name == "nt":
            self.assertIn("SYSTEMROOT", workspace.runner.spec.env_allowlist)

    def test_materialize_ignores_host_global_git_configuration(self) -> None:
        global_config = self.base / "host-global.gitconfig"
        global_config.write_text(
            "[alias]\n\thive-forbidden = status\n",
            encoding="utf-8",
        )
        with patch.dict(
            os.environ,
            {
                "GIT_CONFIG_GLOBAL": str(global_config),
                "GIT_CONFIG_NOSYSTEM": "0",
            },
        ):
            workspace = self.workspace(COMMIT_ONE_SHA)
            receipt, output = workspace._run_git(
                ["config", "--global", "--get", "alias.hive-forbidden"],
                Action.READ_REPOSITORY,
                "verify isolated global Git configuration",
                allow_failure=True,
            )
        self.assertEqual(receipt["result"], "failed")
        self.assertEqual(output, b"")

    def test_mutable_and_short_pins_are_rejected(self) -> None:
        for pin in ("main", "v1.0", COMMIT_ONE_SHA[:12]):
            with self.subTest(pin=pin):
                with self.assertRaises(PinViolation):
                    self.workspace(pin)

    def test_repository_urls_are_rejected(self) -> None:
        for source in (
            "https://example.invalid/repo.git",
            "file:///tmp/repo.git",
            "git@example.invalid:repo.git",
            r"\\example.invalid\share\repo.git",
        ):
            with self.subTest(source=source):
                with self.assertRaises(PinViolation):
                    GitWorkspace.materialize(
                        source,
                        COMMIT_ONE_SHA,
                        self.base / f"url-{self.counter}",
                        self.base / f"url-evidence-{self.counter}",
                    )
                self.counter += 1

    def test_branch_edit_commit_diff_tree_and_receipts(self) -> None:
        workspace = self.workspace()
        workspace.create_branch("phase/fix-increment")
        hook = workspace.root / ".git" / "hooks" / "pre-commit"
        hook.write_bytes(
            b"#!/bin/sh\nprintf hook-ran > hook-ran.txt\nexit 1\n"
        )
        try:
            hook.chmod(0o755)
        except OSError:
            pass
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        diff, digest = workspace.diff()
        self.assertIn(b"-    return value - 1", diff)
        self.assertIn(b"+    return value + 1", diff)
        self.assertTrue(digest.startswith("sha256:"))
        head = workspace.commit("fix: restore increment")
        self.assertEqual(head, FIXED_HEAD_SHA)
        self.assertFalse((workspace.root / "hook-ran.txt").exists())
        tree = workspace._git_text(
            ["rev-parse", "HEAD^{tree}"],
            Action.READ_REPOSITORY,
            "test committed tree",
        )
        self.assertEqual(tree, FIXED_TREE_SHA)
        self.validate_receipts(workspace)

    def test_write_file_rejects_nonportable_and_escaping_paths(self) -> None:
        workspace = self.workspace()
        for path in (
            "../outside.txt",
            "/absolute.txt",
            r"nested\windows.txt",
            ".git/HEAD",
            ".GIT/config",
        ):
            with self.subTest(path=path):
                with self.assertRaises((ValueError, ConfinementViolation)):
                    workspace.write_file(path, b"denied")

    def test_lower_authority_cannot_write_git_metadata(self) -> None:
        workspace = self.workspace()
        workspace.policy = PolicyEngine(AutonomyLevel.SANDBOX)
        with self.assertRaises(GitPolicyDenied):
            workspace.create_branch("phase/typed-denial")
        original_head = (workspace.root / ".git" / "HEAD").read_bytes()
        for path in (".git/HEAD", ".GIT/refs/heads/metadata-bypass"):
            with self.subTest(path=path):
                with self.assertRaises(ConfinementViolation):
                    workspace.write_file(path, b"ref: refs/heads/metadata-bypass\n")
        self.assertEqual((workspace.root / ".git" / "HEAD").read_bytes(), original_head)

    def test_declared_tests_fail_at_fixture_head_and_pass_after_fix(self) -> None:
        workspace = self.workspace()
        failed = workspace.run_tests(self.declared_test_argv())
        self.assertEqual(failed["result"], "failed")
        self.assertNotEqual(failed["execution"]["exit_code"], 0)
        self.assertIn(
            b"FAIL: test_increment_regression",
            workspace._artifact(failed, "stderr"),
        )
        workspace.create_branch("phase/fix-increment")
        workspace.write_file(
            "tiny_pkg/maths.py",
            b"def increment(value: int) -> int:\n    return value + 1\n",
        )
        workspace.commit("fix: restore increment")
        passed = workspace.run_tests(self.declared_test_argv())
        self.assertEqual(
            passed["result"],
            "succeeded",
            workspace._artifact(passed, "stderr").decode("utf-8", "replace"),
        )
        self.assertEqual(passed["execution"]["exit_code"], 0)

    def test_export_and_verify_delivery_with_resolvable_receipts(self) -> None:
        workspace = self.fix_and_commit()
        delivery = workspace.export_delivery(self.base / "delivery")
        self.assertTrue(verify_delivery(delivery.root, self.fixture.root))
        manifest = json.loads(delivery.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["head_sha"], FIXED_HEAD_SHA)
        self.assertEqual(manifest["head_tree"], FIXED_TREE_SHA)
        self.assertEqual(manifest["files"], ["tiny_pkg/maths.py"])
        self.validate_receipts(workspace)

        golden = json.loads(
            (
                Path(__file__).parent
                / "fixtures"
                / "git"
                / "delivery.json"
            ).read_text(encoding="utf-8")
        )
        normalized = deepcopy(manifest)
        normalized["bundle_digest"] = "<git-serialization-digest>"
        normalized["patch_digest"] = "<git-serialization-digest>"
        normalized["receipts"] = ["<content-addressed-receipts>"]
        self.assertEqual(normalized, golden)

        original_manifest = delivery.manifest_path.read_bytes()
        invalid_manifests = []
        for schema_version in (999, True):
            invalid = deepcopy(manifest)
            invalid["schema_version"] = schema_version
            invalid_manifests.append(invalid)
        empty_receipts = deepcopy(manifest)
        empty_receipts["receipts"] = []
        invalid_manifests.append(empty_receipts)
        truncated_receipts = deepcopy(manifest)
        truncated_receipts["receipts"] = truncated_receipts["receipts"][:1]
        invalid_manifests.append(truncated_receipts)
        escaping_file = deepcopy(manifest)
        escaping_file["files"] = ["../escape"]
        invalid_manifests.append(escaping_file)
        for invalid_manifest in invalid_manifests:
            delivery.manifest_path.write_text(
                json.dumps(invalid_manifest, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            self.assertFalse(verify_delivery(delivery.root, self.fixture.root))
            delivery.manifest_path.write_bytes(original_manifest)

        first_receipt = delivery.root / "evidence" / manifest["receipts"][0]["path"]
        original_receipt = first_receipt.read_bytes()
        first_receipt.write_bytes(b"{}")
        self.assertFalse(verify_delivery(delivery.root, self.fixture.root))
        first_receipt.write_bytes(original_receipt)

        tampered_patch = delivery.patch_path.read_bytes() + b"\n# coherent tamper\n"
        delivery.patch_path.write_bytes(tampered_patch)
        manifest["patch_digest"] = sha256_digest(tampered_patch)
        delivery.manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        self.assertFalse(verify_delivery(delivery.root, self.fixture.root))

    def test_dirty_workspace_cannot_export_delivery(self) -> None:
        workspace = self.workspace()
        workspace.create_branch("phase/dirty")
        workspace.write_file("dirty.txt", b"uncommitted")
        with self.assertRaises(WorkspaceDirty):
            workspace.export_delivery(self.base / "dirty-delivery")

    def test_preexisting_delivery_root_is_rejected_before_any_write(self) -> None:
        workspace = self.fix_and_commit()
        delivery_root = self.base / "unsafe-delivery"
        outside = self.base / "outside-evidence"
        delivery_root.mkdir()
        outside.mkdir()
        evidence = delivery_root / "evidence"
        try:
            evidence.symlink_to(outside, target_is_directory=True)
        except OSError:
            evidence.mkdir()
        with self.assertRaises(WorkspaceDirty):
            workspace.export_delivery(delivery_root)
        self.assertEqual(list(outside.iterdir()), [])

    def test_verifier_rejects_escaped_evidence_root(self) -> None:
        workspace = self.fix_and_commit()
        delivery = workspace.export_delivery(self.base / "delivery")
        evidence = delivery.root / "evidence"
        outside = self.base / "outside-evidence"
        evidence.rename(outside)
        try:
            evidence.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != "nt":
                self.skipTest("directory symlinks are unavailable")
            linked = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(evidence), str(outside)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                check=False,
            )
            if linked.returncode != 0:
                self.skipTest("directory junctions are unavailable")
        self.assertFalse(verify_delivery(delivery.root, self.fixture.root))
        if evidence.is_symlink():
            evidence.unlink()
        else:
            evidence.rmdir()
        outside.rename(evidence)

    def test_truncated_git_output_fails_closed(self) -> None:
        workspace = self.workspace()
        workspace.write_file("tiny_pkg/maths.py", b"x" * 4096)
        git_name = Path(shutil.which("git") or "git").name
        workspace.runner = SandboxRunner(
            SandboxSpec(
                workspace.root,
                argv_allowlist=(git_name,),
                timeout_s=5.0,
                max_output_bytes=64,
            ),
            workspace.trusted_root,
            EpisodeAllowance(5, 5.0),
            policy=workspace.policy,
            role=workspace.role,
            runner_identity="git-sandbox-runner-v1",
        )
        with self.assertRaisesRegex(GitOperationFailed, "output limit"):
            workspace.diff()
        self.assertEqual(workspace.receipt_records[-1]["result"], "succeeded")

    def test_policy_denial_occurs_before_git_spawn(self) -> None:
        workspace = self.workspace()
        workspace.policy = PolicyEngine(AutonomyLevel.OBSERVE)
        before = workspace.runner.spawn_count
        with self.assertRaises(GitPolicyDenied):
            workspace.create_branch("phase/denied")
        self.assertEqual(workspace.runner.spawn_count, before)

    def test_run_tests_cannot_bypass_typed_git_authority(self) -> None:
        workspace = self.workspace()
        workspace.policy = PolicyEngine(AutonomyLevel.SANDBOX)
        with self.assertRaises(GitPolicyDenied):
            workspace.create_branch("phase/typed-denial")
        before = workspace.runner.spawn_count
        git = shutil.which("git") or "git"
        bypasses = (
            [git, "switch", "-c", "phase/bypass"],
            [git, "push", "origin", "HEAD:refs/heads/forbidden-push"],
        )
        for argv in bypasses:
            with self.subTest(argv=argv):
                with self.assertRaisesRegex(GitPolicyDenied, "reserved"):
                    workspace.run_tests(argv)
        self.assertEqual(workspace.runner.spawn_count, before)
        self.assertFalse((workspace.root / ".git" / "refs" / "heads" / "bypass").exists())
        self.assertFalse(
            (
                workspace.container_root
                / "source"
                / ".git"
                / "refs"
                / "heads"
                / "forbidden-push"
            ).exists()
        )

    def test_api_has_no_merge_rebase_or_force_surface(self) -> None:
        forbidden = [
            name
            for name in dir(GitWorkspace)
            if any(
                keyword in name.lower()
                for keyword in ("merge", "rebase", "force")
            )
        ]
        self.assertEqual(forbidden, [])
        self.assertEqual(
            [name for name in dir(GitWorkspace) if "push" in name.lower()],
            ["push_branch"],
        )
if __name__ == "__main__":
    unittest.main()
