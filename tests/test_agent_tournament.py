from __future__ import annotations

import errno
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence
from unittest.mock import patch

from hive_mind_os.agent_tournament import (
    _COMMAND_TEMP_PARENT_ENV_NAME,
    _COMMAND_TEMP_PREFIX,
    _DOCTOR_REPAIR_KIND,
    _DOCTOR_TEMP_DIRECTORY_NAME,
    _DOCTOR_WORKSPACE_PREFIX,
    _SEALED_CONTROL_PLANE_TEMP_DESCENDANT_BUDGET,
    _WINDOWS_CLASSIC_PATH_CHARACTER_LIMIT,
    _WINDOWS_COMMAND_TEMP_DESCENDANT_RESERVE,
    CONTROL_PLANE_COMMANDS,
    SYSTEM_TEST_LANES,
    TOURNAMENT_ROLES,
    TournamentError,
    _bounded_subprocess,
    _child_environment,
    _CommandEvidenceFailure,
    _control_plane_identity,
    _decode_command_transcript,
    _doctor_semantic_evidence,
    _encode_command_transcript,
    _environment_policy,
    _environment_profile_for_command,
    _feedback_node_id,
    _host_runtime_evidence,
    _inventory_content_digest,
    _live_source_authority_roots,
    _manifest,
    _node_candidates,
    _node_executable,
    _observed_peak_concurrency,
    _owned_cleanup_identity,
    _remove_disposable_tree,
    _role_node_id,
    _run_isolated_control_plane_doctor,
    _source_authority_roots,
    _source_authority_state_roots,
    _state_manifest,
    _validate_command_cleanup_diagnostic,
    _validate_command_receipt,
    _validate_doctor_isolation,
    _validate_scan_receipt,
    _validate_sealed_control_plane_temp_path_budget,
    _validate_system_receipt,
    _validated_command_temp_parents,
    _write_json,
    build_tournament_plan,
    championship,
    control_plane_doctor_gate,
    control_plane_gate,
    control_plane_tests_gate,
    feedback_contract,
    grade_role,
    inventory_repository,
    run_command_receipt,
    run_tournament,
    static_repository_gate,
    validate_tournament_plan,
    verify_run_directory,
)
from hive_mind_os.brain_kernel.canonical import canonical_digest

ROOT = Path(__file__).resolve().parents[1]
FAKE_CHILD_ENV_NAMES = sorted(
    {
        "ALL_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        _COMMAND_TEMP_PARENT_ENV_NAME,
        "NO_PROXY",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
        "PYTHONNOUSERSITE",
        "PYTHONPATH",
        "PYTHONSAFEPATH",
        "PYTHONUTF8",
    }
)


