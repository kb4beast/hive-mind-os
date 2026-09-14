from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from hive_mind_os.cohort_assurance import (
    CohortAssuranceError,
    CohortAssuranceRuntime,
    RepairDirective,
    TerminalAssessment,
    TerminalEvidence,
    convergence_candidate_digest,
)
from hive_mind_os.cohort_journal import CohortJournalEventKind, FileCohortJournalStore
from hive_mind_os.cohort_policy import CohortExecutionPolicy, EffectClass
from hive_mind_os.cohort_runtime import (
    CohortRunStatus,
    ConvergenceResult,
    PackageRunResult,
    PackageRunState,
    VerificationResult,
)
from hive_mind_os.outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage


def _graph() -> OutcomeGraphSpec:
    return OutcomeGraphSpec(
        (
            OutcomeWorkPackage(
                (package_id := "a"), (package_id,), allowed_paths=("a",)
            ),
            OutcomeWorkPackage(
                (package_id := "b"), (package_id,), allowed_paths=("b",)
            ),
        ),
        base_snapshot="base",
        maximum_concurrent=2,
    )


def _evidence(suffix: str) -> TerminalEvidence:
    digest = convergence_candidate_digest(ConvergenceResult(True, {}))
    return TerminalEvidence(
        digest,
        "builder-cohort",
        "curator-terminal",
        (f"review:{suffix}:{digest}",),
        (f"aggregate:{suffix}:{digest}",),
        (f"verification:{suffix}:{digest}",),
    )


