from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, Sequence

from hive_mind_os import agent_tournament as v1
from hive_mind_os.agent_tournament_v2 import (
    TOURNAMENT_ROLES,
    TournamentV2Error,
    _authority_challenger,
    _cross_examine_v2,
    _derive_report,
    _feedback_node,
    _feedback_v2,
    _generic_failure,
    _manifest,
    _render_report,
    _role_node,
    _run_code_qa,
    _run_native_dag,
    _scan_receipt,
    _validate_challenger,
    _validate_code_qa,
    _validate_manifest,
    _validate_native_dag,
    _write_json_create,
    build_tournament_plan_v2,
    run_tournament_v2,
    validate_tournament_plan_v2,
    verify_run_directory_v2,
)
from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.evaluation_authority import capture_repository_binding
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import generation_zero_prompt, prompt_digest
from hive_mind_os.roles import ROLE_CONTRACTS
from tests.test_evaluation_authority import _manifest_document


def _sealed(
    document: dict[str, object], field: str = "receipt_digest"
) -> dict[str, object]:
    document[field] = canonical_digest(document)
    return document


def _report_receipts(
    *, failed_lane: str | None = None, full_status: str = "passed"
) -> dict[str, dict[str, object]]:
    receipts: dict[str, dict[str, object]] = {}
    receipts["SCAN-REPOSITORY"] = _sealed(
        {
            "repository_binding": {
                "head_commit": "a" * 40,
                "tree_oid": "b" * 40,
                "state_digest": canonical_digest({"state": "clean"}),
            },
            "inventory": {"inventory_digest": canonical_digest({"files": []})},
        }
    )
    for index, role in enumerate(TOURNAMENT_ROLES):
        grade: dict[str, object] = {
            "role": role,
            "score": 80 + index,
            "grade": "B",
            "court": {"disposition": "adapt"},
            "operationally_qualified": False,
        }
        grade["grade_digest"] = canonical_digest(grade)
        receipts[_role_node(role)] = grade
    lanes = {
        "SYSTEM-STATIC": "static",
        "SYSTEM-LIFECYCLE": "lifecycle",
        "SYSTEM-RESILIENCE": "resilience",
        "SYSTEM-EVOLUTION": "evolution",
        "SYSTEM-CONTROL-PLANE": "control-plane",
        "SYSTEM-CONTROL-PLANE-TESTS": "control-plane-tests",
        "SYSTEM-CONTROL-PLANE-DOCTOR": "control-plane-doctor",
        "SYSTEM-NATIVE-DAG": "native-dag",
        "SYSTEM-CODE-QA-V2": "code-qa-v2",
        "SYSTEM-FULL-SUITE": "full-suite",
    }
    for node_id, lane in lanes.items():
        status = full_status if node_id == "SYSTEM-FULL-SUITE" else "passed"
        if node_id == failed_lane:
            status = "failed"
        receipt: dict[str, object] = {"lane": lane, "status": status}
        if node_id == "SYSTEM-CODE-QA-V2":
            receipt.update(
                {
                    "task_count": 3,
                    "retained_losing_attempt_count": 3,
                    "operationally_qualified": False,
                }
            )
        receipt["receipt_digest"] = canonical_digest(receipt)
        receipts[node_id] = receipt
    challenger: dict[str, object] = {
        "lane": "challenger-g1",
        "status": "deferred",
        "disposition": "defer",
        "promotion_authorized": False,
    }
    challenger["receipt_digest"] = canonical_digest(challenger)
    receipts["CHALLENGER-G1"] = challenger
    fatal = [] if failed_lane is None else [f"{failed_lane}: failed"]
    cross: dict[str, object] = {
        "fatal_findings": fatal,
        "development_gaps": ["offline evidence only"],
    }
    cross["receipt_digest"] = canonical_digest(cross)
    receipts["CROSS-EXAMINE"] = cross
    for role in TOURNAMENT_ROLES:
        feedback: dict[str, object] = {"role": role}
        feedback["feedback_digest"] = canonical_digest(feedback)
        receipts[_feedback_node(role)] = feedback
    return receipts