def _doctor_result(
    repository: Path,
    *,
    passed: bool,
    reduced: bool = False,
    execution_repository: Path | None = None,
) -> dict[str, Any]:
    identity = _control_plane_identity(repository)
    execution_root = (execution_repository or repository).resolve()
    check_names = [
        "configuration",
        "repository",
        "receipts",
        "consultation-contracts",
        "runtime-coordination",
        "controller-tests",
    ]
    if not identity["verify_git_objects"]:
        check_names.remove("repository")
    checks: list[dict[str, Any]] = []
    for index, name in enumerate(check_names):
        check_passed = passed or index > 0
        check: dict[str, Any] = {
            "name": name,
            "passed": check_passed,
            "details": [] if check_passed else ["injected failure"],
        }
        if name == "controller-tests":
            if reduced:
                check["details"] = [
                    "SKIPPED: controller tests were not run; this is a reduced "
                    "diagnostic and cannot satisfy a full-doctor requirement"
                ]
                check["evidence"] = {
                    "failure_kind": "skipped",
                    "full_validation": False,
                }
            else:
                stream_evidence = {
                    "observed": True,
                    "utf8_valid": True,
                    "stream_error": None,
                    "content_policy": (
                        "strictly validated then discarded; no text, length, or "
                        "digest retained"
                    ),
                }
                check["evidence"] = {
                    "command_identity": "exact-checkout-isolated-unittest-discover",
                    "interpreter": sys.executable,
                    "cwd": str(execution_root),
                    "test_root": str((execution_root / ".autopilot/tests").resolve()),
                    "timeout_seconds": 600,
                    "isolated": True,
                    "containment": (
                        "windows-job-object" if os.name == "nt" else "posix-process-group"
                    ),
                    "output_policy": (
                        "stdout and stderr strictly UTF-8 validated then discarded"
                    ),
                    "failure_kind": None if check_passed else "nonzero_exit",
                    "failure_kinds": [] if check_passed else ["nonzero_exit"],
                    "returncode": 0 if check_passed else 1,
                    "duration_seconds": 0.001,
                    "stdout": deepcopy(stream_evidence),
                    "stderr": deepcopy(stream_evidence),
                }
        checks.append(check)
    return {
        "schema_version": 1,
        "passed": passed,
        "state": "READY_REDUCED" if reduced else "READY" if passed else "BOOTSTRAP_INVALID",
        "validation_scope": "reduced" if reduced else "full",
        "controller_tests_run": not reduced,
        "plan_fingerprint": identity["plan_fingerprint"],
        "checks": checks,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _fake_command_receipt(
    repository: Path,
    argv: Sequence[str],
    *,
    passed: bool,
    stdout: bytes | None = None,
    stderr: bytes | None = None,
):
    started_at = datetime.now(UTC)
    is_unittest = any(
        tuple(argv[index : index + 2]) == ("-m", "unittest")
        for index in range(len(argv) - 1)
    )
    if stdout is None:
        stdout = (
            (
                json.dumps(
                    _doctor_result(
                        ROOT,
                        passed=passed,
                        execution_repository=repository,
                    ),
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            if tuple(argv) == CONTROL_PLANE_COMMANDS["control-plane-doctor"]
            else b""
        )
    if stderr is None:
        stderr = (
            (
                b"Ran 3 tests in 0.001s\r\n\r\nOK\r\n"
                if passed
                else b"Ran 3 tests in 0.001s\r\n\r\nFAILED (failures=1)\r\n"
            )
            if is_unittest
            else b"" if passed or tuple(argv) == CONTROL_PLANE_COMMANDS["control-plane-doctor"]
            else b"control-plane failed\r\n"
        )
    if tuple(argv) == CONTROL_PLANE_COMMANDS["control-plane-doctor"]:
        try:
            doctor_output = json.loads(stdout.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            pass
        else:
            if isinstance(doctor_output, dict) and "generated_at" in doctor_output:
                doctor_output["generated_at"] = datetime.now(UTC).isoformat().replace(
                    "+00:00", "Z"
                )
                stdout = (json.dumps(doctor_output, sort_keys=True) + "\n").encode(
                    "utf-8"
                )
    time.sleep(0.01)
    ended_at = datetime.now(UTC)
    transcript = _encode_command_transcript(stdout, stderr)
    profile = _environment_profile_for_command(argv)
    temporary_directory = (
        repository.parent / _DOCTOR_TEMP_DIRECTORY_NAME
        if tuple(argv) == CONTROL_PLANE_COMMANDS["control-plane-doctor"]
        else _validated_command_temp_parents(
            _live_source_authority_roots(repository)
        )[0]
        / f"{_COMMAND_TEMP_PREFIX}00000000"
    )
    environment = _child_environment(
        repository,
        profile=profile,
        temporary_directory=temporary_directory,
    )
    receipt = {
        "argv": list(argv),
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "ended_at": ended_at.isoformat().replace("+00:00", "Z"),
        "duration_ms": round((ended_at - started_at).total_seconds() * 1000),
        "status": "passed" if passed else "failed",
        "returncode": 0 if passed else 1,
        "timed_out": False,
        "tests_run": 3 if is_unittest else None,
        "tests_skipped": 0,
        "import_provenance_bound": True,
        "resolved_package": str((repository / "src/hive_mind_os/__init__.py").resolve()),
        "expected_package_root": str((repository / "src/hive_mind_os").resolve()),
        "execution_cwd": str(repository.resolve()),
        "temporary_directory": str(temporary_directory.resolve()),
        "temporary_directory_cleanup_completed": True,
        "environment_policy": _environment_policy(profile, environment),
        "test_output_unambiguous": True,
        "stdout_sha256": "sha256:" + sha256(stdout).hexdigest(),
        "stderr_sha256": "sha256:" + sha256(stderr).hexdigest(),
        "transcript_sha256": "sha256:" + sha256(transcript.encode("utf-8")).hexdigest(),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt, transcript


def passing_runner(repository: Path, argv: Sequence[str]):
    return _fake_command_receipt(repository, argv, passed=True)


def failing_runner(repository: Path, argv: Sequence[str]):
    return _fake_command_receipt(repository, argv, passed=False)


def _state_manifest_fixture(
    *,
    exists: bool,
    files: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    document: dict[str, Any] = {"exists": exists, "files": list(files)}
    document["manifest_digest"] = canonical_digest(document)
    return document


def _fake_doctor_isolation_result(
    repository: Path,
    inventory: Mapping[str, Any],
    command: Mapping[str, Any],
    transcript: str,
):
    identity = _control_plane_identity(repository)
    semantics, doctor_result = _doctor_semantic_evidence(
        command,
        transcript,
        expected_plan_fingerprint=str(identity["plan_fingerprint"]),
        verify_git_objects=bool(identity["verify_git_objects"]),
    )
    absent = _state_manifest_fixture(exists=False)
    repair: dict[str, Any] | None = None
    after = absent
    if doctor_result["passed"] is True:
        repair = {
            "schema_version": 1,
            "kind": _DOCTOR_REPAIR_KIND,
            "target_sha": identity["source_target_sha"],
            "plan_fingerprint": identity["plan_fingerprint"],
            "github_snapshot_digest": None,
            "reconciliation_digest": None,
            "doctor_result_digest": semantics["result_digest"],
            "controller_tests_run": True,
            "recorded_at": command["ended_at"],
        }
        encoded = (
            json.dumps(repair, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).replace("\n", os.linesep).encode("utf-8")
        after = _state_manifest_fixture(
            exists=True,
            files=(
                {
                    "path": "sealed-repair-doctor.json",
                    "bytes": len(encoded),
                    "sha256": "sha256:" + sha256(encoded).hexdigest(),
                },
            ),
        )
    workspace = Path(str(command["execution_cwd"])).resolve().parent
    content_digest = _inventory_content_digest(inventory)
    protected = [
        {
            "kind": kind,
            "path": str(path.resolve()),
            "before": deepcopy(_state_manifest(path)),
            "after": deepcopy(_state_manifest(path)),
            "unchanged": True,
        }
        for kind, path in _source_authority_state_roots(repository, inventory)
    ]
    isolation = {
        "kind": "disposable-standalone-no-hardlink-clone-v1",
        "workspace_root": str(workspace),
        "execution_repository_root": str(workspace / "checkout"),
        "source_scan_digest": inventory.get("inventory_digest"),
        "source_head": inventory.get("head"),
        "source_inventory_content_digest": content_digest,
        "materialized_inventory_content_digest": content_digest,
        "source_target_ref": identity["source_target_ref"],
        "source_target_sha": identity["source_target_sha"],
        "target_branch": identity["target_branch"],
        "origin_policy": "disposable-local-mirror-no-hardlinks",
        "ignored_state_seed_policy": "empty",
        "git_common_directory_confined": True,
        "standalone_git_directory": True,
        "state_root_confined": True,
        "command_temporary_root": str(workspace / _DOCTOR_TEMP_DIRECTORY_NAME),
        "command_temporary_root_confined": True,
        "isolated_state_before": deepcopy(absent),
        "isolated_state_after": after,
        "sealed_repair_evidence": repair,
        "protected_source_states": protected,
        "cleanup_completed": True,
    }
    return dict(command), transcript, isolation, semantics


def passing_doctor_isolation_runner(
    repository: Path,
    inventory: Mapping[str, Any],
    command_runner,
):
    workspace = (
        Path(tempfile.gettempdir()).resolve()
        / f"{_DOCTOR_WORKSPACE_PREFIX}fixture"
    )
    command, transcript = command_runner(
        workspace / "checkout",
        CONTROL_PLANE_COMMANDS["control-plane-doctor"],
    )
    return _fake_doctor_isolation_result(repository, inventory, command, transcript)


class TournamentDagTests(unittest.TestCase):
    def test_plan_has_parallel_independent_roles_and_bounded_feedback(self) -> None:
        plan = build_tournament_plan()
        waves = validate_tournament_plan(plan)
        role_nodes = {_role_node_id(role) for role in TOURNAMENT_ROLES}
        feedback_nodes = {_feedback_node_id(role) for role in TOURNAMENT_ROLES}

        self.assertTrue(any(set(wave) == role_nodes for wave in waves))
        self.assertTrue(any(set(wave) == feedback_nodes for wave in waves))
        self.assertEqual(8, plan["max_parallelism"])
        self.assertEqual(3, plan["feedback_policy"]["max_cycles"])
        self.assertTrue(plan["scoring_policy"]["fatal_gates_are_non_compensating"])

    def test_plan_covers_code_qa_full_suite_and_every_role(self) -> None:
        plan = build_tournament_plan()
        by_id = {node["node_id"]: node for node in plan["nodes"]}
        waves = validate_tournament_plan(plan)
        expected_system_lanes = set(
            ("static", *SYSTEM_TEST_LANES, *CONTROL_PLANE_COMMANDS, "full-suite")
        )

        self.assertEqual(28, len(plan["nodes"]))
        self.assertEqual((1, 8, 7, 1, 1, 1, 8, 1), tuple(map(len, waves)))
        self.assertEqual(
            expected_system_lanes,
            {
                node["lane"]
                for node in plan["nodes"]
                if node["node_id"].startswith("SYSTEM-")
            },
        )
        self.assertIn("SYSTEM-CODE-QA", by_id)
        self.assertIn("SYSTEM-CONTROL-PLANE-TESTS", by_id)
        self.assertIn("SYSTEM-CONTROL-PLANE-DOCTOR", by_id)
        self.assertIn("SYSTEM-FULL-SUITE", by_id)
        control_tests = by_id["SYSTEM-CONTROL-PLANE-TESTS"]
        doctor = by_id["SYSTEM-CONTROL-PLANE-DOCTOR"]
        shared_scope = "resource://sealed-control-plane-tests"
        self.assertIn(shared_scope, control_tests["write_scope"])
        self.assertIn(shared_scope, doctor["write_scope"])
        self.assertIn("SYSTEM-CONTROL-PLANE-TESTS", doctor["dependencies"])
        self.assertFalse(doctor["parallel_safe"])
        self.assertIn("isolated://control-plane-doctor/**", doctor["write_scope"])
        self.assertIn("SYSTEM-CONTROL-PLANE-TESTS", waves[2])
        self.assertEqual(("SYSTEM-CONTROL-PLANE-DOCTOR",), waves[3])
        self.assertEqual(
            {_role_node_id(role) for role in TOURNAMENT_ROLES},
            set(by_id["SYSTEM-CODE-QA"]["dependencies"]),
        )
        self.assertEqual(
            {_feedback_node_id(role) for role in TOURNAMENT_ROLES},
            set(by_id["CHAMPIONSHIP"]["dependencies"]),
        )
        for role in TOURNAMENT_ROLES:
            role_node = by_id[_role_node_id(role)]
            self.assertEqual(("**",), role_node["read_scope"])
            self.assertIn(
                f"run://transcripts/{_role_node_id(role)}.txt",
                role_node["write_scope"],
            )
        self.assertIn("**", by_id["CROSS-EXAMINE"]["read_scope"])
        self.assertIn(
            "run://receipts/CHAMPIONSHIP.json",
            by_id["CHAMPIONSHIP"]["write_scope"],
        )

    def test_plan_digest_and_cycle_tampering_fail_closed(self) -> None:
        plan = build_tournament_plan()
        tampered = deepcopy(plan)
        tampered["objective"] = "silently changed"
        with self.assertRaisesRegex(TournamentError, "digest"):
            validate_tournament_plan(tampered)

        unknown = deepcopy(plan)
        unknown["operationally_complete"] = True
        material = dict(unknown)
        material.pop("plan_digest")
        unknown["plan_digest"] = canonical_digest(material)
        with self.assertRaisesRegex(TournamentError, "plan fields"):
            validate_tournament_plan(unknown)

        unknown_node = deepcopy(plan)
        unknown_node["nodes"][0]["operationally_complete"] = True
        material = dict(unknown_node)
        material.pop("plan_digest")
        unknown_node["plan_digest"] = canonical_digest(material)
        with self.assertRaisesRegex(TournamentError, "node fields"):
            validate_tournament_plan(unknown_node)

        cyclic = deepcopy(plan)
        cyclic["nodes"][0]["dependencies"] = ["CHAMPIONSHIP"]
        material = dict(cyclic)
        material.pop("plan_digest")
        cyclic["plan_digest"] = canonical_digest(material)
        with self.assertRaisesRegex(TournamentError, "topology|cycle"):
            validate_tournament_plan(cyclic)

    def test_plan_rejects_incomplete_executor_and_unordered_write_conflicts(self) -> None:
        incomplete = build_tournament_plan()
        incomplete["nodes"] = [
            node for node in incomplete["nodes"] if node["node_id"] != "CHAMPIONSHIP"
        ]
        material = dict(incomplete)
        material.pop("plan_digest")
        incomplete["plan_digest"] = canonical_digest(material)
        with self.assertRaisesRegex(TournamentError, "inventory"):
            validate_tournament_plan(incomplete)

        conflicting = build_tournament_plan()
        by_id = {node["node_id"]: node for node in conflicting["nodes"]}
        by_id["ROLE-EXPLORER"]["write_scope"] = list(
            by_id["ROLE-ORCHESTRATOR"]["write_scope"]
        )
        material = dict(conflicting)
        material.pop("plan_digest")
        conflicting["plan_digest"] = canonical_digest(material)
        with self.assertRaisesRegex(TournamentError, "overlapping write scopes"):
            validate_tournament_plan(conflicting)

        universal = build_tournament_plan()
        by_id = {node["node_id"]: node for node in universal["nodes"]}
        by_id["ROLE-ORCHESTRATOR"]["write_scope"] = ["**"]
        material = dict(universal)
        material.pop("plan_digest")
        universal["plan_digest"] = canonical_digest(material)
        with self.assertRaisesRegex(TournamentError, "overlapping write scopes"):
            validate_tournament_plan(universal)

    def test_plan_rejects_disabled_parallelism_or_weakened_feedback_and_retry(self) -> None:
        mutations = (
            ("max_parallelism", 1, "max_parallelism"),
            (
                "feedback_policy",
                {"max_cycles": 0},
                "feedback policy",
            ),
            (
                "retry_policy",
                {"retry_only_infrastructure_exceptions": False},
                "retry policy",
            ),
        )
        for field, value, message in mutations:
            with self.subTest(field=field):
                plan = build_tournament_plan()
                plan[field] = value
                material = dict(plan)
                material.pop("plan_digest")
                plan["plan_digest"] = canonical_digest(material)
                with self.assertRaisesRegex(TournamentError, message):
                    validate_tournament_plan(plan)

        serial = build_tournament_plan()
        next(
            node for node in serial["nodes"] if node["node_id"] == "ROLE-EXPLORER"
        )["parallel_safe"] = False
        material = dict(serial)
        material.pop("plan_digest")
        serial["plan_digest"] = canonical_digest(material)
        with self.assertRaisesRegex(TournamentError, "parallel decision"):
            validate_tournament_plan(serial)

    def test_checkout_launcher_is_executable_without_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan.json"
            environment = dict(os.environ)
            environment.pop("PYTHONPATH", None)
            completed = subprocess.run(
                (
                    sys.executable,
                    "-B",
                    "scripts/run_agent_tournament.py",
                    "plan",
                    "--output",
                    str(output),
                ),
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr.decode(errors="replace"))
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(build_tournament_plan()["plan_digest"], written["plan_digest"])
            validate_tournament_plan(written)

    def test_top_level_cli_routes_to_tournament(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "plan.json"
            environment = dict(os.environ)
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                (
                    sys.executable,
                    "-B",
                    "-m",
                    "hive_mind_os.cli",
                    "tournament",
                    "plan",
                    "--output",
                    str(output),
                ),
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr.decode(errors="replace"))
            validate_tournament_plan(json.loads(output.read_text(encoding="utf-8")))

    def test_repository_inventory_ignores_hostile_ambient_git_control_plane(self) -> None:
        expected = inventory_repository(ROOT)
        with tempfile.TemporaryDirectory() as temporary:
            fake = Path(temporary) / ("git.cmd" if os.name == "nt" else "git")
            fake.write_text("@exit /b 99\n" if os.name == "nt" else "#!/bin/sh\nexit 99\n")
            if os.name != "nt":
                fake.chmod(0o755)
            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(Path(temporary) / "wrong.git"),
                    "GIT_WORK_TREE": temporary,
                    "GIT_PAGER": "hostile-pager",
                    "PATH": temporary + os.pathsep + os.environ.get("PATH", ""),
                },
                clear=False,
            ):
                observed = inventory_repository(ROOT)
        self.assertEqual(expected["head"], observed["head"])
        self.assertEqual(expected["inventory_digest"], observed["inventory_digest"])

    def test_node_resolution_ignores_hostile_path_and_uses_fixed_native_candidate(self) -> None:
        self.assertTrue(_node_candidates())
        self.assertTrue(all(candidate.is_absolute() for candidate in _node_candidates()))
        native_prefix = (
            b"MZ\0\0"
            if os.name == "nt"
            else b"\xfe\xed\xfa\xcf"
            if sys.platform == "darwin"
            else b"\x7fELF"
        )
        executable_name = "node.exe" if os.name == "nt" else "node"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixed = root / "fixed" / executable_name
            hostile = root / "hostile"
            fixed.parent.mkdir()
            hostile.mkdir()
            fixed.write_bytes(native_prefix + b"fixed-runtime")
            (hostile / executable_name).write_bytes(native_prefix + b"hostile-runtime")

            with (
                patch(
                    "hive_mind_os.agent_tournament._node_candidates",
                    return_value=(fixed,),
                ),
                patch.dict(os.environ, {"PATH": str(hostile)}, clear=False),
            ):
                resolved = _node_executable()
                evidence = _host_runtime_evidence()
                child_path = _child_environment(ROOT)["PATH"].split(os.pathsep)

            self.assertEqual(fixed.resolve(), resolved)
            self.assertEqual(str(fixed.resolve()), evidence["node"]["path"])
            self.assertEqual(
                "sha256:" + sha256(fixed.read_bytes()).hexdigest(),
                evidence["node"]["sha256"],
            )
            normalized_child_path = {os.path.normcase(value) for value in child_path}
            self.assertIn(os.path.normcase(str(fixed.parent.resolve())), normalized_child_path)
            self.assertNotIn(os.path.normcase(str(hostile.resolve())), normalized_child_path)

    def test_node_resolution_rejects_non_native_candidate(self) -> None:
        executable_name = "node.exe" if os.name == "nt" else "node"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            non_native = root / executable_name
            non_native.write_bytes(b"not-a-native-executable")
            with patch(
                "hive_mind_os.agent_tournament._node_candidates",
                return_value=(non_native,),
            ):
                self.assertIsNone(_node_executable())

    def test_node_resolution_rejects_linked_candidate_when_supported(self) -> None:
        executable_name = "node.exe" if os.name == "nt" else "node"
        native_prefix = (
            b"MZ\0\0"
            if os.name == "nt"
            else b"\xfe\xed\xfa\xcf"
            if sys.platform == "darwin"
            else b"\x7fELF"
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            native = root / ("native-" + executable_name)
            linked = root / ("linked-" + executable_name)
            native.write_bytes(native_prefix + b"native-runtime")
            try:
                linked.symlink_to(native)
            except OSError as error:
                self.skipTest(f"file symlinks are unavailable: {error}")
            with patch(
                "hive_mind_os.agent_tournament._node_candidates",
                return_value=(linked,),
            ):
                self.assertIsNone(_node_executable())

    def test_repository_scan_rejects_rehashed_live_host_runtime_forgery(self) -> None:
        scan = inventory_repository(ROOT)
        scan.pop("inventory_digest")
        scan["execution"] = {
            "runner_identity": "fixture",
            "doctor_isolation_runner_identity": "fixture",
            "trusted_builtin_runner": False,
            "runtime_path": "src/hive_mind_os/agent_tournament.py",
            "runtime_sha256": "sha256:" + "a" * 64,
        }
        self.assertEqual(_host_runtime_evidence(), scan["host_runtimes"])
        forged = deepcopy(scan)
        node = forged["host_runtimes"]["node"]
        if node["available"]:
            node["sha256"] = "sha256:" + "0" * 64
        else:
            node.update(
                {
                    "available": True,
                    "path": str(Path(sys.executable).resolve()),
                    "sha256": "sha256:" + "0" * 64,
                }
            )
        forged["inventory_digest"] = canonical_digest(forged)

        with self.assertRaisesRegex(TournamentError, "live host"):
            _validate_scan_receipt(forged)

    def test_control_plane_test_and_doctor_gates_use_exact_commands(self) -> None:
        observed: list[tuple[str, ...]] = []

        def capturing_runner(repository: Path, argv: Sequence[str]):
            observed.append(tuple(argv))
            return passing_runner(repository, argv)

        observed.clear()
        receipt, _transcript = control_plane_tests_gate(ROOT, capturing_runner)
        self.assertEqual([CONTROL_PLANE_COMMANDS["control-plane-tests"]], observed)
        self.assertEqual("control-plane-tests", receipt["lane"])
        self.assertEqual("passed", receipt["status"])
        self.assertFalse(receipt["critical"])
        self.assertEqual(3, receipt["command_receipt"]["tests_run"])

        observed.clear()
        inventory = inventory_repository(ROOT)
        receipt, transcript = control_plane_doctor_gate(
            ROOT,
            capturing_runner,
            inventory=inventory,
            isolation_runner=passing_doctor_isolation_runner,
        )
        self.assertEqual([CONTROL_PLANE_COMMANDS["control-plane-doctor"]], observed)
        self.assertEqual("control-plane-doctor", receipt["lane"])
        self.assertEqual("passed", receipt["status"])
        self.assertFalse(receipt["critical"])
        self.assertIsNone(receipt["command_receipt"]["tests_run"])
        self.assertTrue(receipt["doctor_semantics"]["semantically_qualified"])
        self.assertTrue(receipt["doctor_isolation"]["cleanup_completed"])
        _validate_system_receipt(
            "SYSTEM-CONTROL-PLANE-DOCTOR",
            receipt,
            inventory,
            transcript,
        )

    def test_only_exact_control_plane_commands_receive_cwd_compatibility(self) -> None:
        exact_commands = (
            CONTROL_PLANE_COMMANDS["control-plane-tests"],
            CONTROL_PLANE_COMMANDS["control-plane-doctor"],
        )
        strict_commands = (
            CONTROL_PLANE_COMMANDS["control-plane"],
            (sys.executable, "-B", "-m", "unittest", "tests.test_models", "-v"),
            (*CONTROL_PLANE_COMMANDS["control-plane-tests"], "--hostile-extra"),
        )
        hostile_pythonpath = str(ROOT.parent / "hostile-pythonpath")
        with patch.dict(
            os.environ,
            {"PYTHONPATH": hostile_pythonpath, "PYTHONSAFEPATH": "0"},
            clear=False,
        ):
            for command in exact_commands:
                with self.subTest(command=command):
                    profile = _environment_profile_for_command(command)
                    environment = _child_environment(ROOT, profile=profile)
                    policy = _environment_policy(profile, environment)
                    self.assertEqual("sealed-control-plane-cwd-compat-v1", profile)
                    self.assertNotIn("PYTHONSAFEPATH", environment)
                    self.assertFalse(policy["python_safe_path_enabled"])
                    self.assertEqual(
                        "sealed-control-plane-repository-worktrees-only",
                        policy["cwd_import_authority"],
                    )
                    self.assertNotIn(hostile_pythonpath, environment["PYTHONPATH"])

            for command in strict_commands:
                with self.subTest(command=command):
                    profile = _environment_profile_for_command(command)
                    environment = _child_environment(ROOT, profile=profile)
                    policy = _environment_policy(profile, environment)
                    self.assertEqual("strict-safe-path-v1", profile)
                    self.assertEqual("1", environment["PYTHONSAFEPATH"])
                    self.assertTrue(policy["python_safe_path_enabled"])
                    self.assertEqual(
                        "disabled-by-safe-path",
                        policy["cwd_import_authority"],
                    )
                    self.assertNotIn(hostile_pythonpath, environment["PYTHONPATH"])

    def test_command_receipt_rejects_forged_environment_profile_and_execution_cwd(
        self,
    ) -> None:
        command = (
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "tests.test_models",
            "-v",
        )
        receipt, transcript = passing_runner(ROOT, command)
        _validate_command_receipt(
            receipt,
            command,
            transcript,
            ROOT,
            require_tests=True,
            label="strict command",
        )

        forged_profile = deepcopy(receipt)
        compatibility_environment = _child_environment(
            ROOT,
            profile="sealed-control-plane-cwd-compat-v1",
        )
        forged_profile["environment_policy"] = _environment_policy(
            "sealed-control-plane-cwd-compat-v1",
            compatibility_environment,
        )
        forged_profile.pop("receipt_digest")
        forged_profile["receipt_digest"] = canonical_digest(forged_profile)
        with self.assertRaisesRegex(TournamentError, "child-environment"):
            _validate_command_receipt(
                forged_profile,
                command,
                transcript,
                ROOT,
                require_tests=True,
                label="forged profile",
            )

        forged_cwd = deepcopy(receipt)
        forged_cwd["execution_cwd"] = str(ROOT.parent.resolve())
        forged_cwd.pop("receipt_digest")
        forged_cwd["receipt_digest"] = canonical_digest(forged_cwd)
        with self.assertRaisesRegex(TournamentError, "execution"):
            _validate_command_receipt(
                forged_cwd,
                command,
                transcript,
                ROOT,
                require_tests=True,
                label="forged cwd",
            )

        aliased_cwd = deepcopy(receipt)
        aliased_cwd["execution_cwd"] = str(
            ROOT.parent / ROOT.name / ".." / ROOT.name
        )
        aliased_cwd.pop("receipt_digest")
        aliased_cwd["receipt_digest"] = canonical_digest(aliased_cwd)
        with self.assertRaisesRegex(TournamentError, "execution"):
            _validate_command_receipt(
                aliased_cwd,
                command,
                transcript,
                ROOT,
                require_tests=True,
                label="aliased cwd",
            )

        forged_temporary_root = deepcopy(receipt)
        repository_temporary_root = ROOT / "hive-tournament-command-forged"
        forged_temporary_root["temporary_directory"] = str(
            repository_temporary_root.resolve()
        )
        forged_temporary_root["environment_policy"][
            "temporary_directory_bindings"
        ] = {
            name: str(repository_temporary_root.resolve())
            for name in ("TEMP", "TMP", "TMPDIR")
        }
        forged_temporary_root.pop("receipt_digest")
        forged_temporary_root["receipt_digest"] = canonical_digest(
            forged_temporary_root
        )
        with self.assertRaisesRegex(TournamentError, "temporary"):
            _validate_command_receipt(
                forged_temporary_root,
                command,
                transcript,
                ROOT,
                require_tests=True,
                label="forged temporary root",
            )

        forged_ambient_parent = deepcopy(receipt)
        outside_ambient = (
            Path(tempfile.gettempdir()).resolve().parent
            / f"{_COMMAND_TEMP_PREFIX}forged-{time.time_ns()}"
        )
        forged_ambient_parent["temporary_directory"] = str(outside_ambient)
        forged_ambient_parent["environment_policy"][
            "temporary_directory_bindings"
        ] = {name: str(outside_ambient) for name in ("TEMP", "TMP", "TMPDIR")}
        forged_ambient_parent.pop("receipt_digest")
        forged_ambient_parent["receipt_digest"] = canonical_digest(
            forged_ambient_parent
        )
        with self.assertRaisesRegex(TournamentError, "short roots"):
            _validate_command_receipt(
                forged_ambient_parent,
                command,
                transcript,
                ROOT,
                require_tests=True,
                label="forged ambient parent",
            )

        legacy_prefix = deepcopy(receipt)
        legacy_temporary_root = (
            Path(tempfile.gettempdir()).resolve()
            / "hive-tournament-command-legacy"
        )
        legacy_prefix["temporary_directory"] = str(legacy_temporary_root)
        legacy_prefix["environment_policy"]["temporary_directory_bindings"] = {
            name: str(legacy_temporary_root) for name in ("TEMP", "TMP", "TMPDIR")
        }
        legacy_prefix.pop("receipt_digest")
        legacy_prefix["receipt_digest"] = canonical_digest(legacy_prefix)
        with self.assertRaisesRegex(TournamentError, "identity"):
            _validate_command_receipt(
                legacy_prefix,
                command,
                transcript,
                ROOT,
                require_tests=True,
                label="legacy temporary prefix",
            )

        aliased_temporary_root = deepcopy(receipt)
        real_temporary_root = Path(receipt["temporary_directory"])
        temporary_alias = str(
            real_temporary_root.parent
            / "alias-parent"
            / ".."
            / real_temporary_root.name
        )
        aliased_temporary_root["temporary_directory"] = temporary_alias
        aliased_temporary_root["environment_policy"][
            "temporary_directory_bindings"
        ] = {name: temporary_alias for name in ("TEMP", "TMP", "TMPDIR")}
        aliased_temporary_root.pop("receipt_digest")
        aliased_temporary_root["receipt_digest"] = canonical_digest(
            aliased_temporary_root
        )
        with self.assertRaisesRegex(TournamentError, "temporary"):
            _validate_command_receipt(
                aliased_temporary_root,
                command,
                transcript,
                ROOT,
                require_tests=True,
                label="aliased temporary root",
            )

    def test_doctor_semantics_bind_success_to_controller_test_evidence(self) -> None:
        identity = _control_plane_identity(ROOT)
        workspace = (
            Path(tempfile.gettempdir()).resolve()
            / f"{_DOCTOR_WORKSPACE_PREFIX}semantic"
        )
        execution_root = workspace / "checkout"
        valid_result = _doctor_result(
            ROOT,
            passed=True,
            execution_repository=execution_root,
        )

        def semantic_evidence(result: Mapping[str, Any]):
            stdout = (json.dumps(result, sort_keys=True) + "\n").encode("utf-8")
            command, transcript = _fake_command_receipt(
                execution_root,
                CONTROL_PLANE_COMMANDS["control-plane-doctor"],
                passed=True,
                stdout=stdout,
            )
            return _doctor_semantic_evidence(
                command,
                transcript,
                expected_plan_fingerprint=str(identity["plan_fingerprint"]),
                verify_git_objects=bool(identity["verify_git_objects"]),
            )

        semantics, _result = semantic_evidence(valid_result)
        self.assertTrue(semantics["semantically_qualified"])

        mutations = {
            "returncode": ("returncode", 1),
            "returncode-bool": ("returncode", False),
            "timeout-float": ("timeout_seconds", 600.0),
            "failure-kinds": ("failure_kinds", ["nonzero_exit"]),
            "cwd": ("cwd", str(ROOT.resolve())),
            "test-root": ("test_root", str((ROOT / ".autopilot/tests").resolve())),
            "interpreter": ("interpreter", str(ROOT / "attacker-python")),
            "containment": ("containment", "none"),
            "stdout-utf8": ("stdout", {"observed": True, "utf8_valid": False}),
            "stderr-stream": (
                "stderr",
                {"observed": True, "utf8_valid": True, "stream_error": "forged"},
            ),
        }
        for label, (field, value) in mutations.items():
            with self.subTest(forgery=label):
                forged = deepcopy(valid_result)
                controller = next(
                    check
                    for check in forged["checks"]
                    if check["name"] == "controller-tests"
                )
                if field in {"stdout", "stderr"}:
                    controller["evidence"][field].update(value)
                else:
                    controller["evidence"][field] = value
                with self.assertRaisesRegex(TournamentError, "controller"):
                    semantic_evidence(forged)

    def test_doctor_gate_rejects_malformed_and_reduced_success_json(self) -> None:
        inventory = inventory_repository(ROOT)
        workspace = (
            Path(tempfile.gettempdir()).resolve()
            / f"{_DOCTOR_WORKSPACE_PREFIX}json"
        )
        execution_root = workspace / "checkout"

        def malformed_runner(repository, source_inventory, _command_runner):
            command, transcript = _fake_command_receipt(
                execution_root,
                CONTROL_PLANE_COMMANDS["control-plane-doctor"],
                passed=True,
                stdout=b'{"schema_version": 1',
            )
            return _fake_doctor_isolation_result(
                repository,
                source_inventory,
                command,
                transcript,
            )

        with self.assertRaisesRegex(TournamentError, "invalid or ambiguous JSON"):
            control_plane_doctor_gate(
                ROOT,
                passing_runner,
                inventory=inventory,
                isolation_runner=malformed_runner,
            )

        def reduced_runner(repository, source_inventory, _command_runner):
            result = _doctor_result(
                repository,
                passed=True,
                reduced=True,
                execution_repository=execution_root,
            )
            command, transcript = _fake_command_receipt(
                execution_root,
                CONTROL_PLANE_COMMANDS["control-plane-doctor"],
                passed=True,
                stdout=(json.dumps(result, sort_keys=True) + "\n").encode("utf-8"),
            )
            return _fake_doctor_isolation_result(
                repository,
                source_inventory,
                command,
                transcript,
            )

        receipt, transcript = control_plane_doctor_gate(
            ROOT,
            passing_runner,
            inventory=inventory,
            isolation_runner=reduced_runner,
        )
        self.assertEqual("failed", receipt["status"])
        self.assertFalse(receipt["doctor_semantics"]["semantically_qualified"])
        self.assertEqual("READY_REDUCED", receipt["doctor_semantics"]["state"])
        _validate_system_receipt(
            "SYSTEM-CONTROL-PLANE-DOCTOR",
            receipt,
            inventory,
            transcript,
        )

    def test_doctor_isolation_verifier_requires_absent_temporary_workspace_and_live_state(
        self,
    ) -> None:
        inventory = inventory_repository(ROOT)
        command, transcript = passing_runner(
            Path(tempfile.gettempdir()).resolve()
            / f"{_DOCTOR_WORKSPACE_PREFIX}fixture"
            / "checkout",
            CONTROL_PLANE_COMMANDS["control-plane-doctor"],
        )
        _command, _transcript, isolation, semantics = _fake_doctor_isolation_result(
            ROOT,
            inventory,
            command,
            transcript,
        )
        _validate_doctor_isolation(isolation, semantics, inventory, ROOT)

        outside_temp = deepcopy(isolation)
        forged_workspace = (
            ROOT.parent / f"hive-tournament-doctor-forged-{time.time_ns()}"
        ).resolve()
        outside_temp["workspace_root"] = str(forged_workspace)
        outside_temp["execution_repository_root"] = str(forged_workspace / "checkout")
        with self.assertRaises(TournamentError):
            _validate_doctor_isolation(outside_temp, semantics, inventory, ROOT)

        legacy_prefix = deepcopy(isolation)
        legacy_workspace = (
            Path(tempfile.gettempdir()).resolve()
            / f"hive-tournament-doctor-legacy-{time.time_ns()}"
        )
        legacy_prefix["workspace_root"] = str(legacy_workspace)
        legacy_prefix["execution_repository_root"] = str(legacy_workspace / "checkout")
        legacy_prefix["command_temporary_root"] = str(
            legacy_workspace / _DOCTOR_TEMP_DIRECTORY_NAME
        )
        with self.assertRaisesRegex(TournamentError, "execution root"):
            _validate_doctor_isolation(legacy_prefix, semantics, inventory, ROOT)

        with tempfile.TemporaryDirectory(
            prefix="hive-tournament-doctor-retained-"
        ) as retained_directory:
            retained = deepcopy(isolation)
            retained_workspace = Path(retained_directory).resolve()
            retained["workspace_root"] = str(retained_workspace)
            retained["execution_repository_root"] = str(
                retained_workspace / "checkout"
            )
            with self.assertRaises(TournamentError):
                _validate_doctor_isolation(retained, semantics, inventory, ROOT)

        fabricated = deepcopy(isolation)
        fabricated_manifest = _state_manifest_fixture(exists=False)
        for row in fabricated["protected_source_states"]:
            row["before"] = deepcopy(fabricated_manifest)
            row["after"] = deepcopy(fabricated_manifest)
        fresh_manifest = _state_manifest_fixture(
            exists=True,
            files=(
                {
                    "path": "live.json",
                    "bytes": 1,
                    "sha256": "sha256:" + "a" * 64,
                },
            ),
        )
        with (
            patch(
                "hive_mind_os.agent_tournament._state_manifest",
                return_value=fresh_manifest,
            ),
            self.assertRaises(TournamentError),
        ):
            _validate_doctor_isolation(fabricated, semantics, inventory, ROOT)

        generated_after_command = deepcopy(semantics)
        generated_after_command["generated_at"] = (
            datetime.now(UTC) + timedelta(hours=1)
        ).isoformat().replace("+00:00", "Z")
        generated_after_command["generated_at_consistent"] = False
        with self.assertRaisesRegex(TournamentError, "timing|repair"):
            _validate_doctor_isolation(
                isolation, generated_after_command, inventory, ROOT
            )

        repair_before_doctor = deepcopy(isolation)
        repair_before_doctor["sealed_repair_evidence"]["recorded_at"] = (
            datetime.fromisoformat(
                str(semantics["command_started_at"]).replace("Z", "+00:00")
            )
            - timedelta(seconds=1)
        ).isoformat().replace("+00:00", "Z")
        with self.assertRaisesRegex(TournamentError, "timing|repair"):
            _validate_doctor_isolation(
                repair_before_doctor, semantics, inventory, ROOT
            )

    def test_output_and_ambient_temp_cannot_overlap_git_or_authority_state(
        self,
    ) -> None:
        inventory = inventory_repository(ROOT)
        for kind, authority_root in _source_authority_roots(ROOT, inventory):
            output = authority_root / f"hive-tournament-output-forgery-{time.time_ns()}"
            with self.subTest(authority=kind):
                with self.assertRaisesRegex(TournamentError, "overlaps"):
                    run_tournament(
                        ROOT,
                        output,
                        full_suite=False,
                        command_runner=passing_runner,
                        doctor_isolation_runner=passing_doctor_isolation_runner,
                    )
                self.assertFalse(os.path.lexists(output))

        protected_state = _source_authority_state_roots(ROOT, inventory)[0][1]
        with (
            patch(
                "hive_mind_os.agent_tournament.tempfile.gettempdir",
                return_value=str(protected_state),
            ),
            patch("hive_mind_os.agent_tournament.tempfile.mkdtemp") as mkdtemp,
            self.assertRaisesRegex(TournamentError, "temporary root"),
        ):
            _run_isolated_control_plane_doctor(ROOT, inventory, passing_runner)
        mkdtemp.assert_not_called()

    def test_isolated_doctor_cleanup_and_source_mutation_fail_closed(self) -> None:
        inventory = inventory_repository(ROOT)
        identity = _control_plane_identity(ROOT)
        roots = _source_authority_state_roots(ROOT, inventory)
        absent = _state_manifest_fixture(exists=False)
        before = [
            {"kind": kind, "path": str(path.resolve()), "manifest": absent}
            for kind, path in roots
        ]
        mutated = deepcopy(before)
        mutated[0]["manifest"] = _state_manifest_fixture(
            exists=True,
            files=(
                {
                    "path": "mutated.json",
                    "bytes": 1,
                    "sha256": "sha256:" + "b" * 64,
                },
            ),
        )

        with tempfile.TemporaryDirectory(
            prefix=f"{_DOCTOR_WORKSPACE_PREFIX}c-"
        ) as temporary:
            workspace = Path(temporary).resolve()
            with (
                patch(
                    "hive_mind_os.agent_tournament._control_plane_identity",
                    return_value=identity,
                ),
                patch(
                    "hive_mind_os.agent_tournament.tempfile.mkdtemp",
                    return_value=str(workspace),
                ),
                patch(
                    "hive_mind_os.agent_tournament._checked_git",
                    side_effect=TournamentError("injected operation failure"),
                ),
                patch(
                    "hive_mind_os.agent_tournament.shutil.rmtree",
                    side_effect=OSError("injected cleanup failure"),
                ),
                self.assertRaisesRegex(TournamentError, "cleanup failed closed"),
            ):
                _run_isolated_control_plane_doctor(ROOT, inventory, passing_runner)

        with tempfile.TemporaryDirectory(
            prefix=f"{_DOCTOR_WORKSPACE_PREFIX}d-"
        ) as temporary:
            workspace = Path(temporary).resolve()
            with (
                patch(
                    "hive_mind_os.agent_tournament._control_plane_identity",
                    return_value=identity,
                ),
                patch(
                    "hive_mind_os.agent_tournament.tempfile.mkdtemp",
                    return_value=str(workspace),
                ),
                patch(
                    "hive_mind_os.agent_tournament._checked_git",
                    side_effect=TournamentError("injected operation failure"),
                ),
                patch("hive_mind_os.agent_tournament.shutil.rmtree"),
                patch(
                    "hive_mind_os.agent_tournament.os.path.lexists",
                    return_value=True,
                ),
                self.assertRaisesRegex(TournamentError, "cleanup failed closed"),
            ):
                _run_isolated_control_plane_doctor(ROOT, inventory, passing_runner)

        with tempfile.TemporaryDirectory(
            prefix=f"{_DOCTOR_WORKSPACE_PREFIX}m-"
        ) as temporary:
            workspace = Path(temporary).resolve()
            with (
                patch(
                    "hive_mind_os.agent_tournament._control_plane_identity",
                    return_value=identity,
                ),
                patch(
                    "hive_mind_os.agent_tournament.tempfile.mkdtemp",
                    return_value=str(workspace),
                ),
                patch(
                    "hive_mind_os.agent_tournament._snapshot_protected_states",
                    side_effect=(before, mutated),
                ),
                patch(
                    "hive_mind_os.agent_tournament._checked_git",
                    side_effect=TournamentError("injected operation failure"),
                ),
                self.assertRaisesRegex(
                    TournamentError,
                    "mutated source control-plane authority state",
                ),
            ):
                _run_isolated_control_plane_doctor(ROOT, inventory, passing_runner)

    def test_control_plane_audit_reaches_strict_lint_under_safe_path(self) -> None:
        receipt, transcript = control_plane_gate(ROOT)
        stdout, stderr = _decode_command_transcript(transcript, label="control-plane")
        rendered = (stdout + stderr).decode("utf-8", errors="replace")
        self.assertEqual("failed", receipt["status"])
        self.assertIn("digest-unsealed", rendered)
        self.assertNotIn("ModuleNotFoundError", rendered)


class IndependentRoleGradeTests(unittest.TestCase):
    def test_all_eight_roles_receive_separately_derived_grade(self) -> None:
        observed = []
        for role in TOURNAMENT_ROLES:
            with self.subTest(role=role):
                grade, _ = grade_role(ROOT, role, passing_runner)
                observed.append(grade["role"])
                expected_score = 86 if role in {"explorer", "builder", "curator"} else 81
                self.assertEqual(expected_score, grade["score"])
                self.assertEqual("adapt", grade["court"]["disposition"])
                self.assertFalse(grade["operationally_qualified"])
                self.assertEqual(6, len(set(grade["court"]["identities"].values())))
                self.assertIn(
                    grade["operational_dimensions"]["repository_delivery"],
                    {"limited-local", "planned"},
                )
                self.assertFalse(grade["court"]["promotion_authorized"])
        self.assertEqual(list(TOURNAMENT_ROLES), observed)

    def test_fixable_test_failure_adapts_instead_of_destroying_champion(self) -> None:
        grade, _ = grade_role(ROOT, "builder", failing_runner)
        self.assertEqual("adapt", grade["court"]["disposition"])
        self.assertEqual([], grade["fatal_findings"])
        feedback = feedback_contract(
            grade,
            {"fatal_findings": [], "development_gaps": ["builder: injected failure"]},
        )
        self.assertTrue(feedback["immutable_champion"])
        self.assertFalse(feedback["promotion_authorized"])
        self.assertEqual("SCAN-REPOSITORY", feedback["restart_nodes"][0])
        self.assertEqual(3, feedback["max_cycles"])
        self.assertEqual(3, feedback["cycles_executed"])
        self.assertEqual(
            [
                "reconsider-from-source-evidence",
                "attack-with-counterexamples",
                "seal-acceptance-rollback-and-reentry",
            ],
            [cycle["stage"] for cycle in feedback["cycles"]],
        )


class WholeSystemGradeTests(unittest.TestCase):
    @staticmethod
    def receipts(*, fatal: bool = False):
        values = {"SCAN-REPOSITORY": {"head": "a" * 40, "branch": "main", "dirty_path_count": 0, "file_count": 1, "inventory_digest": "sha256:" + "a" * 64, "host_runtimes": _host_runtime_evidence(), "execution": {"runner_identity": "fixture", "doctor_isolation_runner_identity": "fixture", "trusted_builtin_runner": False, "runtime_path": "src/hive_mind_os/agent_tournament.py", "runtime_sha256": "sha256:" + "b" * 64}}}
        for role in TOURNAMENT_ROLES:
            values[_role_node_id(role)] = {
                "role": role,
                "score": 100,
                "grade": "A",
                "grade_digest": "sha256:" + sha_char(role) * 64,
                "court": {"disposition": "adopt"},
            }
            values[_feedback_node_id(role)] = {"feedback_digest": "sha256:" + sha_char(role, offset=1) * 64}
        for lane in ("static", *SYSTEM_TEST_LANES, *CONTROL_PLANE_COMMANDS, "full-suite"):
            values["SYSTEM-" + lane.upper()] = {
                "lane": lane,
                "status": "passed",
                "critical": False,
                "receipt_digest": "sha256:" + sha_char(lane) * 64,
            }
        values["CROSS-EXAMINE"] = {
            "fatal_findings": ["safety gate failed"] if fatal else [],
            "development_gaps": [],
        }
        return values

    def test_catastrophic_finding_cannot_hide_inside_perfect_average(self) -> None:
        report = championship(self.receipts(fatal=True), "sha256:" + "f" * 64)
        self.assertEqual(100, report["role_average"])
        self.assertEqual("quarantine", report["court"]["disposition"])
        self.assertIn("safety gate failed", report["fatal_findings"])

    def test_static_gate_parses_every_listed_python_and_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "good.py").write_text("value = 1\n", encoding="utf-8")
            (root / "bad.json").write_text("{broken", encoding="utf-8")
            good_content = (root / "good.py").read_bytes()
            bad_content = (root / "bad.json").read_bytes()
            inventory = {
                "inventory_digest": "sha256:" + "0" * 64,
                "files": [
                    {
                        "path": "good.py",
                        "bytes": len(good_content),
                        "sha256": "sha256:" + sha256(good_content).hexdigest(),
                    },
                    {
                        "path": "bad.json",
                        "bytes": len(bad_content),
                        "sha256": "sha256:" + sha256(bad_content).hexdigest(),
                    },
                ],
            }
            result = static_repository_gate(root, inventory)
        self.assertEqual("failed", result["status"])
        self.assertTrue(result["critical"])
        self.assertEqual("bad.json", result["errors"][0]["path"])


class TournamentExecutionTests(unittest.TestCase):
    def test_inventory_excludes_create_only_output_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "repository"
            (repository / "src/hive_mind_os").mkdir(parents=True)
            (repository / "pyproject.toml").write_text(
                "[project]\nname='inventory-fixture'\nversion='0'\n",
                encoding="utf-8",
            )
            (repository / "src/hive_mind_os/__init__.py").write_text(
                "\"\"\"Inventory fixture.\"\"\"\n",
                encoding="utf-8",
            )
            for argv in (
                ("git", "init", "--quiet"),
                ("git", "config", "user.email", "fixture@example.invalid"),
                ("git", "config", "user.name", "Fixture"),
                ("git", "add", "."),
                ("git", "commit", "--quiet", "-m", "fixture"),
            ):
                subprocess.run(
                    argv,
                    cwd=repository,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )

            output = repository / "evidence/tournaments/run"
            output.mkdir(parents=True)
            (output / "plan.json").write_text("{}\n", encoding="utf-8")
            with patch(
                "hive_mind_os.agent_tournament._required_inventory_paths",
                return_value=frozenset(),
            ):
                opening = inventory_repository(repository, exclude=output)
                (output / "receipt.json").write_text("{}\n", encoding="utf-8")
                closing = inventory_repository(repository, exclude=output)

            self.assertEqual(opening["inventory_digest"], closing["inventory_digest"])
            self.assertEqual(opening["dirty_path_count"], closing["dirty_path_count"])

    def test_executor_writes_verifiable_receipts_without_claiming_skipped_full_suite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            result = run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            verified = verify_run_directory(output)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            role_wave = json.loads((output / "waves/wave-02.json").read_text(encoding="utf-8"))

            self.assertEqual("verified", result["status"])
            self.assertEqual(result, verified)
            self.assertEqual(8, len(role_wave["nodes"]))
            self.assertTrue(role_wave["parallel"])
            self.assertEqual("deferred", next(item for item in report["system_lanes"] if item["lane"] == "full-suite")["status"])
            self.assertEqual("adapt", report["court"]["disposition"])
            self.assertEqual(set(TOURNAMENT_ROLES), {item["role"] for item in report["role_grades"]})

            with self.assertRaisesRegex(TournamentError, "caller-selected repository"):
                verify_run_directory(output, repository=Path(temporary))

            with (
                patch(
                    "hive_mind_os.agent_tournament.__file__",
                    str(Path(temporary) / "other-checkout/agent_tournament.py"),
                ),
                self.assertRaisesRegex(TournamentError, "verifier runtime"),
            ):
                verify_run_directory(output, repository=ROOT)

            with (
                patch(
                    "hive_mind_os.agent_tournament._source_authority_roots",
                    return_value=(("forged-authority", output.parent),),
                ),
                self.assertRaisesRegex(TournamentError, "overlaps"),
            ):
                verify_run_directory(output, repository=ROOT)

            environment = dict(os.environ)
            environment["PYTHONPATH"] = str((ROOT / "src").resolve())
            environment["PYTHONNOUSERSITE"] = "1"
            cli_verify = subprocess.run(
                (
                    sys.executable,
                    "-B",
                    "-m",
                    "hive_mind_os.cli",
                    "tournament",
                    "verify",
                    "--run-dir",
                    str(output),
                    "--repository",
                    str(ROOT),
                ),
                cwd=temporary,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(
                0,
                cli_verify.returncode,
                cli_verify.stderr.decode("utf-8", errors="replace"),
            )

            (output / "unmanifested.txt").write_text("concealed", encoding="utf-8")
            with self.assertRaisesRegex(TournamentError, "inventory mismatch"):
                verify_run_directory(output)

            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "artifact contract mismatch"):
                verify_run_directory(output)

            (output / "unmanifested.txt").unlink()
            _write_json(output / "manifest.json", _manifest(output))
            (output / "nested").mkdir()
            (output / "nested/manifest.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(TournamentError, "directory contract"):
                verify_run_directory(output)

    def test_verifier_rejects_a_self_consistent_but_incomplete_forged_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "forged"
            output.mkdir()
            for directory in ("receipts", "transcripts", "waves"):
                (output / directory).mkdir()
            plan = build_tournament_plan()
            _write_json(output / "plan.json", plan)
            report = {
                "schema_version": 1,
                "kind": "hive-mind-agent-readiness-tournament-report",
                "plan_digest": plan["plan_digest"],
                "court": {"disposition": "adopt"},
            }
            report["report_digest"] = canonical_digest(report)
            _write_json(output / "report.json", report)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "report fields"):
                verify_run_directory(output)

    def test_verifier_rederives_championship_instead_of_trusting_rehashed_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            report["system_score"] = 100
            report["overall_score"] = 100
            report["court"]["disposition"] = "adopt"
            report.pop("report_digest")
            report["report_digest"] = canonical_digest(report)
            _write_json(output / "report.json", report)
            _write_json(output / "receipts/CHAMPIONSHIP.json", report)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "not derivable"):
                verify_run_directory(output)

    def test_closed_schemas_reject_rehashed_unknown_semantic_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )

            role_path = output / "receipts/ROLE-ORCHESTRATOR.json"
            original_role = json.loads(role_path.read_text(encoding="utf-8"))
            forged_role = deepcopy(original_role)
            forged_role["operationally_complete"] = True
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "grade fields"):
                verify_run_directory(output)

            forged_role = deepcopy(original_role)
            forged_role["criteria"][0]["override"] = "pass"
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "criterion"):
                verify_run_directory(output)

            forged_role = deepcopy(original_role)
            next(
                row
                for row in forged_role["criteria"]
                if row["criterion_id"] == "independent-role-tests"
            )["evidence"] = [
                "CLAIM: independently production-certified with live customer value"
            ]
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "sealed checkout"):
                verify_run_directory(output)

            forged_role = deepcopy(original_role)
            forged_role["rubric_observations"]["fail_closed_count"] = 999
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "sealed checkout"):
                verify_run_directory(output)

            forged_role = deepcopy(original_role)
            forged_role["test_receipt"]["tests_skipped"] = False
            forged_role["test_receipt"].pop("receipt_digest")
            forged_role["test_receipt"]["receipt_digest"] = canonical_digest(
                forged_role["test_receipt"]
            )
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "skipped-test evidence"):
                verify_run_directory(output)

            forged_role = deepcopy(original_role)
            forged_role["court"]["promotion_authorized"] = 0
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "disposition or qualification"):
                verify_run_directory(output)
            _write_json(role_path, original_role)

            system_path = output / "receipts/SYSTEM-LIFECYCLE.json"
            original_system = json.loads(system_path.read_text(encoding="utf-8"))
            forged_system = deepcopy(original_system)
            forged_system["operationally_complete"] = True
            forged_system.pop("receipt_digest")
            forged_system["receipt_digest"] = canonical_digest(forged_system)
            _write_json(system_path, forged_system)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "system receipt fields"):
                verify_run_directory(output)
            _write_json(system_path, original_system)

            static_path = output / "receipts/SYSTEM-STATIC.json"
            original_static = json.loads(static_path.read_text(encoding="utf-8"))
            forged_static = deepcopy(original_static)
            forged_static["errors"] = [
                {"path": "pyproject.toml", "error": "fabricated parser failure"}
            ]
            forged_static["status"] = "failed"
            forged_static["critical"] = True
            forged_static.pop("receipt_digest")
            forged_static["receipt_digest"] = canonical_digest(forged_static)
            _write_json(static_path, forged_static)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "sealed checkout"):
                verify_run_directory(output)
            _write_json(static_path, original_static)

            scan_path = output / "receipts/SCAN-REPOSITORY.json"
            original_scan = json.loads(scan_path.read_text(encoding="utf-8"))
            forged_scan = deepcopy(original_scan)
            forged_scan["files"][0]["trusted"] = True
            forged_scan.pop("inventory_digest")
            forged_scan["inventory_digest"] = canonical_digest(forged_scan)
            _write_json(scan_path, forged_scan)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "malformed file row"):
                verify_run_directory(output)
            _write_json(scan_path, original_scan)

            wave_path = output / "waves/wave-02.json"
            original_wave = json.loads(wave_path.read_text(encoding="utf-8"))
            forged_wave = deepcopy(original_wave)
            forged_wave["operationally_complete"] = True
            _write_json(wave_path, forged_wave)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "wave 2 differs"):
                verify_run_directory(output)
            _write_json(wave_path, original_wave)

            serial_wave_path = output / "waves/wave-01.json"
            original_serial_wave = json.loads(
                serial_wave_path.read_text(encoding="utf-8")
            )
            forged_serial_wave = deepcopy(original_serial_wave)
            forged_serial_wave["wave"] = True
            _write_json(serial_wave_path, forged_serial_wave)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "wave 1 differs"):
                verify_run_directory(output)

            forged_serial_wave = deepcopy(original_serial_wave)
            forged_serial_wave["observed_peak_concurrency"] = True
            _write_json(serial_wave_path, forged_serial_wave)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "concurrency evidence"):
                verify_run_directory(output)

            forged_serial_wave = deepcopy(original_serial_wave)
            forged_serial_wave["observed_peak_command_concurrency"] = False
            _write_json(serial_wave_path, forged_serial_wave)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "command-concurrency evidence"):
                verify_run_directory(output)

            forged_serial_wave = deepcopy(original_serial_wave)
            forged_serial_wave["attempts"]["SCAN-REPOSITORY"][0]["attempt"] = True
            _write_json(serial_wave_path, forged_serial_wave)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "attempt number"):
                verify_run_directory(output)
            _write_json(serial_wave_path, original_serial_wave)

            report_path = output / "report.json"
            original_report = json.loads(report_path.read_text(encoding="utf-8"))
            forged_report = deepcopy(original_report)
            forged_report["operationally_complete"] = True
            forged_report.pop("report_digest")
            forged_report["report_digest"] = canonical_digest(forged_report)
            _write_json(report_path, forged_report)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "report fields"):
                verify_run_directory(output)
            _write_json(report_path, original_report)

            event_path = output / "events.jsonl"
            original_events = event_path.read_text(encoding="utf-8")
            events = [json.loads(line) for line in original_events.splitlines()]
            events[0]["operationally_complete"] = True
            previous = None
            for event in events:
                event["previous_event_digest"] = previous
                event.pop("event_digest", None)
                event["event_digest"] = canonical_digest(event)
                previous = event["event_digest"]
            event_path.write_text(
                "\n".join(
                    json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    for event in events
                )
                + "\n",
                encoding="utf-8",
            )
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "event fields"):
                verify_run_directory(output)
            event_path.write_text(original_events, encoding="utf-8")

            events = [json.loads(line) for line in original_events.splitlines()]
            events[0]["sequence"] = True
            previous = None
            for event in events:
                event["previous_event_digest"] = previous
                event.pop("event_digest", None)
                event["event_digest"] = canonical_digest(event)
                previous = event["event_digest"]
            event_path.write_text(
                "\n".join(
                    json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    for event in events
                )
                + "\n",
                encoding="utf-8",
            )
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "event chain"):
                verify_run_directory(output)
            event_path.write_text(original_events, encoding="utf-8")

            forged_manifest = _manifest(output)
            forged_manifest["operationally_complete"] = True
            forged_manifest.pop("manifest_digest")
            forged_manifest["manifest_digest"] = canonical_digest(forged_manifest)
            _write_json(output / "manifest.json", forged_manifest)
            with self.assertRaisesRegex(TournamentError, "manifest fields"):
                verify_run_directory(output)

            forged_manifest = _manifest(output)
            forged_manifest["schema_version"] = True
            forged_manifest.pop("manifest_digest")
            forged_manifest["manifest_digest"] = canonical_digest(forged_manifest)
            _write_json(output / "manifest.json", forged_manifest)
            with self.assertRaisesRegex(TournamentError, "manifest schema"):
                verify_run_directory(output)

            role_text = role_path.read_text(encoding="utf-8")
            role_path.write_text(
                role_text.replace("{", '{"role":"attacker",', 1),
                encoding="utf-8",
            )
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "ambiguous JSON"):
                verify_run_directory(output)

    def test_cross_examination_rejects_rehashed_drift_and_gap_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            cross_path = output / "receipts/CROSS-EXAMINE.json"
            original_cross = json.loads(cross_path.read_text(encoding="utf-8"))

            forged_cross = deepcopy(original_cross)
            forged_cross["final_inventory_digest"] = "sha256:" + "0" * 64
            forged_cross.pop("receipt_digest")
            forged_cross["receipt_digest"] = canonical_digest(forged_cross)
            _write_json(cross_path, forged_cross)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "not drift-bound"):
                verify_run_directory(output)

            forged_cross = deepcopy(original_cross)
            forged_cross["development_gaps"].remove(
                "the authoritative repository lifecycle marks five of eight roles as planned"
            )
            forged_cross.pop("receipt_digest")
            forged_cross["receipt_digest"] = canonical_digest(forged_cross)
            _write_json(cross_path, forged_cross)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "adverse evidence is not exact"):
                verify_run_directory(output)

    def test_verifier_rejects_rehashed_base_score_or_lane_without_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            role_path = output / "receipts/ROLE-ORCHESTRATOR.json"
            original_role = json.loads(role_path.read_text(encoding="utf-8"))
            forged_role = deepcopy(original_role)
            forged_role["score"] = 100
            forged_role["grade"] = "A"
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "aggregate score"):
                verify_run_directory(output)

            _write_json(role_path, original_role)
            transcript_path = output / "transcripts/ROLE-ORCHESTRATOR.txt"
            original_transcript = transcript_path.read_text(encoding="utf-8")
            forged_stdout = b""
            forged_stderr = b"Ran 0 tests in 0.001s\r\n\r\nFAILED (failures=1)\r\n"
            forged_transcript = _encode_command_transcript(
                forged_stdout, forged_stderr
            )
            forged_role = deepcopy(original_role)
            command = forged_role["test_receipt"]
            command["stdout_sha256"] = "sha256:" + sha256(forged_stdout).hexdigest()
            command["stderr_sha256"] = "sha256:" + sha256(forged_stderr).hexdigest()
            command["transcript_sha256"] = "sha256:" + sha256(
                forged_transcript.encode("utf-8")
            ).hexdigest()
            command.pop("receipt_digest")
            command["receipt_digest"] = canonical_digest(command)
            forged_role.pop("grade_digest")
            forged_role["grade_digest"] = canonical_digest(forged_role)
            _write_json(role_path, forged_role)
            transcript_path.write_bytes(forged_transcript.encode("utf-8"))
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "test totals"):
                verify_run_directory(output)

            _write_json(role_path, original_role)
            transcript_path.write_bytes(original_transcript.encode("utf-8"))
            receipt_mutations = (
                (
                    "timing",
                    {"started_at": "2999-01-01T00:00:00Z", "ended_at": "1900-01-01T00:00:00Z", "duration_ms": -999},
                    "timing",
                ),
                (
                    "package",
                    {
                        "resolved_package": str(Path(temporary) / "attacker/__init__.py"),
                        "expected_package_root": str(Path(temporary) / "attacker"),
                    },
                    "package root",
                ),
                (
                    "environment",
                    {
                        "environment_policy": {
                            **original_role["test_receipt"]["environment_policy"],
                            "inherited_names": ["AWS_SECRET_ACCESS_KEY", *FAKE_CHILD_ENV_NAMES],
                            "network_control": "unrestricted",
                        }
                    },
                    "child-environment",
                ),
            )
            for label, mutation, error_pattern in receipt_mutations:
                with self.subTest(forgery=label):
                    forged_role = deepcopy(original_role)
                    forged_role["test_receipt"].update(mutation)
                    forged_role["test_receipt"].pop("receipt_digest")
                    forged_role["test_receipt"]["receipt_digest"] = canonical_digest(
                        forged_role["test_receipt"]
                    )
                    forged_role.pop("grade_digest")
                    forged_role["grade_digest"] = canonical_digest(forged_role)
                    _write_json(role_path, forged_role)
                    _write_json(output / "manifest.json", _manifest(output))
                    with self.assertRaisesRegex(TournamentError, error_pattern):
                        verify_run_directory(output)

            _write_json(role_path, original_role)
            full_path = output / "receipts/SYSTEM-FULL-SUITE.json"
            forged_lane = {
                "lane": "full-suite",
                "status": "passed",
                "critical": False,
            }
            forged_lane["receipt_digest"] = canonical_digest(forged_lane)
            _write_json(full_path, forged_lane)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "lacks command evidence"):
                verify_run_directory(output)

    def test_command_transcript_round_trips_crlf_and_invalid_utf8_losslessly(self) -> None:
        stdout_expected = b"\xff\r\n"
        stderr_expected = b"\xfe\r\n"
        receipt, transcript = run_command_receipt(
            ROOT,
            (
                sys.executable,
                "-B",
                "-c",
                (
                    "import os;"
                    "os.write(1,bytes.fromhex('ff0d0a'));"
                    "os.write(2,bytes.fromhex('fe0d0a'))"
                ),
            ),
        )
        stdout, stderr = _decode_command_transcript(transcript, label="round-trip")
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(stdout_expected, stdout)
        self.assertEqual(stderr_expected, stderr)
        self.assertEqual(
            "sha256:" + sha256(stdout_expected).hexdigest(),
            receipt["stdout_sha256"],
        )
        self.assertEqual(
            "sha256:" + sha256(stderr_expected).hexdigest(),
            receipt["stderr_sha256"],
        )
        with self.assertRaisesRegex(TournamentError, "transcript envelope"):
            _decode_command_transcript(
                '{"encoding":"base64","schema_version":1,"stderr":"","stdout":1111}',
                label="numeric-stream",
            )

        oversized_argv = (
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "tests.test_mission",
            "-v",
        )
        oversized_receipt, oversized_transcript = passing_runner(ROOT, oversized_argv)
        with (
            patch("hive_mind_os.agent_tournament._MAX_COMMAND_STREAM_BYTES", 1),
            self.assertRaisesRegex(TournamentError, "per-stream evidence budget"),
        ):
            _validate_command_receipt(
                oversized_receipt,
                oversized_argv,
                oversized_transcript,
                ROOT,
                require_tests=True,
                label="oversized",
            )

    def test_sanitized_command_environment_runs_typescript_acceptance(self) -> None:
        node_executable = _node_executable()
        if node_executable is None:
            self.skipTest("a fixed native Node runtime is unavailable")
        command = (
            sys.executable,
            "-B",
            "-m",
            "unittest",
            (
                "tests.test_mission_loop_provider.ModelProviderActionAdapterTests."
                "test_node_typescript_repository_rejects_then_corrects_model_actions"
            ),
            "-v",
        )
        with tempfile.TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"PATH": temporary}, clear=False):
                child_environment = _child_environment(ROOT)
                receipt, transcript = run_command_receipt(
                    ROOT,
                    command,
                    timeout_seconds=180,
                )

        _stdout, stderr = _decode_command_transcript(
            transcript,
            label="TypeScript acceptance",
        )
        child_path = {
            os.path.normcase(value)
            for value in child_environment["PATH"].split(os.pathsep)
        }
        self.assertIn(
            os.path.normcase(str(node_executable.parent)),
            child_path,
        )
        self.assertNotIn(os.path.normcase(temporary), child_path)
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(1, receipt["tests_run"])
        self.assertEqual(0, receipt["tests_skipped"])
        self.assertNotIn(b"executable is not allowlisted", stderr)

    def test_command_timing_excludes_the_import_provenance_probe(self) -> None:
        sequence: list[str] = []
        timestamp_values = iter(
            ("2026-09-03T00:00:00Z", "2026-09-03T00:00:00.100000Z")
        )

        def fake_now() -> str:
            sequence.append("timestamp")
            return next(timestamp_values)

        def fake_subprocess(argv, **_kwargs):
            if "importlib.util" in " ".join(argv):
                sequence.append("provenance")
                return (
                    0,
                    str((ROOT / "src/hive_mind_os/__init__.py").resolve()).encode()
                    + b"\n",
                    b"",
                    False,
                )
            sequence.append("command")
            return 0, b"", b"", False

        with (
            patch("hive_mind_os.agent_tournament._now", side_effect=fake_now),
            patch(
                "hive_mind_os.agent_tournament.time.monotonic",
                side_effect=(10.0, 10.1),
            ),
            patch(
                "hive_mind_os.agent_tournament._bounded_subprocess",
                side_effect=fake_subprocess,
            ),
        ):
            receipt, _transcript = run_command_receipt(
                ROOT,
                (sys.executable, "-B", "-c", "pass"),
            )

        self.assertEqual(
            ["provenance", "timestamp", "command", "timestamp"],
            sequence,
        )
        self.assertEqual("2026-09-03T00:00:00Z", receipt["started_at"])
        self.assertEqual("2026-09-03T00:00:00.100000Z", receipt["ended_at"])
        self.assertTrue(receipt["temporary_directory_cleanup_completed"])
        self.assertFalse(os.path.lexists(receipt["temporary_directory"]))
        self.assertEqual(
            {
                "TEMP": receipt["temporary_directory"],
                "TMP": receipt["temporary_directory"],
                "TMPDIR": receipt["temporary_directory"],
            },
            receipt["environment_policy"]["temporary_directory_bindings"],
        )

    @unittest.skipUnless(os.name == "nt", "classic path budget is Windows-specific")
    def test_short_temp_roots_preserve_the_sealed_arena_path_budget(self) -> None:
        script = (
            "import os,pathlib,shutil,tempfile;"
            "t=pathlib.Path(os.environ['TEMP']).resolve();"
            "r=pathlib.Path(tempfile.mkdtemp(prefix='hive-par-',dir=t));"
            f"n=len(str(t))+{_SEALED_CONTROL_PLANE_TEMP_DESCENDANT_BUDGET}"
            "-len(str(r))-1;"
            "p=r/('x'*n);p.mkdir();"
            f"assert len(str(p))==len(str(t))+"
            f"{_SEALED_CONTROL_PLANE_TEMP_DESCENDANT_BUDGET};"
            "shutil.rmtree(r)"
        )
        receipt, _transcript = run_command_receipt(
            ROOT, (sys.executable, "-B", "-c", script)
        )
        command_root = Path(receipt["temporary_directory"])
        self.assertEqual("passed", receipt["status"])
        self.assertTrue(command_root.name.startswith(_COMMAND_TEMP_PREFIX))
        self.assertLessEqual(
            len(str(command_root)) + _SEALED_CONTROL_PLANE_TEMP_DESCENDANT_BUDGET,
            _WINDOWS_CLASSIC_PATH_CHARACTER_LIMIT,
        )
        self.assertFalse(os.path.lexists(command_root))

        workspace = Path(
            tempfile.mkdtemp(
                prefix=_DOCTOR_WORKSPACE_PREFIX,
                dir=Path(tempfile.gettempdir()).resolve(),
            )
        ).resolve()
        doctor_root = workspace / _DOCTOR_TEMP_DIRECTORY_NAME
        try:
            doctor_root.mkdir()
            _validate_sealed_control_plane_temp_path_budget(doctor_root)
            arena = Path(tempfile.mkdtemp(prefix="hive-par-", dir=doctor_root))
            remaining = (
                len(str(doctor_root))
                + _SEALED_CONTROL_PLANE_TEMP_DESCENDANT_BUDGET
                - len(str(arena))
                - 1
            )
            deepest = arena / ("x" * remaining)
            deepest.mkdir()
            self.assertEqual(
                len(str(doctor_root))
                + _SEALED_CONTROL_PLANE_TEMP_DESCENDANT_BUDGET,
                len(str(deepest)),
            )
            shutil.rmtree(arena)
        finally:
            shutil.rmtree(workspace)
        self.assertFalse(os.path.lexists(workspace))

    @unittest.skipUnless(os.name == "nt", "short-root selection is Windows-specific")
    def test_nested_ambient_temp_is_not_inherited_by_command_children(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            inherited_root = Path(parent).resolve() / ("nested-" + "n" * 80)
            inherited_root.mkdir()
            script = (
                "import os,pathlib,shutil,tempfile;"
                "t=pathlib.Path(os.environ['TEMP']).resolve();"
                "r=pathlib.Path(tempfile.mkdtemp(prefix='nested-',dir=t));"
                "p=r/('x'*180);p.mkdir();shutil.rmtree(r)"
            )
            with patch(
                "hive_mind_os.agent_tournament.tempfile.gettempdir",
                return_value=str(inherited_root),
            ):
                expected_parents = _validated_command_temp_parents(
                    _live_source_authority_roots(ROOT)
                )
                receipt, _transcript = run_command_receipt(
                    ROOT, (sys.executable, "-B", "-c", script)
                )

        command_root = Path(receipt["temporary_directory"])
        self.assertEqual("passed", receipt["status"])
        self.assertEqual(expected_parents[0], command_root.parent)
        self.assertNotEqual(inherited_root, command_root.parent)
        self.assertLessEqual(
            len(str(command_root)) + _WINDOWS_COMMAND_TEMP_DESCENDANT_RESERVE,
            _WINDOWS_CLASSIC_PATH_CHARACTER_LIMIT,
        )
        self.assertFalse(os.path.lexists(command_root))

    @unittest.skipUnless(os.name == "nt", "extended path cleanup is Windows-specific")
    def test_command_cleanup_removes_real_paths_beyond_max_path(self) -> None:
        script = (
            "import os,pathlib;"
            "from hive_mind_os.receipts import filesystem_path;"
            "t=pathlib.Path(os.environ['TEMP']).resolve();"
            "d=t/('x'*240);"
            "os.mkdir(filesystem_path(d));"
            "open(filesystem_path(d/'artifact.bin'),'wb').write(b'x')"
        )
        receipt, _transcript = run_command_receipt(
            ROOT, (sys.executable, "-B", "-c", script)
        )
        command_root = Path(receipt["temporary_directory"])
        self.assertEqual("passed", receipt["status"])
        self.assertGreater(len(str(command_root / ("x" * 240))), 260)
        self.assertTrue(receipt["temporary_directory_cleanup_completed"])
        self.assertFalse(os.path.lexists(command_root))

    def test_command_cleanup_retries_a_transient_not_empty_error(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            owned_root = Path(parent).resolve() / "owned"
            owned_root.mkdir()
            (owned_root / "artifact.bin").write_bytes(b"x")
            real_remove = shutil.rmtree
            calls = 0

            def transient_then_remove(path, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError(errno.ENOTEMPTY, "transient not empty")
                return real_remove(path, *args, **kwargs)

            with (
                patch(
                    "hive_mind_os.agent_tournament.shutil.rmtree",
                    side_effect=transient_then_remove,
                ),
                patch("hive_mind_os.agent_tournament.time.sleep") as sleep,
            ):
                _remove_disposable_tree(owned_root)

            self.assertEqual(2, calls)
            sleep.assert_called_once_with(0.05)
            self.assertFalse(os.path.lexists(owned_root))

    def test_command_cleanup_rejects_a_replaced_root_without_touching_target(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as parent:
            fixture = Path(parent).resolve()
            owned_root = fixture / "owned"
            target = fixture / "target"
            owned_root.mkdir()
            target.mkdir()
            sentinel = target / "sentinel.txt"
            sentinel.write_text("must survive", encoding="utf-8")
            identity = _owned_cleanup_identity(owned_root)
            shutil.rmtree(owned_root)
            try:
                owned_root.symlink_to(target, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks are unavailable: {error}")
            try:
                with self.assertRaisesRegex(TournamentError, "link|identity"):
                    _remove_disposable_tree(
                        owned_root, expected_identity=identity
                    )
                self.assertEqual("must survive", sentinel.read_text(encoding="utf-8"))
            finally:
                owned_root.unlink(missing_ok=True)

    @unittest.skipUnless(os.name == "nt", "NTFS junction regression")
    def test_command_cleanup_rejects_a_replacement_junction(self) -> None:
        with tempfile.TemporaryDirectory() as parent:
            fixture = Path(parent).resolve()
            owned_root = fixture / "owned"
            target = fixture / "target"
            owned_root.mkdir()
            target.mkdir()
            sentinel = target / "sentinel.txt"
            sentinel.write_text("must survive", encoding="utf-8")
            identity = _owned_cleanup_identity(owned_root)
            owned_root.rmdir()
            created = subprocess.run(
                ("cmd", "/c", "mklink", "/J", str(owned_root), str(target)),
                capture_output=True,
                check=False,
                text=True,
            )
            if created.returncode != 0:
                self.skipTest(f"directory junctions are unavailable: {created.stderr}")
            try:
                with self.assertRaisesRegex(TournamentError, "link|identity"):
                    _remove_disposable_tree(
                        owned_root, expected_identity=identity
                    )
                self.assertEqual("must survive", sentinel.read_text(encoding="utf-8"))
            finally:
                os.rmdir(owned_root)

    @unittest.skipUnless(os.name == "nt", "Windows short-root fallback")
    def test_invalid_ambient_temp_falls_back_to_user_profile(self) -> None:
        missing_ambient = ROOT.parent / ("missing-ambient-" + "x" * 80)
        with patch(
            "hive_mind_os.agent_tournament.tempfile.gettempdir",
            return_value=str(missing_ambient),
        ):
            parents = _validated_command_temp_parents(
                _live_source_authority_roots(ROOT)
            )
        self.assertEqual(Path(os.environ["USERPROFILE"]).resolve(), parents[0])

    def test_user_profile_is_not_inherited_by_command_children(self) -> None:
        temporary_root = Path(tempfile.gettempdir()).resolve() / (
            _COMMAND_TEMP_PREFIX + "environment"
        )
        environment = _child_environment(
            ROOT, temporary_directory=temporary_root
        )
        self.assertNotIn("USERPROFILE", environment)
        self.assertEqual(
            str(temporary_root.parent),
            environment[_COMMAND_TEMP_PARENT_ENV_NAME],
        )

    @unittest.skipUnless(os.name == "nt", "classic path budget is Windows-specific")
    def test_overlong_control_plane_temp_root_fails_before_execution(self) -> None:
        overlong = Path(tempfile.gettempdir()).resolve() / ("x" * 100)
        with self.assertRaisesRegex(TournamentError, "Windows path budget"):
            _validate_sealed_control_plane_temp_path_budget(overlong)

        with tempfile.TemporaryDirectory() as parent:
            requested = Path(parent).resolve() / f"{_COMMAND_TEMP_PREFIX}budget"
            with (
                patch(
                    "hive_mind_os.agent_tournament._validate_sealed_control_plane_temp_path_budget",
                    side_effect=TournamentError("injected Windows path budget failure"),
                ),
                patch(
                    "hive_mind_os.agent_tournament._run_command_receipt_with_temporary_directory"
                ) as command_execution,
                self.assertRaisesRegex(TournamentError, "Windows path budget"),
            ):
                run_command_receipt(
                    ROOT,
                    CONTROL_PLANE_COMMANDS["control-plane-tests"],
                    temporary_directory=requested,
                )
            command_execution.assert_not_called()
            self.assertFalse(os.path.lexists(requested))

    @unittest.skipUnless(os.name == "nt", "classic path budget is Windows-specific")
    def test_doctor_path_budget_fails_before_clone(self) -> None:
        inventory = inventory_repository(ROOT)
        with tempfile.TemporaryDirectory() as parent:
            workspace = Path(parent).resolve() / f"{_DOCTOR_WORKSPACE_PREFIX}fixture"
            workspace.mkdir()
            with (
                patch(
                    "hive_mind_os.agent_tournament.tempfile.mkdtemp",
                    return_value=str(workspace),
                ),
                patch(
                    "hive_mind_os.agent_tournament._validate_sealed_control_plane_temp_path_budget",
                    side_effect=TournamentError("injected Windows path budget failure"),
                ),
                patch("hive_mind_os.agent_tournament._checked_git") as checked_git,
                self.assertRaisesRegex(TournamentError, "Windows path budget"),
            ):
                _run_isolated_control_plane_doctor(ROOT, inventory, passing_runner)
            checked_git.assert_not_called()
            self.assertFalse(os.path.lexists(workspace))

    def test_cleanup_failure_preserves_non_certifying_command_evidence(self) -> None:
        command = (
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "tests.synthetic_cleanup_fixture",
            "-v",
        )
        provenance = str((ROOT / "src/hive_mind_os/__init__.py").resolve()).encode(
            "utf-8"
        ) + b"\n"
        fake_results = (
            (0, provenance, b"", False),
            (0, b"", b"Ran 1 test in 0.001s\n\nOK\n", False),
        )
        captured: _CommandEvidenceFailure | None = None
        try:
            with (
                patch(
                    "hive_mind_os.agent_tournament._bounded_subprocess",
                    side_effect=fake_results,
                ),
                patch(
                    "hive_mind_os.agent_tournament.shutil.rmtree",
                    side_effect=OSError("simulated cleanup failure"),
                ),
            ):
                run_command_receipt(ROOT, command)
        except _CommandEvidenceFailure as error:
            captured = error
        self.assertIsNotNone(captured)
        assert captured is not None
        diagnostic = captured.command_receipt
        diagnostic_root = Path(diagnostic["temporary_directory"])
        try:
            self.assertEqual("failed", diagnostic["status"])
            self.assertEqual("passed", diagnostic["command_status_before_cleanup"])
            self.assertFalse(diagnostic["temporary_directory_cleanup_completed"])
            self.assertEqual(0, diagnostic["returncode"])
            self.assertEqual(1, diagnostic["tests_run"])
            self.assertEqual(0, diagnostic["tests_skipped"])
            self.assertEqual(
                diagnostic["transcript_sha256"],
                "sha256:" + sha256(captured.transcript.encode("utf-8")).hexdigest(),
            )
            _validate_command_cleanup_diagnostic(
                diagnostic,
                command,
                captured.transcript,
                ROOT,
                label="valid cleanup diagnostic",
            )
            invalid_digest = deepcopy(diagnostic)
            invalid_digest["receipt_digest"] = "sha256:" + "0" * 64
            with self.assertRaisesRegex(TournamentError, "digest"):
                _validate_command_cleanup_diagnostic(
                    invalid_digest,
                    command,
                    captured.transcript,
                    ROOT,
                    label="invalid cleanup diagnostic",
                )
            invalid_transcript = deepcopy(diagnostic)
            invalid_transcript["transcript_sha256"] = "sha256:" + "0" * 64
            invalid_transcript.pop("receipt_digest")
            invalid_transcript["receipt_digest"] = canonical_digest(invalid_transcript)
            with self.assertRaisesRegex(TournamentError, "transcript|hashes"):
                _validate_command_cleanup_diagnostic(
                    invalid_transcript,
                    command,
                    captured.transcript,
                    ROOT,
                    label="invalid cleanup diagnostic",
                )
            with self.assertRaises(TournamentError):
                _validate_command_receipt(
                    diagnostic,
                    command,
                    captured.transcript,
                    ROOT,
                    require_tests=True,
                    label="cleanup-failed diagnostic",
                )
        finally:
            shutil.rmtree(diagnostic_root, ignore_errors=True)
        self.assertFalse(os.path.lexists(diagnostic_root))

    def test_subprocess_output_budget_fails_closed_during_execution(self) -> None:
        with self.assertRaisesRegex(TournamentError, "output exceeded"):
            _bounded_subprocess(
                (
                    sys.executable,
                    "-B",
                    "-c",
                    "import os;os.write(1,b'x'*131072)",
                ),
                cwd=ROOT,
                environment=_child_environment(ROOT),
                timeout_seconds=10,
                max_stream_bytes=1024,
            )

    def test_verifier_rejects_duplicate_summary_and_all_skipped_credit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            role_path = output / "receipts/ROLE-ORCHESTRATOR.json"
            transcript_path = output / "transcripts/ROLE-ORCHESTRATOR.txt"
            original_role = json.loads(role_path.read_text(encoding="utf-8"))
            original_transcript = transcript_path.read_text(encoding="utf-8")

            for label, stdout, stderr, fields, error_pattern in (
                (
                    "duplicate-summary",
                    b"Ran 999999 tests in 0.001s\r\n\r\nOK\r\n",
                    b"Ran 3 tests in 0.001s\r\n\r\nOK\r\n",
                    {"tests_run": 999999, "tests_skipped": 0},
                    "test totals",
                ),
                (
                    "all-skipped",
                    b"",
                    b"Ran 3 tests in 0.001s\r\n\r\nOK (skipped=3)\r\n",
                    {"tests_run": 3, "tests_skipped": 3},
                    "status is not derivable",
                ),
            ):
                with self.subTest(forgery=label):
                    forged_role = deepcopy(original_role)
                    command = forged_role["test_receipt"]
                    transcript = _encode_command_transcript(stdout, stderr)
                    command.update(fields)
                    command["stdout_sha256"] = "sha256:" + sha256(stdout).hexdigest()
                    command["stderr_sha256"] = "sha256:" + sha256(stderr).hexdigest()
                    command["transcript_sha256"] = (
                        "sha256:" + sha256(transcript.encode("utf-8")).hexdigest()
                    )
                    command.pop("receipt_digest")
                    command["receipt_digest"] = canonical_digest(command)
                    forged_role.pop("grade_digest")
                    forged_role["grade_digest"] = canonical_digest(forged_role)
                    _write_json(role_path, forged_role)
                    transcript_path.write_text(transcript, encoding="utf-8")
                    _write_json(output / "manifest.json", _manifest(output))
                    with self.assertRaisesRegex(TournamentError, error_pattern):
                        verify_run_directory(output)
                    _write_json(role_path, original_role)
                    transcript_path.write_text(original_transcript, encoding="utf-8")

    def test_parallel_provenance_requires_positive_overlap(self) -> None:
        first = datetime(1970, 1, 1, tzinfo=UTC)
        adjacent = {
            "one": [
                {
                    "started_at": first.isoformat(),
                    "ended_at": (first + timedelta(seconds=1)).isoformat(),
                }
            ],
            "two": [
                {
                    "started_at": (first + timedelta(seconds=1)).isoformat(),
                    "ended_at": (first + timedelta(seconds=2)).isoformat(),
                }
            ],
        }
        self.assertEqual(1, _observed_peak_concurrency(adjacent))

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            wave_path = output / "waves/wave-02.json"
            wave = json.loads(wave_path.read_text(encoding="utf-8"))
            for index, node_id in enumerate(wave["nodes"]):
                start = first + timedelta(seconds=index * 2)
                row = wave["attempts"][node_id][0]
                row["started_at"] = start.isoformat().replace("+00:00", "Z")
                row["ended_at"] = (start + timedelta(seconds=1)).isoformat().replace(
                    "+00:00", "Z"
                )
                row["duration_ms"] = 1000
            wave["observed_peak_concurrency"] = 1
            _write_json(wave_path, wave)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "not enclosed by its final attempt"):
                verify_run_directory(output)

    def test_verifier_rejects_retry_after_contract_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=passing_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            wave_path = output / "waves/wave-02.json"
            wave = json.loads(wave_path.read_text(encoding="utf-8"))
            rows = wave["attempts"]["ROLE-EXPLORER"]
            completed = deepcopy(rows[0])
            completed["attempt"] = 2
            prior = {
                "attempt": 1,
                "outcome": "contract-or-evidence-exception",
                "error": "TournamentError: forged retry",
                "started_at": rows[0]["started_at"],
                "ended_at": rows[0]["ended_at"],
                "duration_ms": rows[0]["duration_ms"],
            }
            wave["attempts"]["ROLE-EXPLORER"] = [prior, completed]
            _write_json(wave_path, wave)
            _write_json(output / "manifest.json", _manifest(output))
            with self.assertRaisesRegex(TournamentError, "non-retryable retry"):
                verify_run_directory(output)

    def test_infrastructure_retry_is_bounded_and_recorded(self) -> None:
        calls = 0

        def transient_runner(repository: Path, argv: Sequence[str]):
            nonlocal calls
            if "tests.test_hive_cortex_explorer" in argv and calls == 0:
                calls += 1
                raise OSError("transient injected failure")
            return passing_runner(repository, argv)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            run_tournament(
                ROOT,
                output,
                max_workers=8,
                full_suite=False,
                command_runner=transient_runner,
                doctor_isolation_runner=passing_doctor_isolation_runner,
            )
            wave = json.loads((output / "waves/wave-02.json").read_text(encoding="utf-8"))
            attempts = wave["attempts"]["ROLE-EXPLORER"]
            self.assertEqual(2, len(attempts))
            self.assertEqual("infrastructure-exception", attempts[0]["outcome"])
            self.assertEqual("completed", attempts[1]["outcome"])

    def test_exhausted_parallel_wave_preserves_all_results_and_terminal_manifest(self) -> None:
        def broken_runner(_repository: Path, _argv: Sequence[str]):
            raise OSError("injected infrastructure outage")

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with self.assertRaisesRegex(TournamentError, "attempts exhausted"):
                run_tournament(
                    ROOT,
                    output,
                    max_workers=8,
                    full_suite=False,
                    command_runner=broken_runner,
                    doctor_isolation_runner=passing_doctor_isolation_runner,
                )
            self.assertTrue((output / "manifest.json").is_file())
            self.assertTrue((output / "incomplete.json").is_file())
            self.assertEqual(
                {"SCAN-REPOSITORY", *(_role_node_id(role) for role in TOURNAMENT_ROLES)},
                {path.stem for path in (output / "receipts").glob("*.json")},
            )
            self.assertEqual(9, len((output / "events.jsonl").read_text(encoding="utf-8").splitlines()))

    def test_contract_failure_is_not_mislabeled_or_retried(self) -> None:
        calls = 0

        def contract_failure_runner(repository: Path, argv: Sequence[str]):
            nonlocal calls
            if "tests.test_hive_cortex_explorer" in argv:
                calls += 1
                raise TournamentError("injected evidence-integrity defect")
            return passing_runner(repository, argv)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with self.assertRaisesRegex(TournamentError, "node execution failed"):
                run_tournament(
                    ROOT,
                    output,
                    max_workers=8,
                    full_suite=False,
                    command_runner=contract_failure_runner,
                    doctor_isolation_runner=passing_doctor_isolation_runner,
                )
            wave = json.loads((output / "waves/wave-02.json").read_text(encoding="utf-8"))
            attempts = wave["attempts"]["ROLE-EXPLORER"]
            self.assertEqual(1, calls)
            self.assertEqual(1, len(attempts))
            self.assertEqual("contract-or-evidence-exception", attempts[0]["outcome"])

    def test_executor_persists_cleanup_failure_command_diagnostics(self) -> None:
        expected_transcript: str | None = None

        def cleanup_failure_runner(repository: Path, argv: Sequence[str]):
            nonlocal expected_transcript
            receipt, transcript = passing_runner(repository, argv)
            if tuple(argv) != CONTROL_PLANE_COMMANDS["control-plane-tests"]:
                return receipt, transcript
            receipt["status"] = "failed"
            receipt["command_status_before_cleanup"] = "passed"
            receipt["temporary_directory_cleanup_completed"] = False
            receipt["temporary_directory_cleanup_error"] = "OSError: injected"
            receipt.pop("receipt_digest")
            receipt["receipt_digest"] = canonical_digest(receipt)
            expected_transcript = transcript
            raise _CommandEvidenceFailure(
                "injected command temporary cleanup failure",
                receipt,
                transcript,
                repository,
                argv,
                Path(receipt["temporary_directory"]),
            )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with self.assertRaisesRegex(TournamentError, "node execution failed"):
                run_tournament(
                    ROOT,
                    output,
                    max_workers=8,
                    full_suite=False,
                    command_runner=cleanup_failure_runner,
                    doctor_isolation_runner=passing_doctor_isolation_runner,
                )
            failure = json.loads(
                (output / "receipts/SYSTEM-CONTROL-PLANE-TESTS.json").read_text(
                    encoding="utf-8"
                )
            )
            transcript = (
                output / "transcripts/SYSTEM-CONTROL-PLANE-TESTS.txt"
            ).read_text(encoding="utf-8")
            self.assertEqual("contract-failed", failure["status"])
            self.assertTrue(failure["critical"])
            self.assertTrue(failure["diagnostic_only"])
            self.assertEqual(
                expected_transcript,
                transcript,
            )
            self.assertEqual(
                failure["diagnostic_transcript_sha256"],
                "sha256:" + sha256(transcript.encode("utf-8")).hexdigest(),
            )
            self.assertFalse(
                failure["diagnostic_command_receipt"][
                    "temporary_directory_cleanup_completed"
                ]
            )
            with self.assertRaises((OSError, TournamentError)):
                verify_run_directory(output, repository=ROOT)

    def test_executor_rejects_forged_cleanup_diagnostics(self) -> None:
        def forged_cleanup_runner(repository: Path, argv: Sequence[str]):
            receipt, transcript = passing_runner(repository, argv)
            if tuple(argv) != CONTROL_PLANE_COMMANDS["control-plane-tests"]:
                return receipt, transcript
            receipt["status"] = "failed"
            receipt["command_status_before_cleanup"] = "passed"
            receipt["temporary_directory_cleanup_completed"] = False
            receipt["temporary_directory_cleanup_error"] = "OSError: injected"
            receipt.pop("receipt_digest")
            receipt["receipt_digest"] = canonical_digest(receipt)
            raise _CommandEvidenceFailure(
                "injected forged cleanup evidence",
                receipt,
                transcript,
                repository,
                argv,
                Path(tempfile.gettempdir()).resolve() / f"{_COMMAND_TEMP_PREFIX}other",
            )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with self.assertRaisesRegex(TournamentError, "node execution failed"):
                run_tournament(
                    ROOT,
                    output,
                    max_workers=8,
                    full_suite=False,
                    command_runner=forged_cleanup_runner,
                    doctor_isolation_runner=passing_doctor_isolation_runner,
                )
            failure = json.loads(
                (output / "receipts/SYSTEM-CONTROL-PLANE-TESTS.json").read_text(
                    encoding="utf-8"
                )
            )
            unsigned = dict(failure)
            supplied = unsigned.pop("receipt_digest")
            self.assertEqual(supplied, canonical_digest(unsigned))
            self.assertIn("diagnostic rejected", failure["error"])
            self.assertNotIn("diagnostic_command_receipt", failure)
            self.assertNotIn("diagnostic_transcript_sha256", failure)
            self.assertFalse(
                (output / "transcripts/SYSTEM-CONTROL-PLANE-TESTS.txt").exists()
            )
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertNotIn(
                "transcripts/SYSTEM-CONTROL-PLANE-TESTS.txt",
                {row["path"] for row in manifest["files"]},
            )

    def test_executor_rejects_unbound_doctor_cleanup_diagnostics(self) -> None:
        def forged_doctor_runner(
            _repository: Path,
            _inventory: Mapping[str, Any],
            command_runner,
        ):
            workspace = Path(tempfile.gettempdir()).resolve() / "htd-never-created"
            checkout = workspace / "checkout"
            command = CONTROL_PLANE_COMMANDS["control-plane-doctor"]
            receipt, transcript = command_runner(checkout, command)
            receipt["status"] = "failed"
            receipt["command_status_before_cleanup"] = "passed"
            receipt["temporary_directory_cleanup_completed"] = False
            receipt["temporary_directory_cleanup_error"] = "OSError: injected"
            receipt.pop("receipt_digest")
            receipt["receipt_digest"] = canonical_digest(receipt)
            raise _CommandEvidenceFailure(
                "injected unbound doctor cleanup evidence",
                receipt,
                transcript,
                checkout,
                command,
                workspace / _DOCTOR_TEMP_DIRECTORY_NAME,
            )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with self.assertRaisesRegex(TournamentError, "node execution failed"):
                run_tournament(
                    ROOT,
                    output,
                    max_workers=8,
                    full_suite=False,
                    command_runner=passing_runner,
                    doctor_isolation_runner=forged_doctor_runner,
                )
            failure = json.loads(
                (output / "receipts/SYSTEM-CONTROL-PLANE-DOCTOR.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn("diagnostic rejected", failure["error"])
            self.assertNotIn("diagnostic_command_receipt", failure)
            self.assertFalse(
                (output / "transcripts/SYSTEM-CONTROL-PLANE-DOCTOR.txt").exists()
            )

    def test_executor_rejects_serial_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(TournamentError, "between 2 and 8"):
                run_tournament(
                    ROOT,
                    Path(temporary) / "run",
                    max_workers=1,
                    full_suite=False,
                    command_runner=passing_runner,
                    doctor_isolation_runner=passing_doctor_isolation_runner,
                )

    def test_executor_refuses_to_overwrite_prior_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            with self.assertRaisesRegex(TournamentError, "must not already exist"):
                run_tournament(
                    ROOT,
                    output,
                    command_runner=passing_runner,
                    doctor_isolation_runner=passing_doctor_isolation_runner,
                    full_suite=False,
                )


def sha_char(value: str, *, offset: int = 0) -> str:
    alphabet = "0123456789abcdef"
    return alphabet[(sum(value.encode("utf-8")) + offset) % len(alphabet)]


if __name__ == "__main__":
    unittest.main()
