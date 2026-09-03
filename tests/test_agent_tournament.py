from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Sequence
from unittest.mock import patch

from hive_mind_os.agent_tournament import (
    SYSTEM_TEST_LANES,
    TOURNAMENT_ROLES,
    TournamentError,
    _bounded_subprocess,
    _child_environment,
    _decode_command_transcript,
    _encode_command_transcript,
    _feedback_node_id,
    _manifest,
    _observed_peak_concurrency,
    _role_node_id,
    _validate_command_receipt,
    _write_json,
    build_tournament_plan,
    championship,
    control_plane_gate,
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


def passing_runner(repository: Path, argv: Sequence[str]):
    is_unittest = any(
        tuple(argv[index : index + 2]) == ("-m", "unittest")
        for index in range(len(argv) - 1)
    )
    stdout = b""
    stderr = b"Ran 3 tests in 0.001s\r\n\r\nOK\r\n" if is_unittest else b""
    started_at = datetime.now(UTC)
    time.sleep(0.01)
    ended_at = datetime.now(UTC)
    transcript = _encode_command_transcript(stdout, stderr)
    receipt = {
        "argv": list(argv),
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "ended_at": ended_at.isoformat().replace("+00:00", "Z"),
        "duration_ms": round((ended_at - started_at).total_seconds() * 1000),
        "status": "passed",
        "returncode": 0,
        "timed_out": False,
        "tests_run": 3 if is_unittest else None,
        "tests_skipped": 0,
        "import_provenance_bound": True,
        "resolved_package": str((repository / "src/hive_mind_os/__init__.py").resolve()),
        "expected_package_root": str((repository / "src/hive_mind_os").resolve()),
        "environment_policy": {
            "credential_environment_inherited": False,
            "inherited_git_variables": False,
            "git_configuration_isolation": "delegated to the repository code under test",
            "user_site_disabled": True,
            "network_control": "best-effort proxy deny; no kernel sandbox",
            "inherited_names": FAKE_CHILD_ENV_NAMES,
        },
        "test_output_unambiguous": True,
        "stdout_sha256": "sha256:" + sha256(stdout).hexdigest(),
        "stderr_sha256": "sha256:" + sha256(stderr).hexdigest(),
        "transcript_sha256": "sha256:" + sha256(transcript.encode("utf-8")).hexdigest(),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt, transcript


def failing_runner(repository: Path, argv: Sequence[str]):
    is_unittest = any(
        tuple(argv[index : index + 2]) == ("-m", "unittest")
        for index in range(len(argv) - 1)
    )
    stdout = b""
    stderr = (
        b"Ran 3 tests in 0.001s\r\n\r\nFAILED (failures=1)\r\n"
        if is_unittest
        else b"control-plane failed\r\n"
    )
    started_at = datetime.now(UTC)
    time.sleep(0.01)
    ended_at = datetime.now(UTC)
    transcript = _encode_command_transcript(stdout, stderr)
    receipt = {
        "argv": list(argv),
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "ended_at": ended_at.isoformat().replace("+00:00", "Z"),
        "duration_ms": round((ended_at - started_at).total_seconds() * 1000),
        "status": "failed",
        "returncode": 1,
        "timed_out": False,
        "tests_run": 3 if is_unittest else None,
        "tests_skipped": 0,
        "import_provenance_bound": True,
        "resolved_package": str((repository / "src/hive_mind_os/__init__.py").resolve()),
        "expected_package_root": str((repository / "src/hive_mind_os").resolve()),
        "environment_policy": {
            "credential_environment_inherited": False,
            "inherited_git_variables": False,
            "git_configuration_isolation": "delegated to the repository code under test",
            "user_site_disabled": True,
            "network_control": "best-effort proxy deny; no kernel sandbox",
            "inherited_names": FAKE_CHILD_ENV_NAMES,
        },
        "test_output_unambiguous": True,
        "stdout_sha256": "sha256:" + sha256(stdout).hexdigest(),
        "stderr_sha256": "sha256:" + sha256(stderr).hexdigest(),
        "transcript_sha256": "sha256:" + sha256(transcript.encode("utf-8")).hexdigest(),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    return receipt, transcript


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
        self.assertIn("SYSTEM-CODE-QA", by_id)
        self.assertIn("SYSTEM-FULL-SUITE", by_id)
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
        values = {"SCAN-REPOSITORY": {"head": "a" * 40, "branch": "main", "dirty_path_count": 0, "file_count": 1, "inventory_digest": "sha256:" + "a" * 64, "execution": {"runner_identity": "fixture", "trusted_builtin_runner": False, "runtime_path": "src/hive_mind_os/agent_tournament.py", "runtime_sha256": "sha256:" + "b" * 64}}}
        for role in TOURNAMENT_ROLES:
            values[_role_node_id(role)] = {
                "role": role,
                "score": 100,
                "grade": "A",
                "grade_digest": "sha256:" + sha_char(role) * 64,
                "court": {"disposition": "adopt"},
            }
            values[_feedback_node_id(role)] = {"feedback_digest": "sha256:" + sha_char(role, offset=1) * 64}
        for lane in ("static", *SYSTEM_TEST_LANES, "control-plane", "full-suite"):
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
                )
            wave = json.loads((output / "waves/wave-02.json").read_text(encoding="utf-8"))
            attempts = wave["attempts"]["ROLE-EXPLORER"]
            self.assertEqual(1, calls)
            self.assertEqual(1, len(attempts))
            self.assertEqual("contract-or-evidence-exception", attempts[0]["outcome"])

    def test_executor_rejects_serial_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(TournamentError, "between 2 and 8"):
                run_tournament(
                    ROOT,
                    Path(temporary) / "run",
                    max_workers=1,
                    full_suite=False,
                    command_runner=passing_runner,
                )

    def test_executor_refuses_to_overwrite_prior_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            with self.assertRaisesRegex(TournamentError, "must not already exist"):
                run_tournament(ROOT, output, command_runner=passing_runner, full_suite=False)


def sha_char(value: str, *, offset: int = 0) -> str:
    alphabet = "0123456789abcdef"
    return alphabet[(sum(value.encode("utf-8")) + offset) % len(alphabet)]


if __name__ == "__main__":
    unittest.main()