class TournamentPlanV2Tests(unittest.TestCase):
    def test_canonical_plan_is_parallel_native_and_json_stable(self) -> None:
        plan = build_tournament_plan_v2()
        round_tripped = json.loads(json.dumps(plan))
        waves = validate_tournament_plan_v2(round_tripped)
        checked_in = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "docs/execution/dags/agent-readiness-tournament-v2/plan.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(plan, checked_in)
        self.assertEqual(30, len(plan["nodes"]))
        self.assertEqual((1, 8, 8, 1, 1, 1, 1, 8, 1), tuple(map(len, waves)))
        self.assertEqual({_role_node(role) for role in TOURNAMENT_ROLES}, set(waves[1]))
        self.assertEqual("SYSTEM-CODE-QA-V2", waves[2][-1])
        self.assertTrue(plan["policies"]["fatal_gates_are_non_compensating"])
        self.assertTrue(plan["policies"]["default_runs_canonical_full_suite"])
        self.assertFalse(plan["policies"]["challenger_promotion_authorized"])

    def test_plan_refuses_even_self_digested_semantic_changes(self) -> None:
        plan = build_tournament_plan_v2()
        plan["nodes"][0]["objective"] = "weakened"
        plan.pop("plan_digest")
        plan["plan_digest"] = canonical_digest(plan)
        with self.assertRaisesRegex(TournamentV2Error, "code-owned canonical"):
            validate_tournament_plan_v2(plan)

    def test_authority_arguments_are_an_indivisible_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            with self.assertRaisesRegex(TournamentV2Error, "supplied together"):
                run_tournament_v2(
                    Path.cwd(),
                    output,
                    authority_manifest=Path(temporary) / "authority.json",
                )
            self.assertFalse(output.exists())

    def test_run_and_verifier_reject_selected_repository_overlap(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        absent_output = repository / "tests" / "__v2_forbidden_run__"
        self.assertFalse(absent_output.exists())
        with self.assertRaisesRegex(
            TournamentV2Error, "outside the selected repository"
        ):
            run_tournament_v2(repository, absent_output)
        self.assertFalse(absent_output.exists())
        with self.assertRaisesRegex(
            TournamentV2Error, "outside the selected repository"
        ):
            verify_run_directory_v2(repository / "tests", repository=repository)

    def test_monkeypatched_v1_runner_cannot_impersonate_the_pinned_builtin(
        self,
    ) -> None:
        repository = Path(__file__).resolve().parents[1]
        inventory = v1.inventory_repository(repository)
        original = v1.run_command_receipt

        def injected(
            selected_repository: Path, argv: Sequence[str]
        ) -> tuple[dict[str, Any], str]:
            return original(selected_repository, argv)

        injected.__module__ = original.__module__
        injected.__qualname__ = original.__qualname__
        injected.__name__ = original.__name__
        try:
            v1.run_command_receipt = injected
            injected_scan = _scan_receipt(
                repository, inventory, command_runner=injected
            )
            pinned_scan_during_global_drift = _scan_receipt(
                repository, inventory, command_runner=original
            )
        finally:
            v1.run_command_receipt = original

        self.assertFalse(injected_scan["execution"]["trusted_builtin_command_runner"])
        self.assertFalse(
            pinned_scan_during_global_drift["execution"][
                "trusted_builtin_command_runner"
            ]
        )
        self.assertEqual(
            "hive_mind_os.agent_tournament:run_command_receipt",
            injected_scan["execution"]["command_runner_identity"],
        )


class TournamentVerdictV2Tests(unittest.TestCase):
    def test_one_failed_gate_quarantines_without_score_compensation(self) -> None:
        receipts = _report_receipts(failed_lane="SYSTEM-CONTROL-PLANE")
        report = _derive_report(receipts, plan_digest=canonical_digest({"plan": 2}))

        self.assertEqual("quarantine", report["court"]["disposition"])
        self.assertEqual("F", report["whole_system_grade"])
        self.assertGreater(report["role_average"], 80)
        self.assertFalse(report["court"]["promotion_authorized"])

    def test_skip_full_suite_is_incomplete_and_can_never_adopt(self) -> None:
        receipts = _report_receipts(full_status="deferred")
        report = _derive_report(receipts, plan_digest=canonical_digest({"plan": 2}))

        self.assertEqual("defer", report["court"]["disposition"])
        self.assertEqual("I", report["whole_system_grade"])

    def test_green_offline_evidence_still_routes_to_adapt(self) -> None:
        report = _derive_report(
            _report_receipts(), plan_digest=canonical_digest({"plan": 2})
        )
        self.assertEqual("adapt", report["court"]["disposition"])
        self.assertIn("not live-provider", report["qualification"])

    def test_failed_feedback_and_terminal_judgment_are_quarantined(self) -> None:
        receipts = _report_receipts()
        receipts[_feedback_node("builder")] = _generic_failure(
            _feedback_node("builder"), RuntimeError("feedback broke")
        )
        report = _derive_report(receipts, plan_digest=canonical_digest({"plan": 2}))
        self.assertEqual("quarantine", report["court"]["disposition"])
        self.assertIn("FEEDBACK-BUILDER: contract-failed", report["fatal_findings"])

        terminal = _generic_failure("CHAMPIONSHIP", RuntimeError("judge broke"))
        rendered = _render_report(terminal)
        self.assertIn("QUARANTINE", rendered)
        self.assertIn("no adoption is authorized", rendered)

    def test_deferred_independent_role_cannot_be_score_compensated(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        receipts = _report_receipts()
        receipts["SCAN-REPOSITORY"] = _scan_receipt(
            repository,
            v1.inventory_repository(repository),
            command_runner=v1.run_command_receipt,
        )
        receipts[_role_node("builder")]["court"] = {"disposition": "defer"}
        cross = _cross_examine_v2(repository, receipts)
        self.assertIn(
            "builder: independent disposition is defer", cross["fatal_findings"]
        )

    def test_feedback_executes_three_non_mutating_rethink_cycles(self) -> None:
        role = "builder"
        grade = {
            "role": role,
            "fatal_findings": [],
            "development_findings": ["arbitrary repositories remain unproven"],
            "grade_digest": canonical_digest({"grade": role}),
        }
        cross = {
            "fatal_findings": [],
            "development_gaps": ["provider quality unproven"],
            "receipt_digest": canonical_digest({"cross": 2}),
        }
        challenger = {"receipt_digest": canonical_digest({"challenger": 1})}
        feedback = _feedback_v2(role, grade, cross, challenger)

        self.assertEqual(3, feedback["cycles_executed"])
        self.assertTrue(feedback["immutable_champion"])
        self.assertFalse(feedback["promotion_authorized"])
        self.assertIn("re-scan", feedback["challenger_hypotheses"][0])
        self.assertEqual(
            feedback["cycles"][0]["output_hypotheses"],
            feedback["cycles"][1]["input_hypotheses"],
        )
        self.assertEqual("SCAN-REPOSITORY", feedback["restart_nodes"][0])

    def test_no_authority_is_a_typed_defer_not_an_implicit_pass(self) -> None:
        receipt = _authority_challenger(
            Path.cwd(),
            Path.cwd().parent,
            {},
            authority_path=None,
            authority_digest=None,
        )
        self.assertEqual("deferred", receipt["status"])
        self.assertEqual("defer", receipt["disposition"])
        self.assertFalse(receipt["authority_supplied"])
        self.assertFalse(receipt["promotion_authorized"])


class TournamentManifestV2Tests(unittest.TestCase):
    def _base(self, root: Path) -> None:
        for name in ("receipts", "transcripts", "waves"):
            (root / name).mkdir()
        (root / "events.jsonl").write_text("{}\n", encoding="utf-8")
        (root / "plan.json").write_text("{}\n", encoding="utf-8")
        (root / "report.json").write_text("{}\n", encoding="utf-8")
        (root / "report.md").write_text("report\n", encoding="utf-8")

    def test_create_only_writer_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "receipt.json"
            _write_json_create(path, {"value": 1})
            with self.assertRaisesRegex(TournamentV2Error, "create-only"):
                _write_json_create(path, {"value": 2})

    def test_manifest_binds_empty_directories_and_rejects_later_extra(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._base(root)
            _write_json_create(root / "manifest.json", _manifest(root))
            _validate_manifest(root)

            (root / "code-qa").mkdir()
            with self.assertRaisesRegex(TournamentV2Error, "directories"):
                _validate_manifest(root)

    def test_even_rehashed_unknown_top_level_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._base(root)
            (root / "unexpected.txt").write_text("not evidence\n", encoding="utf-8")
            _write_json_create(root / "manifest.json", _manifest(root))
            with self.assertRaisesRegex(TournamentV2Error, "unknown directory tree"):
                _validate_manifest(root)


class TournamentExecutableLanesV2Tests(unittest.TestCase):
    def _clone_current_snapshot(self, source: Path, repository: Path) -> None:
        clone = v1._git(
            source,
            "clone",
            "--quiet",
            "--no-hardlinks",
            str(source),
            str(repository),
        )
        self.assertEqual(0, clone.returncode, clone.stderr.decode(errors="replace"))
        v1._materialize_inventory(source, repository, v1.inventory_repository(source))
        for arguments in (
            ("config", "user.name", "Tournament V2 Test"),
            ("config", "user.email", "tournament-v2@example.invalid"),
            ("add", "--all"),
        ):
            completed = v1._git(repository, *arguments)
            self.assertEqual(
                0,
                completed.returncode,
                completed.stderr.decode(errors="replace"),
            )
        staged = v1._git(repository, "diff", "--cached", "--quiet")
        self.assertIn(staged.returncode, {0, 1})
        if staged.returncode == 1:
            committed = v1._git(
                repository,
                "commit",
                "--quiet",
                "-m",
                "sealed v2 integration snapshot",
            )
            self.assertEqual(
                0,
                committed.returncode,
                committed.stderr.decode(errors="replace"),
            )

    def test_native_and_codeqa_run_reverify_and_reject_tamper(self) -> None:
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="v2t-") as temporary:
            root = Path(temporary).resolve()
            repository = root / "r"
            run_root = root / "o"
            # Commit an exact-byte copy of the current working tree so this
            # integration path exercises the additive v2 files even before the
            # enclosing change is committed.
            self._clone_current_snapshot(source, repository)
            run_root.mkdir()
            calls: list[tuple[str, ...]] = []

            def controlled_runner(
                selected_repository: Path, argv: Sequence[str]
            ) -> tuple[dict[str, Any], str]:
                calls.append(tuple(argv))
                return v1.run_command_receipt(selected_repository, argv)

            inventory = v1.inventory_repository(repository)
            scan = _scan_receipt(
                repository, inventory, command_runner=controlled_runner
            )
            native, transcript = _run_native_dag(
                repository, run_root, scan, controlled_runner
            )
            code_qa = _run_code_qa(repository, run_root)

            self.assertEqual("passed", native["status"])
            self.assertEqual(2, native["max_observed_parallelism"])
            self.assertEqual("passed", code_qa["status"])
            self.assertEqual(1, len(calls))
            _validate_native_dag(native, repository, run_root, scan, transcript)
            _validate_code_qa(code_qa, repository, run_root)

            manifest = _manifest(run_root)
            listed_code_qa = {
                row["path"]
                for row in manifest["files"]
                if str(row["path"]).startswith("code-qa/")
            }
            actual_code_qa = {
                path.relative_to(run_root).as_posix()
                for path in (run_root / "code-qa").rglob("*")
                if path.is_file()
            }
            self.assertEqual(actual_code_qa, listed_code_qa)
            _write_json_create(run_root / "manifest.json", manifest)
            _validate_manifest(run_root)

            tampered_event = deepcopy(native)
            tampered_event["events"][0]["event_digest"] = "sha256:" + "0" * 64
            tampered_event.pop("receipt_digest")
            tampered_event["receipt_digest"] = canonical_digest(tampered_event)
            with self.assertRaisesRegex(TournamentV2Error, "event chain"):
                _validate_native_dag(
                    tampered_event, repository, run_root, scan, transcript
                )

            artifact_digest = str(native["node_receipts"][0]["artifact_digest"])
            artifact_hex = artifact_digest.removeprefix("sha256:")
            artifact_path = (
                run_root
                / "native-dag/evidence/artifacts/sha256"
                / artifact_hex[:2]
                / f"{artifact_hex}.json"
            )
            artifact_bytes = artifact_path.read_bytes()
            artifact_path.write_bytes(artifact_bytes + b"\n")
            with self.assertRaisesRegex(TournamentV2Error, "artifact"):
                _validate_native_dag(native, repository, run_root, scan, transcript)
            artifact_path.write_bytes(artifact_bytes)

            artifact_path.unlink()
            with self.assertRaisesRegex(
                TournamentV2Error, "content-addressed verification"
            ):
                _validate_native_dag(native, repository, run_root, scan, transcript)
            artifact_path.write_bytes(artifact_bytes)

            corpus_path = run_root / "code-qa/corpus-run.json"
            corpus_bytes = corpus_path.read_bytes()
            corpus_path.write_bytes(corpus_bytes + b"\n")
            with self.assertRaisesRegex(TournamentV2Error, "binding is invalid"):
                _validate_code_qa(code_qa, repository, run_root)
            corpus_path.write_bytes(corpus_bytes)

            tampered_corpus = json.loads(corpus_bytes)
            tampered_corpus["task_runs"][0]["attempts"][0]["public_outcome"][
                "stderr_digest"
            ] = "sha256:" + "f" * 64
            tampered_bytes = canonical_bytes(tampered_corpus) + b"\n"
            corpus_path.write_bytes(tampered_bytes)
            tampered_code_qa = deepcopy(code_qa)
            tampered_code_qa["corpus_run_sha256"] = (
                f"sha256:{sha256(tampered_bytes).hexdigest()}"
            )
            tampered_code_qa.pop("receipt_digest")
            tampered_code_qa["receipt_digest"] = canonical_digest(tampered_code_qa)
            with self.assertRaisesRegex(TournamentV2Error, "not reproducible"):
                _validate_code_qa(tampered_code_qa, repository, run_root)
            corpus_path.write_bytes(corpus_bytes)
            unexpected_manifest = run_root / "code-qa/manifest.json"
            unexpected_manifest.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(TournamentV2Error, "reproducible"):
                _validate_code_qa(code_qa, repository, run_root)
            unexpected_manifest.unlink()

    def test_runner_then_offline_verifier_executes_real_parallel_lanes(self) -> None:
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="v2r-") as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            run_root = root / "run"
            self._clone_current_snapshot(source, repository)
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                (str(repository / "src"), str(repository))
            )
            launcher = repository / "scripts/run_agent_tournament_v2.py"
            driver = root / "controlled-run.py"
            driver.write_text(
                """from __future__ import annotations
import json
import sys
from pathlib import Path
from hive_mind_os import agent_tournament as v1
from hive_mind_os.agent_tournament_v2 import (
    _NATIVE_DAG_TEST_MODULES,
    run_tournament_v2,
)

repository = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
native_command = v1._unittest_command(_NATIVE_DAG_TEST_MODULES)

def controlled_runner(selected_repository, argv):
    timeout = 1800 if tuple(argv) == native_command else 1
    return v1.run_command_receipt(
        selected_repository, argv, timeout_seconds=timeout
    )

result = run_tournament_v2(
    repository,
    output,
    max_workers=3,
    full_suite=False,
    command_runner=controlled_runner,
)
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
""",
                encoding="utf-8",
            )
            run = subprocess.run(
                (
                    sys.executable,
                    "-B",
                    str(driver),
                    str(repository),
                    str(run_root),
                ),
                cwd=repository,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=240,
            )
            self.assertEqual(0, run.returncode, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual("verified", result["status"])
            self.assertEqual("quarantine", result["disposition"])
            scan = json.loads(
                (run_root / "receipts/SCAN-REPOSITORY.json").read_text(encoding="utf-8")
            )
            self.assertFalse(scan["execution"]["trusted_builtin_command_runner"])
            report = json.loads((run_root / "report.json").read_text(encoding="utf-8"))
            self.assertIn(
                "SCAN-REPOSITORY: injected command runner is test-only and cannot support an authoritative verdict",
                report["fatal_findings"],
            )
            native = json.loads(
                (run_root / "receipts/SYSTEM-NATIVE-DAG.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                "repair_required", native["semantic_outcomes"]["steward"]["readiness"]
            )
            self.assertEqual(
                "defer", native["semantic_outcomes"]["optimizer"]["recommendation"]
            )
            wave_records = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((run_root / "waves").glob("*.json"))
            ]
            self.assertTrue(
                all(
                    row["observed_peak_concurrency"] >= 2
                    for row in wave_records
                    if row["parallel"]
                )
            )

            verify = subprocess.run(
                (
                    sys.executable,
                    "-B",
                    str(launcher),
                    "verify",
                    "--repository",
                    str(repository),
                    "--run-dir",
                    str(run_root),
                ),
                cwd=repository,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(0, verify.returncode, verify.stderr)
            self.assertEqual("verified", json.loads(verify.stdout)["status"])

            parallel_wave_path = next(
                path
                for path in sorted((run_root / "waves").glob("*.json"))
                if json.loads(path.read_text(encoding="utf-8"))["parallel"]
            )
            parallel_wave = json.loads(parallel_wave_path.read_text(encoding="utf-8"))
            parallel_wave["observed_peak_concurrency"] = 1
            parallel_wave.pop("wave_digest")
            parallel_wave["wave_digest"] = canonical_digest(parallel_wave)
            parallel_wave_path.write_text(
                json.dumps(parallel_wave, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            (run_root / "manifest.json").unlink()
            _write_json_create(run_root / "manifest.json", _manifest(run_root))
            rejected = subprocess.run(
                (
                    sys.executable,
                    "-B",
                    str(launcher),
                    "verify",
                    "--repository",
                    str(repository),
                    "--run-dir",
                    str(run_root),
                ),
                cwd=repository,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(1, rejected.returncode)
            self.assertIn("wave concurrency", rejected.stderr)

    def test_authority_only_run_reverifies_and_rejects_proposal_escape(self) -> None:
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="v2a-") as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            run_root = root / "run"
            authority_path = root / "authority.json"
            self._clone_current_snapshot(source, repository)
            run_root.mkdir()
            champions = {
                role.value: prompt_digest(generation_zero_prompt(ROLE_CONTRACTS[role]))
                for role in Role
            }
            binding = capture_repository_binding(repository)
            now = datetime.now(UTC)
            authority = _manifest_document(
                champions,
                repository={
                    "head_commit": binding.head_commit,
                    "tree_oid": binding.tree_oid,
                },
                validity={
                    "not_before": (now - timedelta(days=1)).isoformat(),
                    "expires_at": (now + timedelta(days=1)).isoformat(),
                },
            )
            authority_path.write_bytes(canonical_bytes(authority) + b"\n")
            receipts = _report_receipts()
            receipts["SCAN-REPOSITORY"] = _scan_receipt(
                repository,
                v1.inventory_repository(repository),
                command_runner=v1.run_command_receipt,
            )
            challenger = _authority_challenger(
                repository,
                run_root,
                receipts,
                authority_path=authority_path,
                authority_digest=str(authority["manifest_digest"]),
            )
            persisted = json.loads(canonical_bytes(challenger).decode("utf-8"))
            _validate_challenger(
                persisted,
                repository,
                run_root,
                receipts,
                authority_manifest=authority_path,
                authority_digest=str(authority["manifest_digest"]),
            )

            escaped = deepcopy(persisted)
            escaped["retained_proposal_records"][0]["path"] = str(
                authority_path.resolve()
            )
            escaped.pop("receipt_digest")
            escaped["receipt_digest"] = canonical_digest(escaped)
            with self.assertRaisesRegex(TournamentV2Error, "proposal row"):
                _validate_challenger(
                    escaped,
                    repository,
                    run_root,
                    receipts,
                    authority_manifest=authority_path,
                    authority_digest=str(authority["manifest_digest"]),
                )

    def test_authority_inside_git_administrative_state_is_rejected(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        inventory = v1.inventory_repository(repository)
        git_directory = Path(str(inventory["git_directory"]))
        authority_path = git_directory / "HEAD"
        self.assertTrue(authority_path.is_file())
        receipts = {
            "SCAN-REPOSITORY": {"inventory": inventory},
        }
        with tempfile.TemporaryDirectory(prefix="v2-git-authority-") as temporary:
            with self.assertRaisesRegex(
                (TournamentV2Error, v1.TournamentError),
                "overlaps .*git.* authority",
            ):
                _authority_challenger(
                    repository,
                    Path(temporary),
                    receipts,
                    authority_path=authority_path,
                    authority_digest="sha256:" + "a" * 64,
                )


if __name__ == "__main__":
    unittest.main()
