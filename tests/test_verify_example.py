"""Exercise the offline ``examples/verify-an-agent-change`` verification example.

The example commits a checked-in agent patch locally and verifies it with the
standalone ``verify`` pipeline.  This suite covers the whole runner without a
network, without live LLM credentials, and without third-party test
dependencies:

* Integration: run the real runner against a fresh temporary directory and
  assert exit status, verdict, changed paths, sealing order, and the published
  bundle artifacts (GitHub kb4beast/hive-mind-os#98).
* Unit: mock ``subprocess`` and the runner's Git helpers to assert the exact
  state transitions (init -> author -> add -> baseline commit -> apply patch
  -> add -> agent commit) and the failure paths return status 1 with a
  ``Example failed`` diagnostic instead of suggesting success.
"""

from __future__ import annotations

import ast
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "verify-an-agent-change"
EXAMPLE_RUNNER = EXAMPLE_ROOT / "run_example.py"
ACCEPTANCE_SPECIFICATION = EXAMPLE_ROOT / "acceptance-spec.json"

_CREDENTIAL_ENVIRON_VARS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "HIVE_MIND_MODEL_PROVIDER",
    "HIVE_MIND_MODEL_BASE_URL",
    "HIVE_MIND_MODEL_MODEL",
    "HIVE_MIND_MODEL_API_KEY_ENV",
)
_PROXY_ENVIRON_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def _load_example_runner():
    """Import ``run_example.py`` as a plain module so tests can mock it."""
    spec = importlib.util.spec_from_file_location(
        "verify_agent_change_example_runner", EXAMPLE_RUNNER
    )
    example_runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(example_runner)
    return example_runner


runner = _load_example_runner()


def _fake_completed(
    returncode: int,
    stdout: bytes | str = b"",
    stderr: bytes | str = b"",
    *,
    text: bool = False,
):
    if not text:
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8")
    return subprocess.CompletedProcess(
        ("fake",),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _example_environment() -> dict[str, str]:
    """Environment that can reach only the local filesystem, never a model."""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY_ROOT / "src")
    for name in (*_CREDENTIAL_ENVIRON_VARS, *_PROXY_ENVIRON_VARS):
        environment.pop(name, None)
    return environment


def _write_adopted_bundle(
    bundle: Path,
    *,
    changed_paths: list[str] | None = None,
    seal_sequence: int = 41,
    repository_read_sequence: int = 42,
) -> None:
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "verification.json").write_text(
        json.dumps(
            {
                "verdict": "adopt",
                "changed_paths": changed_paths or ["discounts.py"],
                "seal_sequence": seal_sequence,
                "repository_read_sequence": repository_read_sequence,
            }
        ),
        encoding="utf-8",
    )


def _adopt_verify_response(
    bundle: Path,
    *,
    changed_paths: list[str] | None = None,
    seal_sequence: int = 41,
    repository_read_sequence: int = 42,
) -> subprocess.CompletedProcess:
    """Model the real ``hive-mind verify`` CLI: publish the bundle, then report."""
    paths = changed_paths or ["discounts.py"]
    _write_adopted_bundle(
        bundle,
        changed_paths=paths,
        seal_sequence=seal_sequence,
        repository_read_sequence=repository_read_sequence,
    )
    return _fake_completed(
        0,
        stdout=json.dumps(
            {
                "status": "adopt",
                "report": str(bundle / "verification.json"),
                "changed_paths": paths,
                "undeclared_paths": [],
                "weakened_tests": [],
            }
        ),
        stderr="",
        text=True,
    )


def _pipeline(repository: Path, candidate: str, verify_factory) -> MagicMock:
    """Build the ``subprocess.run`` mock for the runner's success path."""

    def dispatch(argv, **kwargs):
        arguments = tuple(argv)
        if arguments and arguments[0] == "git":
            return _fake_completed(0, stdout=candidate + "\n")
        return verify_factory(repository.parent / "receipt-bundle")

    return MagicMock(side_effect=dispatch)


