from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from hive_mind_os import cli
from hive_mind_os import verify as verification
from hive_mind_os.verify import VerificationError, verify_repository


class StandaloneVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "agent-change"
        self.repository.mkdir()
        self._git("init")
        self._git("config", "user.email", "agent@example.invalid")
        self._git("config", "user.name", "Agent")
        (self.repository / "app.py").write_text(
            "def value() -> int:\n    return 1\n",
            encoding="utf-8",
        )
        (self.repository / "check_value.py").write_text(
            "from app import value\nassert value() == 2\n",
            encoding="utf-8",
        )
        tests = self.repository / "tests"
        tests.mkdir()
        (tests / "test_existing.py").write_text(
            "def test_existing() -> None:\n    assert True\n",
            encoding="utf-8",
        )
        (tests / "check_existing.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self._git("add", "app.py", "check_value.py", "tests")
        self._git("commit", "-m", "base")
        (self.repository / "app.py").write_text(
            "def value() -> int:\n    return 2\n",
            encoding="utf-8",
        )
        self._git("add", "app.py")
        self._git("commit", "-m", "agent change")
        self.candidate = self._git_text("rev-parse", "HEAD")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *arguments: str) -> None:
        completed = subprocess.run(
            ("git", "-C", str(self.repository), *arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _git_text(self, *arguments: str) -> str:
        completed = subprocess.run(
            ("git", "-C", str(self.repository), *arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def _commit(self, message: str, *paths: str) -> str:
        self._git("add", "--", *paths)
        self._git("commit", "-m", message)
        self.candidate = self._git_text("rev-parse", "HEAD")
        return self.candidate

    def _specification(
        self,
        *,
        paths: list[str] | None = None,
        command: list[str] | None = None,
    ) -> Path:
        specification = self.root / f"acceptance-{time.monotonic_ns()}.json"
        specification.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "value-is-two",
                    "criterion": "value returns two",
                    "command": {
                        "argv": command or [sys.executable, "check_value.py"],
                        "expected": "succeeded",
                    },
                    "declared_paths": paths or ["app.py"],
                }
            ),
            encoding="utf-8",
        )
        return specification

    def _verify(
        self,
        specification: Path,
        bundle_name: str = "bundle",
        *,
        candidate: str | None = None,
    ):
        return verify_repository(
            self.repository,
            specification,
            self.root / bundle_name,
            candidate or self.candidate,
        )

    def test_seals_before_candidate_access_and_emits_a_self_verifying_bundle(self) -> None:
        report = self._verify(self._specification())

        self.assertEqual(report.verdict, "adopt")
        self.assertLess(report.seal_sequence, report.repository_read_sequence)
        self.assertTrue(report.report_path.is_file())
        document = json.loads(report.report_path.read_text(encoding="utf-8"))
        self.assertEqual(document["changed_paths"], ["app.py"])
        self.assertEqual(document["candidate"]["commit"], self.candidate)
        self.assertEqual(
            document["candidate"]["tree"],
            self._git_text("rev-parse", f"{self.candidate}^{{tree}}"),
        )
        self.assertFalse(document["materialization"]["source_worktree_used_for_execution"])
        self.assertTrue(document["checks"][0]["matched"])
        self.assertTrue((report.report_path.parent / "receipts").is_dir())
        receipt = document["checks"][0]["receipt"]
        assert isinstance(receipt, dict)
        receipt_document = json.loads(
            (
                report.report_path.parent
                / "receipts"
                / str(receipt["path"])
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            receipt_document["execution"]["acceptance_specification"]["candidate_commit"],
            self.candidate,
        )
        verification.verify_bundle(report.report_path.parent)

    def test_executes_only_the_immutable_candidate_not_dirty_or_untracked_source_bytes(self) -> None:
        (self.repository / "app.py").write_text(
            "def value() -> int:\n    return 999\n", encoding="utf-8"
        )
        (self.repository / "caller_only.py").write_text("raise RuntimeError\n", encoding="utf-8")

        report = self._verify(self._specification(), "dirty-source-bundle")

        self.assertEqual(report.verdict, "adopt")
        document = json.loads(report.report_path.read_text(encoding="utf-8"))
        self.assertEqual(document["candidate"]["commit"], self.candidate)
        self.assertEqual(document["checks"][0]["candidate_commit"], self.candidate)

    def test_concurrent_source_mutation_after_sealing_cannot_change_the_verdict(self) -> None:
        (self.repository / "check_value.py").write_text(
            "import time\ntime.sleep(0.2)\nfrom app import value\nassert value() == 2\n",
            encoding="utf-8",
        )
        self._commit("make check wait", "check_value.py")
        specification = self._specification(paths=["check_value.py"])

        def mutate_source() -> None:
            time.sleep(0.05)
            (self.repository / "app.py").write_text(
                "def value() -> int:\n    return 77\n", encoding="utf-8"
            )
            (self.repository / "untracked_runtime_helper.py").write_text(
                "raise RuntimeError\n", encoding="utf-8"
            )

        mutator = threading.Thread(target=mutate_source)
        mutator.start()
        try:
            report = self._verify(specification, "concurrent-source-bundle")
        finally:
            mutator.join(timeout=2)

        self.assertEqual(report.verdict, "adopt")
        self.assertEqual(
            json.loads(report.report_path.read_text(encoding="utf-8"))["candidate"]["commit"],
            self.candidate,
        )

    def test_requires_a_full_immutable_candidate_commit_before_publishing(self) -> None:
        output = self.root / "mutable-candidate-bundle"
        with self.assertRaisesRegex(VerificationError, "full 40-hex"):
            verify_repository(self.repository, self._specification(), output, "HEAD")
        self.assertFalse(output.exists())

    def test_cleanup_uses_the_python_311_callback_name(self) -> None:
        with (
            patch.object(verification.sys, "version_info", (3, 11, 0)),
            patch.object(verification.shutil, "rmtree") as remove_tree,
        ):
            verification._rmtree(self.root / "private-worktree")

        self.assertEqual(remove_tree.call_count, 1)
        self.assertIn("onerror", remove_tree.call_args.kwargs)
        self.assertNotIn("onexc", remove_tree.call_args.kwargs)

    def test_rejects_external_git_filter_configuration_before_materialization(self) -> None:
        self._git("config", "filter.hive-test.smudge", "echo contaminated")
        output = self.root / "filter-bundle"

        with self.assertRaisesRegex(VerificationError, "filter"):
            verify_repository(self.repository, self._specification(), output, self.candidate)

        self.assertFalse(output.exists())

    def test_rejects_configured_source_hook_without_executing_it(self) -> None:
        hooks = self.root / "source-hooks"
        hooks.mkdir()
        marker = self.root / "hook-ran.txt"
        hook = hooks / "post-checkout"
        hook.write_text(f"echo ran > '{marker.as_posix()}'\n", encoding="utf-8")
        try:
            hook.chmod(0o755)
        except OSError:
            pass
        self._git("config", "core.hooksPath", str(hooks))

        with self.assertRaisesRegex(VerificationError, "hooks"):
            self._verify(self._specification(), "hook-bundle")

        self.assertFalse(marker.exists())

    def test_rejects_lfs_pointer_content_and_publishes_nothing(self) -> None:
        (self.repository / "large.bin").write_text(
            "version https://git-lfs.github.com/spec/v1\noid sha256:" + "0" * 64 + "\nsize 1\n",
            encoding="ascii",
        )
        self._commit("add lfs pointer", "large.bin")
        output = self.root / "lfs-bundle"

        with self.assertRaisesRegex(VerificationError, "LFS"):
            verify_repository(
                self.repository,
                self._specification(paths=["large.bin"]),
                output,
                self.candidate,
            )

        self.assertFalse(output.exists())

    def test_rejects_symlink_candidate_layout_when_supported(self) -> None:
        link = self.repository / "link.py"
        try:
            link.symlink_to("app.py")
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        self._commit("add symlink", "link.py")

        with self.assertRaisesRegex(VerificationError, "symlink"):
            self._verify(self._specification(paths=["link.py"]), "symlink-bundle")

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_rejects_a_repository_path_through_a_windows_junction(self) -> None:
        junction = self.root / "repository-junction"
        created = subprocess.run(
            ("cmd", "/c", "mklink", "/J", str(junction), str(self.repository)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if created.returncode != 0:
            self.skipTest(f"junction creation unavailable: {created.stderr.strip()}")

        with self.assertRaisesRegex(VerificationError, "symlink or junction"):
            verify_repository(
                junction,
                self._specification(),
                self.root / "junction-bundle",
                self.candidate,
            )

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_rejects_an_output_parent_through_a_windows_junction(self) -> None:
        target = self.root / "output-target"
        target.mkdir()
        junction = self.root / "output-junction"
        created = subprocess.run(
            ("cmd", "/c", "mklink", "/J", str(junction), str(target)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if created.returncode != 0:
            self.skipTest(f"junction creation unavailable: {created.stderr.strip()}")

        with self.assertRaisesRegex(VerificationError, "symlink or junction"):
            verify_repository(
                self.repository,
                self._specification(),
                junction / "bundle",
                self.candidate,
            )

    def test_rejects_a_candidate_that_deletes_an_existing_test(self) -> None:
        (self.repository / "tests" / "test_existing.py").unlink()
        self._git("rm", "tests/test_existing.py")
        self._git("commit", "-m", "delete test")
        self.candidate = self._git_text("rev-parse", "HEAD")

        report = self._verify(
            self._specification(paths=["tests/test_existing.py"]),
            "deleted-test-bundle",
        )

        self.assertEqual(report.verdict, "reject")
        self.assertEqual(report.weakened_tests, ("tests/test_existing.py",))

    def test_non_python_test_changes_are_not_silently_counted_as_passing_analysis(self) -> None:
        (self.repository / "tests" / "check_existing.sh").write_text(
            "#!/bin/sh\nexit 1\n", encoding="utf-8"
        )
        self._commit("change shell test", "tests/check_existing.sh")

        report = self._verify(
            self._specification(paths=["tests/check_existing.sh"]),
            "non-python-test-bundle",
        )

        self.assertEqual(report.verdict, "reject")
        document = json.loads(report.report_path.read_text(encoding="utf-8"))
        self.assertEqual(document["test_analysis"]["not_evaluated"], ["tests/check_existing.sh"])

    def test_declared_scope_must_include_modified_fixture_paths(self) -> None:
        fixtures = self.repository / "tests" / "fixtures"
        fixtures.mkdir()
        (fixtures / "value.json").write_text('{"value": 2}\n', encoding="utf-8")
        self._commit("add fixture", "tests/fixtures/value.json")

        report = self._verify(self._specification(paths=[]), "omitted-fixture-bundle")

        self.assertEqual(report.verdict, "reject")
        self.assertEqual(report.undeclared_paths, ("tests/fixtures/value.json",))

    def test_environment_is_scrubbed_and_output_truncation_is_receipted(self) -> None:
        sentinel = "HIVE_MIND_VERIFY_SENTINEL"
        (self.repository / "check_value.py").write_text(
            "import os\nassert os.environ.get('HIVE_MIND_VERIFY_SENTINEL') is None\n"
            "print('x' * 4096)\nfrom app import value\nassert value() == 2\n",
            encoding="utf-8",
        )
        self._commit("assert scrubbed environment", "check_value.py")
        with patch.dict(os.environ, {sentinel: "contaminated"}), patch.object(
            verification, "_CHECK_MAX_OUTPUT_BYTES", 64
        ):
            report = self._verify(
                self._specification(paths=["check_value.py"]),
                "truncated-output-bundle",
            )

        self.assertEqual(report.verdict, "adopt")
        document = json.loads(report.report_path.read_text(encoding="utf-8"))
        self.assertTrue(document["checks"][0]["output_truncated"])

    def test_timeout_is_receipted_and_cannot_adopt(self) -> None:
        (self.repository / "check_value.py").write_text(
            "import time\ntime.sleep(10)\n", encoding="utf-8"
        )
        self._commit("make check hang", "check_value.py")
        with patch.object(verification, "_CHECK_TIMEOUT_SECONDS", 0.05):
            report = self._verify(
                self._specification(paths=["check_value.py"]),
                "timeout-bundle",
            )

        self.assertEqual(report.verdict, "reject")
        document = json.loads(report.report_path.read_text(encoding="utf-8"))
        self.assertEqual(document["checks"][0]["outcome"], "timeout")

    def test_interrupted_self_verification_never_publishes_a_partial_bundle(self) -> None:
        output = self.root / "interrupted-bundle"
        with patch.object(
            verification,
            "_self_verify_bundle",
            side_effect=VerificationError("simulated publication interruption"),
        ):
            with self.assertRaisesRegex(VerificationError, "simulated publication"):
                verify_repository(self.repository, self._specification(), output, self.candidate)

        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob(".hive-mind-verify-*")), [])

    def test_cli_requires_the_candidate_and_returns_success_for_an_adopted_verdict(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = cli._run_verify(
                cli.build_verify_parser().parse_args(
                    [
                        "--repository",
                        str(self.repository),
                        "--spec",
                        str(self._specification()),
                        "--candidate",
                        self.candidate,
                        "--output",
                        str(self.root / "cli-bundle"),
                    ]
                )
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "adopt")


if __name__ == "__main__":
    unittest.main()
