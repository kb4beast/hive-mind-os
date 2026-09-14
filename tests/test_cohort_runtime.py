from __future__ import annotations

import threading
import unittest
from typing import Any, Mapping

from hive_mind_os.cohort_policy import (
    CohortExecutionMode,
    CohortExecutionPolicy,
    EffectClass,
)
from hive_mind_os.cohort_runtime import (
    CohortRunStatus,
    CohortRuntime,
    ConvergenceResult,
    PackageRunResult,
    PackageRunState,
    VerificationResult,
)
from hive_mind_os.outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage


def package(
    package_id: str, *dependencies: str, lock: str | None = None
) -> OutcomeWorkPackage:
    return OutcomeWorkPackage(
        package_id,
        (f"outcome-{package_id}",),
        dependencies=dependencies,
        semantic_locks=() if lock is None else (lock,),
    )


class CohortRuntimeTests(unittest.TestCase):
    def runtime(self, maximum: int = 8) -> CohortRuntime:
        return CohortRuntime(CohortExecutionPolicy(CohortExecutionMode.COHORT, maximum))

    def test_fans_out_with_one_shared_kickoff_and_one_terminal_round(self) -> None:
        graph = OutcomeGraphSpec(
            (package("a"), package("b"), package("c", "a"), package("d", "b")),
            "sha256:" + "1" * 64,
            maximum_concurrent=4,
        )
        roots_started = threading.Barrier(2)
        kickoff_ids: set[int] = set()
        convergence_calls = 0
        verification_calls = 0

        def execute(
            item: OutcomeWorkPackage,
            kickoff: Any,
            dependencies: Mapping[str, PackageRunResult],
        ) -> PackageRunResult:
            kickoff_ids.add(id(kickoff))
            if item.package_id in {"a", "b"}:
                roots_started.wait(timeout=2)
            self.assertEqual(set(item.dependencies), set(dependencies))
            return PackageRunResult(
                item.package_id,
                PackageRunState.SUCCEEDED,
                {"candidate": item.package_id},
            )

        def converge(kickoff: Any, results: Any) -> ConvergenceResult:
            nonlocal convergence_calls
            convergence_calls += 1
            return ConvergenceResult(True, {"count": len(results)})

        def verify(kickoff: Any, results: Any, convergence: Any) -> VerificationResult:
            nonlocal verification_calls
            verification_calls += 1
            return VerificationResult(True, ("focused-tests",))

        result = self.runtime().execute(
            graph=graph,
            run_id="RUN-1",
            kickoff_context={"objective": "implement end to end", "items": [1, 2]},
            execute_package=execute,
            converge=converge,
            verify=verify,
        )

        self.assertIs(result.status, CohortRunStatus.SUCCEEDED)
        self.assertEqual(1, len(kickoff_ids))
        self.assertEqual(1, convergence_calls)
        self.assertEqual(1, verification_calls)
        self.assertGreaterEqual(result.max_parallelism, 2)
        self.assertEqual({"a", "b"}, set(result.dispatch_batches[0]))

    def test_releases_downstream_work_without_waiting_for_a_whole_wave(self) -> None:
        graph = OutcomeGraphSpec(
            (package("fast"), package("slow"), package("after-fast", "fast")),
            "sha256:" + "2" * 64,
            maximum_concurrent=2,
        )
        slow_release = threading.Event()
        downstream_started = threading.Event()

        def execute(item: OutcomeWorkPackage, *_: Any) -> PackageRunResult:
            if item.package_id == "slow":
                slow_release.wait(timeout=2)
            if item.package_id == "after-fast":
                downstream_started.set()
                slow_release.set()
            return PackageRunResult(item.package_id, PackageRunState.SUCCEEDED, {})

        result = self.runtime().execute(
            graph=graph,
            run_id="RUN-2",
            kickoff_context={},
            execute_package=execute,
            converge=lambda *_: ConvergenceResult(True, {}),
            verify=lambda *_: VerificationResult(True),
        )

        self.assertTrue(downstream_started.is_set())
        self.assertIs(result.status, CohortRunStatus.SUCCEEDED)

    def test_failure_blocks_dependents_but_not_independent_work(self) -> None:
        graph = OutcomeGraphSpec(
            (package("bad"), package("independent"), package("dependent", "bad")),
            "sha256:" + "3" * 64,
            maximum_concurrent=3,
        )
        executed: list[str] = []

        def execute(item: OutcomeWorkPackage, *_: Any) -> PackageRunResult:
            executed.append(item.package_id)
            if item.package_id == "bad":
                raise RuntimeError("boom")
            return PackageRunResult(item.package_id, PackageRunState.SUCCEEDED, {})

        result = self.runtime().execute(
            graph=graph,
            run_id="RUN-3",
            kickoff_context={},
            execute_package=execute,
            converge=lambda *_: ConvergenceResult(True, {}),
            verify=lambda *_: VerificationResult(True),
        )

        self.assertEqual({"bad", "independent"}, set(executed))
        self.assertIs(
            result.package("dependent").state, PackageRunState.BLOCKED_DEPENDENCY
        )
        self.assertIs(result.status, CohortRunStatus.FAILED)

    def test_kickoff_is_detached_and_immutable(self) -> None:
        graph = OutcomeGraphSpec((package("only"),), "sha256:" + "4" * 64)
        source = {"nested": {"values": [1]}}

        def execute(
            item: OutcomeWorkPackage, kickoff: Any, *_: Any
        ) -> PackageRunResult:
            source["nested"]["values"].append(2)  # type: ignore[index,union-attr]
            with self.assertRaises(TypeError):
                kickoff.context["new"] = True
            self.assertEqual((1,), kickoff.context["nested"]["values"])
            return PackageRunResult(item.package_id, PackageRunState.SUCCEEDED, {})

        result = self.runtime().execute(
            graph=graph,
            run_id="RUN-4",
            kickoff_context=source,
            execute_package=execute,
            converge=lambda *_: ConvergenceResult(True, {}),
            verify=lambda *_: VerificationResult(True),
        )
        self.assertIs(result.status, CohortRunStatus.SUCCEEDED)

    def test_policy_capacity_and_hard_effect_boundary_are_enforced_up_front(
        self,
    ) -> None:
        graph = OutcomeGraphSpec(
            (package("routine"), package("deployment")),
            "sha256:" + "5" * 64,
            maximum_concurrent=8,
        )
        executed: list[str] = []

        def execute(item: OutcomeWorkPackage, *_: Any) -> PackageRunResult:
            executed.append(item.package_id)
            return PackageRunResult(item.package_id, PackageRunState.SUCCEEDED, {})

        result = self.runtime(maximum=1).execute(
            graph=graph,
            run_id="RUN-5",
            kickoff_context={},
            execute_package=execute,
            converge=lambda *_: ConvergenceResult(True, {}),
            verify=lambda *_: VerificationResult(True),
            effect_classes={"deployment": EffectClass.DEPLOYMENT},
        )

        self.assertEqual(["routine"], executed)
        self.assertEqual(1, result.max_parallelism)
        self.assertIs(
            result.package("deployment").state, PackageRunState.BLOCKED_POLICY
        )
        self.assertIs(result.status, CohortRunStatus.BLOCKED)

    def test_strict_policy_stays_on_existing_runtime(self) -> None:
        with self.assertRaisesRegex(ValueError, "existing strict runtime"):
            CohortRuntime(CohortExecutionPolicy())


if __name__ == "__main__":
    unittest.main()
