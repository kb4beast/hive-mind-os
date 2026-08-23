from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402
import controller  # noqa: E402


class _KilledProcess:
    def __init__(self, stdout: object, stderr: object, *, returncode: int = -9) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.pid = 12345

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class _TimeoutProcess:
    def __init__(self) -> None:
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.returncode: int | None = None
        self.pid = 12346
        self.wait_timeouts: list[float | None] = []

    def wait(self, timeout: float | None = None) -> int:
        self.wait_timeouts.append(timeout)
        if self.returncode is None:
            raise subprocess.TimeoutExpired(("fixture",), timeout)
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


class _RuntimeErrorStream:
    def read(self, _size: int = -1) -> bytes:
        raise RuntimeError("fixture reader failure")

    def close(self) -> None:
        return None


class _FakeWindowsJob:
    def __init__(self, *, close_result: bool = True, resume_result: bool = True) -> None:
        self.close_result = close_result
        self.resume_result = resume_result
        self.assigned = False
        self.close_calls = 0

    def assign(self, _process: object) -> bool:
        self.assigned = True
        return True

    def resume(self, _process: object) -> bool:
        return self.resume_result

    def close(self) -> bool:
        self.close_calls += 1
        return self.close_result


class DoctorSubprocessBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "fixture"
        copy_autopilot_fixture(
            Path(__file__).resolve().parents[1], self.root / ".autopilot"
        )
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(
            json.dumps(control, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self.plane = controller.ControlPlane(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def child(code: str) -> tuple[str, ...]:
        return (sys.executable, "-c", code)

    def controller_check(self, code: str) -> dict[str, object]:
        with (
            patch.object(self.plane, "_controller_test_command", return_value=self.child(code)),
            patch.object(controller, "CONTROLLER_TEST_TIMEOUT_SECONDS", 2),
        ):
            return self.plane._controller_tests_check()

    @staticmethod
    def windows_job_patch(job: _FakeWindowsJob | None = None):
        if os.name != "nt":
            return contextlib.nullcontext()
        return patch.object(
            controller._WindowsJobContainment,
            "create",
            return_value=job or _FakeWindowsJob(),
        )

    def test_timeout_terminates_its_tree_without_touching_unrelated_processes(self) -> None:
        unrelated = subprocess.Popen(self.child("import time; time.sleep(10)"))
        descendant_completed = self.root / "timed-out-descendant-completed"
        parent = (
            "import pathlib, subprocess, sys, time; "
            "child = subprocess.Popen((sys.executable, '-c', "
            "'import pathlib, sys, time; time.sleep(0.8); "
            "pathlib.Path(sys.argv[1]).write_text(\"completed\", encoding=\"ascii\")', sys.argv[1])); "
            "time.sleep(30)"
        )
        try:
            with (
                patch.object(
                    self.plane,
                    "_controller_test_command",
                    return_value=(*self.child(parent), str(descendant_completed)),
                ),
                patch.object(controller, "CONTROLLER_TEST_TIMEOUT_SECONDS", 0.5),
            ):
                check = self.plane._controller_tests_check()
            self.assertIsNone(unrelated.poll(), "timeout cleanup must not kill an unrelated process")
            time.sleep(0.5)
            self.assertFalse(
                descendant_completed.exists(),
                "timeout cleanup must prevent its descendant from reaching completion",
            )
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=2)

        self.assertFalse(check["passed"])
        evidence = check["evidence"]
        self.assertEqual(evidence["failure_kind"], "timed_out")
        self.assertEqual(evidence["timeout_seconds"], 0.5)
        self.assertIsInstance(evidence["duration_seconds"], float)
        self.assertEqual(evidence["command_identity"], "exact-checkout-isolated-unittest-discover")

    def test_spawn_failure_is_typed(self) -> None:
        with patch.object(controller.subprocess, "Popen", side_effect=FileNotFoundError):
            check = self.plane._controller_tests_check()

        self.assertFalse(check["passed"])
        evidence = check["evidence"]
        self.assertEqual(evidence["failure_kind"], "spawn_failed")
        self.assertEqual(evidence["error_type"], "FileNotFoundError")
        self.assertIn("interpreter", evidence)

    @unittest.skipUnless(os.name == "nt", "Windows Job API preflight is Windows-specific")
    def test_windows_job_lookup_failure_is_typed_without_launching_or_creating_a_job(self) -> None:
        for missing_symbol in ("NtResumeProcess", "CreateJobObjectW"):
            with self.subTest(missing_symbol=missing_symbol):
                create_job = Mock(return_value=777)
                kernel32 = SimpleNamespace(
                    CreateJobObjectW=create_job,
                    SetInformationJobObject=Mock(return_value=True),
                    AssignProcessToJobObject=Mock(return_value=True),
                    CloseHandle=Mock(return_value=True),
                )
                ntdll = SimpleNamespace(NtResumeProcess=Mock(return_value=0))
                if missing_symbol == "NtResumeProcess":
                    delattr(ntdll, missing_symbol)
                else:
                    delattr(kernel32, missing_symbol)

                def load_dll(name: str, **_kwargs: object) -> object:
                    return kernel32 if name == "kernel32" else ntdll

                with (
                    patch.object(controller.ctypes, "WinDLL", side_effect=load_dll),
                    patch.object(controller.subprocess, "Popen") as popen,
                ):
                    check = self.plane._controller_tests_check()

                self.assertFalse(check["passed"])
                self.assertEqual(check["evidence"]["failure_kind"], "containment_unavailable")
                self.assertEqual(
                    check["evidence"]["error_type"],
                    "_WindowsContainmentUnavailable",
                )
                create_job.assert_not_called()
                kernel32.CloseHandle.assert_not_called()
                popen.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows Job API preflight is Windows-specific")
    def test_windows_job_setup_failure_closes_untransferred_handle_without_launching(self) -> None:
        create_job = Mock(return_value=777)
        close_handle = Mock(return_value=True)
        kernel32 = SimpleNamespace(
            CreateJobObjectW=create_job,
            SetInformationJobObject=Mock(return_value=False),
            AssignProcessToJobObject=Mock(return_value=True),
            CloseHandle=close_handle,
        )
        ntdll = SimpleNamespace(NtResumeProcess=Mock(return_value=0))

        def load_dll(name: str, **_kwargs: object) -> object:
            return kernel32 if name == "kernel32" else ntdll

        with (
            patch.object(controller.ctypes, "WinDLL", side_effect=load_dll),
            patch.object(controller.subprocess, "Popen") as popen,
        ):
            check = self.plane._controller_tests_check()

        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["failure_kind"], "containment_unavailable")
        create_job.assert_called_once_with(None, None)
        close_handle.assert_called_once_with(777)
        popen.assert_not_called()

    def test_killed_process_is_typed(self) -> None:
        killed = _KilledProcess(io.BytesIO(b"out"), io.BytesIO(b"err"))
        with self.windows_job_patch(), patch.object(controller.subprocess, "Popen", return_value=killed):
            check = self.plane._controller_tests_check()

        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["failure_kind"], "killed")
        self.assertEqual(check["evidence"]["returncode"], -9)

    def test_invalid_output_is_typed_without_fingerprint_telemetry(self) -> None:
        check = self.controller_check(
            "import sys; sys.stdout.buffer.write(b'\\xff'); sys.stderr.buffer.write(b'\\xfe')"
        )

        self.assertFalse(check["passed"])
        evidence = check["evidence"]
        self.assertEqual(evidence["failure_kind"], "undecodable_output")
        self.assertFalse(evidence["stdout"]["utf8_valid"])
        self.assertFalse(evidence["stderr"]["utf8_valid"])
        rendered = json.dumps(check, sort_keys=True)
        for forbidden in ("byte_count", "sha256", "truncated"):
            self.assertNotIn(forbidden, rendered)

    def test_direct_parent_exit_with_inherited_handles_cannot_extend_doctor(self) -> None:
        completion = self.root / "inherited-handle-descendant-completed"
        parent = (
            "import pathlib, subprocess, sys; "
            "child = subprocess.Popen((sys.executable, '-c', "
            "'import pathlib, sys, time; time.sleep(0.2); "
            "pathlib.Path(sys.argv[1]).write_text(\"completed\", encoding=\"ascii\")', sys.argv[1]))"
        )
        started = time.monotonic()
        with (
            patch.object(
                self.plane,
                "_controller_test_command",
                return_value=(*self.child(parent), str(completion)),
            ),
            patch.object(controller, "CONTROLLER_TEST_TERMINATION_SECONDS", 0.1),
        ):
            check = self.plane._controller_tests_check()
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.5)
        # Strict discard readers never retain text. On Windows the Job close ends
        # this member. POSIX cannot safely kill a leaderless process group, so a
        # non-EOF is a typed failure rather than a false healthy result.
        if os.name == "nt":
            self.assertTrue(check["passed"])
            self.assertFalse(completion.exists())
        else:
            self.assertFalse(check["passed"])
            self.assertEqual(check["evidence"]["failure_kind"], "output_stream_incomplete")
            time.sleep(0.3)
            self.assertTrue(completion.exists(), "self-expiring residual must be observable")

    @unittest.skipIf(os.name == "nt", "POSIX setsid residual is not applicable on Windows")
    def test_posix_detached_descendant_is_typed_not_ready(self) -> None:
        completion = self.root / "detached-descendant-completed"
        parent = (
            "import pathlib, subprocess, sys; "
            "child = subprocess.Popen((sys.executable, '-c', "
            "'import os, pathlib, sys, time; os.setsid(); time.sleep(0.2); "
            "pathlib.Path(sys.argv[1]).write_text(\"completed\", encoding=\"ascii\")', sys.argv[1]))"
        )
        try:
            with (
                patch.object(
                    self.plane,
                    "_controller_test_command",
                    return_value=(*self.child(parent), str(completion)),
                ),
                patch.object(controller, "CONTROLLER_TEST_TERMINATION_SECONDS", 0.1),
            ):
                check = self.plane._controller_tests_check()
            self.assertFalse(check["passed"])
            self.assertEqual(check["evidence"]["failure_kind"], "output_stream_incomplete")
            time.sleep(0.3)
            self.assertTrue(completion.exists(), "detached residual must be observable")
        finally:
            pass

    def test_nonzero_output_is_not_disclosed(self) -> None:
        sentinel = "TOP_SECRET_DO_NOT_DISCLOSE"
        check = self.controller_check(
            f"import sys; print('{sentinel}'); sys.exit(7)"
        )

        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["failure_kind"], "nonzero_exit")
        rendered = json.dumps(check, sort_keys=True)
        self.assertNotIn(sentinel, rendered)
        self.assertEqual(
            check["evidence"]["stdout"]["content_policy"],
            "strictly validated then discarded; no text, length, or digest retained",
        )

    def test_containment_termination_failure_stays_typed(self) -> None:
        timed_out = _TimeoutProcess()
        with (
            self.windows_job_patch(_FakeWindowsJob(close_result=False)),
            patch.object(controller.subprocess, "Popen", return_value=timed_out),
            patch.object(controller, "CONTROLLER_TEST_TIMEOUT_SECONDS", 0),
            patch.object(controller, "CONTROLLER_TEST_TERMINATION_SECONDS", 0.01),
            patch.object(
                self.plane,
                "_terminate_controller_test_process",
                side_effect=lambda process, _job: (process.kill(), False)[1],
            ),
        ):
            check = self.plane._controller_tests_check()

        self.assertEqual(check["evidence"]["failure_kind"], "timed_out")
        self.assertIn("containment_termination_failed", check["evidence"]["failure_kinds"])

    def test_windows_resume_compatibility_failure_is_fail_closed(self) -> None:
        suspended = _KilledProcess(io.BytesIO(), io.BytesIO(), returncode=0)
        with (
            self.windows_job_patch(_FakeWindowsJob(resume_result=False)),
            patch.object(controller.subprocess, "Popen", return_value=suspended),
        ):
            check = self.plane._controller_tests_check()

        if os.name == "nt":
            self.assertFalse(check["passed"])
            self.assertEqual(check["evidence"]["failure_kind"], "containment_setup_failed")
        else:
            self.assertTrue(check["passed"])

    def test_post_launch_reader_start_failure_finalizes_owned_containment(self) -> None:
        process = _TimeoutProcess()
        job = _FakeWindowsJob()
        with (
            self.windows_job_patch(job),
            patch.object(controller.subprocess, "Popen", return_value=process),
            patch.object(controller.Thread, "start", side_effect=RuntimeError("fixture")),
        ):
            check = self.plane._controller_tests_check()

        self.assertFalse(check["passed"])
        self.assertEqual(check["evidence"]["failure_kind"], "post_launch_handling_failed")
        if os.name == "nt":
            self.assertGreaterEqual(job.close_calls, 1)
        else:
            self.assertEqual(process.returncode, -9)

    def test_phase_deadline_is_passed_as_remaining_budget(self) -> None:
        timed_out = _TimeoutProcess()
        with (
            self.windows_job_patch(),
            patch.object(controller.subprocess, "Popen", return_value=timed_out),
            patch.object(controller, "CONTROLLER_TEST_TIMEOUT_SECONDS", 0),
            patch.object(controller, "CONTROLLER_TEST_TERMINATION_SECONDS", 0.01),
            patch.object(
                self.plane,
                "_terminate_controller_test_process",
                side_effect=lambda process, _job: (process.kill(), True)[1],
            ),
        ):
            check = self.plane._controller_tests_check()

        self.assertEqual(check["evidence"]["failure_kind"], "timed_out")
        self.assertLessEqual(timed_out.wait_timeouts[0] or 0, 0.01)

    def test_cli_timeout_emits_only_valid_json(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        command = self.child("import time; time.sleep(2)")
        with (
            patch.object(controller.ControlPlane, "_controller_test_command", return_value=command),
            patch.object(controller, "CONTROLLER_TEST_TIMEOUT_SECONDS", 0.01),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = autopilot.main(["--repo-root", str(self.root), "doctor", "--json"])

        self.assertEqual(code, 1)
        result = json.loads(stdout.getvalue())
        self.assertFalse(result["passed"])
        controller_check = next(item for item in result["checks"] if item["name"] == "controller-tests")
        self.assertEqual(controller_check["evidence"]["failure_kind"], "timed_out")
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_reader_runtime_error_emits_typed_json_without_traceback(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        completed = _KilledProcess(_RuntimeErrorStream(), io.BytesIO(), returncode=0)
        with (
            self.windows_job_patch(),
            patch.object(controller.subprocess, "Popen", return_value=completed),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = autopilot.main(["--repo-root", str(self.root), "doctor", "--json"])

        self.assertEqual(code, 1)
        result = json.loads(stdout.getvalue())
        controller_check = next(item for item in result["checks"] if item["name"] == "controller-tests")
        self.assertFalse(controller_check["passed"])
        self.assertEqual(controller_check["evidence"]["failure_kind"], "output_stream_error")
        self.assertEqual(
            controller_check["evidence"]["stdout"]["stream_error"],
            "output stream read failed",
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_cli_unexpected_doctor_error_is_valid_json(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            patch.object(autopilot.ControlPlane, "doctor", side_effect=RuntimeError("fixture")),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = autopilot.main(
                ["--repo-root", str(self.root), "doctor", "--skip-controller-tests", "--json"]
            )

        self.assertEqual(code, 1)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["checks"][0]["name"], "doctor-execution")
        self.assertEqual(stderr.getvalue(), "")

    def test_skip_result_is_explicitly_reduced(self) -> None:
        result = self.plane.doctor(run_controller_tests=False)

        self.assertTrue(result["passed"])
        self.assertEqual(result["validation_scope"], "reduced")
        self.assertFalse(result["controller_tests_run"])
        self.assertEqual(result["state"], "READY_REDUCED")


class DoctorRuntimeBindingTests(unittest.TestCase):
    @staticmethod
    def repository_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def test_isolated_probe_uses_exact_checkout_despite_inherited_pythonpath(self) -> None:
        repository = self.repository_root()
        plane = controller.ControlPlane(repository)
        foreign = str(Path(tempfile.gettempdir()) / "foreign-editable" / "src")
        with patch.dict(os.environ, {"PYTHONPATH": foreign}, clear=False):
            check = plane._runtime_binding_check()

        self.assertTrue(check["passed"], check)
        evidence = check["evidence"]
        self.assertEqual(evidence["command"][0], sys.executable)
        self.assertEqual(evidence["command"][1], "-I")
        self.assertEqual(
            Path(str(evidence["origin"])).resolve(),
            repository / "src" / "hive_mind_os" / "__init__.py",
        )
        self.assertEqual(plane._isolated_python_environment()["PYTHONPATH"], "")

    def test_ambient_binding_match_and_mismatch_are_deterministic(self) -> None:
        repository = self.repository_root()
        plane = controller.ControlPlane(repository)
        expected = repository / "src" / "hive_mind_os" / "__init__.py"
        foreign = repository.parent / "foreign" / "src" / "hive_mind_os" / "__init__.py"
        with patch.object(
            controller.importlib.util,
            "find_spec",
            return_value=SimpleNamespace(origin=str(foreign)),
        ):
            mismatch = plane._ambient_runtime_binding_check()
        self.assertFalse(mismatch["passed"])
        self.assertEqual(mismatch["evidence"]["severity"], "error")

        with patch.object(
            controller.importlib.util,
            "find_spec",
            return_value=SimpleNamespace(origin=str(expected)),
        ):
            match = plane._ambient_runtime_binding_check()
        self.assertTrue(match["passed"])
        self.assertEqual(match["evidence"]["severity"], "info")

    def test_ambient_binding_integration_reports_consistent_severity(self) -> None:
        plane = controller.ControlPlane(self.repository_root())
        observed = plane._ambient_runtime_binding_check()
        evidence = observed["evidence"]
        self.assertEqual(observed["passed"], evidence["severity"] == "info")
        if evidence["origin"] is None:
            self.assertFalse(observed["passed"])
        else:
            self.assertIsInstance(evidence["origin"], str)

    def test_foreign_runtime_origin_cannot_satisfy_probe(self) -> None:
        plane = controller.ControlPlane(self.repository_root())
        probe = (
            "import json, sys; print(json.dumps({'interpreter': sys.executable, "
            "'origin': r'C:\\\\foreign\\\\hive_mind_os\\\\__init__.py'}))"
        )
        with patch.object(
            plane,
            "_runtime_binding_command",
            return_value=(sys.executable, "-I", "-c", probe),
        ):
            check = plane._runtime_binding_check()

        self.assertFalse(check["passed"])
        self.assertIn("exact checkout", check["details"][0])

    def test_controller_test_command_has_exact_interpreter_and_isolation(self) -> None:
        repository = self.repository_root()
        command = controller.ControlPlane(repository)._controller_test_command()

        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], "-I")
        self.assertEqual(command[4], str((repository / "src").resolve()))
        self.assertEqual(command[-3], "-s")
        self.assertEqual(command[-2], str((repository / ".autopilot" / "tests").resolve()))


class DoctorTargetResolutionTests(unittest.TestCase):
    @staticmethod
    def repository_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def test_target_resolution_prefers_remote_ref_deterministically(self) -> None:
        repository = self.repository_root()
        plane = controller.ControlPlane(repository)
        remote_sha = "1" * 40
        local_sha = "2" * 40

        def fake_git(arguments: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            reference = arguments[-1]
            if reference == f"refs/remotes/origin/{plane.target_branch}":
                return subprocess.CompletedProcess(arguments, 0, remote_sha + "\n", "")
            self.fail(f"local fallback should not be read after remote success: {reference}")

        with patch.object(plane, "_git", side_effect=fake_git):
            self.assertEqual(plane.current_target_sha(), remote_sha)

        def local_only_git(arguments: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            reference = arguments[-1]
            if reference.startswith("refs/remotes/"):
                return subprocess.CompletedProcess(arguments, 128, "", "missing remote")
            self.assertEqual(reference, f"refs/heads/{plane.target_branch}")
            return subprocess.CompletedProcess(arguments, 0, local_sha + "\n", "")

        with patch.object(plane, "_git", side_effect=local_only_git):
            self.assertEqual(plane.current_target_sha(), local_sha)

    def test_target_resolution_integration_is_flexible_about_clone_ref_layout(self) -> None:
        plane = controller.ControlPlane(self.repository_root())
        try:
            target = plane.current_target_sha()
        except controller.AutopilotError as error:
            self.assertIn("cannot resolve target branch", str(error))
        else:
            self.assertRegex(target, r"^[0-9a-f]{40}$")

    def test_local_target_fallback_and_missing_target_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repository"
            copy_autopilot_fixture(
                self.repository_root() / ".autopilot", root / ".autopilot"
            )
            subprocess.run(("git", "init", "-q", "-b", "candidate"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.email", "doctor@example.invalid"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.name", "doctor"), cwd=root, check=True)
            subprocess.run(("git", "add", ".autopilot"), cwd=root, check=True)
            subprocess.run(("git", "commit", "-q", "-m", "fixture"), cwd=root, check=True)
            control_path = root / ".autopilot" / "control-plane.json"
            control = json.loads(control_path.read_text(encoding="utf-8"))
            control["verify_git_objects"] = True
            control["target"]["branch"] = "candidate"
            control_path.write_text(json.dumps(control), encoding="utf-8")
            plane = controller.ControlPlane(root)
            self.assertEqual(
                plane.current_target_sha(),
                subprocess.run(
                    ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True
                ).stdout.strip(),
            )

            control["target"]["branch"] = "deleted-after-merge"
            control_path.write_text(json.dumps(control), encoding="utf-8")
            missing = controller.ControlPlane(root)
            result = missing.doctor(run_controller_tests=False)
            repository_check = next(item for item in result["checks"] if item["name"] == "repository")
            self.assertFalse(repository_check["passed"])
            self.assertTrue(
                any("cannot resolve target branch" in detail for detail in repository_check["details"])
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = autopilot.main(
                    ["--repo-root", str(root), "doctor", "--skip-controller-tests", "--json"]
                )
            document = json.loads(stdout.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(document["validation_scope"], "reduced")
            public_repository = next(
                (item for item in document["checks"] if item["name"] == "repository"),
                document,
            )
            self.assertIsNot(public_repository, document)
            self.assertFalse(public_repository["passed"])


if __name__ == "__main__":
    unittest.main()
