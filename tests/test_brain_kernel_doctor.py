from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import cast

from hive_mind_os import cli
from hive_mind_os.brain_kernel.doctor import (
    assert_kernel_import_boundary,
    inspect_kernel_environment,
)


class KernelDoctorTests(unittest.TestCase):
    def git_fixture(self, root: Path) -> Path:
        repository = root / "repository"
        repository.mkdir()
        subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
        (repository / "README.md").write_text("# fixture\n", encoding="utf-8")
        subprocess.run(("git", "add", "README.md"), cwd=repository, check=True)
        subprocess.run(
            (
                "git",
                "-c",
                "user.name=Kernel Doctor Test",
                "-c",
                "user.email=kernel-doctor@example.test",
                "commit",
                "-qm",
                "fixture",
            ),
            cwd=repository,
            check=True,
        )
        return repository

    def check(self, report: dict[str, object], name: str) -> dict[str, object]:
        checks = cast(object, report["checks"])
        self.assertIsInstance(checks, list)
        for check in cast(list[object], checks):
            if isinstance(check, dict) and check.get("name") == name:
                return check
        self.fail(f"missing doctor check: {name}")

    def test_clean_fixture_reports_readiness_without_creating_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.git_fixture(root)
            state_dir = root / "state"

            report = inspect_kernel_environment(repository, state_dir=state_dir)

            self.assertEqual(report["status"], "ready")
            self.assertEqual(self.check(report, "repository")["status"], "clean")
            self.assertEqual(self.check(report, "state_directory")["status"], "ready")
            self.assertFalse(state_dir.exists())

    def test_dirty_worktree_is_reported_honestly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.git_fixture(root)
            (repository / "untracked.txt").write_text("dirty\n", encoding="utf-8")

            report = inspect_kernel_environment(repository, state_dir=root / "state")

            repository_check = self.check(report, "repository")
            self.assertEqual(repository_check["status"], "dirty")
            self.assertEqual(repository_check["entries"], ["?? untracked.txt"])
            self.assertEqual(report["status"], "attention")

    def test_missing_git_and_unsupported_python_are_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = inspect_kernel_environment(
                Path(temporary),
                state_dir=Path(temporary) / "state",
                git_executable="definitely-not-a-git-executable",
                python_version=(3, 10, 9),
            )

            self.assertEqual(self.check(report, "git")["status"], "missing")
            self.assertEqual(self.check(report, "python")["status"], "unsupported")
            self.assertEqual(report["status"], "attention")

    def test_unusable_state_path_and_invalid_provider_are_reported_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.git_fixture(root)
            state_file = root / "not-a-directory"
            state_file.write_text("state\n", encoding="utf-8")
            secret = "do-not-disclose-this-value"

            report = inspect_kernel_environment(
                repository,
                state_dir=state_file,
                environment={
                    "HIVE_MIND_MODEL_PROVIDER": "not-a-provider",
                    "OPENAI_API_KEY": secret,
                },
            )
            rendered = json.dumps(report, sort_keys=True)

            self.assertEqual(self.check(report, "state_directory")["status"], "unusable")
            self.assertEqual(self.check(report, "provider")["status"], "invalid")
            self.assertNotIn(secret, rendered)

    def test_protected_branch_uncertainty_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.git_fixture(root)
            subprocess.run(("git", "branch", "-M", "main"), cwd=repository, check=True)

            report = inspect_kernel_environment(repository, state_dir=root / "state")

            self.assertEqual(
                self.check(report, "protected_branch")["status"], "uncertain"
            )

    def test_ci_command_inventory_matches_the_constitutional_workflow(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        report = inspect_kernel_environment(
            project_root, state_dir=project_root / ".test-kernel-state"
        )

        self.assertEqual(self.check(report, "ci_commands")["status"], "declared")

    def test_cli_writes_redacted_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = self.git_fixture(root)
            stdout = io.StringIO()

            with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                cli.main(
                    (
                        "kernel",
                        "doctor",
                        "--repository",
                        str(repository),
                        "--state-dir",
                        str(root / "state"),
                        "--json",
                    )
                )

            self.assertEqual(raised.exception.code, 0)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["repository"], str(repository.resolve()))
            self.assertIn("checks", report)

    def test_kernel_cannot_import_repository_cortex(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        assert_kernel_import_boundary(
            project_root / "src" / "hive_mind_os" / "brain_kernel"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "brain_kernel"
            package.mkdir()
            (package / "safe.py").write_text("from pathlib import Path\n", encoding="utf-8")
            assert_kernel_import_boundary(package)
            (package / "unsafe.py").write_text(
                "from hive_mind_os.cortex import repository\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "repository cortex"):
                assert_kernel_import_boundary(package)


if __name__ == "__main__":
    unittest.main()