class VerificationExampleIntegrationTests(unittest.TestCase):
    def test_example_runner_publishes_an_adopted_sealed_bundle_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "example-out"
            completed = subprocess.run(
                (sys.executable, str(EXAMPLE_RUNNER), "--output", str(output)),
                cwd=REPOSITORY_ROOT,
                env=_example_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=60,
            )

            self.assertEqual(
                completed.returncode,
                0,
                f"example stderr:\n{completed.stderr}\nexample stdout:\n{completed.stdout}",
            )
            self.assertIn(
                "Example complete: committed Codex agent patch verified.", completed.stdout
            )
            self.assertIn("Curator verdict: adopt", completed.stdout)
            self.assertIn("Changed paths: discounts.py", completed.stdout)

            bundle = output / "receipt-bundle"
            self.assertTrue((bundle / "verification.json").is_file())
            self.assertTrue((bundle / "ledger.sqlite3").is_file())
            self.assertTrue((bundle / "acceptance.json").is_file())
            self.assertTrue((bundle / "integrity.json").is_file())
            self.assertTrue((bundle / "receipts").is_dir())

            verification = json.loads(
                (bundle / "verification.json").read_text(encoding="utf-8")
            )
            self.assertEqual(verification["verdict"], "adopt")
            self.assertEqual(verification["changed_paths"], ["discounts.py"])
            self.assertEqual(
                json.loads((bundle / "acceptance.json").read_text(encoding="utf-8"))[
                    "command"
                ]["argv"],
                ["python", "check_discount.py"],
            )
            self.assertLess(
                verification["seal_sequence"],
                verification["repository_read_sequence"],
            )

    def test_example_environment_scrubs_credentials_and_proxies(self) -> None:
        environment = _example_environment()
        for name in _CREDENTIAL_ENVIRON_VARS:
            self.assertNotIn(name, environment)
        for name in _PROXY_ENVIRON_VARS:
            self.assertNotIn(name, environment)
        self.assertIn("PYTHONPATH", environment)


class VerificationExampleUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.output = Path(self.temporary.name) / "example-out"
        self.repository = self.output / "nonprofit-checkout"
        self.bundle = self.output / "receipt-bundle"
        self.candidate = "c" * 40

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run_main(self, prepare, process):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(runner, "_prepare_repository", prepare),
            patch.object(runner.subprocess, "run", process),
            patch("sys.argv", ["run_example.py", "--output", str(self.output)]),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            status = runner.main()
        return status, stdout.getvalue(), stderr.getvalue()

    def test_runner_imports_only_stdlib_modules_without_network_clients(self) -> None:
        self.assertEqual(
            set(runner.__dict__).intersection(
                {"requests", "httpx", "aiohttp", "urllib", "http", "anthropic", "openai"}
            ),
            set(),
        )
        source = EXAMPLE_RUNNER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        self.assertNotIn("hive_mind_os", imported)
        self.assertTrue(
            imported
            <= {
                "__future__",
                "argparse",
                "json",
                "pathlib",
                "shutil",
                "subprocess",
                "sys",
            }
        )

    def test_git_runner_uses_the_exact_verified_invocation(self) -> None:
        repository = Path("/tmp/agent-repo")

        with patch.object(runner.subprocess, "run") as run_git:
            run_git.return_value = _fake_completed(0)
            runner._run_git(repository, "add", "discounts.py")

        self.assertEqual(run_git.call_count, 1)
        call = run_git.call_args
        self.assertEqual(
            call.args[0],
            ("git", "-C", str(repository), "add", "discounts.py"),
        )
        self.assertIs(call.kwargs.get("stdin"), subprocess.DEVNULL)
        self.assertFalse(call.kwargs.get("check"))
        self.assertTrue(call.kwargs.get("text"))

    def test_git_runner_surfaces_failing_git_output_as_a_runtime_error(self) -> None:
        with patch.object(runner.subprocess, "run") as run_git:
            run_git.return_value = _fake_completed(
                1, stderr=b"fatal: not a git repository\n"
            )
            with self.assertRaisesRegex(RuntimeError, "fatal: not a git repository"):
                runner._run_git(Path("/tmp/agent-repo"), "init", "--quiet")

        self.assertEqual(run_git.call_count, 1)

    def test_prepare_repository_executes_the_sealed_security_state_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "example-out"
            output.mkdir()
            repository = output / "nonprofit-checkout"
            repository.mkdir()
            (repository / "discounts.py").write_bytes(
                b"def discount():\r\n    return 0\r\n"
            )
            (repository / "check_discount.py").write_bytes(
                b"assert discount()\r\n"
            )
            git_commands: list[tuple[str, ...]] = []

            def record_git(command_root: Path, *arguments: str) -> None:
                git_commands.append((str(command_root), *arguments))

            with patch.object(runner.shutil, "copytree") as copy_tree, patch.object(
                runner, "_run_git", side_effect=record_git
            ):
                prepared = runner._prepare_repository(output)

            self.assertEqual(prepared, repository)
            self.assertTrue(copy_tree.called)
            self.assertIs(copy_tree.call_args.args[0], runner.BASE_REPOSITORY)
            self.assertEqual(
                git_commands,
                [
                    (str(repository), "init", "--quiet"),
                    (str(repository), "config", "user.name", "Example Maintainer"),
                    (
                        str(repository),
                        "config",
                        "user.email",
                        "maintainer@example.invalid",
                    ),
                    (str(repository), "add", "discounts.py", "check_discount.py"),
                    (str(repository), "commit", "--quiet", "-m", "baseline checkout rule"),
                    (
                        str(repository),
                        "apply",
                        "--whitespace=error",
                        str(output / "agent-change.normalized.patch"),
                    ),
                    (str(repository), "add", "discounts.py"),
                    (
                        str(repository),
                        "commit",
                        "--quiet",
                        "--author",
                        "Codex Example Agent <codex@example.invalid>",
                        "-m",
                        "agent: apply nonprofit discount",
                    ),
                ],
            )
            self.assertEqual(
                (repository / "discounts.py").read_bytes(),
                b"def discount():\n    return 0\n",
            )
            self.assertEqual(
                (repository / "check_discount.py").read_bytes(),
                b"assert discount()\n",
            )
            self.assertEqual(
                (output / "agent-change.normalized.patch").read_bytes().count(b"\r"),
                0,
            )

    def test_main_success_prints_status_lines_and_invokes_verify_exactly_once(self) -> None:
        prepare = MagicMock(return_value=self.repository)
        process = _pipeline(self.repository, self.candidate, _adopt_verify_response)

        status, stdout, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Example complete: committed Codex agent patch verified.", stdout)
        self.assertIn(
            "Curator verdict: adopt; acceptance was sealed before the candidate was read.",
            stdout,
        )
        self.assertIn("Changed paths: discounts.py", stdout)
        self.assertIn("Receipt bundle:", stdout)
        self.assertEqual(process.call_count, 2)
        rev_parse_call, verify_call = process.call_args_list
        self.assertEqual(
            rev_parse_call.args[0],
            ("git", "-C", str(self.repository), "rev-parse", "HEAD"),
        )
        verify_argv = verify_call.args[0]
        self.assertEqual(
            verify_argv[:7],
            (
                sys.executable,
                "-m",
                "hive_mind_os.cli",
                "verify",
                "--repository",
                str(self.repository),
                "--spec",
            ),
        )
        self.assertEqual(verify_argv[7], str(ACCEPTANCE_SPECIFICATION))
        self.assertEqual(verify_argv[8:10], ("--candidate", self.candidate.encode()))
        self.assertEqual(verify_argv[10], "--output")
        self.assertEqual(
            Path(verify_argv[11]).parts[-2:],
            ("example-out", "receipt-bundle"),
        )
        document = json.loads((self.bundle / "verification.json").read_text(encoding="utf-8"))
        self.assertEqual(document["verdict"], "adopt")
        self.assertEqual(document["changed_paths"], ["discounts.py"])
        self.assertLess(document["seal_sequence"], document["repository_read_sequence"])

    def test_main_refuses_an_existing_output_directory(self) -> None:
        self.output.mkdir()
        stderr = io.StringIO()
        with (
            patch("sys.argv", ["run_example.py", "--output", str(self.output)]),
            self.assertRaises(SystemExit) as exited,
            redirect_stderr(stderr),
        ):
            runner.main()

        self.assertEqual(exited.exception.code, 2)
        self.assertIn("output directory must not already exist", stderr.getvalue())

    def test_main_reports_repository_preparation_failure(self) -> None:
        prepare = MagicMock(side_effect=RuntimeError("git init exploded"))
        process = MagicMock(side_effect=_fake_completed(0))

        status, stdout, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 1)
        self.assertIn("Example failed", stderr)
        self.assertIn("git init exploded", stderr)
        self.assertEqual(process.call_count, 0)

    def test_main_reports_unresolved_candidate_commit(self) -> None:
        prepare = MagicMock(return_value=self.repository)
        process = MagicMock(
            side_effect=[
                _fake_completed(1, stderr=b"unknown revision\n"),
            ]
        )

        status, stdout, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 1)
        self.assertIn("could not resolve the example candidate commit", stderr)
        self.assertEqual(process.call_count, 1)

    def test_main_reports_failing_verify_cli(self) -> None:
        prepare = MagicMock(return_value=self.repository)
        process = MagicMock(
            side_effect=[
                _fake_completed(0, stdout=self.candidate + "\n"),
                _fake_completed(
                    1,
                    stderr="acceptance command could not be spawned\n",
                    text=True,
                ),
            ]
        )

        status, _, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 1)
        self.assertIn("hive-mind verify failed", stderr)
        self.assertEqual(process.call_count, 2)

    def test_main_reports_a_rejected_summary(self) -> None:
        prepare = MagicMock(return_value=self.repository)

        def verify(argv, **kwargs) -> subprocess.CompletedProcess:
            _write_adopted_bundle(self.bundle)
            return _fake_completed(
                0,
                stdout=json.dumps({"status": "reject"}),
                text=True,
            )

        process = _pipeline(self.repository, self.candidate, verify)

        status, _, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 1)
        self.assertIn("verification result did not satisfy the example contract", stderr)

    def test_main_reports_undeclared_changed_paths(self) -> None:
        prepare = MagicMock(return_value=self.repository)

        def verify(argv, **kwargs):
            return _adopt_verify_response(
                self.bundle, changed_paths=["discounts.py", "untracked.py"]
            )

        process = _pipeline(self.repository, self.candidate, verify)

        status, _, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 1)
        self.assertIn("verification result did not satisfy the example contract", stderr)

    def test_main_reports_late_sealing(self) -> None:
        prepare = MagicMock(return_value=self.repository)

        def verify(argv, **kwargs):
            return _adopt_verify_response(
                self.bundle,
                seal_sequence=42,
                repository_read_sequence=41,
            )

        process = _pipeline(self.repository, self.candidate, verify)

        status, _, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 1)
        self.assertIn("verification result did not satisfy the example contract", stderr)

    def test_main_reports_unparseable_verify_output(self) -> None:
        prepare = MagicMock(return_value=self.repository)
        process = MagicMock(
            side_effect=[
                _fake_completed(0, stdout=self.candidate + "\n"),
                _fake_completed(0, stdout="<html>not json</html>", text=True),
            ]
        )

        status, _, stderr = self._run_main(prepare, process)

        self.assertEqual(status, 1)
        self.assertIn("Example failed", stderr)
        self.assertIn("Expecting value", stderr)


if __name__ == "__main__":
    unittest.main()