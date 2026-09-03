from __future__ import annotations

import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest import mock

from hive_mind_os.dag_executor import ExecutionJournal
from hive_mind_os.portable_plan import NonRepositorySubject, SubjectBinding
from hive_mind_os.runtime_contracts import raw_sha256
from hive_mind_os.subject_execution import (
    SubjectExecutionError,
    SubjectExecutionMode,
    SubjectExecutionService,
)
from tests.test_dag_standard_product import STANDARD, compiler_plan


class SubjectExecutionTests(unittest.TestCase):
    def test_read_only_inspection_works_with_absolute_inputs_and_no_state(self) -> None:
        plan = compiler_plan()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            standard_path = root / "standard.md"
            state_path = root / "missing" / "dag-execution.sqlite3"
            plan_path.write_bytes(plan.canonical_bytes())
            standard_path.write_bytes(STANDARD)
            service = SubjectExecutionService()

            inspection = service.validate_files(
                plan_path=plan_path.resolve(),
                standard_path=standard_path.resolve(),
                expected_plan_digest=plan.digest(),
                mode=SubjectExecutionMode.REPOSITORY,
            )
            self.assertEqual(plan.digest(), inspection.plan_digest)
            self.assertEqual(
                4,
                len(
                    service.rounds(
                        plan_path=plan_path.resolve(),
                        standard_path=standard_path.resolve(),
                        expected_plan_digest=plan.digest(),
                        mode=SubjectExecutionMode.REPOSITORY,
                    )
                ),
            )
            self.assertFalse(
                service.status(
                    state_path=state_path.resolve(),
                    plan_path=plan_path.resolve(),
                    expected_plan_digest=plan.digest(),
                )["state_present"]
            )
            self.assertFalse(state_path.parent.exists())

    def test_build_writes_only_explicit_canonical_output(self) -> None:
        plan = compiler_plan()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proposal = root / "proposal.json"
            standard = root / "standard.md"
            output = root / "sealed.json"
            proposal.write_bytes(plan.canonical_bytes())
            standard.write_bytes(STANDARD)
            service = SubjectExecutionService()
            service.build_file(
                plan_path=proposal.resolve(),
                standard_path=standard.resolve(),
                expected_plan_digest=plan.digest(),
                output_path=output.resolve(),
                mode=SubjectExecutionMode.REPOSITORY,
            )
            self.assertEqual(plan.canonical_bytes(), output.read_bytes())
            with self.assertRaisesRegex(SubjectExecutionError, "already exists"):
                service.build_file(
                    plan_path=proposal.resolve(),
                    standard_path=standard.resolve(),
                    expected_plan_digest=plan.digest(),
                    output_path=output.resolve(),
                    mode=SubjectExecutionMode.REPOSITORY,
                )

            raced_output = root / "raced.json"
            with mock.patch(
                "hive_mind_os.subject_execution.os.link",
                side_effect=FileExistsError("synthetic target race"),
            ):
                with self.assertRaisesRegex(SubjectExecutionError, "already exists"):
                    service.build_file(
                        plan_path=proposal.resolve(),
                        standard_path=standard.resolve(),
                        expected_plan_digest=plan.digest(),
                        output_path=raced_output.resolve(),
                        mode=SubjectExecutionMode.REPOSITORY,
                    )
            self.assertFalse(raced_output.exists())
            self.assertFalse(
                (root / f".{raced_output.name}.{os.getpid()}.tmp").exists()
            )

    def test_build_preserves_unowned_temp_and_concurrent_builds_clean_only_their_own(self) -> None:
        plan = compiler_plan()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proposal = root / "proposal.json"
            standard = root / "standard.md"
            output = root / "sealed.json"
            proposal.write_bytes(plan.canonical_bytes())
            standard.write_bytes(STANDARD)
            unowned = root / f".{output.name}.{os.getpid()}.tmp"
            unowned.write_bytes(b"unowned sentinel")
            service = SubjectExecutionService()
            entered = threading.Event()
            release = threading.Event()
            original_link = os.link
            call_lock = threading.Lock()
            link_calls = 0

            def hold_first_link(source, destination):
                nonlocal link_calls
                with call_lock:
                    link_calls += 1
                    first = link_calls == 1
                if first:
                    entered.set()
                    self.assertTrue(release.wait(timeout=5))
                return original_link(source, destination)

            def build():
                return service.build_file(
                    plan_path=proposal.resolve(),
                    standard_path=standard.resolve(),
                    expected_plan_digest=plan.digest(),
                    output_path=output.resolve(),
                    mode=SubjectExecutionMode.REPOSITORY,
                )

            with mock.patch(
                "hive_mind_os.subject_execution.os.link",
                side_effect=hold_first_link,
            ):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(build)
                    self.assertTrue(entered.wait(timeout=5))
                    second = pool.submit(build)
                    second_result = None
                    second_error = None
                    try:
                        second_result = second.result(timeout=5)
                    except SubjectExecutionError as error:
                        second_error = error
                    release.set()
                    first_result = None
                    first_error = None
                    try:
                        first_result = first.result(timeout=5)
                    except SubjectExecutionError as error:
                        first_error = error

            self.assertEqual(1, sum(item is not None for item in (first_result, second_result)))
            self.assertEqual(1, sum(item is not None for item in (first_error, second_error)))
            self.assertEqual(plan.canonical_bytes(), output.read_bytes())
            self.assertEqual(b"unowned sentinel", unowned.read_bytes())
            self.assertEqual([unowned], list(root.glob(f".{output.name}.*.tmp")))

    def test_non_repository_modes_are_first_class_and_mismatch_fails(self) -> None:
        plan = compiler_plan()
        subject = SubjectBinding.for_non_repository(
            NonRepositorySubject(
                "research-artifact",
                raw_sha256(b"locator"),
                raw_sha256(b"version"),
            )
        )
        plan = replace(plan, subject=subject)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            standard_path = root / "standard.md"
            plan_path.write_bytes(plan.canonical_bytes())
            standard_path.write_bytes(STANDARD)
            service = SubjectExecutionService()
            result = service.validate_files(
                plan_path=plan_path.resolve(),
                standard_path=standard_path.resolve(),
                expected_plan_digest=plan.digest(),
                mode=SubjectExecutionMode.RESEARCH_ARTIFACT,
            )
            self.assertEqual("non_repository", result.subject_kind)
            with self.assertRaisesRegex(SubjectExecutionError, "non-repository"):
                service.validate_files(
                    plan_path=plan_path.resolve(),
                    standard_path=standard_path.resolve(),
                    expected_plan_digest=plan.digest(),
                    mode=SubjectExecutionMode.REPOSITORY,
                )

    def test_status_filters_exact_plan_and_subject_and_rejects_named_mismatch(
        self,
    ) -> None:
        plan = compiler_plan()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            state_path = root / "dag-execution.sqlite3"
            plan_path.write_bytes(plan.canonical_bytes())
            matching_run = "sha256:" + "a" * 64
            unrelated_run = "sha256:" + "b" * 64
            initialized = {
                "plan_digest": plan.digest(),
                "generation_id": "sha256:" + "c" * 64,
                "subject_id": plan.subject.subject_id,
                "compilation_digest": "sha256:" + "d" * 64,
                "node_ids": ["node-a"],
            }
            with ExecutionJournal(state_path) as journal:
                journal.append(matching_run, "run.initialized", initialized)
                journal.append(
                    unrelated_run,
                    "run.initialized",
                    {
                        **initialized,
                        "plan_digest": "sha256:" + "e" * 64,
                        "subject_id": "sha256:" + "f" * 64,
                    },
                )

            result = SubjectExecutionService.status(
                state_path=state_path.resolve(),
                plan_path=plan_path.resolve(),
                expected_plan_digest=plan.digest(),
            )

            self.assertEqual([matching_run], [item["run_id"] for item in result["runs"]])
            self.assertEqual(plan.digest(), result["binding"]["plan_digest"])
            self.assertEqual(plan.subject.subject_id, result["binding"]["subject_id"])
            with self.assertRaisesRegex(SubjectExecutionError, "another plan"):
                SubjectExecutionService.status(
                    state_path=state_path.resolve(),
                    plan_path=plan_path.resolve(),
                    expected_plan_digest=plan.digest(),
                    run_id=unrelated_run,
                )
            with self.assertRaisesRegex(SubjectExecutionError, "does not match"):
                SubjectExecutionService.status(
                    state_path=state_path.resolve(),
                    plan_path=plan_path.resolve(),
                    expected_plan_digest="sha256:" + "0" * 64,
                )

    def test_graph_rejects_plan_substitution_after_validation(self) -> None:
        plan = compiler_plan()
        substituted = replace(plan, plan_id="substituted-plan")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan_path = root / "plan.json"
            standard_path = root / "standard.md"
            plan_path.write_bytes(plan.canonical_bytes())
            standard_path.write_bytes(STANDARD)
            service = SubjectExecutionService()
            validate = service.validate_files

            def validate_then_substitute(**arguments):
                inspection = validate(**arguments)
                plan_path.write_bytes(substituted.canonical_bytes())
                return inspection

            with mock.patch.object(
                service, "validate_files", side_effect=validate_then_substitute
            ):
                with self.assertRaisesRegex(
                    SubjectExecutionError, "changed after validation"
                ):
                    service.graph(
                        plan_path=plan_path.resolve(),
                        standard_path=standard_path.resolve(),
                        expected_plan_digest=plan.digest(),
                        mode=SubjectExecutionMode.REPOSITORY,
                    )

    def test_unconfigured_execution_fails_without_treating_a_file_as_authority(
        self,
    ) -> None:
        with self.assertRaisesRegex(SubjectExecutionError, "EXTERNAL_RUNTIME_REQUIRED"):
            SubjectExecutionService().execute(object())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