class CohortAssuranceTests(unittest.TestCase):
    def test_failed_cohort_gets_one_parallel_repair_and_one_reverification(
        self,
    ) -> None:
        runtime = CohortAssuranceRuntime(CohortExecutionPolicy(max_parallel_packages=2))
        convergence_calls: list[tuple[str, ...]] = []
        assessment_calls: list[str] = []
        repair_directives: list[int] = []

        def execute(package, _kickoff, _dependencies):
            state = (
                PackageRunState.FAILED
                if package.package_id == "a"
                else PackageRunState.SUCCEEDED
            )
            return PackageRunResult(package.package_id, state, {})

        def converge(_kickoff, results):
            convergence_calls.append(tuple(result.state.value for result in results))
            accepted = all(
                result.state is PackageRunState.SUCCEEDED for result in results
            )
            return ConvergenceResult(accepted, {})

        def assess(_kickoff, _results, convergence):
            suffix = str(len(assessment_calls))
            assessment_calls.append(suffix)
            return TerminalAssessment(
                VerificationResult(convergence.accepted, (f"check:{suffix}",)),
                _evidence(suffix),
            )

        def repair(package, _kickoff, _dependencies, directive):
            repair_directives.append(id(directive))
            return PackageRunResult(package.package_id, PackageRunState.SUCCEEDED, {})

        result = runtime.execute(
            graph=_graph(),
            run_id="run",
            kickoff_context={},
            execute_package=execute,
            converge=converge,
            assess=assess,
            plan_repair=lambda _result: RepairDirective(("a", "b"), "repair together"),
            execute_repair=repair,
        )

        self.assertEqual(result.status, CohortRunStatus.SUCCEEDED)
        self.assertTrue(result.repair_attempted)
        self.assertEqual(len(convergence_calls), 2)
        self.assertEqual(len(assessment_calls), 2)
        self.assertEqual(len(set(repair_directives)), 1)

    def test_failed_repair_is_terminal_without_an_iterative_loop(self) -> None:
        runtime = CohortAssuranceRuntime(CohortExecutionPolicy())
        repair_calls: list[str] = []

        result = runtime.execute(
            graph=_graph(),
            run_id="run",
            kickoff_context={},
            execute_package=lambda package, _kickoff, _dependencies: PackageRunResult(
                package.package_id, PackageRunState.FAILED, {}
            ),
            converge=lambda _kickoff, _results: ConvergenceResult(False, {}),
            assess=lambda _kickoff, _results, _convergence: TerminalAssessment(
                VerificationResult(False, ("failed",)), _evidence("failed")
            ),
            plan_repair=lambda _result: RepairDirective(("a",), "try once"),
            execute_repair=lambda package, _kickoff, _dependencies, _directive: (
                repair_calls.append(package.package_id)
                or PackageRunResult(package.package_id, PackageRunState.FAILED, {})
            ),
        )

        self.assertEqual(result.status, CohortRunStatus.FAILED)
        self.assertEqual(repair_calls, ["a"])

    def test_untyped_or_incomplete_terminal_evidence_fails_closed(self) -> None:
        runtime = CohortAssuranceRuntime(CohortExecutionPolicy())

        result = runtime.execute(
            graph=_graph(),
            run_id="run",
            kickoff_context={},
            execute_package=lambda package, _kickoff, _dependencies: PackageRunResult(
                package.package_id, PackageRunState.SUCCEEDED, {}
            ),
            converge=lambda _kickoff, _results: ConvergenceResult(True, {}),
            assess=lambda _kickoff, _results, _convergence: object(),  # type: ignore[arg-type,return-value]
            plan_repair=lambda _result: None,
            execute_repair=lambda package, _kickoff, _dependencies, _directive: (
                PackageRunResult(package.package_id, PackageRunState.SUCCEEDED, {})
            ),
        )

        self.assertEqual(result.status, CohortRunStatus.FAILED)
        self.assertIsNone(result.evidence)
        with self.assertRaises(CohortAssuranceError):
            TerminalEvidence("bad", "", "", (), (), ())

        with self.assertRaisesRegex(CohortAssuranceError, "independent"):
            TerminalEvidence(
                "sha256:" + "a" * 64,
                "same-agent",
                "same-agent",
                ("review:sha256:" + "a" * 64,),
                ("aggregate:sha256:" + "a" * 64,),
                ("verification:sha256:" + "a" * 64,),
            )

    def test_terminal_evidence_must_bind_the_exact_convergence_output(self) -> None:
        runtime = CohortAssuranceRuntime(CohortExecutionPolicy())
        mismatched = TerminalEvidence(
            "sha256:" + "b" * 64,
            "builder",
            "curator",
            ("review:sha256:" + "b" * 64,),
            ("aggregate:sha256:" + "b" * 64,),
            ("verification:sha256:" + "b" * 64,),
        )
        result = runtime.execute(
            graph=_graph(),
            run_id="bound",
            kickoff_context={},
            execute_package=lambda package, _kickoff, _dependencies: PackageRunResult(
                package.package_id, PackageRunState.SUCCEEDED, {}
            ),
            converge=lambda _kickoff, _results: ConvergenceResult(
                True, {"candidate": "actual"}
            ),
            assess=lambda _kickoff, _results, _convergence: TerminalAssessment(
                VerificationResult(True, ("check",)), mismatched
            ),
            plan_repair=lambda _result: None,
            execute_repair=lambda package, _kickoff, _dependencies, _directive: (
                PackageRunResult(package.package_id, PackageRunState.SUCCEEDED, {})
            ),
        )
        self.assertEqual(result.status, CohortRunStatus.FAILED)
        self.assertIn("does not bind", result.verification.message)

    def test_repair_and_terminal_evidence_resume_without_reexecution(self) -> None:
        with TemporaryDirectory() as directory:
            journal = FileCohortJournalStore(directory)
            runtime = CohortAssuranceRuntime(CohortExecutionPolicy(), journal)
            calls = {"execute": 0, "repair": 0, "assess": 0}

            def execute(package, _kickoff, _dependencies):
                calls["execute"] += 1
                state = (
                    PackageRunState.FAILED
                    if package.package_id == "a"
                    else PackageRunState.SUCCEEDED
                )
                return PackageRunResult(package.package_id, state, {})

            def assess(_kickoff, _results, convergence):
                calls["assess"] += 1
                return TerminalAssessment(
                    VerificationResult(convergence.accepted, ("terminal",)),
                    _evidence(str(calls["assess"])),
                )

            def repair(package, _kickoff, _dependencies, _directive):
                calls["repair"] += 1
                return PackageRunResult(
                    package.package_id, PackageRunState.SUCCEEDED, {}
                )

            result = runtime.execute(
                graph=_graph(),
                run_id="durable",
                kickoff_context={},
                execute_package=execute,
                converge=lambda _kickoff, results: ConvergenceResult(
                    all(item.state is PackageRunState.SUCCEEDED for item in results),
                    {},
                ),
                assess=assess,
                plan_repair=lambda _result: RepairDirective(("a",), "repair once"),
                execute_repair=repair,
            )
            self.assertEqual(result.status, CohortRunStatus.SUCCEEDED)
            before = dict(calls)
            resumed = CohortAssuranceRuntime(CohortExecutionPolicy(), journal).execute(
                graph=_graph(),
                run_id="durable",
                kickoff_context={},
                execute_package=execute,
                converge=lambda _kickoff, _results: (_ for _ in ()).throw(
                    AssertionError("convergence reran")
                ),
                assess=assess,
                plan_repair=lambda _result: (_ for _ in ()).throw(
                    AssertionError("repair planning reran")
                ),
                execute_repair=repair,
            )
            self.assertEqual(resumed.status, CohortRunStatus.SUCCEEDED)
            self.assertTrue(resumed.repair_attempted)
            self.assertEqual(resumed, result)
            self.assertEqual(resumed.initial.status, CohortRunStatus.FAILED)
            self.assertEqual(calls, before)
            kinds = tuple(event.kind for event in journal.events("durable"))
            self.assertEqual(kinds.count(CohortJournalEventKind.REPAIR_ATTEMPT), 1)
            self.assertEqual(kinds.count(CohortJournalEventKind.REPAIR_RESULT), 1)
            self.assertEqual(kinds.count(CohortJournalEventKind.RUN_COMPLETED), 1)

    def test_interrupted_repair_consumes_the_only_wave_without_repeating_effects(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            journal = FileCohortJournalStore(directory)
            runtime = CohortAssuranceRuntime(CohortExecutionPolicy(), journal)
            repairs: list[str] = []

            def assess(_kickoff, _results, _convergence):
                return TerminalAssessment(
                    VerificationResult(False, ("failed",)), _evidence("interrupted")
                )

            def interrupt(package, _kickoff, _dependencies, _directive):
                repairs.append(package.package_id)
                raise KeyboardInterrupt("simulated process interruption")

            with self.assertRaises(KeyboardInterrupt):
                runtime.execute(
                    graph=_graph(),
                    run_id="interrupted-repair",
                    kickoff_context={},
                    execute_package=lambda package, _kickoff, _dependencies: (
                        PackageRunResult(package.package_id, PackageRunState.FAILED, {})
                    ),
                    converge=lambda _kickoff, _results: ConvergenceResult(False, {}),
                    assess=assess,
                    plan_repair=lambda _result: RepairDirective(("a",), "once only"),
                    execute_repair=interrupt,
                )
            self.assertEqual(repairs, ["a"])

            resumed = CohortAssuranceRuntime(CohortExecutionPolicy(), journal).execute(
                graph=_graph(),
                run_id="interrupted-repair",
                kickoff_context={},
                execute_package=lambda package, _kickoff, _dependencies: (
                    PackageRunResult(package.package_id, PackageRunState.SUCCEEDED, {})
                ),
                converge=lambda _kickoff, _results: ConvergenceResult(False, {}),
                assess=assess,
                plan_repair=lambda _result: (_ for _ in ()).throw(
                    AssertionError("repair was planned twice")
                ),
                execute_repair=interrupt,
            )
            self.assertEqual(resumed.status, CohortRunStatus.FAILED)
            self.assertEqual(repairs, ["a"])
            kinds = tuple(event.kind for event in journal.events("interrupted-repair"))
            self.assertEqual(kinds.count(CohortJournalEventKind.REPAIR_ATTEMPT), 1)
            self.assertEqual(kinds.count(CohortJournalEventKind.REPAIR_RESULT), 0)
            self.assertEqual(kinds.count(CohortJournalEventKind.RUN_COMPLETED), 1)

    def test_repair_cannot_bypass_a_hard_effect_gate(self) -> None:
        runtime = CohortAssuranceRuntime(CohortExecutionPolicy())

        with self.assertRaisesRegex(CohortAssuranceError, "hard-gated"):
            runtime.execute(
                graph=_graph(),
                run_id="run",
                kickoff_context={},
                execute_package=lambda package, _kickoff, _dependencies: (
                    PackageRunResult(package.package_id, PackageRunState.SUCCEEDED, {})
                ),
                converge=lambda _kickoff, _results: ConvergenceResult(False, {}),
                assess=lambda _kickoff, _results, _convergence: TerminalAssessment(
                    VerificationResult(False, ("failed",)), _evidence("blocked")
                ),
                plan_repair=lambda _result: RepairDirective(("a",), "bypass"),
                execute_repair=lambda package, _kickoff, _dependencies, _directive: (
                    PackageRunResult(package.package_id, PackageRunState.SUCCEEDED, {})
                ),
                effect_classes={"a": EffectClass.DEPLOYMENT},
            )

    def test_repair_wave_must_be_conflict_and_dependency_free(self) -> None:
        runtime = CohortAssuranceRuntime(CohortExecutionPolicy())
        graph = OutcomeGraphSpec(
            (
                OutcomeWorkPackage("a", ("a",), allowed_paths=("shared",)),
                OutcomeWorkPackage("b", ("b",), allowed_paths=("shared",)),
            ),
            base_snapshot="base",
            maximum_concurrent=1,
        )
        # The graph compiler itself rejects unordered shared writers, so use a
        # dependency to make the base graph valid; the repair wave still rejects
        # running them together.
        graph = OutcomeGraphSpec(
            (
                graph.packages[0],
                OutcomeWorkPackage(
                    "b", ("b",), dependencies=("a",), allowed_paths=("shared",)
                ),
            ),
            base_snapshot="base",
            maximum_concurrent=1,
        )
        with self.assertRaisesRegex(CohortAssuranceError, "dependency-related"):
            runtime.execute(
                graph=graph,
                run_id="run",
                kickoff_context={},
                execute_package=lambda package, _kickoff, _dependencies: (
                    PackageRunResult(package.package_id, PackageRunState.FAILED, {})
                ),
                converge=lambda _kickoff, _results: ConvergenceResult(False, {}),
                assess=lambda _kickoff, _results, _convergence: TerminalAssessment(
                    VerificationResult(False, ("failed",)), _evidence("conflict")
                ),
                plan_repair=lambda _result: RepairDirective(("a", "b"), "together"),
                execute_repair=lambda package, _kickoff, _dependencies, _directive: (
                    PackageRunResult(package.package_id, PackageRunState.SUCCEEDED, {})
                ),
            )


if __name__ == "__main__":
    unittest.main()
