import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "Collect-V4ActivationEvidence.ps1"
PROCESS_RUNNER = ROOT / "scripts" / "V4EvidenceProcess.ps1"
TERMINAL_RESULT_MARKER = "HIVE_V4_UNITTEST_RESULT_" + ("a" * 32)
V4_CANDIDATE_COMMIT = "1038b5a7d2eb49904c59957ad3e989af8bb2fcc5"
EXPECTED_FOCUSED_TEST_COUNTS = {
    "tests.test_adapter_registry": 7,
    "tests.test_ci_contract": 11,
    "tests.test_control_token_economy": 14,
    "tests.test_dag_executor": 23,
    "tests.test_dag_standard_product": 5,
    "tests.test_generic_dag_failure_matrix": 5,
    "tests.test_generic_dag_fixtures": 3,
    "tests.test_generic_dag_token_benchmark": 3,
    "tests.test_generic_dag_v4_activation": 14,
    "tests.test_generic_dag_v4_plan": 4,
    "tests.test_hive_cortex_role_applicability": 11,
    "tests.test_hive_cortex_token_economy": 11,
    "tests.test_host_runtime": 57,
    "tests.test_integration_transaction": 34,
    "tests.test_plan_generation": 5,
    "tests.test_plan_lineage": 7,
    "tests.test_planner_prompt": 2,
    "tests.test_portable_plan": 7,
    "tests.test_powershell_preparation": 4,
    "tests.test_public_dag_cli": 4,
    "tests.test_repository_index": 5,
    "tests.test_resource_adapter": 6,
    "tests.test_runtime_contracts": 8,
    "tests.test_sidecar_calibration": 5,
    "tests.test_subject_adapter": 6,
    "tests.test_subject_execution": 7,
    "tests.test_task_reuse": 7,
    "tests.test_v4_source_provenance": 7,
    "tests.test_wave_runtime": 11,
}


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
class CollectV4ActivationEvidenceTests(unittest.TestCase):
    @staticmethod
    def process_is_active(process_id: int) -> bool:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel32.GetExitCodeProcess.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        handle = kernel32.OpenProcess(0x1000, 0, process_id)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)

    def run_process_fixture(
        self,
        directory: Path,
        bootstrap: str,
        *,
        timeout_seconds: int,
        taskkill_executable: Path | None = None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any], Path, Path]:
        bootstrap_path = directory / "fixture bootstrap.py"
        stdout_path = directory / "stdout.txt"
        stderr_path = directory / "stderr.txt"
        harness_path = directory / "invoke-runner.ps1"
        bootstrap_path.write_text(bootstrap, encoding="utf-8")
        harness_path.write_text(
            """$ErrorActionPreference = 'Stop'
. $env:HIVE_V4_PROCESS_RUNNER
$result = Invoke-BoundedPythonValidation `
    -PythonExecutable $env:HIVE_V4_PYTHON `
    -BootstrapPath $env:HIVE_V4_BOOTSTRAP `
    -Modules @('tests.fixture') `
    -WorkingDirectory $env:HIVE_V4_ROOT `
    -TaskkillExecutable $env:HIVE_V4_TASKKILL `
    -TimeoutMilliseconds (([int]$env:HIVE_V4_TIMEOUT) * 1000)
$encoding = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($env:HIVE_V4_STDOUT, [string]$result.stdout, $encoding)
[System.IO.File]::WriteAllText($env:HIVE_V4_STDERR, [string]$result.stderr, $encoding)
[ordered]@{
    child_pid = $result.child_pid
    timed_out = $result.timed_out
    timeout_seconds = $result.timeout_seconds
    timeout_milliseconds = $result.timeout_milliseconds
    duration_milliseconds = $result.duration_milliseconds
    actual_exit_code = $result.actual_exit_code
    effective_exit_code = $result.effective_exit_code
    termination_exit_code = $result.termination_exit_code
    termination_output = @($result.termination_output)
} | ConvertTo-Json -Compress
""",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HIVE_V4_PROCESS_RUNNER": str(PROCESS_RUNNER),
                "HIVE_V4_PYTHON": sys.executable,
                "HIVE_V4_BOOTSTRAP": str(bootstrap_path),
                "HIVE_V4_ROOT": str(ROOT),
                "HIVE_V4_TASKKILL": str(
                    taskkill_executable
                    or Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
                ),
                "HIVE_V4_TIMEOUT": str(timeout_seconds),
                "HIVE_V4_STDOUT": str(stdout_path),
                "HIVE_V4_STDERR": str(stderr_path),
            }
        )
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(harness_path),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        metadata = json.loads(completed.stdout.strip().splitlines()[-1])
        return completed, metadata, stdout_path, stderr_path

    @staticmethod
    def parse_terminal_result_fixture(
        directory: Path,
        stdout: str,
        *,
        expected_tests_run: int,
        stderr: str = "",
    ) -> dict[str, object]:
        directory.mkdir()
        stdout_path = directory / "stdout.txt"
        stderr_path = directory / "stderr.txt"
        harness_path = directory / "parse-terminal-result.ps1"
        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        harness_path.write_text(
            """$ErrorActionPreference = 'Stop'
. $env:HIVE_V4_PROCESS_RUNNER
$stdout = [System.IO.File]::ReadAllText($env:HIVE_V4_STDOUT)
$stderr = [System.IO.File]::ReadAllText($env:HIVE_V4_STDERR)
Get-V4UnittestTerminalResult `
    -Stdout $stdout `
    -Stderr $stderr `
    -Marker $env:HIVE_V4_RESULT_MARKER `
    -ExpectedTestsRun ([int]$env:HIVE_V4_EXPECTED_TESTS) |
    ConvertTo-Json -Compress
""",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.update(
            {
                "HIVE_V4_PROCESS_RUNNER": str(PROCESS_RUNNER),
                "HIVE_V4_STDOUT": str(stdout_path),
                "HIVE_V4_STDERR": str(stderr_path),
                "HIVE_V4_RESULT_MARKER": TERMINAL_RESULT_MARKER,
                "HIVE_V4_EXPECTED_TESTS": str(expected_tests_run),
            }
        )
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(harness_path),
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr + completed.stdout)
        return json.loads(completed.stdout.strip().splitlines()[-1])

    @staticmethod
    def run_collector(
        output_directory: Path, *additional_arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-OutputDirectory",
                str(output_directory),
                "-AllowDirty",
                *additional_arguments,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_collector_writes_review_evidence_without_authorizing_activation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            candidate_root = temporary_root / "candidate"
            materialized = subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    str(candidate_root),
                    V4_CANDIDATE_COMMIT,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, materialized.returncode, materialized.stderr)
            candidate_script = candidate_root / "scripts" / SCRIPT.name
            shutil.copyfile(SCRIPT, candidate_script)
            output_directory = temporary_root / "evidence"
            environment = os.environ.copy()
            environment["GIT_PAGER"] = "cat"
            environment["PYTHONPATH"] = str(
                candidate_root / "missing-poisoned-source"
            )
            try:
                completed = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-File",
                        str(candidate_script),
                        "-OutputDirectory",
                        str(output_directory),
                        "-AllowDirty",
                    ],
                    cwd=candidate_root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if completed.returncode != 0:
                    focused_output_path = output_directory / "focused-test-output.txt"
                    focused_output = (
                        focused_output_path.read_text(encoding="utf-8", errors="replace")
                        if focused_output_path.is_file()
                        else "<focused transcript was not materialized>"
                    )
                    self.fail(
                        completed.stderr
                        + completed.stdout
                        + "\n=== RETAINED FOCUSED TRANSCRIPT ===\n"
                        + focused_output
                    )
                evidence = json.loads(
                    (output_directory / "evidence.json").read_text(encoding="utf-8")
                )

                self.assertEqual(2, evidence["schema_version"])
                self.assertFalse(evidence["qualification_eligible"])
                self.assertFalse(evidence["activation_authorized"])
                self.assertEqual("CANDIDATE_NOT_AUTHORIZED", evidence["activation_status"])
                self.assertTrue(evidence["artifacts"]["manifest_plan_matches"])
                self.assertTrue(evidence["artifacts"]["manifest_inert"])
                self.assertEqual(13, evidence["artifacts"]["source_count"])
                self.assertEqual(
                    0, evidence["artifacts"]["unavailable_source_count"]
                )
                self.assertEqual(
                    "sha256:27822617648a04965c17a9f3c4161d71d76521518aa58b5c128f916cb2e89132",
                    evidence["artifacts"]["source_intake_sha256"],
                )
                self.assertEqual(
                    "sha256:908d82cc7bccea22e37eda43eea28d9d363528b20c6b913014b0fb080c07893c",
                    evidence["artifacts"]["source_archive_sha256"],
                )
                self.assertTrue(
                    evidence["artifacts"]["predecessor_receipt_matches_manifest"]
                )
            finally:
                self.addCleanup(
                    subprocess.run,
                    ["git", "worktree", "prune"],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=True,
                )
            self.assertRegex(evidence["repository"]["head_commit"], r"^[0-9a-f]{40}$")
            self.assertRegex(evidence["repository"]["head_tree"], r"^[0-9a-f]{40}$")
            self.assertTrue(evidence["repository"]["candidate_base_matches_manifest"])
            self.assertTrue(evidence["repository"]["sole_parent_verified"])
            self.assertEqual(0, evidence["validation"]["exit_code"])
            self.assertEqual(0, evidence["validation"]["actual_exit_code"])
            self.assertFalse(evidence["validation"]["timed_out"])
            self.assertEqual(180, evidence["validation"]["timeout_seconds"])
            self.assertEqual(180000, evidence["validation"]["timeout_milliseconds"])
            self.assertEqual(
                60, evidence["validation"]["maximum_module_timeout_seconds"]
            )
            self.assertEqual(
                60000,
                evidence["validation"]["maximum_module_timeout_milliseconds"],
            )
            self.assertGreater(evidence["validation"]["duration_milliseconds"], 0)
            self.assertRegex(
                evidence["validation"]["bootstrap_sha256"], r"^sha256:[0-9a-f]{64}$"
            )
            self.assertTrue(
                Path(evidence["validation"]["expected_package_path"]).samefile(
                    candidate_root / "src" / "hive_mind_os" / "__init__.py"
                )
            )
            expected_module_count = len(EXPECTED_FOCUSED_TEST_COUNTS)
            expected_test_count = sum(EXPECTED_FOCUSED_TEST_COUNTS.values())
            self.assertEqual(expected_module_count, evidence["validation"]["module_count"])
            self.assertEqual(
                expected_module_count,
                evidence["validation"]["attempted_module_count"],
            )
            self.assertEqual(
                expected_module_count,
                evidence["validation"]["completed_module_count"],
            )
            self.assertTrue(evidence["validation"]["all_modules_completed"])
            self.assertTrue(evidence["validation"]["module_process_isolation"])
            self.assertIsNone(evidence["validation"]["timeout_scope"])
            self.assertIsNone(evidence["validation"]["timed_out_module"])
            self.assertIsNone(
                evidence["validation"]["deadline_exhausted_before_module"]
            )
            self.assertEqual(expected_test_count, evidence["validation"]["tests_run"])
            self.assertEqual(
                expected_test_count, evidence["validation"]["expected_tests_run"]
            )
            self.assertTrue(evidence["validation"]["test_count_matches_expected"])
            self.assertEqual(0, evidence["validation"]["failures"])
            self.assertEqual(0, evidence["validation"]["errors"])
            self.assertEqual(0, evidence["validation"]["skipped"])
            self.assertEqual(0, evidence["validation"]["expected_failures"])
            self.assertEqual(0, evidence["validation"]["unexpected_successes"])
            self.assertEqual(
                0,
                evidence["validation"][
                    "resource_warning_stderr_occurrence_count"
                ],
            )
            self.assertEqual(
                0,
                evidence["validation"][
                    "unraisable_exception_stderr_occurrence_count"
                ],
            )
            self.assertTrue(evidence["validation"]["terminal_outcomes_clean"])
            self.assertRegex(
                evidence["validation"]["terminal_result_marker"],
                r"^HIVE_V4_UNITTEST_RESULT_[0-9a-f]{32}$",
            )
            self.assertIn(
                "tests.test_ci_contract", evidence["validation"]["modules"]
            )
            module_results = evidence["validation"]["module_results"]
            self.assertEqual(expected_module_count, len(module_results))
            self.assertEqual(
                evidence["validation"]["modules"],
                [result["module"] for result in module_results],
            )
            self.assertEqual(
                evidence["validation"]["child_pids"],
                [result["child_pid"] for result in module_results],
            )
            for result in module_results:
                with self.subTest(module=result["module"]):
                    self.assertGreater(result["tests_run"], 0)
                    self.assertEqual(
                        EXPECTED_FOCUSED_TEST_COUNTS[result["module"]],
                        result["expected_tests_run"],
                    )
                    self.assertEqual(
                        result["expected_tests_run"], result["tests_run"]
                    )
                    self.assertTrue(result["test_count_matches_expected"])
                    self.assertEqual(0, result["failures"])
                    self.assertEqual(0, result["errors"])
                    self.assertEqual(0, result["skipped"])
                    self.assertEqual(0, result["expected_failures"])
                    self.assertEqual(0, result["unexpected_successes"])
                    self.assertEqual(
                        0, result["resource_warning_stderr_occurrence_count"]
                    )
                    self.assertEqual(
                        0, result["unraisable_exception_stderr_occurrence_count"]
                    )
                    self.assertEqual(1, result["terminal_result_marker_count"])
                    self.assertTrue(result["terminal_result_success"])
                    self.assertTrue(result["terminal_result_outcomes_clean"])
                    self.assertTrue(result["terminal_result_valid"])
                    self.assertIsInstance(result["child_pid"], int)
                    self.assertGreater(result["timeout_milliseconds"], 0)
                    self.assertEqual(0, result["actual_exit_code"])
                    self.assertEqual(0, result["effective_exit_code"])
                    self.assertFalse(result["timed_out"])
                    self.assertRegex(result["stdout_sha256"], r"^sha256:[0-9a-f]{64}$")
                    self.assertRegex(result["stderr_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertTrue(Path(evidence["toolchain"]["git_path"]).is_file())
            self.assertTrue(Path(evidence["toolchain"]["python_path"]).is_file())
            self.assertTrue(evidence["toolchain"]["python_executable_stable"])
            self.assertEqual(
                evidence["toolchain"]["python_sha256_before"],
                evidence["toolchain"]["python_sha256_after"],
            )
            child_pythonpath = evidence["toolchain"]["child_pythonpath"].split(
                os.pathsep
            )
            self.assertEqual(2, len(child_pythonpath))
            self.assertTrue(os.path.samefile(candidate_root / "src", child_pythonpath[0]))
            self.assertTrue(os.path.samefile(candidate_root, child_pythonpath[1]))
            self.assertTrue(evidence["toolchain"]["child_pythonpath_consistent"])
            self.assertTrue(
                all(
                    result["child_pythonpath"]
                    == evidence["toolchain"]["child_pythonpath"]
                    for result in module_results
                )
            )
            self.assertEqual(
                "REQUIRED_NOT_SATISFIED",
                evidence["external_gates"]["independent_review"],
            )
            self.assertEqual(
                "NOT_AUTHORIZED", evidence["external_gates"]["protected_merge"]
            )
            self.assertTrue((output_directory / "SHA256SUMS.txt").is_file())
            self.assertTrue((output_directory / "focused-test-bootstrap.py").is_file())
            self.assertTrue((output_directory / "focused-test-stdout.txt").is_file())
            self.assertTrue((output_directory / "focused-test-stderr.txt").is_file())
            focused_output = (output_directory / "focused-test-output.txt").read_text(
                encoding="utf-8"
            )
            self.assertEqual(
                expected_module_count, focused_output.count("=== MODULE tests.")
            )
            self.assertEqual(
                expected_module_count,
                focused_output.count(evidence["validation"]["terminal_result_marker"]),
            )
            self.assertIn(
                f"BOUND_PACKAGE={Path(child_pythonpath[0]) / 'hive_mind_os' / '__init__.py'}",
                focused_output,
            )
            template = json.loads(
                (output_directory / "unsigned-activation-template.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse(template["executable"])
            review_request = (
                output_directory / "independent-review-request.md"
            ).read_text(encoding="utf-8")
            expected_review_fields = {
                "Candidate commit": evidence["repository"]["head_commit"],
                "Candidate tree": evidence["repository"]["head_tree"],
                "Candidate parent": evidence["repository"]["parent_commit"],
                "Candidate parent tree": evidence["repository"]["parent_tree"],
                "Manifest SHA-256": evidence["artifacts"]["manifest_sha256"],
                "Plan SHA-256": evidence["artifacts"]["plan_sha256"],
                "V3 qualification receipt SHA-256": evidence["artifacts"][
                    "predecessor_receipt_sha256"
                ],
                "Focused-test transcript SHA-256": evidence["validation"][
                    "output_sha256"
                ],
                "Locally qualification-eligible": str(
                    evidence["qualification_eligible"]
                ),
            }
            for label, value in expected_review_fields.items():
                with self.subTest(label=label):
                    self.assertIn(f"- {label}: {value}", review_request)
            for unresolved_name in (
                "head",
                "tree",
                "parent",
                "parentTree",
                "manifestSha256",
                "planSha256",
                "predecessorReceiptSha256",
                "qualificationEligible",
            ):
                with self.subTest(unresolved_name=unresolved_name):
                    self.assertNotIn(f"${unresolved_name}", review_request)

    def test_collector_records_bounded_focused_validation_timeout(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "evidence"
            completed = self.run_collector(
                output_directory,
                "-FocusedTestTimeoutSeconds",
                "1",
            )

            self.assertNotEqual(0, completed.returncode)
            combined_output = completed.stderr + completed.stdout
            self.assertIn("Focused V4 validation", combined_output)
            self.assertIn("1-second overall deadline", combined_output)
            evidence = json.loads(
                (output_directory / "evidence.json").read_text(encoding="utf-8")
            )
            self.assertFalse(evidence["qualification_eligible"])
            self.assertFalse(evidence["activation_authorized"])
            self.assertTrue(evidence["validation"]["timed_out"])
            self.assertEqual(1, evidence["validation"]["timeout_seconds"])
            self.assertEqual(124, evidence["validation"]["exit_code"])
            self.assertTrue(
                evidence["validation"]["actual_exit_code"] is None
                or isinstance(evidence["validation"]["actual_exit_code"], int)
            )
            attempted_module_count = evidence["validation"][
                "attempted_module_count"
            ]
            completed_module_count = evidence["validation"]["completed_module_count"]
            module_results = evidence["validation"]["module_results"]
            self.assertGreaterEqual(attempted_module_count, 0)
            self.assertLessEqual(completed_module_count, attempted_module_count)
            self.assertLess(completed_module_count, len(EXPECTED_FOCUSED_TEST_COUNTS))
            self.assertEqual(attempted_module_count, len(module_results))
            self.assertFalse(evidence["validation"]["all_modules_completed"])
            self.assertEqual(
                evidence["validation"]["modules"][:attempted_module_count],
                [result["module"] for result in module_results],
            )
            timeout_scope = evidence["validation"]["timeout_scope"]
            self.assertIn(
                timeout_scope, {"module_process", "overall_deadline_before_module"}
            )
            if timeout_scope == "module_process":
                module_result = module_results[-1]
                self.assertTrue(module_result["timed_out"])
                self.assertEqual(124, module_result["effective_exit_code"])
                self.assertEqual(
                    module_result["module"],
                    evidence["validation"]["timed_out_module"],
                )
                self.assertIsNone(
                    evidence["validation"]["deadline_exhausted_before_module"]
                )
            else:
                self.assertTrue(all(not result["timed_out"] for result in module_results))
                self.assertIsNone(evidence["validation"]["timed_out_module"])
                self.assertEqual(
                    evidence["validation"]["modules"][attempted_module_count],
                    evidence["validation"]["deadline_exhausted_before_module"],
                )
            focused_output = output_directory / "focused-test-output.txt"
            self.assertTrue(focused_output.is_file())
            if timeout_scope == "overall_deadline_before_module":
                self.assertIn(
                    "OVERALL_VALIDATION_DEADLINE_EXHAUSTED",
                    focused_output.read_text(encoding="utf-8"),
                )

    def test_collector_attributes_a_module_process_timeout_with_partial_streams(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory) / "evidence"
            completed = self.run_collector(
                output_directory,
                "-MaximumFocusedModuleTimeoutMilliseconds",
                "1",
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("exceeded a module deadline", completed.stderr + completed.stdout)
            evidence = json.loads(
                (output_directory / "evidence.json").read_text(encoding="utf-8")
            )
            validation = evidence["validation"]
            self.assertFalse(evidence["qualification_eligible"])
            self.assertTrue(validation["timed_out"])
            self.assertEqual("module_process", validation["timeout_scope"])
            self.assertEqual(
                "tests.test_adapter_registry", validation["timed_out_module"]
            )
            self.assertIsNone(validation["deadline_exhausted_before_module"])
            self.assertEqual(1, validation["attempted_module_count"])
            self.assertEqual(0, validation["completed_module_count"])
            module_result = validation["module_results"][0]
            self.assertTrue(module_result["timed_out"])
            self.assertEqual(1, module_result["timeout_milliseconds"])
            self.assertEqual(124, module_result["effective_exit_code"])
            # A one-millisecond deadline races child-process startup.  Depending
            # on the scheduler, the child may emit its immutable binding banner
            # before the bounded runner terminates it.  The timeout receipt must
            # retain a valid digest either way; requiring an empty stream would
            # turn normal scheduling variance into a false qualification result.
            self.assertRegex(module_result["stdout_sha256"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(module_result["stderr_sha256"], r"^sha256:[0-9a-f]{64}$")
            focused_output = (output_directory / "focused-test-output.txt").read_text(
                encoding="utf-8"
            )
            self.assertIn("=== MODULE tests.test_adapter_registry ===", focused_output)

    def test_terminal_result_rejects_skips_and_every_adverse_outcome(self):
        def terminal_line(**overrides: int | bool) -> str:
            values: dict[str, int | bool] = {
                "tests_run": 1,
                "failures": 0,
                "errors": 0,
                "skipped": 0,
                "expected_failures": 0,
                "unexpected_successes": 0,
                "successful": True,
            }
            values.update(overrides)
            return (
                f"{TERMINAL_RESULT_MARKER} tests_run={values['tests_run']} "
                f"failures={values['failures']} errors={values['errors']} "
                f"skipped={values['skipped']} "
                f"expected_failures={values['expected_failures']} "
                f"unexpected_successes={values['unexpected_successes']} "
                f"successful={str(values['successful']).lower()}\n"
            )

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = self.parse_terminal_result_fixture(
                root / "valid", terminal_line(), expected_tests_run=1
            )
            self.assertTrue(valid["valid"])

            cases = {
                "skipped": {"skipped": 1},
                "expected_failure": {"expected_failures": 1},
                "unexpected_success": {
                    "unexpected_successes": 1,
                    "successful": False,
                },
                "failure": {"failures": 1, "successful": False},
                "error": {"errors": 1, "successful": False},
                "wrong_count": {"tests_run": 2},
            }
            for name, overrides in cases.items():
                with self.subTest(name=name):
                    parsed = self.parse_terminal_result_fixture(
                        root / name,
                        terminal_line(**overrides),
                        expected_tests_run=1,
                    )
                    self.assertFalse(parsed["valid"])
            duplicate = self.parse_terminal_result_fixture(
                root / "duplicate",
                terminal_line() + terminal_line(),
                expected_tests_run=1,
            )
            self.assertEqual(2, duplicate["marker_count"])
            self.assertFalse(duplicate["valid"])

    def test_real_skipped_unittest_result_is_not_a_valid_terminal_receipt(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            completed, metadata, stdout_path, _ = self.run_process_fixture(
                root,
                f"""import io
import unittest

class Probe(unittest.TestCase):
    @unittest.skip("capability unavailable")
    def test_security_boundary(self):
        raise AssertionError("must not execute")

result = unittest.TextTestRunner(stream=io.StringIO()).run(
    unittest.defaultTestLoader.loadTestsFromTestCase(Probe)
)
print(
    f"{TERMINAL_RESULT_MARKER} tests_run={{result.testsRun}} "
    f"failures={{len(result.failures)}} errors={{len(result.errors)}} "
    f"skipped={{len(result.skipped)}} "
    f"expected_failures={{len(result.expectedFailures)}} "
    f"unexpected_successes={{len(result.unexpectedSuccesses)}} "
    f"successful={{str(result.wasSuccessful()).lower()}}",
    flush=True,
)
""",
                timeout_seconds=30,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(0, metadata["effective_exit_code"])
            parsed = self.parse_terminal_result_fixture(
                root / "parsed",
                stdout_path.read_text(encoding="utf-8"),
                expected_tests_run=1,
            )
            self.assertEqual(1, parsed["tests_run"])
            self.assertTrue(parsed["successful"])
            self.assertEqual(1, parsed["skipped"])
            self.assertFalse(parsed["outcomes_clean"])
            self.assertFalse(parsed["valid"])

    def test_real_unraisable_resource_warning_invalidates_success_receipt(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            completed, metadata, stdout_path, stderr_path = self.run_process_fixture(
                root,
                f'''import gc
import unittest
import warnings

class Probe(unittest.TestCase):
    def test_leak(self):
        class Leaky:
            def __del__(self):
                warnings.warn("synthetic leak", ResourceWarning)

        leak = Leaky()
        del leak
        gc.collect()

result = unittest.TextTestRunner().run(
    unittest.defaultTestLoader.loadTestsFromTestCase(Probe)
)
print(
    f"{TERMINAL_RESULT_MARKER} tests_run={{result.testsRun}} "
    f"failures={{len(result.failures)}} errors={{len(result.errors)}} "
    f"skipped={{len(result.skipped)}} "
    f"expected_failures={{len(result.expectedFailures)}} "
    f"unexpected_successes={{len(result.unexpectedSuccesses)}} "
    f"successful={{str(result.wasSuccessful()).lower()}}",
    flush=True,
)
''',
                timeout_seconds=30,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(0, metadata["effective_exit_code"])
            stderr = stderr_path.read_text(encoding="utf-8")
            self.assertIn("ResourceWarning:", stderr)
            self.assertIn("Exception ignored", stderr)
            parsed = self.parse_terminal_result_fixture(
                root / "parsed",
                stdout_path.read_text(encoding="utf-8"),
                stderr=stderr,
                expected_tests_run=1,
            )
            self.assertEqual(1, parsed["tests_run"])
            self.assertTrue(parsed["successful"])
            self.assertGreaterEqual(
                cast(int, parsed["resource_warning_stderr_occurrence_count"]), 1
            )
            self.assertGreaterEqual(
                cast(int, parsed["unraisable_exception_stderr_occurrence_count"]), 1
            )
            self.assertFalse(parsed["outcomes_clean"])
            self.assertFalse(parsed["valid"])

    def test_bounded_runner_drains_both_streams_and_preserves_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            completed, metadata, stdout_path, stderr_path = self.run_process_fixture(
                Path(temporary_directory),
                """import sys
sys.stdout.write("O" * 1048577)
sys.stdout.flush()
sys.stderr.write("E" * 1048583)
sys.stderr.flush()
raise SystemExit(7)
""",
                timeout_seconds=30,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(metadata["timed_out"])
            self.assertEqual(7, metadata["actual_exit_code"])
            self.assertEqual(7, metadata["effective_exit_code"])
            self.assertEqual(b"O" * 1048577, stdout_path.read_bytes())
            self.assertEqual(b"E" * 1048583, stderr_path.read_bytes())

    def test_bounded_runner_timeout_kills_descendants_but_not_unrelated_process(self):
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        sentinel = subprocess.Popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(120)"],
            creationflags=creation_flags,
        )
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                completed, metadata, stdout_path, _ = self.run_process_fixture(
                    Path(temporary_directory),
                    """import subprocess
import sys
import time
child = subprocess.Popen(
    [sys.executable, "-I", "-c", "import time; time.sleep(120)"],
    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
)
print(f"GRANDCHILD_PID={child.pid}", flush=True)
while True:
    time.sleep(1)
""",
                    timeout_seconds=1,
                )

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertTrue(metadata["timed_out"])
                self.assertEqual(124, metadata["effective_exit_code"])
                self.assertLess(int(metadata["duration_milliseconds"]), 15000)
                grandchild_line = stdout_path.read_text(encoding="utf-8").strip()
                self.assertRegex(grandchild_line, r"^GRANDCHILD_PID=\d+$")
                grandchild_pid = int(grandchild_line.partition("=")[2])
                self.assertFalse(self.process_is_active(int(metadata["child_pid"])))
                self.assertFalse(self.process_is_active(grandchild_pid))
                self.assertIsNone(sentinel.poll())
        finally:
            sentinel.terminate()
            sentinel.wait(timeout=10)

    def test_bounded_runner_tolerates_taskkill_stderr_after_owned_process_exits(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            taskkill_wrapper = directory / "taskkill-wrapper.cmd"
            taskkill_wrapper.write_text(
                "@echo off\n"
                '"%SystemRoot%\\System32\\taskkill.exe" %* >nul 2>&1\n'
                "echo SYNTHETIC_TASKKILL_STDERR 1>&2\n"
                "exit /b 128\n",
                encoding="utf-8",
            )
            completed, metadata, _, _ = self.run_process_fixture(
                directory,
                "import time\ntime.sleep(120)\n",
                timeout_seconds=1,
                taskkill_executable=taskkill_wrapper,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertTrue(metadata["timed_out"])
            self.assertEqual(124, metadata["effective_exit_code"])
            self.assertEqual(128, metadata["termination_exit_code"])
            self.assertIn(
                "SYNTHETIC_TASKKILL_STDERR",
                "\n".join(metadata["termination_output"]),
            )

    def test_output_directory_rejects_relative_inside_equal_and_reparse_paths(self):
        relative = self.run_collector(Path("relative-evidence"))
        self.assertNotEqual(0, relative.returncode)
        self.assertIn("fully qualified absolute", relative.stderr + relative.stdout)

        for candidate in (ROOT, ROOT / ".v4-evidence-inside-test"):
            with self.subTest(candidate=str(candidate)):
                inside = self.run_collector(candidate)
                self.assertNotEqual(0, inside.returncode)
                self.assertIn("outside the repository", inside.stderr + inside.stdout)

        target = Path(tempfile.mkdtemp(prefix=".v4-evidence-target-", dir=ROOT))
        try:
            with tempfile.TemporaryDirectory() as temporary:
                link = Path(temporary) / "junction"
                junction_environment = os.environ.copy()
                junction_environment["HIVE_V4_TEST_JUNCTION"] = str(link)
                junction_environment["HIVE_V4_TEST_TARGET"] = str(target)
                created = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "New-Item -ItemType Junction -Path $env:HIVE_V4_TEST_JUNCTION -Target $env:HIVE_V4_TEST_TARGET | Out-Null",
                    ],
                    env=junction_environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                if created.returncode != 0:
                    self.skipTest("junction creation is unavailable: " + created.stderr)
                try:
                    escaped = self.run_collector(link / "escaped-evidence")
                    self.assertNotEqual(0, escaped.returncode)
                    self.assertIn("reparse point", escaped.stderr + escaped.stdout)
                finally:
                    if link.exists():
                        os.rmdir(link)
        finally:
            shutil.rmtree(target)

    def test_collector_requires_exactly_one_parent_from_the_candidate_object(self):
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn(
            "@('rev-list', '--parents', '-n', '1', 'HEAD')",
            script,
        )
        self.assertIn("$parentTokens.Count -ne 2", script)
        self.assertIn("$parentTokens[0] -cne $head", script)
        self.assertIn("sole_parent_verified = $soleParentVerified", script)


if __name__ == "__main__":
    unittest.main()
